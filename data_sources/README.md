# Data sources — lab kits, one folder per scenario

Each folder is a complete, self-verifying lab: PostgreSQL (sample schema +
data, auto-loaded) and MinIO (unstructured documents), on a shared Docker
network, ready for Pentaho Data Catalog — plus the scenario's installable
domain pack and the bulk-load CSV for the Glossary Generator.

| Folder | Scenario | Database | Documents |
| --- | --- | --- | --- |
| [`AWC/`](AWC/) | **Arizona Water Company** — water utility | `awc_operations` (6 tables) | `awc-documents` bucket |
| [`CSCU/`](CSCU/) | **Copper State Credit Union** — financial services | `cscu_core` (11 tables) | `cscu-documents` bucket (18 files) |

**Recommended: the shared lab** ([`lab/`](lab/)) — one PostgreSQL + one MinIO
hosting every scenario side by side (one database + one bucket each):

```sh
cd lab
cp .env.example .env
make up                    # shared postgres + minio
make load SCENARIO=CSCU    # and/or SCENARIO=AWC — they coexist
make console               # PDC connection details per scenario
```

Each scenario folder also carries a standalone compose stack for running that
scenario in isolation (`cd <ID> && cp .env.example .env && make all`) — never
run a standalone stack and the shared lab at the same time (same ports).

Each folder also carries:

- `<scenario>-domain-pack.zip` — the Glossary Generator scenario install
  (`domain_pack.json` + `people.json` roster + INSTALL.txt). Unzip into
  `glossary_generator/`, reseed the Dictionary, restart.
- `domain_pack/` — the same pack files unzipped, for reading and editing.
- `*-datasources.csv` — the two PDC connections pre-filled for the app's
  bulk connection loader (`/api/pdc/bulk-load`).

**Don't mix scenarios** — stand up one lab, install its pack, run its
courseware set (see `courseware/`). Credentials in these kits are lab values;
change them for anything beyond the lab.

*All scenario data is fictional and generated for training.*
