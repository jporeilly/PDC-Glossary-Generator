# Workshop 1 — Connect the Data Sources (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · PDC at `https://pentaho.io`, sources in the Ubuntu VM at `192.168.1.200`*

**Primary role:** Data Steward / IT Administrator
**Estimated time:** 120 min

## Why this workshop matters

Every governance journey begins the same way: you cannot catalog, profile,
protect, or trace data that the catalog cannot see. Workshop 1 is where
Pentaho Data Catalog (PDC) first meets the Copper State Credit Union (CSCU)
data estate. By the end, two very different worlds of data will be visible in
one place — and everything you do in the remaining workshops depends on the
connections you make here.

CSCU is a fictional Arizona credit union with six branches, from Phoenix and
Tempe to Globe and Prescott. Like every financial institution, it runs on two
kinds of information. The first is structured core-banking data — members,
accounts, cards, transactions, loans, compliance cases — living in a
PostgreSQL database. The second, and in most institutions far larger, is
unstructured content: loan applications, member statements, adverse-action
letters, SAR filings, PCI attestations, ACH extracts. Industry studies put
unstructured content at 80–90% of what an organization generates, and a
credit union is no exception.

> **The business problem.** Before PDC, a CSCU analyst asked *"what do we hold
> about member Alicia Mendoza?"* had to search the core banking database, then
> a document share, then someone's email. The answer was scattered, and nobody
> could be sure it was complete. Connecting both the database and the document
> store to one catalog is the first concrete step toward answering that
> question in one place — and toward proving, to an NCUA examiner, that CSCU
> knows where all of its member data lives.

## What you will learn

- How PDC models a data source, and why connection details are encrypted and
  tested before a source goes live.
- How to register both sources in one pass with the Glossary Generator's
  **bulk loader** — the standard method — and what it does per CSV row.
- How to connect a PostgreSQL database and ingest its schema so the
  `cscu_core` tables become catalog assets.
- How file and object-store sources differ from databases — why they are
  scanned rather than schema-ingested, and which engine processes them.
- How to connect the MinIO object store holding CSCU's documents, and preview
  how those documents are processed.
- Why a read-only connection user is the right choice for a catalog, and how
  it reflects good governance from step one.

## Background: how PDC sees data

A data source in PDC is a stored, encrypted definition of how to reach a
system — its type, host, credentials, and options. PDC encrypts the user name
and password before storing them, and a source stays OFFLINE until a
successful **Test Connection** proves the details work. This is deliberate: a
catalog that holds connection secrets for every system in the business must
protect them, and must never present a half-working connection as
trustworthy.

### Two on-ramps: schema ingest vs. file scan

How a source is brought in depends on what kind of data it holds, and this
distinction runs through the whole course:

| | Structured database | File / object store |
| --- | --- | --- |
| Example at CSCU | PostgreSQL `cscu_core` | MinIO `cscu-documents` bucket |
| Load step | Ingest Schema | Scan Files |
| What loads | Tables, columns, types, keys | Files, formats, sizes, paths |
| Processing engine | Data Integration | Data Optimizer |
| Profiling later | Column profiling | Document Processing |

Understanding this split is the single most useful concept in Workshop 1. A
database is described by its schema, so PDC ingests that schema. A bucket of
PDFs and CSVs has no schema, so PDC scans the files and reads their content
with a different engine. Same catalog, two on-ramps.

## Before you begin

### Prerequisites

- The shared lab running with CSCU loaded (`data_sources/lab`: `make up &&
  make load SCENARIO=CSCU`), so PostgreSQL and MinIO are both up and verified.
- Workshop 0 users exist. Work as `omar.haddad` (**Data Storage
  Administrator** — creating and ingesting data sources is his job;
  `elena.ramirez`'s Data Steward role also carries the rights).
- Network reachability from PDC to the two services. The shared lab publishes
  PostgreSQL on the VM IP at port **5433** (PDC's own database owns 5432) and
  MinIO at port 9000. Always use the VM IP `192.168.1.200` — container names
  resolve only inside the lab's Docker network.

### Assets used in this workshop

- `data_sources/CSCU/postgres-init/` — the core banking schema and sample
  data (loaded automatically by the lab loader).
- `data_sources/CSCU/cscu-documents/` — the full document set (18 files
  across compliance, correspondence, loan-applications, statements, payments,
  and rates).
- `assets/cscu-datasources.csv` — both connections pre-filled for the
  Glossary Generator's **bulk loader**, the standard method in Part A.

Keep the two tables below handy — you will enter these values in the steps.
**Test Connection must succeed before either source comes online.**

### Database — CopperState_Core_Banking (PostgreSQL)

| Field | Value | Notes |
| --- | --- | --- |
| Data Source Name | CopperState_Core_Banking | Letters, digits, underscores only — no spaces |
| Data Source Type | PostgreSQL | |
| Host | 192.168.1.200 | The VM IP. Container names don't resolve from PDC |
| Port | 5433 | The lab's published port — 5432 belongs to PDC's own database |
| Database Name | cscu_core | The CSCU core banking database |
| Schemas | cscu_core | Not `public` — an empty schema ingests "OK" and harvests nothing |
| User Name | pdc_user | Read-only — CONNECT, USAGE, SELECT |
| Password | catalog123! | Lab credential — change in production |

### Object store — CopperState_Documents (MinIO via the AWS S3 type)

| Field | Value | Notes |
| --- | --- | --- |
| Data Source Name | CopperState_Documents | Letters, digits, underscores only — no spaces |
| Data Source Type | AWS S3 | MinIO is S3-compatible; connect it with the AWS S3 type |
| Region | us-east-1 | Any value works for MinIO |
| Bucket Name | cscu-documents | The bucket holding CSCU documents |
| Access Key | cscu_minio_user | MinIO access key — read-only |
| Secret Access Key | minio_secret_123! | Lab credential — change in production |
| Endpoint | http://192.168.1.200:9000 | The VM IP, not localhost. An IP forces S3 path-style, which MinIO requires (the AWS S3 form has no path-style toggle) |
| Path | / | Scan the whole bucket from its root |

## Step-by-step

### Part A — Bulk-load both sources (the standard method)

The Glossary Generator's bulk loader registers every source in a CSV in one
pass — for each row it **creates** the data source over PDC's public API, runs
a **test-connection job** and waits for it, then triggers a **metadata
ingest** scoped to the new source (database rows only; object stores have no
schema to ingest). It is repeatable, secrets transit only to PDC, and one CSV
captures a whole scenario.

1. On the Windows host, start the Glossary Generator (`.\run.ps1` in
   `glossary_generator/`) and open `http://127.0.0.1:5000`. Go to the
   **Connections** page and open the **Bulk-load data sources** panel.
2. Enter the PDC connection: Base URL `https://pentaho.io` (the server root —
   the app adds `/api/public/...` itself), API version `v2`, and **Verify
   TLS off** for the lab's self-signed certificate.
3. Authenticate as `omar.haddad` (Data Storage Administrator — creating data
   sources requires those rights) and click **Get token**. The badge shows
   the signed-in user and the token expiry; the token is held in memory only.
   `[SCREENSHOT: bulk-load panel — PDC connection + token badge]`
4. Choose the CSV: `assets/cscu-datasources.csv`. The panel previews both
   rows — the `postgres` row (`CopperState_Core_Banking`) and the `minio` row
   (`CopperState_Documents`). The values are already host-reachable
   (`192.168.1.200`, port 5433), so the **App reachability remap** field can
   stay empty.
5. Tick **Dry run** and run once. The panel shows the exact (redacted)
   request bodies it would send — check `databaseType` is `POSTGRES` for the
   database row and `AWS` for the object store, and that `schemaNames` is
   `cscu_core`. Nothing has touched PDC yet.
   `[SCREENSHOT: dry-run preview — redacted request bodies]`
6. Untick Dry run and **Run**. Progress streams back one row at a time:
   create → test-connection → ingest for the database; create → test for the
   object store.
   `[SCREENSHOT: bulk-load progress — both rows green]`
7. One manual step remains: the **File System Scan is not on the public
   API**. In PDC, open `CopperState_Documents` and click **Scan Files** (a
   first full scan, defaults are fine). Monitor it on the Workers page.
   `[SCREENSHOT: Scan Files on CopperState_Documents]`
8. Verify in the Data Canvas: the eleven `cscu_core` tables and the six
   document folders are visible. If both are there, Parts B and C below are
   reference material — skip to Part D.

> **Why is Scan Files manual?** Creating an object-store source is fully
> supported on the public API, but the scan that reads the bucket is an
> internal, UI-only job. The loader stops cleanly after create + test for
> object stores; the one click in PDC finishes the job. (The database row
> needs no click — schema ingest *is* on the public API.)

### Part B — Connect the core banking database manually (reference)

Use this path when you have no CSV, or to understand exactly what the loader
automates.

1. Sign in to `https://pentaho.io` as `omar.haddad`. In the left navigation
   menu, click **Management**. The Manage Your Environment page opens.
2. In the Resources card, click **Add Data Source**. The Create Data Source
   page opens.
3. In **Data Source Name**, enter `CopperState_Core_Banking`. Names must start
   with a letter and contain only letters, digits, and underscores — spaces
   are not supported.
4. In **Data Source Type**, select **PostgreSQL**. PDC expands the form with
   database-specific fields.
5. Enter the connection details from the table above: Host `192.168.1.200`,
   Port `5433`, Database Name `cscu_core`, User Name `pdc_user`, Password
   `catalog123!`.
   `[SCREENSHOT: CopperState_Core_Banking connection form]`
6. Click **Test Connection** and wait for the confirmation message. The source
   remains OFFLINE until this succeeds — if it fails, the message tells you
   what to fix (usually host, port, or credentials; see Troubleshooting).
7. Click **Ingest Schema**. In the Select schemas dialog, choose the
   `cscu_core` schema — not `public`, which is empty. You can use
   include/exclude patterns to filter tables; for this lab, ingest everything
   in `cscu_core`.
   `[SCREENSHOT: Select schemas — cscu_core]`
8. Click **Ingest**, then **Create Data Source**. PDC loads the eleven tables
   and their columns as catalog assets: branches, employees, members,
   accounts, cards, transactions, loans, ach_payments, kyc_reviews,
   suspicious_activity, gl_entries.

> **Why a read-only user?** You are connecting as `pdc_user`, which has only
> CONNECT, USAGE, and SELECT. The catalog only ever needs to read — it
> profiles and describes data, it never changes it. Using a least-privilege
> user means the catalog literally cannot modify CSCU's member balances or
> loan records, which is exactly the separation of duties an examiner expects.
> Good governance starts at the connection screen.

### Part C — Connect the document store manually (reference)

MinIO is an S3-compatible object store, already running in the shared lab.
PDC connects to it as an object-store data source — a different on-ramp from
the database.

1. Back in **Management → Resources**, click **Add Data Source**. Name it
   `CopperState_Documents`.
2. In **Data Source Type**, select the **AWS S3** type. The form changes to
   ask for bucket details rather than a database name.
3. Enter: Endpoint `http://192.168.1.200:9000`, Access Key `cscu_minio_user`,
   Secret Key `minio_secret_123!`, Bucket `cscu-documents`. Use the VM IP for
   the Endpoint, not `localhost` — from inside the PDC container `localhost`
   is PDC itself, and an IP endpoint forces S3 path-style addressing, which
   MinIO requires. The AWS S3 form has no path-style toggle, so the IP is
   what makes it work.
   `[SCREENSHOT: CopperState_Documents connection form]`
4. Click **Test Connection**. As with the database, the source stays OFFLINE
   until the test passes.
5. Click **Scan Files**. In the Scan Files dialog, accept the defaults for a
   first full scan. Note the options for later: **Incremental Ingest** (12
   hours to 3 months), **Include/Exclude patterns** to scope folders, and
   **Delete Empty Folders**.
   `[SCREENSHOT: Scan Files dialog]`
6. Monitor progress on the **Workers** page. When the scan completes, the six
   `cscu-documents` folders appear in the Data Canvas next to the database
   tables — compliance, correspondence, loan-applications, payments, rates,
   statements.

### Part D — Preview processing

Scanning loads file metadata; processing reads content. You will do this fully
in later workshops, but preview it now so the two on-ramps are clear end to
end.

1. Run **Metadata Ingest** first — it reads the files' metadata into the
   catalog. Then select the `compliance/` folder and choose **Process** to
   open the Choose Process pane and see the jobs PDC offers.
   `[SCREENSHOT: Choose Process pane on the compliance folder]`

| Process | What it does, and where its results appear |
| --- | --- |
| Metadata Ingest | Reads each file's metadata (name, type, size, timestamps, path) into the catalog. Run it first — every other job depends on it |
| Calculate Trust Score | Computes an asset-reliability score from data quality, user ratings, lineage, and whether a glossary term is assigned. Shown in the asset's Key Metrics panel; works for tables and files |
| Data Discovery | Generates statistics, data patterns, and samples in a single pass — the data-profiling step and the prerequisite for most downstream analytics |
| Data Identification | Classifies content and applies tags using dictionaries and data-pattern analysis — the built-in sets plus any custom methods you add (Workshop 5 and the Technical Track). Rule-based, not an LLM |
| PII Detection | An ML check that tags PII columns into an auto-created ML_PII glossary. Scope-limited (JDBC tables and CSV/TSV in specific languages) — it does not act on CSCU's English PDFs |

For the `compliance/` folder the realistic sequence is Metadata Ingest, then
Data Discovery, then Data Identification, optionally Calculate Trust Score.

### Scan & ingest scope options

| Option | What it means |
| --- | --- |
| Delete Empty Folders | Removes folders with no files from the catalog's metadata store so empty directories don't clutter the Data Canvas. Full scans/ingests only |
| Incremental Ingest | Ingests only files created or modified within the chosen period (12 hours to 3 months). Adds to what is already cataloged and never removes earlier results |

The two are mutually exclusive — Delete Empty Folders works on full ingests
only. For this lab, leave Incremental Ingest off (a full ingest) so every
document is read.

## Optional settings: Physical Location, capacity, and cost

After Test Connection succeeds — and after Scan Files (object stores) or
Ingest Schema (databases) — the Create Data Source page shows optional fields
before the final Create button. None are required: they describe where the
data lives and what it costs, and they feed Pentaho Data Optimizer, the
tiering engine that can migrate, delete, and rehydrate files to reduce
storage cost.

| Field | What it does |
| --- | --- |
| Physical Location | Where the data physically lives — recorded for data-residency and compliance context. Does not affect the connection |
| Available for Migration | Includes this source in Data Optimizer tiering (requires a Data Optimizer license) |
| Available for Writing | Lets Data Optimizer write back — needed to rehydrate tiered files |
| Available for Data Mastering | Includes the source in data-mastering activities |
| Cost per Terabyte / Total Capacity | Feed cost modelling so tiering savings can be quantified |
| Note | Free text shared with anyone who opens the data source |

> **For this lab:** leave all of these blank and click **Create Data Source**.
> CSCU would return here to model the savings from tiering cold compliance
> PDFs into archive storage.

## Verify your work

You are done with Workshop 1 when all of the following are true:

- [ ] CopperState_Core_Banking is online and a Discovery search for `members`
  returns the table with its columns.
- [ ] All eleven `cscu_core` tables are visible in the Data Canvas.
- [ ] CopperState_Documents is online and scanned, with the six document
  folders visible in the Data Canvas.
- [ ] You can explain, in your own words, why a database is ingested by schema
  while files are scanned, and which engine processes each.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Test Connection fails for the database | Host or port wrong. Use the VM IP `192.168.1.200` and port **5433** — 5432 on this VM is PDC's own database, and container names don't resolve from PDC. Confirm `pdc_user` / `catalog123!` |
| Test Connection fails for MinIO | Endpoint or keys wrong. Most often the Endpoint is `localhost` — from inside the PDC container that points at PDC itself; use `http://192.168.1.200:9000`. An IP endpoint also forces S3 path-style; a hostname makes the SDK prepend the bucket (`cscu-documents.host`) and fail |
| Ingest succeeds but no tables appear | The schema selection was `public`, which is empty. Re-ingest and select `cscu_core` |
| Scan finds no files | The bucket loaded empty. Re-run the lab loader (`make load SCENARIO=CSCU`) — it verifies 18 objects |
| Source stays OFFLINE | Expected until Test Connection succeeds. Fix the details and test again |
| Bulk loader: Get token fails (401) | Wrong credentials, or the account lacks rights — use `omar.haddad` or another Data Storage Administrator / admin. Confirm Base URL is the server root (`https://pentaho.io`) with Verify TLS off |
| Bulk loader: create fails 400 on the object store | `databaseType` must be the literal `AWS` for S3-compatible stores — the shipped CSV already sets it; check the dry-run body if you edited the CSV |
| Bulk loader: database ingest OK but 0 tables | `schemaNames` points at an empty schema. The CSV sets `cscu_core`; if edited, fix and re-run (the loader skips an existing source's create and re-runs the jobs) |

## Why it matters & discussion

PDC encrypts connection credentials and refuses to bring a source online until
Test Connection succeeds. Discuss with your group: why are both of those
behaviours essential for a regulated credit union that holds member PII and
must demonstrate control of its data? Relate your answer to CSCU's
obligations under GLBA safeguards and BSA record-keeping — and to the question
an examiner will actually ask: *"show me every system that holds member
data."*

## What's next

With both sources connected, Workshop 2 reads what the catalog learned about
them — the structure and metadata of the tables, and the document properties
of the files. You will see that whether an asset is a core-banking table or a
SAR filing, PDC describes it through the same layers of metadata.

All Copper State Credit Union data is fictional and generated for training.
