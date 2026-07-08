# Arizona Water Company — scenario data kit (AWC)

The **water utility** training scenario: everything needed to load the 6-table `awc_operations` schema and the `awc-documents` bucket into
the **shared demo lab** (one PostgreSQL + one MinIO for all scenarios — see
[`../lab/`](../lab/)) and to configure the Glossary Generator for it.

## What's in this folder

| Item | What it is |
| --- | --- |
| `postgres-init/` | Schema + sample data + read-only `pdc_user` SQL, run by the lab loader |
| `awc-documents/` | The unstructured document set uploaded to the `awc-documents` bucket |
| `domain_pack/` | The Glossary Generator domain pack + steward roster (source files) |
| `awc-domain-pack.zip` | Ready-to-install pack (unzip into `glossary_generator/`, or use `install-scenario.sh`) |
| `awc-datasources.csv` | The two PDC connections, pre-filled for the app's bulk loader |
| `scenario.json` | Manifest the lab loader and installer scripts read |

## Load it into the shared lab

On the Docker host (the Ubuntu VM):

```sh
cd ../lab
cp .env.example .env      # first time only
make up                   # start demo-postgres + demo-minio (shared, all scenarios)
make load SCENARIO=AWC   # create + verify this scenario's database and bucket
make console              # reprint the PDC connection details
```

The loader creates, inside the **shared** containers:

| | Value |
| --- | --- |
| PostgreSQL database | `awc_operations` (schema `awc_operations`, **6 tables**, sample data loaded) |
| Read-only DB user | `pdc_user` / `catalog123!` |
| MinIO bucket | `awc-documents` (17 objects) |
| Read-only MinIO user | `awc_minio_user` / `minio_secret_123!` |

Scenarios coexist — loading AWC does not touch the other scenario's database
or bucket. `make remove SCENARIO=AWC` drops only this scenario's pair.

## Topology: app on Windows 11, sources + PDC in an Ubuntu VM

In the standard lab the **Glossary Generator app runs on the Windows 11
bare-metal host**, while the shared stack (PostgreSQL + MinIO) **and PDC
itself run inside an Ubuntu 24.04 VM** with the static IP **`192.168.1.200`**.
PDC is served at **`https://pentaho.io`**. Three vantage points connect to the
same two sources — use the right value for each:

| Who connects | PostgreSQL | MinIO (S3 API) |
| --- | --- | --- |
| **The app** (Windows host) | Host `192.168.1.200` : `5433` | Endpoint `http://192.168.1.200:9000` |
| **PDC** (containers in the VM) | `192.168.1.200:5433` | `http://192.168.1.200:9000` |
| **Shell on the VM** | `localhost:5433` | `http://localhost:9000` |

**Always use the VM IP `192.168.1.200` for the data sources**; reserve
`pentaho.io` for PDC's HTTPS URL. Never use `localhost` from Windows (that's
the Windows machine, not the VM), and never use Docker container names — they
resolve only inside the VM's Docker network. The IP endpoint also forces S3
**path-style** addressing, which MinIO requires (a hostname endpoint can make
S3 clients attempt virtual-host-style bucket URLs and fail).

### One-time setup on the VM (Ubuntu 24.04)

Docker publishes 5433/9000/9001 to the VM's interfaces (PostgreSQL sits on
**5433** because PDC's own database owns 5432 on this VM), so from the VM
side you only need the firewall open if `ufw` is on:

```sh
sudo ufw allow 5433/tcp   # demo-lab PostgreSQL  (app + PDC)
sudo ufw allow 9000/tcp   # MinIO S3 API (app + PDC)
sudo ufw allow 9001/tcp   # MinIO console (optional, browser only)
sudo ufw allow 443/tcp    # PDC (https://pentaho.io)
```

Give the VM its static IP (192.168.1.200) with a **bridged** network adapter
so the Windows host and the VM sit on the same LAN segment.

### One-time setup on the Windows 11 host

`pentaho.io` is a lab hostname, not public DNS — map it to the VM in the hosts
file. In an **elevated** PowerShell:

```powershell
Add-Content C:\Windows\System32\drivers\etc\hosts "192.168.1.200  pentaho.io"
```

Then verify everything is reachable from Windows:

```powershell
Test-NetConnection 192.168.1.200 -Port 5433                      # PostgreSQL
curl.exe http://192.168.1.200:9000/minio/health/live -i          # MinIO -> 200
curl.exe -k https://pentaho.io/ -I                               # PDC UI
```

### Values to enter in the Glossary Generator (on Windows)

**Database connection (Connections → Database, live scan)**

| Field | Value |
| --- | --- |
| Host | `192.168.1.200` (plain hostname/IP — never a URL) |
| Port | `5433` |
| Database | `awc_operations` |
| Schema | `awc_operations` |
| User / Password | `pdc_user` / `catalog123!` (read-only) |

**Document store connection (Connections → Document store, MinIO/S3)**

| Field | Value |
| --- | --- |
| Endpoint | `http://192.168.1.200:9000` (`9001` is the web console, not the API) |
| Access key / Secret | `awc_minio_user` / `minio_secret_123!` (read-only) |
| Bucket | `awc-documents` |

**PDC connection (Apply / Harvest / bulk-load panels)**

| Field | Value |
| --- | --- |
| Base URL | `https://pentaho.io` (server root — the app adds `/api/public/...` itself) |
| Verify TLS | **off** for the lab's self-signed certificate |
| Account | an admin or Business Steward PDC account |

The shipped **`awc-datasources.csv`** already uses `192.168.1.200` for both rows, so the
bulk loader registers sources PDC can reach with no edits.

## Notes

- Lab credentials (`catalog123!`, `minio_secret_123!`, the `demo_admin`
  accounts in `../lab/.env`) are training values — change them for anything
  beyond the lab.
- Rebuilding this scenario from scratch: `make remove SCENARIO=AWC && make
  load SCENARIO=AWC` in `../lab/`.
- The courseware for this scenario lives in `../../courseware/AWC/`.

*All Arizona Water Company data is fictional and generated for training.*
