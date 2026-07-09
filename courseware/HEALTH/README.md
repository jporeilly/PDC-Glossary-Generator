# HEALTH courseware — Lakeshore Health Partners (healthcare)

The workshop set for the healthcare scenario: Lakeshore Health Partners
(LHP), a fictional Minnesota clinic network — six clinics from Minneapolis
to Duluth, six providers, and three planted HIPAA defects (patient SSNs
leaked inside free-text clinical notes, a marketing disclosure without a
signed authorization, and opted-out patients still carrying live marketing
emails) that the workshops progressively expose and measure. Workshops 0–5
are built; the deeper Technical Track modules live in the CSCU set and
transfer directly.

## Workshops

| Workshop | Focus | Guide |
| --- | --- | --- |
| [Workshop-00-Preflight](Workshop-00-Preflight/) | Provision users & roles (Keycloak + PDC) — the LHP cast across all seven PDC roles | `Workshop-00-Guide.md` |
| [Workshop-01-Connect-Data-Sources](Workshop-01-Connect-Data-Sources/) | Connect `lhp_clinical` + the `lhp-documents` bucket, bulk loader, ingest, Scan Files | `Workshop-01-Guide.md` |
| [Workshop-02-Structure-and-Metadata](Workshop-02-Structure-and-Metadata/) | Explore tables, columns, comments, documents — and bookmark the `note_txt` defect | `Workshop-02-Guide.md` |
| [Workshop-03-Glossary-Terms](Workshop-03-Glossary-Terms/) | Build & import the business glossary (121 records), link 108 columns, assign stewards | `Workshop-03-Guide.md` |
| [Workshop-04-Profiling-and-Quality](Workshop-04-Profiling-and-Quality/) | Profile the tables; six business rules incl. the flagship opt-out, SSN-in-notes and disclosure-authorization | `Workshop-04-Guide.md` |
| [Workshop-05-Data-Identification](Workshop-05-Data-Identification/) | Dictionaries + patterns on tables and documents; the free-text blind spot and the MRN custom pattern | `Workshop-05-Guide.md` |

Each workshop folder carries a `Workshop-XX-Guide.md` — the authoritative
markdown master — and a `Workshop-XX-Guide.docx` generated from it in the
course design ([`tools/build-docx.py`](tools/)), with amber placeholder
boxes where screenshots from the LHP lab go.

## The LHP cast

| User | Role(s) | Owns |
| --- | --- | --- |
| maya.lindqvist | Data Steward · Business Steward | Sources, profiling, identification; Patient / Appointments & Encounters / Clinic Operations terms |
| anders.berg | Business Steward | Diagnoses & Results, Prescriptions (HIM lead) |
| rosa.jimenez | Business Steward | Claims & Billing, Payers (revenue cycle) |
| hannah.weiss | Business Steward | Privacy & Disclosures (Privacy Officer) |
| victor.osei | Data Storage Administrator | Creates/ingests the data sources; custodian |
| ingrid.dahl | Data Developer | Authors the Workshop 4 business rules |
| jamal.carter / beth.nakamura | Data User / Business User | The analyst personas and the role-boundary contrast |
| catalog.admin | Admin (all seven in the lab) | Trainer superuser |

## Scenario assets

Lab stack (PostgreSQL `lhp_clinical`, 11 tables + MinIO `lhp-documents`, 18
objects), domain pack and bulk-loader CSV live in
[`data_sources/HEALTH/`](../../data_sources/HEALTH/). Load with
`make load SCENARIO=HEALTH` in `data_sources/lab/`; configure the Glossary
Generator with `install-scenario.ps1` → HEALTH.

All Lakeshore Health Partners data is fictional and generated for training.
