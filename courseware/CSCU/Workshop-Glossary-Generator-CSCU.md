# Workshop — Build the Business Glossary with the Glossary Generator

*Copper State Credit Union (CSCU) scenario · app 1.7.x · validated against PDC 10.2.11*

**Primary role:** Data Steward / Solution Architect
**Estimated time:** 60–90 min
**Prerequisites:** the shared lab running with CSCU loaded
(`data_sources/lab` → `make up && make load SCENARIO=CSCU`),
PDC reachable over HTTPS, the CSCU domain pack installed
(`data_sources/CSCU/cscu-domain-pack.zip` → unzip into `glossary_generator/`).

---

## 1. The scenario

**Copper State Credit Union** is a fictional Arizona credit union with six
branches (Phoenix, Tempe, Tucson, Casa Grande, Globe, Prescott), ~13 pilot
members, and a core banking schema (`cscu_core`, 11 tables)
plus a document store (`cscu-documents` bucket, 18 files). Its data estate has
exactly the governance problems the Registry approach fixes:

- **PII everywhere** — SSNs, DOBs, card PANs, account and routing numbers spread
  across `members`, `cards`, `accounts`, `ach_payments`.
- **A planted PCI violation** — `cards.cvv_cd` stores card verification values,
  which PCI DSS forbids after authorization. Your steward review must catch it.
- **Cryptic core-banking names** — `mbr_no`, `prin_bal_amt`, `apr_rt`,
  `ach_rte_no`. The generator's abbreviation expansion (plus the CSCU pack)
  turns them into readable terms: *Member Number*, *Principal Balance Amount*,
  *APR*, *ACH Routing Number*.
- **A compliance story that spans sources** — SAR 97001 (structuring: two
  $9,450 transfers just under the $10,000 threshold) exists as database rows
  (`suspicious_activity`, `ach_payments`, `transactions`) *and* as documents
  (the Q2 SAR summary PDF, the ACH batch JSON). One glossary must cover both.

## 2. What you will build

An import-ready **business glossary** for PDC — one reviewed term per
business-meaningful column and document folder, each with governed tags
(`pci`, `aml`, `lending`, …), rule-based sensitivity, CDE flags, and steward
assignments — plus the **Registry** the Policy Generator will later read to
emit Data Identification methods.

## 3. Lab flow

### Step 1 — Stand up the sources

```sh
cd data_sources/lab
cp .env.example .env
make up                    # shared postgres + minio (all scenarios)
make load SCENARIO=CSCU    # cscu_core db + cscu-documents bucket, verified
```

`make console` reprints the PDC connection values (database
`CopperState_Core_Banking`, object store `CopperState_Documents`).

### Step 2 — Register the sources in PDC

Use the app's **bulk loader** (Connections → Bulk-load data sources) with
`data_sources/CSCU/cscu-datasources.csv`, or create the two sources by hand.
Then run **Metadata Ingest → Profile → Data Identification** in PDC, and click
**Scan Files** on the document store. (Identify *once* — the steward's
overrides come later and must not be clobbered.)

### Step 3 — Install the scenario and start the app

Unzip `cscu-domain-pack.zip` into `glossary_generator/` (this drops
`domain_pack.json` and the `people.json` steward roster), delete any previous
`tag_dictionary.json`, then `./run.sh`. Confirm on `/config` that
`GLOSSARY_COMPANY=Copper State Credit Union`.

### Step 4 — Scan & review

Connect to `cscu_core` (schema `cscu_core`, read-only `pdc_user`), **Scan**,
then **Add to glossary** from the MinIO bucket so one glossary spans both
sources. On the review grid:

- Check the expansions: `mbr_since_dt` → *Member Since Date*, `apr_rt` → *APR
  Rate*. Edit anything weak.
- Confirm sensitivity: `ssn`, `card_no`, `acct_no` must be HIGH. The profiler
  and the pack's sensitivity floors should already say so — verify, don't trust.
- **Find the planted violation:** `cvv_cd` on `cards`. Its column comment and
  the PCI attestation PDF both flag it. Keep the term, set sensitivity HIGH,
  tag `pci`, and note the remediation in the definition — the glossary is where
  the finding becomes visible to everyone.
- Check the tags the CSCU pack derived: `ach_rte_no` → `payments · ach`,
  `risk_rating_cd` → `compliance · aml`, statements folder → `statement ·
  records`. A bare `document` tag means a vocabulary gap — extend the pack,
  don't hand-edit.

### Step 5 — Govern

The roster is pre-seeded with the CSCU team, each steward carrying the
expertise keywords the matcher uses. **Auto-assign all slots** and verify
the result: *Elena Ramirez* stewards **Member, Accounts & Deposits,
Transactions, Branch Operations**; *Marcus Webb* **Lending, Finance &
Ledger**; *Nadia Flores* **Compliance & Risk, Records & Documents**; *Tom
Callahan* **Cards & Payments**. Elena's Data Steward role fills the
**owner** slots, and *Omar Haddad* (Data Storage Administrator) fills every
**custodian** slot — every pick shows its confidence and matched terms.
Set ratings (Auto/DQ), review date, and status.

### Step 6 — Generate, import, resolve, apply

**Generate JSONL** (writes the Registry alongside), import it in PDC
(**Business Glossary → Actions → Import**), **Resolve term ids**, then
**Apply to PDC** — dry-run first, always. Finish with the Trust Score rollup.

## 4. Checkpoints

| # | Check | Evidence |
| --- | --- | --- |
| 1 | 11 tables + 18 documents scanned | Sources chip on the Glossary page |
| 2 | `cvv_cd` flagged HIGH / `pci` | The review grid row + your note |
| 3 | SAR terms marked CDE, HIGH | `suspicious_activity` terms |
| 4 | Tags all governed (no drift) | Dictionary page: 0 off-vocabulary |
| 5 | Stewards assigned per domain | Govern page slots |
| 6 | Registry written at export | `registries/registry.<glossary>.json` |

## 5. Where the story continues

The Registry you just produced is the input contract for the **Policy
Generator**, which emits the Data Identification dictionaries and patterns
(card PAN, routing number, SSN) bound to these term ids — and then drift-checks
them. That is a separate session.

---

*All Copper State Credit Union data — members, accounts, transactions, SARs and
documents — is fictional and generated for training.*
