"""
policy_draft.py — draft PDC Data Identification artifacts from the reviewed rows.

The first working incarnation of the Policy Generator: every kept term whose scan
produced a detection seed becomes a ready-to-import PDC rule, in exactly the shape
the Technical Track teaches —
  * an induced value regex          -> a Data Pattern (patternsRules JSON),
  * a profiled reference-value list -> a Dictionary (dictionariesRules JSON + values CSV).

The core is deterministic (same rows -> same files); the AI agent (llm.policy_hints_rows)
only polishes the column-name regex and the tag pick when Ollama is available, and its
proposals are guard-railed here (regex must compile, tags must stay governed). Nothing
is imported anywhere by this module — the output is files for PDC's Data Identification
import screens, which the steward reviews first.
"""
from __future__ import annotations
import io, json, re, zipfile

_NON = re.compile(r"[^A-Za-z0-9]+")

# TT-standard blend weights and thresholds (see courseware CSCU-Patterns/Dictionaries)
_PATTERN_CONFIDENCE = {"+": [
    {"*": [{"var": "metadataScore"}, 0.3]},
    {"*": [{"var": "patternScore"}, 0.4]},
    {"*": [{"var": "regexScore"}, 0.3]},
]}
_PATTERN_CONDITION = {"and": [{">=": [{"var": "confidenceScore"}, "0.7"]}]}
_DICT_CONFIDENCE = {"+": [
    {"*": [{"var": "similarity"}, 0.8]},
    {"*": [{"var": "metadataScore"}, 0.2]},
]}
_DICT_CONDITION = {"or": [
    {">=": [{"var": "confidenceScore"}, "0.6"]},
    {">=": [{"var": "metadataScore"}, "0.7"]},
]}


def _slug(s):
    return _NON.sub("_", str(s or "")).strip("_").lower() or "term"


def _kept(r):
    return str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")


def _cols_of(r):
    return [c.strip() for c in str(r.get("Source_Column") or "").split(";") if c.strip()]


def _col_names(r):
    """Bare column names off the row's physical columns (schema.table.column)."""
    out = []
    for c in _cols_of(r):
        name = c.split(".")[-1].strip()
        if name and name not in out:
            out.append(name)
    return out


def column_name_regex(names):
    """Deterministic column-name hint from the physical names the scan actually
    saw: a case-insensitive alternation with flexible separators, e.g.
    ['mbr_no', 'member_no'] -> (?i)(mbr_?no|member_?no)."""
    parts = []
    for n in names:
        toks = [re.escape(t) for t in re.split(r"[^A-Za-z0-9]+", n) if t]
        if toks:
            p = "_?".join(toks)
            if p not in parts:
                parts.append(p)
    if not parts:
        return None
    return "(?i)(" + "|".join(parts) + ")"


def _tags_of(r, limit=3):
    """The rule's Assign-Tags: the row's first governed tags, minus the purely
    structural ones a policy shouldn't stamp on its own."""
    skip = {"maskable", "identifier", "record", "table-level"}
    tags = [t.strip() for t in str(r.get("Suggested_Tags") or "").split(";") if t.strip()]
    return [t for t in tags if t not in skip][:limit]


def _pattern_rule(name, category, col_rx, signature, content_rx, tags, term):
    rule = {
        "__typename": "patternsRules",
        "type": "Pattern",
        "name": name,
        "category": category,
        "status": "enabled",
        "columnNameRegex": ([{"regex": col_rx, "score": 1.0}] if col_rx else []),
        "columnNameWeight": 0.3,
        "contentPatterns": ([{"pattern": signature}] if signature else []),
        "contentPatternWeight": 0.4,
        "contentRegex": [{"regex": content_rx}],
        "contentRegexWeight": 0.3,
        "confidenceScore": _PATTERN_CONFIDENCE,
        "condition": _PATTERN_CONDITION,
        "actions": [{"applyTags": [{"k": t} for t in tags]}] if tags else [],
    }
    if term:
        rule["assignBusinessTerm"] = [{"k": term}]
    return [rule]


def _dictionary_rule(name, category, col_rx, tags, term):
    rule = {
        "__typename": "dictionariesRules",
        "type": "Dictionary",
        "name": name,
        "category": category,
        "minSamples": 1,
        "confidenceScore": _DICT_CONFIDENCE,
        "columnNameRegex": ([{"regex": col_rx, "score": 0.9}] if col_rx else []),
        "condition": _DICT_CONDITION,
        "actions": [{"applyTags": [{"k": t} for t in tags]}] if tags else [],
    }
    if term:
        rule["assignBusinessTerm"] = [{"k": term}]
    return [rule]


# Canonical seeds for the classic shapes that CANNOT be position-induced from
# samples (every email is a different length) or that arrive masked. Keyed by
# a (column-name regex, PII category) gate; kept deliberately short — the
# scan's own induced evidence always wins when present.
_CANONICAL_SEEDS = [
    {"gate_name": re.compile(r"e[-_]?mail", re.I), "gate_pii": {"CONTACT_INFO"},
     "signature": "aaaa@aaaa.aaa",
     "regex": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
     "label": "canonical email shape"},
    {"gate_name": re.compile(r"(^|_)ssn(_|$)|social_?security", re.I), "gate_pii": {"GOVERNMENT_ID"},
     "signature": "nnn-nn-nnnn",
     "regex": r"^\d{3}-\d{2}-\d{4}$",
     "label": "canonical SSN shape"},
]


def _canonical_seed(r):
    """A well-known fallback seed for a row with no profiled evidence, gated on
    BOTH the column name and the PII classification so it never fires loosely."""
    names = " ".join(_col_names(r))
    pii = (r.get("PII_Category") or "").strip()
    for c in _CANONICAL_SEEDS:
        if c["gate_name"].search(names) and pii in c["gate_pii"]:
            return c
    return None


def _valid_regex(rx):
    if not rx or not isinstance(rx, str):
        return False
    try:
        re.compile(rx)
        return True
    except re.error:
        return False


def draft_from_rows(rows, glossary_name="Business Glossary", prefix=None,
                    hints=None, governed_tags=None):
    """rows -> {'patterns': [...], 'dictionaries': [...], 'skipped': [...]}.

    One artifact per kept term that carries a detection seed (Value_Pattern or
    Enum_Values with 2+ values); everything else lands in `skipped` with the
    reason, so the steward can see exactly what the scan could not seed.
    `hints` ({term: {column_regex, tags}} from the AI agent) may override the
    deterministic column regex / tag pick — guard-railed: the regex must compile
    and the tags must be in `governed_tags` (when given)."""
    prefix = (prefix or "").strip() or re.sub(r"\s+", " ", str(glossary_name or "")).split(" ")[0] or "Rule"
    hints = hints or {}
    gov = {str(t).strip().lower() for t in (governed_tags or [])}
    patterns, dictionaries, skipped = [], [], []
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict) or not _kept(r):
            continue
        term = (r.get("Term") or "").strip()
        if not term or term in seen:
            continue
        seen.add(term)
        src = str(r.get("Source_Column") or "").strip()
        if not src:
            skipped.append({"term": term, "why": "table-level term — no physical column to identify"})
            continue
        vp = (r.get("Value_Pattern") or "").strip()
        sig = (r.get("Value_Signature") or "").strip() or None
        seed_kind = "profiled"
        enums = [v.strip() for v in str(r.get("Enum_Values") or "").split(";") if v.strip()]
        if not vp and len(enums) < 2:
            canon = _canonical_seed(r)
            if canon:
                vp, sig, seed_kind = canon["regex"], canon["signature"], "canonical"
            elif not any(c.count(".") >= 2 for c in _cols_of(r)):
                skipped.append({"term": term, "why": "document term — identify documents with vocabulary dictionaries, not value shapes"})
                continue
            elif not sig and not (r.get("Enum_Values") or "").strip():
                skipped.append({"term": term, "why": "no profiled evidence on the row — re-scan the live source (evidence capture needs app 1.8.0+)"})
                continue
            else:
                skipped.append({"term": term, "why": "no stable shape in the data (free text, names, amounts, dates)"})
                continue
        h = hints.get(term) or {}
        col_rx = h.get("column_regex")
        if not (_valid_regex(col_rx)):
            col_rx = column_name_regex(_col_names(r))
        tags = [str(t).strip().lower() for t in (h.get("tags") or []) if str(t).strip()]
        if gov:
            tags = [t for t in tags if t in gov]
        if not tags:
            tags = _tags_of(r)
        name = f"{prefix} {term}"
        category = f"{_slug(prefix).upper()}_{_slug(r.get('Category') or 'General').title().replace('_', '')}"
        if vp:
            patterns.append({
                "filename": f"{_slug(prefix)}_{_slug(term)}.json",
                "term": term,
                "seed": seed_kind,
                "rule": _pattern_rule(name, category, col_rx, sig, vp, tags, term),
            })
        else:
            dictionaries.append({
                "filename": f"{_slug(prefix)}_{_slug(term)}_rule.json",
                "values_filename": f"{_slug(prefix)}_{_slug(term)}.csv",
                "term": term,
                "rule": _dictionary_rule(name, category, col_rx, tags, term),
                "csv": "term\n" + "\n".join(enums) + "\n",
            })
    return {"patterns": patterns, "dictionaries": dictionaries, "skipped": skipped,
            "glossary": glossary_name, "prefix": prefix}


def to_zip_bytes(draft):
    """Package a draft as one zip: Patterns/*.json, Dictionaries/*_rule.json +
    values CSVs, and an INDEX.csv the steward can review at a glance."""
    buf = io.BytesIO()
    index = ["kind,name,file,term"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in draft.get("patterns", []):
            z.writestr("Patterns/" + p["filename"], json.dumps(p["rule"], indent=2) + "\n")
            index.append(f"pattern,{p['rule'][0]['name']},Patterns/{p['filename']},{p['term']}")
        for d in draft.get("dictionaries", []):
            z.writestr("Dictionaries/" + d["filename"], json.dumps(d["rule"], indent=2) + "\n")
            z.writestr("Dictionaries/" + d["values_filename"], d["csv"])
            index.append(f"dictionary,{d['rule'][0]['name']},Dictionaries/{d['filename']},{d['term']}")
        z.writestr("INDEX.csv", "\n".join(index) + "\n")
        z.writestr("README.txt",
                   "Drafted by the Glossary Generator from scan evidence.\n"
                   "Import via PDC: Management -> Data Identification -> Patterns / Dictionaries -> Import.\n"
                   "Review every rule before importing - these are drafts, not decisions.\n")
    return buf.getvalue()
