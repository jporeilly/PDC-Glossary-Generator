# cscu-documents — the CSCU unstructured document store

Uploaded to the `cscu-documents` MinIO bucket by `make load`. One folder per
document domain; PDC's File System Scan catalogs each object, and the Glossary
Generator's document harvest turns folders/files into glossary terms.

| Folder | Contents | Sensitivity story |
| --- | --- | --- |
| `compliance/` | BSA/AML test, NCUA exam response, PCI attestation, SAR summary (PDF) | HIGH — regulatory, SAR confidentiality |
| `correspondence/` | Member emails and letters (TXT/DOCX) | MEDIUM/HIGH — member PII |
| `loan-applications/` | Approved application forms (DOCX) | HIGH — income, collateral, credit data |
| `statements/` | Monthly account statements (CSV) | HIGH — account numbers, balances |
| `payments/` | ACH batch and return extracts (JSON) | HIGH — routing/account numbers |
| `rates/` | Published deposit rate sheets (CSV) | LOW — public |

The compliance PDFs and the payments extracts tie back to the database rows
(SAR 97001 structuring case, the R01 return, check 1044 fraud) so learners can
follow one story across structured and unstructured sources.

*All Copper State Credit Union data is fictional and generated for training.*
