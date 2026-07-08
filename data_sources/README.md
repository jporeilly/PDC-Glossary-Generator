# Data sources — the shared lab + one data folder per scenario

[`lab/`](lab/) is the **single, shared stack**: one PostgreSQL
(`demo-postgres`) and one MinIO (`demo-minio`) hosting every scenario side by
side — each scenario loads into its own database and its own bucket. The
scenario folders hold **data only** (schema + sample SQL, documents, domain
pack + install zip, bulk-load CSV, `scenario.json` manifest).

| Folder | Scenario | Database | Documents |
| --- | --- | --- | --- |
| [`AWC/`](AWC/) | **Arizona Water Company** — water utility | `awc_operations` (6 tables) | `awc-documents` bucket |
| [`CSCU/`](CSCU/) | **Copper State Credit Union** — financial services | `cscu_core` (11 tables) | `cscu-documents` bucket (18 files) |

Quick start (on the Docker host — the Ubuntu VM):

```sh
cd lab
cp .env.example .env
make up                    # start demo-postgres + demo-minio
make load SCENARIO=CSCU    # and/or SCENARIO=AWC — they coexist
make console               # PDC connection details per scenario
```

Each scenario folder carries:

- `postgres-init/` — schema + sample data + read-only user SQL (run by the
  lab loader).
- `<bucket>-documents/` — the unstructured files uploaded to that scenario's
  MinIO bucket.
- `<scenario>-domain-pack.zip` — the Glossary Generator scenario install
  (`domain_pack.json` + `people.json` roster + INSTALL.txt). Unzip into
  `glossary_generator/`, reseed the Dictionary, restart.
- `domain_pack/` — the same pack files unzipped, for reading and editing.
- `*-datasources.csv` — the two PDC connections pre-filled for the app's
  bulk connection loader (`/api/pdc/bulk-load`).
- `scenario.json` — the manifest the lab loader and installer scripts read.

**Don't mix scenarios** — stand up one lab, install its pack, run its
courseware set (see `courseware/`). Credentials in these kits are lab values;
change them for anything beyond the lab.

*All scenario data is fictional and generated for training.*
