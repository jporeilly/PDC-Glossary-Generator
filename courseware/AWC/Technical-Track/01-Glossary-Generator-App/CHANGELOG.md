# Changelog

All notable changes to the **Glossary Generator** are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/); dates are ISO-8601.

---

## [1.6.4] — 2026-07-03

App renamed **Classification Registry -> Policy Generator** (named for its aim: it
reads the Registry and generates the Data Identification policy — dictionaries +
patterns). The middle artifact stays the **Registry**. Docs, workshop, one-pager
and the two-apps diagram updated.
- **`awc-datasources.csv`** added — the two AWC data-source connections (PostgreSQL +
  MinIO) pre-filled from Workshop 1, ready for the bulk connection loader.

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

## [1.5.7] — 2026-07-02

Reversible review controls and true per-group duplicate resolution — merge one name and
disambiguate another in the same pass, every choice reversible.

### Added
- **Reversible review controls.** *Keep High+Med conf*, *Merge duplicates* and
  *Auto-disambiguate* are toggles — they **highlight when applied** and **revert on a
  second click**. *Keep High+Med conf* reverts exactly the rows it changed (table terms
  are never touched); the merge/disambiguate buttons drive the per-group model below.
- **Per-group resolution, inline in the Review grid.** Each duplicate name gets a header
  row with a three-way **Merge / Disambiguate / Keep separate** control and its candidates
  clustered beneath it — **merge one name and disambiguate another at once**. The selected
  option is highlighted (dark) and reverts on a second click. **Detection is dynamic** —
  recomputed from current names over kept rows, so groups update live as you rename inline,
  cull with *Keep High+Med conf*, or apply names. Each choice is independently reversible.
- **Reset all** — returns the grid to the raw scan (filters, keeps, inline edits, and any
  per-group or global merge/disambiguate).

### Changed
- **Trimmed the keep toolbar.** Removed the redundant *Keep all shown*, *Keep none shown*
  and *Invert shown* buttons — the Keep-column header checkbox already keeps or clears all
  shown rows.

### Added (in-app aid)
- **Glossary-page “Under the hood” now covers Merge / Auto-disambiguate / Keep High+Med**
  as `LOCAL` (no-call) entries, alongside the existing database-SQL and S3-API hood panels.

### Fixed
- **Table terms are never grouped, merged, or deleted** — a table term keeps its own row
  even when it shares a name with a real duplicate group; the confidence cull already
  leaves it kept.
- **A Merge/Disambiguate survives a later LLM enrich** — enrichment preserves the row's
  resolution tag, id, and keep state, so you can apply the LLM after resolving duplicates.

### Files touched
- `templates/index.html` — `snapshotScan` (raw-scan snapshot + `_grp` tagging),
  `groupSetKey` / `groupSetIdx` / `_dispKey` / `_collisionInfo` / `_groupHeadTr` (dynamic inline headers),
  `toggleHM` / `toggleMerge` / `toggleDisambig` / `resetAll`, panel markup + CSS.
- `VERSION` — 1.5.6 → 1.5.7.

### Note
- `glossary-review-prune-prototype.html` remains the interaction reference; what it
  previewed now ships in the app.

---

## [1.5.6] — 2026-07-02

Table terms are protected from the confidence cull, the enrichment endpoint no
longer crashes on a null row, and the bundled AWC pack gives every table term a
`Record` suffix.

### Fixed
- **`/api/enrich` returned 500** (`AttributeError: 'NoneType' object has no attribute
  'get'` at `llm.py` → `enrich_rows`). A `None`/blank row slipped past the
  `only_low_confidence` filter (short-circuit evaluation) and was dereferenced.
  `enrich_rows` now drops non-dict rows up front, and the `enrich()` view filters the
  payload to dict rows.
- **Table-level terms were dropped by *Keep High+Med conf*.** A table term carries a
  blank `Confidence` (it is conceptual, not a column match), so the confidence cull set
  its Keep to false. Table terms are now **kept by default and exempt from the cull** —
  `bulkKeep('hm')` skips them via a new `isTableTerm(r)` test (empty `Source_Column`
  plus the `table-level` tag or a `Record`-suffixed name). Only an explicit steward
  action (Keep none / untick) removes one.

### Changed
- **Bundled `water_utility.example.json`** — every table term now ends in **“Record”**
  (`Customer Record`, `Water System Record`, `Rate Plan Record`, `Monthly Usage
  Record`, `Water Quality Record`, `Account Alert Record`), matching the app's
  `<Singular> Record` derivation so table terms have a stable, recognisable shape.

### Files touched
- `llm.py` — `enrich_rows` sanitises rows.
- `app.py` — `enrich()` filters the payload to dict rows.
- `templates/index.html` — `isTableTerm()` helper; `bulkKeep('hm')` exempts table terms.
- `domain_packs/water_utility.example.json` — Record-suffixed table terms.
- `VERSION` — 1.5.5 → 1.5.6.

### Docs
- Workshop **“Build the glossary in the app” → Step 2** covers the review controls and
  the *table terms are always kept* rule.
- `README.md` / `INSTALL.md` updated.

---

## [1.5.5] — 2026-06-30 — Duplicate-term review panel (+ Windows host support)

- Per-group duplicate-review panel on the Generate page; native Windows launcher
  (`run.ps1` / `run.bat`), hardware/VRAM probe, and a model dropdown that reflects the
  local Ollama. (See the bundled `CHANGELOG.md` for the full 1.5.5 detail.)

## [1.5.x] — earlier (summary)

- **Dockerised deployment** (`Dockerfile` / `docker-compose.yml`, `glossary-data`
  volume, port 5000).
- **Scenario-generic build** — no baked-in vocabulary; configured per client via a
  **domain pack** (`GLOSSARY_DOMAIN_PACK`) plus **`GLOSSARY_COMPANY`**.
- **Public-API apply pipeline** — authenticate, resolve imported term IDs, apply
  term↔column links with a mandatory **dry-run**, Trust Score last.
