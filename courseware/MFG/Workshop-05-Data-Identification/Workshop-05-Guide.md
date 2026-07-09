# Workshop 5 — Data Identification (CPC)

*Cascade Precision Components scenario · PDC 11.0.0 · Dictionaries & Patterns · Builds on Workshop 4 — the tables must be profiled first*

**Primary role:** Business Analyst
**Estimated time:** 60 min

## Why this workshop matters

As a Business Analyst you rely on the catalog knowing *what its data is* —
that classification is what lets you search by business meaning, trust
sensitivity labels, and reason about where information lives. **Data
Identification** is the engine that produces it — and CPC teaches the
course's sharpest lesson about it. The built-in method library is
privacy-centric: names, emails, SSNs, card numbers. CPC's estate holds
almost none of that. Run the built-ins and nearly nothing lights up — yet
this data is full of identifiers that matter enormously: part numbers on
safety-critical valves, lot numbers that answer recalls, NCR references
that carry dispositions. Identification is not a privacy feature; it is a
*meaning* feature, and industrial meaning needs custom methods.

> **The big picture.** Profiling tells you the *shape* of a column — its
> statistics, samples, and patterns. Data Identification tells you what
> the column *means*. It compares your data against two kinds of methods
> — dictionaries and patterns — and tags whatever matches, turning "we
> think this column is a lot number" into "the catalog knows it is."

> **Identify once.** Run Data Identification as a one-time baseline.
> After the stewards override tags and sensitivity, re-running
> identification clobbers their work.

## What you will learn

- What Data Identification is, and where it sits in the PDC pipeline.
- The two identification methods — Data Dictionaries (match by value) and
  Data Patterns (match by shape) — and when each applies.
- How a match becomes a tag — confidence, condition, and action — at a
  level a BA needs.
- How dictionaries and patterns combine into policies, and what a run
  produces in the catalog.
- That identification reaches unstructured documents too — the same
  methods, applied to file content through Data Discovery.
- Why the built-in library finds almost nothing at CPC — and how a custom
  method library turns that silence into full coverage.

## Where Data Identification sits

Identification is the second step of the catalog pipeline. Each stage
feeds the next: you cannot identify data you have not profiled, and you
cannot govern data you have not identified.

| Stage | What happens | Why it matters |
| --- | --- | --- |
| Profile | Generates statistics, samples, and data patterns for each column. | Produces the raw material identification matches against. |
| Identify | Matches columns against dictionaries and patterns; applies tags and terms. | Turns raw columns into classified, meaningful assets. |
| Tag & classify | Matched columns carry tags and linked business terms. | Makes meaning, ownership, and sensitivity explicit. |
| Discover & govern | Search, sensitivity, lineage, and the Galaxy View draw on the tags. | Everything downstream depends on identification being right. |

**Profiling comes first:** Data Identification runs on profiled data — it
needs the patterns and samples that profiling produced in Workshop 4.
Profile a table before you identify it, or the job has nothing to match
against.

`[SCREENSHOT: The pipeline — profile, identify, tag, govern]`

## The two methods

Every identification comes down to one question: "what is this column?"
PDC answers it two ways. A **dictionary** matches by value; a **pattern**
matches by shape. Most real-world identification uses both together.

### Method 1 — Data Dictionary (match by value)

A dictionary is a curated list of terms or values. During identification
PDC compares a column's actual contents to that list; a match means the
value appears in the list. Dictionaries are the right tool for data that
has no fixed shape — where the meaning lives in the values themselves.

- **System-defined:** 95 dictionaries ship built-in — ISO country codes,
  currency, marital status, US states, and more.
- **User-defined:** your own lists — upload a single-column CSV, build
  one in the UI, or extract terms from a profiled column.

**Best for:** part types, defect codes, dispositions, plant cities, ASL
statuses, and custom shop-floor terminology.

> **Example — Marital_Status.** The column holds values such as Single ·
> Married · Divorced. Identification compares those values to the
> built-in Marital_Status dictionary. On a match, it applies the tags PII
> and Sensitive: Marital Status. These low-cardinality values have no
> regex shape, so a dictionary — not a pattern — is the correct method.
> Notice the example is a *privacy* one — the built-in library's centre
> of gravity. CPC's own vocabularies — `part_type_cd`, `defect_cd`,
> `disposition_cd` — are exactly the same kind of data, but no built-in
> dictionary knows them; Part B fixes that.

Every dictionary and pattern carries an **identification rule** — the
logic PDC evaluates during Data Identification to decide whether a column
matches. (Note: this is the method's own rule, not a PDC "Business
Rule," which is the separate data-quality feature you met in Workshop 4.)
Take the built-in Marital_Status dictionary: its rule needs a minimum
sample of ~200 values, then computes a confidence score as a weighted
blend of **similarity** (how closely the column's actual values match the
dictionary's accepted list, weighted 0.9) and **metadata score** (hints
from the column name, weighted 0.1) — so content matters far more than
the column's name. The rule only fires when two conditions are both met:
confidence ≥ 0.7 **and** column cardinality ≥ 3 (a guard that stops
columns with one or two distinct values being mislabelled). On a match,
its action applies the tags. Those categories are also what drive the
column's Sensitivity rating (UNKNOWN → LOW/MEDIUM/HIGH), and the
dictionary's linked term lets the same match seed a business-term
association.

`[SCREENSHOT: Data Identification Rule — a built-in dictionary]`

### Method 2 — Data Patterns (match by shape)

Pattern analysis reduces each value to a simple shape string — one symbol
per character position — then matches that shape, and an optional regular
expression, against a known format. Patterns suit data with a
recognizable structure, regardless of the specific values.

The pattern alphabet:

| Symbol | Meaning |
| --- | --- |
| A | Upper-case letter |
| a | Lower-case letter |
| n | Digit 0–9 |
| s | Symbol |
| w | Whitespace |

> **Worked example — the part number.** The value `CPC-84120` reduces to
> the pattern `AAA-nnnnn` — three letters, a kept dash, five digits. From
> the top ~20 patterns it finds, PDC also recommends a tunable RegEx
> (here `^CPC-\d{5}$`), which is reused later for data-quality checks
> that flag outliers. The lot number does the same trick at
> `AAA-nnnn-nnnn` (`LOT-2026-0142`).

**Best for:** part numbers, lot numbers, work/purchase order numbers, NCR
references, and — where they exist — the usual email and phone shapes.

`[SCREENSHOT: Data Patterns — part_no]`

The **eMail** method is a Data Pattern — worth dissecting even though CPC
barely needs it. Its rule computes a confidence score as a weighted blend
of two signals: **regexScore** (how well the column's values match the
email regex, weighted 0.6) and **metadataScore** (how well the column
name matches, weighted 0.4). The name hints live in
`metadataHints.aliases`: a column called `email` scores 0.9, one matching
E-MAIL scores 1.0 — so a well-named column gets a strong metadata signal
even before the values are examined. The `regexMatch` block holds the
actual email regex applied to the content.

What makes this pattern "loose" in a useful way is its condition, which
uses **or**, not and: it fires when either the overall confidence is
≥ 0.5 or the regex score alone is ≥ 0.75. So it catches two cases — a
column that's *named* like email and *looks* like email (combined
confidence clears 0.5), or a column whose values are so clearly email
addresses that the content alone is decisive (regex ≥ 0.75), even if the
column name gives no hint. Like the dictionary, it needs minSamples: 200
before it evaluates. Every custom method you build in Part B uses this
same anatomy — weights, condition, action — pointed at industrial shapes
instead of personal ones.

`[SCREENSHOT: Data Identification Rule — eMail]`

## From match to tag: scored, not guessed

Both methods work the same way underneath. Matching is graded, not a
yes/no guess — which is why identification is reliable. You don't author
these steps as a BA, but knowing their shape explains the results you
see.

| Step | What happens |
| --- | --- |
| 1 · Compare | Profiled values are checked against the dictionary or pattern, plus a hint from the column name. |
| 2 · Score | A confidence score blends content similarity with the metadata (column-name) hint. |
| 3 · Condition | If the score clears the threshold — for example ≥ 0.7 — the match is accepted. |
| 4 · Action | Apply the tags and link the business terms to the column. |

The takeaway: every tag is earned by a graded match clearing a threshold.

## Policies: dictionaries + patterns together

A policy is not a pre-built object you pick off a shelf. In PDC a policy
is simply the combination of dictionaries plus patterns you select for a
run — the methods you choose at the Select Methods step. That selection
*is* your policy.

You assemble it from the built-in dictionaries and patterns plus any of
your own — for CPC, the Part Types dictionary and the Part Number pattern
you'll meet below. Apply, run, then review the results in the Data Canvas
and visualize them in the Galaxy View.

## Walkthrough — identify the estate (and watch the built-ins go quiet)

Run Data Identification on CPC's profiled tables (`cpc_mfg`), first with
the built-in methods only — deliberately, to see what a privacy-centric
library makes of an industrial estate. Work as `nora.whitaker` — in PDC
v11, Data Identification Methods belong to the **Data Steward** and
**Data Storage Administrator** roles (Andre's Data Developer role, which
authored the business rules, cannot author identification methods — the
gates point in opposite directions).

### Part A — Run Data Identification (built-ins only)

1. In the Data Canvas, select the profiled `parts`, `lots` and
   `employees` tables, then open **Actions → Process**.
2. On the Choose Process page, click the **Data Identification** card. If
   it shows as Required, profiling has not completed — run Data Profiling
   first.
3. Click **Select Methods** and choose only built-ins: the person-name
   dictionary, eMail, Phone Number, US States.
   `[SCREENSHOT: Data Identification — Select Methods (built-ins only)]`
4. Click **Start**, and watch the job on the Workers page until it
   completes.

### Part B — Review what was identified: the silence is the lesson

1. Open `employees`. Its `email`, `first_nm` and `last_nm` columns carry
   tags — the one corner of CPC that looks like every other company.
   `[SCREENSHOT: identification results on employees]`
2. Now open `parts` and `lots`. **Almost nothing.** `part_no`, `lot_no`,
   `coc_flag`, `unit_cost` — the columns CPC cares most about — are
   untagged, because no built-in method has ever heard of them. This is
   not a failure of the engine; it is the boundary of its shipped
   knowledge. An estate whose sensitivity is commercial and
   safety-critical, not personal, starts from zero — and that is exactly
   why organisations build custom method libraries.
3. **The governance risk of the silence:** untagged columns read as
   "nothing sensitive here." But `unit_cost` is commercially sensitive
   and `lot_no` is audit-critical — the catalog just doesn't know it yet.
   Until Part C's custom methods run, sensitivity at CPC lives only in
   the Workshop 3 glossary terms — which is why you linked them first.

**Dictionary vs pattern, in practice:** part types, defect codes and
dispositions are dictionary material (their meaning is in the values);
part, lot, WO, PO and NCR numbers are pattern material (their meaning is
in the shape). The method assignments in this guide are illustrative —
confirm them against your lab's identification run.

### Part C — Visualize in the Galaxy View

1. With `parts` selected, open **Actions → View Galaxy**.
2. Click **Filters** and turn on *Show only Tagged Items* — before the
   custom methods, the industrial tables go dark; after Part D of this
   walkthrough, rerun the filter and watch them light up.
   `[SCREENSHOT: Galaxy View — before/after custom methods]`

> **One tag vocabulary, everywhere.** A custom dictionary or pattern must
> apply the exact same tag label as the glossary and everywhere else —
> but PDC won't enforce it, because Assign Tags is free text. So it's a
> discipline: one controlled tag list, reused verbatim across
> dictionaries, patterns, the glossary, and the Glossary Generator's
> governed tag set. And when a method should carry glossary meaning, use
> its Assign Business Term action rather than typing a look-alike tag.

## Beyond tables: identifying unstructured documents

Identification does not stop at tables. PDC also profiles documents —
PDFs, Word files, plain-text, and RTF — and points the very same
dictionaries and patterns at their content. At CPC this is where the
custom methods earn their keep twice: the same lot and part numbers that
live in columns also live inside certificates, audit findings and recall
letters.

> **Two worlds, the same methods.** A structured column is profiled, then
> Data Identification applies the scored rule logic — confidence,
> condition, action. An unstructured document is profiled by Data
> Discovery, and within it **String Detection** scans the text for the
> same dictionary and pattern values — flagging their presence, and
> optionally their count. (String Detection matches values directly; it
> does not apply the dictionaries' scored rules.)

### The document processing options

When you run Data Discovery on files, the Document Processing tab offers
String Detection plus a set of machine-learning helpers that only apply
to documents:

| Option | What it does |
| --- | --- |
| String Detection | Scans document text for the values in selected dictionaries and patterns, and tags the file on a match — presence only, or presence and count. |
| Address Detection | Machine-learning scan for U.S. postal addresses; tags a business term you choose when an address is found. |
| Data Classification | Classifies a document by its semantic content; assigns the matching business terms you supply (for example, a document type). |
| Summaries & sentiment | Generates a concise document summary and a sentiment label, shown on the asset's Summary tab. |
| Document Metadata | Extracts properties such as owner, page count, and paragraph count (Office and PDF files). |

**Supported file types:** PDF, DOC, DOCX, TXT, and RTF, among others.
Structured and semi-structured files (CSV, JSON, Parquet) are profiled
the same way, with structured outputs.

### Walkthrough — traceability references in the CPC correspondence

The `cpc-documents/correspondence` folder holds the emails and letters
around the recall and the supplier suspension. The goal mirrors the
table work: flag every document that carries traceability references.

1. In the Data Canvas, select the `correspondence` folder, then click
   Process. Run **Metadata Ingest** first.
2. Click the **Data Discovery** card. On the Document Processing tab, add
   the CPC patterns and dictionaries (Part Number, Lot Number, Plant
   Cities — built in Part D below) under String Detection.
3. Optionally enable **Data Classification** (to label each letter by
   type). Click **Start Discovering**.
4. Open each document on the Data Canvas. Files that carry part, lot or
   order references now show the matching Tags and Business Terms,
   visible in the Document Properties and Business Terms panes.
   `[SCREENSHOT: discovery results on the recall letter]`

| Document | Type | References it surfaces |
| --- | --- | --- |
| email_expedite_PO-30000112 | Email | PO number · part number · supplier — the ASL-violation smoking gun |
| email_customer_quote_request | Email | part number · customer · pricing ask |
| letter_recall_notification_LOT-2026-0107 | Letter | lot number · part number · shipment number · customer |
| letter_supplier_suspension_pacific_alloys | Letter | supplier · NCR number · audit findings |

> **A pattern reaches into the letters too.** The reference codes in the
> correspondence — `CPC-61180`, `LOT-2026-0107`, `PO-30000112` — follow
> fixed shapes. A custom data pattern for each shape flags CPC references
> wherever they appear in a document, not just in a column — which is how
> a recall query extends from the shipments table into the letter that
> answered it. The method assignments above are illustrative — confirm
> them against the real correspondence in your lab.

## Choosing methods for CPC

At CPC the balance inverts: a handful of built-ins cover the staff table,
and everything else is custom.

### Built-in methods worth selecting (structured)

| CPC data | Built-in method | Type |
| --- | --- | --- |
| employees first_nm / last_nm | person-name dictionary | Dictionary |
| employees / suppliers email | eMail | Pattern |
| phone columns | Phone Number | Pattern |
| city / st columns | US States dictionary | Dictionary |
| part_no, lot_no, wo_no, po_no, ncr_no, ship_no | nothing built-in — the CPC pattern library (custom — below) | — |
| part_type_cd, defect_cd, disposition_cd, asl_status | nothing built-in — the CPC dictionaries (custom — below) | — |

### Custom method 1 — the CPC dictionaries

Four single-column CSVs ship with this workshop (header `term`, one value
per row):

| Dictionary | File | Values |
| --- | --- | --- |
| CPC Plant Cities | `CPC-Plant-Cities-Dictionary.csv` | 16 Pacific Northwest cities, Portland to Corvallis |
| CPC Part Types | `CPC-Part-Types-Dictionary.csv` | VALVE, FITTING, MANIFOLD, SEAL_KIT, ACTUATOR, RAW |
| CPC Defect Codes | `CPC-Defect-Codes-Dictionary.csv` | DIM_OOT, SURFACE, MATERIAL, PLATING, DOC |
| CPC Dispositions | `CPC-Dispositions-Dictionary.csv` | USE_AS_IS, REWORK, SCRAP, RTV |

**Uploading a dictionary:**

1. In the left navigation, go to **Data Operations → Dictionaries**, then
   click **Add Dictionary**.
2. Enter a Name (`CPC Part Types`), a short description, and a Category
   (add a new `CPC_Reference` category). Make sure the dictionary is
   enabled.
3. Choose **Upload Dictionary**, upload the CSV, and set a Confidence
   Score of 0.7.
   `[SCREENSHOT: dictionary upload — CPC Part Types]`
4. (Optional) add a Column Name Regex hint such as `(?i)part_?type|type_cd`
   so the column is matched on its name as well as its values.
5. Click **Create Dictionary**. It now appears in the methods list —
   select it in a Data Identification run on a table, or under String
   Detection when discovering documents. Repeat for the other three, then
   re-run identification on `parts`, `ncrs` and `suppliers` and watch the
   vocabulary columns light up precisely — the silence from Part B,
   answered.

**Rules vs upload:** uploading the word list and setting a confidence
score is all the BA workshop needs. Designing the matching rules behind
it — conditions, actions, and weightings — is method-authoring territory
for the Data Steward.

### Custom method 2 — an example CPC pattern

The correspondence (and every industrial table) carries references like
`CPC-84120`. A custom data pattern catches that shape wherever it
appears:

| Field | Value |
| --- | --- |
| Name | CPC Part Number |
| Pattern | AAA-nnnnn |
| RegEx | ^CPC-\d{5}$ |
| Matches | CPC part numbers, in columns and inside documents |
| Suggested tag / term | Part Number / Part Number |

**You add this one:** the pattern above is a specification, not a
finished method. Create it via **Data Operations → Data Identification
Methods → Data Patterns → Add Pattern**, give the Column-Name Regex
`(?i)part_?(no|num|number)` a 0.3 weight, the position signature
`AAA-nnnnn` a 0.4 weight, and the content regex `^CPC-\d{5}$` a 0.3
weight (the three panes must sum to 1.0), with a confidence condition of
≥ 0.7 — then re-run identification on `parts` and watch the estate's most
important identifier finally earn its tag. Repeat the recipe for Lot
Number (`AAA-nnnn-nnnn`, `^LOT-\d{4}-\d{4}$`) and the order-number family
and the whole library is yours.

## Verify your work

- [ ] Data Identification (built-ins) has completed on `parts`, `lots`
      and `employees` — and you saw the industrial tables stay silent.
- [ ] The four CPC dictionaries are uploaded and appear in the methods
      list, and re-running identification tags the vocabulary columns.
- [ ] The CPC Part Number pattern exists and tags `parts.part_no`.
- [ ] You can name the two methods and say which one fits a given column,
      and why.
- [ ] You can explain how dictionaries and patterns combine into a
      policy.
- [ ] Data Discovery has run on the `correspondence` folder, and the
      recall letter carries lot- and part-number tags.
- [ ] You can explain why a table is profiled and identified, while a
      document is discovered and string-detected — using the same
      methods.
- [ ] You can articulate the scenario's core lesson: identification is a
      meaning engine, not a privacy engine — an estate without PII still
      needs it, and needs it custom.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Data Identification shows Required or is disabled | The table has not been profiled. Run Data Profiling first, then return. |
| No columns were tagged | At CPC, expected on the first (built-ins only) run — that is Part B's lesson. After the custom methods: confirm they were selected and the data was profiled with samples. |
| A column you expected wasn't matched | Its values may not appear in any dictionary and its shape may not match a pattern — every industrial identifier here is the deliberate example. A user-defined dictionary or pattern is the fix. |
| Too many false matches, or confidence too low | Thresholds and weightings are tunable on each method's identification rule. As a BA, note the column and method for follow-up with the Data Steward. |
| A document wasn't tagged for content | String Detection runs only when at least one dictionary or pattern is added under Document Processing. Confirm Data Discovery completed and the methods were selected. |
| Cannot open Data Identification Methods | In PDC v11 the methods pages are gated to the **Data Steward** and **Data Storage Administrator** roles — work as `nora.whitaker` or `petra.novak`. |

## Why it matters & discussion

Identification is the foundation the rest of the catalog stands on.
Search by business meaning, sensitivity labels, lineage, and data-quality
checks all assume data — structured or not — has already been classified
correctly. Get identification right and a recall that spans the `lots`
table, the shipments table and a folder of letters becomes a filter
rather than a manual hunt.

Discuss: a customer calls about a suspect valve. The catalog can find
every column and document that carries its lot number — but only because
someone built the Lot Number pattern. What other CPC identifiers deserve
a method, in what order, and who owns keeping that library current as
part-number formats evolve?

## What's next

This completes the MFG workshop track — and the four-scenario course.
From here the natural continuations are the **Glossary Generator app**
(install the MFG scenario with `install-scenario.ps1` and build this same
glossary with the scan → suggest → govern → export pipeline), and the
**Technical Track** modules in `courseware/CSCU/Technical-Track/` — the
engine-room deep dives on identification rules, custom method libraries,
and similarity/ML, taught on the CSCU scenario but directly transferable
to CPC.

All Cascade Precision Components data is fictional and generated for training.
