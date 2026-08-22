# DQ workshop — working notes

Decided 2026-08-22: `monthly_usage.usage_id 100009` stays broken on purpose and
becomes the seed of a data-quality workshop. This file records what the estate
already offers, what it lacks, and the one design decision to settle before
planting anything. **The workshop itself is not built yet.**

## Why this note exists

Two days were spent making the AWC estate *coherent* — repairing twelve junk
columns, rebuilding vocabularies, making bills reconcile. A DQ workshop needs
the opposite: known, documented defects. Without a note, the next session will
helpfully repair the very rows the workshop depends on. It nearly happened to
100009.

**Rule for anyone touching the estate: every repair script skips the original
rows** (`customers` ≤ 1010, `water_systems` ≤ 2008, `monthly_usage` ≤ min+9).
That is what protects the hand-authored material.

## What the estate ALREADY offers (measured 2026-08-22)

Some of this is deliberate, some is leftover from the pre-1.38.36 seeder. Both
are usable — a workshop does not care whether its dirt was intentional.

| dimension | finding | rows |
|---|---|---|
| Consistency — case | `active/Active`, `suspended/Suspended`, `commercial/Commercial`, `residential/Residential`, `compliant/Compliant` across `customers`, `water_systems`, `tiered_rates`, `water_quality_reports` | 9 column-pairs |
| Validity — range | chlorine residual outside 0.2–4.0 mg/L (EPA limit is 4) | **615** |
| Validity — range | pH outside 6.5–8.5 | 20 |
| Consistency — cross-field | `payment_date` set on a bill that was never paid | **223** |
| Consistency — arithmetic | tier gallons do not sum to `usage_gallons` | **1** (100009) |
| Completeness | `account_alerts.resolved_date` null | 5 |
| Completeness | `monthly_usage.payment_date` null | 3 |

The chlorine and payment-date findings are leftovers from the old seeder,
fixed in the generator but never repaired in the data. **Keep them.** They are
the most realistic material on the estate: a sensor or unit error, and a
cross-field contradiction nobody would notice by reading one column.

## What is MISSING

- **Completeness** — almost nothing is null. A real estate has gaps.
- **Uniqueness** — no duplicates at all. No same-person-two-accounts, no
  repeated meter id.
- **Timeliness** — nothing stale or future-dated (`last_compliance_check`
  years overdue, a reading dated next year).
- **Accuracy** — no meter reading that goes backwards, no negative usage.

## The decision to settle before planting

**Dictionaries are built from live `SELECT DISTINCT`.** Plant a customer in
"Marricopa" and that misspelling lands in the `Service County` dictionary at
the next harvest, and from there into a deployed Data Identification method.

**DECIDED 2026-08-22: contained.** Option 1 below. Planted dirt stays out of
the governed vocabularies; value defects go only in columns nothing governs.

1. **Contained** (chosen). Plant only defects invisible to the governed
   vocabularies: nulls, out-of-range numerics, duplicates, cross-field
   contradictions, bad dates. Plus a small number of value defects in columns
   nothing governs — `email`, `service_zip`, `billing_address` carry no
   dictionary, so a malformed email or a four-digit ZIP costs nothing
   downstream.
2. **Include value dirt.** Richer, and arguably a lesson in itself — "your
   dictionary contains *Marricopa* because your data does" — but it dirties
   the vocabulary the identification demo depends on. If chosen, do it AFTER
   the identification demo is recorded, not before.

## Shape of the build, when it happens

- roughly 20 rows, each carrying ONE named defect, so a finding maps to a row
- an answer-key catalogue: row id → defect → DQ dimension → the check that
  finds it → the remedy
- planted rows sit ABOVE the seeded range so they are distinguishable from
  both the originals and the bulk fill
- the remedy half matters as much as the finding half — the workshop should
  end with the estate measurably better, not just annotated

## Related

The app already computes a DQ score per column with weights for completeness,
uniqueness and validity (Apply page, `Suggested_Quality` /
`Source_Quality_Dims`). A workshop that plants defects and then shows the
score move is more convincing than one that only lists findings.
