"""
Per-company **Term & tag dictionary** — the governed vocabulary that drives
tagging and term naming, in two layers:

  * a GENERIC baseline (built-in): common terms and tags with common sensitivity
    levels — the industry-neutral starting point, protected from deletion,
  * a COMPANY layer (editable): terms and tags specific to this deployment, seeded
    from the domain pack and GROWN from what the scans/discovery actually find.

Both feed the Registry at export, so the Policy Generator draws Data Identification
Assign-Tags (and term links) from the same governed vocabulary. That shared list is
the tag-consistency contract — the one drift surface PDC does not enforce — so edits
are guard-railed (generic baseline can't be removed, rule tags must exist in the
vocabulary, sensitivity values are validated) and any risky change is reported back
as a warning rather than silently applied.

Saved to tag_dictionary.json (override with $GLOSSARY_TAG_DICTIONARY).
"""
from __future__ import annotations
import os, re, json, threading

HERE = os.path.dirname(os.path.abspath(__file__))
DICT_FILE = os.environ.get("GLOSSARY_TAG_DICTIONARY") or os.path.join(HERE, "tag_dictionary.json")
SCHEMA = "term-tag-dictionary/1"
_SENS = ("LOW", "MEDIUM", "HIGH")

# --- GENERIC baseline: tags (with common sensitivity floor) ----------------- #
_SEED_TAGS = {
    "PII":              {"label": "PII", "sensitivity_floor": "HIGH"},
    "personal-data":    {"label": "Personal data", "sensitivity_floor": "HIGH"},
    "direct-identifier":{"label": "Direct identifier", "sensitivity_floor": "HIGH"},
    "privacy":          {"label": "Privacy", "sensitivity_floor": "MEDIUM"},
    "contact":          {"label": "Contact info", "sensitivity_floor": "MEDIUM"},
    "location":         {"label": "Location", "sensitivity_floor": "MEDIUM"},
    "financial":        {"label": "Financial", "sensitivity_floor": "MEDIUM"},
    "sensitive":        {"label": "Sensitive", "sensitivity_floor": "MEDIUM"},
    "tax":              {"label": "Tax"},
    "billing":          {"label": "Billing"},
    "rate":             {"label": "Rate / tariff"},
    "revenue":          {"label": "Revenue"},
    "usage":            {"label": "Usage"},
    "metering":         {"label": "Metering"},
    "water-quality":    {"label": "Water quality"},
    "compliance":       {"label": "Regulatory compliance"},
    "water-system":     {"label": "Water system"},
    "operational":      {"label": "Operational"},
    "asset":            {"label": "Asset"},
    "temporal":         {"label": "Temporal"},
    "governance":       {"label": "Governance"},
    "customer":         {"label": "Customer"},
    "document":         {"label": "Document"},
    "identifier":       {"label": "Identifier"},
    "CDE":              {"label": "Critical Data Element"},
    "maskable":         {"label": "Maskable"},
    "record":           {"label": "Record (table-level)"},
    "table-level":      {"label": "Table-level term"},
}

# --- GENERIC baseline: common terms (canonical name -> aliases/sensitivity/tags) #
# Aliases let divergent names ("Customer Account Number" for "Customer ID") resolve
# to one canonical term, so instances stay mergeable and the registry stays clean.
_SEED_TERMS = {
    "Customer ID":     {"aliases": ["Customer Account Number", "Cust ID"],
                        "sensitivity": "LOW",    "tags": ["identifier", "customer"]},
    "Account Number":  {"aliases": ["Acct Number", "Account No"],
                        "sensitivity": "HIGH",   "tags": ["financial", "identifier", "PII"]},
    "Customer Name":   {"aliases": ["Full Name"],
                        "sensitivity": "MEDIUM", "tags": ["PII", "personal-data", "privacy"]},
    "Email":           {"aliases": ["Email Address", "E-mail"],
                        "sensitivity": "MEDIUM", "tags": ["PII", "contact", "privacy"]},
    "Phone":           {"aliases": ["Phone Number", "Telephone"],
                        "sensitivity": "MEDIUM", "tags": ["PII", "contact", "privacy"]},
    "Service Address": {"aliases": ["Mailing Address"],
                        "sensitivity": "MEDIUM", "tags": ["PII", "location", "privacy"]},
    "SSN":             {"aliases": ["Social Security Number"],
                        "sensitivity": "HIGH",   "tags": ["PII", "direct-identifier", "sensitive"]},
    "Amount":          {"aliases": [], "sensitivity": "MEDIUM", "tags": ["financial", "billing"]},
    "Meter Reading":   {"aliases": ["Usage Reading"], "sensitivity": "LOW", "tags": ["usage", "metering"]},
    "Date":            {"aliases": ["Timestamp"], "sensitivity": "LOW", "tags": ["temporal"]},
}

_SEED_CATEGORY_TAGS = {
    "Billing & Rates":     ["billing"],
    "Usage":               ["usage"],
    "Customer":            ["customer"],
    "Water System":        ["water-system", "operational"],
    "Water Quality":       ["water-quality"],
    "Governance":          ["governance"],
    "Records & Documents": ["document"],
}

_SEED_RULES = [
    (r"amount|charge|\bbill|cost|price|\bfee|payment|invoice|balance|\bdue\b|\bpaid|revenue|outstanding",
                                                     ["billing", "financial"]),
    (r"\btax\b",                                     ["financial", "tax"]),
    (r"rate|tier|\bplan\b|pric",                     ["billing", "rate"]),
    (r"usage|consumption|gallons|\bmeter|reading|volume|\bflow\b|cubic",
                                                     ["usage", "metering"]),
    (r"\bph\b|turbidity|chlorine|\blead\b|contaminant|quality|sample|violation|compliance|\bepa\b|hardness|nitrate",
                                                     ["water-quality", "compliance"]),
    (r"alert|status|\bflag\b|\bstate\b|\bevent\b|severity|resolved", ["operational"]),
    (r"\bdate\b|time|timestamp|\bmonth\b|\byear\b|period|billing_cycle", ["temporal"]),
    (r"system|asset|pipe|pump|valve|infrastructure|reservoir|tank", ["asset", "operational"]),
    (r"email|phone|mobile|contact", ["contact", "privacy"]),
    (r"address|street|\bcity\b|\bzip\b|postal|county|geo|lat|long|coordinate|location", ["location"]),
    (r"account|customer.?id|system.?id|meter.?id|premise", ["identifier"]),
]


def _domain_pack():
    path = os.environ.get("GLOSSARY_DOMAIN_PACK") or os.path.join(HERE, "domain_pack.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _seed():
    """Fresh dictionary from the generic baseline + domain pack (company layer)."""
    pack = _domain_pack()
    cat = {k: list(v) for k, v in _SEED_CATEGORY_TAGS.items()}
    for k, v in (pack.get("category_tags") or {}).items():
        cat[k] = list(v)
    rules = [{"pattern": r["pattern"], "tags": list(r["tags"]), "layer": "company"}
             for r in (pack.get("tag_rules") or [])]
    rules += [{"pattern": p, "tags": list(t), "layer": "generic"} for p, t in _SEED_RULES]
    tags = {k: dict(v, layer="generic") for k, v in _SEED_TAGS.items()}
    for t in (pack.get("extra_tags") or []):
        tags.setdefault(t, {"label": t, "layer": "company", "status": "approved"})
    for r in rules:
        lyr = r.get("layer", "company")
        for t in r["tags"]:
            meta = {"label": t, "layer": lyr}
            if lyr == "company":
                meta["status"] = "approved"       # a curated pack rule is pre-approved
            tags.setdefault(t, meta)
    for ts in cat.values():
        for t in ts:
            tags.setdefault(t, {"label": t, "layer": "generic"})
    terms = {n: dict(v, layer="generic") for n, v in _SEED_TERMS.items()}
    for n, v in (pack.get("terms") or {}).items():
        terms[n] = dict(v, layer="company", status="approved")
    return {"schema": SCHEMA, "domain": pack.get("domain") or "water_utility",
            "category_tags": cat, "rules": rules, "tags": tags, "terms": terms,
            "counts": {}, "term_counts": {}, "examples": {}, "sources": []}


_LOCK = threading.Lock()
_DICT = None
_COMPILED = None
_COMPILED_KEY = None


def _merge_seed(d):
    """Non-destructively re-inject the generic baseline (tags, terms, rules) so an
    edit or upgrade can never lose the protected layer or the vocabulary a rule needs."""
    seed = _seed()
    d.setdefault("schema", SCHEMA)
    d.setdefault("domain", seed["domain"])
    d.setdefault("category_tags", {})
    for k, v in seed["category_tags"].items():
        d["category_tags"].setdefault(k, v)
    d.setdefault("rules", [])
    have = {r.get("pattern") for r in d["rules"]}
    for r in seed["rules"]:
        if r["pattern"] not in have:
            d["rules"].append(r)
    d.setdefault("tags", {})
    for t, meta in seed["tags"].items():
        cur = d["tags"].get(t)
        if not cur:
            d["tags"][t] = meta                       # restore a removed generic tag
        else:
            cur["layer"] = "generic"                  # generic tags stay generic
            cur.setdefault("label", meta.get("label", t))
            if meta.get("sensitivity_floor"):
                cur["sensitivity_floor"] = meta["sensitivity_floor"]
    d.setdefault("terms", {})
    for n, meta in seed["terms"].items():
        cur = d["terms"].get(n)
        if not cur:
            d["terms"][n] = meta                      # restore a removed generic term
        else:
            cur["layer"] = "generic"
    d.setdefault("counts", {}); d.setdefault("term_counts", {})
    d.setdefault("examples", {}); d.setdefault("sources", [])
    return d


def load():
    global _DICT
    with _LOCK:
        if _DICT is not None:
            return _DICT
        try:
            with open(DICT_FILE, encoding="utf-8") as f:
                _DICT = _merge_seed(json.load(f))
        except Exception:
            _DICT = _seed()
            _save_locked()
        return _DICT


def _save_locked():
    if _DICT is None:
        return
    tmp = DICT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_DICT, f, indent=2)
    os.replace(tmp, DICT_FILE)


def save():
    with _LOCK:
        _save_locked()


def reset():
    global _DICT, _COMPILED, _COMPILED_KEY
    with _LOCK:
        _DICT = _seed()
        _COMPILED = _COMPILED_KEY = None
        _save_locked()
        return _DICT


def _guardrail(doc):
    """Validate + repair an incoming dictionary. Returns (dict, warnings). Never
    raises for a fixable issue — it repairs and warns, because a silent bad edit
    is what causes drift."""
    warnings = []
    if not isinstance(doc, dict):
        raise ValueError("dictionary must be an object")
    # sensitivity validation on tags + terms
    for t, meta in list((doc.get("tags") or {}).items()):
        if isinstance(meta, dict) and meta.get("sensitivity_floor") and meta["sensitivity_floor"] not in _SENS:
            warnings.append(f"tag '{t}': invalid sensitivity floor '{meta['sensitivity_floor']}' — cleared")
            meta.pop("sensitivity_floor", None)
    for n, meta in list((doc.get("terms") or {}).items()):
        if isinstance(meta, dict) and meta.get("sensitivity") and meta["sensitivity"] not in _SENS:
            warnings.append(f"term '{n}': invalid sensitivity '{meta['sensitivity']}' — set to LOW")
            meta["sensitivity"] = "LOW"
    # re-inject protected generic baseline (records what was restored)
    before_tags = set((doc.get("tags") or {}).keys())
    before_terms = set((doc.get("terms") or {}).keys())
    _merge_seed(doc)
    for t in sorted(set(doc["tags"]) - before_tags):
        if doc["tags"][t].get("layer") == "generic":
            warnings.append(f"restored protected generic tag '{t}' (can't be removed)")
    for n in sorted(set(doc["terms"]) - before_terms):
        if doc["terms"][n].get("layer") == "generic":
            warnings.append(f"restored protected generic term '{n}' (can't be removed)")
    # every rule tag must exist in the vocabulary (else the rule would emit a
    # tag the registry can't govern — a drift source). Auto-add as company.
    for r in doc.get("rules", []):
        try:
            re.compile(r.get("pattern", ""))
        except re.error:
            warnings.append(f"rule '{r.get('pattern')}' is not a valid regex — kept but inert")
        for t in r.get("tags", []):
            if t not in doc["tags"]:
                doc["tags"][t] = {"label": t, "layer": "company"}
                warnings.append(f"added tag '{t}' required by a rule")
    # term tags must exist too
    for n, meta in (doc.get("terms") or {}).items():
        for t in (meta or {}).get("tags", []):
            if t not in doc["tags"]:
                doc["tags"][t] = {"label": t, "layer": "company"}
                warnings.append(f"added tag '{t}' required by term '{n}'")
    # alias collisions across terms (would make resolution ambiguous → drift)
    seen = {}
    for n, meta in (doc.get("terms") or {}).items():
        for a in (meta or {}).get("aliases", []):
            key = a.strip().lower()
            if key and key in seen and seen[key] != n:
                warnings.append(f"alias '{a}' maps to both '{seen[key]}' and '{n}' — ambiguous")
            seen[key] = n
    return doc, warnings


def replace(new_dict):
    """Steward save of the whole dictionary, guard-railed. Returns warnings."""
    global _DICT, _COMPILED, _COMPILED_KEY
    doc, warnings = _guardrail(dict(new_dict or {}))
    with _LOCK:
        _DICT = doc
        _COMPILED = _COMPILED_KEY = None
        _save_locked()
    return warnings


def compiled_rules():
    global _COMPILED, _COMPILED_KEY
    d = load()
    key = id(d.get("rules")), len(d.get("rules", []))
    if _COMPILED_KEY != key:
        out = []
        for r in d.get("rules", []):
            try:
                out.append((re.compile(r["pattern"], re.I), r["tags"]))
            except re.error:
                pass
        _COMPILED = out
        _COMPILED_KEY = key
    return _COMPILED


def category_tags():
    return load().get("category_tags", {})


def vocabulary():
    return set(load().get("tags", {}).keys())


def tags_meta():
    return load().get("tags", {})


def terms_meta():
    return load().get("terms", {})


def sensitivity_floors():
    return {t: m["sensitivity_floor"] for t, m in load().get("tags", {}).items()
            if isinstance(m, dict) and m.get("sensitivity_floor")}


# alias (lowercased) -> canonical term name, for resolving divergent term names.
def alias_index():
    idx = {}
    for name, meta in load().get("terms", {}).items():
        idx[name.lower()] = name
        for a in (meta or {}).get("aliases", []):
            idx[str(a).strip().lower()] = name
    return idx


# --- steward approval gate -------------------------------------------------- #
# A company tag/term discovered by a scan enters as status "pending". Only the
# generic baseline and steward-approved company items count as GOVERNED — those
# are what flow into the Registry and the Policy Generator. Pending items are
# suggested in the grid but do not govern until a steward approves them.
def _is_governed(meta):
    m = meta or {}
    return m.get("layer") == "generic" or m.get("status") == "approved"


def governed_tags():
    return {t for t, m in load().get("tags", {}).items() if _is_governed(m)}


def governed_terms():
    return {n for n, m in load().get("terms", {}).items() if _is_governed(m)}


def pending():
    d = load()
    return {"tags": sorted(t for t, m in d.get("tags", {}).items()
                           if (m or {}).get("status") == "pending"),
            "terms": sorted(n for n, m in d.get("terms", {}).items()
                            if (m or {}).get("status") == "pending")}


def canonical_name(name):
    """If `name` matches a GOVERNED term's alias, return that canonical term name
    (so divergent scanned names collapse to one term). Returns None when the name
    is already canonical or matches nothing — so callers only rename on a real
    alias hit. Governed-only, so a pending company term's aliases don't auto-apply
    until a steward approves it."""
    if not name:
        return None
    key = str(name).strip().lower()
    d = load()
    for tname, meta in d.get("terms", {}).items():
        if not _is_governed(meta):
            continue
        if key == str(tname).lower():
            return None                      # already the canonical term
        for a in (meta or {}).get("aliases", []):
            if key == str(a).strip().lower():
                return tname
    return None


def review(kind, names, action="approve"):
    """Steward decision on pending items. kind in {'tag','term'}, action in
    {'approve','reject'}. Approve -> status 'approved' (now governs). Reject ->
    remove the company item. Generic baseline is never touched."""
    global _COMPILED, _COMPILED_KEY
    d = load()
    coll = d.get("tags" if kind == "tag" else "terms", {})
    changed = 0
    with _LOCK:
        for nm in (names or []):
            meta = coll.get(nm)
            if not meta or meta.get("layer") == "generic":
                continue
            if action == "reject":
                coll.pop(nm, None); changed += 1
            elif action == "approve" and meta.get("status") != "approved":
                meta["status"] = "approved"; changed += 1
        if changed:
            _COMPILED = _COMPILED_KEY = None
            _save_locked()
    return changed


_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_RANK_R = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}


def lift_sensitivity(sens, tags, term=None):
    """Raise (never lower) a sensitivity to the highest floor implied by its tags'
    governed sensitivity floors and its canonical term's dictionary sensitivity.
    Ordinal, so rules/dictionary can only tighten a classification."""
    d = load()
    cur = _RANK.get(str(sens or "LOW").upper(), 0)
    tm = d.get("tags", {})
    for t in (tags or []):
        f = (tm.get(t) or {}).get("sensitivity_floor")
        if f:
            cur = max(cur, _RANK.get(str(f).upper(), 0))
    if term:
        canon = alias_index().get(str(term).strip().lower())
        if canon:
            ts = (d.get("terms", {}).get(canon) or {}).get("sensitivity")
            if ts:
                cur = max(cur, _RANK.get(str(ts).upper(), 0))
    return _RANK_R[cur]


def accrete(rows, source=None, persist=True):
    """Record what a scan used: tag counts + example terms, AND company terms
    (the Term names + their sensitivity/tags), so the company layer grows from
    real data. Reviewed accretion — only rule-produced tags and scanned terms
    enter, never free text."""
    d = load()
    with _LOCK:
        tags = d.setdefault("tags", {}); counts = d.setdefault("counts", {})
        ex = d.setdefault("examples", {}); terms = d.setdefault("terms", {})
        tcounts = d.setdefault("term_counts", {})
        idx = {}
        for name, meta in terms.items():
            idx[name.lower()] = name
            for a in (meta or {}).get("aliases", []):
                idx[str(a).strip().lower()] = name
        n = 0
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            term = (r.get("Term") or "").strip()
            row_tags = [t.strip() for t in str(r.get("Suggested_Tags") or "").split(";") if t.strip()]
            for t in row_tags:
                tags.setdefault(t, {"label": t, "layer": "company", "status": "pending"})
                counts[t] = counts.get(t, 0) + 1
                lst = ex.setdefault(t, [])
                if term and term not in lst and len(lst) < 8:
                    lst.append(term)
                n += 1
            # company term (skip conceptual table-level record terms)
            if term and not (not str(r.get("Source_Column") or "").strip()
                             and re.search(r"\bRecord$", term)):
                canon = idx.get(term.lower(), term)
                tcounts[canon] = tcounts.get(canon, 0) + 1
                if canon not in terms:
                    terms[canon] = {"aliases": [], "sensitivity": r.get("Sensitivity", "LOW"),
                                    "tags": row_tags[:4], "layer": "company", "status": "pending"}
                    idx[canon.lower()] = canon
                else:
                    # raise the recorded sensitivity to the observed floor
                    cur = terms[canon]
                    if _SENS.index(str(r.get("Sensitivity", "LOW")).upper()) > \
                       _SENS.index(str(cur.get("sensitivity", "LOW")).upper()):
                        cur["sensitivity"] = str(r.get("Sensitivity")).upper()
        if source:
            srcs = d.setdefault("sources", [])
            if source not in srcs:
                srcs.append(source)
        if persist:
            _save_locked()
    return n


def _facet_norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _lev(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not la:
        return lb
    if not lb:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
        prev = cur
    return prev[lb]


def facet_health():
    """The governed-tag facet as PDC's OpenSearch will see it, plus health flags:
    empty buckets (no reviewed usage) and fragmenting near-duplicates (tags that
    normalize to the same key, or are one edit apart) — the drift-in-waiting."""
    d = load()
    tags = d.get("tags", {})
    counts = d.get("counts", {})
    gov = [(t, m) for t, m in tags.items() if _is_governed(m)]
    facet = sorted(({"tag": t, "count": counts.get(t, 0),
                     "sensitivity_floor": (m or {}).get("sensitivity_floor")} for t, m in gov),
                   key=lambda x: -x["count"])
    empty = [x["tag"] for x in facet if x["count"] == 0]
    names = [t for t, _ in gov]
    groups = {}
    for t in names:
        groups.setdefault(_facet_norm(t), []).append(t)
    frag = [g for g in groups.values() if len(g) > 1]
    seen = set()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = _facet_norm(names[i]), _facet_norm(names[j])
            if a == b:
                continue
            if abs(len(a) - len(b)) <= 1 and min(len(a), len(b)) >= 4 and _lev(a, b) == 1:
                key = tuple(sorted((names[i], names[j])))
                if key not in seen:
                    seen.add(key)
                    frag.append(list(key))
    return {"facet": facet, "empty_governed_tags": empty, "fragmenting": frag}


def summary():
    d = load()
    counts = d.get("counts", {}); tcounts = d.get("term_counts", {})
    tags = []
    for t, meta in sorted(d.get("tags", {}).items()):
        meta = meta or {}
        tags.append({"tag": t, "label": meta.get("label", t), "layer": meta.get("layer", "company"),
                     "status": ("generic" if meta.get("layer") == "generic" else meta.get("status", "approved")),
                     "sensitivity_floor": meta.get("sensitivity_floor"),
                     "count": counts.get(t, 0), "examples": d.get("examples", {}).get(t, [])})
    terms = []
    for n, meta in sorted(d.get("terms", {}).items()):
        meta = meta or {}
        terms.append({"term": n, "aliases": meta.get("aliases", []), "layer": meta.get("layer", "company"),
                      "status": ("generic" if meta.get("layer") == "generic" else meta.get("status", "approved")),
                      "sensitivity": meta.get("sensitivity", "LOW"), "tags": meta.get("tags", []),
                      "count": tcounts.get(n, 0)})
    pend = pending()
    return {"schema": d.get("schema", SCHEMA), "domain": d.get("domain"),
            "sources": d.get("sources", []),
            "tag_count": len(tags), "rule_count": len(d.get("rules", [])), "term_count": len(terms),
            "generic_tags": sum(1 for t in tags if t["layer"] == "generic"),
            "generic_terms": sum(1 for t in terms if t["layer"] == "generic"),
            "pending_tags": len(pend["tags"]), "pending_terms": len(pend["terms"]),
            "governed_tags": len(governed_tags()), "governed_terms": len(governed_terms()),
            "tags": tags, "terms": terms, "rules": d.get("rules", []),
            "category_tags": d.get("category_tags", {})}
