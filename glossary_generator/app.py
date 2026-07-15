"""
app.py - Flask backend for the Glossary Suggester.

Endpoints:
  GET  /                 -> the review UI
  GET  /api/llm-status   -> {online, backend, model, ...}
  POST /api/scan         -> {rows:[...], stats:{...}}   (heuristic suggestion)
  POST /api/enrich       -> {rows:[...], enriched:N}    (LLM pass, fallback-safe)
  POST /api/ai-suggest   -> {rows:[...], updated:{...}}  (evidence-grounded AI term/tag pass)
  POST /api/generate     -> {jsonl:"...", stats:{...}}  (import-ready JSONL)

Run:  python app.py   (defaults to http://127.0.0.1:5000)
"""
import os, io, json, uuid, urllib.request, urllib.parse, urllib.error
from collections import Counter
from flask import Flask, request, jsonify, render_template, Response

HERE = os.path.dirname(__file__)

def _load_dotenv(path=None):
    """Minimal, dependency-free .env loader. Reads KEY=VALUE lines from a .env
       file beside app.py (or $GLOSSARY_ENV) and sets them in os.environ WITHOUT
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
import dbconn
import seed_sample

app = Flask(__name__)

def _app_version():
    """Single source of truth for the app version: the VERSION file beside app.py,
       falling back to the literal below if it's missing."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return "1.5.1"

APP_VERSION = _app_version()

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
    return {"terms": len(rows),
            "categories": len({r.get("Category", "") for r in rows}),
            "confidence": dict(Counter(r.get("Confidence", "") for r in rows)),
            "sensitivity": dict(Counter(r.get("Sensitivity", "") for r in rows)),
            "pii": sum(1 for r in rows if r.get("PII_Category")),
            "enriched": sum(1 for r in rows if r.get("LLM_Enriched") == "Yes")}

@app.get("/")
def index():
    """Serve the single-page application shell."""
    return render_template("index.html")

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

@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon():
    """Return the brand favicon as SVG (modern browsers render SVG favicons fine)."""
    return Response(FAVICON_SVG, mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})

@app.get("/health")
def health():
    """Liveness + dependency probe. Always 200 (the process is up); the body reports
       Ollama reachability so an orchestrator never kills the app just because the
       optional LLM enrichment backend is momentarily down."""
    s = llm.status()
    return jsonify({
        "status": "ok",
        "service": "glossary-suggester",
        "version": APP_VERSION,
        "ollama": {"online": s.get("online", False),
                   "model": s.get("model"),
                   "model_present": s.get("model_present", False)},
    })

@app.get("/api/version")
def app_version():
    """Return the running app version."""
    return jsonify({"version": APP_VERSION, "service": "glossary-generator"})

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
    return jsonify({"version": APP_VERSION, "releases": releases})

_SECRET_HINT = ("KEY", "TOKEN", "SECRET", "PASS", "PWD")

@app.get("/config")
def show_config():
    """Effective runtime configuration, with anything secret-looking masked.
       Handy for confirming env wiring inside a container."""
    def mask(name, val):
        return "***" if (val and any(h in name.upper() for h in _SECRET_HINT)) else val
    env = {k: mask(k, v) for k, v in os.environ.items()
           if k.startswith(("GLOSSARY_", "LLM_", "OLLAMA_", "HOST", "PORT"))}
    return jsonify({
        "version": APP_VERSION,
        "paths": {"ddl": DEFAULT_DDL, "people": PEOPLE_FILE, "connections": CONN_FILE,
                  "settings": SETTINGS_FILE, "glossaries": GLOSS_FILE},
        "ollama_url": llm.OLLAMA_URL,
        "model_default": DEFAULT_SETTINGS.get("model"),
        "env": env,
    })

@app.get("/api/llm-status")
def llm_status():
    """Report local Ollama reachability and the currently selected model."""
    model = request.args.get("model")
    return jsonify(llm.status(model))

@app.get("/api/models")
def models():
    """List the models available from the local Ollama install."""
    return jsonify({"models": llm.list_models()})

@app.post("/api/pull-model")
def pull_model():
    """Stream model-download progress (NDJSON) from the user's local Ollama."""
    body = request.get_json(force=True) or {}
    model = body.get("model") or None
    def gen():
        """Yield NDJSON model-download progress events streamed from Ollama."""
        for ev in llm.pull_stream(model):
            yield json.dumps(ev) + "\n"
    return Response(gen(), mimetype="application/x-ndjson")

@app.get("/api/drivers")
def drivers():
    """Report which optional database / object-store drivers are installed."""
    return jsonify({"drivers": dbconn.driver_status()})

# Source files this app will expose for transparency (the "Under the hood" viewer).
# Whitelisted on purpose — runtime state (people.json, settings.json, secrets) is
# never served. This is a teaching tool: the learner can read exactly what runs.
_SOURCE_WHITELIST = {
    "app.py":          "Flask backend — every /api/* endpoint and how it dispatches.",
    "suggester.py":    "Scan + term suggestion: introspection, profiling, JSONL build.",
    "pdc_api.py":      "PDC public-API client: auth, search, filter, PATCH, trust, bulk data-source loader.",
    "dbconn.py":       "Database connection + driver handling for the live scan.",
    "llm.py":          "Local Ollama client used for definition/purpose enrichment.",
    "build_roster.py": "Helper to build a people roster.",
    "cli_suggester.py":"Command-line entry point for the suggester.",
    "seed_sample.py":  "Seeds a sample dataset into a schema for demos.",
}

@app.get("/api/source")
def get_source():
    """Return the text of one whitelisted source file (transparency viewer)."""
    import os
    f = (request.args.get("file") or "").strip()
    if f == "":
        return jsonify({"files": [{"file": k, "note": v} for k, v in _SOURCE_WHITELIST.items()]})
    if f not in _SOURCE_WHITELIST:
        return jsonify({"error": "that file is not exposed"}), 404
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
        with open(path, "r", encoding="utf-8") as fh:
            content = fh.read()
        return jsonify({"file": f, "note": _SOURCE_WHITELIST[f],
                        "content": content, "lines": content.count("\n") + 1})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.get("/api/people")
def people():
    """Return the saved people roster."""
    return jsonify({"people": _load_people()})

@app.post("/api/people")
def save_people():
    """Persist the people roster supplied by the client."""
    body = request.get_json(force=True) or {}
    people = body.get("people", [])
    _save_people(people)
    return jsonify({"people": people, "saved": True})

@app.post("/api/keycloak-users")
def keycloak_users():
    """Fetch the user roster live from Keycloak's Admin API. Accepts either a bearer
       token, or username/password (admin-cli password grant). Returns roster rows.

       PDC fronts Keycloak at <server>/keycloak, so base_url is e.g.
       'https://host/keycloak'. The admin token comes from the 'master' realm by
       default (where the Keycloak admin user lives), while users are listed from
       the target 'realm' (e.g. 'pdc'). Override the admin realm via auth_realm.

       verify_tls=false (the default) skips certificate verification — the
       equivalent of curl -k — so a self-signed lab cert doesn't block the fetch."""
    import ssl
    b = request.get_json(force=True) or {}
    base = (b.get("base_url") or "").rstrip("/")
    realm = (b.get("realm") or "").strip()
    token = (b.get("token") or "").strip()
    if not base or not realm:
        return jsonify({"ok": False, "message": "base_url and realm are required"})
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
                return jsonify({"ok": False, "message": "Could not obtain admin token "
                                f"from realm '{auth_realm}'. Check the admin username/"
                                "password and that the admin realm is correct."})
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
        return jsonify({"ok": True, "people": roster, "count": len(roster),
                        "saved": bool(b.get("save")), "expertise_preserved": carried})
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        hint = ""
        if e.code in (401, 403):
            hint = " — the admin token lacks rights to list users in this realm, " \
                   "or the credentials/admin realm are wrong."
        return jsonify({"ok": False, "message": f"Keycloak fetch failed: HTTP {e.code}{hint} {detail}"})
    except Exception as e:
        msg = str(e)
        if "CERTIFICATE_VERIFY_FAILED" in msg or "self-signed" in msg or "self signed" in msg:
            msg += " — untick 'Verify TLS' to bypass the self-signed certificate."
        return jsonify({"ok": False, "message": f"Keycloak fetch failed: {msg}"})

@app.get("/api/connections")
def get_connections():
    """Return the saved data-source connections."""
    return jsonify({"connections": _load_connections()})

@app.post("/api/connections")
def save_connection():
    """Add or update a saved data-source connection."""
    c = request.get_json(force=True) or {}
    conns = _load_connections()
    if not c.get("id"):
        c["id"] = uuid.uuid4().hex[:12]
        conns.append(c)
    else:
        conns = [c if x.get("id") == c["id"] else x for x in conns]
        if not any(x.get("id") == c["id"] for x in conns):
            conns.append(c)
    _save_connections(conns)
    return jsonify({"connection": c, "connections": conns})

@app.delete("/api/connections/<cid>")
def delete_connection(cid):
    """Delete a saved connection by id."""
    conns = [x for x in _load_connections() if x.get("id") != cid]
    _save_connections(conns)
    return jsonify({"connections": conns})

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
def import_connections_csv():
    """Import the bulk-loader CSV into the app's OWN connections (used by Schema, Files,
       Test and live scan) — the same CSV you register in PDC, so you never re-enter the
       100+ by hand. Upserts by name.

       Body: {csv|rows, preview?, only?}. preview=true returns the candidate list
       (parsed, not saved) so the UI can let the user tick which to import. only=[names]
       imports just those; omit to import all."""
    import pdc_api
    body = request.get_json(force=True, silent=True) or {}
    rows = body.get("rows")
    if not rows and body.get("csv"):
        try:
            rows = pdc_api.parse_csv_rows(body["csv"])
        except Exception as e:
            return jsonify({"error": "could not parse CSV: %s" % e}), 400
    rows = rows or []
    if not rows:
        return jsonify({"error": "no rows — provide 'csv' or 'rows'"}), 400

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
        return jsonify({"candidates": candidates,
                        "count": sum(1 for c in candidates if c["ok"])})

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
    return jsonify({"connections": conns, "added": added, "updated": updated,
                    "skipped": [c["reason"] for c in candidates if not c["ok"]]})

@app.get("/api/settings")
def get_settings():
    """Return the current settings."""
    return jsonify(_load_settings())

def _load_gloss():
    """Load the saved-glossary store (maps id -> {name, rows})."""
    return _read_json(GLOSS_FILE, {"glossaries": {}}).get("glossaries", {})

def _save_gloss(g):
    """Persist the saved-glossary store."""
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
    return jsonify({"glossaries": items})

@app.post("/api/glossaries")
def save_glossary():
    """Save (or overwrite) a named glossary of review rows."""
    import datetime
    body = request.get_json(force=True) or {}
    g = _load_gloss()
    gid = body.get("id") or uuid.uuid4().hex[:12]
    body["id"] = gid
    body["savedAt"] = datetime.datetime.now().isoformat(timespec="seconds")
    g[gid] = body
    _save_gloss(g)
    return jsonify({"id": gid, "savedAt": body["savedAt"], "name": body.get("name")})

@app.get("/api/glossaries/<gid>")
def get_glossary(gid):
    """Return one saved glossary's rows by id."""
    g = _load_gloss()
    if gid not in g:
        return jsonify({"error": "not found"}), 404
    return jsonify(g[gid])

@app.delete("/api/glossaries/<gid>")
def delete_glossary(gid):
    """Delete a saved glossary by id."""
    g = _load_gloss(); g.pop(gid, None); _save_gloss(g)
    return jsonify({"ok": True})

@app.post("/api/settings")
def save_settings():
    """Persist the settings supplied by the client, and apply any LLM config change
       (Ollama URL / model / timeout) to the running client immediately."""
    s = _load_settings(); s.update(request.get_json(force=True) or {})
    _write_json(SETTINGS_FILE, s)
    _apply_llm_settings(s)
    return jsonify(s)

@app.post("/api/test-connection")
def test_connection():
    """Test a database connection without running a full scan."""
    cfg = (request.get_json(force=True) or {}).get("conn", {})
    return jsonify(dbconn.test_connection(cfg))

@app.post("/api/test-minio")
def test_minio():
    """Test a MinIO/S3 connection (bucket reachability + whether object tagging works)."""
    cfg = (request.get_json(force=True) or {}).get("minio", {})
    return jsonify(suggester.test_minio(cfg))

@app.post("/api/list-objects")
def list_objects_route():
    """Browse a MinIO/S3 bucket one folder level at a time (folders + files)."""
    body = request.get_json(force=True) or {}
    cfg = body.get("minio") or {}
    if not (cfg.get("bucket") or "").strip():
        return jsonify({"error": "No bucket specified on this connection."}), 400
    try:
        return jsonify(suggester.list_objects(cfg, body.get("prefix", "")))
    except Exception as e:
        return jsonify({"error": f"Could not list objects: {e}"}), 400

@app.post("/api/object-bytes")
def object_bytes_route():
    """Stream a whole object (PDF/image) so the browser can render it inline. Creds
       stay in the POST body; the client turns the response into a blob URL."""
    from flask import Response
    body = request.get_json(force=True) or {}
    cfg = body.get("minio") or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"error": "No object key supplied."}), 400
    try:
        data, ctype = suggester.get_object_bytes_full(cfg, key)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    resp = Response(data, mimetype=ctype or "application/octet-stream")
    leaf = key.rsplit("/", 1)[-1].replace('"', "")
    resp.headers["Content-Disposition"] = f'inline; filename="{leaf}"'
    resp.headers["Content-Length"] = str(len(data))
    return resp

@app.post("/api/object")
def object_route():
    """Metadata, tags and a short text preview for one object."""
    body = request.get_json(force=True) or {}
    cfg = body.get("minio") or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"error": "No object key supplied."}), 400
    try:
        return jsonify(suggester.object_detail(cfg, key))
    except Exception as e:
        return jsonify({"error": f"Could not read object: {e}"}), 400

@app.post("/api/load-glossary")
def load_glossary():
    """Parse an uploaded glossary (JSONL/CSV) into review rows."""
    body = request.get_json(force=True) or {}
    text = body.get("glossary", "")
    try:
        rows, report = suggester.glossary_to_rows(text)
    except Exception as e:
        return jsonify({"error": f"load failed: {e}"}), 400
    return jsonify({"rows": rows, "stats": _stats(rows), "report": report})

@app.post("/api/enhance-glossary")
def enhance_glossary():
    """Enrich existing review rows from an imported glossary, optionally appending missing terms."""
    body = request.get_json(force=True) or {}
    rows = body.get("rows", [])
    text = body.get("glossary", "")
    append = body.get("append_missing", True)
    try:
        rows2, report = suggester.enhance_from_glossary(rows, text, append)
    except Exception as e:
        return jsonify({"error": f"enhance failed: {e}"}), 400
    return jsonify({"rows": rows2, "stats": _stats(rows2), "report": report})

@app.post("/api/seed")
def seed():
    """Seed the PostgreSQL schema with demo data (optionally only into empty tables)."""
    body = request.get_json(force=True) or {}
    cfg = body.get("conn", {})
    rows = int(body.get("rows", 200))
    only_empty = body.get("only_empty", True)
    try:
        rep = seed_sample.seed(cfg, rows=rows, only_empty=only_empty, schema=cfg.get("schema"))
        return jsonify(rep)
    except Exception as e:
        return jsonify({"error": f"seed failed: {e}"}), 400

@app.post("/api/discover")
def discover():
    """Scan a database source and return suggested glossary rows."""
    cfg = (request.get_json(force=True) or {}).get("conn", {})
    try:
        return jsonify(suggester.discover(cfg, cfg.get("schema")))
    except Exception as e:
        return jsonify({"error": f"discovery failed: {e}"}), 400

@app.post("/api/discover-docs")
def discover_docs():
    """Scan a document/object store and return suggested rows."""
    cfg = (request.get_json(force=True) or {}).get("conn", {})
    try:
        return jsonify(suggester.discover_documents(cfg))
    except Exception as e:
        return jsonify({"error": f"document discovery failed: {e}"}), 400

@app.post("/api/schema")
def schema_route():
    """Scan a database or DDL connection and return its ER graph (tables, columns
       with PK/FK, and FK relationships) for the schema diagram. Object-store
       connections have no relational schema."""
    body = request.get_json(force=True) or {}
    src = body.get("source", "ddl")
    try:
        if src in ("minio", "s3"):
            return jsonify({"error": "Object-store connections have no relational "
                            "schema to diagram — pick a database or DDL source."}), 400
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
        return jsonify({"error": f"schema scan failed: {e}"}), 400
    g = suggester.schema_graph(tables)
    g["schema_name"] = schema_name
    return jsonify(g)

@app.post("/api/apply-keys")
def apply_keys():
    """Write PRIMARY KEY / FOREIGN KEY constraints to a live PostgreSQL schema, using
       a CREATE TABLE script as the source of truth for which keys to set. dry_run
       (default true) returns the planned ALTER statements without executing."""
    body = request.get_json(force=True) or {}
    cfg = body.get("conn") or {}
    dry = bool(body.get("dry_run", True))
    try:
        if (body.get("ddl_text") or "").strip():
            tables = suggester.harvest_ddl_text(body["ddl_text"])
        else:
            tables = suggester.harvest_ddl(body.get("ddl_path", DEFAULT_DDL))
    except Exception as e:
        return jsonify({"error": f"Could not read the CREATE TABLE script for key "
                        f"definitions: {e}"}), 400
    keymap = suggester.keymap_from_tables(tables)
    if not keymap:
        return jsonify({"error": "No primary or foreign keys were found in the script "
                        "to apply. Paste your CREATE TABLE statements (with PRIMARY KEY / "
                        "REFERENCES) first."}), 400
    try:
        return jsonify(suggester.apply_keys_live(cfg, cfg.get("schema"), keymap, dry_run=dry))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/scan")
def scan():
    """Dispatch a scan to the right source handler (database, MinIO/S3, or DDL file)."""
    body = request.get_json(force=True) or {}
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
                    sig += f" \u00b7 Data Quality computed from content for {scored} file(s)"
                scn = {"objects": len(files), "folders": len(folders), "dq_scored": scored}
                return jsonify({"rows": rows, "stats": _stats(rows), "scanned": scn,
                                "check": suggester.scan_check(rows, scn),
                                "ownership": {"signals": [sig]}})
            folders, ownership, scanned = suggester.harvest_minio(cfg)
            rows = suggester.suggest_documents(folders, bucket)
            try: tagdict.accrete(rows, source="minio")
            except Exception: pass
            return jsonify({"rows": rows, "stats": _stats(rows),
                            "scanned": scanned, "ownership": ownership,
                            "check": suggester.scan_check(rows, scanned)})
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
        return jsonify({"error": f"scan failed: {e}"}), 400
    rows = suggester.suggest(tables, schema=body.get("schema"))
    try: tagdict.accrete(rows, source="db")
    except Exception: pass
    pk_cols = sum(1 for cols in tables.values() for c in cols if c.get("pk"))
    fk_cols = sum(1 for cols in tables.values() for c in cols if c.get("fk"))
    scanned = {"tables": len(tables), "columns": sum(len(c) for c in tables.values())}
    return jsonify({"rows": rows, "stats": _stats(rows), "scanned": scanned,
                    "check": suggester.scan_check(rows, scanned, pk_cols, fk_cols)})

@app.post("/api/enrich")
def enrich():
    """LLM-enrich the definitions/purposes of the supplied rows via local Ollama."""
    body = request.get_json(force=True) or {}
    rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]  # 1.5.6: guard null rows
    only_low = bool(body.get("only_low_confidence", False))
    model = body.get("model") or None
    compute = body.get("compute") or None
    rows, counts = llm.enrich_rows(rows, only_low_confidence=only_low, model=model, compute=compute)
    return jsonify({"rows": rows, "enriched": counts,
                    "definitions": counts["definitions"], "purposes": counts["purposes"],
                    "names": counts.get("names", 0),
                    "stats": _stats(rows), "llm": llm.status(model)})

@app.post("/api/ai-suggest")
def ai_suggest():
    """Evidence-grounded AI pass over review rows: the local model proposes term /
       category / governed tags / sensitivity from the SCAN EVIDENCE (profiled value
       signatures, induced regexes, reference values), applied under guardrails —
       tags governed-only, sensitivity tighten-only, term as a suggestion chip."""
    body = request.get_json(force=True) or {}
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
    return jsonify({"rows": rows, "updated": counts, "used_llm": used_llm,
                    "stats": _stats(rows), "llm": llm.status(model)})

@app.post("/api/suggest-expertise")
def suggest_expertise_route():
    """LLM-generate `expertise` keywords for each roster member (these drive
       auto-assign). Falls back to a deterministic offline derivation when Ollama
       is unavailable. Body: {people?, categories?, overwrite?, model?, save?}.
       If `people` is omitted the saved roster is used. Optionally persists."""
    body = request.get_json(force=True) or {}
    people = body.get("people") or _load_people()
    categories = body.get("categories") or []
    overwrite = bool(body.get("overwrite", False))
    model = body.get("model") or None
    people, updated, used_llm = llm.suggest_expertise(
        people, categories=categories, overwrite=overwrite, model=model)
    if body.get("save"):
        _save_people(people)
    return jsonify({"people": people, "updated": updated, "used_llm": used_llm,
                    "saved": bool(body.get("save")), "llm": llm.status(model)})

@app.post("/api/resolve-fuzzy")
def api_resolve_fuzzy():
    """Match OUTSTANDING term names (renamed/disambiguated locally after the
    glossary was imported) against the terms that actually exist in PDC —
    without a round-trip through the Glossary page. Ladder: harvest candidate
    term entities via token searches, propose the best NAME-similarity match
    (>=0.78 normalized), let the local AI adjudicate the rest with the term's
    definition as context. Proposals only — the steward binds each one.
    Body: {names, definitions?, base_url, username/password|token, realm?,
    version?, verify_tls?, glossary_name?, model?, compute?}."""
    import pdc_api
    body = request.get_json(force=True) or {}
    names = [str(n).strip() for n in (body.get("names") or []) if str(n).strip()]
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base or not names:
        return jsonify({"error": "base_url and names are required"}), 400
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
        return jsonify({"error": f"auth failed: {e}"}), 502
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
    return jsonify({"matches": matches, "used_llm": used_llm})

@app.post("/api/resolve-terms")
def resolve_terms():
    """Resolve each businessTerm's id + glossaryId in PDC and stamp them into the Data-Elements JSON."""
    import pdc_api
    body = request.get_json(force=True) or {}
    api_json = body.get("json") or []
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
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
                                         version=version, verify_tls=verify)
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
        return jsonify({"error": str(e)}), 502
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
    return jsonify({"json": resolved_json, "map": name_map, "linked": linked,
                    "unresolved": unresolved, "id_only": id_only, "terms": len(names),
                    "matched": len(name_map), "matched_with_glossary": gid_terms,
                    "glossary_id": default_gid, "links": links_total, "probe": probe, "unconfirmed": unconfirmed,
                    "registry_backfilled": registry_backfilled})

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
def pdc_token():
    """Authenticate to PDC and return the admin/Business-Steward JWT plus a
       display-only decode (username, roles, expiry) so the operator can confirm
       the right account before writing. Token is returned for in-memory use only;
       the app never persists it."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    try:
        token = pdc_api.auth(base, body.get("username", ""), body.get("password", ""),
                             version=version, verify_tls=verify,
                             realm=(body.get("realm") or "pdc").strip(),
                             client_id=(body.get("client_id") or "pdc-client").strip(),
                             method=body.get("auth_method") or "auto")
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"token": token, "claims": pdc_api.decode_jwt(token)})

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
def api_similarity():
    """Score the shown terms pairwise and return suggested merges (near-duplicate or
    same-concept names PDC would treat as unrelated). Body: {rows:[...], threshold?}."""
    import re as _re
    body = request.get_json(force=True, silent=True) or {}
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
    return jsonify({"suggestions": sugg, "term_count": len(terms)})

@app.post("/api/recommend-resolutions")
def api_recommend_resolutions():
    """Advise Merge / Disambiguate / Keep separate for every same-named duplicate
    group in the review rows — the decision aid behind the cluster headers.
    Escalation ladder, cheapest first:
      1. cached scan evidence (FK links, profiled value sets, induced formats),
      2. a LIVE data probe when a connection is supplied (sample distinct values
         from each member column and compare the actual populations),
      3. the AI adjudicator (Ollama) for groups still ambiguous, when ai=true.
    Recommendations are hints only — nothing is auto-applied.
    Body: {rows, conn?, ai?, model?, compute?}."""
    body = request.get_json(force=True, silent=True) or {}
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
    return jsonify({"groups": out, "probed": probed, "used_llm": used_llm})

@app.post("/api/draft-policies")
def api_draft_policies():
    """The Policy Generator's first mile: draft PDC Data Identification rules from
    the scan's detection seeds — an induced value regex becomes a Data Pattern,
    a profiled reference list becomes a Dictionary (+ values CSV), in the exact
    JSON shapes the Technical Track teaches. Deterministic core; with ai=true the
    LLM agent polishes each rule's column-name regex and tag pick (guard-railed:
    regex must compile, tags stay governed). format=zip streams the bundle.
    Body: {rows, glossary_name?, prefix?, ai?, model?, compute?, format?}."""
    body = request.get_json(force=True, silent=True) or {}
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
        from flask import Response
        return Response(data, mimetype="application/zip",
                        headers={"Content-Disposition":
                                 "attachment; filename=drafted-policies.zip"})
    return jsonify({"patterns": [{"filename": p["filename"], "term": p["term"],
                                  "seed": p.get("seed", "profiled"),
                                  "name": p["rule"][0]["name"]} for p in draft["patterns"]],
                    "dictionaries": [{"filename": d["filename"], "term": d["term"],
                                      "name": d["rule"][0]["name"],
                                      "values": d["values_filename"]} for d in draft["dictionaries"]],
                    "skipped": draft["skipped"], "used_llm": used_llm})

@app.post("/api/qa-definitions")
def api_qa_definitions():
    """Definition QA before import: the deterministic linter (circular, echo,
    vague, too-short, copy-paste duplicates) always runs; with ai=true the LLM
    agent also judges whether each definition actually explains the business
    meaning, and proposes a better sentence. Rows come back with QA_Issues /
    QA_Suggestion stamped — flags and proposals only, the steward applies.
    Body: {rows, ai?, model?, compute?}."""
    body = request.get_json(force=True, silent=True) or {}
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
    return jsonify({"rows": rows, "flagged": flagged,
                    "lint_flagged": len(lint), "used_llm": used_llm,
                    "llm": {"online": used_llm or not body.get("ai")}})

@app.post("/api/ai-categorize")
def api_ai_categorize():
    """AI category assignment for uncategorized rows (or all rows with
    only_blank=false): the local model picks ONE category per term from the
    known set — pack categories + the categories already in use — and anything
    off-list is discarded. Body: {rows, only_blank?, model?, compute?}."""
    body = request.get_json(force=True, silent=True) or {}
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
    return jsonify({"rows": rows, "updated": updated,
                    "llm": {"online": used_llm}})

@app.post("/api/retag")
def api_retag():
    """Re-derive meaningful, controlled tags for a set of review rows (the grid's
       'Suggest tags' action). Deterministic; no rescan. Table-level record terms
       keep their table-level tags."""
    body = request.get_json(force=True, silent=True) or {}
    rows = body.get("rows") or []
    try:
        suggester.retag_rows(rows)
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 400
    return jsonify({"rows": rows})

@app.get("/api/tagdict")
def api_tagdict_get():
    """The per-company tag dictionary — the controlled allow-list + rules that drive
       tagging, seeded from the domain and grown from scans. Governs tag consistency
       into the Registry and the Policy Generator."""
    return jsonify(tagdict.summary())

@app.post("/api/tagdict")
def api_tagdict_save():
    """Steward save of the whole dictionary (terms/tags/rules). Guard-railed:
       generic baseline entries are protected, rule/term tags must exist, and
       sensitivity is validated — risky edits come back as warnings."""
    body = request.get_json(force=True, silent=True) or {}
    doc = body.get("dictionary") if isinstance(body.get("dictionary"), dict) else body
    try:
        warnings = tagdict.replace(doc)
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 400
    out = tagdict.summary()
    out["warnings"] = warnings
    audit.record("dictionary.save", actor=body.get("actor"),
                 terms=out.get("term_count"), tags=out.get("tag_count"),
                 warnings=len(warnings))
    return jsonify(out)

@app.post("/api/tagdict/review")
def api_tagdict_review():
    """Steward approve/reject of pending accreted items. Body: {kind:'tag'|'term',
       names:[...], action:'approve'|'reject'}. Only approved (or generic) items
       govern the Registry / Policy Generator."""
    body = request.get_json(force=True, silent=True) or {}
    kind = body.get("kind"); action = body.get("action", "approve")
    names = body.get("names") or []
    if kind not in ("tag", "term"):
        return jsonify({"error": "kind must be 'tag' or 'term'"}), 400
    changed = tagdict.review(kind, names, action, target=body.get("target"))
    if changed:
        audit.record("%s.%s" % (kind, action), actor=body.get("actor"), names=names, changed=changed)
    out = tagdict.summary(); out["changed"] = changed
    return jsonify(out)

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
def api_suggest_domain():
    """Pick the PDC business-domain classifier from the company's OWN data: the
    installed pack's domain key + the company name first (deterministic keyword
    map), the local AI as fallback for unmapped businesses (guardrail: the
    answer must be in the supplied list). Advice for the Govern page's DOMAIN
    default. Body: {domains, categories?, terms?, model?, compute?}."""
    import re as _re
    body = request.get_json(force=True, silent=True) or {}
    domains = [str(d) for d in (body.get("domains") or []) if str(d).strip()]
    company = llm.COMPANY if llm.COMPANY != "your organization" else ""
    pack_domain = str(tagdict.load().get("domain") or "")
    hay = (pack_domain + " " + company).lower()
    if hay.strip() and domains:
        for rx, dom in _DOMAIN_MAP:
            if _re.search(rx, hay) and dom in domains:
                return jsonify({"domain": dom, "used_llm": False,
                                "reason": f"matched the installed pack/company ({pack_domain or company})"})
    dom, used = llm.suggest_domain(company, body.get("categories"), body.get("terms"),
                                   domains, model=body.get("model"), compute=body.get("compute"))
    return jsonify({"domain": dom, "used_llm": used,
                    "reason": ("AI classification from company + glossary content" if dom else
                               "no match — pick manually (Ollama offline and no keyword hit)")})

@app.post("/api/tagdict/ai-review")
def api_tagdict_ai_review():
    """Advise on the pending scan-found terms: a deterministic near-duplicate
    pass against the governed vocabulary (similarity scoring - 'Apy' vs 'APR
    Rate'), then the local AI agent judges the rest with the captured context
    (category, definition, sources). Advice only - the steward clicks approve /
    reject / alias. Body: {model?, compute?}."""
    body = request.get_json(force=True, silent=True) or {}
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
    return jsonify({"advice": advice, "pending": len(pending), "used_llm": used_llm})

@app.post("/api/tagdict/reset")
def api_tagdict_reset():
    """Reseed from the domain pack + defaults. Approved company items and company
       rules are preserved (the governed set survives a reseed); pending items are
       discarded; a timestamped backup of the previous file is taken first."""
    body = request.get_json(force=True, silent=True) or {}
    res = tagdict.reset()
    kept = (res or {}).get("kept") or {}
    audit.record("dictionary.reset", actor=body.get("actor"),
                 detail=("preserved approved: %d tag(s), %d term(s), %d rule(s)"
                         % (kept.get("tags", 0), kept.get("terms", 0), kept.get("rules", 0))
                         + ((" · backup: " + os.path.basename(res["backup"])) if (res or {}).get("backup") else "")))
    out = tagdict.summary()
    out["kept"] = kept
    return jsonify(out)

@app.get("/api/audit")
def api_audit():
    """Recent governance audit entries (newest first) + summary."""
    try:
        n = int(request.args.get("n", 50))
    except Exception:
        n = 50
    return jsonify({"entries": audit.recent(n), "summary": audit.summary()})

@app.get("/api/audit/export.json")
def api_audit_export():
    """Download the full governance audit trail (ships alongside the Registry)."""
    return Response(json.dumps(audit.all_entries(), indent=2), mimetype="application/json",
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
    resp = jsonify(payload)
    resp.headers["Access-Control-Allow-Origin"] = "*"      # read-only; lets the viz app poll cross-origin
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.post("/api/export-pack")
def api_export_pack():
    """Generate a domain pack from the reviewed scan results: table mappings,
    learned abbreviations, the governed company vocabulary, and — the point —
    curated_seeds carrying the induced value patterns and profiled reference
    lists, so the pack's detection seeds are specific to THIS company's data.
    MERGES over the installed pack: learned content fills gaps; where the scan
    DISAGREES with the pack the conflict is reported (pack vs scan value) and
    the steward's resolutions decide — curation keeps the pack's value by
    default, curated_seeds prefer the fresher scan evidence.
    Body: {rows, resolutions?: {"key::name": "scan"|"pack"}, apply?}."""
    body = request.get_json(force=True, silent=True) or {}
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
    return jsonify(out)

@app.get("/api/tagdict/export.json")
def api_tagdict_export():
    """Download the raw dictionary artifact (shareable governance record)."""
    return Response(json.dumps(tagdict.load(), indent=2), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=tag_dictionary.json"})

@app.get("/api/pdc/bulk-load/sample.csv")
def pdc_bulk_sample():
    """Download a starter CSV for the bulk loader (two sample sources). Replace the
       CHANGE_ME secrets before importing."""
    return Response(_BULK_SAMPLE_CSV, mimetype="text/csv",
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
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=connections.csv"})

@app.post("/api/pdc/connections/export")
def pdc_connections_export():
    """Read the data sources already registered in PDC and return them as a
       bulk-loader CSV (same columns the loader consumes), so a hand-built
       connection can be captured and replayed. Secrets are blanked — PDC never
       returns plaintext credentials — so the operator re-enters them before reload.
       Auth is a bearer token or username/password, exactly like the other PDC calls."""
    import pdc_api
    body = request.get_json(force=True, silent=True) or {}
    base = (body.get("base_url") or body.get("base") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
    except Exception as e:
        return jsonify({"error": str(e)}), 401
    try:
        sources = pdc_api.list_data_sources(base, token, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": "could not list data sources: %s" % str(e)[:300]}), 502
    csv_text = pdc_api.connections_to_csv(sources)
    fmt = (body.get("format") or "csv").lower()
    if fmt == "json":
        return jsonify({"count": len(sources), "csv": csv_text,
                        "names": [s.get("resourceName") for s in sources if isinstance(s, dict)]})
    return Response(csv_text, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=pdc-connections.csv"})

@app.post("/api/pdc/bulk-load")
def pdc_bulk_load():
    """Bulk-register data sources in PDC from CSV/JSON rows: for each row
       create -> test-connection (poll) -> metadata ingest. Streams one NDJSON
       event per row (plus start/done) so the UI can show live progress. Auth is
       a bearer token or username/password; secrets are never persisted or logged.
       options: {test, ingest, wait} all default true; dry_run previews bodies."""
    import pdc_api
    body = request.get_json(force=True, silent=True) or {}
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
            return jsonify({"error": "could not parse CSV: %s" % e}), 400
    rows = rows or []
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    if not rows:
        return jsonify({"error": "no rows to load — provide 'rows' or 'csv'"}), 400

    def gen():
        # Dry run: just build and echo the (redacted) bodies, no auth, no calls.
        if dry_run:
            yield json.dumps({"event": "start", "total": len(rows), "dry_run": True}) + "\n"
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
                yield json.dumps(ev) + "\n"
            yield json.dumps({"event": "done", "dry_run": True, "total": len(rows)}) + "\n"
            return

        try:
            token, reauth = _pdc_token_and_reauth(body, base, version, verify)
        except Exception as e:
            yield json.dumps({"event": "error", "message": str(e)}) + "\n"
            return

        yield json.dumps({"event": "start", "total": len(rows)}) + "\n"
        results = []
        for idx, row in enumerate(rows, 1):
            name = row.get("resourceName") or row.get("name") or ("row %d" % idx)
            yield json.dumps({"event": "row_start", "index": idx, "total": len(rows),
                              "resourceName": name}) + "\n"
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
            yield json.dumps({"event": "row", "index": idx, "total": len(rows),
                              "result": rec}) + "\n"

        ok = sum(1 for r in results if r.get("create") in ("OK", "EXISTS", "RECREATED")
                 and r.get("ingest") in ("OK", "SKIP")
                 and r.get("job") in ("OK", "SKIP"))
        yield json.dumps({"event": "done", "total": len(rows), "ok": ok,
                          "failed": len(rows) - ok, "results": results}) + "\n"

    return Response(gen(), mimetype="application/x-ndjson")

@app.post("/api/apply-to-pdc")
def apply_to_pdc():
    """Resolve each Data Element column in PDC, merge the new businessTerms +
       features into whatever it already carries, and PATCH it back. dry_run=true
       returns every planned PATCH (id + body) without sending. Optionally runs
       Calculate Trust Score on the touched ids after an apply."""
    import pdc_api
    body = request.get_json(force=True) or {}
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
        return jsonify({"error": "PDC base URL is required"}), 400
    if not api_json:
        return jsonify({"error": "no Data Elements JSON to apply — export and resolve first"}), 400
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
                                      desc_mode=desc_mode, table_terms=table_terms)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    report.pop("token", None)  # never hand the token back to the browser
    return jsonify(report)

@app.post("/api/apply-to-pdc-stream")
def apply_to_pdc_stream():
    """Same as /api/apply-to-pdc, but streams Server-Sent Events so the browser can
       show a live per-column progress bar. The apply logic is unchanged — it just
       runs in a worker thread with a progress callback that feeds an SSE queue.
       Emits `event: progress` per column/phase and a final `event: done` (report)
       or `event: error`."""
    import pdc_api, threading
    import queue as _queue
    body = request.get_json(force=True) or {}
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
        return jsonify({"error": "PDC base URL is required"}), 400
    if not api_json:
        return jsonify({"error": "no Data Elements JSON to apply — export and resolve first"}), 400

    q = _queue.Queue()

    def _run():
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
                                          progress=lambda ev: q.put(("progress", ev)))
            report.pop("token", None)
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

    return Response(_gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/trigger-profiling")
def trigger_profiling():
    """Kick off a PDC Data Discovery (profiling) job on the document/object-store
       entities in a Data-Elements payload, so files that show 'Profiled Status:
       SKIPPED' get profiled and gain PDC's own Data Quality metric.

       Body: the PDC connection fields + 'json' (the Data-Elements records). We keep
       only the object-store records, resolve their folders (cascading to files) to
       entity UUIDs, and POST the discovery job. 'poll' optionally waits for the job
       to finish so the caller can immediately re-pull profiling stats."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    api_json = body.get("json") or []
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    # restrict to object-store records; database columns are profiled by scanning the DB
    docs = [r for r in api_json
            if str(r.get("type", "")).upper() in ("OBJECT", "FILE", "DIRECTORY")]
    if not docs:
        return jsonify({"error": "no document/object-store records to profile — this "
                        "action profiles MinIO/S3 files, not database columns"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        scope_ids, labels = pdc_api.resolve_document_scope(
            base, token, docs, version=version, verify_tls=verify)
        if not scope_ids:
            return jsonify({"error": "could not resolve any document folders/files in "
                            "PDC — confirm the object store has been scanned into the "
                            "catalog first"}), 404
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
        return jsonify({"error": str(e)}), 502
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
    return jsonify(res)

@app.post("/api/discovery-progress")
def api_discovery_progress():
    """Version-agnostic Data Discovery progress: compare each scoped entity's
    system.profiledAt against the pre-submission baseline — v3's bulk job
    endpoint returns no job id, so the entities themselves are the truth.
    Body: {ids, baseline, base_url, auth...}. Returns {profiled, total, done}."""
    import pdc_api
    body = request.get_json(force=True) or {}
    ids = [str(x) for x in (body.get("ids") or []) if str(x).strip()]
    baseline = body.get("baseline") or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base or not ids:
        return jsonify({"error": "base_url and ids are required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        snap = pdc_api.profiled_snapshot(base, token, ids, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    changed = [i for i in ids if snap.get(i) and snap.get(i) != baseline.get(i)]
    return jsonify({"profiled": len(changed), "total": len(ids),
                    "done": len(changed) == len(ids) and bool(ids)})

@app.post("/api/job-status")
def job_status_route():
    """Poll a PDC background job by id (GET /jobs/{id}/status) so the UI can show a
       profiling/discovery job's progress without leaving the app."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    job_id = (body.get("job_id") or "").strip()
    if not base or not job_id:
        return jsonify({"error": "base_url and job_id are required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        st = pdc_api.job_status(base, token, job_id, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    st.pop("raw", None)
    return jsonify(st)

@app.post("/api/pdc-profiling")
def pdc_profiling():
    """Pull PDC's own profiling stats for a set of columns, keyed by
       'schema.table.column', for the app-vs-PDC side-by-side."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    columns = body.get("columns") or []
    sample_limit = int(body.get("sample_limit", 20) or 20)
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    if not columns:
        return jsonify({"error": "no columns supplied — run discovery first"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        profiles = pdc_api.pdc_profile_for_columns(base, token, columns, version=version,
                                                   verify_tls=verify, sample_limit=sample_limit)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"profiles": profiles, "count": len(profiles),
                    "requested": len(columns)})

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
def pdc_source_to_connection():
    """Turn a source PDC already knows into a saved app connection: fetch the full
       record over /data-sources/filter, prefill engine/host/port/db/schema/user
       (or endpoint/bucket), and save it needing only the secret. If a connection
       with the same name exists, its config is refreshed but a saved secret is
       KEPT — re-adding never wipes a working credential."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    name = (body.get("data_source_name") or "").strip()
    ds_id = (body.get("data_source_id") or "").strip() or None
    if not base or not (name or ds_id):
        return jsonify({"error": "base_url and data_source_name (or id) are required"}), 400
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
        return jsonify({"error": msg}), 502
    if not rec:
        return jsonify({"error": f"PDC returned no data-source record for {name or ds_id!r}"}), 404
    conn, needs, warning = _pdc_record_to_conn(rec)
    if conn is None:
        return jsonify({"error": warning}), 400
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
    return jsonify({"connection": conn, "needs": (None if kept_secret else needs),
                    "kept_secret": kept_secret, "updated": bool(existing),
                    "warning": warning})

@app.post("/api/pdc/data-sources")
def pdc_data_sources():
    """List the data-source connections already configured in PDC, so the user can
       harvest a glossary straight from the catalog (no direct DB access or secret)."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        sources = pdc_api.list_catalog_roots(base, token, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"data_sources": sources, "count": len(sources)})

@app.post("/api/pdc/source-test")
def pdc_source_test():
    """Per-connection 'test': confirm the source resolves in the catalog and report
       how many entities PDC actually holds for it (COLUMN for databases, FILE for
       object stores). An ingest that reported OK but scanned an empty schema shows
       here as 0 — the check that would have caught the public-vs-cscu_core bug.
       Read-only: no jobs triggered."""
    import pdc_api
    body = request.get_json(force=True, silent=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    ds_id = body.get("data_source_id")
    ds_name = body.get("data_source_name")
    if not base or not (ds_id or ds_name):
        return jsonify({"error": "PDC base URL and a data source are required"}), 400
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
        return jsonify({"ok": ok, "columns": ncol, "files": nfile, "message": msg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 502

@app.post("/api/pdc/source-config")
def pdc_source_config():
    """Return the raw stored config of a PDC data source (secrets redacted) so you can
       see exactly which databaseType / serviceType / fileSystemType / configMethod a
       working object-store source uses — the values the loader must match. Create one
       AWS S3 source by hand in the PDC UI, then inspect it here."""
    import pdc_api
    body = request.get_json(force=True, silent=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    name = (body.get("resource_name") or body.get("data_source_name") or "").strip()
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        recs = pdc_api.list_data_sources(base, token, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": str(e)[:300]}), 502
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
    return jsonify({"sources": out, "count": len(out)})

@app.post("/api/pdc/harvest")
def pdc_harvest():
    """Harvest a glossary straight from PDC's catalog: read the COLUMN entities PDC
       already scanned for a data source, run them through the same suggester a live
       scan uses, and overlay what PDC ALREADY governs (sensitivity/trust/terms) so
       the user can see existing work before generating. No direct DB access."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    ds_id = (body.get("data_source_id") or "").strip() or None
    ds_name = (body.get("data_source_name") or "").strip() or None
    if not base:
        return jsonify({"error": "PDC base URL is required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        tables, files, overlay, summary = pdc_api.harvest_from_catalog(
            base, token, ds_id=ds_id, ds_name=ds_name, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    if not tables and not files:
        return jsonify({"error": "PDC returned no columns or files for that data source. "
                        "Confirm the source has been scanned/ingested in PDC."}), 404
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
           f"\u00b7 {governed} already governed in PDC")
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
    return jsonify({"rows": rows, "stats": _stats(rows), "scanned": scn,
                    "pdc_summary": pdc_summary,
                    "ownership": {"signals": [sig]},
                    "check": suggester.scan_check(rows, scn)})

@app.post("/api/pdc/glossary-exists")
def pdc_glossary_exists():
    """Pre-flight check: does a glossary with this name already exist in PDC? Lets the
       UI warn and offer update-vs-create instead of creating a duplicate on import."""
    import pdc_api
    body = request.get_json(force=True) or {}
    base = (body.get("base_url") or "").strip()
    version = body.get("version") or "v2"
    verify = bool(body.get("verify_tls", False))
    name = (body.get("glossary_name") or body.get("name") or "").strip()
    if not base or not name:
        return jsonify({"error": "PDC base URL and glossary_name are required"}), 400
    try:
        token, _ = _pdc_token_and_reauth(body, base, version, verify)
        res = pdc_api.glossary_exists(base, token, name, version=version, verify_tls=verify)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify(res)

@app.post("/api/data-elements")
def data_elements():
    """Build the term<->column Data-Element links plus their bulk-assign CSV and Trust-ready API JSON."""
    body = request.get_json(force=True) or {}
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
    return jsonify({"links": links, "csv": suggester.links_to_csv(links),
                    "json": api_json, "count": len(links), "elements": len(api_json),
                    "terms": len({l["business_term"] for l in links}),
                    "tables": len({(l["schema_name"], l["table_name"]) for l in links}),
                    "quality_scored": rated,
                    # selective-mapping transparency: which terms were linked vs held back
                    "mapped_terms": breakdown["mapped_count"],
                    "skipped_terms": breakdown["skipped_count"],
                    "breakdown": breakdown,
                    "policy": {**suggester.DEFAULT_MAP_POLICY, **(policy or {})}})

@app.post("/api/generate")
def generate():
    """Generate import-ready glossary JSONL (and summary stats) from review rows."""
    body = request.get_json(force=True) or {}
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
    return jsonify({"jsonl": jsonl,
                    "registry": registry_path,
                    "check": suggester.glossary_build_check(rows, recs, name),
                    "stats": {"glossary": name, "lines": len(recs),
                              "categories": sum(1 for r in recs if r["type"] == "category"),
                              "terms": sum(1 for r in recs if r["type"] == "term"),
                              "kept": kept, "dropped": len(rows) - kept}})

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "5000")), debug=False)
