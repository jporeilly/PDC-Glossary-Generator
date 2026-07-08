# CSCU courseware — Copper State Credit Union (financial services)

The workshop set for the credit-union scenario. Workshops 0–5 are built;
6–11 have not been produced yet.

## Workshops

| Workshop | Focus | Guide |
| --- | --- | --- |
| [Workshop-00-Preflight](Workshop-00-Preflight/) | Provision users & roles (Keycloak + PDC) | `Workshop-00-Guide.md` |
| [Workshop-01-Connect-Data-Sources](Workshop-01-Connect-Data-Sources/) | Connect `cscu_core` + the `cscu-documents` bucket, ingest, Scan Files | `Workshop-01-Guide.md` |
| [Workshop-02-Structure-and-Metadata](Workshop-02-Structure-and-Metadata/) | Explore tables, columns, comments, documents, first searches | `Workshop-02-Guide.md` |
| [Workshop-03-Glossary-Terms](Workshop-03-Glossary-Terms/) | Import & review the business glossary, link terms, assign stewards | `Workshop-03-Guide.md` |
| [Workshop-04-Profiling-and-Quality](Workshop-04-Profiling-and-Quality/) | Profile the tables; six business rules incl. the flagship opt-out + PCI CVV | `Workshop-04-Guide.md` |
| [Workshop-05-Data-Identification](Workshop-05-Data-Identification/) | Dictionaries + patterns on tables and documents; the cvv_cd triangulation | `Workshop-05-Guide.md` |

Each workshop folder carries a README (package + assets list) and a
`Workshop-XX-Guide.md` — the markdown master for the Word guide, with
`[SCREENSHOT]` markers where captures from the CSCU lab go. Decks and .docx
builds are pending; generate them from the guides.

## Glossary Generator (Technical Track) notes

| File | What it is |
| --- | --- |
| `Workshop-Glossary-Generator-CSCU.md` | The app-driven glossary workshop (scan → review → govern → generate) |
| `Glossary-Generator-Tags-and-Domain-Pack.md` | Topic note: governed tags & the credit-union pack |
| `Glossary-Generator-LLM-and-Review.md` | Topic note: LLM setup & review-grid behaviour |
| `PDC-Object-Stores-AWS-S3-MinIO.md` | Topic note: registering the `CopperState_Documents` MinIO store |

Scenario assets: lab stack (PostgreSQL `cscu_core`, 11 tables + MinIO
`cscu-documents`, 18 files), sample data, documents and the installable domain
pack live in `data_sources/CSCU/` (`cscu-domain-pack.zip`).

All Copper State Credit Union data is fictional and generated for training.
