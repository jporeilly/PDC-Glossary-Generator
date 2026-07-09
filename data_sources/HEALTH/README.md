# Lakeshore Health Partners — scenario data kit (HEALTH)

The **healthcare** training scenario: everything needed to load the 11-table
`lhp_clinical` schema and the `lhp-documents` bucket into the **shared demo
lab** (one PostgreSQL + one MinIO for all scenarios — see
[`../lab/`](../lab/)) and to configure the Glossary Generator for it.

Lakeshore Health Partners (LHP) is a fictional Minnesota clinic network: six
clinics from Minneapolis and St. Paul up to Duluth, six providers, a patient
panel with the full PHI surface — and the planted defects the workshops hunt:
**patient SSNs leaked inside free-text clinical notes** (2 encounters), **a
PHI disclosure for marketing without a signed HIPAA authorization**
(disclosure-log entry 30005), and **three opted-out patients still carrying
live marketing emails**. The schema is rich in identification material: MRNs
(`LHP-nnnnnn`), 10-digit NPIs, ICD-10, LOINC, NDC and CPT codes.

## What's in this folder

| Item | What it is |
| --- | --- |
| `postgres-init/` | Schema + sample data + read-only `pdc_user` SQL, run by the lab loader |
| `lhp-documents/` | The unstructured document set uploaded to the `lhp-documents` bucket |
| `domain_pack/` | The Glossary Generator domain pack + steward roster (source files) |
| `lhp-domain-pack.zip` | Ready-to-install pack (unzip into `glossary_generator/`, or use `install-scenario.sh`) |
| `lhp-datasources.csv` | The two PDC connections, pre-filled for the app's bulk loader |
| `scenario.json` | Manifest the lab loader and installer scripts read |

## Load it into the shared lab

On the Docker host (the Ubuntu VM):

```sh
cd ../lab
cp .env.example .env        # first time only
make up                     # start demo-postgres + demo-minio (shared, all scenarios)
make load SCENARIO=HEALTH   # create + verify this scenario's database and bucket
make console                # reprint the PDC connection details
```

The loader creates, inside the **shared** containers:

| | Value |
| --- | --- |
| PostgreSQL database | `lhp_clinical` (schema `lhp_clinical`, **11 tables**, sample data loaded) |
| Read-only DB user | `pdc_user` / `catalog123!` |
| MinIO bucket | `lhp-documents` (18 objects) |
| Read-only MinIO user | `lhp_minio_user` / `minio_secret_123!` |

Scenarios coexist — loading HEALTH does not touch the other scenarios'
databases or buckets. `make remove SCENARIO=HEALTH` drops only this
scenario's pair.

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
| Database | Database / Schema | `lhp_clinical` / `lhp_clinical` |
| Database | User / Password | `pdc_user` / `catalog123!` (read-only) |
| Document store | Endpoint | `http://192.168.1.200:9000` |
| Document store | Access key / Secret | `lhp_minio_user` / `minio_secret_123!` |
| Document store | Bucket | `lhp-documents` |
| PDC | Base URL / TLS | `https://pentaho.io` / Verify TLS off (lab cert) |

The shipped **`lhp-datasources.csv`** already uses `192.168.1.200` for both
rows, so the bulk loader registers sources PDC can reach with no edits.

## Notes

- Lab credentials (`catalog123!`, `minio_secret_123!`, the `demo_admin`
  accounts in `../lab/.env`) are training values — change them for anything
  beyond the lab. Patient identifiers (SSNs, NPIs, NDCs) are fictional.
- Rebuilding this scenario from scratch: `make remove SCENARIO=HEALTH &&
  make load SCENARIO=HEALTH` in `../lab/`.
- The courseware for this scenario lives in `../../courseware/HEALTH/`.

*All Lakeshore Health Partners data is fictional and generated for training.*
