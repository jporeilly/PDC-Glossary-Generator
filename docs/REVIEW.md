# Glossary Generator — code review, PDC v3 compatibility & regression

This is the result of a full pass over the codebase: PDC API version compatibility,
the scenario bundle, roster persistence, module health, regression tests,
and refactoring notes. It also lists everything changed in this clean build.

## 1. PDC API v3 compatibility — full audit (re-verified 2026-07-13, app 1.8.7)

Every request the app can send was audited against the OFFICIAL PDC 11 v3
OpenAPI specs (docs.pentaho.com → PDC API Documentation v3), and the shapes are
now enforced by a committed, repeatable test — since 1.9.0 the pytest port
**`pytest -q tests/test_v3_shapes.py`** (strict `additionalProperties: false`
whitelists for the entity PATCH, filter keys, bulk-job names/payloads, cursor
placement).

| Area | App call | v3 verdict |
|---|---|---|
| Auth | Keycloak token grant; legacy `POST /auth` fallback | ✅ both documented for v3 |
| Search | `POST /search {searchTerm, perPage}` | ✅ identical schema v1→v3 |
| Entity read | `GET /entities/{id}` | ✅ |
| Entity update | `PATCH /entities/{id}` — `features.{sensitivity, rating.value, qualityScore, isCriticalDataElement, isLineageVerified}`, `businessTerms[]` (whitelisted keys), `info.description` (1.8.6), `extended.*` (1.8.2 PK/FK) | ✅ every key in the strict v3 schema |
| Entity filter | `POST /entities/filter?extended&size=500` + cursor, filters `names/types/fqdns` | ✅ — **fixed in 1.8.7**: the pagination cursor was sent in the body; v2/v3 define it as a query param (never bit on lab-size catalogs, would loop page 1 on >500 entities) |
| Profiling info | `POST /entities/filter/profiling-info` | ✅ (same cursor fix) |
| Jobs | v3: `POST /jobs/execute/bulk` with named jobs (`CALCULATE_TRUST_SCORE`, `DATA_DISCOVERY` [scope+configs], `TEST_CONNECTION`, `METADATA_INGEST`) | ✅ all four names + payloads match the bulk `oneOf` schema — **improved in 1.8.7**: v3 now goes straight to bulk (the per-job paths do not exist in v3; the old adapter burned a guaranteed 404 first). v3 bulk returns successes/failures, no job id → status polling is skipped there (watch PDC's Workers page) |
| Data sources (bulk loader) | `POST /data-sources`, `DELETE /data-sources/{id}`, `POST /data-sources/filter {filters:{resourceNames}}` | ✅ v3 schema identical (wildcards supported) |

**Defaults:** the Apply/harvest version selectors now default to **v3** (PDC 11's
native version) for new installs; a saved v2 selection is preserved and v2
remains fully supported. The earlier user-guide contradiction about Calculate
Trust Score being "not available in public API's" is resolved in the v3 docs —
`CALCULATE_TRUST_SCORE` is an official bulk job.

**v3-only opportunities noted for later:** `POST /entities/by-ids` (+ profiling
variant) would batch our per-name resolution; the `DATA_IDENTIFICATION` bulk
job accepts `dictionaryIds`/`dataPatternIds` — the natural trigger for the
Policy Generator to run its imported methods programmatically.

> **Key metadata note (1.8.2, still true in v3):** the built-in *Is Primary
> Key / Is Foreign Key* column properties live under `metadata.column.*`,
> which is harvest-owned — the PATCH schema accepts only the `attributes`
> block, so the app records its own PK/FK detection in
> `attributes.extended.{isPrimaryKey, isForeignKey, references}` and in the
> Registry (`concepts[].keys`).

## 2. Scenario bundle — applied?

**Not by default.** The engine ships generic. `suggester._load_domain_pack()` reads
`$GLOSSARY_DOMAIN_PACK` (or a `domain_pack.json` beside the module); absent, the
table->category map and curated terms are empty and categories are derived generically.

A scenario is installed from its pack zip — for CSCU, unzip
`data_sources/CSCU/cscu-domain-pack.zip` into `glossary_generator/` (drops
`domain_pack.json` + the `people.json` roster: Elena Ramirez / Marcus Webb /
Nadia Flores / Tom Callahan, with `expertise` seeded), or set in `.env`:

    GLOSSARY_DOMAIN_PACK=../data_sources/CSCU/domain_pack/credit_union.example.json

Verified: with the pack loaded, `members -> Member`, `loans -> "Loan Record"`, etc.

## 3. Roster persistence to people.json

Confirmed end to end. **Save roster** → `POST /api/people` → `_save_people()` →
`_write_json(people.json, {"people":[...]})`; `_load_people()` reads it back. Round-trip
tested. Two related points:

- The **Suggest expertise** button fills the roster and marks it *unsaved* on purpose
  — you review, then click **Save roster** to persist (same pattern as the Keycloak
  fetch's "save to roster"). It does not silently write to disk.
- Hardened in this build: `_write_json` is now **atomic** (temp file + `os.replace`),
  so a crash mid-write can no longer truncate `people.json` / `settings.json`.

## 4. Module health & refactoring

No bugs found; 14/14 regression checks pass (all modules import; people.json
round-trips; suggester scan, `table_term_rows`, `suggest_expertise`, and the new
`/api/suggest-expertise` route all work; full route table present). Frontend JS parses
clean (no syntax errors), no Jinja tags in the template.

Refactoring is **optional, not required**. Candidates, in priority order:
1. **PDC v3 job adapter** (see §1) — the only change with functional impact, and only
   if you must run against v3.
2. **app.py endpoint boilerplate** — ~12 endpoints repeat
   `version = body.get("version") or "v2"` plus token/reauth setup. A small
   `@with_pdc(...)` decorator or helper would remove the repetition. Cosmetic.
3. **`llm.status()` caching** — it probes Ollama (3s timeout) on every call, including
   inside `suggest_expertise`. A short TTL cache would speed up offline use. Minor.
4. **File size** — `pdc_api.py` (~1.8k lines) and `suggester.py` (~2.4k) are large but
   cohesive; splitting (auth / entities / jobs) would aid navigation, not correctness.

### Framework decision — Flask vs FastAPI (evaluated 2026-07-10, deferred)

Considered migrating the backend to FastAPI and decided **against it for this
app in its current shape**. Rationale:

- **No benefit at this scale.** FastAPI's wins are async concurrency, Pydantic
  request validation, and auto-generated OpenAPI docs. This is a single-user
  lab tool whose slow paths are database scans and Ollama inference — no
  framework accelerates those — and whose API has one consumer: its own page.
- **Real cost.** Dozens of Flask routes (including streaming endpoints, file
  uploads and CSV exports) rewritten to ASGI/Pydantic idioms; gunicorn →
  uvicorn across `run.sh` / `run.ps1` / Docker; full re-validation against
  PDC 11.0.0 (which 1.7.x was carefully validated against); and a
  documentation/courseware sweep — Workshop 1 even shows the
  `* Serving Flask app 'app'` launcher output that screenshots will capture.

**Revisit trigger:** if the Registry becomes a *service* — the Policy
Generator (or other tooling) consuming the app's API over HTTP as a
documented contract rather than reading the registry file — migrate as part
of that redesign, when re-validation is unavoidable anyway. Until then, if
API documentation is wanted (e.g. for the Technical Track), serve a
hand-maintained OpenAPI spec from the existing Flask app instead — a
fraction of the cost, most of the benefit.

## 5. Changes in this build

- **New: LLM expertise generation.** `llm.suggest_expertise()` + `_expertise_llm`
  (Ollama JSON keywords) + `_expertise_fallback` (deterministic, offline, strips the
  person's own name and role words). Endpoint `POST /api/suggest-expertise`. UI:
  "Suggest expertise (LLM)" button + "overwrite existing" toggle in the roster card.
- **New: "Set up stewardship"** one-click macro — fills missing expertise, then
  auto-assigns steward/owner/custodian across every category.
- **New: `.env` support** — dependency-free loader in `app.py`, runs before local
  imports so `GLOSSARY_DOMAIN_PACK` (scenario bundle), `PORT`, `OLLAMA_URL` etc. all apply.
  See `.env.example`.
- **Hardening:** atomic `_write_json`.
- **UX fixes:** roster add-form field overlap removed; Expertise header text
  clarified; default Rating = Auto (DQ); Reviewed date defaults to today + 3 months;
  "Apply to categories" shrunk to a compact checkbox; Keycloak fetch nudges to run
  Suggest expertise when expertise is blank.
- **Removed:** the stale root `index.html` duplicate (the served template is
  `templates/index.html`).

## 6. Install

    cp .env.example .env        # optional; uncomment scenario pack / set OLLAMA_URL etc.
    ./run.sh                    # http://127.0.0.1:5000  (--port <n> to change)

Ollama is optional — without it, expertise generation falls back to offline rules and
LLM enrichment is skipped. This app is separate from Catalog Insights/PDC-Insights
(port 8660); keep their ports distinct.
