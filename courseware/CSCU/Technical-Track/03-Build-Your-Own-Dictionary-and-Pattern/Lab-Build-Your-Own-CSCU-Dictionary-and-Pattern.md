# Lab — Build Your Own CSCU Dictionary & Pattern

*Copper State Credit Union scenario · PDC 11.0.0 · Technical Track Module 03*

**Primary role:** Data Steward / Data Storage Administrator
**Estimated time:** 60 min

> **Tags stay governed.** Every `applyTags` value in this lab comes from the
> app's governed vocabulary, and the app's Dictionary page previews how those
> tags will look as search facets — including which buckets are still empty.
> Empty there means *no reviewed app usage yet*, not "no PDC assets": running
> the policies you author here is exactly what fills PDC's real facet. See
> *Tags & the Domain Pack → Reading the Search facet preview* for the retire
> rules.

> **Why author by hand when the app can draft?** The Glossary Generator's
> **Draft policies (AI)** produces files in exactly these shapes from its scan
> evidence. This lab teaches the anatomy — signatures, weights, confidence
> conditions, apply-tags — so a draft is something you can *judge*, not just
> import. Stewards who can read a rule can also fix one.

## From concept to authoring

Module 02 covered the engine: how Dictionaries match content, Data Patterns
match shape, and a policy applies Tags and Business Terms to profiled data.
This lab does not re-teach that. Here you author the methods CSCU actually
needs, import the full library, and run it — first on the core banking
database, then on the document store. PDC ships 95 dictionaries and a library
of patterns, but none of them know CSCU's member numbers, account codes,
NACHA return codes, or BSA/AML vocabulary. You will build those.

> **Remember.** Data Identification runs on *profiled* data (structured) or
> *discovered* data (documents). A method can only match values it can see —
> and the Trust Score is computed last, after tags exist. In the CSCU cast
> this lab runs as `elena.ramirez` or `omar.haddad` — Data Operations → Data
> Identification Methods is role-gated to Data Steward / Data Storage
> Administrator.

## What you'll build — the CSCU method library

Twenty-five methods, each tied to a real column or document in the CSCU
dataset: **eighteen dictionaries** (match by content) and **seven patterns**
(match by shape). You author one of each by hand to learn the screens, then
import the rest from the supplied files. There are three import routes:

- **Upload Dictionary** — a one-column CSV of values, loaded straight into a
  new dictionary (the simplest route).
- **Import Dictionaries** — a ZIP of CSV value-lists and JSON rules; loads
  the whole dictionary library at once (`CSCU-Dictionaries.zip`).
- **Import Patterns** — a JSON file (or a ZIP of JSON); loads a pattern, or
  all of them together (`CSCU-Patterns.zip`).

The library groups into six categories. The full method-by-method index is in
the appendix (and in `INDEX.csv`).

| Category | What it covers | Methods |
| --- | --- | --- |
| CSCU_Status | Account, member, card, loan, KYC, SAR and ACH state vocabularies | Dictionaries |
| CSCU_Reference | Product/transaction/card/role reference lists, branch names, service cities | Dictionaries |
| CSCU_Lending | Loan types and servicing status | Dictionaries |
| CSCU_Compliance | Risk ratings, SAR activity types, identity documents | Dictionaries |
| CSCU_Payments | ACH status, NACHA return codes, routing numbers | Dictionaries + Patterns |
| CSCU_Identifier / PCI / PII / Finance | Every ID format: member, account, loan, card PAN, email, GL account | Patterns |

## Before you begin

- **Profile the structured tables.** The `cscu_core` tables you want to tag —
  members, accounts, cards, transactions, loans, ach_payments, kyc_reviews,
  suspicious_activity, gl_entries — must already be profiled (Workshop 4).
- **Discover the documents.** For the `cscu-documents` store (the compliance
  PDFs, loan applications and correspondence), run Metadata Ingest and Data
  Discovery first — documents are not column-profiled.
- **Check your role.** Creating and importing methods requires the Data
  Steward or Data Storage Administrator role. No Data Operations → Data
  Identification Methods card means a permissions issue, not a missing
  feature.
- **Have the library files.** The value CSVs, rule JSONs,
  `CSCU-Dictionaries.zip`, `CSCU-Patterns.zip`, and `INDEX.csv` from this
  module's folders.

## Part A — Build a dictionary, then import the rest

A dictionary matches by content: it compares a column's actual values against
a known list. You'll author one — **CSCU Transaction Types** — to learn every
field, then import the other seventeen in one step.

### Author CSCU Transaction Types (Upload Dictionary route)

1. **Open the page.** Left nav → Data Operations → on the Data
   Identification Methods card, click **Dictionaries → Add Dictionary**.
2. **Name & category.** Name it `CSCU Transaction Types`; in Category type
   `CSCU_Reference` and click Add New. Leave Dictionary Status enabled.
3. **Apply Values.** Choose Upload Dictionary, upload
   `cscu_transaction_types.csv` (8 values: POS, ATM, ACH_CR, ACH_DR, XFER,
   FEE, DIVIDEND, CHECK), and set a confidence score of 0.8.
   `[SCREENSHOT: Add Dictionary — values uploaded]`
4. **Column-Name Regex.** Add the hint `(?i)txn_?type|transaction_?type` at
   0.9, and set the pane weight to 0.2. (Similarity 0.8 + metadata 0.2 =
   1.0.)
5. **Condition.** Confidence Score ≥ 0.6 **OR** Metadata Score ≥ 0.7.
6. **Actions.** Assign Tag `Transaction Type`; assign Business Term
   `Transaction Type Code`.
7. **Create.** Click Create Dictionary. `transactions.txn_type_cd` is now
   recognised by what it *contains*, not its name.

### Import the other seventeen

Rather than re-key each one, load them together: **Dictionaries → Import →
upload `CSCU-Dictionaries.zip` → Continue.** Track it on the Workers page.
Each dictionary arrives with its value-list and rule already configured.
`[SCREENSHOT: dictionary import — seventeen loaded]`

> **Increasing complexity — the kinds of dictionary you just loaded.**
> *Simplest* — a closed value list (Account Status, Card Status, SAR Status):
> no name hint needed beyond the default. *With hints + a term* — Branch
> Names adds a column-name hint and assigns the **Branch Record** business
> term. *Compliance-driving* — Risk Ratings tags `compliance` and assigns
> **Risk Rating Code**, feeding the BSA/AML story. *Beyond a value list* —
> Service Cities (16 towns) is the one that also fires on the document store
> in Part D, matching cities inside correspondence.

> **Note.** A dictionary created by the Select Column route works on
> structured data only. To match values inside documents, the dictionary must
> be CSV-uploaded — which is why the library ships every dictionary as a CSV.

## Part B — Build a pattern, then import the rest

A pattern matches by shape: it reduces each value to a position signature and
tests a regular expression. You'll author **CSCU Member Number**, then import
the other six.

### Author CSCU Member Number

1. **Open the page.** Data Operations → Data Identification Methods → Data
   Patterns → **Add Pattern**.
2. **Name & category.** Name it `CSCU Member Number`; Category
   `CSCU_Identifier`; status enabled.
3. **Column-Name Regex.** Add `(?i)(mbr|member)_?(no|num|number)`; weight
   this pane 0.3.
4. **Content Patterns.** Add the position signature `AAAA-nnnnnn` (four
   letters, a kept dash, six digits); weight this pane 0.4.
5. **Content Regex.** Add `^CSCU-\d{6}$`; weight this pane 0.3.
6. **Check the weights.** The three pane weights must sum to 1.0
   (0.3 + 0.4 + 0.3).
7. **Condition & Actions.** Confidence Score ≥ 0.7. Assign Tags `Member
   Number` and `Sensitive`; Assign Business Term `Member Number`.
   `[SCREENSHOT: Add Pattern — CSCU Member Number configured]`
8. **Create.** Click Create Pattern. A real value is `CSCU-100501` — the
   CSCU prefix, then the six-digit member sequence.

### Import the other six

**Data Patterns → Import → upload `CSCU-Patterns.zip`** (or an individual
pattern JSON) → Continue. The seven ID formats across the CSCU estate:

| Pattern | Column / source | Format | Example |
| --- | --- | --- | --- |
| Member Number | members.mbr_no | ^CSCU-\d{6}$ | CSCU-100501 |
| Account Number | accounts.acct_no | ^ACC-\d{8}$ | ACC-00070001 |
| Loan Number | loans.ln_no | ^LN-\d{6}$ | LN-091001 |
| ABA Routing Number | ach_payments.ach_rte_no | ^\d{9}$ | 122100024 |
| Payment Card Number | cards.card_no | ^4\d{3}-\d{4}-\d{4}-\d{4}$ | 4111-1111-1111-1001 |
| Contact Email | members.email / employees.email | standard email regex | james.porter@email.com |
| GL Account Number | gl_entries.gl_acct_no | ^[1245]\d{3}$ | 1010 |

> **Qualify and disqualify.** Member numbers and loan numbers both end in six
> digits, so a loose pattern would collide. The anchored content regex keeps
> them exclusive — `^LN-\d{6}$` qualifies a loan and disqualifies a member.
> The card PAN pattern rarely fires on a *column* other than `cards.card_no`
> — it earns its keep in Part D, where it surfaces card references inside the
> dispute correspondence.

## Part C — Combine into escalating policies and run

A set of selected methods is a Data Identification **policy**. Run them in
three escalating passes rather than all at once — it keeps results legible
and mirrors how a steward rolls coverage out.

| Policy | Run on | Methods selected |
| --- | --- | --- |
| A — warm-up | members | Member Status (dict) + Member Number (pattern) + built-in Email, US ZIP, US Phone, SSN |
| B — operations | accounts, cards, transactions, loans, ach_payments | Account Types, Account Status, Card Types, Card Status, Transaction Types, Loan Types, Loan Status, ACH Status, NACHA Return Codes + Account Number, Loan Number, Routing Number, Card Number patterns |
| C — full | all cscu_core + kyc_reviews, suspicious_activity, gl_entries | every custom method + built-ins, run as one job; then carried onto cscu-documents in Part D |

### Run a policy

1. In Data Canvas, open a profiled table, then **Actions → Process → the
   Data Identification card**.
2. Click **Select Methods**, tick the methods for that policy, click Apply,
   then **Start**.
3. Watch the job on the **Workers** page — it runs asynchronously.
4. Back in Data Canvas, matching columns now carry their tags, business terms
   and sensitivity.
   `[SCREENSHOT: policy run results on members]`

### What you should see

| Column | Method → result |
| --- | --- |
| members.mbr_no | Member Number pattern → member number, sensitive + term Member Number |
| members.mbr_status | Member Status dictionary → member status |
| transactions.txn_type_cd | Transaction Types dictionary → transaction type + term Transaction Type Code |
| cards.card_no | Card Number pattern → card number, pci, sensitive + term Card Number |
| ach_payments.ach_rte_no | Routing Number pattern → routing number, payments, sensitive + term ACH Routing Number |
| kyc_reviews.risk_rating_cd | Risk Ratings dictionary → risk rating, compliance + term Risk Rating Code |

And note the deliberate miss: `cards.cvv_cd` — three digits, no distinctive
shape, no value list — matches nothing. The failing PCI business rule
(Workshop 4) and the PCI attestation document catch what the engine cannot:
engines baseline, stewards decide.

## Part D — Run the methods on unstructured data

The same methods carry onto the `cscu-documents` store, with one change in
mechanism. Documents are not column-profiled — you run **Data Discovery**,
and on its Document Processing tab you reach identification three ways.

### Set up Document Processing

1. In Data Canvas, select the `cscu-documents` folder → Process → run
   Metadata Ingest, then open **Data Discovery**.
2. **String Detection.** Add dictionaries (CSCU Service Cities, CSCU Branch
   Names) and patterns (CSCU Member Number, CSCU Account Number, CSCU
   Payment Card Number). Choose *Detect presence*, or *presence and count*.
3. **Address Detection.** Enable it and choose a business term (e.g. Member
   Address) — files containing US postal addresses get tagged.
4. **Data Classification.** Supply the business terms that name your document
   classes — *Loan Application*, *Suspicious Activity Report*, *Member
   Statement* — and PDC assigns them by semantic content, no exact string
   required.
5. Click **Start Discovering** and track it on Workers.
   `[SCREENSHOT: Data Discovery — string detection configuration]`

> **The mechanism change that matters.** On documents, String Detection
> ignores the dictionary's rule — the confidence score and conditions that
> govern columns don't apply. It is a pure presence (or presence-and-count)
> match, after which the method's actions are applied to the file. So the
> same artifacts transfer, but a document is tagged because a value *appears*
> in it, not because a column crossed a confidence threshold.

### What you should see on the sample documents

| Document | Identified as |
| --- | --- |
| correspondence (txt and docx letters) | Member Number present (CSCU-100509) + Service City present (Tempe, Casa Grande) → member correspondence; card dispute letter also fires the Card Number pattern |
| loan-applications (docx forms) | Member Number + city present → classified Loan Application |
| compliance/sar_filing_summary_2026Q2.pdf | SAR vocabulary + member references → classified Suspicious Activity Report; compliance / Confidential |
| statements (csv) | Member Number + Account Number present (and counted) → classified Member Statement |

## Verify the results

- **Data Canvas.** Open tagged columns and document assets; confirm tags,
  business terms and Sensitivity are present.
- **Galaxy View.** See the tagging visually and locate sensitive and
  regulated data across the catalog at a glance.
- **Search.** Filter by the Member Number, Card Number or Risk Rating tag to
  prove assets are discoverable by what they *are*, not just by name.

## Gotchas & good practice

- **Profile (structured) or discover (documents) first.** A method only
  matches data it can see.
- **Re-running identification re-applies method tags.** If you hand-tune tags
  — or the Glossary Generator app writes overrides over the API — re-running
  the policy re-asserts the dictionary/pattern tags. Identify once, then
  curate; don't loop.
- **Tags are an array.** Over the API a PATCH replaces the whole tag set, so
  any tool that edits tags must read-merge-write. Sensitivity is a scalar and
  overwrites cleanly.
- **Pattern pane weights must sum to 1.0.** Column-Name + Content Patterns +
  Content Regex.
- **String detection ignores dictionary rules.** On documents it's
  presence/count only, and a column-derived dictionary can't be used there —
  use CSV-based dictionaries for the doc store.
- **Template the import envelope from an Export.** Author one method in the
  UI, click Export, and mirror that exact ZIP/JSON for bulk authoring. It's
  validated on load.
- **Trust Score is last.** It rolls up quality, lineage, ratings,
  classification and term assignment, so it only becomes meaningful after
  identification has run.

## How this connects

Module 02 taught the engine; here you authored its inputs for CSCU. The tags
this identification produces are what the Glossary Generator app rides on —
reading them over the API and letting a steward refine the resulting
glossary. Author the methods here; let the app curate the output there.
Next module: **01 — Glossary Generator App**.

## Appendix — CSCU method library index

### Dictionaries (match by content)

| Dictionary | Matches (column / source) | Size | Tags / term |
| --- | --- | --- | --- |
| CSCU Account Types | accounts.acct_type_cd | 5 values | account type |
| CSCU Account Status | accounts.acct_status | 3 values | account status |
| CSCU Member Status | members.mbr_status | 3 values | member status |
| CSCU Transaction Types | transactions.txn_type_cd | 8 values | transaction type + term Transaction Type Code |
| CSCU Card Types | cards.card_type_cd | 2 values | card type |
| CSCU Card Status | cards.card_status | 4 values | card status |
| CSCU Loan Types | loans.ln_type_cd | 5 values | loan type, lending |
| CSCU Loan Status | loans.ln_status | 5 values | loan status, lending |
| CSCU Risk Ratings | kyc_reviews.risk_rating_cd | 3 values | risk rating, compliance + term Risk Rating Code |
| CSCU KYC Status | kyc_reviews.kyc_status | 3 values | kyc status, compliance |
| CSCU SAR Activity Types | suspicious_activity.activity_type_cd | 4 values | sar activity, compliance + term Suspicious Activity Report |
| CSCU SAR Status | suspicious_activity.sar_status | 3 values | sar status, compliance |
| CSCU ACH Status | ach_payments.ach_status | 3 values | ach status, payments |
| CSCU NACHA Return Codes | ach_payments.return_cd | 10 values | nacha return code, payments |
| CSCU Branch Names | branches.br_name | 6 values | branch name + term Branch Record |
| CSCU Service Cities | members.city / branches.br_city + correspondence | 16 values | location, service city |
| CSCU Employee Roles | employees.role_cd | 5 values | employee role |
| CSCU Identity Document Types | kyc_reviews.id_doc_type_cd | 3 values | identity document, compliance |

### Patterns (match by shape)

| Pattern | Matches (column / source) | Format | Tags / term |
| --- | --- | --- | --- |
| CSCU Member Number | members.mbr_no | ^CSCU-\d{6}$ | member number, sensitive + term Member Number |
| CSCU Account Number | accounts.acct_no | ^ACC-\d{8}$ | account number, sensitive + term Account Number |
| CSCU Loan Number | loans.ln_no | ^LN-\d{6}$ | loan number, lending + term Loan Number |
| CSCU ABA Routing Number | ach_payments.ach_rte_no | ^\d{9}$ | routing number, payments, sensitive + term ACH Routing Number |
| CSCU Payment Card Number | cards.card_no | ^4\d{3}-\d{4}-\d{4}-\d{4}$ | card number, pci, sensitive + term Card Number |
| CSCU Contact Email | members.email / employees.email + correspondence | email regex | email, pii |
| CSCU GL Account Number | gl_entries.gl_acct_no | ^[1245]\d{3}$ | gl account, ledger |

All Copper State Credit Union data is fictional and generated for training.
