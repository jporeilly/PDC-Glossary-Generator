# Workshop 5 — Data Identification (LHP)

*Lakeshore Health Partners scenario · PDC 11.0.0 · Dictionaries & Patterns · Builds on Workshop 4 — the tables must be profiled first*

**Primary role:** Business Analyst
**Estimated time:** 60 min

## Why this workshop matters

As a Business Analyst you rely on the catalog knowing *what its data is* —
that classification is what lets you search by business meaning, trust
sensitivity labels, and reason about where information lives. **Data
Identification** is the engine that produces it. At LHP it has the highest
stakes of any scenario in this course: the data it classifies is PHI, and
the places it *cannot* see are exactly where HIPAA problems hide.

> **The big picture.** Profiling tells you the *shape* of a column — its
> statistics, samples, and patterns. Data Identification tells you what
> the column *means*. It compares your data against two kinds of methods
> — dictionaries and patterns — and tags whatever matches, turning "we
> think this column is an SSN" into "the catalog knows it is."

> **Identify once.** Run Data Identification as a one-time baseline. After
> the stewards override tags and sensitivity, re-running identification
> clobbers their work.

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
- Why the engine tags `patients.ssn` effortlessly but is blind to the SSN
  hiding inside a clinical note — and which tool catches each.

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
- **User-defined:** your own lists — upload a single-column CSV, build one
  in the UI, or extract terms from a profiled column.

**Best for:** state codes, specialty codes, appointment types, diagnosis
code sets, city lists, and custom clinical terminology.

> **Example — Marital_Status.** The column holds values such as Single ·
> Married · Divorced. Identification compares those values to the built-in
> Marital_Status dictionary. On a match, it applies the tags PII and
> Sensitive: Marital Status. These low-cardinality values have no regex
> shape, so a dictionary — not a pattern — is the correct method. (LHP's
> own vocabularies — `appt_type_cd`, `specialty_cd`, `dx_cd` — are exactly
> this kind of data, which is why Part B uploads LHP dictionaries for
> them.)

Every dictionary and pattern carries an **identification rule** — the
logic PDC evaluates during Data Identification to decide whether a column
matches. (Note: this is the method's own rule, not a PDC "Business Rule,"
which is the separate data-quality feature you met in Workshop 4.) Take
the built-in Marital_Status dictionary: its rule needs a minimum sample of
~200 values, then computes a confidence score as a weighted blend of
**similarity** (how closely the column's actual values match the
dictionary's accepted list, weighted 0.9) and **metadata score** (hints
from the column name, weighted 0.1) — so content matters far more than the
column's name. The rule only fires when two conditions are both met:
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
expression, against a known format. Patterns suit data with a recognizable
structure, regardless of the specific values.

The pattern alphabet:

| Symbol | Meaning |
| --- | --- |
| A | Upper-case letter |
| a | Lower-case letter |
| n | Digit 0–9 |
| s | Symbol |
| w | Whitespace |

> **Worked example — the MRN.** The value `LHP-300101` reduces to the
> pattern `AAA-nnnnnn` — three letters, a kept dash, six digits. From the
> top ~20 patterns it finds, PDC also recommends a tunable RegEx (here
> `^LHP-\d{6}$`), which is reused later for data-quality checks that flag
> outliers.

**Best for:** SSNs, NPIs, MRNs, claim numbers, email, phone, dates, and
structured code sets (CPT is five digits; NDC is 5-4-2).

`[SCREENSHOT: Data Patterns — email]`

The **eMail** method is a Data Pattern — where a dictionary matches values
against a list, a pattern matches them against a regular expression plus
column-name hints. Its rule computes a confidence score as a weighted
blend of two signals: **regexScore** (how well the column's values match
the email regex, weighted 0.6) and **metadataScore** (how well the column
name matches, weighted 0.4). The name hints live in
`metadataHints.aliases`: a column called `email` scores 0.9, one matching
E-MAIL scores 1.0 — so a well-named column gets a strong metadata signal
even before the values are examined. The `regexMatch` block holds the
actual email regex applied to the content.

What makes this pattern "loose" in a useful way is its condition, which
uses **or**, not and: it fires when either the overall confidence is ≥ 0.5
or the regex score alone is ≥ 0.75. So it catches two cases — a column
that's *named* like email and *looks* like email (combined confidence
clears 0.5), or a column whose values are so clearly email addresses that
the content alone is decisive (regex ≥ 0.75), even if the column name
gives no hint. Like the dictionary, it needs minSamples: 200 before it
evaluates.

On a match, the action applies three tags, each with a confidence value of
100: PII, eMail, and Non-sensitive. Those come straight from the pattern's
categories. This is also a good teaching moment on why sensitivity can
read differently than you'd expect: email is tagged PII (it identifies a
person) yet also Non-sensitive (it's routinely public-facing) — though at
a covered entity even an email address is PHI once it sits in a patient
table, which is why the steward's override matters more here than in any
other scenario.

`[SCREENSHOT: Data Identification Rule — eMail]`

## From match to tag: scored, not guessed

Both methods work the same way underneath. Matching is graded, not a
yes/no guess — which is why identification is reliable. You don't author
these steps as a BA, but knowing their shape explains the results you see.

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
your own — for LHP, the Diagnosis Codes dictionary and the MRN pattern
you'll meet below. Apply, run, then review the results in the Data Canvas
and visualize them in the Galaxy View.

## Walkthrough — identify the patients and encounters tables

Run Data Identification on LHP's profiled tables (`lhp_clinical`),
selecting the dictionaries and patterns that fit their columns. Each
PHI column is caught by the method that suits it, then tagged and linked
to its Workshop 3 business term. Work as `maya.lindqvist` — in PDC v11,
Data Identification Methods belong to the **Data Steward** and **Data
Storage Administrator** roles (Ingrid's Data Developer role, which
authored the business rules, cannot author identification methods — the
gates point in opposite directions).

### Part A — Run Data Identification

1. In the Data Canvas, select the profiled `patients` table, then open
   **Actions → Process**.
2. On the Choose Process page, click the **Data Identification** card. If
   it shows as Required, profiling has not completed — run Data Profiling
   first.
3. Click **Select Methods** and choose the dictionaries and patterns that
   cover names, SSN, email, phone and addresses.
   `[SCREENSHOT: Data Identification — Select Methods (the policy)]`
4. Click **Start**, and watch the job on the Workers page until it
   completes. Repeat for `encounters`, `providers`, `claims` and
   `staff`.

### Part B — Review what was identified

1. Open `patients`. On the Details tab, the matched columns now carry
   Tags and linked Business Terms: `ssn` → SSN (HIGH — the NNN-NN-NNNN
   shape is unmistakable), `email` and `phone` → contact PII, the name
   columns → person-name matches.
   `[SCREENSHOT: identification results on patients]`
2. **The blind spot.** Now open `encounters.note_txt`. It stays untagged —
   even though Workshop 4's failing rule proved two notes carry an SSN.
   This is not a bug; it is the method's nature: a pattern matches a
   column's *values* by shape, and a sixty-word clinical note is not
   shaped like an SSN, no matter what hides inside it. The rule
   (`LHP-No-SSN-In-Clinical-Notes`) searches *inside* the text; the
   pattern classifies the *column*. Pair the untagged note column with
   the failing rule and the HIPAA risk analysis PDF (finding 1):
   quality, compliance and documents all point at the defect the engine
   cannot see. That triangulation is the lesson — engines baseline,
   rules interrogate, stewards decide.
3. Some columns will not be as expected — `mrn` stays untagged too, because
   no built-in method knows LHP's record-number format. Built-in methods
   are a fast, generic starting point, and their limits are exactly why
   every organisation ends up building custom dictionaries and patterns.
   You fix this one below.

**Dictionary vs pattern, in practice:** specialty codes, appointment types
and diagnosis codes are caught by dictionaries (their meaning is in the
values); SSN, email, phone and NPI are caught by patterns (their meaning
is in the shape); an address takes both. The method assignments above are
illustrative — confirm them against your lab's identification run.

### Part C — Visualize in the Galaxy View

1. With `patients` selected, open **Actions → View Galaxy**.
2. Click **Filters** and turn on *Show only Tagged Items* (or items with
   business terms) to highlight exactly the columns identification
   classified.
   `[SCREENSHOT: Galaxy View — tagged patients columns]`

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
dictionaries and patterns at their content. The pipeline differs slightly,
but the methods are identical — and for the free-text problem you just met
in Part B, this is where the answer lives: **String Detection reads inside
the text**, which is exactly what the column-shape pattern could not do.

> **Two worlds, the same methods.** A structured column is profiled, then
> Data Identification applies the scored rule logic — confidence,
> condition, action. An unstructured document is profiled by Data
> Discovery, and within it **String Detection** scans the text for the
> same dictionary and pattern values — flagging their presence, and
> optionally their count. (String Detection matches values directly; it
> does not apply the dictionaries' scored rules.)

### The document processing options

When you run Data Discovery on files, the Document Processing tab offers
String Detection plus a set of machine-learning helpers that only apply to
documents:

| Option | What it does |
| --- | --- |
| String Detection | Scans document text for the values in selected dictionaries and patterns, and tags the file on a match — presence only, or presence and count. |
| Address Detection | Machine-learning scan for U.S. postal addresses; tags a business term you choose when an address is found. |
| Data Classification | Classifies a document by its semantic content; assigns the matching business terms you supply (for example, a document type). |
| Summaries & sentiment | Generates a concise document summary and a sentiment label, shown on the asset's Summary tab. |
| Document Metadata | Extracts properties such as owner, page count, and paragraph count (Office and PDF files). |

**Supported file types:** PDF, DOC, DOCX, TXT, and RTF, among others.
Structured and semi-structured files (CSV, JSON, Parquet) are profiled the
same way, with structured outputs.

### Walkthrough — PHI in the LHP correspondence

The `lhp-documents/correspondence` folder holds emails and letters about
patients. The goal is the same as for the table: flag every document that
contains patient identifiers.

1. In the Data Canvas, select the `correspondence` folder, then click
   Process. Run **Metadata Ingest** first.
2. Click the **Data Discovery** card. On the Document Processing tab, add
   the PII/PHI dictionaries and patterns (name, SSN, email, phone,
   address) under String Detection.
3. Optionally enable **Address Detection** (tag an Address term) and
   **Data Classification** (to label each letter by type). Click **Start
   Discovering**.
4. Open each document on the Data Canvas. Files that contain patient
   identifiers now carry the matching Tags and Business Terms, visible in
   the Document Properties and Business Terms panes.
   `[SCREENSHOT: discovery results on a correspondence letter]`

| Document | Type | Identifiers it surfaces |
| --- | --- | --- |
| email_records_request_LHP-300107 | Email | name · email · address · MRN · DOB |
| email_billing_question_CLM-40000012 | Email | name · email · MRN · claim number |
| letter_referral_cardiology_LHP-300104 | Letter | name · MRN · DOB · diagnoses · NPI |
| letter_appeal_ecg_claim_CLM-40000009 | Letter | name · MRN · claim number · diagnosis · CPT |
| letter_optout_confirmation_LHP-300109 | Letter | name · address · MRN · consent status |

> **A pattern reaches into the letters too.** The reference codes in the
> correspondence — `LHP-300107`, `CLM-40000009` — follow fixed shapes
> (`AAA-nnnnnn`, `AAA-nnnnnnnn`). A custom data pattern for those shapes
> flags LHP record and claim references wherever they appear in a
> document, not just in a column. The method assignments above are
> illustrative — confirm them against the real correspondence in your
> lab.

## Choosing methods for LHP

Most of LHP's data is covered by methods that ship with the catalog.
Start by selecting the built-in dictionaries and patterns that fit, then
add custom LHP methods for what the built-ins don't know.

### Recommended built-in methods — structured (patients, encounters)

| LHP data | Built-in method | Type |
| --- | --- | --- |
| first_nm / last_nm | person-name dictionary | Dictionary |
| ssn | SSN | Pattern |
| email | eMail | Pattern |
| phone | Phone Number | Pattern |
| addr1 / city / st / zip | US States dictionary + ZIP / address pattern | Dict + Pattern |
| dob | date pattern | Pattern |
| mrn | nothing built-in — LHP MRN pattern (custom — below) | — |
| dx_cd / specialty_cd / appt_type_cd | nothing built-in — LHP dictionaries (custom — below) | — |

**Selecting methods:** choose the built-in name dictionary, the SSN,
eMail and Phone patterns, and the US States dictionary together at Select
Methods — that selection is your policy for this run. Exact built-in names
vary by release, so confirm them in your lab's method list.

### Recommended methods — unstructured (correspondence)

| Need | Method |
| --- | --- |
| names / SSN / email / phone | the same dictionary and patterns, run under String Detection |
| postal addresses | Address Detection (ML) + US States dictionary |
| letter type | Data Classification (ML) |
| MRN / claim references | LHP MRN pattern (custom — below) |
| clinic cities | LHP Service Cities dictionary (custom — below) |

### Custom method 1 — the LHP dictionaries

Built-in dictionaries know US states and country codes, but not which
Minnesota communities LHP serves, which specialties it credentials, or
which diagnosis codes its registries track. Four single-column CSVs ship
with this workshop (header `term`, one value per row):

| Dictionary | File | Values |
| --- | --- | --- |
| LHP Service Cities | `LHP-Service-Cities-Dictionary.csv` | 16 Minnesota cities, Minneapolis to Grand Rapids |
| LHP Specialty Codes | `LHP-Specialty-Codes-Dictionary.csv` | FAMMED, PEDS, CARDIO, DERM, ORTHO, BEHAV |
| LHP Appointment Types | `LHP-Appointment-Types-Dictionary.csv` | NEW, FOLLOWUP, PHYSICAL, TELEHEALTH, URGENT |
| LHP Diagnosis Codes | `LHP-Diagnosis-Codes-Dictionary.csv` | The 13 ICD-10 codes in the registry scope |

**Uploading a dictionary:**

1. In the left navigation, go to **Data Operations → Dictionaries**, then
   click **Add Dictionary**.
2. Enter a Name (`LHP Diagnosis Codes`), a short description, and a
   Category (add a new `LHP_Clinical` category). Make sure the dictionary
   is enabled.
3. Choose **Upload Dictionary**, upload the CSV, and set a Confidence
   Score of 0.7.
   `[SCREENSHOT: dictionary upload — LHP Diagnosis Codes]`
4. (Optional) add a Column Name Regex hint such as `(?i)dx|diag` so a
   diagnosis column is matched on its name as well as its values.
5. Click **Create Dictionary**. It now appears in the methods list —
   select it in a Data Identification run on a table, or under String
   Detection when discovering documents. Repeat for the other three, then
   re-run identification on `encounters`, `providers` and `appointments`
   and watch the vocabulary columns light up precisely — that's what
   dictionaries are for.

**Rules vs upload:** uploading the word list and setting a confidence
score is all the BA workshop needs. Designing the matching rules behind it
— conditions, actions, and weightings — is method-authoring territory for
the Data Steward.

### Custom method 2 — an example LHP pattern

The correspondence (and the `mrn` column the built-ins missed) carries
references like `LHP-300107`. A custom data pattern catches that shape
wherever it appears:

| Field | Value |
| --- | --- |
| Name | LHP MRN |
| Pattern | AAA-nnnnnn |
| RegEx | ^LHP-\d{6}$ |
| Matches | LHP medical record numbers, in columns and inside documents |
| Suggested tag / term | MRN / MRN |

**You add this one:** the pattern above is a specification, not a
finished method. Create it via **Data Operations → Data Identification
Methods → Data Patterns → Add Pattern**, give the Column-Name Regex
`(?i)mrn|med(ical)?_?rec` a 0.3 weight, the position signature
`AAA-nnnnnn` a 0.4 weight, and the content regex `^LHP-\d{6}$` a 0.3
weight (the three panes must sum to 1.0), with a confidence condition of
≥ 0.7 — then re-run identification on `patients` and watch the miss from
Part B disappear.

## Verify your work

- [ ] Data Identification has completed on `patients`, `encounters`,
      `providers`, `claims` and `staff`.
- [ ] The matched columns carry Tags and linked Business Terms on the
      Details tab — SSN, email and contact PII where expected.
- [ ] You can name the two methods and say which one fits a given column,
      and why.
- [ ] You can explain how dictionaries and patterns combine into a
      policy.
- [ ] Data Discovery has run on the `correspondence` folder, and
      documents containing patient identifiers carry Tags and Business
      Terms.
- [ ] You can explain why a table is profiled and identified, while a
      document is discovered and string-detected — using the same
      methods.
- [ ] The four LHP dictionaries are uploaded and appear in the methods
      list.
- [ ] You can explain the `note_txt` triangulation — the untagged free-text
      column, the failing SSN rule, and the HIPAA risk analysis all point
      at one defect the shape-matcher cannot see — and why `mrn` needed a
      custom pattern.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Data Identification shows Required or is disabled | The table has not been profiled. Run Data Profiling first, then return. |
| No columns were tagged | No matching methods were selected, or the data lacked samples. Re-run after selecting the relevant dictionaries and patterns, and confirm the data was profiled with samples. |
| A column you expected wasn't matched | Its values may not appear in any dictionary and its shape may not match a pattern — `mrn` is the deliberate example, and `note_txt` can never match a whole-value shape. A user-defined method (or, for free text, a business rule and String Detection) is the fix. |
| Too many false matches, or confidence too low | Thresholds and weightings are tunable on each method's identification rule. As a BA, note the column and method for follow-up with the Data Steward. |
| A document wasn't tagged for content | String Detection runs only when at least one dictionary or pattern is added under Document Processing. Confirm Data Discovery completed and the methods were selected. |
| Cannot open Data Identification Methods | In PDC v11 the methods pages are gated to the **Data Steward** and **Data Storage Administrator** roles — work as `maya.lindqvist` or `victor.osei`. |

## Why it matters & discussion

Identification is the foundation the rest of the catalog stands on. Search
by business meaning, sensitivity labels, lineage, and data-quality checks
all assume data — structured or not — has already been classified
correctly. Get identification right and an OCR data-inventory request that
spans both the `patients` table and a folder of letters becomes a filter
rather than a manual hunt.

Discuss: an investigator asks for every place a patient's SSN is held. The
pattern found `patients.ssn`; the business rule found two leaks inside
clinical notes; String Detection can find it inside a letter. What does
that division of labour tell you about relying on any single control — and
who at LHP owns closing the note_txt leak?

## What's next

This completes the HEALTH workshop track. From here the natural
continuations are the **Glossary Generator app** (install the HEALTH
scenario with `install-scenario.ps1` and build this same glossary with the
scan → suggest → govern → export pipeline), and the **Technical Track**
modules in `courseware/CSCU/Technical-Track/` — the engine-room deep dives
on identification rules, custom method libraries, and similarity/ML,
taught on the CSCU scenario but directly transferable to LHP.

All Lakeshore Health Partners data is fictional and generated for training.
