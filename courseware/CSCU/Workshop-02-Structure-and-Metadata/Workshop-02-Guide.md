# Workshop 2 — Explore Structure & Metadata (CSCU)

*Copper State Credit Union scenario · PDC 10.2.11*

As `jordan.blake` (Business Analyst) you explore what the ingest captured:
tables, columns, types, keys — and the business descriptions engineering left
as column comments.

## Part A — the database structure

1. **Data Canvas** → `CopperState_Core_Banking` → schema `cscu_core`.
   `[SCREENSHOT: Data Canvas — cscu_core table list]`
2. Open **members**: 16 columns. Read the technical metadata (types, PK) and
   the ingested comments — e.g. `ssn`: *"HIGHEST sensitivity — GLBA/identity-
   theft exposure. Mask everywhere outside servicing."*
3. Open **cards** and find `cvv_cd`. Its comment says the column **should not
   exist** (PCI DSS 3.2). Bookmark this — Workshops 4 and 5 turn that comment
   into a measurable rule and an identification finding.
   `[SCREENSHOT: cards.cvv_cd column metadata with comment]`
4. Trace a relationship chain: members → accounts → transactions (FKs), and
   loans → members.

## Part B — the document store

1. Open `CopperState_Documents` and browse the folder tree.
2. Preview `compliance/pci_dss_saq_attestation_2026.pdf` — note it names the
   same `cards.cvv_cd` issue found in Part A: structured and unstructured
   evidence of one governance story.
   `[SCREENSHOT: PDF preview — PCI attestation]`

## Part C — first searches

1. Global search: `member number` — observe hits across tables and documents.
2. Search `routing` — `ach_payments.ach_rte_no` plus the payments JSON files.
3. Save one search for reuse in Workshop 6.

## Checkpoint

- [ ] Can navigate schema → table → column and read comments
- [ ] Found `cvv_cd` and its PCI comment
- [ ] Previewed a compliance PDF; ran and saved a search

All Copper State Credit Union data is fictional and generated for training.
