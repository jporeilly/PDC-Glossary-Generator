#!/bin/bash
# Re-seed the css-auth-proxy provider record with the CURRENT EMAIL_DOMAINS
# (field-proven 2026-08-14: the working write path on PDC 11).
#
# Why not the documented API? The 10.2 doc's PUT {id, emailDomains} is
# accepted-and-ignored or rejected field-by-field on this build, because the
# domains actually live NESTED at provider_conf.emailDomains and the record
# is created whole by the um-css-admin-api-init container - which only runs
# on 404. So: edit EMAIL_DOMAINS in vendor/.env.default first, then run this
# ON THE VM. It repeats the init's own procedure - token, envsubst the raw
# config, DELETE the existing record, POST the fresh one - then verifies at
# the real JSON path. Secrets stay on the VM; nothing is echoed.
#
# Usage:
#   scp reseed-provider.sh pdc@192.168.1.200:/tmp/
#   ssh pdc@192.168.1.200 bash /tmp/reseed-provider.sh          # reseed
#   ssh pdc@192.168.1.200 bash /tmp/reseed-provider.sh verify   # read-only
# (or from Windows in one shot: remote\reseed-domains.ps1 [-VerifyOnly])
set -u
cd /opt/pentaho/pdc-docker-deployment

# conf FIRST: .env.default guards on GLOBAL_SERVER_HOST_NAME being set;
# conf AGAIN after, so its values beat any plain assignments in the defaults
set -a
. conf/.env
. vendor/.env.default
. conf/.env
set +a

export KEYCLOAK_USERNAME="$KEYCLOAK_USER"
export KEYCLOAK_URL="https://${GLOBAL_SERVER_HOST_NAME}/keycloak"
export SERVER_DOMAIN_IP="https://${GLOBAL_SERVER_HOST_NAME}/"
export SERVER_VAL_WITHOUT_SCHEME="${GLOBAL_SERVER_HOST_NAME}"
export TENANT_NAME PDC_CLIENT_NAME REALM_MANAGEMENT_CLIENT_NAME EMAIL_DOMAINS
export DEFAULT_ROLES_TENANT="${UM_DEFAULT_ROLES_TENANT}"
export VIEW_USERS_ROLE_NAME="${UM_VIEW_USERS_ROLE_NAME}"
API="https://${GLOBAL_SERVER_HOST_NAME}/css-admin-api/"

echo "== EMAIL_DOMAINS about to be seeded:"
echo "   $EMAIL_DOMAINS"

TOK=$(curl -s -k --location "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "username=${KEYCLOAK_USERNAME}" \
  --data-urlencode "password=${KEYCLOAK_PASSWORD}" \
  --data-urlencode "client_id=${KEYCLOAK_CLIENT_ID}" \
  --data-urlencode 'grant_type=password' \
  --data-urlencode 'scope=openid' | jq -r '.access_token')
if [ -z "$TOK" ] || [ "$TOK" = "null" ]; then echo "[x] token failed"; exit 1; fi
echo "== [ok] token minted"

envsubst < vendor/um/iam/pdc-providerConfig_raw.json > /tmp/pdc-providerConfig.json
grep -q 'azwater.gov' /tmp/pdc-providerConfig.json || { echo "[x] azwater.gov missing from templated config"; exit 1; }
echo "== [ok] config templated, azwater.gov present"

BEFORE=$(curl -s -k "${API}api/internal/css-auth-proxy/v1/provider/${SERVER_VAL_WITHOUT_SCHEME}" \
  --header "Authorization: Bearer ${TOK}")
echo "== provider before: $(echo "$BEFORE" | jq -c '.data.provider_conf.emailDomains // empty' 2>/dev/null)"

# read-only mode: report and stop - the runbook's verify step
if [ "${1:-}" = "verify" ]; then
  rm -f /tmp/pdc-providerConfig.json
  case "$(echo "$BEFORE" | jq -c '.data.provider_conf.emailDomains // empty' 2>/dev/null)" in
    *azwater.gov*) echo "== [ok] azwater.gov is on the safe list"; exit 0 ;;
    *) echo "== [x] azwater.gov NOT on the safe list - run without 'verify' to reseed"; exit 1 ;;
  esac
fi

# the PROVEN sequence on PDC 11: the record must be recreated whole - the
# init only creates on 404, and partial PUTs are ignored or rejected
echo "== DELETE existing record, POST fresh config"
curl -s -k -o /dev/null -X DELETE "${API}api/internal/css-auth-proxy/v1/provider/${SERVER_VAL_WITHOUT_SCHEME}" \
  --header "Authorization: Bearer ${TOK}"
RESP=$(curl -s -k --location "${API}api/internal/css-auth-proxy/v1/provider" \
  --header "Authorization: Bearer ${TOK}" \
  --header 'Content-Type: application/json' \
  --data '@/tmp/pdc-providerConfig.json')
echo "   POST response: $(echo "$RESP" | jq -c '{success, error}' 2>/dev/null || echo "$RESP" | head -c 200)"
OK=$(echo "$RESP" | jq -r '.success' 2>/dev/null)
if [ "$OK" != "true" ]; then echo "[x] create failed"; echo "$RESP" | head -c 400; exit 1; fi

AFTER=$(curl -s -k "${API}api/internal/css-auth-proxy/v1/provider/${SERVER_VAL_WITHOUT_SCHEME}" \
  --header "Authorization: Bearer ${TOK}")
LIST=$(echo "$AFTER" | jq -c '.data.provider_conf.emailDomains // empty' 2>/dev/null)
echo "== provider after: $LIST"
rm -f /tmp/pdc-providerConfig.json
case "$LIST" in
  *azwater.gov*) echo "== [ok] azwater.gov is on the safe list"; exit 0 ;;
  *) echo "== [x] azwater.gov still absent"; exit 1 ;;
esac
