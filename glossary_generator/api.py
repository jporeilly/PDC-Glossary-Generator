"""
api.py — FastAPI backend for the Glossary Suggester.

The FastAPI port of the old Flask app.py: same /api contract route-for-route
(the vanilla-JS UI in templates/ + static/ runs unchanged against it), plus
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
import threading
import queue as _queue_mod
import uuid

from fastapi import FastAPI, Body, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

import suggester
import tagdict
import audit
import similarity
import policy_draft
import defqa
import packgen
import llm
import llm_detect
import dbconn
import seed_sample

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

templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))

DEFAULT_DDL = os.environ.get("GLOSSARY_DDL", "/mnt/user-data/uploads/01-schema-and-data.sql")
PEOPLE_FILE = os.environ.get("GLOSSARY_PEOPLE", os.path.join(HERE, "people.json"))
# Optional scenario seed roster (e.g. the CSCU people that ship with the credit-union
# domain pack). Copied into the live PEOPLE_FILE once, only when that file is missing or
# its roster is empty — so a fresh /data volume (Docker) or fresh checkout (run.sh) gets
# the seeded roster, but live edits are never overwritten. Unset = generic empty roster.
PEOPLE_SEED = os.environ.get("GLOSSARY_PEOPLE_SEED", "")
CONN_FILE = os.environ.get("GLOSSARY_CONNECTIONS", os.path.join(HERE, "connections.json"))
SETTINGS_FILE = os.environ.get("GLOSSARY_SETTINGS", os.path.join(HERE, "settings.json"))
GLOSS_FILE = os.environ.get("GLOSSARY_GLOSSARIES", os.path.join(HERE, "glossaries.json"))
# Registry artifacts written at export time (consumed by the standalone Policy Generator).
REGISTRY_DIR = os.environ.get("GLOSSARY_REGISTRY_DIR", os.path.join(HERE, "registries"))

def _registry_path(glossary_name):
    """Path of the Registry file for a glossary, keyed by its deterministic id so the
       export step and the resolve step touch the same versioned file."""
    return os.path.join(REGISTRY_DIR, f"registry.{suggester.det_glossary_id(glossary_name)}.json")

DEFAULT_SETTINGS = {"theme": "light",
                    "model": os.environ.get("LLM_MODEL", "llama3.2:3b"),
                    "compute": "auto",
                    "glossary_name": "Business Glossary (Suggested)", "show_help": True,
                    "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/"),
                    "llm_timeout": float(os.environ.get("LLM_TIMEOUT", "30")),
                    "company": os.environ.get("GLOSSARY_COMPANY", "your organization"),
                    "llm_workers": llm._clampint(os.environ.get("LLM_WORKERS", "4"), 4, 1, 16),
                    "llm_batch": llm._clampint(os.environ.get("LLM_BATCH", "6"), 6, 1, 20)}

def _read_json(path, default):
    """Read and JSON-parse `path`, returning `default` when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _write_json(path, data):
    """Serialise `data` to `path` as pretty-printed JSON, atomically.
       Writes to a temp file in the same directory then os.replace()s it into
       place, so a crash mid-write can never truncate or corrupt the target
       (e.g. people.json / settings.json)."""
    import tempfile
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
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
    """Serve the single-page application shell — the React build when it exists
    (frontend/dist, built by the installer), else the legacy Jinja shell."""
    dist_index = os.path.join(os.path.dirname(HERE), "frontend", "dist", "index.html")
    if os.path.isfile(dist_index):
        return FileResponse(dist_index)
    # v busts browser caches for /static/*.css|js on every release — a stale
    # cached script against new endpoints is the VM's classic failure mode
    return templates.TemplateResponse(request, "index.html", {"v": APP_VERSION})

# Brand favicon — an inline SVG (teal→blue rounded tile with a "G" monogram), served
# for both /favicon.svg and the browser's automatic /favicon.ico probe, so neither
# 404s and no binary asset has to ship.
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
    '<stop offset="0" stop-color="#1C7293"/><stop offset="1" stop-color="#065A82"/>'
    '</linearGradient></defs>'
    '<rect width="32" height="32" rx="7" fill="url(#g)"/>'
    '<text x="16" y="23" font-family="Calibri,\'Segoe UI\',Arial,sans-serif" '
    'font-size="21" font-weight="700" fill="#fff" text-anchor="middle">G</text>'
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
        "paths": {"ddl": DEFAULT_DDL, "people": PEOPLE_FILE, "connections": CONN_FILE,
                  "settings": SETTINGS_FILE, "glossaries": GLOSS_FILE},
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
    import audit as _audit
    files = [(SETTINGS_FILE, "settings.json"),
             (CONN_FILE, "connections.json"),
             (GLOSS_FILE, "glossaries.json"),
             (PEOPLE_FILE, "people.json"),
             (tagdict.DICT_FILE, "tag_dictionary.json"),
             (_audit.AUDIT_FILE, "audit_log.json"),
             (os.environ.get("GLOSSARY_DOMAIN_PACK") or os.path.join(HERE, "domain_pack.json"),
              "domain_pack.json")]
    rdir = os.path.join(HERE, "registries")
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
            dest = os.path.join(HERE, "registries", os.path.basename(base))
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
# Whitelisted on purpose — runtime state (people.json, settings.json, secrets) is
# never served. This is a teaching tool: the learner can read exactly what runs.
# Keys are the stable names the UI shows; pdc_api/* keys resolve to the shared
# pdc_client package at the repo root (extracted in 1.9.0).
_SOURCE_WHITELIST = {
    "api.py":          "FastAPI backend — every /api/* endpoint and how it dispatches.",
    "suggester.py":    "Scan + term suggestion: introspection, profiling, JSONL build.",
    "pdc_api/core.py":     "PDC public-API client: transport, auth, response helpers.",
    "pdc_api/entities.py": "PDC public-API client: entity filter/resolve + catalog harvest.",
    "pdc_api/terms.py":    "PDC public-API client: term resolution and id stamping.",
    "pdc_api/jobs.py":     "PDC public-API client: jobs (trust score, discovery, profiling).",
    "pdc_api/apply.py":    "PDC public-API client: merge + PATCH write-back.",
    "pdc_api/bulkload.py": "PDC public-API client: bulk data-source loader.",
    "dbconn.py":       "Database connection + driver handling for the live scan.",
    "llm.py":          "Local Ollama client used for definition/purpose enrichment.",
    "llm_detect.py":   "Host/GPU detection and Ollama model recommendation.",
    "build_roster.py": "Helper to build a people roster.",
    "cli_suggester.py":"Command-line entry point for the suggester.",
    "seed_sample.py":  "Seeds a sample dataset into a schema for demos.",
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
               "level": "file", "profile_dq": False}
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
    import pdc_api
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
              "has_discovery": bool(v.get("discovery"))}
             for k, v in g.items()]
    items.sort(key=lambda x: x.get("savedAt") or "", reverse=True)
    return {"glossaries": items}

@app.post("/api/glossaries")
def save_glossary(body: dict = Body(default={})):
    """Save (or overwrite) a named glossary of review rows."""
    import datetime
    body = body or {}
    try:
        g = _load_gloss(strict=True)
    except Exception as e:
        return _err("glossary store unreadable (%s) — refusing to save over it; "
                    "retry in a moment or check %s" % (e, GLOSS_FILE), 503)
    gid = body.get("id") or uuid.uuid4().hex[:12]
    body["id"] = gid
    body["savedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
    g[gid] = body
    _save_gloss(g)
    return {"id": gid, "savedAt": body["savedAt"], "name": body.get("name")}

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
       (Ollama URL / model / timeout) to the running client immediately."""
    s = _load_settings(); s.update(body or {})
    _write_json(SETTINGS_FILE, s)
    _apply_llm_settings(s)
    return s

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
    key = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + filename
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

@app.post("/api/seed")
def seed(body: dict = Body(default={})):
    """Seed the PostgreSQL schema with demo data (optionally only into empty tables)."""
    body = body or {}
    cfg = body.get("conn", {})
    rows = int(body.get("rows", 200))
    only_empty = body.get("only_empty", True)
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
                files = suggester.harvest_files(cfg, profile_dq=profile_dq)
                rows = suggester.suggest_document_files(files, bucket)
                try: tagdict.accrete(rows, source="minio")
                except Exception: pass
                folders = sorted({f["folder"] for f in files})
                scored = sum(1 for f in files if f.get("qdims"))
                sig = (f"{len(files)} leaf file(s) across {len(folders)} folder(s); "
                       "metadata applies per file")
                if profile_dq:
                    sig += f" · Data Quality computed from content for {scored} file(s)"
                scn = {"objects": len(files), "folders": len(folders), "dq_scored": scored}
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

@app.post("/api/enrich")
def enrich(body: dict = Body(default={})):
    """LLM-enrich the definitions/purposes of the supplied rows via local Ollama."""
    body = body or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]  # 1.5.6: guard null rows
    only_low = bool(body.get("only_low_confidence", False))
    model = body.get("model") or None
    compute = body.get("compute") or None
    rows, counts = llm.enrich_rows(rows, only_low_confidence=only_low, model=model, compute=compute)
    return {"rows": rows, "enriched": counts,
            "definitions": counts["definitions"], "purposes": counts["purposes"],
            "names": counts.get("names", 0),
            "stats": _stats(rows), "llm": llm.status(model)}

@app.post("/api/ai-suggest")
def ai_suggest(body: dict = Body(default={})):
    """Evidence-grounded AI pass over review rows: the local model proposes term /
       category / governed tags / sensitivity from the SCAN EVIDENCE (profiled value
       signatures, induced regexes, reference values), applied under guardrails —
       tags governed-only, sensitivity tighten-only, term as a suggestion chip."""
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
    rows, counts, used_llm = llm.suggest_terms_rows(
        rows, allow_tags=allow, categories=cats,
        only_low_confidence=only_low, model=model, compute=compute)
    # Guard-rail: PII_Category is authoritative from the SCAN, never a free guess.
    # Re-assert the scan classifier for un-profiled columns so a bad value (an
    # import, a legacy scan, or any agent) can't survive — e.g. an ssn mislabeled
    # PERSONAL_NAME becomes GOVERNMENT_ID, an id column's spurious ADDRESS_INFO is
    # cleared. Surfaces as a proposal pill (PII_Category is a watched field), so
    # the steward still applies it. Runs deterministically, LLM or not.
    pii_fixed = 0
    for r in rows:
        g = suggester.guard_pii_row(r)
        if g != (r.get("PII_Category") or "").strip():
            r["PII_Category"] = g
            pii_fixed += 1
    if pii_fixed:
        counts["pii"] = pii_fixed
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
    import pdc_api
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
    import pdc_api
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
                registry_backfilled = _registry.backfill_term_ids(_rp, name_map)
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
    import pdc_api
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
    import pdc_api
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
    import pdc_api, io, csv
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
    Body: {rows, conn?, ai?, model?, compute?}."""
    body = body or {}
    rows = body.get("rows") or []
    groups = similarity.group_rows(rows)
    probed = 0
    probes_by_name = {}

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
    if body.get("ai"):
        fields = ("Term", "Category", "Definition", "Source_Column", "Value_Signature",
                  "Value_Pattern", "Enum_Values", "PII_Category")
        ambiguous = [{"name": r["name"],
                      "members": [{f: m.get(f, "") for f in fields}
                                  for m in groups[r["name"]]]}
                     for r in out if r["band"] != "high" or not r["action"]]
        if ambiguous:
            verdicts, used_llm = llm.adjudicate_groups(
                ambiguous, model=body.get("model"), compute=body.get("compute"))
            for r in out:
                v = verdicts.get(r["name"])
                if v:
                    r.update(action=v["action"], reason=v["reason"],
                             band="review", source="ai")
    out.sort(key=lambda x: (x["band"] != "high", -x["count"]))
    return {"groups": out, "probed": probed, "used_llm": used_llm}

@app.post("/api/draft-policies")
def api_draft_policies(body: dict = Body(default={})):
    """The Policy Generator's first mile: draft PDC Data Identification rules from
    the scan's detection seeds — an induced value regex becomes a Data Pattern,
    a profiled reference list becomes a Dictionary (+ values CSV), in the exact
    JSON shapes the Technical Track teaches. Deterministic core; with ai=true the
    LLM agent polishes each rule's column-name regex and tag pick (guard-railed:
    regex must compile, tags stay governed). format=zip streams the bundle.
    Body: {rows, glossary_name?, prefix?, ai?, model?, compute?, format?}."""
    body = body or {}
    rows = body.get("rows") or []
    gname = body.get("glossary_name") or "Business Glossary"
    gov = sorted(tagdict.governed_tags())
    hints, used_llm = {}, False
    if body.get("ai"):
        concepts = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            term = (r.get("Term") or "").strip()
            vp = (r.get("Value_Pattern") or "").strip()
            ev = (r.get("Enum_Values") or "").strip()
            if term and (vp or ";" in ev):
                concepts.append({"term": term,
                                 "columns": r.get("Source_Column", ""),
                                 "evidence": vp or ("values: " + ev[:120])})
        if concepts:
            hints, used_llm = llm.policy_hints_rows(
                concepts, allow_tags=gov, model=body.get("model"),
                compute=body.get("compute"))
    draft = policy_draft.draft_from_rows(rows, glossary_name=gname,
                                         prefix=body.get("prefix"),
                                         hints=hints, governed_tags=gov)
    if (body.get("format") or "").lower() == "zip":
        data = policy_draft.to_zip_bytes(draft)
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition":
                                 "attachment; filename=drafted-policies.zip"})
    return {"patterns": [{"filename": p["filename"], "term": p["term"],
                          "seed": p.get("seed", "profiled"),
                          "name": p["rule"][0]["name"]} for p in draft["patterns"]],
            "dictionaries": [{"filename": d["filename"], "term": d["term"],
                              "seed": d.get("seed", "profiled"),
                              "name": d["rule"][0]["name"],
                              "values": d["values_filename"]} for d in draft["dictionaries"]],
            "skipped": draft["skipped"], "used_llm": used_llm}

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
        path = os.environ.get("GLOSSARY_DOMAIN_PACK") or os.path.join(HERE, "domain_pack.json")
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
        path = os.environ.get("GLOSSARY_DOMAIN_PACK") or os.path.join(HERE, "domain_pack.json")
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
    import pdc_api, io, csv
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
    import pdc_api
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
    import pdc_api
    base = (body.get("base_url") or body.get("base") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    opts = body.get("options") or {}
    do_test = bool(opts.get("test", False))   # no-op: no confirmed public test job
    do_ingest = bool(opts.get("ingest", True))
    wait = bool(opts.get("wait", True))
    replace_existing = bool(opts.get("replace_existing", False))
    internal_scan = bool(opts.get("internal_scan", False))
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
                                        internal_scan=internal_scan)
        except pdc_api.TokenExpired:
            if reauth:
                try:
                    token = reauth()
                    rec = pdc_api.bulk_load_one(base, token, row, version=version,
                                                verify_tls=verify, do_test=do_test,
                                                do_ingest=do_ingest, wait=wait,
                                                replace_existing=replace_existing,
                                                internal_scan=internal_scan)
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
    import pdc_api
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
    import pdc_api
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
        scope_ids, labels = pdc_api.resolve_document_scope(
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
    import pdc_api
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
    import pdc_api
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
    import pdc_api
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
    return {"profiles": profiles, "count": len(profiles),
            "requested": len(columns)}

_PDC_DB_ENGINES = {"POSTGRES": "postgresql", "POSTGRESQL": "postgresql",
                   "MYSQL": "mysql", "MARIADB": "mysql",
                   "ORACLE": "oracle",
                   "MSSQL": "sqlserver", "SQLSERVER": "sqlserver", "SQL_SERVER": "sqlserver"}
_PDC_OBJ_TYPES = {"AWS", "S3", "AWS_S3", "MINIO"}
_ENGINE_PORTS = {"postgresql": "5432", "mysql": "3306", "oracle": "1521", "sqlserver": "1433"}

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
               "user": rec.get("userName") or "", "password": "",
               "ssl": False, "profile": True}
        return ({"name": name, "type": "db", "config": cfg}, "password",
                _reachability_warning(host))
    if dt in _PDC_OBJ_TYPES:
        endpoint = rec.get("endpoint") or ""
        cfg = {"endpoint": endpoint,
               "bucket": rec.get("container") or "",
               "access_key": rec.get("accessId") or rec.get("accessKeyID") or "",
               "secret_key": "",
               "prefix": str(rec.get("path") or "").lstrip("/"),
               "secure": str(endpoint).lower().startswith("https"),
               "level": "file", "profile_dq": False}
        return ({"name": name, "type": "minio", "config": cfg}, "secret key",
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
    import pdc_api
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
    import pdc_api
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
    import pdc_api
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

@app.post("/api/pdc/source-config")
def pdc_source_config(body: dict = Body(default={})):
    """Return the raw stored config of a PDC data source (secrets redacted) so you can
       see exactly which databaseType / serviceType / fileSystemType / configMethod a
       working object-store source uses — the values the loader must match. Create one
       AWS S3 source by hand in the PDC UI, then inspect it here."""
    import pdc_api
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
    import pdc_api
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
            "ownership": {"signals": [sig]},
            "check": suggester.scan_check(rows, scn)}

@app.post("/api/pdc/glossary-exists")
def pdc_glossary_exists(body: dict = Body(default={})):
    """Pre-flight check: does a glossary with this name already exist in PDC? Lets the
       UI warn and offer update-vs-create instead of creating a duplicate on import."""
    import pdc_api
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

@app.post("/api/data-elements")
def data_elements(body: dict = Body(default={})):
    """Build the term<->column Data-Element links plus their bulk-assign CSV and Trust-ready API JSON."""
    body = body or {}
    rows = body.get("rows", [])
    name = body.get("glossary_name", "Business Glossary")
    lineage = body.get("lineage_verified", True)
    rating = int(body.get("rating", 0) or 0)
    qw = body.get("quality_weights") or None   # {completeness, uniqueness, validity}
    with_quality = bool(body.get("quality", True))
    policy = body.get("map_policy")   # optional selective-mapping override; None => DEFAULT_MAP_POLICY
    links = suggester.data_element_links(rows, name, quality_weights=qw,
                                         with_quality=with_quality, policy=policy)
    api_json = suggester.links_to_api_json(links, name, lineage, rating)
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
    return {"jsonl": jsonl,
            "registry": registry_path,
            "check": suggester.glossary_build_check(rows, recs, name),
            "stats": {"glossary": name, "lines": len(recs),
                      "categories": sum(1 for r in recs if r["type"] == "category"),
                      "terms": sum(1 for r in recs if r["type"] == "term"),
                      "kept": kept, "dropped": len(rows) - kept}}

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
       {status: running|done|error, done, total, phase, detail, events, result}."""
    job = _JOBS.get(job_id)
    if job is None:
        return _err("unknown job", 404)
    return job

@app.post("/api/jobs/resolve-terms")
def api_job_resolve_terms(body: dict = Body(default={})):
    """Job twin of /api/resolve-terms-stream: starts the resolve-and-stamp
       pipeline in the background and returns {job}; poll /api/jobs/{id} for
       per-term progress and the final resolve report in `result`."""
    body = body or {}
    def _runner(job):
        job["result"] = _resolve_terms_impl(body, progress=_job_progress(job))
    return _start_job("resolve-terms", _runner)

@app.post("/api/jobs/apply-to-pdc")
def api_job_apply_to_pdc(body: dict = Body(default={})):
    """Job twin of /api/apply-to-pdc-stream: starts the merge+PATCH pipeline in
       the background and returns {job}; poll /api/jobs/{id} for per-column
       progress and the final apply report in `result`."""
    body = body or {}
    def _runner(job):
        job["result"] = _apply_to_pdc_impl(body, progress=_job_progress(job))
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
#  Static assets — mounted last so every /api/* route above wins. The current
#  UI is the Jinja shell at "/" + /static; when the React build lands
#  (frontend/dist), it takes over "/" automatically.
# --------------------------------------------------------------------------- #
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")

_UI_DIST = os.path.join(os.path.dirname(HERE), "frontend", "dist")
if os.path.isdir(_UI_DIST):
    app.mount("/", StaticFiles(directory=_UI_DIST, html=True), name="ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"),
                port=int(os.environ.get("PORT", "5000")))
