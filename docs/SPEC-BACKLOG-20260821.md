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

## 1 · Remove Draft policies — RESOLVED (built 2026-08-24, rides the next release)

Executed to the plan below. The card, /api/draft-policies, the job twin,
the job-zip route and the drafted-policies lab export are gone; Author is
the only place methods are authored. The flip workflow lives on the
REVIEW page (DETECTION toolbar group): "star Flip N recommended" flips
every row bearing a recommended term to Auto (duplicate-named rows
included - findIndex flipped the wrong sibling, caught live), "M
shapeless -> Mapping-only" declares free-text skips quiet; both driven by
/api/seed-readiness's flippable_terms / quiet_candidates, no draft run
needed. DQ expectations kept their own export: POST /api/dq-expectations
(Quality/*.json + INDEX + README) with a button on the Generate card.
The "Drafted policies bundle" left the estate-report contract.
engine/policy_draft.py retained for dq_rules_from_rows and the report's
detection-coverage block. Original decision + plan kept below.

## (original) 1 · Remove Draft policies from the Glossary app  — Glossary spec

**DECIDED 2026-08-23 (user): the flip workflow moves to the REVIEW page.**
Execution plan, sized a careful half-day — the draft card is not just a
button, it hosts live machinery:
- ★ Flip all recommended + per-term "→ Auto" move to Review's Detection
  filter row; `auto_candidate` comes from the seed ladder without drafting
  (the /api/seed-readiness endpoint already walks it — extend it to return
  the flippable term list).
- The skip-groups' "→ Mapping-only" quiet-in-place flips move with them.
- Decide the DQ expectations' fate (Quality/ in the bundle) — either their
  own export on Apply or retired with the bundle; do not lose them silently.
- Delete: the card, /api/draft-policies + job twin, the MinIO bundle path,
  drafted-policies zip handling; sweep GUIDE/REFERENCE/WALKTHROUGH.
- policy_draft.py: keep only what policy_seed does not already own; the
  engine's flip logic (auto_candidate) moves to policy_seed if not there.

`engine/policy_draft.py` describes itself as "the first working incarnation of
the Policy Generator". It predates Author and was never removed, so methods can
now be drafted in two places and only one of them is on the contract.

Costs: a second hand-off channel (its MinIO bundle) that Policy never reads;
compounds the "which policy?" confusion already logged in `382d9e3`; and two
implementations of the seed ladder that 1.38.24 already had to pull onto a
shared `policy_seed` module to stop diverging.

Remove the button and the bundle. Author becomes the only place methods are
authored.

## 2 · Seed-readiness panel on Apply — RESOLVED (built 2026-08-23, rides the release after 1.38.41)

POST /api/seed-readiness + a card above Generate: kept terms · seeded
(patterns/dictionaries) · mapping-only (with the ★ flippable count) ·
no-usable-seed (collapsible list with reasons), and shared content shapes
surfaced loudly with the terms that claim them. Same seeds_for_row ladder
the Registry and drafter share; summary only, nothing decided. Original
note kept below.

## (original) 2 · Seed-readiness panel on Apply  — Glossary spec

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

## 3 · Make the held-back mapping list actionable — RESOLVED (1.40.0)

Both halves shipped: the Review row editor gained a MAP segment
(Policy decides / Y / N — the documented always-wins override finally has
a control), and the Apply held-back list gained a per-term Map = Y button
that patches every row bearing the term and re-pulls. With 1.38.41's
Selective auto-exempt (the policy half), the Map-everything workaround is
retired. Original note kept below.

## (original) 3 · Make the held-back mapping list actionable  — Glossary spec

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

**The policy fix (added 2026-08-23, from the user asking which mode is
"better"):** Selective should AUTO-EXEMPT `mapping_only` terms. For a term
with a detectable shape, the link is one control among several; for a
mapping-only term the link IS the control, so a relevance gate should never
be what removes it. With that exemption Selective becomes safe out of the
box, and the Map-everything workaround stops being necessary on estates
where noise matters. (Note also: the mapping policy does not affect Registry
completeness — a misconception worth a line in the docs. It affects the
term-column links and which concepts get term_id backfill; seeded concepts
map under Selective anyway because profiled evidence earns the confidence.)

## 4 · AI-proposed label vocabularies — RESOLVED (1.40.0)

Built to the decided contract: POST /api/labels/propose-vocab (the model
proposes from the estate's own document classes/categories, grounded by
labels.validate_vocab — <= 8 entries, <= 6 distinct values), the steward
edits and POST /api/labels/adopt-vocab writes labels.<family> into the
domain pack (backup taken), where the engine — which still refuses to
invent retention — derives it on every scan. Govern labels card carries
the propose/edit/adopt panel. Original note kept below.

## (original) 4 · AI-proposed label vocabularies  — Glossary spec (NOT the PG spec)

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

## 5 · Efficacy check — RESOLVED (Policy, built 2026-08-23, rides the next release)

POST /api/pdc/efficacy + a card on the Drift page: every authored seed
evaluated against the STORED profile samples identification scores with
(entities/filter/profiling-info, one call per source table/file). Verdicts
live (rate) / dead (samples exist, zero match, replacing values shown) /
no_samples (re-profile first) / unresolved. Deterministic join of Registry
seeds and PDC profiles. Original note kept below.

## (original) 5 · Efficacy check — does each deployed method still match anything?  — PG spec

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

## 6 · Identification scope picker, derived from the Registry — RESOLVED (Policy 1.10.15)

Shipped 2026-08-23 (88220c9) as "Scope from Registry" on the Deploy page:
the loaded Registry's governed tables and file-side CSVs resolve to entity
ids in one click (governed-column counts shown; sources not yet registered
in PDC are listed, not dropped), and the Report page's identification
read-back prefills its table list from GET /api/scope-sources. The
per-source "N methods can fire here" count below remains a nice-to-have.
Original note kept below.

## (original) 6 · Identification scope picker, derived from the Registry  — PG spec

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

## 9 · PDC Query — AT PROTOTYPE (0.2.0, 2026-08-24)

github.com/jporeilly/PDC-Query. --ask resolves a natural question against
the Registry (terms + dictionary-VALUE phrase filters), joins ONLY on
identifying shared-term edges, refuses with reasons, and --run executes
read-only. Proven on the live Arizona registry (customers <-> billing
summary on Account Number, 'At Risk' filter); execution pends the estate
VM. Next: profile-cardinality into the classifier (settles UNCLASSIFIED),
synonym grounding via the docs-chat pattern. Original vision kept below.

## (original) 9 · FUTURE PROJECT — PDC Query: questions answered through the catalogue

Raised 2026-08-22, parked deliberately: finish the three-app pipeline first.
This is a NEW TOOL, not a fix to an existing one.

### Named and extended 2026-08-22

The user named it **PDC Query** and added the requirement that makes it a
product rather than a convenience: results return WITH the catalogue's trust
context. Not `213 customers` but 213 customers plus, per column touched: DQ
score, dictionary coverage, profile freshness and sample presence, and any
reconciliation the join needed ("Water System spans two spellings across two
sources"). The answer arrives wearing its own health warning — and PDC is
uniquely placed to attach one, because every input already sits in the
catalogue. Each footer line is justified by a defect this walk actually hit:
sampled enums at 16% coverage, sample-less profiles, case variants, the
Pinal Valley naming mismatch.

Suite position: fourth app, port 5003, same stack and doctrine — and the
THIRD consumer of the Registry contract (Policy authors detection from it,
Insights reads the estate's aggregates, Query builds joins from it). No new
source of truth.

Acceptance tests already exist: the catalog workshop's eight
"CATALOGUE, THEN QUERY" questions (AWC-Catalog-Value-Workshop-20260822.docx),
Q16-Q19 especially. Every metric in the footer carries its as-of date - a DQ
score from a stale profile is the stale-profile bug wearing a dashboard. Two
scope traps declared at birth: it is not a chart tool, and it is not a
chatbot.

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

## 10 · Docs-grounded chat — RESOLVED (built 2026-08-24, rides 1.39.0)

Built to the five doctrines below. engine/docchat.py (BM25 over heading
chunks of the shipped docs, indexed at startup from the installed build's
own files - stage-app ships docs/, so the release-time index step collapses
to the same guarantee), POST /api/ask, an "Ask the docs" drawer in the
shell, and tests/test_docchat.py with 8 retrieval evals including the
canonical buildSamples question. Live-verified grounded + cited through
the server with the configured model; without a model it is a cited doc
search, stated honestly. Original spec kept below.

## (original) 10 · "How do I?" — a docs-grounded chat in the Glossary Generator

Requested 2026-08-22: the app is complex, and a chat window should answer
product questions FROM THE DOCUMENTATION with detailed responses.

Why this app is unusually well-placed: the corpus is versioned with the code,
test-pinned (the Under-the-hood explainers are guarded because losing them
once cost a release), and ships inside the app - GUIDE, WALKTHROUGH,
REFERENCE, README and a narrative CHANGELOG. The Ollama runtime and the
online/offline handling already exist.

Design decided in discussion:
1. **Grounded-or-refuse.** Answers only from the shipped docs, every answer
   cites its section, and "the documentation doesn't answer this - nearest
   section is X" is the honest miss. The LLM never invents behaviour.
2. **Index built at RELEASE time** by the train, chunked by heading, stamped
   with the app version - so answers describe the installed build, and
   index-version != app-version is a drift warning. CHANGELOG chunks let it
   answer "since when?".
3. **Context-aware seeding** - the page the question is asked from boosts its
   own docs.
4. **Retrieval stays boring**: BM25 over heading chunks, deterministic and
   dependency-free; Ollama embeddings optional; with no model at all the
   feature degrades to a decent doc search rather than vanishing.
5. **Eval tests from birth**: a canned QA set pinned in the suite ("why do my
   dictionaries fire but not my patterns?" must retrieve the buildSamples
   entry, cited). A docs chat without evals degrades silently.

Fits as a 1.39.0 feature: /api/ask + a chat drawer in the shell + the train
index step + evals. Build AFTER the clean walkthrough.

## 11 · Factory reset loses to the running app's memory — RESOLVED 1.38.39

Fixed 2026-08-23 (d04f4b0): the server refuses glossary saves for 10s after
a reset (an in-flight autosave can no longer resurrect the estate), the
reset reply re-lists the state directory (survivors surface as `remaining`
instead of hiding behind `deleted[]`), and the UI reports a dirty wipe
instead of declaring success — no auto-reload until the directory verifies
clean. Original diagnosis kept below.

## (original) 11 · Factory reset loses to the running app's memory

Field-caught 2026-08-23, opening the clean walk. Factory reset deleted its
targets — and the state directory was NOT day-zero afterwards:
`glossaries.json` (1.7 MB, every saved glossary) and `estate_receipts.json`
were back, and the Connect card still showed the pre-reset PDC base URL.

The endpoint deletes the files and clears the DICTIONARY cache
(`tagdict._DICT = None`), but nothing clears the frontend workspace — which
still holds all the rows — and its autosave writes `glossaries.json` straight
back. The UI's `usePersistentState` cache (an in-memory Map) likewise
repaints pre-reset values until the process dies. The docstring says "close
and relaunch afterwards"; the resurrection happens before the user can.

The narrower form of this was fixed once before (CHANGELOG: "the next
autosave would have written the deleted glossary back"). Fix shape: the
reset response should make the FRONTEND forget too — clear the ui cache and
`window.location.reload()` on success — and the server should drop every
in-memory store it owns (workspace, receipts), not just the dictionary.
Then verify by listing the state dir, not by trusting the deleted[] reply.

Workaround used on the walk: close the app first, delete the leftovers by
hand, relaunch.

---

## Open item, not a feature

**Four stores hold the same evidence**, each with its own copy and its own
refresh trigger: PDC's stored profile (profiling job), the glossary rows
(re-harvest), the tag dictionary (Sync from Review), the Registry (Generate,
then Resolve). 1.38.36 gave the rows and the dictionary ONE shared
CAPTURE/REFRESH rule, but it did not collapse the copies. Every one of today's
staleness bugs lived in the gap between them. Architectural, bigger than a
spec item — raise with the user before proposing anything.

## 12 · Install/uninstall progress bar — RESOLVED (Glossary 1.40.0 + Policy 1.10.17)

The bar runs as a MARQUEE during the delete phases (install pre-clean of
the old vendored Python + the whole uninstall) and returns to the honest
byte-weighted bar for extraction — a determinate bar cannot be honest
about a phase NSIS gives no weight. Implemented in both apps' custom NSIS
templates; degrades harmlessly if the control lookup fails. Insights
still pending the same port. Original diagnosis kept below.

## (original) 12 · Install/uninstall progress bar sits still during the delete phase

Field-caught 2026-08-23, twice (uninstall, then the 1.38.40 upgrade with a
screenshot). CORRECTED DIAGNOSIS: the detail pane DOES stream one
"Delete file: …" line per file — the removal is not one silent RMDir — but
the NSIS gauge weights progress almost entirely by EXTRACTION BYTES, and
Delete instructions carry ~zero weight. Upgrading first deletes the old
vendored Python tree (thousands of files, most of the wall time) with the
bar parked near 0%, then the bar leaps during extraction. Stock
Tauri-generated NSIS template behaviour; an honest gauge needs a custom
installer template (tauri bundle.windows.nsis.template) that adds
progress weight to the cleanup loop. Cosmetic; the streaming detail lines
are the real liveness indicator meanwhile. Applies to all three suite
apps (shared installer recipe).

---

# Walk-log — clean walkthrough, 2026-08-24 (1.40.0 / 1.10.17)

Field catches from the walk, batched for 1.40.1 unless marked fixed.

## W1 · The docs chat's corpus never shipped — FIXED (dd3eb21)

The installer staged only the runtime; the packaged index was empty and
every question answered "the documentation doesn't appear to cover this"
("not much good if it cant even answer this question"). stage-app.ps1 now
stages docs/ (minus diagrams/) + README.md; an empty index says
"installation defect, not a docs gap"; three pins added.

## W2 · Harvest-from-PDC does not complete enums — RESOLVED (1.41.0)

PDC's stored profile serves SAMPLED values (sampleValues), so 13 of the
walk's vocabularies landed short (Maricopa missing from both county
columns, Fair/Good from the quality ratings, two systems from Service
Area System...). The 1.38.39 completion (_complete_enum, SELECT DISTINCT
<= 48) runs only on the DIRECT-scan path. Fix: when a saved DB connection
covers the harvested source, the harvest path completes flagged enums the
same way; when none does, the readiness panel should mark sampled enums
as UNVERIFIED. Walk remedy: rows completed by hand from live DISTINCT
(scripted, app closed, backup taken).

## W3 · The direct scan cannot refresh evidence — RESOLVED (1.41.0)

SourceConnections' scan('add') lands rows WITHOUT the refreshEvidence
option, so evidence merges fill-only — a re-scan cannot overwrite a
stale/short enum already on the grid. The Connect harvest has the
"Refresh value evidence" checkbox; the Schema/Files scan needs the same.

## W4 · Tag sync: the AI pass never revisits tags — RESOLVED (1.41.0)

Definition and Purpose get enrichment; Suggested_Tags stay frozen
scan-time heuristics — which is how Base Charge wore pii + compliance +
water-quality-compliance + a category echo. Design (decided with the
user mid-walk): (1) deterministic base — drop category-echo and
off-vocabulary tags, keep evidence-earned ones (pii/cde); (2) AI
reconciliation as CLOSED-SET selection from the governed vocabulary only,
<= 4 tags, a stated reason per drop, judged against the NEW definition;
(3) lands as pills, steward accepts, nothing auto-applies; (4) runs after
Def/Purpose settle inside the AI pass. Payoff: cleaner applyBusinessTags
on methods, cleaner steward stamps, honest label derivation.

## W5 · Context-blind PII: an asset's street name is not PERSONAL_NAME — RESOLVED (1.41.0)

Field: "Street Name" in Infrastructure and Assets (pipe/asset GIS data)
classified PERSONAL_NAME, sensitivity HIGH, tags direct-identifier;
privacy - "its not pii, its a street name". The PII heuristic keys on the
column NAME with no context. Fix folds into W4, upgrading it from tag
sync to CLASSIFICATION SYNC: the reconciliation agent judges tags + PII
category + sensitivity together against the enriched Definition (which
here plainly describes asset geography), and the deterministic half gains
context signals the scanner already has - the settled category, sibling
columns (latitude/longitude/material = asset context; email/customer_id =
person context), and the source type. A *_name column defaults to
PERSONAL_NAME only in person context. Walk remedy: steward corrected the
row (LOW, no PII, location tags).

## W6 · Unit suffixes: always "(unit)" lowercase — RESOLVED (1.41.0)

Convention (user, mid-walk): units in term names are lowercase in
parentheses - (psi), (ppm), (ntu). This walk's namer emitted Title-Cased
bare units instead: Chlorine Residual Ppm, Copper Ppm, Hardness Ppb,
Lead Ppb, Total Dissolved Solids Ppm, Turbidity Ntu (while Flow (gpm) /
Pressure (psi) came out right). Fix: the namer canonicalises a trailing
unit token from the existing UNIT_NAME list (sug_shared) to " (unit)"
lowercase at suggest time; pin with the six field cases. Walk remedy:
steward renamed the six in the grid.

## W7 · The Detection flips are missing from the flow explanations — RESOLVED (1.41.0)

Field: "do I now click on Flip 17 recommended then shapeless
Mapping-only? if so these steps need to be added to the flowchart
explanations". The flips moved to Review (backlog 1) but the page's flow
story never learned: the numbered AI AGENTS strip ends at 4 - AI advise,
the "How terms are defined & built" explainer and the Home flowchart
don't mention the DETECTION toolbar group. Fix: a "5 - Detection" entry
on the strip (deterministic, not AI - say so) or an explicit line in the
explainer + Home card: the ORDER matters and must be taught: resolve
the duplicate clusters FIRST (merges consolidate rows, disambiguations
settle names), THEN flip the starred measures to Auto and declare
shapeless skips mapping-only (the recommendation lists recompute live, so
post-settlement counts match the grid that ships), THEN Dictionary.
In-app guidance, GUIDE and WALKTHROUGH all updated together.

## W8 · The Tags panel offers Approve all but no Retire all — RESOLVED (1.41.0)

Field: 11 pending tags, ALL table-name echoes that should die - and the
only wholesale control is "Approve all" ("pretty misleading as there's a
tendency to approve all"). An asymmetric wholesale control IS a
recommendation. Two fixes:
- Retire all beside Approve all, with the same respect for the core six
  (they refuse individually and must refuse wholesale, saying so);
- the deeper cut, folded into W4's deterministic rule: STOP MINTING
  table-name echo tags as candidates at all - a tag that repeats the
  source table is provenance, not classification, and the suggester
  should never propose it into the vocabulary (same treatment as the
  category echoes). Walk remedy: retired the 11 individually.

## W9 · The fold advisor proposes folding numbered series into themselves — RESOLVED (1.41.0)

Field: 30 fold candidates, EVERY one "fold Tier N X into Tier M X" /
"Usage Tier N into Tier M" at 88-96% name similarity - a numbered SERIES
misread as aliases, because string similarity does not know that a
differing digit is semantically decisive. And the advice lands at the
Dictionary gate when term identity was already settled at Review ("this
should have been previously advised when approving the Terms").
Three cuts:
- SERIES GUARD: names identical except for a numeric token are a series,
  never fold candidates - kills all 30 here deterministically;
- the fold advisor's surviving candidates move INTO Review's advise
  stage (one place where term identity is decided), leaving the
  Dictionary gate to vocabulary approval only;
- wholesale symmetry (W8's rule): wherever fold/approve lists render,
  Dismiss all ships beside Fold/Approve all. Walk remedy: dismissed all
  30 by hand.

W9 addendum: the 88% oddballs traced to a NAMER inconsistency - the
splitter expanded tier2/3/4_to_gallons to "Tier N To Gallons" but left
tier1_to_gallons as "Tier1 To Gallons" (no space). Series-token splitting
must be consistent across the series ("tier1" -> "Tier 1" like its
siblings); pin with this case. Walk remedy: renamed the one term.

## W10 · Roster expertise from Keycloak user attributes — RESOLVED (1.41.0)

Field: "is there anywhere in Keycloak to augment the user with a
description of their role that could be used to add expertise?" There is:
USER ATTRIBUTES (Users -> user -> Attributes; on Keycloak ~24 enable
Realm settings -> Unmanaged attributes first). Two halves:
- the roster fetch reads attributes (expertise, title, department) and
  prefills the Expertise column - hand-typing and the LLM suggestion stay
  as fallbacks, an attribute always wins;
- the lab cast script (PDC-Scenarios load-pdc-users.ps1) sets the
  attributes at user-creation time so a fresh estate arrives with
  expertise pre-filled. Groups-as-expertise noted as the alternative;
  role descriptions rejected (authz semantics, wrong home).

## W11 · Uniform expertise suggestions carry no information; the roster wants autosave — RESOLVED (1.41.0)

Field, on Govern: Suggest expertise (LLM) gave every person the IDENTICAL
expertise string, so auto-assign had nothing to distinguish stewards and
"no-one picked up customer-management". Two cuts:
- UNIFORMITY GUARD: when the model's suggestions are (near-)identical
  across people it has learned nothing - detectable deterministically;
  say "no distinguishing evidence - set expertise by hand or via
  Keycloak attributes (W10)" instead of pasting the category list onto
  everyone. With W10's attributes present, the attribute wins and the
  LLM never runs for that person.
- ROSTER AUTOSAVE ("can this page save state"): the roster edits sit
  behind a manual Save roster banner while the grid autosaves on every
  patch; same debounced treatment here (Save stays as the explicit act
  for removals).

## W12 · Governance summary: the frozen-looking cap and the generic pack — RESOLVED (1.41.0)

Field: "not sure if this is refreshing" - it was (disk newest == card),
but two displays undermine trust:
- the audit counter caps at 300 (ring buffer) and sits there forever;
  label it "300 (last 300 kept)" so a maxed counter reads as rolling,
  not frozen;
- Domain: generic - export-pack/adopt never stamps the company into the
  pack (domain_pack.json: domain=generic, company=None). Carry the
  company name from settings into build_pack and the adopt path, and
  show it on the summary card.

## W13 · The readiness shared-shape amber cries wolf on name-anchored seeds — RESOLVED (1.41.0)

Field: the card flagged ^-?[0-9]+(\.[0-9]+)?$ x10 - the ten flipped
measures sharing the numeric SANITY shape, which is by design: a
name-anchored rule's content regex is only the sanity half of the
name-AND-shape conjunction. An always-amber trains stewards to ignore
ambers. The check should exempt seeds with identity=column_name (or list
them separately as "shared sanity shape - name-anchored, safe"),
reserving the warning for genuinely ambiguous content claims like the
ZIP pair.

## W14 · The readiness no-seed bucket counts expected populations as amber — RESOLVED (1.41.0)

Field: "dont really need to include the tables, etc?" - the 19 "no
usable seed" terms were ALL expected cases, each saying so in its own
reason text: table-level Record terms (9, glossary-by-design), document
terms (5, vocabulary-dictionary governed), link-tagged identifiers (5).
Actionable count: zero; badge: amber 19. Design (user's refinement):
GROUP the list BY REASON - each group headed by the explanation and its
count ("table-level term - no physical column to identify (9)",
"document term - identified by vocabulary dictionaries (5)", "tagged via
the term-link (5)"), terms listed inside, groups collapsed by default -
the reason is stated once instead of nineteen times. The amber badge
counts ONLY the genuine-evidence-gap group; expected groups render
neutral. An amber that is always amber trains stewards to ignore ambers
(W13's rule, applied to its neighbour).

## W15 · The Generate card wears the previous run's success after the grid changes — RESOLVED (1.41.0)

Field: five row fixes then "regenerated" - but the registry mtime never
moved: the card was still showing the earlier generation's stats/archive
line, which reads exactly like a fresh success, and the second Generate
was never actually clicked (or its absence was invisible). The estate
report already solves this shape with per-artifact STALE banners
("REGENERATE: the review was saved after this export"). The Generate
card gets the same: when the workspace's savedAt is newer than the shown
generation, banner the result as stale and re-label the button
("Regenerate - the grid changed"). Same treatment for the DQ
expectations button's implicit currency.

## W16 · Editing a derived tag silently reverts — RESOLVED (1.41.0)

Field: the steward removed 'pii' from both Base Charge rows twice; the
Registry re-minted it each Generate because the rows still carried
PII_Category=FINANCIAL and the bridge derives the tag from the
classification. Correct derivation, invisible mechanics. Fix: the grid's
tag editor knows which tags are DERIVED - removing one either clears its
source (with a confirm naming it: "also clears the FINANCIAL PII
classification?") or refuses with the reason, never accepts an edit that
the next Generate undoes.

W16 addendum: the loop's root was FINANCIAL wearing two hats on one row -
a tag named 'financial' and a PII classification named 'FINANCIAL'.
"Clear FINANCIAL" removed the (correct) tag while the classification
kept deriving 'pii'. The row editor should render the PII classification
visibly AS the source of the derived pii tag (one control, labelled "PII
classification - derives the pii tag"), so the two hats cannot be
mistaken for each other.

## W17 · The PII classification cannot be edited - the Map cell all over again — RESOLVED (1.41.0)

Field, after two futile correction loops on Base Charge: PII_Category
renders as a read-only badge under Sensitivity; its only writer is
accepting an AI proposal. Yet it drives the derived pii tag, the PII
Type label and the readiness counts - so a steward literally cannot
execute "this is not PII" (Street Name, Site Name, County, Unpaid
Accounts all still carry their classifications despite this morning's
"corrections"). Fix: an editable PII selector in the row editor (with a
none option), labelled as the source of the derived pii tag (W16's
labelling), same pattern as the Detection and Map segments. Walk remedy:
state surgery over the W5 list, app closed.

## W18 · Flipping to Auto silently costs the term its link exemption — RESOLVED (1.41.0)

Field: Selective held back 38 terms including every starred flip (Lead,
Turbidity, pH...), Asset ID, Segment ID, the Status family and Payment
Status (CBS). The mapping-only auto-exempt keys on
Detection_Intent == mapping_only - so the star flip, which CLEARS that
intent to mint a name-anchored method, also silently removes the link
guarantee, and a Low-confidence flipped term lands held-back. A flip
adds detection; it must never subtract linkage. Fix: should_map_link
also exempts rows whose seed is name-anchored (identity=column_name) -
"was mapping-only by nature" survives the flip. Walk remedy: switched to
Map everything (defensible here: a fully reviewed 142-term glossary IS
the relevance gate).

W18 addendum: rename the policy options when the fix lands. "Map
everything (legacy)" mislabels the correct choice for curated estates -
the steward's review IS the relevance gate there ("so it is legacy as
that includes LOW conf?"). Honest labels: "Map all kept terms - the
review already decided relevance" vs "Selective - hold back
low-confidence extras (large/noisy estates)"; neither is legacy, they
serve different estate classes. The hint text says which class you are
in.

## W19 · A drifted label family needs a managed re-mint, not a manual dance — RESOLVED (1.41.0)

Field: the domain taxonomy changed ('&' -> 'and', +Billing and Revenue),
and the correct-by-docs remedy - delete the family in PDC, re-Create -
raced the stamp: the delete landed after Create, the stamp wrote domain
values against the dead definition id, and ~160 columns now carry an
ORPHANED assignment no UI renders. Three cuts:
- Create detects a family whose PDC vocabulary differs from the derived
  one and offers "re-mint domain (values changed)" - delete + recreate +
  invalidate the stamp plan, one button, no PDC-side manual step;
- the stamp validates each definition id EXISTS at write time and
  refuses the family with a reason instead of writing orphans;
- a cleanup pass (or the stamp's merge) strips assignments whose
  definition id no longer resolves. Walk remedy: re-create + re-stamp +
  scripted orphan sweep.

## W20 · The delete marquee should be a determinate deletion bar — RESOLVED (1.42.0)

Field (2026-08-24, installing 1.41.0): "you dont need to display every
file being deleted, cant the progress bar just show the progress of the
deletion instead of pulsing across, same as install progress." The
1.41.0 marquee was honest about NSIS's weightless deletes but showed no
progress. Fix (both cuts, installer.nsi template):
- SetDetailsPrint textonly around the delete phases - the "Delete file:"
  torrent stays out of the details list; the log records one line and
  the status line counts;
- StepDeleteChildren macro replaces the marquee: the bulk of the tree
  (python\Lib\site-packages, one directory per package) deletes one
  child per instruction while the macro drives the bar itself - count
  children, take the bar (range 0..count), step per deletion, hand it
  back to NSIS's 0..30000 scale after. NSIS's own updates round to no
  message during the phase, so the takeover holds; degrades harmlessly
  if the control lookup fails. Port to Policy's template with the next
  Policy batch; Insights when its marquee port happens.

## W21 · Upload a file to the docs chat — check my JSONL for errors — RESOLVED (1.42.0)

Field (2026-08-24): "it would be great to be able to upload documents to
the chat. lets say i want to check my JSONL for errors." Design, two
cuts, deterministic first:
- a "Check a file" upload on the Ask-the-docs drawer: an uploaded .jsonl
  runs the IMPORT-CONTRACT VALIDATOR - per-line JSON parse (line number
  on failure), required keys, duplicate _ids, term->category integrity,
  ampersand names (the PDC search killer), category drift vs the current
  grid - a findings list with line references, no LLM required;
- the chat then answers questions ABOUT the file: the validator's
  findings plus the offending lines join the doc excerpts as context,
  grounded-or-refuse retained (the model cites [YOUR FILE line N] like
  it cites [GUIDE - section]). CSV/json variants follow the same shape.
Note: Generate's preflight already validates what THIS app exports; the
upload covers hand-edited or foreign files before they hit PDC.

## W22 · Docs-chat retrieval: hybrid embeddings YES, RAG database NO (decision)

Field question (2026-08-24): "would it be better to add a RAG database
and embed all documents there?" Decision: the corpus is 627 chunks
across five markdown files (<1MB) rebuilding in memory at startup - a
vector DATABASE adds a dependency, a store to version and build/index
drift for zero gain at this scale. The miss class embeddings actually
fix (vocabulary mismatch: "pattern" vs "Data Patterns") was mostly
closed deterministically alongside this note (plural fold, question-word
strip, CHANGELOG deweight x0.6). IF quality still disappoints on the
installed build: HYBRID, NO DB - embed the chunks via the existing
Ollama (nomic-embed-text) at startup, vectors in memory, cosine fused
with BM25 (reciprocal-rank), and MANDATORY degrade to pure BM25 when
Ollama is offline (the packaged app must answer without a model).
Uploaded-file checking (W21) stays deterministic either way.

## W23 · Docs chat reaches academy.pentaho.com + docs.pentaho.com (GitBook MCP)

Field (2026-08-24): "can we hook it into the academy.pentaho.com &
docs.pentaho.com Gitbook MCP server." Design: the chat becomes an MCP
CLIENT over streamable HTTP - GitBook auto-hosts an MCP endpoint per
published site - calling each site's search tool and folding the top
results into the excerpt list as [docs.pentaho.com - <title>](url),
cited like any doc section. Constraints that shape it:
- OPT-IN per source on Settings (External documentation sources), OFF by
  default - the packaged app must stay fully functional air-gapped;
- hard timeout (~3s) and silent degrade to the local corpus when the
  site is unreachable - never a hung answer;
- external excerpts are clearly labelled in citations (the steward must
  see which facts came from the product docs vs this app's own);
- responses cached per question for the session (GitBook search is
  rate-limited);
- the grounded-or-refuse contract is unchanged - more excerpts, same
  rules. Implementation: a ~60-line JSON-RPC client in engine/docchat.py
  (initialize -> tools/list -> tools/call search), no SDK dependency.
  Verify the exact MCP endpoints from a machine with internet before
  building (GitBook's URL shape has changed once already).

## P1 · Policy authoring's shared-shape warning cries wolf on name-anchored methods

Field (2026-08-25, Policy half of the clean walk, Author card): the red
"2 content shape(s) are claimed by more than one method" block led with
the 9 flipped measures sharing the numeric sanity shape - which is BY
DESIGN: name-anchored rules match column name AND shape, so the shared
sanity half identifies nothing on its own and the warning's own small
print already says so. W13's rule, unapplied on the Policy side: an
always-amber trains stewards to ignore ambers. Fix: split the block -
name-anchored claimants render as a NEUTRAL "shared sanity shape -
name-anchored, safe (9)" line; the red warning is reserved for shapes
shared by methods with NO name anchor to disambiguate them. Verify
whether the ZIP pair carries name hints; if so it moves to the neutral
line too and the red block disappears on this estate entirely.

## P2 · The unresolved-ids banner prescribes action when no method is affected

Field (2026-08-25, Author card): "1 concept(s) have no term id yet -
methods for them bind by name only. Import the glossary into PDC, then
Reconcile" - but the Author list showed EVERY method bound by id: the
unresolved concept is one of the 93 mapping-only concepts, which author
no method at all, so nothing binds weakly and the prescribed remedy is
moot. Fix: the banner names the concept and says which case it is -
"N authorable concept(s) bind by name - import + Reconcile" (red) vs
"the unresolved concept is link-governed - no method affected" (neutral).
Also surface WHICH concept, so the steward can decide whether its
term->column links matter (Apply-side integrity), instead of hunting.

## P3 · Deploy needs a progress indicator

Field (2026-08-25): "would be good to have a progress indicator when
deploying." The button says "Working..." while a four-phase pipeline
runs (zip import -> poll PDC's import workers -> verify every method
landed -> re-stamp minted term ids into each binding). Fix: narrate like
the labels stamp - phase + counter ("importing", "waiting on PDC import
workers", "verifying 49 methods", "re-stamping term ids... 31/49"),
via the same job/progress plumbing the identification job already uses.

## P4 · The no-term-id banner survived the reconcile that resolved it

Field (2026-08-25, screenshot): the GIS concept's term id resolved at
Reconcile (user-confirmed), yet the Deploy card still wore "1 concept(s)
still have no term id - those methods bind by name only" during the
deploy. Either (a) the banner renders from page-load state and never
refreshed after Reconcile (the W15 stale-card disease), or (b) the
reconcile's resolution was never persisted into the registry file the
Deploy card reads - which would ALSO mean the next session reloads an
unresolved registry. Diagnose: reload the app; banner gone = (a),
banner stays = (b) and the resolve must write back to the registry.
Deploy itself unaffected on this walk (the concept authors no method).

## P5 · Deploy misdiagnoses a never-started import as "stopped at the first member"

Field (2026-08-25, walk-blocking): deploy reported "DataPattern import
stopped at Arizona Segment ID... PDC abandons the rest of the archive at
the first member it cannot parse" + failed 49 - but a live probe showed
BOTH import workers still ACCEPTED / progress 0 / statistics {} eleven
minutes on, queue otherwise idle, zero Arizona methods in PDC: the
importer never READ the archives at all (VM-side manager consumers
wedged), so nothing was parsed and nothing was abandoned. The
stopped-at-first-member inference (1.10.12) assumed the worker reached a
terminal state; a worker still ACCEPTED at verify time is a DIFFERENT
failure and the red box sent the steward hunting a content bug that
does not exist. Fix, two cuts:
- wait_worker's timeout outcome must carry the last-seen status; when it
  is ACCEPTED/queued the deploy reports "PDC never started processing
  the import (worker <id> still queued after Ns) - the VM's
  DATA_PATTERN_MANAGER / DICTIONARY_MANAGER consumers are not picking up
  work; check the containers" and SKIPS the stopped-at inference;
- the verify table's per-method result then reads "import never ran",
  not "not found after import".
Walk remedy: VM-side container check/restart, then redeploy - the app's
reconcile makes the retry safe (create/update plan recomputed).

## P6 · Cross-fire verdict: substring hints and vocabulary twins (the headline check)

Field (2026-08-25, Identify read-back on the redeployed estate): 109
columns clean single-term; the nine flipped measures cross-fired NOWHERE
(name-anchoring held); but 5 columns carry cross-fire, all from generic
substring hints over shared vocabularies:
- customers.account_status += Status (Tiered Rates) + Status (Account
  Alerts); water_systems.system_status += the same pair;
  customers.service_county += County - the substring hints (?i)(status)
  / (?i)(county) "agree" with any column CONTAINING the token, so the
  0.5/0.5 tightening never disambiguated within the family;
- account_alerts.status <-> tiered_rates.status claim each other: both
  columns named exactly "status", both vocabularies shared - name AND
  values indistinguishable, and PDC's metadataHints carry no table scope.
Fix ladder, two cuts:
1. AUTHOR: a hint derived from a generic single-token column name
   anchors - (?i)^status$, (?i)^county$ - while multi-token names keep
   the substring form (account_?status can only match its column
   anyway). Clears the account_status / system_status / service_county
   rows, the ones where a column's OWN specific term exists.
2. DOCTRINE, glossary-side: table-qualified vocabulary twins (Status
   (Tiered Rates) vs Status (Account Alerts)) are undetectable
   distinctly BY CONSTRUCTION - the conversion note/readiness card
   should recommend mapping-only for a dictionary whose vocabulary is
   shared AND whose column name is a bare generic token; their term
   links already govern the right tables. The residual twin cross-fire
   stands until the steward declares them, and the app should say so
   rather than leave it to a read-back probe.

## P7 · Efficacy's "no physical source in the Registry" mis-describes JSON-nested sources

Field (2026-08-25, efficacy on the redeployed estate: 45 live / 0 dead /
4 unresolved): the four unresolved (Reservoir Level Percent, Pressure
(psi), Flow (gpm), Pump Status) each carry sources in the registry - but
ONLY nested JSON document paths (public.<file>.json.<node>.<column>,
5 dotted parts), which the efficacy resolver cannot map to a column
entity; the JSON snapshots are also outside the 11 identification
targets. Turbidity (ntu) resolved because it also has database sources.
Two cuts:
- HONESTY: the note must say "document-nested source (JSON path) - not
  resolvable to a profiled column" instead of "no physical source in
  the Registry", which sends the steward hunting a registry gap that
  is not there;
- RESOLUTION (investigate): if PDC's discovery mints entities for JSON
  nested fields, efficacy should try the nested path before giving up -
  probe a snapshot file's child entities on the live estate to decide.
