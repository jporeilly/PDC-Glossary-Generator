# Glossary Generator — Tags & the Domain Pack

*AWC courseware · companion to the Dictionary and Glossary review steps*

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
box the generic rules cover common domains (billing, usage/metering, water-quality/
compliance, contact, location, identifiers). Anything the rules don't recognise falls
back to just the **category tag**.

For AWC's object store that meant most document folders — GIS, SCADA, inspections,
correspondence, hydrology — showed only `document`, because no rule named them. That's a
**vocabulary coverage gap**, not a bug: the tagging works, the vocabulary was just thin
for those domains.

## 3. The domain pack fixes it

`domain_pack.json` (at the app root) extends the governed vocabulary for your domain. The
shipped **water-utility** pack adds pre-approved rules so AWC document/operational domains
get real tags:

| Folder / name matches | Tags |
|---|---|
| GIS, geospatial, parcel, easement | `gis · spatial · asset` |
| SCADA, telemetry, RTU/PLC, sensor | `scada · operational · telemetry` |
| inspect, survey, field report | `inspection · field-ops` |
| correspondence, letter, notice, memo | `correspondence · records` |
| hydrology, watershed, aquifer, reservoir | `hydrology · water-quality` |
| maintenance, work order, repair, main break | `maintenance · operational` |
| outage, incident, spill, overflow | `incident · operational` |
| permit, licence, certificate | `permit · compliance` |
| plan, design, drawing, as-built | `engineering · asset` |

Tags introduced by the pack are **company-layer and pre-approved** — governed, so they
count as allow-listed vocabulary rather than pending drift. The rules apply to database
columns too, not just documents.

### Pack format

```json
{
  "domain": "water_utility",
  "category_tags":  { "Records & Documents": ["document", "records"] },
  "extra_tags":     ["gis", "scada", "telemetry", "..."],
  "tag_rules": [
    { "pattern": "\\bgis\\b|geospatial|parcel", "tags": ["gis", "spatial", "asset"] }
  ]
}
```

- `tag_rules` — `pattern` is a regex matched (case-insensitive) against name+term+category;
  `tags` are added when it matches. These are the main lever.
- `extra_tags` — tag names to add to the allow-list even if no rule references them yet.
- `category_tags` — the tag(s) every term in a category receives.
- Override the file location with `GLOSSARY_DOMAIN_PACK`.

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
|---|---|
| Make a domain's terms tag meaningfully | Add a `tag_rules` entry to `domain_pack.json` → Reseed → Suggest tags |
| Add an allowed tag with no rule yet | Add it to `extra_tags` → Reseed |
| Change a category's default tag | Edit `category_tags` → Reseed → Suggest tags |
| Approve a scan-grown tag | Dictionary page → review pending → approve |
| Understand why a tag is bare | The name didn't match any rule — add one to the pack |
