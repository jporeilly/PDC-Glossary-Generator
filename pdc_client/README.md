# pdc_client — shared Pentaho Data Catalog public-API client

Stdlib-only Python client for the PDC Public API (v2/v3), extracted from the
Glossary Generator so sibling apps (Policy Generator, future tools) can share
one client instead of maintaining parallel copies.

Modules (each may only lean on earlier ones):

| Module | Covers |
|---|---|
| `core.py` | transport, auth (`/auth`, Keycloak fallback), response helpers, `TokenExpired` |
| `terms.py` | business-term resolution and id stamping |
| `entities.py` | entity filter/resolve, catalog harvest |
| `jobs.py` | jobs: trust score, discovery, profiling, status polling |
| `apply.py` | merge + PATCH write-back of businessTerms/features |
| `bulkload.py` | bulk data-source loader (CSV → create/test/ingest) |

## Consuming it

From the Glossary app: `import pdc_api` (a shim in `glossary_generator/`
re-exports this package unchanged). From another repo, either:

```bash
pip install -e /path/to/PDC-Glossary   # installs the pdc_client package
```

or vendor the directory — it has no dependencies beyond the standard library.

Request shapes are validated offline against the official v3 OpenAPI contract
in `glossary_generator/tests/test_v3_shapes.py`.
