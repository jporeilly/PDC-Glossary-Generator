# Glossary Generator — repository manifest (1.7.2)

The Flask app, with the **Registry writer** hooked in at export time, plus the
**Copper State Credit Union (CSCU)** training scenario (additional scenarios
plug in as data folders). The **Policy Generator** ships
**separately** as its own standalone app (`policy_generator/`). Validated
against **PDC 10.2.11**.

## The model

**Glossary Generator** (this repo) creates the **Registry** at export →
**Policy Generator** (separate app) reads it and builds the Data Identification
policy (dictionaries + patterns).

## Where the hand-off happens

`POST /api/generate` (glossary export) authors the Registry from the final reviewed
rows and writes **`registries/registry.<glossary>.json`** — one concept per kept
term: term name, governed tags, sensitivity, category, and a null `term_id`
(UNKNOWN until PDC mints ids and the Policy Generator's reconcile backfills them).
The response includes a `registry` path.

## Layout

```text
PDC-Glossary/
  README.md                     repo landing page
  docs/                         all documentation
    REFERENCE.md                app reference (env vars, drivers, LLM/GPU, API table)
    GUIDE.md                    full walkthrough of every page and workflow
    INSTALL.md                  stand it up against your own PDC instance
    SUPPLEMENT.md               operating notes for a real PDC instance
    CHALLENGE-AND-GOAL.md       the Registry thesis, plain language
    REVIEW.md                   code review & PDC v3 compatibility notes
    CHANGELOG.md                release history
    MANIFEST.md                 this file
  glossary_generator/           the app (scenario-generic)
    app.py  run.sh  run.bat  run.ps1
    llm.py  pdc_api.py  dbconn.py  suggester.py  cli_suggester.py
    build_roster.py  seed_sample.py  audit.py  similarity.py  tagdict.py
    templates/index.html
    registry/                   app-side Registry WRITER (hooked at /api/generate)
    registries/                 (created at runtime: registry.<glossary>.json)
    domain_packs/README.md      pack format reference (packs live per scenario)
    diagrams/                   six figures, PNG + SVG
    datasources.sample.csv      generic bulk-load starter CSV
    Dockerfile  docker-compose.yml  requirements.txt  .env.example  VERSION
  data_sources/                 scenario data + the shared lab
    lab/                        SHARED stack: one PostgreSQL + one MinIO for all
                                scenarios (make load SCENARIO=<ID> creates that
                                scenario's database + bucket + documents)
    CSCU/                       Copper State Credit Union (financial) — data only
      postgres-init/  cscu-documents/  domain_pack/
      cscu-domain-pack.zip  cscu-datasources.csv  scenario.json
  courseware/
    CSCU/                       workshop guides (markdown masters) + topic notes
```

The **Policy Generator** is delivered separately as `policy_generator/` (its own zip):
the standalone engine that reads the Registry and emits/drift-checks the policy.

## Run the app

Local: `./run.sh` (or `run.bat` / `run.ps1`) → http://127.0.0.1:5000.
Docker: `docker compose up --build`. Full setup is in **`INSTALL.md`**.

## Install a scenario

Unzip the scenario's pack into `glossary_generator/`
(`data_sources/CSCU/cscu-domain-pack.zip`), delete any previous
`tag_dictionary.json`, restart. **One scenario at a time.**

## Test the Registry writer (offline)

```bash
python -m registry.selftest      # rows -> Registry mapping checks
```

## What the app does NOT contain

The classify / emit / drift / reconcile engine is **not** in the app — the app already
classifies via `suggester.py`, so its Registry half only *writes* the reviewed rows as
the artifact. All method-building lives in the separate **Policy Generator**.

*All scenario data is fictional and generated for training.*
