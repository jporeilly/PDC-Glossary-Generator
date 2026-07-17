"""pdc_api.entities — carved from the original pdc_api.py (see package __init__ for the API contract notes). Import surface is the package: `import pdc_api`."""
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
