"""
api.py — FastAPI backend for the Glossary Suggester.

The FastAPI port of the old Flask app.py: same /api contract route-for-route
plus
interactive docs at /docs and additive start/poll job endpoints (/api/jobs/*)
for the long-running PDC work — the SSE/NDJSON streaming endpoints are kept
byte-compatible for the current UI, the job endpoints are the forward path for
the React UI.

The web layer is a thin adapter: every engine module (suggester, tagdict,
llm, pdc_api → pdc_client, …) is unchanged.

Run:  python -m uvicorn api:app          (from glossary_generator/, port 5000
      via run.sh / run.ps1)
"""
import io
import json
import os
import re
import time
import threading
import queue as _queue_mod
import uuid

from fastapi import FastAPI, Body, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(__file__)

def _load_dotenv(path=None):
    """Minimal, dependency-free .env loader. Reads KEY=VALUE lines from a .env
       file beside api.py (or $GLOSSARY_ENV) and sets them in os.environ WITHOUT
       overriding anything already set in the real environment. Supports # comments,
       blank lines, optional surrounding quotes, and a leading 'export '. Silent if
       the file is absent. Runs BEFORE the local imports below so values like
       GLOSSARY_DOMAIN_PACK (the scenario bundle, read at suggester import time),
       PORT and OLLAMA_URL all take effect from one file."""
    path = path or os.environ.get("GLOSSARY_ENV") or os.path.join(HERE, ".env")
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if (len(val) >= 2) and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

from core import paths
from engine import suggester
from engine import tagdict
from core import audit
from engine import similarity
from engine import policy_draft
from engine import defqa
from engine import packgen
from ai import llm
from ai import llm_providers
from ai import llm_detect
from sources import dbconn
from sources import seed_sample

def _app_version():
    """Single source of truth for the app version: the VERSION file beside api.py,
       falling back to the literal below if it's missing."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return "1.9.0"

APP_VERSION = _app_version()

app = FastAPI(
    title="PDC Glossary Generator",
    version=APP_VERSION,
    docs_url=None,   # replaced by the SELF-CONTAINED /docs below — FastAPI's
                     # default pulls Swagger's css/js from cdn.jsdelivr.net,
                     # which is blocked in the desktop shell and dead offline,
                     # so "API · docs" rendered a blank page (field-caught
                     # 2026-08-23 mid-walkthrough)
    description=(
        "Build a Pentaho Data Catalog business glossary from a live data estate: "
        "**Connect → Review → Dictionary → Govern → Resolve → Apply**.\n\n"
        "Scans PostgreSQL/MySQL/Oracle/SQL Server + MinIO/S3 (or a DDL file), "
        "suggests terms, enriches them with a local Ollama model, governs the tag "
        "dictionary, generates import-ready JSONL, then resolves term ids and "
        "applies them to PDC.\n\n[← Back to the app](/)"
    ),
)

def _err(message, status_code):
    """Error payload in the app's contract shape: {'error': msg} + HTTP status
       (the UI checks data.error — never FastAPI's default {'detail': ...})."""
    return JSONResponse({"error": message}, status_code=status_code)


# ---- crash forensics -------------------------------------------------------
# A field crash ("the window closed itself" on AI categorize) left NOTHING to
# read: the packaged shell buffers backend stdout in memory only, and the
# WebView wrote no dump. app.log in the state dir is the durable record -
# backend exceptions land here via logging, and the frontend beacons its
# uncaught errors to /api/client-log below. Rotating and small: 1 MB x 3.
import logging
import logging.handlers

class _ForensicsHandler(logging.handlers.RotatingFileHandler):
    """Open-write-close per record. The log must never hold the state dir
    hostage: the fresh-install wipe deletes that dir under a RUNNING server
    (test-pinned), and Windows cannot delete a directory containing an open
    file. Volume is low (errors + lifecycle lines), so per-record reopen is
    cheap - and _open self-heals the directory like every other writer."""
    def emit(self, record):
        try:
            super().emit(record)
        finally:
            self.close()

    def _open(self):
        try:
            os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        except OSError:
            pass
        return super()._open()


def _setup_file_log():
    try:
        path = os.path.join(paths.state_dir(), "app.log")
        h = _ForensicsHandler(
            path, maxBytes=1_000_000, backupCount=2, encoding="utf-8", delay=True)
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"))
        h.setLevel(logging.INFO)
        # handler on the ROOT only: uvicorn/client loggers PROPAGATE there,
        # and attaching to both wrote every line twice (field-caught)
        root = logging.getLogger("")
        if not any(isinstance(x, logging.handlers.RotatingFileHandler)
                   and getattr(x, "baseFilename", "") == h.baseFilename
                   for x in root.handlers):
            root.addHandler(h)
        for name in ("", "uvicorn", "uvicorn.error", "client"):
            lg = logging.getLogger(name)
            if lg.level in (logging.NOTSET, logging.WARNING):
                lg.setLevel(logging.INFO)
    except Exception:
        pass  # forensics must never block startup

_setup_file_log()


@app.post("/api/client-log")
def api_client_log(body: dict = Body(default={})):
    """The frontend's black box: window.onerror / unhandledrejection beacon
    here (sendBeacon survives page teardown - exactly the moment worth
    recording). Appends to app.log; truncated and never fails the caller."""
    try:
        kind = str(body.get("kind") or "error")[:32]
        msg = str(body.get("message") or "")[:2000]
        stack = str(body.get("stack") or "")[:4000]
        url = str(body.get("url") or "")[:200]
        logging.getLogger("client").error(
            "%s %s %s%s", kind, url, msg, ("\n" + stack) if stack else "")
    except Exception:
        pass
    return {"ok": True}

# No default path: /mnt/user-data/uploads/... was the authoring machine's
# layout and means nothing on a customer install. Unset is honest; the DDL
# field asks for a path when one is needed.
DEFAULT_DDL = os.environ.get("GLOSSARY_DDL", "")
PEOPLE_FILE = paths.state_path("people.json", "GLOSSARY_PEOPLE")
# Optional scenario seed roster (e.g. the CSCU people that ship with the credit-union
# domain pack). Copied into the live PEOPLE_FILE once, only when that file is missing or
# its roster is empty — so a fresh /data volume (Docker) or fresh checkout (run.sh) gets
# the seeded roster, but live edits are never overwritten. Unset = generic empty roster.
PEOPLE_SEED = os.environ.get("GLOSSARY_PEOPLE_SEED", "")
CONN_FILE = paths.state_path("connections.json", "GLOSSARY_CONNECTIONS")
SETTINGS_FILE = paths.state_path("settings.json", "GLOSSARY_SETTINGS")
GLOSS_FILE = paths.state_path("glossaries.json", "GLOSSARY_GLOSSARIES")
# Registry artifacts written at export time (consumed by the standalone Policy Generator).
# Use REGISTRY_DIR everywhere, never a fresh os.path.join(HERE, "registries") - the
# State snapshot/restore pair did exactly that and so ignored the env override it
# documented, which under a packaged install meant restoring into Program Files.
REGISTRY_DIR = paths.state_path("registries", "GLOSSARY_REGISTRY_DIR")

def _registry_path(glossary_name):
    """Path of the Registry file for a glossary, keyed by its deterministic id so the
       export step and the resolve step touch the same versioned file."""
    return os.path.join(REGISTRY_DIR, f"registry.{suggester.det_glossary_id(glossary_name)}.json")


# ---- estate receipts -------------------------------------------------------
# Every closing artifact leaves a RECEIPT (what, when, headline counts) so the
# Estate Report can verify the handoff contract from facts on disk instead of
# trusting ticked boxes ("checks that all the required estate docs are in
# place ready for Policy Generator").
RECEIPTS_FILE = paths.state_path("estate_receipts.json", "GLOSSARY_RECEIPTS")

def _receipt(kind, **data):
    try:
        import datetime
        r = _read_json(RECEIPTS_FILE, {})
        r[kind] = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
                   **{k: v for k, v in data.items() if v is not None}}
        _write_json(RECEIPTS_FILE, r)
    except Exception:
        pass  # a receipt must never fail the action it records

DEFAULT_SETTINGS = {"theme": "light",
                    "model": os.environ.get("LLM_MODEL", "llama3.2:3b"),
                    "compute": "auto",
                    "glossary_name": "Business Glossary (Suggested)", "show_help": True,
                    "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
                    "llm_timeout": float(os.environ.get("LLM_TIMEOUT", "30")),
                    "company": os.environ.get("GLOSSARY_COMPANY", "your organization"),
                    "llm_workers": llm._clampint(os.environ.get("LLM_WORKERS", "4"), 4, 1, 16),
                    "llm_batch": llm._clampint(os.environ.get("LLM_BATCH", "6"), 6, 1, 20),
                    # LLM provider: ollama (local) or a hosted one. API keys are
                    # deliberately NOT here — they live in llm_providers' in-memory
                    # store or the provider's env var, so the State snapshot (which
                    # zips settings.json) never carries billing credentials.
                    "llm_provider": os.environ.get("LLM_PROVIDER", "ollama"),
                    "azure_endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                    "azure_api_version": os.environ.get(
                        "AZURE_OPENAI_API_VERSION", llm_providers.DEFAULT_AZURE_API_VERSION)}

# Never persisted to settings.json, whatever a client sends (see above).
_CREDENTIAL_FIELDS = {"api_key", "apikey", "key", "secret", "token",
                      "anthropic_api_key", "openai_api_key",
                      "google_api_key", "azure_openai_api_key"}

def _read_json(path, default):
    """Read and JSON-parse `path`, returning `default` when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

_WRITE_JSON_LOCK = threading.Lock()

def _write_json(path, data):
    """Serialise `data` to `path` as pretty-printed JSON, atomically.
       Writes to a temp file in the same directory then os.replace()s it into
       place, so a crash mid-write can never truncate or corrupt the target
       (e.g. people.json / settings.json).
       A process-wide lock serialises writers, and the replace retries briefly:
       on Windows os.replace fails with PermissionError while ANY other handle
       holds the target open — a concurrent _read_json in another request
       thread, or an antivirus scan — so back-to-back settings saves 500'd."""
    import tempfile, time
    d = os.path.dirname(os.path.abspath(path)) or "."
    with _WRITE_JSON_LOCK:
        # SELF-HEALING: recreate the state directory if it vanished under a
        # running server (field-caught on a fresh install - the user wiped
        # %APPDATA%\com.pentaho.pdc-glossary after launch, and every write
        # endpoint 500'd with FileNotFoundError while reads kept working)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            for attempt in range(10):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

def _load_people():
    """Load the saved people roster (list of account dicts) from disk."""
    data = _read_json(PEOPLE_FILE, [])
    return data.get("people", []) if isinstance(data, dict) else (data or [])

def _save_people(people):
    """Persist the people roster to disk."""
    _write_json(PEOPLE_FILE, {"people": people})

def _seed_people_if_empty():
    """If a scenario seed roster is configured (GLOSSARY_PEOPLE_SEED) and the live
       roster is missing or empty, copy the seed in once. Never overwrites a roster
       that already has people, so user edits and Keycloak fetches always win."""
    if not PEOPLE_SEED:
        return
    try:
        if _load_people():          # live roster already has people -> leave it alone
            return
        seed = _read_json(PEOPLE_SEED, None)
        people = seed.get("people", []) if isinstance(seed, dict) else (seed or [])
        if people:
            _save_people(people)
    except Exception:
        pass                        # seeding is best-effort; never block startup

_seed_people_if_empty()

def _load_connections():
    """Load the saved data-source connections from disk."""
    data = _read_json(CONN_FILE, {"connections": []})
    return data.get("connections", []) if isinstance(data, dict) else (data or [])

def _save_connections(conns):
    """Persist the saved data-source connections to disk."""
    _write_json(CONN_FILE, {"connections": conns})

def _load_settings():
    """Return the settings, layered over the built-in DEFAULT_SETTINGS. Blank LLM
       fields fall back to the env-derived defaults so the effective value is always
       reported (and a cleared field reverts to the corresponding env var)."""
    s = dict(DEFAULT_SETTINGS); s.update(_read_json(SETTINGS_FILE, {}))
    for k in ("ollama_url", "llm_timeout", "company", "llm_workers", "llm_batch"):
        if not s.get(k):
            s[k] = DEFAULT_SETTINGS[k]
    return s

def _apply_llm_settings(s=None):
    """Push the saved LLM config (Ollama URL / model / timeout / company / workers /
       batch) into the LLM client so a change on the Settings page takes effect
       immediately, without a restart. A saved value overrides the environment
       default; a blank value leaves the env default in place."""
    s = s or _load_settings()
    llm.configure(ollama_url=s.get("ollama_url") or None,
                  model=s.get("model") or None,
                  timeout=s.get("llm_timeout"),
                  company=s.get("company") or None,
                  workers=s.get("llm_workers"),
                  batch=s.get("llm_batch"))
    llm_providers.configure(provider=s.get("llm_provider") or None,
                            azure_endpoint=s.get("azure_endpoint"),
                            azure_api_version=s.get("azure_api_version") or None)

_apply_llm_settings()       # apply persisted LLM settings at startup

def _stats(rows):
    """Summarise a row set (term/category/confidence/sensitivity/PII/enriched counts) for the UI badges."""
    from collections import Counter
    return {"terms": len(rows),
            "categories": len({r.get("Category", "") for r in rows}),
            "confidence": dict(Counter(r.get("Confidence", "") for r in rows)),
            "sensitivity": dict(Counter(r.get("Sensitivity", "") for r in rows)),
            "pii": sum(1 for r in rows if r.get("PII_Category")),
            "enriched": sum(1 for r in rows if r.get("LLM_Enriched") == "Yes")}

@app.get("/", include_in_schema=False)
def index(request: Request):
    """Serve the single-page application shell.

    There is one UI: the React build in frontend/dist. A Jinja shell used to
    stand in when that was absent, but the React build superseded it at 1.11 and
    the fallback then went twenty releases without being exercised against the
    current API - so on the one occasion it fired it would have rendered a
    1.11-era page against this backend. An honest error beats a stale UI.
    """
    dist_index = os.path.join(os.path.dirname(HERE), "frontend", "dist", "index.html")
    if not os.path.isfile(dist_index):
        return _err("The web UI has not been built. From the repo root: "
                    "cd frontend && npm ci && npm run build", 503)
    # MUST revalidate. This file names the content-hashed bundle, so a stale copy
    # loads the previous release's JS - the app upgrades on disk and the user
    # still sees the old UI with no clue why. `no-cache` means "revalidate", not
    # "do not store", so 304s still apply.
    return FileResponse(dist_index, headers={"Cache-Control": "no-cache"})

# Brand favicon — an inline SVG (the 2026 black Pentaho tile: white capital P
# over the red accent bar, matching the app icon), served for both /favicon.svg
# and the browser's automatic /favicon.ico probe, so neither 404s and no binary
# asset has to ship.
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#17171b"/><stop offset="1" stop-color="#0c0c0e"/>'
    '</linearGradient></defs>'
    '<rect width="32" height="32" rx="7" fill="url(#g)"/>'
    '<text x="15.5" y="21.5" font-family="\'Segoe UI Semibold\',\'Segoe UI\',Arial,sans-serif" '
    'font-size="19" font-weight="650" fill="#fff" text-anchor="middle">P</text>'
    '<rect x="7" y="25" width="18" height="2" rx="1" fill="#cc0000"/>'
    '</svg>'
)

@app.get("/favicon.svg", include_in_schema=False)
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return the favicon — the React build's own icon when dist exists, else
    the inline brand SVG (modern browsers render SVG favicons fine)."""
    dist_icon = os.path.join(os.path.dirname(HERE), "frontend", "dist", "favicon.svg")
    if os.path.isfile(dist_icon):
        return FileResponse(dist_icon, headers={"Cache-Control": "public, max-age=86400"})
    return Response(FAVICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})

_SWAGGER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "static", "swagger-ui")


@app.get("/docs", include_in_schema=False)
def swagger_docs():
    """Self-contained Swagger UI — assets vendored, no CDN, works in the
    desktop shell and offline. Carries a way back: the shell's webview has no
    browser chrome, so a same-tab navigation without one is a dead end."""
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDC Glossary Generator - API docs</title>
<link rel="stylesheet" href="/docs-assets/swagger-ui.css">
<style>#backbar{{padding:.55rem 1rem;background:#0c0c0e;font:600 14px system-ui}}
#backbar a{{color:#fff;text-decoration:none}}</style>
</head><body>
<div id="backbar"><a href="/">&#8592; Back to the Glossary Generator</a></div>
<div id="swagger-ui"></div>
<script src="/docs-assets/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({{url: "/openapi.json", dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis], layout: "BaseLayout"}});</script>
</body></html>""")


@app.get("/docs-assets/{name}", include_in_schema=False)
def swagger_assets(name: str):
    if name not in ("swagger-ui.css", "swagger-ui-bundle.js"):
        return _err("not found", 404)
    media = "text/css" if name.endswith(".css") else "application/javascript"
    return FileResponse(os.path.join(_SWAGGER_DIR, name), media_type=media,
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/health")
def health():
    """Liveness + dependency probe. Always 200 (the process is up); the body reports
       Ollama reachability so an orchestrator never kills the app just because the
       optional LLM enrichment backend is momentarily down."""
    s = llm.status()
    return {
        "status": "ok",
        "service": "glossary-suggester",
        "version": APP_VERSION,
        "ollama": {"online": s.get("online", False),
                   "model": s.get("model"),
                   "model_present": s.get("model_present", False)},
    }

@app.get("/api/version")
def app_version():
    """Return the running app version."""
    return {"version": APP_VERSION, "service": "glossary-generator"}

@app.get("/api/whatsnew")
def api_whatsnew():
    """The running build's release notes: the top sections of docs/CHANGELOG.md
    (which lives OUTSIDE the app folder — absent in e.g. the Docker image, so
    degrade to an empty list). Lets the sidebar version pill show what THIS
    build contains — a two-second stale-deployment check. The changelog is
    read fresh on every call while APP_VERSION was read at process start, so
    a leading changelog version newer than APP_VERSION means the checkout
    was updated but the app not restarted."""
    import re as _re
    releases = []
    try:
        path = os.path.join(HERE, "..", "docs", "CHANGELOG.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for m in _re.finditer(r"^## \[([^\]]+)\][ \t]*[—–-]*[ \t]*([^\n]*)\n(.*?)(?=^## \[|\Z)",
                              text, _re.S | _re.M):
            releases.append({"version": m.group(1).strip(),
                             "date": m.group(2).strip(),
                             "body": m.group(3).strip()})
            if len(releases) >= 5:
                break
    except Exception:
        releases = []
    return {"version": APP_VERSION, "releases": releases}

_SECRET_HINT = ("KEY", "TOKEN", "SECRET", "PASS", "PWD")

@app.get("/config")
def show_config():
    """Effective runtime configuration, with anything secret-looking masked.
       Handy for confirming env wiring inside a container."""
    def mask(name, val):
        return "***" if (val and any(h in name.upper() for h in _SECRET_HINT)) else val
    env = {k: mask(k, v) for k, v in os.environ.items()
           if k.startswith(("GLOSSARY_", "LLM_", "OLLAMA_", "HOST", "PORT"))}
    return {
        "version": APP_VERSION,
        # state_dir/state_dir_source answer "where did my glossary go?" without a
        # filesystem hunt - the one question a packaged install makes hard, since
        # the state no longer sits next to the executable.
        "state_dir": paths.state_dir(),
        "state_dir_source": paths.state_source(),
        "paths": {"ddl": DEFAULT_DDL, "people": PEOPLE_FILE, "connections": CONN_FILE,
                  "settings": SETTINGS_FILE, "glossaries": GLOSS_FILE,
                  "registries": REGISTRY_DIR, "domain_pack": paths.domain_pack_path()},
        "ollama_url": llm.OLLAMA_URL,
        "model_default": DEFAULT_SETTINGS.get("model"),
        "env": env,
    }

@app.get("/api/llm-status")
def llm_status(model: str = None):
    """Report local Ollama reachability and the currently selected model."""
    return llm.status(model)

@app.get("/api/detect")
def api_detect():
    """Host detection report for the Settings page: platform, RAM, NVIDIA VRAM
    (aggregated across GPUs), OLLAMA_* env, server status and a model
    recommendation sized to the hardware — multi-GPU rigs get
    OLLAMA_SCHED_SPREAD=1 suggested so Ollama layer-splits across cards."""
    return llm_detect.detection_report(llm.OLLAMA_URL).model_dump()

@app.get("/api/models")
def models():
    """List the models available from the local Ollama install."""
    return {"models": llm.list_models()}

@app.post("/api/pull-model")
def pull_model(body: dict = Body(default={})):
    """Stream model-download progress (NDJSON) from the user's local Ollama."""
    model = (body or {}).get("model") or None
    def gen():
        """Yield NDJSON model-download progress events streamed from Ollama."""
        for ev in llm.pull_stream(model):
            yield json.dumps(ev) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")

@app.get("/api/drivers")
def drivers():
    """Report which optional database / object-store drivers are installed."""
    return {"drivers": dbconn.driver_status()}

def _state_files():
    """Every file the app persists, as (absolute path, archive name). All of it
    is data-only JSON with self-healing loaders, so a snapshot from an older
    app version restores cleanly on a newer one — the app can change, the
    state format tolerates it. Paths honor the same env overrides the app
    itself uses."""
    from core import audit as _audit
    files = [(SETTINGS_FILE, "settings.json"),
             (CONN_FILE, "connections.json"),
             (GLOSS_FILE, "glossaries.json"),
             (PEOPLE_FILE, "people.json"),
             (tagdict.DICT_FILE, "tag_dictionary.json"),
             (_audit.AUDIT_FILE, "audit_log.json"),
             (paths.domain_pack_path(),
              "domain_pack.json")]
    rdir = REGISTRY_DIR
    if os.path.isdir(rdir):
        for f in sorted(os.listdir(rdir)):
            if f.endswith(".json"):
                files.append((os.path.join(rdir, f), "registries/" + f))
    return files

@app.get("/api/state-snapshot")
def api_state_snapshot():
    """Download the app's complete persisted state as one zip: connections,
    settings, saved glossaries, the governed dictionary, roster, audit trail,
    Registries and the installed domain pack. manifest.json records the app
    version it came from. NOTE: the working review grid lives in the browser —
    Save glossary first so it's inside glossaries.json."""
    import io as _io, zipfile, time
    buf = _io.BytesIO()
    included = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, arc in _state_files():
            if os.path.exists(path):
                z.write(path, arc)
                included.append(arc)
        z.writestr("manifest.json", json.dumps(
            {"app_version": APP_VERSION,
             "created": time.strftime("%Y-%m-%d %H:%M:%S"),
             "files": included}, indent=2))
    fname = "glossary-state-%s.zip" % time.strftime("%Y%m%d-%H%M%S")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=" + fname})

@app.post("/api/state-restore")
async def api_state_restore(request: Request):
    """Restore a state snapshot (raw zip body). Only recognized state files are
    written — each to the path the app currently reads it from (env overrides
    honored) — and every file that would be overwritten is backed up first as
    <file>.backup-<timestamp> beside itself. Unknown zip members are skipped
    and reported, never written."""
    import io as _io, zipfile, time, shutil
    try:
        z = zipfile.ZipFile(_io.BytesIO(await request.body()))
    except Exception:
        return _err("that is not a state-snapshot zip", 400)
    manifest = {}
    if "manifest.json" in z.namelist():
        try:
            manifest = json.loads(z.read("manifest.json"))
        except Exception:
            manifest = {}
    targets = {arc: path for path, arc in _state_files() if not arc.startswith("registries/")}
    ts = time.strftime("%Y%m%d-%H%M%S")
    restored, skipped, backed_up = [], [], 0
    for name in z.namelist():
        base = name.replace("\\", "/")
        if base == "manifest.json" or base.endswith("/"):
            continue
        if base in targets:
            dest = targets[base]
        elif (base.startswith("registries/") and base.endswith(".json")
              and "/" not in base[len("registries/"):]):
            dest = os.path.join(REGISTRY_DIR, os.path.basename(base))
        else:
            skipped.append(name)
            continue
        d = os.path.dirname(dest)
        if d:
            os.makedirs(d, exist_ok=True)
        if os.path.exists(dest):
            shutil.copy2(dest, dest + ".backup-" + ts)
            backed_up += 1
        with open(dest, "wb") as f:
            f.write(z.read(name))
        restored.append(base)
    # drop tagdict's in-memory document + compiled caches so the restored
    # dictionary takes effect immediately (load() serves the cached doc)
    try:
        with tagdict._LOCK:
            tagdict._DICT = None
            tagdict._COMPILED = tagdict._COMPILED_KEY = None
    except Exception:
        pass
    return {"restored": restored, "skipped": skipped, "backed_up": backed_up,
            "snapshot_version": manifest.get("app_version"),
            "running_version": APP_VERSION}

# Source files this app will expose for transparency (the "Under the hood" viewer).
#
# Keys are RELATIVE PATHS, so they follow the package layout rather than
# describing it separately - when the modules were grouped into core/ engine/
# ai/ sources/, a list of bare filenames would have quietly 404'd instead.
# cli/* is deliberately absent: those are developer entry points and the
# installer does not ship them, so serving them would fail on a real install.
# Whitelisted on purpose — runtime state (people.json, settings.json, secrets) is
# never served. This is a teaching tool: the learner can read exactly what runs.
# Keys are the stable names the UI shows; pdc_api/* keys resolve to the shared
# pdc_client package at the repo root (extracted in 1.9.0).
_SOURCE_WHITELIST = {
    "api.py":                  "FastAPI backend - every /api/* endpoint and how it dispatches.",
    "core/paths.py":           "Where state lives: the one place that decides which directory.",
    "core/audit.py":           "Append-only steward audit trail.",
    "engine/suggester.py":     "Scan + term suggestion: introspection, profiling, JSONL build.",
    "engine/similarity.py":    "Duplicate detection and the evidence rubric behind it.",
    "engine/tagdict.py":       "The governed Term & tag dictionary.",
    "engine/packgen.py":       "Grows a domain pack from reviewed rows.",
    "engine/packinit.py":      "Scaffolds a thin domain pack for a new company.",
    "engine/defqa.py":         "Definition linter.",
    "engine/policy_draft.py":  "Drafts PDC classification policies from the Registry.",
    "ai/llm.py":               "Model client used for definition/purpose enrichment.",
    "ai/llm_providers.py":     "Hosted providers: Anthropic, OpenAI/Azure, Google.",
    "ai/llm_detect.py":        "Host/GPU detection and model recommendation.",
    "sources/dbconn.py":       "Database connection + driver handling for the live scan.",
    "sources/seed_sample.py":  "Seeds a sample dataset into a schema for demos.",
    "pdc_api/core.py":     "PDC public-API client: transport, auth, response helpers.",
    "pdc_api/entities.py": "PDC public-API client: entity filter/resolve + catalog harvest.",
    "pdc_api/terms.py":    "PDC public-API client: term resolution and id stamping.",
    "pdc_api/jobs.py":     "PDC public-API client: jobs (trust score, discovery, profiling).",
    "pdc_api/apply.py":    "PDC public-API client: merge + PATCH write-back.",
    "pdc_api/bulkload.py": "PDC public-API client: bulk data-source loader.",
}

def _source_path(key):
    """Filesystem path for a whitelisted source key. pdc_api/<mod>.py lives in
       the shared pdc_client package at the repo root since the extraction."""
    if key.startswith("pdc_api/"):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "pdc_client", key.split("/", 1)[1])
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), key)

@app.get("/api/source")
def get_source(file: str = ""):
    """Return the text of one whitelisted source file (transparency viewer)."""
    f = (file or "").strip()
    if f == "":
        return {"files": [{"file": k, "note": v} for k, v in _SOURCE_WHITELIST.items()]}
    if f not in _SOURCE_WHITELIST:
        return _err("that file is not exposed", 404)
    try:
        with open(_source_path(f), "r", encoding="utf-8") as fh:
            content = fh.read()
        return {"file": f, "note": _SOURCE_WHITELIST[f],
                "content": content, "lines": content.count("\n") + 1}
    except Exception as e:
        return _err(str(e), 500)

@app.get("/api/people")
def people():
    """Return the saved people roster."""
    return {"people": _load_people()}

@app.post("/api/people")
def save_people(body: dict = Body(default={})):
    """Persist the people roster supplied by the client."""
    people = (body or {}).get("people", [])
    _save_people(people)
    return {"people": people, "saved": True}

@app.post("/api/keycloak-users")
def keycloak_users(body: dict = Body(default={})):
    """Fetch the user roster live from Keycloak's Admin API. Accepts either a bearer
       token, or username/password (admin-cli password grant). Returns roster rows.

       PDC fronts Keycloak at <server>/keycloak, so base_url is e.g.
       'https://host/keycloak'. The admin token comes from the 'master' realm by
       default (where the Keycloak admin user lives), while users are listed from
       the target 'realm' (e.g. 'pdc'). Override the admin realm via auth_realm.

       verify_tls=false (the default) skips certificate verification — the
       equivalent of curl -k — so a self-signed lab cert doesn't block the fetch."""
    import ssl
    import urllib.request, urllib.parse, urllib.error
    b = body or {}
    base = (b.get("base_url") or "").rstrip("/")
    realm = (b.get("realm") or "").strip()
    token = (b.get("token") or "").strip()
    if not base or not realm:
        return {"ok": False, "message": "base_url and realm are required"}
    # SSL context: verify only when explicitly asked; default is to bypass (curl -k)
    verify_tls = bool(b.get("verify_tls", False))
    ctx = None
    if not verify_tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        if not token:
            # admin token: authenticate against the realm the admin user lives in
            # (Keycloak's built-in admin is in 'master'); default there, overridable.
            auth_realm = (b.get("auth_realm") or "master").strip()
            data = urllib.parse.urlencode({
                "grant_type": "password", "client_id": b.get("client_id") or "admin-cli",
                "username": b.get("username") or "", "password": b.get("password") or ""}).encode()
            tok_url = f"{base}/realms/{auth_realm}/protocol/openid-connect/token"
            with urllib.request.urlopen(urllib.request.Request(tok_url, data=data),
                                        timeout=15, context=ctx) as r:
                token = json.loads(r.read()).get("access_token", "")
            if not token:
                return {"ok": False, "message": "Could not obtain admin token "
                        f"from realm '{auth_realm}'. Check the admin username/"
                        "password and that the admin realm is correct."}
        users_url = f"{base}/admin/realms/{realm}/users?max=2000"
        req = urllib.request.Request(users_url, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
            users = json.loads(r.read())
        roster = [{"name": u.get("username", ""),
                   "display_name": (f"{u.get('firstName','')} {u.get('lastName','')}".strip() or u.get("username", "")),
                   "email": u.get("email", ""), "id": u.get("id", ""),
                   "roles": [], "stakeholder_role": "Steward", "community": "", "owns": "", "expertise": ""}
                  for u in users if u.get("id")]
        # realm role-mappings per user, so stewardship can be assigned by role
        # (Business_Steward -> business steward, Data_Steward -> owner,
        #  Data_Storage_Administrator -> custodian). Best-effort + capped.
        role_cap = int(b.get("role_cap", 300))
        for row in roster[:role_cap]:
            try:
                rm_url = f"{base}/admin/realms/{realm}/users/{row['id']}/role-mappings/realm"
                rr = urllib.request.Request(rm_url, headers={"Authorization": "Bearer " + token})
                with urllib.request.urlopen(rr, timeout=15, context=ctx) as r:
                    rmap = json.loads(r.read())
                row["roles"] = [x.get("name", "") for x in rmap if x.get("name")]
            except Exception:
                pass
        # Preserve manually-curated fields across a re-fetch. Keycloak doesn't store
        # expertise (or owns/community), so without this a fetch would wipe the seeded
        # expertise that auto-assign relies on, and assignment would fall back to role
        # defaults. Match an existing roster entry by id, then email, then username.
        existing = _load_people()
        by_id = {p.get("id"): p for p in existing if p.get("id")}
        by_email = {(p.get("email") or "").lower(): p for p in existing if p.get("email")}
        by_name = {(p.get("name") or "").lower(): p for p in existing if p.get("name")}
        carried = 0
        for row in roster:
            prev = (by_id.get(row["id"])
                    or by_email.get((row.get("email") or "").lower())
                    or by_name.get((row.get("name") or "").lower()))
            if prev:
                for k in ("expertise", "owns", "community", "stakeholder_role"):
                    if prev.get(k) and not row.get(k):
                        row[k] = prev[k]
                        if k == "expertise":
                            carried += 1
        if b.get("save"):
            _save_people(roster)
        return {"ok": True, "people": roster, "count": len(roster),
                "saved": bool(b.get("save")), "expertise_preserved": carried}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        hint = ""
        if e.code in (401, 403):
            hint = (" — the admin token lacks rights to list users in this realm, "
                    "or the credentials/admin realm are wrong.")
        return {"ok": False, "message": f"Keycloak fetch failed: HTTP {e.code}{hint} {detail}"}
    except Exception as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "self-signed" in msg or "self signed" in msg:
            msg += " — untick 'Verify TLS' to bypass the self-signed certificate."
        return {"ok": False, "message": f"Keycloak fetch failed: {msg}"}

@app.get("/api/connections")
def get_connections():
    """Return the saved data-source connections."""
    return {"connections": _load_connections()}

@app.post("/api/connections")
def save_connection(body: dict = Body(default={})):
    """Add or update a saved data-source connection."""
    c = body or {}
    conns = _load_connections()
    if not c.get("id"):
        c["id"] = uuid.uuid4().hex[:12]
        conns.append(c)
    else:
        conns = [c if x.get("id") == c["id"] else x for x in conns]
        if not any(x.get("id") == c["id"] for x in conns):
            conns.append(c)
    _save_connections(conns)
    return {"connection": c, "connections": conns}

@app.delete("/api/connections/{cid}")
def delete_connection(cid: str):
    """Delete a saved connection by id."""
    conns = [x for x in _load_connections() if x.get("id") != cid]
    _save_connections(conns)
    return {"connections": conns}

def _parse_remap(remap):
    """Normalise a remap spec into a list of (from, to) rules. Accepts a dict, a list of
       {from,to}/[from,to], or a string of 'from=to' rules separated by comma/newline."""
    rules = []
    if isinstance(remap, dict):
        rules = [(k, v) for k, v in remap.items()]
    elif isinstance(remap, list):
        for r in remap:
            if isinstance(r, dict) and r.get("from"):
                rules.append((r["from"], r.get("to", "")))
            elif isinstance(r, (list, tuple)) and len(r) == 2:
                rules.append((r[0], r[1]))
    elif isinstance(remap, str):
        import re as _re
        for part in _re.split(r"[,\n]", remap):
            if "=" in part:
                a, b = part.split("=", 1)
                rules.append((a, b))
    return [(str(a).strip(), str(b).strip()) for a, b in rules if str(a).strip()]


def _apply_remap(conn, rules):
    """Rewrite a connection's host/port (exact match) and endpoint (substring) so the
       app's copy is reachable from where the app runs — e.g. cscu-postgres->localhost,
       5432->5433 — while the PDC-side CSV keeps the Docker-internal names."""
    if not rules:
        return conn
    cfg = conn.get("config") or {}
    for frm, to in rules:
        if not frm:
            continue
        for k in ("host", "port"):
            if str(cfg.get(k, "")) == frm:
                cfg[k] = to
        if cfg.get("endpoint"):
            cfg["endpoint"] = str(cfg["endpoint"]).replace(frm, to)
    return conn

def _csv_row_to_conn(row):
    """Map one bulk-loader CSV row to an app connection {name,type,config} for the
       Schema / Files / live-scan pages. Returns (conn, error)."""
    kind = str(row.get("kind") or row.get("databaseType") or "").strip().lower()
    name = (row.get("resourceName") or row.get("name") or "").strip()
    if not name:
        return None, "row missing resourceName"
    if kind in ("postgres", "postgresql", "pg", "mysql", "mariadb", "oracle"):
        engine = ("mysql" if kind in ("mysql", "mariadb")
                  else "oracle" if kind == "oracle" else "postgresql")
        raw = str(row.get("schemaNames") or "")
        schema = (raw.replace(";", ",").split(",")[0].strip()
                  or ("public" if engine == "postgresql" else ""))
        cfg = {"engine": engine, "host": row.get("host"),
               "port": str(row.get("port") or ("3306" if engine == "mysql"
                                               else "1521" if engine == "oracle" else "5432")),
               "database": row.get("databaseName") or row.get("database"),
               "schema": schema, "user": row.get("userName") or row.get("username"),
               "password": row.get("password"), "ssl": False, "profile": True}
        return {"name": name, "type": "db", "config": cfg}, None
    if kind in ("minio", "s3", "aws_s3"):
        endpoint = row.get("endpoint") or ""
        cfg = {"endpoint": endpoint, "bucket": row.get("container") or row.get("bucket"),
               "access_key": row.get("accessKeyID") or row.get("accessKey"),
               "secret_key": row.get("secretAccessKey") or row.get("secretKey"),
               "prefix": str(row.get("path") or "").lstrip("/"),
               "secure": str(endpoint).lower().startswith("https"),
               "level": "file", "profile_dq": False, "content_terms": True}
        return {"name": name, "type": "minio", "config": cfg}, None
    return None, "unsupported kind %r for a live connection (postgres/mysql/oracle/minio/s3 only)" % (kind or "?")

@app.post("/api/connections/import-csv")
def import_connections_csv(body: dict = Body(default={})):
    """Import the bulk-loader CSV into the app's OWN connections (used by Schema, Files,
       Test and live scan) — the same CSV you register in PDC, so you never re-enter the
       100+ by hand. Upserts by name.

       Body: {csv|rows, preview?, only?}. preview=true returns the candidate list
       (parsed, not saved) so the UI can let the user tick which to import. only=[names]
       imports just those; omit to import all."""
    from sources import pdc_api
    body = body or {}
    rows = body.get("rows")
    if not rows and body.get("csv"):
        try:
            rows = pdc_api.parse_csv_rows(body["csv"])
        except Exception as e:
            return _err("could not parse CSV: %s" % e, 400)
    rows = rows or []
    if not rows:
        return _err("no rows — provide 'csv' or 'rows'", 400)

    preview = bool(body.get("preview"))
    only = body.get("only")
    only_set = {str(n).strip().lower() for n in only} if only else None
    remap_rules = _parse_remap(body.get("remap"))

    def _summary(conn):
        f = conn["config"]
        if conn["type"] == "db":
            return "%s · %s:%s/%s (%s)" % (f.get("engine"), f.get("host"), f.get("port"),
                                           f.get("database"), f.get("schema"))
        return "%s / %s" % (f.get("endpoint"), f.get("bucket"))

    candidates, to_import = [], []
    for row in rows:
        conn, err = _csv_row_to_conn(row)
        nm = (row.get("resourceName") or row.get("name") or "").strip()
        if err:
            candidates.append({"name": nm or "(unnamed)", "ok": False, "reason": err})
            continue
        _apply_remap(conn, remap_rules)
        candidates.append({"name": conn["name"], "type": conn["type"], "ok": True,
                           "summary": _summary(conn)})
        if only_set is None or conn["name"].strip().lower() in only_set:
            to_import.append(conn)

    if preview:
        return {"candidates": candidates,
                "count": sum(1 for c in candidates if c["ok"])}

    conns = _load_connections()
    by_name = {str(c.get("name", "")).strip().lower(): c for c in conns}
    added = updated = 0
    for conn in to_import:
        key = conn["name"].strip().lower()
        if key in by_name:
            ex = by_name[key]
            ex["type"] = conn["type"]; ex["config"] = conn["config"]
            updated += 1
        else:
            conn["id"] = uuid.uuid4().hex[:12]
            conns.append(conn); by_name[key] = conn
            added += 1
    _save_connections(conns)
    return {"connections": conns, "added": added, "updated": updated,
            "skipped": [c["reason"] for c in candidates if not c["ok"]]}

@app.get("/api/settings")
def get_settings():
    """Return the current settings."""
    return _load_settings()

@app.get("/api/readiness")
def readiness():
    """What the app is missing that it will not otherwise mention.

    Both of these are OPTIONAL and both degrade SILENTLY, which is the problem:

      domain pack  absent -> the engine returns {} and falls back to generic
                   vocabulary. `mbr_no` stays "Mbr No" instead of becoming
                   "Member Number", categories come from generic keywords. The
                   glossary is valid and bland, and reads as the app
                   underperforming rather than as a missing input.

      roster       absent -> stewardship exports empty. Nothing gates it, PDC
                   accepts it, and the governance the glossary exists to
                   establish is quietly not there.

    Reported so the UI can say so at the point it matters. Never an error: a
    first scan with neither is a legitimate way to start.
    """
    from engine import suggester
    pack = {}
    try:
        pack = suggester._load_domain_pack() or {}
    except Exception:
        pack = {}
    # A pack that resolved but carries no vocabulary is the same experience as no
    # pack at all, so it is reported the same way.
    vocab_keys = ("abbreviations", "terms", "cat_keywords", "table_terms",
                  "table_category", "category_definitions", "category_tags",
                  "tag_rules", "extra_tags")
    filled = {k: len(pack.get(k) or []) for k in vocab_keys if pack.get(k)}
    return {
        "domain_pack": {
            "present": bool(filled),
            "domain": pack.get("domain") or "",
            "path": paths.domain_pack_path(),
            "entries": sum(filled.values()),
            "sections": filled,
        },
        "roster": {"people": len(_load_people())},
        "state_dir": paths.state_dir(),
    }

def _load_gloss(strict=False):
    """Load the saved-glossary store (maps id -> {name, rows}).

    strict=True raises when the file EXISTS but cannot be read/parsed, instead
    of returning an empty store — the write paths use it so a transient read
    failure (file locked by another process, encoding hiccup) can never
    masquerade as "no glossaries" and let the subsequent full rewrite silently
    discard every saved glossary."""
    if strict and os.path.isfile(GLOSS_FILE):
        with open(GLOSS_FILE, encoding="utf-8") as f:
            return (json.load(f) or {}).get("glossaries", {})
    return _read_json(GLOSS_FILE, {"glossaries": {}}).get("glossaries", {})

def _save_gloss(g):
    """Persist the saved-glossary store. Before any rewrite that SHRINKS the
    store, snapshot the current file to glossaries.json.bak — a one-deep safety
    net so a bad rewrite is always recoverable."""
    try:
        prev = _read_json(GLOSS_FILE, {"glossaries": {}}).get("glossaries", {})
        if len(g) < len(prev):
            import shutil
            shutil.copy2(GLOSS_FILE, GLOSS_FILE + ".bak")
    except Exception:
        pass
    _write_json(GLOSS_FILE, {"glossaries": g})

@app.get("/api/glossaries")
def list_glossaries():
    """List saved glossaries as {id, name, term count}."""
    g = _load_gloss()
    items = [{"id": k, "name": v.get("name"), "glossary_name": v.get("glossary_name"),
              "savedAt": v.get("savedAt"), "terms": len(v.get("rows", [])),
              "categories": len({r.get("Category") for r in v.get("rows", [])}),
              "kept": sum(1 for r in v.get("rows", []) if str(r.get("Keep", "Y")).lower() in ("y", "yes", "true", "1")),
              "archived": bool(v.get("archived")), "archivedAt": v.get("archivedAt"),
              "has_discovery": bool(v.get("discovery"))}
             for k, v in g.items()]
    items.sort(key=lambda x: x.get("savedAt") or "", reverse=True)
    return {"glossaries": items}


@app.post("/api/glossaries/{gid}/snapshot")
def snapshot_glossary(gid: str):
    """Copy-on-write versioning: archive the CURRENT stored state of a live
    glossary as a timestamped version (same name, original savedAt kept).
    Called by the UI at the FIRST dirtying edit after a load — the autosave
    overwrites continuously, so the end of a session is too late to save
    "the glossary as I loaded it". One version per load-session; the last
    10 versions per name are kept."""
    import datetime
    try:
        g = _load_gloss(strict=True)
    except Exception as e:
        return _err("glossary store unreadable (%s)" % e, 503)
    src = g.get(gid)
    if not isinstance(src, dict):
        return _err("unknown glossary", 404)
    if src.get("archived"):
        return _err("already an archived version — versions are immutable", 400)
    snap = json.loads(json.dumps(src))
    sid = uuid.uuid4().hex[:12]
    snap["id"] = sid
    snap["archived"] = True
    snap["archivedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
    g[sid] = snap
    nm = str(src.get("name") or "").strip().lower()
    same = sorted(((k, v) for k, v in g.items()
                   if isinstance(v, dict) and v.get("archived")
                   and str(v.get("name") or "").strip().lower() == nm),
                  key=lambda kv: kv[1].get("archivedAt") or "", reverse=True)
    for k, _v in same[10:]:
        g.pop(k, None)
    _save_gloss(g)
    return {"snapshot": sid, "savedAt": snap.get("savedAt"),
            "archivedAt": snap["archivedAt"]}

@app.post("/api/glossaries")
def save_glossary(body: dict = Body(default={})):
    """Save (or overwrite) a named glossary of review rows."""
    import datetime
    # A save that was already in flight when a factory reset ran lands AFTER
    # the wipe and writes the just-deleted estate straight back (field-caught
    # 2026-08-23: glossaries.json resurrected between reset and relaunch).
    # The client-side wiped guard cannot cancel a POST the browser already
    # sent, so the server refuses saves in the seconds after a reset.
    if time.time() - _FACTORY_RESET_AT < 10:
        return _err("a factory reset just ran — this save was refused so it "
                    "cannot resurrect the deleted estate; reload and start "
                    "fresh", 409)
    body = body or {}
    try:
        g = _load_gloss(strict=True)
    except Exception as e:
        return _err("glossary store unreadable (%s) — refusing to save over it; "
                    "retry in a moment or check %s" % (e, GLOSS_FILE), 503)
    gid = body.get("id") or uuid.uuid4().hex[:12]
    body["id"] = gid
    # A NEW glossary whose name collides with an existing one gets a visible
    # suffix. The fresh-scan fork saved a raw twin under the SAME name — the
    # Home list showed two identical "Arizona Water"s and auto-resume (last
    # saved wins) picked the raw one (field-caught: "so now its a mess!").
    # The suffix makes the fork legible at a glance; renaming stays the
    # steward's call. Re-saves of an existing id keep their name untouched.
    if gid not in g:
        want = str(body.get("name") or "").strip()
        # archived VERSIONS share the live glossary's name by design — only
        # live entries participate in the collision suffix
        taken = {str(v.get("name") or "").strip().lower()
                 for k, v in g.items()
                 if isinstance(v, dict) and k != gid and not v.get("archived")}
        if want and want.lower() in taken:
            n = 2
            while f"{want} ({n})".lower() in taken:
                n += 1
            body["name"] = f"{want} ({n})"
    body["savedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
    g[gid] = body
    _save_gloss(g)
    # one-way Review -> Dictionary flow: accepted enrichments/edits in the
    # saved rows refresh the dictionary's PENDING entries (never governed),
    # so the steward reviews the enriched version, not the raw scan capture
    try:
        refreshed = tagdict.refresh_pending(body.get("rows") or [])
    except Exception:
        refreshed = 0
    if refreshed:
        audit.record("dictionary.refresh_pending", actor=body.get("actor"),
                     glossary=body.get("name"), refreshed=refreshed)
    return {"id": gid, "savedAt": body["savedAt"], "name": body.get("name"),
            "pending_refreshed": refreshed}

@app.get("/api/glossaries/{gid}")
def get_glossary(gid: str):
    """Return one saved glossary's rows by id."""
    g = _load_gloss()
    if gid not in g:
        return _err("not found", 404)
    return g[gid]

@app.delete("/api/glossaries/{gid}")
def delete_glossary(gid: str):
    """Delete a saved glossary by id."""
    try:
        g = _load_gloss(strict=True)
    except Exception as e:
        return _err("glossary store unreadable (%s) — refusing to delete; "
                    "retry in a moment" % e, 503)
    g.pop(gid, None)
    _save_gloss(g)
    return {"ok": True}

@app.post("/api/settings")
def save_settings(body: dict = Body(default={})):
    """Persist the settings supplied by the client, and apply any LLM config change
       (provider / URL / model / timeout) to the running client immediately.

       Credential fields are stripped before writing: API keys are session-only
       (POST /api/llm-key) or come from the environment, so they can never reach
       settings.json and therefore never ride along in a State snapshot."""
    incoming = {k: v for k, v in (body or {}).items()
                if k.lower() not in _CREDENTIAL_FIELDS}
    s = _load_settings(); s.update(incoming)
    _write_json(SETTINGS_FILE, s)
    _apply_llm_settings(s)
    return s

@app.get("/api/llm-providers")
def llm_providers_route():
    """Provider catalog for the Settings page: label, suggested models, which
       env var supplies the key, whether the SDK is installed, and whether a key
       currently resolves. Never returns a key value."""
    return {"providers": llm_providers.catalog(),
            "selected": llm_providers.PROVIDER,
            "azure_endpoint": llm_providers.AZURE_ENDPOINT,
            "azure_api_version": llm_providers.AZURE_API_VERSION}

@app.post("/api/llm-key")
def llm_key_route(body: dict = Body(default={})):
    """Set (or clear, with a blank value) a provider API key for THIS PROCESS
       ONLY. Nothing is written to disk — restart and the key is gone unless the
       provider's environment variable supplies it. Returns only where the key
       resolves from, never the key."""
    body = body or {}
    provider = str(body.get("provider") or "").strip().lower()
    if provider not in llm_providers.PROVIDERS:
        return _err("unknown provider %r" % body.get("provider"), 400)
    llm_providers.set_key(provider, body.get("api_key"))
    return {"ok": True, "provider": provider,
            "has_key": bool(llm_providers.resolve_key(provider)),
            "key_source": llm_providers.key_source(provider)}

@app.post("/api/llm-test")
def llm_test_route(body: dict = Body(default={})):
    """Round-trip the selected provider so the Settings dot reflects a real call
       (SDK importable, key valid, model id accepted). Body: {provider?, model?}."""
    body = body or {}
    provider = (body.get("provider") or llm_providers.PROVIDER).strip().lower()
    model = (body.get("model") or "").strip() or None
    if provider == "ollama":
        s = llm.status(model)
        return {"ok": bool(s.get("online")), "provider": "ollama",
                "model": s.get("model"),
                "message": ("Connected to %s · %s" % (s.get("url"), s.get("model")))
                           if s.get("online") else
                           ("Offline at %s%s" % (s.get("url"),
                            " — " + s["error"] if s.get("error") else ""))}
    return llm_providers.test_connection(model=model, provider=provider)

@app.post("/api/test-connection")
def test_connection(body: dict = Body(default={})):
    """Test a database connection without running a full scan."""
    cfg = (body or {}).get("conn", {})
    return dbconn.test_connection(cfg)

@app.post("/api/test-minio")
def test_minio(body: dict = Body(default={})):
    """Test a MinIO/S3 connection (bucket reachability + whether object tagging works)."""
    cfg = (body or {}).get("minio", {})
    return suggester.test_minio(cfg)

@app.post("/api/lab-minio-status")
def lab_minio_status(body: dict = Body(default={})):
    """Reachability + auth check for the 'Send to lab' MinIO status dot. Takes an
       explicit `config`/`minio` object, or a saved `connection` id/name to look
       up. Bucket-agnostic (the export bucket is created on first use)."""
    body = body or {}
    cfg = body.get("config") or body.get("minio")
    if not cfg and body.get("connection"):
        want = str(body.get("connection")).strip().lower()
        stores = [c for c in _load_connections()
                  if str(c.get("type", "")).lower() in ("minio", "s3")]
        conn = next((c for c in stores
                     if str(c.get("id", "")).lower() == want
                     or str(c.get("name", "")).strip().lower() == want), None)
        cfg = (conn or {}).get("config")
    if not cfg:
        return {"ok": False, "message": "no lab MinIO connection configured"}
    return suggester.reach_minio(cfg)

@app.post("/api/list-objects")
def list_objects_route(body: dict = Body(default={})):
    """Browse a MinIO/S3 bucket one folder level at a time (folders + files)."""
    body = body or {}
    cfg = body.get("minio") or {}
    if not (cfg.get("bucket") or "").strip():
        return _err("No bucket specified on this connection.", 400)
    try:
        return suggester.list_objects(cfg, body.get("prefix", ""))
    except Exception as e:
        return _err(f"Could not list objects: {e}", 400)

@app.post("/api/lab-export")
def lab_export(body: dict = Body(default={})):
    """Upload a just-generated artifact (glossary import JSONL / drafted-policies
       zip) to the lab MinIO over one of the app's saved MinIO/S3 connections, so
       it's grabbable ON the VM (console :9001 or `mc cp`) without a file share.

       Body: {filename, text? | b64?, content_type?, connection?, bucket?}.
       `connection` is a saved connection id or name (required only when several
       MinIO/S3 connections exist); `bucket` defaults to pdc-exports and is
       created when missing. Returns {ok, bucket, key, size, connection,
       endpoint, hint}."""
    import base64
    import datetime
    import re
    body = body or {}
    filename = (body.get("filename") or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    filename = "-".join(filename.split())      # spaces make `mc cp` keys awkward
    if not filename:
        return _err("filename is required", 400)
    text, b64 = body.get("text"), body.get("b64")
    if text is None and not b64:
        return _err("nothing to export — provide 'text' or 'b64'", 400)
    try:
        data = text.encode("utf-8") if text is not None else base64.b64decode(b64)
    except Exception as e:
        return _err(f"could not decode payload: {e}", 400)
    stores = [c for c in _load_connections()
              if str(c.get("type", "")).lower() in ("minio", "s3")]
    if not stores:
        return _err("no saved MinIO/S3 connection — add one on the Connect page "
                    "(or import the bulk-loader CSV) first", 400)
    want = str(body.get("connection") or "").strip().lower()
    if want:
        conn = next((c for c in stores
                     if str(c.get("id", "")).lower() == want
                     or str(c.get("name", "")).strip().lower() == want), None)
        if conn is None:
            return _err("no MinIO/S3 connection named %r — saved: %s"
                        % (body.get("connection"),
                           ", ".join(c.get("name", "?") for c in stores)), 404)
    elif len(stores) == 1:
        conn = stores[0]
    else:
        return _err("several MinIO/S3 connections are saved — pass 'connection' "
                    "(id or name): " + ", ".join(c.get("name", "?") for c in stores), 400)
    cfg = conn.get("config") or {}
    bucket = (body.get("bucket") or "pdc-exports").strip()
    # a caller whose filename is ALREADY timestamped (the generation archive)
    # passes key_prefix for a browsable per-glossary path instead of a second
    # timestamp: glossary/<slug>/<ts>-glossary-import.jsonl
    key_prefix = re.sub(r"[^A-Za-z0-9/_-]+", "-",
                        str(body.get("key_prefix") or "")).strip("/")
    key = (key_prefix + "/" + filename) if key_prefix \
        else datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + filename
    ctype = (body.get("content_type") or "").strip() or suggester._guess_ctype(filename)
    try:
        s3 = suggester._s3_client(cfg)
    except Exception as e:
        return _err(str(e), 400)
    note = ""
    try:
        try:
            s3.head_bucket(Bucket=bucket)
        except Exception:
            try:
                s3.create_bucket(Bucket=bucket)   # export bucket, created on first use
            except Exception:
                # lab accounts often can't create buckets (e.g. the cast MinIO
                # user) — fall back to the connection's own bucket under a
                # pdc-exports/ prefix, so the export still lands somewhere the
                # account can write and the console can browse
                fallback = (cfg.get("bucket") or "").strip()
                if not fallback:
                    raise
                bucket, key = fallback, "pdc-exports/" + key
                note = (" (no rights to create a bucket — dropped under "
                        "pdc-exports/ in the connection's own bucket instead)")
        s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=ctype)
    except Exception as e:
        msg = f"upload to {cfg.get('endpoint') or 'the object store'} failed: {e}"
        if "AccessDenied" in str(e):
            msg += (" — this connection's account looks read-only (the lab's cast "
                    "MinIO users are); save a connection with a write-capable "
                    "account (e.g. the lab admin) and pick that one instead")
        return _err(msg, 502)
    return {"ok": True, "bucket": bucket, "key": key, "size": len(data),
            "connection": conn.get("name"), "endpoint": cfg.get("endpoint"),
            "note": note.strip(" ()") if note else "",
            "hint": ("on the VM: MinIO console :9001 → bucket %s, or "
                     "`mc cp local/%s/%s ~/Downloads`%s" % (bucket, bucket, key, note))}

@app.post("/api/object-bytes")
def object_bytes_route(body: dict = Body(default={})):
    """Stream a whole object (PDF/image) so the browser can render it inline. Creds
       stay in the POST body; the client turns the response into a blob URL."""
    body = body or {}
    cfg = body.get("minio") or {}
    key = (body.get("key") or "").strip()
    if not key:
        return _err("No object key supplied.", 400)
    try:
        data, ctype = suggester.get_object_bytes_full(cfg, key)
    except Exception as e:
        return _err(str(e), 400)
    leaf = key.rsplit("/", 1)[-1].replace('"', "")
    return Response(data, media_type=ctype or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{leaf}"',
                             "Content-Length": str(len(data))})

@app.post("/api/object")
def object_route(body: dict = Body(default={})):
    """Metadata, tags and a short text preview for one object."""
    body = body or {}
    cfg = body.get("minio") or {}
    key = (body.get("key") or "").strip()
    if not key:
        return _err("No object key supplied.", 400)
    try:
        return suggester.object_detail(cfg, key)
    except Exception as e:
        return _err(f"Could not read object: {e}", 400)

@app.post("/api/load-glossary")
def load_glossary(body: dict = Body(default={})):
    """Parse an uploaded glossary (JSONL/CSV) into review rows."""
    text = (body or {}).get("glossary", "")
    try:
        rows, report = suggester.glossary_to_rows(text)
    except Exception as e:
        return _err(f"load failed: {e}", 400)
    return {"rows": rows, "stats": _stats(rows), "report": report}

@app.post("/api/enhance-glossary")
def enhance_glossary(body: dict = Body(default={})):
    """Enrich existing review rows from an imported glossary, optionally appending missing terms."""
    body = body or {}
    rows = body.get("rows", [])
    text = body.get("glossary", "")
    append = body.get("append_missing", True)
    try:
        rows2, report = suggester.enhance_from_glossary(rows, text, append)
    except Exception as e:
        return _err(f"enhance failed: {e}", 400)
    return {"rows": rows2, "stats": _stats(rows2), "report": report}

def _truthy(v):
    """A checkbox that arrived as JSON true, or as "true"/"yes"/"1" from a form or
       a hand-edited connections.json. Anything else - including absent - is False,
       because this gates the one call that writes to a database."""
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("y", "yes", "true", "t", "1", "on")


def _ai_categories_run(body):
    """Propose business categories from the schema's own structure - tables,
       columns and FK links the scan proved. Proposals only: the UI applies
       after the steward confirms, and Export pack freezes the outcome.
       Shared by the sync endpoint and its job twin so the payload cannot
       drift between them."""
    from ai import llm
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    # used_llm=False has two very different causes - an estate with too few
    # tables to group, and a model that is not reachable - and the UI can
    # only report honestly if the payload says which (a transient failure
    # mid-walk read as "no model available" and sent the steward to Settings)
    tables = llm.schema_evidence(rows)
    if len(tables) < 2:
        return {"categories": [], "assignments": [None] * len(rows),
                "used_llm": False, "timed_out": 0,
                "reason": "few_tables", "table_count": len(tables)}
    if not llm.status(body.get("model"))["online"]:
        return {"categories": [], "assignments": [None] * len(rows),
                "used_llm": False, "timed_out": 0, "reason": "offline"}
    # a timeout on this ONE long call must be distinguishable from "the model
    # had no opinion" — the UI's "proposed nothing usable" on a clock failure
    # sent the steward model-shopping when the fix was a longer budget
    before = llm.call_failures().get("timeout", 0)
    proposal, assignments, used = llm.propose_categories(
        rows, model=body.get("model"), compute=body.get("compute"),
        # the steward's own target for how many subjects this business has —
        # the model biases low by design, and the right number is a judgement
        # about the estate, not something it can infer alone
        target=body.get("target"))
    timed_out = llm.call_failures().get("timeout", 0) - before
    return {"categories": proposal, "assignments": assignments, "used_llm": used,
            "timed_out": max(timed_out, 0)}


@app.post("/api/ai-categories")
def ai_categories(body: dict = Body(default={})):
    return _ai_categories_run(body or {})

@app.post("/api/seed")
def seed(body: dict = Body(default={})):
    """Seed a PostgreSQL schema with demo data — the ONLY endpoint here that writes
       to a connected database.

       Two gates, because the app cannot tell a demo database from a production
       one and "only empty tables" is thinner protection than it sounds: a
       production estate has empty tables (a new feature's, an audit table not yet
       written to, a staging table between loads), and those would be filled.

         dry_run=True          -> returns the exact tables that WOULD be written,
                                  touching nothing. The UI shows this list and
                                  asks the operator to type the database name.
         allow_sample_data     -> must be set on the CONNECTION, not passed at
                                  call time by whoever clicks. Enforced here so a
                                  UI change can never be the only thing standing
                                  between a live database and 200 fake rows.
    """
    body = body or {}
    cfg = body.get("conn", {})
    rows = int(body.get("rows", 200))
    only_empty = body.get("only_empty", True)
    dry_run = bool(body.get("dry_run", False))

    if dry_run:
        try:
            return seed_sample.plan(cfg, only_empty=only_empty, schema=cfg.get("schema"))
        except Exception as e:
            return _err(f"could not read the schema: {e}", 400)

    if not _truthy(cfg.get("allow_sample_data")):
        return _err(
            "This connection is not marked as safe for sample data, so nothing was "
            "written. Sample data exists for TRAINING AND DEMO DATABASES ONLY: edit "
            "the connection and tick 'allow sample data' if this is one. Never tick "
            "it for a production database or any system of record — empty tables "
            "there would be filled with fabricated rows.", 400)
    try:
        rep = seed_sample.seed(cfg, rows=rows, only_empty=only_empty, schema=cfg.get("schema"))
        return rep
    except Exception as e:
        return _err(f"seed failed: {e}", 400)

@app.post("/api/discover")
def discover(body: dict = Body(default={})):
    """Scan a database source and return suggested glossary rows."""
    cfg = (body or {}).get("conn", {})
    try:
        return suggester.discover(cfg, cfg.get("schema"))
    except Exception as e:
        return _err(f"discovery failed: {e}", 400)

@app.post("/api/discover-docs")
def discover_docs(body: dict = Body(default={})):
    """Scan a document/object store and return suggested rows."""
    cfg = (body or {}).get("conn", {})
    try:
        return suggester.discover_documents(cfg)
    except Exception as e:
        return _err(f"document discovery failed: {e}", 400)

@app.post("/api/schema")
def schema_route(body: dict = Body(default={})):
    """Scan a database or DDL connection and return its ER graph (tables, columns
       with PK/FK, and FK relationships) for the schema diagram. Object-store
       connections have no relational schema."""
    body = body or {}
    src = body.get("source", "ddl")
    try:
        if src in ("minio", "s3"):
            return _err("Object-store connections have no relational "
                        "schema to diagram — pick a database or DDL source.", 400)
        if src in ("postgres", "db"):
            cfg = body.get("conn") or {}
            tables = suggester.harvest_live(cfg, cfg.get("schema"))
            schema_name = cfg.get("schema") or "public"
        elif body.get("ddl_text"):
            tables = suggester.harvest_ddl_text(body["ddl_text"])
            schema_name = "ddl"
        else:
            tables = suggester.harvest_ddl(body.get("ddl_path", DEFAULT_DDL))
            schema_name = "ddl"
    except Exception as e:
        return _err(f"schema scan failed: {e}", 400)
    g = suggester.schema_graph(tables)
    g["schema_name"] = schema_name
    return g

@app.post("/api/apply-keys")
def apply_keys(body: dict = Body(default={})):
    """Write PRIMARY KEY / FOREIGN KEY constraints to a live PostgreSQL schema, using
       a CREATE TABLE script as the source of truth for which keys to set. dry_run
       (default true) returns the planned ALTER statements without executing."""
    body = body or {}
    cfg = body.get("conn") or {}
    dry = bool(body.get("dry_run", True))
    try:
        if (body.get("ddl_text") or "").strip():
            tables = suggester.harvest_ddl_text(body["ddl_text"])
        else:
            tables = suggester.harvest_ddl(body.get("ddl_path", DEFAULT_DDL))
    except Exception as e:
        return _err(f"Could not read the CREATE TABLE script for key "
                    f"definitions: {e}", 400)
    keymap = suggester.keymap_from_tables(tables)
    if not keymap:
        return _err("No primary or foreign keys were found in the script "
                    "to apply. Paste your CREATE TABLE statements (with PRIMARY KEY / "
                    "REFERENCES) first.", 400)
    try:
        return suggester.apply_keys_live(cfg, cfg.get("schema"), keymap, dry_run=dry)
    except Exception as e:
        return _err(str(e), 400)

@app.post("/api/scan")
def scan(body: dict = Body(default={})):
    """Dispatch a scan to the right source handler (database, MinIO/S3, or DDL file)."""
    body = body or {}
    src = body.get("source", "ddl")
    try:
        if src in ("minio", "s3"):
            cfg = body.get("minio") or {}
            bucket = cfg.get("bucket", "documents")
            if (cfg.get("level") or body.get("level")) == "file":
                # profile_dq: when set on the connection, read each object's content
                # and compute a Data-Quality score (csv/json/text/xml), instead of
                # leaving the Data Quality input for PDC to fill.
                profile_dq = bool(cfg.get("profile_dq") or cfg.get("dq"))
                # content_terms: parse each content-profilable object's DECLARED
                # columns into candidate terms — the app-side parity of PDC's own
                # scanner cataloging a CSV's columns (field-caught: the direct
                # scan produced 5 folder terms while PDC's harvest of the same
                # bucket carried every column). Defaults ON, including for
                # connections saved before the flag existed.
                content_terms = bool(cfg.get("content_terms", True))
                files = suggester.harvest_files(cfg, profile_dq=profile_dq,
                                                content_columns=content_terms)
                rows = suggester.suggest_document_files(files, bucket)
                col_rows = suggester.suggest_document_columns(files, bucket) if content_terms else []
                rows = rows + col_rows
                try: tagdict.accrete(rows, source="minio")
                except Exception: pass
                folders = sorted({f["folder"] for f in files})
                scored = sum(1 for f in files if f.get("qdims"))
                parsed = sum(1 for f in files if f.get("columns"))
                sig = (f"{len(files)} leaf file(s) across {len(folders)} folder(s); "
                       "metadata applies per file")
                if content_terms:
                    sig += (f" · {len(col_rows)} column term(s) parsed from "
                            f"{parsed} file(s)' contents")
                if profile_dq:
                    sig += f" · Data Quality computed from content for {scored} file(s)"
                scn = {"objects": len(files), "folders": len(folders),
                       "dq_scored": scored, "content_columns": len(col_rows)}
                return {"rows": rows, "stats": _stats(rows), "scanned": scn,
                        "check": suggester.scan_check(rows, scn),
                        "ownership": {"signals": [sig]}}
            folders, ownership, scanned = suggester.harvest_minio(cfg)
            rows = suggester.suggest_documents(folders, bucket)
            try: tagdict.accrete(rows, source="minio")
            except Exception: pass
            return {"rows": rows, "stats": _stats(rows),
                    "scanned": scanned, "ownership": ownership,
                    "check": suggester.scan_check(rows, scanned)}
        if src == "postgres" or src == "db":
            cfg = body.get("conn") or {}
            tables = suggester.harvest_live(cfg, cfg.get("schema"))
            # label sources with the schema actually scanned — the UI nests it
            # in conn, so suggest() otherwise falls back to 'public' and every
            # Source_Column (and dictionary accretion) carries the wrong schema
            if not body.get("schema"):
                body["schema"] = cfg.get("schema")
            if cfg.get("profile"):
                try:
                    suggester.profile_live(cfg, tables, cfg.get("schema"))
                except Exception:
                    pass  # profiling is best-effort; fall back to name-based
        elif body.get("ddl_text"):
            tables = suggester.harvest_ddl_text(body["ddl_text"])
        else:
            tables = suggester.harvest_ddl(body.get("ddl_path", DEFAULT_DDL))
    except Exception as e:
        return _err(f"scan failed: {e}", 400)
    rows = suggester.suggest(tables, schema=body.get("schema"))
    try: tagdict.accrete(rows, source="db")
    except Exception: pass
    pk_cols = sum(1 for cols in tables.values() for c in cols if c.get("pk"))
    fk_cols = sum(1 for cols in tables.values() for c in cols if c.get("fk"))
    scanned = {"tables": len(tables), "columns": sum(len(c) for c in tables.values())}
    return {"rows": rows, "stats": _stats(rows), "scanned": scanned,
            "check": suggester.scan_check(rows, scanned, pk_cols, fk_cols)}

@app.post("/api/ai-pass")
def api_ai_pass(body: dict = Body(default={})):
    """ONE combined agent pass: definition, purpose, name, category and governed
       tags for each kept row in a single model call per row. Replaces running
       Enrich + AI suggest + AI categorize separately — three passes over the same
       rows that overlapped on name / category / tags, so the last one won. Same
       guardrails: tags governed-only, category fills a blank only, the name is a
       Suggested_Name chip, and sensitivity / PII stay deterministic from the scan."""
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    only_low = bool(body.get("only_low_confidence", False))
    model = body.get("model") or None
    compute = body.get("compute") or None
    try:
        allow = sorted(tagdict.governed_tags())
    except Exception:
        allow = []
    cats = sorted({r.get("Category") for r in rows if r.get("Category")})
    # DETERMINISTIC first, and free: re-derive the governed tags from the
    # dictionary (what the old "Suggest tags" button did on its own). Doing it
    # here means the model sees the governed tags as context and can only add to
    # them — one less button, no extra model time.
    try:
        suggester.retag_rows(rows)
    except Exception:
        pass
    # Lint BEFORE the model runs, so a generic/circular draft reaches the prompt
    # as "REWRITE REQUIRED" and comes back replaced. A flag the steward can't act
    # on is noise — this turns it into the model's instruction, for free.
    try:
        for i, issues in defqa.lint_rows(rows).items():
            rows[i]["QA_Issues"] = ";".join(issues)
    except Exception:
        pass
    rows, counts, used_llm = llm.ai_pass_rows(
        rows, allow_tags=allow, categories=cats,
        only_low_confidence=only_low, model=model, compute=compute)
    # same deterministic PII re-assertion the evidence agent applies: the scan
    # classifier is authoritative, so no agent (or import) can leave a bad value
    pii_fixed = 0
    for r in rows:
        g = suggester.guard_pii_row(r)
        if g != (r.get("PII_Category") or "").strip():
            r["PII_Category"] = g
            pii_fixed += 1
    if pii_fixed:
        counts["pii"] = pii_fixed
    # DETERMINISTIC definition QA, folded in: the linter (circular, echo, vague,
    # too-short, copy-paste duplicates) costs no model time, so the QA chip lands
    # with the pass instead of needing a second sweep over every row. The LLM
    # judge that used to follow it is gone — a whole extra pass for little gain.
    # Re-lint AFTER the rewrite: what is still flagged is what the model could
    # not improve from the available evidence — a real signal, not repeat noise.
    # Clear to "" rather than deleting the key. The UI merges each returned row
    # over its working copy with a spread, so a REMOVED key is invisible: the
    # stale flag would survive, diff as unchanged, and never reach a pill —
    # leaving "generic scan template" pinned under a definition the model had
    # just rewritten into something specific. An explicit empty value clears.
    for r in rows:
        r["QA_Issues"] = ""
        r["QA_Suggestion"] = ""
    try:
        lint = defqa.lint_rows(rows)
        for i, issues in lint.items():
            rows[i]["QA_Issues"] = ";".join(issues)
        if lint:
            counts["qa_flagged"] = len(lint)
    except Exception:
        pass
    return {"rows": rows, "updated": counts, "used_llm": used_llm,
            "stats": _stats(rows), "llm": llm.status(model)}

@app.post("/api/suggest-expertise")
def suggest_expertise_route(body: dict = Body(default={})):
    """LLM-generate `expertise` keywords for each roster member (these drive
       auto-assign). Falls back to a deterministic offline derivation when Ollama
       is unavailable. Body: {people?, categories?, overwrite?, model?, save?}.
       If `people` is omitted the saved roster is used. Optionally persists."""
    body = body or {}
    people = body.get("people") or _load_people()
    categories = body.get("categories") or []
    overwrite = bool(body.get("overwrite", False))
    model = body.get("model") or None
    people, updated, used_llm = llm.suggest_expertise(
        people, categories=categories, overwrite=overwrite, model=model)
    if body.get("save"):
        _save_people(people)
    return {"people": people, "updated": updated, "used_llm": used_llm,
            "saved": bool(body.get("save")), "llm": llm.status(model)}

@app.post("/api/resolve-fuzzy")
def api_resolve_fuzzy(body: dict = Body(default={})):
    """Match OUTSTANDING term names (renamed/disambiguated locally after the
    glossary was imported) against the terms that actually exist in PDC —
    without a round-trip through the Glossary page. Ladder: harvest candidate
    term entities via token searches, propose the best NAME-similarity match
    (>=0.78 normalized), let the local AI adjudicate the rest with the term's
    definition as context. Proposals only — the steward binds each one.
    Body: {names, definitions?, base_url, username/password|token, realm?,
    version?, verify_tls?, glossary_name?, model?, compute?}."""
    from sources import pdc_api
    body = body or {}
    names = [str(n).strip() for n in (body.get("names") or []) if str(n).strip()]
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base or not names:
        return _err("base_url and names are required", 400)
    defs = body.get("definitions") or {}
    try:
        token = (body.get("token") or "").strip()
        if not token:
            token = pdc_api.auth(base, body.get("username", ""), body.get("password", ""),
                                 version=version, verify_tls=verify,
                                 realm=(body.get("realm") or "pdc").strip(),
                                 client_id=(body.get("client_id") or "pdc-client").strip(),
                                 method=body.get("auth_method") or "auto")
    except Exception as e:
        return _err(f"auth failed: {e}", 502)
    gname = (body.get("glossary_name") or "").strip()
    default_gid = suggester.det_glossary_id(gname) if gname else None
    matches, ambiguous = {}, []
    for name in names[:40]:
        try:
            cands = pdc_api.fuzzy_term_candidates(base, token, name,
                                                  version=version, verify_tls=verify)
        except Exception:
            cands = []
        if not cands:
            matches[name] = {"match": None, "reason": "no term candidates in PDC for these tokens"}
            continue
        a = similarity._norm(name)
        scored = sorted(((similarity._lev_ratio(a, similarity._norm(c["name"])), c)
                         for c in cands), key=lambda x: -x[0])
        best_s, best = scored[0]
        if best_s >= 0.78 and best["name"].strip().lower() != name.lower():
            matches[name] = {"match": best["name"], "id": best.get("id"),
                             "glossaryId": best.get("glossaryId") or default_gid,
                             "score": round(best_s, 2), "source": "similarity",
                             "reason": f"{int(best_s * 100)}% name match"}
        else:
            ambiguous.append({"name": name, "definition": defs.get(name, ""),
                              "candidates": [c["name"] for c in cands],
                              "_cands": {c["name"]: c for c in cands}})
    used_llm = False
    if ambiguous:
        verdicts, used_llm = llm.match_terms(
            [{k: v for k, v in a.items() if k != "_cands"} for a in ambiguous],
            model=body.get("model"), compute=body.get("compute"))
        for a in ambiguous:
            v = verdicts.get(a["name"]) or {}
            m = v.get("match")
            c = a["_cands"].get(m) if m else None
            if c:
                matches[a["name"]] = {"match": c["name"], "id": c.get("id"),
                                      "glossaryId": c.get("glossaryId") or default_gid,
                                      "source": "ai", "reason": v.get("reason", "AI match")}
            else:
                matches[a["name"]] = {"match": None,
                                      "reason": v.get("reason", "no confident match")}
    return {"matches": matches, "used_llm": used_llm}

def _resolve_terms_impl(body, progress=None):
    """The resolve-and-stamp pipeline shared by the JSON, SSE and job endpoints.
    Returns the response dict; raises ValueError (bad request) or RuntimeError
    (PDC-side failure). `progress` gets {phase:'term', done, total, name} per
    lookup and {phase:'finishing'} before the stamp/probe tail."""
    from sources import pdc_api
    api_json = body.get("json") or []
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        raise ValueError("PDC base URL is required")
    names = sorted({bt.get("name") for el in api_json
                    for bt in el.get("attributes", {}).get("businessTerms", []) if bt.get("name")})
    try:
        token = (body.get("token") or "").strip()
        if not token:
            token = pdc_api.auth(base, body.get("username", ""), body.get("password", ""),
                                 version=version, verify_tls=verify,
                                 realm=(body.get("realm") or "pdc").strip(),
                                 client_id=(body.get("client_id") or "pdc-client").strip(),
                                 method=body.get("auth_method") or "auto")
        name_map = pdc_api.resolve_terms(base, token, names, body.get("glossary_name"),
                                         version=version, verify_tls=verify,
                                         progress=progress)
        if progress:
            try:
                progress({"phase": "finishing", "total": len(names)})
            except Exception:
                pass
        # PDC's public API does not expose a term's glossaryId (rootId) via search or
        # entity GET, but the glossary id is the deterministic UUID5 PDC preserved on
        # import — so fill it ourselves from the glossary name when PDC won't.
        gname = (body.get("glossary_name") or "").strip()
        default_gid = suggester.det_glossary_id(gname) if gname else None
        resolved_json, linked, unresolved, id_only = pdc_api.stamp_ids(
            api_json, name_map, default_glossary_id=default_gid)
        # probe only when terms are genuinely missing from PDC (not just missing a
        # glossaryId, which we now fill deterministically).
        probe = []
        # names PDC could not CONFIRM by exact-name lookup — their links still
        # carry the deterministic import ids, which only exist in PDC if the
        # term kept its name since import. The UI offers AI matching for these.
        unconfirmed = [n for n in names if n not in name_map]
        probe_names = unconfirmed[:3]
        if probe_names:
            try:
                probe = pdc_api.diagnose_terms(base, token, probe_names,
                                               version=version, verify_tls=verify)
            except Exception:
                probe = []
    except Exception as e:
        raise RuntimeError(str(e))
    # Backfill the resolved PDC term ids into this glossary's Registry so the
    # Policy Generator can bind dictionary methods by dictionaryTermId.
    registry_backfilled = 0
    try:
        if gname:
            _rp = _registry_path(gname)
            if os.path.exists(_rp):
                import registry as _registry
                registry_backfilled = _registry.backfill_term_ids(_rp, name_map,
                                                                 glossary_name=gname)
    except Exception:
        registry_backfilled = 0
    links_total = sum(len(el.get("attributes", {}).get("businessTerms", []))
                      for el in api_json)
    # how many DISTINCT terms resolved with a glossaryId vs id-only
    gid_terms = sum(1 for n, m in name_map.items() if m.get("glossaryId"))
    return {"json": resolved_json, "map": name_map, "linked": linked,
            "unresolved": unresolved, "id_only": id_only, "terms": len(names),
            "matched": len(name_map), "matched_with_glossary": gid_terms,
            "glossary_id": default_gid, "links": links_total, "probe": probe, "unconfirmed": unconfirmed,
            "registry_backfilled": registry_backfilled}

@app.post("/api/resolve-terms")
def resolve_terms(body: dict = Body(default={})):
    """Resolve each businessTerm's id + glossaryId in PDC and stamp them into the Data-Elements JSON."""
    body = body or {}
    try:
        return _resolve_terms_impl(body)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(str(e), 502)

@app.post("/api/resolve-terms-stream")
def resolve_terms_stream(body: dict = Body(default={})):
    """Same as /api/resolve-terms, but streams Server-Sent Events so the browser
       can show a live per-term progress bar (one PDC search per term is the slow
       part). Same worker-thread + queue shape as /api/apply-to-pdc-stream:
       `event: progress` per term, then `event: done` (the full resolve report)
       or `event: error`."""
    body = body or {}
    q = _queue_mod.Queue()

    def _run():
        try:
            out = _resolve_terms_impl(body, progress=lambda ev: q.put(("progress", ev)))
            q.put(("done", out))
        except Exception as e:
            q.put(("error", {"error": str(e)}))
        finally:
            q.put((None, None))

    threading.Thread(target=_run, daemon=True).start()

    def _gen():
        while True:
            kind, payload = q.get()
            if kind is None:
                break
            yield "event: %s\ndata: %s\n\n" % (kind, json.dumps(payload))

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

def _pdc_token_and_reauth(body, base, version, verify):
    """Return (token, reauth) for a PDC call. reauth re-mints a token from
       username/password on a 401; it is None when only a bearer token was given
       (nothing to re-auth with). Token is kept in memory only, never persisted."""
    from sources import pdc_api
    user = body.get("username", "")
    pwd = body.get("password", "")
    token = (body.get("token") or "").strip()
    realm = (body.get("realm") or "pdc").strip()
    # If the user pasted the Keycloak realm URL as the base (a common mistake), the
    # base is normalized everywhere by pdc_api.clean_base; recover the realm from it
    # too so "paste the whole keycloak URL" works without re-typing the realm.
    _clean, _detected = pdc_api.split_base(base)
    if _detected and (not body.get("realm") or realm == "pdc"):
        realm = _detected
    base = _clean
    client_id = (body.get("client_id") or "pdc-client").strip()
    method = body.get("auth_method") or "auto"
    def _mint():
        """Mint a fresh PDC bearer token from the username/password (used to re-auth on a 401)."""
        return pdc_api.auth(base, user, pwd, version=version, verify_tls=verify,
                            realm=realm, client_id=client_id, method=method)
    reauth = None
    if user and pwd:
        reauth = _mint
    if not token:
        if not (user and pwd):
            raise RuntimeError("provide a bearer token, or a username and password")
        token = _mint()
    return token, reauth

@app.post("/api/pdc-token")
def pdc_token(body: dict = Body(default={})):
    """Authenticate to PDC and return the admin/Business-Steward JWT plus a
       display-only decode (username, roles, expiry) so the operator can confirm
       the right account before writing. Token is returned for in-memory use only;
       the app never persists it."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return _err("PDC base URL is required", 400)
    try:
        token = pdc_api.auth(base, body.get("username", ""), body.get("password", ""),
                             version=version, verify_tls=verify,
                             realm=(body.get("realm") or "pdc").strip(),
                             client_id=(body.get("client_id") or "pdc-client").strip(),
                             method=body.get("auth_method") or "auto")
    except Exception as e:
        return _err(str(e), 502)
    return {"token": token, "claims": pdc_api.decode_jwt(token)}

# Sample CSV for the bulk data-source loader — built from the canonical column list
# so the starter, an export, and the loader all share one shape. Leave optional
# columns (databaseType/configMethod/affinityId/region/fqdnId) blank to accept the
# kind-derived defaults; set them to override (an export fills the exact PDC codes).
def _bulk_sample_csv():
    import io, csv
    from sources import pdc_api
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=pdc_api.CSV_COLUMNS, extrasaction="ignore",
                       lineterminator="\r\n")
    w.writeheader()
    w.writerow({"kind": "postgres", "resourceName": "Operations_DB",
                "host": "db-host", "port": "5432", "databaseName": "public",
                "userName": "db_user", "password": "CHANGE_ME",
                "schemaNames": "public", "description": "Sample operational database"})
    w.writerow({"kind": "minio", "resourceName": "Documents",
                "endpoint": "http://minio-host:9000", "accessKey": "minioadmin",
                "secretKey": "CHANGE_ME", "container": "documents", "path": "/",
                "excludePatterns": "*.md;*.tmp",
                "description": "Sample document store (excludePatterns skips *.md and *.tmp)"})
    return buf.getvalue()

_BULK_SAMPLE_CSV = _bulk_sample_csv()

@app.post("/api/similarity")
def api_similarity(body: dict = Body(default={})):
    """Score the shown terms pairwise and return suggested merges (near-duplicate or
    same-concept names PDC would treat as unrelated). Body: {rows:[...], threshold?}."""
    import re as _re
    body = body or {}
    rows = body.get("rows") or []
    agg = {}
    for r in rows:
        nm = (r.get("Term") or "").strip()
        if not nm:
            continue
        d = agg.get(nm)
        if not d:
            d = agg[nm] = {"name": nm, "category": r.get("Category"),
                           "sensitivity": r.get("Sensitivity"), "pii": r.get("PII_Category"),
                           "tags": set(), "count": 0}
        d["count"] += 1
        for t in _re.split(r"[;,]", str(r.get("Suggested_Tags") or "")):
            t = t.strip()
            if t:
                d["tags"].add(t)
        # evidence rollup (first-wins for shapes, union for values/columns/FKs) so
        # score_pair can let profiled data outrank name similarity
        ev = d.setdefault("evidence_row", {"Value_Signature": "", "Value_Pattern": "",
                                           "Enum_Values": "", "PII_Category": "",
                                           "Source_Column": "", "Source_Keys": {}})
        for f in ("Value_Signature", "Value_Pattern", "PII_Category"):
            if not ev[f] and r.get(f):
                ev[f] = str(r[f]).strip()
        if r.get("Enum_Values"):
            have = set(x for x in ev["Enum_Values"].split(";") if x)
            have |= {x.strip() for x in str(r["Enum_Values"]).split(";") if x.strip()}
            ev["Enum_Values"] = ";".join(sorted(have))
        if r.get("Source_Column"):
            cols = [c.strip() for c in str(r["Source_Column"]).split(";") if c.strip()]
            have = [c.strip() for c in ev["Source_Column"].split(";") if c.strip()]
            ev["Source_Column"] = "; ".join(dict.fromkeys(have + cols))
        for sc, k in (r.get("Source_Keys") or {}).items():
            if isinstance(k, dict):
                ev["Source_Keys"][sc] = k
    terms = [dict(v, tags=sorted(v["tags"])) for v in agg.values()]
    sugg = similarity.suggest_merges(terms, threshold=body.get("threshold", similarity.DEFAULT_THRESHOLD))
    return {"suggestions": sugg, "term_count": len(terms)}

def _recommend_resolutions_run(body, progress=None):
    """The duplicate-advice ladder, shared by the sync route and its job twin.
    `progress` narrates: evidence → probe (live value sampling) → adjudicate
    (one model call per still-ambiguous group — the slow stretch)."""
    body = body or {}
    rows = body.get("rows") or []
    groups = similarity.group_rows(rows)
    probed = 0
    probes_by_name = {}

    def _p(ev):
        if progress:
            try:
                progress(ev)
            except Exception:
                pass

    _p({"phase": "evidence", "detail": "weighing cached scan evidence"})
    # live probe: only for groups the cached evidence leaves ambiguous
    cfg = body.get("conn") or {}
    if cfg.get("host") or cfg.get("database"):
        need = {}
        for nm, members in groups.items():
            base = similarity.recommend_resolution(members)
            if base["band"] == "high":
                continue
            srcs = []
            for m in members:
                first = str(m.get("Source_Column") or "").split(";")[0].strip()
                if first.count(".") >= 2:
                    srcs.append(first)
            if len(srcs) >= 2:
                need[nm] = srcs
        if need:
            try:
                flat = sorted({s for ss in need.values() for s in ss})
                _p({"phase": "probe",
                    "detail": "sampling %d live column(s)" % len(flat)})
                samples = suggester.sample_distinct_values(cfg, flat)
                for nm, srcs in need.items():
                    pr = []
                    for i in range(len(srcs)):
                        for j in range(i + 1, len(srcs)):
                            v, why = similarity.compare_value_sets(
                                samples.get(srcs[i]), samples.get(srcs[j]))
                            if v:
                                pr.append((v, why))
                    if pr:
                        probes_by_name[nm] = pr
                        probed += 1
            except Exception:
                pass                      # probe is best-effort; evidence still applies

    out = []
    for nm, members in groups.items():
        rec = similarity.recommend_resolution(members, probes=probes_by_name.get(nm))
        rec.update(name=nm, count=len(members), source="evidence")
        out.append(rec)

    # AI adjudicator for whatever is STILL ambiguous
    used_llm = False
    still_ambiguous = 0
    if body.get("ai"):
        fields = ("Term", "Category", "Definition", "Source_Column", "Value_Signature",
                  "Value_Pattern", "Enum_Values", "PII_Category")
        ambiguous = [{"name": r["name"],
                      "members": [{f: m.get(f, "") for f in fields}
                                  for m in groups[r["name"]]]}
                     for r in out if r["band"] != "high" or not r["action"]]
        # Reported so the caller can tell "the model was not NEEDED" from "the
        # model was not AVAILABLE" — used_llm is False for both, and blaming a
        # healthy Ollama for a run the data already settled is a lie the UI has
        # no way to catch.
        still_ambiguous = len(ambiguous)
        if ambiguous:
            verdicts, used_llm = llm.adjudicate_groups(
                ambiguous, model=body.get("model"), compute=body.get("compute"),
                progress=progress)
            for r in out:
                v = verdicts.get(r["name"])
                if v:
                    r.update(action=v["action"], reason=v["reason"],
                             band="review", source="ai")
    out.sort(key=lambda x: (x["band"] != "high", -x["count"]))
    return {"groups": out, "probed": probed, "used_llm": used_llm,
            "ambiguous": still_ambiguous}


@app.post("/api/recommend-resolutions")
def api_recommend_resolutions(body: dict = Body(default={})):
    """Advise Merge / Disambiguate / Keep separate for every same-named duplicate
    group in the review rows — the decision aid behind the cluster headers.
    Escalation ladder, cheapest first:
      1. cached scan evidence (FK links, profiled value sets, induced formats),
      2. a LIVE data probe when a connection is supplied (sample distinct values
         from each member column and compare the actual populations),
      3. the AI adjudicator (Ollama) for groups still ambiguous, when ai=true.
    Recommendations are hints only — nothing is auto-applied.
    Body: {rows, conn?, ai?, model?, compute?}. For ai=true prefer the job twin
    /api/jobs/recommend-resolutions — same work with live narration."""
    return _recommend_resolutions_run(body)

@app.post("/api/ask")
def api_ask(body: dict = Body(default={})):
    """The docs-grounded chat (spec backlog 10): answer product questions
    FROM the shipped documentation. Grounded-or-refuse — the model answers
    only from retrieved doc sections and cites them; with no model reachable
    the same call degrades to a cited doc search rather than vanishing.
    Body: {question, page?, ai?, model?}. `page` is the asking page's id
    (review, apply, govern…) and boosts its own sections."""
    from engine import docchat
    body = body or {}
    q = (body.get("question") or "").strip()
    if not q:
        return _err("ask a question", 400)
    return docchat.answer(q, page=(body.get("page") or "").strip() or None,
                          ai=bool(body.get("ai", True)),
                          model=body.get("model"), version=APP_VERSION)


@app.post("/api/dq-expectations")
def api_dq_expectations(body: dict = Body(default={})):
    """Data-quality expectations as their own export (kept when the Draft
    policies surface retired, 2026-08-23 — backlog 1's "do not lose them
    silently"): the induced value regex re-expressed as a format check, the
    profiled reference list as allowed_values, and the measured completeness/
    uniqueness baselines as thresholds (a later run below its baseline is a
    regression). Deterministic, derived from the same rows; feed the zip to
    your DQ runner. Body: {rows, glossary_name?, prefix?}."""
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    if not rows:
        return _err("no rows to derive expectations from", 400)
    gname = (body.get("glossary_name") or "Business Glossary").strip()
    quality = policy_draft.dq_rules_from_rows(rows, glossary_name=gname,
                                              prefix=body.get("prefix"))
    import zipfile as _zipfile
    buf = io.BytesIO()
    index = ["kind,name,file,term"]
    with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as z:
        for q in quality:
            z.writestr("Quality/" + q["filename"], json.dumps(q["rule"], indent=2) + "\n")
            index.append(f"quality,{q['rule']['name']},Quality/{q['filename']},{q['term']}")
        z.writestr("INDEX.csv", "\n".join(index) + "\n")
        z.writestr("README.txt",
                   "Data-quality expectations derived by the Glossary Generator from the\n"
                   "same scan profile the glossary was reviewed from. format = the induced\n"
                   "value regex; allowed_values = the profiled reference list;\n"
                   "completeness/uniqueness thresholds = the measured baselines (a later\n"
                   "run below its baseline is a regression). Feed these to your DQ runner\n"
                   "- they are expectations to evaluate, not PDC import artifacts.\n")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             "attachment; filename=dq-expectations.zip"})

@app.post("/api/qa-definitions")
def api_qa_definitions(body: dict = Body(default={})):
    """Definition QA before import: the deterministic linter (circular, echo,
    vague, too-short, copy-paste duplicates) always runs; with ai=true the LLM
    agent also judges whether each definition actually explains the business
    meaning, and proposes a better sentence. Rows come back with QA_Issues /
    QA_Suggestion stamped — flags and proposals only, the steward applies.
    Body: {rows, ai?, model?, compute?}."""
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    for r in rows:                                    # a QA run resets prior flags
        r.pop("QA_Issues", None)
        r.pop("QA_Suggestion", None)
    lint = defqa.lint_rows(rows)
    for i, issues in lint.items():
        rows[i]["QA_Issues"] = ";".join(issues)
    used_llm = False
    if body.get("ai"):
        rows, _n, used_llm = llm.qa_definitions_rows(
            rows, model=body.get("model"), compute=body.get("compute"))
    flagged = sum(1 for r in rows if r.get("QA_Issues"))
    return {"rows": rows, "flagged": flagged,
            "lint_flagged": len(lint), "used_llm": used_llm,
            "llm": {"online": used_llm or not body.get("ai")}}

@app.post("/api/ai-categorize")
def api_ai_categorize(body: dict = Body(default={})):
    """AI category assignment for uncategorized rows (or all rows with
    only_blank=false): the local model picks ONE category per term from the
    known set — pack categories + the categories already in use — and anything
    off-list is discarded. Body: {rows, only_blank?, model?, compute?}."""
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    # the UI sends the WHOLE glossary's category list (it may post rows in
    # chunks for progress; a slice's own categories would be too narrow)
    cats = [str(c).strip() for c in (body.get("categories") or []) if str(c).strip()]
    if not cats:
        cats = sorted({(r.get("Category") or "").strip() for r in rows} - {""})
    for c in tagdict.category_tags().keys():
        if c not in cats:
            cats.append(c)
    rows, updated, used_llm = llm.categorize_rows(
        rows, cats, model=body.get("model"), compute=body.get("compute"),
        only_blank=body.get("only_blank", True))
    return {"rows": rows, "updated": updated,
            "llm": {"online": used_llm}}

@app.post("/api/retag")
def api_retag(body: dict = Body(default={})):
    """Re-derive meaningful, controlled tags for a set of review rows (the grid's
       'Suggest tags' action). Deterministic; no rescan. Table-level record terms
       keep their table-level tags."""
    body = body or {}
    rows = body.get("rows") or []
    try:
        suggester.retag_rows(rows)
    except Exception as e:
        return _err(str(e)[:300], 400)
    return {"rows": rows}

@app.get("/api/tagdict")
def api_tagdict_get():
    """The per-company tag dictionary — the controlled allow-list + rules that drive
       tagging, seeded from the domain and grown from scans. Governs tag consistency
       into the Registry and the Policy Generator."""
    return tagdict.summary()

@app.post("/api/tagdict/sync")
def api_tagdict_sync(body: dict = Body(default={})):
    """One-way Review → Dictionary sync ON DEMAND. The save-path sync only
    fires when an edit triggers a save, so walking to the Dictionary without
    touching the grid adjudicated a pre-edit queue (field-caught: a term
    renamed to "pH Level" still pending as "Ph Level"). The Dictionary page
    posts the live rows on entry, so the stage-gate always sees current
    state — accepted edits refresh pending entries, case renames adopt the
    steward's casing, auto-pruned keys retro-retire. Same one-way rules as
    the save path: pending only, governed entries never change. Returns the
    refreshed summary (the GET shape) plus pending_refreshed."""
    body = body or {}
    rows = body.get("rows") or []
    refreshed = 0
    if rows:
        try:
            refreshed = tagdict.refresh_pending(rows)
        except Exception:
            refreshed = 0
        if refreshed:
            audit.record("dictionary.refresh_pending", actor=body.get("actor"),
                         via="dictionary-page", refreshed=refreshed)
    out = tagdict.summary()
    out["pending_refreshed"] = refreshed
    return out

@app.post("/api/tagdict")
def api_tagdict_save(body: dict = Body(default={})):
    """Steward save of the whole dictionary (terms/tags/rules). Guard-railed:
       generic baseline entries are protected, rule/term tags must exist, and
       sensitivity is validated — risky edits come back as warnings."""
    body = body or {}
    doc = body.get("dictionary") if isinstance(body.get("dictionary"), dict) else body
    try:
        warnings = tagdict.replace(doc)
    except Exception as e:
        return _err(str(e)[:300], 400)
    out = tagdict.summary()
    out["warnings"] = warnings
    audit.record("dictionary.save", actor=body.get("actor"),
                 terms=out.get("term_count"), tags=out.get("tag_count"),
                 warnings=len(warnings))
    return out

def _pending_universe(rows, sources, terms_l, tags_l):
    """Fold one row list into the pending-health evidence universe."""
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        t = str(r.get("Term") or "").strip().lower()
        if t:
            terms_l.add(t)
        for c in str(r.get("Source_Column") or "").split(";"):
            c = c.strip().lower()
            if c:
                sources.add(c)
        for tg in str(r.get("Suggested_Tags") or "").split(";"):
            tg = tg.strip().lower()
            if tg:
                tags_l.add(tg)


@app.get("/api/tagdict/pending-health")
@app.post("/api/tagdict/pending-health")
def api_tagdict_pending_health(body: dict = Body(default={})):
    """Which PENDING entries still have evidence anywhere? The universe is
    every SAVED glossary's rows PLUS the live workspace rows the caller may
    POST. The live rows matter on a first run: the autosave only writes once
    the glossary is NAMED, so before that the store is empty and every entry
    the scan just streamed in read as a fossil — the stale badge covered the
    whole queue and "Retire stale" offered to tombstone the entire vocabulary
    (field-caught). An entry whose sources, name and aliases appear nowhere
    is a real fossil — it came from a scan whose rows no longer exist,
    nothing can ever refresh it, and it pollutes the steward's queue. Names
    only; retiring stays a steward action through /api/tagdict/review."""
    sources, terms_l, tags_l = set(), set(), set()
    for v in _load_gloss().values():
        _pending_universe(v.get("rows"), sources, terms_l, tags_l)
    _pending_universe((body or {}).get("rows"), sources, terms_l, tags_l)
    return tagdict.stale_pending(sources=sources, terms=terms_l, tags=tags_l)

@app.post("/api/tagdict/review")
def api_tagdict_review(body: dict = Body(default={})):
    """Steward approve/reject of pending accreted items. Body: {kind:'tag'|'term',
       names:[...], action:'approve'|'reject'}. Only approved (or generic) items
       govern the Registry / Policy Generator."""
    body = body or {}
    kind = body.get("kind"); action = body.get("action", "approve")
    names = body.get("names") or []
    if kind not in ("tag", "term"):
        return _err("kind must be 'tag' or 'term'", 400)
    changed = tagdict.review(kind, names, action, target=body.get("target"))
    if changed:
        audit.record("%s.%s" % (kind, action), actor=body.get("actor"), names=names, changed=changed)
    out = tagdict.summary(); out["changed"] = changed
    return out

# pack-domain / company-name keywords -> PDC business-domain classifier
_DOMAIN_MAP = [
    (r"credit.?union|\bbank", "Banking"),
    (r"health|clinic|hospital|medical|patient", "Healthcare"),
    (r"manufactur|precision|component|factory", "Manufacturing"),
    (r"retail|outfitter|merchandis|\bshop|e.?commerce", "E-commerce"),
    (r"utilit|water|electric|\bgas\b", "Utilities"),
    (r"energy|oil|solar|wind", "Energy"),
    (r"insur|financ|invest|capital", "Finance"),
    (r"telecom", "Telecommunication"),
    (r"logistic|supply.?chain|freight", "Logistics and supply chain Management"),
    (r"government|municipal|county|federal", "Government sector"),
    (r"legal|law\b", "Legal"),
    (r"transport|transit|rail|airline", "Transportation"),
    (r"real.?estate|property", "Real estate"),
    (r"software|saas|technolog", "Technology"),
]

@app.post("/api/suggest-domain")
def api_suggest_domain(body: dict = Body(default={})):
    """Pick the PDC business-domain classifier from the company's OWN data: the
    installed pack's domain key + the company name first (deterministic keyword
    map), the local AI as fallback for unmapped businesses (guardrail: the
    answer must be in the supplied list). Advice for the Govern page's DOMAIN
    default. Body: {domains, categories?, terms?, model?, compute?}."""
    import re as _re
    body = body or {}
    domains = [str(d) for d in (body.get("domains") or []) if str(d).strip()]
    company = llm.COMPANY if llm.COMPANY != "your organization" else ""
    pack_domain = str(tagdict.load().get("domain") or "")
    hay = (pack_domain + " " + company).lower()
    if hay.strip() and domains:
        for rx, dom in _DOMAIN_MAP:
            if _re.search(rx, hay) and dom in domains:
                return {"domain": dom, "used_llm": False,
                        "reason": f"matched the installed pack/company ({pack_domain or company})"}
    dom, used = llm.suggest_domain(company, body.get("categories"), body.get("terms"),
                                   domains, model=body.get("model"), compute=body.get("compute"))
    return {"domain": dom, "used_llm": used,
            "reason": ("AI classification from company + glossary content" if dom else
                       "no match — pick manually (Ollama offline and no keyword hit)")}

@app.post("/api/tagdict/ai-review")
def api_tagdict_ai_review(body: dict = Body(default={})):
    """Advise on the pending scan-found terms: a deterministic near-duplicate
    pass against the governed vocabulary (similarity scoring - 'Apy' vs 'APR
    Rate'), then the local AI agent judges the rest with the captured context
    (category, definition, sources). Advice only - the steward clicks approve /
    reject / alias. Body: {model?, compute?, names?} — names limits the pass
    to those pending terms, so the UI can batch and show real progress."""
    body = body or {}
    d = tagdict.load()
    gov = sorted(tagdict.governed_terms())
    pending = []
    for n, m in (d.get("terms") or {}).items():
        if (m or {}).get("status") == "pending" and (m or {}).get("layer") != "generic":
            pending.append({"name": n, "category": m.get("category", ""),
                            "definition": m.get("definition", ""),
                            "sources": m.get("sources", []),
                            "sensitivity": m.get("sensitivity", ""),
                            "pattern": m.get("pattern", ""),
                            "tags": m.get("tags", [])})
    names = body.get("names")
    if isinstance(names, list) and names:
        want = {str(x) for x in names}
        pending = [x for x in pending if x["name"] in want]
    advice = {}
    # deterministic near-duplicate pass first (cheap, explainable): normalized
    # edit distance on the names alone — 'Dividend Rates' vs 'Dividend Rate'
    for item in pending:
        best, best_s = None, 0.0
        a = similarity._norm(item["name"])
        for g in gov:
            r = similarity._lev_ratio(a, similarity._norm(g))
            if r > best_s:
                best, best_s = g, r
        if best and best_s >= 0.85:
            advice[item["name"]] = {"action": "alias", "target": best,
                                    "reason": f"near-duplicate of governed term '{best}' ({int(best_s*100)}% name match)"}
    used_llm = False
    rest = [x for x in pending if x["name"] not in advice]
    if rest:
        llm_advice, used_llm = llm.review_pending_terms(
            rest, gov, model=body.get("model"), compute=body.get("compute"))
        advice.update(llm_advice)
    return {"advice": advice, "pending": len(pending), "used_llm": used_llm}

@app.post("/api/tagdict/fold-advisor")
def api_tagdict_fold_advisor(body: dict = Body(default={})):
    """Advise alias folds across the GOVERNED company vocabulary — the
    pending-review near-duplicate pass only covers pending items, so twins
    that both got approved (or arrived via the pack) had no advisor until
    now. Deterministic: each name is token-expanded through the pack's
    abbreviations map (mbr -> Member), then compared by normalized edit
    distance. Identical expansions are a high-confidence fold; >=0.85 ratio
    is flagged for review. Canonical = the term whose own name already IS
    its expansion (the unabbreviated spelling), tie-broken by reviewed
    usage, then name length. Advice only — the steward clicks each fold."""
    import re as _re
    d = tagdict.load()
    pack = tagdict._domain_pack() or {}
    ab = {str(k).lower(): str(v).lower() for k, v in (pack.get("abbreviations") or {}).items()}
    gov = [(n, m) for n, m in (d.get("terms") or {}).items()
           if (m or {}).get("layer") == "company"]

    def toks(name):
        return [t for t in _re.split(r"[^a-z0-9]+", str(name).lower()) if t]

    def expand(name):
        return " ".join(ab.get(t, t) for t in toks(name))

    def canon_score(n):
        unabbrev = 1 if " ".join(toks(n)) == expand(n) else 0
        used = len((d.get("term_usage") or {}).get(n) or ())   # distinct source columns
        return (unabbrev, used, len(str(n)))

    pairs = []
    for i in range(len(gov)):
        for j in range(i + 1, len(gov)):
            na, nb = gov[i][0], gov[j][0]
            ea, eb = expand(na), expand(nb)
            if ea == eb:
                conf, why = "high", "identical after abbreviation expansion ('%s')" % ea
            else:
                r = similarity._lev_ratio(ea, eb)
                if r < 0.85:
                    continue
                conf, why = "review", "%d%% name match after abbreviation expansion" % int(r * 100)
            keep, fold = (na, nb) if canon_score(na) >= canon_score(nb) else (nb, na)
            pairs.append({"keep": keep, "fold": fold, "confidence": conf, "reason": why})
    pairs.sort(key=lambda p: (p["confidence"] != "high", p["keep"]))
    return {"pairs": pairs, "governed": len(gov)}

@app.post("/api/tagdict/reset")
def api_tagdict_reset(body: dict = Body(default={})):
    """Reseed from the domain pack + defaults. Approved company items and company
       rules are preserved (the governed set survives a reseed); pending items are
       discarded; a timestamped backup of the previous file is taken first."""
    body = body or {}
    res = tagdict.reset()
    kept = (res or {}).get("kept") or {}
    audit.record("dictionary.reset", actor=body.get("actor"),
                 detail=("preserved approved: %d tag(s), %d term(s), %d rule(s)"
                         % (kept.get("tags", 0), kept.get("terms", 0), kept.get("rules", 0))
                         + ((" · backup: " + os.path.basename(res["backup"])) if (res or {}).get("backup") else "")))
    out = tagdict.summary()
    out["kept"] = kept
    return out

@app.get("/api/audit")
def api_audit(n: int = 50):
    """Recent governance audit entries (newest first) + summary."""
    return {"entries": audit.recent(n), "summary": audit.summary()}

@app.get("/api/audit/export.json")
def api_audit_export():
    """Download the full governance audit trail (ships alongside the Registry)."""
    return Response(json.dumps(audit.all_entries(), indent=2), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=governance_audit.json"})

@app.get("/api/governance-summary")
def api_governance_summary():
    """One consolidated, read-only payload for the Catalog Insights / viz app to poll:
    vocabulary health (governed vs pending, the tag facet, empty + fragmenting tags),
    the audit summary, and drift (off-vocabulary tags aggregated across written
    registries). Permissive CORS so a browser-side viz can call it directly."""
    import glob
    s = tagdict.summary()
    fh = tagdict.facet_health()
    floors = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "none": 0}
    for t in fh["facet"]:
        f = t.get("sensitivity_floor")
        floors[f if f in ("HIGH", "MEDIUM", "LOW") else "none"] += 1
    pend = {"tags": [t["tag"] for t in s["tags"] if t["status"] == "pending"],
            "terms": [t["term"] for t in s["terms"] if t["status"] == "pending"]}

    # drift: aggregate off_vocabulary_tags across every written registry
    registries, total_off, total_concepts = [], 0, 0
    for path in sorted(glob.glob(os.path.join(REGISTRY_DIR, "registry.*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                reg = json.load(f)
        except Exception:
            continue
        concepts = reg.get("concepts", []) or []
        off = sum(len(c.get("off_vocabulary_tags") or []) for c in concepts)
        flagged = sum(1 for c in concepts if c.get("off_vocabulary_tags"))
        total_off += off
        total_concepts += len(concepts)
        registries.append({"glossary": reg.get("glossary"), "glossary_id": reg.get("glossary_id"),
                           "file": os.path.basename(path), "concepts": len(concepts),
                           "off_vocabulary_tags": off, "concepts_with_drift": flagged})

    payload = {
        "schema": "governance-summary/1",
        "generated_at": audit._now(),
        "app_version": APP_VERSION,
        "domain": s.get("domain"),
        "sources": s.get("sources", []),
        "vocabulary": {
            "tags": {"total": s["tag_count"], "generic": s["generic_tags"],
                     "governed": s["governed_tags"], "pending": s["pending_tags"]},
            "terms": {"total": s["term_count"], "generic": s["generic_terms"],
                      "governed": s["governed_terms"], "pending": s["pending_terms"]},
            "rules": s["rule_count"],
            "sensitivity_floor_distribution": floors,
            "facet": fh["facet"],
            "health": {"empty_governed_tags": fh["empty_governed_tags"],
                       "fragmenting": fh["fragmenting"],
                       "pending_review": pend},
        },
        "audit": audit.summary(),
        "drift": {"registries": registries, "total_concepts": total_concepts,
                  "total_off_vocabulary_tags": total_off,
                  "note": "off_vocabulary_tags = concept tags outside the governed allow-list"},
    }
    return JSONResponse(payload, headers={
        "Access-Control-Allow-Origin": "*",      # read-only; lets the viz app poll cross-origin
        "Cache-Control": "no-store"})

# --------------------------------------------------------------------------- #
#  Seed-request pickup — the Glossary half of the no-seed feedback loop.
#
#  When the Policy Generator finds Registry concepts with no detection seeds
#  and no detection_intent, it writes seed-request*.json into the SAME
#  registries/ directory as the Registry it loaded, shape:
#    {requested_at, registry_file, terms: [{name, reason: "no_seed"}]}
#  The Review page surfaces pending requests as a banner; "Mark handled"
#  renames the file to *.handled.json so it stops showing without losing the
#  paper trail.
# --------------------------------------------------------------------------- #

@app.get("/api/seed-requests")
def api_seed_requests():
    """List pending (un-handled) seed requests from the Policy Generator."""
    import glob
    out = []
    for path in sorted(glob.glob(os.path.join(REGISTRY_DIR, "seed-request*.json"))):
        if path.endswith(".handled.json"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                req = json.load(f) or {}
        except Exception:
            continue  # unreadable/partial file — skip, never break the page
        terms = [t for t in (req.get("terms") or [])
                 if isinstance(t, dict) and str(t.get("name") or "").strip()]
        out.append({"file": os.path.basename(path),
                    "requested_at": req.get("requested_at"),
                    "registry_file": req.get("registry_file"),
                    "terms": terms})
    out.sort(key=lambda r: str(r.get("requested_at") or ""), reverse=True)
    return {"requests": out}

@app.post("/api/seed-requests/handle")
def api_seed_request_handle(body: dict = Body(default={})):
    """Mark one seed request handled: rename seed-request*.json -> *.handled.json."""
    name = os.path.basename(str((body or {}).get("file") or "").strip())
    if not (name.startswith("seed-request") and name.endswith(".json")
            and not name.endswith(".handled.json")):
        return _err("not a seed-request file", 400)
    path = os.path.join(REGISTRY_DIR, name)
    if not os.path.isfile(path):
        return _err("not found", 404)
    dest = path[:-len(".json")] + ".handled.json"
    os.replace(path, dest)   # atomic; overwrites a stale marker on every OS
    return {"handled": name, "renamed_to": os.path.basename(dest)}

@app.post("/api/export-pack")
def api_export_pack(body: dict = Body(default={})):
    """Generate a domain pack from the reviewed scan results: table mappings,
    learned abbreviations, the governed company vocabulary, and — the point —
    curated_seeds carrying the induced value patterns and profiled reference
    lists, so the pack's detection seeds are specific to THIS company's data.
    MERGES over the installed pack: learned content fills gaps; where the scan
    DISAGREES with the pack the conflict is reported (pack vs scan value) and
    the steward's resolutions decide — curation keeps the pack's value by
    default, curated_seeds prefer the fresher scan evidence.
    Body: {rows, resolutions?: {"key::name": "scan"|"pack"}, apply?}."""
    body = body or {}
    rows = body.get("rows") or []
    resolutions = body.get("resolutions") or {}
    base = {}
    try:
        import json as _json
        path = paths.domain_pack_path()
        with open(path, encoding="utf-8") as f:
            base = _json.load(f)
    except Exception:
        base = {}
    pack, report = packgen.build_pack(rows, base=base, resolutions=resolutions)
    out = {"pack": pack, "report": report, "merged_over": bool(base),
           "learned": sum(v for k, v in report.items()
                          if isinstance(v, int) and k != "scan_overrides")}
    if body.get("apply"):
        # write the refreshed pack where the app reads it (backing up the old
        # one) and reseed the dictionary from it — approved company items and
        # company rules survive the reseed, pending scan-noise is discarded
        import json as _json, shutil, time
        # WRITE path, not the read path: the read path can be the shipped
        # starter, which in a packaged install lives in Program Files. Writing
        # there fails and this endpoint would report success on a file it never
        # replaced.
        path = paths.domain_pack_write_path()
        backup = None
        try:
            if os.path.exists(path):
                backup = path + ".backup-" + time.strftime("%Y%m%d-%H%M%S")
                shutil.copy2(path, backup)
        except Exception:
            backup = None
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(pack, f, indent=2, ensure_ascii=False)
        rs = tagdict.reset(preserve_approved=True)
        out.update({"applied": True, "pack_path": path, "pack_backup": backup,
                    "reseed_kept": rs.get("kept")})
        _receipt("pack", learned=out.get("learned"), path=path,
                 applied=True)
    return out

@app.get("/api/tagdict/export.json")
def api_tagdict_export():
    """Download the raw dictionary artifact (shareable governance record)."""
    return Response(json.dumps(tagdict.load(), indent=2), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=tag_dictionary.json"})

@app.get("/api/pdc/bulk-load/sample.csv")
def pdc_bulk_sample():
    """Download a starter CSV for the bulk loader (two sample sources). Replace the
       CHANGE_ME secrets before importing."""
    return Response(_BULK_SAMPLE_CSV, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=datasources.csv"})

# --- Export the app's own saved connections (the cards) as bulk-loader CSV -------
# These are the connections you build by hand in the New-connection form. The app
# already holds their credentials (it needs them to scan), so unlike a PDC export
# this CSV includes secrets and reloads straight into the bulk loader.
_ENGINE_KIND = {"postgresql": "postgres", "postgres": "postgres", "pg": "postgres",
                "mysql": "mysql", "mariadb": "mysql",
                "sqlserver": "mssql", "mssql": "mssql", "oracle": "oracle"}

def _safe_ds_name(name):
    """PDC data-source names must start with a letter and contain only letters,
       digits and underscores (no spaces)."""
    import re
    s = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip()).strip("_")
    if not s:
        s = "data_source"
    if not s[0].isalpha():
        s = "ds_" + s
    return s

def _saved_conn_to_row(conn):
    """Map one saved connection ({name,type,config}) to a bulk-loader CSV row."""
    t = (conn.get("type") or "").lower()
    cfg = conn.get("config") or {}
    name = _safe_ds_name(conn.get("name") or conn.get("id") or "")
    if t == "db":
        return {"kind": _ENGINE_KIND.get(str(cfg.get("engine", "")).lower(), "postgres"),
                "resourceName": name, "host": cfg.get("host", ""),
                "port": str(cfg.get("port", "") or ""), "databaseName": cfg.get("database", ""),
                "userName": cfg.get("user", ""), "password": cfg.get("password", ""),
                "schemaNames": cfg.get("schema", "") or "", "description": conn.get("name", "")}
    if t == "minio":
        ep = str(cfg.get("endpoint", "") or "")
        if ep and "://" not in ep:
            ep = ("https://" if cfg.get("secure") else "http://") + ep
        return {"kind": "minio", "resourceName": name, "endpoint": ep,
                "accessKey": cfg.get("access_key", ""), "secretKey": cfg.get("secret_key", ""),
                "container": cfg.get("bucket", ""), "path": cfg.get("prefix", "") or "/",
                "description": conn.get("name", "")}
    return None  # ddl / unknown — not a PDC data source

@app.get("/api/connections/export.csv")
def connections_export_csv():
    """Export the app's saved connections as a bulk-loader CSV (same columns the
       loader consumes). Includes credentials, so the CSV loads straight back in —
       treat the file as sensitive."""
    import io, csv
    from sources import pdc_api
    rows = [r for r in (_saved_conn_to_row(c) for c in _load_connections()) if r]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=pdc_api.CSV_COLUMNS, extrasaction="ignore",
                       lineterminator="\r\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=connections.csv"})

@app.post("/api/pdc/connections/export")
def pdc_connections_export(body: dict = Body(default={})):
    """Read the data sources already registered in PDC and return them as a
       bulk-loader CSV (same columns the loader consumes), so a hand-built
       connection can be captured and replayed. Secrets are blanked — PDC never
       returns plaintext credentials — so the operator re-enters them before reload.
       Auth is a bearer token or username/password, exactly like the other PDC calls."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or body.get("base") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return _err("PDC base URL is required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
    except Exception as e:
        return _err(str(e), 401)
    try:
        sources = pdc_api.list_data_sources(base, token, version=version, verify_tls=verify)
    except Exception as e:
        return _err("could not list data sources: %s" % str(e)[:300], 502)
    csv_text = pdc_api.connections_to_csv(sources)
    fmt = (body.get("format") or "csv").lower()
    if fmt == "json":
        return {"count": len(sources), "csv": csv_text,
                "names": [s.get("resourceName") for s in sources if isinstance(s, dict)]}
    return Response(csv_text, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=pdc-connections.csv"})

def _bulk_load_events(body):
    """Generator behind /api/pdc/bulk-load and its job twin: for each row
       create -> test-connection (poll) -> metadata ingest, yielding one event
       dict per row (plus start/done). Auth is a bearer token or
       username/password; secrets are never persisted or logged."""
    from sources import pdc_api
    base = (body.get("base_url") or body.get("base") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    opts = body.get("options") or {}
    do_test = bool(opts.get("test", False))   # no-op: no confirmed public test job
    do_ingest = bool(opts.get("ingest", True))
    wait = bool(opts.get("wait", True))
    replace_existing = bool(opts.get("replace_existing", False))
    internal_scan = bool(opts.get("internal_scan", False))
    do_profile = bool(opts.get("profile", False))
    # Defaults TRUE: a CSV in an object store almost always carries a header, and
    # scanning without it names the columns Column-0..Column-N, which is worse
    # than useless - it looks like real structure.
    header_row = bool(opts.get("header_row", True))
    # Analysis is split by SOURCE TYPE, as PDC splits it: a database's tables go
    # through Data Profiling, an object store's files through Data Discovery.
    do_discover = bool(opts.get("discover", True))
    # Options ON the object store's scan: read the structured files' columns, and
    # extract the documents' own properties.
    profile_files = bool(opts.get("profile_files", True))
    doc_metadata = bool(opts.get("doc_metadata", True))
    # 0 = no age restriction, matching PDC's own slider default.
    try:
        skip_recent_days = max(0, int(opts.get("skip_recent_days") or 0))
    except (TypeError, ValueError):
        skip_recent_days = 0
    dry_run = bool(body.get("dry_run", False))

    rows = body.get("rows")
    if not rows and body.get("csv"):
        try:
            rows = pdc_api.parse_csv_rows(body["csv"])
        except Exception as e:
            yield {"event": "error", "message": "could not parse CSV: %s" % e}
            return
    rows = rows or []
    if not base:
        yield {"event": "error", "message": "PDC base URL is required"}
        return
    if not rows:
        yield {"event": "error", "message": "no rows to load — provide 'rows' or 'csv'"}
        return

    # Dry run: just build and echo the (redacted) bodies, no auth, no calls.
    if dry_run:
        yield {"event": "start", "total": len(rows), "dry_run": True}
        for idx, row in enumerate(rows, 1):
            try:
                b = pdc_api.build_data_source_body(row)
                ev = {"event": "row", "index": idx, "total": len(rows),
                      "result": {"resourceName": b.get("resourceName"),
                                 "create": "DRY", "ingest": "DRY", "job": "DRY",
                                 "error": None},
                      "body": pdc_api.redact_secrets(b)}
            except Exception as e:
                ev = {"event": "row", "index": idx, "total": len(rows),
                      "result": {"resourceName": row.get("resourceName"),
                                 "create": "FAIL", "error": str(e)[:300]}}
            yield ev
        yield {"event": "done", "dry_run": True, "total": len(rows)}
        return

    try:
        token, reauth = _pdc_token_and_reauth(body, base, version, verify)
    except Exception as e:
        yield {"event": "error", "message": str(e)}
        return

    yield {"event": "start", "total": len(rows)}
    results = []
    for idx, row in enumerate(rows, 1):
        name = row.get("resourceName") or row.get("name") or ("row %d" % idx)
        yield {"event": "row_start", "index": idx, "total": len(rows),
               "resourceName": name}
        try:
            rec = pdc_api.bulk_load_one(base, token, row, version=version,
                                        verify_tls=verify, do_test=do_test,
                                        do_ingest=do_ingest, wait=wait,
                                        replace_existing=replace_existing,
                                        internal_scan=internal_scan,
                                        do_profile=do_profile,
                                        do_discover=do_discover,
                                        profile_files=profile_files,
                                        header_row=header_row,
                                        doc_metadata=doc_metadata,
                                        skip_recent_days=skip_recent_days)
        except pdc_api.TokenExpired:
            if reauth:
                try:
                    token = reauth()
                    rec = pdc_api.bulk_load_one(base, token, row, version=version,
                                                verify_tls=verify, do_test=do_test,
                                                do_ingest=do_ingest, wait=wait,
                                                replace_existing=replace_existing,
                                                internal_scan=internal_scan,
                                                do_profile=do_profile,
                                                do_discover=do_discover,
                                                profile_files=profile_files,
                                                header_row=header_row,
                                                doc_metadata=doc_metadata,
                                                skip_recent_days=skip_recent_days)
                except Exception as e:
                    rec = {"resourceName": name, "create": "FAIL",
                           "error": "re-auth/retry failed: %s" % str(e)[:240]}
            else:
                rec = {"resourceName": name, "create": "FAIL",
                       "error": "token expired and no username/password to re-auth"}
        except Exception as e:
            rec = {"resourceName": name, "create": "FAIL", "error": str(e)[:300]}
        results.append(rec)
        yield {"event": "row", "index": idx, "total": len(rows), "result": rec}

    ok = sum(1 for r in results if r.get("create") in ("OK", "EXISTS", "RECREATED")
             and r.get("ingest") in ("OK", "SKIP")
             and r.get("job") in ("OK", "SKIP"))
    yield {"event": "done", "total": len(rows), "ok": ok,
           "failed": len(rows) - ok, "results": results}

@app.post("/api/pdc/bulk-load")
def pdc_bulk_load(body: dict = Body(default={})):
    """Bulk-register data sources in PDC from CSV/JSON rows: for each row
       create -> test-connection (poll) -> metadata ingest. Streams one NDJSON
       event per row (plus start/done) so the UI can show live progress. Auth is
       a bearer token or username/password; secrets are never persisted or logged.
       options: {test, ingest, wait} all default true; dry_run previews bodies."""
    body = body or {}
    def gen():
        for ev in _bulk_load_events(body):
            yield json.dumps(ev) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")

def _apply_to_pdc_impl(body, progress=None):
    """The apply pipeline shared by the JSON, SSE and job endpoints. Returns the
       report dict; raises ValueError (bad request) or RuntimeError (PDC-side)."""
    from sources import pdc_api
    api_json = body.get("json") or []
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    dry_run = bool(body.get("dry_run", True))
    calc_trust = bool(body.get("calculate_trust", False))
    apply_table_ratings = bool(body.get("apply_table_ratings", True))
    skip_unresolved = bool(body.get("skip_unresolved_terms", False))
    desc_mode = (body.get("desc_mode") or "fill").strip().lower()
    _rows = body.get("rows") or []
    _gname0 = (body.get("glossary_name") or "").strip()
    table_terms = suggester.table_term_directory(_rows, _gname0 or "Business Glossary") if _rows else None
    if not base:
        raise ValueError("PDC base URL is required")
    if not api_json:
        raise ValueError("no Data Elements JSON to apply — export and resolve first")
    try:
        token, reauth = _pdc_token_and_reauth(body, base, version, verify)
        gname = (body.get("glossary_name") or "").strip()
        default_gid = suggester.det_glossary_id(gname) if gname else None
        report = pdc_api.apply_to_pdc(base, token, api_json, version=version,
                                      verify_tls=verify, dry_run=dry_run, reauth=reauth,
                                      calculate_trust=calc_trust,
                                      apply_table_ratings=apply_table_ratings,
                                      skip_unresolved_terms=skip_unresolved,
                                      glossary_name=(gname or None),
                                      default_glossary_id=default_gid,
                                      desc_mode=desc_mode, table_terms=table_terms,
                                      progress=progress)
    except Exception as e:
        raise RuntimeError(str(e))
    report.pop("token", None)  # never hand the token back to the browser
    return report

@app.post("/api/apply-to-pdc")
def apply_to_pdc(body: dict = Body(default={})):
    """Resolve each Data Element column in PDC, merge the new businessTerms +
       features into whatever it already carries, and PATCH it back. dry_run=true
       returns every planned PATCH (id + body) without sending. Optionally runs
       Calculate Trust Score on the touched ids after an apply."""
    body = body or {}
    try:
        return _apply_to_pdc_impl(body)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception as e:
        return _err(str(e), 502)

@app.post("/api/apply-to-pdc-stream")
def apply_to_pdc_stream(body: dict = Body(default={})):
    """Same as /api/apply-to-pdc, but streams Server-Sent Events so the browser can
       show a live per-column progress bar. The apply logic is unchanged — it just
       runs in a worker thread with a progress callback that feeds an SSE queue.
       Emits `event: progress` per column/phase and a final `event: done` (report)
       or `event: error`."""
    body = body or {}
    # preserve the pre-flight 400s of the old endpoint before the stream starts
    if not (body.get("base_url") or "").strip():
        return _err("PDC base URL is required", 400)
    if not (body.get("json") or []):
        return _err("no Data Elements JSON to apply — export and resolve first", 400)

    q = _queue_mod.Queue()

    def _run():
        try:
            report = _apply_to_pdc_impl(body, progress=lambda ev: q.put(("progress", ev)))
            q.put(("done", report))
        except Exception as e:
            q.put(("error", {"error": str(e)}))
        finally:
            q.put((None, None))

    threading.Thread(target=_run, daemon=True).start()

    def _gen():
        while True:
            kind, payload = q.get()
            if kind is None:
                break
            yield "event: %s\ndata: %s\n\n" % (kind, json.dumps(payload))

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/trigger-profiling")
def trigger_profiling(body: dict = Body(default={})):
    """Kick off a PDC Data Discovery (profiling) job on the document/object-store
       entities in a Data-Elements payload, so files that show 'Profiled Status:
       SKIPPED' get profiled and gain PDC's own Data Quality metric.

       Body: the PDC connection fields + 'json' (the Data-Elements records). We keep
       only the object-store records, resolve their folders (cascading to files) to
       entity UUIDs, and POST the discovery job. 'poll' optionally waits for the job
       to finish so the caller can immediately re-pull profiling stats."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    api_json = body.get("json") or []
    if not base:
        return _err("PDC base URL is required", 400)
    # restrict to object-store records; database columns are profiled by scanning the DB
    docs = [r for r in api_json
            if str(r.get("type", "")).upper() in ("OBJECT", "FILE", "DIRECTORY")]
    if not docs:
        return _err("no document/object-store records to profile — this "
                    "action profiles MinIO/S3 files, not database columns", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        scope_ids, labels, scope_stats = pdc_api.resolve_document_scope(
            base, token, docs, version=version, verify_tls=verify)
        if not scope_ids:
            return _err("could not resolve any document folders/files in "
                        "PDC — confirm the object store has been scanned into the "
                        "catalog first", 404)
        baseline = {}
        try:
            baseline = pdc_api.profiled_snapshot(base, token, scope_ids,
                                                 version=version, verify_tls=verify)
        except Exception:
            baseline = {}
        res = pdc_api.trigger_data_discovery(
            base, token, scope_ids, version=version, verify_tls=verify,
            poll=bool(body.get("poll", False)))
        res["baseline"] = baseline
        res["scope_ids"] = [str(x) for x in scope_ids][:20]
    except Exception as e:
        return _err(str(e), 502)
    res.pop("raw", None)
    res["scope"] = labels
    res["scope_stats"] = scope_stats
    # Scoping a folder cascades to its files; scoping files does not. A payload
    # carries one representative file per folder, so a fallback profiles exactly
    # those and leaves every sibling untouched — while the job still reports
    # SUCCESS. Say so rather than letting "5 target(s)" imply full coverage.
    if not scope_stats.get("cascaded"):
        others = max(0, len(docs) - len(scope_ids))
        res["scope_warning"] = (
            "Could not resolve the document FOLDERS in PDC, so %d individual file(s) "
            "were profiled instead. Folder scope cascades to every file inside it; "
            "file scope does not — any other files in those folders were NOT profiled."
            % scope_stats.get("files", len(scope_ids))
            + (" Confirm the object store's folders are catalogued." if others else ""))
    job_id = res.get("job_id") or res.get("id") or ""
    status = res.get("status") or res.get("state") or ("completed" if res.get("done") else "submitted")
    res["check"] = {
        "title": "Discovery check",
        "rows": [
            {"label": "Resolved in PDC", "value": f"{len(scope_ids)} folder(s)/file(s)"},
            {"label": "Job", "value": (str(status) + (f" · {job_id}" if job_id else ""))},
        ],
        "issues": ([] if scope_ids else
                   [{"tone": "warn", "text": "Nothing resolved — scan the object store into the catalog first."}]),
        "tone": "ok" if scope_ids else "warn",
        "verdict": (f"Data Discovery submitted for {len(scope_ids)} object(s). When it finishes, re-pull profiling "
                    "(or the app-vs-PDC side-by-side) to see each file's Data Quality — the fourth Trust-Score input."),
    }
    return res

_JOB_TERMINAL = ("COMPLETED", "COMPLETE", "SUCCESS", "SUCCEEDED", "DONE",
                 "FINISHED", "FAILED", "FAIL", "ERROR", "CANCELLED", "CANCELED")

@app.post("/api/discovery-progress")
def api_discovery_progress(body: dict = Body(default={})):
    """Version-agnostic Data Discovery progress: compare each scoped entity's
    system.profiledAt against the pre-submission baseline — v3's bulk job
    endpoint returns no job id, so the entities themselves are the truth.

    Terminal-aware: PDC never profiles some file types (pdf/docx often yield
    no Data Quality), so an entity's profiledAt may NEVER flip even though the
    discovery worker finished long ago. When the caller passes the job_id that
    trigger-profiling returned (v1/v2 — v3's bulk endpoint has none), the
    worker's own status is polled too, and `worker_done` tells the watcher to
    stop instead of hanging until its budget runs out.

    Body: {ids, baseline, job_id?, base_url, auth...}.
    Returns {profiled, total, done, per: {id: bool}, job: {status, activity,
    worker, duration, error} | null, worker_done}."""
    from sources import pdc_api
    body = body or {}
    ids = [str(x) for x in (body.get("ids") or []) if str(x).strip()]
    baseline = body.get("baseline") or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base or not ids:
        return _err("base_url and ids are required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        snap = pdc_api.profiled_snapshot(base, token, ids, version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e), 502)
    changed = {i for i in ids if snap.get(i) and snap.get(i) != baseline.get(i)}
    # the discovery job/worker state, when a job id exists to poll (best-effort:
    # a status fetch that fails must not break the entity-based progress signal)
    job, worker_done = None, False
    job_id = str(body.get("job_id") or "").strip()
    if job_id:
        try:
            st = pdc_api.job_status(base, token, job_id, version=version, verify_tls=verify)
            st.pop("raw", None)
            job = st
            worker_done = str(st.get("status") or "").upper() in _JOB_TERMINAL
        except Exception:
            job = None
    return {"profiled": len(changed), "total": len(ids),
            "done": len(changed) == len(ids) and bool(ids),
            "per": {i: (i in changed) for i in ids},
            "job": job, "worker_done": worker_done}

@app.post("/api/job-status")
def job_status_route(body: dict = Body(default={})):
    """Poll a PDC background job by id (GET /jobs/{id}/status) so the UI can show a
       profiling/discovery job's progress without leaving the app."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    job_id = (body.get("job_id") or "").strip()
    if not base or not job_id:
        return _err("base_url and job_id are required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        st = pdc_api.job_status(base, token, job_id, version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e), 502)
    st.pop("raw", None)
    return st

@app.post("/api/pdc-profiling")
def pdc_profiling(body: dict = Body(default={})):
    """Pull PDC's own profiling stats for a set of columns, keyed by
       'schema.table.column', for the app-vs-PDC side-by-side."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    columns = body.get("columns") or []
    sample_limit = int(body.get("sample_limit", 20) or 20)
    if not base:
        return _err("PDC base URL is required", 400)
    if not columns:
        return _err("no columns supplied — run discovery first", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        profiles = pdc_api.pdc_profile_for_columns(base, token, columns, version=version,
                                                   verify_tls=verify, sample_limit=sample_limit)
    except Exception as e:
        return _err(str(e), 502)
    # Derive a Data Quality score from PDC's OWN measurements, per column.
    # The app scores from its own sampling, which it cannot always do: a PDF or
    # DOCX has no rows to sample, and a large file is only partly read. Where
    # PDC has profiled server-side its numbers are the better evidence — and for
    # those formats, the only evidence. None where PDC profiled nothing usable,
    # never a manufactured 0 or 100.
    derived = 0
    for key, p in (profiles or {}).items():
        if not isinstance(p, dict):
            continue
        q = suggester.quality_from_pdc_stats(p.get("stats") or {})
        p["derived_quality"] = q
        if q is not None:
            derived += 1
    return {"profiles": profiles, "count": len(profiles),
            "requested": len(columns), "derived_quality": derived}

_PDC_DB_ENGINES = {"POSTGRES": "postgresql", "POSTGRESQL": "postgresql",
                   "MYSQL": "mysql", "MARIADB": "mysql",
                   "ORACLE": "oracle",
                   "MSSQL": "sqlserver", "SQLSERVER": "sqlserver", "SQL_SERVER": "sqlserver"}
_PDC_OBJ_TYPES = {"AWS", "S3", "AWS_S3", "MINIO"}
_ENGINE_PORTS = {"postgresql": "5432", "mysql": "3306", "oracle": "1521", "sqlserver": "1433"}

def _pdc_enc(v):
    """True when PDC handed back an ENCRYPTED value rather than a usable one.
    PDC stores credentials encrypted and returns them that way in userName /
    accessId — copying those into a connection produced a username of
    'AES/GCM/NoPadding|65536|…', so the DB said "no password supplied" and
    MinIO said "InvalidAccessKeyId" (field-caught: "the connections it adds
    are messed up"). An encrypted value is not a credential; it is noise."""
    s = str(v or "")
    return s.startswith("AES/") or ("|" in s and len(s) > 40 and " " not in s)


def _pdc_record_to_conn(rec):
    """Map a PDC data-source record to an app connection (prefill only — the public
       API never returns a usable password/secret, so the user supplies that once on
       the Connections page). Returns (conn_dict, needs, warning) or (None, None, why)."""
    dt = str(rec.get("databaseType") or "").upper()
    name = rec.get("resourceName") or rec.get("fqdnId") or "pdc-source"
    host = rec.get("host") or ""
    if dt in _PDC_DB_ENGINES:
        eng = _PDC_DB_ENGINES[dt]
        schemas = rec.get("schemaNames") or []
        cfg = {"engine": eng, "host": host,
               "port": str(rec.get("port") or _ENGINE_PORTS[eng]),
               "database": rec.get("databaseName") or "",
               "schema": (schemas[0] if schemas else ("public" if eng == "postgresql" else "")),
               "user": ("" if _pdc_enc(rec.get("userName")) else (rec.get("userName") or "")),
               "password": "",
               "ssl": False, "profile": True}
        return ({"name": name, "type": "db", "config": cfg},
                ("username and password" if not cfg["user"] else "password"),
                _reachability_warning(host))
    if dt in _PDC_OBJ_TYPES:
        endpoint = rec.get("endpoint") or ""
        cfg = {"endpoint": endpoint,
               "bucket": rec.get("container") or "",
               "access_key": ("" if _pdc_enc(rec.get("accessId") or rec.get("accessKeyID"))
                              else (rec.get("accessId") or rec.get("accessKeyID") or "")),
               "secret_key": "",
               "prefix": str(rec.get("path") or "").lstrip("/"),
               "secure": str(endpoint).lower().startswith("https"),
               "level": "file", "profile_dq": False, "content_terms": True}
        return ({"name": name, "type": "minio", "config": cfg},
                ("access key and secret key" if not cfg["access_key"] else "secret key"),
                _reachability_warning(endpoint))
    return (None, None,
            f"databaseType {dt or '(unknown)'} has no live-scan support in the app — "
            "use Harvest from PDC for this source instead")

def _reachability_warning(hostish):
    """PDC often stores container-internal names (cscu-postgres) or in-cluster
       endpoints the app host can't reach — the same remap problem the bulk loader
       solves. Flag anything that isn't obviously an IP/localhost/FQDN."""
    h = str(hostish or "")
    h = h.replace("http://", "").replace("https://", "").split(":")[0].split("/")[0]
    if not h:
        return None
    looks_reachable = (h in ("localhost", "127.0.0.1")
                       or h.replace(".", "").isdigit()          # bare IPv4
                       or "." in h)                             # FQDN-ish
    return None if looks_reachable else (
        f"host '{h}' looks container-internal — if Test Connection fails, replace it "
        "with the Docker host/VM IP and the published port (docker compose ps)")

@app.post("/api/pdc/source-to-connection")
def pdc_source_to_connection(body: dict = Body(default={})):
    """Turn a source PDC already knows into a saved app connection: fetch the full
       record over /data-sources/filter, prefill engine/host/port/db/schema/user
       (or endpoint/bucket), and save it needing only the secret. If a connection
       with the same name exists, its config is refreshed but a saved secret is
       KEPT — re-adding never wipes a working credential."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    name = (body.get("data_source_name") or "").strip()
    ds_id = (body.get("data_source_id") or "").strip() or None
    if not base or not (name or ds_id):
        return _err("base_url and data_source_name (or id) are required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        # Name is the reliable key: the ids filter wants PDC's internal ObjectId,
        # not the catalog-entity UUID the picker holds (sending a UUID 500s with
        # "Cast to ObjectId failed"). Only use ds_id when no name is available.
        rec = pdc_api.get_data_source(base, token, name=name or None,
                                      ds_id=(None if name else ds_id),
                                      version=version, verify_tls=verify)
    except Exception as e:
        msg = str(e)
        if "Cast to ObjectId" in msg:
            msg = ("PDC rejected the id (it expects an internal ObjectId) — "
                   "retry by source name; original: " + msg)
        return _err(msg, 502)
    if not rec:
        return _err(f"PDC returned no data-source record for {name or ds_id!r}", 404)
    conn, needs, warning = _pdc_record_to_conn(rec)
    if conn is None:
        return _err(warning, 400)
    conns = _load_connections()
    existing = next((c for c in conns if (c.get("name") or "").lower() == conn["name"].lower()
                     and c.get("type") == conn["type"]), None)
    kept_secret = False
    if existing:
        old_cfg = existing.get("config") or {}
        secret_field = "password" if conn["type"] == "db" else "secret_key"
        if old_cfg.get(secret_field):
            conn["config"][secret_field] = old_cfg[secret_field]
            kept_secret = True
        conn["id"] = existing.get("id")
        conns = [conn if c.get("id") == conn["id"] else c for c in conns]
    else:
        conn["id"] = uuid.uuid4().hex[:12]
        conns.append(conn)
    _save_connections(conns)
    return {"connection": conn, "needs": (None if kept_secret else needs),
            "kept_secret": kept_secret, "updated": bool(existing),
            "warning": warning}

@app.post("/api/pdc/data-sources")
def pdc_data_sources(body: dict = Body(default={})):
    """List the data-source connections already configured in PDC, so the user can
       harvest a glossary straight from the catalog (no direct DB access or secret)."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return _err("PDC base URL is required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        sources = pdc_api.list_catalog_roots(base, token, version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e), 502)
    return {"data_sources": sources, "count": len(sources)}

@app.post("/api/pdc/source-test")
def pdc_source_test(body: dict = Body(default={})):
    """Per-connection 'test': confirm the source resolves in the catalog and report
       how many entities PDC actually holds for it (COLUMN for databases, FILE for
       object stores). An ingest that reported OK but scanned an empty schema shows
       here as 0 — the check that would have caught the public-vs-cscu_core bug.
       Read-only: no jobs triggered."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    ds_id = body.get("data_source_id")
    ds_name = body.get("data_source_name")
    if not base or not (ds_id or ds_name):
        return _err("PDC base URL and a data source are required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        cols = pdc_api.filter_entities(base, token, {"types": ["COLUMN"]}, version=version,
                                       verify_tls=verify, max_pages=8)
        files = pdc_api.filter_entities(base, token, {"types": ["FILE", "OBJECT", "RESOURCE"]},
                                        version=version, verify_tls=verify, max_pages=8)
        ncol = sum(1 for e in cols if pdc_api._under_root(e, ds_id, ds_name))
        nfile = sum(1 for e in files if pdc_api._under_root(e, ds_id, ds_name))
        ok = (ncol + nfile) > 0
        if ok:
            msg = " · ".join(p for p in [("%d columns" % ncol) if ncol else "",
                                         ("%d files" % nfile) if nfile else ""] if p) + " ingested"
        else:
            msg = ("resolves in the catalog, but PDC holds no columns/files for it — the "
                   "ingest scanned nothing (check schemaNames / bucket, then re-ingest)")
        return {"ok": ok, "columns": ncol, "files": nfile, "message": msg}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, status_code=502)

@app.post("/api/pdc/terms/existing")
def pdc_terms_existing(body: dict = Body(default={})):
    """Which of these candidate terms ALREADY exist in PDC, and in which glossary.

    The same lookup Resolve does, run early. Resolve already reuses an existing
    term's id rather than minting a duplicate, so nothing was ever written twice
    - but it runs at step 4, so a steward could author a definition for a concept
    Billing already owns and only find out on Apply. This answers it during
    Review, while changing your mind is still cheap.

    Deliberately NOT scoped to one glossary: the whole point is to see across
    them. An enterprise runs many small governed glossaries, and reuse rises as
    coverage grows.
    """
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    names = [str(n).strip() for n in (body.get("names") or []) if str(n).strip()]
    # optional category fingerprinting ("be useful if the Term was also
    # checked against the Category"): terms may arrive as [{name, category}]
    # with the glossary name, and the deterministic UUID5 ids do the rest
    row_cat = {str(t.get("name") or "").strip(): str(t.get("category") or "").strip()
               for t in (body.get("terms") or []) if isinstance(t, dict)}
    names = names or [n for n in row_cat if n]
    gname = (body.get("glossary_name") or "").strip()
    if not base:
        return _err("PDC base URL is required", 400)
    if not names:
        return {"found": {}, "checked": 0, "hits": 0}
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        name_map = pdc_api.resolve_terms(base, token, names, None,
                                         version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e)[:300], 502)

    # glossaryId -> readable name, resolved once per glossary rather than per
    # term: a hundred hits in one glossary is one lookup, not a hundred.
    gloss_names, found = {}, {}
    for nm, m in (name_map or {}).items():
        if not isinstance(m, dict) or not m.get("id"):
            continue
        gid = m.get("glossaryId")
        if gid and gid not in gloss_names:
            try:
                ent = pdc_api.get_entity(base, token, gid, version=version, verify_tls=verify)
                e = ent.get("data", ent) if isinstance(ent, dict) else {}
                if isinstance(e, list):
                    e = e[0] if e else {}
                gloss_names[gid] = (e or {}).get("name") or ""
            except Exception:
                gloss_names[gid] = ""     # id still tells the steward it exists
        entry = {"id": m.get("id"), "glossaryId": gid,
                 "glossary": gloss_names.get(gid, "")}
        # Category fingerprint: term ids are UUID5(glossary, category, term),
        # so comparing PDC's id against the derivation for the ROW's category
        # detects a stale-generation import with ZERO extra API calls.
        # Field-caught: PDC held Billing Address under Customer Management
        # while the grid said Billing and Revenue — the flat IN PDC badge
        # hid it. category_ok: True = same category; False = same glossary
        # lineage, different category (pdc_category names it when it matches
        # a category on the current grid); absent = foreign glossary or
        # hand-authored id, nothing to fingerprint against.
        if gname and row_cat.get(nm):
            from engine import suggester as _sg
            expect = _sg.det_term_id(gname, row_cat[nm], nm)
            if m.get("id") == expect:
                entry["category_ok"] = True
            else:
                # the live estate returns glossaryId null from /search, so
                # lineage is proven the other way round: if the found id
                # derives from ANY category on the current grid, it is OUR
                # glossary's term under a stale category (field-caught:
                # Billing Address rode a null glossaryId and the stale badge
                # never fired)
                hit = next((c for c in sorted({v for v in row_cat.values() if v})
                            if _sg.det_term_id(gname, c, nm) == m.get("id")), "")
                if hit or (gid and gid == _sg.det_glossary_id(gname)):
                    entry["category_ok"] = False
                    entry["pdc_category"] = hit
        found[nm] = entry
    return {"found": found, "checked": len(names), "hits": len(found)}


@app.post("/api/pdc/glossary-tree-check")
def pdc_glossary_tree_check(body: dict = Body(default={})):
    """The import-side sibling of "re-profiling is additive": a PDC import
    updates matching terms in place (deterministic UUID5 ids) but never
    REMOVES categories from previous imports, so the glossary tree
    accumulates eras (field-caught: three naming generations in one tree).
    Given the glossary name and the export's category list, report what PDC
    currently holds that the export no longer carries - the folders that
    will linger after import unless deleted in PDC first."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    glossary = (body.get("glossary") or "").strip()
    cats = [str(c).strip() for c in (body.get("categories") or []) if str(c).strip()]
    if not base or not glossary:
        return _err("PDC base URL and glossary name are required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        res = pdc_api.glossary_categories(base, token, glossary,
                                          version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e)[:300], 502)
    if not res.get("exists"):
        return {"exists": False, "pdc_categories": [], "lingering": [],
                "partial": False}
    export_l = {c.lower() for c in cats}
    lingering = [c for c in res.get("categories") or [] if c.lower() not in export_l]
    return {"exists": True, "pdc_categories": res.get("categories") or [],
            "lingering": lingering, "partial": bool(res.get("partial"))}

@app.post("/api/pdc/source-config")
def pdc_source_config(body: dict = Body(default={})):
    """Return the raw stored config of a PDC data source (secrets redacted) so you can
       see exactly which databaseType / serviceType / fileSystemType / configMethod a
       working object-store source uses — the values the loader must match. Create one
       AWS S3 source by hand in the PDC UI, then inspect it here."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    name = (body.get("resource_name") or body.get("data_source_name") or "").strip()
    if not base:
        return _err("PDC base URL is required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        recs = pdc_api.list_data_sources(base, token, version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e)[:300], 502)
    # the fields that decide how PDC routes/ingests a source
    keys = ("resourceName", "databaseType", "serviceType", "fileSystemType",
            "spiVersion", "configMethod", "driverClassName", "jobClasspath",
            "endpoint", "region", "container", "path", "host", "port",
            "accessKey", "accessKeyID", "secretKey", "secretAccessKey", "noAuth")
    out = []
    for r in (recs or []):
        if name and str(r.get("resourceName", "")).strip().lower() != name.lower():
            continue
        row = {}
        for k in keys:
            v = r.get(k)
            if v in (None, "", [], {}):
                continue
            if k in ("secretKey", "secretAccessKey", "password"):
                v = "****"
            elif k in ("accessKey", "accessKeyID") and isinstance(v, str) and len(v) > 4:
                v = v[:3] + "…"
            row[k] = v
        out.append(row)
    return {"sources": out, "count": len(out)}

@app.post("/api/pdc/harvest")
def pdc_harvest(body: dict = Body(default={})):
    """Harvest a glossary straight from PDC's catalog: read the COLUMN entities PDC
       already scanned for a data source, run them through the same suggester a live
       scan uses, and overlay what PDC ALREADY governs (sensitivity/trust/terms) so
       the user can see existing work before generating. No direct DB access."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    ds_id = (body.get("data_source_id") or "").strip() or None
    ds_name = (body.get("data_source_name") or "").strip() or None
    if not base:
        return _err("PDC base URL is required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        tables, files, overlay, summary = pdc_api.harvest_from_catalog(
            base, token, ds_id=ds_id, ds_name=ds_name, version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e), 502)
    if not tables and not files:
        return _err("PDC returned no columns or files for that data source. "
                    "Confirm the source has been scanned/ingested in PDC.", 404)
    # Database columns -> term rows; object-store files -> document rows. A source is
    # one kind or the other, but harvest tolerates a mix.
    rows = suggester.suggest(tables) if tables else []
    if files:
        rows += suggester.suggest_document_files(files, summary.get("bucket") or "documents")
    # Join PDC's current governance back onto each row. Column rows key on the last two
    # dot-segments of "<db>.<table>.<column>"; file rows key on the full
    # "<bucket>/<folder>/<base>" Source_Column.
    governed = 0
    for r in rows:
        sc = str(r.get("Source_Column", "")).split(";")[0].strip()
        if "/" in sc:
            key = sc.lower()
        else:
            seg = sc.split(".")
            key = ".".join(seg[-2:]).lower() if len(seg) >= 2 else sc.lower()
        cur = overlay.get(key)
        if cur and cur.get("governed"):
            governed += 1
            r["PDC_Current"] = cur            # {sensitivity, trust, terms, governed}
    # Build the scan summary so scan_check picks the right mode: table/column counts for
    # a database harvest, an object count for a document harvest.
    scn = {"already_governed": governed, "source": summary["source"]}
    if summary["columns"]:
        scn["tables"] = summary["tables"]
        scn["columns"] = summary["columns"]
    if summary.get("files"):
        scn["objects"] = summary["files"]
    parts = []
    if summary["columns"]:
        parts.append(f"{summary['columns']} column(s) across {summary['tables']} table(s)")
    if summary.get("files"):
        parts.append(f"{summary['files']} file(s)")
    sig = (f"Harvested {' + '.join(parts)} from PDC "
           f"· {governed} already governed in PDC")

    # Build the SAME discovery payload a direct scan produces, from what PDC
    # returned — so the Schema page's per-table panels and the Files page's
    # charts work on a harvest ("would like to see the table results here…
    # all the ingest and profiling results"). Nothing extra is fetched; this
    # is the harvest reshaped.
    discovery = docs_discovery = doc_columns = None
    if tables:
        by_col = {}
        for r in rows:
            sc = str(r.get("Source_Column") or "").split(";")[0].strip()
            # the canonical parser, not a naive dot-split: a document source
            # reads "bucket/folder/file.csv.column", and grabbing seg[-2] made
            # the "table" == "csv" — so no doc row ever matched and the Files
            # profile showed confidence/PII/sensitivity all zero (field:
            # "Term confidence 0" over 53 live terms)
            el = suggester._parse_source(sc)
            if el and el.get("column_name"):
                tkey = str(el.get("table_name") or "").split("/")[-1].lower()
                by_col[(tkey, str(el["column_name"]).lower())] = r
            seg = sc.split(".")
            if len(seg) >= 2:
                by_col.setdefault((seg[-2].lower(), seg[-1].lower()), r)
        dsum = {"tables": 0, "columns": 0, "rows": 0, "pii": 0, "cde": 0,
                "pk_cols": 0, "fk_cols": 0, "classified": 0, "empty": 0,
                "sensitivity": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
                "confidence": {"High": 0, "Medium": 0, "Low": 0},
                "profiled": 0, "db_bytes": 0}
        dtabs, comp_sum, comp_n = [], 0.0, 0
        for tname, cols in tables.items():
            colout, trows = [], 0
            for c in cols:
                prof = c.get("profile") or {}
                sr = by_col.get((tname.lower(), str(c.get("column") or "").lower()), {})
                sens = sr.get("Sensitivity", "LOW")
                pii = sr.get("PII_Category", "")
                cde = sr.get("Critical_Data_Element", "No")
                conf = sr.get("Confidence", "")
                trows = max(trows, int(prof.get("rows") or 0))
                colout.append({
                    "column": c.get("column", ""), "type": c.get("type", ""),
                    "pk": bool(c.get("pk")), "fk": bool(c.get("fk")),
                    "non_null": prof.get("non_null"), "distinct": prof.get("distinct"),
                    "completeness": prof.get("completeness"),
                    "uniqueness": prof.get("uniq"),
                    "sensitivity": sens, "pii": pii, "cde": cde,
                    "kind": prof.get("kind", ""),
                    "examples": (prof.get("enum") or [])[:3],
                    "term": sr.get("Term", ""), "confidence": conf,
                    "profiled": bool(prof),
                })
                dsum["columns"] += 1
                if prof:
                    dsum["profiled"] += 1
                if pii:
                    dsum["pii"] += 1
                if str(cde).lower() == "yes":
                    dsum["cde"] += 1
                if c.get("pk"):
                    dsum["pk_cols"] += 1
                if c.get("fk"):
                    dsum["fk_cols"] += 1
                if pii or sens != "LOW":
                    dsum["classified"] += 1
                if sens in dsum["sensitivity"]:
                    dsum["sensitivity"][sens] += 1
                if conf in dsum["confidence"]:
                    dsum["confidence"][conf] += 1
                if prof.get("completeness") is not None:
                    comp_sum += float(prof["completeness"]); comp_n += 1
            dtabs.append({"name": tname, "rows": trows, "bytes": 0,
                          "empty": trows == 0, "columns": colout,
                          # what the steward scans for: how much of this table
                          # arrived with evidence, and how weak its terms are
                          "profiled_columns": sum(1 for c in colout if c["profiled"]),
                          "low_confidence": sum(1 for c in colout
                                                if str(c["confidence"]).lower() == "low")})
            dsum["tables"] += 1
            dsum["rows"] += trows
            if trows == 0:
                dsum["empty"] += 1
        dsum["avg_completeness"] = round(comp_sum / comp_n, 3) if comp_n else 0
        dsum["largest_tables"] = sorted(
            [{"name": x["name"], "rows": x["rows"], "bytes": 0} for x in dtabs],
            key=lambda x: x["rows"], reverse=True)[:5]
        # Split by KIND: a document store's "tables" are files, and their
        # column profile belongs on the Files page beside the charts — not in
        # the database view (field: "only getting column profiling for
        # unstructured", because the document harvest also overwrote it).
        doc_tabs = [x for x in dtabs if suggester._FILE_EXT.search(x["name"] or "")]
        db_tabs = [x for x in dtabs if x not in doc_tabs]

        def _sum_for(sel):
            s = {k: (0 if isinstance(v, int) else v) for k, v in dsum.items()}
            s["sensitivity"] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
            s["confidence"] = {"High": 0, "Medium": 0, "Low": 0}
            comp, n = 0.0, 0
            for x in sel:
                s["tables"] += 1
                s["rows"] += x["rows"]
                if x["rows"] == 0:
                    s["empty"] += 1
                for c in x["columns"]:
                    s["columns"] += 1
                    if c.get("profiled"):
                        s["profiled"] += 1
                    if c.get("pii"):
                        s["pii"] += 1
                    if str(c.get("cde", "")).lower() == "yes":
                        s["cde"] += 1
                    if c.get("pk"):
                        s["pk_cols"] += 1
                    if c.get("fk"):
                        s["fk_cols"] += 1
                    sv = c.get("sensitivity") or "LOW"
                    if c.get("pii") or sv != "LOW":
                        s["classified"] += 1
                    if sv in s["sensitivity"]:
                        s["sensitivity"][sv] += 1
                    cf = c.get("confidence") or ""
                    if cf in s["confidence"]:
                        s["confidence"][cf] += 1
                    if c.get("completeness") is not None:
                        comp += float(c["completeness"]); n += 1
            s["avg_completeness"] = round(comp / n, 3) if n else 0
            s["largest_tables"] = sorted(
                [{"name": x["name"], "rows": x["rows"], "bytes": 0} for x in sel],
                key=lambda x: x["rows"], reverse=True)[:5]
            return s

        src_name = summary.get("source") or "PDC"
        if db_tabs:
            discovery = {"schema": src_name, "tables": db_tabs,
                         "summary": _sum_for(db_tabs), "source": "harvest"}
        if doc_tabs:
            doc_columns = {"schema": src_name, "tables": doc_tabs,
                           "summary": _sum_for(doc_tabs), "source": "harvest"}

    if files:
        from collections import Counter as _C
        by_type, by_folder = _C(), {}
        for f in files:
            ext = (f.get("ext") or "").lower() or "(none)"
            by_type[ext] += 1
            fol = f.get("folder") or "(root)"
            # the panel labels a folder row from `name`
            b = by_folder.setdefault(fol, {"name": fol, "folder": fol, "count": 0,
                                           "files": 0, "bytes": None})
            b["count"] += 1          # the panel reads `count`
            b["files"] += 1
            if f.get("bytes") is not None:
                b["bytes"] = (b["bytes"] or 0) + int(f["bytes"])
        known = [int(f["bytes"]) for f in files if f.get("bytes") is not None]
        tot_b = sum(known) if known else None
        docs_discovery = {
            "bucket": summary.get("bucket") or "", "prefix": "",
            "summary": {"files": len(files), "bytes": tot_b,
                        "types": len(by_type), "folders": len(by_folder),
                        "avg_bytes": (int(tot_b / len(known)) if known else None)},
            "by_type": [{"ext": e, "count": n,
                         "bytes": (lambda ks: sum(ks) if ks else None)(
                             [int(f["bytes"]) for f in files
                              if ((f.get("ext") or "").lower() or "(none)") == e
                              and f.get("bytes") is not None])}
                        for e, n in by_type.most_common()],
            "by_folder": sorted(by_folder.values(), key=lambda x: -(x["bytes"] or 0)),
            "largest": sorted(({"key": f.get("rel") or f.get("base"),
                                "bytes": f.get("bytes")} for f in files),
                              key=lambda x: -(x["bytes"] or 0))[:10],
            "newest": [{"key": f.get("rel") or f.get("base"),
                        "modified": str(f.get("modified") or "")}
                       for f in sorted(files, key=lambda f: str(f.get("modified") or ""),
                                       reverse=True)[:10]],
            "include": "", "exclude": "",
            "source": "harvest",
        }
    if doc_columns:
        # the file columns PDC profiled, carried with the bucket charts
        docs_discovery = dict(docs_discovery or {"bucket": "", "prefix": "",
                                                 "summary": {}, "by_type": [],
                                                 "by_folder": [], "largest": [],
                                                 "recent": [], "source": "harvest"})
        docs_discovery["columns"] = doc_columns
    # Harvested rows grow the governed vocabulary exactly like direct scans do —
    # a harvest-only workflow (and dictionary recovery after a reseed) needs no
    # direct DB/S3 access to repopulate the pending queue.
    try:
        tagdict.accrete(rows, source="pdc")
    except Exception:
        pass
    # The scan/discovery RESULT view for this source — what PDC's own processing
    # (ingest, profiling, Data Identification, Trust Score) has already produced.
    pdc_summary = {"source": summary["source"], "tables": summary["tables"],
                   "columns": summary["columns"], "files": summary.get("files", 0),
                   **(summary.get("governance") or {})}
    return {"rows": rows, "stats": _stats(rows), "scanned": scn,
            "pdc_summary": pdc_summary,
            # the harvest reshaped as a discovery profile, so the Schema and
            # Files pages show per-table results and charts on a PDC-only path
            "discovery": discovery, "docs_discovery": docs_discovery,
            "ownership": {"signals": [sig]},
            "check": suggester.scan_check(rows, scn)}

@app.post("/api/pdc/glossary-exists")
def pdc_glossary_exists(body: dict = Body(default={})):
    """Pre-flight check: does a glossary with this name already exist in PDC? Lets the
       UI warn and offer update-vs-create instead of creating a duplicate on import."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    name = (body.get("glossary_name") or body.get("name") or "").strip()
    if not base or not name:
        return _err("PDC base URL and glossary_name are required", 400)
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        res = pdc_api.glossary_exists(base, token, name, version=version, verify_tls=verify)
    except Exception as e:
        return _err(str(e), 502)
    return res

@app.post("/api/seed-readiness")
def api_seed_readiness(body: dict = Body(default={})):
    """The glossary's detection-evidence summary, before anything is generated
    (spec backlog item 2): how many terms carry a usable seed, how many are
    mapping-only by declaration, and how many have NO usable evidence — the
    ones the Policy Generator will ask for back. Also surfaces a shape claimed
    by more than one concept, which is the 2026-08-20 eight-concepts-one-regex
    defect made visible where "Draft produced 88 patterns" read like success.
    Pure summary over the rows — nothing is decided or written here; the same
    seeds_for_row ladder the Registry and the drafter share does the reading."""
    from engine import policy_seed
    from registry import bridge
    rows = [r for r in (body or {}).get("rows", []) if isinstance(r, dict)]
    kept = [r for r in rows
            if str(r.get("Keep", "Y")).strip().upper() != "N"]
    try:
        curated = bridge._curated_seeds()
    except Exception:
        curated = {}
    pats = dicts = map_nature = 0
    no_seed = []
    shape_claims = {}
    flippable_terms, quiet_candidates = [], []
    for r in kept:
        seeds, skip, mapping = policy_seed.seeds_for_row(r, curated)
        if mapping is not None:
            # a declaration, not a failure — and a starred one is the seed
            # ladder's "the NAME is authoritative" recommendation. These two
            # lists drive the Review page's bulk-flip actions, the home the
            # flip workflow moved to when Draft policies retired (backlog 1,
            # user decision 2026-08-23).
            if mapping.get("auto_candidate"):
                flippable_terms.append(r.get("Term") or "")
            else:
                map_nature += 1
            continue
        if seeds:
            best = seeds[0]
            if best.get("type") == "pattern":
                pats += 1
                rx = (best.get("regex") or "").strip()
                if rx:
                    shape_claims.setdefault(rx, set()).add(r.get("Term") or "")
            else:
                dicts += 1
        else:
            why = skip or ""
            no_seed.append({"term": r.get("Term") or "", "why": why})
            # free-text / shapeless columns can go QUIET in place — the
            # structural reasons (table-level, document, link-expected)
            # have nothing to flip (same test the draft skip-groups used)
            if re.search(r"induce no shape|no stable shape", why):
                quiet_candidates.append(r.get("Term") or "")
    shared = [{"regex": rx, "terms": sorted(t for t in terms if t)}
              for rx, terms in sorted(shape_claims.items())
              if len({t for t in terms if t}) > 1]
    return {"terms": len(kept),
            "seeded": pats + dicts, "patterns": pats, "dictionaries": dicts,
            "mapping_only": map_nature + len(flippable_terms),
            "flippable": len(flippable_terms),
            "flippable_terms": sorted(t for t in flippable_terms if t),
            "quiet_candidates": sorted(t for t in quiet_candidates if t),
            "no_seed": len(no_seed), "no_seed_terms": no_seed[:60],
            "shared_shapes": shared}


@app.post("/api/data-elements")
def data_elements(body: dict = Body(default={})):
    """Build the term<->column Data-Element links plus their bulk-assign CSV and Trust-ready API JSON."""
    body = body or {}
    rows = body.get("rows", [])
    name = body.get("glossary_name", "Business Glossary")
    lineage = body.get("lineage_verified", True)
    rating = int(body.get("rating", 0) or 0)
    # the steward the ratings are attributed to — PDC renders stars from the
    # rating's `users` map, and the table roll-up harvests raters from the
    # columns, so without this every rating in the walk lands as 0 stars
    rater = (body.get("rater") or "").strip() or None
    qw = body.get("quality_weights") or None   # {completeness, uniqueness, validity}
    with_quality = bool(body.get("quality", True))
    policy = body.get("map_policy")   # optional selective-mapping override; None => DEFAULT_MAP_POLICY
    # the governed vocabulary gates which steward tags may stamp — the same
    # allow-list the Registry embeds for the Policy author's applyTags
    try:
        allowed = set(tagdict.governed_tags())
    except Exception:
        allowed = None
    links = suggester.data_element_links(rows, name, quality_weights=qw,
                                         with_quality=with_quality, policy=policy,
                                         allowed_tags=allowed)
    api_json = suggester.links_to_api_json(links, name, lineage, rating, rater=rater)
    rated = sum(1 for l in links if l.get("quality") is not None)
    breakdown = suggester.map_breakdown(rows, policy)
    return {"links": links, "csv": suggester.links_to_csv(links),
            "json": api_json, "count": len(links), "elements": len(api_json),
            "terms": len({l["business_term"] for l in links}),
            "tables": len({(l["schema_name"], l["table_name"]) for l in links}),
            "quality_scored": rated,
            # selective-mapping transparency: which terms were linked vs held back
            "mapped_terms": breakdown["mapped_count"],
            "skipped_terms": breakdown["skipped_count"],
            "breakdown": breakdown,
            "policy": {**suggester.DEFAULT_MAP_POLICY, **(policy or {})}}

@app.post("/api/pdc/labels-apply")
def api_pdc_labels_apply(body: dict = Body(default={})):
    """Create the steward's KEPT label keys in PDC as data labels (custom
    properties with isDataLabel=true, over /graphql - field-mapped from a
    DevTools capture + live probing). Idempotent: existing names are left
    alone and reported. Values come from the labels engine over the live
    rows, so the vocabulary written is the one the steward approved.
    Body: {base_url, token|username+password, keys: [...], rows: [...]}"""
    from engine import labels as labels_engine
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    if not base:
        return _err("PDC base URL is required", 400)
    keys = [str(k).strip() for k in (body.get("keys") or []) if str(k).strip()]
    if not keys:
        return _err("no label keys - tick the keys to keep on Govern first", 400)
    pack = {}
    try:
        with open(paths.domain_pack_path(), encoding="utf-8") as f:
            pack = json.load(f)
    except Exception:
        pack = {}
    lab = labels_engine.suggest_labels(body.get("rows") or [], pack=pack)
    vocab = lab.get("vocabulary") or {}
    descs = {k["key"]: (k.get("descriptions") or {}) for k in lab.get("keys") or []}
    try:
        token, _ = _pdc_token_and_reauth(body, base, body.get("version") or "v2",
                                         bool(body.get("verify_tls", False)))
        existing = {l["name"].strip().lower(): l
                    for l in pdc_api.list_labels(base, token,
                                                 verify_tls=bool(body.get("verify_tls", False)))}
        created, skipped, missing = [], [], []
        for k in keys:
            vals = vocab.get(k) or []
            if not vals:
                missing.append(k)      # no derived values on the current grid
                continue
            if k.lower() in existing:
                skipped.append({"key": k, "id": existing[k.lower()]["_id"],
                                "values": existing[k.lower()]["values"]})
                continue
            lid = pdc_api.create_label(base, token, k, vals,
                                       descriptions=descs.get(k) or {},
                                       verify_tls=bool(body.get("verify_tls", False)))
            created.append({"key": k, "id": lid, "values": vals})
        _receipt("labels", created=[c["key"] for c in created],
                 existing=[s["key"] for s in skipped])
        return {"created": created, "existing": skipped, "no_values": missing}
    except Exception as e:
        return _err(str(e)[:300], 502)


def _labels_stamp_impl(body, progress=None):
    """The auto-stamp flow: put label VALUES on the column entities themselves,
    driven by the reviewed grid. Assignment is NOT GraphQL (mapped live
    2026-08-17): PATCH /api/public/v3/entities/{id} with
    attributes.customProperties, replaces-wholesale — pdc_api.assign_labels
    does the read-merge-write so labels this app never derived survive.

    Per kept row: derive {key: value} from the labels engine (same evidence
    the create step used), validate each value against the family PDC
    actually holds (a hand-drifted family is reported, never guessed at),
    resolve every real source column to its entity, and stamp one merged
    assignment per entity. dry_run (default) plans and reports only."""
    from engine import labels as labels_engine
    from engine.suggester import _parse_source
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    if not base:
        raise RuntimeError("PDC base URL is required")
    keys = [str(k).strip() for k in (body.get("keys") or []) if str(k).strip()]
    if not keys:
        raise RuntimeError("no label keys - tick the keys to keep on Govern first")
    dry = bool(body.get("dry_run", True))
    verify = bool(body.get("verify_tls", False))
    version = body.get("version") or "v2"
    kept = [r for r in (body.get("rows") or []) if isinstance(r, dict)
            and str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")]
    pack = {}
    try:
        with open(paths.domain_pack_path(), encoding="utf-8") as f:
            pack = json.load(f)
    except Exception:
        pack = {}
    token, reauth = _pdc_token_and_reauth(body, base, version, verify)
    tok = {"t": token}

    def _authed(fn):
        try:
            return fn()
        except pdc_api.TokenExpired:
            if not reauth:
                raise
            tok["t"] = reauth()
            return fn()

    families = {l["name"].strip().lower(): l
                for l in _authed(lambda: pdc_api.list_labels(base, tok["t"], verify_tls=verify))}
    missing = [k for k in keys if k.lower() not in families]
    usable = [k for k in keys if k.lower() in families]

    # plan: one merged assignment per physical column, across every kept row
    # that maps to it (a term on 3 columns stamps all 3)
    plan, mismatches = {}, []
    for r in kept:
        vals = labels_engine.labels_for_row(r, usable, pack=pack)
        if not vals:
            continue
        ok = {}
        for k, v in vals.items():
            fam = families[k.lower()]
            if fam.get("values") and v not in fam["values"]:
                # the family in PDC drifted from the engine's vocabulary
                # (hand-edited values, or created before a category rename) —
                # report it; writing an ungoverned value would corrupt the axis
                mismatches.append({"term": str(r.get("Term") or ""), "key": k,
                                   "value": v, "allowed": fam["values"]})
                continue
            ok[k] = {"id": fam["_id"], "value": v}
        if not ok:
            continue
        for src in str(r.get("Source_Column") or "").split(";"):
            de = _parse_source(src.strip())
            if not de:
                continue
            ckey = (de["schema_name"], de["table_name"], de["column_name"], de["entity_type"])
            entry = plan.setdefault(ckey, {"assign": {}, "labels": {}, "terms": []})
            entry["assign"].update({a["id"]: a["value"] for a in ok.values()})
            entry["labels"].update({k: a["value"] for k, a in ok.items()})
            t = str(r.get("Term") or "").strip()
            if t and t not in entry["terms"]:
                entry["terms"].append(t)

    results, unresolved = [], []
    stamped = planned = 0
    table_cache = {}
    total = len(plan)
    for i, (ckey, entry) in enumerate(sorted(plan.items())):
        sch, tbl, col, etype = ckey
        label = ".".join(x for x in (sch, tbl, col) if x)
        if progress:
            try:
                # "plan" vs "stamp" — the dry run's counter is otherwise
                # indistinguishable from the real write in the UI, and a
                # steward who watched 155/155 tick by believed the labels
                # were stamped when nothing had been written (2026-08-23).
                progress({"phase": "plan" if dry else "stamp",
                          "done": i, "total": total, "column": label})
            except Exception:
                pass
        rec = {"type": etype, "schemaName": sch, "tableName": tbl, "columnName": col}
        row = {"column": label, "labels": dict(entry["labels"]),
               "terms": entry["terms"][:6], "status": "pending"}
        try:
            ent = _authed(lambda: pdc_api.resolve_column_entity(
                base, tok["t"], rec, version, verify, 30, table_cache))
            eid = pdc_api._eid(ent) if ent else None
            if not eid:
                row["status"] = "not-found"
                unresolved.append(label)
                results.append(row)
                continue
            row["id"] = eid
            if dry:
                row["status"] = "planned"
                planned += 1
            else:
                _authed(lambda: pdc_api.assign_labels(
                    base, tok["t"], eid,
                    [{"id": fid, "value": v} for fid, v in entry["assign"].items()],
                    verify_tls=verify))
                row["status"] = "stamped"
                stamped += 1
        except Exception as e:
            row["status"] = "error"
            row["message"] = str(e)[:300]
        results.append(row)
    if progress:
        try:
            progress({"phase": "done", "done": total, "total": total})
        except Exception:
            pass
    return {"dry_run": dry, "total_columns": total,
            "stamped": stamped, "planned": planned,
            "missing_families": missing, "mismatches": mismatches[:40],
            "unresolved": unresolved[:40], "results": results[:400]}


@app.post("/api/labels/propose-vocab")
def api_labels_propose_vocab(body: dict = Body(default={})):
    """AI-proposed label vocabulary for a family with NO scan signal —
    retention, regulatory-basis (spec backlog 4). The model PROPOSES a
    matcher-key -> value mapping from the estate's own evidence (document
    classes, categories, term names); the deterministic guardrails in
    labels.validate_vocab ground it; the steward edits and adopts (or not).
    Nothing is written here. Body: {rows, family?, model?}."""
    from engine import labels as labels_engine
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    family = (body.get("family") or "retention").strip().lower()
    if not rows:
        return _err("no rows — scan and review first, the proposal is grounded in them", 400)
    classes = sorted({labels_engine._doc_class(r) for r in rows} - {""})
    cats = sorted({str(r.get("Category") or "").strip() for r in rows} - {""})
    terms = sorted({str(r.get("Term") or "").strip() for r in rows} - {""})[:40]
    prompt = (
        f"Propose a '{family}' label vocabulary for a data-governance catalog.\n"
        "Output JSON: {\"mapping\": {<matcher>: <value>}, \"rationale\": <one sentence>}.\n"
        "Rules:\n"
        "- A matcher is a short lower-case word taken from the DOCUMENT CLASSES or\n"
        "  CATEGORIES below (plus optionally \"default\").\n"
        "- At most 8 entries and at most 6 DISTINCT values.\n"
        f"- Values are short (max 24 chars). For retention use durations like \"7y\", \"3y\".\n"
        "- Propose only what the evidence supports; this is a PROPOSAL a data steward\n"
        "  will review — do not pad.\n\n"
        f"DOCUMENT CLASSES: {', '.join(classes) or '(none)'}\n"
        f"CATEGORIES: {', '.join(cats) or '(none)'}\n"
        f"SAMPLE TERMS: {', '.join(terms) or '(none)'}\n")
    try:
        from ai import llm
        out = llm._complete_json(prompt, model=body.get("model"), timeout=120)
    except Exception:
        out = None
    if not isinstance(out, dict):
        return _err("no local model reachable — define the vocabulary by hand in the "
                    "domain pack (labels." + family + "), or configure Ollama on Settings", 503)
    mapping = out.get("mapping") if isinstance(out.get("mapping"), dict) else out
    clean, problems = labels_engine.validate_vocab(family, mapping)
    return {"family": family, "proposal": clean, "problems": problems,
            "rationale": str(out.get("rationale") or "")[:300], "used_llm": True}


@app.post("/api/labels/adopt-vocab")
def api_labels_adopt_vocab(body: dict = Body(default={})):
    """The steward's approval: write an edited vocabulary into the installed
    domain pack (labels.<family>), where the labels engine — and every future
    scan — reads it. Same guardrails as the proposal; backup taken; the AI
    never reaches this endpoint on its own. Body: {family, mapping}."""
    from engine import labels as labels_engine
    body = body or {}
    clean, problems = labels_engine.validate_vocab(body.get("family"),
                                                   body.get("mapping"))
    if not clean:
        return _err("; ".join(problems) or "nothing to adopt", 400)
    family = str(body.get("family")).strip().lower()
    import shutil
    pack = {}
    try:
        with open(paths.domain_pack_path(), encoding="utf-8") as f:
            pack = json.load(f)
    except Exception:
        pack = {}
    path = paths.domain_pack_write_path()
    backup = None
    try:
        if os.path.exists(path):
            backup = path + ".backup-" + time.strftime("%Y%m%d-%H%M%S")
            shutil.copy2(path, backup)
    except Exception:
        backup = None
    pack.setdefault("labels", {})[family] = clean
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, ensure_ascii=False)
    _receipt("labels-vocab", family=family, entries=len(clean))
    return {"applied": True, "family": family, "entries": len(clean),
            "problems": problems, "pack_path": path, "pack_backup": backup}


@app.post("/api/labels/suggest")
def api_labels_suggest(body: dict = Body(default={})):
    """Suggest PDC labels (key/value custom properties) from what the scan
    already proved — PII, sensitivity, CDE, the settled category, and any
    vocabulary your domain pack defines (e.g. retention). Labels READ
    classification; they never change it, and nothing is applied: the steward
    picks which keys to keep. Body: {rows}."""
    from engine import labels as labels_engine
    body = body or {}
    pack = {}
    try:
        with open(paths.domain_pack_path(), encoding="utf-8") as f:
            pack = json.load(f)
    except Exception:
        pack = {}
    return labels_engine.suggest_labels(body.get("rows") or [], pack=pack)


@app.post("/api/pdc/profiling-probe")
def api_pdc_profiling_probe(body: dict = Body(default={})):
    """DIAGNOSTIC: what does PDC's own profiling actually expose per column?

    The architecture question behind it: if PDC already ingested and profiled
    the estate (bulk loader), Harvest should be the primary path and the app
    should not need source credentials at all. Harvest reads entity metadata
    today — structure + governance, but NO value evidence — and value evidence
    is what mints Dictionaries, Data Patterns, DQ expectations and the
    deterministic PII/sensitivity calls. So: does profilingInfo carry
    distinct-value samples and/or induced patterns, or only aggregate stats?

    Returns the RAW profilingInfo per column (truncated) plus a capability
    verdict, so the answer is evidence, not argument.
    Body: {base_url, token|username+password, version?, verify_tls?,
           columns: ["schema.table.column", ...]} (or rows: [review rows])."""
    from sources import pdc_api
    body = body or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return _err("PDC base URL is required", 400)

    ds_id = (body.get("data_source_id") or "").strip() or None
    ds_name = (body.get("data_source_name") or "").strip() or None
    cols = [str(c).strip() for c in (body.get("columns") or []) if str(c).strip()]
    ent_ids, parent_ids, total_available = [], [], 0

    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        if not cols and (ds_id or ds_name):
            # same entry point as Harvest: pick a data source from PDC's own
            # list, and let the catalog tell us which columns it holds — no
            # hand-typed paths, no app-side grid needed
            # the same type list the client harvests with — a document
            # store's columns are not typed "COLUMN"
            ents = pdc_api.filter_entities(
                base, token, {"types": list(dict.fromkeys(pdc_api._COL_TYPES))},
                version=version, verify_tls=verify, timeout=40)
            for e in ents:
                if not pdc_api._under_root(e, ds_id, ds_name):
                    continue
                sch, tbl, col = pdc_api._split_entity_path(e)
                if tbl and col:
                    c = ".".join(x for x in (sch, tbl, col) if x)
                    if c not in cols:
                        cols.append(c)
                        eid = pdc_api._eid(e) or e.get("_id") or ""
                        if eid:
                            ent_ids.append(str(eid))
                        par = (e.get("parentId") or e.get("parentID")
                               or (e.get("parentIds") or [None])[0])
                        if par and str(par) not in parent_ids:
                            parent_ids.append(str(par))
                total_available += 1
                if len(cols) >= int(body.get("sample_columns") or 24):
                    break
        if not cols:                   # last resort: the grid's kept columns
            for r in (body.get("rows") or []):
                if not isinstance(r, dict):
                    continue
                sc = str(r.get("Source_Column") or "").split(";")[0].strip()
                if sc.count(".") >= 2 and sc not in cols:
                    cols.append(sc)
                if len(cols) >= 6:
                    break
        if not cols:
            return _err("no columns to probe — pick a PDC data source (List data "
                        "sources in Harvest), or pass columns:[schema.table.column]", 400)

        specs = []
        for c in cols[:32]:
            p = c.split(".")
            specs.append({"schemaName": p[0] if len(p) >= 3 else "",
                          "tableName": p[-2], "columnName": p[-1]})
        prof = pdc_api.pdc_profile_for_columns(base, token, specs, version=version,
                                               verify_tls=verify)
        # DIRECT attempt: ask for profiling by the entities' OWN ids. The
        # name-based path resolves a parent TABLE by name, which for a
        # document store means matching a filename — a failure there is
        # indistinguishable from "PDC has no profiling", so remove the
        # variable rather than argue about it (field: 8 document columns
        # resolved, profiling empty).
        direct = {}
        if ent_ids and not prof:
            for filt in ({"ids": ent_ids[:12]}, {"parentIds": parent_ids[:12]}):
                if not list(filt.values())[0]:
                    continue
                try:
                    items = pdc_api.filter_profiling_info(base, token, filt,
                                                          version=version,
                                                          verify_tls=verify)
                except Exception:
                    items = []
                for it in items or []:
                    pinfo = it.get("profilingInfo") or it.get("profiling") or {}
                    if pinfo:
                        direct[str(it.get("name") or it.get("_id"))] = {
                            "stats": pinfo.get("stats") or pinfo.get("statistics") or {},
                            "sampling": pinfo.get("sampling") or pinfo.get("samples"),
                            "patterns": pinfo.get("patternAnalysis") or pinfo.get("patterns"),
                            "_via": "ids" if "ids" in filt else "parentIds",
                        }
                if direct:
                    break
        prof = prof or direct
    except Exception as e:
        return _err(str(e)[:300], 502)

    def _dig(o, want, depth=0):
        """Any key whose name suggests distinct VALUES (not just counts)."""
        found = []
        if depth > 4:
            return found
        if isinstance(o, dict):
            for k, v in o.items():
                if want in k.lower() and v not in (None, "", [], {}):
                    found.append(k)
                found += _dig(v, want, depth + 1)
        elif isinstance(o, list):
            for v in o[:5]:
                found += _dig(v, want, depth + 1)
        return found

    out, caps = {}, {"stats": False, "values": False, "patterns": False}
    for key, p in (prof or {}).items():
        raw = json.dumps(p, default=str)
        caps["stats"] = caps["stats"] or bool(p.get("stats"))
        caps["patterns"] = caps["patterns"] or bool(p.get("patterns"))
        val_keys = sorted(set(_dig(p, "value") + _dig(p, "distinct") + _dig(p, "sample")))
        caps["values"] = caps["values"] or bool(p.get("sampling")) or bool(val_keys)
        out[key] = {"keys": sorted(p.keys()),
                    "value_like_keys": val_keys,
                    "raw": raw[:4000] + ("…(truncated)" if len(raw) > 4000 else "")}

    # ---- labels / custom properties -------------------------------------
    # The standing open question ("we haven't looked at labels in PDC… could
    # be where we set a label in the API call"). Labels are key-value custom
    # properties on an item; if they ride an entity's attributes, the same
    # PATCH Apply already uses can write them. Dump one entity's real
    # attribute keys so the answer is the catalog's own payload.
    labels = {"attribute_keys": [], "label_like_keys": [], "sample": ""}
    file_sample = ""   # a raw FILE entity, so size/date questions are settled
                       # by payload, not alias guessing (field: 0 B everywhere,
                       # every date identical = the catalog's ingest stamp)
    try:
        probe_ents = pdc_api.filter_entities(
            base, token, {"types": list(dict.fromkeys(pdc_api._COL_TYPES))},
            version=version, verify_tls=verify, timeout=30)
        ent = next((e for e in probe_ents
                    if (not (ds_id or ds_name)) or pdc_api._under_root(e, ds_id, ds_name)), None)
        if ent:
            attrs = pdc_api._attrs_of(ent) or {}
            labels["attribute_keys"] = sorted(attrs.keys())[:60]
            labels["entity_keys"] = sorted(ent.keys())[:40]
            labels["label_like_keys"] = sorted(
                k for k in list(attrs.keys()) + list(ent.keys())
                if any(w in k.lower() for w in
                       ("label", "customprop", "custom_prop", "property",
                        "userdefined", "udp", "annotation")))
            blob = json.dumps(ent, default=str)
            labels["sample"] = blob[:3000] + ("…(truncated)" if len(blob) > 3000 else "")
        # a DEDICATED FILE query: hunting for a FILE inside the page-capped
        # all-types listing missed them entirely (field: probe ran on 1.37.7,
        # no dump appeared) — ask for FILEs alone and the pages are all files
        fents = pdc_api.filter_entities(base, token, {"types": ["FILE"]},
                                        version=version, verify_tls=verify,
                                        timeout=30)
        fent = next((e for e in fents
                     if (not (ds_id or ds_name))
                     or pdc_api._under_root(e, ds_id, ds_name)), None)
        if fent is None and fents:
            fent = fents[0]          # any file beats none; the dump says which
        if fent:
            blob = json.dumps(fent, default=str)
            file_sample = blob[:3000] + ("…(truncated)" if len(blob) > 3000 else "")
    except Exception as e:
        labels["error"] = str(e)[:200]

    if not cols:
        verdict = ("No COLUMN entities found under this source — nothing to ask "
                   "about. An object store holds FILE entities, and its columns "
                   "only exist once PDC's Data Discovery has run; try a database "
                   "source, or run discovery on this store first.")
    elif not out:
        verdict = (f"Resolved {len(cols)} column(s) from the catalog "
                   f"({', '.join(cols[:3])}…) but PDC returned no profilingInfo "
                   "for them — so the columns exist and are NOT profiled (or "
                   "profiling is not exposed on this PDC version). That is a "
                   "different finding from 'no columns found'.")
    elif caps["values"] or caps["patterns"]:
        verdict = ("PDC exposes value-level detail — harvest CAN fill the profile "
                   "dict from the catalog's own work, so a PDC-only path is viable. "
                   "Map the keys listed above onto profile{enum, pattern, kind}.")
    elif caps["stats"]:
        verdict = ("PDC exposes aggregate stats only (no distinct values, no "
                   "patterns) — harvest can fill DQ baselines but NOT dictionaries "
                   "or Data Patterns; those still need a value pass.")
    else:
        verdict = "profilingInfo came back empty for every probed column."
    lab_verdict = ("Label-like keys are present on the entity — labels/custom "
                   "properties can very likely be written with the same "
                   "attributes PATCH Apply already uses."
                   if labels.get("label_like_keys") else
                   "No label-like key on this entity's payload — labels are "
                   "probably a separate resource (or need an item-type "
                   "definition first); capture one 'assign label' call in "
                   "DevTools to see the real endpoint.")
    return {"probed": list(out.keys()), "capabilities": caps,
            # what the catalog gave us to work with, so "absent" can never be
            # confused with "never asked" (field-caught on a document store:
            # three absent chips that actually meant no columns were resolved)
            "columns_found": len(cols), "columns_sample": cols[:8],
            # the id/parentId route answers for EVERY column under the parents,
            # not just the ones we asked about — report both so the chip cannot
            # claim a sample size the listing plainly exceeds (field-caught)
            "profiled_returned": len(out),
            "sampled": True, "probe_via": next(
                (v.get("_via") for v in (prof or {}).values()
                 if isinstance(v, dict) and v.get("_via")), "table-name"),
            "columns": out, "verdict": verdict,
            "labels": labels, "labels_verdict": lab_verdict,
            "file_sample": file_sample}


# Set by /api/factory-reset; the save endpoint refuses writes for a few
# seconds afterwards so an in-flight autosave cannot resurrect the estate.
_FACTORY_RESET_AT = 0.0


@app.post("/api/factory-reset")
def api_factory_reset(body: dict = Body(default={})):
    """Delete ALL app state from inside the app — the guaranteed clean slate.
    Exists because the installer's delete-app-data checkbox demonstrably
    failed to wipe on an upgrade (field: three stale files survived and
    conflated two estates); until that is reproduced and fixed, the app
    owns its own zero. Body: {confirm: "RESET"}. app.log is kept — the
    black box should outlive the wipe. Close and relaunch afterwards so
    the seeds (domain pack, defaults) regenerate."""
    if (body or {}).get("confirm") != "RESET":
        return _err('pass {"confirm": "RESET"} to wipe all app data', 400)
    global _FACTORY_RESET_AT
    _FACTORY_RESET_AT = time.time()
    import shutil
    deleted = []
    targets = [PEOPLE_FILE, CONN_FILE, SETTINGS_FILE, GLOSS_FILE,
               RECEIPTS_FILE, paths.state_path("tag_dictionary.json",
                                               "GLOSSARY_TAG_DICTIONARY"),
               paths.state_path("audit_log.json", "GLOSSARY_AUDIT_LOG"),
               paths.state_path("domain_pack.json", "GLOSSARY_DOMAIN_PACK")]
    for p in targets:
        try:
            if p and os.path.exists(p):
                os.unlink(p)
                deleted.append(os.path.basename(p))
        except Exception:
            pass
    try:
        if os.path.isdir(REGISTRY_DIR):
            shutil.rmtree(REGISTRY_DIR, ignore_errors=True)
            deleted.append("registries/")
    except Exception:
        pass
    # drop the in-memory caches so the running process forgets too
    try:
        with tagdict._LOCK:
            tagdict._DICT = None
            tagdict._COMPILED = tagdict._COMPILED_KEY = None
    except Exception:
        pass
    logging.getLogger("client").error(
        "factory-reset: %s deleted", ", ".join(deleted) or "nothing")
    # Verify by re-listing the state dir, not by trusting deleted[]: the
    # field failure was files that CAME BACK between the wipe and relaunch.
    # app.log (the black box) and exports/ (the user's own downloads) are
    # expected survivors, everything else is a resurrection to surface.
    remaining = []
    try:
        for name in sorted(os.listdir(paths.state_dir())):
            if name == "app.log" or name.startswith("app.log."):
                continue
            if name in ("exports",):
                continue
            remaining.append(name)
    except Exception:
        pass
    return {"deleted": deleted, "remaining": remaining,
            "note": "Close and relaunch the app — seeds and defaults "
                    "regenerate on startup. app.log was kept."}


@app.post("/api/estate-report")
def api_estate_report(body: dict = Body(default={})):
    """The estate's closing summary + the Policy-Generator handoff contract,
    verified from facts on disk (registry, pack, receipts) — never from
    ticked boxes. Body: {rows, glossary_name}. Returns {stats, contract,
    receipts, ready, missing}."""
    from collections import Counter
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
    name = (body.get("glossary_name") or "").strip() or "Business Glossary"

    def _is_kept(r):
        return str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")
    kept = [r for r in rows if _is_kept(r)]
    cats = Counter((str(r.get("Category") or "").strip() or "—") for r in kept)
    sens = Counter((str(r.get("Sensitivity") or "LOW").upper()) for r in kept)
    conf = Counter((str(r.get("Confidence") or "").strip() or "—") for r in kept)
    tags = Counter(t.strip() for r in kept
                   for t in str(r.get("Suggested_Tags") or "").split(";") if t.strip())
    stats = {
        "glossary": name,
        "terms_kept": len(kept), "terms_dropped": len(rows) - len(kept),
        "categories": [{"name": c, "count": n} for c, n in cats.most_common()],
        "sensitivity": dict(sens), "confidence": dict(conf),
        "tags_top": [{"tag": t, "count": n} for t, n in tags.most_common(10)],
        "pii": sum(1 for r in kept if str(r.get("PII_Category") or "").strip()),
        "cde": sum(1 for r in kept
                   if str(r.get("Critical_Data_Element") or "").lower() == "yes"),
        "enriched": sum(1 for r in kept
                        if str(r.get("LLM_Enriched") or "").lower() in ("yes", "true")),
        "table_terms": sum(1 for r in kept
                           if not str(r.get("Source_Column") or "").strip()),
        "with_evidence": sum(1 for r in kept
                             if (r.get("Value_Pattern") or r.get("Enum_Values")
                                 or r.get("Value_Kind"))),
    }

    # ---- data-rich sections ("the report can be alot better and more data
    # rich, with detailed explanations") — every number derives from the same
    # rows and artifacts, no new scans; each block is optional-on-failure so
    # a partial estate still reports.

    # Detection coverage: the drafter's own buckets, deterministic (no AI)
    try:
        from engine import policy_draft
        d = policy_draft.draft_from_rows(rows, glossary_name=name)
        seed_counts = Counter((p.get("seed") or "profiled")
                              for p in d.get("patterns") or [])
        skip_groups = Counter()
        for sk in d.get("skipped") or []:
            why = str(sk.get("why") or "other")
            skip_groups[why.split(" — ")[0].split(" - ")[0][:90]] += 1
        stats["detection"] = {
            "patterns": len(d.get("patterns") or []),
            "patterns_by_seed": dict(seed_counts),
            "dictionaries": len(d.get("dictionaries") or []),
            "mapping_only": len(d.get("mapping_only") or []),
            "skipped": len(d.get("skipped") or []),
            "skip_groups": [{"reason": k, "count": n}
                            for k, n in skip_groups.most_common()],
        }
    except Exception:
        stats["detection"] = None

    # Evidence depth: what profiling actually induced, facet by facet
    def _has(r, k):
        return bool(str(r.get(k) or "").strip())
    stats["evidence"] = {
        "pattern": sum(1 for r in kept if _has(r, "Value_Pattern")),
        "enum": sum(1 for r in kept if _has(r, "Enum_Values")),
        "kind": sum(1 for r in kept if _has(r, "Value_Kind")),
        "range": sum(1 for r in kept if _has(r, "Value_Range")),
        "signature": sum(1 for r in kept if _has(r, "Value_Signature")),
        "none": sum(1 for r in kept
                    if not any(_has(r, k) for k in
                               ("Value_Pattern", "Enum_Values", "Value_Kind",
                                "Value_Range", "Value_Signature"))),
    }

    # Label families + PII tiers: the same engine the Apply labels card uses
    try:
        from engine import labels as labels_engine
        pack = {}
        try:
            with open(paths.domain_pack_path(), encoding="utf-8") as f:
                pack = json.load(f)
        except Exception:
            pack = {}
        lab = labels_engine.suggest_labels(kept, pack=pack)
        stats["labels"] = [{"key": k["key"], "why": k.get("why", ""),
                            "values": [{"value": v["value"], "count": v["count"]}
                                       for v in k.get("values") or []]}
                           for k in lab.get("keys") or []]
    except Exception:
        stats["labels"] = []

    # Sources footprint
    try:
        import re
        from engine.suggester import _parse_source
        schemas, tabs = set(), set()
        col_count = doc_count = 0
        for r in kept:
            for c0 in str(r.get("Source_Column") or "").split(";"):
                c0 = c0.strip()
                if not c0:
                    continue
                de = _parse_source(c0)
                if not de:
                    continue
                col_count += 1
                schemas.add(de.get("schema_name") or "—")
                tabs.add((de.get("schema_name"), de.get("table_name")))
                if "/" in c0 or re.search(
                        r"\.(csv|jsonl?|txt|pdf|docx?|xlsx?)(\.|$)", c0, re.I):
                    doc_count += 1
        stats["sources"] = {"schemas": len(schemas), "tables": len(tabs),
                           "columns": col_count, "document_columns": doc_count}
    except Exception:
        stats["sources"] = None

    # DQ readiness: the checks the bundle derives + the scan's quality scores
    qual = []
    for r in kept:
        try:
            q = int(float(r.get("Suggested_Quality")))
            if q:
                qual.append(q)
        except (TypeError, ValueError):
            pass
    stats["dq"] = {
        "format_checks": stats["evidence"]["pattern"],
        "allowed_value_checks": stats["evidence"]["enum"],
        "range_checks": stats["evidence"]["range"],
        "quality_scored": len(qual),
        "quality_mean": (round(sum(qual) / len(qual)) if qual else None),
        "quality_low": sum(1 for q in qual if q < 70),
    }

    # Governance coverage (ReportPage sends the workspace governance block)
    gov = body.get("governance") or {}
    stats["governance"] = {
        "present": bool(gov),
        "default_steward": bool(str(((gov.get("default") or {})
                                     .get("businessSteward")) or "").strip()),
        "category_overrides": sum(
            1 for o in (gov.get("categories") or {}).values()
            if str((o or {}).get("businessSteward") or "").strip()),
        "label_keys": [str(k) for k in (gov.get("labelKeys") or [])],
    }

    receipts = _read_json(RECEIPTS_FILE, {})
    saved_at = ""
    for g in (_load_gloss() or {}).values():
        if (g.get("name") == name or g.get("glossary_name") == name):
            saved_at = max(saved_at, str(g.get("savedAt") or ""))

    contract, missing = [], []
    def item(key, label, ok, detail, path=None, at=None, stale=False):
        contract.append({"key": key, "label": label, "ok": bool(ok),
                         "detail": detail, "path": path, "at": at,
                         "stale": bool(stale)})
        if not ok:
            missing.append(label)

    # Registry — the Policy Generator's primary input
    rp = _registry_path(name)
    reg = _read_json(rp, None)
    gid = suggester.det_glossary_id(name)
    if not isinstance(reg, dict) or not reg:
        item("registry", "Registry", False,
             "not written yet — Generate JSONL authors it", path=rp)
    elif str(reg.get("glossary_id") or "") != gid:
        item("registry", "Registry", False,
             "belongs to a DIFFERENT glossary (id mismatch) — Generate again "
             "under this name", path=rp)
    else:
        item("registry", "Registry", True,
             f"{len(reg.get('concepts') or [])} concept(s), physical model + "
             "tag vocabulary present", path=rp)

    # Domain pack — installed as this app's pack
    pk = receipts.get("pack") or {}
    pack_path = None
    try:
        pack_path = paths.domain_pack_write_path()
    except Exception:
        pass
    pack_on_disk = bool(pack_path and os.path.exists(pack_path))
    if pk.get("applied") and pack_on_disk:
        item("pack", "Domain pack (installed)", True,
             f"{pk.get('learned', 0)} learned addition(s) installed",
             path=pk.get("path") or pack_path, at=pk.get("at"))
    else:
        item("pack", "Domain pack (installed)", False,
             "generate the pack on the Dictionary page and Install it as "
             "this app's pack (the flywheel turn)", path=pack_path)

    # Receipts-backed artifacts
    gen = receipts.get("generate") or {}
    gen_ok = bool(gen) and gen.get("glossary") == name
    gen_stale = bool(gen_ok and saved_at and str(gen.get("at", "")) < saved_at)
    item("jsonl", "Import JSONL", gen_ok,
         (f"{gen.get('lines', 0)} line(s) — {gen.get('categories', 0)} "
          f"categories, {gen.get('terms', 0)} terms"
          + (" · REGENERATE: the review was saved after this export"
             if gen_stale else "")) if gen_ok
         else "not generated yet (Apply page → Generate JSONL)",
         at=gen.get("at"), stale=gen_stale)

    # (the Drafted-policies bundle left the contract when the Draft surface
    # retired, 2026-08-23 — every decision it carried travels inside the
    # Registry, which is already the contract's first artifact)

    rs = receipts.get("resolve") or {}
    item("resolve", "Resolve receipt", bool(rs),
         "term ids stamped" if rs else
         "not run yet (import the JSONL in PDC first)", at=rs.get("at"))
    ap = receipts.get("apply") or {}
    item("apply", "Apply receipt", bool(ap),
         ("written to PDC" if ap else
          "no non-dry-run apply recorded yet"), at=ap.get("at"))

    stale_any = any(c.get("stale") for c in contract)
    ready = not missing and not stale_any
    return {"stats": stats, "receipts": receipts, "contract": contract,
            "saved_at": saved_at, "ready": ready, "missing": missing,
            "verdict": ("READY for the Policy Generator — every artifact "
                        "present and current." if ready else
                        (f"{len(missing)} artifact(s) missing" if missing else "")
                        + (" · stale artifact(s) need regenerating"
                           if stale_any else ""))}


@app.post("/api/generate")
def generate(body: dict = Body(default={})):
    """Generate import-ready glossary JSONL (and summary stats) from review rows."""
    body = body or {}
    rows = body.get("rows", [])
    name = body.get("glossary_name", "Business Glossary (Suggested)")
    governance = body.get("governance") or None
    recs = suggester.to_jsonl_records(rows, name, governance=governance)
    jsonl = suggester.records_to_jsonl(recs)
    kept = sum(1 for r in rows if str(r.get("Keep", "Y")).lower() in ("y", "yes", "true", "1"))
    # Author the Registry from the final reviewed rows (export time = latest version).
    # The standalone Policy Generator reads this to build the Data Identification policy.
    registry_path = None
    try:
        import registry as _registry
        registry_path = _registry_path(name)
        _registry.build_and_save_registry(rows, name, registry_path,
                                          glossary_id=suggester.det_glossary_id(name))
    except Exception:
        registry_path = None  # never let Registry authoring break the export
    check = suggester.glossary_build_check(rows, recs, name)
    # ---- generation archive: every export lands in the app's own history,
    # timestamped, and the download carries the SAME name — so "which file
    # did I import?" is always answerable (field-caught: a pre-edit
    # "glossary-import (n).jsonl" from Downloads went into PDC and the
    # recategorisation silently didn't carry)
    import glob as _glob
    import time as _time
    slug = suggester._slug(name)
    archived, generations = None, []
    try:
        exp_dir = os.path.join(paths.state_dir(), "exports", slug)
        os.makedirs(exp_dir, exist_ok=True)
        archived = _time.strftime("%Y%m%d-%H%M%S") + "-glossary-import.jsonl"
        # newline="" — the archive must be byte-identical to the download
        # (Windows text mode would rewrite \n as \r\n)
        with open(os.path.join(exp_dir, archived), "w", encoding="utf-8", newline="") as f:
            f.write(jsonl)
        files = sorted((os.path.basename(p) for p in
                        _glob.glob(os.path.join(exp_dir, "*-glossary-import.jsonl"))),
                       reverse=True)
        for old in files[20:]:                      # keep the last 20 generations
            try:
                os.remove(os.path.join(exp_dir, old))
            except OSError:
                pass
        generations = files[:5]
    except Exception:
        archived = None                             # never let archiving break the export
    _receipt("generate", glossary=name, lines=len(recs), kept=kept,
             categories=sum(1 for r in recs if r["type"] == "category"),
             terms=sum(1 for r in recs if r["type"] == "term"),
             registry=registry_path, check_tone=check.get("tone"))
    return {"jsonl": jsonl,
            "registry": registry_path,
            "check": check,
            "archived": archived, "generations": generations, "slug": slug,
            "stats": {"glossary": name, "lines": len(recs),
                      "categories": sum(1 for r in recs if r["type"] == "category"),
                      "terms": sum(1 for r in recs if r["type"] == "term"),
                      "kept": kept, "dropped": len(rows) - kept}}


@app.get("/api/exports/{gslug}/{fname}")
def export_generation_download(gslug: str, fname: str):
    """Download one archived generation. Names are basenames by construction;
    anything path-like is refused."""
    if any(ch in gslug + fname for ch in ("/", "\\", "..")):
        return _err("bad name", 400)
    path = os.path.join(paths.state_dir(), "exports", gslug, fname)
    if not os.path.isfile(path):
        return _err("no such generation", 404)
    with open(path, "rb") as f:
        data = f.read()
    return Response(data, media_type="application/x-ndjson",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})

# --------------------------------------------------------------------------- #
#  Start/poll job endpoints (additive — the forward path for the React UI).
#
#  The SSE/NDJSON streaming endpoints above are kept byte-compatible for the
#  current vanilla-JS UI; these run the SAME pipelines in a daemon worker
#  thread and expose them as {job} -> poll GET /api/jobs/{id}, the pattern
#  proven by Migration Copilot's /translate/start + /translate/status.
# --------------------------------------------------------------------------- #
_JOBS = {}
_JOB_EVENT_CAP = 2000     # bound memory: a job keeps at most this many events

def _start_job(kind, runner):
    """Mint a job, run `runner(job)` in a daemon thread, return {"job": id}.
       The runner mutates the job dict in place (single writer per job); the
       poll handler reads it. Jobs live for the process lifetime."""
    job_id = uuid.uuid4().hex[:12]
    job = {"id": job_id, "kind": kind, "status": "running",
           "done": 0, "total": 0, "phase": "", "detail": "",
           "events": [], "result": None}
    _JOBS[job_id] = job

    def _run():
        try:
            runner(job)
            if job["status"] == "running":
                job["status"] = "done"
        except Exception as e:
            job["status"] = "error"
            job["detail"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"job": job_id}

def _job_progress(job):
    """A progress callback that folds {phase, done, total, ...} events into the
       job's counters and bounded event log."""
    def _cb(ev):
        if isinstance(ev, dict):
            if ev.get("done") is not None:
                job["done"] = ev["done"]
            if ev.get("total") is not None:
                job["total"] = ev["total"]
            if ev.get("phase"):
                job["phase"] = ev["phase"]
            if len(job["events"]) < _JOB_EVENT_CAP:
                job["events"].append(ev)
    return _cb

@app.get("/api/jobs/{job_id}")
def api_job_poll(job_id: str):
    """Poll a background job started via /api/jobs/*. Returns the live job dict:
       {status: running|done|error, done, total, phase, detail, events, result}.
       Underscore keys are server-side payloads (a stored zip is bytes — not
       JSON) and never travel in the poll."""
    job = _JOBS.get(job_id)
    if job is None:
        return _err("unknown job", 404)
    return {k: v for k, v in job.items() if not k.startswith("_")}

@app.post("/api/jobs/resolve-terms")
def api_job_resolve_terms(body: dict = Body(default={})):
    """Job twin of /api/resolve-terms-stream: starts the resolve-and-stamp
       pipeline in the background and returns {job}; poll /api/jobs/{id} for
       per-term progress and the final resolve report in `result`."""
    body = body or {}
    def _runner(job):
        res = _resolve_terms_impl(body, progress=_job_progress(job))
        job["result"] = res
        _receipt("resolve", **{k: v for k, v in (res or {}).items()
                               if isinstance(v, (int, str))
                               and not isinstance(v, bool)
                               and k in ("resolved", "unresolved", "total",
                                         "stamped", "glossary")})
    return _start_job("resolve-terms", _runner)

@app.post("/api/jobs/apply-to-pdc")
def api_job_apply_to_pdc(body: dict = Body(default={})):
    """Job twin of /api/apply-to-pdc-stream: starts the merge+PATCH pipeline in
       the background and returns {job}; poll /api/jobs/{id} for per-column
       progress and the final apply report in `result`."""
    body = body or {}
    def _runner(job):
        res = _apply_to_pdc_impl(body, progress=_job_progress(job))
        job["result"] = res
        # dry runs leave no receipt — the report must reflect real writes
        if not body.get("dry_run", True):
            _receipt("apply", **{k: v for k, v in (res or {}).items()
                                 if isinstance(v, (int, str))
                                 and not isinstance(v, bool)
                                 and k in ("resolved", "written", "not_found",
                                           "tables_rated", "rated", "total",
                                           "trust")})
    return _start_job("apply-to-pdc", _runner)

@app.post("/api/jobs/bulk-load")
def api_job_bulk_load(body: dict = Body(default={})):
    """Job twin of /api/pdc/bulk-load: runs the same per-row create/ingest loop
       in the background; each NDJSON event lands in the job's `events`, row
       counters in done/total, and the final `done` event in `result`."""
    body = body or {}
    def _runner(job):
        for ev in _bulk_load_events(body):
            if len(job["events"]) < _JOB_EVENT_CAP:
                job["events"].append(ev)
            if ev.get("event") == "row":
                job["done"] = ev.get("index", job["done"])
                job["total"] = ev.get("total", job["total"])
            elif ev.get("event") == "start":
                job["total"] = ev.get("total", 0)
            elif ev.get("event") == "done":
                job["result"] = ev
            elif ev.get("event") == "error":
                job["status"] = "error"
                job["detail"] = ev.get("message", "")
    return _start_job("bulk-load", _runner)

@app.post("/api/jobs/labels-stamp")
def api_job_labels_stamp(body: dict = Body(default={})):
    """Stamp label values onto column entities from the reviewed grid (the
       assignment wire: PATCH entities attributes.customProperties, read-
       merge-write). dry_run (default true) resolves and plans without
       writing; poll /api/jobs/{id} for per-column progress and the report."""
    body = body or {}
    def _runner(job):
        res = _labels_stamp_impl(body, progress=_job_progress(job))
        job["result"] = res
        if not body.get("dry_run", True):
            _receipt("labels-stamp", stamped=res.get("stamped", 0),
                     columns=res.get("total_columns", 0),
                     unresolved=len(res.get("unresolved") or []))
    return _start_job("labels-stamp", _runner)


@app.post("/api/jobs/ai-categories")
def api_job_ai_categories(body: dict = Body(default={})):
    """Job twin of /api/ai-categories. The schema-wide call runs for minutes
       on a big grid, and the app renders only the active page - so browsing
       away unmounted Review and the response had nobody to receive it
       ("state is not held if i browse other pages? back to 0"). As a job the
       model keeps working server-side; Review re-attaches on mount and the
       proposals land whenever it finishes."""
    body = body or {}
    def _runner(job):
        job["detail"] = "one call over the whole schema graph"
        job["result"] = _ai_categories_run(body)
    return _start_job("ai-categories", _runner)


@app.post("/api/jobs/recommend-resolutions")
def api_job_recommend_resolutions(body: dict = Body(default={})):
    """Job twin of /api/recommend-resolutions: the per-group adjudication ran
       behind a silent "Advising…" (field: "need some feedback also on AI
       advise for deduplicating"). Poll /api/jobs/{id} — phase walks
       evidence → probe → adjudicate (done/total + the group just judged via
       `detail`); `result` is the same payload the sync route returns."""
    body = body or {}
    def _runner(job):
        cb = _job_progress(job)
        def _p(ev):
            if isinstance(ev, dict) and ev.get("detail"):
                job["detail"] = ev["detail"]
            if isinstance(ev, dict) and ev.get("group"):
                job["detail"] = ev["group"]
            cb(ev)
        job["result"] = _recommend_resolutions_run(body, progress=_p)
    return _start_job("recommend-resolutions", _runner)

@app.post("/api/jobs/pull-model")
def api_job_pull_model(body: dict = Body(default={})):
    """Job twin of /api/pull-model: pulls an Ollama model in the background;
       poll /api/jobs/{id} — the latest progress event carries
       {phase, status, completed, total, percent}."""
    model = (body or {}).get("model") or None
    def _runner(job):
        last = None
        for ev in llm.pull_stream(model):
            last = ev
            job["phase"] = ev.get("phase", "")
            if ev.get("total"):
                job["total"] = ev["total"]
                job["done"] = ev.get("completed") or 0
            if len(job["events"]) < _JOB_EVENT_CAP:
                job["events"].append(ev)
        job["result"] = last
        if last and last.get("phase") == "error":
            job["status"] = "error"
            job["detail"] = last.get("status", "")
    return _start_job("pull-model", _runner)

# --------------------------------------------------------------------------- #
#  Static assets - mounted last so every /api/* route above wins. The SPA in
#  frontend/dist owns "/" and everything under it.
# --------------------------------------------------------------------------- #
class _UiStatic(StaticFiles):
    """Serve the SPA with the only cache policy that survives an upgrade.

    Vite content-hashes every bundle, so `/assets/index-<hash>.js` can be cached
    forever — a new build simply has a new name. But `index.html` is the file
    that POINTS at the current hash, and StaticFiles sends it with no
    Cache-Control at all. With no policy the browser falls back to *heuristic*
    caching and keeps serving yesterday's index, which loads yesterday's bundle:
    the app upgrades on disk and the user still sees the old UI, with no clue
    why, until they know to hard-reload. That is a support call after every
    release.

    `no-cache` does not mean "do not cache" — it means "revalidate before use",
    so the ETag / 304 path is unaffected and the file is re-sent only when it
    actually changed.
    """
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        # StaticFiles normpath()s the request path, so on Windows this arrives as
        # "assets\index-<hash>.js" — normalise before matching or the immutable
        # policy silently never applies on the platform the app ships on.
        if path.replace("\\", "/").startswith("assets/"):
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            resp.headers["Cache-Control"] = "no-cache"
        return resp


_UI_DIST = os.path.join(os.path.dirname(HERE), "frontend", "dist")
if os.path.isdir(_UI_DIST):
    app.mount("/", _UiStatic(directory=_UI_DIST, html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "5000")))
