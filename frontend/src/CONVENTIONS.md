# Frontend conventions — contract for page agents

The React port of the Glossary Generator UI. **PDC-Policy/frontend is the
template kit** — same theme, same components, same code style; the two apps
must look identical. Read a Policy page (e.g. `LoadPage.jsx`) before writing
one here.

## Code style (match Policy exactly)

- Function components, hooks only. No classes, no react-router — the App shell
  routes with a `page` string in `useState`; pages receive `onNavigate(pageId)`.
- No semicolons, single quotes, 2-space indent, `.jsx` extensions in imports.
- No new dependencies. React 18.3 + Vite only.

## Theme & markup

- `src/index.css` is Policy's stylesheet copied wholesale + the marked
  canonical suite shell (copied from PDC-Insights) and a "glossary-only"
  section at the bottom. **Never restyle above the
  marker** — extend only below it, and only with the existing CSS variables
  (`--surface-1/2`, `--text-*`, `--accent`, `--status-*`, `--gridline`,
  `--border`, `--radius`).
- Reuse the existing classes: `.card` (+`<header><h2>`), `.tiles`/`.tile`,
  `.form-grid`, `.actions`, `button.primary/.ghost`, `.badge.good/.warning/
  .serious/.neutral/.accent`, `.table-scroll > table`, `.error`, `.loading`,
  `.hint-line`, `.summary`, `.progress-track/.progress-bar`, `.modal-*`.
- Status colors always pair with an icon or label — never color alone.
- Themes: `midnight | slate | pentaho | light`, set as
  `document.documentElement.dataset.theme`, persisted in
  `localStorage['mc-theme']` (shared key with Policy). `ThemeSelect` owns this.

## Shared components (`src/components/`) — verbatim copies from Policy

- `DocModal.jsx` — fetches a markdown URL into a modal.
- `Markdown.jsx` — minimal renderer (headings, bullets, bold, code, links).
- `ThemeSelect.jsx` — the theme dropdown.
Do not fork these; if one needs a change, change it in Policy first.

## API access (`src/api.js`) — never call fetch() directly in a page

- `apiGet(path)`, `apiPost(path, body)`, `apiDelete(path)`.
- Non-JSON responses: `apiText(path)` (GET → string) and `apiBlob(path, body?)`
  (GET, or POST when a body is given → Blob) — same error contract as the
  JSON wrappers; use them instead of raw `fetch()` for downloads.
- **Error contract:** every backend error is `{"error": msg}` (never FastAPI's
  `detail`) — the wrapper throws `Error(msg)`, including on 200-with-`{error}`
  legacy routes. Catch and render into `<div className="error">`.
- **Long work = jobs, not streams:** `runJob(name, body, onTick)` wraps
  `POST /api/jobs/{name}` → poll `GET /api/jobs/{id}`. Job names:
  `resolve-terms`, `apply-to-pdc`, `bulk-load`, `pull-model`. The job dict is
  `{status: running|done|error, done, total, phase, detail, events[], result}`.
  Drive `.progress-bar` from `done/total` (pull-model events also carry
  `percent`). The old SSE/NDJSON twins (`/api/*-stream`, `/api/pull-model`,
  `/api/pdc/bulk-load`) stay for the legacy UI — use `streamNdjson()` only if
  a job twin truly doesn't exist.

## Global app state (`src/state.js`) — the loaded glossary lives here

Module-level store (like the old UI's global `ROWS`/`CUR_GLOSS`), no contexts.

- Read: `const ws = useWorkspace()` → `{id, name, glossaryName, rows,
  discovery, governance, dirty, saving, savedAt, saveError, pdcSession}`.
- Mutate: `setRows(rows)`, `patchRow(index, patch)`, `setGlossaryMeta({name,
  glossaryName})`, `setDiscovery(d)`, `setGovernance(g)`,
  `clearWorkspace()`. Every mutation marks
  dirty and schedules the save — **never POST /api/glossaries yourself**.
- Load a saved glossary: `openGlossary(id)`.
- Autosave: mutations debounce a `save()` (2 s) and a 30 s interval sweeps up
  the rest. Saves only run once the workspace has an `id` or a `name` — a
  scratch grid is never persisted silently; call `setGlossaryMeta({name})`
  (or `save()` after naming) to turn autosave on.
- Page-local UI state (filters, form fields, panels) stays in the page.
  Cross-page durable prefs go through `GET/POST /api/settings` (partial
  bodies merge server-side).
- `governance` is the Govern page's `buildGovernance()` output (kept current
  by that page); it persists in the save body under the legacy `governance`
  key and the Apply page's Generate includes it in `POST /api/generate`.
- `pdcSession` is **session-only** PDC connectivity —
  `{connected, base, user, at}` or `null` — never persisted in the glossary
  save body and never marks the workspace dirty. Set it via
  `setPdcSession({base, user})` (or `setPdcSession(null)` to clear) **only
  after a round-trip that genuinely proved connectivity**: the Apply page's
  `POST /api/pdc-token` success (cleared again on auth failure) and the
  Connect page's authenticated `/api/pdc/*` reads do this. `App.jsx` renders
  it as the sidebar footer's "PDC ·" status dot — don't add per-page copies.

## Rows shape

A row is one candidate term (one scanned column) with TitleCase keys, e.g.
`Category, Term, Definition, Purpose, Sensitivity (HIGH|MEDIUM|LOW), CDE,
Tags, Confidence (High|Medium|Low), Source, Keep (Y/N), PII_Category,
LLM_Enriched…` — pass rows through untouched; the backend owns the schema.

## App shell (owned by `App.jsx` — don't duplicate in pages)

- Sidebar (canonical suite shell, copied from PDC-Insights): brand block
  (rounded mark + two-line name + version pill — release notes + stale-build
  flag via `/api/whatsnew`), sectioned nav with inline SVG icons, footer with
  LLM status dot (`/api/llm-status`, 60 s poll) and the theme select.
- Stepper: Connect → Review → Govern → Apply on those four pages only.
- Pages export a single default component: `({ onNavigate, version }) => JSX`,
  returning fragments of `<section className="card">` blocks (no outer
  wrapper div needed).
