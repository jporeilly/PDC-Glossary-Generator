# PDC Reset Day — the runbook

One folder, one document, top to bottom. Every step is a copy-paste command
run from `C:\Projects\PDC-Glossary\remote` (unless the step says otherwise).
Field-proven 2026-08-14; commands re-proven and PowerShell-corrected
2026-08-19. Deep background lives in
[PDC-REMOTE-RESET.md](../docs/PDC-REMOTE-RESET.md); this page is the doing.

---

## Quick card — the whole reset, copy-paste order

Every command is PowerShell-native (no bash `&&` — PS 5.1 rejects it) and
carries the corrections the 2026-08-19 reset taught. Details per step in
the numbered sections below.

```powershell
# 0 · Preflight + reset (from C:\Projects\PDC-Glossary\remote)
Set-Location C:\Projects\PDC-Glossary\remote
.\pdc-remote.ps1 doctor
.\pdc-remote.ps1 reset          # type 'reset' to confirm; 8-20 min

# 1 · Licence (curl.exe, NOT curl — PS aliases bare curl to Invoke-WebRequest)
# FRESH-RESET GOTCHA (field-caught 2026-08-19): the rebuilt pdc realm's
# `admin` cannot log in as admin/admin — the stock password policy
# (length(8), specialChars, digits, notUsername) forbids that password,
# so the realm import leaves the user without a usable credential.
# The rescue is the MASTER realm, whose bootstrap IS admin/admin
# (KEYCLOAK_PASSWORD in vendor/.env.default): relax the pdc policy,
# then set admin/admin — the documented lab experience:
#   $mt = (Invoke-RestMethod -Method Post -Uri 'https://pentaho.io/keycloak/realms/master/protocol/openid-connect/token' -Body @{grant_type='password';client_id='admin-cli';username='admin';password='admin'}).access_token
#   Invoke-RestMethod -Method Put -Uri 'https://pentaho.io/keycloak/admin/realms/pdc' -Headers @{Authorization="Bearer $mt"} -ContentType 'application/json' -Body '{"passwordPolicy":"length(5)"}'
#   $u  = (Invoke-RestMethod -Uri 'https://pentaho.io/keycloak/admin/realms/pdc/users?username=admin&exact=true' -Headers @{Authorization="Bearer $mt"})[0].id
#   Invoke-RestMethod -Method Put -Uri "https://pentaho.io/keycloak/admin/realms/pdc/users/$u/reset-password" -Headers @{Authorization="Bearer $mt"} -ContentType 'application/json' -Body '{"type":"password","value":"admin","temporary":false}'
# (The cast step later re-tightens the policy to length(7); passwords
# already set stay valid — policy checks happen at set time.)
.\pdc-remote.ps1 token          # username admin, password admin
# …or straight to the CLIPBOARD for Swagger's Authorize button (paste the
# token bare, no "Bearer" prefix; ~5 min expiry):
$tok = (curl.exe -sk -X POST 'https://pentaho.io/keycloak/realms/pdc/protocol/openid-connect/token' `
  -H 'Content-Type: application/x-www-form-urlencoded' `
  -d 'grant_type=password&client_id=pdc-client&username=admin&password=admin' | ConvertFrom-Json).access_token
Set-Clipboard -Value $tok
curl.exe -k -X POST 'https://pentaho.io/api/v2/licensing/uploadLicense' `
  -H "Authorization: Bearer $(Get-Content .state\token.jwt)" `
  -F 'deviceId=pdc-demo' `
  -F 'fileData=@C:\path\to\licence.bin;type=application/octet-stream'
# sanity: log in at https://pentaho.io as `admin` (username, not an email)

# 2 · Cast users — PolicyValue length(7): the cast password is `azwater`
#     (7 chars); plain -FixPolicy would set length(8) and reject it
Set-Location C:\Projects\PDC-Scenarios
.\load-pdc-users.ps1 -Scenario AWC -BaseUrl https://pentaho.io `
  -SkipTlsCheck -FixPolicy -PolicyValue 'length(7)' -Password azwater

# 3 · Safe list (verify; run without -VerifyOnly only if absent)
Set-Location C:\Projects\PDC-Glossary\remote
.\reseed-domains.ps1 -VerifyOnly

# 4 · Health (302/401 = routed + unauthenticated = fine; 404 = bad)
.\pdc-remote.ps1 health

# 5 · Scale the estate (module form, from glossary_generator, OWNER account
#     — the loader's pdc_user is read-only; owner password is in the
#     demo-postgres container env on the VM, see §6)
Set-Location C:\Projects\PDC-Glossary\glossary_generator
python -m sources.seed_sample --host 192.168.1.200 --port 5433 `
  --db awc_operations --schema awc_operations `
  --user demo_admin --password '<owner-pass>' --rows 1000 --all

# 6 · App: install latest, Settings -> Factory reset if reusing a machine,
#     install the domain pack (skip for a true day-zero walk), then
#     Connect -> Bulk load -> Harvest -> the walk.
```

> Budget for the whole day-zero cycle: **~30-45 minutes**, most of it the
> reset's 8-20 minute rebuild.

---

## 0 · Preflight (2 min)

```powershell
.\pdc-remote.ps1 doctor
```

16 checks — tooling, key, network, VM, deployment. All green before anything
else. If SSH is dead, `.\pdc-remote.ps1 enable-ssh` prints the console fix.

## 1 · Reset (8-20 min)

```powershell
.\pdc-remote.ps1 reset
```

Type `reset` to confirm. Snapshots `conf/.env` + inventory to `logs/` first,
then: stop, remove `pdc-*` containers and `pdc_*` volumes, OpenSearch
truststore surgery, and the second `pdc.sh up` everyone forgets. It verifies
independently and writes checkpoints, so an interrupted run resumes.

**Destroyed:** catalog, data sources, glossaries, Keycloak `pdc`-realm users,
licence, email-domain safe list.
**Survives:** everything under `/opt/pentaho/pdc-docker-deployment` on disk
(including our `vendor/.env.default` domain seed), the lab stack (5433/9000),
this workstation's key and config.

## 2 · Licence (3 min)

```powershell
.\pdc-remote.ps1 token
```

Then upload the offline licence (confirm the exact endpoint in Swagger once
logged in — see PDC-REMOTE-RESET.md §7; the path `pdc-reset.sh` advertises is
not routed on this build):

```powershell
curl -k -X POST 'https://pentaho.io/api/v2/licensing/uploadLicense' -H "Authorization: Bearer $(cat .state/token.jwt)" -F 'deviceId=pdc-demo' -F 'fileData=@<path-to-licence.bin>;type=application/octet-stream'
```

Sanity: log in at `https://pentaho.io` as **`admin`** (the username, not an
email).

## 3 · Cast users into Keycloak (2 min)

Run from `C:\Projects\PDC-Scenarios`:

```powershell
cd C:\Projects\PDC-Scenarios
.\load-pdc-users.ps1 -Scenario AWC -BaseUrl https://pentaho.io -SkipTlsCheck -FixPolicy
```

`-FixPolicy` relaxes the stock realm password policy (lab passwords like
`arizonawater` fail it otherwise). Idempotent — re-running keeps users and
re-applies passwords/roles. Verify one login with the snippet checkpoint 6
prints.

## 4 · Email-domain safe list (1 min)

The domains live at `provider_conf.emailDomains` on the css-auth-proxy
provider record, seeded from `EMAIL_DOMAINS` in the VM's
`vendor/.env.default` — which now includes `azwater.gov`, so a fresh reset
seeds it automatically. **Verify, don't assume** (back in this folder):

```powershell
cd C:\Projects\PDC-Glossary\remote
.\reseed-domains.ps1 -VerifyOnly
```

If it reports absent (or you are adding a NEW domain: edit `EMAIL_DOMAINS`
in the VM's `vendor/.env.default` first):

```powershell
.\reseed-domains.ps1
```

Do NOT chase the vendor doc's `PUT {id, emailDomains}` — it is
accepted-and-ignored on PDC 11. The reseed uses the init's own
DELETE+POST-full-config sequence and verifies at the real JSON path.

## 5 · Health (1 min)

```powershell
.\pdc-remote.ps1 health
```

Remember the codes: **404 = route missing** (bad), **302/401 = routed, just
unauthenticated** (fine).

## 6 · Repopulate — from the app (the PDC-first flow)

**BEFORE any wipe** (the two artifacts that carry the steward's work across
a reset): **Settings → State snapshot** (download the zip), and
**Dictionary → Export domain pack → Apply → commit** to the scenario repo.
The pack is what makes the fresh walk arrive already speaking the company's
language; skipping the export restarts Friday from raw physical names.

Everything else comes through the Glossary Generator, which is the point of
the architecture:

0. **Scale the estate data** (once per reset, BEFORE bulk load): the demo
   tables at 10 rows starve profiling — single-valued vocabularies force
   curated seeds, and PDC's `columnCardinality > 5` rule guard can silence
   authored rules. Seed at real size:

   ```powershell
   # PowerShell, from the repo. NOTE: module invocation from glossary_generator
   # (the script needs its `sources` package), and the OWNER account — the
   # loader CSV's pdc_user is read-only by design. The owner password lives in
   # the demo-postgres container env on the VM:
   #   ssh pdc@192.168.1.200 "docker inspect demo-postgres --format
   #     '{{range .Config.Env}}{{println .}}{{end}}' | grep POSTGRES_PASSWORD"
   Set-Location C:\Projects\PDC-Glossary\glossary_generator
   python -m sources.seed_sample --host 192.168.1.200 --port 5433 `
       --db awc_operations --schema awc_operations `
       --user demo_admin --password '<owner-pass>' --rows 1000 --all
   ```

   The document store stays small on purpose — it is the demo's honest
   sparse corner (the curated-seed workflow needs something to show).
1. **Settings → ⚠ Factory reset** in the app (if you want app-zero too),
   close, relaunch — then **install the domain pack** before the first scan
   (the flywheel: evidence-seeded from minute one).
2. **Connect → Bulk load** — one CSV registers every source in PDC, ingests
   and runs the analysis pass (profiling for databases, discovery for object
   stores).
3. **Harvest** both sources — structure, governance AND the value evidence
   PDC profiled. No app-side source credentials needed. (Re-harvesting later
   after ANOTHER data improvement: tick **Refresh value evidence** on the
   Harvest card so the richer profile overwrites the old evidence — steward
   fields and Auto/Mapping-only flips are never touched.)
4. Walk: Review → Dictionary → Govern → Apply → Report.

Two empty systems to a governed estate, one credential, ~an hour including
the AI passes.

---

## If something fights back

| Symptom | Fix |
|---|---|
| Every URL 404s after reset | The second `pdc.sh up` didn't run — `.\pdc-remote.ps1 resume` |
| `set-password failed` on every user | You forgot `-FixPolicy` |
| Cast login rejected with valid password | Safe list — step 4 verify |
| `Could not establish trust relationship` | Add `-SkipTlsCheck` |
| Keycloak `https:/https://…` error in the app | Doubled scheme in a pasted base URL — retype the field |
| Licence upload 404 | Wrong path — check Swagger, see §7.0 of the big doc |
