# PDC VM troubleshooting — deployment & platform errors

Notes for the PDC 11.0.0 instance running in the lab's Ubuntu VM
(`/opt/pentaho/pdc-docker-deployment`, served at `https://pentaho.io`).
These are **platform** issues — the demo lab stack (PDC-Scenarios' `data_sources/lab/`)
and the Glossary Generator have their own troubleshooting sections.
Ordered checklists: work top to bottom, the first failing check is almost
always the cause. Confirm specifics against the Pentaho documentation for
your exact PDC version.

---

## `service "opensearch-cluster-init" didn't complete successfully: exit 1`

Seen at the end of `docker compose up -d`, after the other containers
report Running. `opensearch-cluster-init` is a **one-shot init job**: it
waits for the OpenSearch cluster to come up healthy, then seeds the
indices, users and policies PDC needs. Exit 1 means it gave up — almost
always because OpenSearch itself never became healthy, not because the
init logic is broken.

### KNOWN CAUSE on this lab's deployment — securityadmin cert trust

On this deployment's OpenSearch image (`cat-opensearch:2.19`,
Bitnami-based) a **fresh volume** reproduces this failure every clean
rebuild. Root cause: the image regenerates
`/opt/bitnami/opensearch/config/extra.crt` (the node's truststore) with
only the node CA — the node's own CN — so it does not trust the
self-signed `CN=admin` certificate. `securityadmin` therefore cannot
authenticate to write the `.opendistro_security` index, and cluster-init
times out waiting for a security-initialized cluster.

Tell-tales: the node log repeats *"Failure no such index
[.opendistro_security]"* / *"OpenSearch Security not initialized"*; a
plain `curl -s http://localhost:9200/_cluster/health` from inside the
node container returns *"not initialized"* instead of a 401; securityadmin
fails with `certificate_unknown`.

**Fix — append the admin cert to the node truststore, restart, run
securityadmin by hand** (run on the VM as the pdc user):

```bash
node=$(docker ps --format '{{.Names}}' | grep opensearch | grep -vE 'init|volume' | head -1)

# make the node trust the admin cert (append to the truststore, as root)
docker exec -u 0 "$node" sh -c '
  if [ $(grep -c "BEGIN CERT" /opt/bitnami/opensearch/config/extra.crt) -lt 2 ]; then
    cat /opt/bitnami/opensearch/config/admin.crt >> /opt/bitnami/opensearch/config/extra.crt
  fi'

docker restart "$node"
sleep 40

# load the security config -> creates .opendistro_security (REST 9200/TLS)
docker exec "$node" bash -c '
  cd /opt/bitnami/opensearch/plugins/opensearch-security/tools && \
  ./securityadmin.sh \
    -cd /opt/bitnami/opensearch/config/opensearch-security/ \
    -icl -nhnv \
    -cacert /opt/bitnami/opensearch/config/extra.crt \
    -cert   /opt/bitnami/opensearch/config/admin.crt \
    -key    /opt/bitnami/opensearch/config/admin.key \
    -h localhost -p 9200'
```

Expect `Done with success`. Then confirm and bring the stack up:

```bash
docker exec "$node" curl -s http://localhost:9200/_cluster/health
# "not initialized" flipping to a 401 response = security is now active
./pdc.sh up
./pdc.sh ps      # cluster-init should reach Exited (0)
```

**The failure cascades — one `up` is not enough.** When cluster-init
exits 1, its dependent inits (e.g. `um-css-admin-api-init`) fail too and
the whole app tier (`fe`, `public-api`, `glossary`, …) stays in
`Created`. Traefik answers but has no backends, so **every URL 404s even
after OpenSearch is fixed**. After the repair you must re-run
`./pdc.sh up` so the stranded services start, then wait for `fe` and
`public-api` to actually reach `Up`. If the tier is stuck in `Created`
and OpenSearch is healthy, see the site-wide-404 section below — there is
a second, independent cause.

**Automated: `pdc-reset.sh`** (repo root, run on the VM). The full
wipe-and-rebuild script does all of this — wipes the `pdc_*` volumes,
brings the stack up, appends the admin cert (idempotently, with cert
paths read from the container's own env), restarts the node, runs
securityadmin, verifies `.opendistro_security`, re-runs `up` to un-stick
the app tier, and waits for `fe`/`public-api` before declaring success.
It also supports `--keep-opensearch` (skip the security dance by
preserving the OpenSearch volumes), optional MailHog, and optional
offline-license re-upload. Use the manual sequence above only when
repairing a live instance **without** wiping.

Notes from the times this has recurred:

- The node's CN follows the host that generated it (`awc-pdc` on the old
  VM, whatever `pdc-demo` minted on this one). The fix does not depend on
  the CN — it appends `admin.crt` to `extra.crt` regardless — so don't be
  thrown if the certificate subjects read differently between rebuilds.
- If securityadmin still throws `certificate_unknown`: the append didn't
  take (`grep -c "BEGIN CERT" extra.crt` inside the node must show 2) or
  the restart didn't reload the truststore — redo those two steps.
- securityadmin must target **REST 9200 with TLS** on this build —
  pointing it at 9300 fails with *"not an HTTP port"*.
- This recurs on **every clean rebuild** with a fresh OpenSearch volume —
  which is exactly why `pdc-reset.sh` exists; prefer it over hand-running
  the sequence.

If the tell-tales above do **not** match, fall back to the generic chain
below — diagnose top-to-bottom on the VM, from
`/opt/pentaho/pdc-docker-deployment`:

### 1. Read the init job's own log first

```sh
docker compose logs opensearch-cluster-init | tail -40
```

The last lines usually name the cause outright — a connection refused /
timeout (OpenSearch never came up: continue to check 2), an
authentication or TLS error, or a cluster-health wait that expired.

### 2. Is OpenSearch itself up and healthy?

```sh
docker compose ps | grep -i opensearch
docker compose logs --tail=100 opensearch
```

If the `opensearch` container is restarting or exited, its log names the
real problem — the three classics are checks 3, 4 and 5. If it is
`Up (healthy)`, skip to check 6.

### 3. `vm.max_map_count` too low — the classic on a fresh VM

OpenSearch refuses to start unless the kernel allows at least 262144
memory-map areas. The tell-tale line in the opensearch log:

```text
max virtual memory areas vm.max_map_count [65530] is too low,
increase to at least [262144]
```

Check and fix (fix survives reboots via sysctl.d):

```sh
sysctl vm.max_map_count                                  # likely 65530
sudo sysctl -w vm.max_map_count=262144                   # immediate
echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-opensearch.conf
```

### 4. Not enough memory

OpenSearch wants several GB of heap; on an undersized VM the container is
OOM-killed (exit code 137 in `docker compose ps -a`, or `Killed` in its
log).

```sh
free -h
docker inspect --format '{{.State.OOMKilled}} {{.State.ExitCode}}' \
  $(docker compose ps -q opensearch)
```

Fix: give the VM more RAM (PDC's sizing guidance applies), or lower the
OpenSearch heap via its JVM options if your deployment exposes them.

### 5. Disk nearly full — the flood-stage watermark

Above ~90% disk usage OpenSearch blocks index creation, so the cluster
starts but cluster-init cannot seed it.

```sh
df -h /            # and the docker data mount, often /var/lib/docker
docker system df   # see what's eating it
```

Fix: free space (`docker system prune` for dangling images/build cache —
review before confirming; it does not touch named volumes), then re-run.

### 6. Slow first boot — the init simply timed out

On a first start, OpenSearch bootstraps its security index while
cluster-init is already waiting; on a slow VM the wait can expire even
though nothing is wrong. One-shot jobs re-run on the next `up`:

```sh
docker compose up -d
docker compose ps -a | grep cluster-init   # want Exited (0)
```

If everything else checks out, re-running once is a legitimate fix.

### 7. Last resort — a half-initialized OpenSearch volume

If a *first* install failed mid-bootstrap (power loss, OOM during check
4), the security index can be left corrupt and every retry fails the same
way. **Only on a fresh install with no data worth keeping**, recreate the
OpenSearch volume — this destroys the search indices:

```sh
docker compose down
docker volume ls | grep -i opensearch      # identify the volume name
docker volume rm <opensearch-volume>
docker compose up -d
```

On an instance that already holds catalog data, stop here and engage
Pentaho support instead.

### Verify the fix

```sh
docker compose ps -a | grep cluster-init   # Exited (0)
curl -sk https://pentaho.io/ -I            # PDC UI answers
```

Then sign in and check the Workers page — search-backed features
(Discovery search, Suggested Columns) come back once the indices exist.

---

## Site-wide 404 — app tier stuck in `Created` (`um-css-admin-api-init` exit 1)

`pentaho.io` returns 404 for every path, including
`/api/public/swagger/`. `./pdc.sh ps` shows `fe`, `public-api`,
`glossary`, `mds`, `applications` and others stuck in `Created`, and
`um-css-admin-api-init` exits 1 with its log looping `http_code=000`
against `https://pentaho.io/keycloak/realms/master`. **Two possible
causes — check both:**

1. **The OpenSearch init failed** (section above): the dependent init
   chain fails and the tier never starts. Fix that first, then re-run
   `./pdc.sh up`.
2. **More subtly: `/etc/hosts` maps `pentaho.io` to `127.0.0.1`.** Inside
   a container, 127.0.0.1 is the container itself — so any service that
   reaches another via the `pentaho.io` URL (Keycloak, Mongo/FerretDB,
   OpenSearch, Kafka; all built from `GLOBAL_SERVER_HOST_NAME=pentaho.io`)
   hits its own loopback and gets `http_code=000`, stranding the entire
   stack. This mapping was introduced during the version upgrade.

Fix the mapping, then recreate the containers so they pick it up:

```sh
sudo sed -i 's/^127\.0\.0\.1\s\+pentaho\.io/192.168.1.200 pentaho.io/' /etc/hosts
grep pentaho.io /etc/hosts    # should now read: 192.168.1.200 pentaho.io
cd /opt/pentaho/pdc-docker-deployment && ./pdc.sh stop && ./pdc.sh up
```

Verify from inside any container — the name must resolve to the LAN IP:

```sh
docker exec "$node" getent hosts pentaho.io   # expect 192.168.1.200, not 127.0.0.1
```

---

## Browser: `NET::ERR_CERT_AUTHORITY_INVALID` at `https://pentaho.io` — with no "Proceed anyway" link

Seen in Chrome (on the VM or the Windows host) after a rebuild. **This is
a browser trust issue, not a PDC failure.** PDC's TLS certificate is
self-signed, so Chrome doesn't trust the CA — and on a fresh rebuild the
certificate regenerates, so hitting this right after wiping volumes is
expected. The twist: `pentaho.io` is under **HSTS**, which is why Chrome
suppresses the "Proceed to pentaho.io (unsafe)" link it normally offers.

If the OpenSearch `_cluster/health` check (section above) already answers
401, PDC itself is healthy — this warning is the only thing between you
and the login page.

### Fastest — the HSTS-override bypass

With the error page focused, type **blind** (there is no input box):

```text
thisisunsafe
```

Chrome accepts it as the HSTS-override passphrase and loads the site.
This is the standard trick precisely because HSTS suppresses the normal
proceed link. It is **per-certificate**, so repeat it after any rebuild
that regenerates the cert.

### Clean — trust the certificate

Import the cert the web tier actually serves. Do **not** grab the
OpenSearch `server.crt` — the cert on 443 is served by the Traefik/proxy
container. Capture what the browser is actually rejecting:

```sh
openssl s_client -connect pentaho.io:443 -servername pentaho.io </dev/null 2>/dev/null \
  | openssl x509 -outform PEM > /tmp/pentaho.crt
openssl x509 -in /tmp/pentaho.crt -noout -subject -issuer   # sanity-check
```

Trust it system-wide on the Ubuntu VM:

```sh
sudo cp /tmp/pentaho.crt /usr/local/share/ca-certificates/pentaho.crt
sudo update-ca-certificates
```

Recent Chrome no longer has an Authorities → Import tab — it reads
imported certificates from the operating system store (*"use imported
local certificates from your operating system"*), so the
`update-ca-certificates` step above is what Chrome picks up; restart the
browser afterwards.

**Gotcha — stale certificates.** The cert regenerates each rebuild, so
old trusted certs accumulate in two separate stores: the OS store
(`/usr/local/share/ca-certificates`) and Chrome's NSS database
(`~/.pki/nssdb`). `update-ca-certificates` only manages the OS store, so
a stale entry (for example a `CN=awc-pdc` leftover) can survive in NSS.
Find and remove them by subject/nickname:

```sh
for f in /usr/local/share/ca-certificates/*.crt; do
  echo "$f -> $(openssl x509 -in "$f" -noout -subject)"; done
certutil -d sql:$HOME/.pki/nssdb -L                 # list Chrome NSS entries
certutil -d sql:$HOME/.pki/nssdb -D -n "<nickname>" # delete a stale one
```

### Which path to use

- Throwaway lab session: `thisisunsafe` is all you need.
- A VM you demo from regularly: the import is worth doing once — **but**
  every volume-wipe rebuild regenerates the cert, so you re-import each
  time. In a rebuild-heavy lab that is itself an argument for the bypass.

---

## `invalid_grant` / "Invalid user credentials" after a rebuild — who are the users?

Token requests against Keycloak fail with
`{"error":"invalid_grant","error_description":"Invalid user credentials"}`
for every username/password you try, even though the stack is healthy.
Three separate traps stack up here, learned the hard way after a clean
`pdc-reset.sh` rebuild:

1. **The 11.0.0 deployment SEEDS the `pdc` realm with six stock users** —
   `admin`, `business_steward`, `business_user`, `data_developer`,
   `data_steward`, `data_user`, all with `@hv.com` emails — so there may be
   **no Register page** after a wipe: the users already exist with whatever
   password the realm import set (try the training default first).
2. **Username, not email.** Keycloak's direct grant wants the `username`
   field: `-d username=admin` works where `-d username=admin@hv.com`
   returns `invalid_grant`, even for the same account.
3. **The usual token one-liner swallows errors.** Piping through
   `sed -n 's/.*"access_token"...'` prints *nothing* on an error response.
   Debug with the raw curl (no pipe), or:

   ```bash
   curl -sk -X POST 'https://pentaho.io/keycloak/realms/pdc/protocol/openid-connect/token' \
     -d client_id=pdc-client -d grant_type=password \
     -d username=admin -d password='...' \
   | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("access_token") or json.dumps(d))'
   ```

**Inspect the realm's actual users** (definitive — no guessing). The
Keycloak container is `pdc-um-keycloak-1` (NOT `um-oauth`, which is PDC's
own OAuth shim), kcadm lives at `/opt/keycloak/bin/kcadm.sh`, and the
server runs under the **`/keycloak` relative path** (plain
`http://localhost:8080` returns 404):

```bash
docker exec pdc-um-keycloak-1 sh -c '
  /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080/keycloak --realm master \
    --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD" \
  && /opt/keycloak/bin/kcadm.sh get users -r pdc --fields username,email,enabled
'
```

- `[ ]` (empty) → the realm has no users; `https://pentaho.io` will show
  the Register page — create the root user there.
- Users listed → the `username` values shown are what the token grant
  wants; check `enabled: true`.

**If the seeded password is unknown, set it** — the container's own
master-admin credentials give you the authority:

```bash
docker exec pdc-um-keycloak-1 sh -c '
  /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080/keycloak --realm master \
    --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD" \
  && /opt/keycloak/bin/kcadm.sh set-password -r pdc --username admin --new-password "<new password>"
'
```

**Verify**: rerun the token curl with `username=admin` and the confirmed
password — a JWT prints. Those same credentials go into the Glossary
Generator's PDC connection fields and `pdc-reset.sh`'s `PDC_ADMIN_PASS`
for the automatic license upload.

---

## Licensed features unavailable after a rebuild

After a volume wipe, licensed features are greyed out even though offline
mode is configured. The offline license is stored in **PDC's internal
database**, which is wiped with the volumes; the
`LICENSING_OFFLINE_INSTALL=true` flag survives (it lives in `conf/.env`),
but the uploaded license does not. Re-upload the `license.bin` after each
rebuild — get a bearer token, then POST it to
`/api/public/v2/licensing/uploadLicense` with `deviceId=pdc-demo` (the
endpoint is `v1` on earlier builds and `/api/public/v3/licensing/upload`
on v3 — the Swagger page shows which your instance exposes).
`pdc-reset.sh` does this automatically when `LICENSE_BIN` and the admin
password are supplied. The full Swagger walkthrough is in the lab setup
guide (PDC-Scenarios' `data_sources/lab/lab-setup.docx`, Part I).

---

*Add further PDC platform issues here as the labs surface them — same
format: the exact error, what the failing piece does, an ordered check
chain, and the verification step.*
