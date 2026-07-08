# Glossary Generator — Tags & the Domain Pack

*Copper State Credit Union (CSCU) courseware · companion to the Dictionary and Glossary review steps*

Explains where the **Suggested_Tags** on the review grid come from, why some rows show
only a generic tag, and how to enrich the vocabulary with a **domain pack** — the
supported way to make tags meaningful without introducing drift.

---

## 1. Tags are governed, not guessed

The tags on each term come from a **controlled vocabulary** (the Dictionary), not from the
LLM. They're built deterministically from:

- the term/column **name, term text, and category**, matched against the dictionary's
  **rules** (`pattern → tags`);
- the **category tag** for the term's category;
- structural signals — PII type, HIGH sensitivity → `maskable`, CDE → `CDE`, key →
  `identifier`.

Everything stays inside the dictionary's allow-list, so tags can't drift into free-text.
**Enrich with LLM does not change tags** — it improves definitions and purposes. If you
want richer tags, you enrich the *vocabulary*, not run the LLM.

## 2. Why some rows show only "document" (or a bare category tag)

A term only gets a domain tag if **a rule matches its name/term/category**. Out of the
box the generic rules cover common domains (billing, contact, location, identifiers,
compliance). Anything the rules don't recognise falls back to just the **category tag**.

For CSCU's document store that would mean most folders — loan applications, statements,
ACH batches, KYC files, SAR summaries — showed only `document`, because no generic rule
names them. That's a **vocabulary coverage gap**, not a bug: the tagging works, the
vocabulary was just thin for financial-services domains.

## 3. The domain pack fixes it

The CSCU pack (`credit_union.example.json`, installed as `domain_pack.json` beside
`suggester.py`) extends the governed vocabulary with pre-approved financial rules so
CSCU's database columns and document folders get real tags:

| Column / folder / name matches | Tags |
| --- | --- |
| card, PAN, CVV, MCC, expiry | `pci · card · payments` |
| ACH, routing, wire, SWIFT, IBAN | `payments · ach` |
| KYC, AML, SAR, suspicious, OFAC, risk rating | `compliance · aml` |
| loan, APR, collateral, principal, maturity | `lending · credit` |
| ledger, journal, GL, debit/credit amounts | `ledger` |
| fraud, dispute, chargeback, reversal | `fraud · compliance` |
| statement | `statement · records` |
| correspondence, letter, notice, memo | `correspondence · records` |
| dividend, APY, interest rate, rate sheet | `rates` |
| member, joint owner, beneficiary | `member` |
| deposit, savings, checking, share draft, certificate | `deposit` |

Tags introduced by the pack are **company-layer and pre-approved** — governed, so they
count as allow-listed vocabulary rather than pending drift. The rules apply to database
columns too, not just documents: `cards.cvv_cd` picks up `pci`, `ach_payments.ach_rte_no`
picks up `payments · ach`, and so on.

### Pack format

```json
{
  "domain": "credit_union",
  "category_tags":  { "Compliance & Risk": ["compliance", "aml"] },
  "extra_tags":     ["pci", "ach", "kyc", "..."],
  "tag_rules": [
    { "pattern": "\\bcard\\b|\\bpan\\b|\\bcvv\\b", "tags": ["pci", "card", "payments"] }
  ]
}
```

- `tag_rules` — `pattern` is a regex matched (case-insensitive) against name+term+category;
  `tags` are added when it matches. These are the main lever.
- `extra_tags` — tag names to add to the allow-list even if no rule references them yet.
- `category_tags` — the tag(s) every term in a category receives.
- Override the file location with `GLOSSARY_DOMAIN_PACK`.

The full CSCU pack (both the tag half and the categorization half — table→category,
table→term, abbreviations like `mbr`→Member and `apr`→APR) ships in
`data_sources/CSCU/domain_pack/` with a ready-to-install zip.

## 4. Applying pack changes — the two-step refresh

The dictionary is seeded once and then persisted (`tag_dictionary.json`), so editing the
pack does **not** retroactively change a running catalog. After adding or changing
`domain_pack.json`:

1. **Dictionary page → Reseed** — rebuilds the vocabulary from the generic baseline + the
   pack. (This discards un-approved scan-grown additions; approved/steward items are the
   governed set.)
2. **Glossary grid → Suggest tags** — re-derives `Suggested_Tags` for the shown rows from
   the refreshed vocabulary.

Then the rows pick up the new domain tags.

## 5. Governance — how new tags stay controlled

- Pack rules and their tags are **company-layer, pre-approved** → immediately governed.
- Tags/terms **grown from scans** enter as **pending** and only govern the Registry once a
  **steward approves** them on the Dictionary page. So the vocabulary grows under review,
  never silently.
- The governed set is what flows into the Registry and (via the Policy Generator) into
  PDC Data Identification — keeping tags, terms and classification drawn from one
  allow-list. Extending the domain pack is the clean way to widen that set.

---

### Quick reference

| Want to… | Do this |
| --- | --- |
| Make a domain's terms tag meaningfully | Add a `tag_rules` entry to `domain_pack.json` → Reseed → Suggest tags |
| Add an allowed tag with no rule yet | Add it to `extra_tags` → Reseed |
| Change a category's default tag | Edit `category_tags` → Reseed → Suggest tags |
| Approve a scan-grown tag | Dictionary page → review pending → approve |
| Understand why a tag is bare | The name didn't match any rule — add one to the pack |

*All Copper State Credit Union data is fictional and generated for training.*
