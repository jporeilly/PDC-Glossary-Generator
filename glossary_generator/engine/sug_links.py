"""Enhance & links - glossary parsing, source parsing, deterministic ids,
mapping policy and data-element links.

Carved from suggester.py (1.38.18) - a pure move; suggester.py remains the
import surface (facade) so no call site changes."""
import os, re, json, uuid
from core import paths
from engine import tagdict
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS
from engine.sug_suggest import _abbrev, quality_score_column

# ----------------------------------------------------------------- ENHANCE
def _plain_lex(s):
    """Extract plain text from a Lexical JSON string (or pass through plain text)."""
    if not s:
        return ""
    try:
        o = json.loads(s)
        def walk(n):
            """Recursively return the first text node found in a Lexical-JSON tree."""
            if isinstance(n, dict):
                if n.get("type") == "text":
                    return n.get("text", "")
                for c in n.get("children", []) or []:
                    r = walk(c)
                    if r:
                        return r
            return ""
        return walk(o.get("root", {})) or str(s)
    except Exception:
        return str(s)

def parse_glossary(jsonl_text):
    """Index an exported glossary (JSONL) by term name for enhancement."""
    catname, terms, raw = {}, {}, []
    gname = None
    for line in (jsonl_text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        t = r.get("type")
        if t == "glossary":
            gname = r.get("name")
        elif t == "category":
            catname[r.get("_id")] = r.get("name")
        elif t == "term":
            raw.append(r)
    for r in raw:
        a = r.get("attributes", {}); info = a.get("info", {}); feat = a.get("features", {})
        terms[r["name"].strip().lower()] = {
            "Term": r["name"], "Category": catname.get(r.get("parentId"), "Uncategorized"),
            "definition": _plain_lex(info.get("definition")),
            "purpose": _plain_lex(info.get("purpose")),
            "sensitivity": feat.get("sensitivity"), "classification": info.get("classification"),
            "cde": feat.get("isCriticalDataElement"),
            "tags": [str(x.get("name")).strip().lower()
                     for x in a.get("tags", []) if x.get("name")]}
    return {"name": gname, "categories": list(catname.values()), "terms": terms}

def enhance_from_glossary(rows, jsonl_text, append_missing=True):
    """Overlay an existing glossary's real metadata onto matched scanned rows,
       and optionally append export terms the scan didn't produce."""
    g = parse_glossary(jsonl_text)
    idx = g["terms"]
    matched, present = 0, {r["Term"].strip().lower() for r in rows}
    for r in rows:
        e = idx.get(r["Term"].strip().lower())
        if not e:
            continue
        matched += 1
        if e["definition"]:  r["Definition"] = e["definition"]
        if e["purpose"]:     r["Purpose"] = e["purpose"]
        if e["sensitivity"]: r["Sensitivity"] = e["sensitivity"]
        if e["cde"] is not None:
            r["Critical_Data_Element"] = "Yes" if e["cde"] else "No"
        if e["tags"]:
            cur = r.get("Suggested_Tags", "").split(";") if r.get("Suggested_Tags") else []
            r["Suggested_Tags"] = ";".join(dict.fromkeys(cur + e["tags"]))
        r["Confidence"] = "High"
        r["Suggested_Reason"] = "Matched existing glossary term"
    added = []
    if append_missing:
        for key, e in idx.items():
            if key in present:
                continue
            sens = e["sensitivity"] or "LOW"
            added.append({"Keep": "Y", "Category": e["Category"], "Term": e["Term"],
                          "Source_Column": f"glossary:{g.get('name') or 'existing'}",
                          "Definition": e["definition"] or f"{e['Term']}.",
                          "Purpose": e["purpose"] or "",
                          "Sensitivity": sens, "PII_Category": "",
                          "Critical_Data_Element": "Yes" if e["cde"] else "No",
                          "Abbreviation": _abbrev(e["Term"]),
                          "Suggested_Tags": ";".join(e["tags"]), "Status": "Draft",
                          "Confidence": "High", "Suggested_Reason": "From existing glossary (not in scan)",
                          "LLM_Enriched": "No"})
    return rows + added, {"glossary": g.get("name"), "matched": matched,
                          "added": len(added), "export_terms": len(idx)}

def _kept_rows(rows):
    """Yield only the rows the reviewer marked to keep."""
    return [r for r in rows if str(r.get("Keep", "Y")).lower() in ("y", "yes", "true", "1")]

# _FILE_EXT anchored to end-of-string finds a FILE; this one finds the
# extension INSIDE a source so the trailing ".column" can be split off —
# "bucket.gis/segments.csv.material" is file "gis/segments.csv" + column
# "material", never column "csv.material" (the dotted-filename trap that
# already bit _row_table, field-caught again as Apply's "not found"s).
_FILE_EXT_ANY = re.compile(r"\.(csv|tsv|psv|json|jsonl|xml|txt|parquet|avro|"
                           r"ya?ml|pdf|docx?|xlsx?|pptx?)(?=\.|$)", re.I)


def _parse_source(src):
    """Resolve a Source_Column into a physical data element (schema/table/column or object)."""
    src = (src or "").strip()
    if not src or src.startswith("glossary:"):
        return None
    if "/" in src:
        head = src.split("/")[0]
        if "." not in head:
            # object path bucket/folder/file — the leaf file is the element
            parts = src.split("/")
            return {"schema_name": parts[0], "table_name": "/".join(parts[1:-1]),
                    "column_name": parts[-1], "entity_type": "OBJECT"}
        # document COLUMN: "bucket.rel/path/file.ext.column" — bucket ends at
        # the first dot, the file ends at its extension, the column (possibly
        # a dotted JSON leaf) is whatever follows
        bucket, rest = src.split(".", 1)
        m = _FILE_EXT_ANY.search(rest)
        if m:
            fname = rest[:m.end()]
            col = rest[m.end():].lstrip(".")
            if col:
                return {"schema_name": bucket, "table_name": fname,
                        "column_name": col, "entity_type": "COLUMN"}
            return {"schema_name": bucket,
                    "table_name": "/".join(fname.split("/")[:-1]),
                    "column_name": fname.split("/")[-1], "entity_type": "OBJECT"}
    # db-style dotted path — but a harvested DOCUMENT column arrives here too,
    # as "schema.file.ext.column" (harvest feeds files through the database
    # suggester), and a naive dot-split makes the table "file" and the column
    # "ext.column". Same canonical rule as the slash branch: one split at the
    # file extension (field: "csv.material" columns re-appeared via harvest)
    if "." in src:
        sch0, rest0 = src.split(".", 1)
        m0 = _FILE_EXT_ANY.search(rest0)
        if m0 and rest0[m0.end():].startswith("."):
            return {"schema_name": sch0, "table_name": rest0[:m0.end()],
                    "column_name": rest0[m0.end():].lstrip("."),
                    "entity_type": "COLUMN"}
    p = src.split(".")
    if len(p) >= 3:
        return {"schema_name": p[0], "table_name": p[1], "column_name": ".".join(p[2:]),
                "entity_type": "COLUMN"}
    if len(p) == 2:
        return {"schema_name": "", "table_name": p[0], "column_name": p[1], "entity_type": "COLUMN"}
    return None

def _gloss_ns(glossary_name):
    """The UUID5 namespace for one glossary — every id below derives from it, so the
       term/glossary ids are deterministic from names alone (no PDC round-trip)."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, "suggested-glossary:" + glossary_name)


def det_glossary_id(glossary_name):
    """The glossary's id (== every term's rootId == the businessTerm glossaryId)."""
    return str(uuid.uuid5(_gloss_ns(glossary_name), "glossary:" + glossary_name))


def det_term_id(glossary_name, category, term):
    """A term's id, matching its `_id` in the generated glossary JSONL (which PDC
       preserves on import). Category is part of the key, mirroring the JSONL build."""
    return str(uuid.uuid5(_gloss_ns(glossary_name), f"term:{category}/{term}"))


# --- Selective mapping policy -------------------------------------------------
# Not every suggested term should become a PDC data-element association. Linking
# every column pollutes governance, lineage and search, and does nothing for the
# Trust Score (whose glossary-term input is binary - presence, not volume). So a
# term is mapped to its column only when it clears a relevance bar: it is a Critical
# Data Element, it is PII, or it has real evidence behind it (a DDL comment, a key,
# or a profiling hit => High/Medium confidence). Low-confidence, name-templated
# columns are left unmapped. The steward can override per row with a "Map" cell
# (Y/N); the whole gate can be tuned or disabled via the policy.
CONF_RANK = {"low": 0, "medium": 1, "high": 2}

DEFAULT_MAP_POLICY = {
    "mode": "policy",            # "policy" = selective gate (default); "all" = legacy link-everything
    "min_confidence": "medium",  # map terms with at least this evidence; weaker (Low) are skipped
    "always_cde": True,          # always map Critical Data Elements, whatever their confidence
    "always_pii": True,          # always map PII columns, whatever their confidence
}

def should_map_link(row, policy=None):
    """Decide whether a reviewed term should be linked to its data element.
       Returns (map?, reason). A per-row "Map" cell (Y/N) always wins; otherwise the
       policy gates on CDE / PII / confidence. 'No match' is a valid, deliberate
       outcome - see DEFAULT_MAP_POLICY."""
    pol = {**DEFAULT_MAP_POLICY, **(policy or {})}
    ov = str(row.get("Map", "")).strip().lower()
    if ov in ("n", "no", "false", "0", "skip"):
        return False, "steward set Map=No"
    if ov in ("y", "yes", "true", "1", "map"):
        return True, "steward set Map=Yes"
    if pol.get("mode") == "all":
        return True, "policy: map all"
    cde = str(row.get("Critical_Data_Element", "No")).strip().lower() == "yes"
    pii = bool(str(row.get("PII_Category", "")).strip())
    if pol.get("always_cde") and cde:
        return True, "Critical Data Element"
    if pol.get("always_pii") and pii:
        return True, "PII column"
    conf = str(row.get("Confidence", "Low")).strip().lower()
    floor = str(pol.get("min_confidence", "medium")).strip().lower()
    if CONF_RANK.get(conf, 0) >= CONF_RANK.get(floor, 1):
        return True, f"{row.get('Confidence', 'Low')} confidence"
    return False, f"{row.get('Confidence', 'Low')} confidence, not CDE/PII"

def _row_real_sources(row):
    """The physical (non-glossary) source columns a row would actually link to."""
    return [s.strip() for s in str(row.get("Source_Column", "")).split(";")
            if _parse_source(s.strip())]

def map_breakdown(rows, policy=None):
    """Explain the gate: which kept terms get mapped to columns and which are held
       back (and why). Drives the steward-facing summary so selectivity is visible,
       not silent."""
    mapped, skipped = [], []
    for r in _kept_rows(rows):
        srcs = _row_real_sources(r)
        ok, why = should_map_link(r, policy)
        item = {"term": r.get("Term", ""), "category": r.get("Category", ""),
                "confidence": r.get("Confidence", ""),
                "cde": r.get("Critical_Data_Element", "No"),
                "pii": r.get("PII_Category", ""), "columns": len(srcs), "reason": why}
        if not srcs:
            item["reason"] = "conceptual / glossary-only term (no physical column)"
            skipped.append(item)
        elif ok:
            mapped.append(item)
        else:
            skipped.append(item)
    return {"mapped": mapped, "skipped": skipped,
            "mapped_count": len(mapped), "skipped_count": len(skipped)}

def data_element_links(rows, glossary_name="Business Glossary", quality_weights=None, with_quality=True, policy=None):
    """Map each kept term to the physical column(s) it came from — the Data Element
       associations (term <-> column) keyed by schema/table/column for bulk assignment.
       Each link carries the column's own scan-suggested rating and DQ qualityScore
       (the latter recomputed here so weights can be tuned without re-scanning).

       Selectivity: only rows the policy keeps are linked (see should_map_link), so
       low-value, non-CDE, non-PII columns are not auto-associated. Pass
       policy={"mode": "all"} to restore the legacy link-every-term behaviour."""
    links = []
    for r in _kept_rows(rows):
        keep, _why = should_map_link(r, policy)
        if not keep:
            continue
        ratings_map = r.get("Source_Ratings") or {}
        fallback = int(r.get("Suggested_Rating", 0) or 0)
        qdims_map = r.get("Source_Quality_Dims") or {}
        keys_map = r.get("Source_Keys") or {}
        for sc in str(r.get("Source_Column", "")).split(";"):
            sc_key = sc.strip()
            de = _parse_source(sc_key)
            if not de:
                continue
            # each physical column carries its own scan-suggested rating; fall back
            # to the term's representative rating if the per-column value is missing
            rating = int(ratings_map.get(sc_key, fallback) or fallback or 0)
            # DQ score from this column's own dimensions, under the chosen weights
            quality = None
            qd = qdims_map.get(sc_key)
            if with_quality and qd:
                quality = quality_score_column(completeness=qd.get("c"), uniqueness=qd.get("u"),
                                               validity=qd.get("v"), expect_unique=qd.get("eu"),
                                               notnull=qd.get("nn"), weights=quality_weights)
            links.append({**de, "business_term": r["Term"], "glossary": glossary_name,
                          "category": r.get("Category", ""), "sensitivity": r.get("Sensitivity", ""),
                          "critical_data_element": r.get("Critical_Data_Element", "No"),
                          "rating": rating, "quality": quality,
                          "definition": (r.get("Definition") or "").strip(),
                          "keys": keys_map.get(sc_key)})
    return links

DE_COLS = ["schema_name", "table_name", "column_name", "entity_type", "business_term",
           "glossary", "category", "sensitivity", "critical_data_element"]

def links_to_csv(links):
    """Render Data-Element links as bulk-assignment CSV."""
    import csv, io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=DE_COLS, extrasaction="ignore")
    w.writeheader()
    for l in links:
        w.writerow(l)
    return buf.getvalue()

def links_to_api_json(links, glossary_name="Business Glossary", lineage_verified=True, rating=0,
                      rater=None):
    """Trust-Score-ready association objects, one per column, shaped for PDC's
       data-collections API: businessTerms + features(isLineageVerified, rating,
       sensitivity, isCriticalDataElement). A linked term + verified lineage + a
       rating + a quality metric are the inputs PDC's Trust Score draws on.

       Each column carries its own scan-suggested rating (link['rating']); when
       multiple terms map to one column the highest suggestion wins. Pass a
       non-zero `rating` to override every column with one fixed value instead.

       `rater` is the steward the rating is attributed to. PDC computes the
       displayed stars from the rating's `users` map — a rating without one
       shows 0 stars — and Apply's table roll-up harvests its raters FROM the
       column ratings, so a rater-less column rating also silently disables
       every table rating downstream (field-caught 2026-08-23: 155 columns
       rated, 0 tables, 0 stars everywhere)."""
    by_col = {}
    for l in links:
        key = (l["schema_name"], l["table_name"], l["column_name"], l["entity_type"])
        rec = by_col.setdefault(key, {
            "type": l["entity_type"], "schemaName": l["schema_name"],
            "tableName": l["table_name"], "columnName": l["column_name"],
            "attributes": {"businessTerms": [],
                           "features": {"sensitivity": l.get("sensitivity", ""),
                                        "isCriticalDataElement": str(l.get("critical_data_element", "No")).lower() == "yes",
                                        "isLineageVerified": bool(lineage_verified)}}})
        # rating: explicit global override, else the highest scan suggestion for the column
        col_rating = int(rating) if rating else int(l.get("rating") or 0)
        if col_rating:
            cur = (rec["attributes"]["features"].get("rating") or {}).get("value", 0)
            if col_rating >= cur:
                rp = {"value": col_rating}
                if rater:
                    rp["users"] = {rater: col_rating}
                rec["attributes"]["features"]["rating"] = rp
        # qualityScore: the Data Quality input (0-100). Highest scan suggestion wins
        # when several terms map to one column. PDC records an externally-set value
        # as a MANUAL quality metric (which is what we want now PDQ is retired).
        q = l.get("quality")
        if q is not None:
            curq = rec["attributes"]["features"].get("qualityScore")
            if curq is None or int(q) >= int(curq):
                rec["attributes"]["features"]["qualityScore"] = int(q)
        # Stamp the term's id and the glossaryId deterministically — they are the
        # SAME UUID5s written into the glossary JSONL (which PDC preserves on import),
        # so the link is born fully glossary-bound (id + glossaryId) with no PDC
        # round-trip. Resolve then only has to confirm, and Apply writes a real link
        # instead of attaching by name (which leaves the Glossary column as "—").
        # entity description: the steward's reviewed definition (PATCHable via
        # attributes.info.description; Apply decides fill-vs-overwrite)
        if l.get("definition") and "info" not in rec["attributes"]:
            rec["attributes"]["info"] = {"description": l["definition"]}
        # PK/FK facts -> attributes.extended. The built-in Is Primary/Foreign Key
        # property (metadata.column.*) is harvest-owned and rejected by the public
        # PATCH schema; extended is the API's writable free-form block, so the
        # scan's own key detection is recorded there.
        kk = l.get("keys")
        if isinstance(kk, dict) and (kk.get("pk") or kk.get("fk")):
            ext = rec["attributes"].setdefault("extended", {})
            ext["isPrimaryKey"] = bool(kk.get("pk"))
            ext["isForeignKey"] = bool(kk.get("fk"))
            if kk.get("ref"):
                ext["references"] = kk["ref"]
        gname = l.get("glossary", glossary_name) or glossary_name
        rec["attributes"]["businessTerms"].append(
            {"name": l["business_term"], "glossary": gname,
             "id": det_term_id(gname, l.get("category", ""), l["business_term"]),
             "glossaryId": det_glossary_id(gname)})
    return list(by_col.values())

def table_term_directory(rows, glossary_name="Business Glossary"):
    """{table_name(lower): term info} for the table-level record terms, so Apply
       can bind each table's OWN businessTerm — plus its description and
       sensitivity — onto the TABLE entity. That is the Trust Score's
       "glossary term assigned" input at table level, automated (it was a
       documented manual steward step before 1.8.6). Ids are the same
       deterministic UUID5s the glossary JSONL carries, so the link is born
       glossary-bound once the glossary is imported."""
    out = {}
    for r in _kept_rows(rows):
        t = (r.get("Source_Table") or "").strip()
        term = (r.get("Term") or "").strip()
        if not t or not term:
            continue
        out[t.lower()] = {
            "name": term,
            "id": det_term_id(glossary_name, r.get("Category", ""), term),
            "glossaryId": det_glossary_id(glossary_name),
            "description": (r.get("Definition") or "").strip(),
            "sensitivity": (r.get("Sensitivity") or "").strip().upper(),
        }
    return out

def glossary_to_rows(jsonl_text):
    """Load an exported glossary directly as editable review rows (round-trip / review)."""
    g = parse_glossary(jsonl_text)
    rows = []
    for e in g["terms"].values():
        sens = e["sensitivity"] or "LOW"
        rows.append({"Keep": "Y", "Category": e["Category"], "Term": e["Term"],
                     "Source_Column": f"glossary:{g.get('name') or 'imported'}",
                     "Definition": e["definition"] or f"{e['Term']}.",
                     "Purpose": e["purpose"] or "", "Sensitivity": sens, "PII_Category": "",
                     "Critical_Data_Element": "Yes" if e["cde"] else "No",
                     "Abbreviation": _abbrev(e["Term"]), "Suggested_Tags": ";".join(e["tags"]),
                     "Status": "Draft", "Confidence": "High",
                     "Suggested_Reason": "Loaded from glossary export", "LLM_Enriched": "No"})
    return rows, {"glossary": g.get("name"), "terms": len(rows),
                  "categories": len({r["Category"] for r in rows})}

