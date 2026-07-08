# PDC demo lab — one shared PostgreSQL + MinIO for all scenarios

A single generic stack that hosts **every** scenario side by side. Each
scenario loads into its **own database** and its **own bucket**, so nothing
changes in the documented connection values and nothing conflicts:

| Scenario | PostgreSQL database | MinIO bucket | Read-only users |
| --- | --- | --- | --- |
| AWC | `awc_operations` (6 tables) | `awc-documents` | `pdc_user` · `awc_minio_user` |
| CSCU | `cscu_core` (11 tables) | `cscu-documents` | `pdc_user` · `cscu_minio_user` |

The stack itself is scenario-free: containers `demo-postgres` and
`demo-minio` on the `demo-net` network, admin account `demo_admin`.
PostgreSQL publishes on host port **5433** (PDC's own PostgreSQL already
binds 5432 on the lab VM); in-container it is still 5432. MinIO publishes
on 9000/9001 as before.
Scenario data (schemas, tables, sample rows, documents, read-only grants)
is applied by the **loader script**, driven by each scenario folder's
`scenario.json` — drop a new scenario folder next to AWC/CSCU and it becomes
loadable with no script changes.

## Quick start (on the Docker host — the Ubuntu VM)

```sh
cp .env.example .env
make up                    # start the shared postgres + minio
make load SCENARIO=CSCU    # create cscu_core + cscu-documents, load + verify
make load SCENARIO=AWC     # and/or the water scenario — they coexist
make console               # PDC connection details per scenario
```

`./load-scenario.sh` with no arguments lists what's available. Loading is
idempotent — an existing database is left untouched (use
`make remove SCENARIO=<ID>` first to rebuild from scratch).

## What `make load` does

1. **PostgreSQL** — creates the scenario's database, then runs its
   `postgres-init/*.sql` in name order (schema + tables + sample data, then
   the read-only `pdc_user` grants), and verifies the expected table count.
2. **MinIO** — creates the scenario's bucket, creates its read-only user and
   a bucket-scoped read-only policy, uploads the documents folder, and
   verifies the object count. Both buckets (`awc-documents`,
   `cscu-documents`) live in the same MinIO.

## Targets

| Command | What it does |
| --- | --- |
| `make up` | Start both services and wait until ready |
| `make load SCENARIO=<ID>` | Load a scenario (database + bucket + documents) |
| `make remove SCENARIO=<ID>` | Drop that scenario's database and bucket |
| `make status` | Containers, databases, buckets at a glance |
| `make console` | Connection details, with per-scenario LOADED state |
| `make logs` | Tail logs |
| `make clean` | Stop containers, keep data |
| `make destroy` | Stop containers and wipe all data volumes |

## Connecting (same topology as before)

PostgreSQL publishes on **5433** (5432 belongs to PDC's own database on the
same VM); MinIO on 9000/9001:

- **From the Windows 11 host (the Glossary Generator app):** PostgreSQL
  `192.168.1.200:5433`, MinIO `http://192.168.1.200:9000`.
- **From PDC (in the VM):** `192.168.1.200:5433` / `http://192.168.1.200:9000`
  (published ports) — or `demo-postgres:5432` / `http://demo-minio:9000` if
  PDC shares `demo-net`.
- Database / schema / credentials per scenario: see the table above or
  `make console`. Full topology notes (hosts file, ufw, `https://pentaho.io`)
  are in each scenario's README.

*All scenario data is fictional and generated for training.*
