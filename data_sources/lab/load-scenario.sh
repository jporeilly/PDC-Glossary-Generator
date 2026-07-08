#!/usr/bin/env bash
# ============================================================
#  PDC demo lab — scenario loader (runs on the Docker host)
#
#  Loads a scenario's data into the SHARED lab stack:
#    - PostgreSQL: creates the scenario's DATABASE, runs its
#      postgres-init/*.sql in name order (schema, tables, data,
#      read-only pdc_user + grants)
#    - MinIO: creates the scenario's BUCKET + read-only user,
#      uploads its documents folder
#    - verifies table and object counts
#
#  Scenarios are discovered from ../<ID>/scenario.json, so a
#  new scenario folder is loadable with no script changes.
#
#  Usage:   ./load-scenario.sh               # list scenarios
#           ./load-scenario.sh CSCU          # load one (several: CSCU <ID> ...)
#           ./load-scenario.sh --remove CSCU # drop its db + bucket
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || { echo "ERROR: .env not found — cp .env.example .env first"; exit 1; }
set -a; . ./.env; set +a

DS=..
command -v python3 >/dev/null 2>&1 && PY=python3 || PY=python
jget() { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get(sys.argv[2],''))" "$1" "$2"; }

PSQL_ADMIN() { docker exec -e PGPASSWORD="$PG_ADMIN_PASSWORD" -i "$PG_CONTAINER" psql -U "$PG_ADMIN_USER" "$@"; }
MC_RUN() { docker run --rm --network "$LAB_NETWORK" --entrypoint sh minio/mc -c \
  "mc alias set lab $MINIO_ENDPOINT $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD >/dev/null 2>&1 && $1"; }

list() {
  echo ""
  echo "  Scenarios found under data_sources/:"
  for m in "$DS"/*/scenario.json; do
    [ -f "$m" ] || continue
    printf "    %-6s %s — db %s · bucket %s\n" \
      "$(jget "$m" id)" "$(jget "$m" name)" "$(jget "$m" database)" "$(jget "$m" bucket)"
  done
  echo ""
  echo "  Load:    ./load-scenario.sh <ID> [<ID>...]"
  echo "  Remove:  ./load-scenario.sh --remove <ID>"
}

load_one() {
  local id="$1" m="$DS/$1/scenario.json"
  [ -f "$m" ] || { echo "ERROR: unknown scenario '$id' (no $m)"; exit 1; }
  local name db schema tables bucket docs muser
  name=$(jget "$m" name); db=$(jget "$m" database); schema=$(jget "$m" schema)
  tables=$(jget "$m" tables); bucket=$(jget "$m" bucket)
  docs="$DS/$id/$(jget "$m" documents_dir)"; muser=$(jget "$m" minio_user)

  echo ""
  echo "=== Loading $name ($id) into the shared lab ==="

  # ---- PostgreSQL: database ------------------------------------------------
  if [ "$(PSQL_ADMIN -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'")" = "1" ]; then
    echo "  = database $db already exists (re-running SQL is skipped — use --remove first to rebuild)"
  else
    PSQL_ADMIN -d postgres -c "CREATE DATABASE $db" >/dev/null
    echo "  + database $db created"
    for f in "$DS/$id"/postgres-init/*.sql; do
      [ -f "$f" ] || continue
      PSQL_ADMIN -d "$db" -v ON_ERROR_STOP=1 -q < "$f"
      echo "  + $(basename "$f") applied"
    done
  fi
  local COUNT
  COUNT=$(PSQL_ADMIN -d "$db" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='$schema' AND table_type='BASE TABLE'")
  if [ "$COUNT" -ge "$tables" ]; then
    echo "  ✓ $COUNT tables present in $db.$schema (expected $tables)"
  else
    echo "  ✗ expected $tables tables in $db.$schema, found $COUNT"; exit 1
  fi

  # ---- MinIO: bucket + read-only user + documents ---------------------------
  MC_RUN "mc mb -p lab/$bucket" >/dev/null && echo "  + bucket $bucket"
  MC_RUN "mc admin user add lab $muser $PDC_MINIO_SECRET 2>/dev/null || true
          printf '%s' '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:GetBucketLocation\"],\"Resource\":[\"arn:aws:s3:::$bucket/*\"]},{\"Effect\":\"Allow\",\"Action\":[\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::$bucket\"]}]}' > /tmp/ro.json
          mc admin policy create lab $bucket-readonly /tmp/ro.json 2>/dev/null
          mc admin policy attach lab $bucket-readonly --user $muser 2>/dev/null || true" >/dev/null
  echo "  + read-only user $muser (policy $bucket-readonly)"
  local DOCS_ABS EXPECTED UP
  DOCS_ABS=$(cd "$docs" && pwd)
  EXPECTED=$(find "$docs" -type f | wc -l | tr -d ' ')
  docker run --rm --network "$LAB_NETWORK" -v "$DOCS_ABS:/docs:ro" --entrypoint sh minio/mc -c \
    "mc alias set lab $MINIO_ENDPOINT $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD >/dev/null 2>&1 && mc cp --recursive /docs/ lab/$bucket/" >/dev/null
  UP=$(MC_RUN "mc ls --recursive lab/$bucket/" | grep -c . || true)
  if [ "$UP" -ge "$EXPECTED" ] && [ "$EXPECTED" -gt 0 ]; then
    echo "  ✓ $UP objects in $bucket (expected $EXPECTED)"
  else
    echo "  ✗ expected $EXPECTED objects in $bucket, found $UP"; exit 1
  fi

  echo "  === $id loaded — PDC values: db $db (schema $schema, pdc_user) · bucket $bucket ($muser) ==="
}

remove_one() {
  local id="$1" m="$DS/$1/scenario.json"
  [ -f "$m" ] || { echo "ERROR: unknown scenario '$id'"; exit 1; }
  local db bucket
  db=$(jget "$m" database); bucket=$(jget "$m" bucket)
  echo ""
  echo "=== Removing $id from the shared lab (database $db + bucket $bucket) ==="
  PSQL_ADMIN -d postgres -c "DROP DATABASE IF EXISTS $db WITH (FORCE)" >/dev/null && echo "  - database $db dropped"
  MC_RUN "mc rb --force lab/$bucket 2>/dev/null || true" >/dev/null && echo "  - bucket $bucket removed"
  echo "  (the read-only users are kept — harmless, reused on next load)"
}

case "${1:-}" in
  "")        list ;;
  --remove)  shift; [ $# -ge 1 ] || { echo "usage: ./load-scenario.sh --remove <ID>"; exit 1; }
             for id in "$@"; do remove_one "$id"; done ;;
  *)         for id in "$@"; do load_one "$id"; done ;;
esac
