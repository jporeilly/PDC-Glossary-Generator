# Desktop shell

Wraps the Glossary Generator into a Windows `.exe` installer, the way the
Pentaho Content Manager courses are packaged.

The app itself is unchanged. This is a Tauri window that starts the existing
FastAPI server on a free port and points a webview at it, so the desktop and
browser builds cannot drift apart — there is one UI, served the same way in both.

## Layout

```
desktop/
  dist/index.html          splash: polls the backend, then navigates to it
  scripts/fetch-python.ps1 vendors a self-contained Python + the requirements
  scripts/stage-app.ps1    copies the app + built SPA into vendor/app
  scripts/check-environment.ps1  post-install check: what is missing, and the fix
  src-tauri/src/main.rs    window, paths, the two invoke commands
  src-tauri/src/server.rs  free port, spawn uvicorn, job object
```

## Build

```powershell
cd frontend; npm ci; npm run build     # the SPA must exist first
cd ..\desktop; npm install
npm run tauri:build                    # fetch:python + stage:app run automatically
```

The installer lands in `src-tauri/target/release/bundle/nsis/`.

`npm run tauri:dev` runs against the checkout instead — no staging, no vendored
runtime, `python` from PATH. Edit Python, reload the window, done.

## Three decisions worth knowing

**A vendored Python, not PyInstaller.** The dependency set includes `oracledb`,
`psycopg2-binary`, `pymssql`, `boto3` and three provider SDKs — dynamic-import
heavy code that PyInstaller's static analysis gets wrong, and gets wrong at
*runtime*, on the attendee's machine. A vendored tree is just files: what was
tested is what ships. It costs roughly 150 MB.

**A free port, chosen at launch.** 5000 is popular and a second instance must
not turn into "the app won't start".

**A kill-on-close job object.** Closing the window stops the server directly,
but a crash or a Task Manager kill would otherwise leak `uvicorn` — still
holding the port and the state files, so the *next* launch fails for a reason
the user cannot see. The job object covers that; see `server.rs`.

## Where state goes

`GLOSSARY_STATE_DIR` is set explicitly to the per-user data directory
(`%APPDATA%\com.pentaho.pdc-glossary`), so the packaged build never depends on
probing whether Program Files is writable. `glossary_generator/paths.py` has the
full resolution order.

Nothing local ships: `stage-app.ps1` excludes `.env`, `glossaries.json`,
`connections.json`, `settings.json`, `people.json` and the rest, then re-scans
the staged tree and fails the build if any of them slipped through. A developer's
`connections.json` would carry lab hostnames into a customer install; `.env`
would carry provider API keys.

## Not done yet

- **Icons are placeholders** (`src-tauri/icons/`) — generated, not designed.
- **No components page.** PCM's `nsis/installer.nsi` has Full/Minimal/Custom
  with `/NoOllama`-style switches; this build installs everything.

## What a fresh install starts with, and what you supply

The installed app starts **empty on purpose** — `stage-app.ps1` ships no
glossary, no connections, no settings and no `.env`, because a developer's copy
of those would carry lab hostnames and API keys to every attendee.

Two files decide what the app knows about a company. Both keep their usual
names, and both live in the **state directory** (`%APPDATA%\com.pentaho.pdc-glossary`
in a packaged install — the environment check prints the exact path, and so does
`/config`):

| File | What it is | How it gets there |
| --- | --- | --- |
| `domain_pack.json` | the scenario vocabulary: table categories, terms, abbreviations, category keywords | copy one in, point `GLOSSARY_DOMAIN_PACK` at it, or let the app write it from a reviewed scan (*Draft pack → apply*) |
| `people.json` | the steward roster | seeded once from `GLOSSARY_PEOPLE_SEED` if empty, then edited in the app |

A pack in the state directory **wins over the starter that shipped with the
install** — that is what makes "bring your own pack" work, and it is why writes
never target the install directory (Program Files is read-only, so *Draft pack →
apply* would otherwise report success on a file it never replaced).

The installer ships `domain_packs/*.example.json` as starting points, and
`packinit.py` scaffolds a thin pack for a new company.

`datasources.csv` is **not** in this list. Nothing reads it from disk: the bulk
loader serves a sample for download and takes the filled-in copy back through
the UI, so it is an upload, not configuration.

## Checking a machine

```powershell
npm run check                       # or: scripts\check-environment.ps1 -Json
```

Run it after installing. It **reports rather than blocks**: only WebView2 and a
usable Python are `FAIL`, because without them the window does not open. Ollama
absent is a `WARN` (the app also drives Anthropic, OpenAI/Azure and Gemini), and
PDC unreachable is a `WARN` (the vhost is normally configured later, and scan,
review and govern all work without it). Treating those as hard failures would
teach people to ignore the output.

Two results worth knowing when you read it:

- **"up, but NO model pulled"** — Ollama answering with an empty model list is
  the trap. The app connects, then every generate call fails, which reads as
  "the AI is broken" rather than "nothing is installed".
- **A bare IP for PDC** — flagged before the probe runs, because PDC routes by
  vhost and answers `401` on *every* path. That looks like bad credentials and
  sends people to reset passwords that were never wrong.

A self-signed certificate is reported as exactly that, not as unreachable — the
check retries with validation off purely to tell "the server is not there" from
"the server is there and its cert is untrusted", which are different problems
with different fixes.

`-Json` emits machine-readable results and nothing else on stdout, for
provisioning logs. Exit code is non-zero only when something genuinely blocks.
