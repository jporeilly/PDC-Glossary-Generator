# Glossary Generator + Policy Generator — 1.6.4 assets

Complete, tested asset set. Validated against **Pentaho Data Catalog 10.2.11**.

## The model in one line

**Glossary Generator** creates the **Registry** → **Policy Generator** reads the
Registry and builds the Data Identification policy (dictionaries + patterns).

- **Glossary Generator** (app 1) — builds the business glossary; authors the Registry.
- **Registry** (artifact) — one row per concept: business term + term id, governed
  tags, sensitivity floor, category, verified references, method spec. Saved with
  the glossary.
- **Policy Generator** (app 2, formerly Method Advisor → Metadata Advisor →
  Classification Registry) — reads the Registry and emits the Data Identification
  methods (dictionary ZIPs + pattern JSON), keeps tagging consistent, fills coverage
  gaps, and runs the drift check.

## What's in this set

| File | What it is |
|---|---|
| `classification/` | The Policy Generator engine (Python package, v1.6.4). Registry, rules-first classifier + sensitivity floor, method emit, drift + reconcile, persistence, domain packs, description enrichment, CLI, self-test. |
| `Workshop-Glossary-Generator-1.6.4.docx` | The workshop guide. Opens with the challenge/goal + two-apps demarcation, then the workflow, then the architecture section. |
| `Glossary-Generator-1.6.4.pptx` | The session deck (24 original slides + a 5-slide architecture reference). |
| `CHALLENGE-AND-GOAL.md` | One-page steward/analyst explainer (challenge, goal, two apps). |
| `README.md` | Workshop supplement. |
| `INSTALL.md` | Install the Flask app against your own PDC instance. |
| `CHANGELOG.md` | Release notes (1.6.4 at top). |
| `awc-datasources.csv` | The two AWC Workshop 1 connections (PostgreSQL + MinIO), pre-filled for the bulk connection loader. Lab credentials — change for production; each needs Test Connection. |
| `diagrams/` | The five architecture diagrams + the challenge/goal figure, as PNG and editable SVG. |

## Test the code

```bash
pip install -r classification/requirements.txt

# offline self-test — no Ollama, no PDC needed (38 checks)
python -m classification selftest

# classify columns (rules-first + sensitivity floor)
python -m classification classify customer_id home_phone order_id account_balance

# overlay an industry pack (water utility example)
python -m classification scan columns.txt --pack classification/domain_packs/water_utility.example.json

# build the policy from the Registry (after term ids are reconciled)
python -m classification reconcile --columns columns.txt --methods method.json --term-ids ids.json
python -m classification drift method.json --term-ids ids.json
```

pytest wrapper: `python -m pytest classification/tests/ -q`.

## Preflight before production use

1. **Backfill `term_id`s** in the Registry as glossary terms are minted (until then
   concepts read `UNKNOWN`). The Registry persists with the glossary
   (`save_registry` / `load_registry`), so reconciled ids survive restarts.
2. **Confirm the method envelope** — the dictionary/pattern shapes are matched to real
   PDC exports; a user-created dictionary export would lock the last details. Dictionaries
   import as a **ZIP of JSON + CSV**; patterns as JSON.
3. **Align tag casing** to your PDC convention (the water example uses TitleCase concept
   tags + `PII`).
4. **Live paths not exercised offline:** Ollama residual classification and Keycloak/PDC
   reads need your environment.

## Notes

- **Generic by design.** The core Registry is industry-neutral (PII / PCI / PHI). Industry
  vocabulary loads from a domain pack (`CLASSIFICATION_DOMAIN_PACK`); the water-utility pack
  is one example — copy and swap for any sector, no code changes.
- The internal Python package is still importable as `classification` (the classification
  engine); the app it powers is **Policy Generator**.
- Diagrams were rendered with small polygon arrowheads. SVG sources are included if you
  want to re-style them.

*All AWC data in the training scenario is fictional and generated for training.*
