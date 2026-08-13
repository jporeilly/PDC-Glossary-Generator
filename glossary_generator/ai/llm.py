"""
llm.py - local LLM client for term enrichment (Ollama).

Talks to a local Ollama server for one-sentence business definitions.
Everything is best-effort: if Ollama is unreachable or returns junk, the
caller keeps the heuristic definition. Nothing here ever raises to the request.

Setup:
  ollama pull llama3.1
  ollama serve            # serves http://localhost:11434

Env:
  LLM_MODEL    model name              (default llama3.1)
  OLLAMA_URL   http://localhost:11434  (default)
  LLM_TIMEOUT  seconds per call        (default 30)
"""
import os, re, json
import concurrent.futures

import httpx

from ai import llm_providers          # hosted providers (Anthropic / OpenAI / Azure / Google)

MODEL      = os.environ.get("LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
TIMEOUT    = float(os.environ.get("LLM_TIMEOUT", "30"))
COMPANY    = os.environ.get("GLOSSARY_COMPANY", "your organization")

def _clampint(val, default, lo, hi):
    try:
        return max(lo, min(int(val), hi))
    except (TypeError, ValueError):
        return default

WORKERS = _clampint(os.environ.get("LLM_WORKERS", "4"), 4, 1, 16)
BATCH   = _clampint(os.environ.get("LLM_BATCH", "6"), 6, 1, 20)

SYSTEM = ("You are a data-governance analyst writing entries for a business "
          "glossary. Definitions are precise, business-facing, and one sentence. "
          "Always write in English, whatever language the model was trained in.")

def configure(ollama_url=None, model=None, timeout=None, company=None,
              workers=None, batch=None):
    """Update the runtime LLM config (used by the Settings page so the Ollama URL /
       model / timeout / company / workers / batch can change without a restart).
       Empty values are ignored, so a caller can update just one field. The module
       functions read these globals at call time, so changes take effect immediately."""
    global OLLAMA_URL, MODEL, TIMEOUT, COMPANY, WORKERS, BATCH
    if ollama_url:
        OLLAMA_URL = str(ollama_url).strip().rstrip("/")
    if model:
        MODEL = str(model).strip()
    if timeout not in (None, ""):
        try:
            TIMEOUT = float(timeout)
        except (TypeError, ValueError):
            pass
    if company:
        COMPANY = str(company).strip()
    if workers not in (None, ""):
        WORKERS = _clampint(workers, WORKERS, 1, 16)
    if batch not in (None, ""):
        BATCH = _clampint(batch, BATCH, 1, 20)
    return {"ollama_url": OLLAMA_URL, "model": MODEL, "timeout": TIMEOUT,
            "company": COMPANY, "workers": WORKERS, "batch": BATCH}

def _post(url, payload, timeout=None):
    """POST a JSON body to the local Ollama endpoint and return the parsed response."""
    if timeout is None:
        timeout = TIMEOUT
    r = httpx.post(url, json=payload, timeout=timeout)
    r.raise_for_status()          # match the old urllib behavior: HTTP errors raise
    return r.json()


def _warm(model=None):
    """Preload the model so the first real batch doesn't pay the cold-load cost.
       Ollama-only: hosted providers have nothing to warm, and firing this at a
       local Ollama while a cloud provider is selected would load the wrong
       model. Best-effort — a failure here never blocks the agent run."""
    if not llm_providers.is_local():
        return
    try:
        _post(OLLAMA_URL + "/api/generate",
              {"model": model or MODEL, "prompt": "ok", "stream": False,
               "options": {"num_predict": 1}}, timeout=max(TIMEOUT, 120))
    except Exception:
        pass


def placement():
    """Where loaded models actually run, from Ollama /api/ps (the real truth,
       set by the SERVER's OS env + hardware - not by this app). Returns e.g.
       {'known':True,'label':'100% GPU'} or {'known':False}."""
    try:
        ps = httpx.get(OLLAMA_URL + "/api/ps", timeout=3).json()
        models = ps.get("models", [])
        if not models:
            return {"known": False, "loaded": False}
        m = models[0]
        for mm in models:  # prefer the configured model if it's loaded
            if MODEL.split(":")[0] in mm.get("name", ""):
                m = mm; break
        total = m.get("size") or 0
        vram = m.get("size_vram") or 0
        if total <= 0:
            return {"known": False, "loaded": True}
        gpu = round(100 * vram / total)
        cpu = 100 - gpu
        if gpu >= 99:   label = "100% GPU"
        elif gpu <= 1:  label = "100% CPU"
        else:           label = f"{cpu}%/{gpu}% CPU/GPU"
        return {"known": True, "loaded": True, "label": label,
                "gpu_pct": gpu, "cpu_pct": cpu, "name": m.get("name", "")}
    except Exception:
        return {"known": False}

def status(model=None):
    """Report whether the selected LLM backend is reachable and which model is
       chosen. Hosted providers report readiness from SDK + key + model (a real
       round trip only happens on the Settings Test button)."""
    model = model or MODEL
    if not llm_providers.is_local():
        return llm_providers.status(model=model)
    try:
        tags = httpx.get(OLLAMA_URL + "/api/tags", timeout=3).json()
        models = [m.get("name", "") for m in tags.get("models", [])]
        return {"online": True, "backend": "ollama", "model": model, "url": OLLAMA_URL,
                "models": models,
                # Exact tag match. A prefix match ("llama3.2" in "llama3.2:latest")
                # reported a model as present when only a DIFFERENT tag of it was
                # pulled, so the UI showed "online" while every call 404'd.
                "model_present": model in models,
                "placement": placement()}
    except Exception as e:
        return {"online": False, "backend": "ollama", "model": model,
                "url": OLLAMA_URL, "error": str(e)}

def _complete(prompt, model=None, num_gpu=None):
    """Single completion. Returns text or None on any failure.

       Every agent in the app reaches the model through here (or _complete_json
       below), so this is the one place that has to know about providers: a
       hosted provider is delegated to llm_providers, and the Ollama path below
       is unchanged."""
    model = model or MODEL
    if not llm_providers.is_local():
        return llm_providers.complete(prompt, SYSTEM, json_mode=False,
                                      model=model, timeout=TIMEOUT)
    options = {"temperature": 0.2}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    try:
        out = _post(OLLAMA_URL + "/api/generate",
                    {"model": model, "system": SYSTEM, "prompt": prompt,
                     "stream": False, "options": options})
        return (out.get("response") or "").strip()
    except Exception:
        return None


# Floor for the combined AI pass's per-row budget (seconds) — override with
# GLOSSARY_AI_PASS_TIMEOUT.
AI_PASS_TIMEOUT = _clampint(os.environ.get("GLOSSARY_AI_PASS_TIMEOUT"), 180, 30, 1800)

# Last-run call failures, so an agent can distinguish "model said nothing" from
# "the model never answered" (timeout) — reset by reset_call_failures().
_CALL_FAILURES = {"timeout": 0, "other": 0}

def _note_call_failure(exc):
    kind = "timeout" if "timed out" in str(exc).lower() or isinstance(exc, socket.timeout) else "other"
    _CALL_FAILURES[kind] = _CALL_FAILURES.get(kind, 0) + 1

def reset_call_failures():
    _CALL_FAILURES.update({"timeout": 0, "other": 0})

def call_failures():
    return dict(_CALL_FAILURES)

def _complete_json(prompt, model=None, num_gpu=None, timeout=None,
                   options=None):
    """Single completion in JSON mode. Returns a parsed dict, or None on any
       failure. Used to get definition + purpose from ONE round trip per row.
       `timeout` overrides the configured budget for calls with a bigger prompt
       (the combined AI pass) that legitimately take longer on a large model.
       `options` overlays the Ollama sampling defaults - the categorize calls
       pass temperature 0 + a fixed seed so the SAME estate proposes the SAME
       taxonomy (field-caught: 5 subjects one run, 2 the next). Local models
       only; hosted providers keep their own defaults."""
    model = model or MODEL
    if not llm_providers.is_local():
        # Hosted models honour a JSON response format but may still wrap the
        # object in a ``` fence, so parse tolerantly rather than json.loads().
        return llm_providers.parse_json(
            llm_providers.complete(prompt, SYSTEM, json_mode=True,
                                   model=model, timeout=TIMEOUT))
    # num_ctx 8192: the model may DECLARE a huge context (a 12b declaring
    # 256K), and Ollama sizes the KV-cache reservation from the runtime
    # context - unbounded, that reservation outgrows one GPU and the model
    # gets SPLIT across cards (or spilled to CPU), paying a PCIe hop per
    # token. Field-caught: an empty 12GB card sat idle while the schema call
    # ran split at 7+ minutes. Our prompts are bounded; so is the cache.
    opts = {"temperature": 0.2, "num_ctx": 8192}
    opts.update(options or {})
    options = opts
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    try:
        out = _post(OLLAMA_URL + "/api/generate",
                    {"model": model, "system": SYSTEM, "prompt": prompt,
                     "stream": False, "format": "json", "options": options},
                    timeout=timeout)
        raw = (out.get("response") or "").strip()
        return json.loads(raw) if raw else None
    except Exception as e:
        # a TIMEOUT here is indistinguishable from "the model had nothing to
        # say" once it becomes None — and on a big local model a long prompt
        # blows the default budget every time, so every agent silently reported
        # "no changes proposed". Record it so the caller can say so.
        _note_call_failure(e)
        return None


_NON_LATIN = re.compile(r"[Ͱ-᳿　-鿿가-힯぀-ヿ豈-﫿]")

def _mostly_english(text):
    """Language guardrail: True when the text is essentially Latin-script.
       Multilingual local models (qwen, deepseek, ...) sometimes drift into
       their home language mid-batch; a proposal that fails this check is
       DISCARDED so the existing English text stays."""
    t = str(text or "")
    if not t:
        return True
    hits = len(_NON_LATIN.findall(t))
    return hits == 0 or hits / len(t) < 0.05


def _clean_sentence(text, *prefixes):
    """Trim a model sentence: first line, strip quotes and a leading label."""
    if not text:
        return None
    text = str(text).splitlines()[0].strip().strip('"').strip()
    for p in prefixes:
        if text.lower().startswith(p.lower()):
            text = text[len(p):].strip()
    if not _mostly_english(text):
        return None
    return text if 8 <= len(text) <= 300 else None

def _clean_name(text, current):
    """Sanitise a model-proposed term NAME. Returns a cleaned name only when it is a
       genuine, sensible improvement over `current`; otherwise None (keep current).
       Guards against junk: empty, label echoes, over-long, or unchanged values."""
    if not text:
        return None
    t = str(text).splitlines()[0].strip().strip('"').strip("'").strip()
    for p in ("Term:", "Name:", "Suggested name:"):
        if t.lower().startswith(p.lower()):
            t = t[len(p):].strip()
    t = re.sub(r"\s+", " ", t).strip(" .")
    if not t or len(t) > 60 or len(t.split()) > 8 or not _mostly_english(t):
        return None
    cur = re.sub(r"\s+", " ", str(current or "")).strip()
    if t.lower() == cur.lower():                 # no change proposed
        return None
    return t

# --------------------------------------------------------------- expertise
# Words that say nothing about a person's *domain* — stripped from the offline
# fallback so it doesn't emit "owns", "terms", "optional", etc. as keywords.
_EXP_STOP = {
    "the", "and", "for", "owns", "own", "terms", "term", "data", "glossary",
    "can", "incl", "including", "displayed", "optional", "persona", "reads",
    "searches", "creates", "manages", "defines", "custom", "properties",
    "worker", "workers", "licence", "license", "view", "galaxy", "metadata",
    "connects", "sources", "profiles", "runs", "curates", "collections",
    "create", "import", "edit", "policies", "users", "account", "accounts",
    "with", "from", "into", "that", "this", "their", "they", "role", "roles",
    "steward", "stewards", "analyst", "analysts", "admin", "user",
    "dr", "mr", "mrs", "ms",
}


def _expertise_llm(person, categories, model=None, num_gpu=None):
    """Ask Ollama for 4-8 domain keywords for one person. Returns a comma-joined
       string, or "" on any failure (caller then uses the offline fallback)."""
    name = person.get("display_name") or person.get("name") or "this user"
    roles = ", ".join(person.get("roles") or []) or "unspecified"
    owns = (person.get("owns") or "").strip()
    community = (person.get("community") or "").strip()
    catline = ", ".join(categories) if categories else "(none provided)"
    prompt = (
        "Map a data-team member to the business domains they should steward.\n"
        f"Person: {name}\nRoles: {roles}\n"
        f"Responsibilities: {owns or 'unspecified'}\n"
        f"Teams / community: {community or 'unspecified'}\n"
        f"Available glossary categories: {catline}\n\n"
        'Return ONLY JSON of the form {"keywords": ["..."]} with 4 to 8 short, '
        "lowercase business-domain keywords (single words or two-word phrases) "
        "describing this person's areas of expertise. Prefer words that overlap the "
        "available categories above. No full sentences, no personal names, and no "
        'generic role words such as "steward", "owner", "admin", "user".')
    obj = _complete_json(prompt, model=model, num_gpu=num_gpu)
    if not isinstance(obj, dict):
        return ""
    kws = obj.get("keywords") or obj.get("expertise") or []
    if isinstance(kws, str):
        kws = re.split(r"[,;]", kws)
    out, seen = [], set()
    banned = {"steward", "owner", "custodian", "admin", "user", "data", "none"}
    for k in kws:
        k = str(k).strip().lower().strip(".,;")
        if k and len(k) > 1 and k not in seen and k not in banned:
            seen.add(k)
            out.append(k)
    return ", ".join(out[:8])


def _expertise_fallback(person, categories=None):
    """Deterministic, offline expertise keywords from a person's owns/community
       text and the available category labels. Keeps auto-assign usable when Ollama
       is offline or returns nothing."""
    text = " ".join(str(person.get(k) or "")
                    for k in ("owns", "community", "expertise")).lower()
    # don't echo the person's own name back as a "skill"
    name_toks = {t for t in re.split(r"[^a-z0-9]+",
                 (str(person.get("display_name") or "") + " " +
                  str(person.get("name") or "")).lower()) if t}
    skip = _EXP_STOP | name_toks
    out, seen = [], set()
    # 1) category labels the person's text overlaps with (the strongest signal)
    for c in (categories or []):
        for w in re.split(r"[^a-z0-9]+", str(c).lower()):
            if len(w) > 3 and w in text and w not in seen and w not in skip:
                seen.add(w)
                out.append(w)
    # 2) the person's own meaningful words, in order
    for w in re.split(r"[^a-z0-9]+", text):
        if len(w) > 3 and w not in seen and w not in skip:
            seen.add(w)
            out.append(w)
    # 3) last resort: lean on the role
    if not out:
        roles = " ".join(person.get("roles") or []).lower()
        if "business" in roles:
            out = ["governance", "policy", "compliance"]
        elif "data" in roles:
            out = ["data quality", "profiling", "lineage"]
        elif "admin" in roles:
            out = ["administration", "accounts", "configuration"]
    return ", ".join(out[:8])


def suggest_expertise(people, categories=None, overwrite=False, model=None,
                      num_gpu=None):
    """Generate `expertise` keywords for each roster member from their role /
       responsibilities (`owns`) / community text and the available glossary
       categories. These keywords are what the auto-assign matcher scores against.
       LLM-first via local Ollama, with a deterministic offline fallback, so it
       always returns something usable. By default only people with no expertise
       are touched; pass overwrite=True to regenerate everyone.
       Returns (people, count_updated, used_llm)."""
    cats = [str(c).strip() for c in (categories or []) if str(c).strip()]
    online = status(model)["online"]
    updated = 0
    used_llm = False
    for p in people:
        if not isinstance(p, dict):
            continue
        if (p.get("expertise") or "").strip() and not overwrite:
            continue
        kws = ""
        if online:
            kws = _expertise_llm(p, cats, model=model, num_gpu=num_gpu)
            if kws:
                used_llm = True
        if not kws:
            kws = _expertise_fallback(p, cats)
        if kws:
            p["expertise"] = kws
            updated += 1
    return people, updated, used_llm


# --------------------------------------------------------------- model management
def list_models():
    """Model names for the Settings dropdown: installed models from Ollama, or
       the hosted provider's suggested ids (never a whitelist — a custom id is
       always allowed, since vendors add and retire ids on their own schedule)."""
    if not llm_providers.is_local():
        meta = llm_providers.PROVIDERS.get(llm_providers.PROVIDER) or {}
        return list(meta.get("models") or [])
    try:
        tags = httpx.get(OLLAMA_URL + "/api/tags", timeout=3).json()
        return [m.get("name", "") for m in tags.get("models", [])]
    except Exception:
        return []

def pull_stream(model=None):
    """Generator that pulls a model and yields progress dicts:
       {phase, status, completed, total, percent}. Safe to iterate to completion.
       Ollama resumes cancelled pulls automatically, so re-calling is cheap."""
    model = model or MODEL
    try:
        with httpx.stream("POST", OLLAMA_URL + "/api/pull",
                          json={"model": model, "stream": True}, timeout=None) as resp:
            for raw in resp.iter_lines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if "error" in obj:
                    yield {"phase": "error", "status": obj["error"], "percent": 0}
                    return
                status = obj.get("status", "")
                total = obj.get("total") or 0
                completed = obj.get("completed") or 0
                pct = round(100 * completed / total, 1) if total else None
                yield {"phase": "success" if status == "success" else "downloading",
                       "status": status, "completed": completed, "total": total,
                       "percent": pct}
    except Exception as e:
        yield {"phase": "error", "status": f"pull failed: {e}", "percent": 0}


# ------------------------------------------------------------ combined AI pass

def _scan_reason(row):
    """The SCAN's own reasoning for a row, with any agent-appended rationale
       stripped. `ai_pass_rows` writes its answer back into Suggested_Reason as
       "AI(pass): …", so feeding the field in raw would hand the model its own
       previous reply as if it were evidence from the data — a second run would
       be arguing with itself. Only the part the scan wrote is evidence."""
    base = str(row.get("Suggested_Reason") or "")
    for marker in ("AI(pass):", "AI(evidence):"):
        i = base.find(marker)
        if i != -1:
            base = base[:i]
    return base.strip().strip("·").strip()


def _ai_pass_one(row, allow_tags, categories, model=None, num_gpu=None):
    """ONE call per row for every LLM-decidable field: name, definition, purpose,
       category and governed tags. This is the ONLY row-level agent prompt left —
       Enrich, AI suggest and AI categorize were three separate passes over the
       same rows that overlapped on name / category / tags (the later pass simply
       overwrote the earlier one's proposal), and each restated the guardrails in
       its own wording, so a change to one had to be made three times or they
       drifted. This prompt carries the evidence grounding the evidence pass had
       and the writing instructions the enricher had."""
    ev = []
    if row.get("Source_Column"):
        ev.append("physical column(s): %s" % row["Source_Column"])
    if row.get("Value_Signature"):
        ev.append("profiled position signature: %s" % row["Value_Signature"])
    if row.get("Value_Pattern"):
        ev.append("induced value regex: %s" % row["Value_Pattern"])
    enum_vals = (row.get("Enum_Values") or "").strip()
    if enum_vals:
        ev.append("profiled reference values: %s" % enum_vals[:200])
    if row.get("PII_Category"):
        ev.append("PII category: %s" % row["PII_Category"])
    reason = _scan_reason(row)
    if reason:
        ev.append("scan reasoning: %s" % reason[:160])
    if row.get("QA_Issues"):
        ev.append("the current definition was flagged as: %s"
                  % str(row["QA_Issues"]).replace(";", ", "))
    prompt = (
        "You curate a governed business glossary%s. For ONE database column, return "
        "every field below in a single JSON object.\n"
        "Current: term \"%s\", category \"%s\", tags: %s.\n"
        "Current definition draft: %s\n"
        "Current purpose draft: %s\n"
        "Evidence from scanning the actual data:\n- %s\n\n"
        "Categories (choose one): %s\n"
        "Governed tag allow-list (use ONLY these): %s\n\n"
        "Return JSON with keys:\n"
        "  \"name\": a clearer business term ONLY if the current one is cryptic or "
        "abbreviated (cust_acct_no -> Customer Account Number); if it already reads "
        "well, repeat it UNCHANGED.\n"
        "  \"definition\": one sentence (max 25 words), precise, business-facing, what it is.\n"
        "  \"purpose\": one sentence (max 25 words), why it matters or how the business "
        "uses it — not a restatement of the definition.\n"
        "  \"category\": one from the list (only useful when the current category is blank).\n"
        "  \"tags\": array, ONLY from the allow-list, the most relevant 2-5.\n"
        "  \"rationale\": one short sentence grounded in the evidence.\n"
        "Do NOT return sensitivity or PII — those are deterministic from the scan."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        row.get("Term", ""), row.get("Category", ""),
        row.get("Suggested_Tags", "") or "(none)",
        (row.get("Definition") or "")[:220], (row.get("Purpose") or "")[:220],
        "\n- ".join(ev) if ev else "(name only - no profile evidence)",
        ", ".join(categories or []) or "(keep current)",
        ", ".join(allow_tags or []) or "(none)",
    )
    # A combined prompt does the work of three agents, so it legitimately runs
    # longer than a single-field call: give it at least 180s on top of whatever
    # the user configured, or a 12B local model times out on EVERY row and the
    # pass silently reports "no changes proposed".
    return _complete_json(prompt, model=model, num_gpu=num_gpu,
                          timeout=max(TIMEOUT, AI_PASS_TIMEOUT))


def _ai_pass_batch(rows, allow_tags, categories, model=None, num_gpu=None):
    """SEVERAL rows in ONE call: Ollama pays the prompt/scheduling overhead once per batch
       instead of once per row, which is the difference between ~120 calls and
       ~20 for a typical scan. Returns a list of reply dicts aligned to `rows`
       (None where the model gave nothing). Falls back to per-row calls if the
       batch reply is missing or unusable, so one bad JSON never drops a chunk."""
    rows = list(rows)
    if not rows:
        return []
    # A batch of ONE is not a smaller batch - it is the per-row path. The
    # compressed pipe-format below exists to fit many rows into one call;
    # sending it for a single row trades quality for nothing. This routing is
    # what makes Settings' batch size 1 literally the AI-review prompt,
    # sweep-wide: full evidence, full instructions, the model's whole output
    # budget on one term.
    if len(rows) == 1:
        return [_ai_pass_one(rows[0], allow_tags, categories,
                             model=model, num_gpu=num_gpu)]
    lines = []
    for i, r in enumerate(rows, 1):
        ev = []
        if r.get("Value_Signature"):
            ev.append("signature %s" % r["Value_Signature"])
        if r.get("Value_Pattern"):
            ev.append("regex %s" % r["Value_Pattern"])
        enum_vals = (r.get("Enum_Values") or "").strip()
        if enum_vals:
            ev.append("values %s" % enum_vals[:200])
        if r.get("PII_Category"):
            ev.append("PII %s" % r["PII_Category"])
        # why the scan proposed this term/tags in the first place. The batched
        # prompt went without it while the per-row path had it, so the evidence
        # the retired AI-suggest agent leaned on was exactly what the pass that
        # replaced it never saw on the path it actually runs.
        reason = _scan_reason(r)
        if reason:
            ev.append("scan reasoning %s" % reason[:160])
        lines.append(
            f'{i}. Term: {r.get("Term","")} | Category: {r.get("Category","") or "(blank)"} | '
            f'Source: {r.get("Source_Column","")} | Tags: {r.get("Suggested_Tags","") or "(none)"} | '
            f'Draft definition: {(r.get("Definition") or "")[:220]} | '
            f'Draft purpose: {(r.get("Purpose") or "")[:220]}'
            + (f' | Evidence: {"; ".join(ev)}' if ev else "")
            + (f' | REWRITE REQUIRED - flagged: {(r.get("QA_Issues") or "").replace(";", ", ")}'
               if r.get("QA_Issues") else ""))
    prompt = (
        "You curate a governed business glossary%s. For EACH numbered column below "
        "return every field, grounded in the evidence given.\n"
        "Categories (choose one): %s\n"
        "Governed tag allow-list (use ONLY these): %s\n\n"
        "Return ONLY a JSON object of the form {\"items\":[{\"n\":1,\"name\":\"...\","
        "\"definition\":\"...\",\"purpose\":\"...\",\"category\":\"...\",\"tags\":[\"...\"],"
        "\"rationale\":\"...\"}, ...]} with one entry per column, keeping the numbering.\n"
        "  name: a clearer business term ONLY if the current one is cryptic or abbreviated "
        "(cust_acct_no -> Customer Account Number); otherwise repeat it UNCHANGED.\n"
        "  definition: one sentence, max 25 words, precise, business-facing, what it is.\n"
        "  purpose: one sentence, max 25 words, why it matters or how the business "
        "uses it — NOT a restatement of the definition.\n"
        "  category: one from the list (only useful where the current category is blank).\n"
        "  tags: 2-5, ONLY from the allow-list.\n"
        "Write each entry from its own evidence alone — do NOT reuse sentence "
        "templates or phrasing across entries.\n"
        "Do NOT return sensitivity or PII — those are deterministic from the scan.\n\n"
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        ", ".join(categories or []) or "(keep current)",
        ", ".join(allow_tags or []) or "(none)",
    ) + "\n".join(lines)
    # the budget scales with the batch: one call now does N rows of work
    obj = _complete_json(prompt, model=model, num_gpu=num_gpu,
                         timeout=max(TIMEOUT, AI_PASS_TIMEOUT) * max(1, len(rows) // 2))
    items = obj.get("items") if isinstance(obj, dict) else None
    if isinstance(items, list) and items:
        by_n = {}
        for pos, it in enumerate(items, 1):
            if not isinstance(it, dict):
                continue
            n = it.get("n")
            try:
                n = int(n)
            except (TypeError, ValueError):
                n = pos
            by_n[n] = it
        out = [by_n.get(i) for i in range(1, len(rows) + 1)]
        if any(isinstance(o, dict) for o in out):
            return out
    # fallback: one call per row so a bad batch reply still enriches the chunk
    return [_ai_pass_one(r, allow_tags, categories, model=model, num_gpu=num_gpu)
            for r in rows]


def ai_pass_rows(rows, allow_tags=None, categories=None, only_low_confidence=False,
                 model=None, compute=None, workers=None, batch_size=None):
    """One combined agent pass: definition, purpose, name, category and tags for
       each kept row in a SINGLE model call per row, under the same guardrails the
       separate agents apply — tags governed-only, category fills a blank only,
       the name is a Suggested_Name chip and never overwrites Term, sensitivity
       and PII are never touched by the model. Returns (rows, counts, used_llm)."""
    rows = [r for r in rows if isinstance(r, dict)]
    counts = {"definitions": 0, "purposes": 0, "names": 0, "tags": 0, "category": 0}
    if not status(model)["online"]:
        return rows, counts, False
    reset_call_failures()
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    allow = [t for t in (allow_tags or [])]
    allow_set = {str(t).strip().lower() for t in allow}
    cats = [c for c in (categories or [])]
    targets = [r for r in rows
               if not (only_low_confidence and r.get("Confidence") == "High")]
    try:
        _warm(model)
    except Exception:
        pass

    # group into batches — ONE call covers `batch_size` rows (env LLM_BATCH),
    # and the batches themselves run concurrently, so a 120-row scan costs
    # ~20 calls instead of 120
    if batch_size is None:
        batch_size = BATCH
    batch_size = max(1, min(int(batch_size), 20))
    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]

    def _do(batch):
        try:
            return batch, _ai_pass_batch(batch, allow, cats, model=model, num_gpu=num_gpu)
        except Exception:
            return batch, [None] * len(batch)

    if workers == 1 or len(batches) <= 1:
        done = [_do(b) for b in batches]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            done = list(ex.map(_do, batches))
    results = [(r, out) for batch, outs in done for r, out in zip(batch, outs)]

    for r, out in results:
        if not isinstance(out, dict):
            continue
        changed = False
        d = _clean_sentence(out.get("definition"), "Definition:")
        if d and d != r.get("Definition"):
            r["Definition"] = d
            r["LLM_Definition"] = "Yes"
            counts["definitions"] += 1
            changed = True
        p = _clean_sentence(out.get("purpose"), "Purpose:")
        if p and p != r.get("Purpose"):
            r["Purpose"] = p
            r["LLM_Purpose"] = "Yes"
            counts["purposes"] += 1
            changed = True
        term = _clean_name(str(out.get("name") or ""), r.get("Term", ""))
        if term and term != r.get("Term") and term != r.get("Suggested_Name"):
            r["Suggested_Name"] = term
            r["LLM_Name"] = "Yes"
            counts["names"] += 1
            changed = True
        cat = str(out.get("category") or "").strip()
        if cat and cats and cat in cats and not (r.get("Category") or "").strip():
            r["Category"] = cat
            counts["category"] += 1
            changed = True
        proposed = out.get("tags") or []
        if isinstance(proposed, list):
            cur = [t for t in (r.get("Suggested_Tags") or "").split(";") if t]
            cur_l = {t.strip().lower() for t in cur}
            added = [str(t).strip().lower() for t in proposed
                     if str(t).strip() and str(t).strip().lower() in allow_set
                     and str(t).strip().lower() not in cur_l]
            if added:
                r["Suggested_Tags"] = ";".join(cur + added)
                counts["tags"] += 1
                changed = True
        if changed:
            r["AI_Suggested"] = "Yes"
            r["LLM_Enriched"] = "Yes"
            why = str(out.get("rationale") or "").strip()
            if not _mostly_english(why):
                why = ""
            if why:
                base = r.get("Suggested_Reason") or ""
                if "AI(pass)" not in base:
                    r["Suggested_Reason"] = (base + " · " if base else "") + "AI(pass): " + why[:180]
    fails = call_failures()
    if fails.get("timeout"):
        counts["timed_out"] = fails["timeout"]
    return rows, counts, True


# ------------------------------------------------------------ AI merge adjudicator
_ADJ_ACTIONS = {"merge": "merge", "split": "split", "disambiguate": "split",
                "separate": "separate", "keep separate": "separate"}

def _adjudicate_one(group, model=None, num_gpu=None):
    """One duplicate-group judgment call. The prompt lays out each candidate's
       scan evidence side by side and asks for ONE of the grid's three actions.
       Returns the parsed proposal dict or None."""
    lines = []
    for i, m in enumerate(group.get("members") or [], 1):
        bits = []
        if m.get("Category"):
            bits.append("category: %s" % m["Category"])
        if m.get("Source_Column"):
            bits.append("column(s): %s" % m["Source_Column"])
        if m.get("Definition"):
            bits.append("definition: %s" % str(m["Definition"])[:180])
        if m.get("Value_Pattern"):
            bits.append("induced format: %s" % m["Value_Pattern"])
        elif m.get("Value_Signature"):
            bits.append("value signature: %s" % m["Value_Signature"])
        ev = (m.get("Enum_Values") or "").strip()
        if ev:
            bits.append("profiled values: %s" % ev[:160])
        if m.get("PII_Category"):
            bits.append("PII class: %s" % m["PII_Category"])
        lines.append("Candidate %d - %s" % (i, "; ".join(bits) or "(name only)"))
    prompt = (
        "You are a data-governance steward%s. %d glossary term candidates share "
        "the name \"%s\" but come from different scans/tables. Decide ONE action:\n"
        "- merge: they are the SAME business concept; one term should link all columns.\n"
        "- disambiguate: the same word hides DIFFERENT concepts; rename with qualifiers.\n"
        "- separate: different concepts in different categories; both can stand as-is.\n\n"
        "%s\n\n"
        "Judge by MEANING and by the data evidence (formats, value lists, PII class), "
        "not by the shared name. Return JSON with keys: action (merge, disambiguate "
        "or separate), rationale (one short sentence grounded in the evidence)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        len(group.get("members") or []),
        group.get("name", ""),
        "\n".join(lines),
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def adjudicate_groups(groups, model=None, compute=None, workers=None,
                      progress=None):
    """AI agent pass over AMBIGUOUS duplicate groups — the ones the deterministic
       evidence rubric could not settle. For each group the model weighs the
       members' definitions and scan evidence and proposes merge / disambiguate /
       separate; the code applies guardrails (action must be one of the grid's
       three; rationale trimmed) and NEVER auto-applies — the result is a hint on
       the group header, the steward still clicks. Returns ({name: {action,
       reason}}, used_llm). `progress`, when given, fires per adjudicated group
       with {phase, done, total, group} — one model call per group ran behind a
       silent "Advising…" (field: "need some feedback also on AI advise")."""
    groups = [g for g in (groups or []) if isinstance(g, dict) and g.get("name")]
    if not groups or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))

    # warm the model first (a cold load can outlive LLM_TIMEOUT and fail silently)
    try:
        _warm(model)
    except Exception:
        pass

    def _do(g):
        try:
            return g, _adjudicate_one(g, model=model, num_gpu=num_gpu)
        except Exception:
            return g, None

    def _note(i, g):
        if progress:
            try:
                progress({"phase": "adjudicate", "done": i, "total": len(groups),
                          "group": g.get("name", "")})
            except Exception:
                pass  # narration must never fail the pass

    if workers == 1 or len(groups) <= 1:
        results = []
        for i, g in enumerate(groups, 1):
            results.append(_do(g))
            _note(i, g)
    else:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_do, g): g for g in groups}
            for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
                results.append(f.result())
                _note(i, futs[f])

    out = {}
    for g, res in results:
        if not isinstance(res, dict):
            continue
        action = _ADJ_ACTIONS.get(str(res.get("action") or "").strip().lower())
        if not action:
            continue
        why = str(res.get("rationale") or "").strip()[:200]
        if not _mostly_english(why):
            why = ""
        out[g["name"]] = {"action": action,
                          "reason": ("AI: " + why) if why else "AI adjudication"}
    return out, True


# ------------------------------------------------------------ AI policy hints
def _policy_hint_one(concept, allow_tags, model=None, num_gpu=None):
    """One rule-polish call for the policy drafter: given a concept's term,
       physical columns and evidence, propose a better column-name regex and
       the 2-3 most relevant governed tags. Returns the parsed dict or None."""
    prompt = (
        "You help author a data-identification rule%s for the business term \"%s\".\n"
        "Physical columns it was found in: %s.\n"
        "Value evidence: %s.\n"
        "Governed tag allow-list (use ONLY these): %s.\n\n"
        "Return JSON with keys: column_regex (a single case-insensitive regex "
        "starting with (?i) that matches these column NAMES and their likely "
        "synonyms/abbreviations, nothing overly broad), tags (array, the 2-3 most "
        "relevant tags from the allow-list)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        concept.get("term", ""),
        concept.get("columns", "") or "(unknown)",
        concept.get("evidence", "") or "(none)",
        ", ".join(allow_tags or []) or "(none)",
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def policy_hints_rows(concepts, allow_tags=None, model=None, compute=None,
                      workers=None, progress=None):
    """AI polish pass for the policy drafter. concepts: [{term, columns,
       evidence}]. Returns ({term: {column_regex, tags}}, used_llm). Guardrails
       live in policy_draft.draft_from_rows (regex must compile, tags must stay
       governed) — this only proposes. `progress`, when given, is called per
       completed concept with {phase, done, total, term} — the polish is one
       model call per rule and ran in SILENCE for minutes (field: "could do
       with some feedback when generating the draft policies")."""
    concepts = [c for c in (concepts or []) if isinstance(c, dict) and c.get("term")]
    if not concepts or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    allow = [t for t in (allow_tags or [])]
    try:
        _warm(model)
    except Exception:
        pass

    def _do(c):
        try:
            return c, _policy_hint_one(c, allow, model=model, num_gpu=num_gpu)
        except Exception:
            return c, None

    def _note(i, c):
        if progress:
            try:
                progress({"phase": "polish", "done": i, "total": len(concepts),
                          "term": c.get("term", "")})
            except Exception:
                pass  # progress is narration, never a failure path

    if workers == 1 or len(concepts) <= 1:
        results = []
        for i, c in enumerate(concepts, 1):
            results.append(_do(c))
            _note(i, c)
    else:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_do, c): c for c in concepts}
            for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
                results.append(f.result())
                _note(i, futs[f])
    out = {}
    for c, res in results:
        if isinstance(res, dict):
            hint = {}
            rx = str(res.get("column_regex") or "").strip()
            if rx:
                hint["column_regex"] = rx
            tags = res.get("tags")
            if isinstance(tags, list):
                hint["tags"] = [str(t).strip() for t in tags if str(t).strip()][:3]
            if hint:
                out[c["term"]] = hint
    return out, True


# ------------------------------------------------------------ AI definition QA
def _qa_one(row, model=None, num_gpu=None):
    """One definition-quality judgment. Returns the parsed dict or None."""
    prompt = (
        "You review a business glossary definition%s for quality.\n"
        "Term: \"%s\" (category: %s; physical column(s): %s).\n"
        "Definition under review: \"%s\"\n\n"
        "A GOOD definition says what the thing IS in business language, is "
        "specific to this term, and would let a new analyst use the data "
        "correctly. It is BAD if it is circular, generic enough to fit any "
        "term, jargon-only, or wrong for the evidence.\n"
        "Return JSON with keys: ok (true/false), issue (one short phrase, empty "
        "when ok), better (an improved one-sentence definition, empty when ok)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        row.get("Term", ""), row.get("Category", "") or "-",
        row.get("Source_Column", "") or "-",
        str(row.get("Definition") or "")[:300],
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def qa_definitions_rows(rows, model=None, compute=None, workers=None):
    """AI definition-QA pass over kept rows. Stamps QA_Issues / QA_Suggestion on
       rows the model flags (merging with any linter findings already present).
       Proposals only — the steward applies a suggestion explicitly. Returns
       (rows, flagged_count, used_llm)."""
    rows = [r for r in rows if isinstance(r, dict)]
    if not status(model)["online"]:
        return rows, 0, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    targets = [r for r in rows
               if str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")
               and (r.get("Term") or "").strip()]
    try:
        _warm(model)
    except Exception:
        pass

    def _do(r):
        try:
            return r, _qa_one(r, model=model, num_gpu=num_gpu)
        except Exception:
            return r, None

    if workers == 1 or len(targets) <= 1:
        results = [_do(r) for r in targets]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, targets))
    flagged = 0
    for r, res in results:
        if not isinstance(res, dict):
            continue
        ok = res.get("ok")
        issue = str(res.get("issue") or "").strip()
        if not _mostly_english(issue):
            continue
        if ok is False and issue:
            cur = [x for x in str(r.get("QA_Issues") or "").split(";") if x.strip()]
            if issue not in cur:
                cur.append(issue)
            r["QA_Issues"] = ";".join(cur)
            better = _clean_sentence(res.get("better"))
            if better and better.lower() != str(r.get("Definition") or "").strip().lower():
                r["QA_Suggestion"] = better
            flagged += 1
    return rows, flagged, True


# --------------------------------------------------- AI category proposer
# The same extension alphabet the suggester scans with - a dot AFTER one of
# these inside a slashed source is a column ("...file.csv.asset_id"), a dot
# BEFORE the first slash is the bucket ("bucket.gis/...").
_DOC_EXT_RX = re.compile(r"\.(csv|tsv|psv|json|jsonl|xml|txt|parquet|avro|"
                         r"ya?ml|pdf|docx?|xlsx?|pptx?)(?=\.|$)", re.I)


def _row_table(r):
    """The physical container a row's first source column lives in - a table
    for a database, the FILE (bucket-relative path) for a document. Pure, and
    shared by the evidence builder and the assignment step so they can never
    disagree. Field-caught: the old slash branch kept everything after the
    LAST slash, so a document column ("bucket.gis/assets.csv.asset_id")
    minted its own one-column 'table' - the categorize prompt then listed
    dozens of meaningless tables the model rightly refused to place."""
    sc = str(r.get("Source_Column") or "").split(";")[0].strip()
    if not sc:
        # conceptual table-level rows (record terms) carry no source column,
        # but they NAME their table - without this they can never follow it
        # into its category, and their old groups survive every categorize
        return str(r.get("Source_Table") or "").strip()
    if "/" in sc:
        head = sc.split("/", 1)[0]
        s = sc.split(".", 1)[1] if "." in head else sc.split("/", 1)[1]
        m = _DOC_EXT_RX.search(s)
        if m:
            s = s[:m.end()]          # drop the trailing ".column" (if any)
        return s.rstrip("/")
    parts = sc.split(".")
    return parts[-2] if len(parts) >= 2 else parts[0]


def schema_evidence(rows):
    """Tables with their columns and FK targets, from the kept rows' own scan
    facts. This is the ER diagram as data - the model is shown STRUCTURE the
    scan proved, never asked to imagine one."""
    tables = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if str(r.get("Keep", "Y")).strip().lower() not in ("y", "yes", "true", "1"):
            continue
        t = _row_table(r)
        if not t:
            continue
        d = tables.setdefault(t, {"columns": set(), "refs": set()})
        for sc in str(r.get("Source_Column") or "").split(";"):
            sc = sc.strip()
            if sc and "/" not in sc:
                d["columns"].add(sc.split(".")[-1])
            elif sc:
                # document source: the column is whatever follows the file
                # extension ("...assets.csv.asset_id" -> asset_id; a JSONL
                # leaf keeps its dotted path). Without this, file tables
                # showed "-" for columns and gave the model nothing to hold.
                m = _DOC_EXT_RX.search(sc)
                if m and m.end() < len(sc):
                    d["columns"].add(sc[m.end():].lstrip("."))
        for col, k in (r.get("Source_Keys") or {}).items():
            if isinstance(k, dict) and k.get("ref"):
                ref = str(k["ref"]).split(".")
                rt = ref[-2] if len(ref) >= 2 else ref[0]
                if rt and rt != t:
                    d["refs"].add(rt)
    return tables


def propose_categories(rows, model=None, compute=None, max_categories=9,
                       target=None):
    """ONE call: propose business categories from the schema's own structure.

    The steward should not have to invent a taxonomy, and the model should not
    be allowed to imagine one - so the prompt carries exactly what the scan
    proved: each table, its columns, and which tables it references. FK links
    are the strongest signal (monthly_usage -> customers says more than any
    name). Returns (proposal, assignments, used_llm) where proposal is
    [{name, definition, tables}] and assignments aligns with rows, category or
    None. PROPOSES ONLY - the caller applies after the steward agrees, the
    Rename button adjusts, and Export pack freezes the outcome so later scans
    are deterministic.
    """
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    tables = schema_evidence(rows)
    if len(tables) < 2 or not status(model)["online"]:
        return [], [None] * len(rows), False
    lines_ = []
    for t, d in sorted(tables.items()):
        cols = ", ".join(sorted(d["columns"])[:24])
        refs = ("  (references: " + ", ".join(sorted(d["refs"])) + ")") if d["refs"] else ""
        lines_.append("- %s: %s%s" % (t, cols or "-", refs))
    # Structural cluster evidence, computed - not imagined. Tables joined by
    # FK references form one subject; path-named file "tables" cluster by
    # their top folder (the estate's own layout). Without this the model sees
    # a flat list and themes per-table - the field run turned 11 physical
    # groups into 11 renamed categories, zero consolidation.
    adj = {t: set() for t in tables}
    for t, d in tables.items():
        for r in d.get("refs", ()):
            if r in adj:
                adj[t].add(r)
                adj[r].add(t)
    for t in tables:
        m = re.match(r"([^/\\]+)[/\\]", t)
        if m:
            fam = "folder:" + m.group(1).lower()
            adj.setdefault(fam, set()).add(t)
            adj[t].add(fam)
    comps, seen_t = [], set()
    for t in sorted(adj):
        if t in seen_t:
            continue
        comp, stack = set(), [t]
        while stack:
            x = stack.pop()
            if x in seen_t:
                continue
            seen_t.add(x)
            comp.add(x)
            stack.extend(adj.get(x, ()))
        real = sorted(x for x in comp if not x.startswith("folder:"))
        if len(real) > 1:
            comps.append(real)
    cluster_hint = ""
    if comps:
        cluster_hint = (
            "The schema's own structure already clusters these tables\n"
            "(foreign-key links; shared folders):\n"
            + "\n".join("- " + ", ".join(c) for c in comps)
            + "\nTables clustered together belong in ONE category. Do not"
            " split a cluster\nacross categories without a strong business"
            " reason.\n\n"
        )
    # Adaptive ceiling, biased low: categories are business SUBJECTS, and
    # even a large estate rarely has more than a handful of those.
    hi = 8 if len(tables) >= 20 else max(3, min(int(max_categories), 6))
    # The RIGHT number is a judgement about this business, not something the
    # model can infer alone: the bias that stopped 11 renamed groups also
    # produced 3 where 5 read better (field). A steward's target leads.
    try:
        target = int(target) if target else None
    except (TypeError, ValueError):
        target = None
    if target:
        target = max(2, min(target, 12))
        hi = max(hi, target + 1)
    n_cats = hi
    aim = ""
    if target:
        aim = ("The steward is aiming for about %d categories - treat that as "
               "the target, not a hard limit: land within one either side "
               "unless the estate genuinely argues otherwise." % target) + chr(10)
    prompt = (
        "You are grouping a %sdata estate into business-glossary categories.\n"
        "Physical tables, their columns, and their foreign-key references:\n\n"
        "%s\n\n"
        "%s"
        "%s"
        "Take a HOLISTIC view: a category is a broad business SUBJECT (the\n"
        "handful of things this business runs on - e.g. its customers, its\n"
        "operations, its infrastructure, its compliance), NOT a theme per\n"
        "table. Decide how many subjects best tell this business's story\n"
        "(between 3 and %d - almost always 3-6), then place EVERY table in\n"
        "exactly one of them. Each category should hold SEVERAL tables.\n"
        "Your job is CONSOLIDATION: the estate above already has one physical\n"
        "group per table, so returning one category per table adds nothing.\n"
        "Before you answer, check your own list:\n"
        "- a category holding exactly ONE table is a RENAME, not an\n"
        "  abstraction - fold that table into the subject it serves;\n"
        "- if two candidate categories overlap (singular/plural, 'X' vs\n"
        "  'X Data', 'X' vs 'X Management'), MERGE them into the broader one.\n"
        "Category names are business ABSTRACTIONS in the language of the\n"
        "business - almost never a single table's name.\n\n"
        'Return JSON: {"categories": [{"name": "1-3 words",\n'
        '  "definition": "one sentence", "tables": ["..."]}]}'
    ) % ((COMPANY + " ") if COMPANY else "", "\n".join(lines_), cluster_hint, aim, n_cats)
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    try:
        _warm(model)
    except Exception:
        pass
    try:
        # ONE schema-wide call on a possibly-large model: the budget must
        # absorb model LOAD (a 27b pays 30-60s before generating) plus a long
        # completion. Too short and the symptom is "no pills + 'proposed
        # nothing usable'" - which reads as model quality when it is a clock
        # (field-caught: gemma3:27b "no pills and weird categories").
        # Floor 900s: the field measured 7:25 for this call on a real estate
        # (temp-0 full completion on a 12b) - the 360s floor cut it TWICE.
        # The timeout exists to catch dead models, not slow ones; the UI
        # narrates elapsed time while it runs.
        res = _complete_json(prompt, model=model, num_gpu=num_gpu,
                             timeout=max(TIMEOUT * 3, AI_PASS_TIMEOUT * 2, 900),
                             options={"temperature": 0, "seed": 42,
                                      "num_ctx": 16384})
    except Exception:
        # A missing or broken model must degrade to "nothing proposed", never
        # surface as a 500 - the steward keeps the physical groups and moves on.
        return [], [None] * len(rows), False
    cats = (res or {}).get("categories")
    if not isinstance(cats, list):
        return [], [None] * len(rows), True
    known = {t.lower(): t for t in tables}
    table_cat, proposal = {}, []
    for c in cats:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        mine = []
        for t in (c.get("tables") or []):
            real = known.get(str(t).strip().lower())
            if real and real not in table_cat:       # first assignment wins
                table_cat[real] = name
                mine.append(real)
        if mine:
            proposal.append({"name": name,
                             "definition": str(c.get("definition") or "").strip(),
                             "tables": mine})
    # Mechanical completion over PROVEN structure: the model's job is naming
    # the subjects and seeding each cluster - finishing the placement is
    # bookkeeping the code does. An unplaced table inherits the category the
    # majority of its cluster-mates (FK links, shared folders) were given.
    # Field-caught: on a 35-table estate the model placed a fraction and 30
    # tables kept physical groups, so 5 proposed subjects still yielded a
    # 16-category grid. This is inference from evidence, not guessing: a
    # table follows its own cluster or stays put.
    for comp in comps:
        placed = sorted(table_cat[t] for t in comp if t in table_cat)
        if not placed:
            continue                      # whole cluster unplaced - reported below
        win = max(sorted(set(placed)), key=placed.count)
        for t in comp:
            if t not in table_cat:
                table_cat[t] = win
                entry = next((p for p in proposal if p["name"] == win), None)
                if entry:
                    entry["tables"] = sorted(set(entry["tables"]) | {t})
    # Cluster-islands (a folder with one file, an FK-isolated table) can never
    # inherit, and the field walk showed the schema-wide call skips a handful
    # of them - each skip keeps a physical group alive, so 4 proposed subjects
    # still left a 13-category grid. One small SECOND call places just the
    # leftovers, guardrailed to the model's OWN category list: the choice is
    # constrained, it lands as pills the steward approves, and a table the
    # model still refuses stays honestly physical.
    leftover = sorted(t for t in tables if t not in table_cat)
    if leftover and proposal:
        by_name = {p["name"].lower(): p["name"] for p in proposal if p["name"]}
        cat_lines = "\n".join("- %s: %s" % (p["name"], p["definition"] or "-")
                              for p in proposal if p["name"])
        tbl_lines = "\n".join("- %s: %s" % (
            t, ", ".join(sorted(tables[t]["columns"])[:12]) or "-")
            for t in leftover)
        p2 = (
            "These business-glossary categories are settled:\n%s\n\n"
            "Place EACH remaining table into exactly ONE of those categories\n"
            "(use the category names verbatim; every table gets a placement):\n"
            "%s\n\n"
            'Return JSON: {"placements": {"table name": "category name"}}'
        ) % (cat_lines, tbl_lines)
        try:
            res2 = _complete_json(p2, model=model, num_gpu=num_gpu,
                                  timeout=max(TIMEOUT * 2, AI_PASS_TIMEOUT),
                                  options={"temperature": 0, "seed": 42})
        except Exception:
            res2 = None
        for t, cname in ((res2 or {}).get("placements") or {}).items():
            real = known.get(str(t).strip().lower())
            win = by_name.get(str(cname).strip().lower())
            if real and win and real not in table_cat:
                table_cat[real] = win
                entry = next((p for p in proposal if p["name"] == win), None)
                if entry:
                    entry["tables"] = sorted(set(entry["tables"]) | {real})
    assignments = [table_cat.get(_row_table(r)) for r in rows]
    # Tables the model left out twice AND whose whole cluster went unplaced
    # are REPORTED, never guessed: their rows keep the physical group the
    # scan gave them, visibly, for the steward.
    unassigned = sorted(t for t in tables if t not in table_cat)
    if unassigned:
        proposal.append({"name": "", "definition": "", "tables": unassigned,
                         "unassigned": True})
    return proposal, assignments, True


# ------------------------------------------------------------ AI categorizer
def categorize_rows(rows, categories, model=None, compute=None, workers=None,
                    only_blank=True):
    """AI category assignment: for rows with no meaningful category (or all rows
       when only_blank=False) the model picks ONE category from the known list.
       Guardrails: the choice must be in the list, everything else is ignored.
       Returns (rows, updated_count, used_llm)."""
    rows = [r for r in rows if isinstance(r, dict)]
    cats = [str(c).strip() for c in (categories or []) if str(c).strip()]
    if not cats or not status(model)["online"]:
        return rows, 0, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    generic = {"", "general", "uncategorized", "uncategorised", "other", "misc"}
    targets = [r for r in rows
               if str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")
               and (r.get("Term") or "").strip()
               and (not only_blank or str(r.get("Category") or "").strip().lower() in generic)]
    if not targets:
        return rows, 0, True
    try:
        _warm(model)
    except Exception:
        pass

    def _do(r):
        prompt = (
            "Assign the business-glossary category%s for the term \"%s\".\n"
            "Definition: %s\nPhysical column(s): %s\n"
            "Categories (choose EXACTLY one): %s\n\n"
            "Return JSON with keys: category."
        ) % (
            (" at " + COMPANY) if COMPANY else "",
            r.get("Term", ""), str(r.get("Definition") or "")[:200],
            r.get("Source_Column", "") or "-", ", ".join(cats),
        )
        try:
            return r, _complete_json(prompt, model=model, num_gpu=num_gpu)
        except Exception:
            return r, None

    if workers == 1 or len(targets) <= 1:
        results = [_do(r) for r in targets]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, targets))
    updated = 0
    by_lower = {c.lower(): c for c in cats}
    for r, res in results:
        if not isinstance(res, dict):
            continue
        cat = by_lower.get(str(res.get("category") or "").strip().lower())
        if cat and cat != r.get("Category"):
            r["Category"] = cat
            r["AI_Suggested"] = "Yes"
            updated += 1
    return rows, updated, True


# ------------------------------------------------------------ AI pending-term review
_PENDING_ACTIONS = {"approve": "approve", "reject": "reject", "alias": "alias"}

def _pending_one(item, governed, model=None, num_gpu=None):
    """One candidate-term judgment. Returns the parsed proposal dict or None."""
    bits = []
    if item.get("category"):
        bits.append("category seen: %s" % item["category"])
    if item.get("definition"):
        bits.append("definition: %s" % str(item["definition"])[:200])
    if item.get("sources"):
        srcs = item["sources"]
        bits.append("seen in %d source column(s): %s%s"
                    % (len(srcs), "; ".join(srcs[:3]),
                       (" (+%d more)" % (len(srcs) - 3)) if len(srcs) > 3 else ""))
    if item.get("sensitivity"):
        bits.append("sensitivity: %s" % item["sensitivity"])
    if item.get("pattern"):
        bits.append("profiled value pattern: %s" % item["pattern"])
    if item.get("tags"):
        bits.append("tags: %s" % "; ".join(item["tags"][:5]))
    prompt = (
        "You are the data steward%s reviewing a CANDIDATE business term a scan "
        "found, deciding whether it enters the governed vocabulary.\n"
        "Candidate: \"%s\"\n- %s\n\n"
        "Existing governed terms: %s\n\n"
        "Decide ONE action:\n"
        "- approve: a concept the business asks about or runs on. The test is "
        "\"would someone in the business ask for this by name?\" - statuses, "
        "lifecycle states and operational measures COUNT (\"Account Status\", "
        "\"Active Customers\" are business vocabulary: the business asks what "
        "an account's status is and how many customers are active). "
        "Operational is NOT the same as technical, and narrow-but-real beats "
        "broad-but-vague.\n"
        "- alias: the SAME concept as one existing governed term (a synonym, "
        "abbreviation or misspelling of it) - name that term as target. Never "
        "alias a specific concept into a vaguer one (\"Alert Date\" into "
        "\"Date\" governs nothing).\n"
        "- reject: structural or file artifacts only - surrogate keys and "
        "ids, fragments, a field of a one-off dated snapshot file, or a name "
        "too vague for anyone to ever ask for (\"Data\", \"Value\").\n\n"
        "Breadth is evidence FOR the vocabulary, never against it: a candidate "
        "seen across MANY tables or files is a cross-cutting business concept, "
        "and one consolidated from several sources may embody the steward's "
        "own merge decision - never advise retiring it as 'too technical'.\n"
        "Names and labels of operational things (System Name, Site Name) ARE "
        "business vocabulary: the test is asking for something by name, and a "
        "name is precisely how the business asks. That the named thing is "
        "infrastructure does not make its name technical.\n"
        "Derived and CALCULATED columns (totals, rates, conversions, per-unit "
        "measures) are business MEASURES - frequently the KPIs the business "
        "runs on - never a 'technical calculation' to reject: Total Before "
        "Tax is how billing reports, a tier-to-gallons factor is how a tiered "
        "rate bills. The formula belongs IN the definition; being computed is "
        "not a disqualifier.\n"
        "For id / identifier candidates the tell is the VALUE SHAPE: a "
        "distinctive coded format (a profiled value pattern in the evidence, "
        "like a prefixed code) means people quote it - business vocabulary, "
        "approve (a Meter ID is read off the hardware). No pattern - a bare "
        "sequential integer that only joins tables - is a surrogate key: "
        "reject.\n"
        "Rejection is DURABLE: a rejected term is never proposed again, while "
        "a wrong approve costs the steward one click later. When uncertain, "
        "approve - and let the rationale say why you hesitated.\n"
        "Return JSON with keys: action (approve, alias or reject), target (the "
        "existing governed term when action is alias, else empty), rationale "
        "(one short sentence)."
    ) % (
        (" at " + COMPANY) if COMPANY else "",
        item.get("name", ""),
        "\n- ".join(bits) if bits else "(no context captured)",
        ", ".join(governed[:80]) or "(none)",
    )
    return _complete_json(prompt, model=model, num_gpu=num_gpu)


def review_pending_terms(pending, governed, model=None, compute=None, workers=None):
    """AI adjudication of scan-found candidate terms. For each pending item the
       model proposes approve / alias-of / reject with a rationale; guardrails:
       the action must be one of the three, an alias target must be an existing
       governed term (else the advice downgrades to approve), and nothing is
       applied - the steward clicks. Returns ({name: {action, target, reason}},
       used_llm)."""
    pending = [x for x in (pending or []) if isinstance(x, dict) and x.get("name")]
    gov = [str(g) for g in (governed or []) if str(g).strip()]
    if not pending or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    gov_lower = {g.lower(): g for g in gov}
    try:
        _warm(model)
    except Exception:
        pass

    def _do(item):
        try:
            return item, _pending_one(item, gov, model=model, num_gpu=num_gpu)
        except Exception:
            return item, None

    if workers == 1 or len(pending) <= 1:
        results = [_do(x) for x in pending]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, pending))

    out = {}
    for item, res in results:
        if not isinstance(res, dict):
            continue
        action = _PENDING_ACTIONS.get(str(res.get("action") or "").strip().lower())
        if not action:
            continue
        target = gov_lower.get(str(res.get("target") or "").strip().lower(), "")
        if action == "alias" and not target:
            action = "approve"                     # bad target: fail safe
        why = str(res.get("rationale") or "").strip()[:200]
        if not _mostly_english(why):
            why = ""
        # Deterministic BREADTH GUARD around the model: advice must never
        # recommend the durable action against a term the estate keeps
        # vouching for. A candidate seen in 3+ source columns is a
        # cross-cutting concept — very often the steward's own Merge — so a
        # model "reject" downgrades to approve with the guard named
        # (field-caught: it advised retiring "System Name", a five-source
        # steward merge, as "a technical infrastructure component"). The
        # steward can still retire by hand; sovereignty stays with the click.
        n_src = len(item.get("sources") or ())
        if action == "reject" and n_src >= 3:
            action = "approve"
            why = ("breadth guard: seen in %d source columns — a "
                   "cross-cutting concept (possibly your own merge); retire "
                   "only by deliberate choice. The model argued: %s"
                   % (n_src, why or "reject"))[:200]
        elif action == "reject" and (item.get("pattern") or "").strip():
            # the scan proved a distinctive value format — identifiers people
            # quote are vocabulary by our own rule, so advice may not call
            # them noise. The steward can still disagree by hand.
            action = "approve"
            why = ("pattern guard: values carry the distinctive format %s — "
                   "quoted identifiers are vocabulary; retire only by "
                   "deliberate choice. The model argued: %s"
                   % (item.get("pattern"), why or "reject"))[:200]
        if action == "alias" and target:
            # folding a SPECIFIC concept into a VAGUER one governs nothing
            # ("Alert Date" into "Date") — the prompt asks the model not to,
            # this guarantees it: a target whose words are a strict subset of
            # the candidate's is the vaguer generalization. Abbreviation folds
            # ("Cust ID" into "Customer Identifier") share no word set and
            # pass untouched.
            cand_w = {w for w in re.split(r"[^a-z0-9]+", item["name"].lower()) if w}
            tgt_w = {w for w in re.split(r"[^a-z0-9]+", target.lower()) if w}
            if tgt_w and tgt_w < cand_w:
                why = ("alias guard: \"%s\" is broader than the candidate — "
                       "folding specific into vague governs nothing. The "
                       "model argued: %s" % (target, why or "alias"))[:200]
                action = "approve"
                target = ""
        out[item["name"]] = {"action": action, "target": target,
                             "reason": ("AI: " + why) if why else "AI review"}
    return out, True


# ------------------------------------------------------------ AI domain pick
def suggest_domain(company, categories, terms, domains, model=None, compute=None):
    """Pick the ONE PDC business-domain classifier that best fits this company,
       from the caller-supplied list. Guardrail: the answer must be in the list
       (else None). Returns (domain|None, used_llm)."""
    doms = [str(d) for d in (domains or []) if str(d).strip()]
    if not doms or not status(model)["online"]:
        return None, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    prompt = (
        "Classify the business domain of this organization for a data catalog.\n"
        "Company: %s\n"
        "Glossary categories: %s\n"
        "Sample business terms: %s\n\n"
        "Choose EXACTLY one domain from this list: %s\n"
        "Return JSON with keys: domain."
    ) % (
        company or "(unknown)",
        ", ".join((categories or [])[:12]) or "(none)",
        ", ".join((terms or [])[:15]) or "(none)",
        ", ".join(doms),
    )
    res = _complete_json(prompt, model=model, num_gpu=num_gpu)
    if isinstance(res, dict):
        by_lower = {d.lower(): d for d in doms}
        return by_lower.get(str(res.get("domain") or "").strip().lower()), True
    return None, True


# ------------------------------------------------------------ AI term matcher
def match_terms(items, model=None, compute=None, workers=None):
    """Resolve-stage adjudicator: an outstanding term name (usually renamed or
       disambiguated locally AFTER the glossary was imported) against the
       candidate term names that actually exist in PDC. The model picks the
       candidate that is the SAME business concept, or none. Guardrails: the
       answer must be one of the candidates; nothing is bound automatically —
       the steward clicks. items: [{name, definition?, candidates: [names]}].
       Returns ({name: {match|None, reason}}, used_llm)."""
    items = [x for x in (items or [])
             if isinstance(x, dict) and x.get("name") and x.get("candidates")]
    if not items or not status(model)["online"]:
        return {}, False
    num_gpu = 0 if compute == "cpu" else (99 if compute == "gpu" else None)
    if workers is None:
        workers = WORKERS
    workers = max(1, min(workers, 16))
    try:
        _warm(model)
    except Exception:
        pass

    def _do(it):
        prompt = (
            "A business glossary term was renamed locally AFTER the glossary was "
            "imported into the data catalog, so its old name still lives there.\n"
            "Local term: \"%s\"\n%s"
            "Candidate terms that exist in the catalog: %s\n\n"
            "Pick the ONE candidate that is the SAME business concept (an earlier "
            "name, a less/more qualified form, an abbreviation), or none if none "
            "match. Return JSON with keys: match (the candidate name or empty), "
            "rationale (one short sentence)."
        ) % (
            it["name"],
            ("Definition: %s\n" % str(it["definition"])[:200]) if it.get("definition") else "",
            ", ".join(it["candidates"][:25]),
        )
        try:
            return it, _complete_json(prompt, model=model, num_gpu=num_gpu)
        except Exception:
            return it, None

    if workers == 1 or len(items) <= 1:
        results = [_do(x) for x in items]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_do, items))

    out = {}
    for it, res in results:
        if not isinstance(res, dict):
            continue
        by_lower = {c.lower(): c for c in it["candidates"]}
        match = by_lower.get(str(res.get("match") or "").strip().lower())
        why = str(res.get("rationale") or "").strip()[:200]
        if not _mostly_english(why):
            why = ""
        out[it["name"]] = {"match": match,
                           "reason": ("AI: " + why) if why else ("AI match" if match else "AI: no candidate is the same concept")}
    return out, True
