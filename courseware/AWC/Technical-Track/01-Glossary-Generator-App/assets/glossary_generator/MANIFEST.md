# Glossary Generator — complete 1.6.20 app

Unzips to **`glossary_generator/`**. The Flask app, with the **Registry writer**
hooked in at export time. The **Policy Generator** ships **separately** as its own
standalone app (`policy_generator/`). Validated against **PDC 10.2.11**.

## The model

**Glossary Generator** (this app) creates the **Registry** at export →
**Policy Generator** (separate app) reads it and builds the Data Identification
policy (dictionaries + patterns).

## Where the hand-off happens

`POST /api/generate` (glossary export) authors the Registry from the final reviewed
rows and writes **`registries/registry.<glossary>.json`** — one concept per kept
term: term name, governed tags, sensitivity, category, and a null `term_id`
(UNKNOWN until PDC mints ids and the Policy Generator's reconcile backfills them).
The response now includes a `registry` path.

## Layout

```
glossary_generator/
  app.py  run.sh  run.bat  run.ps1          the Flask app + launchers
  llm.py  pdc_api.py  dbconn.py  suggester.py  cli_suggester.py  build_roster.py  seed_sample.py
  templates/index.html
  registry/                                  ← app-side Registry WRITER (hooked at /api/generate)
     model.py  bridge.py  __init__.py  selftest.py
  registries/                                (created at runtime: registry.<glossary>.json)
  domain_packs/   people.json   datasources.sample.csv   awc-datasources.csv
  Dockerfile  docker-compose.yml  requirements.txt  .env.example  VERSION (1.6.20)
  courseware/   (workshop .docx, deck .pptx)
  diagrams/     (six figures, PNG + SVG)
  README.md  SUPPLEMENT.md  INSTALL.md  CHALLENGE-AND-GOAL.md  GUIDE.md  REVIEW.md  CHANGELOG.md
```

The **Policy Generator** is delivered separately as `policy_generator/` (its own zip):
the standalone engine that reads the Registry and emits/drift-checks the policy.

## Run the app

Local: `./run.sh` (or `run.bat` / `run.ps1`) → http://127.0.0.1:5000.
Docker: `docker compose up --build`. Full setup is in **`INSTALL.md`**.

## Test the Registry writer (offline)

```bash
python -m registry.selftest      # 11 checks — rows -> Registry mapping
```

## What the app does NOT contain

The classify / emit / drift / reconcile engine is **not** in the app — the app already
classifies via `suggester.py`, so its Registry half only *writes* the reviewed rows as
the artifact. All method-building lives in the separate **Policy Generator**.

*All AWC data in the training scenario is fictional and generated for training.*
