# cpc-documents — Cascade Precision Components document store

Unstructured content for the MFG scenario, uploaded to the `cpc-documents`
MinIO bucket by the lab loader. Six folders, mirroring what a precision
manufacturer really holds:

| Folder | Contents | Format |
| --- | --- | --- |
| quality | Certificate of Conformance, mill/material cert, AS9102 first-article report, for-cause supplier audit | PDF |
| compliance | ISO 9001 surveillance audit (finding: Released lots without CoC), AS9100 internal audit (finding: unapproved USE_AS_IS), calibration audit | PDF |
| ncr-reports | NCR-2026-014, the plating-escape 8D, MRB minutes | DOCX |
| correspondence | The expedite email that hit the suspended-supplier block, recall notification, supplier suspension letter, customer quote thread | TXT / DOCX |
| erp-exports | Work-order completion batch, ASL export | JSON |
| price-lists | Customer price list 2026 H2 (commercially sensitive) | CSV |

The content interlocks with the `cpc_mfg` database: the same part numbers
(`CPC-nnnnn`), lot numbers (`LOT-YYYY-nnnn`), work/purchase orders, NCRs,
suppliers, customers and defects appear in both — so identification,
discovery and the workshops' triangulation exercises work end to end.

All Cascade Precision Components data is fictional and generated for training.
