"""pdc_api.apply — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
import json
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from .core import TokenExpired, _eid, _req, clean_base
from .entities import _attrs_of, get_entity, resolve_column_entity, resolve_table_entity
from .terms import diagnose_terms, resolve_terms
from .jobs import calculate_trust_score

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
