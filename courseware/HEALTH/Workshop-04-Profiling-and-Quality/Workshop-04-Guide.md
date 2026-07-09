# Workshop 4 — Profile Data & Assess Quality (LHP)

*Lakeshore Health Partners scenario · PDC 11.0.0 · Data Profiling · Trust Score · Business Rules*

**Primary role:** Data Steward / Data Developer
**Estimated time:** 90 min

## Why this workshop matters

In Workshop 2 the `patients` table had a blank PK/FK column and a Trust
Score of 0 / Untrusted; in Workshop 3 you linked glossary terms, but the
score still rested on defaults. This workshop runs the engine that fills
the operational layer. **Data Profiling** reads every value once and
produces statistics, data patterns, and sample values; Data Catalog's
foreign-key detection looks across tables for relationships in that
output; and **Calculate Trust Score** finally has real evidence to roll
up. Then you go one step beyond the profiler: **Business Rules** turn
LHP's HIPAA obligations into scheduled, scored SQL — compliance you can
trend, not assert. After this workshop, the question *can I trust this
table?* has a defensible answer.

> **The business problem.** An LHP analyst is about to build the no-show
> report on `appointments`. Is the data complete? Are there nulls in the
> status columns? Which column is the key, and does it join cleanly to
> `patients`? Without profiling, these are guesses. Profiling turns them
> into measured facts — row counts, null counts, cardinality, and
> discovered keys — so the analyst builds on evidence, not hope. And three
> of LHP's obligations are already broken in the data, invisibly: two
> clinical notes carry a patient SSN in clear text, one marketing
> disclosure went out without a signed authorization, and three opted-out
> patients still carry live marketing emails. Part E makes all three
> failures *measurable* — the prerequisite for fixing them and proving the
> fix.

**Profiling is a prerequisite:** it is not an optional step. Until a table
is profiled, Data Catalog flags it as Required, and Data Identification
(Workshop 5) cannot run on it — so profiling comes first for every asset.

## What you will learn

- How to run Data Profiling on a structured table, and why the default
  settings (a sample of up to 500,000 rows) suit most cases.
- What profiling produces: statistics (row count, null count,
  cardinality), data patterns, and sample values.
- Where the PK/FK column comes from — declared keys in the source plus
  Data Catalog's relationship detection — and what to do when it stays
  blank.
- How Calculate Trust Score rolls up four inputs — and why the Data
  Quality metric needs the Pentaho Data Quality add-on.
- What the Profiling options do — sampling (Sample Type, Skip Recent) and
  the parallelism threads — and why LHP keeps the defaults.
- How LHP's documents are profiled by Data Discovery, which extracts text,
  flags duplicate files, and can OCR scanned PDFs.
- How PDC Business Rules work: the three-column SQL contract the Rules
  Engine scores, and why in PDC v11 a **Data Developer** — not an Admin —
  authors them.

## Background: what profiling produces

Data Profiling examines structured data in a single pass and computes
detailed properties for every column. Along the way it generates
intermediate data — a Roaring Bitset, a HyperLogLog cardinality estimate,
and data-pattern analysis — that downstream jobs consume. Foreign-key
detection depends on it directly, working across tables to infer
relationships from that output. Profiling produces a Data Quality
Pre-Analysis — an estimated quality percentage in the column's profile
results — which is not the same as the licensed Data Quality metric shown
in Key Metrics.

| Profiling produces | What it is | Where you see it |
| --- | --- | --- |
| Statistics | Total row count, null count, min/max, string widths. | Summary → Statistics; column details |
| Cardinality & HLL | Unique-value count and a ~2%-margin estimate. | Column details (Cardinality, HLL) |
| Data patterns | The most frequent value patterns, with RegEx suggestions. | Summary → Data Patterns |
| Sample values | A controlled sample of values per column. | Details → Sample Data (Raw / Aggregated) |
| Intermediate data | Bitset, HLL, and pattern analysis that foreign-key detection consumes. | Not shown directly; enables PK/FK |

`[SCREENSHOT: One profiling pass — statistics, cardinality, patterns, samples]`

> **PHI note.** Profiling reads real values and Extract Samples shows them
> on the asset pages — in a covered entity that means PHI is visible to
> anyone who can open the profiled column. That is by design (stewards
> need to see what they govern), and it is why Workshop 0's role
> discipline matters: profiling results inherit the catalog's access
> control.

### The Trust Score, now with evidence

Trust Score is still the roll-up of four inputs you met in Workshops 2 and
3 — Data Quality, User Ratings, Data Lineage, and whether a Glossary Term
is assigned. Workshop 3 satisfied the glossary-term input. Profiling now
makes the rest meaningful, and once the Pentaho Data Quality add-on and
its Data Quality Loader are in place, the Data Quality component reports
across completeness, accuracy, validity, uniqueness, and consistency.

| Trust Score input | Filled by | In this course |
| --- | --- | --- |
| Data Quality | Pentaho Data Quality add-on + Data Quality Loader, over profiled data. | Workshop 4 (licensed) |
| User Ratings | Analysts rating the asset 1–5 stars. | Any time |
| Data Lineage | Reviewing and verifying the asset's lineage. | Set Verified manually in Part C |
| Glossary Term | Linking a business term to the asset. | Workshop 3 (done) |

`[SCREENSHOT: Key Metrics — four inputs rolled up on a table]`

## Before you begin

### Prerequisites

- Workshops 1–3 complete — sources connected, metadata read, and the
  glossary linked.
- Two logins from the LHP cast: `maya.lindqvist` (Data Steward) runs the
  profiling and Trust Score parts, and `ingrid.dahl` (**Data Developer**)
  authors the business rules in Part E — in PDC v11 that role owns
  Business Rules, and notably the Admin role can view but not create
  them.

### Assets used in this workshop

- The `patients`, `encounters`, and `claims` tables in `lhp_clinical` —
  the worked examples (you then profile all eleven tables).
- The compliance PDFs in the `lhp-documents` store — the HIPAA security
  risk analysis, the disclosure audit, the coding audit, and the Notice of
  Privacy Practices — profiled in Part D via Data Discovery.
- `assets/Lakeshore-Health-Partners-Business-Rules.sql` — six ready
  conditions in PDC's three-column shape for Part E.
- The Workshop 3 glossary terms already linked to `patients` (so the
  glossary-term Trust Score input is satisfied).

## Step-by-step

### Part A — Run Data Profiling

LHP has two kinds of assets, and each is scanned its own way. Database
tables — like `patients` — are profiled with **Data Profiling**, the
structured-data scan you run in this Part. The compliance PDFs in the
`lhp-documents` store are scanned with **Data Discovery**, its
unstructured counterpart, in Part D.

1. In the Data Canvas, open `Lakeshore_Clinical` and select the `patients`
   table.
2. Open **Actions**, then **Process**, then click **Start** on the Data
   Profiling card — the scan for a structured table. (The other cards on
   this page belong to other steps; the table below maps each one.)
   `[SCREENSHOT: patients — Data Profiling card]`
3. Keep the default settings. Profiling samples up to 500,000 rows, which
   suits LHP's tables, and Extract Samples is on by default so you get
   preview values.
   `[SCREENSHOT: Data Profiling — default settings]`
4. Watch the job on the Workers page until it completes, then repeat for
   the other ten tables — `clinics`, `staff`, `providers`, `payers`,
   `appointments`, `encounters`, `lab_results`, `prescriptions`, `claims`,
   and `disclosure_log`. (You can select several tables at once and start
   one profiling job for the set.)

**Which card, which asset:** the Choose Process page lists every
processing step as a card, but each belongs to a particular job. A
structured table is scanned with Data Profiling; an unstructured document
is scanned with Data Discovery — so a table has no Data Discovery card to
run, and a document has no Data Profiling card.

| Process card | When you use it |
| --- | --- |
| Metadata Ingest | Workshops 1–2 — capture structure & metadata |
| Data Profiling | This Part (A) — scan a structured table |
| Data Discovery | Part D — scan unstructured documents |
| Data Identification | Workshop 5 — tag PHI & sensitivity |
| Calculate Trust Score | Part C — roll up the Trust Score inputs |

### The Profiling options

The Profiling page exposes sampling and performance controls. LHP's tables
are small, so you leave these at their defaults and profiling reads each
table in full — but here is what each control does.

| Option | What it does |
| --- | --- |
| Extract samples | Captures sample values during profiling and shows them on the Summary tab. On by default. |
| Skip Recent (days) | Skips any table already profiled within this many days; 0 means profile every time. |
| Sample Type | How much data to read: Sample Clause (a percentage, or a row count on Microsoft SQL / Snowflake only), First N Rows, Every Nth Row, or Filter (a custom SQL WHERE clause, e.g. `st = 'MN'`). Clear resets these. |
| Split Job by Columns | Splits a wide table into parallel jobs by column, for performance. |
| Columns Per Job | How many columns each job handles when splitting by columns (25 by default). |
| Number of Tables Per Job | How many tables go into a single profiling job (10 by default). |
| Persist Threads | Threads used to write profiling results. |
| Persist File Threads | Threads used to persist profiling data to files for large datasets. |
| Profile Threads | Threads allocated to the profiling work itself, enabling parallel execution. |

For LHP: leave every option at its default. The tables are far smaller
than the 500,000-row sample cap, so profiling reads them in full, and the
parallelism controls only matter for very large tables.

**On sampling:** when you choose a percentage, profiling uses Reservoir
Sampling — for example 30% draws a representative 30% of the rows in a
single pass. (Sample Clause by row count is supported only on Microsoft
SQL and Snowflake.)

`[SCREENSHOT: Profiling Options page]`

### Part B — Read the profile

1. On the `patients` Summary tab, the Statistics pane now shows a Row
   Count alongside the Column count, and the Last Successful Scanned date
   is set.
   `[SCREENSHOT: patients Summary — Statistics pane with Row Count]`
2. Click a column (for example, `ssn`) to see column-level statistics —
   Null Count, Cardinality, HLL, Uniqueness, and Density — and a Data
   Patterns pane with RegEx suggestions. `ssn` comes back as a crisp
   NNN-NN-NNNN and `mrn` as `AAA-nnnnnn` — patterns Workshop 5's
   identification engine will put to work.
   `[SCREENSHOT: ssn column — statistics and Data Patterns]`
3. Open the **Details** tab and the Sample Data pane (Raw and Aggregated)
   to preview real values and how often each occurs. On `appointments`,
   check `appt_type_cd`'s five distinct values — that enum becomes a
   dictionary in Workshop 5. On `encounters`, note that `note_txt` is
   long free text: the profiler records lengths and samples, but a
   sixty-word note has no single "shape" — remember that for Workshop 5.
   `[SCREENSHOT: Details — Sample Data, Raw and Aggregated]`
4. Still on Details, look at the **PK/FK** column. It is populated by Data
   Catalog's cross-table foreign-key detection, which runs on profiling
   output, so it fills in only once every related table has been profiled,
   not just this one. The box below explains what to do if it is blank.
   `[SCREENSHOT: Details — PK/FK detection]`

**Why the PK/FK column can be blank:** the PK/FK column is populated by
Data Catalog's foreign-key detection, which runs on profiling output and
works across tables. LHP's schema already declares every key —
`patients.pt_id` is a primary key, and `appointments`, `encounters`,
`lab_results`, `prescriptions`, `claims` and `disclosure_log` declare
foreign keys to it — so the database is not the problem. The column stays
blank when detection has not had both sides of a relationship to compare,
that is, when only some of the related tables have been profiled. To fill
it, run Metadata Ingest on the schema, then Data Profiling on every
related table, not just `patients`:

```
-- The schema already declares all keys — nothing to add.
-- In PDC, process the WHOLE schema so detection has
-- both sides of every relationship to compare:
--   Actions > Process > Metadata Ingest   (all tables)
--   Actions > Process > Data Profiling    (all tables)
-- clinics, staff, providers, patients, payers,
-- appointments, encounters, lab_results, prescriptions,
-- claims, disclosure_log.
-- Watch every job finish on the Workers page, then
-- reopen the Details tab on patients.
```

### What the column statistics mean

When you open a profiled column, Data Catalog shows a set of statistics.
These are the ones you will read most often.

| Statistic | What it means |
| --- | --- |
| Rows | Total number of records in the column's table. |
| Nulls | Values explicitly marked as no data (database NULL). |
| Blanks | Empty cells with no characters at all — distinct from NULLs. |
| Cardinality | Count of distinct values; low cardinality means few unique values, which is a strong hint for keys and categories. |
| Min / Max Length | Shortest and longest values in the column, by character count. |
| Avg Length | Average number of characters across the values. |
| Stdev Length | How much the value lengths vary around the average — a wide spread can signal inconsistent or dirty data. |
| Bytes | Total storage size of the column's data. |

**At the schema level too:** profiling records a row count and the
last-profiled date for each schema and table; the schema-level Sensitivity
and a Confidence Score come later, from Data Identification in Workshop 5.

### Part C — Compute the Trust Score

The Trust Score is a roll-up, not a fresh measurement. It combines four
inputs — a linked glossary term, Data Lineage marked Verified, a User
Rating, and the Data Quality metric — so you set those first, then run the
calculation. Sensitivity sits in the same Key Metrics panel, but it is a
separate metric, not a Trust Score input.

1. Confirm the glossary term you linked in Workshop 3 is still attached to
   `patients` — the table-level **Patient Record** term. A linked term is
   the first of the four Trust Score inputs.
   `[SCREENSHOT: patients table — Glossary tab]`
2. Set **Data Lineage to Verified**. In the Key Metrics panel on the
   Summary tab, change Data Lineage from Unverified to Verified for the
   table — the second input.
3. Apply a **User Rating**. Give the asset a 1-to-5-star rating in the Key
   Metrics panel — the third input.
4. Handle **Data Quality**, the fourth input. With the Pentaho Data
   Quality add-on and its Data Quality Loader configured, this metric
   scores completeness, accuracy, validity, uniqueness, and consistency;
   without the add-on it stays Not Computed and the Trust Score rolls up
   the other three.
5. Optionally set the **Sensitivity** to Low, Medium, or High in the same
   panel — for `patients`, High is the honest answer. It is good
   governance and drives the catalog's risk view, but it is not one of
   the Trust Score inputs.
6. Now run the calculation. Open **Actions**, then **Process**, and click
   **Start** on the Calculate Trust Score card. Watch the job on the
   Workers page.
7. When the job completes, read the Key Metrics panel. With a glossary
   term, Verified lineage, and a rating in place, the Trust Score moves
   off 0 / Untrusted to Trusted or Highly Trusted, depending on the
   inputs.
   `[SCREENSHOT: patients — Trust Score in Key Metrics]`

**The Trust Score is a sliding scale:** it does not need all four inputs
to compute. Calculate Trust Score rolls up whatever is present and
positive right now — each input that is in place raises the number, each
one missing holds it down — and the result slides along a band from
Untrusted through Trusted to Highly Trusted. A table with only Verified
lineage and a 4-star rating still scores (around the low-40s, Untrusted);
add the glossary term and it rises; compute Data Quality and it rises
further. Data Quality is the heaviest input, so until it is computed the
ceiling stays low. Pentaho does not publish the exact weight of each
input, so treat the inputs as levers that move the score, not as a fixed
formula.

**Trust Score on documents.** Files are the unstructured twin of tables
and are scored the same way:

1. Confirm a glossary term is attached to the file — for example the
   Disclosure Log Entry term on
   `compliance/privacy_disclosure_audit_2026H1.pdf`. A linked term is the
   first of the four inputs.
2. In the file's Key Metrics panel: apply a rating, set Data Lineage to
   Verified, and set Sensitivity (High is reasonable for a disclosure
   audit; the Business Term is the check that matters).
3. Run the calculation: **Actions → Process → Start Calculate Trust
   Score**, and watch the Workers page.
   `[SCREENSHOT: Key Metrics — privacy_disclosure_audit_2026H1.pdf]`

### Part D — Profile the documents (Data Discovery)

The `lhp-documents` store holds LHP's compliance PDFs, correspondence,
intake forms and statements, not table rows — so they are scanned by
**Data Discovery**, the unstructured-data counterpart to Data Profiling.
The steps mirror Part A:

1. In the Data Canvas, open the `Lakeshore_Documents` store and select the
   `compliance` folder that holds the regulatory PDFs.
2. Open **Actions**, then **Process**. For documents the Choose Process
   page offers Metadata Ingest, Data Discovery, and Data Identification.
   Click **Start** on the Data Discovery card — there is no Data Profiling
   card for documents.
   `[SCREENSHOT: compliance folder — Data Discovery card]`
3. The Configure Process page opens with three tabs — Data Discovery,
   Document Processing, and Data Profiling. Keep the defaults, which suit
   LHP, and click **Start Discovering**.
4. Watch the job on the Workers page until it completes, then repeat for
   the other folders — `correspondence`, `intake-forms`, `interfaces`,
   `fee-schedules` and `statements`.

Where Data Profiling computes column statistics, Data Discovery scans file
contents. For LHP's PDFs it:

- Extracts document properties and text from each PDF (and Office files),
  so the content becomes searchable in the catalog.
- Computes a checksum of the contents to flag duplicate documents, when
  *Compute checksum of document contents* is selected.
- Scans the text with dictionaries for keywords and patterns, which can
  trigger tags and glossary-term assignments.
- Runs OCR (Tesseract or EasyOCR) on scanned or image-only PDFs so their
  text can be read.

Data Catalog can also AI-assist on the documents — summarising each PDF,
detecting addresses, and classifying it against business terms (for
example, *Disclosure Log Entry* or *Patient Record*) on the Document
Processing tab.

**Why it matters for later workshops:** Data Identification needs either
Data Profiling (for tables) or Data Discovery (for documents) to have run
first. Discovering the `lhp-documents` PDFs here is what lets Workshop 5
flag PHI and identifiers inside them.

### Part E — Business Rules: score the obligations

Profiling measured the data as it is; business rules judge it against what
it *must* be. Switch to `ingrid.dahl` — in PDC v11 the **Data Developer**
role owns Business Rules (the Admin role can view but not create them;
this is v11's role-gating in practice).

A PDC Business Rule is a hierarchical layer above one or more SQL data
quality conditions. Each condition returns **three aggregate columns**,
which the Rules Engine uses to evaluate compliance and set a PASS /
WARNING / FAIL status:

```
total_count   - the total number of rows examined
scopeCount    - the number of rows actually IN SCOPE for the rule
nonCompliant  - the number of in-scope rows that FAIL the rule
```

`assets/Lakeshore-Health-Partners-Business-Rules.sql` carries six ready
conditions in exactly that shape, each tied to an LHP obligation:

| Rule | Dimension | What it protects |
| --- | --- | --- |
| LHP-Marketing-OptOut-Compliance | Conformity | **Flagship:** opted-out patients must not be contactable on marketing extracts (HIPAA marketing authorization) |
| LHP-No-SSN-In-Clinical-Notes | Validity | Identifiers must never sit in free-text notes; fails by design until the redaction runs |
| LHP-Disclosure-Authorization | Conformity | MARKETING/RESEARCH disclosures require a signed authorization on file |
| LHP-MRN-Format-Validity | Conformity | Every MRN matches LHP-nnnnnn |
| LHP-NPI-Format-Validity | Conformity | Every provider carries a 10-digit NPI |
| LHP-Paid-Not-Above-Billed | Consistency | A payer can never pay or allow more than was billed |

Configure each rule the same way:

1. Open **Data Operations → Business Rules card → Business Rules**.
2. Click **Add Business Rule** and enter the rule's name from the table.
3. Click **Create Business Rule**, then **Configure**.
4. Set the Business Rule Type and the Data Quality **Dimension** shown in
   the table (the seven dimensions are Accuracy, Uniqueness, Consistency,
   Timeliness, Conformity, Completeness, and Validity).
5. Set the **Schedule** (Daily / Weekly / Monthly) — a rule that runs on a
   schedule is compliance you can trend.
6. Set the rule scope (the target table) and paste the rule's SQL from the
   assets file into the condition box, then run it.
   `[SCREENSHOT: Business Rule configuration — flagship rule SQL]`

**Read the results.** The flagship rule reports **3 in scope** (the
opted-out patients) and **3 non-compliant** (all still carry live emails)
— exactly the gap a marketing extract must suppress.
`LHP-No-SSN-In-Clinical-Notes` reports **2 non-compliant of 14**: the
planted PHI leak from Workshop 2, now measured — and the same finding the
HIPAA risk analysis reports as HIGH. `LHP-Disclosure-Authorization`
reports **1 non-compliant of 2 in scope**: the marketing disclosure the
privacy audit flagged (entry 30005). The other three rules pass — which is
just as informative, because they will keep passing (or start failing) on
their schedule, without anyone remembering to check.
`[SCREENSHOT: Business Rules dashboard — pass/fail statuses]`

## Verify your work

- [ ] All eleven `lhp_clinical` tables show a Row Count and a profiled
      date.
- [ ] Column-level statistics (Null Count, Cardinality, Uniqueness) and
      Sample Data are visible on `patients` and `appointments`.
- [ ] Once every related table in the schema is profiled, the PK/FK
      column shows `pt_id` as the primary key on `patients`; the LHP
      schema already declares the keys, so the remaining step is profiling
      the full related set.
- [ ] After Calculate Trust Score, the `patients` Trust Score is no longer
      0 / Untrusted.
- [ ] The `lhp-documents` folders are discovered and their text is
      searchable.
- [ ] Six business rules are configured and evaluated; the flagship,
      SSN-in-notes and disclosure rules show the expected failures — and
      you can say why.
- [ ] You can name the four Trust Score inputs and say which one requires
      the Pentaho Data Quality add-on.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| PK/FK still blank after profiling | Foreign-key detection is cross-table, so it needs every related table profiled, not just this one. Confirm the keys are declared in the source (the LHP schema declares them all), then run Metadata Ingest and Data Profiling across the whole `lhp_clinical` schema and check the Workers page. If it is still blank after every related table is profiled, the schema is provably correct, so treat it as a Data Catalog scan or version question for Pentaho support. |
| Data Quality shows Not Computed | The Data Quality metric requires the Pentaho Data Quality add-on and the Data Quality Loader. Profiling alone does not populate it; the rest of the Trust Score still computes. |
| Row count or samples missing | The table was not profiled, or Extract Samples was disabled. Re-run Data Profiling with the default settings. |
| Profiling skips a table | Skip Recent (days) may be set, so a table profiled within that window is skipped. Clear the value or wait. |
| Cannot create a business rule | In PDC v11, Business Rules are authored by the **Data Developer** role — `ingrid.dahl` in the LHP cast. The Admin role can view but not create them; a Data Steward cannot author them either. |
| Rule saves but never evaluates | The SQL must return exactly the three-column contract — `total_count`, `scopeCount`, `nonCompliant` (the quoted casing matters). Paste the conditions from the assets file unchanged. |

## Why it matters & discussion

Profiling is what turns a catalog entry into trustworthy evidence. Before
Workshop 4, the `patients` Trust Score was a placeholder; now it rests on
measured statistics, discovered keys, and a linked glossary term — and the
business rules put numbers on obligations that used to live in a policy
binder. Discuss: which of LHP's tables would you profile first, and what
does it change that the SSN-in-notes leak is now a scheduled, failing rule
instead of a secret in a free-text field?

## What's next

With the data profiled and keys discovered, the catalog now knows the
shape and quality of LHP's data. Workshop 5 puts that to work for
compliance: Data Identification scans the profiled tables with
dictionaries and patterns to flag PHI automatically, and you set the
Sensitivity that protects LHP's patients — including understanding why the
SSNs hiding in the notes needed a *rule* to find, when the engine tagged
the `ssn` column effortlessly.

All Lakeshore Health Partners data is fictional and generated for training.
