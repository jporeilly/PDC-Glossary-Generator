# RETAIL courseware — Canyon Trail Outfitters (retail)

The workshop set for the retail scenario: Canyon Trail Outfitters (CTO), a
fictional Arizona outdoor-gear retailer — six stores, a loyalty program,
web/phone channels, and two planted defects (full card PANs stored in the
POS `payments` table, and opted-out customers still carrying live marketing
emails) that the workshops progressively expose and measure. Workshops 0–5
are built; the deeper Technical Track modules live in the CSCU set and
transfer directly.

## Workshops

| Workshop | Focus | Guide |
| --- | --- | --- |
| [Workshop-00-Preflight](Workshop-00-Preflight/) | Provision users & roles (Keycloak + PDC) — the CTO cast across all seven PDC roles | `Workshop-00-Guide.md` |
| [Workshop-01-Connect-Data-Sources](Workshop-01-Connect-Data-Sources/) | Connect `cto_retail` + the `cto-documents` bucket, bulk loader, ingest, Scan Files | `Workshop-01-Guide.md` |
| [Workshop-02-Structure-and-Metadata](Workshop-02-Structure-and-Metadata/) | Explore tables, columns, comments, documents — and bookmark the `card_no` defect | `Workshop-02-Guide.md` |
| [Workshop-03-Glossary-Terms](Workshop-03-Glossary-Terms/) | Build & import the business glossary (109 records), link 93 columns, assign stewards | `Workshop-03-Guide.md` |
| [Workshop-04-Profiling-and-Quality](Workshop-04-Profiling-and-Quality/) | Profile the tables; six business rules incl. the flagship opt-out + PCI no-full-PAN | `Workshop-04-Guide.md` |
| [Workshop-05-Data-Identification](Workshop-05-Data-Identification/) | Dictionaries + patterns on tables and documents; the `card_no` triangulation and the `loyalty_no` custom pattern | `Workshop-05-Guide.md` |

Each workshop folder carries a `Workshop-XX-Guide.md` — the authoritative
markdown master — and a `Workshop-XX-Guide.docx` generated from it in the
course design ([`tools/build-docx.py`](tools/)), with amber placeholder
boxes where screenshots from the CTO lab go.

## The CTO cast

| User | Role(s) | Owns |
| --- | --- | --- |
| sofia.marin | Data Steward · Business Steward | Sources, profiling, identification; Customer / Orders & Fulfillment / Store Operations terms |
| derek.boone | Business Steward | Merchandising, Inventory, Suppliers |
| ken.tanaka | Business Steward | Payments (the PCI story) |
| alicia.vega | Business Steward | Loss Prevention & Compliance |
| leo.fischer | Data Storage Administrator | Creates/ingests the data sources; custodian |
| tessa.nguyen | Data Developer | Authors the Workshop 4 business rules |
| casey.holt / robin.pierce | Data User / Business User | The analyst personas and the role-boundary contrast |
| catalog.admin | Admin (all seven in the lab) | Trainer superuser |

## Scenario assets

Lab stack (PostgreSQL `cto_retail`, 11 tables + MinIO `cto-documents`, 18
objects), domain pack and bulk-loader CSV live in
[`data_sources/RETAIL/`](../../data_sources/RETAIL/). Load with
`make load SCENARIO=RETAIL` in `data_sources/lab/`; configure the Glossary
Generator with `install-scenario.ps1` → RETAIL.

All Canyon Trail Outfitters data is fictional and generated for training.
