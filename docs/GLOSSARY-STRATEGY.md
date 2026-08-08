# Implementing a Business Glossary in Pentaho Data Catalog

**A strategy and best-practice guide** — the rollout, the gotchas, and why
glossaries drift unless specific things are in place.

This is the *why* and the *in what order*. For how to drive the app, see
[GUIDE.md](GUIDE.md); for the API surface, [REFERENCE.md](REFERENCE.md).

---

## 1. The premise

A catalog gives you **containers**. It does not give you **conventions**.

PDC ships everything you need to hold a governed glossary: glossaries, business
terms, tags, sensitivity, roles, and Data Identification methods (dictionaries
and patterns) that stamp terms onto columns automatically. What it does not do —
what no catalog does — is force two people to describe the same concept the same
way.

That matters because in PDC the same three facts about a column get decided in
more than one place:

| Fact | Decided in the glossary | Decided again in… |
| --- | --- | --- |
| What this concept **is** | Business term + definition | Data Identification method bound to a term |
| How it is **labelled** | Tags on the term | Tags a pattern/dictionary stamps on match |
| How **sensitive** it is | Sensitivity on the term | Sensitivity applied by identification |

Nothing forces those to agree. Six months on you have `PII` and `pii`,
"Customer ID" and "Cust Identifier", one steward calling a postcode HIGH and
another calling it LOW — and a classification you cannot defend in an audit.
That is not a discipline failure. It is the predictable result of asking humans
to hold a convention in their heads across ten domains and two years.

**The premise of the Glossary Generator is that the governed unit is not the
glossary — it is one row per concept**, carrying the term, its controlled tags,
its rule-derived sensitivity and its category, written once and read by
everything downstream. That row is the **Registry**
(`registries/registry.<glossary>.json`). The glossary JSONL is an output. The
Registry is the asset.

---

## 2. Why glossaries drift — the conditions

Drift is not random. It is what happens when any of the following is missing.
Each one has a characteristic failure you can recognise.

### X — A controlled tag vocabulary

**Unless tags come from an allow-list**, every steward invents their own.
Free-text tagging produces `PII`, `pii`, `PII-Data`, `personal` — four labels,
one concept, and a search that returns a quarter of what it should.

The app holds a **two-layer Term & Tag dictionary**: a generic baseline plus a
steward-approved company layer. Tags are drawn from it, not typed —
`suggester.suggest_tags` builds "a deterministic, meaningful, de-duplicated tag
set … from the controlled tag dictionary (allow-list + rules)".

*Recognise it by:* tag counts that keep rising while coverage doesn't.

### Y — Deterministic classification

**Unless sensitivity and PII category are derived from evidence by rule**, they
become opinion — and opinion varies by person, by mood, and by how much time
someone had that afternoon. Worse, if you let an LLM decide them, they vary
*per run*, which means your classification is not reproducible and therefore not
auditable.

In this app they are computed from the profile — value patterns, signatures,
reference lists — never proposed by the model. The prompt says so explicitly:

> `Do NOT return sensitivity or PII — those are deterministic from the scan.`
> — `glossary_generator/ai/llm.py`

The LLM drafts *language* (names, definitions, purpose). It does not get a vote
on classification.

*Recognise it by:* two runs over the same data producing different sensitivity.

### Z — One row read by both the glossary and the identification methods

**Unless the glossary and the detection methods draw from the same row**, they
diverge the moment either is edited. Someone tightens a pattern; the term's tags
no longer match what the pattern stamps. Nothing errors. The catalog is now
quietly inconsistent.

The Registry is the contract: the Glossary Generator **writes** it at export;
the [Policy Generator](https://github.com/jporeilly/PDC-Policy-Generator)
**reads** it to emit dictionaries and patterns bound to the same term, stamping
the same tags — and drift-checks deployed methods against it afterwards.

*Recognise it by:* a column carrying a term whose tags differ from the term's own.

### …and one more, once you have several glossaries

**Unless you can see across glossaries**, each steward re-authors concepts their
neighbours already own. "Customer Identifier" in Customer, "Cust ID" in Billing,
"Client Number" in Servicing — three terms, one concept, and no way to roll up.

Resolve has always reused an existing term's id catalog-wide rather than minting
a duplicate, so nothing is written twice. Since **1.36.8**, Review also *tells*
you during authoring: **Check PDC for existing terms** badges each candidate
with the glossary that already owns it.

---

## 3. Rollout strategy

The order matters more than the pace. Standards first, then scale.

### Phase 0 — Pilot one domain (the point is the standard, not the glossary)

Pick one domain with a willing steward and genuinely important data. Run it end
to end. **The deliverable is not the glossary — it is the convention**: the
domain pack, the tag dictionary, the category set, the sensitivity rules.

Budget for this taking longer than the domains that follow. It should.

### Phase 1 — Freeze the global layer

Before a second domain starts, fix what every domain shares:

| Global — set once, changed by exception | Per domain — the steward's call |
| --- | --- |
| Tag allow-list | Which concepts exist |
| Sensitivity rules | Definitions and purpose |
| Category set | Stewardship and ratings |
| Naming conventions | The approval gate |

A steward decides *what the concepts are*. They do not get to invent the
vocabulary those concepts are described in. That distinction is what makes many
small glossaries safe instead of a drift factory.

### Phase 2 — Roll out by domain

One glossary per **accountable steward**, not per source — sources cut across
domains, stewardship doesn't. Scope each load with `includePatterns` /
`excludePatterns` in the bulk CSV so you review one coherent subject area at a
time.

Per domain: scan + profile → generate → **check for existing terms** → review →
govern → resolve → apply.

Run the cross-glossary check *early* on later domains. Reuse climbs as coverage
grows, and it is far cheaper to reuse than to reconcile.

### Phase 3 — Identification methods, then drift-check

Feed the Registry to the Policy Generator, deploy the dictionaries and patterns,
then run its drift check on a schedule. This is the step that makes the glossary
*operational* rather than documentation: terms start landing on columns
automatically, stamped with the tags the Registry says they carry.

---

## 4. Sizing the domain split

- **One glossary per accountable owner.** If nobody's name is on it, it decays.
- **5–15 glossaries** suits a mid-size enterprise. Fewer and review is
  unmanageable; more and you fragment concepts across too many owners.
- **Terms plateau, columns don't.** Rows collapse on `(Category, Term)` before a
  human sees them, so sixty `customer_id` columns become one term carrying sixty
  sources. An organisation has a few hundred business concepts however many
  tables express them — size the effort on concepts, not columns.

---

## 5. Building the domain pack

The pack is what makes the second scan visibly better than the first: the
vocabulary of one company, learned once. The temptation is to sit down and
author an industry taxonomy before scanning anything. Resist it.

`packinit` — the scaffolder — states the reason plainly, and it is worth quoting
because it is the whole practice in one sentence:

> `table_category / table_terms / terms / tag_rules` left **EMPTY on purpose**.
> Inventing table names for a database nobody has scanned yet produces rules that
> never match **and read as if they were curated**.

That last clause is the trap. A hand-authored taxonomy looks authoritative,
matches nothing, and goes unquestioned precisely because it looks deliberate.

### Author one thing: the category list

(You do not start from a blank wall: a packless scan groups rows under their
**physical names** — *Monthly Usage* from `monthly_usage`, a document's top
folder — and the steward renames each group once to the business word. Evidence
proposes; the steward disposes. Stewards are never left guessing.)

It is the only input a person reliably knows before scanning, because it comes
from how the business talks rather than how its data is modelled. Everything
derivable is then derived from it — one keyword per category from its own
distinctive word (*Water Quality* → `quality`), a slugified governed tag, a
placeholder definition awaiting the steward.

- **5–9 categories.** Fewer and they stop discriminating; more and no one holds
  the whole set in their head.
- **Name them as the business names them**, not as the schema does. Categories
  that mirror source systems produce a glossary documenting the database rather
  than the business.
- **One steward per category** where you can manage it.

### Grow everything else from reviewed rows

`packgen` exports the reviewed state back into pack format, so the pack evolves
from real company data instead of remaining a guess:

| Learned | From |
| --- | --- |
| `table_category` / `table_terms` | the actual tables in the scan |
| `cat_keywords` | table-name tokens |
| `abbreviations` | aligned column tokens — `mbr_no` + "Member Number" → `mbr: Member` |
| `category_tags` / `tag_rules` / `terms` | the **approved** company layer only |
| `curated_seeds` | induced value patterns and profiled reference lists |

The **abbreviations** earn the most and are the least guessable: every
organisation shortens words its own way, and that mapping is exactly what makes
the next scan arrive with `mbr_no` already reading as *Member Number*.

Two rules keep this safe. Only **approved** vocabulary reaches the pack, so it
inherits the steward's judgement rather than the scanner's guesses. And merges
**surface conflicts side by side** instead of overwriting — a steward's recorded
decision beats the machine's newest opinion, while `curated_seeds` prefer the
fresher scan, because those were machine-derived evidence to begin with.

### Use industry standards as a check, never as a seed

AWWA for water, FIBO or BIAN for financial services, and their equivalents
elsewhere are useful — **after** your first pass, as a diff. Seeding from one
imports vocabulary the company does not actually use, and you end up governing
terms nobody says out loud, which is how a glossary becomes shelfware. Run the
domain, then compare against the standard to find the gaps that are genuinely
missing rather than merely absent.

### The sequence

    scaffold (packinit) -> scan -> review -> export pack -> commit
                                                  |
                                              next scan starts here

A company with no pack at all is a legitimate start: run **packless**, do one
full cycle, and the first export *is* your base pack — built entirely from
evidence someone has already approved.

---

## 6. Gotchas

Verified the hard way. Each of these looks like success while being wrong.

**Scanning is not profiling.** PDC's file scan defaults `withProfile: false` and
`headerExists: false`. Inherit those and your CSVs are catalogued with **no
columns** — or columns named `Column-0 … Column-N`, because the header row was
read as data. Every badge still reads OK. The app sets both explicitly from
1.36.7; if you scan from PDC's UI, tick them in Configure Process.

**Re-profiling is additive.** Run a scan again with different header settings and
PDC *adds* the new columns without retiring the old, leaving `Column-0`,
`asset_id`, `Column-1`, `asset_type` interleaved. **Recreate the data source**
rather than re-running over the top.

**Classification before the glossary is a catch-22.** PDC's Data Classification
assigns business terms — which do not exist until the glossary is built, from
the very profile the scan produces. Enabled on a first pass it can only mark
everything unclassified, leaving a pile to resolve by hand. PDC itself defaults
it off. Run it later, deliberately, and only over **unstructured** documents;
structured files never need it, because the app assigns their terms directly with
the profile evidence behind each one.

**PDC routes its internal API by hostname.** Reached on a bare IP the internal
endpoints 401 with a valid token while the public API answers fine — so an
object-store file scan fails and everything else succeeds. Use the vhost URL.

**A gateway is not an auth failure.** If PDC sits behind Cloudflare, a WAF or a
proxy, a browser login does not authenticate a non-browser client. The symptom
reads as "Keycloak auth failed"; the cause is an edge refusal. Check for the
gateway's fingerprint before touching realms or passwords.

**AI drafts language, never classification.** If you wire in a model, keep it off
sensitivity, PII category and tags. Non-reproducible classification is not
auditable, and an auditable classification is the entire point.

---

## 7. Anti-patterns

- **One enterprise glossary.** No owner, unbounded review, and every steward
  editing the same object.
- **Free-text tags.** The single fastest route to drift.
- **AI-authored definitions applied unreviewed.** The model is a drafting aid;
  the steward is accountable.
- **Classification run before terms exist.** See above.
- **Per-steward sensitivity judgement.** Sensitivity is a rule, not an opinion.
- **Treating the glossary as the deliverable.** It is the Registry that keeps
  everything else honest.

---

## 8. What this app does not solve

Stated plainly, so the plan accounts for it:

- **Concurrency.** Single-tenant state, no auth — several stewards working at
  once need separate instances.
- **Very large single sources.** Profiling scope is capped at 20,000 entities
  per source, reported rather than silently clipped. Row counts are irrelevant —
  a ten-million-row table is one entity.
- **Long-running scans.** The loader waits synchronously per source, sized for a
  demo rather than an overnight estate scan.
- **Organisational agreement.** No tool decides who owns "Customer". Settle that
  before Phase 2, or the glossaries will encode the argument.
