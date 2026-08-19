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
is imported anywhere by this module — the output is EVIDENCE the steward reviews. The
import package itself is the Policy Generator's job: the same decisions travel there
inside the Classification Registry (see registry/bridge.py and engine/policy_seed.py),
which is the one contract between the two apps.
"""
from __future__ import annotations
import io, json, re, zipfile

# The row -> detection-seed ladder is SHARED with the Registry bridge (1.38.24):
# this module mints a rule from the best seed, the bridge carries them all into
# the Registry, and neither decides what counts as evidence on its own any more.
from engine.policy_seed import (
    DATE_SHAPE as _DATE_SHAPE, NUM_SHAPE as _NUM_SHAPE, NO_SHAPE as _NO_SHAPE,
    cols_of as _cols_of, col_names as _col_names, column_name_regex,
    kind_patterns as _kind_patterns, was_profiled as _was_profiled,
    auto_candidate as _auto_candidate, no_value_shape as _no_value_shape,
    seeds_for_row,
)

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
_DICT_CONDITION = {"and": [
    # the shipped Pentaho "Personal Data Identifier" template's exact shape —
    # (confidence OR name-hint) AND a cardinality guard. The template guards
    # at > 5; ours mints dictionaries from the column's OWN profiled
    # vocabulary (2..48 distinct), so > 1 mirrors the mint's enum floor
    # without vetoing a legitimate 3-value LOW/MEDIUM/HIGH.
    {"or": [
        {">=": [{"var": "confidenceScore"}, "0.6"]},
        {">=": [{"var": "metadataScore"}, "0.7"]},
    ]},
    {">": [{"var": "columnCardinality"}, "1"]},
]}

# Name-anchored measure rules (steward flipped a mapping-only nature to Auto):
# the content shape carries SANITY only — the range lives in the DQ rule — so
# identity must come from the column name. The weights rebalance to name 0.5 +
# content regex 0.5: under the standard 0.3/0.4/0.3 blend a rule with no
# contentPatterns can never clear the 0.7 gate (0.3 + 0.3 = 0.6), while 0.5/0.5
# makes the rule a strict name AND shape conjunction — neither alone reaches 0.7.
_NAME_ANCHOR_WEIGHTS = (0.5, 0.0, 0.5)
# regexScore is NOT a PDC condition variable (only confidenceScore,
# metadataScore, similarity, columnCardinality are) — so the name-AND-shape
# conjunction can only live in the blended confidenceScore, which is what the
# 0.5/0/0.5 weights do. The cardinality guard is PDC's own template guard: a
# constant or near-constant column can never satisfy a sanity shape.
_NAME_ANCHOR_CONDITION = {"and": [
    {">=": [{"var": "confidenceScore"}, "0.7"]},
    {">": [{"var": "columnCardinality"}, "5"]},
]}


def _slug(s):
    return _NON.sub("_", str(s or "")).strip("_").lower() or "term"


def _kept(r):
    return str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")


def _tags_of(r, limit=3):
    """The rule's Assign-Tags: the row's first governed tags, minus the purely
    structural ones a policy shouldn't stamp on its own."""
    skip = {"maskable", "identifier", "record", "table-level"}
    tags = [t.strip() for t in str(r.get("Suggested_Tags") or "").split(";") if t.strip()]
    return [t for t in tags if t not in skip][:limit]


def _pattern_rule(name, category, col_rx, signature, content_rx, tags, term,
                  weights=None, condition=None):
    w_name, w_pat, w_rx = weights or (0.3, 0.4, 0.3)
    if weights is None:
        conf = _PATTERN_CONFIDENCE
    else:
        # the confidence blend must mirror the weight fields — a rebalanced
        # rule keeping the stock 0.3/0.4/0.3 formula could never fire
        parts = [{"*": [{"var": "metadataScore"}, w_name]}]
        if w_pat:
            parts.append({"*": [{"var": "patternScore"}, w_pat]})
        parts.append({"*": [{"var": "regexScore"}, w_rx]})
        conf = {"+": parts}
    rule = {
        "__typename": "patternsRules",
        "type": "Pattern",
        "name": name,
        "category": category,
        "status": "enabled",
        "columnNameRegex": ([{"regex": col_rx, "score": 1.0}] if col_rx else []),
        "columnNameWeight": w_name,
        "contentPatterns": ([{"pattern": signature}] if signature else []),
        "contentPatternWeight": w_pat,
        "contentRegex": [{"regex": content_rx}],
        "contentRegexWeight": w_rx,
        "confidenceScore": conf,
        "condition": condition or _PATTERN_CONDITION,
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
            else:
                # recognised kinds carry the profiler's shape into DQ too —
                # an email column's format expectation ships even though the
                # detection pattern is canonical ("build a draft policy and
                # some dq rules as well": full estate coverage, all custom)
                kind = str(r.get("Value_Kind") or "").strip().lower()
                if kind in _kind_patterns():
                    checks.append({"check": "format", "regex": _kind_patterns()[kind],
                                   "kind": kind, "source": "recognised"})
            if len(enums) >= 2:
                checks.append({"check": "allowed_values", "values": enums,
                               "source": "profiled"})
            # numeric range: min/max observed at profiling time become the
            # expectation's baseline — a capacity that has lived in 201..5095
            # arriving as 0 or 500000 is exactly what DQ should catch. The
            # open numeric-range item, closed by the evidence now riding rows.
            rng = str(r.get("Value_Range") or "").strip()
            m_rng = re.match(r"^(-?[0-9.]+)\.\.(-?[0-9.]+)$", rng)
            if m_rng:
                lo, hi = float(m_rng.group(1)), float(m_rng.group(2))
                checks.append({"check": "range",
                               "min": int(lo) if lo.is_integer() else lo,
                               "max": int(hi) if hi.is_integer() else hi,
                               "source": "profiled baseline"})
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
    patterns, dictionaries, skipped, mapping_only = [], [], [], []
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
        # The row -> seed ladder lives in policy_seed and is shared with the
        # Registry bridge: it hands back every seed the row supports, best
        # evidence first. This drafter mints ONE artifact per term, so it takes
        # the first; the Registry carries them all.
        seeds, skip, mo = seeds_for_row(r, curated)
        if skip:
            # a missing physical column outranks the declaration: a table-level
            # term has nothing to link OR to detect, and saying so is the useful
            # message (the order the ladder itself keeps)
            skipped.append({"term": term, "why": skip})
            continue
        if mo:
            # the row may still carry evidence — the Registry keeps it, this
            # drafter mints nothing, which is what mapping-only means
            mapping_only.append({"term": term,
                                 "why": "mapping-only by design — governed via "
                                        "term↔column links; no detection method expected",
                                 "auto_candidate": mo["auto_candidate"]})
            continue
        seed = seeds[0]
        seed_kind = seed["source"]
        vp = seed["regex"] if seed["type"] == "pattern" else ""
        sig = seed.get("signature") if seed["type"] == "pattern" else None
        enums = list(seed.get("values") or [])
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
                "rule": _pattern_rule(
                    name, category, col_rx, sig, vp, tags, term,
                    weights=_NAME_ANCHOR_WEIGHTS if seed_kind == "name-anchored" else None,
                    condition=_NAME_ANCHOR_CONDITION if seed_kind == "name-anchored" else None),
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
    return {"patterns": patterns, "dictionaries": dictionaries, "skipped": skipped, "mapping_only": mapping_only,
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
        if draft.get("labels") and draft["labels"].get("keys"):
            z.writestr("Labels/labels.json", json.dumps(draft["labels"], indent=2) + "\n")
            for k in draft["labels"]["keys"]:
                index.append(f"label,{k['key']},Labels/labels.json,")
        z.writestr("INDEX.csv", "\n".join(index) + "\n")
        z.writestr("README.txt",
                   "Drafted by the Glossary Generator from scan evidence.\n"
                   "\n"
                   "THIS BUNDLE IS EVIDENCE TO REVIEW, NOT AN IMPORT PACKAGE. Read the drafts\n"
                   "here; import from the POLICY GENERATOR, which authors the same decisions\n"
                   "in the layout PDC's own Export produces (a flat zip of pattern JSON, one\n"
                   "nested zip per dictionary) and can push them over PDC's import API. The\n"
                   "folders below are laid out for a human, and PDC will not read them.\n"
                   "\n"
                   "Patterns/ and Dictionaries/: the drafted Data Identification rules. Every\n"
                   "one of them travels to the Policy Generator inside the Classification\n"
                   "Registry, so nothing here has to be carried across by hand.\n"
                   "Quality/: data-quality expectations (data-contract style) derived from the same\n"
                   "profile - format = the induced value regex, allowed_values = the profiled\n"
                   "reference list, completeness/uniqueness thresholds = the measured baselines\n"
                   "(a later run below its baseline is a regression). Feed them to your DQ runner.\n"
                   "Labels/: the label families and values derived from the same rows - stamped\n"
                   "onto columns from the Apply page, not imported as Data Identification.\n"
                   "\n"
                   "Review every rule before deploying - these are drafts, not decisions.\n")
    return buf.getvalue()
