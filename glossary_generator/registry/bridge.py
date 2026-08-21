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
    # tags are standardised lower-case across the pipeline (facet consistency)
    tags = list(dict.fromkeys(str(t).strip().lower() for t in raw if str(t).strip()))
    if row.get('PII_Category') and 'pii' not in tags:
        tags.append('pii')
    return tags


def _tag_vocabulary():
    """The controlled tag allow-list (+ sensitivity floors) and the canonical term
    vocabulary (+ aliases + sensitivity) from the per-company Term & tag dictionary,
    embedded in the Registry so the Policy Generator's Assign-Tags and term links stay
    inside the same governed vocabulary — the consistency contract."""
    try:
        from engine import tagdict
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


def _curated_seeds():
    """Curated detection seeds from the installed domain pack — vetted
    canonical shapes (SSN, email, …) and reference lists (service cities)
    for concepts profiling can't induce. This is the custom-only program's
    replacement for PDC's built-ins: the seed lives in the versioned pack,
    travels through the Registry with source 'curated', and the Policy
    Generator authors it like any other evidence. {term_name_lower: [seeds]}"""
    path = os.environ.get("GLOSSARY_DOMAIN_PACK") or \
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "domain_pack.json")
    try:
        with open(path, encoding="utf-8") as f:
            cur = (json.load(f) or {}).get("curated_seeds") or {}
    except Exception:
        return {}
    out = {}
    for name, seed in cur.items():
        seeds = seed if isinstance(seed, list) else [seed]
        out[str(name).strip().lower()] = [s for s in seeds if isinstance(s, dict)]
    return out


def _known_term_ids(out_path) -> dict:
    """Term ids an EXISTING Registry file already knows, keyed by term name.

    Generate used to write every term_id as null, so re-generating after a
    Resolve silently threw away ids PDC had already minted — and the next deploy
    bound methods by NAME, which detaches the moment a term is renamed. Field
    evidence (2026-08-19): a re-Generate left 50 of 139 ids in the file while PDC
    knew all 139, and 40 of 115 deployed methods went out weakly bound with
    nothing to warn anyone.

    Ids are keyed on the term name, so carrying them forward is safe: a term
    whose name is unchanged is the same term. A renamed term simply has no entry
    and is left null for Reconcile, exactly as before.
    """
    try:
        with open(out_path, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, ValueError):
        return {}
    return {c.get("term_name"): c.get("term_id")
            for c in (prev.get("concepts") or [])
            if isinstance(c, dict) and c.get("term_name") and c.get("term_id")}


def build_registry(rows, glossary_name: str, glossary_id: str = None,
                   known_term_ids: dict = None) -> dict:
    """rows -> Registry dict (one concept per kept term).

    `known_term_ids` ({term_name: id}) carries forward what a previous Registry
    already resolved, so Generate can never REGRESS the contract."""
    known_term_ids = known_term_ids or {}
    # lazy, like this module's other engine imports: registry/ stays importable
    # on its own (the Policy Generator reads the artifact, never this code)
    from engine.policy_seed import seeds_for_row
    concepts, seen = [], set()
    vocab = _tag_vocabulary()
    allow = set(vocab.get("allow_list") or [])
    curated = _curated_seeds()
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
        # scan evidence -> detection seeds, through the ladder this module now
        # SHARES with the drafter (engine.policy_seed). It used to read only the
        # row's raw profiled fields here, so two classes of evidence the drafter
        # honoured never reached the Registry — a profiler-recognised kind, and
        # the steward's Auto flip on a mapping-only nature (a date, a bounded
        # measure). The Policy Generator authors from this contract alone, so
        # what the bridge cannot express PDC never sees: the walk that drafted
        # 88 patterns handed over a Registry worth 18. Seeds arrive best-first;
        # the Registry carries them all.
        detect, _skip, _mapping = seeds_for_row(r, curated)
        # physical key facts per source column — relationship context for the
        # Policy Generator (which columns are identity vs reference joins)
        keys = {sc: {"pk": bool(k.get("pk")), "fk": bool(k.get("fk")),
                     "ref": k.get("ref") or None}
                for sc, k in (r.get('Source_Keys') or {}).items()
                if isinstance(k, dict)}
        # detection intent — the Glossary half of the no-seed feedback loop.
        # "mapping_only": the steward flagged the term (Review grid's Detection
        # toggle) as governed by term links only — no value shape exists, so the
        # Policy Generator stops expecting a detection method for it. The flag
        # always wins. Otherwise "seeded" when detection seeds exist; when
        # neither, the field is omitted (legacy shape — Policy may then write a
        # seed-request asking the steward to decide). The ladder already read
        # the flag, so the answer comes from there rather than from a second
        # reading of the row.
        concepts.append({
            "concept": concept,
            "term_name": term,
            # carried forward when a previous Registry already resolved this
            # term; None means genuinely unknown, for Reconcile to fill
            "term_id": known_term_ids.get(term),
            "sensitivity": Sensitivity.parse(r.get('Sensitivity', 'LOW')).name,
            "tags": tags,
            "off_vocabulary_tags": off,            # empty when tags are all governed
            "category": (r.get('Category') or None),
            "definition": (r.get('Definition') or ''),
            "detect": detect,
            "sources": [c.strip() for c in str(r.get('Source_Column') or '').split(';') if c.strip()],
            # the physical type per source column. The Policy Generator authors
            # offline and cannot ask PDC what a column holds, so without this it
            # treats a BIT flag and a NUMERIC measure identically — and mints a
            # value-shape rule for the flag that PDC can never evaluate (proven
            # on the estate 2026-08-20: two BIT columns, two inert methods,
            # drift-clean forever). Types come straight off the scanned row.
            "source_types": {k: str(v) for k, v in (r.get('Source_Types') or {}).items() if v},
            "keys": keys,
            "method": None,
            **({"detection_intent": "mapping_only"} if _mapping
               else {"detection_intent": "seeded"} if detect else {}),
        })
    # ---- a shape shared by many concepts identifies none of them -----------
    # The profiler induces a regex per column, and columns of different concepts
    # can share one: on the Arizona estate `^[A-Z]{2}[0-9]{4}$` was induced for
    # EIGHT concepts (Customer County, Source Type, Water System Type…). Authored
    # with the profiled blend the regex alone clears the gate, so a free-text
    # `notes` column came back bound to all eight and tagged pii/privacy/location
    # (field-caught 2026-08-20).
    #
    # Such a shape is not identity, it is a sanity check — exactly what a
    # name-anchored seed already means. Marking it so makes the column NAME carry
    # identity and forces name AND shape to agree, which is what keeps the
    # legitimate matches and drops the accidental ones.
    shared = {}
    for c in concepts:
        for d in c.get("detect") or []:
            if d.get("type") == "pattern" and d.get("regex"):
                shared.setdefault(d["regex"], set()).add(c["term_name"])
    ambiguous = {rx for rx, terms in shared.items() if len(terms) > 1}
    for c in concepts:
        for d in c.get("detect") or []:
            if d.get("type") == "pattern" and d.get("regex") in ambiguous:
                d["identity"] = "column_name"
                d["shared_with"] = sorted(shared[d["regex"]] - {c["term_name"]})

    # Physical model — the schema/relationship layer. Built from EVERY scanned
    # column's PK/FK (all rows, kept OR pruned), so the join graph is
    # authoritative and independent of glossary curation: pruning a surrogate key
    # as a business term never loses the relationship. Mirrors how mature
    # catalogs keep keys/relationships in the physical layer, decoupled from the
    # business glossary — the Policy Generator gets its identity/reference-join
    # context from here rather than from whichever terms happened to survive.
    phys, relationships, seen_edge = {}, [], set()
    for r in rows or []:
        if not isinstance(r, dict) or r.get('type') == 'category':
            continue
        for sc, k in (r.get('Source_Keys') or {}).items():
            if not isinstance(k, dict):
                continue
            cur = phys.setdefault(sc, {"column": sc, "pk": False, "fk": False, "ref": None})
            cur["pk"] = cur["pk"] or bool(k.get('pk'))
            cur["fk"] = cur["fk"] or bool(k.get('fk'))
            cur["ref"] = cur["ref"] or (k.get('ref') or None)
            if k.get('fk') and k.get('ref'):
                edge = (sc, k['ref'])
                if edge not in seen_edge:
                    seen_edge.add(edge)
                    relationships.append({"from": sc, "to": k['ref'], "type": "fk"})

    return {"schema": "classification-registry/1", "glossary": glossary_name,
            "glossary_id": glossary_id, "pack": None, "concepts": concepts,
            "physical_model": {"keys": sorted(phys.values(), key=lambda x: x["column"]),
                               "relationships": relationships},
            "tag_vocabulary": vocab, "governance_audit": _audit_summary(),
            "references": {}}


def _audit_summary():
    """A compact governance audit summary (who approved/edited the vocabulary, when),
    embedded so the Registry carries its own provenance to the Policy Generator."""
    try:
        from core import audit
        return audit.summary()
    except Exception:
        return {"count": 0, "recent": []}


def build_and_save_registry(rows, glossary_name: str, out_path: str,
                            glossary_id: str = None) -> dict:
    # read the file we are about to overwrite FIRST: whatever it already knows
    # about term ids survives the regeneration
    reg = build_registry(rows, glossary_name, glossary_id=glossary_id,
                         known_term_ids=_known_term_ids(out_path))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(reg, f, indent=2)
    return reg


def backfill_term_ids(path: str, name_map: dict, glossary_name: str = None) -> int:
    """Stamp resolved PDC term ids into an existing Registry (match by term_name).

    Called after the glossary is imported and /api/resolve-terms has resolved each
    businessTerm's id. `name_map` is { term_name: {"id": ..., "glossaryId": ...} }
    (a bare id string is also accepted). Returns how many term ids were filled.
    Turns the initial (UNKNOWN) Registry into the resolved one the Policy Generator
    reads to bind dictionary methods by dictionaryTermId.

    FOREIGN IDS ARE REFUSED. resolve_terms matches on NAME: PDC's search exposes
    neither glossaryId nor rootId for a term, so two glossaries holding the same
    term name resolve to whichever PDC returns first. Field-caught 2026-08-21 with
    ADWR's glossary alongside Arizona Water: both hold "GIS", and the AWC concept
    was about to be bound to ADWR's term — a valid id, resolving cleanly, in the
    wrong glossary, invisible to drift because the contract and the catalog agree.

    We do not need PDC to answer this. The app MINTED the ids it imported, and
    det_term_id reproduces them from (glossary, category, term) alone, so a
    resolved id either is ours or is a stranger. Pass `glossary_name` to enforce
    that. The check stands down when NONE of the resolved ids are ours — that
    means PDC minted its own on import, and the ids can no longer be told apart
    by provenance.
    """
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    gname = glossary_name or reg.get("glossary_name") or reg.get("glossary")
    mine = None
    if gname:
        from engine.sug_links import det_term_id
        expected = {c.get("term_name"): det_term_id(gname, c.get("category") or "",
                                                    c.get("term_name") or "")
                    for c in reg.get("concepts", [])}
        resolved = {(m.get("id") if isinstance(m, dict) else m) for m in name_map.values()}
        # ids preserved on import -> provenance is meaningful; none -> stand down
        mine = expected if (resolved & set(expected.values())) else None

    filled = 0
    reg["foreign_term_ids"] = []
    for c in reg.get("concepts", []):
        m = name_map.get(c.get("term_name"))
        if not m:
            continue
        tid = m.get("id") if isinstance(m, dict) else m
        if tid and mine is not None and tid != mine.get(c.get("term_name")):
            # a same-named term in someone else's glossary
            reg["foreign_term_ids"].append({"term_name": c.get("term_name"),
                                            "resolved": tid,
                                            "expected": mine.get(c.get("term_name"))})
            continue
        if tid and c.get("term_id") != tid:
            c["term_id"] = tid
            filled += 1
    if not reg["foreign_term_ids"]:
        reg.pop("foreign_term_ids")
    if reg.get("glossary_id") is None:
        for m in name_map.values():
            gid = m.get("glossaryId") if isinstance(m, dict) else None
            if gid:
                reg["glossary_id"] = gid
                break
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=2)
    return filled
