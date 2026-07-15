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
