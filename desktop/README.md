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
- **No environment check.** Ollama and a reachable PDC are the two things worth
  reporting on after install, as warnings rather than hard failures — the app
  works against hosted LLM providers, and the PDC vhost is usually configured
  afterwards.
