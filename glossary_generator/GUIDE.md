# Glossary Generator — Guide

A local web app that scans data sources, profiles the data, suggests Business
Glossary terms, lets you review and govern them, and exports import-ready JSONL
for **Pentaho Data Catalog → Business Glossary → Import**. One glossary can span
several sources (a database plus a document store).

---

## 1. Install & run

```bash
cd glossary_generator
python3 -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
python app.py                                            # http://127.0.0.1:5000
```

Override host/port: `PORT=5050 HOST=0.0.0.0 python app.py`. `run.sh` does venv +
install + run in one step. On Windows use `run.ps1` (or the `run.bat` wrapper) instead. PostgreSQL, DDL and MinIO/S3 scanning work out of the
box; other DB engines are opt-in (see **Settings → Drivers**). LLM enrichment is
optional and needs a local **Ollama** (`ollama serve`).

The interface is a four-section dashboard: **Home · Connections · Glossary ·
Govern · Settings**.

---

## 2. Home

Landing page: the four-step workflow (Connect → Review &amp; prune → Govern &amp;
generate → Apply to PDC), best-practice notes, and your **Saved glossaries** (load
or delete any saved workspace — see §7).

---

## 3. Connections

Each source is its own **saved connection** (persisted to `connections.json`).

Types: **Database (live scan)**, **Document store (MinIO/S3)**, **DDL file (path)**.

Per database connection card:

| Action | What it does |
|---|---|
| **Scan** | Suggest terms (replaces the current list) — start a glossary here |
| **Add to glossary** | Scan and **merge** into the current list — span multiple sources |
| **Discover** | Full column profiling (see §3.1) |
| **Seed data** | Populate empty tables with realistic sample data (see §8) |
| **Test** | Verify the connection |
| **Edit / Delete** | Manage the saved connection |

> **Multi-source glossaries.** A PDC glossary is source-agnostic — terms are
> business concepts. Scan your database, then **Add to glossary** from the MinIO
> bucket; a *Sources* chip shows the split (e.g. `Database 110 · Document store 21`).

**Profile data** toggle (on a DB connection): samples real column values on scan
to set sensitivity, PII and CDE from the data — not just the column name.

### 3.1 Data discovery (compare with PDC)

**Discover** runs real profiling SQL and renders a column-profiling panel:

- **Summary**: tables, columns, total rows, PII columns, CDE columns, empty tables.
- **Per-table** (expandable): per-column **completeness %**, **distinct**,
  **uniqueness %**, **sensitivity**, **PII**, **CDE**, **detected type**
  (email / phone / zip / date / decimal / identifier / enum), PK/FK, and examples.

These are the same dimensions PDC's profiler captures (completeness, cardinality,
patterns, sensitivity), so you can line the two up side by side.

### 3.2 Harvest from PDC (no direct DB access)

Instead of connecting straight to the database, you can build the glossary from
what **PDC has already cataloged**. The **Harvest from PDC** card on Connections:

1. **List data sources** — the public API has no "list all data sources" call
   (the data-sources endpoint is retrieve-by-id only), so the picker reads the
   harvestable roots (schemas / sources) from `POST /entities/filter` — the same
   endpoint Resolve and Apply use. Authenticate with a username/password or paste
   a **bearer token**; every PDC call is sent with `Authorization: Bearer <token>`.
2. **Harvest selected** — calls `POST /entities/filter` for the chosen source's
   `COLUMN` entities and reads PDC's real metadata (`metadata.column.dataType` /
   `isPrimaryKey` / `isNullable`, `attributes.info.description`). PDC's description
   **becomes the definition** (High confidence), and any column PDC **already
   governs** (`attributes.features.sensitivity` / `trustScore`,
   `attributes.businessTerms[]`) is flagged with an **"in PDC"** badge so you don't
   overwrite existing work.

This is the most PDC-native path: the catalog is the source of truth and the
generator reads from it. Endpoints live in `pdc_api.py`
(`list_data_sources`, `harvest_from_catalog`) and `app.py`
(`/api/pdc/data-sources`, `/api/pdc/harvest`); the "Under the hood — reading
PDC's catalog" panel shows the exact calls.

> **PDC base URL = the server root** (e.g. `https://192.168.1.200`). The app adds
> `/keycloak/realms/<realm>/…` and `/api/public/v2/…` itself. Pasting the full
> Keycloak realm URL (`…/keycloak/realms/pdc`) is tolerated — `pdc_api.clean_base`
> strips it (and recovers the realm) so the request isn't built with a doubled path.

### 3.3 Bulk-load data sources into PDC (no glossary work — a setup step)

Where 3.2 *reads* from a catalog PDC already scanned, this *writes* the sources in
the first place. It is the **Connect + Ingest** step that precedes profiling,
identification and the glossary — handy when you are standing up a lab or a
customer environment and need many sources registered at once.

Paste or choose a **CSV** (one row per source) and the panel, for each row:

1. **creates** the data source — `POST /api/public/<v>/data-sources`
2. runs a **test-connection** job and waits for it — `POST /jobs/execute/test-connection`, then polls `GET /jobs/{id}/status`
3. triggers a **metadata ingest** — `POST /jobs/execute/metadata/ingest`, scoped to the new record's `resourceId`

Progress streams back a row at a time (create / test / job / ingest), exactly like
the summary table the original PowerShell script printed.

**CSV columns.** `kind` selects the connector — `postgres`, `minio`/`s3`, or
`azure_blob` — and only the relevant columns are read:

| kind | required columns |
|------|------------------|
| `postgres` | `resourceName, host, port, databaseName, userName, password` (`schemaNames` optional) |
| `minio` / `s3` | `resourceName, endpoint, accessKeyID, secretAccessKey, container` (`path`, `region` optional) |
| `azure_blob` | `resourceName, accountName, azureSharedKey, container` |

Optional everywhere: `description, fqdnId, affinityId, configMethod, path,
includePatterns, excludePatterns`. Download a starter file from the panel link
(`/api/pdc/bulk-load/sample.csv`) or use `datasources.sample.csv` in the app
folder — it has two sample sources (a `public`-schema database and a
`documents` MinIO store) with `CHANGE_ME` where the secrets go.

> **Dry run** builds and shows the (redacted) request bodies without contacting
> PDC — use it to check a CSV before sending. Secrets are transmitted to PDC only;
> the app never writes them to disk or logs. Creating data sources needs an
> account with the rights to do so (e.g. Data Storage Administrator).

The same engine is callable headless: `POST /api/pdc/bulk-load` with
`{base_url, username/password or token, csv, options:{test,ingest,wait}, dry_run}`.

---

## 4. Glossary

Review and refine the suggested terms, then generate.

- **Columns**: Keep · Category · Term · Definition · **Purpose** · Sensitivity
  (colour-coded: HIGH red, MEDIUM orange, LOW teal) · CDE · Tags · Confidence · Source.
- **Filters**: text, category, sensitivity, confidence, **tags**, PII-only, kept-only.
- **Keep controls**: master tri-state, shift-select ranges, *Keep High+Med conf*.
- **Open glossary for review…** — load an existing export straight into the grid.
- **Enhance from glossary…** — overlay an export's real definitions/purpose/tags/
  sensitivity onto matched terms (and add any the scan missed).
- **Enrich with LLM** — rewrite definitions with the local model.
- **Save glossary / Load saved…** — see §7.
- **Generate JSONL** — exports the kept terms. This now lives on the **Govern**
  page (its **Generate &amp; apply** card), not the Glossary page, because
  stewardship and ratings are written into the JSONL at generate time — so you
  always Govern before you Generate. The Glossary page hands off to Govern with a
  **Set stewardship →** button. The glossary need not exist in PDC yet — UUIDs come
  from the Keycloak roster.

**Confidence** is an evidence signal, not a quality score:
**High** = DB comment, key, or a profiling hit; **Medium** = PII pattern or
low-cardinality; **Low** = templated from the name. Raise it by profiling, adding
DB column comments, or enhancing against an existing glossary.

**How the Term name is derived (and cryptic columns).** Each column becomes one
candidate Term by humanising the column name — underscores to spaces, Title Case —
*plus* an abbreviation-expansion map so cryptic names still read well:
`cust_acct_no` → "Customer Account Number", `txn_dt` → "Transaction Date",
`inv_amt` → "Invoice Amount" (covers generic forms like no/num→Number,
acct→Account, amt→Amount, qty→Quantity, dob→Date of Birth). A domain pack can add
scenario abbreviations (e.g. ws→Water System). Anything not in the map falls
through to plain Title Case, so a truly opaque name (`x1`, `col_007`) still yields a
weak name you can edit. Expansions are only suggestions — every Term cell is editable.

**LLM-suggested rename.** When you **Enrich with LLM**, the model also proposes a
clearer Term name for columns it judges cryptic (and repeats the name unchanged when
it already reads well). It is shown as a clickable **&#8594; chip** next to the Term —
clicking it adopts the name; it is **never** written over your Term silently. The
enrich summary reports how many names were suggested. The model only rewrites the
*definition* and *purpose* automatically; the *name* always waits for your click.

**CDE (Critical Data Element)** is auto-inferred from keys, sensitivity, financial/
identity PII, profiled identifiers, and critical/compliance/safety terms (account
number, licence, permit, meter, balance, compliance, lead/pH/turbidity, capacity…).
Always reviewable per row by the steward.

---

## 5. Govern

- **User roster** — add/remove people, set each person's **Expertise** (free text
  + keywords), Save roster (persists to `people.json`). People bind to PDC accounts
  by **UUID** (per-instance, from Keycloak).
- **Fetch users from Keycloak** — pull the roster live from Keycloak's Admin API
  (base URL + realm + admin user/password, or a bearer token).
- **Stewardship defaults** — business steward, owner, custodian, status, rating,
  reviewed-date, stakeholders — applied to every kept term (and category), with a
  **per-category steward** override (pre-filled from MinIO owner tags / `owns` map).
- **Auto-assign all slots** — keyword-matches each person's role + expertise (+ a
  small domain-synonym map) against each category's label, term and column names,
  then fills the steward / owner / custodian slots. Role badges gate each slot
  (Business Steward → steward, Data Steward → owner, Data-Storage Admin → custodian);
  with the fallback toggle on, an empty role pool falls back to expertise-only.
  Deterministic and offline. Each pick shows a confidence + the matched terms, and
  slots you set by hand are **locked** so they're never overwritten ("Clear auto"
  unlocks the auto-filled ones). Manual edits always win.
- **Auto (scan DQ) rating** — on the global and per-category Rating dropdowns,
  derives 1–5 stars from the scanned Data Quality (mean of the per-column DQ scores):
  ≥97 % → 5, ≥90 → 4, ≥80 → 3, ≥70 → 2, else 1. When the global rating is Auto,
  every category is rated on **its own** mean DQ. Resolved to a concrete integer at
  export, so the JSONL and Trust-Score rollup are unchanged.

These flow into the generated JSONL (`info.owner/custodian/businessSteward`,
`stakeholders`, `features.rating`, `reviewedAt`, `status`).

---

## 6. Settings

- **Local LLM (Ollama)** — model picker, GPU offload (Auto/Max/Off), pull model
  with progress.
- **Database drivers** — per-engine Python driver status + install command, and the
  PDC JDBC-jar hint.
- **Appearance** — theme (Light / Teal / Dark, applied live) and the help banner.

Settings persist to `settings.json`.

---

## 7. Saving & loading glossaries

**Save glossary** (Glossary page) stores a named **workspace** — its terms,
governance settings and the data-discovery profile — to `glossaries.json`.
Reload it anytime from **Home → Saved glossaries** or the **Load saved…** dropdown;
the grid, summary, discovery panel and governance selections are all restored.

---

## 8. Seeding sample data

Value-based profiling needs representative rows. `seed_sample.py` is a
schema-introspecting generator: it reads `information_schema`, orders tables by
foreign-key dependencies, skips auto-increment keys, references real parent PKs for
FK columns, and generates realistic values by column name/type (emails, phones,
`ACC########` account numbers, names, addresses, ZIPs, status/type enums, amounts,
dates).

In the app: the **Seed data** button on a database connection (fills empty tables,
then re-runs Discover). From the CLI:

```bash
python seed_sample.py --host localhost --port 5433 --db your_db \
                      --user db_user --password 'CHANGE_ME' --rows 200
# --all also tops up non-empty tables
```

---

## 9. Adapting to your scenario

The engine is scenario-agnostic. Two knobs tailor it without code changes:

- **`GLOSSARY_COMPANY`** — the organization name woven into the LLM prompts
  (defaults to "your organization").
- **Domain pack** — an optional JSON of scenario vocabulary (table→category,
  table→term, keyword rules, abbreviations, category definitions). Point at it with
  `GLOSSARY_DOMAIN_PACK=path/to/pack.json`, or drop `domain_pack.json` beside
  `suggester.py`. See `domain_packs/` — `water_utility.example.json` reproduces the
  original Arizona Water vocabulary as a worked example.

Connections, buckets, and the glossary name are all set in the app UI or via the
`GLOSSARY_*` environment variables (see the table in §1).

---

## 10. Import into PDC

Terms export as **Draft** (proposals until a Business Steward accepts them). The
import **replaces the whole glossary** — to update in place, open the existing
export for review so the `_id`s are reused. In PDC: **Glossary → Actions → Import**.

Before importing, the **Check PDC** button next to the glossary name (Govern page)
calls `POST /api/pdc/glossary-exists`, which searches PDC for a glossary of that
name. It warns if an exact match already exists (so you update rather than
duplicate) or if a similar one is present.

**Apply to PDC** (the resolve → merge → PATCH path) writes business-term links and
features back onto existing column entities. Before each PATCH, every business term
is reduced to the keys PDC's schema accepts — `id`, `glossaryId`, `name`,
`sourceName`, `sourceType`, `confidenceScore`. App-internal fields (e.g. the
`glossary` display name) are dropped; sending them makes PDC reject the PATCH with a
`400`. Existing links on the column are preserved — new terms are unioned in,
never replaced.

---

## 11. Working in the UI — wayfinding & feedback

A few aids make the pipeline easier to follow:

- **Workflow stepper.** A thin strip at the top of every working page tracks
  *Connect → Review → Govern → Apply*, one stage per nav page (Connections,
  Glossary, Govern, Apply to PDC). Generate isn't a separate stage — it's an
  action on the Govern page. Each stage lights up as it's
  satisfied (a connection exists, terms are scanned, a steward is set, JSONL is
  generated, an apply has run) and is clickable to jump straight there. It's hidden
  on Home and Settings.
- **Apply progress bar.** Apply to PDC streams its progress live — the bar fills
  column by column ("Resolving & patching column 14 of 52 · …"), then shows the
  table-rating roll-up and Trust Score phases. It falls back to a single request if
  streaming isn't available. The underlying write logic is unchanged; the stream
  only reports progress.
- **How terms are built (Glossary page).** A "How terms are defined & built"
  panel explains where each field comes from — Term (humanised column name),
  Definition (DB comment → key text → template), Purpose, Sensitivity (name
  patterns, overridden by value profiling), CDE, Tags, and Confidence (an evidence
  signal). All of it is derived locally by `suggester.py` at scan time — no extra
  API calls — with `View source` to read the exact logic.
- **Plain-language explainers.** Several pages carry a short explainer card:
  *Connection types & what each button does* (Connections), *How terms are
  defined & built* (Glossary), *How stewardship & auto-assign work* (Govern), and
  *Why generate & import before you resolve* (Resolve Term IDs). The exposed
  source (`/api/source` / View source) is also commented for learners — the
  term-building heuristics in `suggester.py` in particular.
- **Under the hood — on every stage.** Each working page has a collapsible
  *Under the hood* panel showing the exact calls it runs, built from your own
  settings: **SQL** (information_schema + pg_catalog) on Connections, the **S3**
  ListObjectsV2/GetObject calls on Files, the local `/api/generate` plus the
  **Ollama** enrichment call on Glossary, the **Keycloak** admin token + users
  fetch on Govern, and the full **PDC public-API** choreography on Apply. Secrets
  are masked; every call has a Copy button. Each panel also lists the **scripts**
  that run it with a **View source** button — the real Python is served read-only
  from a whitelist (`/api/source`), so a learner can read exactly what executes.
  Nothing with secrets (people.json, settings) is ever exposed.
- **Why import before resolve.** The Apply page opens with a short explainer: a
  term link binds to its glossary only when it carries both `id` and `glossaryId`,
  and those exist only after the term exists in PDC — i.e. after you import the
  generated JSONL. Hence the forced order Govern → Generate → Import → Resolve →
  Apply.
- **Roster filter & validation.** The Govern roster has a filter box (name, email,
  expertise) for large Keycloak pulls. The add-person row validates UUID
  (8-4-4-4-12 hex) and email format before *Add* is enabled, and **Enter** submits.
- **Unsaved-roster nudge.** Editing expertise, adding, or removing a person marks
  the roster dirty (an "unsaved" dot by *User roster*); the browser also warns
  before you navigate away. *Save roster* clears it.
- **Copy JSONL.** The Generate output has a *Copy JSONL* button next to the
  download link.

---

## 12. Runtime files (git-ignored)

`connections.json`, `settings.json`, `glossaries.json`, `people.json` hold your
saved state. They're local to the app folder.
