"""packinit — scaffold a THIN domain pack for a new company.

A domain pack is read by three engines from one file (see domain_packs/README.md):
suggester.py takes the categorisation and naming keys, tagdict.py takes the
governed tag vocabulary, and the Registry takes the verified references. Written
from scratch that is a lot of empty structure to get right, and the shape is not
guessable — which is why a new scenario tends to start with no pack at all and
lets the LLM carry classification that rules should be doing.

This writes the skeleton so the first scan has something deterministic to work
with. It is deliberately THIN: it seeds what can be derived from a category list
and leaves the rest empty, because the rest is meant to be *grown*:

    scaffold (this tool) -> scan -> review -> Export domain pack -> commit
                                              (packgen.build_pack merges the
                                               reviewed rows over the pack)

What it seeds, and why that much and no more:
  cat_keywords     one keyword per category, derived from the category's own
                   distinctive word ("Water Quality" -> "quality"). First-match
                   wins, so ordering matters and duplicates are dropped.
  category_tags    one governed tag per category, slugified.
  extra_tags       those same slugs, pre-approved into the allow-list.
  category_definitions  a placeholder sentence per category, for the steward.
  table_category / table_terms / terms / tag_rules
                   left EMPTY on purpose. Inventing table names for a database
                   nobody has scanned yet produces rules that never match and
                   read as if they were curated. The export step fills them from
                   evidence.

Usage:
    python packinit.py --domain water_utility --company "Northgate Water" \
        --categories "Customer,Billing & Rates,Usage,Water Quality,Water System,Governance" \
        -o domain_packs/water_utility.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# A SUGGESTED starting list for --categories, used only when the caller omits
# it. This is a scaffolding tool whose output the steward edits, so proposing a
# skeleton is its job - unlike the engine, which must not assert a taxonomy at
# scan time (see suggester.CAT_KEYWORDS).
DEFAULT_CATEGORIES = ["Customer", "Finance", "Operations", "Governance",
                      "Records & Documents"]

# The engine ships no builtin keywords any more, so nothing here can collide
# with one. Kept as an empty set rather than deleted so the warning path below
# still compiles for whatever the engine may reserve in future.
_BUILTIN_KEYWORDS = set()

# Words too generic to route a category on their own — a keyword of "data" or
# "record" would swallow half the estate on the first scan.
_STOPWORDS = {"and", "the", "of", "data", "info", "information", "general",
              "other", "misc", "record", "records", "document", "documents"}


def slugify(text):
    """'Water Quality' -> 'water-quality' — the governed-tag spelling."""
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)


def keyword_for(category):
    """The most distinctive single word of a category name, or None.

    Prefers the LAST meaningful word ('Billing & Rates' -> 'rates'), which is
    usually the noun that names the thing; falls back to the first."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", str(category).lower()) if w]
    words = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    if not words:
        return None
    return words[-1]


def scaffold(domain, company=None, categories=None):
    """Build the thin pack dict. Pure — no I/O, so it is testable."""
    cats = [c.strip() for c in (categories or DEFAULT_CATEGORIES) if str(c).strip()]
    seen, cat_keywords, skipped = set(), [], []
    for c in cats:
        kw = keyword_for(c)
        if not kw:
            # every word was a stopword ("Records & Documents"). Say so — a
            # category silently left without a rule is the failure this tool
            # exists to prevent, and the steward may want to pick a word by hand.
            skipped.append(("(none)", c, "every word is too generic to route on — "
                                         "add a keyword by hand if this category "
                                         "should be matched by name"))
            continue
        if kw in _BUILTIN_KEYWORDS:
            # keep the pack honest: a rule that can never fire is worse than no
            # rule, because it reads as configured behaviour
            skipped.append((kw, c, "already a builtin keyword — would never fire"))
            continue
        if kw in seen:
            skipped.append((kw, c, "an earlier category already claims this word"))
            continue
        seen.add(kw)
        cat_keywords.append([kw, c])

    pack = {
        "domain": domain,
        "note": (f"THIN scaffold for {company or domain}. Seeded from the category list only. "
                 "Grow it: scan -> review -> Export domain pack (merges the reviewed rows "
                 "over this file) -> review the additions -> commit. Keys left empty here "
                 "are meant to be filled from evidence, not guessed."),
        "cat_keywords": cat_keywords,
        "category_tags": {c: [slugify(c)] for c in cats},
        "extra_tags": sorted({slugify(c) for c in cats}),
        "category_definitions": {
            c: f"{c} concepts for {company or domain}. Replace with the steward's wording."
            for c in cats
        },
        # Empty ON PURPOSE — these describe a specific estate, so they are
        # written by the export step once a scan has produced evidence.
        "table_category": {},
        "table_terms": {},
        "tag_rules": [],
        "abbreviations": {},
        "terms": {},
    }
    return pack, skipped


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="packinit",
        description="Scaffold a thin domain pack for a new company/scenario.")
    ap.add_argument("--domain", required=True,
                    help="domain slug, e.g. water_utility / credit_union")
    ap.add_argument("--company", default=None, help="company name, for the placeholders")
    ap.add_argument("--categories", default=None,
                    help="comma-separated glossary categories (default: a generic set)")
    ap.add_argument("-o", "--out", default=None,
                    help="output path (default: stdout). Refuses to overwrite.")
    ap.add_argument("--force", action="store_true", help="allow overwriting --out")
    a = ap.parse_args(argv)

    cats = a.categories.split(",") if a.categories else None
    pack, skipped = scaffold(a.domain, a.company, cats)
    text = json.dumps(pack, indent=2, ensure_ascii=False) + "\n"

    if not a.out:
        sys.stdout.write(text)
    else:
        if os.path.exists(a.out) and not a.force:
            # a pack is hand-curated and slow to rebuild; never clobber silently
            print(f"refusing to overwrite {a.out} — pass --force if you mean it",
                  file=sys.stderr)
            return 2
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {a.out}", file=sys.stderr)

    for kw, cat, why in skipped:
        print(f"  note: no keyword for '{cat}' — '{kw}' {why}", file=sys.stderr)
    print("  next: point GLOSSARY_DOMAIN_PACK at it (or name it domain_pack.json), "
          "scan, review, then Export domain pack to grow it", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
