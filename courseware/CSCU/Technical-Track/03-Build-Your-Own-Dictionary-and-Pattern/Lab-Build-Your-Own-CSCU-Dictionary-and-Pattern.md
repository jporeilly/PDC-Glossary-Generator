# Lab — Build Your Own CSCU Dictionary & Pattern

*Copper State Credit Union scenario · PDC 11.0.0 · Technical Track Module 03*

You author one **dictionary** (match by content) and one **pattern** (match by
shape), combine them into a **policy**, and run it against the profiled
`cscu_core` tables.

## Prerequisites

- `cscu_core` ingested and **profiled** (BA Workshops 1 and 4).
- A **Data Steward** or **Data Storage Administrator** login — in the CSCU
  cast that is `elena.ramirez` or `omar.haddad`; Data Operations → Data
  Identification Methods is role-gated.
- Module 02 (the engine deep-dive) is strongly recommended first.

## Part A — a dictionary: CSCU Transaction Types

1. Open **Data Operations → Dictionaries → Add** and upload
   `CSCU-Dictionaries/cscu_transaction_types.csv` (single `term` column, the
   eight `txn_type_cd` values: POS, ATM, ACH_CR, ACH_DR, XFER, FEE, DIVIDEND,
   CHECK). `[SCREENSHOT: dictionary upload dialog]`
2. Create the method from `cscu_transaction_types_rule.json`: name **CSCU
   Transaction Types**, category `CSCU_Reference`, column-name regex
   `(?i)txn_?type|transaction_?type` (score 0.9), tag **Transaction Type**,
   business term **Transaction Type Code**.
   `[SCREENSHOT: method configuration]`
3. Read the rule's anatomy: confidence = 0.8 × content similarity + 0.2 ×
   metadata score; the method fires when confidence ≥ 0.6 **or** metadata ≥
   0.7. A low-cardinality enum column scores near-perfect similarity — that is
   why dictionaries are the right tool for code columns.

## Part B — a pattern: CSCU Member Number

1. Open **Data Operations → Data Patterns → Add**: name **CSCU Member Number**,
   category `CSCU_Identifier`.
2. From `CSCU-Patterns/cscu_member_number.json`: column regex
   `(?i)(mbr|member)_?(no|num|number)` (weight 0.3), content pattern
   `AAAA-nnnnnn` (weight 0.4), content regex `^CSCU-\d{6}$` (weight 0.3),
   threshold 0.7; tags **Member Number**, **Sensitive**; business term
   **Member Number**. `[SCREENSHOT: pattern configuration]`
3. Anatomy: three signals — column *name*, value *shape* (position analysis),
   and an exact regex — each weighted. The shape catches `CSCU-100501` even in
   a column named something unhelpful; the name regex catches an empty column.

## Part C — combine into a policy and run

1. Add both methods to a Data Identification **policy** and run it scoped to
   `cscu_core.members` and `cscu_core.transactions`.
   `[SCREENSHOT: policy run]`
2. Verify: `transactions.txn_type_cd` tagged **Transaction Type** and linked to
   the term; `members.mbr_no` tagged **Member Number · Sensitive** and linked.
3. Spot-check a *miss*: `cards.cvv_cd` matches neither method — the planted
   PCI violation still needs the steward (Workshops 4–5 story).

## Going further

`INDEX.csv` lists all 18 dictionaries and 7 patterns that ship with this
module — enough for a full CSCU identification policy. Upload the bundles
(`CSCU-Dictionaries.zip`, `CSCU-Patterns.zip`) and enable selectively; run
**identification once**, then let the stewards override.

All Copper State Credit Union data is fictional and generated for training.
