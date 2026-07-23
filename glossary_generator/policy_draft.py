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


# Custom-only: this engine authors a Data Pattern / Dictionary ONLY from a
# concept's own profiled evidence (induced Value_Pattern or reference list).
# There are deliberately NO inbuilt/canonical shapes (e.g. a hardcoded SSN or
# email regex) — a built-in pattern can misclassify against the real data and
# cause drift. A concept that profiling can't induce is either seeded from the
# versioned domain pack (curated seeds, carried through the Registry) or left to
# a re-scan with value profiling on. See registry/bridge.py::_curated_seeds.


def _valid_regex(rx):
    if not rx or not isinstance(rx, str):
        return False
    try:
        re.compile(rx)
        return True
    except re.error:
        return False


# ------------------------------------------------------------------ DQ rules
# Data-quality expectations — the third leg of the industry-standard split:
#   glossary   = what the concept IS,
#   detection  = which columns ARE one (Patterns/Dictionaries above),
#   quality    = are the VALUES valid (these).
# Every check is derived from the scan itself (custom, deterministic): the
# induced value regex becomes a format-conformance check, a profiled reference
# list becomes an allowed-values check, and the profiled completeness /
# uniqueness become baseline thresholds ("don't regress below what the scan
# measured"). Nothing inbuilt — a term with no profiled signal gets no rule.

def _floor2(x):
    try:
        return int(float(x) * 100) / 100.0
    except (TypeError, ValueError):
        return None


# Type-conformance checks from the scanned column TYPE (schema metadata — still
# custom/deterministic). Valuable where the rules actually run: extracts and
# landing zones, where the engine no longer enforces the type. Name fallback for
# date-shaped columns covers rows scanned before types were persisted.
_TYPE_DATE = re.compile(r"date|time(stamp)?", re.I)
_TYPE_NUM = re.compile(r"int|decimal|numeric|float|double|real|money", re.I)
_NAME_DATE = re.compile(r"(^|_)(dt|date|dob|ts)($|_)|date|birth|timestamp", re.I)


def _type_check(col, ctype):
    t = str(ctype or "").strip()
    if t:
        if _TYPE_DATE.search(t):
            return {"check": "valid_date", "source": "schema (type %s)" % t}
        if _TYPE_NUM.search(t):
            return {"check": "numeric", "source": "schema (type %s)" % t}
        return None
    name = col.split(".")[-1]
    if _NAME_DATE.search(name):
        return {"check": "valid_date", "source": "column name (date-shaped)"}
    return None


def dq_rules_from_rows(rows, glossary_name="Business Glossary", prefix=None):
    """rows -> [{filename, term, rule, checks}] — one DQ-expectation artifact per
    kept term that carries at least one scan-derived signal."""
    prefix = (prefix or "").strip() or re.sub(r"\s+", " ", str(glossary_name or "")).split(" ")[0] or "Rule"
    out, seen = [], set()
    for r in rows or []:
        if not isinstance(r, dict) or not _kept(r):
            continue
        term = (r.get("Term") or "").strip()
        cols = _cols_of(r)
        if not term or term in seen or not cols:
            continue
        seen.add(term)
        vp = (r.get("Value_Pattern") or "").strip()
        sig = (r.get("Value_Signature") or "").strip()
        enums = [v.strip() for v in str(r.get("Enum_Values") or "").split(";") if v.strip()]
        dims = r.get("Source_Quality_Dims") or {}
        keys = r.get("Source_Keys") or {}
        types = r.get("Source_Types") or {}
        expectations = []
        for col in cols:
            checks = []
            tc = _type_check(col, types.get(col))
            if tc:
                checks.append(tc)
            if vp:
                checks.append({"check": "format", "regex": vp,
                               **({"signature": sig} if sig else {}),
                               "source": "profiled"})
            if len(enums) >= 2:
                checks.append({"check": "allowed_values", "values": enums,
                               "source": "profiled"})
            d = dims.get(col) or {}
            comp = _floor2(d.get("c"))
            if d.get("nn"):
                checks.append({"check": "not_null", "min_completeness": 1.0,
                               "source": "schema (NOT NULL)"})
            elif comp is not None:
                checks.append({"check": "not_null", "min_completeness": comp,
                               "observed": comp, "source": "profiled baseline"})
            uniq = _floor2(d.get("u"))
            k = keys.get(col) or {}
            if d.get("eu") or k.get("pk"):
                checks.append({"check": "unique",
                               "min_uniqueness": uniq if uniq is not None else 1.0,
                               **({"observed": uniq} if uniq is not None else {}),
                               "source": ("schema (PRIMARY KEY)" if k.get("pk")
                                          else "profiled baseline")})
            if checks:
                expectations.append({"column": col, "checks": checks})
        if not expectations:
            continue
        name = f"{prefix} {term} DQ"
        out.append({
            "filename": f"{_slug(prefix)}_{_slug(term)}_dq.json",
            "term": term,
            "checks": sum(len(e["checks"]) for e in expectations),
            "rule": {
                "type": "DataQualityExpectations",
                "name": name,
                "term": term,
                "category": (r.get("Category") or None),
                "glossary": glossary_name,
                "note": ("derived from the scan's own profile — format = induced value "
                         "regex, allowed_values = profiled reference list, thresholds = "
                         "measured baselines (a run below baseline is a regression)"),
                "expectations": expectations,
            },
        })
    return out


# Column kinds whose VALUES carry no detectable shape — a surrogate integer key,
# a date, a person/free-text name, or a raw amount. You can't recognise an
# "Account ID" or a date by its value (any integer/date could be one), so these
# are governed by the term↔column link (tagged on Apply), never a value pattern.
# Deliberately narrow: codes/statuses and formatted numbers (account_no,
# routing, zip, phone, ssn, email…) are NOT here — those become dictionaries /
# patterns once profiled.
_NO_SHAPE = re.compile(
    r"(^|_)id$|_id$|identifier"                 # surrogate-key ids
    r"|(^|_)dt$|date|dob|birth"                 # dates
    r"|(^|_)nm$|name"                           # names / free text
    r"|amount|(^|_)amt$|balance|(^|_)bal$",     # raw amounts
    re.I)


def _no_value_shape(cols):
    """True when EVERY source column is a kind with no detectable value shape, so
    the term is a link-only concern rather than a not-yet-profiled one."""
    names = [str(c).split(".")[-1] for c in (cols or []) if c]
    return bool(names) and all(_NO_SHAPE.search(n) for n in names)


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
    # Curated seeds from the versioned domain pack (source 'curated') — the
    # custom-only program's generic baseline for concepts profiling can't induce.
    # These are user-maintained in the pack, not inbuilt/hardcoded. Profiled
    # evidence always wins; curated only fills a gap.
    try:
        from registry.bridge import _curated_seeds
        curated = _curated_seeds()
    except Exception:
        curated = {}
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
            # Profiled evidence wins; otherwise fall back to a CURATED seed from
            # the versioned domain pack (the generic baseline). Still no
            # inbuilt/hardcoded shapes — the seed lives in the user's pack.
            cur = curated.get(term.lower(), [])
            cp = next((s for s in cur if s.get("type") == "pattern" and (s.get("regex") or "").strip()), None)
            cd = next((s for s in cur if s.get("type") == "dictionary" and len([v for v in (s.get("values") or []) if str(v).strip()]) >= 2), None)
            if cp:
                vp, sig, seed_kind = cp["regex"].strip(), (cp.get("signature") or "").strip() or None, "curated"
            elif cd:
                enums, seed_kind = [str(v).strip() for v in cd["values"] if str(v).strip()], "curated"
            elif not any(c.count(".") >= 2 for c in _cols_of(r)):
                skipped.append({"term": term, "why": "document term — identify documents with vocabulary dictionaries, not value shapes"})
                continue
            elif not sig and not (r.get("Enum_Values") or "").strip():
                if _no_value_shape(_cols_of(r)):
                    skipped.append({"term": term, "why": "tagged via the term↔column link, not a value pattern — a surrogate id / date / name / amount has no value shape to detect (expected)"})
                else:
                    skipped.append({"term": term, "why": "no profiled evidence on the row — re-scan the live source with value profiling on to induce a custom pattern, or add a curated seed for this term to the domain pack"})
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
                "seed": seed_kind,
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
        for q in draft.get("quality", []):
            z.writestr("Quality/" + q["filename"], json.dumps(q["rule"], indent=2) + "\n")
            index.append(f"quality,{q['rule']['name']},Quality/{q['filename']},{q['term']}")
        z.writestr("INDEX.csv", "\n".join(index) + "\n")
        z.writestr("README.txt",
                   "Drafted by the Glossary Generator from scan evidence.\n"
                   "Patterns/ and Dictionaries/: import via PDC Management -> Data Identification -> Import.\n"
                   "Quality/: data-quality expectations (data-contract style) derived from the same\n"
                   "profile - format = the induced value regex, allowed_values = the profiled\n"
                   "reference list, completeness/uniqueness thresholds = the measured baselines\n"
                   "(a later run below its baseline is a regression). Feed them to your DQ runner.\n"
                   "Review every rule before importing - these are drafts, not decisions.\n")
    return buf.getvalue()
