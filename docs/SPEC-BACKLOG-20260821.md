# Spec backlog — from the AWC clean walk, 2026-08-21

Eight items found by walking the Glossary → Policy pipeline end to end on the
live Arizona Water estate: repair → re-profile → re-harvest → Dictionary →
Govern → Generate → import → Resolve → Apply → Load → Author → Reconcile →
Deploy → Identify → read back.

**Scope note.** Items 1–4 and 8 are Glossary-side; 5–7 are Policy Generator.
They live in one file on purpose — they are one afternoon's findings about one
pipeline, and several only make sense against the others. PDC-Policy carries a
pointer to this file rather than a split copy.

**Status.** These are notes for specs, not specs. Items 7 and 8 are
investigations with an unconfirmed mechanism and say so; do not implement
against them without reproducing first.

Nine defects found on the same walk were fixed and shipped in Glossary 1.38.36
and Policy 1.10.11 — those are in the two CHANGELOGs, not here. This file is
only what was left undone.

---

## 1 · Remove Draft policies from the Glossary app  — Glossary spec

`engine/policy_draft.py` describes itself as "the first working incarnation of
the Policy Generator". It predates Author and was never removed, so methods can
now be drafted in two places and only one of them is on the contract.

Costs: a second hand-off channel (its MinIO bundle) that Policy never reads;
compounds the "which policy?" confusion already logged in `382d9e3`; and two
implementations of the seed ladder that 1.38.24 already had to pull onto a
shared `policy_seed` module to stop diverging.

Remove the button and the bundle. Author becomes the only place methods are
authored.

## 2 · Seed-readiness panel on Apply  — Glossary spec

Replaces (1) with the part worth keeping: an early warning that the glossary's
EVIDENCE is poor, which is the Glossary app's own business. Not a drafting
surface.

Needs no new model — it is a summary of `detection_intent`, which the Registry
already writes:

> 124 terms · 46 seeded (31 dictionaries, 17 patterns) · 52 mapping-only by
> nature · 26 carry no usable seed — Policy will ask for these back

Would have shown the 2026-08-20 defect loudly: eight concepts backed by one
identical regex is visible in that summary, where "Draft policies produced 88
patterns" reads like success.

## 3 · Make the held-back mapping list actionable  — Glossary spec

`ApplyPage.jsx:946` renders the held-back terms as a read-only `<li>` list and
tells the steward to "set **Map** = Y on the rows you want linked" — with no
control to do it, and the only per-row `Map` cell back on the Review grid among
170 rows. So in practice everyone switches the policy to map-everything.

Make it a checkbox list that writes `Map = Y`.

**Worse than it first looked (found 2026-08-21 while trying to set one):** the
per-row `Map` cell the UI keeps referring to **has no control anywhere in the
frontend** — searched every .jsx/.js. `should_map_link` reads `row["Map"]` and
honours Y/N above every policy including "map everything", `sug_suggest` writes
a default, and the Apply page tells the steward "a per-row Map = Y/N always
wins" — but nothing in the app can write it. The documented override is
reachable only by editing the saved glossary JSON by hand. So the spec covers
BOTH: a Map cell on the Review grid, and the held-back list on Apply made
actionable.

Why it matters beyond convenience: Selective holds back low-confidence,
non-CDE, non-PII terms — and on this estate 32 of those were `mapping_only`,
whose ONLY available governance is the term↔column link. The policy filters
hardest exactly where there is no fallback (the whole water-chemistry panel:
pH, chlorine, lead, copper, turbidity, hardness, TDS).

## 4 · AI-proposed label vocabularies  — Glossary spec (NOT the PG spec)

Decided 2026-08-21: labels are created and stamped by the Glossary app, so this
does not belong in `SPEC-policy-advisor.md`. (The Advisor spec's doctrine 3
already keeps the PG core deterministic via an optional panel — the same
instinct, but labels are not a PG concern at all.)

The four built-in label keys are deterministic and need no AI — `PII Type`,
`access-tier`, `criticality`, `domain` all READ classification the steward set
on Review. That is a feature: a deterministic label is defensible in an audit.

AI earns its place only where there is NO scan signal — `retention`,
`regulatory-basis` — where mapping a term to a vocabulary value is domain
judgment. Same contract as the Advisor: LLM proposes, deterministic core
grounds, steward approves, nothing auto-applies. Note the engine already
REFUSES to invent retention ("a regulatory fact for your organisation") and
emits a note asking for `labels.retention` in the domain pack — the AI proposal
should fill that pack vocabulary, not bypass it.

Constraint to carry into the spec: a label needs <= 6 distinct values or the
engine drops it as "a field, not a label".

## 5 · Efficacy check — does each deployed method still match anything?  — PG spec

The blind spot between the two things that DO exist:

| | subject | answers |
|---|---|---|
| re-profiling | the data | what do these columns contain now? |
| Drift | the deployment | does the method still match the contract? |
| **efficacy** | **the two together** | **does the method still match any DATA?** |

Drift reads deployed methods, never data (`api.py:1068` — governed tags vs the
allow-list, term binding, regex/signature vs seeds, dictionary row counts).
Re-profiling updates the stored profile and says nothing about methods.

So a method whose data moved underneath it reports **clean**: the contract and
the catalog agree with each other, and it matches zero rows forever. Exactly
what would have happened had `^[A-Z]{2}[0-9]{4}$` been deployed for County.

Cheap to build — the stored profile is already in PDC, the seeds are already in
the Registry; it is a join, not a new source of truth. Deterministic, no AI.
Would have caught the numeric threshold, the stale profile, AND today's dead
patterns without anyone having to notice.

## 6 · Identification scope picker, derived from the Registry  — PG spec

Raised 2026-08-21 while running identification off the Deploy page, which has
no scope control at all. The obvious build is a catalog browser (schema ->
table -> tick), and that is the thing NOT to build: PDC already has one, most
of it is irrelevant, and it makes the user answer a question the app can
answer for itself.

The Registry records the source columns every method governs, so the app can
derive the tables the DEPLOYED set can actually tag — for AWC, 9 tables and 4
file objects. Short, entirely relevant, ticked by default, with a count of how
many methods can fire on each:

> awc_operations.customers                 12 methods can fire here
> awc_operations.water_systems              8
> awc-documents/gis/asset_inventory.csv     2

Schema as a grouping header, tables as the selectable rows. No third level.

Why the COUNT matters and not just the list: scoping a run to a table where no
method can fire is the identification twin of the empty prefix — it runs,
reports success, and proves nothing. The count makes that visible before the
job starts rather than after it returns nothing.

## 7 · Patterns cannot score above their name hint — RESOLVED 2026-08-22

Found 2026-08-21 running identification on the AWC estate. 18 of 18 eligible
dictionaries fired and tagged 24 columns. **0 of 11 patterns fired.**

### RESOLUTION

The hypothesis was right and the fix is one config key. PDC's data-profiling
job retains sample values only when asked - `buildSamples`, defaulting to
FALSE for JDBC - and `profile_source` sent `configs={}` there, so every
stored profile carried `sampleValues: []` and regexScore had nothing to
match. Found by diffing workers: object-store discovery ran with
`buildSamples: True`, table profiling with `False`.

Proof, per this item's own protocol: one re-profile of `customers` with the
flag on, then the SAME method at its authored "0.5" threshold fired at 0.79
(regexScore 1.0*0.70 + metadataScore 0.3*0.30 - the arithmetic identifies
both halves). Full-estate re-profile + the complete 40-method run: all 11
patterns tagged their columns at 0.75-0.79. No threshold was lowered.

Fix shipped in Glossary 1.38.38 (`profile_source` sends buildSamples for
JDBC, test-pinned). Note for spec item 5: the efficacy check now has its
second worked example - "11 patterns can never exceed 0.09" was computable
from data already in PDC before any identification ran.

### What the evidence says

A deployed pattern's rule computes
`confidenceScore = regexScore * 0.70 + metadataScore * 0.30`.
Observed score, every time: **0.09** — which is exactly `0.3 * 0.30`, the
metadataScore from the column-name alias hint. The regex half contributes
ZERO.

Measured by forcing the threshold to "0.01" so the rule always evaluates,
then varying the inputs one at a time:

| method configuration                                   | score |
|--------------------------------------------------------|-------|
| as authored (string weights, no profilePatterns)         | 0.09 |
| numeric weights (matching the dictionaries that work)    | 0.09 |
| profilePatterns supplied from PDC's own compactPattern   | 0.09 |
| both together                                            | 0.09 |
| condition `{"==":[1,1]}` (unconditionally true)          | tags at 0.09 |

### What this RULES OUT

- the threshold (0.5 and 0.3 both blocked; PDC's own built-ins ask 0.3)
- string-vs-number weights — Wednesday's coercion lesson does NOT extend to
  the multiplication weights; only comparison operands need strings
- `profilePatterns` / the missing `Value_Signature`
- the regex itself, enablement, term binding, the import, the method name
- authoring generally: no property settable on the method moves the score

### What it points to

PDC appears to score a regex against sampled VALUES held with the column's
stored profile, and this estate's profiles retain none — the first profile
read of the day came back with `sampling` empty. No samples, no regexScore,
so a pattern's ceiling is whatever its name hint contributes (0.3 * 0.30).

That is an ESTATE / PROFILING-CONFIG property, not an authoring bug, which is
why every change to the method left the number identical.

### Next step, on a fresh head

Find whether the JDBC `data-profiling` job takes a config that retains value
samples (`profile_source` sends `configs={}` for JDBC; the object-store path
sends withProfile / headerExists / withDocMetadata). If it does, re-profile
with it and re-run — the score should move without touching a single method.

Do NOT "fix" this by lowering the authored threshold to 0.05: that ships a
pattern that fires on its column name alone, dressed as value detection. It
is the same lie as a shape shared by eight concepts, just quieter.

### Related product gap

Nothing in the app surfaces a method that CANNOT score. Drift reports clean
(contract and catalog agree), the deploy table reports imported+bound, and the
identification run reports COMPLETED. Spec item 5's efficacy check would have
said "11 patterns can never exceed 0.09 against a 0.5 threshold" before the
run, from data already in PDC.

## 8 · The governed vocabulary lost every term's pattern — RESOLVED 2026-08-22

Found 2026-08-21 EOD checking the Dictionary page after installing 1.38.36.

### RESOLUTION

Mechanism confirmed by reproduction and the audit log, fixed, and the data
restored. It was never the approve — `review('term', ..., 'approve')` flips
status only (reproduced clean). The killer was the **Dictionary page's Save**:
`toDoc()` rebuilds every term as `{aliases, sensitivity, tags, layer, status}`
and `POST /api/tagdict` replaced the document wholesale, so the 09:14:55Z
`dictionary.save` (audit-logged, actor catalog.admin, 12 seconds after the
tag approvals) wiped **pattern, definition, category, sources and confidence
from all 125 terms** — far wider than the patterns item 8 noticed.

Fix: `tagdict.replace()` now carries per-term fields the payload does not
carry, for terms present on both sides — engine/evidence.py's doctrine
(absent = not mine to change; present-but-empty = an explicit steward edit).
Pinned by TestWholeDocumentSaveIsNotAWipe. Data restored from the pre-wipe
backup: 122 definitions/categories/confidences/source-lists and the 5
legitimate patterns; the 8 dead junk patterns stayed out.

### What is known for certain

| snapshot                                    | terms | with a pattern |
|---------------------------------------------|-------|----------------|
| before the manual 10:15 clear                | 125   | 13 (8 dead + 5 real) |
| the app's OWN backup, `...backup-20260821-101509` | 125 | **0** |
| backup taken pre-upgrade (14:5x)             | 125   | 0 |
| live now, on 1.38.36                         | 125   | 0 |

Eight terms carrying the dead `^[A-Z]{2}[0-9]{4}$` were cleared by hand with
the app CLOSED, and five legitimate patterns were verified present immediately
afterwards — `Account Number`, `Phone`, `Meter ID`, `Asset ID`, `Segment ID`.
The app was then reopened and the steward clicked **Approve all** on the
pending queue. The app's own pre-write backup is stamped 10:15:09 and already
has zero. So the app rewrote the dictionary at that moment and dropped the
remaining five.

**1.38.36 is exonerated** — the pre-upgrade backup already showed zero, and the
app was 1.38.34 at the time.

### What is NOT known

The mechanism. `review(kind, names, 'approve')` documents itself as flipping
status only, and `accrete` SETS `pattern` from the row's `Value_Pattern`
rather than clearing it (tagdict.py ~line 849 rebuilds the entry wholesale).
Neither obviously drops the field. Reproduce before theorising: seed a pending
term carrying a pattern, approve it, diff the entry.

### Why it is item 8 and not a panic

The detection seeds that become deployed Data Patterns come from the REVIEW
ROWS (`Value_Pattern`), not from the dictionary. Those rows were intact, which
is why Deploy still authored 11 patterns with correct regexes over an empty-of-
patterns dictionary. Today's pipeline was unaffected end to end.

What is lost is the governed vocabulary's own record of the shape. That
matters for the **pack flywheel** — the domain pack that carries learned seeds
to the next estate. Confirm what `packgen` actually reads before relying on a
pack export; if it reads the dictionary rather than the rows, an exported pack
now ships without shapes.

### Process note worth keeping

This was reported to the user as "the 5 real patterns survive" — true when
measured, false ten minutes later. A point-in-time read of state the app also
writes is not a settled fact. Re-check after any steward action that touches
the same store.

## 9 · FUTURE PROJECT — a query builder driven by the Registry

Raised 2026-08-22, parked deliberately: finish the three-app pipeline first.
This is a NEW TOOL, not a fix to an existing one.

### The thesis

`awc_operations` declares **no constraints at all** — no primary keys, no
foreign keys (verified 2026-08-22). A conventional query builder that
introspects a schema has nothing to work with, which is normal for anything
loaded by ETL.

The glossary asserts the relationships the database never declared. **31 of
124 concepts span more than one column**, and each shared term is a join edge:

> Customer Type -> tiered_rates · customers · customer_billing_summary
> System ID     -> tiered_rates · pinal_valley_pressure.json · all_systems_snapshot.json
> Base Charge   -> tiered_rates · monthly_usage

Edges no schema introspection could find, because they cross Postgres and JSON
in object storage. **The catalogue is the join graph the database does not
have.** That is the whole idea.

### What the Registry already provides

`sources` (term -> columns), `source_types` (physical types), `sensitivity`,
`definition`, `detection_intent`, stewards. The `keys` field exists in the
schema but is EMPTY on all 124 concepts here — because the estate declares no
keys to harvest. Do not build on `keys`.

### Shape

1. pick TERMS, not tables — the user works in business language
2. resolve to columns, disambiguating a term that spans several
3. derive joins from shared terms
4. emit a PLAN, not just SQL — cross-source cannot be one statement
5. carry provenance into the result: definition, steward, DQ score, so the
   answer arrives with its own health warning

For (4), look hard at **DuckDB**: it attaches Postgres and reads CSV/JSON from
S3-compatible storage in one query, which collapses the orchestration. The
pump-vs-unpaid-bills question becomes a single statement.

### The hard problem — solve this FIRST

**Not every shared term is a safe join.** `System ID` is an identifier and
joining on it is correct. `Customer Type` is also shared across three tables,
and joining on it fans out catastrophically — it is an attribute with three
distinct values.

The tool must tell identifying terms from attribute terms. Inputs are
available (profiled cardinality, `Value_Kind`, detection intent, name shape),
but getting it wrong silently returns millions of rows: the exact class of
confident-wrong answer this whole programme exists to prevent. **Refuse an
ambiguous join rather than guess.**

### Doctrine

Deterministic core builds the query from the term map; an optional LLM front
end only translates the question into a term SELECTION. Same split as the
Policy Advisor — the LLM proposes, the deterministic core grounds.

### First experiment, when it starts

A CLI taking two or three term names and emitting the plan plus the SQL. An
hour's work against the Registry tells you whether join-from-terms holds up on
real data.

---

## Open item, not a feature

**Four stores hold the same evidence**, each with its own copy and its own
refresh trigger: PDC's stored profile (profiling job), the glossary rows
(re-harvest), the tag dictionary (Sync from Review), the Registry (Generate,
then Resolve). 1.38.36 gave the rows and the dictionary ONE shared
CAPTURE/REFRESH rule, but it did not collapse the copies. Every one of today's
staleness bugs lived in the gap between them. Architectural, bigger than a
spec item — raise with the user before proposing anything.
