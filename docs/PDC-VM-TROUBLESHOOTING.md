# PDC VM troubleshooting — deployment & platform errors

Notes for the PDC 11.0.0 instance running in the lab's Ubuntu VM
(`/opt/pentaho/pdc-docker-deployment`, served at `https://pentaho.io`).
These are **platform** issues — the demo lab stack (`data_sources/lab/`)
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

Diagnose top-to-bottom on the VM, from
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

*Add further PDC platform issues here as the labs surface them — same
format: the exact error, what the failing piece does, an ordered check
chain, and the verification step.*
