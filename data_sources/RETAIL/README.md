# Canyon Trail Outfitters — scenario data kit (RETAIL)

The **retail** training scenario: everything needed to load the 11-table
`cto_retail` schema and the `cto-documents` bucket into the **shared demo
lab** (one PostgreSQL + one MinIO for all scenarios — see
[`../lab/`](../lab/)) and to configure the Glossary Generator for it.

Canyon Trail Outfitters (CTO) is a fictional Arizona outdoor-gear retailer:
six stores from Phoenix and Tempe to Globe and Prescott, a loyalty program,
web and phone channels, and the two planted defects the workshops hunt —
**full card PANs stored unmasked in the POS payments table** (PCI DSS) and
**opted-out customers still carrying live marketing emails** (consumer
privacy), plus a refund-abuse pattern feeding a loss-prevention case.

## What's in this folder

| Item | What it is |
| --- | --- |
| `postgres-init/` | Schema + sample data + read-only `pdc_user` SQL, run by the lab loader |
| `cto-documents/` | The unstructured document set uploaded to the `cto-documents` bucket |
| `domain_pack/` | The Glossary Generator domain pack + steward roster (source files) |
| `cto-domain-pack.zip` | Ready-to-install pack (unzip into `glossary_generator/`, or use `install-scenario.sh`) |
| `cto-datasources.csv` | The two PDC connections, pre-filled for the app's bulk loader |
| `scenario.json` | Manifest the lab loader and installer scripts read |

## Load it into the shared lab

On the Docker host (the Ubuntu VM):

```sh
cd ../lab
cp .env.example .env        # first time only
make up                     # start demo-postgres + demo-minio (shared, all scenarios)
make load SCENARIO=RETAIL   # create + verify this scenario's database and bucket
make console                # reprint the PDC connection details
```

The loader creates, inside the **shared** containers:

| | Value |
| --- | --- |
| PostgreSQL database | `cto_retail` (schema `cto_retail`, **11 tables**, sample data loaded) |
| Read-only DB user | `pdc_user` / `catalog123!` |
| MinIO bucket | `cto-documents` (18 objects) |
| Read-only MinIO user | `cto_minio_user` / `minio_secret_123!` |

Scenarios coexist — loading RETAIL does not touch the other scenario's
database or bucket. `make remove SCENARIO=RETAIL` drops only this scenario's
pair.

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
**path-style** addressing, which MinIO requires. One-time VM firewall and
Windows hosts-file setup is identical for every scenario — see
[`../CSCU/README.md`](../CSCU/README.md) or [`../lab/README.md`](../lab/README.md).

### Values to enter in the Glossary Generator (on Windows)

**Database connection (Connections → Database, live scan)**

| Field | Value |
| --- | --- |
| Host | `192.168.1.200` (plain hostname/IP — never a URL) |
| Port | `5433` |
| Database | `cto_retail` |
| Schema | `cto_retail` |
| User / Password | `pdc_user` / `catalog123!` (read-only) |

**Document store connection (Connections → Document store, MinIO/S3)**

| Field | Value |
| --- | --- |
| Endpoint | `http://192.168.1.200:9000` (`9001` is the web console, not the API) |
| Access key / Secret | `cto_minio_user` / `minio_secret_123!` (read-only) |
| Bucket | `cto-documents` |

**PDC connection (Apply / Harvest / bulk-load panels)**

| Field | Value |
| --- | --- |
| Base URL | `https://pentaho.io` (server root — the app adds `/api/public/...` itself) |
| Verify TLS | **off** for the lab's self-signed certificate |
| Account | an admin or Business Steward PDC account |

The shipped **`cto-datasources.csv`** already uses `192.168.1.200` for both
rows, so the bulk loader registers sources PDC can reach with no edits.

## Notes

- Lab credentials (`catalog123!`, `minio_secret_123!`, the `demo_admin`
  accounts in `../lab/.env`) are training values — change them for anything
  beyond the lab.
- Rebuilding this scenario from scratch: `make remove SCENARIO=RETAIL &&
  make load SCENARIO=RETAIL` in `../lab/`.
- The courseware for this scenario lives in `../../courseware/RETAIL/`.

*All Canyon Trail Outfitters data is fictional and generated for training.*
