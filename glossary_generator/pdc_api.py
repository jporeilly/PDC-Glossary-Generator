"""
pdc_api.py - PDC Public API client.

Two jobs:
  1. RESOLVE  - look up each business term by name -> {id, glossaryId} and stamp
                the ids into the Data Elements JSON (so it is POST-able to
                /data-collections).
  2. APPLY    - for each kept term<->column association, resolve the column's
                entity id, MERGE the new businessTerms + features into whatever
                the column already carries, and PATCH it back into PDC. Supports
                a dry-run that returns every planned PATCH (id + body) without
                sending, then an apply mode that reports per-column pass/fail.
                Optionally kicks off Calculate Trust Score on the touched ids.
  3. PROFILE  - pull PDC's own profiling stats for a set of columns so the app's
                discovery panel can show app-vs-PDC side by side.

Grounded in the PDC Public API (confirmed from the instance Swagger):
  - Auth:    POST /api/public/<v>/auth   (form) -> {data:{accessToken}}
  - Search:  POST /api/public/<v>/search ({searchTerm, searchFacets:{type:["term"]}})
             a term hit carries its own _id (term id) and rootId (its glossary).
  - Filter:  POST /api/public/<v>/entities/filter?extended=true&size=500
             body {"filters": {...}} - at least one of:
               fqdns | names | types | parentIds | rootIds | resourceIds |
               collectionIds | buckets | profileStatus | profiledAt
             response {status, data:[ {_id, name, type, fqdn, fqdnDisplay,
               parentId, rootId, resourceId, resourceName, attributes, ...} ]}
  - Patch:   PATCH /api/public/<v>/entities/{_id}   body {"attributes": {...}}
             server semantics: arrays full-replace, scalars overwrite, object
             keys merge -> so we send the already-merged businessTerms superset.
  - Profile: POST /api/public/<v>/entities/filter/profiling-info?sampleLimit=N
             same filters body; each item adds nested profilingInfo.stats.
  - Trust:   POST /api/public/<v>/jobs/execute/calculate-trust-score {"scope":[ids]}
             poll GET /api/public/<v>/jobs/{id}/status
"""
import json
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error


# Tolerate users pasting the Keycloak realm URL (or an API path) as the "base".
# PDC's base is the SERVER ROOT, e.g. https://host. The code appends the keycloak
# and /api/public paths itself, so if the base already contains them you get a
# doubled URL like .../keycloak/realms/pdc/keycloak/realms/pdc/... -> 404.
_REALM_RE = re.compile(r"/(?:auth|keycloak)/realms/([^/]+)", re.I)

def split_base(base_url):
    """Return (clean_base, detected_realm_or_None). Strips a trailing Keycloak realm
       path, token path, /keycloak, or /api/public/vN so the server root is left."""
    b = (base_url or "").strip().rstrip("/")
    m = _REALM_RE.search(b)
    realm = m.group(1) if m else None
    b = re.sub(r"/protocol/openid-connect/token/?$", "", b, flags=re.I)
    b = re.sub(r"/(?:auth|keycloak)/realms/[^/]+.*$", "", b, flags=re.I)
    b = re.sub(r"/api/public/v\d+.*$", "", b, flags=re.I)
    b = re.sub(r"/keycloak/?$", "", b, flags=re.I)
    return b.rstrip("/"), realm

def clean_base(base_url):
    """The PDC server root, robust to a base that already includes the keycloak or
       API path (a common paste mistake). Superset of base_url.rstrip('/')."""
    return split_base(base_url)[0]


class TokenExpired(Exception):
    """Raised on a 401 so the caller can re-auth once and retry."""


def _ctx(verify_tls):
    """Build an SSL context that skips certificate verification when verify_tls is False (curl -k equivalent)."""
    if verify_tls:
        return None
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _req(method, url, token=None, body=None, headers=None, verify_tls=True,
         timeout=30, form=False):
    """Generic request. Returns parsed JSON (or {} on empty body).
       Raises TokenExpired on 401; RuntimeError with the server text otherwise."""
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx(verify_tls)) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:600]
        except Exception:
            pass
        if e.code == 401:
            raise TokenExpired(detail or "401 Unauthorized")
        raise RuntimeError(f"HTTP {e.code} on {method} {url}: {detail}")


def _post(url, data, headers, verify_tls=True, timeout=20, form=False):
    """Back-compat shim used by auth()/resolve_terms()."""
    tok = (headers or {}).get("Authorization", "").replace("Bearer ", "") or None
    return _req("POST", url, token=tok, body=data, verify_tls=verify_tls,
                timeout=timeout, form=form)


# --------------------------------------------------------------------------- #
#  Auth
# --------------------------------------------------------------------------- #
def keycloak_auth(base_url, username, password, realm="pdc", client_id="pdc-client",
                  verify_tls=True, timeout=20, scope=None):
    """Get a JWT straight from PDC's Keycloak token endpoint \u2014 the documented,
       reliable path. PDC delegates auth to Keycloak, so this is the real IdP.
         POST <base>/keycloak/realms/<realm>/protocol/openid-connect/token
         client_id=pdc-client  grant_type=password  username  password
       Returns the token from .access_token."""
    url = clean_base(base_url) + f"/keycloak/realms/{realm}/protocol/openid-connect/token"
    payload = {"client_id": client_id, "grant_type": "password",
               "username": username, "password": password}
    if scope:
        payload["scope"] = scope
    out = _req("POST", url, body=payload, verify_tls=verify_tls, timeout=timeout, form=True)
    tok = out.get("access_token") or (out.get("data") or {}).get("access_token")
    if not tok:
        raise RuntimeError("Keycloak auth returned no access_token")
    return tok


def pdc_api_auth(base_url, username, password, version="v2", verify_tls=True, timeout=20):
    """Legacy path: POST /api/public/<v>/auth -> {data:{accessToken}}. Some
       instances don't expose this; prefer keycloak_auth()."""
    url = clean_base(base_url) + f"/api/public/{version}/auth"
    payload = {"username": username, "password": password, "client_id": "pdc-client",
               "grant_type": "password", "scope": "openid profile email"}
    out = _req("POST", url, body=payload, verify_tls=verify_tls, timeout=timeout, form=True)
    tok = (out.get("data") or {}).get("accessToken") or out.get("accessToken")
    if not tok:
        raise RuntimeError("auth succeeded but no accessToken in response")
    return tok


def auth(base_url, username, password, version="v2", verify_tls=True, timeout=20,
         realm="pdc", client_id="pdc-client", method="auto"):
    """Return a bearer token from username/password.
         method='keycloak' -> Keycloak token endpoint (recommended)
         method='pdc'      -> legacy /api/public/<v>/auth
         method='auto'     -> Keycloak first, fall back to /auth (default)
       Signature stays backward-compatible; existing callers now get Keycloak-first."""
    if method == "pdc":
        return pdc_api_auth(base_url, username, password, version, verify_tls, timeout)
    if method == "keycloak":
        return keycloak_auth(base_url, username, password, realm, client_id, verify_tls, timeout)
    # auto
    try:
        return keycloak_auth(base_url, username, password, realm, client_id, verify_tls, timeout)
    except Exception as e_kc:
        try:
            return pdc_api_auth(base_url, username, password, version, verify_tls, timeout)
        except Exception as e_pdc:
            raise RuntimeError(f"Keycloak auth failed: {e_kc}  |  /auth fallback failed: {e_pdc}")


def decode_jwt(token):
    """Display-only decode of a JWT payload (NOT verified). Returns a small dict
       of the claims that matter for confirming who/what the token is for:
       username, roles, issued/expiry. Best-effort; never raises."""
    import base64, time as _time
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)               # pad base64url
        claims = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return {}
    roles = []
    ra = claims.get("realm_access") or {}
    if isinstance(ra, dict):
        roles = ra.get("roles") or []
    exp = claims.get("exp")
    out = {
        "username": claims.get("preferred_username") or claims.get("sub") or "",
        "name": claims.get("name") or claims.get("given_name") or "",
        "email": claims.get("email") or "",
        "roles": roles,
        "is_admin": any(str(r).lower() in ("admin", "system_administrator")
                        for r in roles),
        "exp": exp,
    }
    if isinstance(exp, (int, float)):
        out["expires_in"] = max(0, int(exp - _time.time()))
        out["expired"] = out["expires_in"] <= 0
    return out


# --------------------------------------------------------------------------- #
#  Shared helpers
# --------------------------------------------------------------------------- #
def _results(out):
    """Pull the entity/asset list out of a response, tolerant of shape."""
    d = out.get("data", out)
    if isinstance(d, dict):
        for k in ("results", "items", "hits", "data"):
            if isinstance(d.get(k), list):
                return d[k]
        return []
    return d if isinstance(d, list) else []


def _cursor(out):
    """Pull the pagination cursor out of a response envelope, tolerating field-name aliases."""
    ci = out.get("cursorInfo") or {}
    if isinstance(ci, dict):
        return ci.get("cursor") or ci.get("nextCursor") or ci.get("next")
    return out.get("cursor") or out.get("nextCursor")


def _eid(it):
    """Return an entity's id, tolerating the `_id` vs `id` spelling."""
    return it.get("_id") or it.get("id")


def _glossary_id(item):
    # for a TERM, the glossary it belongs to is its rootId (NOT parentId, which
    # is the category). Prefer rootId; fall back only to an explicit glossaryId.
    """Return the glossary a term belongs to (its rootId), falling back to an explicit glossaryId."""
    p = item.get("properties") if isinstance(item.get("properties"), dict) else {}
    return (item.get("rootId") or item.get("glossaryId") or item.get("rootID")
            or p.get("rootId") or p.get("glossaryId"))


def _bt_match(item, name):
    """If a /search result already carries this term in its businessTerms[], return
       (termId, glossaryId) straight from PDC's documented search shape
       (businessTerms[] = {termId, name, fqdn, glossaryId})."""
    for bt in (item.get("businessTerms") or []):
        if str(bt.get("name", "")).strip().lower() == name.strip().lower():
            tid = bt.get("termId") or bt.get("id")
            if tid:
                return tid, bt.get("glossaryId")
    return None, None


# --------------------------------------------------------------------------- #
#  Resolve terms (name -> id + glossaryId)
# --------------------------------------------------------------------------- #
def fuzzy_term_candidates(base_url, token, name, version="v2",
                          verify_tls=True, timeout=20, max_candidates=25):
    """Candidate TERM entities for an outstanding name, harvested by searching
    the name AND its significant tokens (PDC has no list-glossary-terms
    endpoint). 'Branch Identifier' searches 'Branch Identifier', 'branch',
    'identifier' and collects every result that IS a term — the pool a fuzzy/AI
    matcher chooses from. Returns [{name, id, glossaryId}] deduped by name."""
    import re as _re
    base = clean_base(base_url)
    surl = base + f"/api/public/{version}/search"
    tokens = [t for t in _re.split(r"[^A-Za-z0-9]+", str(name)) if len(t) > 2][:3]
    queries = [name] + tokens
    seen, out = set(), []
    for q in queries:
        try:
            res = _req("POST", surl, token=token,
                       body={"searchTerm": q, "perPage": 50},
                       verify_tls=verify_tls, timeout=timeout)
            hits = _results(res)
        except Exception:
            hits = []
        for it in hits:
            if "term" not in str(it.get("type") or it.get("originalType") or "").lower():
                continue
            nm = str(it.get("name") or "").strip()
            key = nm.lower()
            if not nm or key in seen:
                continue
            seen.add(key)
            out.append({"name": nm, "id": _eid(it), "glossaryId": _glossary_id(it)})
            if len(out) >= max_candidates:
                return out
    return out


def resolve_terms(base_url, token, names, glossary_name=None, version="v2",
                  verify_tls=True, timeout=20):
    """Look up each term name in PDC. Returns {name: {id, glossaryId}} for hits.

    PDC's public API has no 'list glossary terms' endpoint, so a term name is
    resolved three ways, in order of reliability:
      A) POST /search the name and take a result that IS the term itself (its own
         `type` contains 'term'), reading its id and rootId (the glossary).
         IMPORTANT: we do NOT facet the search by type=['term']. In /search the
         `type` facet means ASSET type (FILE, COLUMN, TABLE...), so faceting on
         'term' returns ZERO hits — that was the bug that made Resolve match 0/111
         even with the glossary imported. We match on each result's own type field.
      B) any /search result whose businessTerms[] already carries the name gives
         {termId, glossaryId} directly (PDC's documented search response shape).
      C) POST /entities/filter by name and, for a term-typed entity, read its
         rootId as the glossaryId.
    A term not yet in PDC (glossary not imported) simply resolves to nothing."""
    base = clean_base(base_url)
    surl = base + f"/api/public/{version}/search"
    eurl = base + f"/api/public/{version}/entities/"
    out_map = {}

    def _root_of(tid):
        """GET the entity by id and return its rootId (the glossary), best-effort."""
        try:
            ent = _req("GET", eurl + str(tid), token=token, verify_tls=verify_tls, timeout=timeout)
            e = ent.get("data", ent)
            if isinstance(e, list):
                e = e[0] if e else {}
            return _glossary_id(e)
        except Exception:
            return None

    for name in sorted(set(n for n in names if n)):
        try:
            res = _req("POST", surl, token=token,
                       body={"searchTerm": name, "perPage": 50},
                       verify_tls=verify_tls, timeout=timeout)
            hits = _results(res)
        except Exception:
            hits = []

        tid = gid = None
        # path A: a search result that IS the term
        for it in hits:
            if str(it.get("name", "")).strip().lower() != name.strip().lower():
                continue
            if "term" not in str(it.get("type") or it.get("originalType") or "").lower():
                continue
            tid = _eid(it)
            gid = _glossary_id(it)
            if tid and not gid:
                gid = _root_of(tid)
            if tid:
                break
        # path B: recover id AND/OR a missing glossaryId from any result's
        # businessTerms[] (PDC returns {termId, name, glossaryId} there).
        if not tid or not gid:
            for it in hits:
                b_tid, b_gid = _bt_match(it, name)
                if b_tid:
                    tid = tid or b_tid
                    gid = gid or b_gid
                    if tid and gid:
                        break
        # path C: entities/filter by name -> term entity -> rootId
        if not (tid and gid):
            try:
                ents = filter_entities(base_url, token, {"names": [name]},
                                       version, verify_tls, timeout)
            except Exception:
                ents = []
            for e in ents:
                if str(e.get("name", "")).strip().lower() != name.strip().lower():
                    continue
                if "term" not in str(e.get("type") or "").lower():
                    continue   # only trust term-typed entities (avoid same-named columns)
                tid = tid or _eid(e)
                gid = gid or _glossary_id(e)
                if tid and not gid:
                    gid = _root_of(tid)
                if tid:
                    break

        if tid:
            out_map[name] = {"id": tid, "glossaryId": gid}
    return out_map


def diagnose_terms(base_url, token, sample_names, version="v2", verify_tls=True, timeout=20):
    """Probe PDC for a few term names so the UI can show WHY Resolve found nothing.
       For each sample name reports: how many /search hits, the distinct result
       `type` values, whether any result exposed a glossaryId or already carried
       the term in businessTerms[], and how many /entities/filter-by-name hits.
       Returns a short list of dicts (no ids) safe to display."""
    base = clean_base(base_url)
    surl = base + f"/api/public/{version}/search"
    probes = []
    for name in [n for n in sample_names if n][:3]:
        rep = {"name": name, "search_hits": 0, "search_types": [],
               "search_has_glossaryId": False, "bt_match": False,
               "filter_hits": 0, "filter_types": []}
        try:
            res = _req("POST", surl, token=token, body={"searchTerm": name, "perPage": 50},
                       verify_tls=verify_tls, timeout=timeout)
            hits = _results(res)
            rep["search_hits"] = len(hits)
            types = set()
            for it in hits:
                if it.get("type"):
                    types.add(str(it.get("type")))
                if _glossary_id(it):
                    rep["search_has_glossaryId"] = True
                if _bt_match(it, name)[0]:
                    rep["bt_match"] = True
            rep["search_types"] = sorted(types)[:8]
        except Exception as e:
            rep["search_error"] = str(e)[:160]
        try:
            ents = filter_entities(base_url, token, {"names": [name]}, version, verify_tls, timeout)
            rep["filter_hits"] = len(ents)
            rep["filter_types"] = sorted({str(e.get("type") or "?") for e in ents})[:8]
        except Exception as e:
            rep["filter_error"] = str(e)[:160]
        probes.append(rep)
    return probes


def stamp_ids(api_json, name_map, default_glossary_id=None):
    """Fill businessTerms[].id and glossaryId, then classify each link by its FINAL
       state (does it now carry BOTH id and glossaryId?).

       Sources, in order: (1) whatever the link already carries (the link builder
       now stamps deterministic ids), (2) PDC's resolved name->ids map, (3) a
       deterministic `default_glossary_id` for the glossary — used when a term has
       an id but neither the link nor PDC supplied a glossaryId. PDC's public API
       does not expose a term's rootId via search OR entity GET, so this last
       fallback is what actually lets a term bind to its glossary. The glossary id
       is the same UUID5 PDC preserved on import, so it is the correct value.

       Returns (resolved_json, linked_count, unresolved_names, id_only_names) and
       a 4th-tuple-friendly note: id_only now only contains terms that ended up
       with an id but STILL no glossaryId (should be empty once a default is given)."""
    unresolved = set()
    id_only = set()
    linked = 0
    for el in api_json:
        for bt in el.get("attributes", {}).get("businessTerms", []):
            m = name_map.get(bt.get("name")) or {}
            # fill id: keep an existing (deterministic) id, else take PDC's
            if not bt.get("id") and m.get("id"):
                bt["id"] = m["id"]
            # fill glossaryId: existing -> PDC -> deterministic default
            if not bt.get("glossaryId"):
                if m.get("glossaryId"):
                    bt["glossaryId"] = m["glossaryId"]
                elif default_glossary_id and bt.get("id"):
                    bt["glossaryId"] = default_glossary_id
            # classify by FINAL state, not by who supplied it
            if bt.get("id") and bt.get("glossaryId"):
                linked += 1
            elif bt.get("id"):
                id_only.add(bt.get("name"))
            else:
                unresolved.add(bt.get("name"))
    return (api_json, linked,
            sorted(n for n in unresolved if n),
            sorted(n for n in id_only if n))


# --------------------------------------------------------------------------- #
#  Entity filter + column resolution
# --------------------------------------------------------------------------- #
def filter_entities(base_url, token, filters, version="v2", verify_tls=True,
                    timeout=30, extended=True, size=500, max_pages=6):
    """POST /entities/filter. Returns the flat list of entity dicts (paginated)."""
    base = clean_base(base_url) + f"/api/public/{version}/entities/filter"
    items, cursor, pages = [], None, 0
    while pages < max_pages:
        # v2/v3 contract: cursor + size + extended are QUERY params; the body
        # carries only the filters (an in-body cursor is silently ignored and
        # would re-fetch page 1 forever on a large catalog)
        q = {"extended": str(bool(extended)).lower(), "size": size}
        if cursor:
            q["cursor"] = cursor
        url = base + "?" + urllib.parse.urlencode(q)
        out = _req("POST", url, token=token, body={"filters": filters},
                   verify_tls=verify_tls, timeout=timeout)
        items.extend(_results(out))
        cursor = _cursor(out)
        pages += 1
        if not cursor:
            break
    return items


def _path_text(ent):
    """Lower-cased haystack of the locators we can match a column/table/file against."""
    parts = [str(ent.get(k, "")) for k in ("fqdn", "fqdnDisplay", "resourceName", "name")]
    md = ent.get("metadata") if isinstance(ent.get("metadata"), dict) else {}
    f = md.get("file") if isinstance(md.get("file"), dict) else {}
    parts += [str(f.get("path", "")), str(f.get("bucket", ""))]
    return " ".join(parts).lower()


def _attrs_of(ent):
    """Current attributes block off an entity hit (extended filter returns it),
       tolerant of the 'metadata' alias."""
    a = ent.get("attributes")
    if isinstance(a, dict):
        return a
    m = ent.get("metadata")
    return m if isinstance(m, dict) else {}


# column-ish and table-ish PDC entity types (matched case-insensitively).
# Object-store leaf files are typed FILE (not OBJECT/COLUMN) and folders are
# typed DIRECTORY, so both lists must include them or document entities never
# resolve and their metadata never gets written.
_COL_TYPES = ["COLUMN", "FIELD", "OBJECT", "FILE", "RESOURCE"]
_TBL_TYPES = ["TABLE", "RESOURCE", "OBJECT", "FILE", "DATASET", "DIRECTORY"]


_FILE_TYPES = ["FILE", "OBJECT", "RESOURCE", "DIRECTORY"]


# ===========================================================================
# PDC-as-source: read the catalog the customer already built.
#
# Instead of connecting straight to the database/object store, these helpers
# pull what PDC has ALREADY scanned. The training story is "PDC is the source of
# truth; the generator reads from it." Connection SECRETS (password / secret key)
# are encrypted at rest in PDC and never returned by the API, so none of this can
# (or tries to) recover a credential.
# ===========================================================================

def _norm_data_source(d):
    """Flatten a PDC data-source record to the fields our Connections form needs,
       tolerant of nested connection/properties blocks and key aliases. Secrets
       (password/secretKey) are intentionally NOT surfaced — PDC never returns them."""
    conn = {}
    for k in ("connection", "properties", "config", "connectionDetails", "details"):
        v = d.get(k)
        if isinstance(v, dict):
            conn.update(v)
    def pick(*keys):
        for src in (d, conn):
            for k in keys:
                if src.get(k) not in (None, ""):
                    return src.get(k)
        return ""
    return {
        "id":       _eid(d) or pick("dataSourceId", "sourceId"),
        "name":     pick("name", "dataSourceName", "displayName"),
        "type":     pick("type", "dataSourceType", "sourceType", "connectionType"),
        "host":     pick("host", "hostname", "server", "endpoint"),
        "port":     pick("port"),
        "database": pick("database", "databaseName", "db", "project"),
        "schema":   pick("schema", "schemaName"),
        "bucket":   pick("bucket", "bucketName"),
        "username": pick("username", "user", "accessKey"),   # identity, not the secret
    }


# PDC's public API has NO "list all data sources" endpoint — data-sources is
# retrieve-by-id only (POST /data-sources/by-ids, GET /data-sources/{id}). So we
# discover the harvestable roots from the catalog itself via entities/filter, the
# same endpoint resolve/apply already use successfully.
_ROOT_TYPES = ["SCHEMA", "DATA_SOURCE", "DATASOURCE", "DATABASE", "RESOURCE", "DIRECTORY"]

def list_catalog_roots(base_url, token, version="v2", verify_tls=True, timeout=30):
    """Discover the catalog roots you can harvest (schemas / sources PDC already
       scanned) via POST /entities/filter. Returns id, name, type and fqdn so the
       picker can show them and harvest can scope to one.

       NOTE: distinct from list_data_sources() below, which returns the raw
       data-source *configuration* records (for the CSV round-trip). This one
       returns the shaped catalog roots the harvest picker renders."""
    ents = filter_entities(base_url, token, {"types": _ROOT_TYPES}, version=version,
                           verify_tls=verify_tls, timeout=timeout)
    out, seen = [], set()
    for e in ents:
        fq = str(e.get("fqdn") or "")
        name = e.get("name") or e.get("fqdnDisplay") or fq
        key = fq or name
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"id": _eid(e) or fq, "name": name, "type": e.get("type") or "",
                    "fqdn": fq, "fqdnDisplay": e.get("fqdnDisplay") or ""})
    return out


def _split_entity_path(ent):
    """Best-effort (schema, table, column) for a COLUMN entity. Prefers explicit
       fields, else parses the human-readable path, e.g.
       'mssql:adventureworks2022/HumanResources/Employee/FirstName'
       -> ('HumanResources', 'Employee', 'FirstName')."""
    a = _attrs_of(ent)
    col = ent.get("columnName") or a.get("columnName") or ""
    tbl = ent.get("tableName")  or a.get("tableName")  or ""
    sch = ent.get("schemaName") or a.get("schemaName") or ""
    if not (col and tbl):
        s = str(ent.get("fqdnDisplay") or ent.get("fqdn") or ent.get("name") or "")
        head, sep, rest = s.partition("/")
        if sep and ":" in head:      # leading "<source>:<db>" segment -> drop it
            s = rest
        parts = [p for p in s.split("/") if p]
        if parts:
            col = col or parts[-1]
            tbl = tbl or (parts[-2] if len(parts) >= 2 else "")
            sch = sch or (parts[-3] if len(parts) >= 3 else "")
    return sch, tbl, (col or ent.get("name") or "")


def _aget(a, *keys):
    """First non-empty value among attribute key aliases."""
    for k in keys:
        v = a.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _col_meta(ent):
    """Pull the real column-metadata blocks off a PDC entity (the public-API shape):
       metadata.column.*, attributes.info.*, attributes.features.*, businessTerms[].
       Flat keys are still read as a fallback so simpler payloads also work."""
    md = ent.get("metadata") if isinstance(ent.get("metadata"), dict) else {}
    col = md.get("column") if isinstance(md.get("column"), dict) else {}
    attrs = ent.get("attributes") if isinstance(ent.get("attributes"), dict) else {}
    info = attrs.get("info") if isinstance(attrs.get("info"), dict) else {}
    feats = attrs.get("features") if isinstance(attrs.get("features"), dict) else {}
    bts = attrs.get("businessTerms") if isinstance(attrs.get("businessTerms"), list) else []
    return col, info, feats, attrs, bts


def _source_match(ent, ds_name):
    """True if a source name appears anywhere in the entity's locators/attrs."""
    dl = ds_name.lower()
    if dl in _path_text(ent):
        return True
    a = _attrs_of(ent)
    return dl in " ".join(str(a.get(k, "")) for k in
                          ("dataSource", "dataSourceName", "source", "sourceName")).lower()


def _under_root(ent, root_id, root_name):
    """Scope a COLUMN entity to a chosen catalog root by fqdn prefix or name."""
    if not root_id and not root_name:
        return True                       # no scope -> take everything
    fq = str(ent.get("fqdn") or "")
    if root_id and (fq == root_id or fq.startswith(root_id.rstrip("/") + "/") or root_id in fq):
        return True
    if root_name and _source_match(ent, root_name):
        return True
    return False


def _file_record(ent):
    """Map a PDC FILE/OBJECT entity to the file-dict suggest_document_files consumes.
       Returns (record, bucket) or (None, '') for folders / non-leaf containers."""
    md = ent.get("metadata") if isinstance(ent.get("metadata"), dict) else {}
    mf = md.get("file") if isinstance(md.get("file"), dict) else {}
    bucket = mf.get("bucket") or ""
    ext = str(mf.get("extension") or "").lstrip(".")
    path = str(mf.get("path") or ent.get("fqdnDisplay") or ent.get("fqdn") or ent.get("name") or "")
    disp = path.replace("\\", "/")
    head, sep, rest = disp.partition("/")
    if sep and ":" in head:                       # drop "s3:bucket" / "minio:bucket" prefix
        disp = rest
    parts = [p for p in disp.split("/") if p]
    base = ent.get("name") or ent.get("resourceName") or (parts[-1] if parts else "")
    if not base:
        return None, ""
    if not ext and "." in base:
        ext = base.rsplit(".", 1)[-1]
    etype = str(ent.get("type") or "").upper()
    if etype in ("DIRECTORY", "FOLDER") or not ext:   # containers have no leaf extension
        return None, ""
    folder = parts[-2] if len(parts) >= 2 else "(root)"
    a = _attrs_of(ent)
    info = a.get("info") if isinstance(a.get("info"), dict) else {}
    owner = info.get("owner") or _aget(a, "owner", "createdBy") or ""
    return {"folder": folder, "base": base, "bucket": bucket, "ext": ext,
            "owner": owner, "recent": False}, bucket


def harvest_from_catalog(base_url, token, ds_id=None, ds_name=None, version="v2",
                         verify_tls=True, timeout=40, max_pages=12):
    """Read what PDC has ALREADY cataloged for a source (via POST /entities/filter)
       and reshape it into the structures the suggester consumes — with NO direct
       database/object-store access and no secret.

       Handles both kinds of source:
         - databases  -> COLUMN entities -> {table: [column-dict]} for suggest()
         - object/doc stores -> FILE entities -> file-dicts for suggest_document_files()
       Also overlays what PDC already governs (sensitivity, trust, business terms),
       keyed to match each row's Source_Column.

       Returns (tables, files, overlay, summary)."""
    overlay, governed = {}, 0
    # governance breakdown — the scan/discovery RESULT view, per entity:
    # identified = Data Identification stamped a sensitivity; trust_scored / term_linked /
    # tagged likewise. sens_dist buckets the identified sensitivities.
    gov = {"identified": 0, "trust_scored": 0, "term_linked": 0, "tagged": 0,
           "sens_dist": {}}
    def _tally(sens, trust, terms, attrs):
        if sens:
            gov["identified"] += 1
            key = str(sens).upper()
            gov["sens_dist"][key] = gov["sens_dist"].get(key, 0) + 1
        if trust is not None:
            gov["trust_scored"] += 1
        if terms:
            gov["term_linked"] += 1
        tags = attrs.get("tags") if isinstance(attrs, dict) else None
        if isinstance(tags, list) and any(
                (t.get("name") if isinstance(t, dict) else t) for t in tags):
            gov["tagged"] += 1

    # --- databases: COLUMN entities ---------------------------------------
    col_ents = filter_entities(base_url, token, {"types": ["COLUMN"]}, version=version,
                               verify_tls=verify_tls, timeout=timeout, max_pages=max_pages)
    tables = {}
    for e in col_ents:
        if not _under_root(e, ds_id, ds_name):
            continue
        sch, tbl, col = _split_entity_path(e)
        if not (tbl and col):
            continue
        col_md, info, feats, attrs, bts = _col_meta(e)
        keytype = str(_aget(attrs, "keyType", "constraintType") or "").upper()
        nullable = col_md.get("isNullable")
        tables.setdefault(tbl, []).append({
            "table": tbl, "column": col, "schema": sch,
            "type": (col_md.get("dataType") or col_md.get("sqlDataType") or col_md.get("typeName")
                     or _aget(attrs, "dataType", "type", "columnType", "datatype") or ""),
            "pk": bool(col_md.get("isPrimaryKey")) or bool(_aget(attrs, "isPrimaryKey", "primaryKey"))
                  or keytype in ("PRIMARY", "PK"),
            "fk": bool(col_md.get("isForeignKey")) or bool(_aget(attrs, "isForeignKey", "foreignKey"))
                  or keytype in ("FOREIGN", "FK"),
            "notnull": (nullable is False) or (str(_aget(attrs, "nullable")).lower() == "false")
                       or bool(_aget(attrs, "notNull")),
            "unique": bool(_aget(attrs, "unique", "isUnique")),
            "comment": (info.get("description") or info.get("definition") or col_md.get("remarks")
                        or _aget(attrs, "description", "comment", "businessDescription", "definition") or ""),
        })
        sens = feats.get("sensitivity") or _aget(attrs, "sensitivity", "sensitivityLevel", "dataSensitivity")
        trust = feats.get("trustScore")
        if trust is None:
            trust = _aget(attrs, "trustScore", "trust", "trust_score")
        terms = [t for t in ((t.get("name") if isinstance(t, dict) else t) for t in bts) if t]
        _tally(sens, trust, terms, attrs)
        is_gov = bool(sens or (trust is not None) or terms)
        governed += 1 if is_gov else 0
        overlay[f"{tbl}.{col}".lower()] = {"sensitivity": sens, "trust": trust, "terms": terms, "governed": is_gov}

    # --- object / document stores: FILE entities --------------------------
    file_ents = filter_entities(base_url, token, {"types": ["FILE", "OBJECT", "RESOURCE"]},
                                version=version, verify_tls=verify_tls, timeout=timeout, max_pages=max_pages)
    scoped = [e for e in file_ents if _under_root(e, ds_id, ds_name)]
    # If scoping a document source returns nothing (PDC fqdn hierarchy may not prefix
    # cleanly), but the source has no columns either, fall back to all file entities so
    # the user still sees the documents they picked.
    use = scoped if scoped else (file_ents if not tables else [])
    files, bucket = [], ""
    for e in use:
        rec, bkt = _file_record(e)
        if not rec:
            continue
        files.append(rec)
        bucket = bucket or bkt
        col_md, info, feats, attrs, bts = _col_meta(e)
        sens = feats.get("sensitivity") or _aget(attrs, "sensitivity", "sensitivityLevel")
        trust = feats.get("trustScore")
        if trust is None:
            trust = _aget(attrs, "trustScore", "trust")
        terms = [t for t in ((t.get("name") if isinstance(t, dict) else t) for t in bts) if t]
        _tally(sens, trust, terms, attrs)
        is_gov = bool(sens or (trust is not None) or terms)
        governed += 1 if is_gov else 0
        bkt2 = rec["bucket"] or bucket or "documents"
        src = (f"{bkt2}/{rec['folder']}/{rec['base']}" if rec["folder"] != "(root)"
               else f"{bkt2}/{rec['base']}")
        overlay[src.lower()] = {"sensitivity": sens, "trust": trust, "terms": terms, "governed": is_gov}

    summary = {"tables": len(tables), "columns": sum(len(v) for v in tables.values()),
               "files": len(files), "bucket": bucket,
               "already_governed": governed,
               "governance": gov,
               "source": ds_name or ds_id or "all data sources"}
    return tables, files, overlay, summary


def glossary_exists(base_url, token, name, version="v2", verify_tls=True, timeout=20):
    """Search PDC for a business glossary with this name BEFORE importing, so the UI
       can offer update-vs-create instead of silently creating a duplicate glossary.
       Returns {exists, exact, id, name, matches}."""
    surl = clean_base(base_url) + f"/api/public/{version}/search"
    out = _req("POST", surl, token=token, body={"searchTerm": name, "perPage": 50},
               verify_tls=verify_tls, timeout=timeout)
    want = (name or "").strip().lower()
    matches = []
    for it in _results(out):
        t = str(it.get("type") or it.get("entityType") or "").upper().replace("-", " ").replace("_", " ")
        if "GLOSSARY" in t:
            matches.append({"id": _eid(it), "name": str(it.get("name") or "").strip(), "type": t})
    exact = next((m for m in matches if m["name"].lower() == want), None)
    chosen = exact or (matches[0] if matches else None)
    return {"exists": bool(chosen), "exact": bool(exact),
            "id": chosen["id"] if chosen else None,
            "name": chosen["name"] if chosen else None,
            "matches": matches}


def _resolve_object_entity(base_url, token, rec, version="v2", verify_tls=True, timeout=30):
    """Resolve an object-store record (bucket=schemaName, folder=tableName,
       file=columnName, type OBJECT/FILE) to its PDC FILE/OBJECT entity.

       Files are not COLUMNs, so the generic column resolver's name+table logic
       can miss them. Here we scope by the bucket and match the file name with or
       without its extension (PDC may store either), requiring the bucket — and the
       folder when present — in the entity path. Returns the entity dict or None.

       A None here usually means the file has not been ingested/profiled into PDC
       yet (run Data Discovery on the document store first), not that the name is
       wrong."""
    bucket = (rec.get("schemaName") or "").strip()
    folder = (rec.get("tableName") or "").strip()
    fname = (rec.get("columnName") or "").strip()
    if not fname:
        return None
    stem = fname.rsplit(".", 1)[0] if "." in fname else fname
    want = {fname.lower(), stem.lower()}

    # filters, most precise first: bucket-scoped exact name, then name+file-types
    filters = []
    if bucket:
        filters.append({"buckets": [bucket], "names": [fname]})
        if stem != fname:
            filters.append({"buckets": [bucket], "names": [stem]})
    filters.append({"names": [fname], "types": list(dict.fromkeys(_FILE_TYPES))})
    if stem != fname:
        filters.append({"names": [stem], "types": list(dict.fromkeys(_FILE_TYPES))})

    for f in filters:
        try:
            hits = filter_entities(base_url, token, f, version, verify_tls, timeout)
        except Exception:
            hits = []
        cands = []
        for e in hits:
            nm = str(e.get("name", "")).strip().lower()
            if nm not in want and not nm.startswith(stem.lower()):
                continue
            p = _path_text(e)
            if bucket and bucket.lower() not in p:
                continue
            cands.append(e)
        if cands:
            if folder:                       # prefer a hit whose path also has the folder
                infolder = [e for e in cands if folder.lower() in _path_text(e)]
                if infolder:
                    return infolder[0]
            return cands[0]
    return None


def resolve_column_entity(base_url, token, rec, version="v2", verify_tls=True,
                          timeout=30, _table_cache=None):
    """Resolve a Data Element record (schemaName/tableName/columnName/type) to its
       PDC column entity. Returns the entity dict (with _id + attributes) or None.

       Strategy, most-direct first:
         1) fqdn match  - if the record already carries an fqdn, filter by it.
         2) name match  - filter names:[column] types:[COLUMN..], then disambiguate
                          by requiring the table (and schema, if given) in the path.
         3) parent walk - resolve the table entity, then list its child columns by
                          parentIds and match on name. Unambiguous; table lookups
                          are cached across records."""
    col = (rec.get("columnName") or "").strip()
    tbl = (rec.get("tableName") or "").strip()
    sch = (rec.get("schemaName") or "").strip()
    rtype = (rec.get("type") or "COLUMN").upper()
    if not col:
        return None
    cache = _table_cache if _table_cache is not None else {}

    # object-store files (and folders) are resolved by bucket + file name, not by
    # the column/table logic below — they are FILE/OBJECT entities, not COLUMNs.
    if rtype in ("OBJECT", "FILE", "RESOURCE", "DIRECTORY"):
        oe = _resolve_object_entity(base_url, token, rec, version, verify_tls, timeout)
        if oe and _eid(oe):
            return oe
        # fall through to the generic logic only as a last resort

    def _has_table(ent):
        """True when a candidate entity's path contains the wanted table (and schema, if given); disambiguates same-named columns."""
        p = _path_text(ent)
        ok = (tbl.lower() in p) if tbl else True
        if sch:
            ok = ok and (sch.lower() in p)
        return ok

    # 1) direct fqdn
    fqdn = (rec.get("fqdn") or "").strip()
    if fqdn:
        for e in filter_entities(base_url, token, {"fqdns": [fqdn]}, version,
                                 verify_tls, timeout):
            if str(e.get("name", "")).strip().lower() == col.lower():
                return e

    # 2) name + type, disambiguated by the table/schema in the path
    types = list(dict.fromkeys([rtype] + _COL_TYPES))
    hits = filter_entities(base_url, token, {"names": [col], "types": types},
                           version, verify_tls, timeout)
    named = [e for e in hits if str(e.get("name", "")).strip().lower() == col.lower()]
    scoped = [e for e in named if _has_table(e)]
    if len(scoped) == 1:
        return scoped[0]
    if len(named) == 1 and not tbl:
        return named[0]

    # 3) resolve the table, then walk its columns by parentId
    tkey = (sch.lower(), tbl.lower())
    tid = cache.get(tkey)
    if tid is None and tbl:
        t_hits = filter_entities(base_url, token,
                                 {"names": [tbl], "types": list(dict.fromkeys(_TBL_TYPES))},
                                 version, verify_tls, timeout)
        t_named = [e for e in t_hits if str(e.get("name", "")).strip().lower() == tbl.lower()]
        t_scoped = [e for e in t_named if (not sch) or sch.lower() in _path_text(e)]
        pick = (t_scoped or t_named)
        tid = _eid(pick[0]) if pick else ""
        cache[tkey] = tid
    if tid:
        cols = filter_entities(base_url, token,
                               {"parentIds": [tid], "types": list(dict.fromkeys(_COL_TYPES))},
                               version, verify_tls, timeout)
        exact = [e for e in cols if str(e.get("name", "")).strip().lower() == col.lower()]
        if exact:
            return exact[0]

    # fall back to a unique scoped/name hit if we got here
    if len(scoped) > 1:
        return scoped[0]
    if len(named) == 1:
        return named[0]
    return None


def get_entity(base_url, token, eid, version="v2", verify_tls=True, timeout=30):
    """GET a single entity by id (extended) and return its dict, or None on failure."""
    url = clean_base(base_url) + f"/api/public/{version}/entities/{eid}"
    out = _req("GET", url, token=token, verify_tls=verify_tls, timeout=timeout)
    e = out.get("data", out)
    if isinstance(e, list):
        e = e[0] if e else {}
    return e if isinstance(e, dict) else {}


def resolve_table_entity(base_url, token, schema, table, version="v2",
                         verify_tls=True, timeout=30):
    """Resolve a (schema, table) pair to its PDC table entity. Filters by name +
       table-ish types, then requires the schema in the path to disambiguate.
       Returns the entity dict (with _id + attributes) or None."""
    tbl = (table or "").strip()
    sch = (schema or "").strip()
    if not tbl:
        return None
    hits = filter_entities(base_url, token,
                           {"names": [tbl], "types": list(dict.fromkeys(_TBL_TYPES))},
                           version, verify_tls, timeout)
    named = [e for e in hits if str(e.get("name", "")).strip().lower() == tbl.lower()]
    scoped = [e for e in named if (not sch) or sch.lower() in _path_text(e)]
    pick = (scoped or named)
    return pick[0] if pick else None


# --------------------------------------------------------------------------- #
#  Merge (client-side) - server full-replaces arrays, so we send the superset
# --------------------------------------------------------------------------- #
def _term_key(bt):
    """Stable de-dupe key for a businessTerm. Keys on the term NAME so a term that
       was previously attached by name only (no id) and the same term freshly
       resolved (carrying id + glossaryId) UNIFY into one entry — the resolved
       id/glossaryId overlay the name-only stub instead of creating a duplicate,
       unlinked second copy. Falls back to id only when somehow nameless."""
    return str(bt.get("name") or bt.get("id") or "").strip().lower()


# PDC's PATCH schema for businessTerms[] is strict: any key it does not recognise
# (notably the app-internal 'glossary' name we carry for display/grouping) makes
# the whole PATCH fail with a 400. So every term is whitelisted down to the
# properties PDC actually accepts before it goes into the body.
_BT_KEYS = ("id", "glossaryId", "name", "sourceName", "sourceType", "confidenceScore")


def _clean_term(bt):
    """Strip a businessTerm dict to PDC's accepted PATCH keys.

    Drops 'glossary' and any other app-internal fields, keeping only the
    whitelisted keys that have a real value. The merge keys terms on id-or-name,
    so at least one of those is always present - the link still resolves."""
    if not isinstance(bt, dict):
        return bt
    return {k: bt[k] for k in _BT_KEYS if bt.get(k) not in (None, "")}


def merge_attributes(current, incoming):
    """Merge incoming businessTerms + features onto the column's current attributes.
       businessTerms: union by id-or-name (incoming overlays so resolved ids land).
       features: object-merge (incoming keys overwrite). Other incoming keys overwrite.
       Returns the attributes block to send in the PATCH body."""
    cur = current if isinstance(current, dict) else {}
    inc = incoming if isinstance(incoming, dict) else {}
    out = {}

    # businessTerms: keep existing, overlay/append incoming by key
    cur_terms = cur.get("businessTerms") or []
    inc_terms = inc.get("businessTerms") or []
    merged = {}
    order = []
    for bt in cur_terms:
        k = _term_key(bt)
        if k and k not in merged:
            merged[k] = dict(bt); order.append(k)
    for bt in inc_terms:
        k = _term_key(bt)
        if not k:
            continue
        if k in merged:
            merged[k].update({kk: vv for kk, vv in bt.items() if vv not in (None, "")})
        else:
            merged[k] = dict(bt); order.append(k)
    if inc_terms or cur_terms:
        # whitelist each term to PDC's accepted PATCH keys (drops 'glossary' etc.)
        out["businessTerms"] = [_clean_term(merged[k]) for k in order]

    # features: union (current then incoming overlay)
    cur_f = cur.get("features") if isinstance(cur.get("features"), dict) else {}
    inc_f = inc.get("features") if isinstance(inc.get("features"), dict) else {}
    if cur_f or inc_f:
        f = dict(cur_f)
        for k, v in inc_f.items():
            if v not in (None, ""):
                f[k] = v
        out["features"] = f

    # extended: object-merge (current then incoming overlay), so key facts land
    # without clobbering unrelated extended attributes already on the entity
    cur_e = cur.get("extended") if isinstance(cur.get("extended"), dict) else {}
    inc_e = inc.get("extended") if isinstance(inc.get("extended"), dict) else {}
    if cur_e or inc_e:
        e = dict(cur_e)
        e.update({k: v for k, v in inc_e.items() if v is not None})
        out["extended"] = e

    # any other incoming attribute keys overwrite
    for k, v in inc.items():
        if k in ("businessTerms", "features", "extended"):
            continue
        out[k] = v
    return out


# --------------------------------------------------------------------------- #
#  Apply to PDC (resolve -> merge -> PATCH), with dry-run
# --------------------------------------------------------------------------- #
def _retry_auth(fn, reauth):
    """Run fn(token); on TokenExpired, call reauth() for a fresh token and retry once."""
    try:
        return fn(None)
    except TokenExpired:
        if not reauth:
            raise
        new_tok = reauth()
        return fn(new_tok)


_SENS_UP = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_SENS_DN = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}


def apply_to_pdc(base_url, token, api_json, version="v2", verify_tls=True,
                 timeout=30, dry_run=True, reauth=None, calculate_trust=False,
                 apply_table_ratings=True, table_lineage_verified=True,
                 skip_unresolved_terms=False, glossary_name=None,
                 default_glossary_id=None, desc_mode="fill", table_terms=None,
                 progress=None):
    """For each Data Element record: resolve the column entity, merge attributes,
       and PATCH (unless dry_run). Returns a structured report.

       When apply_table_ratings is set, each table touched also gets a rating
       PATCHed onto its own entity — the mean of its columns' scan-suggested
       ratings — plus verified lineage, so the table-level Trust Score (which PDC
       rolls up at the Table/File level) has its inputs. The trust-score job is
       then scoped to those table ids rather than the columns.

       reauth: optional zero-arg callable returning a fresh token on 401."""
    results = []
    touched_ids = []
    table_cache = {}
    table_ratings = {}   # (schema, table) -> [rating values from columns]
    table_quality = {}   # (schema, table) -> [qualityScore values from columns]
    table_sens = {}      # (schema, table) -> max column sensitivity rank
    object_store_keys = set()  # (bucket, folder) keys whose elements are object-store
                               # FILES — the file is the Trust-Score unit, not the folder
    unresolved_term_names = set()   # term links carrying a name but no glossaryId
    resolved_on_apply = 0           # how many we had to resolve here (Resolve was skipped)
    cur_token = {"t": token}

    base = clean_base(base_url)

    # SELF-HEAL: a businessTerm only links to its glossary in PDC when it carries
    # BOTH id and glossaryId. If the user skipped the Resolve step (or re-pulled the
    # links, which clears them), those are blank and PDC attaches the term by NAME
    # ONLY — the Glossary column then shows "—" and the term is not counted toward
    # the table Trust Score. So before applying, resolve any term still missing an
    # id/glossaryId now (idempotent; costs nothing when everything is already
    # resolved) and stamp the ids in place.
    _need = sorted({(t.get("name") or "").strip()
                    for rec in api_json
                    for t in ((rec.get("attributes") or {}).get("businessTerms") or [])
                    if t.get("name") and not (t.get("id") and t.get("glossaryId"))})
    if _need:
        try:
            def _res(tok):
                if tok:
                    cur_token["t"] = tok
                return resolve_terms(base, cur_token["t"], _need, glossary_name,
                                     version=version, verify_tls=verify_tls, timeout=timeout)
            _tmap = _retry_auth(_res, reauth) or {}
        except Exception:
            _tmap = {}
        for rec in api_json:
            for t in ((rec.get("attributes") or {}).get("businessTerms") or []):
                m = _tmap.get((t.get("name") or "").strip())
                if m:
                    if not t.get("id") and m.get("id"):
                        t["id"] = m["id"]
                    if not t.get("glossaryId") and m.get("glossaryId"):
                        t["glossaryId"] = m["glossaryId"]
                # PDC won't return a term's glossaryId — fill the deterministic one
                # (the glossary id PDC preserved on import) for any id-bearing term.
                if default_glossary_id and t.get("id") and not t.get("glossaryId"):
                    t["glossaryId"] = default_glossary_id
                if t.get("id") and t.get("glossaryId"):
                    resolved_on_apply += 1

    def _rating_of(attrs):
        """Pull an integer rating value out of an attributes block, or None when absent."""
        r = ((attrs or {}).get("features") or {}).get("rating") or {}
        v = r.get("value")
        return int(v) if isinstance(v, (int, float)) and v else None

    def _quality_of(attrs):
        """Pull an integer qualityScore out of an attributes block, or None when absent."""
        v = ((attrs or {}).get("features") or {}).get("qualityScore")
        return int(v) if isinstance(v, (int, float)) else None

    _ap_total = len(api_json)
    for _ap_i, rec in enumerate(api_json):
        col_label = ".".join(x for x in [rec.get("schemaName"), rec.get("tableName"),
                                         rec.get("columnName")] if x)
        if progress:
            try:
                progress({"phase": "column", "done": _ap_i, "total": _ap_total,
                          "column": col_label or rec.get("columnName") or rec.get("name") or ""})
            except Exception:
                pass
        incoming_attrs = rec.get("attributes") or {}
        # A term link only binds to a glossary when it carries a glossaryId (stamped
        # by Resolve after the glossary is imported). Without it PDC attaches the
        # name only and the Glossary column shows "—". Track these; optionally drop
        # them so Apply never writes an unlinked, glossary-less association.
        bts = incoming_attrs.get("businessTerms") or []
        unlinked = [t for t in bts if not (t.get("glossaryId") and t.get("id"))]
        for t in unlinked:
            if t.get("name"):
                unresolved_term_names.add(t["name"])
        if skip_unresolved_terms and unlinked:
            kept = [t for t in bts if t.get("glossaryId") and t.get("id")]
            incoming_attrs = dict(incoming_attrs)
            incoming_attrs["businessTerms"] = kept
        row = {"column": col_label, "type": rec.get("type"), "found": False,
               "id": None, "fqdn": None, "status": "pending", "message": ""}
        try:
            # resolve the column entity (re-auth aware)
            def _resolve(tok):
                """Resolve the current record's column/file entity, re-authenticating on a 401."""
                t = tok or cur_token["t"]
                if tok:
                    cur_token["t"] = tok
                return resolve_column_entity(base, cur_token["t"], rec, version,
                                             verify_tls, timeout, table_cache)
            ent = _retry_auth(_resolve, reauth)
            if not ent or not _eid(ent):
                row["status"] = "not-found"
                if (rec.get("type") or "").upper() in ("OBJECT", "FILE", "RESOURCE", "DIRECTORY"):
                    row["message"] = ("no matching file entity — profile the document "
                                      "store in PDC first (Step 4 / Data Discovery), then re-apply")
                else:
                    row["message"] = "no matching column entity in PDC"
                results.append(row)
                continue
            eid = _eid(ent)
            row.update(found=True, id=eid, fqdn=ent.get("fqdn") or ent.get("fqdnDisplay"))

            # current attributes: prefer what the extended filter returned, else GET
            current = _attrs_of(ent)
            if not current.get("businessTerms") and not current.get("features"):
                def _get(tok):
                    """GET the current entity's full attributes, re-authenticating on a 401."""
                    t = tok or cur_token["t"]
                    if tok:
                        cur_token["t"] = tok
                    return get_entity(base, cur_token["t"], eid, version, verify_tls, timeout)
                try:
                    full = _retry_auth(_get, reauth)
                    current = _attrs_of(full) or current
                except Exception:
                    pass

            merged = merge_attributes(current, incoming_attrs)
            # entity description: honor the mode. "fill" writes only where PDC
            # has none; "overwrite" replaces; "off" never sends info at all.
            inc_desc = ((incoming_attrs.get("info") or {}).get("description") or "").strip()
            cur_desc = ((current.get("info") or {}).get("description") or "").strip()
            if desc_mode == "off" or not inc_desc or (desc_mode != "overwrite" and cur_desc):
                merged.pop("info", None)
            else:
                merged["info"] = {"description": inc_desc}
            body = {"attributes": merged}
            row["body"] = body
            row["current_terms"] = [t.get("name") for t in (current.get("businessTerms") or [])]
            row["merged_terms"] = [t.get("name") for t in merged.get("businessTerms", [])]

            # remember this column's suggested rating so we can roll it up to the table
            is_obj = (rec.get("type") or "").upper() in ("OBJECT", "FILE", "RESOURCE", "DIRECTORY")
            rv = _rating_of(incoming_attrs)
            if rv:
                tkey = ((rec.get("schemaName") or ""), (rec.get("tableName") or ""))
                if is_obj:
                    object_store_keys.add(tkey)
                table_ratings.setdefault(tkey, []).append(rv)
            sv = str(((incoming_attrs.get("features") or {}).get("sensitivity")) or "").upper()
            if sv in _SENS_UP:
                tkey = ((rec.get("schemaName") or ""), (rec.get("tableName") or ""))
                if is_obj:
                    object_store_keys.add(tkey)
                table_sens[tkey] = max(table_sens.get(tkey, 0), _SENS_UP[sv])
            qv = _quality_of(incoming_attrs)
            if qv is not None:
                tkey = ((rec.get("schemaName") or ""), (rec.get("tableName") or ""))
                if is_obj:
                    object_store_keys.add(tkey)
                table_quality.setdefault(tkey, []).append(qv)

            if dry_run:
                row["status"] = "planned"
                touched_ids.append(eid)
                results.append(row)
                continue

            # APPLY
            purl = base + f"/api/public/{version}/entities/{eid}"
            def _patch(tok):
                """PATCH the merged attributes onto the current entity, re-authenticating on a 401."""
                t = tok or cur_token["t"]
                if tok:
                    cur_token["t"] = tok
                return _req("PATCH", purl, token=cur_token["t"], body=body,
                            verify_tls=verify_tls, timeout=timeout)
            _retry_auth(_patch, reauth)
            row["status"] = "applied"
            touched_ids.append(eid)
        except Exception as e:
            row["status"] = "error"
            row["message"] = str(e)[:300]
        results.append(row)

    if progress:
        try: progress({"phase": "columns-done", "done": _ap_total, "total": _ap_total})
        except Exception: pass

    # ---- table-level rollup: roll up column ratings + DQ qualityScore onto tables ----
    table_results = []
    table_ids = []
    table_keys = set(table_ratings) | set(table_quality) | set(table_sens)
    if table_terms:
        # a table-level term may exist for a table none of whose columns carried
        # a rating (e.g. all LOW) — make sure that table still gets its term
        named = {t.lower() for t in table_terms}
        for rec0 in api_json:
            tk = ((rec0.get("schemaName") or ""), (rec0.get("tableName") or ""))
            if (rec0.get("tableName") or "").lower() in named:
                table_keys.add(tk)
    if apply_table_ratings and table_keys:
        if progress:
            try: progress({"phase": "tables", "total": len(table_keys)})
            except Exception: pass
        for (sch, tbl) in table_keys:
            rvals = table_ratings.get((sch, tbl)) or []
            qvals = table_quality.get((sch, tbl)) or []
            srank = table_sens.get((sch, tbl))
            ttinfo = (table_terms or {}).get((tbl or "").lower())
            if not rvals and not qvals and not srank and not ttinfo:
                continue
            mean_rating = max(1, min(5, int(round(sum(rvals) / len(rvals))))) if rvals else None
            mean_quality = max(0, min(100, int(round(sum(qvals) / len(qvals))))) if qvals else None
            trow = {"table": ".".join(x for x in [sch, tbl] if x) or tbl,
                    "rating": mean_rating, "from_columns": len(rvals),
                    "quality": mean_quality, "quality_from": len(qvals),
                    "found": False, "id": None, "status": "pending", "message": ""}
            # Object stores: the FILE is the Trust-Score-bearing entity (per PDC, Trust
            # Score is for Tables and Files only), and each file already received its
            # rating / DQ / verified-lineage / term in the per-element apply above. A
            # folder is neither a table nor a Trust Score target, so there is nothing to
            # roll up to — report that honestly instead of as a "table not found".
            if (sch, tbl) in object_store_keys:
                # Trust Score stays per file, but the FOLDER entity can still
                # carry the roll-up (rating, DQ, sensitivity) so the canvas
                # isn't blank at folder level. Folders never join the trust
                # scope and never take the table term.
                nfiles = max(len(rvals), len(qvals), 1)
                try:
                    def _rdir(tok):
                        t = tok or cur_token["t"]
                        if tok:
                            cur_token["t"] = tok
                        return resolve_table_entity(base, cur_token["t"], sch, tbl,
                                                    version, verify_tls, timeout)
                    dent = _retry_auth(_rdir, reauth)
                    if not dent or not _eid(dent):
                        trow.update(status="file-level", found=False,
                                    message=(f"{nfiles} file(s) applied directly; no matching "
                                             f"folder entity to roll up to"))
                        table_results.append(trow)
                        continue
                    dfeat = {}
                    if mean_rating is not None:
                        dfeat["rating"] = {"value": mean_rating}
                    if mean_quality is not None:
                        dfeat["qualityScore"] = mean_quality
                    if srank:
                        dfeat["sensitivity"] = _SENS_DN[srank]
                    dbody = {"attributes": {"features": dfeat}}
                    trow.update(found=True, id=_eid(dent),
                                fqdn=dent.get("fqdn") or dent.get("fqdnDisplay"), body=dbody,
                                message=(f"folder roll-up from {nfiles} file(s); Trust Score "
                                         f"stays per file"))
                    if dry_run:
                        trow["status"] = "planned"
                    else:
                        durl = base + f"/api/public/{version}/entities/{_eid(dent)}"
                        def _dpatch(tok):
                            t = tok or cur_token["t"]
                            if tok:
                                cur_token["t"] = tok
                            return _req("PATCH", durl, token=cur_token["t"], body=dbody,
                                        verify_tls=verify_tls, timeout=timeout)
                        _retry_auth(_dpatch, reauth)
                        trow["status"] = "applied"
                except Exception as e:
                    trow["status"] = "error"
                    trow["message"] = str(e)[:300]
                table_results.append(trow)
                continue
            try:
                def _rtbl(tok):
                    """Resolve the (schema, table) entity for the rating/quality rollup, re-authenticating on a 401."""
                    t = tok or cur_token["t"]
                    if tok:
                        cur_token["t"] = tok
                    return resolve_table_entity(base, cur_token["t"], sch, tbl,
                                                version, verify_tls, timeout)
                tent = _retry_auth(_rtbl, reauth)
                if not tent or not _eid(tent):
                    trow["status"] = "not-found"
                    trow["message"] = "no matching table entity in PDC"
                    table_results.append(trow)
                    continue
                tid = _eid(tent)
                tfeat = {}
                if mean_rating is not None:
                    tfeat["rating"] = {"value": mean_rating}
                if mean_quality is not None:
                    tfeat["qualityScore"] = mean_quality
                if srank:
                    tfeat["sensitivity"] = _SENS_DN[srank]
                if table_lineage_verified:
                    tfeat["isLineageVerified"] = True
                tattrs = {"features": tfeat}
                if ttinfo:
                    # the table's OWN business term (Trust Score's assigned-term
                    # input) — union-merged with whatever the table already has
                    bt = {"name": ttinfo["name"]}
                    if ttinfo.get("id"):
                        bt["id"] = ttinfo["id"]
                    if ttinfo.get("glossaryId"):
                        bt["glossaryId"] = ttinfo["glossaryId"]
                    if not (skip_unresolved_terms and not (bt.get("id") and bt.get("glossaryId"))):
                        tattrs["businessTerms"] = [bt]
                    tdesc = (ttinfo.get("description") or "").strip()
                    cur_t = _attrs_of(tent)
                    cur_tdesc = ((cur_t.get("info") or {}).get("description") or "").strip()
                    if tdesc and desc_mode != "off" and (desc_mode == "overwrite" or not cur_tdesc):
                        tattrs["info"] = {"description": tdesc}
                    tattrs = merge_attributes(cur_t, tattrs)
                    if "info" in tattrs and not ((tattrs.get("info") or {}).get("description") or "").strip():
                        tattrs.pop("info", None)
                tbody = {"attributes": tattrs}
                trow["term"] = (ttinfo or {}).get("name")
                trow["sensitivity"] = _SENS_DN.get(srank)
                trow.update(found=True, id=tid,
                            fqdn=tent.get("fqdn") or tent.get("fqdnDisplay"), body=tbody)
                if dry_run:
                    trow["status"] = "planned"
                    table_ids.append(tid)
                    table_results.append(trow)
                    continue
                turl = base + f"/api/public/{version}/entities/{tid}"
                def _tpatch(tok):
                    """PATCH the rolled-up rating/quality/verified-lineage onto the table entity, re-authenticating on a 401."""
                    t = tok or cur_token["t"]
                    if tok:
                        cur_token["t"] = tok
                    return _req("PATCH", turl, token=cur_token["t"], body=tbody,
                                verify_tls=verify_tls, timeout=timeout)
                _retry_auth(_tpatch, reauth)
                trow["status"] = "applied"
                table_ids.append(tid)
            except Exception as e:
                trow["status"] = "error"
                trow["message"] = str(e)[:300]
            table_results.append(trow)

    # If term links are STILL unresolved after the self-heal pass, probe PDC so the
    # Apply result can explain WHY (same diagnostic as the Resolve step) — whether
    # the glossary is missing from PDC or just shaped/typed unexpectedly.
    apply_probe = []
    if unresolved_term_names:
        try:
            def _diag(tok):
                if tok:
                    cur_token["t"] = tok
                return diagnose_terms(base, cur_token["t"], sorted(unresolved_term_names)[:3],
                                      version=version, verify_tls=verify_tls, timeout=timeout)
            apply_probe = _retry_auth(_diag, reauth) or []
        except Exception:
            apply_probe = []

    report = {
        "dry_run": bool(dry_run),
        "total": len(api_json),
        "found": sum(1 for r in results if r["found"]),
        "not_found": sum(1 for r in results if r["status"] == "not-found"),
        "applied": sum(1 for r in results if r["status"] == "applied"),
        "planned": sum(1 for r in results if r["status"] == "planned"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "ids": sorted(set(touched_ids)),
        "table_results": table_results,
        "table_ids": sorted(set(table_ids)),
        "tables_rated": sum(1 for t in table_results if t["status"] in ("applied", "planned")),
        "objectstore_folders": sum(1 for t in table_results if t["status"] == "file-level"),
        "unresolved_terms": sorted(unresolved_term_names),
        "unresolved_terms_skipped": bool(skip_unresolved_terms and unresolved_term_names),
        "terms_resolved_on_apply": resolved_on_apply,
        "probe": apply_probe,
        "results": results,
        "token": cur_token["t"],
    }

    # Trust Score: scope to the rated TABLE ids (PDC rolls trust up at table/file
    # level); fall back to the touched column ids when no tables were rated.
    if calculate_trust and not dry_run:
        scope = report["table_ids"] or report["ids"]
        if scope:
            if progress:
                try: progress({"phase": "trust", "total": len(scope)})
                except Exception: pass
            try:
                report["trust"] = calculate_trust_score(base, cur_token["t"], scope,
                                                         version, verify_tls)
            except Exception as e:
                report["trust"] = {"ok": False, "message": str(e)[:300]}
    return report


# --------------------------------------------------------------------------- #
#  Calculate Trust Score (+ poll)
# --------------------------------------------------------------------------- #
# v3 reorganised job execution around a bulk endpoint; these are the named-job
# equivalents of the v1/v2 per-job paths (see docs/REVIEW.md section 1).
_V3_BULK_NAMES = {
    "calculate-trust-score": "CALCULATE_TRUST_SCORE",
    "data-discovery": "DATA_DISCOVERY",
    "test-connection": "TEST_CONNECTION",
    "metadata/ingest": "METADATA_INGEST",
}

def _execute_job(base_url, token, name, body, version="v2", verify_tls=True, timeout=30):
    """POST a named job. v1/v2 expose one endpoint per job
       (/jobs/execute/<name>); v3 moved job execution to a bulk pattern.
       Under v1/v2 the individual path is called; under v3 the call goes
       straight to POST /jobs/execute/bulk with the named-job payload (v3 has
       no per-job endpoints). Returns the response dict, normalized so callers
       can read data/jobId/id/_id (v3 bulk returns successes/failures, no job
       id — polling is skipped there; watch PDC's Workers page instead)."""
    base = clean_base(base_url)
    if str(version).lower() not in ("v3", "3"):
        # v1/v2: one endpoint per job
        url = base + f"/api/public/{version}/jobs/execute/{name}"
        return _req("POST", url, token=token, body=body,
                    verify_tls=verify_tls, timeout=timeout)
    # v3 reorganised job execution around the bulk endpoint EXCLUSIVELY (the
    # per-job paths do not exist there), so don't burn a guaranteed 404 first
    bulk_name = _V3_BULK_NAMES.get(name) or         name.replace("/", "_").replace("-", "_").upper()
    out = _req("POST", base + f"/api/public/{version}/jobs/execute/bulk",
               token=token,
               body=[{"name": bulk_name, "type": "START", "payload": body}],
               verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out) if isinstance(out, dict) else out
    if isinstance(d, list) and d:
        first = d[0]
        return first if isinstance(first, dict) else {"data": first}
    return out if isinstance(out, dict) else {"data": out}


def calculate_trust_score(base_url, token, ids, version="v2", verify_tls=True,
                          timeout=30, poll=True, poll_tries=20, poll_wait=2.0):
    """POST /jobs/execute/calculate-trust-score {"scope":[ids]} then poll status.
       NOTE: a PDC user-doc page claims this is Tables/Files only and 'not available
       in public APIs' while the instance Swagger exposes it - so this is best-effort
       and reports whatever the instance does."""
    import time
    base = clean_base(base_url)
    out = _execute_job(base_url, token, "calculate-trust-score",
                       {"scope": list(ids)}, version=version,
                       verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out)
    job_id = (d.get("jobId") or d.get("id") or d.get("_id")
              if isinstance(d, dict) else None)
    rep = {"ok": True, "job_id": job_id, "submitted": len(list(ids)), "status": None,
           "raw": out}
    if poll and job_id:
        surl = base + f"/api/public/{version}/jobs/{job_id}/status"
        for _ in range(poll_tries):
            try:
                s = _req("GET", surl, token=token, verify_tls=verify_tls, timeout=timeout)
                sd = s.get("data", s)
                st = str((sd.get("status") or sd.get("state") or "")).upper() \
                    if isinstance(sd, dict) else ""
                rep["status"] = st or rep["status"]
                if st in ("COMPLETED", "SUCCESS", "SUCCEEDED", "FAILED", "ERROR", "CANCELLED"):
                    rep["ok"] = st in ("COMPLETED", "SUCCESS", "SUCCEEDED")
                    break
            except Exception as e:
                rep["message"] = str(e)[:200]
                break
            time.sleep(poll_wait)
    return rep


# --------------------------------------------------------------------------- #
#  Trigger PDC Data Discovery / profiling (so object-store documents get their
#  Profiled Status + Data Quality, instead of staying SKIPPED)
# --------------------------------------------------------------------------- #
def resolve_document_scope(base_url, token, api_json, version="v2",
                           verify_tls=True, timeout=30):
    """Work out which PDC entities a profiling job should run over, from the document
       (object-store) records in a Data-Elements payload.

       Each document record is type OBJECT/FILE with schemaName=bucket,
       tableName=folder, columnName=file. Profiling a FOLDER cascades to the files
       inside it, so we resolve the unique (bucket, folder) pairs to their DIRECTORY
       entities and scope those -- far fewer ids than one per file. If a folder can't
       be resolved, we fall back to resolving its individual FILE entities so nothing
       is silently dropped.

       Returns (scope_ids, labels): the entity UUIDs to profile and human-readable
       'bucket/folder' (or 'bucket/folder/file') labels for the UI."""
    seen_folder, scope_ids, labels = set(), [], []
    fallback_files = []
    for rec in api_json:
        # only object-store records carry a bucket/folder/file shape worth profiling
        if str(rec.get("type", "")).upper() not in ("OBJECT", "FILE", "DIRECTORY"):
            continue
        bucket = (rec.get("schemaName") or "").strip()
        folder = (rec.get("tableName") or "").strip()
        if not folder:
            continue
        key = (bucket, folder)
        if key in seen_folder:
            continue
        seen_folder.add(key)
        ent = resolve_table_entity(base_url, token, bucket, folder, version,
                                   verify_tls, timeout)
        if ent and _eid(ent):
            scope_ids.append(_eid(ent))
            labels.append(f"{bucket}/{folder}")
        else:
            # remember the records under this unresolved folder for a file-level retry
            fallback_files.append(rec)
    # folder didn't resolve -> resolve the individual files under it instead
    for rec in fallback_files:
        ent = resolve_column_entity(base_url, token, rec, version, verify_tls, timeout)
        if ent and _eid(ent):
            scope_ids.append(_eid(ent))
            labels.append(".".join(x for x in [rec.get("schemaName"),
                                               rec.get("tableName"),
                                               rec.get("columnName")] if x))
    # de-duplicate ids while preserving order
    seen, uniq_ids, uniq_labels = set(), [], []
    for i, lab in zip(scope_ids, labels):
        if i and i not in seen:
            seen.add(i)
            uniq_ids.append(i)
            uniq_labels.append(lab)
    return uniq_ids, uniq_labels


# Default Data-Discovery config tuned for the documents this app governs:
#  - computeChecksum  : checksum each file for duplicate detection
#  - ingestProperties : pull document properties (author/pages) for PDF/Office files
#  - buildSamples     : extract row samples -> Data Profiling for delimited files
#  - headerExists     : treat the first row of a delimited file as the header
# 'withProfile' (profile object/document stores alongside discovery) is added only on
# v3, where the field exists; on v1/v2 the discovery job itself profiles the scope.
_DISCOVERY_DEFAULTS = {
    "computeChecksum": True,
    "ingestProperties": True,
    "buildSamples": True,
    "headerExists": True,
    "contentScanType": "SCAN_ONLY",
}


def trigger_data_discovery(base_url, token, scope_ids, version="v2", verify_tls=True,
                           timeout=30, configs=None, poll=False, poll_tries=30,
                           poll_wait=3.0):
    """Start a Data Discovery job (which profiles the scope) over the given entity
       UUIDs via POST /api/public/{version}/jobs/execute/data-discovery.

       scope_ids : list of entity UUIDs (folders and/or files) to process
       configs   : overrides merged over _DISCOVERY_DEFAULTS
       poll      : when True, poll /jobs/{id}/status until it finishes (or times out)

       Returns {ok, job_id, worker, activity, status, message, submitted, raw}."""
    import time
    if not scope_ids:
        return {"ok": False, "message": "no entities in scope to profile",
                "job_id": None, "submitted": 0}
    base = clean_base(base_url)
    cfg = dict(_DISCOVERY_DEFAULTS)
    # withProfile is a v3-only field that also profiles file/object/document stores;
    # sending it to v1/v2 risks a strict-validation 400, so gate it on the version.
    if str(version).lower() in ("v3", "3"):
        cfg["withProfile"] = True
    if configs:
        cfg.update(configs)
    out = _execute_job(base_url, token, "data-discovery",
                       {"scope": list(scope_ids), "configs": cfg}, version=version,
                       verify_tls=verify_tls, timeout=timeout)
    data = out.get("data", out) if isinstance(out, dict) else {}
    job_id = data.get("_id") or data.get("id") or data.get("jobId")
    rep = {"ok": True, "job_id": job_id, "submitted": len(list(scope_ids)),
           "worker": data.get("workerName"), "activity": data.get("activity"),
           "status": None, "message": out.get("message", "") if isinstance(out, dict) else "",
           "raw": out}
    # Optionally wait for the worker to finish so the caller can immediately re-pull
    # the now-populated profiling stats / Data Quality.
    if poll and job_id:
        for _ in range(poll_tries):
            try:
                st = job_status(base, token, job_id, version, verify_tls, timeout)
            except Exception as e:
                rep["message"] = str(e)[:200]
                break
            rep["status"] = st.get("status") or rep["status"]
            done = str(rep["status"] or "").upper()
            if done in ("COMPLETED", "SUCCESS", "SUCCEEDED", "FAILED", "ERROR", "CANCELLED"):
                rep["ok"] = done in ("COMPLETED", "SUCCESS", "SUCCEEDED")
                break
            time.sleep(poll_wait)
    return rep


def job_status(base_url, token, job_id, version="v2", verify_tls=True, timeout=20):
    """Check a background job via GET /api/public/{version}/jobs/{id}/status.
       Returns {status, activity, worker, duration, raw} (status is e.g. RUNNING /
       COMPLETED / FAILED)."""
    url = clean_base(base_url) + f"/api/public/{version}/jobs/{job_id}/status"
    out = _req("GET", url, token=token, verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out) if isinstance(out, dict) else {}
    if not isinstance(d, dict):
        d = {}
    # PDC surfaces failure detail under varying keys/levels depending on the worker; pull
    # the first non-empty across the data object, its nested result, and the envelope so
    # the loader can show *why* an ingest failed, not just FAIL.
    err = ""
    sources = [d, (d.get("result") if isinstance(d.get("result"), dict) else {}),
               (out if isinstance(out, dict) else {})]
    for src in sources:
        for k in ("error", "errorMessage", "failureReason", "failureMessage",
                  "message", "reason", "statusMessage", "exception", "cause"):
            v = src.get(k)
            if v:
                err = v if isinstance(v, str) else json.dumps(v)
                break
        if err:
            break
    if not err and str(d.get("status") or "").upper() in ("FAILED", "ERROR"):
        # last resort: the activity string often names the failing step
        err = str(d.get("activity") or "")
    return {"status": d.get("status") or d.get("state"),
            "activity": d.get("activity"), "worker": d.get("workerName"),
            "duration": d.get("duration"), "error": (err or "")[:500], "raw": out}
def filter_profiling_info(base_url, token, filters, version="v2", verify_tls=True,
                          timeout=30, sample_limit=20, size=500, max_pages=6):
    """POST /entities/filter/profiling-info. Returns list of items, each with
       identity fields + a nested profilingInfo (stats, sampling, patterns)."""
    base = clean_base(base_url) + f"/api/public/{version}/entities/filter/profiling-info"
    items, cursor, pages = [], None, 0
    while pages < max_pages:
        q = {"sampleLimit": sample_limit, "size": size}
        if cursor:
            q["cursor"] = cursor                     # query param, per the v3 contract
        url = base + "?" + urllib.parse.urlencode(q)
        out = _req("POST", url, token=token, body={"filters": filters},
                   verify_tls=verify_tls, timeout=timeout)
        items.extend(_results(out))
        cursor = _cursor(out)
        pages += 1
        if not cursor:
            break
    return items


def pdc_profile_for_columns(base_url, token, columns, version="v2", verify_tls=True,
                            timeout=30, sample_limit=20):
    """Pull PDC profiling stats for a set of columns described as
       [{schemaName, tableName, columnName, type, fqdn?}, ...].
       Resolves table-by-table via parentIds (cheap), pulls profiling-info for
       each table's columns, then keys the stats by 'schema.table.column' to lay
       next to the app's own discovery. Returns {col_key: {stats, sampling, ...}}."""
    base = clean_base(base_url)
    table_cache = {}
    # group requested columns by (schema, table)
    by_table = {}
    for c in columns:
        key = ((c.get("schemaName") or "").strip(), (c.get("tableName") or "").strip())
        by_table.setdefault(key, []).append((c.get("columnName") or "").strip().lower())

    result = {}
    for (sch, tbl), wanted in by_table.items():
        # resolve table id
        ent = resolve_column_entity  # not used; resolve table directly below
        tid = table_cache.get((sch.lower(), tbl.lower()))
        if tid is None and tbl:
            t_hits = filter_entities(base, token,
                                     {"names": [tbl], "types": list(dict.fromkeys(_TBL_TYPES))},
                                     version, verify_tls, timeout)
            t_named = [e for e in t_hits if str(e.get("name", "")).strip().lower() == tbl.lower()]
            t_scoped = [e for e in t_named if (not sch) or sch.lower() in _path_text(e)]
            pick = (t_scoped or t_named)
            tid = _eid(pick[0]) if pick else ""
            table_cache[(sch.lower(), tbl.lower())] = tid
        if not tid:
            continue
        items = filter_profiling_info(base, token, {"parentIds": [tid],
                                                    "types": list(dict.fromkeys(_COL_TYPES))},
                                      version, verify_tls, timeout, sample_limit)
        for it in items:
            cname = str(it.get("name", "")).strip()
            if wanted and cname.lower() not in wanted:
                continue
            pinfo = it.get("profilingInfo") or it.get("profiling") or {}
            ckey = ".".join(x for x in [sch, tbl, cname] if x)
            result[ckey] = {
                "id": _eid(it),
                "fqdn": it.get("fqdn") or it.get("fqdnDisplay"),
                "stats": pinfo.get("stats") or pinfo.get("statistics") or {},
                "sampling": pinfo.get("sampling") or pinfo.get("samples"),
                "patterns": pinfo.get("patternAnalysis") or pinfo.get("patterns"),
                "raw": pinfo,
            }
    return result


# =========================================================================== #
#  Bulk data-source loader  (create -> metadata ingest -> poll)
#  Reuses this module's clean_base/_req/auth/verify_tls and the same
#  jobs/execute + jobs/{id}/status pattern used by calculate_trust_score().
#  Endpoints confirmed against the PDC Public API (v2) reference:
#    create : POST /api/public/<v>/data-sources                       -> data:[{_id,...}]
#    ingest : POST /api/public/<v>/jobs/execute/metadata/ingest        (config body + resourceId)
#             = the "Ingest Schemas or Scan" job (initial ingest for a new source).
#             NB: metadata/re-ingest is a different job — a REFRESH that takes
#             {scope:[<entity uuid>]}; a new source's id is not a uuid, so it 400s there.
#    poll   : GET  /api/public/<v>/jobs/{id}/status                    -> {status}
#    list   : POST /api/public/<v>/data-sources/filter  {filters:{resourceNames:["*"]}}
#  No confirmed public test-connection value-add here; connectivity is validated
#  locally by the app's Test-connection buttons before a bulk load.
# =========================================================================== #

_SECRET_KEYS = ("password", "azureSharedKey", "secretKey", "secretAccessKey",
                "accessKey", "oauthClientSecret", "trustStorePassword",
                "keyStorePassword")

_JOB_OK  = ("COMPLETED", "COMPLETE", "SUCCESS", "SUCCEEDED", "DONE", "FINISHED")
_JOB_BAD = ("FAILED", "FAIL", "ERROR", "CANCELLED", "CANCELED", "ABORTED")


def redact_secrets(obj):
    """Return a deep copy of a dict/list with known secret values masked, so a
       payload can be logged or echoed in an error without leaking credentials."""
    if isinstance(obj, dict):
        return {k: ("***REDACTED***" if k in _SECRET_KEYS and v not in (None, "")
                    else redact_secrets(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return obj


def parse_csv_rows(text):
    """Parse CSV text into a list of dict rows (header-keyed). Tolerates a BOM."""
    import csv, io
    if text and text[:1] == "\ufeff":
        text = text[1:]
    return [dict(r) for r in csv.DictReader(io.StringIO(text))]


def _nonempty(d):
    """Drop keys whose value is None or "" (PDC rejects some empty fields)."""
    return {k: v for k, v in d.items() if v not in (None, "")}


def _split_list(v):
    """'a;b , c' -> ['a','b','c'];  list -> list;  blank -> []."""
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    if not v:
        return []
    return [p.strip() for p in str(v).replace(";", ",").split(",") if p.strip()]


def build_data_source_body(row):
    """Map a flat row (CSV/dict) to a PDC create-data-source JSON body.

       row['kind'] (or 'databaseType') selects the connector:
         postgres | mysql | s3 | minio | azure_blob
       Required per kind:
         postgres/mysql : resourceName, host, port, databaseName, userName, password
         s3/minio       : resourceName, endpoint, accessKeyID, secretAccessKey, container
         azure_blob     : resourceName, accountName, azureSharedKey, container
       Optional everywhere: description, fqdnId, affinityId, configMethod, path,
         schemaNames, includePatterns, excludePatterns, totalCapacity, costPrice,
         costFrequency, country.
    """
    kind = str(row.get("kind") or row.get("databaseType") or "").strip().lower()
    name = (row.get("resourceName") or row.get("name") or "").strip()
    if not name:
        raise ValueError("row is missing resourceName")

    common = {
        "resourceName": name,
        "fqdnId":       (row.get("fqdnId") or name),
        "description":  row.get("description", ""),
        "affinityId":   row.get("affinityId") or "DEFAULT",
        # credentials = PDC reads the discrete host/port/user/password (or key) fields
        # we send here. (The old default of "uri" expected a single uri string and
        # left credential-style connections mis-configured.) Overridable per row.
        "configMethod": row.get("configMethod") or "credentials",
    }

    if kind in ("postgres", "postgresql", "pg"):
        body = dict(common, databaseType="POSTGRES",
                    host=row.get("host"), port=str(row.get("port") or "5432"),
                    databaseName=row.get("databaseName") or row.get("database"),
                    userName=row.get("userName") or row.get("username"),
                    password=row.get("password"),
                    schemaNames=_split_list(row.get("schemaNames")))
    elif kind in ("mysql", "mariadb"):
        body = dict(common, databaseType="MYSQL",
                    host=row.get("host"), port=str(row.get("port") or "3306"),
                    databaseName=row.get("databaseName") or row.get("database"),
                    userName=row.get("userName") or row.get("username"),
                    password=row.get("password"))
    elif kind in ("s3", "aws_s3", "minio"):
        endpoint = row.get("endpoint") or ""
        ak = row.get("accessKey") or row.get("accessKeyID") or row.get("accessId")
        sk = row.get("secretKey") or row.get("secretAccessKey")
        # A working UI-created AWS S3 source stores databaseType="AWS" (confirmed by
        # inspecting an untouched Test_S3) — NOT "AWS_S3" (which leaves the Edit form's
        # type blank) and NOT "S3". Its record carries no fileSystemType (PDC derives
        # that from databaseType="AWS" at scan time), so we send just databaseType to
        # match the known-good source and not risk the create's oneOf schema.
        body = dict(common, databaseType="AWS",
                    endpoint=endpoint,
                    region=row.get("region") or "us-east-1",
                    accessId=ak, accessKeyID=ak, accessKey=ak,
                    secretKey=sk, secretAccessKey=sk,
                    container=row.get("container") or row.get("bucket"),
                    path=row.get("path", "") or "/",
                    defaultEndpointsProtocol=row.get("protocol")
                        or ("http" if str(endpoint).lower().startswith("http://") else "https"))
    elif kind in ("oracle",):
        # Field set per the PDC "Add a data source" doc (credentials method):
        # host / port / databaseName (service name) / userName / password, plus a
        # REQUIRED driver — PDC ships no Oracle JDBC jar, so upload ojdbc11.jar via
        # Manage Drivers first or the create/test will fail. databaseType="ORACLE"
        # follows the POSTGRES/MYSQL uppercase convention; the public docs don't
        # publish the enum, so verify against a UI-created Oracle source if the
        # create 400s (same discovery path as databaseType="AWS" for object stores).
        body = dict(common, databaseType="ORACLE",
                    host=row.get("host"), port=str(row.get("port") or "1521"),
                    databaseName=row.get("databaseName") or row.get("database")
                        or row.get("serviceName"),
                    userName=row.get("userName") or row.get("username"),
                    password=row.get("password"),
                    driverClassName=row.get("driverClassName") or "oracle.jdbc.OracleDriver",
                    schemaNames=_split_list(row.get("schemaNames")))
    elif kind in ("azure", "azure_blob", "azure_blob_storage"):
        body = dict(common, databaseType="AZURE_BLOB_STORAGE",
                    accountName=row.get("accountName"),
                    azureSharedKey=row.get("azureSharedKey"),
                    container=row.get("container"),
                    path=row.get("path", ""),
                    location={"country": row.get("country") or "US"})
    else:
        raise ValueError("unknown data-source kind: %r (use postgres|mysql|oracle|s3|minio|azure_blob)" % kind)

    inc = _split_list(row.get("includePatterns"))
    exc = _split_list(row.get("excludePatterns"))
    if inc:
        body["includePatterns"] = inc
    if exc:
        body["excludePatterns"] = exc

    price = row.get("costPrice")
    if price not in (None, ""):
        try:
            body["totalCapacity"] = float(row["totalCapacity"]) if row.get("totalCapacity") not in (None, "") else None
        except (TypeError, ValueError):
            pass
        body["costPerTb"] = _nonempty({
            "price": float(price),
            "frequency": row.get("costFrequency") or "month",
        })
    # An explicit databaseType from the row wins over the kind-derived default, so a
    # record exported from this PDC (which carries the exact type code PDC uses)
    # reloads without guesswork.
    if str(row.get("databaseType") or "").strip():
        body["databaseType"] = str(row["databaseType"]).strip()

    # Pass through the fields that route an object store to the file-scan path (vs JDBC).
    # PDC sets these when you pick a type in the UI; the public API doesn't publish their
    # values, so once you read them off a working source (Inspect PDC source config) you
    # can supply them here as CSV columns without a code change.
    for k in ("serviceType", "fileSystemType", "spiVersion", "driverClassName",
              "jobClasspath", "configMethod"):
        v = row.get(k)
        if v not in (None, ""):
            body[k] = v

    return _nonempty(body)


def internal_scan_files(base_url, token, data_body, verify_tls=True, timeout=30):
    """EXPERIMENTAL / UNSUPPORTED: trigger an object-store file scan via PDC's INTERNAL
       UI endpoint (POST /api/start-job) — the call the web app's "Scan Files" button
       makes. It is NOT part of the public API: no /public/, no version, undocumented,
       and it may change or break between PDC releases. Gated behind an explicit toggle.
       Body shape (from the UI capture): {name:"METADATA_INGEST", type:"START", data:{…}}."""
    url = clean_base(base_url) + "/api/start-job"
    body = {"name": "METADATA_INGEST", "type": "START", "data": data_body}
    out = _req("POST", url, token=token, body=body, verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out) if isinstance(out, dict) else {}
    jid = (d.get("jobId") or d.get("id") or d.get("_id")) if isinstance(d, dict) else None
    return {"job_id": jid, "raw": out}


def delete_data_source(base_url, token, ds_id, version="v2", verify_tls=True, timeout=30):
    """DELETE /data-sources/{id}. Used to recreate a source whose stored config is
       wrong (e.g. an object store created before the AWS_S3 fix, so it carries no
       credentials). Returns True on success."""
    if not ds_id:
        return False
    url = clean_base(base_url) + f"/api/public/{version}/data-sources/{ds_id}"
    try:
        _req("DELETE", url, token=token, verify_tls=verify_tls, timeout=timeout)
        return True
    except Exception:
        return False


def create_data_source(base_url, token, body, version="v2", verify_tls=True, timeout=30):
    """POST /data-sources. The API accepts one object (or an array) and returns
       201/207 with data as an ARRAY of created records. Returns {resourceId, raw}.
       resourceId (the created _id) is needed to scope the ingest job."""
    url = clean_base(base_url) + f"/api/public/{version}/data-sources"
    out = _req("POST", url, token=token, body=body, verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out) if isinstance(out, dict) else out
    rec = d[0] if isinstance(d, list) and d else (d if isinstance(d, dict) else {})
    rec = rec if isinstance(rec, dict) else {}
    rid = rec.get("_id") or rec.get("resourceId") or rec.get("id")
    return {"resourceId": rid, "record": rec, "raw": out}


def run_job(base_url, token, name, body, version="v2", verify_tls=True, timeout=30):
    """POST /jobs/execute/<name>. Returns {job_id, raw} — same shape used by
       calculate_trust_score()."""
    out = _execute_job(base_url, token, name, body, version=version,
                       verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out) if isinstance(out, dict) else {}
    jid = None
    if isinstance(d, dict):
        jid = d.get("jobId") or d.get("id") or d.get("_id")
    return {"job_id": jid, "raw": out}


def wait_job(base_url, token, job_id, version="v2", verify_tls=True, timeout=20,
             poll_wait=3.0, max_wait=300, on_update=None):
    """Poll /jobs/{id}/status until a terminal state or max_wait seconds.
       Returns {ok, status, timeout}."""
    import time
    start = time.time()
    last = None
    while True:
        st = job_status(base_url, token, job_id, version=version,
                        verify_tls=verify_tls, timeout=timeout)
        s = str(st.get("status") or "").upper()
        last = s or last
        if on_update:
            try:
                on_update(s, st)
            except Exception:
                pass
        if s in _JOB_OK:
            return {"ok": True, "status": s, "timeout": False, "error": ""}
        if s in _JOB_BAD:
            return {"ok": False, "status": s, "timeout": False, "error": st.get("error", "")}
        if (time.time() - start) >= max_wait:
            return {"ok": False, "status": last or "TIMEOUT", "timeout": True, "error": ""}
        time.sleep(poll_wait)


def _ingest_body(create_body, record):
    """Body for the INITIAL metadata ingest — the "Ingest Schemas or Scan" job
    (POST /jobs/execute/metadata/ingest). It takes the data-source **config**
    (the same body used to create), scoped to the created record by resourceId /
    fqdnId, so PDC connects and ingests that exact source.

    This is distinct from metadata/re-ingest, which is the later REFRESH job and
    takes {"scope": [<entity uuid>]} — a data source's create id is not a uuid, so
    re-ingest is wrong for a freshly created source (it 400s: /scope/0 must be uuid).
    """
    ib = dict(create_body or {})
    ib["resourceId"] = (record or {}).get("resourceId") or (record or {}).get("_id") or ib.get("resourceId")
    if (record or {}).get("fqdnId"):
        ib["fqdnId"] = record["fqdnId"]
    return _nonempty(ib)


def find_existing_data_source(base_url, token, resource_name, version="v2",
                              verify_tls=True, timeout=30):
    """Return the data-source record already in PDC whose resourceName matches
       (case-insensitive), or None. Lets the loader skip create for sources that
       already exist instead of hitting the 400 duplicate-fqdn error on a re-run."""
    if not resource_name:
        return None
    base = clean_base(base_url)
    qs = urllib.parse.urlencode({"skip": 0, "limit": 200})
    url = f"{base}/api/public/{version}/data-sources/filter?{qs}"
    try:
        out = _req("POST", url, token=token,
                   body={"filters": {"resourceNames": [resource_name]}},
                   verify_tls=verify_tls, timeout=timeout)
    except Exception:
        return None
    data = out.get("data", []) if isinstance(out, dict) else []
    rn = str(resource_name).strip().lower()
    for rec in (data or []):
        if str(rec.get("resourceName", "")).strip().lower() == rn:
            return rec
    return None


def bulk_load_one(base_url, token, row, version="v2", verify_tls=True, timeout=30,
                  do_test=False, do_ingest=True, wait=True,
                  poll_wait=3.0, max_wait=300, skip_existing=True, replace_existing=False,
                  internal_scan=False):
    """Process a single row: create the data source, then trigger the metadata
       re-ingest job scoped to the new record and (optionally) poll it to a
       terminal state. Never raises for a row-level failure — returns a result
       record. TokenExpired DOES propagate so the caller can re-auth and retry.

       do_test is accepted for backward compatibility but is a no-op: PDC exposes
       no confirmed public test-connection job, and the app validates connectivity
       locally (Test connection buttons) before bulk load."""
    rec = {"resourceName": (row.get("resourceName") or row.get("name") or ""),
           "create": "SKIP", "ingest": "SKIP", "job": "SKIP",
           "resourceId": None, "jobId": None, "error": None}
    create_ok = ingest_ok = False
    try:
        body = build_data_source_body(row)
        rec["resourceName"] = body["resourceName"]

        existing = None
        if skip_existing or replace_existing:
            existing = find_existing_data_source(base_url, token, body["resourceName"],
                                                 version, verify_tls, timeout)
        if existing and replace_existing:
            # Safe recreate: only delete the old source once we know the new body is
            # valid. Try to create first — PDC rejects it as a name/fqdn *conflict*, which
            # proves the body is good, so we delete + recreate. If it instead fails
            # *validation*, keep the existing source untouched (this is what stops a bad
            # row from deleting a working source).
            ex_id = existing.get("_id") or existing.get("resourceId") or existing.get("id")
            try:
                cr = create_data_source(base_url, token, body, version, verify_tls, timeout)
                rec["resourceId"] = cr["resourceId"]
                create_ok = True
                rec["create"] = "OK"
            except Exception as ce:
                m = str(ce).lower()
                looks_like_validation = any(w in m for w in (
                    "required property", "must be array", "must match", "oneof",
                    "schema", "invalid", "not allowed"))
                if looks_like_validation:
                    rec["create"] = "FAIL"
                    rec["error"] = ("recreate aborted — new config is invalid, existing "
                                    "source kept: " + str(ce)[:200])
                    return rec
                delete_data_source(base_url, token, ex_id, version, verify_tls, timeout)
                cr = create_data_source(base_url, token, body, version, verify_tls, timeout)
                rec["resourceId"] = cr["resourceId"]
                create_ok = True
                rec["create"] = "RECREATED"
        elif existing:
            # already in PDC — don't re-create (that 400s on the duplicate fqdn);
            # reuse its id and (optionally) re-scan it.
            rec["resourceId"] = existing.get("_id") or existing.get("resourceId") or existing.get("id")
            rec["create"] = "EXISTS"
            create_ok = True
            cr = {"resourceId": rec["resourceId"], "record": existing}
        else:
            cr = create_data_source(base_url, token, body, version, verify_tls, timeout)
            rec["resourceId"] = cr["resourceId"]
            create_ok = True
            rec["create"] = "OK"

        if not rec["resourceId"]:
            rec["error"] = "created, but no resource id came back — cannot scope ingest"
            rec["ingest"] = "FAIL"
            return rec

        _kind = str(row.get("kind") or "").strip().lower()
        _is_object_store = _kind in ("minio", "s3", "aws_s3") or body.get("databaseType") == "AWS"
        if do_ingest and _is_object_store:
            if internal_scan:
                # EXPERIMENTAL: PDC's internal /api/start-job — the UI's Scan Files call.
                data = dict(body)
                data["resourceId"] = rec["resourceId"]
                _fq = (cr.get("record") or {}).get("fqdnId") if isinstance(cr, dict) else None
                if _fq:
                    data["fqdnId"] = _fq
                data.setdefault("deleteEmptyFolders", False)
                data.setdefault("incremental", False)
                try:
                    jr = internal_scan_files(base_url, token, data, verify_tls, timeout)
                    rec["jobId"] = jr["job_id"]
                    ingest_ok = True
                    rec["ingest"] = "OK"
                    rec["job"] = "SENT"
                    rec["note"] = "file scan triggered via PDC internal /api/start-job (experimental — verify in PDC)"
                    if wait and jr["job_id"]:
                        w = wait_job(base_url, token, jr["job_id"], version, verify_tls,
                                     timeout, poll_wait=poll_wait, max_wait=max_wait)
                        if w.get("status"):
                            rec["job"] = "OK" if w["ok"] else ("TIMEOUT" if w.get("timeout") else "FAIL")
                            if not w["ok"] and w.get("error"):
                                rec["error"] = "internal scan: " + str(w["error"])[:200]
                except Exception as e:
                    rec["ingest"] = "FAIL"
                    rec["error"] = "internal /api/start-job failed: " + str(e)[:200]
            else:
                # Public API doesn't expose the object-store file-scan trigger; create the
                # source correctly and leave the scan to PDC's Scan Files (or the toggle).
                rec["ingest"] = "SKIP"
                rec["job"] = "SKIP"
                rec["note"] = ("object store created OK (AWS S3, ready to scan) — the public "
                               "API doesn't expose the file-scan trigger, so click Scan Files "
                               "on it in PDC, then Harvest")
        elif do_ingest:
            jr = run_job(base_url, token, "metadata/ingest",
                         _ingest_body(body, cr.get("record")),
                         version, verify_tls, timeout)
            rec["jobId"] = jr["job_id"]
            ingest_ok = True
            rec["ingest"] = "OK"
            if wait and jr["job_id"]:
                w = wait_job(base_url, token, jr["job_id"], version, verify_tls,
                             timeout, poll_wait=poll_wait, max_wait=max_wait)
                rec["job"] = "OK" if w["ok"] else ("TIMEOUT" if w.get("timeout") else "FAIL")
                if not w["ok"]:
                    detail = (w.get("error") or "").strip()
                    rec["error"] = ("ingest job ended %s" % w.get("status")) + (" — %s" % detail if detail else "")
                    if w.get("timeout"):
                        rec["error"] += " (still running when polling stopped — check the Workers page)"

    except TokenExpired:
        raise
    except Exception as e:
        rec["error"] = str(e)[:300]
        if not create_ok:
            rec["create"] = "FAIL"
        elif do_ingest and not ingest_ok:
            rec["ingest"] = "FAIL"
    return rec


# --------------------------------------------------------------------------- #
#  List / export existing data sources  (round-trips the bulk-loader CSV)
#    list   : POST /api/public/<v>/data-sources/filter  {filters:{resourceNames:["*"]}}
# --------------------------------------------------------------------------- #

def list_data_sources(base_url, token, version="v2", verify_tls=True, timeout=30,
                      page_size=500, max_pages=40):
    """Return every data source PDC holds, via the wildcard filter endpoint.
       The public API has no bare list-all, but filter with resourceNames=['*']
       is the supported way to enumerate them."""
    base = clean_base(base_url)
    out_rows, skip = [], 0
    for _ in range(max_pages):
        qs = urllib.parse.urlencode({"skip": skip, "limit": page_size})
        url = f"{base}/api/public/{version}/data-sources/filter?{qs}"
        out = _req("POST", url, token=token, body={"filters": {"resourceNames": ["*"]}},
                   verify_tls=verify_tls, timeout=timeout)
        data = out.get("data", []) if isinstance(out, dict) else []
        out_rows.extend(data)
        info = out.get("pageInfo", {}) if isinstance(out, dict) else {}
        total = info.get("totalCount")
        skip += page_size
        if not data or (total is not None and skip >= total):
            break
    return out_rows


def get_data_source(base_url, token, name=None, ds_id=None, version="v2",
                    verify_tls=True, timeout=30):
    """Fetch ONE data-source record (full fields: databaseType, host, port,
       databaseName, userName, endpoint, container, schemaNames, …) by resource
       name or id, via the same filter endpoint list_data_sources uses. Secrets
       come back encrypted/absent — the public API never returns a usable
       password or secret key."""
    base = clean_base(base_url)
    filters = {"ids": [ds_id]} if ds_id else {"resourceNames": [name or "*"]}
    url = f"{base}/api/public/{version}/data-sources/filter?skip=0&limit=5"
    out = _req("POST", url, token=token, body={"filters": filters},
               verify_tls=verify_tls, timeout=timeout)
    data = out.get("data", []) if isinstance(out, dict) else []
    if not data:
        return None
    if name:  # prefer the exact-name hit if the filter matched loosely
        exact = next((r for r in data
                      if str(r.get("resourceName", "")).lower() == name.lower()), None)
        return exact or data[0]
    return data[0]


# Map a stored PDC databaseType back to the loader's friendly 'kind'.
_TYPE_TO_KIND = {
    "POSTGRES": "postgres", "POSTGRESQL": "postgres",
    "MYSQL": "mysql", "MARIADB": "mysql",
    "S3": "minio", "AWS_S3": "minio", "AWS S3": "minio",
    "AZURE_BLOB_STORAGE": "azure_blob", "AZURE_BLOB": "azure_blob",
}

# Column order for the bulk-loader CSV — kept symmetric with build_data_source_body,
# so an export round-trips straight back into the loader. Secret columns are emitted
# empty on export (PDC only ever returns encrypted secrets, never plaintext).
CSV_COLUMNS = [
    "kind", "resourceName",
    "host", "port", "databaseName", "userName", "password", "schemaNames",
    "endpoint", "region", "accessKey", "secretKey", "container", "path",
    "includePatterns", "excludePatterns",
    "databaseType", "fqdnId", "description",
]
_SECRET_CSV_COLS = {"password", "secretAccessKey", "secretKey"}


def connections_to_csv(sources):
    """Render PDC data-source records as bulk-loader CSV text. Secrets are blanked
       (PDC never returns plaintext), so the operator re-enters them before reload —
       everything else round-trips exactly, including the real databaseType and
       configMethod codes this PDC uses."""
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore",
                       lineterminator="\r\n")
    w.writeheader()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        dtype = str(s.get("databaseType") or "").strip()
        schemas = s.get("schemaNames")
        row = {
            "kind":         _TYPE_TO_KIND.get(dtype.upper(), dtype.lower() or ""),
            "resourceName": s.get("resourceName") or s.get("fqdnId") or "",
            "databaseType": dtype,
            "configMethod": s.get("configMethod") or "",
            "affinityId":   s.get("affinityId") or "",
            "host":         s.get("host") or "",
            "port":         s.get("port") or "",
            "databaseName": s.get("databaseName") or "",
            "userName":     s.get("userName") or "",
            "endpoint":     s.get("endpoint") or "",
            "region":       s.get("region") or "",
            "accessKeyID":  s.get("accessKeyID") or "",
            "accessKey":    s.get("accessKey") or "",
            "container":    s.get("container") or "",
            "path":         s.get("path") or "",
            "schemaNames":  ";".join(schemas) if isinstance(schemas, list) else (schemas or ""),
            "fqdnId":       s.get("fqdnId") or "",
            "description":  s.get("description") or "",
        }
        for c in _SECRET_CSV_COLS:
            row[c] = ""   # never export secrets
        w.writerow(row)
    return buf.getvalue()
