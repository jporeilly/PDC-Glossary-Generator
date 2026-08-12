# The Clean-Run Walkthrough — install to PDC

The field-exam script: a fresh install walked through every stage of the
workflow, with a **pass-check** at each step so you know the stage landed
before moving on, and a **talk track** — the words to say while you drive —
so the same document runs a demo, an enablement session, or a solo exam.

Numbers in *(parentheses)* are from the Arizona Water reference estate —
yours will differ; the *shape* of each check should not.

> **Rule of thumb:** scans capture evidence *at scan time*. After upgrading
> the app, re-scan before judging results — an old grid carries old evidence.

---

## Phase 0 — Clean install

- [ ] Close the running app.
- [ ] Run the installer → **tick "delete app data"** → finish.
- [ ] Launch.

**Pass-check:** the sidebar shows the new version, Home lists **no** saved
glossaries, the LLM chip is green on your model, PDC shows "not connected".

> **Talk track** — *"We're starting from nothing on purpose. Everything you
> are about to see — terms, categories, patterns, policies — will be earned
> from the estate itself during this session. There is no demo data baked
> in, no canned glossary. The two status lights matter: the model runs
> locally, so nothing we scan leaves this machine; and we are not connected
> to the catalog yet — the app builds the glossary first, the catalog
> receives it at the end."*

## Phase 1 — Connect

- [ ] Settings: model, compute, and **company name** (a wipe clears it).
- [ ] Connect → import the connections CSV for your estate.
- [ ] **Test** each connection.

**Pass-check:** every connection tests green *(3 connections)*.

> **Talk track** — *"One CSV describes the estate — databases, object
> stores, credentials — and becomes saved connections in one import. Each
> one gets a live test before we trust it. In a real engagement this file
> comes from the platform team; it's also how the same run repeats on the
> next environment."*

## Phase 2 — Scan — both sources before any AI

- [ ] Object store connection → **Add to glossary** *(~43 rows)*.
- [ ] Database connection → **Add to glossary** — merges into the same grid
      *(~180 rows, ~157 kept)*.

**Pass-checks:**
- Structural keys auto-pruned, with reasons on the rows *(~23)*.
- Bare structural columns (`description`, `notes`) and period-stamped
  snapshot columns (`*_may_2026`, `*_2026q1`) start **un-kept**.
- Low-cardinality code columns carry **Enum values**; formatted columns
  carry a **Value pattern** (open a row's evidence to confirm).

> **Talk track** — *"Every column the scan finds becomes one candidate
> term — database columns, and the columns inside the files in the object
> store: a CSV's header row is read, a JSON file's structure is walked. The
> scan also profiles values as it goes, and that evidence stays on the row:
> this status column carries its actual value list, this account number
> carries the format its values share. Notice what the app already declined
> for us — surrogate keys, a column literally named 'description', a
> snapshot column stamped with the month it was exported. Each one is
> un-ticked, not deleted, with the reason written on the row: the steward
> can restore any of them with one click. The app proposes; a person always
> decides."*

## Phase 3 — Review — the keystone flow

- [ ] `1 · AI categories`.

  **Pass-check:** the completion line reports a **consolidation** — e.g.
  *"5 categories proposed … would take the grid from 11 to 5"* — with no
  "NOT a consolidation" warning and few or no tables keeping physical
  groups. Re-running proposes the **same** taxonomy (the call is seeded).

> **Talk track** — *"Here's the first real AI moment. The model is shown
> only what the scan proved — tables, columns, and which tables reference
> which — and asked a business question: what handful of subjects does this
> company actually run on? For a water utility it comes back with things
> like Customer Management, Asset Management, Water Quality & Compliance —
> not one category per table, a real taxonomy. Two things to trust here:
> the line at the bottom tells you exactly what accepting will do to the
> category count before you accept anything; and the call is deterministic —
> run it twice, same answer. AI that proposes the same taxonomy every time
> is AI you can put in front of an auditor."*

- [ ] **Accept all** pills.
- [ ] `2 · Approve categories (N)` — the keystone.

  **Pass-check:** the message confirms the count **and** *"Saved as …"* —
  an unnamed workspace is auto-named and saved here; everything after this
  moment survives a closed window.

> **Talk track** — *"This button is the governance moment of the whole
> flow. Approving the categories is the steward declaring the taxonomy
> settled — and everything downstream keys off that declaration: the
> dictionary syncs to it, stewardship binds to it, the export freezes it so
> the next scan of this estate lands in the same shape. The count is on the
> button — you know exactly how many categories you're signing off. And the
> moment you approve, the workspace names and saves itself: from here on,
> nothing we do can be lost to a closed window."*

- [ ] `3 · AI pass (all fields)` — the long stage; the batch line narrates
      progress. **Accept all** when it finishes.

> **Talk track** — *"Now one model call per term writes the language:
> definition, purpose, a clearer name where the physical one is cryptic,
> and governed tags. Everything lands as proposals — the grid fills with
> pills, and nothing touches a row until it's accepted. The progress line
> tells you what it's working on; on a real estate this is the coffee
> stage. What you get back is a glossary that reads like a business wrote
> it, at a per-term cost of seconds, not the weeks a manual glossary
> project burns."*

- [ ] **Resolve duplicates** — `4 · AI advise` lights on the strip while
      same-named clusters await a decision. Work each cluster's header bar:
      **Merge / Disambiguate / Keep separate**, recommendation and reason
      shown *(~10 clusters; ~20 rows fold)*. AI advise escalates only the
      groups badged *(check)*.

> **Talk track** — *"The pass ran first on purpose: with final names and
> real definitions in hand, false duplicates dissolve and the remaining
> calls are easy. Consolidating eleven physical groups into five subjects
> means the same business concept can now appear twice — Capacity from the
> GIS files and Capacity from the operations database sit in one category.
> Each cluster is a deliberate steward decision on its own header — there
> is no wholesale button, by design. A merge folds them into a single term
> that keeps both physical sources as evidence: one concept, two linked
> columns, which is exactly what the catalog should hold."*

- [ ] `✓ Review complete → Dictionary`.

## Phase 4 — Dictionary

**Pass-check on entry:** the sync chip reads **synced**, and there are
**zero** stale badges on a first run. (Stale appears on *later* rounds,
when the estate has moved and pending entries lost all backing — retire
those with one click.)

- [ ] Approve the vocabulary that belongs; retire scan noise.

> **Talk track** — *"Everything the review streamed in — terms and tags —
> queues here as pending vocabulary, and the steward promotes what belongs
> to the company's governed language. The chip up top says this page is in
> sync with the review we just finished, so what you approve is what you
> saw. And this page is the flywheel: next quarter, when the estate has
> moved on, anything whose backing evidence disappeared gets flagged stale
> — dead vocabulary leaves the queue in one click instead of fossilising."*

## Phase 5 — Govern

- [ ] Real people with **real account UUIDs** (Keycloak fetch, or manual) —
      stewardship binds to PDC accounts by UUID, and the per-category grid
      unlocks only for accounts that have one.
- [ ] Set expertise per person, then `⚡ auto` assign.
- [ ] Set the **PDC glossary name** — this names the glossary the import
      file creates/updates; the workspace's autosave name is not it.
- [ ] **Apply stewardship to terms**.

> **Talk track** — *"Terms without owners are shelf-ware, so before
> anything reaches the catalog we bind people to it. The roster comes
> straight from your identity provider — these are real catalog accounts,
> matched by UUID, not names in a spreadsheet. Auto-assign matches each
> category to the person whose declared expertise fits it, and every
> assignment is overridable per category. When this exports, every term
> carries a steward, an owner, and a custodian."*

## Phase 6 — Apply → PDC

- [ ] Authenticate to PDC.
- [ ] **Check PDC tree for lingering categories** — imports update in place
      but never *remove* categories, so earlier eras linger until deleted
      in PDC. Expect listed leftovers on a re-used glossary; delete them in
      PDC first if you want a clean tree.

> **Talk track** — *"One honest quirk of catalog imports: they update and
> add, but never remove. If this glossary has been imported before, old
> category folders linger in the tree. This preflight asks the catalog
> what it currently holds and lists exactly what this export no longer
> carries — so you clean the tree deliberately, before the import, instead
> of discovering three naming generations in it later."*

- [ ] **Generate JSONL**.

  **Pass-check:** build check clean — no duplicate-collision warning (you
  merged in Phase 3) and no unowned-terms notice (you applied stewardship).

> **Talk track** — *"The export is import-ready JSONL in the catalog's own
> format — glossary, categories, and terms with definitions, sensitivity,
> tags and stewardship baked in. The build check is the honesty gate: it
> tells you about anything that would collide or arrive unowned while you
> can still fix it. It also writes the Registry — the machine-readable
> record of every term-to-column mapping this review settled, which is what
> makes the next scan of this estate deterministic."*

- [ ] **Draft policies** (AI polish on) — the line under the button narrates
      *seeds → polish (rule n of m) → assemble*.

  **Pass-check:** dictionaries minted for your reference-data columns; the
  skip list holds only the honest cases — numerics/free text ("profiled,
  but no shape"), dates/names/ids (tagged via the term↔column link),
  document terms, table-level records, and barely-repeating columns that
  genuinely need a curated seed.

> **Talk track** — *"This is the bridge from glossary to enforcement. Every
> value pattern the scan induced becomes a Data Pattern the catalog can
> detect with; every reference list becomes a Dictionary with its values
> CSV; and the same evidence is re-expressed as data-quality expectations —
> format checks, allowed values, completeness baselines. Read the skip list
> with me, because it's a feature: every term that did NOT get a rule says
> why — a date has no value shape to detect, free text has no stable
> pattern, and a column whose values barely repeat needs a curated seed
> rather than a guessed one. No rule in this bundle is invented; every one
> traces to sampled evidence."*

- [ ] Import the JSONL in PDC (Glossary → Actions → Import).
- [ ] Back in the app: **Resolve term ids**.
- [ ] **Run Data Discovery on documents** (step 3 on the page) and let the
      PDC jobs finish — PDC mints the file-column *entities* and computes
      its file Data Quality. The app profiled these files at scan time;
      PDC has not, and until it does, document-column terms have nothing
      to link to (Apply reports them *not found*).
- [ ] **Apply terms**.

> **Talk track** — *"The catalog assigns every imported term its identity.
> Resolve looks each term up by name and stamps those ids back onto our
> rows. For the object store there's one catalog-side step: our scanner
> read inside those files at scan time — the catalog hasn't yet, so we
> ask it to run its own Data Discovery, which creates
> the file-column entities and scores file quality, its fourth
> Trust-Score input. Then Apply writes the term-to-column associations
> into the catalog — the moment the glossary stops being a document and
> starts being live metadata on real assets. From here the flywheel runs:
> rescan, review the delta, approve, re-export. The first pass is the
> project; every pass after it is maintenance."*

## Phase 7 — Closeout: the estate's deliverables, versioned

Everything this run produced should exist as a FILE, per estate, ready for
the Policy Generator and the next environment. Tick each artifact:

- [ ] **Import JSONL** — downloaded (and/or shipped to the lab store):
      glossary + categories + terms, the catalog's copy of record.
- [ ] **Registry** — written automatically at Generate (path shown in the
      summary): the machine-readable term↔column mapping the Policy
      Generator reads; what makes the next scan deterministic.
- [ ] **Domain pack** — `1 · Generate pack` → `3 · Install as this app's
      pack` (the flywheel turn) → `2 · Inspect / ship` the same file into
      the scenario repo's `domain_pack/` folder, so the next INSTALL starts
      from what this run taught.
- [ ] **Drafted policies bundle** — Data Patterns + Dictionaries (+ values
      CSVs) + DQ expectations, downloaded from the draft job (the job copy
      carries the AI polish). Skips reviewed: every remaining skip should
      read as a constraint (link-only kinds, curated-seed candidates), not
      a failure.
- [ ] **Resolve & Apply receipts** — resolve stamped ids; apply reported
      written/rated counts; "not found" investigated (document columns need
      step 3's Data Discovery to have run first).
- [ ] **Versioned** — the pack and bundle land in the scenario repo with a
      commit; the glossary name in PDC matches the intended one.

**Pass-check:** a colleague could rebuild this estate's governance from the
repo alone — pack, registry, policies, JSONL — without your workspace.

---

## When a pass-check fails

| Symptom | Usual cause | Where to look |
|---|---|---|
| Terms lack patterns/enums after upgrade | Grid scanned on an older build | Re-scan both sources — the merge absorbs new evidence, edits stand |
| Category count grows instead of shrinking | Pills from an older run, or unsettled physical groups | The delta line names it; reject/edit near-duplicate pills before approving |
| Whole pending queue flagged stale | Pre-1.36.60 build (health check couldn't see the live grid) | Upgrade; on current builds a first run shows zero stale |
| Window closed / page died | — | `app.log` in the state dir records backend and frontend errors |
| "No pills" from a large model | The clock, not the model | Raise the LLM timeout in Settings; first call after idle pays model load |
