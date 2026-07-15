# Glossary Generator — app reference

> **What's new (1.6.4 → 1.6.20):** bulk data-source loader (create → metadata
> ingest → poll) and saved-connection CSV export; meaningful controlled tags and
> locked table terms; a persisted two-layer **Term & tag dictionary** (generic
> baseline + editable company layer) with guard-railed edits, a steward approval
> gate, and a sensitivity lift; the **Registry** now embeds the governed vocabulary
> so the Policy Generator's Data Identification tags stay consistent; plus a
> "ready for the Policy Generator" hand-off indicator. Since 1.6.12: the Dictionary
> is its own page with scan-time alias resolution; a search-facet preview; a steward
> audit trail; similarity-scored suggested merges (**Find similar**); a multi-select
> **Harvest from PDC** picker that scales to 100+ sources; installable scenario
> domain packs; and non-destructive **Enrich** with **↶ Revert enrich**. Since 1.7.0
> the workshop scenario is **Copper State Credit Union** (financial services) — see
> `CHANGELOG.md` and the CSCU workshop in the PDC-Scenarios repo
> (`courseware/CSCU/Glossary/Workshop-Glossary-Generator-CSCU.md`).
>
> **Integrations:** a consolidated read-only `GET /api/governance-summary` exposes
> vocabulary health (governed vs pending, the tag facet, empty + fragmenting tags),
> the steward audit summary, and drift (off-vocabulary tags across written registries)
> in one CORS-enabled payload — so Catalog Insights / a visualization app can just poll
> it. Full audit trail at `GET /api/audit` and `GET /api/audit/export.json`.

A local-first web app that **scans a relational source, suggests a business
glossary, lets a steward review it, and exports import-ready PDC glossary JSONL**
— with optional definition enrichment from a local **Ollama** model.

It automates the manual "analyse schema → identify terms → format for import"
workflow, with a human-in-the-loop review step. Suggested terms are written with
status **Draft**: they are proposals, not approved governance, until a Business
Steward signs off.

For the full walkthrough — architecture, how each stage works, the heuristics,
the LLM prompt, the import path, teaching notes, and extension points — see
**GUIDE.md**.

---

## Layout

```text
glossary_generator/
  app.py                  Flask API + serves the UI
  suggester.py            core: harvest -> suggest -> JSONL (importable, no Flask)
  dbconn.py               driver-aware DB connections + test + driver status
  llm.py                  Ollama client: definition enrichment + model pull
  pdc_api/                PDC Public API client (core/entities/terms/jobs/apply/bulkload)
  templates/index.html    single-page UI (markup only)
  static/style.css        the UI stylesheet
  static/js/00..12-*.js   the UI logic, split per area, loaded in numbered order
  cli_suggester.py        headless CLI version of the pipeline
  run.sh                  Linux/macOS launcher (venv + deps + run)
  run.ps1 / run.bat       Windows launcher (PowerShell; .bat wrapper)
  requirements.txt
docs/                     this reference + GUIDE, INSTALL, SUPPLEMENT, ...
PDC-Scenarios repo        every vertical's data kit, domain pack and courseware
  data_sources/lab/       SHARED PostgreSQL + MinIO for all scenarios
  data_sources/<ID>/      scenario data + installable domain pack
  courseware/<ID>/        workshop guides and topic notes per scenario
```

The core (`suggester.py`, `dbconn.py`, `llm.py`) is Flask-free and importable, so
the same logic backs the web app, the CLI, and any unit tests.

---

## Install & run

```bash
cd glossary_generator
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000
```

Open the URL, point **DDL path** at a schema file (or pick **Database** and fill
the connection form), then **Scan & suggest**.

| Env          | Default                                          | Purpose                        |
|--------------|--------------------------------------------------|--------------------------------|
| `HOST`       | `127.0.0.1`                                      | bind address                   |
| `PORT`       | `5000`                                           | bind port                      |
| `GLOSSARY_DDL` | `/mnt/user-data/uploads/01-schema-and-data.sql`  | default DDL when none supplied |
| `LLM_MODEL`  | `llama3.1`                                        | Ollama model name              |
| `OLLAMA_URL` | `http://localhost:11434`                         | Ollama server URL              |
| `LLM_TIMEOUT`| `30`                                             | seconds per generation         |

---

## Running on Ubuntu 24.04 (Noble)

Runs as-is on Ubuntu 24.04 (Python 3.12). Two Noble-specific notes:

**1. Use a venv (PEP 668).** Noble blocks `pip install` into the system Python
("externally-managed-environment"). Use a virtual environment:

```bash
sudo apt update && sudo apt install -y python3-venv
cd glossary_generator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py                       # http://127.0.0.1:5000
```

(Alternatively `pip install -r requirements.txt --break-system-packages`, but a
venv is cleaner.) `psycopg2-binary` installs from a prebuilt wheel — no compiler
or `libpq-dev` needed. The other engine drivers (`pymysql`, `oracledb`, `pymssql` — installed by default since 1.6.20)
also install cleanly on Noble.

**2. Ollama as a systemd service** (optional — only for LLM enrichment):

```bash
curl -fsSL https://ollama.com/install.sh | sh      # installs + starts the service
ollama pull llama3.1                               # or use the app's Pull model button
```

This is where the GPU/CPU policy lives (see "GPU vs CPU"): set it on the service,
not on the app —

```bash
sudo systemctl edit ollama
#   [Service]
#   Environment="CUDA_VISIBLE_DEVICES=0"     # pin GPU 0  (or OLLAMA_NUM_GPU=0 for CPU-only)
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

For GPU acceleration, install the NVIDIA driver (535+ on Linux) first; without a
GPU, Ollama runs CPU-only and the status pill will read `100% CPU`. The preview
renderer (`wkhtmltoimage`) is not needed to run the app, but is available via
`sudo apt install wkhtmltopdf` if you want it.

## Running on Windows 11

Runs natively on Windows — the code is pure Python with no POSIX-only imports.
Use the PowerShell launcher instead of `run.sh`:

```powershell
cd glossary_generator
.\run.ps1                     # http://127.0.0.1:5000
.\run.ps1 -Port 8080          # choose a port
.\run.ps1 -PyVersion 3.12     # force a Python (see note below)
```

If PowerShell blocks the unsigned script the first time, use the **`run.bat`**
wrapper, or run once with `powershell -ExecutionPolicy Bypass -File .\run.ps1`.
Permanent fix on a dev box: `Unblock-File .\run.ps1` then
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**Python version.** `run.ps1` prefers a wheel-friendly interpreter
(3.13 → 3.12 → 3.11 → newest). A brand-new Python (e.g. 3.14) may have no prebuilt
`psycopg2-binary` wheel yet, forcing a source build that fails without a C
compiler — the launcher steers around that, and `-PyVersion 3.12` forces a
specific one. `.venv` is rebuilt automatically if the interpreter changes.

**Hardware / model sizing.** Pre-flight reads GPU VRAM (`nvidia-smi`, then the
registry `qwMemorySize`, then CIM) and prints `ollama pull` suggestions matched to
your VRAM.

**Ollama.** On Windows `localhost` can resolve to IPv6 `::1` and miss Ollama's
IPv4 bind, so point the app at the v4 address in `.env`:

```
OLLAMA_URL=http://127.0.0.1:11434
```

The header pill and the model dropdown (which lists your *installed* models) both
depend on the app reaching Ollama, so this also populates the picker.

### Connecting to Postgres / MinIO running in Docker (app on the host)

With the app running natively on Windows and your database or object store in
Docker, reach them through the **ports Docker publishes to the host** — not the
container names or internal ports (those only work container-to-container). Use
`127.0.0.1` and the host-side port from your compose `ports:` mapping:

- **PostgreSQL** — Host `127.0.0.1` (not `localhost`, same IPv6 reason), Port = the
  left side of the mapping (e.g. `5433` if you mapped `5433:5432`), then database /
  user / password. The Host field is a plain hostname — never a URL, no `http://`.
- **MinIO** — Endpoint `http://127.0.0.1:9000` (the S3 API port; `9001` is the web
  console, not the API), plus access key / secret and bucket.

Check what's published with `docker compose ps` (or `docker ps` →
`0.0.0.0:5433->5432/tcp`). If a container has no `ports:` entry the host can't see
it — add one (e.g. `5433:5432`) and `docker compose up -d`. A remote PDC at a
hostname such as `pentaho.io` is a *separate* connection (the PDC base URL); it is
not where your local Docker Postgres/MinIO live.

## Workflow

1. **Scan & suggest** — parses tables/columns/keys/comments and proposes one term
   per business-meaningful column, grouped into categories, with inferred
   sensitivity, PII category, CDE flag, abbreviation, and tags.
2. **Review** — edit any cell inline; untick **Keep** to drop a term. Confidence
   and the source column guide pruning. Nothing is auto-published.
3. **Enrich with LLM** *(optional)* — rewrites definitions via Ollama. Safe if
   Ollama is offline (keeps the heuristic text). Enriched rows show an `LLM` tag.
4. **Generate JSONL** — emits `Suggested-Glossary.jsonl` (only `Keep=Y` rows)
   for **Business Glossary -> Actions -> Import**.

---

## Governed tags & the domain pack

Tags on the review grid are **governed vocabulary**, not LLM output — they're derived
deterministically from a controlled allow-list plus name/term rules, so they can't drift
(this is the whole point of the Classification Registry thesis). The generic baseline
covers common patterns (billing, usage/metering, contact, location, compliance, …);
scenario-specific tags come from a **domain pack**.

If a set of terms is only getting a bare category tag (e.g. document-store folders all
tagged just `document`), that means the domain has no matching rule yet — extend the pack
rather than reaching for the LLM. Edit `domain_pack.json` (loaded by default, beside
`suggester.py`) and add a `tag_rules` entry:

```json
"tag_rules": [
  { "pattern": "\\bgis\\b|geospatial|spatial|parcel", "tags": ["gis", "spatial", "asset"] },
  { "pattern": "scada|telemetry|\\brtu\\b|sensor",     "tags": ["scada", "operational", "telemetry"] }
]
```

Pack `tag_rules` are company-layer and pre-approved (governed). Then **apply**:

1. **Dictionary** page → **Reseed** (reloads the vocabulary from the pack).
2. **Glossary** grid → **Suggest tags** (re-derives tags for the current rows).

The app ships **generic** — install a scenario pack to get one: unzip
PDC-Scenarios' `data_sources/CSCU/cscu-domain-pack.zip` (Copper State Credit Union — cards/PCI, ACH,
KYC/AML, lending, ledger rules) into the app folder. See `domain_packs/README.md`
for the full pack schema (categorization keys *and* tag keys), and
PDC-Scenarios' `data_sources/CSCU/domain_pack/credit_union.example.json` for a complete example.

---

## Connecting to a live database

Pick source **Database (live scan)** to open the connection form: engine, host,
port (auto-filled per engine), database, schema, user, password, SSL. **Test
connection** verifies before you scan.

### Drivers (the "download driver" step)

This app scans through **Python DB-API drivers**, not JDBC:

| Engine            | Python driver | Install                   | PDC JDBC jar (Manage Drivers) |
|-------------------|---------------|---------------------------|-------------------------------|
| PostgreSQL        | `psycopg2`    | ships (`psycopg2-binary`) | `postgresql-42.7.x.jar`       |
| SQL Server        | `pymssql`     | ships (`pymssql`)         | `mssql-jdbc` / `sqljdbc`      |
| MySQL / MariaDB   | `pymysql`     | ships (`pymysql`)         | `mysql-connector-j` / mariadb |
| Oracle            | `oracledb`    | ships (`oracledb`, thin)  | `ojdbc11.jar`                 |

The **Drivers** panel (top-right button) shows live install status per engine and
the exact `pip` command for any that are missing. All four drivers install with the app by default (since 1.6.20); the panel confirms live status — useful after a manual/venv install that skipped one.

> Loading the same source into **PDC** is a separate step: PDC ships no JDBC
> drivers, so you upload the vendor jar via **Manage Drivers -> Add New ->** pick
> the database type -> drag-and-drop the jar (last column above). The lab image
> has built-in PostgreSQL support.

`suggester.harvest_live(cfg)` takes the connection dict the form builds and reads
columns, keys, and comments from `information_schema` (PostgreSQL also pulls
`pg_description` column comments).

---

## LLM enrichment & model download

The app works fully **without** an LLM (heuristic definitions). To improve
definitions with a local model:

```bash
ollama pull llama3.1
ollama serve                       # http://localhost:11434
```

You don't have to pull from a shell — the app manages the model:

- The header pill detects whether your chosen model is present in Ollama.
- If it's missing, a **Pull model** button appears; clicking it streams the
  download (progress bar) from the Ollama registry **to your local Ollama** —
  nothing routes through the app host.
- Cancelled pulls resume automatically.

Override the model in the toolbar field at runtime, or with `LLM_MODEL`.

### GPU vs CPU — owned by the Ollama server

Whether inference runs on GPU or CPU is decided by the **Ollama server's
environment and hardware**, set when `ollama serve` starts — not by this app and
not per request. So the app's job is to *detect and show* where the model
actually runs, and offer a soft offload preference on top.

**Set it in the server's OS environment** (the real control):

```bash
OLLAMA_NUM_GPU=0 ollama serve          # force CPU-only
CUDA_VISIBLE_DEVICES=-1 ollama serve   # hide all GPUs (CPU-only)
CUDA_VISIBLE_DEVICES=0 ollama serve    # pin to GPU 0
```

```bash
# durable (systemd):
sudo systemctl edit ollama
#   [Service]
#   Environment="OLLAMA_NUM_GPU=0"        # or CUDA_VISIBLE_DEVICES=0
sudo systemctl daemon-reload && sudo systemctl restart ollama
```

**What the app shows / does:**

- The status pill reports the **detected placement** from Ollama's `/api/ps`
  (the same data as `ollama ps`): `Ollama · llama3.1 · 100% GPU`, `· 100% CPU`,
  or a split like `· 22%/78% CPU/GPU` when a model is too big for VRAM.
- The **GPU offload** toggle is a *soft per-request preference* via the generate
  API's `options.num_gpu`: **Auto** (unset), **Max** (`99`, offload all that
  fits), **Off** (`0`, CPU-only). "Off" is reliable (asking for zero offload is
  honoured); "Max" only helps if the server's environment already permits GPU —
  it cannot conjure a GPU the server was started without.

The two compose: set the hardware policy at the server (env), use the toggle to
nudge per run.

## API reference

| Method & path               | Purpose                                            |
|-----------------------------|----------------------------------------------------|
| `GET  /`                    | the review UI                                      |
| `GET  /api/llm-status`      | Ollama reachability + whether the model is pulled  |
| `GET  /api/models`          | installed Ollama models                            |
| `POST /api/pull-model`      | stream a model download (NDJSON progress)          |
| `GET  /api/drivers`         | per-engine Python driver install status            |
| `POST /api/test-connection` | verify a DB connection (no scan)                   |
| `POST /api/scan`            | harvest + suggest -> rows + stats                  |
| `POST /api/enrich`          | LLM definition pass (fallback-safe)                |
| `POST /api/ai-suggest`      | evidence-grounded AI term/tag/sensitivity pass     |
| `POST /api/recommend-resolutions` | advise Merge / Disambiguate / Keep separate per duplicate group (evidence -> live value probe -> AI adjudicator) |
| `POST /api/qa-definitions`  | lint + AI-judge definitions (stamps QA_Issues / QA_Suggestion) |
| `POST /api/ai-categorize`   | AI files uncategorized terms into known categories |
| `POST /api/draft-policies`  | draft PDC pattern/dictionary rules from detection seeds (`format=zip` downloads the bundle) |
| `POST /api/resolve-fuzzy`   | match outstanding (renamed) term names against PDC's real terms — similarity + AI adjudication |
| `POST /api/export-pack`     | generate a domain pack from the reviewed scan results (merges over the installed pack; curated_seeds from induced patterns/enums) |

PDC API version: the app speaks v1/v2/v3 (selector on Apply & harvest; default **v3**, PDC 11's native version). Every request shape is validated against the official v3 OpenAPI spec by `python -m v3_selftest` — see docs/REVIEW.md §1 for the audit table.
| `POST /api/generate`        | build import-ready JSONL from the kept rows        |

---

## CLI (headless)

`cli_suggester.py` runs the same pipeline without the web layer and writes the
review CSV + JSONL directly:

```bash
python cli_suggester.py            # scans the default DDL
```

Or import the core in your own script:

```python
from suggester import harvest_ddl, suggest, to_jsonl_records, records_to_jsonl
rows = suggest(harvest_ddl("schema.sql"))
open("glossary.jsonl", "w").write(records_to_jsonl(to_jsonl_records(rows)))
```

---

## Notes / caveats

- **Suggest, don't publish.** Terms are Draft until a steward reviews them.
- **Import replaces the whole glossary** (timestamp-driven, not incremental):
  generate the complete set you want to keep, and reuse term `_id`s to update in
  place.
- The glossary import does **not** carry term->column links or custom properties —
  apply those separately via the entity attributes API.
- **Heuristics need review.** Name-pattern inference (sensitivity, PII) gets you a
  strong first draft, not a finished glossary — that's the point of the review step.
- Live multi-engine harvest covers the `information_schema` engines (PostgreSQL, SQL
  Server, MySQL) and Oracle (via the `ALL_TAB_COLUMNS` / `ALL_CONSTRAINTS` /
  `ALL_COL_COMMENTS` dictionary views, since 1.6.20). Oracle's schema is the owner —
  it defaults to the connecting user, uppercased; set it on the connection to scan
  a different owner.

---

## Repository manifest

The Flask app, with the **Registry writer** hooked in at export time, plus the
**Copper State Credit Union (CSCU)**, **Canyon Trail Outfitters (RETAIL)**,
**Lakeshore Health Partners (HEALTH)** and **Cascade Precision Components (MFG)**
training scenarios (additional scenarios plug in as data folders). The **Policy Generator** ships
**separately** as its own standalone app (`policy_generator/`). Validated
against **PDC 11.0.0**.

### The model

**Glossary Generator** (this repo) creates the **Registry** at export →
**Policy Generator** (separate app) reads it and builds the Data Identification
policy (dictionaries + patterns).

### Where the hand-off happens

`POST /api/generate` (glossary export) authors the Registry from the final reviewed
rows and writes **`registries/registry.<glossary>.json`** — one concept per kept
term: term name, governed tags, sensitivity, category, and a null `term_id`
(UNKNOWN until PDC mints ids and the Policy Generator's reconcile backfills them).
The response includes a `registry` path.

### Layout

```text
PDC-Glossary/
  README.md                     repo landing page
  docs/                         all documentation
    GUIDE.md                    THE manual: why (Registry thesis) + install/setup
                                + full walkthrough + real-PDC operating notes
    REFERENCE.md                app reference (env vars, drivers, LLM/GPU, API
                                table, repository manifest — this section)
    PDC-VM-TROUBLESHOOTING.md   PDC platform errors on the lab VM (opensearch-cluster-init, ...)
    REVIEW.md                   code review & PDC v3 compatibility audit
    CHANGELOG.md                release history
  glossary_generator/           the app (scenario-generic)
    app.py  run.sh  run.bat  run.ps1
    llm.py  dbconn.py  suggester.py  cli_suggester.py
    pdc_api/                    PDC Public API client package (core, entities,
                                terms, jobs, apply, bulkload)
    build_roster.py  seed_sample.py  audit.py  similarity.py  tagdict.py
    policy_draft.py  defqa.py  packgen.py
    selftest.py                 offline engine checks (run after a pull)
    v3_selftest.py              PDC v3 API shape checks
    templates/index.html        markup; logic in static/js/, styles in static/style.css
    static/                     style.css + js/00-bulkload..12-init (numbered load order)
    registry/                   app-side Registry WRITER (hooked at /api/generate)
    registries/                 (created at runtime: registry.<glossary>.json)
    domain_packs/README.md      pack format reference (packs live per scenario)
    diagrams/                   six figures, PNG + SVG
    datasources.sample.csv      generic bulk-load starter CSV
    Dockerfile  docker-compose.yml  requirements.txt  .env.example  VERSION
  (data_sources/ + courseware/  moved to the PDC-Scenarios repo)
    lab/                        SHARED stack: one PostgreSQL + one MinIO for all
                                scenarios (make load SCENARIO=<ID> creates that
                                scenario's database + bucket + documents)
    CSCU/                       Copper State Credit Union (financial) — data only
      postgres-init/  cscu-documents/  domain_pack/
      cscu-domain-pack.zip  cscu-datasources.csv  scenario.json
    RETAIL/                     Canyon Trail Outfitters (retail) — same kit shape
      postgres-init/  cto-documents/  domain_pack/
      cto-domain-pack.zip  cto-datasources.csv  scenario.json
    HEALTH/                     Lakeshore Health Partners (healthcare) — same kit shape
      postgres-init/  lhp-documents/  domain_pack/
      lhp-domain-pack.zip  lhp-datasources.csv  scenario.json
    MFG/                        Cascade Precision Components (manufacturing) — same kit shape
      postgres-init/  cpc-documents/  domain_pack/
      cpc-domain-pack.zip  cpc-datasources.csv  scenario.json
    CSCU/                       workshop guides (markdown masters) + Technical Track
    RETAIL/                     the retail workshop set (W00-W05 + assets)
    HEALTH/                     the healthcare workshop set (W00-W05 + assets)
    MFG/                        the manufacturing workshop set (W00-W05 + assets)
```

The **Policy Generator** is delivered separately as `policy_generator/` (its own zip):
the standalone engine that reads the Registry and emits/drift-checks the policy.

### Run the app

Local: `./run.sh` (or `run.bat` / `run.ps1`) → http://127.0.0.1:5000.
Docker: `docker compose up --build`. Full setup is in **`GUIDE.md` Part B**.

### Install a scenario

Run `install-scenario.ps1` / `install-scenario.sh` (PDC-Scenarios repo) and pick a scenario —
or unzip the scenario's pack into `glossary_generator/`
(PDC-Scenarios' `data_sources/<ID>/*-domain-pack.zip`), delete any previous
`tag_dictionary.json`, restart. **One scenario at a time.**

### Test the Registry writer (offline)

```bash
python -m registry.selftest      # rows -> Registry mapping checks
```

### What the app does NOT contain

The classify / emit / drift / reconcile engine is **not** in the app — the app already
classifies via `suggester.py`, so its Registry half only *writes* the reviewed rows as
the artifact. All method-building lives in the separate **Policy Generator**.

*All scenario data is fictional and generated for training.*
