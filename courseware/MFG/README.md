# MFG courseware — Cascade Precision Components (manufacturing)

The workshop set for the manufacturing scenario: Cascade Precision
Components (CPC), a fictional Pacific Northwest maker of precision
hydraulic valves, fittings and manifolds — six plants, a bill of materials
(the strongest lineage story in the course), full lot traceability, and
three planted quality-system defects (two Released lots without a
Certificate of Conformance, a CRITICAL nonconformance dispositioned
USE_AS_IS without MRB approval, and a purchase order issued to a suspended
supplier). This is the deliberate **non-PII scenario**: Workshop 5's
built-in identification run goes almost silent, proving that
identification is a meaning engine, not a privacy engine — and that
industrial estates need custom method libraries. Workshops 0–5 are built;
the deeper Technical Track modules live in the CSCU set and transfer
directly.

## Workshops

| Workshop | Focus | Guide |
| --- | --- | --- |
| [Workshop-00-Preflight](Workshop-00-Preflight/) | Provision users & roles (Keycloak + PDC) — the CPC cast across all seven PDC roles | `Workshop-00-Guide.md` |
| [Workshop-01-Connect-Data-Sources](Workshop-01-Connect-Data-Sources/) | Connect `cpc_mfg` + the `cpc-documents` bucket, bulk loader, ingest, Scan Files | `Workshop-01-Guide.md` |
| [Workshop-02-Structure-and-Metadata](Workshop-02-Structure-and-Metadata/) | Explore tables, columns, comments, documents — and bookmark the CoC and MRB defects | `Workshop-02-Guide.md` |
| [Workshop-03-Glossary-Terms](Workshop-03-Glossary-Terms/) | Build & import the business glossary (118 records), link 100 columns, assign stewards | `Workshop-03-Guide.md` |
| [Workshop-04-Profiling-and-Quality](Workshop-04-Profiling-and-Quality/) | Profile the tables; six business rules incl. CoC-before-release, MRB approval and the suspended-supplier PO | `Workshop-04-Guide.md` |
| [Workshop-05-Data-Identification](Workshop-05-Data-Identification/) | The non-PII lesson: built-ins go quiet, then the custom part/lot pattern library lights the estate up | `Workshop-05-Guide.md` |

Each workshop folder carries a `Workshop-XX-Guide.md` — the authoritative
markdown master — and a `Workshop-XX-Guide.docx` generated from it in the
course design ([`tools/build-docx.py`](tools/)), with amber placeholder
boxes where screenshots from the CPC lab go.

## The CPC cast

| User | Role(s) | Owns |
| --- | --- | --- |
| nora.whitaker | Data Steward · Business Steward | Sources, profiling, identification; Production / Traceability / Plant Operations terms |
| felix.okonkwo | Business Steward | Parts & BOM, Suppliers & Purchasing (engineering) |
| yuki.mori | Business Steward | Quality & Inspection, Nonconformance (the CoC and MRB stories) |
| silas.grant | Business Steward | Shipments & Customers (the recall story) |
| petra.novak | Data Storage Administrator | Creates/ingests the data sources; custodian |
| andre.gibson | Data Developer | Authors the Workshop 4 business rules |
| mia.torres / owen.fitch | Data User / Business User | The analyst personas and the role-boundary contrast |
| catalog.admin | Admin (all seven in the lab) | Trainer superuser |

## Scenario assets

Lab stack (PostgreSQL `cpc_mfg`, 11 tables + MinIO `cpc-documents`, 18
objects), domain pack and bulk-loader CSV live in
[`data_sources/MFG/`](../../data_sources/MFG/). Load with
`make load SCENARIO=MFG` in `data_sources/lab/`; configure the Glossary
Generator with `install-scenario.ps1` → MFG.

All Cascade Precision Components data is fictional and generated for training.
