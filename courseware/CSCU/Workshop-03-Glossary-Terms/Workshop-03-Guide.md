# Workshop 3 — Build the Business Glossary (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · Business Glossary*

**Primary role:** Business Steward
**Estimated time:** 60 min

## Why this workshop matters

In Workshops 1 and 2 you connected CSCU's data and learned to read its three
metadata layers — and you saw the business layer come up empty, because that
knowledge does not live on the table. It lives in the Business Glossary. This
workshop fills that gap. You will build CSCU's glossary: the controlled
vocabulary that turns a cryptic column like `mbr_no` into a governed term
with a plain-language definition, an owner, and a sensitivity level — then
link those terms to the Catalog so every analyst speaks the same language.

> **The business problem.** An NCUA examiner asks CSCU to show every field
> that holds member personal data, who owns it, and how it is classified.
> Without a glossary, that means crawling more than a hundred columns across
> eleven tables and guessing which ones are PII. With a glossary, the
> member's personal fields — name, SSN, date of birth, email, phone — are
> governed terms, each defined once, classified once, and linked to every
> matching column, so the answer is a single search. Workshop 3 builds that
> vocabulary.

## What you will learn

- What a Business Glossary is, and how the Glossary, Category, and Term
  hierarchy organizes CSCU's business language — and why each layer exists.
- The built-in properties that carry governance — Domain, Sensitivity,
  Classification, Business Steward, and Owner — and why they live on the
  term, not the table.
- How to create a glossary, categories, and terms in the Data Canvas.
- How to import a glossary from a CSV or JSON Lines file — and how to get
  the exact format by exporting first.
- How to link business terms to their columns across every table in the
  source, and recalculate each table's Trust Score.
- How the Similarity Score powers the Suggested Columns you approve — and
  where the engine behind it is configured and run (the Technical Track).

## Background: how a glossary is organized

PDC organizes business language as a three-level hierarchy. A **Glossary** is
the top-level container; **Categories** group related terms; and **Terms**
are the individual governed concepts, each with its own definition and
properties. A term can sit under a category, directly under a glossary, or
stand alone (in which case it shows as Unassigned). Tags are separate —
lightweight, informal labels for quick discovery that complement terms
rather than replace them.

Why these four parts exist: each solves a different problem. The Glossary is
the single, definitive reference, so the business stops arguing over what a
word means. Categories make that vocabulary navigable, so an analyst can
find terms by business area instead of scrolling a flat list. Terms let you
define and govern a concept once — definition, owner, sensitivity — rather
than re-deciding it on every table. And Linked Data Elements connect that
business language to the physical columns and files that implement it,
across every data source, so one search answers "where does this live and
how is it governed?" and one change shows its full impact.

| Level | What it is | CSCU example |
| --- | --- | --- |
| Glossary | The top-level container for a body of business language. | CSCU Business Glossary |
| Category | A grouping of related terms within a glossary. | Member; Cards & Payments; Compliance & Risk |
| Term | A single governed business concept, with a definition and properties. | Member Number; Card Number; Risk Rating Code |

`[SCREENSHOT: Business Glossary — glossary, categories and terms in the navigation tree]`

A glossary nests categories and terms, links each term to the real columns
and files, with tags alongside.

### The properties that make a term governed

Every glossary item carries built-in properties. These — not the table — are
where CSCU's governance actually lives. Sensitivity, Domain, and Status are
always present: PDC shows them on every term with a default value, so they
are never blank — set them deliberately rather than leaving the default. The
rest you fill in as policy dictates.

| Property | What it records | Example for Member Number |
| --- | --- | --- |
| Sensitivity | Unknown, Low, Medium, or High. Always shown; defaults to Unknown. | High |
| Domain | The industry domain the term belongs to, chosen from PDC's built-in domain list. Always shown; the CSCU import lands terms as General — refine deliberately if your list carries a finance domain. | General |
| Status | Draft, Review, Accepted, or Deprecated. Always shown; defaults to Draft. | Accepted |
| Classification | Public, Private, or Company Confidential. | Company Confidential |
| Business Steward | The role accountable for changes to the term. | Elena Ramirez |
| Owner | The role responsible for maintaining the term. | Elena Ramirez |
| Custodian | The role or person who maintains the data day to day, distinct from the accountable Owner. | Omar Haddad |
| Review Date | When the term is next due for review. Shown in the UI as "Reviewed At". | 30 Sep 2026 |
| Stakeholders | People or roles with an interest in the term, beyond Owner and Steward. | Nadia Flores (BSA/AML) |

**Link it and it sticks:** these properties map straight to the Glossary tab
you saw in Workshop 2 — assign a term to `members` and the table inherits
this governance context.

`[SCREENSHOT: Term Summary — the Properties panel]`

### Tags and Custom Properties

A term carries two more layers of metadata beyond the built-in properties,
and you set both on its Summary page.

**Tags:** lightweight, free-text labels for discovery and grouping. Type
them into the Tags card on the right of the term's Summary page, and reuse
them across terms. For CSCU, useful tags include `pii`, `glba`, `pci`,
`aml`, `compliance`, `member-facing` and `ncua`. Tags complement terms —
they do not replace them.

**Custom Properties:** admin-defined fields that extend the built-in set. An
Admin defines each property once for the whole Catalog (a name and a type);
a Business Steward then fills in its value per term, on the term's Custom
Properties tab. Because a property must exist before you can set it,
creating custom properties is an Admin task (`catalog.admin`) outside this
workshop — here you simply assign values to any that already exist.
Properties CSCU might define: *Regulation* (GLBA, PCI DSS, BSA), *Retention
period*, *Examination scope*.

`[SCREENSHOT: Term — Tags card and Custom Properties tab]`

## Before you begin

### Prerequisites

- Workshops 1 and 2 complete — both CSCU sources connected and explored.
- A **Business Steward** (or higher) PDC login — creating, importing, and
  editing glossary items is a governed action reserved for the Business
  Steward role. Work as `nadia.flores` for the import; `elena.ramirez`
  carries Business Steward alongside her Data Steward role, so she can do
  everything in this workshop too. (`jordan.blake` and `riley.morgan`
  cannot — try it and watch the actions stay disabled.)

### Assets used in this workshop

- The CSCU glossary content table in this guide — your source of truth for
  the terms you will build by hand in Part A.
- `assets/CSCU-Business-Glossary.jsonl` — the full glossary as 123 JSON
  Lines records (1 glossary + 8 categories + 114 terms), produced by the
  Glossary Generator pipeline and ready to import in Part B.
- `assets/CSCU-Term-Linking-Map.csv` — all 71 term-to-column links for Part
  D, grouped by table.
- `assets/CSCU-glossary-user-map.csv` — which steward owns which categories,
  for the stewardship pass in Part E.
- The connected `cscu_core` database — the `members` table is where you
  will link terms first.

## The CSCU glossary you will build

Here is a representative slice of the CSCU Business Glossary — a term or two
from each of its categories. The full glossary holds 114 terms across eight
categories — column-level terms plus one table-level term per table (Member
Record, Loan Record, and so on — you will meet those in Part C). Each row is
a term, grouped by category. Build this slice by hand in Part A, or import
the full glossary (`CSCU-Business-Glossary.jsonl`) in Part B.

| Term | Category | Sensitivity | Classification | Business Steward | Definition |
| --- | --- | --- | --- | --- | --- |
| Member Number | Member | High | Company Confidential | Elena Ramirez | Unique identifier of a credit-union member (format CSCU-nnnnnn). |
| SSN | Member | High | Private | Elena Ramirez | Social Security number of the member. |
| Account Number | Accounts & Deposits | High | Company Confidential | Elena Ramirez | Unique identifier of a deposit account. |
| Balance Amount | Accounts & Deposits | Medium | Company Confidential | Elena Ramirez | Current ledger balance of an account. |
| Card Number | Cards & Payments | High | Private | Tom Callahan | Primary account number (PAN) of a payment card. |
| Routing Number | Cards & Payments | Medium | Public | Tom Callahan | ABA routing number used for ACH transfers. |
| Transaction Amount | Transactions | Medium | Company Confidential | Elena Ramirez | Monetary amount of a posted transaction. |
| Loan Number | Lending | High | Company Confidential | Marcus Webb | Unique identifier of a loan (format LN-nnnnnn). |
| Risk Rating Code | Compliance & Risk | Low | Company Confidential | Nadia Flores | BSA/AML risk rating assigned at KYC review. |
| SAR Status | Compliance & Risk | Low | Company Confidential | Nadia Flores | Filing status of a Suspicious Activity Report. |
| General Ledger Account Number | Finance & Ledger | High | Company Confidential | Marcus Webb | Chart-of-accounts number a journal line posts to. |
| Branch Name | Branch Operations | High | Company Confidential | Elena Ramirez | Public-facing name of a CSCU branch. |

## Step-by-step

### Part A — Create the glossary in the Data Canvas

1. Click **Glossary** in the left navigation menu to open the Business
   Glossary page.
2. Click **Actions**, then **Add New Glossary**. Name it `CSCU Business
   Glossary` and click Continue. Add a Definition and a Purpose.
   `[SCREENSHOT: Create Glossary → Category → Term]`
3. Click **Actions**, then **Add New Category**. Create the eight
   categories: **Member, Accounts & Deposits, Cards & Payments,
   Transactions, Lending, Compliance & Risk, Finance & Ledger,** and
   **Branch Operations** — each with the CSCU Business Glossary as its
   Parent.
4. Click **Actions**, then **Add New Term**. For each term in the table
   above, enter its name, choose its category as the Parent, click Create,
   then add its Definition.
   `[SCREENSHOT: Create Term]`
5. On each term's Summary tab, open the Properties panel and set
   Sensitivity, Domain, Classification, Business Steward, Owner, Custodian,
   Stakeholders, and the Review Date. Set Status to **Accepted** when the
   term is ready.
   `[SCREENSHOT: Term Properties panel filled in]`
6. (Optional) Add Tags such as `pii`, `glba`, or `compliance` for quick
   discovery — tags complement the term, they do not replace it.

### Part B — Import the glossary from a file (the bulk method)

Building terms by hand is fine for a handful; for a real glossary you
import. PDC imports JSON Lines or CSV. This workshop ships the full CSCU
glossary as `CSCU-Business-Glossary.jsonl` — 123 records covering the
glossary, all eight categories, and 114 terms with definitions,
sensitivities and CDE flags already set.

> **Two paths to the same glossary.** This file was produced by the
> **Glossary Generator app** (scan → suggest → steward review → export),
> which the Technical Track drives end to end. In this workshop you consume
> its output as a Business Steward; in the Technical Track you produce it.
> Use one path per environment, not both — the import lands the whole tree.

1. Get the exact format first: after building one term in Part A, click
   **Actions**, then **Export**, choose CSV or JSON, and download. The
   exported file's columns are the precise schema any hand-built import
   must match. (The supplied JSONL is already in that shape.)
2. On the Business Glossary page, click **Actions**, then **Import**, drag
   in `CSCU-Business-Glossary.jsonl`, and click Submit.
   `[SCREENSHOT: Import a Glossary]`
3. Confirm the imported glossary, its eight categories, and 114 terms
   appear in the navigation tree.
4. Spot-check two terms: open **Cards & Payments → CVV Code** — its
   definition documents a PCI defect (Workshop 2 planted it), not an
   approved data element — and **Compliance & Risk → Risk Rating Code**,
   whose definition came straight from the column comment.
   `[SCREENSHOT: CVV Code term after import]`

> **Export before you import.** Importer columns can vary by version, so
> never hand-build a file blind. Export a glossary first — even a one-term
> one — and mirror its exact headers and Parent references. An exported
> file is guaranteed to round-trip back in.

> **Set the people-fields in the UI after import.** Import carries the
> descriptive properties — Definition, Sensitivity, Domain, Status,
> Classification. It does not carry Custodian, Owner, Review Date
> ("Reviewed At"), or Stakeholders. Those resolve to real users, so the
> people they name must exist in PDC first (Workshop 0), then be assigned
> on each term's Summary page after the import lands. Tags and Custom
> Properties are not in the import file either. Plan the short stewardship
> pass in Part E to set all of these.

### Part C — Link terms, then feed the table's Trust Score

> **KEY POINT — Trust Score is a table / file metric, never a column one.**
> Calculated at table/file level only. A column never gets its own Trust
> Score, so linking a term to a column will never produce one — no matter
> how the term is linked. **The table reads a table-level term.** Link each
> table's table-level term (Member Record, Loan Record, …) to the table
> itself, then run Calculate Trust Score. That table term — not the column
> links — is the glossary-term input the score actually reads. **Column
> links still matter — just not for the score.** They carry the term's
> meaning, sensitivity and ownership onto the column for search, lineage
> and governance. That is their job; feeding a column score is not. **The
> term input is binary.** The score asks only whether a meaningful term is
> assigned — not how many. Over-linking to inflate it is semantically wrong
> and degrades the governance the score measures. **Need a number on a
> column?** It is authored, not calculated — extract the entities, compute
> your own score, and bulk-write it back per column via the API — a
> Technical Track exercise, not part of this workshop.

**Where Trust Score lives.** Trust Score is a native metric on two entity
types only: tables and files. In PDC's hierarchy a column sits inside a
table and a folder sits above files, so the scored peers are the table and
the file — a file is the unstructured twin of a table, scored the same way.
A column and a folder are only a part or a container, and never carry a
Trust Score.

| Entity | Native Trust Score? | How it's set | What it means / carries |
| --- | --- | --- | --- |
| Table | Yes | Calculate (4 inputs) or type a value in Key Metrics | Reliability of the whole table — Data Quality, ratings, verified lineage, and a table-level term |
| File | Yes | Same as a table; Data Quality comes from Data Discovery | Reliability of a document — the same four inputs |
| Column | No | Authored only — bulk-write per column via the API | Profiling/DQ, sensitivity, tags and term links — for governance and discovery, not a score |
| Folder | No | — (a container) | The object-store equivalent of a schema; carries no score |

> **Which terms to map.** Not every term needs a column, and linking every
> term to every column to lift a score backfires — it pollutes governance,
> lineage, and search. Choose what to map by business relevance, then
> prioritize by risk and criticality: **CDEs and regulated or PII columns
> first** — at CSCU that is `ssn`, `dob`, `card_no`, `mbr_no` and their
> kin. Flag these as Critical Data Elements, link the right term, set
> sensitivity and classification, and verify lineage. Then reporting and
> KPI columns; then the long tail as capacity allows. **Leave concepts
> unmapped:** governance terms name ideas the business needs defined, not
> physical columns, so they are expected to have no data element.

**Enrich the columns** (optional; this does not feed the Trust Score). Work
as `elena.ramirez` — linking needs the glossary rights of a Business
Steward, and her Data Steward side carries the data-source view.

1. Click **Glossary** in the left navigation, then open a term you want to
   link — for example, **Member Number** under the Member category.
2. Click the **Data Elements** tab. It has two views: **Elements** (the
   columns already linked to this term) and **Suggested Columns** (matches
   PDC proposes for you).
   `[SCREENSHOT: Member Number — Data Elements tab]`
3. Click **+ Add Data Element**, choose the `CopperState_Core_Banking`
   source, and select the matching column — for Member Number that is
   `members.mbr_no`. It then appears in the Elements list with an Item Type
   of COLUMN. (Faster: open Suggested Columns, review PDC's matches, and
   Approve the right ones — approving assigns the term automatically. See
   the Similarity Score section further on.)
   `[SCREENSHOT: Suggested Columns — Member Number]`
4. Repeat for the other terms you are linking — for example **SSN** to
   `members.ssn`, and **Account Number** to `accounts.acct_no`.

These column links enrich each column for search, lineage and governance.
None of them feed the Trust Score — that comes next, with the table-level
term.

### What linking a term to a column means

Part C links terms to the Catalog through Add Data Elements (the Data
Elements tab). When you map a term to a column this way you create a
**Business Term Association** — a governed link between the business
concept and the physical field, identified as `table.column` (for example,
Phone → `members.phone`). The column itself does not change; what you have
added is a relationship. From that point:

- **Meaning travels to the data.** Anyone inspecting `members.phone` in the
  Catalog now sees the term's definition, sensitivity, classification and
  owner — none of which live on the table itself.
- **Classify once, govern everywhere.** The same term can map to matching
  columns in several tables — and across data sources, the structured
  database and the document store alike; set sensitivity and classification
  once on the term, and every linked element inherits them.
- **One term, many columns — a worked example:** a single business term can
  carry several Linked Data Elements, and its one governed meaning applies
  to every column at once. In CSCU, **Member Number** links to six elements
  across five tables: `members.mbr_no`, `members.mbr_id`,
  `accounts.mbr_id`, `loans.mbr_id`, `kyc_reviews.mbr_id`, and
  `suspicious_activity.mbr_id` — same definition, same High sensitivity,
  six physical homes. **Account ID** does the same across `accounts`,
  `cards`, `transactions`, `ach_payments` and `suspicious_activity`. Define
  it once on the term and all of them inherit it; re-classify the term and
  every linked column follows. That is what delivers consistency across
  systems, and it is what lets the term answer "where does this live, and
  what changes if I touch it?" in one place.
- **Discovery improves.** Searching the term — or filtering by HIGH
  sensitivity, or by the `pii` tag — now returns that column. The
  examiner's question becomes a single search.
- **It appears in lineage and the Galaxy View.** The association is a
  relationship edge connecting the business-term node to the data-asset
  node.
- **It feeds governance, not the score directly.** The glossary-term input
  the Trust Score reads is the table-level term, and it is binary — is a
  meaningful term assigned or not. It rewards having the right semantic
  coverage, not the volume of links.

You shouldn't link all terms to a column just to lift the score. The Trust
Score is calculated from multiple inputs — Data Quality (completeness,
accuracy, validity, uniqueness, consistency), User Ratings (1–5 stars),
Data Lineage (verified or not), and whether a glossary term is assigned —
and it operates at the table/file level, never scoring individual columns.
Linking every term you have to a single column would be semantically wrong:
a column should carry the term (or small set of terms) that genuinely
describes its content. Over-linking pollutes your glossary mappings, breaks
lineage and impact analysis, misleads anyone searching the catalog, and
undermines the very governance the Trust Score is trying to measure. You
would be optimizing a proxy metric while degrading the thing it is a proxy
for.

The better path to a high Trust Score is to treat the four inputs as a
checklist of genuine governance work: assign accurate business terms where
they belong, verify lineage, run data quality processing, and gather user
ratings. A table that is correctly termed, lineage-verified, and
quality-checked earns its score honestly — and stays trustworthy when
someone actually relies on it.

One practical combination worth calling out: your most important columns
are often both CDEs and well-termed. At CSCU, flag `ssn`, `card_no` and
`mbr_no` as Critical Data Elements so they get prioritized stewardship,
link them to the correct business term so people understand them, then make
sure quality and lineage are verified for those specifically. That is where
the effort pays off most.

**Feed the table's Trust Score**

1. Map the table-level term to the table. CSCU's glossary already carries
   one table term per table — Member Record, Member Account Record, Payment
   Card Record, Transaction Record, Loan Record, ACH Payment Record, KYC
   Review Record, Suspicious Activity Report, General Ledger Entry, Branch
   Record and Employee Record.
2. Open the `members` table's Glossary tab (or the Member Record term's
   Data Elements tab) and link **Member Record** to the `members` table.
   This table-level term — not the column links — is the glossary-term
   input the Trust Score actually reads.
   `[SCREENSHOT: members table — Glossary tab with Member Record linked]`
3. Run **Calculate Trust Score**. In the Data Canvas, open the
   `CopperState_Core_Banking` source and select the `members` table, then
   **Actions → Process → Start Calculate Trust Score**. The table term you
   just linked is one of the four inputs, so the number stays low until the
   others are in place.
   `[SCREENSHOT: members table — Trust Score after calculation]`

Why this works: the Trust Score is an aggregate of four inputs — Data
Quality, User Ratings, verified Data Lineage, and whether a Glossary Term
is assigned. Assigning a term satisfies one of them, and it is the only one
you can set without profiling the data. On its own it will not lift the
table out of Untrusted: Data Quality is the dominant input and stays Not
Computed until the data is profiled in Workshop 4.

To watch the score climb now, also rate the table (stars) and set its Data
Lineage to Verified, then re-run the calculation. In other words the Trust
Score is a sliding scale: it computes from whatever inputs are present and
rises as you add each one — a linked term, Verified lineage, a rating —
then climbs furthest once Data Quality is computed in Workshop 4.

### Part D — Link the rest of the Catalog

Part C linked one table; now repeat across the whole source. The map below
lists every business term and the column it links to, grouped by table —
all 71 links are also in `assets/CSCU-Term-Linking-Map.csv`. Work table by
table:

**Also link each table's table-level term:** as you finish each table, link
its table-level term to the table — Member Record to `members`, Member
Account Record to `accounts`, Payment Card Record to `cards`, Transaction
Record to `transactions`, Loan Record to `loans`, ACH Payment Record to
`ach_payments`, KYC Review Record to `kyc_reviews`, Suspicious Activity
Report to `suspicious_activity`, General Ledger Entry to `gl_entries`,
Branch Record to `branches`, and Employee Record to `employees`. That table
term is the glossary-term input each table's Trust Score actually reads.

1. For each table, link every term to the column shown, using the term's
   Data Elements tab exactly as in Part C.
2. When a table is done, select it in the Data Canvas and run **Actions →
   Process → Start Calculate Trust Score**, so each table records its
   glossary-term input. (Expect the number to stay low until the data is
   profiled in Workshop 4.)

| Table | Business terms to link (term → column) |
| --- | --- |
| members | Member Number → mbr_no and mbr_id; SSN → ssn; Date of Birth → dob; Email → email; Phone → phone; City → city; ZIP → zip; Branch ID → br_id; Member Status → mbr_status |
| accounts | Account ID → acct_id; Account Number → acct_no; Member Number → mbr_id; Branch ID → br_id; Account Type Code → acct_type_cd; Account Status → acct_status; Balance Amount → bal_amt; Available Balance Amount → avail_bal_amt; Interest Rate → int_rt |
| cards | Card ID → card_id; Account ID → acct_id; Card Number → card_no; Card Type Code → card_type_cd; CVV Code → cvv_cd; Card Status → card_status |
| transactions | Transaction ID → txn_id; Account ID → acct_id; Transaction Amount → txn_amt; Transaction Type Code → txn_type_cd; Merchant Category Code → mcc_cd |
| loans | Loan Number → ln_no and ln_id; Member Number → mbr_id; Loan Type Code → ln_type_cd; Principal Balance Amount → prin_bal_amt; Loan Status → ln_status |
| ach_payments | ACH ID → ach_id; Account ID → acct_id; Routing Number → ach_rte_no; External Account Number → ext_acct_no; Dir Code → dir_cd; ACH Status → ach_status; Return Code → return_cd |
| kyc_reviews | KYC ID → kyc_id; Member Number → mbr_id; Risk Rating Code → risk_rating_cd; ID Doc Type Code → id_doc_type_cd; ID Doc Number → id_doc_no; Reviewer Employee ID → reviewer_emp_id; KYC Status → kyc_status |
| suspicious_activity | SAR ID → sar_id; Member Number → mbr_id; Account ID → acct_id; Activity Type Code → activity_type_cd; Filed By Employee ID → filed_by_emp_id; SAR Status → sar_status |
| gl_entries | General Ledger ID → gl_id; General Ledger Account Number → gl_acct_no; Branch ID → br_id |
| branches | Branch ID → br_id; Branch Name → br_name; Branch City → br_city; Branch County → br_county; Branch ZIP → br_zip; Branch Phone → br_phone; Mgr Employee ID → mgr_emp_id; Branch Status → br_status |
| employees | Employee ID → emp_id; Branch ID → br_id; Email → email; Role Code → role_cd |

The document store (`CopperState_Documents`) is governed by this same
glossary. Its terms link to whole folders — for example Suspicious Activity
Report to the `compliance` folder, Loan Record to `loan-applications`, and
ACH Payment Record to `payments` — so one vocabulary spans both the
database and the file store.

### Part E — Assign the stewards

Import carried the descriptive properties; now put the people on the terms.
`assets/CSCU-glossary-user-map.csv` records the expertise-driven map — set
each category's terms' Business Steward and Owner accordingly, and set
Status to Accepted as each steward signs off their own terms:

| Steward | Categories owned |
| --- | --- |
| Elena Ramirez | Member; Accounts & Deposits; Transactions; Branch Operations |
| Marcus Webb | Lending; Finance & Ledger |
| Nadia Flores | Compliance & Risk (all CDE) — and future document-record terms |
| Tom Callahan | Cards & Payments |

Set **Custodian** to Omar Haddad (Data Storage Administrator) on the
identifier terms his storage estate carries, and add Nadia Flores as a
**Stakeholder** on anything BSA/AML adjacent — SAR, KYC and risk terms.

## Introducing the Similarity Score

In Part C you opened the Suggested Columns view and approved the matches
PDC proposed. Those proposals are not name guesses — they come from PDC's
metadata similarity engine, and each one carries a **Similarity Score**.
This short section introduces that score so you know what you are
approving, and it sets the scene for the Technical Track, where that engine
is configured and run.

### What the score measures

Metadata similarity uses machine learning to find and rank similar columns,
tables, and terms across the whole Catalog. It scores each candidate on
metadata structure and meaning rather than column names alone, and
expresses the result as a number from 0 to 1 — PDC's confidence that a term
fits a column. A higher score is a stronger match.

**Meaning over names:** because the score reads structure and meaning, it
can match a column whose name looks nothing like the term. In CSCU, the
**Member Number** term can be proposed for `mbr_id` in `accounts` and
`loans`, and **Routing Number** for `ach_rte_no` — links a name-only search
would miss.

**It runs as a job, not on demand:** the Suggested Columns you see are the
results of a metadata similarity run, not generated the moment you open the
tab. An administrator runs that job; you review what it produced.

### Reading and acting on suggestions

The Suggested Columns list shows matches above a score threshold — 0.5 by
default. Lower the threshold to see more, looser candidates; raise it to
see only the closest. Then act on each one:

- **Approve** assigns the term to the column automatically — the same
  Business Term Association you would create by hand in the Elements view,
  only faster.
- **Reject** dismisses a wrong match. A rejected suggestion is excluded
  from future runs for that asset, so reject deliberately rather than to
  tidy the list.

**Your judgment still decides:** the score assists, it does not approve. A
high score is a recommendation, not a verdict — approve the matches that
genuinely describe the column, and the same over-linking cautions from the
previous section apply. Good semantic coverage, not volume, is the goal.

`[SCREENSHOT: Suggested Columns — members.mbr_no]`

## Verify your work

- [ ] The CSCU Business Glossary exists, with eight categories and your
      terms beneath them.
- [ ] Each term has a Definition, a Domain, a Sensitivity, a
      Classification, and a Business Steward.
- [ ] Each term you linked lists its columns on the Data Elements tab, and
      the `members` columns show their assigned business term.
- [ ] Every data table — all eleven, `members` through `employees` — has
      its terms linked, each carries its own table-level term (Member
      Record, Loan Record, and so on) that its Trust Score reads, and each
      has had its Trust Score recalculated.
- [ ] After re-running Calculate Trust Score, the `members` Trust Score is
      no longer 0 / Untrusted.
- [ ] Stewardship is assigned per Part E — Elena, Marcus, Nadia and Tom
      each own their categories.
- [ ] You can explain why the score moved (the glossary-term input) and why
      a quality-based score still waits for Workshop 4 profiling.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Import fails, or terms land under Unassigned | Your file's columns or Parent values do not match the expected schema. Export a glossary first and mirror its exact headers and parent references. The supplied JSONL imports as-is — if it fails, check you did not edit it. |
| Term created but no governance shows | Sensitivity, Domain, Classification, and Steward are set per term in the Properties panel. Open the term's Summary tab and fill them in. |
| Trust Score still 0 after linking a term | Re-run the Calculate Trust Score job after the term is linked. A completed job with activeMillis 0 means it had no inputs at the moment it ran. |
| Cannot create or edit glossary items | Glossary editing is governed by role-based access control and requires the **Business Steward** role. In the CSCU cast that is Nadia, Marcus, Tom — and Elena, whose account carries both Business Steward and Data Steward. A Data Steward role alone cannot edit the glossary. |

## Why it matters & discussion

A new analyst searches the Catalog for member personal data. Because CSCU
governs each personal field as its own term — Member Number, SSN, Date of
Birth, Email, Phone, all classified, stewarded by Elena Ramirez and linked
to every matching column — the search returns exactly the right fields with
their governance attached. Discuss: what would that same search return with
no glossary, and what would it cost CSCU, in an NCUA examination, to
assemble that answer by hand?

## What's next

Your business vocabulary now exists and is linked to the data. Workshop 4
runs Data Profiling and Data Quality: PDC profiles the data — the
operational layer, row counts, and keys — and Dana Ortiz (Data Developer)
turns CSCU's compliance obligations into scheduled, scored business rules.
With both a linked term and profiled quality in place, Calculate Trust
Score finally produces a real, quality-based number.

Beyond this business track, the Technical Track goes under the hood of the
Suggested Columns you approved here. Its Similarity & ML Inference module
shows how the similarity engine is run and tuned, and how it connects to an
inference backend — the production side of the suggestions you consumed
here as a Steward.

All Copper State Credit Union data is fictional and generated for training.
