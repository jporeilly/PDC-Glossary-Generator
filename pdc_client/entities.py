"""pdc_api.entities — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
import itertools
import json
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
from .core import _cursor, _eid, _req, _results, clean_base

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
# FOLDER, not just DIRECTORY: an object store's folders come back from PDC typed
# FOLDER (a live scan reports "16 FILE + 5 FOLDER entities"), and the rest of this
# package already knows it — bulkload uses ("FOLDER", "FILE") and _is_container
# tests ("DIRECTORY", "FOLDER"). Only these two lists missed it, which filtered
# every object-store folder out server-side: resolve_table_entity found nothing,
# so Data Discovery silently fell back to scoping individual FILES. Folder scope
# cascades to every file inside it; file scope does not — so one representative
# file per folder got profiled and its siblings never did, with the job still
# reporting SUCCESS.
_TBL_TYPES = ["TABLE", "RESOURCE", "OBJECT", "FILE", "DATASET", "DIRECTORY", "FOLDER"]


_FILE_TYPES = ["FILE", "OBJECT", "RESOURCE", "DIRECTORY", "FOLDER"]


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
    # size + modified ride the entity too — without them every harvested file
    # showed 0 B and "most recent" was ordered by nothing (field-caught)
    def _num(*vals):
        for v in vals:
            try:
                if v not in (None, ""):
                    return int(float(v))
            except (TypeError, ValueError):
                continue
        return None          # unknown - the UI shows a dash, never "0 B"
    # The raw FILE entity (finally dumped from a live estate) settled it:
    # size lives at metadata.stats.bytes — a sibling of metadata.file, which
    # is why two rounds of aliasing metadata.file.* never found it. The
    # guesses stay as fallbacks for other PDC versions.
    ms = md.get("stats") if isinstance(md.get("stats"), dict) else {}
    size = _num(ms.get("bytes"), ms.get("size"),
                _aget(a, "usedCapacity", "used_capacity", "capacity"),
                mf.get("usedCapacity"), mf.get("size"), mf.get("sizeInBytes"),
                mf.get("contentLength"), mf.get("fileSize"),
                _aget(a, "size", "sizeInBytes", "contentLength"),
                info.get("usedCapacity"), info.get("size"),
                ent.get("usedCapacity"))
    modified = str(mf.get("lastModified") or mf.get("modifiedAt")
                   or _aget(a, "lastModified", "modifiedAt", "lastModifiedDate",
                            "youngestChildDate")
                   or info.get("lastModified") or info.get("modifiedAt")
                   or ent.get("youngestChildDate")
                   or ent.get("updatedAt") or ent.get("modifiedAt") or "")
    doc = md.get("document") if isinstance(md.get("document"), dict) else {}
    doc_ext = doc.get("extended") if isinstance(doc.get("extended"), dict) else {}
    return {"folder": folder, "base": base, "bucket": bucket, "ext": ext,
            "bytes": size, "modified": modified,
            "title": str(doc.get("title") or ""),
            "author": str(doc.get("author") or ""),
            "doc_category": str(doc_ext.get("cp:category") or ""),
            "owner": owner, "recent": False}, bucket


def _shape_regex(pattern, sample):
    """PDC's patternAnalysis shape alphabet zipped with its own sample value
    -> an anchored regex. A=upper, a=lower, d=digit; anything else is taken
    LITERALLY FROM THE SAMPLE (separators, spaces), so "AAAsAAsdddddd" +
    "AWC-CG-001001" -> ^[A-Z]{3}-[A-Z]{2}-[0-9]{6}$."""
    if not pattern or not sample or len(pattern) != len(sample):
        return ""
    classes = {"A": "[A-Z]", "a": "[a-z]", "d": "[0-9]"}
    parts = []
    idx = 0
    for ch, grp in itertools.groupby(pattern):
        n = len(list(grp))
        cls = classes.get(ch)
        if cls is None:
            lit = re.escape(sample[idx:idx + n])
            parts.append(lit)
        else:
            parts.append(cls + ("{%d}" % n if n > 1 else ""))
        idx += n
    return "^" + "".join(parts) + "$"


def _profile_from_pdc(pinfo):
    """Map PDC's profilingInfo onto the `profile` dict the suggester consumes.

    Shapes read off a LIVE PDC 11 payload (2026-08-14) - the vendor docs and
    two earlier guesses were wrong, so every key here was seen in the wild:
      stats.density / stats.uniqueness   percentages (100 = complete/unique)
      stats.rowCount / nonNullCount      counts
      stats.min / stats.max              string LENGTHS for text columns -
                                         only real values when bindType is
                                         numeric, hence the guard
      profilingInfo.bitsetCardinality    the TRUE distinct count
      patternAnalysis.patterns           [{pattern, sample, counter, ...}] -
                                         shape signatures with one REAL sample
                                         each; the samples double as the value
                                         list for low-cardinality columns and
                                         as recognised-kind evidence
      dataSampling                       EMPTY on this build - never map it
    Older key spellings are kept as fallbacks for other PDC versions."""
    if not isinstance(pinfo, dict) or not pinfo:
        return {}
    stats = pinfo.get("stats") or pinfo.get("statistics") or {}
    out = {}

    def num(bag, *names):
        for n in names:
            v = bag.get(n) if isinstance(bag, dict) else None
            if isinstance(v, (int, float)):
                return float(v)
        return None

    total = (num(stats, "rowCount", "totalCount", "count", "sampleSize")
             or num(stats, "nonNullCount"))
    density = num(stats, "density")
    if density is not None:
        out["completeness"] = round(max(0.0, min(1.0, density / 100.0)), 3)
    else:
        nulls = num(stats, "nullCount", "nulls", "missingCount", "blankCount")
        if total and nulls is not None:
            out["completeness"] = round(max(0.0, min(1.0, (total - nulls) / total)), 3)
    uniq_pct = num(stats, "uniqueness")
    distinct = (num(pinfo, "bitsetCardinality")
                or num(stats, "distinctCount", "uniqueCount", "cardinality"))
    if uniq_pct is not None:
        out["uniq"] = round(max(0.0, min(1.0, uniq_pct / 100.0)), 3)
    elif total and distinct is not None:
        out["uniq"] = round(min(1.0, distinct / total), 3)
    if total:
        out["rows"] = int(total)
    if distinct is not None:
        out["distinct"] = int(distinct)

    # numeric range: ONLY when the binding says numeric - for text columns
    # stats.min/max are string lengths (field-caught: a status column read
    # "min 7 max 13", the lengths of its two values)
    bind = str(pinfo.get("bindType") or stats.get("bindType") or "").upper()
    if bind and bind not in ("STRING", "TEXT", "CHAR", "VARCHAR", "BOOLEAN", "DATE",
                             "TIMESTAMP", "DATETIME"):
        lo, hi = num(stats, "min", "minValue"), num(stats, "max", "maxValue")
        if lo is not None and hi is not None:
            out["min"], out["max"] = lo, hi
        avg = num(stats, "average", "avgValue")
        if avg is not None:
            out["avg"] = avg

    # patternAnalysis: shape+sample pairs. Samples are REAL values - the value
    # list for a low-cardinality column, recognised-kind evidence for the rest
    lex = []
    for k in ("lexicalMin", "lexicalMax"):
        v = stats.get(k)
        if isinstance(v, str) and v.strip():
            lex.append(v.strip())
    pa = pinfo.get("patternAnalysis") or {}
    pats = ((pa.get("patterns") if isinstance(pa, dict) else None)
            or pinfo.get("patterns"))
    samples, shapes = [], []
    if isinstance(pats, list):
        for it in pats[:24]:
            if not isinstance(it, dict):
                continue
            s = str(it.get("sample") or "").strip()
            if s and s not in samples:
                samples.append(s)
            rx = _shape_regex(str(it.get("pattern") or ""), str(it.get("sample") or ""))
            if rx:
                shapes.append((rx, float(it.get("counter") or 0)))
    # lexicalMin/Max are true values on string columns and often recover the
    # value a one-sample-per-shape listing missed (pump_status: Running and
    # Stopped share one shape, so patterns carried only one of them)
    for v in lex:
        if v not in samples:
            samples.append(v)
    if samples:
        out["samples"] = samples

    # recognised kinds from the samples, DATE FIRST: 2026-05-14 is digits-
    # and-dashes, so the phone shape would swallow every date (field-caught:
    # alert_date minted as kind phone). Canonical class shapes only - the
    # samples vote, nothing is stored.
    if samples:
        import re as _re
        _KIND_RX = [
            ("date", _re.compile(r"^\d{4}-\d{2}-\d{2}([T ].*)?$|^\d{1,2}/\d{1,2}/\d{2,4}$")),
            ("email", _re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")),
            ("ssn", _re.compile(r"^[0-9]{3}-[0-9]{2}-[0-9]{4}$")),
            ("zip", _re.compile(r"^[0-9]{5}(-[0-9]{4})?$")),
            ("phone", _re.compile(r"^\+?[0-9][0-9()\-. ]{6,}[0-9]$")),
        ]
        for kind_name, rx in _KIND_RX:
            hits = sum(1 for s in samples if rx.match(s))
            # dates: a nullable column often yields ONE sample (one shape) -
            # if every sample is a date, it is a date. Other kinds keep the
            # two-vote floor against single-sample coincidences.
            floor = 1 if kind_name == "date" else 2
            if hits == len(samples) and hits >= floor:
                out["kind"] = kind_name
                break
            if hits >= max(2, int(0.8 * len(samples))):
                out["kind"] = kind_name
                break

    high_card = bool(stats.get("isHighCardinality"))
    if (len(samples) >= 2 and not high_card
            and out.get("kind") not in ("date",)
            and distinct is not None and 2 <= distinct <= 12
            and (out.get("uniq") is None or out["uniq"] < 0.95)):
        # the samples may be PARTIAL (one per shape group) - still a usable
        # candidate list; the suggester's gates decide what it becomes.
        # len >= 2: a single sample is NOT a value list, and claiming it
        # blocked the zips' perfectly good ddddd pattern (field-caught)
        out["enum"] = sorted(samples)[:12]

    # a shape only counts as a DETECTION pattern when it discriminates
    # (digits or literal separators) AND reads as a FORMAT: a few shapes
    # describing many values (account_number: 2 shapes / 10 values). Many
    # shapes is prose wearing digits - addresses and descriptions minted
    # over-matching unions before this gate (field-caught). Dates never
    # mint: every date matches every date's shape.
    def _weak_digit_run(r):
        # a bare short digit run ("^[0-9]{4}$") matches every year and count
        # in the estate - a format needs more to discriminate
        m = re.fullmatch(r"\^\[0-9\]\{(\d+)\}\$", r)
        return bool(m and int(m.group(1)) <= 5)
    discriminating = [(r, c) for r, c in shapes
                      if ("[0-9]" in r or re.search(r"\[^ ]", r))
                      and not _weak_digit_run(r)]
    if (discriminating and total and "enum" not in out
            and out.get("kind") not in ("date",)
            and len(discriminating) <= 3):
        covered = sum(c for _, c in discriminating)
        shapes = discriminating
        if covered / total >= 0.9:
            rx = "|".join(r for r, _ in shapes[:6])
            out["pattern"] = rx if len(shapes) == 1 else "^(?:%s)$" % "|".join(
                r.strip("^$") for r, _ in shapes[:6])
            out["valid"] = round(min(1.0, covered / total), 3)
            out.setdefault("kind", "code")

    # legacy fallbacks for other PDC versions: a ready-made regex in the
    # patterns list (the shape the 10.2 docs describe), prose refused
    if "pattern" not in out and isinstance(pats, list) and pats:
        first = pats[0]
        rx = first if not isinstance(first, dict) else (
            first.get("regex") or first.get("expression") or first.get("value"))
        rx = "" if rx is None else str(rx).strip()
        if rx and any(ch in rx for ch in "^$[]\\+*?{}") and len(rx) <= 400:
            out["pattern"] = rx
            out.setdefault("kind", "code")

    # legacy fallbacks for other PDC versions (sampling.sample as a list)
    if "enum" not in out:
        sampling = pinfo.get("sampling") or pinfo.get("samples") or {}
        raw = sampling.get("sample") if isinstance(sampling, dict) else sampling
        if isinstance(raw, list) and raw:
            vals = []
            for item in raw[:24]:
                s = item.get("value") if isinstance(item, dict) else item
                s = "" if s is None else str(s).strip()
                if s and s not in vals:
                    vals.append(s)
            if 2 <= len(vals) <= 12 and (out.get("uniq") is None or out["uniq"] < 0.95):
                out["enum"] = sorted(vals)[:12]

    if out:
        out.setdefault("reason", "Profiled by PDC")
    return out


def harvest_from_catalog(base_url, token, ds_id=None, ds_name=None, version="v2",
                         verify_tls=True, timeout=40, max_pages=12, with_profile=True):
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
    ent_index, parent_ids = {}, set()      # entity id -> (table, column)
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
        # remember WHERE this column lives in the catalog: profiling is
        # fetched by entity/parent id, because resolving a parent by NAME
        # silently misses document "tables" (a filename), which is how
        # harvested file columns arrived with no value evidence
        _eid_ = _eid(e) or e.get("_id") or ""
        _par_ = (e.get("parentId") or e.get("parentID")
                 or (e.get("parentIds") or [None])[0])
        if _eid_:
            ent_index[str(_eid_)] = (tbl, col)
        if _par_:
            parent_ids.add(str(_par_))
        # a live dump showed COLUMN entities carry metadata.stats themselves
        # (rows, nulls, cardinality, density/uniqueness percentages, and
        # min/max/avg/stdev - the numeric-range evidence): a baseline profile
        # for free, before profiling-info is even asked
        _md = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        _st = _md.get("stats") if isinstance(_md.get("stats"), dict) else {}
        base_prof = {}
        if _st:
            rows_n = _st.get("rows")
            if isinstance(_st.get("density"), (int, float)):
                base_prof["completeness"] = round(float(_st["density"]) / 100.0, 3)
            elif isinstance(rows_n, (int, float)) and rows_n and isinstance(_st.get("nulls"), (int, float)):
                base_prof["completeness"] = round((rows_n - _st["nulls"]) / rows_n, 3)
            if isinstance(_st.get("uniqueness"), (int, float)):
                base_prof["uniq"] = round(float(_st["uniqueness"]) / 100.0, 3)
            elif isinstance(rows_n, (int, float)) and rows_n and isinstance(_st.get("cardinality"), (int, float)):
                base_prof["uniq"] = round(min(1.0, _st["cardinality"] / rows_n), 3)
            if isinstance(rows_n, (int, float)):
                base_prof["rows"] = int(rows_n)
            for src_k, dst_k in (("minValue", "min"), ("maxValue", "max"),
                                 ("avgValue", "avg"), ("stdevValue", "stdev")):
                if isinstance(_st.get(src_k), (int, float)):
                    base_prof[dst_k] = _st[src_k]
            if base_prof:
                base_prof["reason"] = "Profiled by PDC"
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
            **({"profile": base_prof} if base_prof else {}),
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

    # --- PDC's own profiling -> the profile dict ---------------------------
    # The catalog already profiled these columns; asking for it here is what
    # lets a harvested grid carry value evidence (dictionaries, patterns, DQ
    # baselines) instead of structure alone. Fetch BY ID: a live probe showed
    # the by-name route finds nothing for a document store, because its
    # "table" is a filename — id/parentId answers for both source kinds.
    profiled = 0
    if with_profile and tables:
        from .jobs import filter_profiling_info, pdc_profile_for_columns  # local: avoids a cycle
        by_table_col = {}
        try:
            ids = list(ent_index.keys())
            items = []
            for i in range(0, len(ids), 200):
                try:
                    items += filter_profiling_info(base_url, token, {"ids": ids[i:i + 200]},
                                                   version, verify_tls, timeout) or []
                except Exception:
                    pass
            if not items and parent_ids:
                pids = sorted(parent_ids)
                for i in range(0, len(pids), 50):
                    try:
                        items += filter_profiling_info(base_url, token,
                                                       {"parentIds": pids[i:i + 50],
                                                        "types": list(dict.fromkeys(_COL_TYPES))},
                                                       version, verify_tls, timeout) or []
                    except Exception:
                        pass
            for it in items:
                pinfo = it.get("profilingInfo") or it.get("profiling") or {}
                if not pinfo:
                    continue
                where = ent_index.get(str(_eid(it) or it.get("_id") or ""))
                if not where:
                    nm = str(it.get("name") or "").strip().lower()
                    where = next((v for v in ent_index.values()
                                  if v[1].strip().lower() == nm), None)
                if where:
                    by_table_col[where] = pinfo
        except Exception:
            by_table_col = {}

        if not by_table_col:                 # last resort: the by-name route
            try:
                specs = [{"schemaName": c.get("schema") or "", "tableName": t_,
                          "columnName": c.get("column") or ""}
                         for t_, cols in tables.items() for c in cols]
                prof = pdc_profile_for_columns(base_url, token, specs, version=version,
                                               verify_tls=verify_tls, timeout=timeout)
                for t_, cols in tables.items():
                    for c in cols:
                        key = ".".join(x for x in (c.get("schema") or "", t_,
                                                   c.get("column") or "") if x)
                        if prof.get(key):
                            by_table_col[(t_, c.get("column") or "")] = prof[key]
            except Exception:
                pass

        for t_, cols in tables.items():
            for c in cols:
                p = _profile_from_pdc(by_table_col.get((t_, c.get("column") or "")) or {})
                if p or c.get("profile"):
                    # entity baseline first, profiling-info wins on overlap
                    c["profile"] = {**(c.get("profile") or {}), **p}
                    profiled += 1

    summary = {"tables": len(tables), "columns": sum(len(v) for v in tables.values()),
               "files": len(files), "bucket": bucket,
               "already_governed": governed,
               "governance": gov,
               "profiled_columns": profiled,
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


def glossary_categories(base_url, token, glossary_name, version="v2",
                        verify_tls=True, timeout=30, max_pages=12):
    """Names of the category folders PDC currently holds under ONE business
    glossary. There is no public list-glossary endpoint (see resolve_terms'
    contract note), so: resolve the glossary root via search, then try
    server-side type filters a glossary tree may use, falling back to an
    unfiltered page-walk scoped by _under_root. `partial` goes True when the
    page cap may have truncated the walk - the caller must say so rather than
    report a clean tree it only half-saw.
    Returns {"exists", "id", "name", "categories": [names], "partial"}."""
    g = glossary_exists(base_url, token, glossary_name, version=version,
                        verify_tls=verify_tls, timeout=timeout)
    if not g.get("id"):
        return {"exists": False, "id": None, "name": None,
                "categories": [], "partial": False}
    gid, gname = g["id"], g.get("name")

    def _cat_like(e):
        t = str(e.get("type") or e.get("originalType") or "").lower()
        return "categ" in t and "term" not in t

    def _collect(filters):
        try:
            ents = filter_entities(base_url, token, filters, version=version,
                                   verify_tls=verify_tls, timeout=timeout,
                                   max_pages=max_pages)
        except Exception:
            return [], False
        names = sorted({str(e.get("name") or "").strip() for e in ents
                        if e.get("name") and _cat_like(e)
                        and _under_root(e, gid, gname)})
        return names, len(ents) >= 500 * max_pages

    # cheap paths first: a matching server-side type filter returns only the
    # tree; an unknown type value may be ignored by PDC and return everything,
    # which _cat_like + _under_root still reduce correctly
    for tname in ("CATEGORY", "GLOSSARY_CATEGORY", "BUSINESS_GLOSSARY_CATEGORY"):
        names, capped = _collect({"types": [tname]})
        if names:
            return {"exists": True, "id": gid, "name": gname,
                    "categories": names, "partial": capped}
    names, capped = _collect({})
    return {"exists": True, "id": gid, "name": gname,
            "categories": names, "partial": capped}


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
