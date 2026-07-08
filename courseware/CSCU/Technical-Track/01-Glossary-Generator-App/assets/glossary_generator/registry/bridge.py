"""
Build the Registry artifact from the app's reviewed review-rows, at export time.

The Glossary Generator authors the Registry as a by-product of export: the rows
are the final reviewed state (Term, Category, Sensitivity, PII_Category,
Suggested_Tags). term_id is left null — PDC mints ids on import, and the Policy
Generator's reconcile backfills them later. Output schema matches what the
Policy Generator's load_registry() consumes.
"""
from __future__ import annotations
import json, os, re
from .model import Sensitivity

_CAMEL = re.compile(r'(?<=[a-z0-9])(?=[A-Z])')
_NON = re.compile(r'[^A-Za-z0-9]+')


def _slug(s: str) -> str:
    s = _CAMEL.sub(' ', s or '')
    s = _NON.sub('_', s).strip('_').lower()
    return s or 'concept'


def _kept(row) -> bool:
    return str(row.get('Keep', 'Y')).lower() in ('y', 'yes', 'true', '1')


def _tags(row) -> list:
    raw = row.get('Suggested_Tags') or row.get('Tags') or []
    if isinstance(raw, str):
        raw = [t.strip() for t in re.split(r'[;,]', raw) if t.strip()]
    tags = list(dict.fromkeys(raw))
    if row.get('PII_Category') and not any(str(t).upper() == 'PII' for t in tags):
        tags.append('PII')
    return tags


def _tag_vocabulary():
    """The controlled tag allow-list (+ sensitivity floors) and the canonical term
    vocabulary (+ aliases + sensitivity) from the per-company Term & tag dictionary,
    embedded in the Registry so the Policy Generator's Assign-Tags and term links stay
    inside the same governed vocabulary — the consistency contract."""
    try:
        import tagdict
        gov_tags = tagdict.governed_tags()
        gov_terms = tagdict.governed_terms()
        meta = tagdict.tags_meta()
        floors = tagdict.sensitivity_floors()
        terms = {n: {"sensitivity": (m or {}).get("sensitivity", "LOW"),
                     "aliases": (m or {}).get("aliases", []),
                     "tags": (m or {}).get("tags", []),
                     "layer": (m or {}).get("layer", "company")}
                 for n, m in tagdict.terms_meta().items() if n in gov_terms}
        return {
            "allow_list": sorted(gov_tags),
            "sensitivity_floors": {t: f for t, f in floors.items() if t in gov_tags},
            "terms": terms,
            "domain": tagdict.load().get("domain"),
            "source": "term_tag_dictionary",
            "note": "governed = generic baseline + steward-approved; pending items excluded",
        }
    except Exception:
        return {"allow_list": [], "sensitivity_floors": {}, "terms": {}, "source": None}


def build_registry(rows, glossary_name: str, glossary_id: str = None) -> dict:
    """rows -> Registry dict (one concept per kept term)."""
    concepts, seen = [], set()
    vocab = _tag_vocabulary()
    allow = set(vocab.get("allow_list") or [])
    for r in rows or []:
        if r.get('type') == 'category':
            continue
        term = (r.get('Term') or '').strip()
        if not term or not _kept(r):
            continue
        concept = _slug(term)
        if concept in seen:
            continue
        seen.add(concept)
        tags = _tags(r)
        # governance flag: any tag outside the controlled allow-list (drift risk)
        off = [t for t in tags if allow and t not in allow]
        concepts.append({
            "concept": concept,
            "term_name": term,
            "term_id": None,                       # UNKNOWN until reconcile
            "sensitivity": Sensitivity.parse(r.get('Sensitivity', 'LOW')).name,
            "tags": tags,
            "off_vocabulary_tags": off,            # empty when tags are all governed
            "category": (r.get('Category') or None),
            "definition": (r.get('Definition') or ''),
            "detect": [],
            "method": None,
        })
    return {"schema": "classification-registry/1", "glossary": glossary_name,
            "glossary_id": glossary_id, "pack": None, "concepts": concepts,
            "tag_vocabulary": vocab, "governance_audit": _audit_summary(),
            "references": {}}


def _audit_summary():
    """A compact governance audit summary (who approved/edited the vocabulary, when),
    embedded so the Registry carries its own provenance to the Policy Generator."""
    try:
        import audit
        return audit.summary()
    except Exception:
        return {"count": 0, "recent": []}


def build_and_save_registry(rows, glossary_name: str, out_path: str,
                            glossary_id: str = None) -> dict:
    reg = build_registry(rows, glossary_name, glossary_id=glossary_id)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(reg, f, indent=2)
    return reg


def backfill_term_ids(path: str, name_map: dict) -> int:
    """Stamp resolved PDC term ids into an existing Registry (match by term_name).

    Called after the glossary is imported and /api/resolve-terms has resolved each
    businessTerm's id. `name_map` is { term_name: {"id": ..., "glossaryId": ...} }
    (a bare id string is also accepted). Returns how many term ids were filled.
    Turns the initial (UNKNOWN) Registry into the resolved one the Policy Generator
    reads to bind dictionary methods by dictionaryTermId.
    """
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    filled = 0
    for c in reg.get("concepts", []):
        m = name_map.get(c.get("term_name"))
        if not m:
            continue
        tid = m.get("id") if isinstance(m, dict) else m
        if tid and c.get("term_id") != tid:
            c["term_id"] = tid
            filled += 1
    if reg.get("glossary_id") is None:
        for m in name_map.values():
            gid = m.get("glossaryId") if isinstance(m, dict) else None
            if gid:
                reg["glossary_id"] = gid
                break
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)
    return filled
