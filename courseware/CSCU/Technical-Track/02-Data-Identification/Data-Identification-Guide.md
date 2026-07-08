# Data Identification — the engine underneath Workshop 5 (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · Technical Track Module 02*

**Primary role:** Data Steward / Data Developer / Admin
**Estimated time:** 45 min

## Why this matters

Profiling tells you what your data looks like. Data Identification is the
step that turns those profiling results into governance: it scans the
profiled values, recognises what they are, and applies **Tags** and
**Business Terms** automatically. It is how a raw column called `email`
becomes a column the catalog knows is PII, Sensitive, and linked to the
Email Address business term — without anyone tagging it by hand. Those tags
are also what later business rules act on.

> **Remember.** Data Identification runs on *profiled* data, so profiling
> must come first — a method can only match values it can see. And the Trust
> Score is computed *last*, after tags exist. The pipeline is: profiling →
> identification → business rules → Trust Score.

## Two methods, one goal

Data Identification classifies each profiled column two complementary ways,
then tags it. The two lenses catch different things, which is why you usually
run both together.

| Method | Matches on | Good for |
| --- | --- | --- |
| Data Dictionary | the column's actual values, against predefined lists of known terms | account/transaction/status codes, branch names, NACHA return codes, custom vocabulary |
| Data Pattern | the shape of the values, as a character-position signature | emails, SSNs, member and account numbers, routing numbers, card PANs — anything with a recognisable format |

The core equation: **Data Dictionary + Pattern Analysis = a Data
Identification Policy.** You select the methods that fit your data, run them
as one job, and on every match the policy applies tags.
`[SCREENSHOT: method selection — dictionaries and patterns as one policy]`

## Method 1 — Data Dictionaries

A data dictionary is a collection of predefined terms and values. Unlike a
glossary, it actively scans the actual column values and classifies the
column by what it *contains*, not just its name — so it can identify data
that names alone never reveal, such as a column of two-letter state codes.

- **System-defined.** PDC ships with 95 built-in dictionaries — ISO country
  codes, currency symbols, standard classifications — ready to use.
- **User-defined.** Built for your business context. Authoring these — for
  CSCU's account types, transaction codes, risk ratings and NACHA return
  codes — is the work of Module 03, and 18 ready-made CSCU dictionaries ship
  with it.

### The matching rule and confidence score

Every dictionary carries a JSON rule. It computes a weighted confidence
score, tests it against conditions, and — if they pass — applies tags.
Condensed, the CSCU Transaction Types rule
(`cscu_transaction_types_rule.json`, Module 03) reads:

> **In plain language.** Confidence = value similarity × 0.8 + column-name
> hint × 0.2 (the regex `(?i)txn_?type|transaction_?type` scores the name).
> Fires when confidence ≥ 0.6 **or** the metadata score alone ≥ 0.7. On a
> match it tags the column **Transaction Type** and assigns the business term
> **Transaction Type Code**. A low-cardinality enum like `txn_type_cd` (eight
> distinct values, all inside the list) scores near-perfect similarity —
> which is exactly why dictionaries are the right tool for code columns.

## Method 2 — Data Patterns

Pattern analysis reduces each value to a signature — a character-by-character
substitution that records where letters, digits, symbols and whitespace fall.
It is dimensional reduction for text, and it is what lets PDC recognise a
*format* rather than a value.

| Symbol | Means | Symbol | Means |
| --- | --- | --- | --- |
| a | lower-case letter | w | whitespace (space, tab) |
| A | upper-case letter | s | symbol  - / \| ! $ % ^ & * |
| n | digit 0–9 | - | other / control character |

**Worked example.** A CSCU member number `CSCU-100501` reduces to
`AAAA-nnnnnn` — four letters, a kept dash, six digits. An account number
`ACC-00070001` reduces to `AAA-nnnnnnnn`; a routing number `122100024` is
simply `nnnnnnnnn`. Significant symbols (a dash or underscore) can be kept
verbatim, and case can optionally be tracked.
`[SCREENSHOT: pattern signature illustration]`

### Position analysis, and from pattern to tag

As values stream in, PDC tallies each recurring pattern and tracks the
largest and smallest character seen at every position — revealing fixed
prefixes (here, the `CSCU-` prefix) and how variable each position is, so it
can propose tighter RegEx. The top ~20 patterns are kept and fed to three
jobs at once:

- **RegEx generation** — an auto-built regular expression for the format.
- **Data identification** — a profiled column's `profilePattern` is compared,
  with a confidence score, to a predefined pattern; on a match it applies
  tags, exactly as a dictionary does.
- **Data-quality checks** — values that fall outside the accepted pattern
  surface as outliers, the candidate errors a DQ rule flags.

## Policies — combining the two

Together, dictionaries and data patterns are called data identification
policies. PDC ships many, spanning whole sectors — **Finance**, **PCI-DSS**,
and **Data Privacy** are the ones a credit union reaches for first. You
select the methods relevant to your data and run them as one job. After a
run, open the Galaxy View to visualise the tagging, follow the data flow, and
locate sensitive data with its security and sensitivity at a glance.

## Running Data Identification

1. **Open the Data Identification tile.** On a profiled table, choose
   Actions → Process, then the Data Identification card.
2. **Select Methods.** Pick the dictionaries and data patterns that fit your
   data — together they form the policy.
3. **Start, and track in Workers.** The job runs asynchronously; watch its
   progress on the Workers page.
4. **Read the results in Data Canvas.** Matching columns are now tagged — for
   example PII and Sensitive — ready for search and governance.
   `[SCREENSHOT: identification results on members]`

## Data Identification in action — a simple CSCU policy

You don't have to build anything to see this work. PDC's built-in Data
Privacy policy already covers email and US ZIP. Run it on the Copper State
Credit Union `members` table and read what it applies.

| Column | How it matches | Tags applied | Sens. |
| --- | --- | --- | --- |
| members.email | Email data pattern (regex value match) + name hint "email" | PII · Sensitive · term Email Address | HIGH |
| members.zip | US ZIP pattern nnnnn / nnnnn-nnnn + name hint "zip" | PII · Location | MEDIUM |
| members.ssn | SSN pattern nnn-nn-nnnn + name hint "ssn" | PII · Sensitive | HIGH |

Plus a table tag **Contains_Personal_Data** on `members`. Each rule fires
when confidence clears its threshold and cardinality is high enough, and the
table's Sensitivity reflects the highest matched column. That is the whole
loop: profiled values in, governed tags out — and those tags are exactly what
a business rule reads next.

## From tags to business rules

Identification is where governance starts, not where it ends. Once a column
is recognised, a business rule can act on it. CSCU's flagship example lives
right in the `members` table.

> **CSCU-Marketing-OptOut-Compliance.** The schema carries a consent flag,
> `opted_out_marketing` — TRUE means the member has opted out of marketing
> and must not be contacted. Identification has already tagged
> `members.email` as PII. The business rule joins the two: no marketing email
> may be sent to any member whose opt-out flag is TRUE. And the data is
> seeded to test it — three opted-out members still hold a valid email
> address, which is precisely the violation the rule must catch (Workshop 4).

And note what identification *misses*: `cards.cvv_cd` is a 3-digit column no
generic method recognises. The failing PCI business rule (Workshop 4), the
PCI attestation document, and the steward's review triangulate what the
engine cannot see alone — engines baseline, stewards decide.

## Where the steward fits

Identification is the **baseline**, not the verdict. Sensitivity conflicts
resolve toward the identified value, but a steward override — applied through
the Glossary Generator in Module 01 — wins last. Run identification **once**;
re-running it after steward overrides clobbers their work.

## Key takeaways

- **Dictionaries match content** — known values, via a weighted confidence
  score and a cardinality test.
- **Patterns match shape** — a per-position signature that also generates
  RegEx and finds data-quality outliers.
- **Policies combine both** — selected methods, run as one job, on
  already-profiled data.
- **Output is governance** — Tags and Business Terms that feed Sensitivity,
  search, the Galaxy View, and the business rules that act on them.

**Next:** Module 03 — Build Your Own CSCU Dictionary & Pattern authors the
methods behind this engine for CSCU's own member numbers, account codes, and
compliance vocabulary — 18 dictionaries and 7 patterns ship ready-made.

All Copper State Credit Union data is fictional and generated for training.
