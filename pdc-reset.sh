#!/usr/bin/env bash
#
# pdc-reset.sh — wipe + recreate the Pentaho Data Catalog app deployment (pdc-demo / 11.0.0),
# auto-repair the OpenSearch security-index init, then un-stick the app tier.
#
# Why this exists (all learned the hard way):
#   1. A fresh pdc_opensearch volume regenerates extra.crt with only the node CA, so the node
#      never trusts the self-signed CN=admin cert -> securityadmin can't write .opendistro_security
#      -> opensearch-cluster-init exits 1.
#   2. That failure CASCADES: dependent inits (um-css-admin-api-init) fail and the whole app tier
#      (fe, public-api, glossary, ...) stays in "Created". Traefik answers but has no backends,
#      so every URL 404s. Fixing OpenSearch is not enough — you must re-run `up` afterwards so the
#      stranded services start, and wait for fe/public-api to actually come Up.
#
# This script wipes volumes, brings the stack up, repairs OpenSearch security, re-runs up,
# and waits for the frontend + API before declaring success.
#
# Usage:
#   ./pdc-reset.sh                     # prompts before wiping
#   ./pdc-reset.sh -y                  # no prompt (destructive)
#   ./pdc-reset.sh --keep-opensearch   # wipe everything EXCEPT opensearch volumes (skips the security dance)
#
set -euo pipefail

# ------------------------------- config ---------------------------------------
PDC_DIR="${PDC_DIR:-/opt/pentaho/pdc-docker-deployment}"
VOLUME_PREFIX="${VOLUME_PREFIX:-pdc_}"
CONTAINER_PREFIX="${CONTAINER_PREFIX:-pdc-}"
PDC_HOST="${PDC_HOST:-https://pentaho.io}"        # PDC's own HTTPS URL
DEVICE_ID="${DEVICE_ID:-pdc-demo}"

# conf/.env overrides to guarantee on every rebuild (config survives the wipe, but we enforce these)
ENFORCE_OFFLINE_LICENSE="${ENFORCE_OFFLINE_LICENSE:-1}"   # sets LICENSING_OFFLINE_INSTALL=true

# Optional: MailHog email capture (0/1). Ensures KEYCLOAK_SMTP override + reattaches the container.
MAILHOG="${MAILHOG:-0}"
MAILHOG_FROM="${MAILHOG_FROM:-pdc-demo@pdc-demo.local}"

# Optional offline-license re-upload (leave LICENSE_BIN empty to skip)
LICENSE_BIN="${LICENSE_BIN:-}"                    # e.g. /opt/pentaho/license.bin
PDC_ADMIN_USER="${PDC_ADMIN_USER:-admin}"
PDC_ADMIN_PASS="${PDC_ADMIN_PASS:-}"             # Keycloak/PDC admin password
KC_REALM="${KC_REALM:-pdc}"
KC_CLIENT="${KC_CLIENT:-pdc-client}"

ASSUME_YES=0
KEEP_OS=0
for a in "$@"; do
  case "$a" in
    -y|--yes) ASSUME_YES=1 ;;
    --keep-opensearch) KEEP_OS=1 ;;
  esac
done

# ------------------------------- helpers --------------------------------------
log()  { printf '\033[1;34m[reset]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ ok ]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

os_node() { docker ps --format '{{.Names}}' | grep opensearch | grep -vE 'init|volume' | head -1; }

# wait until a service container reports "Up" (matches pdc-<svc>-N)
wait_service() {
  local svc="$1" timeout="${2:-240}" i state
  for i in $(seq 1 $((timeout/5))); do
    state="$(docker ps --format '{{.Names}}\t{{.Status}}' \
             | grep -E "^${CONTAINER_PREFIX}${svc}-[0-9]" | awk -F'\t' '{print $2}' | head -1)"
    case "$state" in Up*) return 0;; esac
    sleep 5
  done
  return 1
}

# wait until OpenSearch REST answers at all (any response = reachable)
wait_os_rest() {
  local node="$1" i
  for i in $(seq 1 60); do
    if docker exec "$node" sh -c \
         'curl -sk https://localhost:9200 -o /dev/null 2>/dev/null || curl -s http://localhost:9200 -o /dev/null 2>/dev/null'; then
      return 0
    fi
    sleep 3
  done
  return 1
}

# add-or-replace a KEY=VALUE line in conf/.env (value must not contain a pipe).
# conf/.env is usually root-owned: skip when already correct, escalate with sudo
# when we can, and WARN rather than die otherwise (set -e must not kill the
# reset over a flag that normally already survives the wipe).
ensure_env_kv() {
  local key="$1" val="$2" f="$PDC_DIR/conf/.env" SUDO=""
  if [ -f "$f" ] && grep -q "^${key}=${val}\$" "$f"; then
    ok "conf/.env already has ${key}=${val}"
    return 0
  fi
  if [ ! -w "$f" ] && { [ -e "$f" ] || [ ! -w "$(dirname "$f")" ]; }; then
    if sudo -n true 2>/dev/null || [ -t 0 ]; then
      SUDO="sudo"
    else
      warn "conf/.env not writable (and no sudo) — set ${key}=${val} in $f manually if it's missing."
      return 0
    fi
  fi
  $SUDO touch "$f" || { warn "could not write $f — set ${key}=${val} manually."; return 0; }
  if $SUDO grep -q "^${key}=" "$f"; then
    $SUDO sed -i "s|^${key}=.*|${key}=${val}|" "$f"
  else
    printf '%s=%s\n' "$key" "$val" | $SUDO tee -a "$f" >/dev/null
  fi
}

# ------------------------------- pre-flight -----------------------------------
[ -d "$PDC_DIR" ] || die "PDC dir not found: $PDC_DIR"
[ -x "$PDC_DIR/pdc.sh" ] || die "pdc.sh not found/executable in $PDC_DIR"
cd "$PDC_DIR"

if [ "$ASSUME_YES" -ne 1 ]; then
  echo "This PERMANENTLY DELETES ${VOLUME_PREFIX}* volumes (catalog, glossaries, users, trust"
  echo "scores, license). Config and certs under $PDC_DIR persist."
  [ "$KEEP_OS" -eq 1 ] && echo "(--keep-opensearch: opensearch volumes will be PRESERVED)"
  read -r -p "Type 'reset' to continue: " ans
  [ "$ans" = "reset" ] || die "Aborted."
fi

# ------------------------------- teardown -------------------------------------
log "Stopping PDC services..."
./pdc.sh stop || warn "pdc.sh stop returned non-zero (continuing)"

log "Force-removing ${CONTAINER_PREFIX}* containers (frees the volumes)..."
mapfile -t cids < <(docker ps -a --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}" || true)
[ "${#cids[@]}" -gt 0 ] && docker rm -f "${cids[@]}" >/dev/null || true

log "Removing ${VOLUME_PREFIX}* volumes$([ "$KEEP_OS" -eq 1 ] && echo ' (except opensearch)')..."
if [ "$KEEP_OS" -eq 1 ]; then
  mapfile -t vols < <(docker volume ls -q | grep "^${VOLUME_PREFIX}" | grep -v opensearch || true)
else
  mapfile -t vols < <(docker volume ls -q | grep "^${VOLUME_PREFIX}" || true)
fi
if [ "${#vols[@]}" -gt 0 ]; then
  printf '  - %s\n' "${vols[@]}"
  docker volume rm "${vols[@]}" >/dev/null
  ok "Removed ${#vols[@]} volume(s)."
else
  warn "No matching volumes found."
fi

# ------------------------- enforce conf/.env overrides ------------------------
if [ "$ENFORCE_OFFLINE_LICENSE" -eq 1 ]; then
  log "Ensuring LICENSING_OFFLINE_INSTALL=true in conf/.env..."
  ensure_env_kv "LICENSING_OFFLINE_INSTALL" "true"
fi
if [ "$MAILHOG" -eq 1 ]; then
  if ! grep -q '^KEYCLOAK_SMTP=' conf/.env 2>/dev/null; then
    log "Adding MailHog KEYCLOAK_SMTP override to conf/.env..."
    ensure_env_kv "KEYCLOAK_SMTP" "'{\"host\":\"mailhog\",\"port\":\"1025\",\"auth\":\"false\",\"ssl\":\"\",\"starttls\":\"false\",\"from\":\"${MAILHOG_FROM}\",\"fromDisplayName\":\"PDC Demo\",\"replyTo\":\"\",\"replyToDisplayName\":\"\",\"envelopeFrom\":\"\",\"user\":\"\",\"password\":\"\"}'"
  else
    warn "KEYCLOAK_SMTP already set in conf/.env — leaving it."
  fi
fi

# ------------------------------- recreate -------------------------------------
log "Bringing PDC up..."
./pdc.sh up

log "Waiting for the OpenSearch node..."
node=""; for _ in $(seq 1 30); do node="$(os_node)"; [ -n "$node" ] && break; sleep 3; done
[ -n "$node" ] || die "OpenSearch node container never appeared."
ok "Node: $node"
wait_os_rest "$node" || die "OpenSearch REST never responded."

# ------------------- OpenSearch security-index repair -------------------------
if [ "$KEEP_OS" -eq 1 ]; then
  log "Skipping OpenSearch security repair (--keep-opensearch: index preserved)."
else
  # cert locations come from the container's own env (source of truth)
  CA="$(docker exec "$node" printenv OPENSEARCH_CA_CERT_LOCATION 2>/dev/null || echo /opt/bitnami/opensearch/config/extra.crt)"
  CERT="$(docker exec "$node" printenv OPENSEARCH_SECURITY_ADMIN_CERT_LOCATION 2>/dev/null || echo /opt/bitnami/opensearch/config/admin.crt)"
  KEY="$(docker exec "$node" printenv OPENSEARCH_SECURITY_ADMIN_KEY_LOCATION 2>/dev/null || echo /opt/bitnami/opensearch/config/admin.key)"
  OS_USER="$(docker exec "$node" printenv OPENSEARCH_USERNAME 2>/dev/null || echo admin)"
  OS_PASS="$(docker exec "$node" printenv OPENSEARCH_PASSWORD 2>/dev/null || echo admin)"

  log "Making the node trust the admin cert (append to $CA, as root)..."
  # fresh extra.crt holds only the node CA (CN=pdc-demo); append the self-signed CN=admin cert
  # or securityadmin's mTLS fails with certificate_unknown. Idempotent: only if <2 certs present.
  docker exec -u 0 "$node" sh -c "
    if [ \$(grep -c 'BEGIN CERT' '$CA') -lt 2 ]; then
      cp -n '$CA' '${CA}.orig' 2>/dev/null || true
      cat '$CERT' >> '$CA'; echo appended
    else echo 'already trusted'; fi
  "
  log "Restarting node to reload the truststore..."
  docker restart "$node" >/dev/null
  wait_os_rest "$node" || die "Node did not come back after restart."
  sleep 5

  # REST TLS is on for this build, so securityadmin targets REST 9200 (9300 -> 'not an HTTP port').
  # Retry: right after the restart the node can answer REST while the cluster is
  # still forming, and securityadmin fails transiently — one attempt is not enough.
  log "Loading security config (securityadmin -> REST 9200/TLS)..."
  sec_ok=0
  for attempt in 1 2 3; do
    if docker exec "$node" bash -c "
      cd /opt/bitnami/opensearch/plugins/opensearch-security/tools && \
      ./securityadmin.sh -cd /opt/bitnami/opensearch/config/opensearch-security/ \
        -icl -nhnv -cacert '$CA' -cert '$CERT' -key '$KEY' -h localhost -p 9200
    "; then sec_ok=1; break; fi
    warn "securityadmin attempt ${attempt}/3 failed — cluster may still be forming; retrying in 20s..."
    sleep 20
  done
  [ "$sec_ok" -eq 1 ] || die "securityadmin failed 3x — work docs/PDC-VM-TROUBLESHOOTING.md ('opensearch-cluster-init' checklist: certs, vm.max_map_count, memory, disk watermark); inspect: docker logs $node --tail 40"

  if docker exec "$node" curl -sk -u "$OS_USER:$OS_PASS" \
       "https://localhost:9200/_cat/indices/.opendistro_security" 2>/dev/null | grep -q opendistro_security; then
    ok "Security index initialized (.opendistro_security present)."
  else
    warn "Could not confirm .opendistro_security — check node logs."
  fi
fi

# ---------------- un-stick the app tier stranded in 'Created' -----------------
# After OpenSearch is healthy, re-run up so fe/public-api/glossary/etc. (held in Created by the
# failed init chain) actually start. Without this you get a site-wide 404 despite Traefik being up.
log "Re-running up to start any services stranded in Created..."
./pdc.sh up

log "Waiting for the frontend and API to come Up (this is what clears the 404)..."
if wait_service fe 300 && wait_service public-api 300; then
  ok "fe and public-api are Up."
else
  warn "fe/public-api did not reach Up in time — check: ./pdc.sh ps"
  warn "If um-css-admin-api-init exited 1, re-run ./pdc.sh up once more; it depends on OpenSearch."
fi
./pdc.sh ps || true

# ---------------------------- optional: MailHog -------------------------------
if [ "$MAILHOG" -eq 1 ]; then
  net="$(docker network ls --format '{{.Name}}' | grep -E '^pdc(_default)?$' | head -1)"
  net="${net:-pdc_default}"
  if ! docker ps --format '{{.Names}}' | grep -q '^mailhog$'; then
    log "Starting MailHog on network $net..."
    docker run -d --name mailhog --network "$net" --restart unless-stopped -p 8025:8025 mailhog/mailhog >/dev/null || \
      warn "MailHog start failed (already exists? reattach with: docker network connect $net mailhog)"
  else
    docker network connect "$net" mailhog 2>/dev/null || true
    ok "MailHog already running; ensured it's on $net."
  fi
fi

# ---------------------------- optional: license -------------------------------
if [ -n "$LICENSE_BIN" ]; then
  if [ ! -f "$LICENSE_BIN" ]; then
    warn "LICENSE_BIN set but file missing: $LICENSE_BIN — skipping upload."
  elif [ -z "$PDC_ADMIN_PASS" ]; then
    warn "PDC_ADMIN_PASS not set — skipping license upload."
  else
    log "Requesting token + uploading offline license..."
    TOKEN="$(curl -sk -X POST "$PDC_HOST/keycloak/realms/$KC_REALM/protocol/openid-connect/token" \
      -d "client_id=$KC_CLIENT" -d grant_type=password \
      -d "username=$PDC_ADMIN_USER" -d "password=$PDC_ADMIN_PASS" \
      | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
    if [ -z "$TOKEN" ]; then
      warn "Token request failed — upload the license manually via Swagger."
    else
      curl -sk -X POST "$PDC_HOST/api/public/v2/licensing/uploadLicense" \
        -H "Authorization: Bearer $TOKEN" \
        -F "deviceId=$DEVICE_ID" \
        -F "fileData=@$LICENSE_BIN;type=application/octet-stream" \
        && ok "License upload request sent." \
        || warn "License upload failed — do it manually via Swagger."
    fi
  fi
fi

# ------------------------------- done -----------------------------------------
echo
ok "Reset complete."
echo "Next (manual) steps:"
echo "  1. Open $PDC_HOST — the Register page will prompt you to recreate the root user."
[ -z "$LICENSE_BIN" ] && \
echo "  2. Re-upload the offline license (.bin) via Swagger: $PDC_HOST/api/public/swagger/"
echo "  3. Re-load the demo lab (cd data_sources/lab && make up && make load SCENARIO=<ID>,"
echo "     ID one of CSCU, RETAIL, HEALTH, MFG) and re-register that scenario's two data"
echo "     sources — fastest via the app's bulk loader and the scenario's datasources CSV."
