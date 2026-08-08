"""pdc_api.core — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
import json
import re
import ssl
import os
import socket
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


# An HTTP client should say what it is. Left unset, urllib sends
# "Python-urllib/3.x", which Cloudflare's browser integrity check refuses with
# error 1010 - the request never reaches PDC, and the failure looks like an auth
# problem. This is a description, not a disguise: a WAF rule that needs to allow
# this app can match on it.
USER_AGENT = "PDC-Glossary-Generator (+https://github.com/jporeilly/PDC-Glossary-Generator)"


def _access_headers():
    """Cloudflare Access service-token headers, when configured.

    Authenticating a BROWSER against Access sets a CF_Authorization cookie on
    that browser session. This client is a separate HTTP client with no cookie
    and no way to complete an interactive login, so it stays blocked however
    many codes a person types in. A service token is Cloudflare's documented
    answer for non-browser clients: two headers, checked at the edge.

    From the environment, never from the app's settings file - these are
    credentials, and settings.json is included in the State snapshot the app can
    export.

        CF_ACCESS_CLIENT_ID       <id>.access
        CF_ACCESS_CLIENT_SECRET   <secret>
    """
    cid = os.environ.get("CF_ACCESS_CLIENT_ID", "").strip()
    sec = os.environ.get("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cid and sec:
        return {"CF-Access-Client-Id": cid, "CF-Access-Client-Secret": sec}
    return {}


def _cloudflare_code(text):
    """Cloudflare's own error number, if this came from the edge rather than PDC.

    A 1xxx code in an HTML body means the request was refused BEFORE the origin
    saw it, so nothing about credentials, realms or clients is implicated.
    """
    import re as _re
    if not text:
        return None
    m = _re.search(r"error code:\s*(1\d{3})", text)
    if m:
        return m.group(1)
    if "cloudflare" in text.lower() and "<html" in text.lower():
        return "unknown"
    return None


def _req(method, url, token=None, body=None, headers=None, verify_tls=True,
         timeout=30, form=False):
    """Generic request. Returns parsed JSON (or {} on empty body).
       Raises TokenExpired on 401; RuntimeError with the server text otherwise."""
    h = dict(headers or {})
    h.setdefault("User-Agent", USER_AGENT)
    for k, v in _access_headers().items():
        h.setdefault(k, v)
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
            # PDC sits behind oauth2-proxy: an absent/expired token on the
            # INTERNAL endpoints (/api/*, no /public/) is answered with a 302 to
            # Keycloak, not a 401 — urllib follows it and hands back the login
            # HTML, which used to surface as a baffling JSON parse error.
            if raw.lstrip()[:1] == "<" and "/protocol/openid-connect/auth" in raw:
                raise TokenExpired("redirected to the Keycloak login — token missing or expired")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        # MUST come before URLError: HTTPError SUBCLASSES it. With the wider
        # clause first, every HTTP response landed there and was re-raised bare,
        # so this handler never ran - losing the response body, the
        # 401 -> TokenExpired mapping and the Cloudflare detection below. The
        # visible symptom was "HTTP Error 400: Bad Request" with no detail, and
        # it also defeated the bulk loader's safe-recreate guard, which reads
        # PDC's error text to tell a bad body from a name conflict.
        detail = ""
        try:
            # 2000, not 600. PDC echoes the entire submitted record back before
            # saying what was wrong with it, so a 600-char cap cut the body off
            # mid-echo and lost the reason - including "Duplicate key violation",
            # which the bulk loader reads to tell a name conflict from a bad
            # body. Truncating the part that decides behaviour is worse than a
            # long message.
            detail = e.read().decode("utf-8")[:2000]
        except Exception:
            pass
        cf = _cloudflare_code(detail)
        if cf:
            # Do NOT raise TokenExpired here even on a 403: the credentials were
            # never tested. Saying "auth failed" sends people to check realms and
            # passwords that Keycloak never saw.
            raise RuntimeError(
                "Blocked by Cloudflare (error {code}), not by PDC - the request "
                "was refused at the edge and never reached the server, so "
                "credentials are not the problem. Allow this client in the "
                "Cloudflare WAF (match the User-Agent {ua!r}, or skip Browser "
                "Integrity Check for the API paths), or reach PDC on an address "
                "that bypasses Cloudflare. If this is Cloudflare ACCESS, a "
                "browser login does not help a non-browser client: add a Bypass "
                "policy for this network's egress IP, or create a service token "
                "and set CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET. "
                "URL: {url}".format(
                    code=cf, ua=USER_AGENT, url=url))
        if e.code == 401:
            raise TokenExpired(detail or "401 Unauthorized")
        raise RuntimeError(f"HTTP {e.code} on {method} {url}: {detail}")
    except urllib.error.URLError as e:
        # Reached before any HTTP happened: DNS, TLS or a refused connection.
        # Reporting these as "auth failed" is how a hosts-file entry missing on
        # one machine became an afternoon of checking realms and passwords.
        reason = getattr(e, "reason", e)
        host = urllib.parse.urlsplit(url).hostname or url
        if isinstance(reason, socket.gaierror):
            raise RuntimeError(
                "Cannot resolve {host!r} - this is DNS, not authentication, so "
                "nothing was ever sent. Check the spelling, and remember a lab "
                "vhost usually only resolves on machines carrying the hosts-file "
                "entry for it: a laptop without that entry reaches whatever the "
                "PUBLIC internet has at that name instead.".format(host=host))
        if isinstance(reason, (ConnectionRefusedError, TimeoutError, socket.timeout)):
            raise RuntimeError(
                "{host} resolved but did not answer ({reason}) - the name is "
                "right and the service is not listening, or a firewall is in "
                "the way. Credentials are not involved.".format(host=host, reason=reason))
        raise RuntimeError("Could not reach {host}: {reason}".format(host=host, reason=reason))


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
