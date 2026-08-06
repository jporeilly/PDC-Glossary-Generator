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
  scripts/seed-company.ps1 first-run: company name + categories -> domain_pack.json
  scripts/lib/common.ps1   shared state-dir / interpreter resolution
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

## The installer

`nsis/installer.nsi` adds a components page over Tauri's default template.

| Install type | What runs |
| --- | --- |
| **Full** | app, company seed, Ollama, environment check |
| **Minimal (app only)** | app only |
| **Custom** | tick individually |

The bundled Python runtime shows as a ticked, greyed-out entry. It has no
payload of its own — it's laid down by the core section regardless — but the
page is where someone decides what this thing needs, and "you don't have to
install Python" is the most useful thing it can say there.

Each optional step delegates to a script in `$INSTDIR\provisioning\`, all of
which are re-runnable afterwards and are safe no-ops when their work is done.
Nothing there can fail the installation: a skipped step leaves a working app.

Silent installs:

```powershell
setup.exe /S /Company="Acme Energy" /Categories="Customer,Billing,Metering"
setup.exe /S /NoSeed /NoOllama /NoCheck
```

`/Company=` is what makes the seed work unattended. Without it in a silent
install the seed is **skipped rather than prompting**, because a prompt in an
unattended job hangs it forever.

## Testing on a clean laptop

Expect these, none of which are bugs:

- **SmartScreen will block it.** The installer is unsigned, so Windows shows
  "Windows protected your PC" → *More info* → *Run anyway*. Every attendee will
  hit this until the binary is code-signed; that's the one thing standing
  between this and a hands-off rollout.
- **Admin rights, always.** `installMode` is `perMachine`, so it installs to
  `C:\Program Files\PDC Glossary Generator` and always prompts for elevation.
  A standard user cannot install it.

  It was `both` until 1.32.6, which sounded more flexible and wasn't: the
  template's default-path chain has no `both` branch, so `$INSTDIR` was never
  set and MultiUser's per-user default won - the app landed somewhere nobody
  expected. `perMachine` names the path outright.

  One consequence worth knowing on a **shared** machine: the seed step runs as
  the installing admin, so it writes that account's `%APPDATA%`. A second user
  logging in gets an unseeded state directory and needs
  `provisioning\seed-company.ps1` run once as themselves.
- **Network is needed for two things only** — the WebView2 bootstrapper (if the
  machine lacks the runtime) and the Ollama model pull. The app and its Python
  are entirely inside the installer.
- **The Ollama step is the long one.** It pulls a single model sized to that
  machine — several GB. Untick it for a quick test, or run
  `provisioning\install-ollama.ps1` later.

Then verify:

```powershell
& "$env:ProgramFiles\PDC Glossary Generator\provisioning\check-environment.ps1"
```

On a clean machine expect `WebView2 OK`, `Python (vendored) OK`, `Vendored
dependencies OK`, a state directory under `%APPDATA%\com.pentaho.pdc-glossary`,
and `PDC` skipped until you give it a server. If `Vendored dependencies` fails,
the install is incomplete — that check imports `oracledb` and `psycopg2` rather
than just confirming `python.exe` exists.

## Not done yet

- **Icons are placeholders** (`src-tauri/icons/`) — generated, not designed.
- **The installer is unsigned** — see SmartScreen above.

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
| `domain_pack.json` | the scenario vocabulary: table categories, terms, abbreviations, category keywords | `npm run seed` (below), or let the app write it from a reviewed scan (*Draft pack → apply*) |
| `people.json` | the steward roster | export it from Keycloak (below), or seed from `GLOSSARY_PEOPLE_SEED` and edit in the app |

### Seeding a company

```powershell
npm run seed        # asks for the company name and its categories
```

Since 1.29 the engine asserts **no categories of its own**, so a fresh install
classifies nothing until a pack tells it how. `seed-company.ps1` asks for the two
things only the customer can answer, scaffolds a thin pack with `packinit`, and
writes it to the state directory along with the company name in `settings.json`.

The pack is thin on purpose — category keywords, governed tags, placeholder
definitions; table mappings and terms left empty. Those come from evidence:

    seed -> scan -> review -> Export domain pack

Re-running refuses to overwrite an existing pack without `-Force`, because by
then it has usually been grown from a scan and is worth far more than the
skeleton. `-Company` and `-Categories` make it non-interactive for unattended
installs.

### Seeding the roster from Keycloak

```powershell
.\load-pdc-users.ps1 -ExportPeople .\people.json -SkipTlsCheck
```

(in the PDC-Scenarios repo — `make users-people` prints the same command.)

Read-only, over **HTTPS**: it uses Keycloak's Admin REST API, so no SSH and no
container access. It prompts for the Keycloak admin password, because that API
is bearer-token only.

The account **UUID** is the point. Names, emails and roles can be typed by hand;
the UUID cannot, and without it a glossary term cannot be bound to a real
steward — the app keeps such a person visible but will not offer them as a
binding. Persona detail that Keycloak knows nothing about (`stakeholder_role`,
`community`, `owns`, `expertise`) is merged forward by email, so refreshing the
roster does not discard curation.

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
