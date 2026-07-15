# Domain packs

A domain pack injects scenario-specific vocabulary into the suggestion engine so the
core stays generic. Point the app at one with:

    GLOSSARY_DOMAIN_PACK=domain_packs/credit_union.example.json

or (the default) drop a file named `domain_pack.json` beside `suggester.py`. If
`GLOSSARY_DOMAIN_PACK` is unset, the app loads `./domain_pack.json` automatically.

A pack is read by **three** engines, each picking out its own keys from the same file —
so a complete pack carries all three sets:

## Categorization & naming (read by `suggester.py`)

| Key | Purpose |
| --- | --- |
| `table_category` | Category assigned to table-level (conceptual) terms |
| `table_terms` | Table-name → business-term overrides |
| `cat_keywords` | List of `[keyword, category]` — routes column/term names to a category |
| `abbreviations` | Expansion map for abbreviations in names |
| `category_definitions` | Default definition text per category |

## Governed tag vocabulary (read by `tagdict.py`)

| Key | Purpose |
| --- | --- |
| `category_tags` | `{category: [tags]}` — the tag(s) every term in a category gets |
| `tag_rules` | List of `{pattern, tags}` — regex on a term's name/term/category adds governed tags. **This is how you give a domain meaningful tags** (e.g. `chargeback` → `fraud;payments`). Pack rules are **company-layer and pre-approved**. |
| `extra_tags` | Tag names to add to the governed allow-list (pre-approved) |
| `terms` | Seed governed terms `{name: {aliases, sensitivity, tags, …}}` |

All keys are optional; values **extend/override** the generic built-ins, and tags stay
within the governed allow-list (no drift).

### Applying changes

The dictionary is seeded once and then persisted (`tag_dictionary.json`). After editing a
pack, **reseed** so the changes take effect:

1. App → **Dictionary** page → **Reseed** (or delete `tag_dictionary.json` and restart).
2. On the **Glossary** grid → **Suggest tags** to re-derive tags for the current rows.

Tags are governed vocabulary, **not** LLM output — so *Enrich with LLM* won't change them;
the domain pack is how you enrich the tag set.

## The pack generator — packs evolve from scan results (1.8.17)

Packs don't have to stay hand-authored. After a full scan + review cycle,
**Dictionary → Export domain pack** exports the reviewed state back into pack
format — the flywheel:

    shipped pack → scan → review/approve → Export domain pack → next install
    starts from evidence, not guesses

What it learns: `table_category`/`table_terms` from the reviewed rows,
`cat_keywords` from table tokens, **abbreviations** by aligning column tokens
with term words (`mbr_no` + "Member Number" → `mbr: Member`, 2+ sightings),
the **governed company vocabulary** (approved items only), and
**`curated_seeds`** carrying the induced value patterns and profiled
reference lists per term — detection seeds specific to this company's data.

Semantics: **merge, never silently overwrite** — learned content fills gaps
and adds new entries, and where the scan **disagrees** with the installed pack
the conflict is listed (pack value vs scan value) with a checkbox per row, so
the steward decides each one. Defaults: curation-bearing keys keep the pack's
value (a steward's recorded decision beats the machine's newest opinion);
**`curated_seeds` prefer the scan** — those entries are machine-derived
evidence in the first place, so fresher profiling wins and the replaced seed
stays visible in the conflict list. Term entries take safe unions (aliases
and tags union in; sensitivity tightens automatically, and a *loosening* is
surfaced as a conflict rather than applied or dropped). Two ways to use the
result:

1. **Apply to this app** (one click, confirmed): writes the refreshed pack
   over the installed `domain_pack.json` (timestamped backup) and reseeds the
   dictionary — approved company items and rules survive the reseed.
2. **Commit it** to the scenario's `domain_pack/` folder (PDC-Scenarios) so
   every future install starts from the evolved pack. Do this even after
   applying locally — an uncommitted improvement dies with the install.

### Starting from nothing (bootstrapping a base pack)

You don't need to hand-author a pack for a new company or scenario. Run the
app **packless** (the built-in generic defaults still route obvious columns),
do one scan → review → govern cycle, then **Export domain pack**: with no
installed pack to merge over, the export *is* your first base pack —
table mappings, learned abbreviations, the approved vocabulary, and
company-specific detection seeds, all from evidence. Commit it as the
scenario's pack and every later cycle refines it through the merge above.

## Shipped packs

Scenario packs ship with their scenario, not with the app (the app stays clean):

- **Copper State Credit Union (CSCU)** — financial services (members, accounts,
  cards, lending, BSA/AML compliance, general ledger):
  `data_sources/CSCU/domain_pack/credit_union.example.json` +
  `credit_union.people.json` (the steward roster seed).
- **Canyon Trail Outfitters (CTO)** — retail (loyalty customers, merchandising,
  inventory, orders, payments/PCI, loss prevention):
  `data_sources/RETAIL/domain_pack/retail.example.json` + `retail.people.json`.
- **Lakeshore Health Partners (LHP)** — healthcare (patients/PHI, encounters,
  diagnoses & results, prescriptions, claims, HIPAA disclosures):
  `data_sources/HEALTH/domain_pack/healthcare.example.json` +
  `healthcare.people.json`.
- **Cascade Precision Components (CPC)** — manufacturing (parts/BOM, ASL
  suppliers, work orders, lot traceability, NCR/MRB, shipments — the non-PII
  contrast): `data_sources/MFG/domain_pack/manufacturing.example.json` +
  `manufacturing.people.json`.

Install one with `install-scenario.ps1` / `install-scenario.sh` (or unzip the
scenario's `*-domain-pack.zip` into `glossary_generator/`), then reseed.
Additional scenario packs plug in the same way: a `data_sources/<ID>/domain_pack/`
folder plus a `scenario.json` manifest. Don't mix scenarios: install one pack at a
time and reseed.

## Curated detection seeds (read by `registry/bridge.py` at Generate time)

| Key | Purpose |
| --- | --- |
| `curated_seeds` | `{term_name: seed}` (or a list of seeds) — vetted canonical shapes and reference lists for concepts the scan can't induce. Each seed is `{type: "pattern", regex, signature?}` or `{type: "dictionary", values: [...]}`. At Generate, seeds are merged into the Registry's `concepts[].detect` with `source: "curated"` — **profiled evidence always wins** over a curated seed of the same type. This is how a custom-only identification program covers the shapes PDC's built-ins would otherwise handle (SSN, email, phone, service cities): the seed lives in the versioned pack, so the Policy Generator's authored method is fully tracked and auditable. |
