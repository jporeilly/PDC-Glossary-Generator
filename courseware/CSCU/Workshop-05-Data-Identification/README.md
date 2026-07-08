# Workshop 5: Data Identification

**Primary role:** Business Analyst
**Estimated time:** 45 min

## What's in this package

- **`Workshop-05-Guide.md`** — the workshop guide (markdown master, CSCU context).
- **Focus:** Data Dictionaries and Data Patterns across structured tables *and* unstructured documents (Data Discovery / string detection). The Technical Track goes deeper into building custom methods.

> The deck and Word guide for the CSCU edition have not been produced yet —
> `Workshop-05-Guide.md` is the authoritative source: build the .docx/.pptx from it
> and capture the screenshots at each `[SCREENSHOT]` marker on the CSCU lab.

## Assets used in this workshop

- `assets/CSCU-Branch-Cities-Dictionary.csv  (custom dictionary — CSCU service cities in member addresses and correspondence)`
- `assets/CSCU-Transaction-Types-Dictionary.csv  (custom dictionary — the txn_type_cd enum)`
- `assets/CSCU-Business-Glossary.csv  (glossary summary for reference)`
- `assets/Copper-State-Credit-Union-Business-Rules.sql`
- `assets/cscu-documents/correspondence/  (letters + emails scanned for string detection)`

## How to run it

1. Make sure the shared lab is running with CSCU loaded
   (`data_sources/lab/`: `make up && make load SCENARIO=CSCU`).
2. Make sure you have completed the previous workshops — this one builds on them.
   (In particular, the `members`, `cards` and `transactions` tables must be profiled.)
3. Work through `Workshop-05-Guide.md` step by step.

All Copper State Credit Union data is fictional and generated for training.
