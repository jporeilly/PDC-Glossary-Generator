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

MERGE semantics, never blind overwrite: learned content fills gaps and adds
new entries. Where the scan DISAGREES with the base pack, the disagreement is
surfaced as a conflict (pack value vs scan value, side by side) instead of a
silent drop — the steward decides each one. Defaults per key: curation-bearing
keys keep the pack's value (a steward's recorded decision beats the machine's
newest opinion); curated_seeds prefer the scan's value (those entries are
machine-derived evidence in the first place — fresher data wins, and the
replaced seed is still visible in the conflict report). Pass `resolutions`
({"key::name": "scan"|"pack"}) to override any default.
"""
from __future__ import annotations
import re

import tagdict

_NON = re.compile(r"[^A-Za-z0-9]+")

# conflict keys where the scan's value wins by default: these entries are
# machine-derived detection evidence, not hand-authored intent — fresher
# profiling beats a stale seed, and the old value stays visible in the report
_SCAN_WINS = {"curated_seeds"}


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


def build_pack(rows, base=None, resolutions=None):
    """Reviewed rows + governed dictionary -> a domain pack dict, merged over
    `base`. Returns (pack, report); report counts the learned additions per
    key and carries report["conflicts"] — every place the scan disagreed with
    the base, with the side that won ("use"). `resolutions` maps "key::name"
    -> "scan"|"pack" to override the per-key defaults (_SCAN_WINS)."""
    base = dict(base or {})
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    res = {str(k): ("scan" if str(v).strip().lower() == "scan" else "pack")
           for k, v in (resolutions or {}).items()}
    d = tagdict.load()
    report = {}
    conflicts = []

    def resolve(key, name, packv, scanv):
        """Record a pack-vs-scan disagreement; return the side that wins."""
        use = res.get(f"{key}::{name}", "scan" if key in _SCAN_WINS else "pack")
        conflicts.append({"key": key, "name": name,
                          "pack": packv, "scan": scanv, "use": use})
        return use

    def merge_map(key, learned):
        cur = dict(base.get(key) or {})
        added = 0
        for k, v in learned.items():
            if k not in cur:
                cur[k] = v
                added += 1
            elif isinstance(cur[k], list) and isinstance(v, list):
                # list values (e.g. category_tags) union — additive, no conflict
                extra = [x for x in v if x not in cur[k]]
                if extra:
                    cur[k] = list(cur[k]) + extra
            elif cur[k] != v:
                if resolve(key, k, cur[k], v) == "scan":
                    cur[k] = v
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
    # terms merge is richer than add-only: review improvements PROPAGATE into
    # existing entries through safe unions — aliases and tags union in,
    # sensitivity tightens but never loosens. Curation can't be removed or
    # weakened; it can only be enriched.
    cur_terms = dict(base.get("terms") or {})
    added = updated = 0
    _rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    for n, v in learned_terms.items():
        if n not in cur_terms:
            cur_terms[n] = v
            added += 1
            continue
        e = dict(cur_terms[n])
        changed = False
        al = list(e.get("aliases") or [])
        for a in v["aliases"]:
            if a not in al:
                al.append(a); changed = True
        tg = list(e.get("tags") or [])
        for t in v["tags"]:
            if t not in tg:
                tg.append(t); changed = True
        sr = _rank.get(str(v.get("sensitivity", "LOW")).upper(), 0)
        er = _rank.get(str(e.get("sensitivity", "LOW")).upper(), 0)
        if sr > er:
            e["sensitivity"] = v["sensitivity"]; changed = True
        elif sr < er:
            # loosening is a conflict, not a silent block — steward decides
            if resolve("terms.sensitivity", n,
                       e.get("sensitivity", "LOW"), v["sensitivity"]) == "scan":
                e["sensitivity"] = v["sensitivity"]; changed = True
        if changed:
            e["aliases"], e["tags"] = al, tg
            cur_terms[n] = e
            updated += 1
    if cur_terms:
        base["terms"] = cur_terms
    report["terms"] = added
    report["terms_enriched"] = updated

    # steward retire-tombstones: an entry explicitly retired in the dictionary
    # but still sitting in the base pack would resurrect on the next install —
    # surface each as a removal decision. Default REMOVE (mirrors the recorded
    # steward intent); the conflict row keeps it visible and overridable.
    _RETIRED_NOTE = "retired by the steward — remove from the pack"
    ret = d.get("retired") or {}
    for n in ret.get("terms") or []:
        if n in (base.get("terms") or {}):
            use = res.get(f"terms::{n}", "scan")
            conflicts.append({"key": "terms", "name": n,
                              "pack": base["terms"][n], "scan": _RETIRED_NOTE,
                              "use": use})
            if use == "scan":
                base["terms"].pop(n, None)
    for t in ret.get("tags") or []:
        if t in (base.get("extra_tags") or []):
            use = res.get(f"extra_tags::{t}", "scan")
            conflicts.append({"key": "extra_tags", "name": t,
                              "pack": t, "scan": _RETIRED_NOTE, "use": use})
            if use == "scan":
                base["extra_tags"] = [x for x in base["extra_tags"] if x != t]

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
    report["conflicts"] = conflicts
    report["scan_overrides"] = sum(1 for c in conflicts if c["use"] == "scan")
    return base, report
