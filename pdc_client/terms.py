"""pdc_api.terms — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
import json
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from .core import _bt_match, _eid, _glossary_id, _req, _results, clean_base
from .entities import filter_entities

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
                  verify_tls=True, timeout=20, progress=None):
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

    todo = sorted(set(n for n in names if n))
    for _ti, name in enumerate(todo):
        if progress:
            try:
                progress({"phase": "term", "done": _ti, "total": len(todo), "name": name})
            except Exception:
                pass
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
