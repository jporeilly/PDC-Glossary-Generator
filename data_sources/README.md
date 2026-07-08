# Data sources — lab kits, one folder per scenario

Each folder is a complete, self-verifying lab: PostgreSQL (sample schema +
data, auto-loaded) and MinIO (unstructured documents), on a shared Docker
network, ready for Pentaho Data Catalog — plus the scenario's installable
domain pack and the bulk-load CSV for the Glossary Generator.

| Folder | Scenario | Database | Documents |
| --- | --- | --- | --- |
| [`AWC/`](AWC/) | **Arizona Water Company** — water utility | `awc_operations` (6 tables) | `awc-documents` bucket |
| [`CSCU/`](CSCU/) | **Copper State Credit Union** — financial services | `cscu_core` (11 tables) | `cscu-documents` bucket (18 files) |

Quick start (either scenario):

```sh
cd AWC        # or CSCU
cp .env.example .env
make all      # preflight -> up -> bucket -> load -> check
make console  # prints the PDC connection details
```

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
