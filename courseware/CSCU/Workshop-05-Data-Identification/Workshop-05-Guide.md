# Workshop 5 — Data Identification (CSCU)

*Copper State Credit Union scenario · PDC 10.2.11*

Data Identification stamps **tags and sensitivity** onto columns (and, via
Data Discovery, documents) using two method types: **dictionaries** (match a
value list) and **patterns** (match a regex). CSCU is rich in both.

> **Identify once.** Run Data Identification as a one-time baseline. After the
> stewards override tags/sensitivity (Technical Track: the Glossary Generator's
> Apply), re-running identification clobbers their work.

## Part A — system methods on the banking tables

1. As `elena.ramirez` (**Data Steward** — in v11, Data Identification
   Methods belong to the Data Steward and Data Storage Administrator roles;
   Dana's Data Developer role cannot author them): **Data Operations → Data
   Identification**. Confirm the
   built-in methods relevant to CSCU are enabled: SSN, Email Address, Phone
   Number, **Credit Card Number**, US Address/ZIP.
2. Run identification on `members`, `cards`, `accounts`, `transactions`,
   `ach_payments`.
3. Review the results: `members.ssn` → SSN (HIGH), `cards.card_no` → Credit
   Card Number (HIGH — the 4111… test PANs match the issuer pattern + Luhn),
   `members.email` / `phone` → contact PII.
   `[SCREENSHOT: identification results on members]`
4. **The planted finding:** `cards.cvv_cd` — a 3-digit column the generic
   methods may miss. Pair it with Workshop 4's failing PCI rule and the PCI
   attestation PDF: identification, quality and documents all point at the
   same defect. That triangulation is the lesson.

## Part B — custom dictionaries

1. **Data Operations → Dictionaries → Add**: upload
   `assets/CSCU-Branch-Cities-Dictionary.csv` (single `term` column) as
   **CSCU Service Cities**. `[SCREENSHOT: dictionary upload]`
2. Upload `assets/CSCU-Transaction-Types-Dictionary.csv` as
   **CSCU Transaction Types**.
3. Attach each to a method and re-run identification on `members` (city
   column) and `transactions` (`txn_type_cd`). Low-cardinality enum columns
   light up precisely — that's what dictionaries are for.

## Part C — unstructured: Data Discovery on the documents

1. Run **Data Discovery** on `CopperState_Documents`, scoped to
   `correspondence/`.
2. String detection finds member PII inside the letters — names, addresses,
   the member numbers (`CSCU-100509`), account references — and the city
   dictionary matches the branch cities.
   `[SCREENSHOT: discovery results on a correspondence letter]`
3. Compare sensitivity now shown on the documents vs. the folders' defaults.

## Part D — read the results like a steward

- Tags applied by identification are the **baseline**; Workshop 3's glossary
  terms and the stewards' judgement sit above it.
- Sensitivity conflicts (name-pattern LOW vs. identified HIGH) resolve toward
  the identified value — but a steward override (Technical Track) wins last.

## Checkpoint

- [ ] System methods identified SSN / card / contact PII on the five tables
- [ ] Two CSCU dictionaries uploaded and matched
- [ ] Data Discovery ran over correspondence/ and tagged member PII
- [ ] You can explain the cvv_cd triangulation (rule + method + PDF)

All Copper State Credit Union data is fictional and generated for training.
