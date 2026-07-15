"""
packgen.py — generate/refresh a domain pack from what the scans actually learned.

Closes the pack loop: a pack seeds the engine, the engine scans and the steward
reviews, and THIS module exports that reviewed state back into pack format —
so the pack evolves from real company data instead of staying a hand-authored
guess. Learned content:

  * table_category / table_terms       from the reviewed rows' physical tables
  * cat_keywords                       from table-name tokens -> categories
  * abbreviations                      aligned column tokens -> term words
                                       (mbr_no + "Member Number" -> mbr: Member)
  * category_tags / tag_rules /        from the GOVERNED company layer of the
    extra_tags / terms                 Term & tag dictionary (approved only)
  * curated_seeds                      the scan's induced value patterns and
                                       profiled reference lists, per term —
                                       the company-specific detection seeds

MERGE semantics, never blind overwrite: hand-curated entries in the base pack
always win; learned content fills gaps and adds new entries, and the report
says exactly what was added — the steward reviews the diff, then commits the
pack to the scenario repo.
"""
from __future__ import annotations
import re

import tagdict

_NON = re.compile(r"[^A-Za-z0-9]+")


def _kept(r):
    return str(r.get("Keep", "Y")).strip().lower() in ("y", "yes", "true", "1")


def _tables_of(rows):
    """{table: {category counts}} + per-table columns from the kept DB rows."""
    tables = {}
    for r in rows:
        if not isinstance(r, dict) or not _kept(r):
            continue
        for src in str(r.get("Source_Column") or "").split(";"):
            bits = [b for b in src.strip().split(".") if b]
            if len(bits) < 3:
                continue                      # object-store / non-column sources
            t = bits[-2]
            d = tables.setdefault(t, {"cats": {}, "cols": []})
            cat = (r.get("Category") or "").strip()
            if cat:
                d["cats"][cat] = d["cats"].get(cat, 0) + 1
            d["cols"].append((bits[-1], (r.get("Term") or "").strip()))
    return tables


def _abbrev_pairs(col, term):
    """Align column tokens with term words: mbr_no + 'Member Number' ->
    [('mbr','Member')] — only when the token is a strict prefix or an ordered
    subsequence of the word, and shorter than it (a genuine abbreviation)."""
    toks = [t for t in _NON.split(col.lower()) if t]
    words = [w for w in term.split() if w]
    out = []
    if len(toks) != len(words):
        return out

    def subseq(small, big):
        it = iter(big)
        return all(ch in it for ch in small)

    for tok, word in zip(toks, words):
        wl = word.lower()
        if tok == wl or len(tok) >= len(wl) or len(tok) < 2:
            continue
        if wl.startswith(tok) or subseq(tok, wl):
            out.append((tok, word))
    return out


def build_pack(rows, base=None):
    """Reviewed rows + governed dictionary -> a domain pack dict, merged over
    `base` (hand-curated wins). Returns (pack, report) where report counts the
    learned additions per key."""
    base = dict(base or {})
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    d = tagdict.load()
    report = {}

    def merge_map(key, learned):
        cur = dict(base.get(key) or {})
        added = 0
        for k, v in learned.items():
            if k not in cur:
                cur[k] = v
                added += 1
        if cur:
            base[key] = cur
        report[key] = added

    tables = _tables_of(rows)

    # table_category: majority category per table
    learned_tc = {}
    for t, info in tables.items():
        if info["cats"]:
            learned_tc[t] = max(info["cats"].items(), key=lambda kv: kv[1])[0]
    merge_map("table_category", learned_tc)

    # table_terms: from the table-level record rows
    learned_tt = {}
    for r in rows:
        if _kept(r) and (r.get("Source_Table") or "").strip() and (r.get("Term") or "").strip():
            learned_tt[r["Source_Table"].strip()] = r["Term"].strip()
    merge_map("table_terms", learned_tt)

    # cat_keywords: table-name token -> its category (fallback routing)
    have_kw = {tuple(x) for x in (base.get("cat_keywords") or [])}
    added_kw = []
    for t, cat in learned_tc.items():
        tok = _NON.split(t.lower())[0]
        if tok and len(tok) > 3 and (tok, cat) not in have_kw:
            added_kw.append([tok, cat])
            have_kw.add((tok, cat))
    if added_kw or base.get("cat_keywords"):
        base["cat_keywords"] = (base.get("cat_keywords") or []) + added_kw
    report["cat_keywords"] = len(added_kw)

    # abbreviations: aligned column-token -> term-word pairs seen >= 2 times
    counts = {}
    for info in tables.values():
        for col, term in info["cols"]:
            for tok, word in _abbrev_pairs(col, term):
                counts[(tok, word)] = counts.get((tok, word), 0) + 1
    learned_ab = {tok: word for (tok, word), n in counts.items() if n >= 2}
    merge_map("abbreviations", learned_ab)

    # governed company vocabulary -> category_tags / tag_rules / extra_tags / terms
    merge_map("category_tags", {c: list(ts) for c, ts in (d.get("category_tags") or {}).items()})
    have_rules = {r.get("pattern") for r in (base.get("tag_rules") or [])}
    added_rules = [{"pattern": r["pattern"], "tags": list(r.get("tags") or [])}
                   for r in (d.get("rules") or [])
                   if r.get("layer") == "company" and r.get("pattern") not in have_rules]
    if added_rules or base.get("tag_rules"):
        base["tag_rules"] = (base.get("tag_rules") or []) + added_rules
    report["tag_rules"] = len(added_rules)

    gov = tagdict.governed_tags()
    ruled = {t for r in (base.get("tag_rules") or []) for t in r.get("tags", [])}
    for c in (base.get("category_tags") or {}).values():
        ruled.update(c)
    have_extra = set(base.get("extra_tags") or [])
    added_extra = sorted(t for t, m in (d.get("tags") or {}).items()
                         if (m or {}).get("layer") == "company" and (m or {}).get("status") == "approved"
                         and t in gov and t not in ruled and t not in have_extra)
    if added_extra or base.get("extra_tags"):
        base["extra_tags"] = sorted(set(base.get("extra_tags") or []) | set(added_extra))
    report["extra_tags"] = len(added_extra)

    learned_terms = {}
    for n, m in (d.get("terms") or {}).items():
        if (m or {}).get("layer") == "company" and (m or {}).get("status") == "approved":
            learned_terms[n] = {"aliases": list(m.get("aliases") or []),
                                "sensitivity": m.get("sensitivity", "LOW"),
                                "tags": list(m.get("tags") or [])}
    merge_map("terms", learned_terms)

    # curated_seeds: the company-specific detection seeds the scan induced
    learned_seeds = {}
    for r in rows:
        if not _kept(r):
            continue
        term = (r.get("Term") or "").strip()
        if not term:
            continue
        vp = (r.get("Value_Pattern") or "").strip()
        enums = [v.strip() for v in str(r.get("Enum_Values") or "").split(";") if v.strip()]
        if vp:
            learned_seeds.setdefault(term, {"type": "pattern", "regex": vp,
                                            "signature": (r.get("Value_Signature") or "").strip() or None})
        elif len(enums) >= 2:
            learned_seeds.setdefault(term, {"type": "dictionary", "values": enums})
    merge_map("curated_seeds", learned_seeds)

    base.setdefault("domain", d.get("domain") or "generic")
    base["note"] = (str(base.get("note") or "").split(" [refreshed")[0]
                    + " [refreshed from scan results by the pack generator — review the additions, then commit]")
    return base, report
