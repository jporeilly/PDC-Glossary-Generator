"""Document store - MinIO/S3 access, harvest, previews, the document DQ
profiler and the document term suggesters.

Carved from suggester.py (1.38.18) - a pure move; suggester.py remains the
import surface (facade) so no call site changes."""
import os, re, json, uuid
from core import paths
from engine import tagdict
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS
from engine.sug_profile import _profile_values
from engine.sug_suggest import (humanize, quality_score_column,
                               rate_document, suggest, suggest_tags)

# --------------------------------------------------------- DOCUMENT STORE (MinIO/S3)
# Ownership can only be "determined" from the store if it was recorded there.
# We look, in order, at: S3 object tags, x-amz-meta-* user metadata, and bucket
# tags. Keys that look like an owner/steward field are treated as a binding hint
# (resolved later against the people roster by email/username).
OWNER_KEYS = ("steward", "datasteward", "businesssteward", "owner", "custodian", "maintainer")

def _looks_like_owner(key):
    """True when a tag/metadata key looks like an owner/steward field."""
    k = re.sub(r"[^a-z]", "", (key or "").lower())
    return any(o in k for o in OWNER_KEYS)

def _owner_from_pairs(pairs):
    """Pick an owner/steward value out of (key, value) tag/metadata pairs."""
    for k, v in pairs:
        if _looks_like_owner(k) and v:
            return str(v).strip()
    return ""

def _s3_client(cfg):
    """Build an S3 client for a MinIO/S3 endpoint. Raises a clear error if boto3
       is missing or the endpoint is unreachable (callers surface the message)."""
    try:
        import boto3
        from botocore.config import Config
    except Exception:
        raise RuntimeError("boto3 not installed - run: pip install boto3")
    endpoint = (cfg.get("endpoint") or "").strip()
    secure = bool(cfg.get("secure", False))
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = ("https://" if secure else "http://") + endpoint
    return boto3.client(
        "s3", endpoint_url=endpoint or None,
        aws_access_key_id=cfg.get("access_key") or cfg.get("user") or "",
        aws_secret_access_key=cfg.get("secret_key") or cfg.get("password") or "",
        region_name=cfg.get("region") or "us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=8, read_timeout=15, retries={"max_attempts": 2}))

def test_minio(cfg):
    """Verify a MinIO/S3 connection without a full scan: {ok, message, objects, tagging}."""
    bucket = (cfg.get("bucket") or "").strip()
    if not bucket:
        return {"ok": False, "message": "No bucket specified"}
    try:
        s3 = _s3_client(cfg)
    except Exception as e:
        return {"ok": False, "needs_driver": "boto3" in str(e), "message": str(e)}
    try:
        resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
        n = resp.get("KeyCount", 0)
        tagging = False
        if resp.get("Contents"):
            try:
                s3.get_object_tagging(Bucket=bucket, Key=resp["Contents"][0]["Key"])
                tagging = True
            except Exception:
                tagging = False
        return {"ok": True, "message": "Bucket reachable", "objects": n, "tagging": tagging}
    except Exception as ex:
        return {"ok": False, "message": _minio_error_hint(ex)}


def _minio_error_hint(ex):
    """Turn a boto/botocore exception into a one-line reason with a lab-specific
       hint for the common mistakes (TLS scheme mismatch, wrong keys, wrong port)."""
    s = str(ex)
    msg = f"Connection failed: {ex}"
    if "WRONG_VERSION_NUMBER" in s:
        msg += (" — the endpoint answered plain HTTP to a TLS handshake: this "
                "port has no TLS. Use http:// in the endpoint and untick HTTPS "
                "(MinIO on :9000 is usually plain HTTP in the lab).")
    elif "record layer failure" in s or "UNEXPECTED_RECORD" in s:
        msg += (" — scheme mismatch between the endpoint URL and the TLS toggle; "
                "make http/https and the HTTPS tick agree.")
    elif "InvalidAccessKeyId" in s:
        msg += " — the access key doesn't exist on this MinIO; check the Access key."
    elif "SignatureDoesNotMatch" in s:
        msg += " — the secret key is wrong for that access key."
    elif "Could not connect" in s or "Connection refused" in s or "Failed to establish" in s or "timed out" in s:
        msg += (" — endpoint unreachable. The S3 API is on :9000 (:9001 is the "
                "web console only); check host/port and that MinIO is up.")
    return msg


def reach_minio(cfg):
    """Bucket-agnostic reachability + auth check for the connection status dot.
       list_buckets validates the endpoint and credentials without needing a
       specific bucket to exist (the lab export bucket is created on first use).
       {ok, message, buckets?}."""
    try:
        s3 = _s3_client(cfg)
    except Exception as e:
        return {"ok": False, "needs_driver": "boto3" in str(e), "message": str(e)}
    try:
        resp = s3.list_buckets()
        names = [b.get("Name") for b in resp.get("Buckets", [])]
        return {"ok": True, "message": "Connected", "buckets": names}
    except Exception as ex:
        # An authenticated-but-unauthorized account (some lab "cast" users can
        # write to their own bucket but not list) still proves the endpoint and
        # keys are good — treat that as connected, just without listing rights.
        if "AccessDenied" in str(ex):
            return {"ok": True, "message": "Connected (account can't list buckets)",
                    "buckets": []}
        return {"ok": False, "message": _minio_error_hint(ex)}

_TEXT_EXTS = {"txt", "csv", "tsv", "json", "jsonl", "ndjson", "xml", "md", "log",
              "yaml", "yml", "html", "htm", "sql", "py", "sh", "conf", "ini", "properties"}
_IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"}
_CTYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
           "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
           "bmp": "image/bmp", "svg": "image/svg+xml",
           "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           "txt": "text/plain", "csv": "text/csv", "json": "application/json",
           "html": "text/html", "htm": "text/html", "xml": "application/xml"}


def _ext_of(key):
    """Lowercased extension of an object key (last path segment)."""
    leaf = key.rsplit("/", 1)[-1]
    return leaf.rsplit(".", 1)[-1].lower() if "." in leaf else ""


def _guess_ctype(key, fallback=""):
    """Content-type from extension (authoritative for known viewable types), so a PDF
       streamed from MinIO renders even when the store reports octet-stream."""
    return _CTYPES.get(_ext_of(key)) or fallback or "application/octet-stream"


def list_objects(cfg, prefix="", max_keys=2000):
    """List ONE level of a bucket (S3 delimiter='/') for the file browser:
       subfolders (CommonPrefixes) + files at this prefix with size/modified/ext.
       `prefix` is relative to the connection's configured base prefix."""
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    base = (cfg.get("prefix") or "").strip().strip("/")
    bpref = base + "/" if base else ""
    rel = (prefix or "").strip().strip("/")
    full = bpref + (rel + "/" if rel else "")
    folders, files, count, truncated = [], [], 0, False
    for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=full, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            p = cp.get("Prefix", "")
            name = p[len(full):].rstrip("/")
            if name:
                folders.append({"name": name, "prefix": p[len(bpref):].rstrip("/")})
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/") or key == full:
                continue
            name = key[len(full):]
            if "/" in name:
                continue
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            mod = obj.get("LastModified")
            files.append({"name": name, "key": key, "size": obj.get("Size", 0),
                          "modified": mod.isoformat() if mod else "", "ext": ext})
            count += 1
            if count >= max_keys:
                truncated = True
                break
        if truncated:
            break
    folders.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())
    total_bytes = sum(f["size"] for f in files)
    return {"bucket": bucket, "base_prefix": base, "prefix": rel,
            "folders": folders, "files": files, "total_bytes": total_bytes,
            "file_count": len(files), "folder_count": len(folders), "truncated": truncated}


def object_detail(cfg, key, max_preview=6000):
    """Metadata + tags (+ a short text preview for text-like files) for one object."""
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    out = {"key": key, "name": key.rsplit("/", 1)[-1], "tags": [], "metadata": {},
           "preview": None, "preview_truncated": False}
    try:
        h = s3.head_object(Bucket=bucket, Key=key)
        out["size"] = h.get("ContentLength", 0)
        out["content_type"] = h.get("ContentType", "")
        out["modified"] = h.get("LastModified").isoformat() if h.get("LastModified") else ""
        out["metadata"] = dict(h.get("Metadata", {}) or {})
    except Exception as e:
        out["error"] = str(e)
        return out
    try:
        ts = s3.get_object_tagging(Bucket=bucket, Key=key).get("TagSet", [])
        out["tags"] = [{"key": t["Key"], "value": t["Value"]} for t in ts]
    except Exception:
        out["tags"] = []
    ext = key.rsplit(".", 1)[-1].lower() if "." in key.rsplit("/", 1)[-1] else ""
    out["ext"] = ext
    # classify how the UI should show it
    if ext == "pdf":
        out["preview_kind"] = "pdf"
    elif ext == "docx":
        out["preview_kind"] = "docx"
    elif ext in _IMAGE_EXTS:
        out["preview_kind"] = "image"
    elif ext in _TEXT_EXTS:
        out["preview_kind"] = "text"
    else:
        out["preview_kind"] = "none"

    if ext in _TEXT_EXTS and out.get("size", 0) > 0:
        raw = _get_object_bytes(s3, bucket, key, max_preview)
        if raw:
            try:
                out["preview"] = raw.decode("utf-8", errors="replace")
            except Exception:
                out["preview"] = None
            out["preview_truncated"] = out.get("size", 0) > max_preview
    elif ext == "docx" and 0 < out.get("size", 0) <= _DOCX_MAX:
        # Word docs can't render natively, so convert to HTML server-side
        try:
            data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            html, how = docx_to_html(data)
            out["html"] = html
            out["docx_renderer"] = how
        except Exception as e:
            out["html"] = None
            out["docx_error"] = str(e)
    return out


_VIEW_MAX = 25 * 1024 * 1024   # cap inline viewing at 25 MB
_DOCX_MAX = 8 * 1024 * 1024    # convert Word docs up to 8 MB


def get_object_bytes_full(cfg, key, max_bytes=_VIEW_MAX):
    """Fetch a whole object for inline viewing (PDF/image), with its content-type.
       Refuses files over max_bytes so a huge object can't be pulled into a view."""
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    h = s3.head_object(Bucket=bucket, Key=key)
    size = h.get("ContentLength", 0)
    if size and size > max_bytes:
        raise ValueError(f"File is {size:,} bytes — too large to view inline "
                         f"(limit {max_bytes // (1024*1024)} MB). Use Download instead.")
    ctype = _guess_ctype(key, h.get("ContentType", ""))
    data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return data, ctype


def docx_to_html(data):
    """Render a .docx to HTML. Prefers mammoth (keeps headings/lists/bold); falls back
       to python-docx (paragraph text); returns (html_or_None, renderer_name)."""
    import io
    try:
        import mammoth
        res = mammoth.convert_to_html(io.BytesIO(data))
        return res.value or "<p><em>(empty document)</em></p>", "mammoth"
    except ImportError:
        pass
    except Exception as e:
        return None, f"mammoth-error: {e}"
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        parts = []
        for p in doc.paragraphs:
            t = (p.text or "").strip()
            if not t:
                continue
            style = (p.style.name or "").lower() if p.style else ""
            if "heading 1" in style or style == "title":
                parts.append(f"<h2>{_html_escape(t)}</h2>")
            elif "heading" in style:
                parts.append(f"<h3>{_html_escape(t)}</h3>")
            elif "list" in style:
                parts.append(f"<li>{_html_escape(t)}</li>")
            else:
                parts.append(f"<p>{_html_escape(t)}</p>")
        for tbl in getattr(doc, "tables", []):
            rows = []
            for r in tbl.rows:
                cells = "".join(f"<td>{_html_escape(c.text.strip())}</td>" for c in r.cells)
                rows.append(f"<tr>{cells}</tr>")
            if rows:
                parts.append("<table border='1' cellspacing='0' cellpadding='4'>"
                             + "".join(rows) + "</table>")
        return ("\n".join(parts) or "<p><em>(empty document)</em></p>", "python-docx")
    except ImportError:
        return None, "no-renderer"
    except Exception as e:
        return None, f"docx-error: {e}"


def _html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def harvest_minio(cfg, max_objects=20000, tag_sample=600):
    """Walk a bucket, roll objects into top-level folders, and sniff ownership.
       Returns (folders_dict, ownership_report, scanned_counts)."""
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    prefix = (cfg.get("prefix") or "").lstrip("/")
    folders, n, tagged = {}, 0, 0
    ownership = {"bucket_owner": "", "by_folder": {}, "signals": [], "tags_sampled": 0}

    try:
        bt = s3.get_bucket_tagging(Bucket=bucket).get("TagSet", [])
        ownership["bucket_owner"] = _owner_from_pairs((t["Key"], t["Value"]) for t in bt)
    except Exception:
        pass

    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            rel = key[len(prefix):].lstrip("/") if prefix else key
            top = rel.split("/")[0] if "/" in rel else "(root)"
            fpref = "/".join([p for p in [prefix.rstrip("/"), (top if top != "(root)" else "")] if p])
            f = folders.setdefault(top, {"name": top, "prefix": fpref, "count": 0,
                                         "bytes": 0, "exts": {}, "samples": [], "owners": {}})
            f["count"] += 1
            f["bytes"] += obj.get("Size", 0)
            base = key.rsplit("/", 1)[-1]
            if "." in base:
                ext = base.rsplit(".", 1)[-1].lower()
                f["exts"][ext] = f["exts"].get(ext, 0) + 1
            if len(f["samples"]) < 3:
                f["samples"].append(rel)
            n += 1
            if tagged < tag_sample:
                owner = ""
                try:
                    ts = s3.get_object_tagging(Bucket=bucket, Key=key).get("TagSet", [])
                    owner = _owner_from_pairs((t["Key"], t["Value"]) for t in ts)
                except Exception:
                    pass
                if not owner:
                    try:
                        meta = s3.head_object(Bucket=bucket, Key=key).get("Metadata", {})
                        owner = _owner_from_pairs(meta.items())
                    except Exception:
                        pass
                if owner:
                    f["owners"][owner] = f["owners"].get(owner, 0) + 1
                tagged += 1
            if n >= max_objects:
                break
        if n >= max_objects:
            break

    ownership["tags_sampled"] = tagged
    for top, f in folders.items():
        if f["owners"]:
            f["owner"] = max(f["owners"], key=f["owners"].get)
            ownership["by_folder"][top] = f["owner"]
    if ownership["bucket_owner"]:
        ownership["signals"].append(f"Bucket tag owner: {ownership['bucket_owner']}")
    for top, ow in ownership["by_folder"].items():
        ownership["signals"].append(f"Folder '{top}' owner tag/metadata: {ow}")
    if not ownership["signals"]:
        ownership["signals"].append(
            f"No owner/steward signal found in object tags or x-amz-meta-* metadata "
            f"({tagged} object(s) sampled). Assign the steward manually.")
    return folders, ownership, {"objects": n, "folders": len(folders)}

# ----------------------------------------------------- DOCUMENT DATA-QUALITY PROFILER
# These helpers let the app compute a real Data-Quality score for object-store files
# by reading their CONTENT, instead of leaving the Data Quality input blank for PDC
# to fill later. The output is a dims dict {c,u,v,eu,nn} that is byte-for-byte
# compatible with the Source_Quality_Dims that SQL columns produce, so a document
# rides the SAME weighted scorer (quality_score_column) and the SAME apply pipeline
# (data_element_links -> links_to_api_json -> features.qualityScore -> PATCH).

# File formats we can profile from bytes. Anything else (pdf, docx, images, binary)
# returns None and is left to PDC's own document profiling.
_DQ_TEXT_EXTS  = {"txt", "md", "log", "rtf"}      # free text / prose / logs
_DQ_JSON_EXTS  = {"json"}                          # one whole-document JSON value
_DQ_JSONL_EXTS = {"jsonl", "ndjson"}              # one JSON record per line
_DQ_DELIM_EXTS = {"csv", "tsv", "psv"}            # delimited record sets
_DQ_XML_EXTS   = {"xml"}                          # one whole-document XML tree
_DQ_PROFILABLE = (_DQ_TEXT_EXTS | _DQ_JSON_EXTS | _DQ_JSONL_EXTS
                  | _DQ_DELIM_EXTS | _DQ_XML_EXTS)
# Line-oriented formats can be profiled from a truncated HEAD of a large file (we drop
# the last, possibly-incomplete line). Whole-document formats (json/xml) cannot be
# truncated without breaking the parse, so large ones are skipped (-> defer to PDC).
_DQ_LINE_EXTS = _DQ_TEXT_EXTS | _DQ_JSONL_EXTS | _DQ_DELIM_EXTS


def _completeness_of_records(records):
    """completeness = non-empty values / total values across a list of flat records.
       A value is 'empty' if it is None or a blank/whitespace-only string. Nested
       dict/list values count as present (non-empty) -- we only penalise true gaps.
       Returns a 0.0-1.0 fraction, or None when there is nothing to measure."""
    total = filled = 0
    for rec in records:
        if isinstance(rec, dict):
            for v in rec.values():
                total += 1
                if v is None:
                    continue
                if isinstance(v, str) and not v.strip():
                    continue
                filled += 1
        else:
            # a bare (non-dict) record counts as a single cell
            total += 1
            if rec not in (None, "") and not (isinstance(rec, str) and not rec.strip()):
                filled += 1
    return (filled / total) if total else None


def _uniqueness_of(rows):
    """uniqueness = distinct / total over row signatures. A high value means few
       duplicate records, which is a data-quality positive. JSON-encodes each row
       with sorted keys so dict order doesn't create false 'differences'."""
    if not rows:
        return None
    sigs = [json.dumps(r, sort_keys=True, default=str) for r in rows]
    return len(set(sigs)) / len(sigs)


def profile_document_object(content, ext):
    """Compute Data-Quality dimensions for ONE object's content.

       Returns a dims dict shaped exactly like a column's Source_Quality_Dims entry:
         c  completeness  non-empty values / total values
         v  validity      well-formedness: parses cleanly / decodes as UTF-8
         u  uniqueness    distinct records / total (duplicate detection)
         eu expect_unique whether uniqueness should count toward the score. True only
                          for record-set files (JSON array / JSONL / delimited),
                          where duplicate rows are a genuine defect; False for a
                          single object or free text, where 'uniqueness' is meaningless
         nn notnull       always False here -- we measure completeness directly rather
                          than inferring it from a NOT NULL constraint
       Returns None when the extension isn't content-profilable (pdf/docx/binary),
       so the caller leaves the Data Quality input to PDC."""
    ext = (ext or "").lower()
    if not content or ext not in _DQ_PROFILABLE:
        return None

    # Decode to text. For a format that is supposed to be text, undecodable bytes are
    # themselves a validity defect, so we remember whether the UTF-8 decode succeeded.
    try:
        text = content.decode("utf-8")
        decoded = True
    except Exception:
        try:
            text = content.decode("latin-1")   # last-resort so we can still inspect
        except Exception:
            return None
        decoded = False

    # ---- JSON: a single whole-document value (object, array, or scalar) ----------
    if ext in _DQ_JSON_EXTS:
        try:
            obj = json.loads(text)
        except Exception:
            # malformed JSON -> validity 0; nothing else is trustworthy to measure
            return {"c": None, "u": None, "v": 0.0, "eu": False, "nn": False}
        if isinstance(obj, list):                       # array of records
            return {"c": _completeness_of_records(obj), "u": _uniqueness_of(obj),
                    "v": 1.0, "eu": True, "nn": False}
        if isinstance(obj, dict):                       # one record
            return {"c": _completeness_of_records([obj]), "u": None,
                    "v": 1.0, "eu": False, "nn": False}
        return {"c": 1.0 if obj not in (None, "") else 0.0, "u": None,
                "v": 1.0, "eu": False, "nn": False}     # bare scalar, still well-formed

    # ---- JSONL / NDJSON: one JSON record per line --------------------------------
    if ext in _DQ_JSONL_EXTS:
        recs, bad = [], 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                bad += 1                                # a line that won't parse = defect
        total = len(recs) + bad
        validity = (len(recs) / total) if total else 0.0
        return {"c": _completeness_of_records(recs), "u": _uniqueness_of(recs),
                "v": validity, "eu": True, "nn": False}

    # ---- delimited record sets: CSV / TSV / PSV ----------------------------------
    if ext in _DQ_DELIM_EXTS:
        import csv, io
        delim = {"csv": ",", "tsv": "\t", "psv": "|"}[ext]
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r]
        if not rows:
            return {"c": None, "u": None, "v": 1.0 if decoded else 0.0,
                    "eu": False, "nn": False}
        header, body = rows[0], rows[1:]
        ncol = len(header)
        # validity = share of body rows whose column count matches the header; a
        # ragged row (too few/many fields) is a structural quality defect.
        validity = (sum(1 for r in body if len(r) == ncol) / len(body)) if body else 1.0
        # completeness = non-empty cells / total cells across the body rows.
        cells = filled = 0
        for r in body:
            for v in r:
                cells += 1
                if str(v).strip():
                    filled += 1
        completeness = (filled / cells) if cells else None
        # uniqueness = distinct body rows / total -> duplicate-record detection.
        uniqueness = _uniqueness_of([tuple(r) for r in body]) if body else None
        return {"c": completeness, "u": uniqueness, "v": validity,
                "eu": True, "nn": False}

    # ---- XML: one whole-document tree --------------------------------------------
    if ext in _DQ_XML_EXTS:
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(text)
        except Exception:
            return {"c": None, "u": None, "v": 0.0, "eu": False, "nn": False}
        # completeness = non-empty attribute values + non-empty leaf text / all slots.
        total = filled = 0
        for el in root.iter():
            for av in el.attrib.values():
                total += 1
                if str(av).strip():
                    filled += 1
            if not list(el):                            # leaf element -> has text slot
                total += 1
                if (el.text or "").strip():
                    filled += 1
        completeness = (filled / total) if total else None
        return {"c": completeness, "u": None, "v": 1.0, "eu": False, "nn": False}

    # ---- plain text / markdown / logs --------------------------------------------
    # completeness = non-blank lines / total lines (an all-whitespace file is poor);
    # validity = decoded cleanly as UTF-8; uniqueness is not meaningful for prose.
    lines = text.splitlines()
    nonblank = sum(1 for ln in lines if ln.strip())
    completeness = (nonblank / len(lines)) if lines else (1.0 if text.strip() else 0.0)
    return {"c": completeness, "u": None, "v": 1.0 if decoded else 0.0,
            "eu": False, "nn": False}


def _get_object_bytes(s3, bucket, key, max_bytes):
    """Fetch up to max_bytes of an object for profiling using a ranged GET, so a large
       file never pulls in whole. Returns bytes (possibly a truncated head) or b''.
       Sampling a head is acceptable for DQ the same way column profiling samples rows
       rather than scanning every value."""
    try:
        resp = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{max_bytes - 1}")
        return resp["Body"].read()
    except Exception:
        # some stores reject Range on tiny objects; fall back to a capped full GET
        try:
            return s3.get_object(Bucket=bucket, Key=key)["Body"].read(max_bytes)
        except Exception:
            return b""


def harvest_files(cfg, max_objects=20000, owner_sample=600,
                  profile_dq=False, dq_max_bytes=5_000_000, dq_sample=800,
                  content_columns=False):
    """Enumerate INDIVIDUAL objects (leaf files) in a bucket, retaining each key so
       metadata can be applied per file (harvest_minio rolls these up into folders and
       discards the keys). Honours the same include/exclude globs as discover_documents
       and samples owner tags/metadata up to owner_sample objects. Returns a list of
       file dicts: {key, rel, bucket, folder, base, ext, size, owner, recent}.

       When profile_dq is set, each content-profilable file (csv/tsv/psv/json/jsonl/
       xml/txt/md/log) up to dq_sample files is also READ (a head of up to dq_max_bytes)
       and scored for Data Quality; the resulting dims land on the file dict as 'qdims',
       which suggest_document_files turns into Source_Quality_Dims so the file's
       qualityScore is computed and PATCHed exactly like a SQL column's."""
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    prefix = (cfg.get("prefix") or "").lstrip("/")
    include = _doc_patterns(cfg.get("include"))
    exclude = _doc_patterns(cfg.get("exclude"))
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    files, n, sniffed, dq_done = [], 0, 0, 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            rel = key[len(prefix):].lstrip("/") if prefix else key
            base = key.rsplit("/", 1)[-1]
            if include and not _doc_match(rel, base, include):
                continue
            if exclude and _doc_match(rel, base, exclude):
                continue
            top = rel.split("/")[0] if "/" in rel else "(root)"
            ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
            lm = obj.get("LastModified")
            recent = False
            if lm is not None:
                try:
                    recent = (now - lm).days <= 90
                except Exception:
                    recent = False
            owner = ""
            if sniffed < owner_sample:
                try:
                    ts = s3.get_object_tagging(Bucket=bucket, Key=key).get("TagSet", [])
                    owner = _owner_from_pairs((t["Key"], t["Value"]) for t in ts)
                except Exception:
                    pass
                if not owner:
                    try:
                        meta = s3.head_object(Bucket=bucket, Key=key).get("Metadata", {})
                        owner = _owner_from_pairs(meta.items())
                    except Exception:
                        pass
                sniffed += 1
            rec_file = {"key": key, "rel": rel, "bucket": bucket, "folder": top,
                        "base": base, "ext": ext, "size": obj.get("Size", 0),
                        "owner": owner, "recent": recent}
            # Optional: read the object and compute a Data-Quality score from content.
            # Bounded two ways: only the first dq_sample files are profiled, and only a
            # head of up to dq_max_bytes is read per file. Whole-document formats
            # (json/xml) are skipped when larger than the cap (truncation would break
            # the parse); line-oriented formats are profiled from a head with the last
            # partial line dropped.
            if (profile_dq or content_columns) and dq_done < dq_sample and ext in _DQ_PROFILABLE:
                size = obj.get("Size", 0) or 0
                if size <= dq_max_bytes or ext in _DQ_LINE_EXTS:
                    raw = _get_object_bytes(s3, bucket, key, dq_max_bytes)
                    if raw and size > dq_max_bytes and ext in _DQ_LINE_EXTS:
                        raw = raw.rsplit(b"\n", 1)[0]      # drop truncated final line
                    if profile_dq:
                        qd = profile_document_object(raw, ext)
                        if qd:
                            rec_file["qdims"] = qd
                    if content_columns:
                        # same read, second harvest: the columns this object
                        # DECLARES become candidate terms downstream — the
                        # app-side parity of PDC cataloging a CSV's columns
                        cc = extract_document_columns(raw, ext)
                        if cc:
                            rec_file["columns"] = cc
                    dq_done += 1
            files.append(rec_file)
            n += 1
            if n >= max_objects:
                break
        if n >= max_objects:
            break
    return files

def _doc_patterns(s):
    """Parse a comma/newline-separated glob string into a lowercased pattern list.
       e.g. '*.md, inspections/*' -> ['*.md', 'inspections/*']."""
    if not s:
        return []
    return [p.strip().lower() for p in re.split(r"[,\n]+", str(s)) if p.strip()]


def _doc_match(rel, base, pats):
    """True if the object matches any glob pattern, tested against both its
       relative key (so 'inspections/*' works) and its basename (so '*.md' works)."""
    import fnmatch
    rl, bl = rel.lower(), base.lower()
    return any(fnmatch.fnmatch(bl, p) or fnmatch.fnmatch(rl, p) for p in pats)


def extract_document_columns(content, ext, max_cols=200, sample_rows=200):
    """The columns a content-profilable object DECLARES, with sampled values.
       Purely mechanical — whatever the file says, for any estate: delimited
       files (csv/tsv/psv) use their header row; JSON arrays and JSONL flatten
       each record's scalar leaves to dotted paths (readings.alarm,
       systems.flow_gpm) — the same shape PDC's own scanner catalogs. Returns
       [{column, values}], or [] when the format declares no columns."""
    ext = (ext or "").lower()
    if not content:
        return []
    try:
        text = content.decode("utf-8")
    except Exception:
        try:
            text = content.decode("latin-1")
        except Exception:
            return []

    if ext in _DQ_DELIM_EXTS:
        import csv as _csv, io
        delim = {"csv": ",", "tsv": "\t", "psv": "|"}[ext]
        rows = [r for r in _csv.reader(io.StringIO(text), delimiter=delim) if r]
        if not rows:
            return []
        header = [str(h).strip() for h in rows[0]]
        if not any(header):
            return []
        body = rows[1:sample_rows + 1]
        cols = []
        for i, h in enumerate(header[:max_cols]):
            if not h:
                continue
            cols.append({"column": h, "values": [r[i] for r in body if i < len(r)]})
        return cols

    records = []
    if ext in _DQ_JSON_EXTS:
        try:
            obj = json.loads(text)
        except Exception:
            return []
        if isinstance(obj, list):
            records = [r for r in obj if isinstance(r, dict)][:sample_rows]
        elif isinstance(obj, dict):
            records = [obj]
        else:
            return []
    elif ext in _DQ_JSONL_EXTS:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if isinstance(r, dict):
                records.append(r)
            if len(records) >= sample_rows:
                break
    else:
        return []

    coldict, order = {}, []

    def _leaves(node, prefix):
        if isinstance(node, dict):
            for k, v in node.items():
                _leaves(v, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(node, list):
            for x in node[:sample_rows]:
                _leaves(x, prefix)
        else:
            if prefix not in coldict:
                if len(coldict) >= max_cols:
                    return
                coldict[prefix] = []
                order.append(prefix)
            if node is not None and len(coldict[prefix]) < sample_rows:
                coldict[prefix].append(node)

    for r in records:
        _leaves(r, "")
    return [{"column": k, "values": coldict[k]} for k in order if k]


def suggest_document_columns(files, bucket="documents"):
    """Candidate terms from the COLUMNS content-profilable files declare — the
       app-side parity of PDC's own scanner, which catalogs a CSV's columns as
       COLUMN entities (field-caught: the direct scan produced 5 folder terms
       while PDC's harvest of the same bucket carried every column). Purely
       mechanical and estate-agnostic: each column's sampled values run the
       SAME deterministic profiler as a database column (_profile_values →
       patterns, enums, sensitivity), and the rows flow through suggest()'s
       document path — leaf naming, pack-driven categories, envelope pruning.
       Entries carry the full shape suggest() bracket-accesses (comment / pk /
       fk / notnull / type), so a document column and a SQL column are the
       same thing downstream."""
    tables = {}
    for f in files or []:
        cols = f.get("columns") or []
        if not cols:
            continue
        # the RELATIVE path is the "table" (its top folder becomes the
        # physical-fallback category: gis/asset_inventory.csv → Gis); the
        # bucket rides in the schema slot of the source identity instead —
        # live-test-caught: bucket-prefixed names filed every column under
        # one bucket-named category
        tname = f.get("rel") or f.get("base") or ""
        entries = []
        for c in cols:
            name = str(c.get("column") or "").strip()
            if not name:
                continue
            raw_vals = c.get("values") or []
            vals = [str(v) for v in raw_vals if str(v).strip()]
            prof = _profile_values(name, vals, max(len(raw_vals), 1)) if vals else {}
            # the COMPLETE shape suggest() bracket-accesses (enumerated, not
            # guessed: column/pk/fk/attributes/comment/table/notnull/type/
            # ref_table/ref_col) — a document column IS a column downstream
            entries.append({"column": name, "profile": prof, "comment": "",
                            "type": "", "pk": False, "fk": False,
                            "notnull": False, "attributes": {},
                            "table": f.get("base") or "", "ref_table": "",
                            "ref_col": ""})
        if entries:
            tables[tname] = entries
    return suggest(tables, schema=bucket) if tables else []


def discover_documents(cfg, max_objects=50000, top_n=8):
    """High-level discovery of a bucket's contents: file counts, total size,
       breakdown by file type and by folder, plus largest and newest objects.

       Optional cfg['include'] / cfg['exclude'] are comma/newline-separated glob
       patterns. An object is kept when it matches an include pattern (or none are
       given) and matches no exclude pattern. Patterns test the basename and the
       relative key, so '*.md' drops all Markdown and 'inspections/*' scopes a
       folder. Filtered objects are counted but excluded from every roll-up."""
    import heapq
    s3 = _s3_client(cfg)
    bucket = (cfg.get("bucket") or "").strip()
    prefix = (cfg.get("prefix") or "").lstrip("/")
    include = _doc_patterns(cfg.get("include"))
    exclude = _doc_patterns(cfg.get("exclude"))
    files = total = filtered = 0
    by_type, by_folder = {}, {}
    largest, newest = [], []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            size = obj.get("Size", 0) or 0
            lm = obj.get("LastModified")
            rel = key[len(prefix):].lstrip("/") if prefix else key
            base = key.rsplit("/", 1)[-1]
            # include/exclude glob filtering (before the object counts anywhere)
            if include and not _doc_match(rel, base, include):
                filtered += 1
                continue
            if exclude and _doc_match(rel, base, exclude):
                filtered += 1
                continue
            ext = base.rsplit(".", 1)[-1].lower() if "." in base else "(none)"
            top = rel.split("/")[0] if "/" in rel else "(root)"
            files += 1; total += size
            t = by_type.setdefault(ext, {"ext": ext, "count": 0, "bytes": 0})
            t["count"] += 1; t["bytes"] += size
            fo = by_folder.setdefault(top, {"name": top, "count": 0, "bytes": 0})
            fo["count"] += 1; fo["bytes"] += size
            heapq.heappush(largest, (size, key))
            if len(largest) > top_n:
                heapq.heappop(largest)
            if lm is not None:
                heapq.heappush(newest, (lm.timestamp(), key, lm.isoformat()))
                if len(newest) > top_n:
                    heapq.heappop(newest)
            if files >= max_objects:
                break
        if files >= max_objects:
            break
    summary = {"files": files, "bytes": total, "folders": len(by_folder),
               "types": len(by_type), "avg_bytes": round(total / files) if files else 0,
               "filtered": filtered}
    return {
        "bucket": bucket, "prefix": prefix, "summary": summary,
        "include": cfg.get("include") or "", "exclude": cfg.get("exclude") or "",
        "by_type": sorted(by_type.values(), key=lambda x: x["count"], reverse=True),
        "by_folder": sorted(by_folder.values(), key=lambda x: x["bytes"], reverse=True),
        "largest": [{"key": k, "bytes": s} for s, k in sorted(largest, reverse=True)],
        "newest": [{"key": k, "modified": iso} for _, k, iso in sorted(newest, reverse=True)],
    }

DOC_RULES = [
    (r"complian|legal|audit|regulat|consent|privacy", "HIGH", ["document", "compliance"], True),
    (r"customer|account|billing|invoice|payment|financ", "MEDIUM", ["document", "pii"], False),
    (r"qualit|lab|test|sampl|inspect", "MEDIUM", ["document"], False),
    (r"public|report|notice|brochure|template", "LOW", ["document"], False),
]

def _doc_classify(folder):
    """Classify a document folder into (sensitivity, tags, is_critical_data_element)."""
    fl = folder.lower()
    for pat, sens, tags, cde in DOC_RULES:
        if re.search(pat, fl):
            return sens, list(tags), cde
    return "LOW", ["document"], False

def suggest_documents(folders, bucket="documents"):
    """Turn harvested document folders into review rows under the document category.
       Carries an Owner_Hint when the store recorded an owner/steward."""
    rows = []
    for top, f in folders.items():
        name = humanize(top.replace("-", " ").replace("_", " ")) if top != "(root)" else "Bucket Root"
        sens, tags, cde = _doc_classify(top)
        exts = ", ".join(sorted(f["exts"])[:5]) if f["exts"] else "mixed"
        owner = f.get("owner", "")
        defn = (f"Document folder containing {f['count']} object(s) ({exts}) "
                f"in the {bucket} object store.")
        purp = (f"Holds {top.replace('-', ' ').replace('_', ' ')} documents for reference, "
                f"audit, and compliance." if top != "(root)"
                else "Holds supporting documents for reference and compliance.")
        conf = "High" if owner else ("Medium" if f["exts"] else "Low")
        reason = f"Owner tag/metadata: {owner}" if owner else "Derived from object-store folder"
        doc_tags = suggest_tags(tagdict.document_category(), sens, "", "Yes" if cde else "No", False, tags, name=name, term=name)
        rows.append({"Keep": "Y", "Category": tagdict.document_category(), "Term": name,
                     "Source_Column": f"{bucket}/{f['prefix']}".rstrip("/"),
                     "Definition": defn, "Purpose": purp, "Sensitivity": sens, "PII_Category": "",
                     "Critical_Data_Element": "Yes" if cde else "No", "Abbreviation": "",
                     "Suggested_Tags": ";".join(doc_tags), "Status": "Draft", "Confidence": conf,
                     "Suggested_Reason": reason, "LLM_Enriched": "No", "Owner_Hint": owner})
    return rows

def suggest_document_files(files, bucket="documents"):
    """Per-FILE review rows (leaf objects), so metadata lands on the individual files
       you see in PDC rather than only the folder. Each file inherits its folder's
       business term + sensitivity classification and carries its own document rating
       (keyed by the full object path in Source_Ratings, so it survives term dedup).

       Data Quality: when harvest_files was run with profile_dq (so a file carries
       'qdims' from reading its content), those dimensions are attached here as
       Source_Quality_Dims -- exactly like a SQL column -- so the file gets a computed
       qualityScore through the normal weighted pipeline. Files without 'qdims'
       (un-profilable formats like PDF/DOCX, or DQ left off) attach no dims and defer
       the Data Quality input to PDC's own file profiling; the app still sets the other
       three Trust-Score inputs (term, verified lineage, rating) + sensitivity."""
    rows, seen, out = [], {}, []
    for f in files:
        folder = f.get("folder") or "(root)"
        base = f.get("base") or (f.get("key", "").rsplit("/", 1)[-1])
        if not base:
            continue
        bkt = f.get("bucket") or bucket
        sens, tags, cde = _doc_classify(folder)
        term = (humanize(folder.replace("-", " ").replace("_", " "))
                if folder != "(root)" else "Bucket Root")
        src = f"{bkt}/{folder}/{base}" if folder != "(root)" else f"{bkt}/{base}"
        rating = rate_document(owner=f.get("owner"), ext=f.get("ext"),
                               sensitivity=sens, recent=f.get("recent"))
        doc_tags = suggest_tags(tagdict.document_category(), sens, "", "Yes" if cde else "No", False, tags, name=term, term=term)
        row = {"Keep": "Y", "Category": tagdict.document_category(), "Term": term,
               "Source_Column": src,
               "Definition": f"Object '{base}' in the {bkt}/{folder} object store.",
               "Purpose": f"Holds {term} data for reference, audit, and compliance.",
               "Sensitivity": sens, "PII_Category": "",
               "Critical_Data_Element": "Yes" if cde else "No", "Abbreviation": "",
               "Suggested_Tags": ";".join(doc_tags),
               "Suggested_Rating": rating, "Source_Ratings": {src: rating},
               "Status": "Draft", "Confidence": "High" if f.get("owner") else "Medium",
               "Suggested_Reason": (f"Owner tag/metadata: {f['owner']}" if f.get("owner")
                                    else "Leaf object in classified folder"),
               "LLM_Enriched": "No", "Owner_Hint": f.get("owner", "")}
        # If the object's content was profiled, carry the dimensions (keyed by the same
        # Source_Column path) so data_element_links computes a qualityScore for it.
        qd = f.get("qdims")
        if qd:
            row["Source_Quality_Dims"] = {src: qd}
            row["Suggested_Quality"] = quality_score_column(
                completeness=qd.get("c"), uniqueness=qd.get("u"), validity=qd.get("v"),
                expect_unique=qd.get("eu"), notnull=qd.get("nn"))
        rows.append(row)
    # dedup by (Category, Term): files sharing a folder term merge into one row,
    # each keeping its own Source_Column + per-file rating + per-file DQ dims
    for r in rows:
        key = (r["Category"], r["Term"])
        if key in seen:
            seen[key]["Source_Column"] += "; " + r["Source_Column"]
            seen[key].setdefault("Source_Ratings", {}).update(r.get("Source_Ratings", {}))
            seen[key]["Suggested_Rating"] = max(seen[key].get("Suggested_Rating", 0),
                                                r.get("Suggested_Rating", 0))
            if r.get("Source_Quality_Dims"):
                seen[key].setdefault("Source_Quality_Dims", {}).update(r["Source_Quality_Dims"])
            continue
        seen[key] = r
        out.append(r)
    return out

