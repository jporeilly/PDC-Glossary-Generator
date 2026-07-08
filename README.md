# PDC Glossary Generator

**Version:** 1.6.20 · validated against Pentaho Data Catalog 10.2.11

A local-first web app that **scans your data sources, suggests a business
glossary, lets a steward review and govern it, and exports import-ready JSONL**
for **Pentaho Data Catalog → Business Glossary → Import** — so the glossary and
its tags stay governed instead of drifting.

It automates the manual "analyse schema → identify terms → format for import"
workflow with a human-in-the-loop review step: suggested terms are proposals
(**Draft**), not approved governance, until a Business Steward signs off.

## Why — the Registry

In PDC the same three facts about a column — its business term, its tags, and
its sensitivity — get decided in more than one place, by hand. Nothing forces
them to agree, so vocabularies drift (`PII` vs `pii`) and classifications become
hard to defend in an audit.

This app maintains **one governed answer per concept**: a controlled two-layer
**Term & Tag dictionary** (generic baseline + steward-approved company layer),
and a **Classification Registry** written at export time
(`registries/registry.<glossary>.json`). A separate **Policy Generator** app
reads that Registry to build PDC's Data Identification methods, keeping tagging
consistent end-to-end. The full rationale is in
[CHALLENGE-AND-GOAL.md](glossary_generator/CHALLENGE-AND-GOAL.md).

## What it does

- **Connect** — live database scan (PostgreSQL, SQL Server, MySQL/MariaDB,
  Oracle), MinIO/S3 document stores, or a plain DDL file. Or skip direct access
  entirely and **harvest from what PDC has already cataloged**.
- **Review** — one suggested term per business-meaningful column, with inferred
  sensitivity, PII category, CDE flag, governed tags, and an evidence-based
  confidence signal. Edit everything inline; merge or disambiguate duplicates.
- **Govern** — steward/owner/custodian assignment (manual or keyword
  auto-assign from a Keycloak-fetched roster), ratings, review dates, and a
  steward approval gate over the vocabulary, with a full audit trail.
- **Generate & apply** — export the kept terms as PDC-importable JSONL, then
  resolve term ids and **apply term links, tags and sensitivity back onto PDC
  column entities** over the public API, ending with a Trust Score rollup.
- **Enrich (optional)** — rewrite definitions with a local **Ollama** model.
  Fully offline-safe: no Ollama, no problem — heuristic definitions remain.

## Repository layout

```text
glossary_generator/     the Flask app (app.py) + launchers (run.sh / run.ps1 / run.bat)
  suggester.py          core pipeline: harvest → suggest → JSONL (Flask-free)
  pdc_api.py            PDC public-API client (auth, harvest, bulk-load, apply)
  tagdict.py            two-layer Term & Tag dictionary with steward approval
  registry/             Registry writer (hooked into export)
  domain_packs/         scenario vocabularies (water-utility example included)
  courseware/           workshop document, slide deck, and topic notes
  diagrams/             architecture figures (PNG + SVG)
  README.md             app-level details (env vars, drivers, GPU/CPU, API table)
  GUIDE.md              full walkthrough of every page and workflow
  INSTALL.md            standing it up against your own PDC instance
```

## Install & run

**Requirements:** Python 3.9+ (or Docker). Everything runs locally; PDC and
Ollama are reached over the network only when you use those features.

### Linux / macOS

```bash
cd glossary_generator
./run.sh                     # venv + deps + run → http://127.0.0.1:5000
```

### Windows

```powershell
cd glossary_generator
.\run.ps1                    # → http://127.0.0.1:5000
```

(If PowerShell blocks the unsigned script, use `run.bat` or
`powershell -ExecutionPolicy Bypass -File .\run.ps1`.)

### Docker

```bash
cd glossary_generator
docker compose up --build    # state persists in the glossary-data volume
```

### Manual

```bash
cd glossary_generator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open **<http://127.0.0.1:5000>** and follow the workflow stepper:
*Connect → Review → Govern → Apply*.

### Optional: LLM enrichment

```bash
ollama pull llama3.2:3b      # or use the app's Pull model button
ollama serve                 # http://localhost:11434
```

The app detects Ollama automatically (on Windows set
`OLLAMA_URL=http://127.0.0.1:11434` — see the app README for why).

### Configuration

Copy [`.env.example`](glossary_generator/.env.example) to `.env` and edit —
every setting is optional. Two knobs adapt it to your scenario without code
changes: `GLOSSARY_COMPANY` (name woven into LLM prompts) and
`GLOSSARY_DOMAIN_PACK` (scenario vocabulary JSON — see
[domain_packs/README.md](glossary_generator/domain_packs/README.md)).

## Documentation

| Document | What it covers |
| --- | --- |
| [README.md](glossary_generator/README.md) | App details: env vars, drivers, Ollama/GPU, API reference |
| [GUIDE.md](glossary_generator/GUIDE.md) | Full walkthrough of every page and workflow |
| [INSTALL.md](glossary_generator/INSTALL.md) | Setup against your own PDC instance (Docker + local) |
| [CHALLENGE-AND-GOAL.md](glossary_generator/CHALLENGE-AND-GOAL.md) | The Registry thesis, plain language |
| [SUPPLEMENT.md](glossary_generator/SUPPLEMENT.md) | Operating notes for a real PDC instance |
| [CHANGELOG.md](glossary_generator/CHANGELOG.md) | Release history |
| [courseware/](glossary_generator/courseware/) | Workshop document and slide deck |

*All Arizona Water Company (AWC) data in the training scenario is fictional and
generated for training.*
