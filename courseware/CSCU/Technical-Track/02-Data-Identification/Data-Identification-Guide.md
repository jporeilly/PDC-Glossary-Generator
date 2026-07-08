# Data Identification — the engine underneath Workshop 5 (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · Technical Track Module 02*

## 1. What identification is

Data Identification stamps **tags** and **business terms** (and drives
sensitivity) onto profiled columns and discovered documents. Two method types:

- **Dictionaries — match by content.** A value list; a column whose profiled
  values sit inside the list scores high similarity. Right tool for enums:
  `txn_type_cd`, `acct_type_cd`, `risk_rating_cd`.
- **Data Patterns — match by shape.** Weighted signals: column-name regex,
  position analysis (`AAAA-nnnnnn`), content regex. Right tool for
  identifiers: `CSCU-100501`, `ACC-00070001`, nine-digit routing numbers,
  card PANs.

`[SCREENSHOT: Data Operations → Data Identification Methods]`

## 2. Anatomy of a rule

Walk `cscu_transaction_types_rule.json` (Module 03): confidence formula
(0.8 × similarity + 0.2 × metadata), column-name regex with a score,
fire condition (confidence ≥ 0.6 OR metadata ≥ 0.7), actions (apply tags,
assign business term). Then `cscu_member_number.json`: three weighted signals
(name 0.3, shape 0.4, regex 0.3) against a 0.7 threshold.
`[SCREENSHOT: method rule editor]`

## 3. Policies and the run

Methods are grouped into a **policy**; the policy runs as a job over selected
sources. On CSCU: system methods (SSN, email, phone, credit card) find
`members.ssn`, `members.email`, `cards.card_no`; the custom methods from
Module 03 pick up the enums and CSCU identifiers.
`[SCREENSHOT: policy run + results on members]`

## 4. The rules that matter in operation

- **Profile first** — identification reads profiled values; an unprofiled
  table gives the engine nothing to match.
- **Identify once** — re-running after steward overrides (the Glossary
  Generator's Apply) clobbers their work. Baseline once, then curate.
- **Tags merge, sensitivity overwrites** — remember this when the app writes
  back.
- **Trust Score last** — it rolls up quality + ratings + lineage +
  classification + term links.

## 5. Where the steward fits

Identification is the **baseline**, not the verdict. The CSCU story:
`cards.cvv_cd` — a 3-digit column generic methods may miss — is caught by the
failing PCI business rule (Workshop 4), the PCI attestation document, and the
steward's review in the Glossary Generator. Module 01 applies that curation
over the PDC API.

All Copper State Credit Union data is fictional and generated for training.
