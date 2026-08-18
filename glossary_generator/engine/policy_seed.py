"""
policy_seed.py — the ONE ladder from a reviewed row to its detection seeds.

Two consumers used to decide this separately, and drifted: the drafter
(policy_draft) minted a rule for a steward's Auto flip and for a profiler-
recognised kind, while the Registry bridge (registry/bridge) emitted only the
row's raw profiled evidence. The Registry is the contract the Policy Generator
authors from, so anything the bridge could not express simply never reached
PDC — a walk that drafted 88 patterns handed over a Registry worth 18.

The ladder lives here; both call it. Seeds come back in the Registry's own
`detect` shape, best evidence first:

    {"type": "pattern",    "regex": ..., "signature": ...|None, "source": ...}
    {"type": "dictionary", "values": [...],                     "source": ...}

`source` names the evidence — "profiled" (induced from the estate's values),
"curated" (a vetted seed from the versioned domain pack), "recognised" (the
profiler matched a known kind in this estate's data), "name-anchored" (the
steward flipped a mapping-only nature to Auto: the column NAME is the
identity, the content shape only a sanity check — such a seed also carries
`"identity": "column_name"`, which is how the authoring side knows to weight
name and shape as a conjunction instead of trusting the shape alone).
"""
from __future__ import annotations
import re

# Sanity shapes for a name-anchored rule. The range never identifies (every
# 1-10 rating matches "0-14"); it stays in the DQ rule. These say only "this
# column still holds what it should".
DATE_SHAPE = r"^\d{4}-\d{2}-\d{2}([T ].*)?$|^\d{1,2}/\d{1,2}/\d{2,4}$"  # mirrors the profiler's date kind
NUM_SHAPE = r"^-?[0-9]+(\.[0-9]+)?$"

# Column kinds whose VALUES carry no detectable shape — a surrogate integer key,
# a date, a person/free-text name, or a raw amount. You can't recognise an
# "Account ID" or a date by its value (any integer/date could be one), so these
# are governed by the term↔column link (tagged on Apply), never a value pattern.
# Deliberately narrow: codes/statuses and formatted numbers (account_no,
# routing, zip, phone, ssn, email…) are NOT here — those become dictionaries /
# patterns once profiled.
NO_SHAPE = re.compile(
    r"(^|_)id$|_id$|identifier"                 # surrogate-key ids
    r"|(^|_)dt$|date|dob|birth"                 # dates
    r"|(^|_)nm$|name"                           # names / free text
    r"|amount|(^|_)amt$|balance|(^|_)bal$",     # raw amounts
    re.I)


def cols_of(row):
    return [c.strip() for c in str(row.get("Source_Column") or "").split(";") if c.strip()]


def col_names(row):
    """Bare column names off the row's physical columns — through the ONE
    canonical source splitter, so a document column yields its real column
    name and a JSONL leaf keeps its dotted path ("record.customer.id"),
    instead of split('.')[-1] shredding it to "id" and the rule regex
    over-matching every id column in the estate (the dotted-filename trap's
    third sibling — field-caught: "this will also affect the draft
    policies")."""
    from engine.suggester import _parse_source
    out = []
    for c in cols_of(row):
        de = _parse_source(c)
        name = ((de or {}).get("column_name") or c.split(".")[-1]).strip()
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


# Kinds the profiler RECOGNISED in this estate's actual values (>=60% of the
# sample matched) — each mints a CUSTOM Data Pattern using the profiler's own
# shape, so there is ONE definition of "email" in the codebase. Clarified in
# the field: custom-only means WE ship every policy (PDC's inbuilt set stays
# unused) — it never meant generic concepts go undetected. The recognition
# came from this estate's data; the deployment is ours; the policy is custom.
# "date" deliberately absent: every date column matches a date shape, so a
# date Data Pattern would over-match — dates stay tagged via the term↔column
# link.
def kind_patterns():
    from engine import suggester as _sug
    return {"email": _sug.RX_EMAIL.pattern, "phone": _sug.RX_PHONE.pattern,
            "zip": _sug.RX_ZIP.pattern, "ssn": _sug.RX_SSN.pattern,
            "card": _sug.RX_CC.pattern}


def was_profiled(row):
    """Did profiling touch this row? The prose marker (Suggested_Reason
    'Profiled: …') dies the moment the AI pass rewrites that field — the
    profile's own DATA on the row is the durable witness (field-caught:
    enriched rows were told to 're-scan with profiling on')."""
    if str(row.get("Suggested_Reason") or "").startswith("Profiled"):
        return True
    if row.get("Suggested_Quality") is not None:
        return True
    if row.get("Source_Quality_Dims"):
        return True
    return bool(str(row.get("Value_Kind") or "").strip())


def auto_candidate(row):
    """True when a mapping-only row is a SAFE Auto-flip candidate: numeric
    range evidence + a unit-bearing name. Everything else (generic amounts,
    dates, names) stays an unmarked steward call."""
    from engine.sug_shared import UNIT_NAME
    if not str(row.get("Value_Range") or "").strip():
        return False
    for h in [str(row.get("Term") or "")] + col_names(row):
        if UNIT_NAME.search(re.sub(r"[^A-Za-z0-9]+", "_", h.strip())):
            return True
    return False


def no_value_shape(cols):
    """True when EVERY source column is a kind with no detectable value shape, so
    the term is a link-only concern rather than a not-yet-profiled one. Column
    names come through the canonical source splitter — split('.')[-1] turned a
    document column into its file extension's neighbour and misclassified it."""
    from engine.suggester import _parse_source
    names = []
    for c in (cols or []):
        if not c:
            continue
        de = _parse_source(str(c))
        names.append(((de or {}).get("column_name") or str(c).split(".")[-1]))
    return bool(names) and all(NO_SHAPE.search(n) for n in names)


def seeds_for_row(row, curated=None):
    """row -> (seeds, skip, mapping_only).

    `seeds` is the row's detection evidence in Registry `detect` shape, best
    first (a caller minting ONE artifact takes seeds[0]; the Registry carries
    them all). `skip` is the steward-facing reason when the row yields no
    seed, and is None whenever seeds exist. `mapping_only` is a dict
    ({"auto_candidate": bool}) when the steward declared the term governed by
    its term↔column links — a DECLARATION, not a failure, which is why it is
    neither a seed nor a skip.

    `curated` is the domain pack's {term_name_lower: [seed, …]} map (see
    registry.bridge._curated_seeds); passed in rather than loaded here so this
    module stays a leaf and both callers read the same pack exactly once.
    """
    curated = curated or {}
    term = (row.get("Term") or "").strip()
    # mapping-only is a DECLARATION, not a failure: this term is governed
    # by its term↔column links and no detection method is expected. The
    # skip list exists to name missing evidence - listing intentional
    # mapping terms there was exactly the noise the intent flag was built
    # to end (caught by the end-to-end run). The declaration does NOT erase
    # the row's evidence: whatever the scan induced still travels into the
    # Registry, and only the intent changes (pinned by test_seed_loop) — a
    # steward who flips the term back should not have to re-scan for it.
    mapping = ({"auto_candidate": auto_candidate(row)}
               if str(row.get("Detection_Intent") or "").strip() == "mapping_only" else None)
    if not str(row.get("Source_Column") or "").strip():
        return [], "table-level term — no physical column to identify", mapping

    seeds = []
    vp = (row.get("Value_Pattern") or "").strip()
    sig = (row.get("Value_Signature") or "").strip() or None
    enums = [v.strip() for v in str(row.get("Enum_Values") or "").split(";") if v.strip()]
    if vp:
        seeds.append({"type": "pattern", "regex": vp, "signature": sig,
                      "source": "profiled"})
    # two values is the floor a dictionary can be authored from — a one-value
    # reference list is not a vocabulary, and the authoring side drops it, so
    # carrying it in the Registry only pretended to be evidence.
    if len(enums) >= 2:
        seeds.append({"type": "dictionary", "values": enums, "source": "profiled"})
    if seeds:
        return seeds, None, mapping

    # Profiled evidence wins; otherwise fall back to a CURATED seed from
    # the versioned domain pack (the generic baseline). Still no
    # inbuilt/hardcoded shapes — the seed lives in the user's pack.
    cur = curated.get(term.lower(), [])
    cp = next((s for s in cur if s.get("type") == "pattern" and (s.get("regex") or "").strip()), None)
    cd = next((s for s in cur if s.get("type") == "dictionary"
               and len([v for v in (s.get("values") or []) if str(v).strip()]) >= 2), None)
    if cp:
        seeds.append({"type": "pattern", "regex": cp["regex"].strip(),
                      "signature": (cp.get("signature") or "").strip() or None,
                      "source": "curated"})
    if cd:
        seeds.append({"type": "dictionary",
                      "values": [str(v).strip() for v in cd["values"] if str(v).strip()],
                      "source": "curated"})
    if seeds:
        return seeds, None, mapping

    kind = str(row.get("Value_Kind") or "").strip().lower()
    kinds = kind_patterns()
    if kind in kinds:
        # the profiler recognised the estate's own values as this kind —
        # mint the CUSTOM pattern (PDC's inbuilt set is unused by design,
        # so the coverage must ship from here)
        return ([{"type": "pattern", "regex": kinds[kind], "signature": sig,
                  "source": "recognised"}], None, mapping)

    if mapping:
        # the declaration ends the ladder: everything below either mints for a
        # steward's Auto flip (which this row is the opposite of) or names
        # missing evidence, and a mapping-only term is not missing anything —
        # putting it in the skips was the exact noise the intent flag ended.
        return [], None, mapping

    cols = cols_of(row)
    if not any(c.count(".") >= 2 for c in cols):
        return [], "document term — identify documents with vocabulary dictionaries, not value shapes", None

    # NAME-ANCHORED MEASURE: the steward flipped this row to Auto
    # despite its nature (a date, a bounded measure like pH or
    # Lead ppb). The range alone never discriminates - every
    # 1-10 rating matches "0-14" - but PDC's blended scoring
    # makes name + shape TOGETHER a legitimate rule: column-name
    # regex carries identity, content regex carries sanity
    # (date shape, or numeric shape with the range in DQ).
    # This check comes BEFORE the signature gate: a profiled date
    # carries a dddd-dd-dd SIGNATURE, and gating the mint behind
    # "no signature" sent a flipped Payment Date to the skips
    # (field-caught on the mass-flip walk). A signature rides the
    # rule's contentPatterns at weight 0 - informative, inert.
    rng = str(row.get("Value_Range") or "").strip()
    if (rng or kind == "date") and column_name_regex(col_names(row)):
        # mapping-only rows never reach this ladder — so an Auto
        # row here IS the steward's flip (or the suggest-time
        # unit-name default), and it overrides the NO_SHAPE name
        # heuristic (payment_date has "date" in its name by
        # definition). No name regex -> no anchor -> still a skip.
        return ([{"type": "pattern", "regex": DATE_SHAPE if kind == "date" else NUM_SHAPE,
                  "signature": sig, "source": "name-anchored",
                  "identity": "column_name"}], None, None)
    if sig or (row.get("Enum_Values") or "").strip():
        return [], "no stable shape in the data (free text, names, amounts, dates)", None
    if no_value_shape(cols):
        return [], ("tagged via the term↔column link, not a value pattern — a surrogate id / "
                    "date / name / amount has no value shape to detect (expected)"), None
    if kind == "date":
        return [], ("recognised as date values — every date column matches a date shape, so a "
                    "date Data Pattern would over-match; dates are tagged via the term↔column "
                    "link (expected)"), None
    if was_profiled(row):
        # the row WAS profiled — telling the steward to re-scan
        # is wrong advice; the values simply induce no shape
        return [], ("profiled, but the values induce no shape (numeric or free-form content) — "
                    "add a curated seed for this term to the domain pack if it should be "
                    "detectable"), None
    return [], ("no profiled evidence on the row — re-scan the live source with value profiling "
                "on to induce a custom pattern, or add a curated seed for this term to the "
                "domain pack"), None
