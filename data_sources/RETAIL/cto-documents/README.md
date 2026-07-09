# cto-documents — Canyon Trail Outfitters document store

Unstructured content for the RETAIL scenario, uploaded to the `cto-documents`
MinIO bucket by the lab loader. Six folders, mirroring what a retailer really
holds:

| Folder | Contents | Format |
| --- | --- | --- |
| compliance | PCI DSS attestation (NON-COMPLIANT: full PANs in POS db), CCPA privacy request log, LP quarterly loss report, returns-policy audit | PDF |
| correspondence | Refund-dispute email thread, price-match email, denied-return letter, opt-out confirmation, backorder apology | TXT / DOCX |
| invoices | Supplier invoices (Alpine Peak Gear, Desert Sun Apparel, Granite Ridge Footwear) | DOCX |
| pos-exports | POS register closeout batch, web-orders export | JSON |
| pricing | July promo price sheet (note the 50% clearance line) | CSV |
| receipts | Store and web receipts with loyalty numbers and card last-4 | TXT |

The content interlocks with the `cto_retail` database: the same loyalty
numbers (`CTO-nnnnnn`), order numbers (`SO-nnnnnnnn`), SKUs (`CT-AAA-nnnn`),
customers, cases and defects appear in both — so identification, discovery
and the workshops' triangulation exercises work end to end.

All Canyon Trail Outfitters data is fictional and generated for training.
