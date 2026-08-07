"""pdc_api.bulkload — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
import json
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from .core import TokenExpired, _req, clean_base
from .jobs import _JOB_BAD, _JOB_OK, _SECRET_KEYS, _execute_job, job_status

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


# The scan's profiling switches, read off a real job record from PDC's own
# "Configure Process" dialog (jobType "File System Scan", schemaId
# "file_system_scan"). PDC defaults withProfile and headerExists to FALSE, and
# sending no value inherits that - which catalogues every CSV with no columns,
# or with columns named Column-0..Column-N because the header row was read as
# data. Both are the wrong answer for a structured file, so both are set here.
#
# classification stays FALSE deliberately, and that is not timidity: PDC's
# classifier assigns BUSINESS TERMS, which do not exist until this app has built
# the glossary - and it builds it from the very profile this scan produces.
# Enabling it on a first pass can only mark everything unclassified. Once the
# glossary is applied, a second deliberate pass with classification on is worth
# running over UNSTRUCTURED documents, where there are no column names to reason
# from. Structured files never need it: the app assigns their terms directly.
_SCAN_PROFILE_DEFAULTS = {
    "withProfile": True,        # "Profile structured and semi-structured files"
    "headerExists": True,       # "Treat first row as header"
    "withChecksum": True,       # "Compute checksum of document content"
    "withDocMetadata": True,    # owner, page count, paragraph count
    "classification": False,    # needs business terms that do not exist yet
    "addressDetection": False,  # same dependency: it tags a term you must supply
    "summarizeDocuments": False,
}


def internal_scan_files(base_url, token, data_body, verify_tls=True, timeout=30,
                        profile_files=True, header_row=True):
    """EXPERIMENTAL / UNSUPPORTED: trigger an object-store file scan via PDC's INTERNAL
       UI endpoint (POST /api/start-job) — the call the web app's "Scan Files" button
       makes. It is NOT part of the public API: no /public/, no version, undocumented,
       and it may change or break between PDC releases. Gated behind an explicit toggle.
       Body shape (from the UI capture): {name:"METADATA_INGEST", type:"START", data:{…}}."""
    url = clean_base(base_url) + "/api/start-job"
    data_body = dict(data_body or {})
    for k, v in _SCAN_PROFILE_DEFAULTS.items():
        data_body.setdefault(k, v)

    # OPEN BUG - an object-store scan started here enumerates nothing.
    #
    # PDC's SCAN_ROUTER creates our METADATA_INGEST as a **METADATA_REINGEST**
    # pipeline, which looks for CHANGES rather than walking the bucket: the job
    # reports "Data Discovery: total: 0", COMPLETES, and leaves the Data Canvas
    # empty. The database path is unaffected - it goes through the public
    # metadata/ingest job and gets a metadata_ingest pipeline, which works.
    #
    # Measured against the lab 2026-08-07, with the bucket holding 16 objects,
    # MinIO reachable from inside the worker container and the credentials
    # independently verified. Ruled out: containers, an empty path prefix,
    # fullRescan=true, and the public metadata/ingest endpoint. What is still
    # needed is a capture of what PDC's own "Scan Files" button sends, since
    # that produces a first ingest and this does not.
    #
    # The worker enumerates from `containers` (PLURAL); the data-source body
    # carries `container` (singular). A working scan captured from PDC's UI
    # carries both, so both are sent - necessary, evidently not sufficient.
    if not data_body.get("containers") and data_body.get("container"):
        data_body["containers"] = [data_body["container"]]

    # Values PDC's own Configure Process dialog sends that an API-built body
    # leaves null. patternType must accompany include/excludePatterns ("*.md" is
    # a valid glob and an invalid regex); the two day-filters are the dialog's
    # sliders, default 0 = no age restriction; contentScanType matches a captured
    # working scan.
    #
    # HONEST STATUS (measured against the lab 2026-08-07): setting these makes
    # the job COMPLETE rather than FAIL, but it still enumerates nothing on an
    # object store - see the note on METADATA_REINGEST in internal_scan_files.
    # They are kept because they match a known-good scan, not because they are
    # known to fix anything.
    #
    # Deliberately NOT setting supportedMaxFileSize: the dialog defaults it to
    # 100MB, but null appears to mean "no ceiling", and silently capping an
    # estate's large files would be a worse bug than the one being chased.
    for k, v in (("patternType", "GLOB"),
                 ("filesModifiedLaterThanDays", 0),
                 ("filesAccessedLaterThanDays", 0),
                 ("contentScanType", "SCAN_ONLY")):
        if data_body.get(k) in (None, ""):
            data_body[k] = v
    # Explicit arguments win over the defaults above, so a caller can scan
    # metadata only, or handle a headerless CSV, without editing this table.
    data_body["withProfile"] = bool(profile_files)
    data_body["headerExists"] = bool(header_row)
    body = {"name": "METADATA_INGEST", "type": "START", "data": data_body}
    out = _req("POST", url, token=token, body=body, verify_tls=verify_tls, timeout=timeout)
    d = out.get("data", out) if isinstance(out, dict) else {}
    jid = (d.get("jobId") or d.get("id") or d.get("_id")) if isinstance(d, dict) else None
    return {"job_id": jid, "raw": out}


# 40 pages x 500 = 20,000 entities per source. Generous for a real estate while
# still bounded, so a catalog far larger than expected cannot spin here forever.
# A source that genuinely exceeds it is REPORTED rather than quietly clipped -
# a short scope that says SUCCESS is the failure mode this whole path already had.
_ENTITY_MAX_PAGES = 40


def source_entity_ids(base_url, token, resource_name=None, resource_id=None,
                      kinds=("TABLE",), limit=500, verify_tls=True, timeout=30,
                      version="v2"):
    """Entity UUIDs belonging to a data source, for scoping the profiling job.
       Profiling takes ENTITY uuids (POST /entities/filter, v3), not the
       data-source create id — the same distinction ingest vs re-ingest has.
       Entities carry `resourceId` (the data source's _id) rather than its name,
       so a name is resolved to that id first."""
    rid = resource_id
    if not rid and resource_name:
        ex = find_existing_data_source(base_url, token, resource_name, version,
                                       verify_tls, timeout) or {}
        rid = ex.get("_id") or ex.get("resourceId") or ex.get("id")
    # Ask the SERVER for this source's entities, and follow the cursor.
    #
    # This used to post {"filters": {}} with size=500 and keep the matching rows
    # in Python: it read the first 500 entities of the WHOLE ESTATE and profiled
    # whichever of this source's entities happened to land inside that window.
    # On a demo estate that mostly worked; on a real one the source's entities
    # would rarely be in the first page at all, so the job would scope to almost
    # nothing and still report SUCCESS. Nothing about the result said so.
    #
    # entities.filter_entities already does this correctly - filters server-side
    # and follows the cursor across pages - so it is used rather than a second,
    # worse copy living here.
    from .entities import filter_entities
    filters = {}
    if rid:
        filters["resourceIds"] = [str(rid)]
    want = {str(k).upper() for k in (kinds or ())}
    if want:
        filters["types"] = sorted(want)

    rows = filter_entities(base_url, token, filters, version="v3",
                           verify_tls=verify_tls, timeout=timeout,
                           extended=False, size=min(int(limit), 500),
                           max_pages=_ENTITY_MAX_PAGES)
    ids = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        # Re-checked client-side: a server that ignores a filter it does not
        # recognise would otherwise hand back the whole estate, and scoping a
        # profiling job to another source's entities is worse than scoping it
        # to none.
        if want and str(r.get("type") or "").upper() not in want:
            continue
        if rid and str(r.get("resourceId") or "") != str(rid):
            continue
        eid = r.get("_id") or r.get("id")
        if eid:
            ids.append(eid)
    return ids


def profile_source(base_url, token, resource_name=None, version="v2", verify_tls=True,
                   timeout=30, wait=False, poll_wait=3.0, max_wait=600, limit=500,
                   resource_id=None, object_store=False):
    """Run PDC's analysis job over a data source's entities. Both are PUBLIC,
       supported jobs (worker DATA_PROFILE), unlike the object-store file scan:

         structured (JDBC)      -> data-profiling, scoped to TABLE entities
                                   ("Data Profiling": distributions, uniqueness,
                                   patterns — the evidence DQ and identification use)
         unstructured (files)   -> data-discovery, scoped to FOLDER/FILE entities
                                   ("Data Discovery": what's inside the documents)

       POST /jobs/execute/<job> {"scope":[<entity uuid>…], "configs":{}}.
       Returns {job_id, entities, ok, status, error, activity}."""
    job = "data-discovery" if object_store else "data-profiling"
    kinds = ("FOLDER", "FILE") if object_store else ("TABLE",)
    ids = source_entity_ids(base_url, token, resource_name, resource_id, kinds=kinds,
                            verify_tls=verify_tls, timeout=timeout, limit=limit,
                            version=version)
    if not ids:
        return {"job_id": None, "entities": 0, "ok": False, "activity": job,
                "error": ("no scanned files found to discover — run the object store's "
                          "Scan Files in PDC first"
                          if object_store else
                          "no ingested tables found to profile — run the metadata ingest first")}
    jr = run_job(base_url, token, job, {"scope": ids, "configs": {}},
                 version, verify_tls, timeout)
    rec = {"job_id": jr["job_id"], "entities": len(ids), "ok": bool(jr["job_id"]),
           "activity": job, "error": None, "warning": None}
    # No silent caps: a scope clipped at the page ceiling profiles part of the
    # source and still returns SUCCESS, which reads as "all done".
    if len(ids) >= _ENTITY_MAX_PAGES * min(int(limit), 500):
        rec["warning"] = ("scope hit the %d-entity ceiling — this source has more, and "
                          "the rest were NOT included" % len(ids))
    if wait and jr["job_id"]:
        w = wait_job(base_url, token, jr["job_id"], version, verify_tls, timeout,
                     poll_wait=poll_wait, max_wait=max_wait)
        rec["ok"] = bool(w.get("ok"))
        rec["status"] = w.get("status")
        if not w.get("ok"):
            rec["error"] = ("profiling job ended %s" % w.get("status")) + (
                " — %s" % w["error"] if w.get("error") else "")
    return rec


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
                  internal_scan=False, do_profile=False, header_row=True):
    """Process a single row: create the data source, then trigger the metadata
       re-ingest job scoped to the new record and (optionally) poll it to a
       terminal state. Never raises for a row-level failure — returns a result
       record. TokenExpired DOES propagate so the caller can re-auth and retry.

       do_test is accepted for backward compatibility but is a no-op: PDC exposes
       no confirmed public test-connection job, and the app validates connectivity
       locally (Test connection buttons) before bulk load."""
    rec = {"resourceName": (row.get("resourceName") or row.get("name") or ""),
           "create": "SKIP", "ingest": "SKIP", "job": "SKIP", "profile": "SKIP",
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
                # FAILS CLOSED. This used to delete unless the text looked like a
                # validation error - so an error it could not READ was taken as
                # proof of a name conflict. When core.py briefly lost the response
                # body, every create failed as a bare "HTTP Error 400: Bad
                # Request", and this guard deleted working sources on the strength
                # of a message it had never parsed. Deleting now needs positive
                # evidence that the name is the only thing wrong; anything else,
                # including an unreadable error, keeps the existing source.
                looks_like_conflict = any(w in m for w in (
                    "already exists", "already in use", "duplicate", "conflict",
                    "409", "unique"))
                if not looks_like_conflict:
                    rec["create"] = "FAIL"
                    rec["error"] = ("recreate aborted, existing source kept — the create "
                                    "failed for some reason other than the name being "
                                    "taken: " + str(ce)[:200])
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
            # An object store's files reach the catalog ONLY through the file
            # scan, and Data Discovery analyses what that scan produced — so
            # "profile / discover" has to run the scan first or it discovers
            # nothing. The public API doesn't expose the trigger, so this uses
            # PDC's internal /api/start-job (the UI's own Scan Files call) with
            # the same bearer token.
            if internal_scan or do_profile:
                # PDC's internal /api/start-job — the UI's Scan Files call.
                data = dict(body)
                data["resourceId"] = rec["resourceId"]
                _fq = (cr.get("record") or {}).get("fqdnId") if isinstance(cr, dict) else None
                if _fq:
                    data["fqdnId"] = _fq
                data.setdefault("deleteEmptyFolders", False)
                data.setdefault("incremental", False)
                try:
                    # The scan is what profiles a structured file, so the profile
                    # switch belongs here - not only on the Discovery job after it.
                    jr = internal_scan_files(base_url, token, data, verify_tls, timeout,
                                             profile_files=bool(do_profile),
                                             header_row=bool(header_row))
                    rec["jobId"] = jr["job_id"]
                    ingest_ok = True
                    rec["ingest"] = "OK"
                    rec["job"] = "SENT"
                    rec["note"] = "file scan triggered (PDC internal /api/start-job — the UI's Scan Files call)"
                    if wait and jr["job_id"]:
                        w = wait_job(base_url, token, jr["job_id"], version, verify_tls,
                                     timeout, poll_wait=poll_wait, max_wait=max_wait)
                        if w.get("status"):
                            rec["job"] = "OK" if w["ok"] else ("TIMEOUT" if w.get("timeout") else "FAIL")
                            if not w["ok"] and w.get("error"):
                                rec["error"] = "internal scan: " + str(w["error"])[:200]
                except Exception as e:
                    rec["ingest"] = "FAIL"
                    msg = str(e)[:200]
                    # PDC's proxy routes the INTERNAL api by hostname: reached on a
                    # bare IP it 401s even with a valid token, while the public API
                    # answers fine — so only the file scan fails, confusingly.
                    host = urllib.parse.urlparse(clean_base(base_url)).hostname or ""
                    if "401" in msg and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
                        msg += (" — PDC routes its internal API by hostname; use the vhost URL "
                                "(e.g. https://pentaho.io) as the PDC base URL, not the IP %s." % host)
                    rec["error"] = "internal /api/start-job failed: " + msg
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

        # Profiling runs AFTER the ingest: it is scoped to the entities the
        # ingest created, so it needs that job to have finished (wait=True) —
        # otherwise there are no tables to profile yet.
        # object stores skip the ingest (no public file-scan trigger), so gate on
        # a good create instead: Data Discovery still runs over whatever files a
        # previous Scan Files put in the catalog.
        if do_profile and create_ok and rec["job"] in ("OK", "SENT", "SKIP", "TIMEOUT"):
            try:
                pr = profile_source(base_url, token, rec["resourceName"], version,
                                    verify_tls, timeout, wait=wait,
                                    poll_wait=poll_wait, max_wait=max_wait,
                                    resource_id=rec["resourceId"],
                                    object_store=_is_object_store)
                if pr.get("job_id"):
                    rec["profileJobId"] = pr["job_id"]
                    rec["profile"] = "OK" if pr.get("ok") else "FAIL"
                    label = "discovering" if _is_object_store else "profiling"
                    rec["note"] = ((rec.get("note") + " · ") if rec.get("note") else "") + \
                        "%s %d entit%s" % (label, pr["entities"], "y" if pr["entities"] == 1 else "ies")
                    if pr.get("warning"):
                        rec["note"] += " · " + pr["warning"]
                else:
                    rec["profile"] = "FAIL"
                if pr.get("error") and not rec["error"]:
                    rec["error"] = str(pr["error"])[:200]
            except TokenExpired:
                raise
            except Exception as e:
                rec["profile"] = "FAIL"
                if not rec["error"]:
                    rec["error"] = "profiling failed: " + str(e)[:200]

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
