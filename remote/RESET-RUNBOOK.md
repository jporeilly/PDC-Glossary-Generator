# PDC Reset Day — the runbook

One folder, one document, top to bottom. Every step is a copy-paste command
run from `C:\Projects\PDC-Glossary\remote` (unless the step says otherwise).
Field-proven 2026-08-14. Deep background lives in
[PDC-REMOTE-RESET.md](../docs/PDC-REMOTE-RESET.md); this page is the doing.

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

   ```bash
   python seed_sample.py --host 192.168.1.200 --port 5433 --db awc_operations \
                         --user <loader-user> --password '<loader-pass>' \
                         --rows 1000 --all
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
