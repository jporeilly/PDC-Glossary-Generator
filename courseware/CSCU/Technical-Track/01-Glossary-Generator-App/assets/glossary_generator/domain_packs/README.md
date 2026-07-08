# Domain packs

A domain pack injects scenario-specific vocabulary into the suggestion engine so the
core stays generic. Point the app at one with:

    GLOSSARY_DOMAIN_PACK=domain_packs/water_utility.example.json

or (the default) drop a file named `domain_pack.json` beside `suggester.py`. If
`GLOSSARY_DOMAIN_PACK` is unset, the app loads `./domain_pack.json` automatically.

A pack is read by **two** engines, each picking out its own keys from the same file —
so a complete pack carries both sets:

## Categorization & naming (read by `suggester.py`)

| Key | Purpose |
|---|---|
| `table_category` | Category assigned to table-level (conceptual) terms |
| `table_terms` | Table-name → business-term overrides |
| `cat_keywords` | List of `[keyword, category]` — routes column/term names to a category |
| `abbreviations` | Expansion map for abbreviations in names |
| `category_definitions` | Default definition text per category |

## Governed tag vocabulary (read by `tagdict.py`)

| Key | Purpose |
|---|---|
| `category_tags` | `{category: [tags]}` — the tag(s) every term in a category gets |
| `tag_rules` | List of `{pattern, tags}` — regex on a term's name/term/category adds governed tags. **This is how you give a domain meaningful tags** (e.g. `gis` → `gis;spatial;asset`). Pack rules are **company-layer and pre-approved**. |
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

`water_utility.example.json` reproduces the Arizona Water (AWC) vocabulary — both the
categorization keys and the governed tag rules — and matches the default `domain_pack.json`.
