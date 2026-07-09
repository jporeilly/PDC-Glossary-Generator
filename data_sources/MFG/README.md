# Cascade Precision Components — scenario data kit (MFG)

The **manufacturing** training scenario: everything needed to load the
11-table `cpc_mfg` schema and the `cpc-documents` bucket into the **shared
demo lab** (one PostgreSQL + one MinIO for all scenarios — see
[`../lab/`](../lab/)) and to configure the Glossary Generator for it.

Cascade Precision Components (CPC) is a fictional Pacific Northwest maker
of precision hydraulic valves, fittings and manifolds: six plants from
Portland to Spokane, a bill of materials (the catalog's strongest lineage
story), full lot traceability — and the planted defects the workshops hunt:
**two Released lots with no Certificate of Conformance on file**, **a
CRITICAL nonconformance dispositioned USE_AS_IS without MRB approval**
(NCR-2026-014), and **a purchase order issued to a suspended supplier**
(PO-30000112). This is the deliberate **non-PII scenario**: the only
personal data is the staff table, so the built-in PII identification
methods find almost nothing — the point. Sensitivity here is commercial
(unit costs, price lists) and safety-critical (traceability), and the
regulator is the ISO 9001 / AS9100 auditor.

## What's in this folder

| Item | What it is |
| --- | --- |
| `postgres-init/` | Schema + sample data + read-only `pdc_user` SQL, run by the lab loader |
| `cpc-documents/` | The unstructured document set uploaded to the `cpc-documents` bucket |
| `domain_pack/` | The Glossary Generator domain pack + steward roster (source files) |
| `cpc-domain-pack.zip` | Ready-to-install pack (unzip into `glossary_generator/`, or use `install-scenario.sh`) |
| `cpc-datasources.csv` | The two PDC connections, pre-filled for the app's bulk loader |
| `scenario.json` | Manifest the lab loader and installer scripts read |

## Load it into the shared lab

On the Docker host (the Ubuntu VM):

```sh
cd ../lab
cp .env.example .env       # first time only
make up                    # start demo-postgres + demo-minio (shared, all scenarios)
make load SCENARIO=MFG     # create + verify this scenario's database and bucket
make console               # reprint the PDC connection details
```

The loader creates, inside the **shared** containers:

| | Value |
| --- | --- |
| PostgreSQL database | `cpc_mfg` (schema `cpc_mfg`, **11 tables**, sample data loaded) |
| Read-only DB user | `pdc_user` / `catalog123!` |
| MinIO bucket | `cpc-documents` (18 objects) |
| Read-only MinIO user | `cpc_minio_user` / `minio_secret_123!` |

Scenarios coexist — loading MFG does not touch the other scenarios'
databases or buckets. `make remove SCENARIO=MFG` drops only this scenario's
pair.

## Topology and connection values

The topology is identical for every scenario — app on the Windows 11 host,
shared stack + PDC in the Ubuntu VM at `192.168.1.200`, PDC at
`https://pentaho.io`, lab PostgreSQL published on **5433** (PDC's own
database owns 5432). Full one-time setup is in
[`../lab/README.md`](../lab/README.md).

**Values to enter in the Glossary Generator (on Windows):**

| Connection | Field | Value |
| --- | --- | --- |
| Database | Host / Port | `192.168.1.200` / `5433` |
| Database | Database / Schema | `cpc_mfg` / `cpc_mfg` |
| Database | User / Password | `pdc_user` / `catalog123!` (read-only) |
| Document store | Endpoint | `http://192.168.1.200:9000` |
| Document store | Access key / Secret | `cpc_minio_user` / `minio_secret_123!` |
| Document store | Bucket | `cpc-documents` |
| PDC | Base URL / TLS | `https://pentaho.io` / Verify TLS off (lab cert) |

The shipped **`cpc-datasources.csv`** already uses `192.168.1.200` for both
rows, so the bulk loader registers sources PDC can reach with no edits.

## Notes

- Lab credentials (`catalog123!`, `minio_secret_123!`, the `demo_admin`
  accounts in `../lab/.env`) are training values — change them for anything
  beyond the lab. Certificates, specs and prices are fictional.
- Rebuilding this scenario from scratch: `make remove SCENARIO=MFG && make
  load SCENARIO=MFG` in `../lab/`.
- The courseware for this scenario lives in `../../courseware/MFG/`.

*All Cascade Precision Components data is fictional and generated for training.*
