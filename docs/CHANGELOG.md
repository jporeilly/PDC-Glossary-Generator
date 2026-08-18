# Changelog

All notable changes to the Glossary Generator are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses
date-based releases. Entries predating this file are summarised under *Earlier*.

> The **1.6.x** line adds the **Policy Generator** engine (`classification/`) and the
> updated courseware alongside the Flask app; the app's suggest/review/export core
> carries forward from 1.5.7.

- **Registry hooked into the app.** `POST /api/generate` now authors and writes
  `registries/registry.<glossary>.json` from the final reviewed rows (export time =
  latest version). The classify/emit engine was **carved out** into a separate
  standalone **Policy Generator** (`policy_generator/`); the app carries only the
  minimal Registry writer (`registry/`).

## [1.38.25] - 2026-08-18

### Added - the Estate Report grows up: data-rich, explained, and honest
### about Refresh

"the report can be alot better and more data rich, with detailed
explanations. Refresh doesnt seen to work."

- **Six new report sections**, every number derived from the same rows and
  artifacts (no new scans), each with its explanation in place:
  **Detection coverage** (the drafter's own buckets — patterns by seed
  kind, dictionaries, mapping-only by design, skips grouped by reason);
  **Evidence depth** (formats / vocabularies / recognised kinds / numeric
  ranges / signatures / none — with the range-is-DQ-not-identification
  posture stated); **Data-quality readiness** (format, allowed-values and
  range checks + the scan's quality scores, low scorers flagged);
  **Label families** (PII Type tiers and friends, straight from the labels
  engine); **Estate footprint** (columns / tables / schemas / document
  columns); **Stewardship** (default steward, per-category overrides, kept
  label keys — ReportPage now sends the governance block). The exported
  HTML report carries all of it.
- **Refresh tells you what it did**: busy state while compiling, a
  "compiled HH:MM:SS" stamp after — recomputing over unchanged facts used
  to look identical to doing nothing (field-read as "Refresh doesnt seen
  to work"). Stale artifacts now get their own banner naming the artifact,
  the reason, and a Regenerate-on-Apply link — with the honest note that
  Refresh re-reads facts and cannot un-stale one.
- Docs swept for 1.38.19-1.38.25: GUIDE gains saved-glossary versions,
  session-held page state, generation versioning + MinIO backup, delta
  apply and the rename/recategorise checklist (with the category-
  fingerprint check); REFERENCE gains the snapshot/exports/terms-existing/
  estate-report entries; WALKTHROUGH's import step carries the two
  field-proven checkpoints.

First BUILT installer to carry 1.38.24's seed-ladder unification (that
release was committed by the Policy Generator session without a build).
Suite 369.

## [1.38.24] - 2026-08-18

### Fixed - the Registry now carries what the drafter mints (one seed ladder)

The Policy Generator authors from the Classification Registry and nothing
else, so evidence the Registry cannot express never reaches PDC. Two classes
of it were being lost: a profiler-**recognised** kind, and - the expensive one
- the steward's **Auto flip** on a mapping-only nature (a date, a bounded
measure like pH or Lead ppb). The drafter minted rules for both; the bridge
emitted only the row's raw profiled fields. The Arizona Water walk drafted 88
patterns and handed over a Registry worth 18, and the only way to notice was
to count both by hand.

The row -> seed decision now lives ONCE, in `engine/policy_seed.py`
(`seeds_for_row`), and both callers use it: the drafter mints from the best
seed, the bridge carries them all into `detect`. Same rows in, same seeds out
- pinned by `test_policy_seed.py`, which fails if the two ever disagree again.

- **Name-anchored seeds travel** with `identity: "column_name"`, so the
  authoring side knows the column NAME carries identity and the content regex
  is only a sanity check (the Policy Generator weights them 0.5/0.5 with a
  cardinality guard - see its 1.10.1).
- **A one-value reference list is no longer a seed.** It marked a concept
  `seeded` while the authoring side, which needs 2+ values, silently dropped
  it: four Arizona Water concepts claimed evidence that could never yield a
  method.
- **A mapping-only declaration still keeps its evidence** (only the intent
  changes, as before) but never picks up a name-anchored mint - a declaration
  is the opposite of a flip.
- **The drafted bundle stops claiming it is importable.** Its README told
  stewards to import `Patterns/` and `Dictionaries/` through PDC's Data
  Identification screens, which its folder layout cannot satisfy - PDC takes a
  flat zip of pattern JSON and one nested zip per dictionary, which is what
  the Policy Generator authors. The bundle is review evidence; the README and
  the Apply card now say so.

Arizona Water, same rows: Registry detect went 18 patterns + 31 dictionaries
-> 88 patterns + 27 dictionaries, matching the draft exactly. Suite 368.

## [1.38.23] - 2026-08-18

### Changed - Apply is a DELTA: unchanged columns are skipped and say so

"be better if this did just the delta, i.e those where there is no match"
- re-applying 70 columns when only a handful changed re-PATCHed all 70.
Now, when the merge reproduces exactly what the entity already carries,
the PATCH is skipped: the row reports **unchanged =** (dry-run and real
alike), the summary counts "already up to date (skipped - delta apply)",
and the trust job scopes to real writes. The comparison is conservative -
server-side junk is cleaned from both sides before comparing, and any
normalisation doubt reads as changed (the merge is idempotent, so an
unnecessary PATCH is safe; a skipped necessary one would not be).
Unchanged rows still contribute to the table rollups - the table mean
needs every member. Suite 358.

## [1.38.22] - 2026-08-18

### Added / Fixed - glossary versions, and editing under a filter

- **Saved-glossary versioning (copy-on-write)**: the FIRST edit after
  loading a saved glossary archives the loaded state as a version — same
  name, ORIGINAL savedAt, immutable — before the debounced autosave can
  overwrite it ("the old Glossary is just timestamped and archived. still
  there in the list"). One version per load-session (a harvest folding
  into a loaded glossary counts, so the pre-harvest state is always
  recoverable); the last 10 versions per glossary are kept. Home's Saved
  glossaries table folds "N earlier version(s)" under each live row —
  timestamped, openable, deletable. Opening a version loads it as a
  working COPY (versions are immutable; saving the copy creates a new
  entry via the collision suffix, and archived versions deliberately
  don't participate in that suffix). Proven in the wild during
  verification: the first sim edit to a loaded glossary minted its
  version unprompted.
- **Editing the field a filter matches on no longer evicts the row**
  (field-caught: "when i go to type in the new Category the focus is
  lost"): with the category filter set to Customer Management, the first
  keystroke into a row's Category made the row stop matching, unmount,
  and take the input with it. Grouping already froze mid-edit; FILTER
  MEMBERSHIP now freezes on the same snapshot — while focus is inside
  the grid, rows hold their place; the re-filter applies on the way out.
  Verified per-keystroke: input alive and row held through a full
  category rename under an active filter, row correctly re-filtered on
  blur.

Suite 357.

## [1.38.21] - 2026-08-18

### Added - every generation is a version: local archive + MinIO backup

"i want to keep backed up versions in minIO" — and the morning's stale-
import incident proved why: a pre-edit "glossary-import (n).jsonl" from
Downloads went into PDC and looked identical to the fresh one.

- **Generation archive**: every Generate writes a timestamped copy into
  the app's own exports history (state dir, exports/<glossary>/
  <ts>-glossary-import.jsonl, last 20 kept), the Generate card lists the
  previous generations with re-download links, and the **Download button
  carries the generation's timestamped name — the filename IS the
  version**, so a stale file can never masquerade as the current one.
  Byte-identical guarantee pinned (Windows text-mode \r\n rewrite caught
  by the test).
- **MinIO backup**: with the lab connection up, each generation ships
  automatically to pdc-exports under a browsable per-glossary prefix
  (glossary/<slug>/<timestamped-name>; lab-export gains key_prefix for
  already-stamped filenames), with an on-by-default toggle and the landed
  key named on the card. Backup failure is reported, never blocks the
  export. Verified live: archive line, timestamped download, and the real
  object landing in the lab MinIO.

Suite 355.

## [1.38.20] - 2026-08-18

### Added - the existing-terms check fingerprints the CATEGORY

"be useful if the Term was also checked against the Category" — it is now,
and with zero extra API calls. Field-caught the same morning: PDC held
Billing Address under Customer Management while the grid said Billing and
Revenue, because the import had used a pre-edit JSONL — and the flat
IN PDC badge hid it completely.

- Term ids are deterministic UUID5(glossary, category, name), so the
  Review-time **Check PDC for existing terms** now compares the id PDC
  returns against the derivation for the ROW's category:
  **IN PDC ✓** = same category; **IN PDC · category differs (X)** = the
  same glossary's term under a STALE category — a previous import
  generation, named when it matches a category on the current grid, with
  the remediation in the tooltip (regenerate, delete the glossary in PDC,
  re-import). A foreign glossary or hand-authored term keeps the neutral
  badge — nothing to fingerprint against.
- Lineage is proven from the id alone (any current-grid category whose
  derivation matches) because the live estate's /search returns
  glossaryId null — the first cut leaned on glossaryId and the stale
  badge never fired (live-caught during verification).
- The check's summary line counts the drifted terms and says what to do.

Verified against the live estate: the pre-edit import generation shows
"IN PDC · category differs (Customer Management)" on exactly the moved
terms; matching terms show ✓. Suite 354.

## [1.38.19] - 2026-08-17

### Fixed / Added - pages hold their state, the flip closes its last gaps

- **"All pages should be able to maintain their state if another page is
  selected and you go back"** — they do now, for the session: results and
  inputs across Apply (auth, data elements, generate output, draft, staged
  flips, resolve/apply reports, labels & stamp reports), Connect (harvest
  sources/selections/notes, bulk-load CSV + dry-run table, probe), Schema
  (connection, graph, open table, keys plan, view mode), Files (bucket,
  listing, open file), Govern (unbaked stewardship defaults/overrides/
  orphans, label keys), Dictionary (AI advice, fold plan, pack export,
  resolutions, add-forms) ride the session cache; busy flags and anything
  refetched on mount stay transient. Auth lives under 'pdc.' and survives
  a glossary switch; glossary-derived state ('apply.', 'govern.') clears
  when a different glossary loads.
- **The draft and the stamp are RESUMABLE jobs**: leave the page mid-run
  and the poll re-attaches on return with live progress, the result
  landing in the cached view — "guess i had to wait" (a mass-flip redraft
  polishing ~40 extra rules looked like a stale page) becomes a visible
  progress line instead of a mystery.
- **A signature no longer gates the flip** (field-caught on the mass-flip
  walk): a profiled date CARRIES a dddd-dd-dd signature, and the
  name-anchored mint hid behind "no signature" — a flipped Payment Date
  landed in "no stable shape". The name-anchor check now comes first; the
  signature rides the rule's contentPatterns at weight 0.
- **Unit-named bounded measures arrive AUTO** ("I thought this would be
  done automatically"): the nature classifier now defaults a measure whose
  name carries its unit (pH, lead_ppb, turbidity_ntu — units are class
  knowledge) to Auto detection at suggest time, minting name-anchored
  rules with no steward click. Generic numerics keep the safe mapping-only
  default; the drafter's ★ recommended flips remain for rows harvested
  before this default.

Suite grows to 353. Verified live: draft → navigate to Review → return,
the draft (stars included) still on screen; all nine pages render clean
with zero console errors.

## [1.38.18] - 2026-08-17

### Changed - the suggester carve: 3,144 lines become seven role modules

Pure structural move, its own train so it stays bisectable from every
behaviour change around it ("does the suggester getting too big. might be
worth refactoring for the different roles?" - it was, and it did). The
file's own section banners were the cut lines:

- `sug_harvest` (441) - relational harvest: DDL/live schema walk, keys,
  graph, sampling
- `sug_profile` (266) - value profiling: signatures, induced patterns,
  profile_live, discover
- `sug_suggest` (994) - term suggestion: naming, categorising,
  classify/define/tags/ratings, quality, detection intent, suggest()
- `sug_docs` (963) - document store: MinIO/S3, harvest, previews, the
  document DQ profiler and document term suggesters
- `sug_links` (392) - enhance & links: glossary/source parsing,
  deterministic ids, mapping policy, data-element links
- `sug_generate` (308) - JSONL records + build/scan checks
- `sug_shared` - cross-module constants (SENS_RANK/RANK_SENS relocated
  here: they were the single edge making suggest→generate→links→suggest
  a cycle)

`suggester.py` remains the import surface - a facade re-exporting every
public and single-underscore name (the same shim pattern sources/pdc_api.py
uses over pdc_client), so no call site anywhere changed. Cross-module
imports were derived by pyflakes on a simulated split before the real one.

Caveat that matters: MONKEYPATCH THE OWNING MODULE - rebinding a name on
the facade does not reach the module whose functions read it (exactly one
test needed retargeting: CAT_KEYWORDS -> sug_suggest; api.py's
`suggester._s3_client`/`_load_domain_pack` call sites read through the
facade and stay patchable there).

Verified beyond the suite (351): CLI imports, and the 24-check
deterministic E2E against the live estate - scan → invariants → draft →
bundle → labels → estate report - ALL PASS on the carved code.

## [1.38.17] - 2026-08-17

### Fixed - three guards from one morning's field walk

- **The fresh-scan fork can't happen silently anymore** ("so now its a
  mess!"): every scan/harvest now lands through one guarded path
  (state.js landScanRows). A landing on an EMPTY grid while a saved
  glossary exists asks first — load the settled glossary and fold the
  fresh evidence in (recommended), or knowingly start a separate grid.
  Non-empty grids merge by source identity exactly as before.
- **Same-name saves get a visible suffix**: a NEW glossary colliding with
  an existing name saves as "Name (2)" — the fork that made two identical
  "Arizona Water"s (with the raw twin stealing auto-resume) is now legible
  in the Home list at a glance. Re-saves of an existing id keep their name;
  the workspace adopts the server's suffix so every surface agrees.
- **Generic tags are retirable** ("cant retire generic tags"): the same
  durable tombstone company items get — it survives the load-time
  re-inject AND Reseed — and retiring a tag strips it from every rule
  that emits it (a rule left with no tags is dropped), so the
  rules-reference-governed-tags invariant holds. The exception is the
  load-bearing core six (pii, maskable, identifier, cde, record,
  table-level): engine code paths stand on those, and their Retire button
  is now visibly disabled WITH the reason — the silent refusal was the
  real bug.

Suite grows to 351 (generic-retire lifecycle incl. tombstone-through-
reseed and the core-six refusal; save-collision suffix; the landing-path
shape pin follows the merge into state.js).

## [1.38.16] - 2026-08-17

### Added - flip where you read: the draft's own lists become the control

"is there an easy way to flip without having to go back and forth between
pages?" - yes, now the draft results ARE the flip surface:

- **In-place flips on Apply**: every term on the mapping-only line carries
  a **→ Auto** button, and the free-text skip groups ("values induce no
  shape", "no stable shape") carry **→ Mapping-only** - the row updates in
  place (same autosaving mutation Review uses), a "N flip(s) staged" line
  confirms, and the next **Draft policies** click honours them. Flip,
  re-draft, send to the lab - one page.
- **The draft recommends its own flips**: mapping-only entries are starred
  **auto_candidate** when they are a bounded measure whose name carries
  its unit (pH, lead_ppb, turbidity_ntu, "(ppm)" suffixes) - units are
  CLASS knowledge (ppm is ppm in any estate), same doctrine as email/zip
  shapes. Starred terms sort first and **★ Flip all recommended (N)**
  stages them in one click. Generic amounts and dates stay unmarked: the
  name-anchored form makes the column name authoritative estate-wide, and
  that assertion stays the steward's consent - the engine sorts the queue,
  it never decides. (Live-verified: pH Level and Lead (ppb) starred,
  Payment Date and Amount Paid not; flip-all → re-draft minted both,
  mapping-only line dropped 3 → 1.)

Suite grows to 349 (auto-candidate pins).

## [1.38.15] - 2026-08-17

### Added - labels close the loop: the assignment wire, mapped and driven

The per-column label assignment - the one capture that kept "labels" a
definitions-only feature - turned out not to be GraphQL at all. The user's
DevTools session showed the READ side (the entity's
`attributes.customProperties`), and error-shape probing found the write:

- **The wire**: `PATCH /api/public/v3/entities/{id}` with
  `{"attributes": {"customProperties": [{"id": <definition _id>,
  "value": "Confidential"}]}}`. The array replaces WHOLESALE (proven by
  clear-and-restore on the live customers.phone column), so
  `pdc_client.assign_labels` is read-merge-write: labels this app never
  derived survive, and a blank value removes exactly one. No entity-update
  mutation exists in the GraphQL schema - which is why no `graphql` filter
  ever caught it.
- **The auto-stamp flow** (`/api/jobs/labels-stamp` + the Data labels card
  on Apply): per kept row, the labels engine derives {key: value} from the
  same evidence the create step used; every real source column resolves to
  its entity (the same resolver the term-links apply uses); one merged
  assignment lands per column. **Dry-run first** - the same propose→apply
  posture as the rest of the page - with per-column progress and honest
  reporting: families missing from PDC, columns with no matching entity,
  and **drifted families** (a value the engine derived that PDC's family no
  longer lists is reported, never written - the live PII Type had been
  hand-edited down to one value, which is exactly the corruption this
  guard exists for).
- **Create aligned to the UI's own capture**: `defaultValue: ""` and
  itemTypes default `["Columns","Folders","Files"]` - a label that can't
  land on files is half a label in a document-bearing estate.
- Docs: GUIDE grows "Data labels - tags vs labels" (a tag answers "is this
  in the set?", a label answers "which one is it?") plus the assignment
  wire; REFERENCE carries the endpoint and the PDC labels wire note;
  WALKTHROUGH gains the flip-a-measure-to-Auto demo step.

Suite grows to 348 (assignment client pins, stamp-flow pins including the
drifted-family guard).

## [1.38.14] - 2026-08-17

### Added - the steward's Auto flip is honoured with a name-anchored rule

"Im also sure some of these mappings can be auto ... pH level can only go
to 14?, payment date, will have a pattern" - correct, and the discriminator
is name + shape TOGETHER, which is exactly what PDC's blended scoring can
express. Design cross-checked two ways before landing: against PDC's own
docs (the confidence formula, the shipped Personal Data Identifier
template) and against the industry (Purview's own Date-of-Birth classifier
is column-name-only; Informatica's "match data AND column name" mode is
the same conjunction; no surveyed product uses a numeric range as
identification evidence - ranges live in DQ everywhere).

- **Name-anchored measure rules**: a row whose nature defaulted to
  mapping-only (a date, a bounded measure) that the steward flips to Auto
  now mints a Data Pattern instead of landing in the skips: the column-name
  regex carries identity, a sanity shape carries content (the profiler's
  date union for dates, `^-?[0-9]+(\.[0-9]+)?$` for measures), and the
  RANGE still rides the DQ rule where it belongs.
- **Weights rebalance to 0.5 name / 0.5 regex** for this form - under the
  stock 0.3/0.4/0.3 blend a rule with no contentPatterns can never clear
  the 0.7 gate (0.3 + 0.3 = 0.6). And since regexScore is NOT a PDC
  condition variable, the blend is the only place the name-AND-shape
  conjunction can live: neither name alone nor shape alone reaches 0.7.
- **columnCardinality guards** (from Pentaho's shipped template): the
  name-anchored condition requires cardinality > 5 - a constant column can
  never satisfy a sanity shape; dictionary conditions now carry the
  template's exact (confidence OR name-hint) AND cardinality shape,
  guarded at > 1 to match the enum floor instead of the template's > 5
  (which would veto a legitimate 3-value LOW/MEDIUM/HIGH).
- **Review page Detection filter** (All / Auto / Mapping-only) in the
  filter row - "please also check the map only Terms" is now one click:
  filter to Mapping-only, flip the pH/payment-date/lead-class rows, and
  the next draft honours them. Render-verified live: 3 mapping-only and
  2 Auto rows partition a 5-row grid correctly both ways.
- The nature DEFAULT stays mapping-only - the safe posture is unchanged;
  only an explicit steward flip mints the name-anchored form. A flipped
  row with no derivable column-name regex still skips: no anchor, no rule.

Suite grows to 341 (name-anchored mint pins, dictionary-template pin,
and the date-kind pin rewritten for the flip semantics).

## [1.38.13] - 2026-08-15

### Fixed - the recognised kinds learn their manners

1.38.12's sample-driven kinds worked - and immediately showed three new
faults against the live payloads, all fixed and pinned:

- **Dates first, and dates mint NOTHING**: 2026-05-14 is digits-and-dashes,
  so the phone shape swallowed alert_date; and a nullable date column
  yields ONE sample, below the two-vote floor - if every sample is a date,
  it is a date, and no date ever gets a pattern.
- **A format is FEW shapes describing many values** (account_number: 2
  shapes / 10 values). Many shapes is prose wearing digits - addresses and
  descriptions minted over-matching unions before the shape-count gate.
- **Bare short digit runs are not formats**: ^[0-9]{4}$ matches every year
  and count in the estate.

Also: Detection_Intent joins the merge fill-list, so re-harvests carry new
quiet-defaults onto existing rows (Population Served-class columns).

Honestly refused, verified against live payloads: per-row-unique
descriptive text (source_type on an 8-row table - a dictionary that grows
by one value per row is not a dictionary), comma-packed lists
(service_cities), single-value snapshots (tiered_rates.status). Those are
steward calls: seed a vocabulary in the domain pack, or set mapping-only.

## [1.38.12] - 2026-08-15

### Fixed - the 48-skip draft named its own causes; all four fixed

Live payloads for each named miss, then structural fixes - nothing
estate-specific (canonical class shapes and payload semantics only;
customer knowledge stays in the domain pack):

- **Recognised kinds from samples**: shape-multiplicity broke email (nine
  shapes, none at 90% coverage) even though every sample is plainly an
  email. When >=80% of a column's own samples match a canonical class
  shape (email/phone/zip/ssn), the kind is set and the drafter mints the
  recognised custom pattern - the harvest path finally has the same
  recognised-kind power the direct scan always had.
- **A single sample is not a value list**: the one-value "enum" ['85122']
  claimed the zips and blocked their perfectly good ddddd pattern. Enum
  now requires two distinct samples.
- **lexicalMin/Max recover missed values**: Running and Stopped share one
  shape, so the one-sample-per-shape listing carried only one; the
  lexical bounds are true values on string columns and complete the
  pair. True single-value columns stay quiet.
- **bigint is numeric**: the word-boundary regex missed bigint/int8, so
  population_served-class columns never inherited the free-numeric
  mapping-only default.

All pinned with the live shapes. Comma-list columns (service_cities) and
single-value columns stay honestly skipped.

## [1.38.11] - 2026-08-15

### Fixed - found by running the workflow end to end

A scripted end-to-end (scan -> evidence -> save -> pack -> generate ->
data elements -> draft job -> bundle zip -> labels -> estate report, 24
checks, no LLM, no PDC writes) plus a click-through of every page:

- **The skip list now honours Detection_Intent.** Mapping-only terms
  (dates, names, free numbers, flags) no longer clutter the draft's skip
  list - they report in their own quiet line: "N term(s) mapping-only by
  design". The skip list is back to naming genuinely missing evidence.
- **The stepper no longer draws green dashes across completed steps** -
  nowrap hints spilled out of shrunken flex items and the connector bars
  drew straight across the spill; step buttons now clip with ellipsis
  (verified by bounding-box intersection: zero overlaps).

Everything else held: 24/24 end-to-end checks pass, all ten pages render
with a loaded workspace, suite at 330.

## [1.38.10] - 2026-08-15

### Fixed - the Draft click itself crashed with "ws is not defined"

The cruellest possible place: a fully fueled grid, 142 terms exported
clean - and the Draft button threw. The 1.38.6 label-keys edit referenced
the workspace inside GenerateCard, which receives `governance` as a PROP
and has no `ws` in scope. One line; verified by driving the exact failing
click on a live preview (draft starts, seeds collect, no error). The
probe also samples 24 columns now (sample_columns overridable) - 8 kept
hiding the interesting ones.

## [1.38.9] - 2026-08-14

### Fixed - the Terms half of the draft: harvest reads PDC's REAL shapes

"Just terrible for Terms - great for dq." 138 skips, because the value
evidence never reached the harvested rows: on this PDC 11 build,
`dataSampling` is EMPTY and the vendor-documented shapes do not exist.
Raw payloads pulled straight from the estate settled the truth:

- **Values live in `patternAnalysis.patterns[].sample`** - one real value
  per shape group. For low-cardinality columns those samples ARE the value
  list: payment_status -> a complete dictionary (At Risk / Good Standing);
  service_city -> the actual cities as a candidate list.
- **Patterns derive from PDC's shape alphabet zipped with its own sample**
  (A=upper, a=lower, d=digit, literals from the sample):
  "AAAsAAsdddddd" + "AWC-CG-001001" -> ^[A-Z]{3}-[A-Z]{2}-[0-9]{6}$,
  with per-shape counts giving honest coverage. Only DISCRIMINATING
  shapes mint (digits or separators) - word-shapes match every sentence
  in the estate, and a value list beats a shape anyway.
- **Stats corrected**: density/uniqueness are percents,
  `bitsetCardinality` is the true distinct count, and stats.min/max are
  string LENGTHS unless bindType is numeric - so a status column can no
  longer contribute a phantom "7..13" value range, while customer_id's
  real 1001..1010 still feeds range DQ.

All pinned with fixtures captured from the live estate. Legacy shapes
(documented sampling lists, ready-made regexes) remain as fallbacks for
other PDC versions.

### Added - detection intent defaults by NATURE

"Dates could automatically be set as map instead of everything auto" -
and three siblings joined them. mapping_only wherever the nature of the
data precludes a discriminating shape: dates, personal names, free
numeric measures, booleans. Coded enums, formatted codes and recognised
kinds stay Auto - and a no-evidence text column stays Auto too, because
it might be a dictionary tomorrow. Nature decides, never absence of
evidence; the steward can flip any row.

## [1.38.8] - 2026-08-14

### Changed - PII Type: the steward's taxonomy becomes the engine's

The steward modelled a data label live in PDC's Create Custom Property
form - PII Type: Restricted / Confidential / Internal, each with a real
definition - and it is simply better than the engine's binary "handling"
key. Adopted verbatim: the engine now tiers the deterministic PII call by
exposure harm (government ID and financial -> Restricted; names, emails,
phones -> Confidential; ZIP, city, county quasi-identifiers -> Internal),
and the per-value descriptions ship into PDC's availableValues so the
label reads like the steward wrote it - because they did.

Also read off the UI-created record and corrected in the client:
fieldType is lowercase "select" and the hierarchy maps to scope
["Entities"]. The Data labels card is idempotent against the hand-made
PII Type - same name, case-insensitive, reported as existing.

## [1.38.7] - 2026-08-14

### Added - labels write into PDC: the endpoint is captured and mapped

One DevTools capture of the UI's getDataLabels call ended the long-standing
gap: PDC labels are CUSTOM PROPERTIES with isDataLabel=true over
POST /graphql, and a bearer token works. Introspection is off, but Apollo's
"did you mean" suggestions named the mutations, and live probing proved
create and delete end to end (including cleaning up the probe's own stray).
New pdc_client.labels module (gql/list/create/remove), and an Apply-page
**Data labels** card that writes the steward's kept keys as data labels
with their engine-derived vocabularies - idempotent, existing names
reported and never overwritten. Assigning labels to individual columns
remains a PDC-side step until that call is captured too.

### Fixed - expertise speaks the settled taxonomy, per person

Suggest expertise fed the LLM categories from ALL rows - and dropped rows
keep their scan-era names forever, so retired categories ("water quality
reports" after the rename to "Water Quality") salted everyone's keywords,
and the whole roster got one identical list with no Infrastructure in
sight. The vocabulary is now KEPT rows only (the settled taxonomy), and
the prompt demands the SUBSET that fits each person's roles - different
per person, the categories' own wording, never a table name or a retired
variant.

### Changed - the Domain pack steps are proper buttons

Standard-size buttons (same as Save dictionary), one primary at a time as
the state advances - the flywheel's most important turn no longer hides
in mini pills.

## [1.38.6] - 2026-08-14

### Added - the draft bundle covers labels

"Does this cover labels?" It does now. The bundle gains
**Labels/labels.json**: the evidence-derived keys (handling, access-tier,
criticality, domain, plus any pack vocabulary such as retention), the
steward's kept set from Govern, per-term assignments with the terms behind
each value, and the small governed vocabulary - the Policy Generator's
labels contract, indexed in INDEX.csv alongside patterns, dictionaries
and quality. Writing labels INTO PDC remains gated on capturing the real
endpoint (one DevTools look at an "assign label" call settles it).

## [1.38.5] - 2026-08-14

### Added - numeric profiling is evidence, and it says so

"We know that the data has been ingested and profiled, so there will be
sample pattern and values." Correct - and for a numeric column the profile
is completeness, uniqueness and min/max, which rightly mints no value set
or pattern. But the UI called that "no evidence" and the steward read a
fully-profiled estate as broken. Now:

- **`Value_Range` rides the row** ("201..5095"), filled from any profiler
  that observes min/max - including PDC's own entity stats on the
  harvest path. Survives merges like the rest of the evidence.
- **The cluster comparison shows it**: candidates read `num 201..5095`
  instead of "no evidence".
- **The advise rubric counts numerics honestly**: "2 of 2 candidates are
  profiled numerics (201..5095 / 15..480) - a shared range is not a
  shared concept, so the numbers cannot decide". Identity comparison
  stays deliberately conservative: ranges never merge concepts (the
  Paid/Outstanding lesson holds).
- **Range DQ checks mint at draft time** - the observed min/max become
  the expectation's baseline (`{"check": "range", "min": 201, "max":
  5095, "source": "profiled baseline"}`). The open numeric-range item,
  closed.

## [1.38.4] - 2026-08-13

### Fixed - "aim for 3" means 2-4, not 6

The target only lifted the model's ceiling, so aiming for 3 could land on
6 - "100% over". The stated range now WRAPS the target (aim for N asks
for between N-1 and N+1), so obeying the range is obeying the aim. Blank
keeps the default 3-6 behaviour, and a high target still lifts the
ceiling it needs.

### Changed - the advise rubric counts its evidence

"No profiled evidence" on a fully-profiled estate read as a data bug.
When members carry value sets but no PAIR is comparable, the reason now
says so with numbers: "value evidence on 2 of 4 candidates but no
comparable pair - the rest are prose or free numbers". The blanket
phrase survives only when literally no candidate carries evidence.

## [1.38.3] - 2026-08-13

### Fixed - duplicate resolution you can change your mind about

Three field-caught faults in one state machine:

- **Reverting a decision now brings everything back.** "Keep separate"
  restores the candidates AND the header with its buttons and the AI
  recommendation - re-deciding needs no re-run of AI advise. The machine
  is memoryless between decisions: merge/split snapshot the LIVE members
  at the moment of the action, and a revert restores that snapshot and
  forgets the group.
- **Headers sit over their own rows.** Display clusters key on the
  CURRENT term name, nothing else - the revert stamp used to key display
  too, so a split-product renamed by the AI pass stayed glued to its old
  cluster ("its not 1 candidate merged into one. in this case its 2").
- **The decision's evidence is in view.** Each undecided cluster header
  lists its candidates - source, category, evidence, first line of the
  definition - one aligned row each, so choosing Merge / Disambiguate /
  Keep separate no longer means scrolling a wide grid ("as you cant see
  the other rows its difficult to select the correct strategy").

Proven live: merge -> revert -> re-merge on a seeded duplicate, header,
recommendation and comparison intact at every step.

### Fixed - keys cannot ride in on the harvest path

"How did Customer ID get through when its a key?" Because PDC's harvest
carries no PK/FK flags, and the structural prune required them. Evidence
now stands in where declarations are absent: an id-named column that is
near-unique is a surrogate key in fact, and the same id-named column in
two or more tables is a join key in fact - both arrive un-kept, with the
reason on the row. Formatted natural keys (a real value pattern) and
identity PII still always survive, and a lone repeating id with no other
evidence stays for the steward to judge.

## [1.38.2] - 2026-08-13

### Fixed - the dotted-filename family's last hideout

The Files profile still showed zero confidence over 53 live terms after
the matcher fix - because the rows themselves were mis-parsed one level
deeper. Harvest routes document files through the DATABASE suggester, so
their sources read "schema.file.csv.column" (no slash), and the parser's
dotted branch made the table "file" and the column "csv.column" - the
same family of bug fixed at three other junctions, in its fourth hideout.
The parser now applies the one canonical rule everywhere: a single split
at the file extension. Nested JSON leaves survive
("all_systems_snapshot.json" + "export_metadata.classification") and
database columns are untouched. Pinned at the endpoint level: a document
harvest whose profile joins no rows now fails the suite. This also
protected policy drafting, which would have named harvested document
columns "csv.material" again.

### Changed - the docs profile drops its zero-byte trailer

The "Largest: ... (120 rows, 0 B)" line only had zeros to offer for
files - the bucket charts below carry the real sizes.

## [1.38.1] - 2026-08-13

### Fixed - the Files profile counts its own terms

"Term confidence 0" over 53 live document terms: the profile's row matcher
did a naive dot-split, so a document source ("bucket/folder/file.csv.column")
matched on a "table" called `csv` and no doc row ever joined. The matcher
now uses the canonical source parser, so confidence, PII and sensitivity
counts are real on the Files profile.

### Changed - unstructured metrics speak file language

The Files profile drops the database-only tiles (Keys PK-FK, Empty tables),
counts **Files** rather than "Tables", and titles itself accordingly -
"dont need some of these metrics for unstructured".

## [1.38.0] - 2026-08-13

### Connect deals only with PDC

The information architecture now says what the product means. **Connect**
carries the catalog-facing work alone: bulk load, harvest, and the
diagnostic probe. The app-side source connections - the credentials that
power the DIRECT paths - moved to the pages that still need them:

- **Database connections live on Schema**, beside the live browser, ER
  diagram, keys write-back and Seed data they power.
- **Object-store connections live on Files**, beside the bucket browser.
- Each page shows only its own kind, with the "Add a source connection
  directly" form demoted to an advanced disclosure beneath - the fallback
  for sources PDC has not profiled, not a parallel path.

The explainer panels moved with their buttons, and the docs-guard test
that noticed Connect "losing" them now expects them at their new home.
(The move initially shipped the form without its defaults constants -
caught by render-verification as a blank Schema page before release,
the same trap as the discovery-panel extraction.)

## [1.37.9] - 2026-08-13

### Fixed - file sizes, from the key the catalog actually uses

Two raw entity dumps from the live estate ended the guessing:

- **Size is `metadata.stats.bytes`** - a SIBLING of `metadata.file`, which
  is why two rounds of aliasing `metadata.file.*` never found it. Wired,
  with the old guesses kept as fallbacks for other PDC versions. The
  file dates were real all along (`metadata.file.modifiedAt` is the true
  mtime; the catalog record's own updatedAt is separate).
- **`metadata.document` rides the record now**: title, author, and the
  `cp:category` class ("Field Inspection Report") - document-class
  evidence the labels engine can use, captured at harvest.

### Added - a baseline profile straight off the entity

A COLUMN dump showed the entity itself carries `metadata.stats`: rows,
nulls, cardinality, density and uniqueness percentages, and
**min/max/avg/stdev**. Harvest now takes a baseline profile from the
entity before profiling-info is even asked (profiling-info enriches on
top), so completeness and uniqueness baselines are free - and the numeric
RANGE evidence (201..5095 on length_feet) now rides the profile, opening
the door to range DQ checks.

### Changed - two Review guards from a live near-miss

- The AI pass refuses to start while Category pills are pending: prose
  must be written against the taxonomy you chose, not the one it is
  replacing (field: pass started at 13 approved with 13 -> 6 pending).
- While an agent runs, an older proposal banner collapses to a one-line
  reminder instead of impersonating the active panel ("ive clicked on AI
  pass, but the panel hasnt updated").

## [1.37.8] - 2026-08-13

### Fixed - the raw FILE dump actually finds a file

1.37.7's probe still showed no Raw FILE entity: the lookup hunted for a
FILE inside the page-capped all-types listing, and this source's files sat
beyond those pages - the columns made it in, the files never did. The
probe now queries FILE entities directly (so every page is files), scopes
to the chosen source, and falls back to any file in the catalog rather
than none - the dump states which file it shows either way.

## [1.37.7] - 2026-08-13

### Fixed - the size arbiter is actually visible now

`usedCapacity` was the second alias guess to miss, which settles the
method: no more guessing. The diagnostic captured a raw FILE entity since
1.37.5 - but the card never rendered it (backend field, no UI). It now
shows as **Raw FILE entity** in the probe results: whatever key the
catalog stores sizes and dates under appears there, or the catalog does
not hold them - either way the next fix is exact. Also: the last two
"0 B" coercions (the Total-size tile, the by-type rows) now dash honestly
like the rest.

### Changed - the release train can no longer ship past a failure

1.37.6 released while the suite reported a failure: `set -e -o pipefail`
is demonstrably inert for piped steps in the environment the trains run
in, so the guard everyone trusted was decorative. Trains now run
`scripts/release-train.sh`: an explicit check on every step, full output
captured to `dist/train-<version>.log` (no more `tail -1` deciding what
the log gets to know), loud TRAIN_FAIL and halt. The suite failure itself
was a flake - 2 sightings under heavy build load against 6 verified-clean
runs; the log capture means its next appearance names itself.

## [1.37.6] - 2026-08-13

### Fixed - file sizes read from the keys PDC actually uses

A Contents screenshot from PDC's own UI settled it: the catalog holds the
sizes ("Used Capacity" per folder, real child dates) while every harvested
file read a dash - so the API aliases were simply missing PDC's key names.
The camelCase of the UI's own words now leads the alias list:
`usedCapacity` for size, `youngestChildDate` among the date fallbacks.
Pinned with the entity shape the UI implies; the diagnostic's raw FILE
dump remains the arbiter if a PDC version spells them differently again.

## [1.37.5] - 2026-08-13

### Added - long AI runs survive leaving the page

"So state is not held if i browse other pages? back to 0." It wasn't: the
app renders only the active page, so navigating away unmounted Review and
a five-minute categorize had nobody left to receive it. Now:

- **AI categories runs as a backend job.** Browse anywhere - the model
  keeps working server-side; Review re-attaches on return, the elapsed
  clock resumes from the job's own start time, and the proposals land
  whenever they are ready. Same for **AI advise**.
- **Pills, progress and recommendations survive navigation** - proposals,
  the batch bar, per-cluster advice and the categories-ran flag live in
  the session cache, not component state.
- **A mid-flight AI pass keeps landing pills** even while you are on
  another page: its loop writes through the cache, and the remounted page
  subscribes - so you come back to more pills than you left, not fewer
  ("can we implement this for all pages? so that the state is
  maintained").

### Fixed - unknown file sizes read as a dash, never "0 B"

The catalog stated no size for the harvested objects, and coercing that
to zero told the user the data was broken ("data for files still not
fixed"). Unknown now stays unknown end to end - per file, per folder, per
type, and in the totals. The identical dates on every file are the
catalog's ingest stamp, not the files' own - the diagnostic now dumps a
raw FILE entity so what PDC truly stores is read from payload, not
guessed from aliases.

### Fixed - the discovery charts have their own stylesheet

The confidence and weak-tables charts shipped class names no loaded
stylesheet defined - labels, bars and numbers ran together. The panels now
carry their own CSS (they render on Schema and Files, not just the page
whose stylesheet happened to match): one aligned label | bar | value grid,
full-width tracks so every bar starts at the same x.

## [1.37.4] - 2026-08-13

### Fixed - harvested files carry their sizes, dates and folder names

The Files charts drew, but every object read **0 B**, "most recent" was
ordered by nothing, and the by-folder bars had no labels ("no file data
for unstructured"). Two faults: `_file_record` never asked the PDC entity
for its size or modified date (both ride `metadata.file`, alias-tolerant
now), and the folder rows were keyed `folder` where the panel labels from
`name`. If a size still reads 0 B after this, that is the catalog's own
answer - PDC holds no size for that object - not a dropped field.

## [1.37.3] - 2026-08-13

### Fixed - the Files page went blank after a document harvest

Its own black box named the fault in one line — *Uncaught TypeError:
Cannot read properties of undefined (reading 'toLocaleString')* — from the
folder chart reading `f.count` on a payload that carried `files`. Three
faults, one root: the harvest payload did not speak the panel's
vocabulary.

- `by_folder` now carries `count` (and `by_type` its byte totals), and the
  panels degrade a missing number to 0 rather than blanking the page.
- The newest-objects list is `newest`, not `recent` — it had been silently
  empty rather than loud, which is worse.
- **Document columns no longer overwrite the database profile.** A harvest
  now splits by kind: database tables fill the **Schema** view, the columns
  PDC profiled *inside files* fill the **Files** view beneath the bucket
  charts, each with its own recomputed summary. Harvesting a document store
  used to clobber the database one, so only the unstructured profile
  survived.

Both payload shapes are pinned by tests that assert the exact keys the
panels read, and that a document harvest leaves the database view alone.

## [1.37.2] - 2026-08-13

### Added - you decide how many subjects this business has

The schema call biases low on purpose — it was fixing 11 physical groups
wearing new names — and on a harvested estate it overshot to 3, folding
rate and tariff terms inside Customer Management. How many subjects a
business has is a judgement about that business, so the strip now carries
an **aim for N** control beside `1 - AI categories`. Blank keeps today's
behaviour; a number reaches the model as a target, not a cap ("land within
one either side unless the estate genuinely argues otherwise"), and lifts
the ceiling it would otherwise hit.

### Added - the consolidation stays on screen

The 13 -> 3 delta was only ever stated in the completion line, which the
next message replaced. It now rides the **Categories** chip
(`Categories 13 → 3`, green when it shrinks) and the keystone button
(`2 · Approve categories (13 → 3)`), derived live from the pending pills —
so the number you are about to approve can never be mistaken for the
number the run proposed.

### Added - harvest fills the Schema and Files views

Those pages showed results only after a DIRECT scan, so on the PDC-only
path they stayed empty. Harvest now returns the same discovery shape, built
from what the catalog already gave us: **Schema** gets per-table results
(columns, completeness, uniqueness, PII/CDE, keys, and how much of each
table arrived with evidence) and **Files** gets its charts (by type, by
folder, largest, most recent). Two new charts read the estate at a glance:
**term confidence** and **tables carrying low-confidence terms**, ranked.

### Changed - filter by category first, then search inside it

The free-text box came first, which invited a guess against the whole grid
(a filter for "rate/tariff" matched nothing). The category picker now leads
and the text box reads "Then filter within it".

### Changed - one type ramp for every expandable panel

Nested "Under the hood" asides and top-level collapsible cards are the same
control and now read at the same size and weight; only colour marks the
aside as subordinate.

## [1.37.1] - 2026-08-13

### Fixed - harvest asks for profiling the way that actually works

The live probe settled it: PDC *does* profile document columns, and the
by-NAME route simply never found them — a document store's "table" is a
filename, so resolving a parent by name missed every one. Probing by the
entities' own ids answered for both source kinds (**via parentIds**, with
stats, values and patterns all present). Harvest now fetches profiling by
entity id first, falls back to parent ids, and keeps the by-name route only
as a last resort — so a harvested **document** grid carries the same value
evidence a database one does. Pinned by a test that fails if the name route
is ever tried first again.

### Changed - the probe reports honest counts

The id route answers for every column under the same parent, not only the
ones sampled — so a chip reading "sampled 8" sat above a listing of thirty
("bit more than 8 samples for unstructured"). It now reports **asked N ·
PDC answered for M**.

### Changed - PDC scan results stop lecturing

Repeating "0 identified means Data Identification has not run" under every
harvested source told the steward something they already knew, three lines
at a time. Each source now states the facts — *PDC holds 9 table(s) · 137
column(s) · no classifications yet* — zero counts stay silent, and the
explanation appears once, beneath the cards, only when nothing anywhere is
classified. When governance does exist, the counts and the sensitivity
spread return, with a note that harvest overlays existing work.

### Fixed - one type ramp for collapsible panels

The new disclosures carried `.summary` on top of the card-summary rule and
fought two declarations at once. Collapsible cards now read like any card
heading (same size, weight, and grey suffix as an `h2` + its `span`), while
nested "Under the hood" asides stay deliberately subordinate.

## [1.37.0] - 2026-08-12

### PDC is the system of record

A minor-version bump because the architecture changed, not the details.

The app used to hold its own source connections and scan databases and
object stores directly. It no longer needs to: the bulk loader registers
and profiles the estate **in PDC**, and Harvest brings back structure,
governance **and** — as of this line — the value evidence PDC already
computed. One credential, one system of record; the glossary, dictionaries,
Data Patterns, DQ expectations and labels all derive from the catalog.

What changed to make that true:

- **Harvest carries PDC's profiling.** It maps `profilingInfo` onto the
  same profile dict a direct value scan produced — reference lists from
  `sampling.sample`, Data Pattern seeds from induced patterns, completeness
  and uniqueness from the counts. Guarded: near-unique columns never become
  a dictionary, and a human summary ("99.9% numeric") is never shipped as a
  regex.
- **A probe that answers with payloads.** Pick a PDC data source and it
  reports what the catalog actually exposes — stats / values / patterns,
  raw payload included — how many columns it sampled, and by which route it
  asked (parent-table name, or the entities' own ids, so a name-resolution
  miss can never masquerade as "PDC has no profiling"). It also dumps a
  real entity's attributes to answer whether labels ride them.
- **No more connections the app cannot use.** PDC returns credentials
  encrypted (`AES/GCM/NoPadding|…`), so connections derived from a PDC
  record were born broken — "no password supplied", "InvalidAccessKeyId".
  That path is removed, encrypted values are refused rather than pasted
  into credential fields, and the direct-connection form is demoted to an
  advanced disclosure pending the last measurement on document columns.
- **Labels.** Suggested from evidence the scan already proved — handling
  from the PII call, access-tier from sensitivity, criticality from the CDE
  flag, domain from the approved category — chosen on Govern, and now shown
  per row in Review's expanded evidence, so the steward sees the
  consequence beside the reason. `retention` stays absent until your domain
  pack defines it: "7 years on compliance records" is your regulatory fact,
  not this engine's invention.
- **Discovery results render where they belong** — the database profile on
  Schema beside its tables, the bucket charts on Files beside its files.

## [1.36.70] - 2026-08-12

### Changed - harvest maps PDC's profiling, in the shapes PDC really uses

A live probe against the estate answered the architecture question: for a
structured source PDC exposes **stats, values and patterns**. It nests the
values under `sampling{sample, totalSamples, discardedSamples}` — and
tellingly returns `sample` for low-cardinality columns (billing_city,
system_type, phone) while high-cardinality ones carry only the counters, so
the catalog itself says which columns are reference data. The mapper now
reads those shapes: sample values become reference lists (Dictionary rules
and allowed-values checks), induced patterns become Data Pattern seeds, and
null/distinct counts become completeness and uniqueness baselines.
Guarded both ways — near-unique columns never become a dictionary, and a
human summary in `patterns` ("99.9% numeric") is refused rather than
shipped as a regex.

### Fixed - the probe measured the instrument, not the catalog

Probing a document store reported "no profiling" when PDC plainly held 57
terms' worth of CSV-header columns. Two faults, both in the probe: it
scoped by id where harvest scopes by fqdn-then-id, and it asked only for
type COLUMN when a document store's columns are typed otherwise. It now
scopes exactly as harvest does, uses the client's full type list, and
reports **columns resolved** alongside the capability chips — so "absent"
can never again be confused with "never asked".

### Changed - discovery results render where they belong

The database profile (expandable tables, sensitivity and key tiles) now
renders on the **Schema** page beside the tables it describes, and the
bucket profile (file-type and folder charts) on the **Files** page beside
the files — both read from the workspace, so they survive navigation and
reload rather than living in one page's local state.

## [1.36.69] - 2026-08-12

### Changed - PDC is the source of truth: harvest carries its profiling

"Harvest from PDC is used to build the glossary, all the data should be
there — after all that's what PDC uses." Correct, and the gap was OURS:
harvest read entity metadata (structure, keys, comments, the governance
overlay) and never asked for the profiling PDC had already computed, so a
harvested grid arrived with no value evidence and could seed no
dictionaries, Data Patterns or DQ expectations. Harvest now pulls
profiling-info per column and maps it onto the same profile dict a direct
value scan produces — reference lists, induced patterns, completeness and
uniqueness baselines — alias-tolerant across PDC versions, with near-unique
columns still refused a value list so ids never read as reference data. The
harvest summary reports how many columns came back profiled.

### Added - labels, suggested from evidence and never invented

PDC labels are small key/value custom properties. The Govern page now
proposes them from what the scan already proved: `handling` (the PII call),
`access-tier` (sensitivity), `criticality` (the CDE flag) and `domain` (the
category you approved) — each shown with its values, the terms behind them
and the evidence line. The steward keeps the keys; values are recomputed
from the live grid at export so a kept label cannot go stale. Labels READ
classification and never change it.

`retention` is deliberately absent until your domain pack defines it:
"7 years on compliance records" is a regulatory fact for an organisation,
not something this engine may invent. Define `labels.retention` in the pack
and the suggestion appears, matched on each document's own class. A key
whose values exceed PDC's ~6-value cap is refused, with the reason.

### Added - a probe that answers architecture questions with payloads

Connect gains a diagnostic driven by the same "List data sources" call
Harvest uses: pick a PDC source and it reports what the catalog actually
exposes — stats / values / patterns, per column, raw payload included — and
dumps a real entity's attribute keys to show whether labels ride attributes
(writable through the PATCH Apply already uses) or need their own endpoint.

### Fixed - the app stops making broken connections

PDC returns credentials ENCRYPTED: userName and accessId come back as
`AES/GCM/NoPadding|…`, which the app copied straight into a connection —
so the database said "no password supplied" and MinIO said
"InvalidAccessKeyId" ("the connections it adds are messed up"). The
→ Connection button is gone (harvest is the path; the loader CSV carries
real credentials when a direct scan is genuinely needed), and any encrypted
value is now refused rather than pasted into a credential field. The
"Add a source connection directly" panel is demoted to an advanced
disclosure, pending the probe's verdict on removing it entirely.

### Fixed - smaller truths

- The harvest scan-result line no longer claims profiling never ran when
  only Data Identification hasn't: ingest and profiling clearly ran if PDC
  holds the columns; `0 identified` means classification is the missing
  step.
- Factory reset now survives its own process: the workspace lives in tab
  memory, so the next autosave would have written the deleted glossary
  straight back. The reset stops this process saving and hard-reloads.
- The reachability-remap example is generic rather than one scenario's
  container name.

## [1.36.68] - 2026-08-12

### Added - Factory reset: the app owns its own zero

The installer's delete-app-data checkbox demonstrably failed to wipe on an
upgrade and two estates conflated. Settings now carries a guarded
**Factory reset** — deletes every state file (connections, settings, saved
glossaries, dictionary, roster, audit, Registries, installed pack) and the
running process's caches; app.log survives (the black box outlives the
wipe). Take a snapshot first if in doubt; close and relaunch after. The
walkthrough's Phase 0 now leads with it.

### Fixed - profiled values travel at your threshold

Barely-repeating reference columns (Service City's 8 cities, County's 5)
were SEEN by profiling but never persisted - the strict repeated-codes
gate refused, and the drafter and DQ arrived empty-handed. A small non-id
value set (2-12 distinct, uniqueness below id-territory) now rides the
profile as a candidate list ("lets set for equal or more than 2 values"):
dictionary rules and allowed-values baselines mint from it, while the
strict gate keeps its meaning for review semantics and the key prune.
Re-scan once to fill existing grids (the merge fills empty evidence and
keeps every edit) - the same re-scan also fills Value_Kind, unlocking the
recognised-kind patterns for email/phone/zip columns.

### Fixed - honest words, located offenders

- The build check's duplicate-name chips now carry WHERE each name lives
  ("Status - in Account Alerts · Water Systems"), on their own line -
  naming the term alone still sent the steward hunting.
- The "Profile documents in PDC" card no longer claims PDC never profiled
  a bulk-loaded estate ("the documents were initially profiled via the
  bulk loader" - correct): discovery ran at setup; the step is the
  GAP-FILLER for files added since or metadata-only ingests, and its
  check submits jobs only for those.

## [1.36.67] - 2026-08-12

### Added - the Estate Report: the flow ends on a noun

A new final workflow page ("a final page like a report summary … with some
pretty summary graphs"): the estate's governance stated - terms kept /
dropped, categories, sensitivity mix, PII/CDE, enrichment and evidence
coverage, top tags - drawn in the app's own idiom, no chart library.

Beneath it, the **Policy-Generator handoff contract**, verified from facts
on disk, never from ticked boxes: the Registry is parsed and id-matched to
THIS glossary (a different estate's file fails with the reason), the
installed domain pack is checked, and every closing action now leaves a
RECEIPT (generate, draft, pack install, resolve, non-dry-run apply) that
the contract consults - with freshness flags when the review was saved
after an artifact was produced ("REGENERATE"). One verdict line: READY for
the Policy Generator, or exactly what is missing or stale. Exportable as a
single self-contained HTML report to commit next to the pack.

## [1.36.66] - 2026-08-12

### The clean-run release: a full walk's field findings, in one build

An end-to-end field run (fresh install -> scan -> categorize -> keystone ->
AI pass -> dedupe -> Dictionary -> Govern -> generate -> import -> resolve ->
Data Discovery -> apply -> draft policies) produced fourteen improvements.

**The flow lights every stage.**
- Duplicate resolution is step 4 ON the strip ("i forgot the deduplicate
  last time!"): 4 - AI advise takes the blue when the pass finishes while
  same-named clusters await decisions, and goes quiet only when every
  cluster is decided. The pass-then-dedupe order is now the taught order
  (final names + real definitions make the calls easy).
- The stepper no longer goes quiet mid-pass: accepting pills lit the
  "enriched" signal at batch 8 of 26 and step 3 lost the blue.
- AI advise narrates (evidence -> live probe -> "adjudicating group n of m
  - <name>") as a background job, like every long agent now does.
- The in-app guide (diagram + working order) and docs/WALKTHROUGH.md are
  rewritten to the keystone flow, with a Phase 7 closeout checklist: every
  artifact the estate produced, versioned, Policy-Generator-ready.

**Apply reaches everything it should.**
- The PDC connection card now LEADS the Apply page (its session feeds
  everything below, including the tree check that sat above it).
- "Profile documents in PDC" moved BEFORE Apply and says the honest thing:
  the APP profiled these files at scan time - PDC has not, and until its
  Data Discovery mints the file-column entities, Apply has nothing to link
  ("surely this step should come before").
- The dotted-filename trap's whole family is extinct: _parse_source now
  splits document sources at the file extension (Apply asked PDC for a
  column named "csv.material" - every document column "not found"), and
  the policy drafter's column names go through the same one splitter (a
  JSONL leaf shredded to bare "id" made an over-matching rule regex).

**Policies cover the estate - all custom, all evidence.**
- Clarified with the field: custom-only means WE ship every policy (PDC's
  inbuilt set stays unused) - it never meant generic concepts go
  undetected. Columns the profiler RECOGNISED as email/phone/zip/ssn/card
  in this estate's values now mint custom Data Patterns carrying the
  profiler's own shape, plus matching DQ format expectations. "date" stays
  link-only (a date shape matches every date column).
- The profiler's verdict travels as data (Value_Kind on each row): the
  AI pass rewriting Suggested_Reason no longer makes profiled rows read as
  unprofiled ("re-scan" advice on rows profiling DID touch).
- The Build check names every offender inline (the backend always sent
  them; the UI dropped them - a warning that ended on a colon), and its
  verdicts say where to fix and that the check reruns.
- The held-back links list splits honestly: policy-held terms (actionable)
  vs table-level record terms (glossary-only by design, one line).

**Smaller field catches.**
- The domain-pack flow reads as steps: 1 - Generate pack, 2 - Inspect /
  ship, 3 - Install as this app's pack (the flywheel turn, was "Apply to
  this app").
- Keycloak fetch no longer offers generate-expertise-at-fetch: trim the
  roster to your stewards first, then Suggest expertise ("we'll only be
  dealing with stewards, custodians, owners").

## [1.36.65] - 2026-08-11

### Fixed - the schema call fits one GPU and says how long it takes

The categorize call went from 7:25 to 1:12 on the same machine - a 6x
speedup from one line. The model DECLARES a 256K context; Ollama sizes
its KV-cache reservation from the runtime context, and unbounded that
outgrew a single 12GB card - the model got SPLIT across both GPUs (an
empty card sat carrying half a model) and every token paid a PCIe hop.
Worse, temperature-0 decoding is brittle across runner builds: the same
prompt that yields five clean subjects on the single-card runner decoded
into a 19-second nothing on the split one. Every local call now passes a
bounded num_ctx (8K; 16K for the schema-wide call): the runner fits one
card, tokens stay on-die, and the same estate proposes the same taxonomy.
The call's budget floor also rises to 15 minutes (the field measured
7:25 before the fix - the timeout exists to catch dead models, not slow
ones), and the busy line now shows the only honest numbers for a single
opaque call: a live elapsed clock and how long THIS machine took last
time ("definitely takes more than a minute - can we add an estimate?").

### Changed - every duplicate is a steward decision

The wholesale "Merge duplicates" and "Auto-disambiguate" buttons are
gone ("the steward needs to go through every Term"): they were the only
controls on the Review page that ACTED without a look, against the
propose-then-approve constitution. Each duplicate cluster's header
carries the per-cluster decision with its recommendation; AI advise and
Find similar stay (they only suggest); the generate preflight still
names any collision that reaches it.

### Fixed - small honesty items, field-caught in one afternoon

- A failed PDC call's error banner outlived its retry - it sat next to
  "tree matches this export". Every retry clears it on entry.
- A doubled scheme pasted into the base-URL field ("https:/https://host")
  parsed as no-host and read as a NETWORK failure (the user went to check
  the NIC). clean_base now keeps the last scheme - the one attached to
  the real host.
- app.log wrote every line twice (the forensics handler was attached to
  both the root logger and the uvicorn loggers that propagate to it).

## [1.36.64] - 2026-08-11

### Added - drafting narrates, and the bundle keeps its polish

"Could do with some feedback when generating the draft policies" - the
AI polish is one model call per rule and ran for minutes behind a silent
"Drafting…". Draft policies now runs as a background job with a live
line under the button: collecting detection seeds → AI polish · rule
n of m — <term> → assembling rules & bundle (live-verified at rule 21 of
36 on the estate). The finished zip is kept on the job and downloads
from it, fixing a quiet fidelity gap: the old download re-drafted
deterministically and silently dropped the AI hints the panel had just
shown.

### Fixed - small reference tables profile as the reference data they are

The enum gate's flat floor (10+ sampled rows) starved exactly the most
reference-y tables there are - 8 water systems' counties and types
carried NO evidence while a busy billing table's status did ("a pattern
or values must be available?"). The floor is now relative - each value
seen about twice, minimum 5 non-null - so NULLs no longer starve it
either (Compliant×3/Warning×2 with 3 nulls is reference data by any
honest reading). Near-unique values still never read as enums: the
key-prune guard is untouched. Live result: 30 rows carry reference
lists where a handful did, and the drafter mints dictionaries for them.
The skip reasons also now tell the truth: "profiled, but the values
induce no shape" is distinct from "no profiled evidence - re-scan with
profiling on", which was wrong advice for rows profiling DID touch.

### Fixed - period-stamped and structural columns start un-kept

"Some of these Terms should have been retired: Total Revenue May 2026,
Description" - both have crisp deterministic signatures and now join
the structural-key prune family, un-kept with the reason on the row:
a period-stamped column (may_2026, 2026q1, _2026) names WHEN the
extract was cut and would mint a new term per period; a bare
description/notes/comments column describes its table's rows, not a
business concept. Qualified names (asset_description) and stampless
concepts (install_year) are untouched, and restoring is one tick.
Judgment calls (Length Feet) stay with the AI advisor.

## [1.36.63] - 2026-08-11

### Fixed - the PDC tree check reaches PDC

"module 'sources.pdc_api' has no attribute 'glossary_categories'" - the
function lives in pdc_client.entities but was never added to the
package's __init__ exports, so the compatibility shim re-exported
everything EXCEPT it and the first live click on "Check PDC tree for
lingering categories" died before reaching the network (field-caught the
moment the never-live-verified branch met reality). One line: the export
list now carries glossary_categories, and a test pins the route to fail
on the HOST, never the wiring.

## [1.36.62] - 2026-08-11

### Changed - categorize consolidates: subjects, clusters, completion

"No consolidation, just a name change" - the schema-wide call turned 11
physical groups into 11 renamed categories, then a rerun proposed 15,
then 2. Root causes, each fixed and pinned:

- **The evidence was wrong.** A document column ("bucket.gis/assets.csv
  .asset_id") minted its own one-column "table" after the last slash, so
  the model stared at dozens of meaningless tables and rightly refused
  to place them. The container is now the FILE; conceptual table-level
  record terms (no source column) follow their Source_Table - before
  this they could never follow their table anywhere.
- **The structure stayed implicit.** FK-joined tables and same-folder
  files now arrive in the prompt as explicit named clusters, computed
  from the scan's own facts. The prompt frames categories as broad
  business SUBJECTS (almost always 3-6, ceiling 8 even at 20+ tables),
  bans one-table rename-categories, and orders overlap merges.
- **Placement is finished by code, not hope.** An unplaced table
  inherits the category the majority of its cluster-mates were given
  ("the tables are then sync'd behind the scenes"); cluster-islands get
  one small second call constrained to the model's OWN category list;
  a table the model still refuses stays honestly physical.
- **Same estate, same taxonomy.** Both categorize calls run at
  temperature 0 with a fixed seed - the field saw 5 subjects one run
  and 2 the next; the walk now reproduces the identical 5 twice.
- **Reruns replace, never interleave.** A fresh AI-categories run
  replaces the previous run's Category pills everywhere - merging them
  mixed two taxonomies (the likely source of the original 11-to-15
  sprawl). The completion line also counts one-table proposals
  ("renames, not groupings").

Live result on the Arizona Water estate (157/180 kept, DB + documents):
"5 categories proposed on 180 row(s) - accepting every pill would take
the grid from 11 to 5 categories." Reproduced identically on a second
fresh walk.

### Added - the keystone saves the work

Two field losses in one day - a window crash and a page reload - each
wiped a full unsaved session, because the autosave only runs once the
glossary has a NAME. Approve categories now names an unnamed glossary
for the steward ("<company> review - <date>", renameable, said out
loud in the keystone message) and saves immediately: everything after
the settle moment survives a dead window.

### Added - crash forensics that survive the crash

The vanished-window crash left NOTHING to read: no Windows event, no
WebView dump, and the packaged shell buffers backend output in memory
only. Now app.log in the state dir is the durable record - backend
exceptions and lifecycle lines land there (rotating, 1 MB x 3), and the
frontend beacons every uncaught error and unhandled rejection to
POST /api/client-log (sendBeacon survives page teardown - exactly the
moment worth recording; rate-capped). The handler opens-writes-closes
per record so the log never holds the state dir hostage - the
fresh-install wipe still works under a running server (test-pinned).

## [1.36.61] - 2026-08-11

### Changed - the category count is visible before it is approved

Categorization exists to CONSOLIDATE, but the field run went from 11
groups to 15 categories and nothing said so until the keystone was
already set. Now the number is in the steward's face at both moments:
the AI-categories completion line reports the delta ("accepting every
pill would take the grid from 11 to 15 categories - NOT a consolidation:
reject or edit near-duplicate pills before approving"), and the Approve
button itself carries the live count ("2 - Approve categories (15)") so
the number being approved is read BEFORE the click. Model-side, the
prompt now states the job outright - consolidation, clearly FEWER
categories than tables, near-duplicate candidates merged before
answering - with a test pinning the contract. Counts use the keystone's
own accounting (kept rows), so every number on the strip agrees.

## [1.36.60] - 2026-08-11

### Fixed - a first run is not a fossil field

The stale check's evidence universe was SAVED glossaries only, and the
autosave only writes once the glossary is NAMED - so a fresh install
reaching the Dictionary before naming saw its entire just-scanned queue
flagged stale, with "Retire stale" offering to tombstone the whole
vocabulary (field-caught: "why are the Terms marked Stale before
approval?"). The Dictionary page now posts the live Review grid with the
health check and the universe unions it with every saved glossary: a
first run shows zero stale, and later rounds still surface true fossils -
pending entries from scans whose rows are gone everywhere, which nothing
can ever refresh. That flywheel reading is the intent: stale earns its
meaning on round two, when the estate has moved and dead vocabulary
should leave the steward's queue in one click.

## [1.36.59] - 2026-08-11

### Changed - the agent strip lights one step at a time

Steps 1 and 3 were both blue at once, so nothing on the strip said "you
are HERE". It now reads as a stepper: the current step carries the
primary highlight and the others drop to ghost - AI categories hands the
blue to Approve categories once proposals land, the keystone hands it to
AI pass, and after an enriched pass the strip goes quiet (the flow lives
at Review complete). Highlight only: every button stays clickable, so a
steward working manually is never gated by the lighting.

## [1.36.58] - 2026-08-11

### Fixed - a timed-out categories call says so, and gets time to finish

"No pills and weird categories" from a larger model read as model quality;
the likelier truth was a CLOCK - one schema-wide call must absorb model
LOAD (a 27b pays 30-60s before generating) plus a long completion, and on
timeout the UI said "the model proposed nothing usable", sending the
steward model-shopping. The call's budget now floors at 2x the AI-pass
timeout (>=360s, test-pinned), the endpoint reports timeouts distinctly,
and the message tells the truth: "The model TIMED OUT ... not a quality
verdict", pointing at the Settings timeout and warm loads. Field wisdom
recorded with it: on this workload the 12b gemma has been the sweet spot -
bigger is not automatically better for strict-JSON schema reasoning.

## [1.36.57] - 2026-08-11

### Added - terms from file contents: a CSV column is a column

The direct object-store scan produced 5 folder terms while PDC's harvest
of the SAME bucket carried every CSV column - the app never parsed file
contents into terms at all ("would expect a lot more Terms for
Documents"). Now it does, estate-agnostically: content-profilable objects
(csv/tsv/psv, JSON arrays, JSONL) declare their columns (headers, or
record leaves flattened to dotted paths like readings.flow_gpm), each
column's sampled values run the SAME deterministic profiler as a database
column (induced patterns, enums, sensitivity - Asset ID arrives carrying
^AST-\d{4}$), and the rows flow through the standard document path: leaf
naming, per-folder physical categories, envelope fields auto-pruned with
their reason. On the connection: "Terms from file contents (columns)",
default ON - including for connections saved before the flag existed.

Released under the new discipline: proven against the LIVE lab bucket
before building - which caught two defects the unit tests missed
(path-derived record-term names, bucket-named categories) plus a
would-be production KeyError from suggest()'s bracket-accessed column
shape. 268 tests; live result: 16 files -> 38 column terms, Gis/Scada
categories, envelopes pruned.

## [1.36.56] - 2026-08-11

### Changed - one grid writer, in the working order

After 1.36.55 made non-empty grids always merge, Scan and Add to glossary
were the same behavior wearing two names - and the replace-flavored one
had already wiped a grid, while Discover's name suggested it might add
rows (it never has; it profiles). The product owner's collapse, shipped:
the connection card now reads Test -> Discover -> Add to glossary, and
"Add to glossary" is THE one action that writes the review grid - the
first source starts the glossary, later sources join it, and scanning one
source never touches another's rows. The separate Scan button is gone;
tooltips and the "what each button does" explainer state each button's
whole truth, including "profiles ONLY - it never adds rows" on Discover
(the misread that cost half an hour this morning).

## [1.36.55] - 2026-08-11

### Fixed - scanning one source never deletes another's rows

The plain Scan button REPLACED the whole workspace unless "Add to
glossary" was the click - so "JDBC added, then Scan on Documents" silently
wiped the JDBC cohort before Add was ever pressed, and the Review showed
only documents (field-caught on the day-4 rebuild; the same trap almost
certainly explains older "the JDBC scan didn't add its terms" reports). A
non-empty grid now ALWAYS merges - row identity is source-based, so a
rescan refreshes evidence instead of duplicating - and the message says so
("other sources' rows are untouched"). A from-scratch grid is what Reset
all is for: explicit, never a side effect of previewing a second source.

## [1.36.54] - 2026-08-11

### Fixed - the auto-prune badge says WHY

Every auto-pruned row wore a hardcoded "KEY" badge, so a JSON envelope
field like export_date read as "dates have now been identified as keys"
(field-caught) - a mislabel presenting a correct prune as a wrong
judgment. The badge now reflects the Prune_Reason: KEY for surrogate
PK/FK ids, ENVELOPE for document-envelope fields, PRUNED otherwise; the
tooltip keeps quoting the full reason, and only genuinely key-pruned rows
claim their relationship travels to the physical model.

Also learned in the same field session and recorded here: Harvest-from-PDC
builds rows from the CATALOG, which carries no PK/FK metadata - so a
harvested grid cannot auto-prune surrogate keys, and it resurrects
everything PDC remembers (dated snapshot files included). Build review
grids from DIRECT scans; use Harvest to overlay what PDC governs. Whether
PDC's column entities expose key attributes (which would let harvest
prune) is an open probe - the estate was mid-rebuild when checked.

## [1.36.53] - 2026-08-10

### Fixed - the Review page rendered blank on .52

The silent-heal effect read catBusy in its dependency array, and that
state was declared ~300 lines below it. Dependency arrays evaluate during
render, so the reference hit the temporal dead zone and the whole page
unmounted to white - a class of crash neither the bundler nor a bundle
grep can catch, which is exactly how it escaped (field-caught seconds
into the .52 clean install). The declaration moved up beside its sibling
agent states with a comment explaining why it must stay there, and the
fix was verified by RENDERING the page, not by grepping the bundle - the
lesson as much as the fix.

## [1.36.52] - 2026-08-10

### Added - the Review lifecycle: approve the keystone, then complete

The taxonomy's settling was implicit and everything downstream guessed.
The strip now reads as the work is done: 1 - AI categories proposes,
"2 - Approve categories" is the KEYSTONE (product owner's word - the app's
verb is Approve), 3 - AI pass writes language inside the settled taxonomy.
Approving stores {at, categories} with the workspace, syncs the Dictionary
immediately, warns first if a kept category still looks like a physical
table/folder group, and reverts to actionable if the set drifts - visible,
never silent. Govern consults the keystone instead of only guessing.

And the stage now CLOSES deliberately: "Review complete -> Dictionary"
saves the glossary, syncs the Dictionary to the exact grid, records the
completion with the workspace, and moves on - warning (never blocking)
when the keystone is missing or AI pills are still pending. One moment
where everything is in sync, by construction. Wiring pinned in test_docs.

## [1.36.51] - 2026-08-10

### Changed - the same-source heal went behind the scenes

1.36.50 shipped the repair as a button; the product owner's correction
landed minutes later: "the steward shouldn't have to decide or do anything
- the categories have been set." Same-source duplication is damage, never
intent - no steward action can create two rows carrying one source column,
only the old label-keyed merge could - and a condition that is always
damage is not a decision. The heal now runs silently whenever the grid is
quiet (deferred while proposals or agents are in flight, since folding
re-indexes rows): no button, no toast, the grid is simply correct. Pinned
inverted in test_docs: the button text must NOT exist.

## [1.36.50] - 2026-08-10

### Fixed - row identity is evidence, not labels

The fresh-install exam's big one: 133 kept terms became 248, with 96 names
repeating across categories. Rows merged into the workspace on the old
Category|Term key - and Category and Term are precisely the fields a review
SETTLES, so after renaming, every re-ingestion (re-scan, harvest) matched
nothing and appended the whole estate again. Identity now comes from the
source columns a row carries - the one thing steward edits never change -
in a shared rowmerge module (Connect's merge delegates to it; the fold
preserves steward work by construction: owner's edits and Keep stand, only
evidence is absorbed). For grids the old key already damaged, Review's
DUPLICATES group grows a repair - "Fold same-source rows (N)", shown only
when damage exists - that folds each duplicate into its settled owner and
removes it. Shape pinned in test_docs, including "no Category|Term row key
survives".

### Added - Apply preflight: what will linger in PDC's tree

A PDC import updates terms in place (deterministic ids) but never REMOVES
categories, so the glossary tree accumulates eras - three naming
generations were visible in one tree (field-caught). "Check PDC tree for
lingering categories" on the Generate card reads what PDC currently holds
under the glossary (search-resolved root + entities/filter, honest
`partial` flag when pagination may truncate - PDC has no list endpoint)
and names the folders this export no longer carries, so deleting them
first is a decision, not a surprise.

## [1.36.49] - 2026-08-10

### Added - the Sync button says whether you are synced

It worked silently, which reads as not working ("not sure if the sync from
review button does anything" - fair). It now speaks the app's status-dot
language: a pulsing dot while the one-way sync runs, green "in sync with
Review · N refreshed" when the queue reflects the live grid, and red "not
synced - showing the last saved state" when the sync failed (the page
falls back to an unsynced read rather than dying). The button also
disables itself when no glossary is loaded on Review - there is nothing
to sync from, and a button that no-ops teaches distrust.

## [1.36.48] - 2026-08-10

### Fixed - the filter dropdowns follow the settled taxonomy

After AI categorize, the category filter kept offering the physical groups
- because DROPPED rows keep their scan-era categories forever (the agents
deliberately run on kept rows only), and the dropdown listed every row's
category as equals. Kept rows' categories now lead the list; values that
survive only on dropped rows sit under an explicit "- only on dropped rows
-" group, still reachable because filtering is also how a pruned key gets
found and restored. Same split for the tags filter, and the "Categories N"
chip now counts the glossary being exported (kept rows), not the residue.

## [1.36.47] - 2026-08-10

### Fixed - state writes self-heal when the directory vanishes

The fresh-install exam's first finding: wipe the state directory AFTER the
app has launched (the natural order - install, launch, remember the wipe)
and every write endpoint answered 500 Internal Server Error while reads
kept working. Import-into-app-connections and Harvest both died on virgin
soil: the atomic writers (api._write_json, the dictionary's _save_locked,
the audit trail's _save) created their temp files in a directory they
assumed still existed. All three now recreate it first - losing state to a
deliberate wipe is acceptable, a half-dead server is not. Reproduced,
fixed, and pinned by a test that deletes the state dir under a running
TestClient. Workaround on ≤.46: restart the app.

## [1.36.46] - 2026-08-09

### Fixed - retired tags disappear everywhere, and the registry stops shouting

Retiring a tag removed it from the allow-list while every term that ever
carried it kept displaying it - "uncategorized" sat on half the governed
vocabulary after its tag was long retired. A tag retire now strips the tag
from every term entry, and the tombstone beats a stale Suggested_Tags
string on rescan, so a durably retired tag can never ride back in on a
row. Both test-pinned.

The governed tables also stop reading as a wall of suggestions: the
per-row Fold / Retire maintenance actions reveal only on the row's hover
or keyboard focus. Approved means settled - the actions are there when
you come looking, invisible when you are not.

## [1.36.45] - 2026-08-09

### Fixed - folds are never blind, and never lie about succeeding

The governed table's Fold was a free-text prompt whose target hit an
EXACT-KEY, case-sensitive lookup that silently no-opped on a miss - while
the toast reported the fold as done. Now: the typed target resolves
case-insensitively against the actual governed vocabulary, a miss says so
out loud (retired names cannot resolve - tombstones are not targets), and
a confirm states exactly what happens before it does: what folds, into
what, and how many mapped columns move. The backend resolves
case-insensitively too, test-pinned both ways (resolution and the
full-no-op guarantee on a miss).

### Changed - the governed table says what it is

"Why am I going through the Term list again?" - because nothing said this
is the settled REGISTRY rather than another review. It now does: approval
happened in the pending queue, merges happened on Review; Fold and Retire
here are maintenance - cross-scan twins the fold advisor surfaces (drift
no single review can see; a freshly reviewed glossary usually has none,
and that silence is the Review doing its job) and undoing a decision that
turned out wrong. Stale AI advice is also dropped the moment its item
leaves the pending queue, so recommendations never outlive what they
recommended about.

## [1.36.44] - 2026-08-09

### Changed - calculated measures are vocabulary, and the formula rides along

The advisor called "Tier4 To Gallons" a technical calculation rather than a
business concept - but derived columns are frequently the KPIs the business
runs on: Total Before Tax is how billing reports, a tier-to-gallons factor
is how a tiered rate bills. The calibration now states it (a Term can carry
its formula in PDC - the derivation belongs IN the definition; being
computed is not a disqualifier), test-pinned like the rest of the rule set.

## [1.36.43] - 2026-08-09

### Added - deterministic guards around the advisor

Prompts reduce misfires; guards eliminate classes of them ("seems as
though the guardrails could be improved" - yes). Three now post-process
every piece of advice, each naming itself in the reason and keeping the
model's argument visible, and none of them touches the steward's own
buttons - sovereignty stays with the click:

- BREADTH GUARD: a model "reject" on a term seen in 3+ source columns
  downgrades to approve - a cross-cutting concept, very often the
  steward's own Merge (the System Name case, deterministically closed).
- PATTERN GUARD: a model "reject" on a term whose values carry a
  distinctive coded format downgrades - the scan proved people quote it.
- ALIAS GUARD: folding a specific concept into a vaguer one ("Alert
  Date" into "Date") is blocked by word-subset check; abbreviation folds
  ("Cust ID" into "Customer Identifier") pass untouched.

## [1.36.42] - 2026-08-09

### Changed - the advisor respects breadth and names

It recommended retiring "System Name" - a five-source steward MERGE - as
"a technical infrastructure component rather than a business concept"
(field-caught; advice-not-action is what kept it from being a durable
disaster). Two rules join the calibration, pinned by test: breadth is
evidence FOR the vocabulary, never against it - a candidate seen across
many tables is a cross-cutting concept, and a consolidated one may embody
the steward's own merge decision; and names of operational things ARE
business vocabulary, because asking for something by name is the test and
a name is precisely how the business asks. The prompt also now receives
the FULL source count instead of a silent first-three truncation.

## [1.36.41] - 2026-08-09

### Added - the id-vs-key evidence reaches the decision point

"Is Report ID an identifier or a key?" is a judgment call stewards face
over and over, and an inexperienced one will miss it (field-caught - Meter
ID needed a return trip). The scan already holds the discriminator: an
identifier the business QUOTES almost always carries a distinctive coded
value pattern (Meter ID is read off the hardware), while a surrogate key is
a bare unpatterned integer that only joins tables. That evidence now
travels: accrete captures the induced value pattern onto the pending entry,
the Review sync keeps it current, the pending queue SHOWS it in the meta
line ("value pattern ^MTR-\d{6}$" - or, for a patternless *ID* term, "no
value pattern - bare id, likely a join key"), and the AI advisor receives
it with the rule spelled out. The steward still clicks; now every level of
experience sees the tell.

## [1.36.40] - 2026-08-09

### Fixed - the Dictionary adjudicates the Review you actually have

The Review -> Dictionary sync rode the glossary SAVE, and a save only fires
on an edit - so installing a build with sync fixes and walking straight to
the Dictionary showed a pre-edit queue (field-caught: "pH Level" corrected
on Review, still pending as "Ph Level"; "there's a gap between the changes
made in the Review and whats picked up by the Dictionary" - exactly right).

Two closures. The page now SYNCS ITSELF ON ENTRY: it posts the live rows to
the new /api/tagdict/sync (same one-way rules - pending only, governed
entries never change; accepted edits refresh, corrected casings adopt,
auto-pruned keys retro-retire) and renders the refreshed summary, fetching
stale-health only after the sync lands. And a "Sync from Review" button
sits beside AI review for mid-session refreshes - so the advice always
targets current entries, never a stale queue. API-tested both ways
(sync adjudicates without a save; an empty sync is a plain read).

## [1.36.39] - 2026-08-09

### Changed - upgrading says "Upgrade", and does it in one pass

The maintenance page offered two generic radio choices, neither of which
said Upgrade, and preselected the one that chains the OLD version's
uninstaller wizard into the middle of the install - the messy details
screen a field upgrade hit. The page now leads with what matters ("your
glossaries, dictionary, roster and settings are never touched - only
application files change"), labels both paths truthfully, and preselects
"Upgrade in place (recommended)": one clean pass, which this installer
makes safe by design because the vendored python tree is replaced
wholesale rather than overlaid. The uninstall-first path stays available
for a deliberate clean sweep; same-version and downgrade flows are
unchanged.

## [1.36.38] - 2026-08-09

### Added - the pending queue proves its evidence is current

The Dictionary became a stage-gate when it joined the workflow (Review ->
Dictionary -> Govern), and a gate full of debris makes the steward regress:
re-litigating settled decisions and dead scans instead of ruling on new
vocabulary. Pending entries whose sources, name and aliases appear in NO
saved glossary are now detected server-side (/api/tagdict/pending-health -
the universe is EVERY saved glossary, so cross-domain vocabulary is never
flagged), badged "stale" in the queue with the reason on hover, and
retirable in one click per section ("Retire stale (N)"). Durable and safe:
a real concept re-proposes itself with evidence on a future scan. Together
with 1.36.37 (keys never enter, case renames flow, fossils detectable) the
queue now holds exactly one thing - questions the current estate actually
raises.

## [1.36.37] - 2026-08-09

### Fixed - the pending queue respects decisions already made

Two field-caught leaks in the Review -> Dictionary flow. A CASE-ONLY term
correction ("Ph Level" -> "pH Level") refreshed the pending entry's
definition but never its name: the case-folded index matched, so the rename
path - built for exactly this family of fixes - was unreachable for it. The
entry now adopts the steward's casing and keeps the scan's spelling as an
alias, so rescans fold instead of re-proposing.

And auto-pruned structural keys (System ID, Alert ID...) piled into the
pending queue asking the steward a question the scan itself had already
answered. They no longer enter it at accrete time (nor seed tags), and
entries absorbed before the guard retire on the next glossary save - popped
and tombstoned exactly like a steward click. Rows merely unticked WITHOUT a
Prune_Reason are deliberately untouched: dropped from one glossary is not
retired from the company vocabulary.

## [1.36.36] - 2026-08-09

### Changed - the pending-review advisor knows operational is not technical

It recommended Retire for "Account Status" and "Active Customers" - the
exact concepts a business runs on - because its whole calibration was one
line, and a small model reads "status of a record" as a technical artifact.
The bar is now explicit: the test is "would someone in the business ask for
this by name?" (statuses, lifecycle states and operational measures count);
reject is scoped to structural/file artifacts only (surrogate keys and ids,
fields of one-off dated snapshot files, names too vague to ask for);
aliasing a specific concept into a vaguer one is forbidden ("Alert Date"
into "Date" governs nothing); and - the load-bearing line - rejection is
DURABLE (never re-proposed) while a wrong approve costs the steward one
click, so uncertainty resolves to approve. Test-pinned. Advice, as ever,
is advice: the steward clicks.

## [1.36.35] - 2026-08-09

### Fixed - stewardship survives the taxonomy settling

Per-category stewardship is keyed by category NAME and baked into the JSONL
the Policy Generator and resolve depend on - but the name was a loose
pointer. Renaming a category on Review left its override behind, and
Govern's next visit rebuilt its cards from live categories only and
re-baked, silently destroying the steward's decision. Now Review's Rename
migrates the override with the category (on collision the destination's
filled slots win - both are steward decisions, the surviving name is the
deliberate one - and its blanks inherit). Overrides orphaned by FOLDS (many
groups into one business category) are preserved in the baked governance -
they match no rows at generate time, so they cost nothing - and Govern
surfaces them by name with a discard button, instead of vanishing them.

### Fixed - Apply's "no steward" warning reads the governance that bakes

Govern reported "stamped 114 of 114" and Apply immediately warned that all
114 would export with no steward. The preflight read r.Steward - a field
nothing in the codebase writes - so it warned always, about everything,
regardless of what the steward had done. It now mirrors the actual bake:
category override, then default steward, then the stamped row fields - and
only counts a term unowned when all three come up empty.

## [1.36.34] - 2026-08-09

### Added - Govern shows dots and locks the roster while expertise generates

The user started clicking buttons because nothing said "busy" (field-caught):
expertise generation ran behind a line of grey text. Worse than cosmetic -
the completion merge maps over the roster AS CAPTURED AT CALL TIME, so any
edit made mid-run (a function toggle, typed expertise, a Remove) was
silently thrown away when results landed. The pulsing dots now ride the
status line, the Suggest button reads "Generating...", and the roster's
mutating surface - function chips, expertise fields, Remove, Add, Save
roster - locks until the merge lands, from every entry point (the roster
button, the Keycloak fetch's auto-fill, the one-click macro). The dots CSS
moved to index.css: it is the app-wide busy idiom now, not a Review detail.

### Added - stewardship flags categories that are still physical groups

After a fresh table scan, Govern listed 14 "categories" as equals - six the
steward had settled and eight that were humanized table/folder names
(Monthly Usage, Tiered Rates...), the review's evidence fallback awaiting
categorization. Assigning stewards to those keys governance to names about
to be renamed or folded. Each such card now carries a "physical group"
badge (detected by slug: every kept member's source contains the category's
own name as a table/folder segment) and a notice above the list counts them
and links back to Review - finish 1 - AI categories or Rename, then set
stewardship over the settled set.

## [1.36.33] - 2026-08-09

### Fixed - accepting one field no longer lights the other field's LLM chip

Accept a proposed Definition and the Purpose chip lit too, with its proposal
still sitting unaccepted (field-caught, screenshot and all). Every accept
carried the row-level LLM_Enriched flag - a legacy marker from before
per-field provenance existed - and the chips fall back to it when a
per-field flag is missing, which is exactly the state of a field you have
not accepted yet.

Accepts now carry per-field flags only (whole-row accepts strip the legacy
flag as well), and the fallback is scoped to true legacy rows - ones with NO
per-field flag at all - so rows already damaged by the old carry heal on
sight. The LLM-enriched count reads all four flags. Pinned in test_docs so
the chips stay truthful: they are the steward's record of what the model
wrote versus what a human did.

## [1.36.32] - 2026-08-09

### Fixed - the AI pass can now match AI review, and says how

AI review kept writing real definitions while the sweep left templates - on
the same rows, supposedly with "the same prompt". It wasn't the same prompt.
The batched path compressed everything the single-row path sends rich:
reference values cut at 90 chars (vs 200), scan reasoning at 120 (vs 160),
the drafts at 120 (vs 220) - and its instructions dropped the one line that
does the most work ("purpose: why it matters - NOT a restatement of the
definition"). On top of that, N rows sharing one completion pushes the model
into template rhythm, echoing its own phrasing row after row.

Three changes close the gap. A batch of ONE now routes to the rich per-row
prompt - so Settings' Batch size at 1 literally runs the AI-review prompt,
sweep-wide. Multi-row batches carry the full evidence truncations and the
missing instructions, plus an explicit "do not reuse sentence templates or
phrasing across entries". And the Settings hint, the pass description and
the AI-review tooltip now tell the truth about the trade: batch size is the
quality dial - 1 for depth, higher for speed. Field-caught on the GPU box:
the Gis folder term went from "Holds Gis data for reference" to "Geographic
Information System data representing physical infrastructure assets" the
moment the row got a call of its own.

## [1.36.31] - 2026-08-09

### Changed - Dictionary joins the workflow, between Review and Govern

The launcher banner and the Review guide have taught Connect -> Review ->
Dictionary -> Govern all along; only the sidebar disagreed, exiling
Dictionary to a one-item Governance group. Approval stopped being a
side-trip when Review began streaming accepted edits into the pending
vocabulary and category pills made it a per-run gate - so the nav, the
breadcrumb, the header stepper (five stages now) and the Home workflow map
all place Dictionary in the pipeline, with a dotted back-edge on the map
for the flywheel: the approved vocabulary governs what the agents may
propose next. Review's forward button is now "Approve vocabulary ->" and
the Dictionary page gained "Set stewardship ->".

### Changed - the AI pass explains itself without its own changelog

"Why one agent: it replaced three (Enrich, AI suggest, AI categorize)..."
was refactoring history, not guidance (user's call). The pass now gives the
reason a steward actually needs: every field is proposed together, from the
same evidence and the same guardrails, so a proposed name never contradicts
its own definition, category or tags.

## [1.36.30] - 2026-08-09

### Added - Detection's Auto vs Mapping-only, explained where terms are explained

The DETECTION toggle in a row's expanded editor carried a one-line tooltip
about Mapping-only and said nothing about Auto - the default whose behaviour
actually branches. "How terms are defined & built" now carries a Detection
entry alongside Category, Name and the rest: Auto answers "can this term be
recognised by the look of its values?" from evidence (a profiled value shape
seeds a detection method in the exported Registry; no shape leaves the
question open, and the Policy Generator asks the steward for a seed), while
Mapping-only closes the question deliberately - term-link governance only,
no detection method expected, and it wins even over existing seeds. The
toggle's tooltip now states both halves and points at the panel.

## [1.36.29] - 2026-08-09

### Changed - the AI categories busy indicator is dots, not a beam

The indeterminate sweep read as a stray cursor beam, and it was the only
lateral motion in an app whose one "working" idiom is an opacity pulse (the
status dots, the Dictionary review chip, the agent in-flight batch). The
progress track is gone entirely - a track invites reading progress into it,
and none exists for one long call - replaced by three accent dots pulsing in
staggered phase, a living ellipsis on the label. Reduced-motion gets static
dots, same as everywhere else.

## [1.36.28] - 2026-08-08

### Fixed - run.sh installs pdc_client itself

A fresh `./run.sh` built its venv from requirements.txt and then imported
api.py straight into `ModuleNotFoundError: pdc_client` - the package lives one
level UP (repo root on a dev checkout, tarball root on the Linux lab tree) and
requirements.txt does not carry it. Both trees put `pyproject.toml` beside the
package, so run.sh now performs one editable install of `..` when the import
fails, and dies with a plain explanation when there is nothing to install
from. Field-caught on the lab VM; the same gap cost the dev machine a morning
two days ago - the launcher now closes it everywhere instead of each machine
rediscovering it.

## [1.36.27] - 2026-08-08

### Fixed - inline edits no longer lose focus after every letter

Typing in Term or Category recomputed the duplicate clusters on each keystroke,
and the cluster key - which contains the row's own text - was part of the React
key of the row's subtree. Renaming the key unmounts the subtree, so the input
was destroyed mid-word and the cursor lost: one letter at a time, as reported
from the field.

Grouping now works from a snapshot frozen when focus enters the grid and
regroups when it leaves - the structure holds still while you type, and the
reshuffle happens at the moment losing the element costs nothing. Everything
rendered inside still reads the live row; only the KEYS read the snapshot.

## [1.36.26] - 2026-08-08

### Fixed - "ph" no longer expands to Phone, because it might mean pH

Field-caught on a GPU review of a water utility: the built-in abbreviation map
turned `ph_level` into **"Phone Level"** - and the PII name-matcher then read
the expanded name, stamping CONTACT_INFO, `contact;privacy` tags and MEDIUM
sensitivity onto a **chemistry measurement**. One wrong generic assumption
cascaded straight into classification - drift condition Y, caused by our own
builtin.

`ph` is genuinely ambiguous - Phone in a CRM, pH in a lab - and a global map
cannot know. It is removed from the builtin expansions and from the duplicate
matcher's normaliser (where it made pH columns cluster with telephone columns).
Ambiguous tokens belong to the **domain pack**: rename the term to *pH Level*
once, Export pack records `ph -> pH` as the company's own abbreviation, and
every later scan gets it right deterministically. `phn` still expands to Phone.

## [1.36.25] - 2026-08-08

### Changed - AI categories is a primary button, and shows that it is working

Both field-caught on first GPU use. The button is primary (blue) like the AI
pass it precedes. And because it is ONE long call, the running state is an
**indeterminate sweep** with a caption ("one call over the whole schema
graph… bigger models take up to a minute") rather than an invented percentage
- honest feedback over fake precision, and `prefers-reduced-motion` gets a
static bar.

## [1.36.24] - 2026-08-08

### Changed - AI categories sits before the AI pass, numbered

The buttons now read as the work is done: **1 · AI categories** (settle the
taxonomy - one schema-wide call), **2 · AI pass** (write the language inside
it). Previously AI categories sat in the duplicates bar, after tools it should
precede - the field caught it on first use. Definitions get written against
final groups, and the two agents never fight over the Category column.

## [1.36.23] - 2026-08-08

### Changed - AI category assignments land as pills, not a bulk confirm

Acceptance is the steward's approval - the standing rule for everything the
model proposes - so AI categories now flows through the shared proposal
machinery: each assignment is a **Category pill** on its row (old value ->
proposed value), accepted per pill or with Accept all, dismissible like any
other proposal, and nothing touches a row until accepted. The strip's agent
description explains the pass; a category is a pure **abstraction** with a
many-to-one link - *Clients* can hold `customers`, `account_alerts` and
whatever else serves that subject - and Rename adjusts the label at any time
before Export pack freezes the set.

## [1.36.22] - 2026-08-08

### Added - Review says when the glossary's scope is too wide

"Hopefully the steward will realize the domain needs to be smaller" is a hope,
not a mechanism. When a review spans more than 20 physical tables, Review now
says so: a glossary that wide is usually more than one business domain - too
many categories, no single accountable steward - and the fix is scope, not a
bigger taxonomy. The notice points at the working practice: one bulk load per
subject area via `includePatterns`, one glossary per domain with its own
steward, the cross-glossary check keeping shared concepts reused, and one
company pack serving every domain.

## [1.36.21] - 2026-08-08

### Added - AI categories: an abstract business grouping from the schema

The physical fallback gives structure; this gives it business language. The new
**AI categories** button (Review) shows the model exactly what the scan proved -
each table, its columns, and its FK references - and asks for a holistic
grouping: the model decides how many categories best represent the business
(the fewest that discriminate, typically 5-10, up to 12 on a 20+ table estate),
places every table in one, and names them as **abstractions**, not table names.

Proven live on the AWC schema: `customers`, `account_alerts` and
`monthly_usage` - the FK-linked cluster - came back as one *Customer
Information* category, with water quality separate.

Guardrails, all tested: proposals only (a confirm applies them); tables the
model cannot place are **reported and keep their physical group**, never
guessed; offline or with a broken model it degrades to nothing proposed rather
than an error; and the taxonomy the steward settles is **frozen by Export
pack** - later scans categorise deterministically, and changing the set again
is a deliberate act that the pack merge surfaces as conflicts, not drift.

### Changed - packless categories come from the estate, not a wall of Uncategorized

A first scan with no domain pack filed 123 of 123 terms under **Uncategorized**,
and the AI could not help: it only picks from a known list, and the list was
empty. The steward was left guessing a taxonomy out of nothing - which is
exactly what a steward must never be asked to do.

The old behaviour was itself a fix: the engine once leaked an invented
water-utility taxonomy, and the cure was to assert nothing. Right diagnosis,
over-corrected. The estate's **physical structure is not invented** - the scan
proved `monthly_usage` exists. So `categorize()` now falls back to the
humanised physical name: *Monthly Usage* from the table, *Gis* from a
document's top folder. Business words are still never asserted.

The steward's job becomes **renaming a group once** - filter to a category and
the new **Rename "…"** button renames it on every row (the filter follows). Then
Export pack records the physical → business mapping, and the next scan
categorises deterministically. Verified live: a packless DDL scan now returns
*Monthly Usage* and *Water Quality Reports*, zero Uncategorized.

## [1.36.20] - 2026-08-08

### Changed - the AI pass explains itself in paragraphs

The proposal strip's description was one dense block. Now four short paragraphs
with a lead each: what one call covers, **what it may not decide** (the
guardrails), why it replaced three overlapping agents, and how to redo one row
or one field. Same text serves the "How to review" guide - one source, two
surfaces, as before.

## [1.36.19] - 2026-08-08

### Fixed - a pasted URL in the `host` column no longer fails the ingest

The minio row's `endpoint` IS a URL, so people reasonably write the postgres
`host` the same way - and `http://192.168.x.x` then resolves as nothing, the
ingest job ends `FAILED`, and the row gives no hint that punctuation was the
whole problem. The intent is unambiguous, so the loader now strips a scheme, a
path and a `:port` tail (the port has its own column) from `host` for all three
JDBC kinds. The RECREATED badge in the same run confirmed the 1.36.17
delete/recreate machinery working in the field.

## [1.36.18] - 2026-08-08

### Changed - the explainers now teach the endpoint rule that cost a scan

A laptop bulk load failed its object-store scan with
`UnknownHostException: awc-documents.pentaho.io`. Two lessons, now stated on the
Connect and Files panels:

- **Endpoints are reached by PDC's workers, not by the machine running this
  app.** Only the PDC base URL needs to be reachable from your laptop; the
  MinIO endpoint is consumed inside the VM, where containers do not inherit the
  host's hosts file.
- **Use the VM's IP, never a hostname.** Given a hostname, the S3 SDK switches
  to virtual-hosted addressing and prepends the bucket (`bucket.your-host`),
  which resolves nowhere. An IP forces the path-style addressing MinIO needs.

The examples are placeholders - the fresh-install guard rejected the first
draft for carrying a real lab host into the shipped bundle, which is precisely
what it exists to do.

## [1.36.17] - 2026-08-08

### Fixed - columns profile from the API, and "recreate if exists" works

Completes 1.36.16, with one correction to it: the 53 columns credited to the new
scan chain **pre-existed from a manual UI scan**. What 1.36.16 actually proved
was files and folders. Columns are proven now, and they come from somewhere
better:

**The file options live in the PUBLIC data-discovery job's `configs`** - the job
`profile_source` already ran, with `configs: {}`. Empty. The whole time. On the
file scan those same keys silence enumeration entirely; in discovery's configs
they profile the CSVs:

    scan (minimal body)                          -> 21 files, 0 columns
    data-discovery configs={withProfile,
      headerExists, withDocMetadata}             -> 53 columns, immediately

So the pipeline is: TEST_CONNECTION lists -> METADATA_INGEST persists (both
internal, minimal bodies) -> data-discovery profiles (public, flags in configs).
The UI's Structured/Unstructured options and the CSV columns now feed the
configs. The age sliders are sent only when nonzero - unproven in configs, and
a build that ignores them scans more rather than less.

**And "recreate if exists" works end to end**, three fixes deep:

- `delete_data_source` uses the internal `CLEANUP_DATASOURCE` job (the REST
  DELETE answers 404 on this build). The key is `id`, **not** `resourceId` -
  captured from the catalog's own Delete button after resourceId earned a 500.
- The delete also calls
  `rule-api/v1/metadata-rules/cleanUpDeletedDataSourceRuleAssociations`,
  without which the old id lingers in rule associations.
- Deletion is asynchronous with no usable job id, so the delete **polls for the
  source to actually disappear** (~10s) and the follow-up create retries briefly
  on "Duplicate key violation" - the name leaves the list before the unique
  index frees.

Also raised `_req`'s error-detail cap from 600 to 2000 characters: PDC echoes
the whole submitted record before the reason, so the cap was cutting off
"Duplicate key violation" - the very text the recreate guard reads. A guard
that fails closed is only as good as the evidence it is shown.

Measured, forced recreate on the lab: RECREATED -> 21 files/folders -> 53
columns, all green, no manual step.

### Security - both Dependabot advisories cleared

- **postcss** bumped 8.5.19 -> 8.5.26 (advisory fixed in 8.5.23). Build tooling
  only - the emitted bundle is byte-identical.
- **glib** dismissed as *not used*, with the evidence: it is a transitive
  dependency of tauri 2's **Linux** GTK stack, `cargo tree -i glib` on the
  Windows host target is empty, the GTK stack pins it below the patched 0.20,
  and the planned Linux lab edition ships no Tauri shell. Re-evaluate only if a
  Tauri Linux build is ever added.

## [1.36.16] - 2026-08-08

### Fixed - the object-store scan enumerates. It never had.

A bulk-loaded object store reached PDC with its files catalogued and nothing
inside them, or with no files at all. Every badge read OK. Two days of flags,
paths, patterns and `fullRescan` changed nothing, and MinIO's own request trace
settled why: across four scans PDC issued **zero** S3 calls, while a control
listing was captured in full.

The request body was wrong underneath, and a capture of the catalog's own
**Test Connection** call showed it:

| We sent | PDC's UI sends |
| --- | --- |
| `accessId`, `accessKey`, `secretKey`, `secretAccessKey` — echoed back from the stored record, **already encrypted** | *nothing* — PDC looks its own up from `resourceId` |
| `excludePatterns: ["*.md"]` | `excludePatterns: [{"value": "*.md"}]` |
| `withProfile`, `headerExists`, `containers`, `patternType`, `contentScanType`, `configMethod` | none of them |

Handing the worker ciphertext where it expected a credential is what silenced
it. Every flag tried before this was tuning on a body that was broken in its
bones.

**And it is two jobs, in order.** `TEST_CONNECTION` — despite the name — is the
pass that **lists** the bucket and stores the result; the scan then persists what
it found, via `lastTestConnectionId`. Skip the first and the second walks
nothing, completes, and reports success over an empty catalog.

Measured on the lab, same bucket, through the loader itself:

    before   FOLDER/FILE  0    COLUMN  0
    after    FOLDER/FILE  21   COLUMN  53

`_scan_config_body()` now builds the minimal shape, `internal_test_connection()`
runs the listing pass, and `bulk_load_one` sequences them. Tests pin the order
and assert no credential is ever sent.

**A public route exists for the listing pass** —
`POST /api/public/v2/jobs/execute/test-connection` returns 200, as does the v3
bulk form — but whether it enumerates is **unproven**: it produced the same
`SCAN_ROUTER` pipeline with no file list, and confirming needs a data source
with no entities. Recorded in the code, worth retrying with a clean source. The
internal path is the one that is measured.

## [1.36.15] - 2026-08-08

### Added - how to build a domain pack, written down

The practice was already encoded in the tools and documented nowhere.
`domain_packs/README.md` explained the keys and the generator; neither it nor the
strategy guide said how to *choose* the vocabulary — which is the part people get
wrong, by sitting down to author an industry taxonomy before scanning anything.

`packinit` already gives the reason, and it is the whole rule in one sentence:

> `table_category / table_terms / terms / tag_rules` left **EMPTY on purpose**.
> Inventing table names for a database nobody has scanned yet produces rules that
> never match **and read as if they were curated**.

Now stated in both places:

- **[GLOSSARY-STRATEGY.md](GLOSSARY-STRATEGY.md) §5** — *Building the domain
  pack*: author the category list and nothing else; grow the rest from reviewed
  rows; why `abbreviations` earn the most and are the least guessable; and why
  industry standards (AWWA, FIBO, BIAN) are a **check after** a first pass rather
  than a seed — seed from one and you govern terms nobody says out loud.
- **`domain_packs/README.md`** — the same practice, short, at the top where
  someone editing a pack is already standing, linking to the fuller rationale.

Sections 5–7 of the strategy guide renumber to 6–8.

## [1.36.14] - 2026-08-08

### Added - the app now says what it is missing

Two inputs are optional, and both degraded **silently** — the run succeeded and
looked identical to a healthy one, which is the same failure shape as the
`profile / discover` default that shipped unticked in 1.36.5.

- **No domain pack** — the engine returns `{}` and falls back to generic
  vocabulary: `mbr_no` stays *Mbr No* instead of becoming *Member Number*, and
  categories come from generic keywords. The glossary is valid and **bland**,
  which reads as the app underperforming rather than as an input nobody supplied.
  Connect now says so, and points at the fix: scan, review, then export a pack —
  it grows from rows already approved.
- **No stewardship** — the JSONL exports and PDC accepts it, with every term
  owned by nobody. The Generate card now counts them:
  *"N of M term(s) will export with no steward"*, with a link to Govern.
  Deliberately not a block: a draft circulated for comment is a legitimate thing
  to want.

New `GET /api/readiness` reports both. A pack carrying only a domain name counts
as **absent**, because it produces the same bland glossary as no pack at all and
must not read as configured. It never raises — a broken pack still answers 200
with `present: false`, since this warns and must never be the thing that stops
the app loading.

### Changed - the example roster is genericised

`domain_packs/water_utility.people.json` carried `@azwater.gov` addresses. The
folder is excluded from the installer and never shipped, but real-looking
customer identifiers do not belong in the repo either. Now `@example.org`.

### Fixed - .env.example described the removed Flask app

It told people to place the file *"same folder as app.py"*, an entry point
removed at 1.35.0. The file-locations section now explains that those variables
**override** the state files — names are not fixed, point them anywhere — and
that unset they resolve through `core/paths.py`.

## [1.36.13] - 2026-08-08

### Added - the remaining explainers, and the transparency viewer is reachable again

Every panel lost with the Jinja UI at 1.35.0 is back. Eleven were real content;
the twelfth, *"Review duplicate term names"*, was a section heading for a feature
the React page already carries in better form (the duplicate advisor, with
evidence, live probe and AI), so it was not recreated.

- **Files** — browsing the object store (S3 API): `list_objects_v2` with a
  delimiter, and why the folder tree is really common prefixes.
- **Review** — how terms are defined & built (why the count you review is far
  smaller than the column count), and this page's calls.
- **Govern** — fetching the roster from Keycloak, including why the admin token
  comes from `master` while users come from `pdc`, and why a copied roster
  produces bindings that resolve to nobody.
- **Apply** — generating the JSONL: deterministic `UUID5` ids, which is what
  makes a re-import update in place rather than duplicate.
- **Dictionary** — the governed vocabulary API, and the pack flywheel.

**The transparency viewer is wired back in.** `/api/source` has served 18
whitelisted modules since the Jinja days and stayed server-side tested
throughout, but nothing called it after that UI went - a whole feature live and
unreachable for a release. It is now a panel on Home: pick a module, read it
straight from disk. Runtime state stays off the whitelist and answers 404.

`test_docs.py` pins every panel title per page **and** the viewer's wiring, since
the way all of this was lost is that nothing failed when it went.

### Changed - seed data is gated, and says what it is for

`/api/seed` is the only endpoint that writes to a connected database. Its whole
protection was a browser `confirm()` and "only empty tables" - which reads as
safe and is not: a production estate has empty tables (a new feature's, an audit
table not yet written to, a staging table between loads) and they would have been
filled with fabricated rows.

- **`allow_sample_data` on the connection**, off by default and enforced
  server-side, so a frontend change can never be the only thing in the way.
- **A read-only dry run** (`seed_sample.plan()`) naming the exact tables. "It
  only fills empty tables" is a reassurance; "it will insert into `audit_log` and
  `staging_customers`" is a decision.
- **Type the database name** to confirm - not something done by reflex on the
  wrong connection.
- **TRAINING AND DEMO DATABASES ONLY** now appears in the module docstring, the
  refusal message, the checkbox and the explainer.

## [1.36.12] - 2026-08-08

### Added - the Connect page's four "Under the hood" explainers are back

Removing the legacy Jinja UI at 1.35.0 took **12** explainer panels with it. The
React app never carried them, nothing referenced them and no test covered them,
so the loss surfaced only when someone went looking. These are the first four,
all on Connect:

- **Connection types & what each button does**
- **Under the hood** — bulk-loading data sources (PDC Public API)
- **Under the hood** — reading PDC's catalog
- **Under the hood** — what a database scan runs

**Rewritten against what the code does now, not pasted.** The originals were
1.34-era and several claims had gone stale - a stale explainer is worse than
none. Corrections made while porting:

- the old text said *"every call is read-only"*. **Seed data writes**, and now
  says so. The rest of the page is read-only, verified: the only `CREATE TABLE`
  in the scan engine is a regex that *parses* DDL.
- the bulk-load panel documents the internal `POST /api/start-job` call, its
  `withProfile`/`headerExists`/`withDocMetadata` options, and the hostname
  routing that 401s it on a bare IP while the public API works - all of which
  cost an evening to establish and was written down nowhere a user could see.
- the harvest panel states what it does **not** touch: no database, no object
  store, no credential for either.
- the scan panel names the actual catalog views (`information_schema.columns`,
  `table_constraints`/`key_column_usage`, `pg_index`/`pg_constraint`, Oracle's
  `all_tab_columns`) and says values are used for statistics and not stored.

`test_docs.py` now pins the expected panel titles per page, because the way
these were lost is that nothing failed when they went. The list grows as the
remaining eight are ported.

### Known - the transparency source viewer is orphaned

`/api/source` serves 18 whitelisted modules so a learner can read exactly what
runs. It is live and server-side tested, and the React app calls it nowhere - it
lost its UI with the Jinja shell. Recorded rather than quietly wired.

## [1.36.11] - 2026-08-07

### Changed - the option rows now split by SOURCE TYPE, as PDC does

1.36.10 split them by file kind, which was the wrong axis. PDC divides the work
by what the SOURCE is:

| Row | PDC job | Applies to |
| --- | --- | --- |
| **Structured** — `profile` | Data Profiling | a database's tables |
| **Unstructured** — `discover` | Data Discovery | an object store's files |

The file-level switches are options **on** the discovery pass, not a category of
their own - which is where PDC's own Configure Process dialog puts them, and
where the code already drew the line (`job = "data-discovery" if object_store`).
A bucket holds documents and csv files together, so one scan carries both:

    STRUCTURED    profile
    UNSTRUCTURED  discover · profile files · first row is a header
                  document metadata · skip files newer than [n] days

`profile files` is PDC's "Profile structured and semi-structured files"
(`withProfile`). The four options beneath `discover` grey out when it is
unticked, so nothing looks clickable but ignored.

### Removed - the ML-dependent options

`summaries`, `address detection` and `classification` all require ML to be
configured. Offering a switch that silently does nothing is worse than offering
none, so they are gone from the UI and the CSV, and pinned false in the scan
body. Run them deliberately from PDC's own UI once ML is set up - which is also
the right moment for classification, since it assigns business terms that do not
exist until this app's glossary has been applied.

### Added - skipRecentDays

PDC's "Files Modified / Accessed More Than N Day(s) Ago" sliders, as a number on
the Unstructured row and a `skipRecentDays` CSV column. 0 scans everything;
raise it to skip a landing area still being written to. `row_int` reads it with
the same contract as `row_flag` - blank, missing and unparseable all mean "use
the default", so a meaningful **0** is never confused with an empty cell.

CSV columns are now `profile`, `discover`, `profileFiles`, `header`,
`docMetadata`, `skipRecentDays`; `datasources.sample.csv` ships all three shapes.

## [1.36.10] - 2026-08-07

### Added - structured and unstructured files get their own scan options

A CSV in an object store and a PDF in the same bucket want opposite treatment.
The CSV wants its columns profiled and its first row read as names; the PDF has
no columns at all and wants its document properties instead. One set of switches
could not serve both.

**In the UI** the options are now three labelled rows:

    Load          ingest metadata · recreate if exists
    Structured    profile / discover · first row is a header
    Unstructured  document metadata · summaries · classification [second pass]

**In the CSV** each has a matching optional column - `profile`, `header`,
`docMetadata`, `summaries`, `classification` - which overrides the UI default
for that row. So one bucket can be registered twice and scanned two ways:

    minio,Documents_Structured,...,*.csv;*.json,...,true,true,false,false,false
    minio,Documents_Unstructured,...,*.pdf;*.docx,...,false,false,true,false,false

A **blank or absent column means "use the default"**, never `false`. A CSV
written before these columns existed behaves exactly as it did - silently
switching profiling off for every unfilled row would repeat 1.36.5's bug in a
new place, so `row_flag` treats blank, missing and unparseable alike and the
tests pin all three.

**classification carries a `second pass` chip and stays off.** It assigns
business terms, which do not exist until this app's glossary has been built and
applied - from the very profile the scan produces. On a first pass it can only
mark everything unclassified. Run it deliberately, afterwards, over documents.

`datasources.sample.csv` now ships all three shapes: a database row leaving every
option blank, and the two object-store rows above.

## [1.36.9] - 2026-08-07

### Changed - the bulk load's options sit on their own row

Mixed into the button row they wrapped unpredictably as the window narrowed, and
**first row is a header** ended up alone on a line below the buttons, reading as
if it belonged to something else. Buttons keep their row; the four options sit
beneath in one group with a tighter gap, so they read as switches on the action
rather than as more actions. Verified in the running app: options below buttons,
all four on one line, defaults unchanged.

### Fixed - run.ps1 carried the same dead-UI message as run.sh

`run.sh` was corrected at 1.36.4; the PowerShell launcher still told the operator
it was "serving the legacy UI until it is". The Jinja shell went at 1.35.0 and
`/` now answers 503. Its guard was also the narrower kind, requiring the frontend
directory to *exist* before checking for the build.

Fixing the same sentence in two files is the smell, not the bug: any future
launcher wants the same check, and the honest fix would be one script both call.

### Note - the dev venv needs pdc_client installed

`pdc_client` lives at the repo root and is not importable from
`glossary_generator/`, so `run.ps1` fails at import with `ModuleNotFoundError`
unless the package is installed into the dev venv:

    glossary_generator\.venv\Scripts\python.exe -m pip install -e .

This is the arrangement `stage-app.ps1` already documents, and it cannot reach
the installer: `.venv` is in `$excludeDirs`, and the bundle takes its own copy of
`pdc_client` by robocopy.

## [1.36.8] - 2026-08-07

### Added - Review says which terms PDC already holds, and in which glossary

**Check PDC for existing terms** on the Review page badges each candidate that
already exists, with the owning glossary name: `IN PDC · Customer`.

Resolve has always looked terms up catalog-wide and reused an existing id rather
than minting a duplicate, so nothing was ever written twice. But Resolve is step
4 — a steward could spend twenty minutes authoring a definition for a concept
Billing already owns and only learn of it on Apply. This runs the same lookup
during Review, while changing your mind is still cheap.

Deliberately **not** scoped to one glossary: seeing across them is the point. An
enterprise runs many small governed glossaries rather than one large one, and
the reuse rate climbs as coverage grows — so the check earns more the further in
you are.

`POST /api/pdc/terms/existing` takes the kept term names and returns
`{name: {id, glossaryId, glossary}}`. Glossary names resolve once per glossary,
not once per term. Credentials are used for the call and never persisted, the
same as every other PDC call the app makes.

## [1.36.7] - 2026-08-07

### Fixed - the file scan never asked PDC to profile the files

An object store loaded through the bulk loader ended up in PDC with its CSVs
catalogued and **no columns** - or columns named `Column-0 … Column-9`, which
looks like real structure and is not. Every badge read OK.

PDC's file system scan defaults **`withProfile: false`** and
**`headerExists: false`**, and the loader sent neither, so it inherited both.
Confirmed against a real job record from PDC's own Configure Process dialog
(`jobType: "File System Scan"`, `schemaId: "file_system_scan"`):

| Dialog checkbox | Parameter |
| --- | --- |
| Profile structured and semi-structured files | `withProfile` |
| Treat first row as header | `headerExists` |
| Compute checksum of document content | `withChecksum` |
| Document Metadata | `withDocMetadata` |

The switches belong on the **scan**, not on the Data Discovery job that follows
it - the scan reads the files; the aggregation stage after it only rolls up what
the scan produced. Both are now set explicitly, with **first row is a header**
exposed on the bulk load card (defaulted on) so a headerless CSV stays scannable.

### Why classification stays off

PDC's Data Classification assigns **business terms** - which do not exist until
this app has built the glossary, and it builds it from the very profile this
scan produces. Enabled on a first pass it can only mark everything unclassified,
leaving a pile to resolve by hand. PDC itself defaults it off.

The order that works: scan and profile, let the app generate the glossary and
apply it, and only then - if wanted - run a second, deliberate Discovery pass
with classification on over **unstructured** documents, where there are no column
names to reason from. Structured files never need it; the app assigns their terms
directly, with the profile evidence behind each one.

## [1.36.6] - 2026-08-07

### Fixed - every HTTP error had been reduced to "HTTP Error 400: Bad Request"

`HTTPError` **subclasses** `URLError`, and Python matches `except` clauses in
order. 1.36.2 added the `URLError` handler **above** the HTTP one, so every HTTP
response landed there and was re-raised bare. The handler below it became
unreachable, taking four things with it:

- the response body - PDC's own explanation of the 400 was read and discarded
- `401 -> TokenExpired`, so expiry stopped being recognised
- the Cloudflare detection added one release earlier, in 1.36.1
- **the bulk loader's safe-recreate guard**

That last one caused real damage. The guard reads PDC's error text to tell a bad
request body from a name conflict, and deletes only for a conflict. With no text
to read it concluded "conflict" and **deleted a working data source**, then
failed to recreate it.

Two fixes, because the ordering bug was only half of it:

- `except HTTPError` now precedes `except URLError`, with the reason recorded
  where someone might reorder them again. Tests cover the body, the 401 and the
  Cloudflare path - the error path had never been exercised, which is why a
  regression this broad passed 204 tests.
- **The recreate guard fails closed.** It deleted unless the error looked like a
  validation failure, so an error it could not parse was taken as proof of a
  conflict. Deleting now requires positive evidence that the name is the only
  problem; anything unreadable keeps the existing source.

### Fixed - profiling scoped itself from the first 500 entities of the whole estate

`source_entity_ids` posted `{"filters": {}}` and matched `resourceId` in Python.
It read the first 500 entities of the **entire catalog** and profiled whichever
of the source's entities happened to fall in that window. On a demo estate that
mostly worked; on a real one the source would rarely be in the first page at all,
so the job scoped to almost nothing and still reported SUCCESS.

`entities.filter_entities` already filtered server-side and followed the cursor
correctly - so this now calls it instead of keeping a second, worse copy.
`resourceIds` and `types` go to the server; the client-side check stays in case a
server ignores a filter it does not recognise. A scope that hits the 20,000-entity
ceiling is **reported on the row** rather than quietly clipped.

### Fixed - the README described the removed Jinja UI as a live fallback

The same stale claim as `run.sh` in 1.36.4, in a second place.

## [1.36.5] - 2026-08-07

### Changed - the bulk load now analyses by default, and says when it did not

A bulk load registered two object stores in PDC and left them with files but no
columns, statistics or sensitivity. Nothing had failed: **profile / discover**
ships unticked, so neither the file scan nor Data Discovery ever ran. Every
badge read OK and the only trace was a grey `SKIP`, which reads as "nothing to
do here" rather than "the step you wanted was omitted".

The commit that added the step is titled *"so the setup is one stop"* - and then
defaulted it off, stopping the setup short. The sibling database form
(`DB_DEFAULTS`) has always defaulted `profile: true`: the same word on the same
page, behaving in opposite ways.

- **Default flipped to on.** Ingest without analysis is the rarer intent.
- **Skips are stated in words.** A source that registered but was never analysed
  now raises a note saying what is missing and how to fill it in - counted only
  where the create succeeded, so a row that failed earlier still reports its own
  error rather than being blamed on profiling.
- The results header now reads **profile / discover**, matching the checkbox,
  and the card's description says what the step does and what is lost without it.

## [1.36.4] - 2026-08-07

### Fixed - run.sh promised a fallback UI that no longer exists

On a checkout without `frontend/dist`, the Linux launcher warned that it was
"serving the legacy UI until it is". The Jinja shell and `templates/` were
removed at **1.35.0**; `api.py` now answers `/` with a **503** and a build
instruction. So the message named a UI that is gone and implied the app would
still render something - sending an operator to debug a blank page instead of
running one build command.

The guard was also too narrow: it required `../frontend` to *exist* before
checking for the build, so a deployment missing the directory outright got no
warning at all. That is precisely the case most likely to reach a lab VM, where
the SPA arrives prebuilt or not at all. Now checked unconditionally, and the
command matches `api.py`'s own (`npm ci`, not `npm install`).

Found while scoping the Linux lab edition.

## [1.36.3] - 2026-08-07

### Fixed - the build manifests each claimed a different version

`frontend/package.json` said 1.24.0, `desktop/package.json` and
`desktop/src-tauri/Cargo.toml` said 0.1.0, while the app shipped 1.36.3. Nothing
reads these at runtime, so nothing ever contradicted them - which is precisely
why they drifted, and why the fix is a test rather than a resolution to be
careful. `test_docs.py` already held the drift guard for `tauri.conf.json`, the
changelog and both README stamps; it now covers the three build manifests too.

Harmless to the installed binary - `tauri.conf.json` names the bundle - but a
tree that gives four answers about its own version cannot be read with
confidence, and a reader has no way to tell which one is true.

### Added - the environment check reports the Cloudflare Access token

Including the trap that makes it look configured when it is not.

`$env:CF_ACCESS_CLIENT_ID = "..."` in a PowerShell session reaches **only that
session**. The app launches from the Start menu and inherits nothing from it, so
the variables are set, the operator can see them, and the app still gets
nothing. The check distinguishes the two and prints the fix:

    [WARN] Cloudflare Access token   set in THIS shell only - the app will not see it
      setx CF_ACCESS_CLIENT_ID "<id>.access"; setx CF_ACCESS_CLIENT_SECRET "<secret>"

Half a pair is reported too - both headers are required and one alone is a
misconfiguration rather than a partial credential. Presence only; the values are
never printed.

### Why one URL behaved two ways

Worth recording, because it took three wrong theories to get to it. `pentaho.io`
resolves differently per machine:

- the development machine has a **hosts entry** (`192.168.1.200 pentaho.io`), so
  it reaches the lab VM directly and never touches Cloudflare;
- a clean laptop resolves the **public record**, which goes through Cloudflare
  Access.

Same URL, same app, two entirely different network paths - and therefore two
unrelated failures (edge refusal on one machine, nothing at all on the other)
that both surfaced as "Keycloak auth failed". A service token is needed only on
the second path.

## [1.36.2] - 2026-08-07

### Fixed - network failures reported themselves as authentication failures

    Keycloak auth failed: <urlopen error [Errno 11001] getaddrinfo failed>

DNS. Nothing was sent, nothing authenticated, and the message pointed at
Keycloak. Only `HTTPError` was caught, so every `URLError` - name resolution,
refused connection, timeout - surfaced through a caller that assumed the failure
was about credentials.

Each now names itself, and says what it is NOT:

- **Cannot resolve** - "this is DNS, not authentication, so nothing was ever
  sent", plus the reason a lab vhost commonly fails on one machine and not
  another: it resolves only where the hosts-file entry exists.
- **Resolved but no answer** - "the name is right and the service is not
  listening, or a firewall is in the way. Credentials are not involved."

### Worth recording: the lab vhost only resolves where the hosts entry exists

The lab reaches PDC as `https://pentaho.io` through a hosts-file entry
(`192.168.1.200 pentaho.io`) on the development machine. The domain is the
author's own, so nothing is being sent anywhere unexpected - but the entry is
per-machine, and a workshop laptop without it resolves the PUBLIC record
instead of the lab VM. That is why the same URL reached the lab here and a
Cloudflare edge there.

For a laptop, either add the hosts entry or use a name that reaches the VM from
that network. A bare IP will not do: PDC routes by vhost and answers 401 on
every path.

### Tests

204.

## [1.36.1] - 2026-08-07

### Fixed - "Keycloak auth failed" when Keycloak never saw the request

    Keycloak auth failed: HTTP 403 ... error code: 1010
    /auth fallback failed: HTTP 403 ... error code: 1010

Cloudflare's **browser integrity check**. `urllib` sends `Python-urllib/3.x`
unless told otherwise, and that signature is refused at the edge - so the
request never reached PDC and no credential was ever tested. Both paths failing
identically was the tell.

Three changes:

- **The client identifies itself.** A descriptive `User-Agent`, which is what an
  HTTP client should send anyway, and which a WAF rule can match on to allow it.
- **Cloudflare refusals are named as such.** A `1xxx` code in the body means the
  edge refused it; the error now says so and stops claiming auth failed. It is
  deliberately NOT raised as `TokenExpired` even on a 403 - "auth failed" sends
  people to check realms and passwords that were never involved.
- **Cloudflare Access service tokens** via `CF_ACCESS_CLIENT_ID` /
  `CF_ACCESS_CLIENT_SECRET`. Authenticating a *browser* against Access sets a
  cookie on that browser session; this client has no cookie and cannot complete
  an interactive login, so it stays blocked however many codes are typed in. A
  service token is Cloudflare's documented answer for non-browser clients.

From the environment, never `settings.json` - that file is included in the State
snapshot the app can export, and these are credentials.

### Tests

204.

## [1.36.0] - 2026-08-06

### Added - CI, and a fresh-install smoke test

There was no CI. Two jobs now:

- **tests** on Linux - the suite, on every push.
- **fresh-install** on Windows - vendors the runtime, stages the app, greps the
  staged tree for anything scenario-specific, then **boots the shipped tree
  against an empty state directory** and asserts it serves the UI, resolves
  state to that directory, and finds no domain pack.

That second job is the one that matters. Every leak found today was visible from
a fresh install and invisible from a developer's checkout, and all of them were
found by a person installing the app on a laptop.

`test_fresh_install.py` does the same in-process, and **found three more on its
first run**:

- `seed_sample.py` had `--user pdc_user --password 'catalog123!'` as argparse
  **defaults** - a real lab account, in a module `api.py` imports, so it shipped.
  Anyone running the tool without arguments was quietly trying somebody else's
  login. Both are `required=True` now.
- `DEFAULT_DDL` was `/mnt/user-data/uploads/01-schema-and-data.sql`, the
  authoring machine's layout, meaningless on a customer install. Empty now.

The banned-string test reads its exclusion list **from `stage-app.ps1`** rather
than keeping a copy: a drifted copy would either fail on the developer's own
`connections.json`, which never ships, or - far worse - stop checking a file
that does.

### Added - code signing, off until a certificate is configured

`bundle.windows.signCommand` runs `scripts/sign.ps1` for every bundled binary.
With no `PDCG_SIGN_THUMBPRINT` set it prints a line and **exits 0**, so an
unsigned developer build still succeeds - a build that failed because a
colleague has no certificate would help nobody.

No certificate or `.pfx` is in the repo. A thumbprint names a certificate the
machine already trusts, carries no key material, and is safe in a CI variable
while the private key stays in the store or on the token behind it - which the
code-signing rules have required since June 2023.

Both the file digest and the **timestamp** digest are SHA-256. Leaving the
timestamp at signtool's SHA-1 default produces a signature that expires with the
certificate instead of outliving it.

### Tests

201.

## [1.35.0] - 2026-08-06

### Removed - the legacy Jinja UI

`templates/` and `static/js/00-12` (456 KB) are gone, with the Jinja shell, the
`/static` mount and the `jinja2` dependency. The React build superseded it at
1.11 and the fallback then went twenty releases without being exercised against
the current API - so on the one occasion it fired it would have rendered a
1.11-era page against a 1.34 backend. `/` now returns a 503 naming the cause
(`cd frontend && npm ci && npm run build`), which is the only way to reach it:
a checkout that was never built.

### Removed - the example domain packs no longer ship

`water_utility.example.json` was going into every installer. Having spent 1.29,
1.33 and 1.34 taking one industry's vocabulary out of the categories, the tag
dictionary and the CDE patterns, shipping that industry's pack as the sole
example put it straight back in the box - with a customer's name on part of it.
Packs are scenario material; `packinit` writes a fresh one from the company name
at install time.

### Removed - customer names from the environment files

`.env` named a customer and pointed at their pack; `.env.example` named another
and referenced a scenario zip. Both now say `Your Company` and
`/path/to/domain_pack.json`. `.env` is gitignored and never shipped, but a
checkout that behaves unlike a fresh install is exactly the gap that hid several
of today's bugs.

### Added - Try again

The failure panel restarts the backend in place, on a **new** free port - if the
last failure was the port, reusing it fails the same way. Everybody closes and
relaunches after a failed start; the app may as well do it, and a port clash or
a file briefly held by antivirus clears on the second attempt. It returns to the
live view rather than reloading, so the log already captured is kept.

### Added - Open data folder

Opens the state directory in Explorer. It is the answer to "where did my
glossary go?", and typing an `%APPDATA%` path by hand is nobody's idea of a good
time.

### Fixed - retry leaked its predecessor's timer

Each retry started a new interval without clearing the old one, so the elapsed
counter advanced two seconds per second and two independent deadline timers
raced to declare failure. Caught by retrying twice in the preview and watching
the clock.

## [1.34.1] - 2026-08-06

### Fixed - drinking-water regulation was deciding Critical Data Elements

`CDE_PATTERNS` carried `meter.?id`, `lead.?level`, `contaminant`, `ph.?level`
and `turbidity`. That regex marks columns as **Critical Data Element** - the
highest-care classification the app assigns - so one industry's regulator was
deciding CDEs in every estate.

This is the third place the water utility had reached into the engine, after the
category keywords (1.29) and the tag dictionary (1.33.0), and the furthest in:
categories are cosmetic next to a governance flag.

What stays is regulatory vocabulary that crosses industries - national
identifiers, tax ids, licences, balances, amounts due, compliance, violations. A
domain pack adds whatever a company's own regulator cares about. A test now
asserts `chlorine_residual_ppm`, `turbidity_ntu` and `meter_id` are not CDEs by
name alone, and that `account_number`, `ssn` and `amount_due` still are.

### Fixed - the last real host in the UI

`SettingsPage` named the lab in two places: the MinIO endpoint placeholder and
the "no port given" hint. Both now use `[PDC SERVER]`, matching the other three
forms.

### Audit

Everything remaining that names a scenario is a **comment or docstring** -
`cscu-postgres` in an example, `turbidity_ntu` explaining why a similarity rule
exists. Those record why the code is shaped as it is and were left alone;
deleting them would lose the reasoning and change no behaviour. The shipped
bundle contains no `192.168.`, no `pentaho.io`, no `pdc_user`, no
`/mnt/user-data`.

183 tests.

## [1.34.0] - 2026-08-06

### Fixed - the lab's IP address shipped in the UI

`MINIO_DEFAULTS.endpoint` was `192.168.1.200:9000` - not a placeholder, an
actual **pre-filled value**. A fresh install on a customer machine arrived
pointing at a host on a network they have never seen, so the first thing the app
did was fail to connect to somebody else's server. `DB_DEFAULTS` carried
`pdc_user` and port `5433` the same way, and the DDL path defaulted to
`/mnt/user-data/uploads/...`.

Defaults are **shape**, never somebody's address. Engine names, ports and
`schema: public` are safe to assume; hosts, accounts and buckets are not. All
three default sets are now empty where they named anything real.

### Changed - one convention for every connection field

Three forms had three: `https://192.168.1.200 (server root)` on Connect,
`https://pdc.example.com` on Apply, `https://host/keycloak` on Govern - and only
one of them said whose credentials to type.

    PDC base URL   https://[PDC SERVER]
    Keycloak       https://[PDC SERVER]/keycloak
    Username       PDC admin user / Keycloak admin user
    Password       PDC admin password / Keycloak admin password
    MinIO endpoint [PDC SERVER]:9000  (the S3 API port, not the console)

A bracketed marker cannot be mistaken for a working default the way
`https://pdc.example.com` and `admin` both can. And the Keycloak form now says
PDC fronts it **on its own host** at `/keycloak` - people otherwise reach for the
Keycloak container's address, and since PDC routes by vhost a bare IP answers
401 on every path, which reads as bad credentials.

Verified against the built bundle: no `192.168.`, no `pdc_user`, no
`/mnt/user-data` anywhere in it.

## [1.33.1] - 2026-08-06

### Fixed - the restructure broke the seed, and the standalone script with it

`[--] skipped` again, for a third and entirely new reason: `Resolve-AppPy`
probed for `packinit.py` in the app root, and 1.33.0 moved that module into
`engine/`. The resolver returned `$null`, `seed-company.ps1` threw "packinit.py
not found", and the step reported skipped - which also meant
`provisioning\seed-company.ps1`, the very command the skip message tells you to
run, was broken in the same way.

The resolver now probes **`api.py`**, the one file whose position is fixed:
`boot.py` imports it by name, so it cannot move without the app failing loudly
first. Anchoring on a module that might be regrouped is what caused this.

Neither the test suite nor the staging import check could catch it: both go
through Python imports, and this is a PowerShell path probe. Verified directly
against the restructured tree instead - `exit=0`, company and pack written.

## [1.33.0] - 2026-08-06

### Changed - the modules are grouped into packages

`glossary_generator/` was 18 flat modules. Now:

    core/     paths, audit
    engine/   suggester, similarity, tagdict, packgen, packinit, defqa, policy_draft
    ai/       llm, llm_providers, llm_detect
    sources/  dbconn, seed_sample, pdc_api
    cli/      cli_suggester, build_roster

`api.py` stays at the root - `boot.py` imports it by name - and `registry/` was
already a package. Filenames are unchanged: the source viewer, the docs and this
changelog all refer to them by name, and renaming as well as moving would have
invalidated every one of those at once.

Two things the move broke, both caught by the suite rather than by an installer:

- `paths.APP_DIR` was `dirname(__file__)`, so once `paths.py` lived in `core/`
  every asset resolved into `core/` - `VERSION`, `templates/`,
  `domain_pack.json`. Nothing raised; the app simply stopped finding its own
  files. It is anchored on the parent now, so it survives the module moving
  again.
- Two deferred `import pdc_api, io, csv` statements inside functions, which the
  import rewrite's line pattern did not match.

The "Under the hood" viewer now serves **relative paths** rather than bare
filenames, so it follows the layout instead of describing it separately, and a
test asserts every whitelisted entry resolves. `cli/*` is deliberately absent -
the installer does not ship it, so serving it would 404 on a real install.

### Changed - the generic tag dictionary is governance vocabulary, not an industry

It shipped `Meter Reading` as a governed term, `metering` / `usage` / `rate` /
`billing` / `revenue` / `asset` tags, and rules like
`usage|consumption|meter|reading` - the water-utility scenario leaking into the
engine, exactly as `"Billing & Rates"` did in `CAT_KEYWORDS` before 1.29. On a
fresh install a credit union was offered "Metering" as governed vocabulary that
nobody had chosen.

The line drawn: the generic layer keeps vocabulary about **data governance** -
regulatory categories, sensitivity, identifiers, structure - and gives up
vocabulary about a **business domain**. 26 tags to 20, 10 terms to 9, 11 rules
to 8. `pii`, `personal-data`, `maskable`, `cde`, `temporal` and `compliance` all
stay, and a test now fails if industry vocabulary returns.

`Service Address` became `Address`, keeping both spellings as aliases so a
utility pack still resolves to the canonical term.

### Tests

182.

## [1.32.18] - 2026-08-06

### Fixed - the seed was skipped on every install

The checklist said `[--] skipped - run provisioning\seed-company.ps1 to see why`
even with a company name entered. Two faults, found by reproducing the
installer's exact invocation:

**Empty arguments.** `powershell -File` reads `-Categories ""` as a *missing*
argument and exits before running anything:

    Missing an argument for parameter 'Categories'

The installer passed `-Categories` and `-PdcUrl` unconditionally, so the normal
case - the page now asks only for the company - failed every time. The argument
list is built conditionally now, omitting switches with no value.

**A second unguarded prompt.** The categories `Read-Host` was never given the
interactive check that the company prompt got in 1.32.7. It would have thrown
under `-NonInteractive` the moment the first fault was fixed. Both prompts now
go through one `Read-IfInteractive` helper, because guarding them separately is
precisely how this was missed twice.

Verified with the exact command the installer sends: `exit=0`, and the pack and
settings written - `Arizona Water` -> `arizona_water`, four categories.

## [1.32.17] - 2026-08-06

### Fixed - the swirl was flush against the header's edge

It was pasted at a fixed 71% of the width and is about 28% wide, so it ran to
99% while the wordmark opposite had a 6% margin. Visible on every installer and
uninstaller page.

The position is now derived from the mark's own width against the same margin
constant, so the two sides match whatever the scale factor becomes - a fixed x
would drift again the moment the swirl were resized.

## [1.32.16] - 2026-08-06

### Fixed - 1.32.15's splash did not run at all

It showed the logo, an empty version badge and "waiting for the backend...", and
nothing else - no checklist, no polling, no navigation. It read as a very slow
start; it was a **syntax error**. The splash script is one block, so an error
anywhere stops all of it.

The cause was `join('
')` written through an inline Python heredoc, which ate
the escape and left an unterminated string literal. That is the fourth time
today the same class of fault has shipped - ``, ``, `` in PowerShell
paths, and now `
` in JavaScript.

### Added - the splash is parsed and cross-checked by the test suite

Because reviewing harder has now failed four times:

- `node --check` on the extracted script. A syntax error here is invisible until
  the app is installed and launched, which is the most expensive place to find
  one.
- Every `invoke('...')` target is checked against the `#[tauri::command]`
  functions the shell actually defines. A renamed command fails **silently** -
  the promise rejects, the catch re-polls, the splash waits forever - which is
  the same shape as the CORS bug and just as unreadable from the screen.

179 tests.

## [1.32.15] - 2026-08-06

### Fixed - "Ollama has no model pulled" on a machine with fourteen

The hand-rolled HTTP client did not understand `Transfer-Encoding: chunked`,
which is how Ollama answers `/api/tags`. It handed the raw body - hex length
prefixes and all - to the JSON parser, which failed, so `first_model()` returned
`None` and **Suggest fixes** refused to run for want of a model.

That is the cost of the forty-line client, and it is still the right trade
against a TLS-carrying HTTP crate for one localhost endpoint - but chunked
encoding is not exotic and should have been handled from the start. It decodes
now, keeping a truncated body rather than discarding a nearly complete answer
when a read times out.

### Added - the failure panel says what KIND of failure it is

The last real failure was indistinguishable from success in the raw data: the
log was full of `GET /api/version 200 OK` while the window could not read a
single response. A panel that dumps JSON invites the wrong diagnosis.

It now leads with a classification drawn from evidence the shell already has:

- a traceback in the log -> "The backend stopped with an error"
- `address already in use` -> "The port was already taken"
- **200s in the log but never connected** -> "The server started, but the window
  could not reach it", and says explicitly that this is not a broken install
- no output at all -> "The backend produced no output at all"

## [1.32.14] - 2026-08-06

### Fixed - the splash never opened the app, against a server that was ready

"Connecting to the workspace" span for 81 seconds while the backend logged
`GET /api/version 200 OK` over and over. The server was fine the whole time.

The splash lives on a `tauri://` origin, so `fetch('http://127.0.0.1:PORT/...')`
is **cross-origin**. The request goes out - hence the 200s in the log - but the
webview will not hand the response to JavaScript, because FastAPI sends no
`Access-Control-Allow-Origin`. The promise rejected, the `catch` re-polled, and
the loop ran forever.

Readiness is now asked of the **shell**: `server_ready` performs the GET from
Rust, where no same-origin rule applies. The top-level navigation that follows
was never affected - navigating cross-origin is allowed, which is why the app
itself works once it gets there.

Worth noting the previous fixes were all real but none could have caught this:
the paths resolved, the process was alive, the port was open, the log was
streaming. Every signal said healthy because everything was.

### Fixed - a backslash eaten by an escape

The unseeded-install hint read `Run provisioningseed-company.ps1`. Same class of
fault as the `.ps1` control characters, in a JavaScript string this time.

## [1.32.13] - 2026-08-06

### Changed - the install log is a checklist and nothing else

Every step now prints the same two shapes: a line while it runs, one indented
result when it finishes. The results say what happened rather than that
something did, and the outcome markers line up - `[ok]`, `[--]` for skipped,
`[!!]` for a problem - so the eye can find the one line that matters.

    Installing application files (bundled Python and drivers)...
       [ok] application files
    Seeding Test Company...
       [ok] domain pack written
    Setting up Ollama (installs it, and downloads a model only if you have none)...
       [ok] local model available
    Checking this machine...
       [ok] no problems found

The version came off the first line - it is on the welcome page already - and
the Ollama line now says what it will actually do, since "pulling one model
(several GB)" was true only on a machine with none.

## [1.32.12] - 2026-08-06

### Fixed - an existing Ollama setup is now left alone

The install pulled a 19 GB model onto a machine that already had thirteen. The
check for "is this model present" worked; the missing judgement was that a
machine with ANY model is one somebody has already set up, and replacing their
choice with a better-fitting one is presumptuous - on a workshop laptop it is a
very long download nobody asked for.

It now reports the recommendation and stops:

    [ok] 13 model(s) already installed - leaving them alone
    this hardware would suit qwen2.5:32b; pull it with:  ollama pull qwen2.5:32b

`-Model` still forces a specific pull, so this is a default rather than a
refusal. A machine with no models at all still gets one.

### Fixed - the pull flooded the install log, in mojibake

`SetDetailsPrint none` did not suppress it: `nsExec::ExecToLog` writes to the
details list directly. So `ollama pull` emptied its progress bars into the log -
thousands of lines, and garbled, because those bars are UTF-8 block characters
and NSIS rendered them as CP-1252.

All three provisioning calls use `nsExec::Exec` now, which runs the same command
and captures nothing. The exit code still comes back, which is all the checklist
needs.

## [1.32.11] - 2026-08-06

### Changed - the install log stops listing every file

The details pane was printing one `Extract: ...` line per file - about 12,000 of
them - which buried the checklist it was meant to be. `SetDetailsPrint textonly`
around the extraction keeps the STATUS line at the top moving, so unpacking a
48 MB payload still looks alive, while nothing goes into the log below it. Not
`none`: freezing both would make a long extract look like a hang, which is the
problem this set out to avoid.

The whole install now reads as six lines.

### Changed - the installer asks for one thing, not three

Categories and the PDC server are off the Company details page. Neither earned
its place: the categories have a sensible starting set and grow from the first
scan anyway, and the server belongs on the app's Connections page, where it can
be changed without reinstalling. Three fields for one real question made the
page look like it wanted more than it did.

Both remain as `/Categories=` and `/PdcUrl=` for unattended installs -
`seed-company.ps1` still accepts them. The page simply stops asking.

## [1.32.10] - 2026-08-06

### Changed - the installer shows a checklist, not a transcript

`nsExec::ExecToLog` piped every line of every provisioning script into the
details pane - several hundred lines of PowerShell output for three steps. The
useful signal was in there somewhere, which is the same as not being there.

`SetDetailsPrint none` around each call silences the chatter without changing
what runs or what exit code comes back, so the pane now reads:

    Installing PDC Glossary Generator 1.32.10 - app, bundled Python and drivers
    Seeding Acme Energy...
      [ok] company seeded
    Ollama: installing if missing, then pulling one model (several GB)...
      [ok] local model ready
    Checking this machine...
      [ok] environment checks passed

A step that fails says which script to re-run, which prints the full output it
just suppressed. That is the right place for the detail: nobody reads three
hundred lines during an install, and the person who needs them wants them after.

## [1.32.9] - 2026-08-06

### Fixed - the environment check could not find the bundled Python

On a real installation it reported "Python 3.9+ not found" and called it a
blocking failure. The script carried its **own copy** of the "which interpreter"
rule, hardcoded to the checkout layout
(`desktop\src-tauriendor\python\python.exe`). In an installed tree the
runtime is at `$INSTDIR\python`, so it looked in a directory that does not
exist. The one script whose job is to say whether the install is sound was the
one that could not find it.

It now uses the shared `Resolve-PyExe` / `Resolve-AppPy` / `Resolve-StateDir`
from `lib/common.ps1`, which understand both layouts - the same resolvers
`seed-company.ps1` and `install-ollama.ps1` already used. That module was created
precisely so this rule would exist once; leaving one caller with a private copy
is what produced the failure.

Verified from a simulated install root: **"Everything checks out."**

### Added - the installer asks for the PDC server

Alongside the company name, and optional. It is written to `settings.json` as
`pdc_base`, so the app opens pointing at the right catalog and the environment
check has a server to probe instead of skipping it. Any server - there is still
no default anywhere. Credentials are never stored there; the app asks when it
connects.

## [1.32.8] - 2026-08-06

### Changed - developer tools no longer ship

`cli_suggester.py` and `build_roster.py` are out of the staged tree: nothing
imports them, and they are not part of what a customer installs.

`seed_sample.py` **stays**. It reads like a developer script and was on the first
list for removal, but `api.py` imports it - dropping it would have broken the
packaged app on a customer machine and nowhere else. Checked rather than assumed.

### Added - staging proves the tree can be imported

Which is what makes the above safe. The stage is now imported using the runtime
that will ship with it, and the build fails if it cannot. A file-existence check
could never catch a module excluded by mistake; this does, in about two seconds.

### Fixed - the import check was shipping bytecode

It compiled `__pycache__` into the tree `robocopy` had just finished excluding
it from, and those `.pyc` files shipped - stale caches for a Python version the
user may not be running. `-B` on the probe, and a sweep afterwards so anything
else that touches the stage cannot leave caches behind either.

Also dropped `diagrams/` from the stage - 1.4 MB of documentation artwork the
app never serves. It stays in the repo, where `docs/GUIDE.md` and
`REFERENCE.md` reference it. **97 files staged down to 60, 1.6 MB.**

### On "remove files that are not referenced"

Audited, and the honest answer is that **nothing here is unreferenced**:

| Looked at | Referenced by |
| --- | --- |
| `diagrams/` | `docs/GUIDE.md`, `REFERENCE.md`, `README.md` |
| `registry/selftest.py` | `glossary_generator/README.md` documents `python -m registry.selftest` |
| `cli_suggester.py`, `build_roster.py` | `docs/REFERENCE.md` |

So the cleanup is about what **ships**, not what exists - which is what the
staging excludes now do. One genuine open question remains, and it is a decision
rather than a tidy-up: the legacy Jinja UI (`templates/` + `static/js/00-12`,
~456 KB) is still live code - `api.py` falls back to it when `frontend/dist` is
absent - but the React build has superseded it since 1.11, so it has not been
exercised against the current API in a long time. Keeping it means maintaining a
second UI; removing it means a checkout with no built frontend serves nothing.

### Fixed - the installer would not compile

`${SectionIsSelected}` resolves its section id at COMPILE time, so the new seed
page could not sit above the `Section` that defines `SecSeed`. The `Page custom`
directive stays where it is - pages are emitted in declaration order - and the
functions moved below the sections, next to `ApplyComponentFlags`, which already
worked that way.

### Added - tests on the shell scripts

Every `.ps1` under `desktop/scripts` is checked for control characters and
non-ASCII. The same fault occurred three times in one day: a Windows path
written through an inline Python heredoc, where ``, `` and `` silently
become control bytes. Each time it parsed, committed, and failed only when run -
once mid-build, once inside an installer. 176 tests (was 163).

## [1.32.7] - 2026-08-06

### Fixed - the install-time seed failed with an unauthorized-access error

Reported as "no access to provisioning\seed-company.ps1", which is not what was
happening. In a normal (non-silent) install no `/Company=` is given, so the
script fell through to `Read-Host` - and `nsExec` runs it with **no interactive
console**. The prompt does not ask a question there; it fails, and the failure
surfaces as something that looks like a file-permission problem in Program
Files. The path and the ACLs were never involved.

Fixed at both ends, because either alone would leave the trap in place:

- **The installer now asks.** A page after the components page collects the
  company name and categories, shown only when the seed component is ticked and
  `/Company=` was not supplied. An empty name unticks the component rather than
  running the script to no purpose.
- **The script no longer prompts blind.** It checks for an interactive console
  first, and with none it explains what to run and exits **0** - the app installs
  perfectly well without a domain pack, so this was never a failure.

`powershell -NonInteractive` is now passed explicitly, so a future prompt fails
loudly at the point it is added rather than hanging an unattended install.

Verified with the installer's exact invocation: no `-Company` gives a clean skip
at exit 0, and `-Company "Acme Energy"` seeds `domain_pack.json` and
`settings.json` without a console.

## [1.32.6] - 2026-08-06

### Fixed - the default install path was not Program Files

`installMode` was `both`, which sounds more flexible than it is. Tauri's
template picks the default `$INSTDIR` with

    !if perMachine ... !else if currentUser ...

and there is **no `both` branch**, so `$INSTDIR` was simply never set and
MultiUser's own per-user default took over. The app landed somewhere nobody
expected, which is how it was spotted.

Now `perMachine`: `C:\Program Files\PDC Glossary Generator`, named outright by
the template rather than inferred. Two consequences, both deliberate:

- It always elevates, and a standard user cannot install it. For a tool an admin
  puts on a workshop machine that is the right trade.
- On a **shared** machine the seed runs as the installing admin and writes that
  account's `%APPDATA%`. A second user gets an unseeded state directory and needs
  `provisioning\seed-company.ps1` run once as themselves. Recorded in the README
  rather than worked around, because the alternative - state in the install
  directory - is what 1.25.0 removed.

## [1.32.5] - 2026-08-06

### Added - the build version, on screen from the first frame

A badge beside the title, sourced from the **shell** rather than the backend.
That distinction is the whole point: "which build is this?" is the first
question on any failure, and on a startup failure the backend is precisely what
is missing. It shows on the success path too, so a screenshot of a working app
is as identifiable as a screenshot of a broken one.

## [1.32.4] - 2026-08-06

### Fixed - the failure panel could not be scrolled

The startup view sets `overflow: hidden` deliberately, and the failure panel
inherits it. A real traceback is 40 lines, so the buttons ended up below the
fold with no way to reach them - the one thing on that screen that must always
be clickable. The body scrolls once the panel is shown, and only then.

### Added - ask the local model before emailing anyone

When Ollama is running with a model, a **Suggest fixes** button sends the
startup report to it and shows up to three concrete things to try. Hidden
entirely when no local model is available, rather than shown-and-disabled: a
dead button on an error screen is one more thing to wonder about.

**Local only.** The report carries file paths, the company name and a traceback;
sending that to a hosted provider to save a support email would be a poor trade,
and the licence already says a local model keeps everything on the machine. The
answer is labelled with the model that produced it and called a starting point,
not a diagnosis.

The Ollama client is hand-rolled over `TcpStream` - about forty lines. The only
endpoint this shell will ever call is `127.0.0.1:11434`: plain HTTP, no TLS, no
redirects, no auth. Pulling in a full HTTP client and its TLS stack for one JSON
POST would cost more in binary size and build time than the feature is worth.
Generation runs on a blocking thread with a 120-second read timeout, so a stalled
model cannot freeze the panel that is meant to be helping.

## [1.32.3] - 2026-08-06

### Fixed - the support panel could appear for an app that was merely slow

The failure panel has always been hidden unless startup failed, but "failed" was
decided by a single 90-second timer - which cannot tell a dead backend from a
slow one. A cold start on a slow disk (12,000 files, and the first import of
`oracledb`/`boto3`/`openai` is not quick) could cross it and put a support
address in front of someone whose app was about to work. That generates exactly
the enquiries the panel exists to prevent.

Split into three signals:

- **The backend exited** - `server_alive` reports it directly from
  `child.try_wait()`, and the panel appears at once. No amount of waiting
  revives an exited process, so making someone sit out a timeout is pure delay.
- **45 seconds** - an inline note saying it is taking longer than usual and the
  log below is live. Support is NOT offered. Polling continues.
- **4 minutes** - give up and offer support. Deliberately far out now that a
  genuine crash no longer has to wait for it.

Verified both paths against the real code: alive-but-slow leaves the panel
hidden and shows the notice; a dead backend surfaces it in under a second with
the deadline set to effectively never.

## [1.32.2] - 2026-08-06

### Added - the failure panel produces a support email

The point of that panel is not to be read, it is to be **sent**. Three actions:

- **Copy details** - the whole report to the clipboard.
- **Save report** - writes `startup-report.txt` to the state directory (writable
  by definition; the install directory is not) and reveals it in Explorer, so it
  can be attached rather than pasted.
- **Email support** - opens a pre-addressed mail to
  `james.oreilly@pentaho.com`, having copied the details first. `mailto` bodies
  are truncated by most clients well before a 40-line traceback fits, so the
  body carries the summary and the detail travels by clipboard.

The report is assembled by the **shell**, not the page: version, OS, executable
path, resolved paths, install identity and the full backend log. On a startup
failure the page itself may be half-working, and a report missing the version is
the one that generates a second round of emails.

### Fixed - clipboard copy could fail with no fallback

`navigator.clipboard.writeText` can **reject** as well as be absent - "Document
is not focused" is the common one, and it happens exactly when someone clicks a
button while focus is elsewhere. The legacy `execCommand` path was only reached
when the API was missing, so that case simply failed. Rejection now falls back
too, and if both refuse the message says so and points at Save report rather
than claiming success.

## [1.32.1] - 2026-08-06

### Added - the splash answers the first question a new install raises

A chip strip under the log: company, category count, whether Ollama is up, the
configured PDC, and the state directory. First launch after an install is
exactly when "did the seed actually work?" gets asked, and the answer otherwise
lives behind the `/config` endpoint.

An unseeded install says so outright - the engine ships no categories, so a scan
would return everything `Uncategorized`, and finding that out after the scan is
the wrong order.

`env_report` is a native Rust command: a file read and a 400ms TCP probe.
Shelling out to `check-environment.ps1` on every launch would add seconds to
startup for two answers that do not need a PowerShell process.
`check-environment.ps1` remains the thorough, operator-facing version.

### Changed - the swirl is a status indicator

It spins fastest while there is most left to do and settles as the checks
complete, rather than turning at a constant rate regardless.

### Fixed - "collecting..." could be the last word

The error panel calls `diagnostics`, and if the shell itself is wedged that call
never settles - so the panel whose entire job is explaining a failure became a
second, more confusing failure. It now gives up after five seconds and says the
shell is wedged rather than slow.

### Changed - uninstall no longer offers to delete your work by default

The "delete app data" box is now **unticked**, the opposite of Pentaho Content
Manager, where it starts ticked so a re-install restarts a course. Here that data
is the user's work: saved glossaries, the governed dictionary, connections, and
the domain pack grown from their own scans. None of it is recoverable from the
installer, and a glossary can represent days of steward review. Someone
uninstalling to fix a problem would have lost all of it to a checkbox they did
not read.

## [1.32.0] - 2026-08-06

### Fixed - the packaged app could not start at all

The first clean-laptop install failed with "The local server did not start",
while every path in the diagnostics reported `true`. The cause: Tauri's
`resource_dir()` canonicalises, so on Windows it returns an extended-length path
- `\?\C:\Program Files\...`. Those are legal for file APIs, which is why
`is_file()` passed on all of them, but they are **not** legal as a process
working directory: `SetCurrentDirectory` rejects the verbatim form, so
`boot.py`'s `os.chdir()` raised and the backend died before uvicorn bound a
port.

Stripped in the shell (`strip_verbatim`) and again in `boot.py` (`_plain`), for
drive paths only - a genuine UNC or an over-long path still needs the prefix.

### Fixed - a failure with nothing to show for itself

`stdout`/`stderr` were piped and never read. The traceback explaining the
failure sat in a pipe nobody drained, so a dead server looked exactly like a
slow one - and an undrained pipe would eventually have blocked a *working*
server mid-run. Both streams are now drained on their own threads into a
40-line ring buffer, exposed as `server_log`.

### Added - a startup screen that shows the work

Rebuilt around the Pentaho swirl (`make-swirl.py`, a vector path so it can be
drawn on and rotated - reusable as-is by Content Manager), with five checks that
advance off **real signals**: uvicorn's own `Started server process`,
`Waiting for application startup`, `Application startup complete`. Nothing
advances on a timer, because a checklist that ticks itself is a progress bar
wearing a disguise. Beneath it, the backend's live output.

A failure now turns the active check red and colours the traceback, instead of
sitting at 90 seconds and then blanking.

Two bugs found by driving the real code path with fake log lines:

- `pushLines` cleared its placeholder by re-calling itself with the cursor still
  at 0 - infinite recursion on the first line of output.
- The checklist ran **backwards**: uvicorn prints `Uvicorn running on ...` last,
  and that also matches the Python step's pattern, so a finished step got its
  spinner back. Progression is monotonic now.

Opened in a plain browser it says so, rather than freezing: `window.__TAURI__`
is absent there, so every call rejects and the old page just sat still.

The elapsed clock and the 90-second deadline run on their **own interval**, not
inside the poll chain. They started life as the first two lines of `poll()`,
which made both depend on that chain staying alive: one `invoke` that never
settles - a wedged backend is precisely when that happens - and the counter
freezes at whatever second it last reached while the timeout never fires, so the
screen sits there forever looking busy. Verified by stubbing `invoke` with a
promise that never resolves: the clock keeps counting, and the deadline still
trips through to the error panel.

### Added - installer feedback and a licence

The details pane is shown by default and the "Show details" button hidden - the
optional steps take minutes and a collapsed log made a working installer look
hung. Core install now narrates what it is doing.

`LICENSE.txt` is adapted from Pentaho Content Manager's for this product: the
course-content and exam-results sections replaced by what this app actually
does - connecting to your sources, what profiling reads, and the one route by
which data leaves the machine (a hosted AI provider, off by default). It records
that classification is deterministic rather than AI-driven, which is a
regulatory position worth stating in writing.

## [1.31.2] - 2026-08-06

### Changed - Pentaho branding, shared with Content Manager

Same swirl, same wordmark, same `#CC0000`: `src-tauri/icons/brand/` and
`scripts/make-icons.py` are copied from Pentaho Content Manager so the two
installers look like they came from the same place. The masks are the classic
Pentaho logo with the Hitachi tagline stripped.

The **art is regenerated, not copied**. `make-icons.py` already took a
`--title`, so the sidebar names this product; a new `--strapline` replaces PCM's
"Workshop lab guide", which would have been wrong on a glossary tool. Wired into
`bundle.windows.nsis` as `installerIcon`, `headerImage` and `sidebarImage`,
replacing the generated placeholder icons.

### Fixed - the sidebar strapline was clipped

It rendered through a fixed-size font while the title above it used `fit_font`,
so anything longer than the 164px sidebar was silently cut mid-word - "Business
glossary for Pentaho Data Catalog" came out as "ess glossary for Pentaho Data
Ca". The strapline is fitted too now, so the next person to change that text
cannot reintroduce it.

## [1.31.1] - 2026-08-06

### Fixed - a BOM silently threw away everything the installer collected

`Set-Content -Encoding UTF8` writes a byte-order mark in PowerShell 5.1. The app
reads its state with `encoding="utf-8"` (not `utf-8-sig`) inside a `try/except`
that returns the **default** on failure - so the BOM did not raise. It made
`_read_json` fall back, silently, while everything reported success.

Two files were affected, and both are exactly the files an install writes:

- `settings.json` from `seed-company.ps1` - the company name the installer asked
  for would have been discarded, and the app would have shown "your
  organization".
- `people.json` from `load-pdc-users.ps1 -ExportPeople` - the roster would have
  come back EMPTY, after a successful-looking export.

Both now write with `UTF8Encoding($false)`. Verified from a simulated install
root: first bytes `7B 0D 0A`, and Python reads the company back.

Found by rehearsing the **installed** layout (`$INSTDIR\python`,
`$INSTDIRpp`, `$INSTDIR\provisioning`) rather than the checkout - the same
rehearsal confirmed `Resolve-PyExe`, `Resolve-AppPy` and `Resolve-StateDir` all
resolve correctly there, with state landing in
`%APPDATA%\com.pentaho.pdc-glossary`.

## [1.31.0] - 2026-08-06

### Added - a components page, and the seed runs at install

`desktop/src-tauri/nsis/installer.nsi` extends Tauri's default template with
Full / Minimal / Custom, modelled on the Pentaho Content Manager installer:

| Install type | What runs |
| --- | --- |
| Full | app, company seed, Ollama, environment check |
| Minimal (app only) | app only |

The bundled Python appears as a ticked, greyed-out entry with no payload of its
own. It is laid down by the core section either way; the page is where someone
decides what this needs, and "you do not have to install Python" is the most
useful thing it can say there.

Every optional step delegates to a script in `$INSTDIR\provisioning\`, all
re-runnable afterwards and safe no-ops when their work is already done. None of
them can fail the installation - a skipped step leaves a working app, which is
the same principle the environment check follows.

Silent switches: `/NoSeed`, `/NoOllama`, `/NoCheck`, plus `/Company=` and
`/Categories=` to drive the seed unattended. **Without `/Company=` a silent
install skips the seed rather than prompting** - a prompt in an unattended job
hangs it forever.

### Added - `install-ollama.ps1`, one model, sized to the machine

Installs Ollama via winget if missing, starts it, waits for the port, then pulls
**one** model - the one `llm_detect.recommend()` sizes to this hardware. Not a
set: each is several GB and pulling a spread "just in case" turns a workshop
setup into a long download of things nobody will run. Skips the download when
that model is already present, so the installer log stays honest about what it
actually did.

### Changed - the shared resolvers handle both layouts

`lib/common.ps1` is bundled into `provisioning/`, where the directory layout is
`$INSTDIR\python` and `$INSTDIRpp` rather than the checkout's
`desktop\src-tauriendor\...`. `Resolve-PyExe` and `Resolve-AppPy` now probe
candidates covering both, so one copy of each rule serves the installed and
development trees.

### Changed - the vendored runtime is replaced on upgrade, not overlaid

NSIS file extraction only adds and overwrites. A dependency dropped between
releases would linger in `$INSTDIR\python` and stay importable, making "what
shipped" and "what is installed" quietly different. That tree is now removed
before the new one lands.

### Known gap

The installer is **unsigned**, so SmartScreen shows "Windows protected your PC"
on a clean machine. Every attendee hits it until the binary is code-signed -
the one thing standing between this and a hands-off rollout.

## [1.30.0] - 2026-08-06

### Added - `seed-company.ps1`, the first-run step 1.29 made necessary

Removing the builtin categories means a fresh install classifies nothing until a
pack tells it how. This asks for the two things only the customer can answer -
company name and glossary categories - scaffolds a thin pack with `packinit`,
and writes it to the **state directory** together with the company name in
`settings.json`. `-Company`/`-Categories` make it non-interactive; `npm run seed`
is the shortcut.

Refuses to overwrite an existing pack without `-Force` (and backs it up), because
by then it has usually been grown from a scan and is worth far more than a
skeleton.

The 1.29 removal shows up here immediately: seeding `Customer,...,Usage,...` now
produces keywords for **all six** categories. The old builtin-collision check
dropped `Customer` and `Usage` as "would never fire", so the two commonest
categories came out unmatched.

### Added - `load-pdc-users.ps1 -ExportPeople` (PDC-Scenarios)

Builds `people.json` from the Keycloak realm over **HTTPS** - the Admin REST API,
so no SSH and no container access. It prompts for the admin password because
that API is bearer-token only.

The account **UUID** is the point: names, emails and roles can be typed by hand,
the UUID cannot, and without it a glossary term cannot be bound to a real steward
(the app keeps such a person visible but will not offer them as a binding).
Disabled accounts are skipped and `default-roles-*` filtered - listing Keycloak
plumbing makes every steward look identically privileged.

Persona detail Keycloak knows nothing about (`stakeholder_role`, `community`,
`owns`, `expertise`) is merged forward by email, so refreshing does not discard
curation. `make users-people` prints the command.

### Added - `desktop/scripts/lib/common.ps1`

`check-environment.ps1` and `seed-company.ps1` both need "where does state live"
and "which Python do I run". Two copies is two chances to disagree with
`paths.py`, and a check that probes a different directory from the one the app
writes to is worse than no check.

Its `Resolve-AppPy` prefers the **checkout** over `vendorpp`: the staged tree
is a build artifact that goes stale, and preferring it once ran a pre-1.29
`packinit` that warned about builtin keywords which no longer exist. In a
packaged install the checkout path is simply absent, so the staged tree still
wins there.

### Fixed

`packinit` writes its "no keyword for X" notes to stderr, and under
`$ErrorActionPreference = "Stop"` PowerShell 5.1 turns any stderr line from a
native command into a terminating `NativeCommandError` - so a successful seed
with useful notes looked like a crash. The call now judges by exit code.

## [1.29.0] - 2026-08-06

### Removed - the engine no longer ships a category taxonomy

`suggester.CAT_KEYWORDS` carried 14 builtin keywords: `("billing", "Billing &
Rates")`, `("usage", "Usage")`, `("document", "Records & Documents")` and the
rest. That was the **water-utility scenario leaked into the engine** - a credit
union scanning `invoice_total` got a category named "Billing & Rates" that
nobody had chosen, and it read as a considered default rather than a leak.

Renaming them to neutral words was the first attempt and was the wrong fix: it
kept the same flaw, the engine asserting a taxonomy the customer never agreed
to. They are gone. Categories come from the domain pack, which is grown from the
company's own scan - the same rule that removed `_CANONICAL_SEEDS` in 1.11.x.

With no pack, `categorize()` returns `Uncategorized` and `categorize_column()`
returns `None`. That is honest and reviewable: the steward assigns categories
during review, and **Export domain pack** turns those decisions into the pack,
so the second scan is categorised from the company's own evidence.

`category_definitions` went the same way - writing a definition here would put
words in the steward's mouth about a category the engine did not choose. The
templated fallback reads as unfinished, which it is.

### The one exception, and it is now overridable

The engine creates document rows itself (`document_rows`), so it must name a
category for them. That is a **content-type** label for unstructured content,
not a domain taxonomy. `tagdict.document_category()` returns the pack's
`document_category` if set, else `Records & Documents`, and it is read through a
function so a pack installed later still wins.

### Fixed - the document harvest lost its governed tag

Caught while checking exactly this: removing the category->tag seeds meant
`suggest_tags` fell back to the slug `records-documents`, which is not in the
vocabulary, instead of the governed `document` tag. The single seed the engine
still needs is back, keyed on `document_category()`.

### Fixed - first-match ordering in the water pack

The 14 keywords moved into `water_utility.example.json` so the scenario keeps
its categories. They must sit FIRST: `cat_keywords` is first-match, and the
pack's existing `("email", "Records & Documents")` rule otherwise claimed a
database column called `customer_email`. Verified: `customer_email -> Customer`,
`invoice_total -> Billing & Rates`, `turbidity_ntu -> Water Quality`,
`conservation_letter -> Records & Documents`.

### Changed

`packinit.py` no longer keeps a hand-copied list of the engine's builtin
keywords - there are none to collide with. The scaffolder keeps a *suggested*
category list for `--categories`, which is its job: its output is a skeleton the
steward edits, unlike the engine, which must not assert anything at scan time.

Company name in the docstring and test fixture is now a fictional one.

### Tests

163.

## [1.28.0] - 2026-08-06

### Changed - no hardcoded PDC server, and no hardcoded model

Both defaults were wrong for anyone who is not on this laptop.

**PDC**: the check no longer falls back to `https://pentaho.io`. It now resolves
`-PdcUrl` -> `$env:PDC_BASE_URL` -> **the app's own saved connection**
(`settings.json` `pdc_base`, written by the Connections page) -> `.env` ->
**a prompt** -> and if none of those answer, it SKIPs the PDC checks rather than
guessing. Guessing a host either probes a stranger's server or reports a healthy
machine as broken because someone else's is down. `-NoPrompt` for unattended
runs; `-Json` implies it. Reading the app's saved connection is the point: the
server you last worked against is the one worth checking.

**Ollama model**: `check-environment.ps1` no longer names `llama3.2:3b`. It calls
the app's own `llm_detect.recommend()`, which sizes the model to the hardware -
VRAM first, aggregating multi-GPU, then RAM, then a CPU floor - and reports what
it found. Naming a model here would have been a second rule quietly disagreeing
with the app's Settings page; recommending a 32B model to a laptop and a 1B model
to a 2x3060 rig are both real costs. Verified on the dev rig: `2x RTX 3060,
24.0 GB VRAM -> qwen2.5:32b`. Where the detector cannot run, the fix text points
at the Settings page instead of inventing a name.

### Fixed - the domain pack could not be written in a packaged install

`domain_pack_path()` returned an ASSET path (beside the code), but the pack is
two things at once: a starter that ships with the install, and a file the app
REWRITES via *Draft pack -> apply*. Under a packaged install that path is in
Program Files, so the write fails and the endpoint reports success on a file it
never replaced.

Split in two: `domain_pack_path()` reads `$GLOSSARY_DOMAIN_PACK` -> the **state
directory** -> the shipped starter; `domain_pack_write_path()` never returns the
install directory. A pack the user drops into the state directory now wins over
the shipped one, which is what makes "supply your own pack" work at all.

### Fixed

PowerShell strips embedded double quotes when passing arguments to a native
executable, so the detector probe's `json.dumps({"model": ...})` arrived as bare
names and died with `NameError`. Single quotes inside the Python.

### Tests

160.

## [1.27.0] - 2026-08-06

### Added - `check-environment.ps1`

A post-install check for whoever is preparing a workshop machine, in the shape
Pentaho Content Manager already uses: one `[STATE] name  detail` line per check,
with a fix command attached, plus `-Json` for provisioning logs.

**It reports rather than blocks.** Only WebView2 and a usable Python are `FAIL`,
because without them the window does not open. Ollama absent is a `WARN` - the
app also drives Anthropic, OpenAI/Azure and Gemini - and PDC unreachable is a
`WARN`, because the vhost is normally configured after install and scan, review
and govern all work without it. Treating optional things as hard failures teaches
people to ignore the output, which costs more than the check is worth.

Checks: WebView2, the vendored runtime *and whether it can import its own
packages*, the state directory (probed by writing, matching `paths.py`), free
disk, Ollama, hosted-provider keys (presence only - never printed), the PDC URL
shape and PDC reachability.

Three cases it is deliberately careful about:

- **Ollama up with no model pulled.** The app connects and then every generate
  call fails, which reads as "the AI is broken" rather than "nothing is
  installed". Reported distinctly, with `ollama pull llama3.2:3b`.
- **A bare IP for PDC**, flagged before the probe even runs: PDC routes by vhost
  and answers `401` on *every* path, which looks like bad credentials and sends
  people to reset passwords that were never wrong. Confirmed against the live
  instance while testing - `https://192.168.1.200` returns exactly that 401.
- **A self-signed certificate is not unreachability.** The first version
  reported the lab's cert as "PDC unreachable", which would send someone to
  check DNS and firewalls for a server answering HTTP 200. It now retries with
  validation off purely to tell the two apart, and names the certificate.

### Fixed

`tauri.conf.json` is version-stamped in step with `VERSION`; the first installer
built out as `1.25.0` because the bump landed after the build began.

## [1.26.0] - 2026-08-06

### Added - `desktop/`, a Windows installer for the app

A Tauri shell that starts the existing FastAPI server on a free port and points
a webview at it. The app is unchanged and there is still one UI, served the same
way in both builds, so the desktop and browser versions cannot drift apart.

`npm run tauri:build` produces an NSIS `.exe` in
`desktop/src-tauri/target/release/bundle/nsis/`.

**A vendored Python, not PyInstaller.** `fetch-python.ps1` stages the official
Windows embeddable package plus the requirements (~164 MB). The dependency set
is `oracledb`, `psycopg2-binary`, `pymssql`, `boto3` and three provider SDKs -
dynamic-import-heavy code that PyInstaller's static analysis gets wrong, and
gets wrong at *runtime*, on the attendee's machine. A vendored tree is just
files: what was tested is what ships. The stamp covers the requirements hash as
well as the Python version, so adding a dependency forces a rebuild.

**A free port, chosen at launch**, because 5000 is popular and a second instance
must not read as "the app won't start".

**A kill-on-close job object.** Closing the window stops the server directly,
but a crash or a Task Manager kill would leak `uvicorn` - still holding the port
and the state files, so the *next* launch fails for a reason the user cannot
see.

**A splash that can fail out loud.** It polls `/api/version` (not `/`, which is
the SPA shell and answers before the app is ready) and, after 90 seconds, shows
what the shell actually resolved: app dir, boot script, state dir, whether the
vendored runtime is present. A blank window is the worst failure mode on a
workshop machine.

### Three things the packaging exposed

- **The embeddable runtime's `._pth` replaces `sys.path` outright** and drops the
  working directory, and `PYTHONPATH` is ignored while a `._pth` is present - so
  `python -m uvicorn api:app` can never import the app, whatever directory it
  runs in. `boot.py` sets the path explicitly and gives packaged and dev
  launches one code path.
- **`pdc_client` lives at the repo root** and is pip-installed into the dev venv,
  so nothing under `glossary_generator/` points at it. It is now staged
  explicitly, with an assertion that would have caught the omission before an
  installer shipped.
- **`robocopy` returns 1 for "files were copied"**, and PowerShell surfaces the
  last native exit code as the script's - so a successful staging run would have
  looked like a failure to npm and aborted the build.

### Security

`stage-app.ps1` excludes `.env`, `glossaries.json`, `connections.json`,
`settings.json`, `people.json`, `audit_log.json` and the rest, then re-scans the
staged tree and fails the build if any of them slipped through. A developer's
`connections.json` would carry lab hostnames into a customer install; `.env`
would carry provider API keys.

### Tests

158. The new one pins `tauri.conf.json`'s version to `VERSION` - it names the
installer, so drift there ships a file that misstates what is inside it.

### Not done

Placeholder icons; no Full/Minimal/Custom components page; no post-install
environment check for Ollama and PDC reachability.

## [1.25.0] - 2026-08-06

### Added - state has a home of its own (`paths.py`)

Groundwork for a packaged Windows install. Every persisted file used to default
to a path beside `api.py`, which is right for a checkout and for the lab VM, and
fatal under `C:\Program Files`: the directory is read-only, so the first save
fails and the app looks broken rather than mis-installed.

`paths.py` is now the single place that decides, in order:

1. `$GLOSSARY_STATE_DIR` - explicit wins. The installer's launcher will set this,
   so the packaged app never infers anything.
2. The app directory, when it is writable. **Existing installs do not move** -
   checkouts, `run.ps1`/`run.sh` and the training VM behave exactly as before.
3. `%APPDATA%\PDC-Glossary` (or `$XDG_DATA_HOME`/`~/Library/Application Support`)
   when the app directory is read-only, i.e. a packaged install.

Writability is **probed** by creating a file, not asked via `os.access(W_OK)` -
on Windows that reports the read-only attribute and ignores ACLs, so it returns
true for a Program Files directory that then refuses the write.

Per-file overrides (`$GLOSSARY_GLOSSARIES` and friends) still win over all of
it, unchanged.

### Fixed - the State snapshot ignored the registry override it documented

`snapshot_files()` and the restore path both built `os.path.join(HERE,
"registries")` directly while `_registry_path()` used `$GLOSSARY_REGISTRY_DIR`.
The docstring claimed "paths honor the same env overrides the app itself uses",
which was untrue for exactly this one: with the override set, a snapshot
exported the wrong directory and a restore wrote into the install tree. Both now
go through `REGISTRY_DIR`.

### Changed - one rule for where the domain pack comes from

`os.environ.get("GLOSSARY_DOMAIN_PACK") or <dir>/domain_pack.json` had been
written out independently in `api.py` (three times), `tagdict.py` and
`suggester.py`. A missing pack makes the engine fall back to generic defaults
silently, so a copy that resolved differently would surface as a bland glossary
rather than an error. Now `paths.domain_pack_path()`.

### Changed - `/config` reports where state lives

Adds `state_dir` and `state_dir_source`, and lists `registries` and
`domain_pack` alongside the existing paths - "where did my glossary go?" should
not require a filesystem hunt once the state stops sitting next to the app.

### Tests

157 (was 144). `test_paths.py` pins the decision order, the probe, and that
assets never resolve into the state dir. `conftest.py` also sets
`GLOSSARY_STATE_DIR` to the temp dir, so a state file added later without its
own env var cannot quietly start polluting the checkout.

## [1.24.0] — 2026-08-05

### Fixed — overlapping values are not one concept unless they are a code list
- The companion to 1.23.0, one rule up. Value-set overlap was read as identity
  for **any** profiled values, so **`Paid Bills ← Outstanding Bills`** scored
  *"profiled value sets overlap (100%)"* at `0.85 · strong` — opposite states of
  a bill, whose counts both draw from `{0, 1}`.
- Overlap identifies a concept for a **coded vocabulary** — two columns drawing
  from `{OPEN, CLOSED, PENDING}` really are the same domain — and says nothing
  for numbers, where a shared range just means both hold small integers.
- `_is_coded_vocabulary()` gates it: a set qualifies only when at least one value
  is non-numeric, and only with two or more values (a single shared code is thin).
  Numeric overlap now returns **no verdict** with *"a shared range is not a shared
  concept, so compare the definitions"*, and disjoint numeric sets fall through to
  the format checks rather than claiming *different*.
- Verified on the AWC glossary (157 terms): pairs in the **strong** band went from
  many to **zero**. Lead/copper/turbidity and the bills pairs left the list
  entirely; the Tier rate pairs remain on genuine name similarity, honestly
  labelled *(no evidence claim)*.

### Fixed
- A test docstring containing `^0\.\d{2}$` in a non-raw string raised a
  `SyntaxWarning: invalid escape sequence` — harmless today, an error in a future
  Python. The suite is warning-free again.

## [1.23.0] — 2026-08-05

### Fixed — an identical value format is not an identical concept
- `compare_evidence` treated **any** matching induced regex as proof of one
  concept. On a real glossary that ranked **`Lead Ppb ← Turbidity Ntu`** and
  **`Copper Ppm ← Turbidity Ntu`** at `0.85 · strong`, because all three match
  `^0\.\d{2}$` — which means nothing more than *"a small decimal"*. Same for
  `Tier1 Rate ← Tier2 Rate` on `^\d\.\d{4}$`: deliberately different rates that
  share a numeric shape.
- Merging those would have been a serious glossary error — putting one regulated
  contaminant's limits on another's term.
- The giveaway was the ranking: in that same run the one **genuinely correct**
  merge, `Chlorine Residual ← Chlorine Residual Ppm`, scored **0.84 · review** —
  *below* the wrong ones — because name identity was outranked by format identity.
- Format identity now counts only when the format is **distinctive**: something a
  system minted on purpose (`^AWC-[A-Z]{2}-\d{6}$`, `^CSCU-\d{6}$`) rather than a
  bare number. A generic shape returns **no verdict** with *"that shape is too
  generic to identify a concept — compare the definitions"*, so the pair falls
  through to name/token scoring and the steward decides.
- The bias is deliberate: a letter **class** (`^[A-Z]{2}\d{4}$`) is a shape, not a
  minted marker, so it is treated as generic. A false negative asks a question; a
  false positive merges unrelated concepts.

## [1.22.0] — 2026-08-05

### Fixed — one file, one category: a mixed document filed its columns wrongly
- `categorize()` takes the **table** name, which for a document store is the
  **file** name. That is fine for a database (the table *is* the subject) and
  wrong for a file: one SCADA snapshot carries `turbidity_ntu` and
  `chlorine_residual_ppm` (water quality) beside `pump_status` and
  `reservoir_level_percent` (water system). Whatever single keyword the file
  matched filed the lot under it.
- The visible symptom was a duplicate that could never merge: a harvested
  **Turbidity Ntu** landed in *Water System* while the database's own sat in
  *Water Quality*, and rows key on **Category + Term**, so they appended instead.
- `categorize_column()` now lets a column's own name decide, and `suggest()`
  applies it **for document-derived rows only** — in a database, letting a column
  override would file `customer_id` in `water_systems` under Customer. A column
  with no opinion falls back to the file's category, so operational measures keep
  it. The row's category also now drives its governed tags and purpose text,
  which previously followed the file.
- The water_utility pack gained the measures that decide their own category:
  `turbidity`, `chlorine`, `coliform`, `ph_level`, `lead_ppb`, `contaminant`
  → **Water Quality**.
- Verified on a simulated harvest of one file: turbidity and chlorine residual to
  Water Quality, pump status and reservoir level to Water System, the table term
  to Water System — three categories from one file.

## [1.21.0] — 2026-08-05

### Fixed — the document prune rule was eating the payload
- 1.19.0 pruned **every** dotted path on the reasoning that the concept lives at
  the leaf. On a real SCADA harvest that pruned 28 of 54 rows — including
  `systems.chlorine_residual_ppm` and `systems.turbidity_ntu`, which are
  **regulated drinking-water measures**: exactly what a utility's glossary exists
  to govern. Nesting is a fact about the file format, not evidence that a value
  is uninteresting.
- The line that actually matters is **envelope vs payload**. The envelope
  describes the *file* (units declarations, export date, source, snapshot type,
  interval, sensor/record ids, timestamps); the payload is the *data in it*. The
  rules now name the envelope explicitly — including bookkeeping fields wherever
  they sit — and keep everything else. Same harvest: **37 kept, 10 pruned**.

### Changed — a flattened path takes its leaf as the term name
- `systems.chlorine_residual_ppm` is the term **Chlorine Residual Ppm**, sitting
  under a JSON container that means nothing to a steward. `document_leaf_name()`
  takes the leaf, so the term reads as a business concept — and the same concept
  arriving from a database column now merges with it instead of sitting alongside
  as a near-duplicate.
- A useful second-order effect: `export_metadata.units.flow` becomes **Flow** and
  prunes as bookkeeping, while `readings.flow_gpm` becomes **Flow Gpm** and is
  kept. The unit declaration and the measure stop colliding.

### Fixed — the PDC token died on every page change
- Connect's sign-in was plain `useState`, so navigating away unmounted the card
  and threw the token out — a page change meant signing in again (four times in
  one debugging session). It now uses the session UI cache: an in-memory Map for
  the tab's lifetime, never written to disk, which is what *"never persisted"*
  already promised.
- The **password** deliberately stays in component state and dies with the form —
  it is needed once to mint the token and should not outlive that.

## [1.20.0] — 2026-08-05

### Added — `packinit`, a scaffolder for a new company's domain pack
- A pack is read by **three** engines from one file — `suggester` (categories,
  naming), `tagdict` (governed tags, seed terms), the Registry (references) — so
  writing one from scratch means getting a shape you cannot guess. The practical
  result is that a new scenario starts with **no pack**, and the model ends up
  carrying classification that deterministic rules should be doing.
- `python packinit.py --domain <slug> --company "<name>" --categories "A,B,C"`
  writes the skeleton. It is deliberately **thin**: it seeds only what a category
  list can justify — one `cat_keyword` per category (the distinctive last word),
  slugified `category_tags`, pre-approved `extra_tags`, placeholder
  `category_definitions`.
- `table_category`, `table_terms`, `tag_rules` and `terms` are left **empty on
  purpose**. Inventing table names for an estate nobody has scanned produces
  rules that never match and read as though they were curated; those keys are
  filled from evidence by *Export domain pack* (`packgen.build_pack`).
- It refuses to emit a rule that **cannot fire** — a keyword already claimed by a
  builtin (`customer`, `usage`, `document`…) or by an earlier category — and says
  why, rather than leaving dead weight that reads as configured behaviour. A
  category whose every word is too generic to route on (*Records & Documents*) is
  reported too, instead of being silently dropped.
- Never overwrites an existing pack without `--force`: a pack is hand-curated and
  slow to rebuild.

### Changed — the water_utility pack learned the document estate
- Added `asset`, `pipe`, `network`, `pressure`, `scada` → **Water System**;
  `inspection` → **Water Quality**; `email`, `letter` → **Records & Documents**.
  Every document file in the AWC estate now categorises deterministically —
  previously only `epa_compliance_*.pdf` and `all_systems_*.json` did.
- `correspondence` would have been the intuitive keyword and would **never have
  fired**: `categorize()` matches the *file* name, and those files are
  `email_*` / `letter_*`. The folder name never reaches it.
- Removed six rules that could never fire: `account`, `customer`, `customers`
  (claimed by builtins first) and the duplicate `system`, `system`, `water`
  (claimed by an earlier pack rule). `cat_keywords` is **first-match**, so these
  were dead weight. Verified no database table changed category.

## [1.19.0] — 2026-08-05

### Added — auto-prune rules for columns harvested from documents
- PDC's Data Discovery flattens a nested file into dotted paths, so a JSON like
  `{"export_metadata":{"units":{"flow":"gpm"}},"readings":[{"pump_status":…}]}`
  harvests as candidate terms named `export_metadata.units.flow` and
  `readings.pump_status`. Those are file **structure**, not business concepts —
  a unit-of-measure declaration in a header is not a glossary term, and every
  JSON in a document store emits a fresh batch of them.
- `document_path_prune()` gives them the same treatment a surrogate key already
  gets: **pruned by default with the reason on the row, restorable by ticking
  Keep**. Three rules, first match wins, most specific first — document envelope
  (`export_metadata.*`, `meta.*`), control fields (`_x`, `$schema`, `@ts`), then
  any remaining nested path, whose reason says the concept is the leaf.
- The rules cannot fire on a database column, which has no path separator.

## [1.18.0] — 2026-08-05

### Added — Data Quality derived from PDC's own profiling
- `quality_from_pdc_stats()` scores a column from **PDC's** measurements rather
  than the app's sampling: `density → completeness`, `uniqueness → uniqueness`
  (counted only where uniqueness is expected, so a low-cardinality enum is not
  punished for repeating). Validity is not exposed in PDC's stats, so it is left
  unmeasured and `quality_score_column` renormalises over what remains.
- **Why it matters.** The app can only score what it can read. A PDF or DOCX has
  no rows to sample and never gets an app-side score; a large file is only partly
  read. PDC profiles server-side, so where it has measured something its numbers
  are better evidence — and for those formats, the only evidence there will be.
- `POST /api/pdc-profiling` now returns `derived_quality` per column plus a
  count, and the app-vs-PDC compare shows **PDC DQ** per row and says how many
  columns a score could be derived for.
- It returns **None** where PDC profiled nothing usable — never a manufactured 0
  or 100, the same rule `quality_score_column` already followed. An unprofiled
  column with an invented score is worse than an honest blank.

### Fixed — *Add to glossary* kept the quality evidence and dropped the score
- `foldSources` merged `Source_Quality_Dims` on a colliding row but never merged
  `Suggested_Quality`, so re-scanning an object store with content profiling on
  reported *"5 existing term(s) gained this source's columns & evidence"* and
  left every Data Quality blank. The measurements arrived; the number derived
  from them did not, and Apply had nothing to write — which is why documents
  showed `qualityScore —` in PDC however often the scan was re-run.
- Highest wins, matching `Suggested_Rating` beside it, and only when non-zero: an
  unprofilable row must stay *without* a score rather than acquire a 0, which
  would assert measured-and-terrible about a file nobody can measure.
- Verified end to end on the AWC documents: the scan reports `dq_scored 6`, the
  merge persists Correspondence 86 / Gis 100 / Scada 100 (pdf and docx correctly
  none), the payload went from 97 to **103** links carrying a DQ score, and the
  apply rolled DQ 100 / 100 / 86 onto the three folder entities — which also
  moved all five folders from `file-level` to **`applied`** for the first time,
  and took the table/folder rating count from 9 to **14**.

## [1.17.1] — 2026-08-05

### Fixed — Data Discovery profiled one file per folder and reported success
- `_TBL_TYPES` listed `DIRECTORY` but **not `FOLDER`**, and PDC types an object
  store's folders **FOLDER** — a live scan reports *"16 FILE + 5 FOLDER entities
  discovered"*. The rest of the package already knew: `bulkload` uses
  `("FOLDER", "FILE")` and the container test reads `("DIRECTORY", "FOLDER")`.
  Only the entity-filter type lists had drifted.
- The consequence was well hidden. PDC filtered every folder out **server-side**,
  so `resolve_table_entity` returned `None` — indistinguishable from "that folder
  isn't catalogued". `resolve_document_scope` then did what it was designed to do
  and fell back to individual FILE ids "so nothing is silently dropped". But a
  Data-Elements payload carries **one representative file per folder**, and file
  scope does **not** cascade while folder scope does. So Discovery profiled 5
  files, skipped the other 11, and returned **SUCCESS** — nothing in the job, the
  Workers page or the app said otherwise.
- Verified against a live PDC: the job's scope labels went from
  `awc-documents.compliance.epa_…pdf` (dotted — the file fallback) to
  `awc-documents/compliance` (slashed — the folder), with no fallback warning.

### Fixed — the fallback is no longer silent
- `resolve_document_scope` returns scope stats, and a run that could not resolve
  its folders now says so: *"Folder scope cascades to every file inside it; file
  scope does not — any other files in those folders were NOT profiled."* The
  fallback is still the right behaviour; passing it off as full coverage was not.

### Fixed — `qualityScore` in the preview read-back was mislabelled
- It is the **MANUAL** metric an external writer sets — this app's own score.
  PDC's Discovery-*computed* Data Quality is a different metric and never lands
  there, so an unlabelled `—` on a document row read as *"PDC has no quality"*
  when it meant *"we never wrote one"* — and briefly had a working Discovery run
  diagnosed as a failure. Now labelled `qualityScore (app-set)`.

## [1.17.0] — 2026-08-05

### Changed — same-named terms are always disambiguated, never "kept separate"
- The duplicate advisor recommended **Keep separate** whenever the members'
  categories differed, on the reasoning that PDC can hold two same-named terms in
  different categories. PDC can. **Resolve cannot**: `resolve_terms` matches
  purely by name and breaks on the *first* hit, so two terms called "Status"
  resolve to whichever PDC returns first and one group's columns get stamped with
  the other group's term id — silently.
- The app already knew this. The generator's own preflight warns *"name-based
  Resolve can't tell them apart, so a column may link to the wrong one"* — so the
  advisor was recommending the state the export step flags as a hazard. A
  duplicate group is keyed **on the shared name**, so different concepts there
  always need renaming: the category branch is gone and both paths recommend
  **Disambiguate**.
- **Keep separate** stays as a control — it is the neutral state a Merge or
  Disambiguate reverts to — but it is no longer offered as advice for a group
  that would ship a name collision.

### Fixed — an undecided duplicate group looked like a decision
- `action === 'separate'` meant both *"the steward chose Keep separate"* and
  *"nobody has chosen anything"*, so an untouched group rendered Keep separate
  with the **selected** style: the app appearing to have picked the one outcome
  that ships two terms under one name, highlighted as if it were the advice,
  directly beside advice saying otherwise. Until a steward picks, nothing is
  selected and the recommendation is the only button lit (`aria-pressed` follows).

### Fixed — the UI kept serving the previous release's JavaScript
- `GET /` returned the React `index.html` as a bare `FileResponse` with **no
  `Cache-Control`**, so browsers applied *heuristic* caching to the one file that
  names the content-hashed bundle. The app upgraded on disk and the user kept
  loading the old JS, with no clue why, until someone told them to hard-reload.
  The Jinja shell always had its `v` cache-buster; the React path never got one.
- `index.html` now sends `Cache-Control: no-cache` — *"revalidate before use"*,
  not *"don't store"*, so the ETag/304 path is untouched. `/assets/*` is
  content-hashed by Vite and goes the other way: `max-age=31536000, immutable`.
  (That branch needed a Windows fix — `StaticFiles` `normpath`s the request path,
  so it arrives as `assets\index-<hash>.js` and a `startswith("assets/")` test
  never matched on the platform the app ships on.)

### Fixed — "AI advise" blamed Ollama for runs it was never asked to do
- `used_llm: false` covers both *the model was unavailable* and *the model was
  never needed*, and the message assumed the first — reporting *"Ollama offline
  so evidence decides"* on a run where Ollama was demonstrably up and the live
  probe had settled all eight groups on data. The endpoint now returns
  `ambiguous`, and the UI distinguishes *"the data settled every one, so no model
  call was needed"* from *"the model did not answer"*.
- The button also shows the scope it always had: the server escalates only groups
  the deterministic pass could not settle (`band != "high"` — the same predicate
  behind the **check** badge), so it now reads **AI advise (N)** against N check
  badges and disables itself at zero instead of costing a pointless round trip.

## [1.16.1] — 2026-08-05

### Fixed — a QA flag survived the rewrite that cleared it
- Accepting an AI-proposed definition left the old **QA ⚠** chip pinned under it,
  so a definition the model had just rewritten into something specific still read
  *"generic scan template — says nothing specific to this column"*. Once saved,
  the stale flag persisted into `glossaries.json`.
- The server was right: `/api/ai-pass` re-lints after the model and drops
  `QA_Issues` from every row that is no longer flagged. The bug was on the wire —
  the grid merges each returned row over its working copy with a spread
  (`{...working, ...returned}`), and a **removed key is invisible to a spread**.
  The old value survived, diffed as unchanged, and so never reached a pill; the
  `QA_Issues` carry on Definition had nothing to carry. The cleared flag is now
  sent as an explicit empty value, which a merge can actually apply.
- Verified against the saved Arizona Water glossary on the row that had it stuck:
  flag present → **AI review** → accept the Definition pill → flag gone.

## [1.16.0] — 2026-08-05

### Changed — one agent, and a per-row **AI review** instead of two leftover buttons
- **Enrich with LLM** and **AI suggest (evidence)** are gone from the toolbar.
  1.15.0 folded them into the AI pass but kept both around "to re-run a single
  field", which never justified two buttons: the pass proposes *per-field pills*,
  so re-running one field was always a matter of accepting one pill.
- What was actually missing was **scope**, not agents. An expanded row now has
  **AI review** — the same `/api/ai-pass` call, prompt, evidence and guardrails,
  targeted at that one row, for when a single term came back weak and a full
  sweep isn't worth the minutes. A per-row click runs whether or not **Keep** is
  ticked: the kept-rows rule exists to stop a *sweep* spending model time on
  pruned noise, not to veto an explicit click.
- The real cost of the leftovers was **three prompts restating the same
  guardrails** — tags governed-only, never set sensitivity or PII, fill category
  only when blank. Changing one meant changing three or letting them drift.
  `_ai_pass_one` is now the only row-level agent prompt in the codebase.

### Removed
- `enrich_definition`, `enrich_purpose`, `enrich_one`, `enrich_batch`,
  `enrich_rows`, `_suggest_one` and `suggest_terms_rows` from `llm.py` (~330
  lines), plus the `POST /api/enrich` and `POST /api/ai-suggest` routes. Both
  were subsets of the combined pass: Enrich saw no scan evidence at all — just
  the term, source column, current draft and category — and AI suggest never
  touched Definition or Purpose, while its category rule already fired on blanks
  only. Neither could contribute anything the pass hadn't already produced.

### Fixed — the batched pass never saw the scan's reasoning
- `Suggested_Reason` is evidence the retired AI-suggest agent leaned on, and
  `_ai_pass_one` sent it — but `_ai_pass_batch`, the path that actually runs,
  did not. Absorbing that agent without its evidence would have quietly lost
  something, so the batch prompt now carries it too.
- It is filtered on the way in. `ai_pass_rows` appends its own answer to
  `Suggested_Reason` as `AI(pass): …`, so sending the field raw would hand a
  second run its previous reply back as though the scan had observed it — the
  model arguing with itself. New `_scan_reason()` keeps only the scan's half.

## [1.15.1] — 2026-08-05

### Fixed — a flagged row was told to rewrite twice
- `_ai_pass_one` built its evidence list with the `QA_Issues` block pasted twice,
  so a flagged row's *"the current definition was flagged as: …"* line appeared
  two times in one prompt. Only the per-row fallback path was affected — the one
  the pass drops to when a batch reply is malformed — and the batch prompt that
  normally carries the *REWRITE REQUIRED* order was always correct. No output
  changed; the duplicate just spent budget and read as misplaced emphasis.
- The existing linter test only covered the batch prompt, which is how this got
  through. A regression test now drives the per-row fallback and asserts the flag
  is stated exactly once — verified to fail against the pre-fix module. 94 tests.

## [1.15.0] — 2026-08-05

### Changed — one combined **AI pass** replaces three overlapping agents
- Enrich, AI suggest and AI categorize each swept every kept row on their own,
  and they overlapped on name / category / tags — so a scan paid for three
  passes and the last agent silently overwrote the others' proposals. The new
  **AI pass (all fields)** covers definition, purpose, a clearer name, governed
  tags and a blank category, under the same guardrails: tags governed-only, an
  existing category untouched, the name offered as a `Suggested_Name` chip, and
  sensitivity / PII still deterministic from the scan. Measured on real rows,
  2.2× faster than the passes it replaces.
- **Suggest tags** and **AI categorize** are gone from the toolbar: categorize
  is covered blank-only by the pass, and the deterministic governed-tag
  derivation now runs inside `/api/ai-pass` — no LLM time, one less button, and
  the model sees the governed tags as context so it can only add to them.
  **Enrich** and **AI suggest** remain for re-running a single field.
- The **AI QA judge is retired** — a whole extra sweep over every row for little
  gain. Its deterministic half survives and costs nothing: the definition linter
  (circular, echo, vague, too-short, duplicate) runs inside `/api/ai-pass` and
  still stamps the QA chip.

### Added — the AI pass is batched, and says what it is doing
- The pass now batches like `enrich_batch` does: **one call per `LLM_BATCH` rows**
  (default 6) instead of one call per row, with a per-row fallback if a batch
  reply is malformed so bad JSON never drops a chunk. Measured on real AWC rows
  with `gemma3:12b`: 6 rows in one 48s call, where the per-row path spent ~36s
  *per row*. A 120-row scan goes from ~120 calls to ~20.
- Live progress for a run that is now minutes long: the batch is announced
  **before** its call (a bar that only moves on completion reads as stuck), and
  the panel shows batch *N* of *M*, ticking elapsed, an ETA and s/row derived
  from the batches already done, plus the terms currently in flight and a
  pulsing segment for the batch being worked.

### Changed — the definition linter's flags became rewrite orders
- A QA flag was a dead end: it said a definition was generic without proposing
  anything, and said it again on the next scan, so the steward saw the same
  complaint three runs running with nothing to act on. The linter now runs
  **before** the model inside `/api/ai-pass` and its verdict is fed into the
  prompt as *"REWRITE REQUIRED — flagged: generic, echoes the term"*, with an
  explicit instruction to replace the draft using a specific sentence from the
  evidence. Rows are **re-linted afterwards**, so what remains flagged is what
  the model could not improve from the available evidence — a real signal
  instead of repeat noise. No extra model calls: same batch, same pass.
- The linter also flags **the scan's own templated definitions** ("Severity
  associated with an account alert record", "Unique identifier for a account
  alert record"). They read like prose, so no existing rule caught them — not
  too short, not circular, not a vague opener — yet they carry no business
  meaning, since every column in a table gets the same shape. Verified against a
  live AWC scan with `gemma3:12b`: five templated definitions came back specific
  and the post-pass lint flagged none of them.

### Added — profile / discover scans an object store's files first, plus **Get token**
- Data Discovery does **not** crawl a bucket — it analyses what a *file scan* has
  already catalogued. With the ingest skipped there were zero file entities, so
  Discovery had nothing to do and the object store came back `profile=FAIL` while
  the database profiled fine. **Profile / discover** now triggers the file scan
  first for an object store (PDC's own Scan Files call via the internal
  `/api/start-job`, with the same bearer token) and then runs Discovery. Verified
  end to end: create EXISTS → ingest OK → job OK → profile OK, with 16 FILE and
  5 FOLDER entities discovered. The separate *"scan object stores (internal API)"*
  checkbox is gone — one control does the whole job.
- A **Get token** button beside the PDC credentials mints the bearer token from
  the username / password and reports who it belongs to (roles, expiry) before
  anything writes. Every call in the run — create, ingest, profile / discover —
  reuses that token.
- The entities filter is clamped to `size<=500`, which the API enforces.

### Changed — the Detection toggle spells out what it will write
- Auto vs Mapping-only changes only the exported Registry, so flipping it in the
  grid looked like it did nothing. The row now states its effect: with a value
  shape, **Auto** seeds a detection method; without one, **Auto** leaves detection
  open (Policy will request a seed) while **Mapping-only** closes the question.

### Fixed
- **Long model calls timed out silently.** `_complete_json` swallowed timeouts and
  returned `None`, so on a big local model (a combined call takes ~100s against a
  30s budget) every agent reported *"no changes proposed"* — indistinguishable
  from the model having nothing to say. Long-prompt calls now get their own budget
  (`GLOSSARY_AI_PASS_TIMEOUT`, 180s default), timeouts are counted, and the run
  summary says the model did not answer in time and points at the Settings timeout.
- **The AI pass crashed before any request left the browser.** The runner
  referenced `settings`, which `ReviewPage` does not have (copied from the
  Dictionary page), throwing a `ReferenceError` ahead of the fetch — so every
  chunk landed in the catch and the run ended instantly with *"no changes proposed
  (120 row(s) failed)"*. The server uses its own configured model, so the field is
  simply gone.
- **A bare `401 Unauthorized` on bulk load when the PDC base URL is an IP.** PDC's
  proxy routes the internal API (`/api/start-job`, the file-scan trigger) by
  hostname, so on a bare IP it 401s even with a valid token while the public API
  answers fine on the same address. The result was a run where every database step
  succeeded and only the object store failed, with no clue why. The row's error now
  names the cause and the fix: use the vhost URL (e.g. `https://pentaho.io`), not
  the IP.

## [1.14.0] — 2026-07-23

### Added — hosted LLM providers (Anthropic, OpenAI, Azure OpenAI, Google)
- The AI agents are no longer Ollama-only. A new **`llm_providers.py`** adds a
  provider abstraction behind the two functions every agent already funnelled
  through (`llm._complete` / `_complete_json`), so Enrich, AI suggest, QA,
  categorize, Suggest tags, policy hints, duplicate adjudication, expertise and
  domain all work on any provider with no per-agent changes.
- **Settings → LLM provider** picks the backend. Ollama-only controls (URL, GPU
  offload, Pull model, installed-model list) hide for hosted providers, which
  instead show an API-key field — plus endpoint / API-version for Azure. Model
  ids are suggestions, never a whitelist: a custom id is always allowed, since
  vendors add and retire ids on their own schedule.
- **API keys are session-only by design.** A key entered in Settings lives in
  process memory and is *never* written to `settings.json`, so the State
  snapshot (which zips that file) can't leak billing credentials; `POST
  /api/settings` also strips credential-shaped fields defensively. Persist a key
  by exporting the provider's env var (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `AZURE_OPENAI_API_KEY`, `GOOGLE_API_KEY`). Resolution is session → env, and the
  UI is told only *whether* a key resolves and from where — never its value.
- Each SDK (`anthropic`, `openai` — which covers Azure too — and `google-genai`)
  is imported lazily and listed as optional in `requirements.txt`, matching the
  boto3 pattern: absent SDKs degrade to a clear *"run: pip install …"* rather
  than breaking startup. New endpoints: `GET /api/llm-providers`,
  `POST /api/llm-key`, `POST /api/llm-test` (a real round trip, so the Settings
  result reflects key validity and model id, not just configuration).
- Hosted replies are JSON-parsed tolerantly (bare object, ``` fence, or prose
  around it) since only Ollama guarantees raw JSON.

### Fixed — Ollama model status could report a model as present when it wasn't
- `llm.status()` matched the model tag by prefix, so `llama3.2:3b` reported
  `model_present: true` when only `llama3.2:latest` was pulled — the UI showed
  "online" while every generation call 404'd. It now matches the exact tag.
  Switching the provider back to Ollama also prefers a model actually pulled on
  the host instead of the catalog default.

## [1.13.1] — 2026-07-23

### Added — type-derived DQ checks (dates & numerics)
- The scan now persists each column's **physical type** on the row
  (`Source_Types`), and DQ expectations derive **type-conformance checks** from
  it: date/timestamp columns get `valid_date`, numeric columns get `numeric` —
  sourced `schema (type …)`. Valuable where the rules actually run (extracts /
  landing zones, where the engine no longer enforces types). A name-shaped
  fallback (`*_dt`, `date`, `dob`…) covers rows scanned before types were
  persisted. Still custom-only: the type is the scan's own metadata.
- On CSCU this lifts the bundle from 28 to **43 DQ rules**, dates included.

## [1.13.0] — 2026-07-23

### Added — Data-quality expectation rules in the policies bundle
- **Draft policies now emits a third artifact class: `Quality/` DQ-expectation
  rules** — the industry-standard three-layer split completed (glossary = what
  it is, detection = which columns are one, quality = are the values valid).
  One JSON per kept term with scan-derived signals, data-contract style:
  - **format** — the induced value regex (+ signature) as a conformance check
    (e.g. Loan Number must match `^LN-\d{6}$`),
  - **allowed_values** — the profiled reference list,
  - **not_null** — threshold 1.0 from a NOT NULL constraint, else the measured
    completeness as a baseline,
  - **unique** — for PKs / identifier-shaped columns, baseline = measured
    uniqueness.
  Every check carries its `source` (profiled / schema). Custom-only: same
  discipline as the patterns — no inbuilt thresholds; a term with no profiled
  signal gets no rule, and baselines mean "a run below what the scan measured
  is a regression". Included in the zip bundle (`Quality/`, INDEX, README) and
  Send-to-lab; the Apply summary lists each rule with its check count.

## [1.12.0] — 2026-07-23

### Added — Best-practice structural-key pruning (glossary ≠ physical schema)
- **The scan auto-prunes structural keys as business terms** (deterministic,
  reversible): a surrogate PK / FK reference-id (`*_id` name, no identity PII,
  no profiled value shape) arrives with **Keep un-ticked**, a **KEY** badge and
  the reason on the row, and a **"Structural keys auto-pruned N"** chip. Natural
  / business keys (`mbr_no`, `acct_no` — formatted, or identity PII like
  `tax_id`) are always kept. Ticking Keep restores any row. Mirrors how mature
  catalogs (Actian/Zeenea, Collibra, Alation) model it: keys belong to the
  physical layer, not the business glossary.
- **The Registry now carries a `physical_model`** built from EVERY scanned
  column's PK/FK facts (kept or pruned) — keys + FK relationship edges — so the
  join graph is authoritative and independent of glossary curation. Pruning a
  key as a term never loses the relationship; the Policy Generator reads
  identity/reference-join context from the physical model.
- When the dictionary canonicalizes a surrogate and its natural key onto ONE
  term (`mbr_id` + `mbr_no` → "Member Number"), the natural key wins: the merged
  term stays kept with both columns linked.
- Auto-pruned keys sit **outside duplicate resolution** (they never form or join
  Merge/Disambiguate groups) and **Keep High+Med conf** won't silently resurrect
  them (key columns are High confidence).

### Fixed — glossary store hardened against silent wipe
- The saved-glossary store was read-modify-rewrite with a loader that returned
  an EMPTY store on any read error — so a transient failure (e.g. the file
  locked by a second backend instance) could make a save silently discard every
  other saved glossary. Write paths now use a **strict load** (refuse to save /
  delete when the file exists but is unreadable, HTTP 503) and any rewrite that
  **shrinks** the store first snapshots the file to `glossaries.json.bak`.

## [1.11.3] — 2026-07-23

### Fixed — Lab object store (MinIO) config UX
- The HTTPS toggle is now **authoritative over the endpoint scheme**: an
  explicit `https://` in the URL no longer silently overrode an un-ticked box
  (which produced confusing TLS errors). Toggling HTTPS rewrites the scheme, and
  typing a scheme syncs the box.
- An inline **nudge** when the endpoint uses the **console port `:9001`** or has
  **no port** — the S3 API is on `:9000`.
- `(optional)` sits inline with the **Bucket** label (was dropping to its own
  line under the flex-column label).

### Changed — Draft policies are custom-only (no inbuilt canonical shapes)
- Removed the hardcoded `_CANONICAL_SEEDS` (SSN `nnn-nn-nnnn`, email regex) from
  `policy_draft.py`. The Policy Generator now authors a Data Pattern / Dictionary
  **only** from a concept's own profiled scan evidence (induced `Value_Pattern`
  or reference list) — never an inbuilt shape, which could misclassify against
  the real data and cause drift (e.g. stamping an SSN rule gated on
  `GOVERNMENT_ID` when the column is classified otherwise).
- A concept like SSN still gets a custom policy — but the pattern is induced
  from the actual values, so re-scan the source with **value profiling on**. The
  skip reason now says exactly that.
- **Curated domain-pack seeds now flow into Draft policies** (not just the
  Registry): `draft_from_rows` fills a gap from the versioned pack's
  `curated_seeds` (source `curated`) when profiling can't induce one — the
  custom-only program's generic baseline, still no hardcoded shapes. Profiled
  evidence always wins; the UI labels each artifact `profiled` or `curated` and
  counts them.

### Changed — AI-suggest guard-rails tightened (no governed-field drift)
- **PII_Category is re-asserted from the scan classifier.** AI-suggest now runs
  a deterministic PII guard (`suggester.guard_pii_row`): an un-profiled column is
  clamped to what the classifier assigns, rejecting any value the scanner
  wouldn't (an `ssn` mislabeled `PERSONAL_NAME` becomes `GOVERNMENT_ID`; a
  spurious `ADDRESS_INFO` on an id column is cleared). Profiled columns are
  trusted. Surfaces as a proposal pill. (The AI never *set* PII — this heals
  drift from imports/legacy scans and prevents future drift.)
- **AI-suggest no longer overwrites a category** — it only fills a **blank** one
  (matching AI categorize); an existing category the scan/steward set is kept.
- **AI-suggest no longer proposes sensitivity** — sensitivity stays deterministic
  (scan classifier + value profiling + governed-tag floors; only a steward
  raises it). The LLM prompt no longer asks for sensitivity or PII.

### Changed — Draft-policies skip reasons distinguish link-only from not-profiled
- The big "no profiled evidence — re-scan" bucket lumped together columns that
  will *never* have a value shape (surrogate integer keys, dates, names, raw
  amounts) with ones that simply weren't profiled. A column-name heuristic now
  splits them: surrogate-id / date / name / amount columns read *"tagged via the
  term↔column link, not a value pattern — …(expected)"*, so the steward isn't
  told to re-scan a column that can't be seeded. On CSCU this turns an alarming
  72-term "re-scan" list into ~32 expected link-only + ~20 actually-actionable.

### Fixed — Draft-policies "skipped" list showed "undefined" for every term
- The skipped-terms line read `s.reason`, but `draft_from_rows` returns the
  reason in `s.why`, so every skipped term rendered `— undefined`. It now shows
  the real reason, **grouped by reason** with a lead-in noting a rule needs a
  value *shape* (a profiled value pattern or a reference-value list), not just
  tags — e.g. *no profiled evidence on the row — re-scan the live source*
  (SSN and most columns land here when the glossary was built without live
  value profiling), *no stable shape (free text, names, amounts, dates)*,
  *table-level term*, and *document term*.

## [1.11.2] — 2026-07-23

### Added — Lab MinIO connection status + configuration
- **Connectivity dot on "Send to lab".** The Apply page's export controls now
  show a live green/red dot for the lab MinIO, with the reason inline (e.g.
  *InvalidAccessKeyId — the access key doesn't exist*) and a **Configure →**
  link to Settings when it's not reachable. Backed by a new bucket-agnostic
  reachability check (`suggester.reach_minio` via `list_buckets`, so it goes
  green on a valid endpoint+credentials even before the export bucket exists)
  and `POST /api/lab-minio-status`.
- **Settings → "Lab object store (MinIO)"** card to configure the export target
  (endpoint, access/secret key, optional bucket, HTTPS) with a Test button +
  status dot. Saves a dedicated `lab-minio` connection that "Send to lab"
  prefers. The hint spells out that the **S3 API is on `:9000`** (`:9001` is the
  web console only, and `mc` also uses `:9000`).
- Error hints for the common lab mistakes: wrong keys, TLS/scheme mismatch, and
  hitting the console port instead of the S3 API port.

## [1.11.1] — 2026-07-23

### Added — Review AI-agent guidance + toolbar order
- Each agent now has a one-line **"what it does"** explanation (Enrich, AI
  suggest, AI categorize, Suggest tags, AI QA definitions), sourced once and
  shown in **both** the "How to review" guide **and** the proposal strip that
  appears when a run finishes — so the explanation is right there when you're
  deciding whether to accept. Previously that detail lived only in the buttons'
  hover tooltips.
- **AI QA definitions** moved to the **end** of the AI-agents toolbar so the
  button order matches the documented working sequence — QA is the quality gate
  and runs last, after Enrich → AI suggest → AI categorize → Suggest tags.

### Fixed — Govern "Glossary name" no longer starts blank
- The **Apply stewardship** "Glossary name" field (the PDC glossary name written
  into the JSONL at export) sat empty until typed, even when the workspace
  already had a saved-glossary name. It now defaults to the saved name — set
  when a glossary is opened or first named — so it's pre-filled and still
  editable (an explicit value always wins).

### Fixed — Govern "⚡ auto" domain button pushed under the next column
- On the **Stewardship defaults** row, the Domain `<select>` (flex:1) kept its
  default `min-width:auto`, so it wouldn't shrink below its longest option and
  the inline **⚡ auto** classifier button overflowed the cell — sliding under
  the next field and becoming unclickable. The select can now shrink
  (`min-width:0`) and the button holds its width, so both fit on the row.

### Fixed — Review page lost its working state on navigation
- Leaving the Review page (e.g. hopping to the **Dictionary** to approve
  vocabulary) and coming back reset the grid's filters, the open editor row,
  duplicate-resolution (Merge/Disambiguate) state, Find-similar results, the
  Keep-High+Med revert snapshot and the scroll position — the App renders only
  the active page, so the inactive one unmounts and its local `useState` was
  discarded. These now persist for the session via a small `usePersistentState`
  cache in `state.js` (namespaced `review.*`), cleared when a **different**
  glossary is opened so nothing bleeds across.
- Also fixed a related latent bug: the **Reset all** baseline (`snapRef`) was
  re-captured from the *already-edited* rows on remount, so Reset all would
  reset to your edits rather than the raw scan. The baseline is now persisted.

### Changed — Schema ER diagram auto-layout
- **Mutual-FK cycles no longer strand a hub in the leftmost layer.** A pair
  like `branches.mgr_emp_id ⇄ employees.br_id` is a 2-cycle; the old
  cycle-breaker kept an incidental back-edge that pinned `employees` to the
  far-left column even though `kyc_reviews` and `suspicious_activity` (far
  right) reference it — so those FK edges spanned the whole diagram. The
  layout now drops the edge into the **less-referenced** table of each mutual
  pair, so the bigger hub stays left and its partner floats to its natural
  depth beside the tables that use it.
- **Result on the CSCU core-banking schema (14 tables, 15 FKs):** edge
  crossings 12 → 7 (only one a true crossing), total edge length −17%,
  bounding box 1824×587 → 1176×583 — so *Fit* opens at ~79% instead of the
  55% floor, and the graph is centred with no clipped curves or labels.
- More barycenter ordering sweeps (4 → 8) and vertical relax passes (3 → 5)
  for a bit more crossing reduction on denser schemas.

### Changed — Document discovery panel clarity + colour coding
- **Clean 2×2 layout.** The four breakdowns (By file type, By folder,
  Largest objects, Most recent) used the shared auto-fit `.grid-2`, which
  wrapped to **three** columns on a wide Connect card and orphaned "Most
  recent" on its own row with a large empty gap. They now sit in a fixed
  2×2 of bordered panels (each with an uppercase heading + count chip),
  collapsing to a single column under 820px.
- **File-type colour coding.** Each extension gets a fixed hue (pdf red,
  docx blue, csv green, xlsx teal, json amber, txt slate, md violet;
  anything else muted). The hue drives the *By file type* bar and a small
  colour dot on every Largest/Most-recent row, tying the two views together.
- **Readable object keys.** Largest/Most-recent rows now show the folder
  prefix muted and the filename bold (instead of one long clipped mono
  string), using the wider half-card column before ellipsizing.
- React edition only (`frontend/`); the legacy Jinja fallback
  (`templates/` + `static/js/05-connections.js`) is unchanged.

## [1.11.0] — 2026-07-18

### Added — the Glossary half of the no-seed feedback loop (with Policy Generator)
- **`detection_intent` on Registry concepts.** The Registry writer now states
  each concept's intent: `"mapping_only"` when the steward flagged the term
  (the flag always wins), `"seeded"` when the concept carries detection seeds
  (profiled or curated), and the field is **omitted** when neither applies —
  that gap is the Policy Generator's cue to ask.
- **Detection toggle on the Review grid.** The expanded row editor's evidence
  strip gains a **Detection: Auto / Mapping-only** seg. Mapping-only = the
  term is governed by term links (Apply) and has no value shape, so the
  Policy Generator stops expecting a detection method for it. Persists on the
  row (`Detection_Intent`) via autosave; the legacy UI passes the field
  through untouched.
- **Seed-request pickup.** The Policy Generator writes `seed-request*.json`
  beside the Registry (`{requested_at, registry_file, terms:[{name, reason}]}`)
  when concepts arrive with no seeds and no intent. New `GET
  /api/seed-requests` lists pending requests; `POST /api/seed-requests/handle`
  renames one to `*.handled.json`. The Review page shows a banner —
  **Show these terms** filters the grid to the requested names, the guidance
  line spells out the fix (re-scan with Profile data on, or mark free-text
  terms Mapping-only, then Generate again), **Mark handled** retires it.
- Tests: `tests/test_seed_loop.py` — intent emission (seeded / flag-wins /
  omitted) and the seed-request list + handle round-trip.

### Fixed — "What it does" workflow diagram (README + GUIDE)
The mermaid overview redrawn for clean rendering on GitHub: the Term & Tag
dictionary now sits fully **inside** the Glossary Generator cluster (between
Review and Govern, dotted hop Review → dictionary → Govern — no edges
crossing the main spine), the lab-sources cylinder keeps a two-word label
with the "DBs · MinIO · DDL" detail on its edge, and the PDC import target
is a rectangle ("PDC — glossary import") so its label no longer clips.
Validated with mermaid.parse and a real rendered-geometry check (all labels
inside their shapes, zero edge crossings).

## [1.10.11] — 2026-07-18

### Changed — docs sync
Docs-only release: README, GUIDE and REFERENCE caught up with 1.10.8→1.10.10.
The agent write-ups now describe the **inline click-to-accept proposal
pills** (live per batch, Accept all / Dismiss all, LLM provenance only after
accept) instead of the retired proposal panel/diff wording; the Review
guide is documented as the **interactive clickable flow** (Dictionary hop
and the AI-agent sequence chips included); the Schema ER section carries
the round-three **Fit** facts (canvas sized to the diagram, 55% zoom floor,
side-by-side wrap for dense layers); the Apply docs gain the
**terminal-aware discovery watcher** (per-file profiled ✓ /
no-DQ-from-PDC / failed wrap-up) and the new **⇪ Send to lab (MinIO)**
export (`POST /api/lab-export`, bucket `pdc-exports`, write-capable
connection required); and the DQ semantics are stated everywhere they
matter — unprofiled columns show **DQ —**, never a fabricated 100.
REFERENCE's API table adds `/api/discovery-progress` and `/api/lab-export`.
No code changes.

## [1.10.10] — 2026-07-18

### Added
**"Send to lab" export (Apply)** — the Generate card's JSONL and the drafted-
policies zip each gain a ghost **⇪ Send to lab (MinIO)** button that uploads
the just-generated artifact to the lab MinIO over one of the app's saved
MinIO/S3 connections (a picker appears when several are saved), via the new
`POST /api/lab-export`. The export lands in bucket **pdc-exports** (created
on first use) under a timestamped key; the success line shows bucket/key and
the on-VM path (MinIO console `:9001`, or `mc cp` to `~/Downloads`).

### Changed
**Discovery watcher is terminal-aware (Apply step 4)** — the "N of M
profiled…" watcher no longer hangs until its 10-minute budget when PDC
finishes without profiling every file (pdf/docx-style types get no Data
Quality, so their `profiledAt` never flips). `/api/discovery-progress` now
also polls the discovery job's own status (when v1/v2 returned a job id) and
returns a per-entity profiled map; the watcher stops the moment the worker
reaches a terminal state and prints a per-file wrap-up — profiled ✓ /
no-DQ-from-PDC (expected for the type) / failed — plus elapsed time. Hitting
the watch budget now says so explicitly ("Watch budget reached (10 min)…")
instead of a vague still-running note. Stop watching stays.

**PDC connection panel (Apply)** — same clean grid treatment Govern's
Keycloak fetch panel got in 1.10.9: a fixed 4-column grid (Base URL / API
version / Keycloak realm / Username, then Password / Bearer token spanning
three columns) with the hints under their inputs, and the TLS tick moved to
the action row beside the primary **Get admin token**.

### Fixed
**DQ 100 was assertable without profiling** — `quality_score_column()` let a
bare NOT NULL constraint stand in for completeness when nothing was profiled,
so unprofiled scans (e.g. pasted DDL) showed a wall of DQ 100s claiming
perfect quality about data nobody sampled. An unprofiled column now yields
**no score** — the Data Elements JSON/CSV omit `qualityScore` and the apply
tables show a muted **DQ —** ("not profiled") chip instead of 100. The
NOT-NULL proxy still applies when at least one dimension was really measured.
Verified against the CSCU lab database (192.168.1.200:5433, read-only): on
live-profiled scans the 100s are genuine — the planted defects are null/blank
based and DO score lower (accounts.close_dt 0, ach_payments.return_cd 17,
transactions.mcc_cd 35, merch_nm 65, branches.mgr_emp_id 67,
loans.collateral_desc 67, suspicious_activity.mbr_id 75), while the remaining
columns' completeness truly is 1.0 on the small lab tables and PDC-style
format defects that stay format-valid are invisible to sampling.

## [1.10.9] — 2026-07-17

### Changed
**Primary-button sweep** — the action that drives the workflow is now the
blue primary button on every page, one per panel where possible: Connect's
Harvest panel **List data sources** and pre-flight **Check in PDC**, Schema's
**Diagram SQL**, Apply's **Pull / refresh links from glossary** (step 1 of
Data Elements), Govern's **Apply stewardship to terms** and bottom-nav
**Resolve term IDs →**, Dictionary's
**Export domain pack** and the **⤵ AI fold advisor** (now a standard-size
primary above the Terms table instead of a mini in the heading), Review's
**Save glossary**, and Settings' **Test connection** plus **Restore from
snapshot…** (with **⬇ Download snapshot** becoming a standard ghost button
instead of a link). Settings' Enrichment-tuning row also aligns its three
inputs on one baseline (the Company hint moved below its input).

**Govern polish** — the roster's Name-&-functions chips now show each
person's true role state at a glance: a held function is a filled accent
chip with a ✓ (tooltip says whether it comes from a Keycloak role or a
manual roster override), a not-held one is a muted dashed outline; both
remain click-to-toggle. The Keycloak fetch panel is a fixed 4-column grid
(Base URL / Realm / Admin realm / Username, then Password / Bearer token
with its hint under the input) with the checkboxes and the primary Fetch
on one action row. Stewardship defaults aligns every input on one baseline:
the Domain hint sits inline with its label, ⚡ auto is a compact chip
attached to the Domain select, and "apply to categories too" lives with
the Reviewed-date field it accompanies.

### Fixed
**Apply stewardship stamps kept terms only** — "Apply stewardship to terms"
was stamping steward / owner / custodian onto every workspace row, dropped
ones included ("128 of 128" after pruning to 95). It now stamps only rows
with Keep ticked and reports "… onto N of N kept term(s)"; the per-category
override cards likewise build from kept rows only, so a category that
survives solely in dropped rows no longer drives stewardship.

**Schema ER layout, round three** — Fit now really centres: the canvas
sizes itself to the diagram (capped at 70% of the window) so there are no
dead bands above or below; dense layers (>4 tables) spread with a wider
vertical gap; the layer pitch stretches to fill ~90% of the canvas width;
Fit is floored at 55% zoom so node titles stay legible — a layer that would
sink below that wraps into two side-by-side node-columns instead (very
large graphs accept the 55% floor and pan). Verified numerically on a
14-table / 15-FK / 3-orphan shape: fit 62%, top and bottom margins equal,
no node overlaps.

**Review guide is now interactive** — "How to review" is a Home-style
clickable flow: ① Prune → ② Resolve duplicates → ③ Approve pending
vocabulary (the box navigates to the Dictionary, with a come-back note) →
④ the AI agents as sequence chips (Enrich → Suggest · Categorize · Tags →
QA as the gate; chips highlight the AI toolbar) → ⑤ Name the glossary →
Govern (navigates). The ordered list underneath matches, including when to
flip to the Dictionary (after prune/merge, before the tag agents — approved
tags feed Suggest tags) and back.

**AI agent results are now inline pills — the proposal popup is gone.**
Agents still propose-then-apply (the grid never mutates mid-run), but the
presentation moved into the grid: as each batch returns, click-to-accept
pills light up on the affected cells — Term gets the classic **→ name**
chip, Definition/Purpose previews get an **AI →** pill (tooltip shows the
proposed text; the expanded editor shows old vs proposed side by side with
its own Accept), and Category / Sensitivity / PII / Tags get compact
**AI → value** pills. A slim strip above the grid tracks the run ("N AI
proposals on M rows · **Accept all** · **Dismiss all**") and a live
"rows with proposals so far" counter sits next to the progress bar while
batches stream in. Accepting a field also carries its provenance flags, so
the grid's **LLM** pills appear only after a proposal is accepted — the
strip and guide say so explicitly.
The Review summary chips are colour-matched to the grid: Confidence H/M/L
in the Conf. badge palette (green / amber / muted); PII and Sensitivity
keep the sensitivity palette.

## [1.10.8] — 2026-07-17

### Changed
Home: the saved-glossaries table now uses a fixed column layout so every
header sits over its column, with Terms/Kept right-aligned end to end.
The blank "Glossary" column is now **"PDC glossary"** with a tooltip —
it's the export name set via the Govern page's Glossary name field —
and shows a muted, hinted — until one is set. The "What it does"
workflow diagram (README + GUIDE) was redrawn: app pages grouped in a
Glossary Generator subgraph, short cylinder/edge labels and wrapped
node text so nothing clips.

## [1.10.7] — 2026-07-17

### Changed — docs sync
Docs-only release: README, GUIDE and REFERENCE caught up with everything
1.10.0→1.10.6 shipped. README + GUIDE now describe the Schema page's
Cards | ER-diagram toggle and drag-and-drop DDL zone, Review's
"How to review — the working order" panel, scrolling grid with expandable
Definition/Purpose editor rows, the labelled kept-rows-only AI-agent group
(propose → apply), the Dictionary's flywheel + "Approve, Retire or Alias"
explainers, labelled ✓/✕/⤵ actions, header-level AI review of pending, and
the honest (identity-keyed, rescan-idempotent, pre-deployment) facet
counts, plus the sidebar-footer PDC connection dot and full-width page
headers. REFERENCE's layout/manifest now lists `frontend/` with the nine
React pages. No code changes.

## [1.10.6] — 2026-07-17

### Fixed
Dictionary: the "show N rows" setting now also caps the pending-review
term list (scrolls within the window like the governed tables) — it
previously governed only the vocabulary tables while all pending items
rendered unbounded.

## [1.10.5] — 2026-07-17

### Fixed
- **AI agents run on kept rows only** (legacy ran on everything): pruning
  141→95 now means the agents process 95 — progress reads "0/95 (kept
  rows)" and QA flags skip dropped rows. Proposal mapping verified
  end-to-end (absolute-index join; structural ops locked during runs).
- **Dictionary action buttons rendered as blank pills** — root cause was a
  CSS class collision: Connect's bare `.mini` (a 52×7 completeness bar)
  clobbered `button.mini` app-wide in the bundled sheet. Scoped to
  `span.mini`; actions are now labelled ("✓ Approve" / "✕ Retire" /
  "⤵ To alias") with tooltips and aria-labels.
- **Facet-preview counts were accreted per scan** (cde showed 281 with 124
  terms after repeated scans): usage is now identity-keyed — distinct
  current terms per tag, distinct source columns per term — so rescans are
  no-ops; reject/fold/junk-heal keep counts current; legacy numeric counts
  migrate by rebuilding from term evidence. A steward Save no longer
  silently zeroes usage or the retire-empty gate. 4 regression tests.

### Changed
- Dictionary: "AI review pending…" promoted into the pending-panel header,
  fold advisor labelled with an inline hint, and a new "Approve, Retire or
  Alias" explainer with CSCU examples beside the flywheel panel.
- Page headers use the full width (the 560px intro cap is gone), and the
  facet-preview note now explains the pre-deployment semantics: live
  facets appear in PDC after methods deploy and Data Identification runs.

## [1.10.4] — 2026-07-17

### Changed — ER layout refined; Review guide opens by default
Schema ER diagram: fixed the mount-time fit race that left the graph
huddled bottom-right; true bounding-box fit with auto re-fit until first
interaction; wider layer pitch + neighbour relaxation (dependents align
with their hubs); edges fan at shared targets, detour around intermediate
nodes (audited: zero pass-throughs), labels get opaque chips placed to
avoid every node and each other. Review: the "How to review" guide panel
now starts expanded, spans the full width, and notes when to visit the
Dictionary (pending vocabulary from scans; tags draw from the governed
allow-list).

## [1.10.3] — 2026-07-17

### Changed — the Review grid breathes
Ten always-visible inline inputs left every cell squashed (four-character
Definition boxes at 141 rows). The grid now scrolls inside its own pane with
real per-column min-widths, a sticky header and frozen Keep / Category / Term
columns; **Definition and Purpose collapse to one-line previews** that expand
in place — click either to open a full-width editor row with proper textareas
and the row's scan evidence (sources, induced pattern, value signature,
reference values) right underneath. Nothing moved to a modal and nothing was
dropped: sensitivity, CDE, tags, confidence and the evidence popover all work
as before, just tighter. The duplicate-cluster bars pin their
Merge / Disambiguate / Keep separate buttons to the right edge, the AI-agent
buttons sit in a labelled "AI AGENTS — propose → you apply" group, and a
collapsed **"How to review — the working order"** panel at the top walks the
steward through Prune → Resolve duplicates → Enrich & QA → Name → Govern.

### Fixed — "Add to glossary" no longer discards colliding terms' sources
Both UIs deduped an add-scan on the legacy `Category|Term` key by *skipping*
any row whose key already existed, so scanning a second source with the same
schema reported nothing but dups and silently threw away its columns and
evidence. Collisions now **merge instead of vanish** — the existing term keeps
the steward's edits and gains the new source's `Source_Column` path(s),
per-source ratings / keys / DQ dimensions, the higher rating and any missing
value-pattern evidence (the same fold the scanner itself applies within one
scan). Distinct terms append exactly as before, and the Connect-card status
now says how many existing terms absorbed the new source.

### Added — Schema ER diagram; drag-and-drop DDL
The Schema page gains a Cards | ER diagram toggle (ER by default when
relationships exist): compact table nodes with PK/FK rows, bezier edges
from FK column to referenced PK with arrowheads and labels, layered
auto-layout (hubs left, dependents right, orphans below, barycenter
crossing reduction), pan/zoom/node-drag and a Re-arrange reset. The
"diagram a CREATE TABLE script" panel is now a drag-and-drop zone
(.sql/.ddl/.txt, click-to-browse, auto-runs Diagram SQL) with paste
preserved.

## [1.10.2] — 2026-07-17

### Fixed — PDC dot now lights after a bulk-load run
The sidebar's PDC connection indicator only listened to the Apply page's
Get-token and the Harvest panel's reads — connecting via the bulk loader
(the most common first contact) left it on "not connected". A real
(non-dry) bulk-load run now sets the session too.

## [1.10.1] — 2026-07-17

### Removed — the bulk-load Sample CSV link
The Connect page's bulk loader no longer offers the "Sample CSV" download:
its placeholder rows (`db-host`, port 5432) were one careless click away
from becoming broken PDC data sources — exactly what happened in the lab
(a failed Operations_DB metadata ingest on `UnknownHostException: db-host`).
The scenario's real `datasources.csv` (installed by the bootstrap) is the
documented path; the backend sample endpoint remains for the curious.

## [1.10.0] — 2026-07-17

### Changed — React UI port (architectural)

- **Web layer rebuilt on the shared Policy kit**: the legacy Jinja shell + numbered
  plain scripts get a **React 18 (Vite) frontend** (`frontend/`) on the same design
  system as the Policy Generator — sidebar shell with version pill and LLM status,
  Connect → Review → Govern → Apply stepper, four color themes, `/api/*` contract
  unchanged route-for-route. Page by page:
  - **Home** — workflow tiles, the full working cycle, saved-glossary list (click to load).
  - **Connect** — bulk-load into PDC, PDC harvest, per-source connections, scan &
    add-to-glossary, discovery panel.
  - **Review** — the full review grid with inline editing, filters, duplicate advisor,
    and the AI agents (Enrich / AI suggest / AI QA / AI categorize / Suggest tags)
    upgraded to **propose-then-apply**: every AI pass renders a diff the steward
    applies or discards, instead of mutating the grid in place.
  - **Dictionary** — governed Terms/Tags/Rules vocabulary, pending steward review,
    facet preview, fold advisor, domain-pack export.
  - **Govern** — Keycloak roster fetch, function toggles, expertise + auto-assign,
    stewardship defaults and per-category overrides; the built governance now lives
    in the **shared workspace** (autosaved under the legacy `governance` key, restored
    on load) and generation moved to Apply — Govern keeps a pointer.
  - **Apply** — Generate JSONL (+ Registry, with the workspace's governance baked in),
    draft policies, PDC connection, Data Elements, Resolve, dry-run Apply, profiling
    and app-vs-PDC compare.
  - **Settings** — state snapshot, LLM/hardware detection, drivers, appearance.
- **Long work is jobs, not streams**: the React pages drive `POST /api/jobs/*` +
  polling (`resolve-terms`, `apply-to-pdc`, `bulk-load`, `pull-model`); the SSE/NDJSON
  twins remain for the legacy UI.
- **Legacy UI retained as the fallback**: `api.py` serves `frontend/dist` at `/` when
  it exists (the PDC-Demo installer builds it; manual `npm run build`), else the Jinja
  shell — launchers (`run.sh` / `run.ps1`) now say which UI you're getting. The legacy
  shell stays until a removal release.
- **Suite shell uniformity**: the sidebar restructured to the canonical PDC suite
  shell shared with Catalog Insights and the Policy Generator — brand block (rounded
  app mark + two-line name + version chip with the what's-new/stale-build modal),
  Home + WORKFLOW / GOVERNANCE / CONFIGURE nav sections with inline SVG icons, a
  breadcrumb topbar, footer LLM status dot + theme select, Settings on the shared
  two-column card grid — and the default theme is now **light**.
- **Schema and Files split out of Connect** as indented sub-pages: the schema
  browser (PK/FK badges, table inspector, apply-keys dry-run) and the MinIO/S3
  object browser (folder breadcrumbs, previews, downloads) are now their own
  pages, shown as Connect's children in the sidebar with a
  Workflow / Connect / Schema-style breadcrumb; the stepper keeps Connect active
  on both.

## [1.9.2] — 2026-07-17

### Changed — Windows-first install docs; Insights port
Docs-only release. The README's one-command install now leads with the
Windows 11 host bootstrap (the standard topology — apps on the host, lab +
PDC on the VM) with the Lab VM path second. Sibling-app port references
updated for Catalog Insights' move to **5002** (`.env.example`, REVIEW.md).
No code changes.

## [1.9.1] — 2026-07-17

### Fixed — documentation caught up with the 1.9.0 port
Docs-only release. REVIEW.md's framework-decision section, written when the
FastAPI migration was evaluated and deferred (2026-07-10), now records the
honest history — deferred then, shipped in 1.9.0 — and its refactoring
notes point at `api.py` instead of the removed `app.py`. REFERENCE.md's
layout and repository manifest now show the repo-root `pdc_client/` package
with the `pdc_api.py` shim, list the docs that actually exist, and drop the
last stray "Flask" wordings. No code changes.

## [1.9.0] — 2026-07-17

### Changed — Flask → FastAPI (the Policy Generator port pattern, applied)
The backend is now **FastAPI** (`api.py`), ported route-for-route from the
Flask `app.py` — all 76 endpoints keep their exact request/response contract
(including the `{"error": ...}` payload shape and the SSE/NDJSON streaming
endpoints, now served via `StreamingResponse`), so the existing UI runs
unchanged. Verified by a side-by-side parity run against the old Flask app
before its removal. What the port adds:

- **Interactive API docs** at `/docs` (Swagger UI) over the entire API.
- **Start/poll job endpoints** (`POST /api/jobs/{resolve-terms, apply-to-pdc,
  bulk-load, pull-model}` → poll `GET /api/jobs/{id}`) — additive twins of the
  streaming endpoints and the forward path for the upcoming React UI.
- **`GET /api/detect`** — host detection (RAM, NVIDIA VRAM aggregated across
  GPUs, `OLLAMA_*` env) plus a model recommendation sized to the hardware;
  multi-GPU rigs get `OLLAMA_SCHED_SPREAD=1` suggested (new `llm_detect.py`,
  adapted from Migration Copilot's proven detection module).
- Launchers boot **uvicorn** (`run.sh` / `run.ps1` / `run.bat`, same ports,
  same flags); `gunicorn` and Flask dropped from requirements, `fastapi`,
  `uvicorn`, `jinja2` and `httpx` added.

### Changed — shared PDC client extracted (`pdc_client/`)
The `pdc_api/` package moved to the repo root as **`pdc_client`** — a
stdlib-only, self-contained PDC Public API client that sibling apps (Policy
Generator next) can share. `import pdc_api` still works via a thin shim, so
nothing else changed; `/api/source` still serves the client modules under
their familiar `pdc_api/*` names.

### Changed — selftests → pytest
`selftest.py` (53 engine/endpoint checks) and `v3_selftest.py` (34 PDC v3
shape checks) are ported to **pytest** under `glossary_generator/tests/`
(`pytest -q` from the app folder), joined by a docs-consistency test that
fails the suite when VERSION, the changelog head and the README version
stamp drift apart. The endpoint checks now run through FastAPI's TestClient.

### Changed — llm.py transport
The hand-rolled `urllib` Ollama calls are replaced with `httpx` (same
behavior, HTTP errors still fall back safely); the public surface of
`llm.py` is unchanged.

### Removed
- `app.py`, `selftest.py`, `v3_selftest.py` (ported as above).
- Docker deployment (`Dockerfile`, `docker-compose.yml`) — the app installs
  natively on Windows 11 / macOS and on the Ubuntu 24.04 training VM via
  `install-pdc-demo.sh`; a container path is no longer maintained.

## [1.8.29] — 2026-07-16

### Added — glossary autosave (save once, it stays saved)
The working grid lived only in the browser between explicit saves — close
the browser with unsaved review work and it was gone (the 3-second session
snapshot survives refreshes, not restarts). Now, once a glossary has been
saved or loaded (so a workspace exists), the app autosaves changes to that
same workspace every 30 seconds and on page close — rows, governance and
discovery, with a quiet "autosaved HH:MM" hint. It never invents a
workspace: the first Save glossary is still the steward's explicit act;
after that, the workspace tracks the work. Combined with auto-resume,
"save early, then forget saving exists" is now the workflow.

## [1.8.28] — 2026-07-15

### Added — Fold all (high-confidence) on the AI fold advisor
One click folds every HIGH-confidence pair (identical after abbreviation
expansion) into its canonical term — one audit entry per fold, durable
aliases. Review-band suggestions are never included, and the confirm
reminds you to dismiss any pair whose canonical spelling looks wrong
before running (the advisor picks the unabbreviated name, which on an
uncurated vocabulary can itself be junk — e.g. "Merchant Category Code
Code").

## [1.8.27] — 2026-07-15

### Added — AI fold advisor over the governed vocabulary
The near-duplicate intelligence only ever ran over PENDING items — twins
that both got approved (or arrived via the pack) had no advisor, leaving
the steward to eyeball the Terms table. **AI fold advisor** (Terms header,
Dictionary page) now scores the governed company terms pairwise: names are
token-expanded through the pack's abbreviations (mbr → Member) and compared
by normalized edit distance — identical expansions are a high-confidence
fold, ≥85% is flagged for review. The unabbreviated spelling is proposed
as the canonical (tie-break: reviewed usage, then length). Each proposal
is one click to fold (durable alias, audit-logged) or dismiss.

### Added — "show N rows" on the vocabulary tables
The Terms/Tags/Rules tables were fixed at ~7 visible rows — cramped for an
87-term vocabulary. A selector in the Terms header sets rows-before-scroll
(7/15/30/60) for all three tables, remembered per browser.

## [1.8.26] — 2026-07-15

### Changed — bulk "Retire empty company tags" gated until a scan has run
Right after a (re)seed every usage counter is zero by definition, so the
facet preview offered to bulk-retire the ENTIRE curated allow-list — and
with 1.8.25's durable tombstones a click would have stripped it from the
pack at the next export. The bulk button now appears only once the
dictionary has grown from at least one scan; before that a hint explains
why. Per-item ✕ retire on the tables remains available at all times.

### Added — the working cycle, written down where you work
The exact end-to-end order (scan → review → dictionary → Suggest tags →
govern → save/generate → import → resolve → apply → export pack → commit)
now lives as a collapsible panel on the **Home page**, a pointer on the
Dictionary flywheel note, and a section in GUIDE Part C — including the
nuances that used to be tribal knowledge: Apply-to-this-app IS the reseed,
renames need delete+reimport, zeroed facet counters mean "no scan yet".

## [1.8.25] — 2026-07-15

### Added — steward mistakes are now recoverable in-product
The answer to "an inexperienced steward bulk-approves scan noise — then
what?", which previously had no in-app fix once the noise reached the
pack (the load-merge and Reseed resurrected anything you retired):

- **Durable retire (tombstones).** Rejecting an approved company term or
  tag records a tombstone: the entry stays retired through reloads AND
  Reseeds instead of resurrecting from the pack. A future scan with real
  evidence re-proposes the concept as pending, and approving it lifts
  the tombstone. Alias-folding a pack twin is tombstoned the same way,
  so folds stick. Save dictionary preserves tombstones.
- **Pack removal at export.** Export domain pack lists each tombstoned
  entry still in the installed pack as a conflict row — default REMOVE
  (mirroring the steward's recorded intent), untick to keep. The pack
  stops re-seeding what the steward retired.
- **Per-item undo in the tables.** Approved company terms get ✕ (retire)
  and ⤵ (fold into another term as alias); company tags get ✕ — the
  actions that previously existed only for pending items.
- **The footgun gets a gate.** Approve all now confirms with the count
  and spells out the consequence (approved items govern the Registry and
  reseed every install via the pack) before proceeding.

Selftest grows to 52 with the full tombstone lifecycle (durable through
load-merge + reseed, export removal + override, re-proposal lifting).

## [1.8.24] — 2026-07-15

### Fixed
- **AI buttons stayed greyed after loading a saved glossary.** The LLM
  status check (the only place Enrich / AI suggest / AI QA / AI categorize
  get enabled) re-ran after a scan but NOT after Load saved… /
  auto-resume / Open glossary for review — and boot could race the
  session-grid restore. All three load paths now re-evaluate the buttons
  once rows exist.
- **Pack vocabulary was locked out of steward actions.** `_merge_seed`
  (the load-time heal) relabeled EVERY seed term and tag to the generic
  layer — including the domain pack's — so after Apply + reseed the whole
  curated vocabulary showed "generic" and approve/reject/alias silently
  skipped it. Pack-seeded entries now keep `company/approved` through
  every load; mislabeled dictionaries self-heal on the next read.

- **`python3 selftest.py` works outside the venv.** On the VM the system
  python lacks Flask, which crashed the endpoint section mid-run. The
  selftest now re-execs itself into `.venv`'s python when it finds one
  (so a bare `python3 selftest.py` runs all 47 checks), and with no venv
  it skips just the endpoint section with a note — the 41 engine checks
  still run.

### Changed — Dictionary page reads in workflow order
The main card (was "Tag dictionary" over a Terms table) is now
**Governed vocabulary** with three self-contained numbered groups, each
table with its own add-controls directly beneath it:
**1 · Terms** (aliases fold divergent names) → **2 · Tags** (the
allow-list) → **3 · Rules** — which finally get their own table
(pattern · emitted tags · layer); previously rules were invisible and
their add-fields were jammed onto the end of the tag row.

## [1.8.23] — 2026-07-15

### Added — state snapshot + auto-resume
Two answers to "is my state current next time I run?":

- **It already was, on the same machine** — every state file (settings,
  connections, saved glossaries, dictionary, roster, audit, Registries,
  installed pack) is data-only JSON beside the app; `git pull` never
  touches it and the loaders self-heal older formats across versions.
- **Auto-resume**: the app now remembers the last saved/loaded glossary
  (`settings.last_glossary`) and reopens it on start when the browser
  session has nothing to restore — no more manual "Load saved…" after a
  restart. Save glossary remains the one required click for grid work.
- **State snapshot** (Settings page): download the entire persisted state
  as one zip (with a version-stamped manifest) and restore it — for
  machine moves, wipes, and pre-experiment restore points. Restore
  whitelists known state files only, backs up each overwritten file
  beside itself, and reports a snapshot-vs-running version mismatch.

Also: the source-transparency viewer now lists the six `pdc_api/` package
modules (it still pointed at the pre-split `pdc_api.py`). Selftest grows
to 45 checks with full state-file isolation and a snapshot/restore
round-trip.

## [1.8.22] — 2026-07-15

### Added — live progress on Resolve; the Apply bar stops bouncing
- **Resolve & stamp IDs** now streams a per-term progress bar (new
  `POST /api/resolve-terms-stream`, same SSE worker shape as the apply
  stream; the JSON endpoint remains for fallback). The bar shows
  "Resolving term N of M · <name>" while PDC is searched one term at a
  time — previously the button just sat on "Authenticating and resolving
  terms…" for the whole pass.
- **Fixed-geometry progress bars**: the Apply-to-PDC bar (and the new
  Resolve bar) put the bar FIRST at a fixed 320px with the label after
  it, truncated with an ellipsis — the bar no longer shifts position as
  the column/term name in the label changes length.

## [1.8.21] — 2026-07-15

### Changed — structural pass (no behavior changes)
The feature-freeze housekeeping, in three pieces:

- **Committed offline selftest** (`selftest.py`, 42 checks — no PDC, no
  Ollama, no network, temp-dir state): version-vs-changelog discipline,
  the tagdict lifecycle, the duplicate advisor's evidence rubric, the
  definition linter, the pack merge (conflict defaults + overrides + safe
  unions), policy-draft guard-rails, and the offline endpoints. Run it
  after every VM pull: `python selftest.py`.
- **index.html split** (4,920 → 849 lines): styles to `static/style.css`,
  logic to `static/js/00-bulkload … 12-init` (numbered load order, one
  shared global scope, no build step). Every asset URL carries
  `?v=<version>`, so browser caches bust on release — a stale cached
  script against new endpoints was the classic VM failure mode.
- **`pdc_api.py` → `pdc_api/` package**: core (transport/auth), entities,
  terms, jobs, apply, bulkload — dependency graph verified acyclic,
  import surface identical (`import pdc_api` unchanged everywhere).

Verified end to end: `v3_selftest` 34/34, `selftest` 42/42, `node --check`
on all 13 JS modules, and a headless-Chrome boot smoke test.

## [1.8.20] — 2026-07-15

### Added — progress bar on the pending-terms AI review
**AI review** on the Dictionary page's pending panel now batches the
candidates (10 per request via the new `names` filter on
`POST /api/tagdict/ai-review`) and shows a live progress bar with cancel —
recommendations appear batch by batch instead of the button sitting on
"Reviewing…" for the whole pass. Cancel finishes the current batch and
keeps everything advised so far.

## [1.8.19] — 2026-07-15

### Added — What's new on the version pill
The sidebar version pill is now clickable: it opens a release-notes panel
served by the new `GET /api/whatsnew` (top sections of `docs/CHANGELOG.md`,
read fresh per call). If the changelog's leading version is newer than the
running process's version, the panel flags it in red — the two-second
diagnosis for the recurring "pulled but not restarted / pull didn't land"
stale-deployment confusion. Degrades gracefully where the changelog isn't
shipped (Docker image). Also: an under-the-hood note on the Dictionary
page — "whose scan feeds the pack?" — covering evidence provenance
(PDC scans → app scan → steward review → pack) and the packless bootstrap.

## [1.8.18] — 2026-07-15

### Changed — pack merge: conflicts surface, steward decides
The pack generator's merge no longer silently drops the losing side when the
scan disagrees with the installed pack. Every disagreement is now listed in
the export report (`report.conflicts`: pack value vs scan value vs who won)
and rendered as a checkbox row in the Export dialog — tick to take the
scan's value, untick to keep the pack's; toggling regenerates the pack so
the download and **Apply** always reflect the choices
(`resolutions: {"key::name": "scan"|"pack"}` on `POST /api/export-pack`).

Defaults per key: curation-bearing keys keep the pack's value (a steward's
recorded decision beats the machine's newest opinion); **curated_seeds
prefer the scan** — machine-derived evidence, fresher profiling wins, the
replaced seed stays visible. A sensitivity *loosening* on an existing pack
term is now a reported conflict instead of a silent block; list-valued keys
(category_tags) union instead of conflicting. Docs updated (pack README +
GUIDE Part C), including how to **bootstrap a base pack from nothing**:
run packless, scan + review once — the first export IS the base pack.

## [1.8.17] — 2026-07-14

### Added — the domain pack generator (the loop closes)
A pack seeds the engine; the engine scans and the steward reviews; the new
**Export domain pack** (Dictionary page, `POST /api/export-pack`,
`packgen.py`) exports that reviewed state BACK into pack format — so packs
evolve from real company data instead of staying hand-authored guesses:

- `table_category`/`table_terms` from the reviewed rows' physical tables,
  `cat_keywords` from table tokens, **abbreviations learned by aligning
  column tokens with term words** (`mbr_no` + "Member Number" → `mbr: Member`,
  needs 2+ sightings);
- `category_tags`/`tag_rules`/`extra_tags`/`terms` from the GOVERNED company
  layer of the dictionary (approved only);
- **`curated_seeds` carrying the scan's induced value patterns and profiled
  reference lists per term** — company-specific detection seeds, ready to
  seed the next install and flow to the Policy Generator.

**Merge semantics, never overwrite**: hand-curated entries in the installed
pack always win; learned content fills gaps and adds, and the report counts
the additions per key — review, then commit to the scenario repo.

**Re-merge propagates review improvements** into existing pack terms via
safe unions: aliases and tags union in, sensitivity tightens but never
loosens - curation can be enriched, never removed or weakened
(report: terms_enriched).

**Apply to this app** (one click, confirmed): writes the refreshed pack over
the installed `domain_pack.json` (timestamped backup kept) and reseeds the
dictionary from it — approved company items and rules survive the reseed.
Commit the file to the scenario repo so the next install starts from it.

## [1.8.16] — 2026-07-14

### Added — curated detection seeds (domain pack → Registry)

The domain pack can now carry **`curated_seeds`** — vetted canonical shapes
(SSN, email, phone, ZIP) and reference lists (service cities) for concepts
profiling can't induce. `registry/bridge.py` merges them into the Registry's
`concepts[].detect` at Generate time with `source: "curated"`; profiled
evidence always wins over a curated seed of the same type. This is the
custom-only identification program's replacement for PDC's built-ins: the
seed is versioned in the pack, travels through the Registry with provenance,
and the Policy Generator authors it like any other evidence. The CSCU pack
(PDC-Scenarios) ships six curated seeds as the baseline. Registry selftest
still 13/13.

## [1.8.15] — 2026-07-14

### Fixed — document Data Discovery completes its workflow again
Under API v3 the bulk job endpoint returns **no job id**, so after "Started
Data Discovery…" the status button hid and the step dead-ended — submitted,
never confirmed, no follow-through. The step now watches the **entities
themselves** (each one's `system.profiledAt` flips when its profiling
finishes), which works on every API version:

- pre-submission snapshot travels with the trigger; a new
  `POST /api/discovery-progress` compares live timestamps against it;
- the UI drives the shared progress bar ("PDC Data Discovery — 12/18"),
  polls every 6s up to 10 minutes, Cancel stops watching (the PDC job keeps
  running);
- on completion: "✓ Data Discovery complete — N of N profiled" with the
  next steps (re-pull Data Elements / side-by-side → re-Apply → recalculate
  Trust). Honest timeout message when folders don't report per-entity
  timestamps (check PDC's Workers page).

## [1.8.14] — 2026-07-14

### Resolve — unconfirmed terms surfaced honestly, AI match now reaches them
- With deterministic pre-stamping, links are never "unresolved" — so a term
  PDC could not CONFIRM by name (e.g. a generic single word like "State", or
  a term renamed after import) hid behind a green "fully linked" headline
  while its links quietly fell back to the deterministic import ids. Renamed
  terms would Apply a **dead id**.
- The panel now: states plainly "✓ All N links are bound — ready to Apply",
  lists unconfirmed names in their own amber section with the det-id-fallback
  risk spelled out, and offers **AI match in PDC** for exactly those names
  (binding replaces the deterministic id with PDC's real one). The probe is
  reframed as confirmation diagnostics, collapsed by default.

## [1.8.13] — 2026-07-14

### Resolve — AI matching for outstanding terms, in place
- **"AI match in PDC"** on the unresolved list: terms renamed or
  disambiguated locally AFTER the glossary import used to dead-end at
  "0 hits — go re-import". Now the app harvests candidate TERM entities from
  PDC (token searches), proposes the best name-similarity match (≥78%
  normalized), and lets the local AI adjudicate the rest using each term's
  definition ("Branch Identifier → Branch ID"). One-click **Bind id** (or
  Bind all) stamps the real PDC id + glossaryId into the links — your local
  name stays; no round-trip through the Glossary page or a re-import.
  Endpoint: `POST /api/resolve-fuzzy`. The probe verdict points at the button.

### UX
- **Drafted-policies zip promoted to a primary button** ("Download drafted
  policies (zip)") with a 1-2-3-4 next-steps strip (download → review →
  PDC Data Identification Import → run identification) — it IS the draft
  policy set, so it reads like one now.

### Changed — scenarios carved out into PDC-Scenarios

All per-scenario assets moved to the new
[PDC-Scenarios](https://github.com/jporeilly/PDC-Scenarios) repo:
`data_sources/` (all four verticals **and** the shared lab), `courseware/`
(all sets + the consolidated roster), the `install-scenario` /
`reset-scenario` scripts, and copies of the app diagrams the courseware
builders embed. This repo is now the app only. The scenario scripts were
adapted to discover the app (`GLOSSARY_APP_DIR` or the usual
beside/inside layouts), and PDC-Scenarios' new `select-vertical.sh <ID>`
sparse-pulls a single vertical. Docs swept (README, GUIDE, REFERENCE,
PDC-VM-TROUBLESHOOTING, app README). The Policy Generator's courseware
moved there too (`courseware/CSCU/Policy-Generator/`).

## [1.8.12] — 2026-07-14

### Govern — the roster now drives everything
- **Function toggles on every roster row** (Steward / Owner / Custodian).
  Your setting overrides the Keycloak-derived role and persists with Save
  roster — so Owner is no longer locked to whoever carries the Keycloak
  `data_steward` role (previously only catalog.admin).
- **Defaults populate from the roster.** The defaults-row prefill picks
  role-holders from the effective functions (jordan marked Owner → Owner
  default = jordan; omar marked Custodian → Custodian default = omar). Saved
  defaults still win over the prefill.
- **Functions are exclusive capabilities.** Someone scoped to Custodian only
  (omar) is never selectable — or auto-assigned, even via the expertise-only
  fallback — as Steward or Owner. Every people dropdown (defaults row and all
  per-category overrides) now offers only function-eligible people; unscoped
  people remain available everywhere. Node-tested with the page's real
  functions: pools, prefill, exclusion, unscoped fallback.
- **Domain sets itself from company data.** New ⚡ auto button beside DOMAIN
  (and Set-up-stewardship fills it when unsaved): the installed pack's domain
  key + company name map deterministically (credit_union→Banking,
  healthcare→Healthcare, manufacturing→Manufacturing, retail→E-commerce, …);
  the local AI classifies unmapped businesses from the glossary content
  (guardrail: must be in the PDC domain list). All four scenarios verified
  deterministic; LLM fallback live-tested.

## [1.8.11] — 2026-07-14

### Fixed — Auto-assign routes by expertise again, without trampling defaults
1.8.9's "respect defaults" was too blunt: with defaults set it suppressed ALL
routing (0 slots filled). The rule is now a fair contest, factored into a
pure, unit-tested `slotDecision()`:

- a category override is written only when a candidate's expertise for that
  category **strictly beats the default person's own score** — the rationale
  shows the matched terms and both scores ("matched compliance, aml, kyc —
  beats your default elena ramirez (15.0 vs 0.0)");
- when the default is also the best match (or nothing scores higher), the
  slot stays on *(use default)* with the reason;
- role-only fallbacks never override a default (the original 1.8.9 bug where
  the Owner-role holder swept every category);
- "Set up stewardship" still LLM-generates any missing roster expertise
  first, so the contest runs on real keywords.

Verified with the page's actual functions extracted into a node harness:
expertise override, default-holds, tie, and no-default cases all pass.

## [1.8.10] — 2026-07-14

### Pending steward review — context, junk control, and an AI reviewer
- **Pending terms now show what a steward needs to decide**: the category the
  scan saw, sensitivity (color-coded), confidence, tags, the source columns/
  files it appeared in, and the captured definition — no more bare name chips.
- **Scan noise never enters.** Synthetic names from headerless CSVs
  (`Column-0…N`, `Field-N`, `Unnamed-N`) are blocked at accretion AND healed
  out of existing pending lists on next start (approved items untouched).
- **AI review button**: a deterministic near-duplicate pass against the
  governed vocabulary first (normalized name match ≥85% — "Dividend Rates" vs
  "Dividend Rate"), then the local AI judges the rest from the captured
  context: **Approve / Reject / Alias of <term>** with a rationale. Advice
  only — and a one-click **→ alias** action folds a duplicate into the
  governed term as an alias (new `alias` review action, audit-logged).

## [1.8.9] — 2026-07-14

### UX
- **All summary metrics color-coded.** PII count red; Confidence H red /
  M orange / L blue (matching the Sensitivity mapping, per user preference);
  Sensitivity HIGH/MED/LOW red/orange/blue (from 1.8.8).
- **Definition QA bulk actions.** The QA panel gains per-row checkboxes with
  Select/deselect all, plus **Use selected suggestions** and **Dismiss
  selected** — resolve a whole QA run in two clicks.

### Fixed — stewardship defaults now mean what they say
- **Auto-assign respects explicit defaults.** It used to fill every category's
  steward/owner/custodian override from roster roles + expertise — so a
  default like *Owner: elena ramirez* was silently shadowed by the Owner-role
  holder (catalog admin) in all categories. With the new **respect defaults**
  toggle (on by default), any slot that has an explicit default stays on
  *(use default)* everywhere; re-running Auto-assign also clears its earlier
  auto-fills on those slots. The rationale panel shows "left on your default —
  <name>". Untick to restore full expertise routing.
- **Defaults persist.** The whole defaults block (steward, owner, custodian,
  status, domain, rating, reviewed date, apply-to-categories, stakeholders)
  now saves to settings.json — automatically on change, and via the new
  **Save defaults** button — and restores on every restart, beating the
  role-based prefill.

## [1.8.8] — 2026-07-13

### UX
- **Progress bars for every agent pass.** AI QA definitions, AI categorize and
  AI suggest (evidence) now drive the same progress bar as Enrich — percentage,
  N/total, and a working **Cancel** that finishes the current batch and keeps
  what's already applied. AI categorize is now chunked (6 rows per call) so its
  progress is real; the whole glossary's category list travels with every chunk
  so each slice picks from the same known set.
- **Sensitivity counts are color-coded** wherever the HIGH/MED/LOW rollup
  appears (summary chip, scan/build checks): HIGH red, MED orange, LOW blue.

## [1.8.7] — 2026-07-13

### PDC 11 / API v3 — full audit, two fixes, a committed shape test
- **Audited every endpoint against the official v3 OpenAPI specs** (auth,
  search, entities get/patch/filter, profiling-info, jobs, data-sources).
  Verdict table in docs/REVIEW.md §1. New **`v3_selftest.py`**
  (`python -m v3_selftest`, 34 checks) validates every request builder against
  the strict v3 whitelists — the entity PATCH is `additionalProperties: false`
  at every level, so an unknown key is a 400.
- **Fixed: filter pagination cursor** was sent in the request body; v2/v3
  define it as a query parameter. Harmless on lab-size catalogs (one page),
  but would re-fetch page 1 forever on >500 entities.
- **Improved: v3 job execution goes straight to `/jobs/execute/bulk`** — v3
  has no per-job endpoints, so the old try-individual-first adapter burned a
  guaranteed 404 per job call. v1/v2 behavior unchanged.
- **v3 is now the default API version** for new installs (saved selections
  preserved); selector tooltips explain the versions.

### Docs consolidated (9 files -> 5)
- `GUIDE.md` is now THE manual — it absorbed `CHALLENGE-AND-GOAL.md` (Part A:
  the why), `INSTALL.md` (Part B: install & set up, refreshed to 1.8.x), and
  the still-current operating notes from `SUPPLEMENT.md` (Part D: run order,
  identify-once lifecycle, tag-array write semantics). `REFERENCE.md` absorbed
  `MANIFEST.md` (repository manifest section, file list refreshed). The four
  merged files are deleted; every cross-reference repointed. `CHANGELOG.md`,
  `REVIEW.md` and `PDC-VM-TROUBLESHOOTING.md` remain separate on purpose
  (release history, engineering audit, VM platform ops).

### Also
- **Build check names every offender, clickable.** The duplicated/repeated/
  no-definition/no-category term lists are no longer truncated text — each
  term is a chip that jumps the review grid straight to it (filter + scroll),
  so you can resolve the last few without hunting through the glossary.

## [1.8.6] — 2026-07-13

### Added — Apply fills the canvas (descriptions, table terms, roll-ups)
Fixes the "everything is blank in PDC" niggles: folders/tables with no
description, sensitivity, rating, or terms after Apply.

- **Entity descriptions.** Apply now writes each entity's description from the
  steward's reviewed definition (`attributes.info.description`) — columns,
  files, and tables. New Apply option: **fill empty** (default — never touches
  a description someone already wrote in PDC), **overwrite**, or **don't
  write**.
- **Table terms auto-link.** The table-level record terms ("Member Account
  Record", …) used to say *link by hand*; the table roll-up now binds each
  table's own businessTerm (deterministic id + glossaryId, so it's
  glossary-bound after import) plus the term's definition as the table
  description. That is the table Trust Score's assigned-term input, automated.
- **Table sensitivity roll-up.** Tables get `sensitivity` = the max of their
  columns' applied sensitivity (no more "Unknown Sensitivity" on tables whose
  columns are HIGH).
- **Folder roll-ups.** Object-store folders — previously "nothing to roll up"
  — now receive mean rating, mean DQ and max sensitivity from their files.
  Trust Score stays per file (PDC computes it for tables and files only);
  folders never take terms or join the trust scope.
- The "Rate tables & columns" toggle is now **"Roll up to tables & folders
  (rating, sensitivity, table term)"** and governs all of the above.

## [1.8.5] — 2026-07-13

### Improved — Generate & apply UX
- **The JSONL download is now unmissable.** Generate's result renders a solid
  "Download glossary JSONL" button plus a 1-2-3-4 next-steps strip (Download →
  PDC Import → Resolve Term IDs → Apply) with the warning that the PDC import
  is what mints the term ids — nothing binds without it.

### Improved — policy drafter coverage & transparency
- **Canonical fallback seeds.** Shapes that can never be position-induced from
  samples now draft anyway, double-gated on column name AND PII class: email
  columns (`CONTACT_INFO`) get the classic email regex + `aaaa@aaaa.aaa`
  content pattern; SSN columns (`GOVERNMENT_ID`) get `^\d{3}-\d{2}-\d{4}$`.
  Marked "(canonical shape)" in the panel; profiled evidence still wins when
  present.
- **Precise skip reasons, visible.** "96 skipped — no seed" is now an
  expandable list stating *why* per term: table-level term (no column),
  document term (identify documents with vocabulary dictionaries), no stable
  shape in the data (free text / names / amounts — expected), or **no profiled
  evidence on the row** — the tell that a glossary predates 1.8.0 evidence
  capture and needs a re-scan.
- The draft summary explains that skipped terms are normal, not failures.

## [1.8.4] — 2026-07-13

### Fixed
- **LLM language drift.** Multilingual models (qwen2.5 et al.) could answer in
  Chinese mid-batch, overwriting English definitions. Every prompt now pins
  English output AND a language guardrail discards any non-Latin proposal
  (definitions, names, QA rewrites, rationales) before it touches a row —
  re-running Enrich rewrites previously drifted text back to English.

### Added — the agent build-out (three new AI agents, all guardrailed)
- **Policy drafter** (`policy_draft.py`, `POST /api/draft-policies`, "Draft
  policies (AI)" on the Govern page): the Policy Generator's first working
  mile. Every kept term with a detection seed becomes a ready-to-import PDC
  Data Identification rule in the Technical-Track shapes — an induced value
  regex becomes a **Data Pattern** (`patternsRules` JSON with column-name
  hints, content pattern + regex, TT-standard weights/thresholds), a profiled
  reference list becomes a **Dictionary** (`dictionariesRules` JSON + values
  CSV). Deterministic core; the AI agent polishes each rule's column-name
  regex and tag pick (guardrails: regex must compile, tags stay governed).
  One zip download (Patterns/, Dictionaries/, INDEX.csv); drafts only —
  review, then import in PDC.
- **Definition QA agent** (`defqa.py` + `llm.qa_definitions_rows`,
  `POST /api/qa-definitions`, "AI QA definitions" button): a deterministic
  linter (circular, echoed, vague, too-short, copy-paste-duplicate
  definitions — works offline) plus the LLM judging whether each definition
  actually explains the business meaning, with a proposed better sentence.
  Flags land as `QA_Issues`/`QA_Suggestion`; a review panel lists them with
  one-click "Use suggestion" — nothing applies itself.
- **Category assignment agent** (`llm.categorize_rows`,
  `POST /api/ai-categorize`, "AI categorize" button): files uncategorized
  terms into the known categories (domain pack + in-use); off-list answers
  are discarded.
- All three verified live against qwen2.5:14b-instruct alongside the 1.8.3
  adjudicator; every agent degrades gracefully when Ollama is offline.

## [1.8.3] — 2026-07-13

### Added
- **Merge / Disambiguate / Keep separate decision aid.** The duplicate-group
  headers in the review grid now carry a *recommendation* with its reason, and
  the matching action is pre-highlighted (hints only — the steward still
  clicks). Three-stage escalation ladder, cheapest first:
  1. **Cached scan evidence** (`similarity.recommend_groups`): FK links between
     the columns (same concept by construction), profiled reference-value
     overlap, induced value formats/signatures, PII class. Runs automatically
     (debounced) whenever the duplicate groups change. Rubric: evidence-same →
     Merge; evidence-different → Disambiguate when the members share a category
     (import collides there) or Keep separate across categories; no evidence →
     weak Merge on matching context.
  2. **Live data-value probe** (`suggester.sample_distinct_values`): for groups
     the cached evidence can't settle, sample distinct values from each member
     column over the active database connection and compare the actual
     populations (containment ≥60% → same; zero overlap → different).
  3. **AI adjudicator** (`llm.adjudicate_groups`): a local-LLM agent weighs the
     definitions + evidence side by side for whatever is still ambiguous and
     proposes one of the three actions with a rationale (guardrailed to those
     actions; marked "AI" in the hint).
  Stages 2–3 run from the new **AI advise** button; endpoint
  `POST /api/recommend-resolutions`.
- **Find similar knows the data now.** `/api/similarity` rolls up each term's
  scan evidence; a shape match lifts a pair straight to the strong band, and a
  shape **conflict** ("Card Number" vs "Care Number" with different formats)
  is flagged *different concepts* with the merge button withheld.
- **Pentaho blue theme.** Settings → Theme gains a "Pentaho blue" option —
  PDC's deep navy chrome with the bright action blue.

## [1.8.2] — 2026-07-13

### Added
- **PK/FK facts flow to PDC and the Registry.** The scan has always detected
  primary/foreign keys (DDL parsing, Postgres `pg_catalog`, Oracle
  `all_constraints`) for the schema diagram — now the facts are carried, not
  dropped:
  - Review rows record `Source_Keys` per physical column
    (`{pk, fk, ref: "table.column"}`), surviving term merges and save/load.
  - **Apply to PDC** PATCHes them onto each key column as
    `attributes.extended.{isPrimaryKey, isForeignKey, references}`. Note:
    PDC's built-in *Is Primary Key / Is Foreign Key* properties live under
    `metadata.column.*`, which is harvest-owned — the public API's PATCH
    schema (v1–v3, `additionalProperties: false`) rejects it, so those
    built-ins can only be set by PDC's own Metadata Ingest. `extended` is
    the API's writable free-form block and is where the app's detection
    lands (visible on the entity, merge-safe with existing extended keys).
  - **Registry concepts** gain a `keys` map (per source column), giving the
    Policy Generator relationship context: which columns are identity vs
    reference joins.

## [1.8.1] — 2026-07-13

### Changed
- **Tags standardised to lower-case, everywhere.** Tags are facet keys in PDC's
  OpenSearch — `PII` and `pii` would fragment into two buckets — so the whole
  pipeline now emits and stores one canonical form: trimmed lower-case
  (`pii`, `cde`, `financial`, …). Display labels keep their casing (the tag
  `pii` still shows the label "PII").
  - **Dictionary boundary** (`tagdict.py`): a normalization pass runs at
    seed/load/steward-save/accretion, folding tag keys, rule tags, category
    tags and term tags; case-variant duplicates merge (counts summed,
    sensitivity floors tightened, generic layer wins). An existing pre-1.8.1
    `tag_dictionary.json` **heals itself on next app start — no reseed needed**.
  - **Emitters**: name-rule tags (`PII`→`pii`, `Financial`→`financial`),
    document-classification tags, `suggest_tags()` output, the Registry
    bridge (`pii` forced by a PII category), the AI evidence pass (governed
    tags now append lower-case), the PDC glossary JSONL export, and tags
    ingested back from PDC entities.
  - **Scenario assets swept**: all four domain packs (+ re-zipped), the four
    W03 Business-Glossary JSONL imports, the four W05 flat CSVs, and the CSCU
    Technical-Track pattern/dictionary JSONs (applyTags fold to lower-case;
    business-term assignments keep Title Case — terms aren't tags) with the
    lab guide + docx rebuilt to match.
  - Registry selftest expectations updated (13/13 pass).

## [1.8.0] — 2026-07-10

Evidence-grounded suggestion: the scan now LEARNS value formats from the data,
the AI can reason over that evidence, and the Registry hands the Policy
Generator ready-made detection seeds.

### Added
- **Pattern induction from profiled data.** When >=90% of a column's sampled
  values share one position signature (e.g. `AAA-nnnnn` for `CPC-84120`), the
  scan derives an anchored regex (`^CPC-\d{5}$`) — stable literal prefixes are
  kept verbatim, the rest generalizes by character class. Enum detection now
  keeps up to 12 reference values. Review rows carry the evidence as
  `Value_Signature`, `Value_Pattern` and `Enum_Values` (kept across merges).
- **Registry `detect` seeds.** Each exported concept now carries its scan
  evidence — `{type: pattern, regex, signature}` and/or
  `{type: dictionary, values}` — so the Policy Generator can author the Data
  Pattern / Dictionary for a term directly from the profiled data behind it
  ("this Term is based on this pattern / dictionary").
- **AI suggest (evidence)** — `POST /api/ai-suggest` + a Review-page button.
  The local model reads each row's scan evidence and proposes the business
  term (surfaced as a suggestion chip, never overwriting the steward's Term),
  governed tags and sensitivity — under guardrails: tags filtered to the
  governed allow-list, sensitivity tighten-only, category only from the known
  set, rationale appended to Suggested_Reason. Warm-up call absorbs cold model
  loads that outlive LLM_TIMEOUT.
- **PDC v3 job adapter.** Job execution (calculate-trust-score,
  data-discovery, test-connection, metadata ingest) now tries the individual
  endpoint and, under v3, falls back to `POST /jobs/execute/bulk` with the
  named-job payload on 404/405 — closing the one v3 gap called out in
  REVIEW.md section 1. v1/v2 behaviour unchanged.

### Fixed
- Bulk-load CSV textarea no longer soft-wraps long rows over each other
  (one record per line, horizontal scroll).
- The connection cards' Delete button is now visibly red (its style referenced
  an undefined CSS variable) and asks for confirmation before removing.

### Changed
- `install-scenario.*` also installs the scenario's bulk-load CSV as
  `glossary_generator/datasources.csv` and retargets env-pinned
  `GLOSSARY_DOMAIN_PACK` / `GLOSSARY_PEOPLE_SEED` to the selected scenario;
  `reset-scenario.*` removes/comments them.

## [1.7.2] — 2026-07-08

The CSCU-only release: the Arizona Water Company scenario was removed from
the repository (data_sources/AWC, courseware/AWC and the AWC domain pack).

### Changed
- **All documentation swept to CSCU-only** — root README, data_sources and
  courseware indexes, lab README/compose/loader comments, GUIDE, INSTALL,
  MANIFEST, REFERENCE, SUPPLEMENT, domain-pack README. The shared lab and the
  scenario plug-in model are unchanged: additional scenarios (a Retail
  scenario is planned next) drop in as `data_sources/<ID>/` + `courseware/<ID>/`
  folders with a `scenario.json`.
- **lab-setup.docx rebuilt CSCU-only** with two embedded diagrams (lab
  topology; shared-stack model), sourced from `data_sources/lab/diagrams/`
  (PNG + SVG).

## [1.7.1] — 2026-07-08

### Added
- **Shared demo lab** (`data_sources/lab/`) — ONE PostgreSQL + ONE MinIO for
  all scenarios. `load-scenario.sh` (wrapped by `make load SCENARIO=<ID>`)
  creates the scenario's own database (`awc_operations` / `cscu_core`),
  runs its `postgres-init/*.sql`, creates its bucket (`awc-documents` /
  `cscu-documents`) + read-only user, uploads the documents, and verifies
  counts — scenarios coexist with no port conflicts, and every documented
  connection value is unchanged. Scenario discovery is data-driven from
  each folder's `scenario.json` (extended with database/schema/bucket keys),
  so new scenarios need no script changes. The per-scenario standalone
  stacks were **removed** — scenario folders are data-only; the shared lab
  is the single way to stand the sources up.
- **CSCU courseware Workshops 00–05** under `courseware/CSCU/` (Preflight →
  Data Identification): per-workshop READMEs, markdown guide masters with
  `[SCREENSHOT]` markers, and generated assets — users, glossary JSONL
  (123 records), term-linking map, metadata dictionary, six business rules
  (flagship marketing-opt-out + PCI no-stored-CVV), two custom dictionaries.
  The full original AWC 11-workshop course is archived under `courseware/AWC/`.
- **Windows-host topology sections** in both lab READMEs: app on Windows 11,
  PostgreSQL/MinIO/PDC in the Ubuntu 24.04 VM at 192.168.1.200
  (`https://pentaho.io`) — per-vantage-point connection tables, ufw and
  hosts-file setup, reachability checks.

### Changed
- All docs (root README, data_sources index, workshop guides, installer
  next-steps) now present the shared lab as the recommended path.
- The CSCU compliance steward was renamed **Nadia Flores** (was Priya Nair,
  which collided with the AWC course's Data Analyst persona).

## [1.7.0] — 2026-07-08

The two-scenario release: the app is now fully **scenario-generic**, and each
training scenario ships as a complete, separated, installable bundle.

### Added
- **Copper State Credit Union (CSCU) scenario** — a fictional Arizona credit
  union replaces Arizona Water Company as the primary workshop. New under
  `data_sources/CSCU/`: a self-verifying lab stack (docker-compose + Makefile,
  mirroring the AWC kit) with an 11-table `cscu_core` core-banking schema
  (members, accounts, cards, transactions, loans, ACH, KYC, SARs, GL — column
  comments, views, and a planted `cards.cvv_cd` PCI-DSS violation for the
  governance exercise), an 18-file `cscu-documents` MinIO bucket (SAR/PCI/NCUA
  compliance PDFs, loan-application and correspondence DOCX, statements/rates
  CSV, ACH JSON — all tied to the database rows so one story spans both
  sources), the `credit_union` domain pack + steward roster, a bulk-load CSV,
  and a ready-to-install `cscu-domain-pack.zip`.
- **Scenario installer / reset scripts.** `install-scenario.sh` / `.ps1` lists
  the scenarios found under `data_sources/` (via each folder's `scenario.json`
  manifest), and installs the selected one into the app's git-ignored runtime
  config (`domain_pack.json`, `people.json`, `GLOSSARY_COMPANY` in `.env`,
  dictionary reseed) — the app tree itself stays clean. `reset-scenario.sh` /
  `.ps1` undoes it (`--all`/`-All` for a full runtime reset). Everything is
  backed up with timestamps before being touched.
- **CSCU courseware set** under `courseware/CSCU/`: a markdown-first workshop
  guide plus the three topic notes rewritten for the credit-union scenario.

### Changed
- **Everything scenario-scoped is now separated.** The AWC water-utility
  scenario moved intact into `data_sources/AWC/` (lab stack, documents, domain
  pack + `awc-domain-pack.zip`, datasources CSV) and `courseware/AWC/` (the
  original .docx guide, .pptx deck and topic notes, restored to their AWC
  content). The app ships with **no** scenario pack; `domain_pack.json` is now
  a git-ignored runtime file created by the installer.
- **Documentation moved to `docs/`** at the repo root (the app README became
  `docs/REFERENCE.md`; a slim navigation README remains in the app folder),
  and all docs were updated for the CSCU scenario and the new layout.
- **Generic tag baseline is now actually generic.** The water-utility items
  that had leaked into `tagdict.py`'s generic seed (water-quality/water-system
  tags, categories and rules) moved into the AWC domain pack; the default
  dictionary domain is `generic`.

## [1.6.20] — 2026-07-07

The workflow release: the Dictionary takes its real place in the flow (nav, stepper,
Home guidance), the review grid survives a reload, all four database drivers ship by
default, and the launchers identify themselves.

### Added
- **"→ Connection" on the Harvest from PDC picker — PDC source becomes an app
  connection.** For a direct live scan of a source PDC already knows, you no longer
  retype anything: the button reads the full record over `/data-sources/filter`
  (`get_data_source`) and saves a prefilled app connection — engine (mapped from
  `databaseType`: POSTGRES/MYSQL/ORACLE/MSSQL → db, AWS/MinIO → object store),
  host, port, database, first schema, user / endpoint, bucket, access key, prefix.
  The one thing the public API never returns is the secret, so the connection is
  saved needing only the password (or secret key) set once on Connections.
  Re-adding an existing connection refreshes the prefill but **keeps a saved
  secret**. A reachability heuristic warns when PDC's stored host looks
  container-internal (e.g. `az-water-postgres`) and points at the host-IP +
  published-port remap. Lookup is by **resource name** — the data-sources filter's
  `ids` field wants PDC's internal ObjectId, and sending the picker's catalog-entity
  UUID 500s with "Cast to ObjectId failed" (found live; name is the reliable key).
  The button only shows on RESOURCE roots — schema roots aren't data sources. Unsupported types (Azure Blob) get a clear "use Harvest
  instead" message. Complements — not replaces — the two existing lanes: Harvest
  (PDC→terms, no connection) and the bulk loader (CSV→PDC).
- **Harvest now shows PDC's scan & discovery results, not just the terms.** The
  harvest call always read what PDC's own processing had produced (sensitivity,
  trust, term links) but only reported a term count. Each harvested source now
  renders a **"PDC scan & discovery results"** card: ingested tables/columns (or
  files), **identified** count with the sensitivity distribution (H/M/L), and
  **trust-scored / term-linked / tagged** coverage — plus a hint when 0 identified
  means Profiling / Data Identification hasn't run on that source yet. Works in
  both the single-source and multi-select harvest; the per-row "in PDC" badges on
  the grid are unchanged. (`summary.governance` from `harvest_from_catalog`,
  `pdc_summary` in the `/api/pdc/harvest` response.)
- **All four database drivers install by default.** `pymssql`, `pymysql` and
  `oracledb` (thin mode — no Oracle client needed) moved from commented-out
  optional lines to first-class entries in `requirements.txt`, alongside
  `psycopg2-binary`. The Drivers panel now confirms status rather than gating
  setup; `run.sh`/`run.ps1` pick the change up automatically (requirements hash).
- **Oracle is a first-class engine in both lanes.** Live scan: `harvest_live`
  gains an Oracle branch (`ALL_TAB_COLUMNS` / `ALL_CONSTRAINTS` position-aligned
  PK+FK / `ALL_COL_COMMENTS`, keyword binds, recycle-bin and `$`-objects skipped;
  schema = owner, defaulting to the connecting user uppercased). Test Connection
  falls back to `dual` when `v$version` isn't granted, so least-privilege accounts
  don't false-fail. Bulk loader: new `kind=oracle` (`databaseType="ORACLE"`,
  host/port 1521/databaseName/credentials, `driverClassName` defaulting to
  `oracle.jdbc.OracleDriver`, `schemaNames`); the CSV row also maps to an app-side
  live connection. **PDC prerequisite:** upload `ojdbc11.jar` via Manage Drivers
  first — PDC ships no Oracle JDBC driver, and the create/test fails without it.
  `databaseType="ORACLE"` follows the POSTGRES/MYSQL convention but is the one
  value not yet verified against a live create — if it 400s, inspect a UI-created
  Oracle source (same discovery path that established `databaseType="AWS"`).
- **The review grid survives a reload.** The grid was in-memory only, so a
  browser refresh or accidental navigation lost all unsaved review work. It now
  autosaves to sessionStorage (same tab, every 3s + on unload) and restores on
  boot with a "restored — unsaved" notice. **Save glossary** remains the durable
  checkpoint.

### Fixed
- **Reseed no longer destroys the approved vocabulary.** `Reseed` wiped the whole
  dictionary — including steward-APPROVED company terms/tags — contradicting the
  documented contract ("discards un-approved scan-grown additions; approved/
  steward items are the governed set") and silently erasing an approval session.
  Reseed now preserves approved company items and company-layer rules, discards
  pending items, writes a **timestamped backup** of the previous dictionary file
  first, reports what it kept (UI message + audit detail), and the confirm/tooltip
  say exactly that. `reset(preserve_approved=False)` keeps the full-wipe path.
- **Harvest grows the vocabulary.** `/api/pdc/harvest` now accretes harvested rows
  into the dictionary (`source="pdc"`) like direct db/minio scans do — a
  harvest-only workflow reaches the pending→approve flow, and re-harvesting is a
  recovery path that repopulates the pending queue after a reseed without direct
  DB/S3 access.
- **Merge / Disambiguate work in either order around Enrich.** The enrich handler
  replaces each row with the server's returned dict; group identity (`_grp`), row
  id, resolution tag and keep state are now explicitly preserved client-side across
  that swap instead of relying on the server echoing them. Combined with the
  live-base fix below, "enrich first, then merge/disambiguate" and "resolve first,
  then enrich" both work — the previous ordering constraint was a symptom, not a
  rule.
- **Merge / Disambiguate clicks actually apply.** Clicking a resolution looked up
  the group's members in the raw-scan snapshot (`_grpEnsureBase` filtered
  `SCAN_SNAPSHOT`), so any group whose key the snapshot never saw — terms renamed
  into a collision, rows appended by a later harvest — resolved to an **empty
  base**: the click threw in the console, nothing moved on the grid, and the empty
  base was cached so retries failed too. Even when it worked, merging pulled
  pre-enrich snapshot rows, silently discarding LLM enrichment for that group.
  The base is now captured from the **live grid** at first action: renamed and
  harvested groups resolve, revert restores exactly what you had (edits and
  enrichment included), a poisoned cache self-heals, and an empty group reports
  "nothing to resolve" instead of throwing.
- **The S3 endpoint scheme and the TLS tick can no longer disagree.** boto3 uses
  the endpoint URL verbatim, so `https://…` in the field beat an unticked HTTPS
  box and Test kept failing with `WRONG_VERSION_NUMBER` (a TLS handshake against
  MinIO's plain-HTTP :9000). The two now sync both ways — typing a scheme sets the
  tick, toggling the tick rewrites the scheme, and loading a saved connection
  reconciles them; a schemeless endpoint is still governed by the tick alone. The
  Test error for `WRONG_VERSION_NUMBER` / record-layer failures also explains the
  fix instead of dumping the raw SSL trace.
- **Terms renamed into the same name (e.g. applied LLM suggestions) can now be
  merged.** Duplicate detection was keyed to the scan-time name (the mechanism
  that lets a merge survive renames/enrich), so two rows renamed into a collision
  never formed a group — "Merge duplicates" / "Auto-disambiguate" reported none,
  and the inline per-group **Merge / Disambiguate / Keep separate** headers never
  appeared, despite identical names on the grid. Detection (shared by the toolbar
  toggles and the grid's header clustering) now re-keys unresolved rows to their **current** name
  (dynamic, as documented since 1.5.7) while rows inside an **active**
  merge/disambiguate keep their frozen key, so resolutions still survive later
  renames and enrich passes. Table terms remain never-groupable; unkept rows and
  empty names never count.

### Changed
- **Workflow stepper covers the Dictionary.** The top indicator bar now shows
  **Connect → Review → Dictionary → Govern → Resolve** and appears on the
  Dictionary page (it was hidden there). The Dictionary step reads done when a
  scan exists and the pending queue is clear, and refreshes live as items are
  approved/rejected; each step carries a what-happens-here tooltip.
- **Nav order matches the workflow.** The **Dictionary** page moved from after
  Resolve Term IDs to between **Glossary** and **Govern** — pending vocabulary is
  scan-grown, so approval happens after the scan and **before** export (only
  governed items flow into the Registry). The Home "Govern & generate" step now
  says so. Page title casing: "Term & **T**ag dictionary".
- **Launchers print the app version.** `run.sh` / `run.ps1` banners now read
  `VERSION` (e.g. "Glossary Generator v1.6.20"), the stale "Glossary Suggester"
  name is corrected, and the banner flow line includes the Dictionary step.

### Docs
- Workshop gains **"Guard rails — the vocabulary is protected from mistakes"**
  (Dictionary section): edit validation, reseed-preserves-approved + timestamped
  backup, audit-trail provenance, and the re-scan/re-harvest recovery loop. The
  deck gains a matching **"Safe to make mistakes — recoverable by design"** slide
  after the two-layers slide.
- Workshop gains **"Where it sits in the workflow"** (Dictionary section): reseed
  (if the pack changed) → scan → approve pending → Suggest tags → export, and why
  aliases apply only at scan time.

---

## [1.6.19] — 2026-07-04

### Fixed
- **Govern page: Keycloak fetch now comes before the roster, and the bearer-token field
  isn't squashed.** "Fetch users from Keycloak" is the first step (it populates the
  roster), so it now sits above "User roster" with a "start here" hint. The
  `…or bearer token` input was crammed between Password and the checkboxes; it's now on
  its own full-width row labelled "Bearer token — optional, use instead of username /
  password", with Verify TLS / save / generate-expertise and the Fetch button on a clean
  action row.
  domains.** Object-store (document) rows were mostly tagged just `document`, because the
  governed vocabulary only had generic rules covering `compliance`/`billing`/`meters`;
  AWC domains like GIS, SCADA, inspections, correspondence, hydrology, maintenance fell
  through to the bare category tag. The new domain pack adds governed, pre-approved
  `tag_rules` for those, so e.g. GIS → `gis;spatial;asset`, SCADA →
  `scada;operational;telemetry`, Correspondence → `correspondence;records`. Tags stay
  within the governed allow-list (no drift). **To apply on an existing deployment: reseed
  the Dictionary (Dictionary → Reseed), then re-run "Suggest tags" on the grid.** Tags are
  governed vocabulary, not LLM output, so Enrich doesn't change them — this pack is how
  you enrich them.
- **Courseware: `courseware/Glossary-Generator-Tags-and-Domain-Pack.md`** — how governed
  tags are derived (vocabulary, not LLM), why bare-`document` rows happen, the domain-pack
  format, the Reseed → Suggest-tags refresh, and the pending/approve governance.
- **Non-destructive Enrich (snapshot + "↶ Revert enrich").** The app now snapshots the
  grid before every Enrich-with-LLM run; a **Revert enrich** button restores the
  pre-enrich definitions/purposes (keeping prune/merge/edits), so you can try one model,
  revert, and try another. The snapshot is per-run and clears on load/re-scan/Reset all.
  The Enrich result now names the model used.
- **Courseware: `courseware/Glossary-Generator-LLM-and-Review.md`** — pointing the LLM at
  a GPU host (remote Ollama: `OLLAMA_HOST=0.0.0.0:11434`, firewall, base-URL, VM→host
  addressing), the non-destructive model-comparison workflow, and a Clear-vs-Reset-all-vs-
  Save safety table (what loses work and what doesn't).

Connections stabilization — bug fixes to the bulk loader and Harvest-from-PDC flow
(kept on 1.6.19; these are fixes, not new versions).

### Fixed
### Fixed
- **"Recreate if exists" no longer deletes a source it can't rebuild.** It used to
  delete-then-create, so a failed create (e.g. an invalid row) lost the existing source.
  Now it creates first and only deletes + recreates on a name/fqdn **conflict** (which
  proves the new body is valid); on a **validation** failure it aborts and keeps the
  existing source, reporting why.
- **Object-store skip note corrected.** The row note claimed "metadata ingest is for
  database schemas only" — the real reason is that the **public API doesn't expose the
  object-store file-scan trigger** (PDC's UI uses an internal `/api/start-job` endpoint we
  deliberately don't call, to stay on stable public APIs). The loader creates a correctly
  typed AWS S3 source; scanning is one **Scan Files** click in PDC, then Harvest.
- **Object stores: correct type is `databaseType="AWS"` (not `AWS_S3`).** Read off an
  untouched, working UI-created source (`Test_S3`): its record stores `databaseType: "AWS"`
  — that's the value PDC's "AWS S3" dropdown maps to. `S3` and `AWS_S3` both leave the
  Edit form's type blank (unmappable), which is why created sources wouldn't render or
  scan. The loader now sends `databaseType="AWS"` for `minio`/`s3` (plus endpoint/bucket,
  key under `accessId`, `secretKey`) and no `fileSystemType` (the record carries none;
  PDC derives it). A loader-created object store now matches a known-good one field for
  field. It still skips `metadata/ingest` (a DB job) — object stores scan via Scan Files.
- **PDC source config inspector (to crack the object-store type).** The loader gains an
  **Inspect PDC source config** tool (`POST /api/pdc/source-config`, secrets redacted)
  that dumps a source's routing fields — `databaseType`, `serviceType`, `fileSystemType`,
  `configMethod`, `driverClassName`, etc. The public API doesn't publish the object-store
  `databaseType` enum, and neither `S3` (→ blank type) nor `AWS_S3` (→ JDBC ingest path,
  "could not connect") is correct. Create one working AWS S3 source by hand in the PDC
  UI, inspect it, and read the exact values the loader must send.
- **"Recreate if exists" for the bulk loader.** The existence check (added to avoid 400s
  on re-runs) had a side effect: once a source exists, its stored config is never
  updated, so a corrected type/credentials in the CSV never reach PDC — the source is
  only re-scanned. New opt-in **recreate if exists** checkbox deletes the existing source
  and recreates it fresh (status **RECREATED**), so fixes actually apply. Use it to repair
  a source created before the `AWS_S3` fix (which has no credentials — the S3 scan then
  fails with "Unable to load credentials from … AwsCredentialsProviderChain"). Backed by
  `delete_data_source` (`DELETE /data-sources/{id}`).
- **Object-store data source was created with no type (the real MinIO scan failure).**
  The loader sent `databaseType="S3"` for `minio`/`s3`, which PDC doesn't recognize — the
  source was created but with a **blank Data Source Type**, so none of the
  endpoint/bucket/key fields attached and the scan had nothing to connect to (visible in
  PDC's Edit Data Source form as "Select…" with no connection fields). Now sends
  `databaseType="AWS_S3"` (the code behind PDC's "AWS S3" type), and populates **both**
  object-store key field names (`accessKey`/`secretKey` and `accessKeyID`/
  `secretAccessKey`) so the connector picks up whichever it reads. A `databaseType` column
  in the CSV still overrides, in case a given build uses a different enum.
- **Cleaner CSV format.** The loader CSV dropped rarely-used/duplicate columns
  (`configMethod`, `affinityId`, and the duplicate `accessKeyID`/`secretAccessKey` pair)
  down to a readable 19-column set — using `accessKey`/`secretKey` for object stores.
  Export and the sample CSV match; the shipped `awc-datasources.csv` is regenerated clean.
  (`container` is the **bucket** — `awc-documents`; the MinIO server name `az-water-minio`
  is not the container, and the endpoint uses the reachable IP.)
- **Bulk loader now skips connections that already exist.** On a re-run PDC returned
  `HTTP 400` on `POST /data-sources` because the data source (fqdnId) already existed.
  The loader now checks for an existing source by `resourceName` first; if found it
  reuses that source's id and re-scans it, reporting **EXISTS** instead of failing.
  Re-runs are idempotent.
- **AWC data-sources CSV used the wrong schema.** `awc-datasources.csv` had
  `schemaNames=public` for the operations database, so PDC ingested an empty `public`
  schema (green "OK", zero tables). Corrected to `awc_operations` (matching the
  workshop's connection details), with the MinIO row's `region=us-east-1` filled in.
- **Harvest picker showed blank source rows.** Two functions were both named
  `list_data_sources` — a shaped one (`{id, name, type, fqdn}` for the picker) and a raw
  one (config records for the CSV export). Python kept the second, so the picker got raw
  records whose keys are `resourceName`/`_id` and rendered empty. Renamed the shaped one
  to `list_catalog_roots`; the harvest endpoint now uses it, export keeps the raw one.

### Added
- **Include / exclude patterns in the loader CSV.** Added `includePatterns` /
  `excludePatterns` columns (semicolon- or comma-separated globs) that flow into both the
  data-source create and the metadata **scan** job (`metadata/ingest` is the "Ingest
  Schemas or Scan" job — one endpoint for DB schema *and* object-store files, per the API
  docs). Set e.g. `excludePatterns=*.md;*.tmp` to skip files from an object-store scan.
  The shipped `awc-datasources.csv` now excludes `*.md` on the MinIO row.
- **Fuller ingest failure reasons.** `job_status` now digs across the data object, its
  nested result, and the envelope (and falls back to the activity string) so more of
  PDC's failure detail reaches the note column.
- **Experimental "scan object stores (internal API)" toggle.** Opt-in checkbox on the
  loader that, for object stores, triggers the file scan via PDC's **internal**
  `POST /api/start-job` (the UI's Scan Files call, body `{name:"METADATA_INGEST",
  type:"START", data:{…}}`). Clearly flagged unsupported/undocumented — off by default
  (off = create-only). `internal_scan` option; `pdc_api.internal_scan_files`.
- **Courseware: `courseware/PDC-Object-Stores-AWS-S3-MinIO.md`** — reference note on the
  `databaseType="AWS"` gotcha, file-system-vs-database routing, the `accessId` credential
  field, the public-API-vs-internal-scan boundary, include/exclude patterns, and the
  PDC-vs-app reachability split, with a troubleshooting table.
- **App-reachability remap on import.** "Add to app connections" gains a remap field
  (`from=to`, comma/newline separated) that rewrites host/port (exact) and endpoint
  (substring) as connections are imported — e.g. `az-water-postgres=localhost, 5432=5433`
  — so the app's copies are reachable from where the app runs, while the PDC-side CSV
  keeps the Docker-internal names. The preview updates live as you type. `POST
  /api/connections/import-csv` accepts `remap`.
- **Import the CSV into the app's own connections — pick which ones.** The bulk loader
  gets an **Add to app connections** button: it previews every connection in the CSV in a
  searchable checklist so you tick just the ones you want (not all 100+), then imports the
  selected into the app's connections (`POST /api/connections/import-csv` with
  `preview`/`only`, upsert by name). Those feed the **Schema**, **Files**, **Test** and
  live-scan pages — the same CSV you register in PDC, no re-entry. Maps `postgres`/`mysql`
  → db and `minio`/`s3` → object-store connections.
- **Bulk loader surfaces *why* an ingest failed.** `job_status` extracts PDC's failure
  detail and the row note shows it (e.g. "ingest job ended FAILED — connection refused"),
  instead of a blind "FAILED". Timeouts note the job may still be running.
- **Per-connection console in Harvest from PDC.** Each listed source has its own **Test**
  (read-only — reports how many columns/files PDC actually holds, so an empty ingest shows
  as "0 columns · 0 files") and **Harvest** (pull that one source's terms), alongside the
  searchable multi-select bulk harvest. Labels fall back name → id → "(unnamed source)".
- **Ingest gotchas called out in the UI.** Warns that `schemaNames` must match the real
  schema, and that object stores need a valid bucket + reachable endpoint (metadata ingest
  lists files; content classification is PDC's Data Discovery step).

### Notes
- Re-scan (re-ingest) and per-source Discover trigger PDC jobs scoped by the source's
  entity UUID (not reliably returned by the list endpoint) — left to wire against a live
  PDC rather than shipped blind. Primitives (`trigger_data_discovery`, metadata ingest)
  are present.

## [1.6.18] — 2026-07-04

### Changed
- **Harvest-from-PDC picker scales to 100+ sources.** The "Harvest from PDC" card (pull
  the glossary from what PDC has already cataloged — no re-created connections, no
  secrets) replaced its single-select dropdown with a **searchable, multi-select list**:
  filter by name/type/fqdn, tick any number of sources (or select-all-shown), and
  **Harvest selected** now harvests them in sequence, accumulating and de-duplicating
  terms into one glossary, with a per-source failure summary. This is the practical
  answer to "I don't want to re-create 100+ connections" — the connections already live
  in PDC; pick the ones you want and pull. Empty-ingest and per-source errors are
  surfaced so a source that ingested "OK" but found nothing is visible.

---

## [1.6.17] — 2026-07-04

### Added
- **Similarity-scored suggested merges (`similarity.py` + "Find similar").** PDC matches
  business terms only by identity — it has no notion that `phone`, `customer_phone` and
  `cust_phone_no` are one concept. This adds the reconciliation layer PDC lacks: a
  scored comparison of the shown terms across **lexical** (normalized Levenshtein),
  **token/abbreviation** (expansion + subset containment, so `phone ⊂ customer_phone`),
  and **structural** (category / PII / sensitivity / tag-overlap) signals, blended into
  a 0–1 score. `POST /api/similarity` returns ranked pairs above a (tunable) threshold,
  each with a canonical `keep`, the `drop`, a strong/review band, and the contributing
  signal breakdown. The Glossary page gains a **Find similar** button and a steward-gated
  "Suggested merges" panel: each pair shows its score and signal bars, with Merge
  (renames `drop`→`keep` across rows), Flip (swap which is kept), and Dismiss. Deliberately
  a *proposer* — the steward disposes — and it generalizes the exact-name Merge duplicates
  and the facet fragmentation detector into one explainable surface. First pass: no
  embeddings/deps; data-shape (profiled value patterns) is left as the next signal.

---

## [1.6.16] — 2026-07-04

### Added
- **Consolidated `GET /api/governance-summary` for the visualization app.** One
  read-only payload so Catalog Insights (PDC-Insights) can just poll instead of
  scraping: **vocabulary** (governed vs pending tag/term counts, the full tag facet
  with usage, sensitivity-floor distribution), **health** (empty governed tags,
  fragmenting near-duplicates, pending-review lists), the **audit** summary (count,
  last action, actors, recent entries), and **drift** (off-vocabulary tags aggregated
  across every written registry, with a per-registry breakdown). CORS-enabled
  (`Access-Control-Allow-Origin: *`, `Cache-Control: no-store`) so a browser-side viz
  can call it directly. Backed by a reusable `tagdict.facet_health()` (server-side
  port of the empty/fragmentation logic). Schema `governance-summary/1`.

---

## [1.6.15] — 2026-07-04

### Added
- **Steward audit trail.** An append-only governance record (`audit.py` →
  `audit_log.json`) captures every dictionary **save**, pending **approve/reject**, and
  **reset** with a UTC timestamp and an actor. The Dictionary page gains an "Acting as"
  steward field (persisted locally, sent with each action) and a **Governance audit
  trail** panel with a table of recent actions and an **Export audit JSON** button. A
  compact summary (count, last action, actors, recent entries) is embedded in the
  Registry at export via `registry/bridge.py`, so the governed vocabulary carries its
  own provenance to the Policy Generator. Endpoints: `GET /api/audit`,
  `GET /api/audit/export.json`. `audit_log.json` is gitignored (not shipped).

---

## [1.6.14] — 2026-07-04

### Added
- **"Under the hood" panels for the new features.** The bulk loader (Connections) now
  has an expandable panel showing the real PDC calls — create data source → metadata
  ingest → poll status, the filter/list call, and the local connection-export — with
  explanations and source-file pointers. The Dictionary page gains a panel documenting
  the governed-vocabulary API (`/api/tagdict` load/save/review/reset/export, and how
  scans accrete pending items and the Registry embeds the allow-list). The Govern
  panel now notes it also authors the Registry (`registry/bridge.py`), and the Glossary
  panel documents `/api/retag`. Matches the existing collapsible under-the-hood style.

---

## [1.6.13] — 2026-07-04

### Added
- **Search facet preview (Dictionary page).** Each governed tag becomes an OpenSearch
  facet in PDC (a filter on `attributes.tags.name`); this previews the facet from
  reviewed usage so stewards can tidy it before methods deploy. Shows a bucket-size bar
  per governed tag, and flags (a) **empty** governed tags (no reviewed usage — dead
  facet buckets) and (b) **fragmenting near-duplicates** — tags that normalize to the
  same key (`water-quality` / `Water Quality` / `waterquality`) or are one edit apart
  (`billing` / `biling`), which would split into separate buckets a single filter can't
  merge. Pending tags are noted as not-yet-in-the-facet. Terms filter cleanly on their
  own `businessTerms.name` facet; this focuses on the cross-cutting tag facet.

---

## [1.6.12] — 2026-07-04

Completes the dictionary follow-ups and declutters the workflow.

### Added
- **Scan-time alias resolution.** When a scanned column's name matches a *governed*
  term's alias, the term is canonicalized to that term at scan time (e.g. a `cust_id`
  column and a `customer_account_number` column both become **Customer ID**), so
  divergent names across tables collapse into one mergeable term instead of separate
  variants. The confidence reason notes "canonicalized from '…' (dictionary alias)".
  Governed-only, so a pending term's aliases don't auto-apply until approved; seed
  aliases were tightened to conservative synonyms to avoid over-merging.
- **Dictionary is its own page.** The Term & tag dictionary moved out of Settings into
  a dedicated **Dictionary** nav page — company-vocabulary governance now has its own
  home, separate from per-glossary term review.

### Changed
- **Clearer Glossary workflow.** The review action bar is grouped under labels
  (Prune · Duplicates · Tags), the filter bar is labelled, and the subtitle points to
  the Dictionary page for where tags come from. Terms and their tags stay reviewed
  together (one decision); only the vocabulary governance is split out.

### Note
- Confirms the two prior follow-ups shipped in 1.6.11: the steward **approval gate**
  (accreted items are pending until approved) and the **sensitivity lift** (tag/term
  floors raise a term's sensitivity at scan and on re-tag).

---

## [1.6.11] — 2026-07-04

Adds the steward approval gate for accreted vocabulary and wires the sensitivity lift.

### Added
- **Steward approval gate.** A company tag or term discovered by a scan now enters the
  dictionary as **pending**, not live. Only the generic baseline and **steward-approved**
  company items are *governed* — and only governed items flow into the Registry / Policy
  Generator. The Settings panel shows a "Pending steward review" section with per-item
  and approve-all controls; `POST /api/tagdict/review` records the decision. Pending tags
  still surface as suggestions in the grid, and show up as `off_vocabulary_tags` on a
  concept until approved.
- **Sensitivity lift.** A term's sensitivity is now raised (never lowered) to the highest
  floor implied by its tags' sensitivity floors and its canonical term's dictionary
  sensitivity — applied at scan time and on re-tag. Ordinal, so the dictionary can only
  tighten a classification (e.g. a column tagged `PII` is lifted to HIGH; a term matching
  "Account Number" is lifted to HIGH).

### Docs
- Refreshed the changelog and manifest; added a "What's new since 1.6.4" workshop
  supplement and deck.

---

## [1.6.10] — 2026-07-04

Two-layer Term & tag dictionary with guard-rails, an LLM-rename fix, and a visible
Registry hand-off.

### Added
- **Two layers, terms included.** The dictionary now holds **terms** as well as tags,
  each marked **generic** (built-in baseline: common terms/tags with common
  sensitivity) or **company** (editable, grown from scans). Generic terms carry
  **aliases** so divergent names (e.g. "Customer Account Number" → "Customer ID")
  resolve to one canonical term. Company terms accrete from scans with their observed
  sensitivity (raised to the highest seen).
- **Guard-railed edits.** Saving the dictionary is validated and repaired rather than
  blindly applied (drift is a PDC limitation, so a bad edit can't be silent): the
  generic baseline can't be removed (restored), every rule/term tag must exist in the
  vocabulary (auto-added), sensitivity values are checked, invalid regexes are flagged,
  and alias collisions are reported. All fixes come back as **warnings** shown in the
  panel.
- **Registry carries the term vocabulary too.** The Registry's `tag_vocabulary` block
  now also embeds the canonical **terms** (sensitivity, aliases, tags), so the Policy
  Generator governs both Assign-Tags and term links from one source.
- **Settings panel** gains a Terms table (with generic/company badges, sensitivity,
  aliases), an add-term form, layer badges on tags, and guard-rail warnings.

### Fixed
- **LLM name apply now propagates.** Clicking a suggested name (e.g. rename "Customer
  ID") renames **every instance** of that term at once, so the duplicates stay one
  mergeable term instead of splitting into un-mergeable variants.
- **Registry hand-off is visible.** After Generate, a "Handoff to the Policy Generator"
  card on Govern shows glossary-saved, JSONL-generated and **Registry written: <path>**
  with a ready-state, answering "is the registry created and saved?".

---

## [1.6.9] — 2026-07-04

Turns the tag vocabulary into a real, persisted, per-company **tag dictionary** —
the governance backbone for tag consistency across the glossary, the Registry, and
the Policy Generator.

### Added
- **`tagdict.py` — per-company tag dictionary.** The controlled tag allow-list plus
  the name→tag rules are now a saved artifact (`tag_dictionary.json`), not code:
  * **seeded** from the domain pack + built-in generic/water defaults,
  * **grown from scans** — every database scan and document discovery accretes the
    tags it used (counts + example terms) into the dictionary (reviewed accretion:
    only tags the controlled rules produced ever enter — never free text),
  * **saved and reloaded**, so it persists and accumulates per company,
  * carries a **sensitivity floor** per governed tag.
- **Tagging reads the live dictionary.** `suggest_tags` now sources its rules,
  category tags and allow-list from `tagdict`, so a scenario is configured by editing
  the dictionary, not the module.
- **Registry embeds the vocabulary.** `POST /api/generate` now writes a
  `tag_vocabulary` block (allow-list + sensitivity floors + domain) into the Registry,
  and flags any concept whose tags fall outside it (`off_vocabulary_tags`). The Policy
  Generator reads that block, so its Data Identification Assign-Tags stay inside the
  same governed vocabulary — closing the tag-drift surface by construction.
- **Tag-dictionary API + Settings panel.** `GET/POST /api/tagdict`,
  `POST /api/tagdict/reset`, `GET /api/tagdict/export.json`. Settings gains a
  **Tag dictionary** card: view every tag with its floor, usage count and example
  terms; add tags and rules; save, export (shareable governance record), or reseed.

### Note
- One complete codebase. `tag_dictionary.json` is created on first run (or first scan)
  and is not shipped, so it seeds cleanly from the domain. Tagging, accretion, the
  registry embed and the endpoints are all covered by the test pass.

---

## [1.6.8] — 2026-07-04

Makes term/tag definition less manual: meaningful controlled tags, locked+badged
table terms, and a one-click re-tag.

### Added
- **Meaningful, controlled tags.** `suggest_tags` now derives domain tags from the
  term/column name and category through a curated rule set (billing, financial, usage,
  metering, water-quality, compliance, operational, asset, temporal, identifier, …),
  layered on the existing PII/CDE/key/sensitivity signals. Every tag is filtered
  against a controlled allow-list (`TAG_VOCABULARY`) so tags say what a term *is*
  instead of collapsing to the category slug, and can't drift. A domain pack can extend
  it via `category_tags` / `tag_rules` / `extra_tags`. Tags are threaded with the
  column and term name at scan time (databases and object-store documents).
- **One-click "Suggest tags"** on the Review bar → `POST /api/retag` re-derives tags for
  every shown term (no rescan) — for glossaries loaded from file, or after editing
  categories. Table terms keep their table-level tags.

### Fixed / Changed
- **Table terms are now locked and badged.** A table-level record term (name ends in
  "Record", no source column) shows a **TABLE** pill and a left accent, and its keep
  checkbox is checked + disabled — it can't be dropped, even at low confidence or via
  Keep-High+Med / master-toggle / bulk actions. The guard lives in one place
  (`setKeep`), so every path respects it.
- Table-level terms also carry their category's meaningful tag (e.g. `record;table-level;
  billing`) instead of just `record;table-level`.

### Note
- One complete codebase. Deterministic tag logic is unit-tested; the re-tag endpoint and
  table-term lock are covered by the boot smoke test.

---

## [1.6.7] — 2026-07-04

Fixes the ingest 400 seen in testing (`/scope/0 must match format "uuid"`), makes
the connection export match the real workflow, and stops the results table from
overflowing. Verified against the full PDC v2 Jobs reference.

### Fixed
- **Ingest used the wrong job.** 1.6.6 switched ingest to
  `jobs/execute/metadata/re-ingest`, whose `scope` must be **entity UUIDs** — but a
  freshly created data source's id isn't a uuid, so PDC returned
  `400 … /scope/0 must match format "uuid"`. The correct job for a new source is
  `jobs/execute/metadata/ingest` (the "Ingest Schemas or Scan" job), which takes the
  data-source **config** body scoped by `resourceId`. Ingest now sends the create body
  plus the created `resourceId`/`fqdnId`. (`metadata/re-ingest` is the later *refresh*
  job and is intentionally not used for initial load.)
- **Results table overflow.** The bulk-load results table now uses a fixed layout with
  a column group and wrapping (`word-break`) note cell, so long error text wraps inside
  the card instead of bleeding past the edge. Working-row colspan corrected.

### Changed
- **Export existing now exports the app's own saved connections** (the cards you build
  in the New-connection form) — the actual "I made these by hand, now bulk-load them"
  workflow — via `GET /api/connections/export.csv`. Because the app already holds their
  credentials, this CSV **includes secrets** and reloads straight into the loader; the
  file is sensitive. (The PDC-side export `POST /api/pdc/connections/export`, which
  reads sources already registered in PDC and blanks secrets, remains available for
  capturing hand-built PDC connections.)

### Note
- One complete codebase. Live PDC calls can't be exercised offline; the create→ingest
  path is covered by unit tests against the confirmed request/response shapes, and the
  export→reload round-trip is tested end to end.

---

## [1.6.6] — 2026-07-04

Fixes the bulk data-source loader and metadata ingest against the confirmed
PDC 10.2.11 Public API (v2), and adds a connection **export**. All endpoints and
bodies were re-verified against the Pentaho API reference and Academy.

### Fixed
- **Create response parsing.** `POST /data-sources` returns `data` as an **array**
  of created records (201/207). The loader was reading `_id` off that array as if it
  were an object, so `resourceId` came back `null` — the connection looked created
  but nothing downstream could be scoped to it. Now reads `data[0]._id`.
- **Metadata ingest was calling the wrong job.** The correct job is
  `POST /jobs/execute/metadata/re-ingest` with body `{"scope":["<data-source id>"]}`
  (an array of entity UUIDs), not `metadata/ingest` with a connection-shaped body.
  Ingest is now scoped by the created id, with optional `deleteEmptyFolders` /
  `incremental` / `scanSinceTimeframe`.
- **`configMethod` default corrected.** The credentials-style body (discrete
  host/port/user/password or keys) was being sent with `configMethod:"uri"`, which
  expects a single URI string — leaving connections mis-configured. Default is now
  `credentials`; still overridable per row.
- **Unconfirmed test-connection job removed.** There is no confirmed public
  test-connection job; the row state machine is now create → re-ingest → poll.
  Connectivity is validated locally by the app's Test-connection buttons before load.
- **Object-store credentials** accept either spelling (`accessKeyID`/`secretAccessKey`
  or `accessKey`/`secretKey`); MinIO/S3 protocol is derived from the endpoint scheme.
- **Sample resource names fixed.** PDC forbids spaces in data-source names; the old
  sample used `Operations DB`. Starter and AWC CSVs regenerated to the canonical column
  set with valid names.

### Added
- **Export existing PDC connections → CSV.** `POST /api/pdc/connections/export` reads
  the data sources already registered in PDC (via the wildcard
  `POST /data-sources/filter`) and returns a **loader-ready CSV** — the same columns
  the bulk loader consumes. Build a connection by hand in PDC, export it, and replay
  it. Secret columns come back blank (PDC only ever returns encrypted secrets), so the
  operator re-enters them before reload. The export carries PDC's exact `databaseType`
  and `configMethod` codes, which the loader now honors verbatim — so a hand-built
  connection round-trips without guesswork. Exposed as an **Export existing** button on
  the bulk-load panel.

### Note
- Delivered as one complete codebase (app + template + CSVs, in sync). No behavioural
  change to the glossary scan/review/export or the `registry/` writer.

---

## [1.6.5] — 2026-07-04

Fixes a packaging regression: a **stale `templates/index.html`** (a ~1.5.6 snapshot)
had been shipped alongside the current 1.6.4 backend, so the running app rendered the
old detached duplicate-resolution panel while the version badge — which reads the
`VERSION` file over `/api/version`, independent of the template — still showed the
new number. The regression was invisible from the badge alone.

### Fixed
- **Inline duplicate-cluster layout restored.** The Merge / Disambiguate / Keep
  separate control is rendered **inside the review grid** again, as a header row
  (`tr.gclhead`) above each group's clustered candidate rows, instead of a detached
  list above the grid. `drawRows` now clusters the shown rows by group key
  (members contiguous, anchored at first occurrence) and injects the header; the row
  template is factored into `_rowHtml`.
- **Active choice uses the darker highlight** (`--dark` #0A3D52) and stays reversible
  (click the active segment to revert to Keep separate).
- **The header survives a merge.** After merging, the group collapses to one row but
  keeps its header (`… → merged into one`) so it can be reverted inline.
- **Table terms hardened out of collisions at the source.** `snapshotScan` assigns a
  table-level term a unique group key, so a conceptual table term can never join a
  duplicate cluster (grid, bulk toggle, or merge) even if it shares a name.
- **Detached `#grpResolve` panel retired** to a hide-only shim; `PANEL_GROUPS` stays
  maintained for the bulk *Merge duplicates* / *Auto-disambiguate* toggles.
- **Version made coherent.** `VERSION` → 1.6.5 and the template's hard-coded brand
  fallback bumped to match, so the static file no longer disagrees with the badge.

### Note
- Backend was already correct at 1.6.4 and unchanged: the `registry/` writer and its
  `/api/generate` + resolve-terms backfill hooks were intact. This release is a
  template + version-coherence fix, delivered as one complete codebase.

---

## [1.6.4] — 2026-07-03

App renamed **Classification Registry -> Policy Generator** (named for its aim: it
reads the Registry and generates the Data Identification policy — dictionaries +
patterns). The middle artifact stays the **Registry**. Docs, workshop, one-pager
and the two-apps diagram updated.
- **`awc-datasources.csv`** added — the two AWC data-source connections (PostgreSQL +
  MinIO) pre-filled from Workshop 1, ready for the bulk connection loader.
- **`water_utility.people.json`** added — the AWC people/steward roster seed.

---

## [1.6.3] — 2026-07-03

The method-authoring app (formerly Method Advisor -> Metadata Advisor) was renamed
to **Classification Registry**, and the single-source artifact it consumes named
the **Registry** to avoid a name clash. *(Renamed again to **Policy Generator** in
1.6.4 — the name that describes its aim.)*

---

## [1.6.2] — 2026-07-03

Dictionary import container corrected, and a one-call policy build added.

### Fixed
- **Dictionary import is a ZIP.** Dictionaries import into PDC as a **ZIP of JSON +
  CSV** (an earlier reading of a bare JSON was of an already-unzipped, built-in
  export). Confirmed against Pentaho documentation and Academy: dictionaries must
  be ZIP; patterns may be JSON or ZIP.

### Added
- **Build the policy from the Registry** — one call emits the whole Data
  Identification method set (pattern JSON + dictionary ZIPs) for every concept with
  a reconciled term id and a method spec; unminted concepts are skipped, not emitted
  with a null term link.
- **Per-concept method specs** in domain packs:
  `{"kind":"pattern","regex":[...]}` or `{"kind":"dictionary","values":[...]}`.

---

## [1.6.1] — 2026-07-03

Persistent registry, verified compliance references, and safe LLM description
enrichment. Adds an architecture diagram set (see README).

### Added
- **Persistent registry.** The Registry is now saved with the
  glossary (`registry.<glossary>.json`) and reloaded on open — reconciled term
  ids, category bindings, learned concepts, tags, sensitivity, detection rules,
  and the reference map all persist. Without this the reconcile handshake is lost
  on restart and drift cannot be assessed next session.
- **Verified reference map.** Domain packs may carry a `references` block of
  curated, human-verified `{title, authority, url, jurisdiction, verified}`
  links, keyed by concept or tag. The water example ships real EPA (SDWA / NPDWR)
  and Arizona ADEQ (Title 18 Ch. 4) links.
- **Safe description enrichment.** The LLM writes the description *prose* only and
  is told not to invent citations or URLs; compliance *links* come solely from the
  verified reference map. Same principle as the tag allow-list.
- **Architecture diagrams** (`diagrams/`): registry spine, lifecycle/reconcile
  loop, LLM safety split, layered registry.

### Note
- Registry-from-scan is reviewed accretion (steward-confirmed), never inference;
  the generic PII/PCI/PHI floors stay authoritative.

---

## [1.6.0] — 2026-07-03

**Architectural.** Introduces the **Registry** — a single source
of truth that unifies how business terms, governed tags, and sensitivity are
produced, and closes the loop with a **drift linter** and **reconcile** view
that keep Data Identification methods aligned to the glossary. Generic to any
industry: the core registry is neutral PII/PCI/PHI, and industry vocabulary
loads from a domain pack (the same pattern as `GLOSSARY_DOMAIN_PACK`).

### The single registry
- One canonical entry per **concept** carries: glossary **term id**, governed
  **tags**, a sensitivity **floor**, and (for pattern methods) a **category**.
- Both sides read from it — the glossary term's tags *and* the Data
  Identification method's tags are generated from the same entry, so they
  cannot silently diverge. Sync becomes a build invariant, not a reconcile job.

### Deterministic sensitivity (fixes mis-grading)
- Rules-first classification grounded in a codified taxonomy: a person
  identifier (e.g. a customer id) is HIGH + PII; a bare surrogate key is LOW.
- The sensitivity is an ordinal **floor** — rules can raise a classification;
  the optional LLM residual runs only on unmatched columns and can **never
  lower** a rule hit. Regulated fields no longer depend on a model's guess.
- Tags come from a controlled **allow-list** derived from the registry, ending
  free-generated tag repetition.

### Policy Generator emit (the method-authoring app)
- Emits Data Identification **DataPattern** and **Dictionary** methods that bind
  to the glossary (dictionary → `dictionaryTermId`; pattern → `categories`) and
  stamp `applyTags` from the registry. Shapes verified against real PDC exports.

### Drift linter + reconcile
- The linter reads a deployed method back and diffs its `applyTags` against the
  registry: **OK / DRIFT / UNLINKED / ORPHAN**.
- Reconcile turns a catalog scan + deployed methods into verdicts:
  **CLASSIFIED / UNKNOWN / MISSING / DRIFT / UNLINKED**.
- **Drift is a post-reconciliation capability.** A dictionary method binds to a
  concept by `dictionaryTermId`, which only exists once the reviewed glossary is
  imported into PDC and its minted ids are read back and applied to the registry
  (`reconcile_term_ids`). Before that pivot, dictionary methods read as UNKNOWN
  and their tag drift cannot be assessed. Pattern methods bind by category, so
  pattern drift can be seen earlier, but the full drift view follows reconcile.

### Generic — no baked-in industry
- Core registry is industry-neutral. `CLASSIFICATION_DOMAIN_PACK` (or
  `load_domain_pack`) overlays industry concepts + detection rules + categories.
- Ships `domain_packs/water_utility.example.json` as **one example only**; copy
  and swap the vocabulary for any sector — no code changes.

### Files
- New `classification/` package: `registry`, `classify`, `llm`, `emit`,
  `envelope`, `drift`, `reconcile`, CLI, self-test (28 checks), domain packs.
- `VERSION` — 1.5.7 → 1.6.0.

---

## [1.5.7] - 2026-07-02 — Reversible review controls + per-group resolution

### Added
- **Reversible review controls.** *Keep High+Med conf*, *Merge duplicates* and
  *Auto-disambiguate* are toggles — they **highlight when applied** and **revert on a
  second click**. *Keep High+Med conf* reverts exactly the rows it changed (table terms
  are never touched); the merge/disambiguate buttons now drive the per-group model below
  across every duplicate group and undo cleanly.
- **Per-group resolution panel** on the Review page. Each duplicate name gets a
  three-way **Merge / Disambiguate / Keep separate** control, so you can **merge one name
  and disambiguate another in the same pass**. Every choice is independently reversible:
  rows are tagged with their original group (`_grp`) and each group re-derives from a
  pristine scan base, so nothing is destructive.
- **Reset all** — returns the grid to the raw scan (filters, keeps, inline edits, and any
  per-group or global merge/disambiguate).

### Changed
- **Trimmed the keep toolbar.** Removed the redundant *Keep all shown*, *Keep none shown*
  and *Invert shown* buttons — the checkbox in the Keep-column header already keeps or
  clears all shown rows (tri-state).

Implementation (`templates/index.html`): `snapshotScan` (raw-scan snapshot + `_grp`
tagging), `groupSet` / `groupSetIdx` / `renderGroupResolve` (per-group panel),
`toggleHM` / `toggleMerge` / `toggleDisambig` / `resetAll`.

### Note
- `glossary-review-prune-prototype.html` remains as the interaction reference; the
  behaviour it previewed now ships in the app.

## [1.5.6] - 2026-07-02 — Table terms kept by default; enrich null-guard

### Fixed
- **`/api/enrich` 500** (`AttributeError: 'NoneType' object has no attribute 'get'`
  at `llm.py` → `enrich_rows`). A `None`/blank row in the payload slipped past the
  `only_low_confidence` filter (short-circuit) and was dereferenced. `enrich_rows`
  now drops non-dict rows up front, and the `enrich()` view filters the payload to
  dict rows.
- **Table-level terms were dropped by *Keep High+Med conf*.** A table term carries a
  blank `Confidence` (it is conceptual, not a column match), so the confidence cull
  set its Keep to false. Table terms are now **kept by default and exempt from the
  cull** — `bulkKeep('hm')` skips them via a new `isTableTerm(r)` test (empty
  `Source_Column` plus the `table-level` tag or a `Record`-suffixed name). Only an
  explicit steward action (Keep none / untick) removes one.

### Changed
- **Bundled `water_utility.example.json`** — every table term now ends in **“Record”**
  (`Customer Record`, `Water System Record`, `Rate Plan Record`, `Monthly Usage
  Record`, `Water Quality Record`, `Account Alert Record`), matching the app's
  `<Singular> Record` derivation and giving table terms a stable, recognisable shape.

## [1.5.5] - 2026-06-30 — Duplicate-term review panel

### Windows host support — added 2026-07-02 (held at 1.5.5)

No change to the suggestion/profiling/export pipeline, so the version is held
at 1.5.5; these additions make the app run natively on a Windows host.

- **Native Windows launcher** — `run.ps1` (PowerShell) plus a `run.bat` wrapper,
  the Windows equivalent of `run.sh`: creates/uses `.venv`, reinstalls deps only
  when `requirements.txt` changes, and launches the app. Pre-flight prefers a
  wheel-friendly Python (3.13 → 3.12 → 3.11 → newest; `-PyVersion` forces one)
  and auto-rebuilds `.venv` if the interpreter changed — this avoids source-build
  failures on a brand-new Python (e.g. 3.14) that has no `psycopg2-binary` wheel yet.
- **Hardware probe + model sizing** — the launcher reads GPU VRAM
  (`nvidia-smi` → registry `qwMemorySize` → CIM) and prints `ollama pull`
  suggestions matched to the detected VRAM.
- **Model dropdown reflects the local Ollama** — the Model selector now reads
  `GET /api/models` and groups it *Installed (ready to use)* → *Suggested — not
  yet pulled* → *Custom…*, restores the saved model on load, and refreshes after a
  pull. Previously it showed a fixed catalogue only.
- **Ollama probe uses `127.0.0.1`** instead of `localhost`, so Windows doesn't miss
  the server via IPv6 `::1`. Set `OLLAMA_URL=http://127.0.0.1:11434` in `.env` for
  the app's own calls (enrichment + the model list) on Windows.
- Browser tab title corrected to **Glossary Generator**.

### Added
- **Review duplicate term names** panel in the Generate & apply card. When the build
  check finds names that repeat across categories (which name-based Resolve can't tell
  apart), an expandable panel lists each clashing name with its occurrences (category +
  source table) and an editable name field per occurrence. Options:
  - **Qualify by category** (per group or all) — renames duplicates to
    `Term (Category)`, e.g. `Account Number (Billing & Rates)` vs `Account Number (Customer)`.
  - **Merge all into one each** — collapses a repeated name into a single term linked to
    all its columns (PDC's one-term-many-columns model).
  - **Inline rename** — type a new name; clashing/empty names are highlighted live.
  Fixing the names re-runs the build check automatically so the warning clears in place.

### Fixed
- **Rating** field in Stewardship defaults now bottom-aligns with the other fields (its
  hint no longer pushes the select up).

## [1.5.4] - 2026-06-30 — Settings UI fixes

### Fixed
- Segmented controls (GPU offload, Theme) now have equal-width buttons and no longer
  overlap or stretch unevenly; their columns are fixed-width.
- "Help banner" shrunk from a full-width bar to a compact checkbox.

### Added
- "Test connection" now shows an inline result next to the button — connected URL +
  model state, or the offline error and a hint to use `http://host.docker.internal:11434`
  in Docker — so the probe outcome is visible without watching the sidebar.

## [1.5.3] - 2026-06-30 — Configurable LLM settings

### Added
- **LLM settings are now editable in-app** under Settings → Local LLM (Ollama), and
  take effect immediately (no restart) via a new `llm.configure()` applied on save:
  - **Ollama URL** and **request timeout**
  - **Company** name used in enrichment prompts (`GLOSSARY_COMPANY`)
  - **Enrich workers** (1–16) and **batch size** (1–20) for enrichment throughput
  A saved value overrides the corresponding environment variable; clearing a field
  reverts to the env default. "Test connection" re-probes against the new URL.

### Changed
- `model`, `ollama_url`, `llm_timeout`, `company`, `llm_workers` and `llm_batch`
  defaults are now env-aware in `DEFAULT_SETTINGS`, so `/api/settings` reports the
  effective values; `/config` shows the live Ollama URL in use.
- The LLM client reads timeout, workers and batch dynamically, so changes apply at
  runtime; `enrich_rows` no longer re-reads the environment directly.

### Notes
- Useful for the Docker deployment: point the app at
  `http://host.docker.internal:11434` from the UI without rebuilding or editing `.env`.

## [1.5.2] - 2026-06-30 — Scenario seed roster & post-fetch expertise

### Added
- **Per-scenario seed roster.** A scenario's people now travel with its domain pack:
  the AWC roster moved to `domain_packs/water_utility.people.json`. Set
  `GLOSSARY_PEOPLE_SEED` (alongside `GLOSSARY_DOMAIN_PACK`) and the app copies the seed
  into the live roster **once, only when it is missing or empty** — so a fresh `/data`
  volume (Docker) or fresh checkout (run.sh) starts with the seeded people, while live
  edits and Keycloak fetches are never overwritten.
- **Generate expertise after a Keycloak fetch.** A "⚡ generate expertise (LLM)"
  toggle (on by default) beside the Fetch button; when a fetch returns people with no
  expertise, the LLM fills it in automatically right after, so auto-assign has more
  than role to match on. Untick to keep the previous nudge-only behaviour.

### Changed
- The default `people.json` now ships **empty** (generic). AWC people are applied via
  the seed above, keeping the engine scenario-neutral out of the box.

### Notes
- Seeding is one mechanism for both run.sh and Docker (runs at app startup), so no
  entrypoint script is needed. Seeded UUIDs still only bind on the Keycloak instance
  they came from — treat the seed as a starting roster and re-fetch to get bindable IDs.

## [1.5.1] - 2026-06-30 — Stewardship & expertise

### Added
- **LLM expertise generation.** `llm.suggest_expertise()` generates `expertise`
  keywords per roster member from their role, responsibilities (`owns`) and
  community text plus the scanned categories. LLM-first via local Ollama
  (`_expertise_llm`, strict JSON keywords) with a deterministic offline fallback
  (`_expertise_fallback`) that strips the person's own name and generic role words.
- **`POST /api/suggest-expertise`** endpoint (`{people?, categories?, overwrite?,
  model?, save?}`); uses the saved roster when `people` is omitted.
- **"Suggest expertise (LLM)" button** and **"overwrite existing"** toggle in the
  roster card; results merge back by id/email/name and mark the roster unsaved.
- **"Set up stewardship" one-click macro** — fills any missing expertise, then
  auto-assigns steward/owner/custodian across every category.
- **`.env` support** — dependency-free loader in `app.py` that runs before the local
  imports, so `GLOSSARY_DOMAIN_PACK` (the AWC bundle), `PORT`, `OLLAMA_URL`, etc. all
  take effect from one file. Real environment variables still override it. See
  `.env.example`.
- **Post-Keycloak-fetch nudge** prompting to run Suggest expertise when fetched users
  have no expertise.
- **Brand favicon.** Inline SVG (teal→blue tile with a “G” monogram) served at
  `/favicon.svg` and `/favicon.ico`, linked in the page head — no more `/favicon.ico`
  404 and the browser tab now shows the brand mark.
- **API version tags in the "Under the hood" panels.** Every rendered PDC call now
  shows a `v1`/`v2`/`v3` badge (parsed from the call URL) so the developer can identify
  which API version it targets at a glance; Keycloak token calls are tagged `keycloak`.
  The Harvest preview URLs now reflect the version selected in the Harvest card.

### Changed
- Default **Rating** is now **Auto (DQ)** (was None), applied when the Govern page
  opens; per-category rating label aligned to "Auto (DQ)".
- Default **Reviewed date** is now **today + 3 months** (set only when empty, so a
  loaded glossary's saved date is never clobbered).
- Expertise column/field help text clarified to "comma-separated keywords · matched to
  category terms when auto-assigning".

### Fixed
- Roster add-person form field overlap (UUID/Expertise inputs colliding with the
  Add / Save buttons) — re-flowed with sane flex bases and a grouped button cluster.
- "Apply to categories" shrunk from a full-width bar to a compact checkbox.

### Hardened
- `_write_json` is now **atomic** (temp file + `os.replace`), so a crash mid-write can
  no longer truncate `people.json` / `settings.json` / other state files.

### Removed
- Stale root `index.html` duplicate. The served template is `templates/index.html`.

### Notes
- Reviewed for PDC API v3: auth, `entities/filter`, entity PATCH and search are v2/v3
  compatible; the per-job execution endpoints (Calculate Trust Score, profiling/
  discovery triggers, harvest test-connection/ingest) follow the v1/v2 style and are
  not yet adapted to v3's bulk `/jobs/execute/bulk` pattern — keep the connector on
  **v2** for 10.2.11. Full detail in `REVIEW.md`.
- The Arizona Water vocabulary bundle remains **opt-in** via `GLOSSARY_DOMAIN_PACK`;
  `people.json` ships AWC-flavoured (roster + expertise).

## Earlier

History before this file is not itemised here. Recent prior work included genericising
the engine (AWC vocabulary moved to `domain_packs/water_utility.example.json`),
Docker packaging, the `POST /entities/filter` data-source listing pattern, and the
table-level "record" term model (`table_term_rows`) feeding Trust Score.
