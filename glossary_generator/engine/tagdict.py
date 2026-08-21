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

from core import paths

HERE = paths.APP_DIR
DICT_FILE = paths.state_path("tag_dictionary.json", "GLOSSARY_TAG_DICTIONARY")
SCHEMA = "term-tag-dictionary/1"
_SENS = ("LOW", "MEDIUM", "HIGH")


def norm_tag(t):
    """Canonical tag form: trimmed, lower-case. Tags are facet keys in PDC's
    OpenSearch — 'PII' and 'pii' would fragment into two buckets — so the whole
    pipeline (rules, packs, scans, LLM proposals, registry) standardises on
    lower-case. Labels keep their display casing; only the tag key is folded."""
    return str(t or "").strip().lower()


def _norm_tag_list(ts):
    out, seen = [], set()
    for t in (ts or []):
        k = norm_tag(t)
        if k and k not in seen:
            seen.add(k); out.append(k)
    return out


def _normalize_doc(d):
    """Fold every tag key/reference in a dictionary document to lower-case,
    merging case-variant duplicates (usage sets unioned, floors tightened,
    examples unioned). Runs at seed/load/save time so pre-1.8.1 dictionaries
    with 'PII' or 'CDE' heal in place — no reseed needed."""
    tags = d.get("tags") or {}
    merged = {}
    for t, meta in tags.items():
        k = norm_tag(t)
        if not k:
            continue
        meta = dict(meta or {})
        meta.setdefault("label", str(meta.get("label") or t))
        cur = merged.get(k)
        if not cur:
            merged[k] = meta
            continue
        # case-variant duplicate: generic layer and approved status win,
        # sensitivity floors tighten
        if meta.get("layer") == "generic":
            cur["layer"] = "generic"
        if meta.get("status") == "approved" and cur.get("status") != "approved":
            cur["status"] = "approved"
        f_new, f_cur = meta.get("sensitivity_floor"), cur.get("sensitivity_floor")
        if f_new and (not f_cur or _SENS.index(f_new) > _SENS.index(f_cur)):
            cur["sensitivity_floor"] = f_new
    d["tags"] = merged
    if isinstance(d.get("usage"), dict):
        folded = {}
        for t, lst in d["usage"].items():
            k = norm_tag(t)
            if not k:
                continue
            dst = folded.setdefault(k, [])
            for e in (lst or []):
                e = str(e).strip().lower()
                if e and e not in dst:
                    dst.append(e)
        d["usage"] = {t: sorted(v) for t, v in folded.items()}
    ex = {}
    for t, lst in (d.get("examples") or {}).items():
        k = norm_tag(t)
        if not k:
            continue
        dst = ex.setdefault(k, [])
        for e in (lst or []):
            if e not in dst and len(dst) < 8:
                dst.append(e)
    d["examples"] = ex
    for r in d.get("rules") or []:
        if isinstance(r, dict):
            r["tags"] = _norm_tag_list(r.get("tags"))
    d["category_tags"] = {c: _norm_tag_list(ts)
                          for c, ts in (d.get("category_tags") or {}).items()}
    for meta in (d.get("terms") or {}).values():
        if isinstance(meta, dict) and meta.get("tags"):
            meta["tags"] = _norm_tag_list(meta["tags"])
    return d

# --- GENERIC baseline: tags (with common sensitivity floor) ----------------- #
# GENERIC = governance vocabulary, not industry vocabulary.
#
# billing / rate / revenue / usage / metering / asset were removed in
# 1.33: they are the water-utility scenario leaking into the engine, the
# same fault the category keywords had before 1.29. A credit union has no
# use for "Metering", and offering it as governed vocabulary implies
# somebody chose it. A domain pack supplies whatever a company actually
# needs; extra_tags puts it straight into the allow-list.
# The load-bearing CORE of the baseline — the six tags engine code paths
# stand on (guard_pii_row reads pii; the drafter's structural-skip set reads
# maskable/identifier/record/table-level; the CDE flag flows through cde).
# These stay unretirable with a WHY the UI can show; every other generic
# tag/term is retirable with the same durable tombstone as company items
# ("cant retire generic tags" — the silent refusal was the real bug).
_CORE_TAGS = {"pii", "maskable", "identifier", "cde", "record", "table-level"}

_SEED_TAGS = {
    "pii":              {"label": "PII", "sensitivity_floor": "HIGH"},
    "personal-data":    {"label": "Personal data", "sensitivity_floor": "HIGH"},
    "direct-identifier":{"label": "Direct identifier", "sensitivity_floor": "HIGH"},
    "privacy":          {"label": "Privacy", "sensitivity_floor": "MEDIUM"},
    "contact":          {"label": "Contact info", "sensitivity_floor": "MEDIUM"},
    "location":         {"label": "Location", "sensitivity_floor": "MEDIUM"},
    "financial":        {"label": "Financial", "sensitivity_floor": "MEDIUM"},
    "sensitive":        {"label": "Sensitive", "sensitivity_floor": "MEDIUM"},
    "tax":              {"label": "Tax"},
    "compliance":       {"label": "Regulatory compliance"},
    "operational":      {"label": "Operational"},
    "temporal":         {"label": "Temporal"},
    "governance":       {"label": "Governance"},
    "customer":         {"label": "Customer"},
    "document":         {"label": "Document"},
    "identifier":       {"label": "Identifier"},
    "cde":              {"label": "Critical Data Element"},
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
                        "sensitivity": "HIGH",   "tags": ["financial", "identifier", "pii"]},
    "Customer Name":   {"aliases": ["Full Name"],
                        "sensitivity": "MEDIUM", "tags": ["pii", "personal-data", "privacy"]},
    "Email":           {"aliases": ["Email Address", "E-mail"],
                        "sensitivity": "MEDIUM", "tags": ["pii", "contact", "privacy"]},
    "Phone":           {"aliases": ["Phone Number", "Telephone"],
                        "sensitivity": "MEDIUM", "tags": ["pii", "contact", "privacy"]},
    # "Service Address" is a utility's word for it; the aliases keep a pack
    # that uses one resolving to this canonical term.
    "Address":         {"aliases": ["Mailing Address", "Service Address"],
                        "sensitivity": "MEDIUM", "tags": ["pii", "location", "privacy"]},
    "SSN":             {"aliases": ["Social Security Number"],
                        "sensitivity": "HIGH",   "tags": ["pii", "direct-identifier", "sensitive"]},
    "Amount":          {"aliases": [], "sensitivity": "MEDIUM", "tags": ["financial"]},
    "Date":            {"aliases": ["Timestamp"], "sensitivity": "LOW", "tags": ["temporal"]},
}

# The bucket harvested DOCUMENTS land in - the one category name the engine
# still needs, because it CREATES those rows itself (suggester.document_rows)
# and a row must carry a category. It is a content-type label for unstructured
# content, not a domain taxonomy, which is why it survived the 1.29 removal of
# the 14 builtin categories.
#
# Set "document_category" in a domain pack to rename it; the fallback below
# applies only when no pack says otherwise. Read through a function rather than
# frozen at import so a pack installed later still wins.
_DOCUMENT_CATEGORY_FALLBACK = "Records & Documents"


def document_category():
    """Category for harvested documents: the pack's, else the fallback."""
    return (_domain_pack().get("document_category")
            or _DOCUMENT_CATEGORY_FALLBACK)

# Rules follow the same line as the tags above: a pattern is generic only if
# it means the same thing in any estate. The rate/tier, usage/metering and
# asset/equipment rules went with their tags in 1.33.
_SEED_RULES = [
    (r"amount|charge|\bbill|cost|price|\bfee|payment|invoice|balance|\bdue\b|\bpaid|revenue|outstanding",
                                                     ["financial"]),
    (r"\btax\b",                                     ["financial", "tax"]),
    (r"violation|compliance|regulat|audit", ["compliance"]),
    (r"alert|status|\bflag\b|\bstate\b|\bevent\b|severity|resolved", ["operational"]),
    (r"\bdate\b|time|timestamp|\bmonth\b|\byear\b|period|billing_cycle", ["temporal"]),
    (r"email|phone|mobile|contact", ["contact", "privacy"]),
    (r"address|street|\bcity\b|\bzip\b|postal|county|geo|lat|long|coordinate|location", ["location"]),
    (r"account|customer.?id|system.?id", ["identifier"]),
]


def _domain_pack():
    path = paths.domain_pack_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _seed():
    """Fresh dictionary from the generic baseline + domain pack (company layer)."""
    pack = _domain_pack()
    # The only category->tag seed the engine supplies, for the only category it
    # creates. Everything else is the pack's (see suggester.CAT_KEYWORDS).
    # Without it the document harvest still runs, but its rows fall back to the
    # ungoverned slug "records-documents" instead of the governed "document" tag.
    cat = {document_category(): ["document"]}
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
    return _normalize_doc(
        {"schema": SCHEMA, "domain": pack.get("domain") or "generic",
         "category_tags": cat, "rules": rules, "tags": tags, "terms": terms,
         "usage": {}, "term_usage": {}, "examples": {}, "sources": []})


# synthetic names PDC/profilers invent for headerless CSV columns — scan noise,
# never vocabulary. Blocked at accretion and healed out of pending on load.
_JUNK_TERM = re.compile(r"^(column|field|col|unnamed)[-_ ]?\d+$", re.I)


def _term_index(d):
    """lowercased name/alias -> canonical term name, over a specific document."""
    idx = {}
    for name, meta in (d.get("terms") or {}).items():
        idx[str(name).lower()] = name
        for a in (meta or {}).get("aliases", []):
            idx[str(a).strip().lower()] = name
    return idx


def _remap_usage(d, drop=()):
    """Keep the idempotent usage stores keyed to CURRENT term identities:
    fold keys that became an alias onto their canonical term, drop keys in
    `drop` (terms a steward explicitly removed), and keep unknown keys as-is
    (e.g. table-level Record terms, which carry tags in scans but never enter
    the dictionary). Lists stay sorted + de-duplicated so serialization is
    stable and counts stay len()-able."""
    dropped = {str(x).strip().lower() for x in (drop or ())}
    idx = _term_index(d)
    usage = d.get("usage") if isinstance(d.get("usage"), dict) else {}
    for t, lst in list(usage.items()):
        out = []
        for k in (lst or []):
            kk = str(k).strip().lower()
            if not kk or kk in dropped:
                continue
            canon = idx.get(kk)
            if canon:
                kk = str(canon).strip().lower()
            if kk not in out:
                out.append(kk)
        usage[t] = sorted(out)
    d["usage"] = usage
    tu = {}
    for n, lst in (d.get("term_usage") or {}).items():
        key = str(n).strip().lower()
        if key in dropped:
            continue
        canon = idx.get(key) or n
        dst = tu.setdefault(canon, [])
        for k in (lst or []):
            if k and k not in dst:
                dst.append(k)
        dst.sort()
    d["term_usage"] = tu

_LOCK = threading.Lock()
_DICT = None
_COMPILED = None
_COMPILED_KEY = None


def _merge_seed(d):
    """Non-destructively re-inject the generic baseline (tags, terms, rules) so an
    edit or upgrade can never lose the protected layer or the vocabulary a rule needs."""
    seed = _seed()
    d.setdefault("tags", {}); d.setdefault("terms", {})
    _normalize_doc(d)                    # heal pre-1.8.1 mixed-case tag keys
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
    d.setdefault("retired", {"tags": [], "terms": []})
    d["retired"].setdefault("tags", []); d["retired"].setdefault("terms", [])
    _rt_tags = set(d["retired"]["tags"]); _rt_terms = set(d["retired"]["terms"])
    d.setdefault("tags", {})
    for t, meta in seed["tags"].items():
        cur = d["tags"].get(t)
        if not cur:
            # a steward tombstone holds for generic and company seeds alike —
            # only the load-bearing core always comes back
            if t in _rt_tags and t not in _CORE_TAGS:
                continue                              # steward retired it — stays retired
            d["tags"][t] = meta                       # restore a removed seed tag
        elif meta.get("layer") == "generic":
            cur["layer"] = "generic"                  # generic BASELINE tags stay generic
            cur.setdefault("label", meta.get("label", t))
            if meta.get("sensitivity_floor"):
                cur["sensitivity_floor"] = meta["sensitivity_floor"]
        else:
            # pack-seeded tag: curated company vocabulary, pre-approved — heal any
            # copy a previous merge mislabeled generic so steward actions reach it
            cur["layer"] = "company"
            cur.setdefault("status", "approved")
            cur.setdefault("label", meta.get("label", t))
    d.setdefault("terms", {})
    for n, meta in seed["terms"].items():
        cur = d["terms"].get(n)
        if not cur:
            if n in _rt_terms:
                continue                              # steward retired it — stays retired
            d["terms"][n] = meta                      # restore a removed seed term
        elif meta.get("layer") == "generic":
            cur["layer"] = "generic"                  # generic BASELINE terms stay generic
        else:
            # pack-seeded term: company layer, pre-approved (heals the historic
            # bug where every pack term was force-relabeled generic on load)
            cur["layer"] = "company"
            cur.setdefault("status", "approved")
    # usage stores are keyed by TERM IDENTITY (sets serialized as sorted
    # lists), so rescanning the same source is idempotent. Pre-1.9.x
    # dictionaries carried bare numeric counters accreted on every scan pass —
    # rescans double-counted, so those ints have unknown provenance: rebuild
    # the sets from scan-grown term evidence instead (terms that entered via a
    # scan carry `sources`; seeded baseline/pack terms don't count as usage)
    # and drop the legacy counter keys. The next scan tops the sets up exactly.
    if not isinstance(d.get("usage"), dict):
        u = {}
        for name, meta in (d.get("terms") or {}).items():
            m = meta or {}
            if not m.get("sources"):
                continue                       # seeded, not scan-observed
            key = str(name).strip().lower()
            for t in (m.get("tags") or []):
                lst = u.setdefault(norm_tag(t), [])
                if key not in lst:
                    lst.append(key)
        d["usage"] = {t: sorted(v) for t, v in u.items()}
    if not isinstance(d.get("term_usage"), dict):
        d["term_usage"] = {n: sorted({s for s in (m or {}).get("sources") or [] if s})
                           for n, m in (d.get("terms") or {}).items()
                           if (m or {}).get("sources")}
    d.pop("counts", None); d.pop("term_counts", None)
    d.setdefault("examples", {}); d.setdefault("sources", [])
    junk = [n for n, m in list(d.get("terms", {}).items())
            if isinstance(m, dict) and m.get("status") == "pending"
            and m.get("layer") != "generic" and _JUNK_TERM.match(str(n).strip())]
    for nm in junk:
        d["terms"].pop(nm, None)
    _remap_usage(d, drop=junk)
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
    # self-healing: recreate the state directory if it vanished under a
    # running server (same field case as api._write_json)
    os.makedirs(os.path.dirname(os.path.abspath(DICT_FILE)) or ".", exist_ok=True)
    tmp = DICT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_DICT, f, indent=2)
    os.replace(tmp, DICT_FILE)


def save():
    with _LOCK:
        _save_locked()


def reset(preserve_approved=True):
    """Reseed from the generic baseline + domain pack. Honors the governed-
    vocabulary contract (courseware: "discards un-approved scan-grown additions;
    approved/steward items are the governed set"): steward-APPROVED company tags
    and terms, and company-layer rules, are PRESERVED; pending scan-grown items
    are discarded and the baseline/pack refreshes. A timestamped backup of the
    previous dictionary file is written first, so a reseed is never destructive
    beyond recovery. preserve_approved=False gives the old scorched-earth wipe.
    Returns {"kept": {"tags": n, "terms": n, "rules": n}, "backup": path|None}."""
    global _DICT, _COMPILED, _COMPILED_KEY
    with _LOCK:
        prev = _DICT
        if prev is None:
            try:
                with open(DICT_FILE, encoding="utf-8") as f:
                    prev = json.load(f)
            except Exception:
                prev = None
        backup = None
        try:
            if os.path.exists(DICT_FILE):
                import time as _t, shutil as _sh
                backup = DICT_FILE + ".backup-" + _t.strftime("%Y%m%d-%H%M%S")
                _sh.copy2(DICT_FILE, backup)
        except Exception:
            backup = None
        _DICT = _seed()
        kept = {"tags": 0, "terms": 0, "rules": 0}
        if preserve_approved and isinstance(prev, dict):
            # steward retire-tombstones survive the reseed: the retired pack
            # entries are dropped from the fresh seed instead of resurrecting
            ret = prev.get("retired") or {}
            _DICT["retired"] = {"tags": list(ret.get("tags") or []),
                                "terms": list(ret.get("terms") or [])}
            for kind in ("tags", "terms"):
                for nm in _DICT["retired"][kind]:
                    # tombstones hold across the reseed for generic and
                    # company entries alike — only the load-bearing core
                    # tags always return
                    if kind == "tags" and nm in _CORE_TAGS:
                        continue
                    _DICT[kind].pop(nm, None)
            for kind in ("tags", "terms"):
                for nm, meta in (prev.get(kind) or {}).items():
                    m = meta or {}
                    if (m.get("layer") == "company" and m.get("status") == "approved"
                            and nm not in (_DICT.get(kind) or {})):
                        _DICT.setdefault(kind, {})[nm] = m
                        kept["tags" if kind == "tags" else "terms"] += 1
            seeded = {(r.get("pattern"), tuple(r.get("tags") or []))
                      for r in _DICT.get("rules", []) if isinstance(r, dict)}
            for r in (prev.get("rules") or []):
                if (isinstance(r, dict) and r.get("layer") == "company"
                        and (r.get("pattern"), tuple(r.get("tags") or [])) not in seeded):
                    _DICT.setdefault("rules", []).append(r)
                    kept["rules"] += 1
        _COMPILED = _COMPILED_KEY = None
        _save_locked()
        return {"kept": kept, "backup": backup}


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
            warnings.append(f"restored core generic tag '{t}' (load-bearing — can't be removed)"
                            if t in _CORE_TAGS else
                            f"restored missing generic tag '{t}' (retire it on the Dictionary page if unwanted)")
    for n in sorted(set(doc["terms"]) - before_terms):
        if doc["terms"][n].get("layer") == "generic":
            warnings.append(f"restored missing generic term '{n}' (retire it on the Dictionary page if unwanted)")
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
        prev = _DICT if _DICT is not None else None
        if prev is None:
            try:
                with open(DICT_FILE, encoding="utf-8") as f:
                    prev = json.load(f)
            except Exception:
                prev = {}
        prev = prev or {}
        if "retired" not in doc:
            # the UI's save payload doesn't carry tombstones — keep the
            # current ones, or a Save would resurrect retired pack entries
            doc["retired"] = dict(prev.get("retired")
                                  or {"tags": [], "terms": []})
        # the save payload doesn't carry the accretion state either — keep
        # it, or a Save would zero the facet preview and reset the
        # grown-from-a-scan gate. Usage keys of terms the save REMOVED are
        # dropped, so counts stay "distinct CURRENT terms carrying the tag".
        for key in ("usage", "term_usage", "examples"):
            if not doc.get(key):
                doc[key] = {k: list(v or []) for k, v in (prev.get(key) or {}).items()}
        if not doc.get("sources"):
            doc["sources"] = list(prev.get("sources") or [])
        removed = ({str(n).strip().lower() for n in (prev.get("terms") or {})}
                   - set(_term_index(doc).keys()))
        _remap_usage(doc, drop=removed)
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
    return _term_index(load())


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


def review(kind, names, action="approve", target=None):
    """Steward decision on pending items. kind in {'tag','term'}, action in
    {'approve','reject','alias'}. Approve -> status 'approved' (now governs).
    Reject -> remove the company item. Alias (terms only) -> the pending name
    becomes an ALIAS of the governed `target` term and the pending entry is
    removed - the duplicate folds into the canonical concept. Generic baseline
    is never touched."""
    global _COMPILED, _COMPILED_KEY
    d = load()
    coll = d.get("tags" if kind == "tag" else "terms", {})
    changed = 0
    dropped_terms = []
    with _LOCK:
        for nm in (names or []):
            meta = coll.get(nm)
            if not meta:
                continue
            if meta.get("layer") == "generic":
                # generic entries are retirable like company ones (durable
                # tombstone) — EXCEPT the load-bearing core, and only the
                # reject action makes sense on an already-governed layer
                if action != "reject" or (kind == "tag" and nm in _CORE_TAGS):
                    continue
            if action == "alias" and kind == "term":
                # resolve the target case-insensitively — an exact-key miss
                # used to silently no-op while the UI reported success, which
                # is the worst possible outcome for a durable operation
                tname = str(target or "")
                if tname and tname not in d.get("terms", {}):
                    low = {k.lower(): k for k in d.get("terms", {})}
                    tname = low.get(tname.lower(), tname)
                tgt = d.get("terms", {}).get(tname)
                if not tgt or nm == tname:
                    continue
                als = tgt.setdefault("aliases", [])
                if nm not in als:
                    als.append(nm)
                coll.pop(nm, None)
                # folding a pack-seeded twin must stick: tombstone the folded
                # name so the load-merge doesn't restore it as its own term
                rt = d.setdefault("retired", {}).setdefault("terms", [])
                if nm not in rt:
                    rt.append(nm)
                changed += 1
            elif action == "reject":
                coll.pop(nm, None)
                # retired items leave the usage stores too, so facet counts
                # stay "distinct CURRENT terms carrying the tag"
                if kind == "tag":
                    (d.get("usage") or {}).pop(nm, None)
                    # a retired tag disappears EVERYWHERE: term entries keep
                    # their own tags lists, so without this the allow-list
                    # forgot the tag while every term still displayed it (the
                    # "uncategorized on everything" case, field-caught)
                    for tmeta in (d.get("terms") or {}).values():
                        if isinstance(tmeta, dict) and nm in (tmeta.get("tags") or []):
                            tmeta["tags"] = [t for t in tmeta["tags"] if t != nm]
                    # rules that emit the retired tag lose it, and a rule with
                    # no tags left is dropped — the rules-reference-governed-
                    # tags invariant holds for seed and company rules alike
                    rules = d.get("rules") or []
                    for ru in rules:
                        if isinstance(ru, dict) and nm in (ru.get("tags") or []):
                            ru["tags"] = [t for t in ru["tags"] if t != nm]
                    d["rules"] = [ru for ru in rules
                                  if not isinstance(ru, dict) or ru.get("tags")]
                else:
                    dropped_terms.append(nm)
                # tombstone: an explicit steward retire is DURABLE — the load-
                # merge and Reseed skip re-seeding this name from the pack. A
                # future scan may still re-propose it as pending (evidence
                # wins), and approving it then lifts the tombstone.
                rl = d.setdefault("retired", {}).setdefault(
                    "tags" if kind == "tag" else "terms", [])
                if nm not in rl:
                    rl.append(nm)
                changed += 1
            elif action == "approve" and meta.get("status") != "approved":
                meta["status"] = "approved"
                rl = (d.get("retired") or {}).get("tags" if kind == "tag" else "terms")
                if rl and nm in rl:
                    rl.remove(nm)                     # re-approval lifts the tombstone
                changed += 1
        if changed:
            # re-key the usage sets: folded names follow their canonical term
            # (the alias index now resolves them), rejected terms drop out
            _remap_usage(d, drop=dropped_terms)
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
    """Record what a scan used — IDEMPOTENTLY. Per-tag usage is a set of term
    identities (the distinct terms observed carrying the tag; per-term usage a
    set of source columns), not a running counter, so rescanning the same
    source never inflates the Search facet preview. Also records example terms
    AND company terms (the Term names + their sensitivity/tags), so the company
    layer grows from real data. Reviewed accretion — only rule-produced tags
    and scanned terms enter, never free text."""
    d = load()
    with _LOCK:
        tags = d.setdefault("tags", {}); usage = d.setdefault("usage", {})
        ex = d.setdefault("examples", {}); terms = d.setdefault("terms", {})
        tusage = d.setdefault("term_usage", {})
        idx = _term_index(d)
        n = 0
        for r in rows or []:
            if not isinstance(r, dict):
                continue
            # Auto-pruned structural keys (Prune_Reason, arriving unkept) never
            # enter the pending queue: the scan itself already answered them —
            # a surrogate PK/FK id is not vocabulary, and its tags shouldn't
            # seed the allow-list either. Entries absorbed before this guard
            # existed are retro-retired by refresh_pending.
            if (str(r.get("Prune_Reason") or "").strip()
                    and str(r.get("Keep", "Y")).strip().lower() in ("n", "no", "false", "0")):
                continue
            term = (r.get("Term") or "").strip()
            row_tags = _norm_tag_list(str(r.get("Suggested_Tags") or "").split(";"))
            # a durably retired tag never rides back in on a row: the steward's
            # tombstone beats the scan's stale Suggested_Tags string
            retired_t = set((d.get("retired") or {}).get("tags") or [])
            if retired_t:
                row_tags = [t for t in row_tags if t not in retired_t]
            canon = idx.get(term.lower(), term) if term else ""
            # term identity for the usage sets: canonical, junk excluded
            tkey = str(canon).strip().lower() if (term and not _JUNK_TERM.match(term)) else ""
            for t in row_tags:
                tags.setdefault(t, {"label": t, "layer": "company", "status": "pending"})
                if tkey:
                    lst = usage.setdefault(t, [])
                    if tkey not in lst:
                        lst.append(tkey)
                        lst.sort()
                lst = ex.setdefault(t, [])
                if term and term not in lst and len(lst) < 8:
                    lst.append(term)
                n += 1
            # company term (skip conceptual table-level record terms and the
            # synthetic Column-N names headerless CSVs produce)
            if term and not _JUNK_TERM.match(term) and not (
                    not str(r.get("Source_Column") or "").strip()
                    and re.search(r"\bRecord$", term)):
                srcs = [c.strip() for c in str(r.get("Source_Column") or "").split(";") if c.strip()]
                seen = tusage.setdefault(canon, [])
                for c in (srcs or ([source] if source else [])):
                    if c not in seen:
                        seen.append(c)
                seen.sort()
                if canon not in terms:
                    # the induced value pattern travels with the entry: for
                    # *_id candidates it is THE discriminator between a quoted
                    # business identifier (coded format) and a surrogate key
                    # (bare integer, no pattern) - the steward and the advisor
                    # both need it at the decision point
                    terms[canon] = {"aliases": [], "sensitivity": r.get("Sensitivity", "LOW"),
                                    "tags": row_tags[:4], "layer": "company", "status": "pending",
                                    "category": (r.get("Category") or "").strip(),
                                    "definition": str(r.get("Definition") or "").strip()[:200],
                                    "confidence": (r.get("Confidence") or "").strip(),
                                    "pattern": (r.get("Value_Pattern") or "").strip(),
                                    "sources": srcs[:3]}
                    idx[canon.lower()] = canon
                else:
                    # raise the recorded sensitivity to the observed floor and
                    # top up the steward context from later sightings
                    cur = terms[canon]
                    if _SENS.index(str(r.get("Sensitivity", "LOW")).upper()) > _SENS.index(str(cur.get("sensitivity", "LOW")).upper()):
                        cur["sensitivity"] = str(r.get("Sensitivity")).upper()
                    if not cur.get("category"):
                        cur["category"] = (r.get("Category") or "").strip()
                    if not cur.get("definition"):
                        cur["definition"] = str(r.get("Definition") or "").strip()[:200]
                    if not cur.get("confidence"):
                        cur["confidence"] = (r.get("Confidence") or "").strip()
                    if not cur.get("pattern") and (r.get("Value_Pattern") or "").strip():
                        cur["pattern"] = (r.get("Value_Pattern") or "").strip()
                    have = cur.setdefault("sources", [])
                    for c in srcs:
                        if c not in have and len(have) < 5:
                            have.append(c)
        if source:
            srcs = d.setdefault("sources", [])
            if source not in srcs:
                srcs.append(source)
        if persist:
            _save_locked()
    return n


def refresh_pending(rows, persist=True):
    """Carry ACCEPTED Review-grid improvements (LLM enrich/QA proposals the
    steward accepted, or manual grid edits) forward into the PENDING company
    terms, so the Dictionary's steward queue shows the enriched version
    instead of the raw scan capture. Called from the glossary save, so only
    applied changes ever flow — proposals the steward didn't accept never
    reach the dictionary, and approved/governed/generic entries are NEVER
    touched (the approval gate stays with the steward).

    Matching: by name or alias first. A row whose (possibly QA-corrected)
    name matches nothing is matched by source-column overlap against the
    pending entries; the pending entry is then renamed to the corrected name
    with the raw scan name kept as an alias — so the next scan folds into
    the corrected term instead of re-proposing the misread (the 'Phone
    Level' → 'pH Level' case). If the corrected name already belongs to
    ANOTHER entry, the stale pending duplicate folds into it as an alias.
    Returns the number of pending entries updated/folded."""
    global _COMPILED, _COMPILED_KEY
    d = load()
    changed = 0
    auto_retired = []
    with _LOCK:
        terms = d.setdefault("terms", {})
        tusage = d.setdefault("term_usage", {})
        idx = _term_index(d)

        def is_pending(name):
            m = terms.get(name) or {}
            return m.get("layer") != "generic" and m.get("status", "approved") == "pending"

        # source column -> pending entry name, for rename detection
        by_src = {}
        for name in terms:
            if not is_pending(name):
                continue
            for s in (terms[name] or {}).get("sources") or []:
                by_src.setdefault(str(s).strip().lower(), name)

        def apply_row(meta, r):
            hit = 0
            definition = str(r.get("Definition") or "").strip()[:200]
            if definition and definition != meta.get("definition"):
                meta["definition"] = definition; hit = 1
            category = (r.get("Category") or "").strip()
            if category and category != meta.get("category"):
                meta["category"] = category; hit = 1
            # A pattern is EVIDENCE, not prose: the pending entry is a
            # projection of the row, so a row that no longer induces a shape
            # must not leave the term asserting one. Guarding this on
            # `pattern and` the way definition and category are guarded was
            # the same silent-staleness bug rowmerge.js carried: the repaired
            # AWC columns came back as enums with no shape, and eight pending
            # terms kept ^[A-Z]{2}[0-9]{4}$ — a pattern matching zero rows,
            # one Approve away from entering the governed vocabulary and
            # seeding a method that could never fire. Definition and category
            # stay fill-only above: those are steward prose, and a blank there
            # means "nothing new to say", not "it is gone".
            pattern = (r.get("Value_Pattern") or "").strip()
            if pattern != (meta.get("pattern") or ""):
                if pattern:
                    meta["pattern"] = pattern
                else:
                    meta.pop("pattern", None)
                hit = 1
            return hit

        for r in rows or []:
            if not isinstance(r, dict):
                continue
            term = (r.get("Term") or "").strip()
            if not term or _JUNK_TERM.match(term):
                continue
            # Retro-retire: an auto-pruned key (Prune_Reason, unkept) was
            # answered by the scan itself — asking the steward AGAIN in the
            # pending queue is double work, so its pending entry retires the
            # way a steward click would (popped + tombstoned; accrete no
            # longer absorbs them). Rows the steward merely unticked WITHOUT
            # a Prune_Reason are deliberately left alone: dropped from one
            # glossary is not retired from the company vocabulary.
            if (str(r.get("Prune_Reason") or "").strip()
                    and str(r.get("Keep", "Y")).strip().lower() in ("n", "no", "false", "0")):
                nm = idx.get(term.lower())
                if nm and is_pending(nm) and nm.lower() == term.lower():
                    terms.pop(nm, None)
                    auto_retired.append(nm)
                    rl = d.setdefault("retired", {}).setdefault("terms", [])
                    if nm not in rl:
                        rl.append(nm)
                    changed += 1
                continue
            srcs = [c.strip().lower() for c in str(r.get("Source_Column") or "").split(";") if c.strip()]
            canon = idx.get(term.lower())
            if canon is not None:
                if is_pending(canon):
                    changed += apply_row(terms[canon], r)
                    # A CASE-ONLY correction ("Ph Level" → "pH Level") lands
                    # HERE, not on the rename path below: the case-folded
                    # index matches, content refreshes, and the stored name
                    # kept the scan's casing forever. When the row's term IS
                    # this entry's own name modulo case (never an alias hit),
                    # adopt the steward's casing and keep the old spelling as
                    # an alias so rescans fold instead of re-proposing.
                    if term != canon and term.lower() == canon.lower():
                        meta = terms.pop(canon)
                        aliases = meta.setdefault("aliases", [])
                        if canon not in aliases:
                            aliases.append(canon)
                        terms[term] = meta
                        if canon in tusage:
                            tusage[term] = sorted(set(tusage.pop(canon)) | set(tusage.get(term) or []))
                        idx[term.lower()] = term
                        for s in list(by_src):
                            if by_src[s] == canon:
                                by_src[s] = term
                        canon = term
                        changed += 1
                # a stale pending twin of this entry (same source, old scan
                # misread) folds in as an alias instead of lingering pending
                stale = next((by_src[s] for s in srcs
                              if s in by_src and by_src[s] != canon), None)
                if stale and is_pending(stale):
                    meta = terms.pop(stale)
                    aliases = terms[canon].setdefault("aliases", [])
                    if stale not in aliases:
                        aliases.append(stale)
                    if stale in tusage:
                        tusage[canon] = sorted(set(tusage.pop(stale)) | set(tusage.get(canon) or []))
                    idx[stale.lower()] = canon
                    for s in list(by_src):
                        if by_src[s] == stale:
                            del by_src[s]
                    changed += 1
                continue
            # unknown name — a rename. Find the pending entry it came from.
            old = next((by_src[s] for s in srcs if s in by_src), None)
            if not old:
                continue
            meta = terms.pop(old)
            aliases = meta.setdefault("aliases", [])
            if old not in aliases:
                aliases.append(old)
            terms[term] = meta
            apply_row(meta, r)
            if old in tusage:
                merged = sorted(set(tusage.pop(old)) | set(tusage.get(term) or []))
                tusage[term] = merged
            idx[term.lower()] = term
            idx[old.lower()] = term
            for s in list(by_src):
                if by_src[s] == old:
                    by_src[s] = term
            changed += 1
        if auto_retired:
            _remap_usage(d, drop=auto_retired)
            _COMPILED = _COMPILED_KEY = None
        if changed and persist:
            _save_locked()
    return changed


def stale_pending(*, sources, terms, tags):
    """PENDING entries with no current evidence anywhere: their sources, name
    and aliases match nothing in the given row universe (built from every
    SAVED glossary, not just the loaded one — cross-domain vocabulary stays
    safe). These are fossils from scans whose rows are gone: refresh_pending
    can only carry improvements from rows that exist, so nothing can ever fix
    them, and they sit in the steward's queue as arbitrary debris (the "Flow /
    category Uncategorized from a May snapshot file" case, field-caught).
    Returns {"terms": [names], "tags": [names]} — names only; the steward's
    Retire stays the acting hand. Governed/generic entries are never reported."""
    d = load()
    src = {str(s).strip().lower() for s in (sources or ()) if str(s).strip()}
    tnames = {str(t).strip().lower() for t in (terms or ()) if str(t).strip()}
    tag_l = {str(t).strip().lower() for t in (tags or ()) if str(t).strip()}
    stale_terms = []
    for name, meta in (d.get("terms") or {}).items():
        if not isinstance(meta, dict) or meta.get("layer") == "generic":
            continue
        if meta.get("status", "approved") != "pending":
            continue
        names = {name.lower()} | {str(a).strip().lower()
                                  for a in (meta.get("aliases") or ())}
        entry_src = {str(s).strip().lower() for s in (meta.get("sources") or ())}
        if (names & tnames) or (entry_src & src):
            continue
        stale_terms.append(name)
    stale_tags = []
    for t, meta in (d.get("tags") or {}).items():
        if not isinstance(meta, dict) or meta.get("layer") == "generic":
            continue
        if meta.get("status", "approved") != "pending":
            continue
        if str(t).strip().lower() in tag_l:
            continue
        stale_tags.append(t)
    return {"terms": sorted(stale_terms), "tags": sorted(stale_tags)}


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
    normalize to the same key, or are one edit apart) — the drift-in-waiting.
    A bucket's count is the number of DISTINCT terms scans observed carrying
    the tag — recomputed from the usage sets, so rescans don't inflate it."""
    d = load()
    tags = d.get("tags", {})
    usage = d.get("usage", {})
    gov = [(t, m) for t, m in tags.items() if _is_governed(m)]
    facet = sorted(({"tag": t, "count": len(usage.get(t) or ()),
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
    # counts are DERIVED from the identity-keyed usage sets (distinct terms
    # per tag / distinct source columns per term) — idempotent under rescans
    usage = d.get("usage", {}); tusage = d.get("term_usage", {})
    tags = []
    # case-insensitive: 'pH Level' belongs with the P's, not after Z
    for t, meta in sorted(d.get("tags", {}).items(), key=lambda kv: kv[0].lower()):
        meta = meta or {}
        tags.append({"tag": t, "label": meta.get("label", t), "layer": meta.get("layer", "company"),
                     "status": ("generic" if meta.get("layer") == "generic" else meta.get("status", "approved")),
                     "core": t in _CORE_TAGS,
                     "sensitivity_floor": meta.get("sensitivity_floor"),
                     "count": len(usage.get(t) or ()), "examples": d.get("examples", {}).get(t, [])})
    terms = []
    for n, meta in sorted(d.get("terms", {}).items(), key=lambda kv: kv[0].lower()):
        meta = meta or {}
        terms.append({"term": n, "aliases": meta.get("aliases", []), "layer": meta.get("layer", "company"),
                      "status": ("generic" if meta.get("layer") == "generic" else meta.get("status", "approved")),
                      "sensitivity": meta.get("sensitivity", "LOW"), "tags": meta.get("tags", []),
                      "category": meta.get("category", ""), "definition": meta.get("definition", ""),
                      "confidence": meta.get("confidence", ""), "sources": meta.get("sources", []),
                      "pattern": meta.get("pattern", ""),
                      "count": len(tusage.get(n) or ())})
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
