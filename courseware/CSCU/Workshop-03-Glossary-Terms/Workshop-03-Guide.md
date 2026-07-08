# Workshop 3 — Build the Business Glossary (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0*

You stand up CSCU's business glossary: eight categories (Member, Accounts &
Deposits, Cards & Payments, Transactions, Lending, Compliance & Risk, Finance
& Ledger, Branch Operations), one term per business-meaningful column, each
with sensitivity, CDE flag and governed tags — then link terms to columns and
assign stewards.

> **Two paths.** This workshop imports the prepared glossary
> (`CSCU-Business-Glossary.jsonl`) and reviews it — the manual path. The
> **Technical Track** builds the same glossary interactively with the
> **Glossary Generator app** (scan → review → govern → generate). Use one path
> per environment, not both.

## Why this workshop matters

Tables answer *where* data lives; the glossary answers *what it means* — in
the language the business actually speaks. Terms carry the definitions,
sensitivity and criticality that examiners ask about, and they are the
anchor that later links columns, documents and policies into one governed
vocabulary.

**The business problem.** Ask three CSCU departments what "member number"
means and you may get three answers (the ID, the account, the card). A
governed glossary makes one answer authoritative, assigns it a steward by
name, and connects it to the exact columns that hold it.

## What you will learn

- How a category tree and draft terms are imported in one pass — and why the
  import replaces the whole glossary.
- What a well-formed term carries: definition, sensitivity, CDE flag,
  governed tags, steward.
- How term-to-column links turn definitions into navigation.
- How stewardship maps CSCU's four business domains onto named Business
  Stewards.

## Part A — import the glossary

1. As `nadia.flores` (or any Business Steward): **Business Glossary →
   Actions → Import** → choose `assets/CSCU-Business-Glossary.jsonl`.
2. The import **replaces the whole glossary** — on a fresh instance that's
   fine; to update later, re-import a complete set with the same term ids.
3. Verify the eight categories and ~114 draft terms.
   `[SCREENSHOT: Business Glossary — category tree after import]`

## Part B — review the terms a steward owns

1. Open **Compliance & Risk** (Nadia's domain): *Risk Rating Code*,
   *Suspicious Activity Report*, *KYC Review Record* … — all HIGH/CDE.
2. Check the definitions came from the column comments (High confidence) and
   the tags stay inside the governed set (`compliance`, `aml`).
3. Open **Cards & Payments** and find *CVV Code*: its definition carries the
   PCI warning. Confirm sensitivity is HIGH; this term documents a defect,
   not an approved data element.
   `[SCREENSHOT: CVV Code term detail]`

## Part C — link terms to columns

As `elena.ramirez` (her Data Steward side carries the data-source write
rights a Business Steward lacks), use `assets/CSCU-Term-Linking-Map.csv`
(`schema,table,column → business_term`) to attach terms to the profiled columns — e.g. `members.mbr_no` → *Member
Number*, `ach_payments.ach_rte_no` → *ACH Routing Number*. In the UI: open the
column → **Business Terms → Add**. (The Technical Track automates exactly this
via the app's Resolve → Apply.)
`[SCREENSHOT: members.mbr_no with linked term]`

## Part D — stewardship

Assign each category's steward per `assets/users.csv` / the user-map CSV —
the expertise-driven map covers all nine categories:
Elena → Member, Accounts & Deposits, Transactions, Branch Operations;
Marcus → Lending, Finance & Ledger; Nadia → Compliance & Risk, Records &
Documents; Tom → Cards & Payments.

## Checkpoint

- [ ] Glossary imported: 8 categories, ~114 terms, status Draft
- [ ] CVV Code reviewed and HIGH
- [ ] At least five terms linked to columns
- [ ] Stewards assigned per domain

All Copper State Credit Union data is fictional and generated for training.
