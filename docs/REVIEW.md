# Glossary Generator — code review, PDC v3 compatibility & regression

This is the result of a full pass over the codebase: PDC API version compatibility,
the scenario bundle, roster persistence, module health, regression tests,
and refactoring notes. It also lists everything changed in this clean build.

## 1. PDC API v3 compatibility

The PDC client (`pdc_api.py`) takes the API version as a parameter (`v1`/`v2`/`v3`)
and builds `/api/public/<version>/...` paths, and the main Apply-to-PDC UI exposes a
v1/v2/v3 selector — so requests path-route to whatever version you pick. The question
is whether the request/response *shapes* still match. Checked against the live PDC API
reference (v1, v2, v3):

| Area | Code uses | v2 | v3 | Verdict |
|---|---|---|---|---|
| Auth (Keycloak primary; legacy `/auth`) | bearer token | same | same (`/v3/auth`) | Compatible |
| `entities/filter` | cursor pagination, `size=500`, `extended=true`, reads `cursorInfo.cursor` | cursor + `cursorInfo` | identical, plus new `tags`/`terms`/`termIds` filters | Compatible |
| `entities/{id}` PATCH | `attributes.features.{sensitivity, rating.value, isCriticalDataElement, isLineageVerified}`, `attributes.businessTerms[]` | same schema | same schema | Compatible |
| `search` / resolve-terms | search by name | same | same | Compatible |
| Trust score | `POST /jobs/execute/calculate-trust-score {"scope":[ids]}` then poll `/jobs/{id}/status` | individual endpoint exists | **changed** — v3 moves job execution to a bulk pattern `POST /jobs/execute/bulk` with `{name:"CALCULATE_TRUST_SCORE", type:"START", payload:{scope}}` | **v3 risk** |
| Trigger profiling / discovery | `POST /jobs/execute/data-discovery` | individual endpoint | likely bulk (`DATA_DISCOVERY` / `DATA_PROFILE` named jobs) | **v3 risk** |
| Connection test / metadata ingest (harvest) | `/jobs/execute/test-connection`, `/jobs/execute/metadata/ingest` | individual endpoints | likely bulk (`TEST_CONNECTION` / `METADATA_INGEST` named jobs) | **v3 risk** |

**Bottom line:** the read/write core (auth, filter, PATCH, search) is fully v2- and
v3-compatible. The **job-execution** calls (Calculate Trust Score, trigger
profiling/discovery, and harvest's test-connection/ingest) follow the v1/v2 style of
one endpoint per job; **v3 reorganised these into a single bulk endpoint**, so under a
literal `v3` selection those specific features may 404. **Recommendation: keep the
connector on `v2` on a 10.2.11 instance (fully compatible).** A v3 job adapter — POST
the bulk array and read the per-job result — is the one change needed for end-to-end
v3, and is isolated to ~4 helpers in `pdc_api.py`.

> Doc note: the PDC *user guide* states Calculate Trust Score "is not available in
> public API's", which contradicts the API *reference* (the `calculate-trust-score`
> job is documented for v1/v2). The app was built against the v2 endpoint; verify on
> your instance.

## 2. Scenario bundle — applied?

**Not by default.** The engine ships generic. `suggester._load_domain_pack()` reads
`$GLOSSARY_DOMAIN_PACK` (or a `domain_pack.json` beside the module); absent, the
table->category map and curated terms are empty and categories are derived generically.

A scenario is installed from its pack zip — for CSCU, unzip
`data_sources/CSCU/cscu-domain-pack.zip` into `glossary_generator/` (drops
`domain_pack.json` + the `people.json` roster: Elena Ramirez / Marcus Webb /
Priya Nair / Tom Callahan, with `expertise` seeded), or set in `.env`:

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
