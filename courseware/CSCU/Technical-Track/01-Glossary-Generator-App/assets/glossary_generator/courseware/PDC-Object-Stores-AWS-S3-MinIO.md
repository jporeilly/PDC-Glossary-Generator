# PDC Reference — Registering an AWS S3 / MinIO Object Store

*Arizona Water Company (AWC) courseware · companion to the Bulk-load data sources step*

This note captures the hard-won details of getting an object store (AWS S3 or a
MinIO/S3-compatible bucket) into Pentaho Data Catalog via the API, so nobody has to
re-derive them. The `Arizona_Water_Documents` MinIO bucket is the worked example.

---

## 1. The one thing that trips everyone up: `databaseType = "AWS"`

PDC decides **how** to ingest a source from a single field on the data-source record:

| Source kind | Field that routes it | Value |
|---|---|---|
| Relational database | `databaseType` | `POSTGRES`, `MYSQL`, … |
| Object store / file system | `databaseType` | **`AWS`** (for S3 **and** MinIO) |

An object store is **not** a database to PDC — it is a *file system*. But the routing
value is still carried in `databaseType`, and for an S3-compatible store that value is
the literal string **`AWS`**.

Values that look right but are **wrong**:

- `S3` → the source is created with **no type**; the Edit Data Source form shows
  "Select…" and none of the connection fields appear.
- `AWS_S3` (underscore) → same blank type; the ingest falls back to the JDBC/database
  path and fails with *"could not connect"* or *"Metadata Ingest FAILED"*.

The authoritative way to confirm the value on any PDC instance: create one S3 source by
hand in the UI (Data Source Type → **AWS S3**), save, then read its stored `databaseType`
via `POST /api/public/v2/data-sources/filter`. On PDC 10.2 it is `AWS`.

> There is no separate `fileSystemType` on the create body — PDC derives it from
> `databaseType = "AWS"` at scan time. Send only `databaseType`.

## 2. Connection fields

For `databaseType = "AWS"`, the record carries:

| Field | Value for `Arizona_Water_Documents` | Notes |
|---|---|---|
| `endpoint` | `http://192.168.1.200:9000` | Full URL. Use an **IP** for MinIO — it forces S3 *path-style* addressing, which MinIO requires. |
| `region` | `us-east-1` | Any value works for MinIO. |
| `container` | `awc-documents` | This is the **bucket**. "Container" is PDC's generic term across object stores (Azure calls it a container; S3/GCS call it a bucket). |
| `path` | `/` | Folder within the bucket to scan; `/` = whole bucket. |
| access key | `awc_minio_user` | Stored/sent as **`accessId`** (the loader also sends `accessKey`/`accessKeyID` for safety). |
| secret key | *(secret)* | `secretKey` / `secretAccessKey`. |
| `configMethod` | `credentials` | vs. IAM role / secrets manager. |

## 3. Creating vs. scanning — a public-API boundary

This is the key architectural fact:

- **Creating** the source is fully supported on the public API
  (`POST /api/public/v2/data-sources`). The loader does this correctly for object stores.
- **Scanning** the bucket (the "File System Scan") is **not exposed on the public API**.
  The UI's **Scan Files** button calls an *internal* endpoint, `POST /api/start-job`, with
  a `{ name: "METADATA_INGEST", type: "START", data: { …the source object… } }` envelope.

Do **not** confuse this with `POST /api/public/v2/jobs/execute/metadata/ingest` — that is
the **database schema** ingest. It requires `databaseType`, and on an object store it runs
a schema-style "Metadata Ingest" that has nothing to scan, so it fails.

### Recommended (stable) workflow

1. **Bulk-load / create** the object-store source via the loader (public API). It comes up
   correctly typed as AWS S3 with all fields populated.
2. Open it in PDC and click **Scan Files** (one click; this is the internal call, made by a
   human, not by courseware code). It runs the File System Scan.
3. **Harvest from PDC** pulls the scanned files into the glossary.

The Glossary Generator's loader has an **experimental toggle** ("scan object stores via
internal API") that calls `/api/start-job` for you. It works, but it is undocumented and
unversioned — treat it as a lab convenience, not a supported integration.

## 4. Scoping the scan — include / exclude patterns

Add `includePatterns` / `excludePatterns` (semicolon- or comma-separated globs) to the
data-source config; they flow into the scan. Example: `excludePatterns = *.md;*.tmp`
skips those files. The AWC `Arizona_Water_Documents` row excludes `*.md`.

## 5. Network reachability — two vantage points

The same source needs **different host values depending on who connects**:

| Who connects | Host to use | Why |
|---|---|---|
| **PDC** (bulk-load / harvest) | Docker service name, e.g. `az-water-postgres`, `http://192.168.1.200:9000` | PDC runs on the Docker network and resolves service names. |
| **The Glossary app** (Schema / Files / Test / live-scan) | Host reachable from where the app runs, e.g. `localhost:5433`, `192.168.1.200:9000` | The app runs outside Docker; service names don't resolve, and container ports must be published to the host. |

So the loader CSV keeps the PDC-correct names, and **Add to app connections** offers a
reachability remap (`az-water-postgres=localhost, 5432=5433`) to rewrite host/port on the
app's copies at import time. A Docker service name that fails from the app host with
*"Temporary failure in name resolution"* is this, not a credential problem.

## 6. Loader CSV columns (clean format)

```
kind,resourceName,host,port,databaseName,userName,password,schemaNames,
endpoint,region,accessKey,secretKey,container,path,
includePatterns,excludePatterns,databaseType,fqdnId,description
```

- **Database row** fills `host, port, databaseName, userName, password, schemaNames`
  (set `schemaNames` to the schema the tables actually live in — an ingest into an empty
  schema reports OK but harvests nothing).
- **Object-store row** fills `endpoint, region, accessKey, secretKey, container, path`
  and (optionally) `excludePatterns`. Leave `databaseType` blank — the loader sets `AWS`
  — or set it explicitly to override.

---

### Quick troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Edit form: Data Source Type = "Select…", no fields | `databaseType` is `S3`/`AWS_S3` | Use `databaseType = AWS`. |
| `ingest jdbc metadata / could not connect` | Object store routed as a database | `databaseType = AWS` (not `AWS_S3`). |
| `HTTP 400 … required property 'databaseType'` | `databaseType` omitted | It is required on create; send `AWS`. |
| `HTTP 500 on metadata/ingest` | Called the DB ingest on an object store | Don't; create only, then Scan Files. |
| DB ingest OK but 0 tables | `schemaNames` points at an empty schema | Set it to the real schema (e.g. `awc_operations`, not `public`). |
| App scan: "Temporary failure in name resolution" | App used a Docker service name | Use the host-reachable address (`localhost:5433`). |
