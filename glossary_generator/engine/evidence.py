"""Value evidence: what a scan OBSERVED about a column's values, and the one
rule for folding a new observation into a stored one.

There are exactly two intents, and conflating them has now cost three
defects on the same day:

  CAPTURE  first sight, or a routine rescan. Fill what is missing and never
           erase: the steward's work and earlier evidence both survive an
           incoming blank, because a blank here means "nothing new to say".

  REFRESH  the DATA changed - the estate was rescaled, repaired, re-profiled -
           and the steward asked for the fresh reading to win. The fresh
           observation replaces the set WHOLE, blanks included, because it is
           ONE observation and not five independent fields. A column that
           used to induce a shape and now induces an enum must not keep the
           shape: on the AWC estate that left ^[A-Z]{2}[0-9]{4}$ standing on
           eight terms after the data behind it was repaired, a pattern
           matching zero rows that would have deployed as a Data Pattern and
           silently never fired.

The one thing both modes agree on: a scan that observed NOTHING AT ALL (an
unprofilable pdf or docx row) never erases anything. Absence of observation
is not observation of absence.

`frontend/src/evidence.js` is this module's mirror - the rows are merged in
the browser and the dictionary in Python, so the rule is written twice by
necessity. test_docs.py pins the two to the same field list and modes; keep
them in step.
"""

# The five fields a profiler fills. They travel together.
EVIDENCE_FIELDS = ("Value_Signature", "Value_Pattern", "Enum_Values",
                   "Value_Kind", "Value_Range")

CAPTURE = "capture"
REFRESH = "refresh"


def observed(row):
    """Did this scan see ANY value evidence at all?

    The question REFRESH turns on. A row carrying an enum but no pattern DID
    observe the column - it observed that there is no shape - and its blank
    pattern is a finding. A row carrying nothing observed nothing.
    """
    return any(str((row or {}).get(f) or "").strip() for f in EVIDENCE_FIELDS)


def merge(target, row, mode, fields=None):
    """Fold a scan row's evidence into `target`, in place. Returns True if
    anything changed.

    `fields` maps a target key to the row field that feeds it, so a store
    that keeps a projection can use the same rule: the review grid holds all
    five under their own names, the dictionary holds `pattern` alone. Whether
    the scan observed anything is judged on the WHOLE row either way - which
    is how a dictionary entry's pattern gets cleared by a rescan that came
    back with an enum instead.
    """
    if mode not in (CAPTURE, REFRESH):
        raise ValueError(f"unknown evidence mode {mode!r} - use CAPTURE or REFRESH")
    fields = fields or {f: f for f in EVIDENCE_FIELDS}
    row = row or {}
    fresh = mode == REFRESH and observed(row)
    changed = False
    for key, src in fields.items():
        incoming = str(row.get(src) or "").strip()
        current = str(target.get(key) or "").strip()
        if incoming:
            if incoming != current:
                target[key] = incoming
                changed = True
        elif fresh and current:
            # the fresh reading says this field is empty, and it LOOKED.
            # Never create a key that was not there: a store keeping a
            # projection should not grow empty fields it never carried.
            target[key] = ""
            changed = True
    return changed
