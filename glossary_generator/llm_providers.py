"""
llm_providers.py — provider abstraction for the LLM agents.

The app was Ollama-only. Every agent (enrich, AI suggest, QA, categorize,
Suggest tags, policy hints, duplicate adjudication, expertise, domain) funnels
through llm._complete / llm._complete_json, so this module is all that is
needed to also reach the hosted providers: it exposes ONE `complete()` that
speaks Ollama, Anthropic, OpenAI, Azure OpenAI, or Google Gemini.

Credentials are session-only by design. A key set from the Settings page lives
in this process's memory and is NEVER written to settings.json — so the State
snapshot (which zips settings.json) can be shared without leaking billing
credentials. Persist a key by exporting the provider's environment variable
instead; the resolution order is session override -> environment.

Each hosted provider uses its own official SDK, imported lazily so the app runs
unchanged when they aren't installed (same pattern as boto3 for MinIO):
    pip install anthropic          # Anthropic
    pip install openai             # OpenAI *and* Azure OpenAI
    pip install google-genai       # Google Gemini
"""
from __future__ import annotations

import json
import os
import re

# --------------------------------------------------------------------------
# Provider catalog. `models` are SUGGESTIONS for the Settings dropdown, never a
# whitelist — hosted vendors add and retire ids on their own schedule, so the UI
# always allows a custom id and nothing here rejects one.
# --------------------------------------------------------------------------
PROVIDERS = {
    "ollama": {
        "label": "Ollama (local)",
        "kind": "local",
        "env": None,
        "package": None,
        "default_model": "llama3.2:3b",
        "models": [],                       # discovered live from /api/tags
        "needs": [],
    },
    "anthropic": {
        "label": "Anthropic",
        "kind": "cloud",
        "env": "ANTHROPIC_API_KEY",
        "package": "anthropic",
        "default_model": "claude-opus-5",
        "models": ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5",
                   "claude-fable-5"],
        "needs": ["api_key"],
    },
    "openai": {
        "label": "OpenAI",
        "kind": "cloud",
        "env": "OPENAI_API_KEY",
        "package": "openai",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "o4-mini"],
        "needs": ["api_key"],
    },
    "azure": {
        "label": "Azure OpenAI / Foundry",
        "kind": "cloud",
        "env": "AZURE_OPENAI_API_KEY",
        "package": "openai",
        "default_model": "",                # the Azure *deployment* name
        "models": [],
        "needs": ["api_key", "endpoint", "model"],
    },
    "google": {
        "label": "Google Gemini",
        "kind": "cloud",
        "env": "GOOGLE_API_KEY",
        "package": "google-genai",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
        "needs": ["api_key"],
    },
}

DEFAULT_AZURE_API_VERSION = "2024-10-21"

# Runtime config. `provider` is persisted in settings.json; the key never is.
PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", DEFAULT_AZURE_API_VERSION).strip()

# provider id -> API key, in-memory only (see module docstring).
_SESSION_KEYS: dict[str, str] = {}


def configure(provider=None, azure_endpoint=None, azure_api_version=None):
    """Update provider selection at runtime (Settings page, no restart)."""
    global PROVIDER, AZURE_ENDPOINT, AZURE_API_VERSION
    if provider:
        p = str(provider).strip().lower()
        if p in PROVIDERS:
            PROVIDER = p
    if azure_endpoint is not None:
        AZURE_ENDPOINT = str(azure_endpoint).strip().rstrip("/")
    if azure_api_version:
        AZURE_API_VERSION = str(azure_api_version).strip()


def set_key(provider, key):
    """Hold an API key for this process only. Passing a blank key clears the
       session override so resolution falls back to the environment variable."""
    p = str(provider or "").strip().lower()
    if p not in PROVIDERS:
        return False
    key = (key or "").strip()
    if key:
        _SESSION_KEYS[p] = key
    else:
        _SESSION_KEYS.pop(p, None)
    return True


def resolve_key(provider=None):
    """The key actually used for a provider: session override, else its env var."""
    p = (provider or PROVIDER).strip().lower()
    meta = PROVIDERS.get(p) or {}
    if p in _SESSION_KEYS:
        return _SESSION_KEYS[p]
    env = meta.get("env")
    return (os.environ.get(env) or "").strip() if env else None


def key_source(provider=None):
    """Where the key came from — for the UI, which never sees the key itself."""
    p = (provider or PROVIDER).strip().lower()
    if p in _SESSION_KEYS:
        return "session"
    meta = PROVIDERS.get(p) or {}
    if meta.get("env") and os.environ.get(meta["env"]):
        return "env"
    return None


def is_local(provider=None):
    p = (provider or PROVIDER).strip().lower()
    return (PROVIDERS.get(p) or {}).get("kind") != "cloud"


def catalog():
    """Provider metadata for the Settings page. Reports only WHETHER a key is
       present and where it came from — never the key."""
    out = []
    for pid, meta in PROVIDERS.items():
        out.append({
            "id": pid,
            "label": meta["label"],
            "kind": meta["kind"],
            "env": meta.get("env"),
            "package": meta.get("package"),
            "default_model": meta.get("default_model", ""),
            "models": list(meta.get("models") or []),
            "needs": list(meta.get("needs") or []),
            "has_key": bool(resolve_key(pid)) if meta["kind"] == "cloud" else True,
            "key_source": key_source(pid),
            "installed": _sdk_installed(pid),
        })
    return out


def _sdk_installed(provider):
    """True when the provider's SDK can be imported (cheap check for the UI)."""
    pkg = (PROVIDERS.get(provider) or {}).get("package")
    if not pkg:
        return True
    import importlib.util
    mod = {"google-genai": "google.genai"}.get(pkg, pkg)
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _missing_sdk(provider):
    pkg = (PROVIDERS.get(provider) or {}).get("package")
    return "%s SDK not installed - run: pip install %s" % (
        (PROVIDERS.get(provider) or {}).get("label", provider), pkg)


# --------------------------------------------------------------------------
# JSON extraction. Ollama guarantees raw JSON via format:"json"; hosted models
# often wrap it in a ```json fence or add a sentence of preamble, so the shared
# path is tolerant rather than assuming a bare object.
# --------------------------------------------------------------------------
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def parse_json(text):
    """Best-effort parse of a model's JSON reply. Returns a dict or None."""
    if not text:
        return None
    raw = text.strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    m = _FENCE.search(raw)                       # ```json { ... } ```
    if m:
        try:
            return json.loads(m.group(1).strip())
        except ValueError:
            pass
    i, j = raw.find("{"), raw.rfind("}")         # prose before/after the object
    if 0 <= i < j:
        try:
            return json.loads(raw[i:j + 1])
        except ValueError:
            pass
    return None


# --------------------------------------------------------------------------
# Provider adapters. Each returns completion text, or raises with a message the
# caller surfaces; complete() below converts failures into None so the agents
# keep their "never raises to the request" contract.
# --------------------------------------------------------------------------
def _anthropic(prompt, system, model, json_mode, timeout, max_tokens):
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(_missing_sdk("anthropic"))
    key = resolve_key("anthropic")
    if not key:
        raise RuntimeError("no Anthropic API key (set ANTHROPIC_API_KEY or enter one in Settings)")
    client = anthropic.Anthropic(api_key=key, timeout=timeout)
    sys_prompt = system
    if json_mode:
        sys_prompt += " Reply with a single raw JSON object and nothing else."
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=sys_prompt,
        # These are short extraction/rewrite calls, so keep spend low; effort is
        # the supported control (sampling params are rejected on current models).
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    # Safety classifiers can decline a request: HTTP 200 with stop_reason
    # "refusal" and no usable content. Check before reading blocks.
    if getattr(resp, "stop_reason", None) == "refusal":
        raise RuntimeError("Anthropic declined this request (stop_reason=refusal)")
    # Thinking blocks can precede the answer — take the text blocks only.
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


def _openai_like(prompt, system, model, json_mode, timeout, max_tokens, azure=False):
    try:
        import openai
    except ImportError:
        raise RuntimeError(_missing_sdk("azure" if azure else "openai"))
    pid = "azure" if azure else "openai"
    key = resolve_key(pid)
    if not key:
        raise RuntimeError("no %s API key (set %s or enter one in Settings)"
                           % (PROVIDERS[pid]["label"], PROVIDERS[pid]["env"]))
    if azure:
        if not AZURE_ENDPOINT:
            raise RuntimeError("no Azure endpoint configured (Settings -> Azure endpoint)")
        client = openai.AzureOpenAI(api_key=key, azure_endpoint=AZURE_ENDPOINT,
                                    api_version=AZURE_API_VERSION, timeout=timeout)
    else:
        client = openai.OpenAI(api_key=key, timeout=timeout)
    kwargs = {
        "model": model,                      # on Azure this is the deployment name
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**kwargs)
    return (resp.choices[0].message.content or "").strip()


def _google(prompt, system, model, json_mode, timeout, max_tokens):
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError(_missing_sdk("google"))
    key = resolve_key("google")
    if not key:
        raise RuntimeError("no Google API key (set GOOGLE_API_KEY or enter one in Settings)")
    client = genai.Client(api_key=key)
    cfg = {"system_instruction": system, "max_output_tokens": max_tokens}
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=genai_types.GenerateContentConfig(**cfg))
    return (getattr(resp, "text", "") or "").strip()


# Last failure per provider, so the Settings "Test" button can explain a dead
# connection instead of just reporting offline.
_LAST_ERROR: dict[str, str] = {}


def last_error(provider=None):
    return _LAST_ERROR.get((provider or PROVIDER).strip().lower())


def complete(prompt, system, json_mode=False, model=None, timeout=30.0,
             max_tokens=2048, provider=None, raise_errors=False):
    """One completion through the selected provider.

       Returns the reply text (or None on any failure, matching the agents'
       best-effort contract). Ollama is handled by llm.py itself — this is the
       hosted path. Set raise_errors=True to get the reason instead of None
       (used by the Settings connection test)."""
    p = (provider or PROVIDER).strip().lower()
    meta = PROVIDERS.get(p)
    if not meta:
        return None
    model = (model or meta.get("default_model") or "").strip()
    if not model:
        msg = "no model configured for %s" % meta["label"]
        _LAST_ERROR[p] = msg
        if raise_errors:
            raise RuntimeError(msg)
        return None
    try:
        if p == "anthropic":
            text = _anthropic(prompt, system, model, json_mode, timeout, max_tokens)
        elif p == "openai":
            text = _openai_like(prompt, system, model, json_mode, timeout, max_tokens)
        elif p == "azure":
            text = _openai_like(prompt, system, model, json_mode, timeout, max_tokens, azure=True)
        elif p == "google":
            text = _google(prompt, system, model, json_mode, timeout, max_tokens)
        else:
            raise RuntimeError("provider %r has no hosted adapter" % p)
        _LAST_ERROR.pop(p, None)
        return text
    except Exception as e:                    # never propagate into a request
        _LAST_ERROR[p] = str(e)
        if raise_errors:
            raise
        return None


def status(model=None, provider=None):
    """Reachability for the sidebar/Settings dot. Cloud providers are reported
       ready when their SDK is installed and a key resolves; a real round trip
       only happens on the explicit Test button (test_connection below)."""
    p = (provider or PROVIDER).strip().lower()
    meta = PROVIDERS.get(p) or {}
    model = (model or meta.get("default_model") or "").strip()
    if not _sdk_installed(p):
        return {"online": False, "backend": p, "provider": p, "model": model,
                "error": _missing_sdk(p), "needs_install": True}
    if not resolve_key(p):
        return {"online": False, "backend": p, "provider": p, "model": model,
                "error": "no API key — set %s or enter one in Settings" % meta.get("env"),
                "needs_key": True}
    if p == "azure" and not AZURE_ENDPOINT:
        return {"online": False, "backend": p, "provider": p, "model": model,
                "error": "no Azure endpoint configured"}
    if not model:
        return {"online": False, "backend": p, "provider": p, "model": model,
                "error": "no model configured"}
    return {"online": True, "backend": p, "provider": p, "model": model,
            "model_present": True, "key_source": key_source(p),
            "url": AZURE_ENDPOINT if p == "azure" else meta["label"],
            "last_error": last_error(p)}


def test_connection(model=None, provider=None, timeout=20.0):
    """Explicit round trip for the Settings Test button: {ok, message, model}."""
    p = (provider or PROVIDER).strip().lower()
    meta = PROVIDERS.get(p) or {}
    model = (model or meta.get("default_model") or "").strip()
    try:
        text = complete("Reply with the single word: OK.",
                        "You are a connection test. Reply with exactly one word.",
                        model=model, timeout=timeout, max_tokens=512,
                        provider=p, raise_errors=True)
    except Exception as e:
        return {"ok": False, "provider": p, "model": model, "message": str(e)}
    if not text:
        return {"ok": False, "provider": p, "model": model,
                "message": "empty reply from %s" % meta.get("label", p)}
    return {"ok": True, "provider": p, "model": model,
            "message": "Connected to %s · %s" % (meta.get("label", p), model)}
