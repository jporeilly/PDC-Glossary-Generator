# Installation & Setup — Run the Glossary Generator on Your Own PDC Instance

*App version **1.7.1** · validated against **Pentaho Data Catalog 10.2.11**.*

This guide stands the **Glossary Generator** app up against *your* Pentaho Data
Catalog (PDC) instance — your data sources, your accounts, your network. The app
ships **generic** (no scenario vocabulary baked in); a scenario is installed from
its domain pack. This guide uses **Copper State Credit Union (CSCU)** — the
financial-services scenario — as the worked example throughout. The water-utility
scenario (Arizona Water Company) ships separately and completely under
`data_sources/AWC/` and `courseware/AWC/`.

> **What the app needs from PDC.** The app scans your sources locally and then drives
> PDC's **public API** to resolve terms, apply governance, and calculate Trust Score.
> It does **not** create the glossary over the API — you import the generated glossary
> through the PDC UI once, then the app attaches terms to columns. So a reachable PDC
> instance with public-API access and an account that can edit the glossary is the
> core requirement.

---

## 1. Prerequisites

**A host for the app.** A Linux/macOS/Windows machine or VM that has network line of
sight to three things: your PDC instance (HTTPS), each database you'll scan (e.g.
PostgreSQL on 5432), and any object store you'll scan (MinIO/S3 endpoint). For the CSCU
lab this is typically the same VM the catalog work is done from.

**One of:**
- **Docker + Docker Compose** — recommended; isolates dependencies. *(or)*
- **Python 3.9+** — for the local `run.sh` path.

**A running PDC instance** with the public API enabled and reachable over HTTPS. This
guide is validated against **PDC 10.2.11**; confirm your version's API segment (`v2`
vs `v3`) from its Swagger — entity/search shapes are stable across both, but the
`jobs` endpoints (Trust Score, Data Discovery) are richest in `v3`.

**A PDC account.** `admin` / `system_administrator` works for everything; a **Business
Steward** is enough for glossary edits and is the safer least-privilege choice. PDC
fronts identity with **Keycloak** (realm `pdc`, client `pdc-client`); the same account
works whether you authenticate through `/api/public/<v>/auth` or straight against
Keycloak.

**Source credentials.** Read-only database credentials for each source you'll scan
live (or a `CREATE TABLE` DDL file if you can't reach the database), and access
key/secret for any MinIO/S3 object store.

**Optional — Ollama** for one-sentence definition/purpose enrichment. It's the only
non-local, and entirely optional, step in the pipeline; everything else runs without
it. Budget ~4 GB for the default `llama3.2:3b` model (a GPU helps but CPU works).

---

## 2. Configure for your scenario (domain pack + company name)

The generic engine ships with no scenario vocabulary. Two settings tailor it without
touching code:

- **`GLOSSARY_COMPANY`** — the organization name woven into the LLM enrichment prompts
  (default: "your organization").
- **`GLOSSARY_DOMAIN_PACK`** — path to an optional JSON of scenario vocabulary
  (table→category, table→term, keyword rules, abbreviations, category definitions).
- **`credit_union.people.json`** — a companion **people/steward roster** for the CSCU
  scenario (`{"people": [...]}`: `display_name`, `email`, `name`, `roles`,
  `expertise`, `owns`, …). Import it to seed the stewards who own glossary terms.
- **`CLASSIFICATION_DOMAIN_PACK`** — path to an optional JSON that overlays
  **industry classification concepts** (term + tags + sensitivity + category +
  column-name detection) onto the generic PII/PCI/PHI core. This drives the
  registry that Policy Generator and the drift linter share. Example packs ship
  for both scenarios; copy and swap for any sector — no code changes.

For **CSCU**, the simplest install is the pack zip — unzip
`data_sources/CSCU/cscu-domain-pack.zip` into `glossary_generator/` (it drops
`domain_pack.json`, auto-loaded, plus the `people.json` roster), then set:

```
GLOSSARY_COMPANY="Copper State Credit Union"
```

The same pack can be referenced in place instead:

```
GLOSSARY_DOMAIN_PACK=../data_sources/CSCU/domain_pack/credit_union.example.json
```

The CSCU vocabulary covers Member Record, Loan Record, KYC Review Record, the
`mbr`/`apr`/`ach` abbreviations, and the pci/aml/lending tag rules. For a different
customer, copy the pack, edit the vocabulary, and point at your copy. See
`glossary_generator/domain_packs/README.md` for the key reference.

---

## 3. Install — Path A: Docker (recommended)

1. **Unzip the app** and `cd` into it.

2. **Set your scenario values.** Unzip the CSCU pack into the app folder first
   (see §2), then edit `docker-compose.yml` — uncomment and set `GLOSSARY_COMPANY`:

   ```yaml
   services:
     glossary:
       environment:
         GLOSSARY_COMPANY: "Copper State Credit Union"
         OLLAMA_URL: http://host.docker.internal:11434   # only if using Ollama
   ```

   (The unzipped `domain_pack.json` is copied into the image beside `suggester.py`
   and auto-loaded — no variable needed.)

3. **Build and run:**

   ```bash
   docker compose up --build
   ```

4. **Smoke test** (see §5). The app listens on port **5000**; state (people,
   connections, settings, glossaries) persists in the `glossary-data` volume mounted
   at `/data`, so it survives restarts.

> **Ollama in a container.** `localhost` inside the container is *not* your host. Keep
> Ollama on the host and point the app at `http://host.docker.internal:11434` (the
> compose file already adds the `host-gateway` mapping Linux needs). Or simply skip
> Ollama — enrichment is optional.

---

## 4. Install — Path B: Local (no Docker)

1. **Unzip** and `cd` into the app folder.

2. **Export your scenario values**, then launch with the bundled launcher (it creates
   a virtualenv, installs dependencies, and runs):

   ```bash
   export GLOSSARY_COMPANY="Copper State Credit Union"
   ./run.sh                 # http://127.0.0.1:5000
   ./run.sh --host 0.0.0.0  # bind all interfaces (e.g. on a lab VM)
   ./run.sh --port 8080     # choose a port
   ```

   (Scenario vocabulary: unzip `data_sources/CSCU/cscu-domain-pack.zip` into the
   app folder first, or export `GLOSSARY_DOMAIN_PACK` pointing at the pack file.)

   `run.sh` does a pre-flight check (Python version, free port, whether Ollama is
   reachable) before starting, and skips the dependency reinstall on repeat runs.

   Alternatively, run it by hand: `pip install -r requirements.txt` then
   `python app.py`.

---

## 5. First run — smoke test

Confirm the process is healthy and your configuration took effect:

```bash
curl http://localhost:5000/health     # {"status":"ok", "ollama":{...}}
curl http://localhost:5000/config     # effective paths + env (secrets masked)
```

`/health` returns 200 whenever the app is up; the `ollama` block reports the
enrichment backend, which is allowed to be offline. `/config` echoes the resolved
paths, the default model, and your `GLOSSARY_*` variables (anything secret-looking is
masked) — a quick way to confirm the domain pack and company name are wired in.

Then open **`http://<host>:5000`** in a browser.

---

## 6. Point it at your PDC instance

In the UI, open **Glossary → Data Elements (links)** to reveal the PDC panel.

1. **Base URL** — `https://<your-pdc-host>` (no trailing `/api/...`; the app adds the
   path). For self-signed lab certificates, the app exposes a *verify TLS* toggle —
   the underlying calls correspond to `curl -k`.
2. **Version** — `v2` for entities/search; `v3` for the richest jobs surface. Confirm
   against your instance's Swagger.
3. **Username / password → Get token.** The app authenticates, fills the token field,
   and shows the signed-in user, whether the account carries an admin role, and the
   expiry countdown. Verify the **admin ✓** (or your expected Business Steward) badge,
   and that the expiry covers your run. The token is held **in memory only**, never
   persisted; the app re-authenticates on a 401.

The call underneath, for reference:

```
POST https://<host>/api/public/v2/auth        (application/x-www-form-urlencoded)
  username=<user>  password=<pwd>  client_id=pdc-client
  grant_type=password  scope=openid profile email
200 -> { "data": { "accessToken": "eyJhbGciOi..." } }
```

---

## 7. Add your data sources

On the **Connections** screen, add one connection per source:

- **Database (live scan)** — PostgreSQL / MySQL / SQL Server, **read-only**. Reads
  schema, keys, and comments; sampling refines sensitivity and data quality. CSCU's
  source schema is `cscu_core` (your real schema name; the app no longer assumes
  it — set it on the connection).
- **Object store (MinIO/S3)** — browses a bucket over the S3 API; each file becomes a
  document term. **Use the host/VM IP for the endpoint, not `localhost`** — inside a
  container or from another host, `localhost` points at the wrong place.
- **DDL file** — parses a `CREATE TABLE` script when you can't reach the live
  database; same suggestions, no connection.

**Bulk-load the connections.** A starter CSV is downloadable from the app
(`/api/pdc/bulk-load/sample.csv`) or shipped as `datasources.sample.csv`. The CSCU
scenario also ships **`data_sources/CSCU/cscu-datasources.csv`** — the same format
pre-filled with the two CSCU lab connections, ready to load:

| kind | resourceName | reaches |
| --- | --- | --- |
| `postgres` | `CopperState_Core_Banking` | `192.168.1.200:5433` (shared `demo-postgres`, published on 5433) · db `cscu_core` · user `pdc_user` · schema `cscu_core` |
| `minio` | `CopperState_Documents` | `http://192.168.1.200:9000` · bucket `cscu-documents` · path `/` |

The credentials in it are the **lab values** (`catalog123!`, `minio_secret_123!`) — change
them for anything beyond the lab. Use the **VM/host IP** for the MinIO endpoint (not a
container name) so S3 path-style is forced, which MinIO requires. Each source still needs a
successful **Test Connection** before it comes online.

---

## 8. Before you run it — where it fits in PDC's order

The app **rides on PDC's data scan**: it confirms and overrides the tags and
sensitivity that **Data Identification** produces, then layers stewardship, term
links, and Trust Score on top. So complete PDC's scan **first**:

```
Ingest -> Profile -> Identify (+PII) -> import the glossary -> Reconcile term ids
  -> emit/deploy methods -> Resolve -> Apply -> Drift check -> Calculate Trust Score (last)
```

Three rules that matter on a real instance: **identify once** (re-running Data
Identification after the app clobbers the steward's overrides); **tags merge, sensitivity
overwrites** (the app reads-merges-writes the tag array so it never wipes auto-tags);
and **Trust Score last** (it rolls up everything else, so calculate it after all other
inputs are final). The Workshop and its supplement cover this in full.

> **Drift is a post-reconciliation view (1.6.0).** The drift linter compares a
> deployed Data Identification method's tags against the Registry.
> A dictionary method binds to a concept by `dictionaryTermId`, which only exists
> once the reviewed glossary has been imported into PDC and its minted ids read
> back and reconciled into the registry. So drift on dictionary methods can only
> be assessed **after** that reconcile step — before it, they read as UNKNOWN.
> Pattern methods bind by category and can be checked a step earlier.

> **Reversible review, dynamic per-group resolution, table terms protected (1.5.7).** In
> the Review & prune grid, duplicate names cluster under an inline header with a three-way
> **Merge / Disambiguate / Keep separate** control (the selected option is highlighted and
> reverts on a second click); detection is dynamic, so groups update as you rename inline
> or cull. *Keep High+Med conf*, *Merge duplicates*, *Auto-disambiguate* and **Reset all**
> are reversible toggles. **Table terms are never grouped, merged, culled, or deleted** —
> even if a table term shares a name with a real duplicate group. Resolutions survive a
> later LLM enrich, so applying the LLM after merging is safe.

---

## 9. Security & operations

- **Least privilege.** Prefer a **Business Steward** account over admin for glossary
  edits.
- **Secrets.** The app keeps the PDC token in memory for the run only and never writes
  it to disk. Don't commit real credentials; the sample CSV and compose file ship with
  `CHANGE_ME` placeholders.
- **Registry persistence (1.6.1).** The Registry saves beside the
  glossary as `registry.<glossary>.json` and reloads on open, so reconciled term
  ids and learned concepts survive restarts — required for drift detection to work
  across sessions. Back it up with the rest of `/data`.
- **State.** Under Docker, `/data` (the `glossary-data` volume) holds
  `people/connections/settings/glossaries` JSON. Back it up if you've curated a roster.
  Locally, those files sit beside the app unless you redirect them with the
  `GLOSSARY_PEOPLE` / `GLOSSARY_CONNECTIONS` / `GLOSSARY_SETTINGS` /
  `GLOSSARY_GLOSSARIES` variables.
- **TLS.** PDC is HTTPS; for self-signed lab certs use the app's verify-TLS toggle. In
  production, use a trusted certificate and leave verification on.
- **Dry-run on a new instance.** The first time you point the app at a PDC instance,
  treat the **Apply** dry-run as mandatory — preview every PATCH before a single write.

---

## 10. Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `/health` shows `ollama` offline | Expected if you're not using enrichment — it's optional. |
| `401` mid-run | Token expired; the app re-auths automatically, or click **Get token** again. |
| Object store unreachable | You used `localhost` — use the host/VM IP for the S3 endpoint. |
| `Route not found` (404) listing data sources | Expected — the public API has no "list all sources" call; the app discovers them via `entities/filter`. |
| Term **Resolve** finds nothing | The glossary hasn't been imported into PDC yet. The order is **import -> resolve -> apply**. |
| `400` on **Apply** | Usually an unexpected field on a term; the app whitelists term keys, so confirm you're on a current build. |
| `v2` jobs endpoint missing | Trust Score / Data Discovery live on `v3` — switch the version segment. |
| Suggestions use the wrong vocabulary | Check `GLOSSARY_DOMAIN_PACK` is set and the path is correct (`/config` will show it). |
| `500` on **enrich** — `AttributeError: 'NoneType' object has no attribute 'get'` (`llm.py` → `enrich_rows`) | A null/blank row reached the enricher — usually a table-level term arriving as an empty slot. Fixed in **1.5.6** (rows are guarded in `enrich_rows` and filtered at the `enrich()` boundary); upgrade, or apply the guard from `CHANGELOG.md`. |
| A table term disappears after **Keep High+Med conf** | Pre-1.5.6 behaviour. Table terms are now kept by default and exempt from the confidence cull — upgrade to 1.5.6. |

---

## 11. Upgrading & uninstalling

- **Upgrade (Docker):** stop the stack, replace the app files, `docker compose up
  --build`. The `glossary-data` volume persists your roster and connections across the
  rebuild.
- **Upgrade (local):** replace the files and re-run `run.sh`; it reinstalls
  dependencies only when `requirements.txt` changed.
- **Uninstall:** `docker compose down` (add `-v` to also delete the state volume), or
  just delete the app folder and its `.venv` for the local path.

---

*All Copper State Credit Union (CSCU) data in the training scenario is fictional and generated for training.*
