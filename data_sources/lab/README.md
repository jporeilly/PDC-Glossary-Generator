# PDC demo lab — one shared PostgreSQL + MinIO for all scenarios

A single generic stack that hosts **every** scenario side by side. Each
scenario loads into its **own database** and its **own bucket**, so nothing
changes in the documented connection values and nothing conflicts:

> **Start here:** [`lab-setup.docx`](lab-setup.docx) is the consolidated,
> end-to-end install & configuration guide — repository, one-time network
> setup, shared stack, scenario load, Glossary Generator configuration, PDC
> connections, and the rebuild troubleshooting (Parts A-I). This README is
> the quick reference for the lab stack itself.


| Scenario | PostgreSQL database | MinIO bucket | Read-only users |
| --- | --- | --- | --- |
| CSCU | `cscu_core` (11 tables) | `cscu-documents` (18 files) | `pdc_user` · `cscu_minio_user` |

The stack itself is scenario-free: containers `demo-postgres` and
`demo-minio` on the `demo-net` network, admin account `demo_admin`.
PostgreSQL publishes on host port **5433** (PDC's own PostgreSQL already
binds 5432 on the lab VM); in-container it is still 5432. MinIO publishes
on 9000/9001 as before.
Scenario data (schemas, tables, sample rows, documents, read-only grants)
is applied by the **loader script**, driven by each scenario folder's
`scenario.json` — drop a new scenario folder next to CSCU and it becomes
loadable with no script changes.

## Quick start (on the Docker host — the Ubuntu VM)

```sh
cp .env.example .env
make up                    # start the shared postgres + minio
make load SCENARIO=CSCU    # create cscu_core + cscu-documents, load + verify
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
   verifies the object count. Every scenario's bucket lives in the same
   MinIO.

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
- **From PDC (in the VM):** the same — `192.168.1.200:5433` /
  `http://192.168.1.200:9000` via the published ports. Use the **VM IP for
  data sources** and reserve `pentaho.io` for PDC's HTTPS URL; container
  names resolve only inside `demo-net` and are used only by the lab's own
  tooling.
- Database / schema / credentials per scenario: see the table above or
  `make console`. Full topology notes (hosts file, ufw, `https://pentaho.io`)
  are in each scenario's README.

*All scenario data is fictional and generated for training.*

## Troubleshooting — leftovers from the old AWC stack

The retired AWC-era lab ran as its own Compose project (`awc`), and Docker
keeps its artifacts until removed: a `awc-net` network (172.18.0.0/16) and
possibly old containers with a restart policy still attached to it. Nothing
in the current repo references them — clean them up once on the VM:

```sh
docker network inspect awc-net --format '{{range .Containers}}{{.Name}} {{end}}'
docker ps -a | grep -iE 'awc|az-water'      # any old AWC containers
docker rm -f <old-container> ...            # remove attached leftovers first
docker network rm awc-net
```

## Troubleshooting — PDC itself (same VM)

The lab stack and PDC share the VM, so a broken PDC blocks every workshop
even when `make status` is green. Known PDC platform issues are documented
in [`docs/PDC-VM-TROUBLESHOOTING.md`](../../docs/PDC-VM-TROUBLESHOOTING.md):

- **`opensearch-cluster-init ... exit 1` on `docker compose up`** — on this
  deployment (`cat-opensearch:2.19`, fresh volume) the node truststore
  omits the admin cert, so securityadmin can't initialize
  `.opendistro_security` — and the failure cascades, stranding the app
  tier in `Created` (site-wide 404). Automated end to end by
  [`pdc-reset.sh`](../../pdc-reset.sh) at the repo root; the doc carries
  the manual repair for a no-wipe fix.
- **Chrome `NET::ERR_CERT_AUTHORITY_INVALID` at `https://pentaho.io` with
  no "Proceed anyway"** — self-signed cert + HSTS. Quick bypass: focus the
  error page and type `thisisunsafe` blind; the clean cert-import path is
  in the doc. Recurs after every rebuild that regenerates the cert.
