# PDC Glossary Generator

**Version:** 1.7.0 · validated against Pentaho Data Catalog 10.2.11

A local-first web app that **scans your data sources, suggests a business
glossary, lets a steward review and govern it, and exports import-ready JSONL**
for **Pentaho Data Catalog → Business Glossary → Import** — so the glossary and
its tags stay governed instead of drifting.

The app is **scenario-generic**; two complete, fully separated training
scenarios ship with it, each with its own lab stack, domain pack and courseware:

| Scenario | Industry | Lab kit | Courseware |
| --- | --- | --- | --- |
| **CSCU** — Copper State Credit Union | Financial services | [data_sources/CSCU/](data_sources/CSCU/) | [courseware/CSCU/](courseware/CSCU/) |
| **AWC** — Arizona Water Company | Water utility | [data_sources/AWC/](data_sources/AWC/) | [courseware/AWC/](courseware/AWC/) |

## Why — the Registry

In PDC the same three facts about a column — its business term, its tags, and
its sensitivity — get decided in more than one place, by hand. Nothing forces
them to agree, so vocabularies drift (`PII` vs `pii`) and classifications become
hard to defend in an audit.

This app maintains **one governed answer per concept**: a controlled two-layer
**Term & Tag dictionary** (generic baseline + steward-approved company layer),
and a **Classification Registry** written at export time
(`registries/registry.<glossary>.json`).

![Two apps, one handoff — Glossary Generator writes the Registry, Policy Generator reads it](glossary_generator/diagrams/two-apps.png)

The Registry is the **contract between two separate apps**, used in order —
mirroring PDC's own split between the Business Glossary and Data
Identification:

1. **Glossary Generator** (this repo) builds the business glossary: it scans
   sources, proposes concepts, lets the steward review them, and produces the
   JSONL you import into PDC (which mints the term ids). As a by-product of
   export it **authors the Registry** — one row per concept with the business
   term, governed tags (from a controlled allow-list), rule-based sensitivity,
   and category.
2. **Policy Generator** (a separate app, shipped independently) **reads the
   Registry** — with the term ids reconciled after import — and emits PDC's
   Data Identification methods: dictionaries (ZIP) and patterns (JSON), each
   bound to its term and stamping the Registry's tags. It also drift-checks
   deployed methods against the Registry.

Because both apps draw from the same row, the glossary term, the tags a method
stamps, and the sensitivity can no longer quietly diverge. The full rationale
is in [CHALLENGE-AND-GOAL.md](docs/CHALLENGE-AND-GOAL.md), and the other
workshop figures are in [diagrams/](glossary_generator/diagrams/).

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
glossary_generator/     the app (scenario-generic): Flask API + review UI
docs/                   all documentation (reference, guide, install, changelog, …)
data_sources/           lab kits — one folder per scenario (AWC, CSCU), each with
                        docker-compose + Makefile, sample DB, MinIO documents,
                        domain pack + install zip, bulk-load CSV
courseware/             two complete workshop sets — AWC and CSCU
install-scenario.sh     scenario picker/installer (install-scenario.ps1 on Windows)
reset-scenario.sh       remove the installed scenario / reset the app to generic
```

## Install & run

**Requirements:** Python 3.9+ (or Docker). Everything runs locally; PDC and
Ollama are reached over the network only when you use those features.

### 1. Pick a scenario

```bash
./install-scenario.sh            # lists AWC / CSCU, installs the pack + roster
# Windows: .\install-scenario.ps1
```

This copies the selected scenario's vocabulary (`domain_pack.json`), steward
roster (`people.json`) and company name (`.env`) into the app's runtime config
— all git-ignored, so the app itself stays clean. One scenario at a time.
(Equivalent manual step: unzip `data_sources/<scenario>/*-domain-pack.zip`
into `glossary_generator/`.) To switch scenarios, just rerun it; to remove the
scenario and reset the app to generic, run `./reset-scenario.sh`
(`-All` / `--all` also clears connections, settings and saved glossaries).

### 2. Stand up the lab sources

```bash
cd data_sources/CSCU             # or AWC
cp .env.example .env
make all                         # postgres + minio, loaded and verified
```

### 3. Run the app

```bash
cd glossary_generator
./run.sh                         # Linux/macOS → http://127.0.0.1:5000
.\run.ps1                        # Windows (or run.bat)
docker compose up --build        # Docker
```

Then open **<http://127.0.0.1:5000>** and follow the workflow stepper:
*Connect → Review → Govern → Apply*. The scenario's workshop guide is in
`courseware/<scenario>/`.

### Optional: LLM enrichment

```bash
ollama pull llama3.2:3b      # or use the app's Pull model button
ollama serve                 # http://localhost:11434
```

The app detects Ollama automatically (on Windows set
`OLLAMA_URL=http://127.0.0.1:11434` — see [REFERENCE.md](docs/REFERENCE.md)
for why). Configuration beyond that: copy
[`.env.example`](glossary_generator/.env.example) to `.env` — every setting is
optional.

## Documentation

| Document | What it covers |
| --- | --- |
| [REFERENCE.md](docs/REFERENCE.md) | App details: env vars, drivers, Ollama/GPU, API reference |
| [GUIDE.md](docs/GUIDE.md) | Full walkthrough of every page and workflow |
| [INSTALL.md](docs/INSTALL.md) | Setup against your own PDC instance (Docker + local) |
| [CHALLENGE-AND-GOAL.md](docs/CHALLENGE-AND-GOAL.md) | The Registry thesis, plain language |
| [SUPPLEMENT.md](docs/SUPPLEMENT.md) | Operating notes for a real PDC instance |
| [MANIFEST.md](docs/MANIFEST.md) | Full repository layout and packaging |
| [CHANGELOG.md](docs/CHANGELOG.md) | Release history |
| [data_sources/](data_sources/) | The two lab kits (AWC · CSCU) |
| [courseware/](courseware/) | The two workshop sets (AWC · CSCU) |

*All scenario data — Arizona Water Company and Copper State Credit Union — is
fictional and generated for training.*
