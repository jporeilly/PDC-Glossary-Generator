"""pdc_api.jobs — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
import json
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from .core import _cursor, _eid, _req, _results, clean_base
from .entities import (
    _COL_TYPES,
    _TBL_TYPES,
    _path_text,
    filter_entities,
    resolve_column_entity,
    resolve_table_entity)

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


def profiled_snapshot(base_url, token, ids, version="v2", verify_tls=True,
                      timeout=20, cap=20):
    """{entity_id: profiledAt|None} for up to `cap` entities — the version-
    agnostic way to watch a Data Discovery run finish. v3's bulk job endpoint
    returns no job id to poll, but each entity's system.profiledAt flips when
    its profiling completes, so progress = how many timestamps changed since
    the pre-submission snapshot."""
    base = clean_base(base_url)
    out = {}
    for eid in list(ids)[:cap]:
        try:
            ent = _req("GET", base + f"/api/public/{version}/entities/{eid}",
                       token=token, verify_tls=verify_tls, timeout=timeout)
            e = ent.get("data", ent)
            if isinstance(e, list):
                e = e[0] if e else {}
            out[str(eid)] = ((e.get("system") or {}).get("profiledAt")
                             or (e.get("system") or {}).get("scannedAt"))
        except Exception:
            out[str(eid)] = None
    return out


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
