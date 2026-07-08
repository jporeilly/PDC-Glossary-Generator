# Copper State Credit Union — Full Lab (PostgreSQL + MinIO)

One-command, self-verifying setup for the complete Pentaho Data Catalog
course environment: the **core banking database** (PostgreSQL with the CSCU
sample data) and the **document store** (MinIO with the unstructured files),
on a shared network, ready for PDC to connect to both.

## Prerequisites
- Docker with the Compose plugin (`docker compose`)
- `make`
- The `cscu-documents/` folder (included) and `postgres-init/` scripts
  (included) in this directory

## Quick start

```sh
make all
```

This runs `preflight → up → bucket → load → check` and stops at the first
failed check with a clear message. On success it prints the connection
details for **both** PDC data sources.

## What comes up

| Service     | Container           | What it holds                              |
|-------------|---------------------|--------------------------------------------|
| PostgreSQL  | `cscu-postgres` | `cscu_core` schema, 11 tables, sample data |
| MinIO       | `cscu-minio`    | `cscu-documents` bucket, 18 unstructured files |

The database **auto-loads** on first start: the SQL in `postgres-init/`
runs in name order, creating the schema, loading the sample data, and
creating the read-only `pdc_user`. The MinIO bucket, user, and document
upload are handled by the Makefile so their ordering is explicit.

## Targets

### Setup
| Command       | What it does                                          |
|---------------|-------------------------------------------------------|
| `make all`    | Full stack with checks at every step                  |
| `make up`     | Start both services and wait until each is ready      |
| `make bucket` | Create the MinIO bucket and read-only user            |
| `make load`   | Upload documents to MinIO                              |
| `make reload` | Clear and re-upload the documents                     |

### Verification
| Command             | What it checks                                          |
|---------------------|---------------------------------------------------------|
| `make check`        | Everything below — database AND object store            |
| `make pg-verify`    | DB: all 11 tables loaded + read-only user works          |
| `make pg-tables`    | Lists each table with its row count + the opt-out count |
| `make verify-bucket`| The MinIO bucket exists and is listable                 |
| `make verify-user`  | The read-only MinIO user can log in AND cannot write    |
| `make verify-files` | Uploaded object count matches the local file count      |
| `make status`       | Health of both services at a glance                     |

### Tools
| Command        | What it does                                          |
|----------------|-------------------------------------------------------|
| `make pg-shell`| Open an interactive `psql` shell on the database      |
| `make console` | Print PDC connection details for both sources         |
| `make logs`    | Tail logs from both services                          |

### Teardown
| Command        | What it does                                          |
|----------------|-------------------------------------------------------|
| `make clean`   | Stop and remove both containers (keeps data)          |
| `make destroy` | Remove both containers AND wipe all data              |
| `make pg-reset`| Rebuild ONLY the database from scratch (re-runs init) |

## What the checks catch

- **`preflight`** — Docker present and running, compose plugin available,
  the documents folder and the database init scripts both present.
- **`pg-up`** — waits for `pg_isready`, then polls until all 11 tables
  appear, so it knows the sample data finished loading before continuing.
- **`pg-tables`** — confirms every expected table exists, prints row
  counts, and confirms the `opted_out_marketing` column is populated (the
  Workshop 4 opt-out scenario depends on it).
- **`pg-user`** — confirms the read-only `pdc_user` can read AND that
  writes are denied, so PDC will connect and cannot mutate the data.
- **`verify-root`** — compares MinIO's running root user to `.env`, catching
  the credential-drift trap MinIO bakes into its data volume on first start.
- **`bucket`** — creates the bucket as its own committed step before any
  upload, so the auto-create race during `mc cp` cannot happen.
- **`verify-user` / `verify-files`** — the MinIO user is read-only, and the
  uploaded object count matches the local file count (no partial uploads).

## Configuration

Everything lives in `.env` — one source of truth for both services, so the
compose file and the Makefile cannot drift apart. Edit `.env` to change any
credential, port, bucket name, or the documents folder. `.env.example` is a
reference copy.

## Connecting Pentaho Data Catalog

Run `make console` any time to reprint these.

**Database source**

| Field    | Value (in-container)    | Value (from host) |
|----------|-------------------------|-------------------|
| Type     | PostgreSQL              | PostgreSQL        |
| Host     | `cscu-postgres`     | `localhost`       |
| Port     | `5432`                  | `5432`            |
| Database | `cscu_core`        | `cscu_core`  |
| User     | `pdc_user`              | `pdc_user`        |
| Password | `catalog123!`           | `catalog123!`     |

**Object-store source**

| Field             | Value (in-container)         | Value (from host)       |
|-------------------|------------------------------|-------------------------|
| Type              | S3-compatible / object store | S3-compatible           |
| Endpoint          | `http://cscu-minio:9000` | `http://localhost:9000` |
| Access Key        | `cscu_minio_user`             | `cscu_minio_user`        |
| Secret Key        | `minio_secret_123!`          | `minio_secret_123!`     |
| Bucket            | `cscu-documents`              | `cscu-documents`         |
| Path-Style Access | Enabled                      | Enabled                 |

Use the in-container values if PDC runs as a container on the `cscu-net`
network; use the host values if PDC runs on your machine.

## Notes
- Changing database credentials in `.env` after first start has no effect
  until you `make pg-reset` (or `make destroy`), because PostgreSQL — like
  MinIO — bakes its initial users into the data volume on first init.
- Both services share the `cscu-net` network, so PDC reaches both on one
  network.
