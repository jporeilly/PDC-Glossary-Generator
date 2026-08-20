# PDC Reset Day — the runbook

Copy-paste, top to bottom, **PowerShell 5.1-native — every command below was
field-run on the dev console**. Field-proven 2026-08-14, re-proven and
corrected 2026-08-19, full clean-start sequence (both apps + the walk) added
2026-08-20. Budget **~30–45 min** (mostly the rebuild).
Depth: [PDC-REMOTE-RESET.md](../docs/PDC-REMOTE-RESET.md).

> **Why curl.exe and not Invoke-RestMethod:** PS 5.1's Invoke-RestMethod has
> **no skip-certificate flag at all** — against the VM's self-signed cert it
> can only fail ("Could not establish trust relationship"). `curl.exe -k` is
> the reliable form on this rig. JSON bodies use `\"` escapes because PS 5.1's
> native-argument quoting eats bare inner quotes.

**Destroyed by reset:** catalog, data sources, glossaries, `pdc`-realm
users, licence, safe list. **Survives:** the deployment on disk and the
lab stack (postgres :5433, MinIO :9000) — the demo data is safe.

```powershell
# 0 · Preflight + reset
Set-Location C:\Projects\PDC-Glossary\remote
.\pdc-remote.ps1 doctor                    # 16 green checks first
.\pdc-remote.ps1 reset                     # type 'reset'; 8-20 min

# 1 · Restore admin/admin (the fresh realm's stock password policy forbids
#     it, so the realm import leaves admin unusable; master realm IS
#     admin/admin and fixes it)
$mt = (curl.exe -sk -X POST 'https://pentaho.io/keycloak/realms/master/protocol/openid-connect/token' -H 'Content-Type: application/x-www-form-urlencoded' -d 'grant_type=password&client_id=admin-cli&username=admin&password=admin' | ConvertFrom-Json).access_token
curl.exe -sk -X PUT 'https://pentaho.io/keycloak/admin/realms/pdc' -H "Authorization: Bearer $mt" -H 'Content-Type: application/json' -d '{\"passwordPolicy\":\"length(5)\"}'
$u = (curl.exe -sk 'https://pentaho.io/keycloak/admin/realms/pdc/users?username=admin&exact=true' -H "Authorization: Bearer $mt" | ConvertFrom-Json)[0].id
curl.exe -sk -X PUT "https://pentaho.io/keycloak/admin/realms/pdc/users/$u/reset-password" -H "Authorization: Bearer $mt" -H 'Content-Type: application/json' -d '{\"type\":\"password\",\"value\":\"admin\",\"temporary\":false}'
# empty output = success; sanity is the login at step 2's end

# 2 · Licence — token to clipboard, then Swagger
$tok = (curl.exe -sk -X POST 'https://pentaho.io/keycloak/realms/pdc/protocol/openid-connect/token' -H 'Content-Type: application/x-www-form-urlencoded' -d 'grant_type=password&client_id=pdc-client&username=admin&password=admin' | ConvertFrom-Json).access_token
Set-Clipboard -Value $tok                  # ~5 min expiry; re-run to refresh
# https://pentaho.io/swagger/ -> Authorize -> paste (bare token) ->
# licensing -> POST /api/v2/licensing/uploadLicense -> Try it out ->
# deviceId pdc-demo + the .bin -> Execute -> 200.
# Or curl:
curl.exe -k -X POST 'https://pentaho.io/api/v2/licensing/uploadLicense' `
  -H "Authorization: Bearer $tok" -F 'deviceId=pdc-demo' `
  -F 'fileData=@C:\path\to\licence.bin;type=application/octet-stream'
# sanity: log in at https://pentaho.io as admin / admin

# 3 · Cast users (length(7): the cast password `azwater` is 7 chars —
#     plain -FixPolicy sets length(8) and rejects it)
Set-Location C:\Projects\PDC-Scenarios
.\load-pdc-users.ps1 -Scenario AWC -BaseUrl https://pentaho.io `
  -SkipTlsCheck -FixPolicy -PolicyValue 'length(7)' -Password azwater
# non-interactive: add  -AdminPassword (ConvertTo-SecureString 'admin' -AsPlainText -Force)
# then PROVE the cast took (read-only, no admin credential):
.\load-pdc-users.ps1 -Scenario AWC -BaseUrl https://pentaho.io `
  -SkipTlsCheck -Password azwater -Verify

# 4 · Email-domain safe list (IAM: users can only be created/log in with an
#     email whose domain is on the css-auth-proxy provider's safe list, at
#     provider_conf.emailDomains). azwater.gov seeds automatically from
#     EMAIL_DOMAINS in the VM's vendor/.env.default - VERIFY, don't assume:
Set-Location C:\Projects\PDC-Glossary\remote
.\reseed-domains.ps1 -VerifyOnly
# To ADD a domain: edit EMAIL_DOMAINS on the VM first, then reseed. The
# reseed uses the init's own DELETE+POST-full-config sequence and verifies
# at the real JSON path - do NOT chase the vendor doc's PUT {id,emailDomains},
# it is accepted-and-ignored on PDC 11:
#   ssh pdc@192.168.1.200   # edit /opt/pentaho/pdc-docker-deployment/vendor/.env.default -> EMAIL_DOMAINS=azwater.gov,newco.com
.\reseed-domains.ps1                       # DELETE+POST + verify (VM-side twin: remote\reseed-provider.sh)

# 5 · Health
.\pdc-remote.ps1 health                    # 302/401 fine, 404 bad

# 6 · Estate CHECK — the reset does NOT touch the lab data, so on a re-reset
#     day you VERIFY rather than seed. Expect ~1010 total and 0 non-conforming:
ssh pdc@192.168.1.200 "docker exec demo-postgres psql -U demo_admin -d awc_operations -tAc `"SELECT count(*), count(*) FILTER (WHERE account_number !~ '^AWC-') FROM awc_operations.customers`""

# 6b · Scale the estate — FIRST TIME ONLY. The seeder TOPS UP (adds N rows
#     above the max PK); running it against an already-scaled estate doubles
#     it. (OWNER account — pdc_user is read-only; the owner password is in
#     the demo-postgres container env:
#     ssh pdc@192.168.1.200 "docker inspect demo-postgres --format '{{range .Config.Env}}{{println .}}{{end}}' | grep POSTGRES_PASSWORD")
Set-Location C:\Projects\PDC-Glossary\glossary_generator
python -m sources.seed_sample --host 192.168.1.200 --port 5433 `
  --db awc_operations --schema awc_operations `
  --user demo_admin --password '<owner-pass>' --rows 1000 --all
# The document store stays small on purpose — the demo's honest sparse corner.
```

## 7 · Apps — clean install (both)

- **Glossary Generator**: uninstall the old build → install the latest
  `PDC-Glossary\dist\PDC Glossary Generator_<ver>_x64-setup.exe`
  (or **Settings → Factory reset** if keeping the install). **No domain
  pack** for a true day-zero walk.
- **Policy Generator**: uninstall the old build → install the latest
  `PDC-Policy\dist\PDC Policy Generator_<ver>_x64-setup.exe`.
- Connections to recreate in the Glossary app:
  postgres `192.168.1.200:5433` · db/schema `awc_operations` · user
  `pdc_user` (creds: the PDC-Scenarios bulk CSV) — MinIO
  `192.168.1.200:9000` · bucket `awc-documents` — PDC `https://pentaho.io`
  (Keycloak base `https://pentaho.io/keycloak`, realm `pdc`).

## 8 · The walk (Glossary)

Connect → **Bulk load** → wait for PDC profiling → **Harvest** (structured +
documents) → Review: `1 · AI categories` → settle the set via the **chips**
→ Accept all → `2 · Approve categories` (the keystone) → `3 · AI pass` →
**walk the pills** one by one → **Dismiss rest** → `4 · AI advise` → decide
the clusters → **✓ Review complete** → **Dictionary: approve the pending
vocabulary** (step 3 on Home — the governed-vocabulary gate) → Govern:
roster · stewardship · tick the label keys → **Generate** (self-archives +
MinIO backup) → PDC: Business Glossary → Import → Apply: **Resolve ids** →
dry-run → apply → Create labels → Preview → **Stamp** → **Draft policies**
(expect: account_number **Auto from profiled evidence**, the city
dictionaries **minting**, flip the ★ recommended) → send the bundle to
MinIO → Report.

## 9 · Policy Generator

**Load** (Registry auto-discovers from the Glossary hand-off; Connect to
PDC sits at the top of Load) → **Author** (the Evidence column says why
each method exists) → **Reconcile** (live progress bar) → **Deploy** →
PDC: run **Data Identification** on `customers` selecting the deployed
methods; add them under **String Detection** on the correspondence folder
→ **Drift**. The **Report** page is the whole account; Export standalone
HTML for handouts.

**Before any wipe** (when you DO want continuity): app **Settings → State
snapshot** + **Dictionary → Export domain pack → Apply → commit**. For a
later re-harvest after the data improved, tick **Refresh value evidence**
on the Harvest card.

## If something fights back

| Symptom | Fix |
|---|---|
| Every URL 404s after reset | The second `pdc.sh up` didn't run — `.\pdc-remote.ps1 resume` |
| `Could not establish trust relationship` | PS 5.1 Invoke-RestMethod cannot skip self-signed certs at all — use the `curl.exe -k` forms above / `-SkipTlsCheck` on the scripts |
| Token: `invalid_grant` for admin | Step 1 not done — the fresh realm has no usable admin password |
| JSON body reaches the API mangled | PS 5.1 eats bare `"` in native args — write bodies as `'{\"key\":\"value\"}'` |
| `set-password failed` on every user | Policy — use `-FixPolicy -PolicyValue 'length(7)'` |
| Cast login rejected with valid password | Safe list — step 4 verify |
| Keycloak `https:/https://…` error in the app | Doubled scheme in a pasted base URL — retype the field |
| Licence upload 404 | Wrong path — check Swagger; see PDC-REMOTE-RESET.md §7 |
| Draft says account_number "induces no shape" | Stale evidence — PDC re-profile `customers`, then re-harvest with **Refresh value evidence** ticked, then redraft |
| Seed dies on PK/unique/date/overflow | You're on a pre-1.38.27 seeder — update; the current one is constraint-tolerant |
