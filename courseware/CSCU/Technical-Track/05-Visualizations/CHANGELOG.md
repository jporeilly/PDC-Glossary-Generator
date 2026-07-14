# Changelog

## 1.3.0 — download & print dashboards

- Every dashboard can be downloaded as a .studio.json spec and printed / saved
  as PDF, from both the app dashboard view and the chat preview.
- Download (app): new GET /api/dashboards/<section>/<id>/download streams the
  spec as an attachment; the toolbar Download button uses it (with a client-side
  fallback). Download (chat): exports the in-memory spec.
- Print / PDF: a @media print stylesheet hides the app chrome and lays out only
  the active dashboard with a branded header, so the browser's Save-as-PDF
  produces a clean report — no server-side renderer or extra dependency.
- Tests: test_app.py now covers the download endpoint (attachment headers + 404).
- Docs: download & print documented in README, INSTALL, and DASHBOARDS.

## 1.2.1 — tests, code comments, docs

- Added tools/test_app.py: a functional suite (34 checks) covering section-aware
  recommend, the deterministic chat builder, the /api/chat + /api/recommend +
  /chat routes, refine, save, and generator validation. Runs on demo data.
- Detailed comments added to the chat route, the chat page's JavaScript (header
  + per-function), and surrounding code grown since the last comment pass.
- Docs: documented the in-app chat builder and section-aware suggestions in
  README, INSTALL (verify step now runs both suites), and DASHBOARDS.

## 1.2.0 — section-aware suggestions

- The in-app chat builder is now section-aware. Open /chat?section=<section>
  (or the "Build with AI" button inside any Analytics section) and the starter
  chips are that section's recommended dashboards, ranked by real catalog
  signals; new dashboards are pinned to the section.
- recommend() / GET /api/recommend / the MCP recommend_dashboards tool all take
  an optional category|section filter.
- Added evergreen per-section suggestions so every Analytics section (incl. User
  and Quality) always has real starters, with signal-driven ones ranked higher.
- Wired the main app's "Build with AI" button to the section-aware chat, and a
  "← Dashboards" link back from the builder.

## 1.1.0 — in-app AI dashboard builder (chat)

- New chat window in the web app at /chat: describe a dashboard, preview it, and
  click "Add to dashboards" to save it into the right section. Grounded on the
  real Query Library and validated before save.
- New POST /api/chat endpoint (conversational, role-gated) backed by the LLM
  generator, with a deterministic offline builder (app/chat_build.py) so the
  chat works end to end without a model.
- Shares the same generator + save path as the standard dashboards and the MCP
  server; the in-app chat and the MCP server are the built-in vs external chats.

## 1.0.7 — docs: connect the MCP server to a chat

- INSTALL §8 now walks through hooking the MCP server up to a chat end to end:
  Claude Desktop config file locations (macOS/Windows), pointing `command` at the
  venv Python that has the deps, restart, verifying the tools appear, and an
  example suggest-then-build conversation.
- Added notes for other MCP chat clients over HTTP and a quick tool test with the
  MCP Inspector (`mcp dev`).

## 1.0.6 — CPU option + hardware-aware model suggestion

- Added `tools/suggest_model.py`: detects OS, RAM, CPU cores, and any NVIDIA GPU,
  then recommends an Ollama model (GPU or CPU tier) and the right native run
  command for the platform.
- Documented a CPU-only path with a model-sizing table (3B/1.5B/0.5B) and tips
  (smaller model, OLLAMA_NUM_PARALLEL=1, keep JSON mode on).
- Added per-platform native run commands; Windows uses `waitress-serve`
  (gunicorn is POSIX-only). Noted in README, INSTALL, and requirements.

## 1.0.5 — read-only account default + native-first LLM config

- Examples now use a READ-ONLY PDC account (`pdc_user`) everywhere, reflecting
  best practice (the app only reads; least-privilege belongs in PDC).
- `LLM_BASE_URL` now defaults to the native `http://localhost:11434`. When the
  app runs via docker compose, the compose file auto-overrides it with
  `host.docker.internal` — so native runs work out of the box and Docker runs
  still reach a host Ollama, with no manual switching.
- Documented a first-class "run natively (no Docker)" path for the web app and
  the MCP server (venv + gunicorn / `python -m mcp_server.server`).
- Deployment guide now recommends native app + native Ollama on the Windows/GPU
  box as the lower-friction setup, Docker as the self-contained alternative.

## 1.0.4 — docs update

- Documented the corrected PDC auth flow (form-encoded /auth → data.accessToken)
  across INSTALL, ARCHITECTURE, and PDC-CONNECTOR, with a manual token curl and
  a read/connect test.
- Added Ollama connection guidance: which LLM_BASE_URL to use where, the
  OLLAMA_HOST=0.0.0.0 bind gotcha, and how to verify the connection.
- Expanded troubleshooting (Ollama bind, model-not-installed, PDC auth/version).
- Clarified the PDC_BEARER_TOKEN caveat (disables auto re-auth) in .env.example.

## 1.0.3 — PDC auth fix

- Corrected the PDC /auth call to match the documented contract: it now sends
  FORM-ENCODED credentials (client_id=pdc-client, grant_type=password,
  scope="openid profile email") instead of JSON, and reads the JWT from
  data.accessToken (was data.token). Required for authenticating to a real PDC
  instance.

## 1.0.2 — port change (final)

- Web app default host port is **8660** (was briefly 8090, which also clashes
  with Pentaho's AWS/K8s config port-forward; original default 8080 is Tomcat).
  8660 clears the Pentaho/Tomcat and PDC port ranges. Fully overridable via
  `INSIGHTS_PORT`; the container always listens on 8660 internally. MCP server
  stays on 8765. See the Ports table in docs/GUIDE.md (Install & set up) for the reserved list.

## 1.0.1 — port change

- Initial move off 8080 (superseded by 1.0.2).

## 1.0.0 — first complete release

Initial end-to-end build of Catalog Insights: AI-assisted reporting and
dashboards for Pentaho Data Catalog, plus an MCP server, delivered as a single
containerised project. Runs today in demo mode; ready to point at a live PDC
10.2.11 instance.

### Web app
- Flask backend, read-only PDC client (auth, search, facets, entities,
  data-sources) with automatic re-auth on 401.
- Dashboard spec schema (`.studio.json`) as the single contract.
- LLM dashboard generator: ground → generate → validate → repair loop.
- 12 built-in standard dashboards across 6 sections (also enablement examples).
- Self-contained design mock UI (`ui/mock/index.html`).
- API: `/health`, `/config`, `/api/{facets,search,snapshot,recommend,generate}`,
  `/api/dashboards` — each role-gated.

### MCP server
- 9 tools + 3 resources over the same engine: list_data_sources,
  catalog_snapshot, search_assets, recommend_dashboards, list_standard_dashboards,
  get_query_catalog, generate_dashboard, validate_dashboard, save_dashboard.
- Recommends dashboards from live scan/connection state, then builds them.
- stdio (Claude Desktop) and HTTP transports.

### Security
- Shared auth/roles/audit (`app/security.py`) enforced by both front doors.
- Roles viewer < steward < admin (mirroring PDC tiers); only write is gated.
- Auth modes: none | apikey | jwt (shared secret or JWKS, role-claim mapping).
- Structured JSON audit log of every privileged action.
- Test suite: `python tools/test_security.py`.

### LLM
- Pluggable providers: local (Ollama), commercial (Anthropic/OpenAI), disabled.
- Local default for governance data privacy; constrained JSON output.

### Ops & docs
- Docker + docker-compose (web + optional `--profile mcp`).
- Demo mode (`INSIGHTS_DEMO=true`) for running without a live PDC.
- README, INSTALL guide, 8 docs, 5 rendered architecture/flow diagrams.
- Detailed inline code comments throughout.

### Known limitations
- Dashboard panels are demo-backed until wired to live PDC reads.
- Trust-score *recalculation* via the public API is version-dependent — verify
  on the target instance.
- MCP HTTP OAuth metadata is wired but should be validated against your IdP.
