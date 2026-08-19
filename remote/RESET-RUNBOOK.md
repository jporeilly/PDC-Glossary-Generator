# PDC Reset Day — the runbook

Copy-paste, top to bottom, PowerShell-native. Field-proven 2026-08-14,
re-proven and corrected 2026-08-19. Budget **~30–45 min** (mostly the
rebuild). Depth: [PDC-REMOTE-RESET.md](../docs/PDC-REMOTE-RESET.md).

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
$mt = (Invoke-RestMethod -Method Post -Uri 'https://pentaho.io/keycloak/realms/master/protocol/openid-connect/token' -Body @{grant_type='password';client_id='admin-cli';username='admin';password='admin'}).access_token
Invoke-RestMethod -Method Put -Uri 'https://pentaho.io/keycloak/admin/realms/pdc' -Headers @{Authorization="Bearer $mt"} -ContentType 'application/json' -Body '{"passwordPolicy":"length(5)"}'
$u = (Invoke-RestMethod -Uri 'https://pentaho.io/keycloak/admin/realms/pdc/users?username=admin&exact=true' -Headers @{Authorization="Bearer $mt"})[0].id
Invoke-RestMethod -Method Put -Uri "https://pentaho.io/keycloak/admin/realms/pdc/users/$u/reset-password" -Headers @{Authorization="Bearer $mt"} -ContentType 'application/json' -Body '{"type":"password","value":"admin","temporary":false}'
# (PS 5.1 + self-signed cert: if Invoke-RestMethod refuses TLS, use the
#  curl.exe equivalents — see git history of this file.)

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

# 5 · Scale the estate (OWNER account — pdc_user is read-only; the owner
#     password is in the demo-postgres container env:
#     ssh pdc@192.168.1.200 "docker inspect demo-postgres --format
#       '{{range .Config.Env}}{{println .}}{{end}}' | grep POSTGRES_PASSWORD")
Set-Location C:\Projects\PDC-Glossary\glossary_generator
python -m sources.seed_sample --host 192.168.1.200 --port 5433 `
  --db awc_operations --schema awc_operations `
  --user demo_admin --password '<owner-pass>' --rows 1000 --all
# The document store stays small on purpose — the demo's honest sparse corner.

# 6 · App: install the latest build; Settings -> Factory reset if reusing a
#     machine; install the domain pack (skip for a true day-zero walk);
#     Connect -> Bulk load -> Harvest -> the walk.
```

**Before any wipe** (when you DO want continuity): app **Settings → State
snapshot** + **Dictionary → Export domain pack → Apply → commit**. For a
later re-harvest after the data improved, tick **Refresh value evidence**
on the Harvest card.

## If something fights back

| Symptom | Fix |
|---|---|
| Every URL 404s after reset | The second `pdc.sh up` didn't run — `.\pdc-remote.ps1 resume` |
| Token: `invalid_grant` for admin | Step 1 not done — the fresh realm has no usable admin password |
| `set-password failed` on every user | Policy — use `-FixPolicy -PolicyValue 'length(7)'` |
| Cast login rejected with valid password | Safe list — step 4 verify |
| `Could not establish trust relationship` | Add `-SkipTlsCheck` (scripts) / use `curl.exe -k` (REST) |
| Keycloak `https:/https://…` error in the app | Doubled scheme in a pasted base URL — retype the field |
| Licence upload 404 | Wrong path — check Swagger; see PDC-REMOTE-RESET.md §7 |
| Seed dies on PK/unique/date/overflow | You're on a pre-1.38.27 seeder — update; the current one is constraint-tolerant |
