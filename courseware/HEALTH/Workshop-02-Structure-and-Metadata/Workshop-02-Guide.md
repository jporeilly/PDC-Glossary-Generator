# Workshop 2 — Explore Structure & Metadata (LHP)

*Lakeshore Health Partners scenario · PDC 11.0.0*

**Primary role:** Business Analyst
**Estimated time:** 60 min

## Why this workshop matters

A catalog is only as useful as the metadata it holds. In Workshop 1 you
connected two data sources; now you learn to read what PDC captured about
them. For a Lakeshore Health Partners analyst, this is the difference
between staring at a table called `patients` and understanding that it
holds PHI, is described by governed business terms, carries a trust score,
and links to encounters and claims. Metadata is the context that turns raw
data into something a business can trust and govern.

> **The business problem.** A new analyst joins LHP and is handed the
> `patients` table. Which column identifies the patient? Which fields are
> among HIPAA's 18 identifiers? Who owns the definition of "active
> patient"? Without metadata, every one of these questions means
> interrupting a colleague. With a well-described catalog, the answers are
> on the asset's own pages. Workshop 2 teaches you to find them.

## What you will learn

- The three layers of metadata — technical, business, and operational — and
  what each tells you.
- How to read a table's columns, data types, sizes, and nullability in the
  Data Canvas — and where key relationships appear once they are
  discovered.
- How to read an asset's business metadata — its Description, Remarks,
  linked Business Terms and Sensitivity — and where governance roles like
  Domain, Classification, and Business Steward actually live.
- How the same three-layer model applies to an unstructured document, not
  just a table.
- How to spot a metadata gap — a missing definition or owner — that needs a
  steward's attention.

## Background: the three layers of metadata

PDC organizes what it knows about every asset into three layers. Learning
to read all three is the core skill of this workshop:

| Layer | Answers the question | Example for `patients` |
| --- | --- | --- |
| Technical | What is it, physically? | Columns, data types, primary/foreign keys, row count |
| Business | What does it mean? | Description / Remarks, linked Business Terms, Sensitivity (Domain, Classification & Business Steward live on the Glossary term) |
| Operational | Can I trust it? | Quality score, last profiled date, lineage to other assets |

Most technical metadata — columns, data types, sizes, and nullability — is
captured automatically when you ingest a schema; row counts and the PK/FK
column are added later by profiling: the PK/FK column reflects the keys
declared in the source, surfaced by cross-table foreign-key detection once
every related table is profiled.

Business metadata is partly automatic and partly added by stewards — it is
where human knowledge enters the catalog. Operational metadata accrues as
the asset is profiled and used. Together they make an asset
self-describing.

## What's populated now — and what appears after Workshop 4

Workshop 1 ran only Metadata Ingest (for the schema) and Scan Files (for
the documents). That fills in the technical layer completely, but the
business and operational layers are produced by processing jobs you run in
Workshops 4 and 5. So in this workshop you learn where each field lives and
read what is there — and several fields will be empty until then. That is
expected, not an error.

| Processing job | What it populates | Available in Workshop 2? |
| --- | --- | --- |
| Metadata Ingest (Workshop 1) | Technical layer — columns, data types, sizes, nullability; file size and format for documents | Yes — fully available now |
| Data Profiling / Data Discovery (Workshop 4) | Operational layer — column statistics, patterns, samples, row counts, last-profiled date; drives the foreign-key detection that fills the PK/FK column | No — empty until Workshop 4 |
| Calculate Trust Score (Workshop 4) | Operational layer — the trust score, from data quality, ratings, lineage, and glossary terms; shown in Key Metrics | Default (0 / Untrusted) shows now; a real score needs profiling |
| Data Identification (Workshop 5) | Business layer — Tags and Business Terms applied from dictionaries and patterns | No — empty until Workshop 5 |
| PII Detection | Column-level PII flags — scope-limited (JDBC tables and CSV/TSV in specific languages) | Not applicable to LHP's English documents |

One exception: business metadata a steward types in — a Description, a
Purpose, a steward name — does not depend on a processing job, so it may
already be filled in. Part B is partly about spotting where those
human-entered fields are still missing.

> **Why the Trust Score reads 0 / Untrusted before profiling.** Every asset
> carries a Trust Score from the moment it is cataloged: it defaults to
> Untrusted (0), exactly as Sensitivity defaults to Unknown and Data
> Lineage to Unverified. The score is a roll-up of four inputs — Data
> Quality, User Ratings, Data Lineage, and whether a Glossary Term is
> assigned — and it is a table- and file-level metric, computed for the
> asset as a whole, never per column. Running Calculate Trust Score
> recomputes the roll-up from whatever exists right now; on a freshly
> ingested table none of the inputs are populated, so it stays 0. Only the
> Data Quality input needs profiling, which is why a meaningful score
> appears after Workshop 4 — though you can nudge it off 0 earlier by
> verifying lineage, adding a rating, or linking a table-level term.

## Before you begin

### Prerequisites

- Workshop 1 complete — both LHP sources connected and visible in the Data
  Canvas.
- Work as `jamal.carter` (Data User — the Business Analyst persona).

### Assets used in this workshop

- The connected `lhp_clinical` database (the `patients` table is the
  focus).
- The HIPAA security risk analysis PDF from `lhp-documents/compliance/`
  (to read document metadata).

## Step-by-step

### Part A — Read a table's technical metadata

1. In the left navigation menu, click **Data Canvas** and open the
   `Lakeshore_Clinical` source.
2. Select the `patients` table. The Summary tab opens with an overview of
   the asset.
   `[SCREENSHOT: patients table — Summary tab]`
3. Open the **Details** tab to see the Contained Items — every column with
   its Data Type, Column Size, and Nullable flag. Notice the PK/FK column
   is still blank: it reflects the keys declared in the source, but PDC
   only surfaces them through foreign-key detection, which runs on
   profiling output across related tables in Workshop 4. For now, predict
   which column is the key (`pt_id`) and which look like foreign keys
   (`primary_prov_id`); you will confirm them once every related table has
   been profiled.
   `[SCREENSHOT: patients Details tab — columns and types]`
4. Find a column whose meaning is not obvious from its name — LHP's schema
   is full of them: `mrn`, `mkt_optout`, `sex_cd`. The technical layer
   tells you `mkt_optout` is a boolean, but not what it is for. That is the
   business layer's job — and the ingested column comment (*"HIPAA:
   marketing use of PHI requires signed authorization… CRITICAL privacy
   field"*) is your first taste of it.

### Part B — Read the business and operational layers

1. On the `patients` Summary tab, read the asset's own business metadata:
   the Description, the Properties (Remarks), and the **Key Metrics**
   panel — Data Quality, Data Lineage, Sensitivity, and Trust Score. A
   table has a Sensitivity level (Unknown until set), not a Classification
   field.
2. Open the **Business Terms** panel (or the Glossary tab). A table
   carries no Domain, Classification, or Business Steward of its own —
   those are built-in properties of the Glossary term you link to it.
   Terms arrive in Workshop 3; after that, open a linked term to see its
   Domain, Classification, Business Steward, and Owner.
   `[SCREENSHOT: patients Summary — Key Metrics and Business Terms panels]`
3. Find where the data quality / trust score and the last-profiled date
   appear in the operational layer. Expect them empty for now — they are
   produced by Data Profiling and Calculate Trust Score in Workshop 4.
   Note where lineage would appear.
4. Identify at least one gap — an empty Description, no linked Business
   Terms, Sensitivity still Unknown, or a Trust Score of Untrusted — and
   note it as work for a steward. On `encounters`, the `note_txt` column
   comment flags a defect the stewards must own (*"DEFECT: two notes in
   this dataset carry a patient SSN in clear text"*): bookmark it for
   Workshops 4 and 5.

### Part C — The same three layers for a document

Metadata is not just for tables. Open a document and see the same model
expressed differently.

1. In the Data Canvas, open the `compliance/` folder and select
   `hipaa_security_risk_analysis_2026.pdf`.
2. On its Summary tab, find the **Document Properties** pane — file size,
   format, and (after document processing) page count and owner. This is
   the document's technical layer.
3. Find the **Business Terms**, **Tags**, and **Custom Properties** panels
   — the business layer, identical to a table's. Business Terms and Tags
   are applied by Data Identification in Workshop 5, so they may be empty
   now; Custom Properties can be set by a steward at any time.
4. Read the first page of the risk analysis: finding 1 names the same
   `encounters.note_txt` issue you found in Part B — structured and
   unstructured evidence of one governance story, side by side in one
   catalog.
   `[SCREENSHOT: risk analysis — Summary tab with Document Properties]`

### Part D — The role boundary, seen from a browser

Sign out and repeat Part A's first step as `beth.nakamura` (**Business
User**): the glossary and policies are visible, but the data sources are
absent — the Business tier's boundary, live. In a covered entity this is
not cosmetic: it is the minimum-necessary rule expressed in software.
`[SCREENSHOT: beth.nakamura view — no data sources]`

## Verify your work

- [ ] You can state the data type, size, and nullability of any column in
  `patients`, and explain that key roles (PK/FK) surface once every
  related table has been profiled in Workshop 4.
- [ ] You can read the table's Sensitivity, Trust Score, Data Quality and
  Data Lineage in Key Metrics, and explain that Domain, Classification,
  and Business Steward live on the linked Glossary term.
- [ ] You can locate where the quality score will appear (it populates in
  Workshop 4) and explain which tab shows lineage.
- [ ] You identified at least one metadata gap to hand to a steward —
  including the `note_txt` comment.
- [ ] You opened the HIPAA risk analysis PDF and found its Summary tab and
  Document Properties.
- [ ] You saw the Business User vs Data User boundary as `beth.nakamura`.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| The patients table is missing | Schema ingest did not complete in Workshop 1, or it ingested `public`. Re-ingest the `lhp_clinical` schema |
| No quality score shown | The table has not been profiled yet. That happens in Workshop 4; the field is empty until then |
| Document has no page count or owner | Those come from document processing, run later. Format and size are available now |
| beth.nakamura sees data sources | The account carries an extra role. Check its roles in Users & Communities — Business User only |

## Why it matters & discussion

A new analyst asks, *"Can I email everyone in the patients table about our
new telehealth service?"* Which single column answers that question, and
which metadata layer does it belong to? Discuss why the answer
(`mkt_optout`, a piece of business metadata with a HIPAA-authorization
purpose) is far more valuable than any technical detail — and what it would
cost LHP, under HIPAA's marketing rules, to get that answer wrong.
Workshop 4 turns exactly this question into a scheduled business rule.

## What's next

You can now read what the catalog knows. Workshop 3 builds the business
glossary — the governed terms, sensitivity, and stewardship you link to
LHP's tables. Workshop 4 then measures how much you can trust the data —
profiling its quality and scoring the compliance rules.

All Lakeshore Health Partners data is fictional and generated for training.
