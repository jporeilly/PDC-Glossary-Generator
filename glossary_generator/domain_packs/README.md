# Domain packs

A domain pack injects scenario-specific vocabulary into the suggestion engine so the
core stays generic. Point the app at one with:

    GLOSSARY_DOMAIN_PACK=domain_packs/credit_union.example.json

or (the default) drop a file named `domain_pack.json` beside `suggester.py`. If
`GLOSSARY_DOMAIN_PACK` is unset, the app loads `./domain_pack.json` automatically.

A pack is read by **two** engines, each picking out its own keys from the same file —
so a complete pack carries both sets:

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
