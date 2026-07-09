# Workshop 5 — Data Identification (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · Dictionaries & Patterns · Builds on Workshop 4 — the tables must be profiled first*

**Primary role:** Business Analyst
**Estimated time:** 60 min

## Why this workshop matters

As a Business Analyst you rely on the catalog knowing *what its data is* —
that classification is what lets you search by business meaning, trust
sensitivity labels, and reason about where information lives. **Data
Identification** is the engine that produces it. This workshop builds a
complete conceptual picture of how that engine works; the Technical Track
then builds and tunes the methods behind it.

> **The big picture.** Profiling tells you the *shape* of a column — its
> statistics, samples, and patterns. Data Identification tells you what the
> column *means*. It compares your data against two kinds of methods —
> dictionaries and patterns — and tags whatever matches, turning "we think
> this column is a card number" into "the catalog knows it is."

> **Identify once.** Run Data Identification as a one-time baseline. After
> the stewards override tags and sensitivity (Technical Track: the Glossary
> Generator's Apply), re-running identification clobbers their work.

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
- Why the one column it *misses* (`cvv_cd`) is as instructive as everything
  it finds.

## Where Data Identification sits

Identification is the second step of the catalog pipeline. Each stage feeds
the next: you cannot identify data you have not profiled, and you cannot
govern data you have not identified.

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

**Best for:** state codes, transaction and account type codes, status
vocabularies, city lists, and custom business terminology.

> **Example — Marital_Status.** The column holds values such as Single ·
> Married · Divorced. Identification compares those values to the built-in
> Marital_Status dictionary. On a match, it applies the tags PII and
> Sensitive: Marital Status. These low-cardinality values have no regex
> shape, so a dictionary — not a pattern — is the correct method. (CSCU's
> own enums — `txn_type_cd`, `acct_type_cd`, `kyc_status` — are exactly
> this kind of data, which is why Part B uploads CSCU dictionaries for
> them.)

Every dictionary and pattern carries an **identification rule** — the logic
PDC evaluates during Data Identification to decide whether a column
matches. (Note: this is the method's own rule, not a PDC "Business Rule,"
which is the separate data-quality feature you met in Workshop 4.) Take the
built-in Marital_Status dictionary: its rule needs a minimum sample of
~200 values, then computes a confidence score as a weighted blend of
**similarity** (how closely the column's actual values match the
dictionary's accepted list, weighted 0.9) and **metadata score** (hints
from the column name, weighted 0.1) — so content matters far more than the
column's name. The rule only fires when two conditions are both met:
confidence ≥ 0.7 **and** column cardinality ≥ 3 (a guard that stops columns
with one or two distinct values being mislabelled). On a match, its action
applies the tags. Those categories are also what drive the column's
Sensitivity rating (UNKNOWN → LOW/MEDIUM/HIGH), and the dictionary's linked
term lets the same match seed a business-term association.

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

> **Worked example — the member number.** The value `CSCU-100501` reduces
> to the pattern `AAAA-nnnnnn` — four letters, a kept dash, six digits.
> From the top ~20 patterns it finds, PDC also recommends a tunable RegEx
> (here `^CSCU-\d{6}$`), which is reused later for data-quality checks that
> flag outliers.

**Best for:** email, phone, SSN, card numbers, routing numbers, IP
addresses, dates, and structured reference codes.

`[SCREENSHOT: Data Patterns — email]`

The **eMail** method is a Data Pattern — where a dictionary matches values
against a list, a pattern matches them against a regular expression plus
column-name hints. Its rule computes a confidence score as a weighted blend
of two signals: **regexScore** (how well the column's values match the
email regex, weighted 0.6) and **metadataScore** (how well the column name
matches, weighted 0.4). The name hints live in `metadataHints.aliases`: a
column called `email` scores 0.9, one matching E-MAIL scores 1.0 — so a
well-named column gets a strong metadata signal even before the values are
examined. The `regexMatch` block holds the actual email regex applied to
the content.

What makes this pattern "loose" in a useful way is its condition, which
uses **or**, not and: it fires when either the overall confidence is ≥ 0.5
or the regex score alone is ≥ 0.75. So it catches two cases — a column
that's *named* like email and *looks* like email (combined confidence
clears 0.5), or a column whose values are so clearly email addresses that
the content alone is decisive (regex ≥ 0.75), even if the column name gives
no hint. Like the dictionary, it needs minSamples: 200 before it evaluates.

On a match, the action applies three tags, each with a confidence value of
100: PII, eMail, and Non-sensitive. Those come straight from the pattern's
categories. This is also a good teaching moment on why sensitivity can read
differently than you'd expect: email is tagged PII (it identifies a person)
yet also Non-sensitive (it's routinely public-facing), which is why
`members.email` may not land as HIGH the way `ssn` or `card_no` does — the
category tags, not the field itself, decide the sensitivity.

`[SCREENSHOT: Data Identification Rule — eMail]`

## From match to tag: scored, not guessed

Both methods work the same way underneath. Matching is graded, not a yes/no
guess — which is why identification is reliable. You don't author these
steps as a BA, but knowing their shape explains the results you see.

| Step | What happens |
| --- | --- |
| 1 · Compare | Profiled values are checked against the dictionary or pattern, plus a hint from the column name. |
| 2 · Score | A confidence score blends content similarity with the metadata (column-name) hint. |
| 3 · Condition | If the score clears the threshold — for example ≥ 0.7 — the match is accepted. |
| 4 · Action | Apply the tags and link the business terms to the column. |

**For the Technical Track:** you will set the weightings, write the
conditions, and tune the thresholds behind each method (Modules 02 and 03).
For now, the takeaway is that every tag is earned by a graded match
clearing a threshold.

## Policies: dictionaries + patterns together

A policy is not a pre-built object you pick off a shelf. In PDC a policy is
simply the combination of dictionaries plus patterns you select for a run —
the methods you choose at the Select Methods step. That selection *is* your
policy.

You assemble it from the built-in dictionaries and patterns plus any of
your own — for CSCU, the Service Cities dictionary and the Member Number
pattern you'll meet below. Apply, run, then review the results in the Data
Canvas and visualize them in the Galaxy View.

## Walkthrough — identify the members and cards tables

Run Data Identification on CSCU's profiled tables (`cscu_core`), selecting
the dictionaries and patterns that fit their columns. Each personal-data
column is caught by the method that suits it, then tagged and linked to its
Workshop 3 business term. Work as `elena.ramirez` — in PDC v11, Data
Identification Methods belong to the **Data Steward** and **Data Storage
Administrator** roles (Dana's Data Developer role, which authored the
business rules, cannot author identification methods — the gates point in
opposite directions).

### Part A — Run Data Identification

1. In the Data Canvas, select the profiled `members` table, then open
   **Actions → Process**.
2. On the Choose Process page, click the **Data Identification** card. If
   it shows as Required, profiling has not completed — run Data Profiling
   first.
3. Click **Select Methods** and choose the dictionaries and patterns that
   cover names, email, phone, SSN and addresses.
   `[SCREENSHOT: Data Identification — Select Methods (the policy)]`
4. Click **Start**, and watch the job on the Workers page until it
   completes. Repeat for `cards`, `accounts`, `transactions` and
   `ach_payments`.

### Part B — Review what was identified

1. Open `members`. On the Details tab, the matched columns now carry Tags
   and linked Business Terms: `ssn` → SSN (HIGH), `email` and `phone` →
   contact PII. On `cards`, `card_no` is caught by the card-number
   pattern — the 4111… test PANs match the issuer prefix and Luhn check.
   `[SCREENSHOT: identification results on members]`
2. Some columns will *not* be as expected — which should be no surprise!
   Built-in methods are a fast, generic starting point, and their limits
   are exactly why every organisation ends up building custom dictionaries
   and patterns.
3. **The planted finding:** `cards.cvv_cd` — a 3-digit column no generic
   method recognises — stays untagged. Pair it with Workshop 4's failing
   PCI rule and the PCI DSS attestation PDF in `compliance/`:
   identification, quality and documents all point at the same defect.
   That triangulation is the lesson — engines baseline, stewards decide.

**Dictionary vs pattern, in practice:** status codes and the opt-out flag
are caught by dictionaries (their meaning is in the values); email, phone,
SSN and card numbers are caught by patterns (their meaning is in the
shape); an address takes both. The method assignments above are
illustrative — confirm them against your lab's identification run.

### Part C — Visualize in the Galaxy View

1. With `members` selected, open **Actions → View Galaxy**.
2. Click **Filters** and turn on *Show only Tagged Items* (or items with
   business terms) to highlight exactly the columns identification
   classified.
   `[SCREENSHOT: Galaxy View — tagged members columns]`

> **One tag vocabulary, everywhere.** A custom dictionary or pattern must
> apply the exact same tag label as the glossary and everywhere else — but
> PDC won't enforce it, because Assign Tags is free text. So it's a
> discipline: one controlled tag list, reused verbatim across dictionaries,
> patterns, the glossary, and the Glossary Generator's governed tag set.
> And when a method should carry glossary meaning, use its Assign Business
> Term action rather than typing a look-alike tag.

## Beyond tables: identifying unstructured documents

Identification does not stop at tables. PDC also profiles documents — PDFs,
Word files, plain-text, and RTF — and points the very same dictionaries and
patterns at their content. The pipeline differs slightly, but the methods
are identical: a name dictionary or an email pattern works just as well
inside a letter as it does in a column.

> **Two worlds, the same methods.** A structured column is profiled, then
> Data Identification applies the scored rule logic — confidence,
> condition, action. An unstructured document is profiled by Data
> Discovery, and within it **String Detection** scans the text for the same
> dictionary and pattern values — flagging their presence, and optionally
> their count. (String Detection matches values directly; it does not apply
> the dictionaries' scored rules.)

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

### Walkthrough — PII in the CSCU correspondence

The `cscu-documents/correspondence` folder holds emails and letters about
members. The goal is the same as for the table: flag every document that
contains personal data.

1. In the Data Canvas, select the `correspondence` folder, then click
   Process. Run **Metadata Ingest** first.
2. Click the **Data Discovery** card. On the Document Processing tab, add
   the PII dictionaries and patterns (name, email, phone, address) under
   String Detection.
3. Optionally enable **Address Detection** (tag an Address term) and **Data
   Classification** (to label each letter by type). Click **Start
   Discovering**.
4. Open each document on the Data Canvas. Files that contain personal data
   now carry the matching Tags and Business Terms, visible in the Document
   Properties and Business Terms panes.
   `[SCREENSHOT: discovery results on a correspondence letter]`

| Document | Type | Personal data it surfaces |
| --- | --- | --- |
| email_dispute_card_4111_1004 | Email | name · email · member number · account ref · card dispute detail |
| email_wire_inquiry_thread | Email | name · email · member number · wire amount |
| letter_adverse_action_LN-APP-2026-0342 | Letter | name · address · loan application ref |
| letter_dormant_account_CSCU-100507 | Letter | name · address · member number |
| letter_overdraft_notice_ACC-00070010 | Letter | name · address · account number · fee amount |

> **A pattern reaches into the letters too.** The reference codes in the
> correspondence — `CSCU-100507`, `ACC-00070010` — follow fixed shapes
> (`AAAA-nnnnnn`, `AAA-nnnnnnnn`). A custom data pattern for those shapes
> flags CSCU member and account references wherever they appear in a
> document, not just in a column. The method assignments above are
> illustrative — confirm them against the real correspondence in your lab.

## Choosing methods for CSCU

Most of CSCU's data is covered by methods that ship with the catalog.
Start by selecting the built-in dictionaries and patterns that fit, then
add custom CSCU methods for what the built-ins don't know.

### Recommended built-in methods — structured (members, cards)

| CSCU data | Built-in method | Type |
| --- | --- | --- |
| first_nm / last_nm | person-name dictionary | Dictionary |
| email | eMail | Pattern |
| phone | Phone Number | Pattern |
| ssn | SSN | Pattern |
| card_no | Credit Card Number | Pattern |
| addr1 / city / st / zip | US States dictionary + ZIP / address pattern | Dict + Pattern |
| opted_out_marketing | low-cardinality flag — custom Yes/No dictionary (Technical Track) | — |

**Selecting methods:** choose the built-in name dictionary, the eMail,
Phone, SSN and card patterns, and the US States dictionary together at
Select Methods — that selection is your policy for this run. Exact built-in
names vary by release, so confirm them in your lab's method list.

### Recommended methods — unstructured (correspondence)

| Need | Method |
| --- | --- |
| names / email / phone | the same dictionary and patterns, run under String Detection |
| postal addresses | Address Detection (ML) + US States dictionary |
| letter type | Data Classification (ML) |
| member / account references | CSCU Member Number pattern (custom — below) |
| branch cities | CSCU Service Cities dictionary (custom — below) |

### Custom method 1 — the CSCU Service Cities dictionary

Built-in dictionaries know US states and country codes, but not which
Arizona communities CSCU serves. A Service Cities dictionary lets
identification recognise CSCU's branch and member cities — in the
`members.city` column and in the correspondence alike. The asset is a
single-column CSV: `CSCU-Branch-Cities-Dictionary.csv` (header `term`, one
city per row — 16 towns from Phoenix and Tempe to Globe, Prescott, Payson
and Kingman).

**Uploading the dictionary:**

1. In the left navigation, go to **Data Operations → Dictionaries**, then
   click **Add Dictionary**.
2. Enter a Name (`CSCU Service Cities`), a short description, and a
   Category (add a new `CSCU_Reference` category). Make sure the dictionary
   is enabled.
3. Choose **Upload Dictionary**, upload `CSCU-Branch-Cities-Dictionary.csv`,
   and set a Confidence Score of 0.7.
   `[SCREENSHOT: dictionary upload — CSCU Service Cities]`
4. (Optional) add a Column Name Regex hint such as `(?i)city|town` so a
   city column is matched on its name as well as its values.
5. Click **Create Dictionary**. It now appears in the methods list — select
   it in a Data Identification run on a table, or under String Detection
   when discovering documents. Do the same for
   `CSCU-Transaction-Types-Dictionary.csv` (`CSCU Transaction Types` — the
   eight `txn_type_cd` values), then re-run identification on `members` and
   `transactions` and watch the low-cardinality enum columns light up
   precisely — that's what dictionaries are for.

**Rules vs upload:** uploading the word list and setting a confidence score
is all the BA workshop needs. Designing the matching rules behind it —
conditions, actions, and weightings — is covered in the Technical Track.

### Custom method 2 — an example CSCU pattern

The correspondence (and the `mbr_no` column) carries references like
`CSCU-100507`. A custom data pattern catches that shape wherever it
appears. Use this as the worked example when you build it in the Technical
Track (Module 03 authors it step by step):

| Field | Value |
| --- | --- |
| Name | CSCU Member Number |
| Pattern | AAAA-nnnnnn |
| RegEx | ^CSCU-\d{6}$ |
| Matches | CSCU member numbers, in columns and inside documents |
| Suggested tag / term | Member Number / Member Number |

**You add this one:** the pattern above is a specification, not a finished
method. Creating patterns and dictionaries from scratch — regex authoring,
confidence weightings, conditions, and actions — is the Technical Track's
territory.

## Verify your work

- [ ] Data Identification has completed on `members`, `cards`, `accounts`,
      `transactions` and `ach_payments`.
- [ ] The matched columns carry Tags and linked Business Terms on the
      Details tab — SSN, card, and contact PII where expected.
- [ ] You can name the two methods and say which one fits a given column,
      and why.
- [ ] You can explain how dictionaries and patterns combine into a policy.
- [ ] Data Discovery has run on the `correspondence` folder, and documents
      containing personal data carry Tags and Business Terms.
- [ ] You can explain why a table is profiled and identified, while a
      document is discovered and string-detected — using the same methods.
- [ ] The CSCU Service Cities and CSCU Transaction Types dictionaries are
      uploaded and appear in the methods list.
- [ ] You can explain the `cvv_cd` triangulation — the untagged column, the
      failing PCI rule, and the attestation PDF all point at one defect.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Data Identification shows Required or is disabled | The table has not been profiled. Run Data Profiling first, then return. |
| No columns were tagged | No matching methods were selected, or the data lacked samples. Re-run after selecting the relevant dictionaries and patterns, and confirm the data was profiled with samples. |
| A column you expected wasn't matched | Its values may not appear in any dictionary and its shape may not match a pattern — `cvv_cd` is the deliberate example. A user-defined dictionary or pattern is the fix — covered in the Technical Track. |
| Too many false matches, or confidence too low | Thresholds and weightings are tunable. Adjusting them is the Technical Track's focus; as a BA, note the column and method for follow-up. |
| A document wasn't tagged for content | String Detection runs only when at least one dictionary or pattern is added under Document Processing. Confirm Data Discovery completed and the methods were selected. |
| Cannot open Data Identification Methods | In PDC v11 the methods pages are gated to the **Data Steward** and **Data Storage Administrator** roles — work as `elena.ramirez` or `omar.haddad`. |

## Why it matters & discussion

Identification is the foundation the rest of the catalog stands on. Search
by business meaning, sensitivity labels, lineage, and data-quality checks
all assume data — structured or not — has already been classified
correctly. Get identification right and a compliance request that spans
both the `members` table and a folder of letters becomes a filter rather
than a manual hunt.

Discuss: an NCUA examiner asks for every place a member's data is held.
Which method catches a `secondary_email` column if it's added to the table
next quarter — and how would you find the same member's details inside the
`correspondence` folder?

## What's next

The Technical Track goes under the hood of everything you've just seen:
Module 02 dissects the engine — rule anatomy, weights and conditions —
and Module 03 builds the full CSCU method library: eighteen dictionaries
and seven patterns, including the CSCU Member Number pattern specified
above, assembled into escalating policies and run against both the banking
database and the document store.

All Copper State Credit Union data is fictional and generated for training.
