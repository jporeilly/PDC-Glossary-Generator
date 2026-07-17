"""pdc_api.core — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
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
