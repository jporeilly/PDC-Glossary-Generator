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

## Topology: app on Windows 11, sources + PDC in an Ubuntu VM

In the standard lab the **Glossary Generator app runs on the Windows 11 bare-metal
host**, while this stack (PostgreSQL + MinIO) **and PDC itself run inside an
Ubuntu 24.04 VM** with the static IP **`192.168.1.200`**. PDC is served at
**`https://pentaho.io`**. Three different vantage points connect to the same
two sources — use the right value for each:

| Who connects | PostgreSQL | MinIO (S3 API) |
| --- | --- | --- |
| **The app** (Windows host) | Host `192.168.1.200` : `5432` | Endpoint `http://192.168.1.200:9000` |
| **PDC** (containers in the VM) | `192.168.1.200:5432` (published port) — or `cscu-postgres:5432` only if PDC shares this stack's Docker network | `http://192.168.1.200:9000` — or `http://cscu-minio:9000` on a shared network |
| **Shell on the VM** | `localhost:5432` | `http://localhost:9000` |

Never use `localhost` from Windows — that's the Windows machine, not the VM.
Container names (`cscu-postgres`, `cscu-minio`) resolve **only inside the
VM's Docker network**; from Windows they fail with *name resolution* errors. The
IP endpoint also forces S3 **path-style** addressing, which MinIO requires.

### One-time setup on the VM (Ubuntu 24.04)

Docker publishes 5432/9000/9001 to the VM's interfaces (the compose `ports:`
mappings), so from the VM side you only need the firewall open if `ufw` is on:

```sh
sudo ufw allow 5432/tcp   # PostgreSQL  (app + PDC)
sudo ufw allow 9000/tcp   # MinIO S3 API (app + PDC)
sudo ufw allow 9001/tcp   # MinIO console (optional, browser only)
sudo ufw allow 443/tcp    # PDC (https://pentaho.io)
```

Give the VM its static IP (192.168.1.200) with a **bridged** network adapter so
the Windows host and the VM sit on the same LAN segment.

### One-time setup on the Windows 11 host

`pentaho.io` is a lab hostname, not public DNS — map it to the VM in the hosts
file. In an **elevated** PowerShell:

```powershell
Add-Content C:\Windows\System32\drivers\etc\hosts "192.168.1.200  pentaho.io"
```

Then verify everything is reachable from Windows:

```powershell
Test-NetConnection 192.168.1.200 -Port 5432                      # PostgreSQL
curl.exe http://192.168.1.200:9000/minio/health/live -i          # MinIO -> 200
curl.exe -k https://pentaho.io/ -I                               # PDC UI
```

### Values to enter in the Glossary Generator (on Windows)

**Database connection (Connections → Database, live scan)**

| Field | Value |
| --- | --- |
| Host | `192.168.1.200` (plain hostname/IP — never a URL) |
| Port | `5432` |
| Database | `cscu_core` |
| Schema | `cscu_core` |
| User / Password | `pdc_user` / `catalog123!` (read-only) |

**Document store connection (Connections → Document store, MinIO/S3)**

| Field | Value |
| --- | --- |
| Endpoint | `http://192.168.1.200:9000` (`9001` is the web console, not the API) |
| Access key / Secret | `cscu_minio_user` / `minio_secret_123!` (read-only) |
| Bucket | `cscu-documents` |

**PDC connection (Apply / Harvest / bulk-load panels)**

| Field | Value |
| --- | --- |
| Base URL | `https://pentaho.io` (server root — the app adds `/api/public/...` itself) |
| Verify TLS | **off** for the lab's self-signed certificate |
| Account | an admin or Business Steward PDC account |

The shipped **`cscu-datasources.csv`** already uses `192.168.1.200` for both rows, so the
bulk loader registers sources PDC can reach with no edits. If you instead run
PDC *on this stack's Docker network*, container names work too — the app's
**App reachability remap** on the CSV import panel rewrites hosts for the app's
own copies (e.g. `cscu-postgres=192.168.1.200`).

## Notes
- Changing database credentials in `.env` after first start has no effect
  until you `make pg-reset` (or `make destroy`), because PostgreSQL — like
  MinIO — bakes its initial users into the data volume on first init.
- Both services share the `cscu-net` network, so PDC reaches both on one
  network.
