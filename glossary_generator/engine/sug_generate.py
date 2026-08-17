"""Generate - import-ready JSONL records and the build/scan checks.

Carved from suggester.py (1.38.18) - a pure move; suggester.py remains the
import surface (facade) so no call site changes."""
import os, re, json, uuid
from core import paths
from engine import tagdict
from engine.sug_shared import DOMAIN, GEN_TS, SENS_RANK, RANK_SENS
from engine.sug_links import det_glossary_id, det_term_id

# ----------------------------------------------------------------- GENERATE
def _lex(text):
    """Wrap plain text as a minimal Lexical-JSON string (PDC's rich-text format)."""
    if not text:
        return None
    obj = {"root": {"children": [{"children": [{"detail": 0, "format": 0, "mode": "normal",
            "style": "", "text": str(text), "type": "text", "version": 1}],
            "direction": "ltr", "format": "", "indent": 0, "type": "paragraph", "version": 1}],
            "direction": "ltr", "format": "", "indent": 0, "type": "root", "version": 1}}
    return json.dumps(obj, ensure_ascii=False)

REVIEW_TIME = "T00:00:00.000Z"   # PDC stores reviewedAt at midnight UTC

def _classification(sens):
    """Map a sensitivity level to PDC's classification label (HIGH->Company Confidential, MEDIUM->Private, else Public)."""
    return ("Company Confidential" if sens == "HIGH"
            else "Private" if sens == "MEDIUM" else "Public")

def _kept(r):
    """True when a row is marked kept (Keep in y/yes/true/1)."""
    return str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")

def _people_block(people, rating, review_iso, created_override=""):
    """Build the reusable injection pieces for one people-scope (glossary-wide or
       per-category). `people` = {owner, custodian, businessSteward, stakeholders}.
       Safe/empty when nothing is set (output then matches the no-governance case)."""
    people = people or {}
    owner = (people.get("owner") or "").strip()
    custodian = (people.get("custodian") or "").strip()
    steward = (people.get("businessSteward") or "").strip()

    info_people = {}
    if owner:     info_people["owner"] = owner
    if custodian: info_people["custodian"] = custodian
    if steward:   info_people["businessSteward"] = steward

    features_extra = {}
    rater = steward or owner or custodian
    if rating and rater:
        features_extra["rating"] = {"value": rating, "users": {rater: rating}}

    attr_extra = {}
    clean_sh = []
    for s in (people.get("stakeholders") or []):
        sid = (s.get("id") or "").strip()
        if not sid:
            continue
        clean_sh.append({"roles": s.get("roles") or ["Steward"],
                         "name": s.get("name") or "", "id": sid, "email": s.get("email") or ""})
    if clean_sh:
        attr_extra["stakeholders"] = clean_sh
    if review_iso:
        attr_extra["reviewedAt"] = review_iso

    created_by = (created_override or steward or owner or "suggester")
    updated_by = (steward or owner or "suggester")
    return info_people, features_extra, attr_extra, created_by, updated_by


def _merge_people(base, over):
    """Per-category override: replace owner/custodian/businessSteward/stakeholders
       individually when the override supplies them, else inherit from base."""
    out = dict(base or {})
    over = over or {}
    for k in ("owner", "custodian", "businessSteward"):
        if (over.get(k) or "").strip():
            out[k] = over[k]
    if over.get("stakeholders"):
        out["stakeholders"] = over["stakeholders"]
    return out


def _cat_effective(over, g_status, g_rating, g_review_iso):
    """Resolve a category's effective status / rating / reviewed-date. Each field
       falls back to the glossary-wide value unless the category overrides it.
       An empty string means 'use default'; rating '0' is a real override (None)."""
    over = over or {}
    status = (str(over.get("status") or "")).strip() or g_status
    rraw = over.get("rating", "")
    if str(rraw).strip() != "":
        try:
            rating = int(rraw)
        except (TypeError, ValueError):
            rating = g_rating
    else:
        rating = g_rating
    rv = (over.get("reviewedAt") or "").strip()
    review_iso = ((rv if "T" in rv else rv + REVIEW_TIME) if rv else g_review_iso)
    return status, rating, review_iso


def to_jsonl_records(rows, glossary_name="Business Glossary (Suggested)", governance=None):
    """Build PDC glossary import records (glossary/category/term objects) from review rows."""
    gov = governance or {}
    status = (gov.get("status") or "Draft").strip() or "Draft"
    domain = (gov.get("domain") or DOMAIN).strip() or DOMAIN  # glossary-wide PDC classifier
    apply_cat = gov.get("applyToCategories", True)
    created_override = (gov.get("createdBy") or "").strip()
    try:
        rating = int(gov.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    rv = (gov.get("reviewedAt") or "").strip()
    review_iso = (rv if "T" in rv else (rv + REVIEW_TIME)) if rv else ""

    # default people scope: explicit "default", else legacy top-level fields
    default_people = gov.get("default") or {
        "owner": gov.get("owner", ""), "custodian": gov.get("custodian", ""),
        "businessSteward": gov.get("businessSteward", ""), "stakeholders": gov.get("stakeholders", [])}
    cat_overrides = gov.get("categories") or {}

    ns = uuid.uuid5(uuid.NAMESPACE_DNS, "suggested-glossary:" + glossary_name)
    root = det_glossary_id(glossary_name)

    g_info, g_feat, g_attr, g_cby, g_uby = _people_block(default_people, rating, review_iso, created_override)
    gloss_info = {"status": status}
    gloss_info.update(g_info)
    recs = [{"createdAt": GEN_TS, "fqdn": glossary_name, "rootId": root, "createdBy": g_cby,
             "name": glossary_name, "attributes": {"isSoftCreated": False, "info": gloss_info},
             "type": "glossary", "updatedAt": GEN_TS, "resourceId": "null", "_id": root, "sort": None}]

    cats, cat_id, cat_rows = [], {}, {}
    for r in rows:
        if not _kept(r):
            continue
        cat_rows.setdefault(r["Category"], []).append(r)
        if r["Category"] not in cats:
            cats.append(r["Category"])

    # resolve each category's effective people-block + status once; terms inherit theirs
    cat_block = {}
    cat_status = {}
    for cat in cats:
        ov = cat_overrides.get(cat)
        c_status, c_rating, c_review = _cat_effective(ov, status, rating, review_iso)
        cat_status[cat] = c_status
        cat_people = _merge_people(default_people, ov)
        cat_block[cat] = _people_block(cat_people, c_rating, c_review, created_override)

    for cat in cats:
        cid = str(uuid.uuid5(ns, "category:" + cat)); cat_id[cat] = cid
        infoP, featX, attrX, cby, uby = cat_block[cat]
        csens = RANK_SENS[max((SENS_RANK.get(x["Sensitivity"], 0) for x in cat_rows[cat]), default=0)]
        cinfo = {"domain": domain,
                 "definition": _lex(f"{cat} terms in the {glossary_name} business glossary."),
                 "classification": _classification(csens), "status": cat_status[cat],
                 "purpose": _lex(f"Groups {cat.lower()} business terms for governance and discovery.")}
        cattrs = {"features": {"sensitivity": csens}, "isSoftCreated": False, "info": cinfo}
        if apply_cat:
            cinfo.update(infoP)
            cattrs["features"].update(featX)
            cattrs.update(dict(attrX))
        else:
            cattrs = {"isSoftCreated": False, "info": {"domain": domain, "status": cat_status[cat]}}
        recs.append({"createdAt": GEN_TS, "updatedBy": uby, "fqdn": f"{glossary_name}/{cat}",
                     "rootId": root, "createdBy": cby, "name": cat,
                     "attributes": cattrs, "type": "category", "parentId": root,
                     "updatedAt": GEN_TS, "resourceId": "null", "_id": cid, "sort": None})

    for r in rows:
        if not _kept(r):
            continue
        cat = r["Category"]
        infoP, featX, attrX, cby, uby = cat_block[cat]
        tid = det_term_id(glossary_name, cat, r['Term'])
        sens = r["Sensitivity"]
        info = {"domain": domain, "definition": _lex(r["Definition"]),
                "classification": _classification(sens),
                "status": cat_status[cat], "purpose": _lex(r.get("Purpose") or f"Suggested from {r['Source_Column']}.")}
        info.update(infoP)
        if r.get("Abbreviation"):
            info["abbreviation"] = r["Abbreviation"]
        features = {"sensitivity": sens,
                    "isCriticalDataElement": str(r["Critical_Data_Element"]).lower() == "yes"}
        features.update(featX)
        attrs = {"features": features, "isSoftCreated": False, "info": info}
        attrs.update(dict(attrX))
        if r.get("Suggested_Tags"):
            attrs["tags"] = [{"name": t.strip().lower()}
                             for t in r["Suggested_Tags"].split(";") if t.strip()]
        recs.append({"createdAt": GEN_TS, "updatedBy": uby,
                     "fqdn": f"{glossary_name}/{cat}/{r['Term']}", "rootId": root,
                     "createdBy": cby, "name": r["Term"], "attributes": attrs,
                     "type": "term", "parentId": cat_id[cat], "updatedAt": GEN_TS,
                     "resourceId": "null", "_id": tid, "sort": None})
    return recs

def records_to_jsonl(recs):
    """Serialise glossary records to JSONL (one JSON object per line)."""
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n"


# --------------------------------------------------------------------------- #
#  Action "verdict" checks — each returns {title, rows[], issues[], tone, verdict}
#  so the UI can show "what came back + a plain-English verdict" (like the PDC
#  Resolve probe) for Generate JSONL, Scan, and Document Discovery.
# --------------------------------------------------------------------------- #
def _trunc(items, n=6):
    items = list(items)
    return ", ".join(items[:n]) + ("…" if len(items) > n else "")


def glossary_build_check(rows, recs, glossary_name):
    """Build-time sanity check for the glossary JSONL: counts, plus the issues that
       actually bite on import or Resolve — id collisions (same term twice in a
       category share one UUID5 id), names that repeat across categories (ambiguous
       for name-based Resolve), and missing category/definition."""
    from collections import Counter
    kept = [r for r in rows if _kept(r)]
    terms = [r for r in recs if r.get("type") == "term"]
    cats = [r for r in recs if r.get("type") == "category"]

    no_def = [r.get("Term", "") for r in kept if not str(r.get("Definition", "")).strip()]
    no_cat = [r.get("Term", "") for r in kept if not str(r.get("Category", "")).strip()]
    pair_ct = Counter((r.get("Category", ""), r.get("Term", "")) for r in kept)
    dup_pairs = sorted(f"{(c or '—')} / {t}" for (c, t), n in pair_ct.items() if n > 1)
    name_ct = Counter(r.get("Term", "") for r in kept)
    dup_names = sorted(t for t, n in name_ct.items() if n > 1)

    rows_out = [
        {"label": "Glossary", "value": glossary_name},
        {"label": "Lines", "value": f"{len(recs)} ({len(cats)} categories, {len(terms)} terms)"},
        {"label": "Kept / dropped", "value": f"{len(kept)} / {len(rows) - len(kept)}"},
    ]
    issues = []
    # every flagged term rides along in full ("terms": [{label, q}]) so the UI can
    # render clickable chips that jump the grid straight to the offender — no
    # scrolling the glossary to hunt down the last few
    if dup_pairs:
        issues.append({"tone": "bad", "text": f"{len(dup_pairs)} term(s) duplicated within a category — "
                       "each pair shares ONE generated id, so on import one overwrites the other. "
                       "Merge or rename these on the Review page (the duplicate header offers both):",
                       "terms": [{"label": p2, "q": p2.split(" / ", 1)[-1]} for p2 in dup_pairs]})
    if dup_names:
        # name WHERE each duplicate lives — "Status" alone still sent the
        # steward hunting through five categories (field-caught twice)
        name_cats = {}
        for r in kept:
            name_cats.setdefault(r.get("Term", ""), set()).add(
                (r.get("Category", "") or "—").strip() or "—")
        issues.append({"tone": "warn",
                       "text": f"{len(dup_names)} term name(s) live in more than one "
                       "category. Resolve matches terms BY NAME and may link a column "
                       "to the wrong one — on the Review page, rename one of each "
                       "(filter by the name), or merge them if they are one concept:",
                       "terms": [{"label": f"{t}  —  in {' · '.join(sorted(name_cats.get(t, [])))}",
                                  "q": t} for t in dup_names]})
    if no_cat:
        issues.append({"tone": "warn", "text": f"{len(no_cat)} term(s) have no category — they land in PDC under "
                       "'Unassigned'. Set a category on the Review page:",
                       "terms": [{"label": t, "q": t} for t in sorted(set(no_cat))]})
    if no_def:
        issues.append({"tone": "warn", "text": f"{len(no_def)} term(s) have no definition — they import blank. "
                       "The AI pass (or a row edit) on the Review page fills them:",
                       "terms": [{"label": t, "q": t} for t in sorted(set(no_def))]})

    tone = "bad" if dup_pairs else ("warn" if issues else "ok")
    verdict = ({"ok": f"All {len(terms)} terms are clean — import this JSONL in PDC (Glossary → Actions → Import), then Resolve & Apply.",
                "warn": "Importable as-is — but every term named above risks an ambiguous link or an "
                        "'Unassigned' landing. Fix them on the Review page, then Generate again; the "
                        "check reruns each time.",
                "bad": "Duplicate terms in the same category LOSE DATA on import — merge or rename them "
                       "on the Review page before importing, then Generate again."})[tone]
    return {"title": "Build check", "rows": rows_out, "issues": issues, "tone": tone, "verdict": verdict}


def scan_check(rows, scanned, pk_cols=0, fk_cols=0):
    """Verdict for a scan: what the catalog saw and what's worth a look before
       generating (no PKs, no DQ, lots of low-confidence templated terms)."""
    from collections import Counter
    sens = Counter(r.get("Sensitivity", "") for r in rows)
    conf = Counter(r.get("Confidence", "") for r in rows)
    cde = sum(1 for r in rows if str(r.get("Critical_Data_Element", "")).lower() == "yes")
    pii = sum(1 for r in rows if str(r.get("PII_Category", "")).strip())
    dq = sum(1 for r in rows if r.get("Suggested_Quality") is not None)
    is_db = scanned.get("tables") is not None

    rows_out = []
    if is_db:
        rows_out.append({"label": "Scanned", "value": f"{scanned.get('tables', 0)} tables · {scanned.get('columns', 0)} columns"})
    if scanned.get("objects") is not None:
        rows_out.append({"label": "Scanned", "value": f"{scanned.get('objects', 0)} files · {scanned.get('folders', 0)} folders"})
    rows_out.append({"label": "Terms suggested", "value": str(len(rows))})
    rows_out.append({"label": "Sensitivity", "value": f"HIGH {sens.get('HIGH', 0)} · MED {sens.get('MEDIUM', 0)} · LOW {sens.get('LOW', 0)}"})
    rows_out.append({"label": "CDE / PII", "value": f"{cde} critical · {pii} PII"})
    if is_db:
        rows_out.append({"label": "Keys detected", "value": f"{pk_cols} PK · {fk_cols} FK"})
    rows_out.append({"label": "Confidence", "value": f"High {conf.get('High', 0)} · Med {conf.get('Medium', 0)} · Low {conf.get('Low', 0)}"})
    if is_db:
        rows_out.append({"label": "DQ computed", "value": f"{dq} of {len(rows)} columns"})

    issues = []
    if is_db and not pk_cols:
        issues.append({"tone": "warn", "text": "No primary keys detected — PDC's 'Is Primary Key' comes from the DB catalog scan, "
                       "so re-catalog the source (and check the JDBC driver) if you expect PKs."})
    if is_db and dq == 0:
        issues.append({"tone": "warn", "text": "No Data Quality computed — turn on profiling for this connection so each column gets a "
                       "DQ score (one of the four Trust-Score inputs)."})
    low = conf.get("Low", 0)
    if low and low > max(1, len(rows) // 2):
        issues.append({"tone": "warn", "text": f"{low} of {len(rows)} terms are Low confidence (templated from the column name) — "
                       "review their definitions before generating."})
    tone = "warn" if issues else "ok"
    verdict = ("Scan looks good — review the suggested terms, then Generate JSONL." if tone == "ok"
               else "Scan complete. The notes above are worth a look before you generate the glossary.")
    return {"title": "Scan check", "rows": rows_out, "issues": issues, "tone": tone, "verdict": verdict}
