# Workshop 1 — Connect the Data Sources (CSCU)

*Copper State Credit Union scenario · PDC 10.2.11 · PDC at `https://pentaho.io`,
sources in the Ubuntu VM at `192.168.1.200`*

You connect PDC to CSCU's two sources: the **core banking database**
(PostgreSQL `cscu_core`, 11 tables) and the **document store** (MinIO bucket
`cscu-documents`, 18 files), then ingest metadata and scan the files.

## Prerequisites

- The shared lab is up with CSCU loaded: `cd data_sources/lab && make up &&
  make load SCENARIO=CSCU` (`make console` prints both connection blocks).
- Workshop 0 users exist. Work as `elena.ramirez` (Data Steward) or
  `catalog.admin`.
- PDC ships PostgreSQL JDBC support in the lab image — no driver upload needed.

## Part A — the database source

1. **Data Sources → Add New** → PostgreSQL.
2. Enter the connection — PDC runs in the same VM as the published ports, so
   use the VM IP:

   | Field | Value |
   | --- | --- |
   | Name | `CopperState_Core_Banking` |
   | Host / Port | `192.168.1.200` / `5432` |
   | Database | `cscu_core` |
   | User / Password | `pdc_user` / `catalog123!` (read-only) |
   | Schemas | `cscu_core` — **not** `public` (an empty schema ingests "OK" and harvests nothing) |

   `[SCREENSHOT: Add Data Source — CopperState_Core_Banking form]`
3. **Test Connection** → green. **Save**.
4. Run **Metadata Ingest** on the source and wait for the job to finish.
   `[SCREENSHOT: job monitor — metadata ingest complete]`
5. Verify: the source shows **11 tables** (branches, employees, members,
   accounts, cards, transactions, loans, ach_payments, kyc_reviews,
   suspicious_activity, gl_entries).

## Part B — the document store

1. **Data Sources → Add New** → **AWS S3** (PDC's type for any S3-compatible
   store — MinIO included).
2. Enter:

   | Field | Value |
   | --- | --- |
   | Name | `CopperState_Documents` |
   | Endpoint | `http://192.168.1.200:9000` (the S3 API — `9001` is the console) |
   | Access / Secret | `cscu_minio_user` / `minio_secret_123!` (read-only) |
   | Bucket (container) | `cscu-documents` |
   | Path | `/` · Path-style: enabled (forced by the IP endpoint) |

   `[SCREENSHOT: Add Data Source — CopperState_Documents form]`
3. **Save**, then open the source and click **Scan Files** (the File System
   Scan — this step is UI-only; it is not on the public API).
4. Verify: **18 objects** across compliance/, correspondence/,
   loan-applications/, statements/, payments/, rates/.
   `[SCREENSHOT: document store — scanned folder tree]`

## Alternative — bulk-load both sources from CSV

The Glossary Generator's bulk loader registers both rows of
`assets/cscu-datasources.csv` in one pass (create → test → ingest); the MinIO
row still needs the manual **Scan Files** click afterwards. See the app's
Connections page → *Bulk-load data sources* (dry-run first).

## Checkpoint

- [ ] `CopperState_Core_Banking`: connected, ingested, 11 tables
- [ ] `CopperState_Documents`: connected, file scan complete, 18 objects
- [ ] Both sources visible in the Data Canvas

All Copper State Credit Union data is fictional and generated for training.
