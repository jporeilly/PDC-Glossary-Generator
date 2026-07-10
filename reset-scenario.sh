#!/usr/bin/env bash
# ============================================================
#  PDC Glossary Generator — scenario remover / app reset
#
#  Undoes install-scenario.sh: removes the installed scenario's
#  runtime files so the app is back to its clean, generic state.
#  Everything removed is first backed up beside itself with a
#  .backup-<timestamp> suffix (all git-ignored).
#
#  Default: removes the scenario config
#    - domain_pack.json      (the installed vocabulary)
#    - people.json           (the steward roster)
#    - tag_dictionary.json   (the persisted, seeded dictionary)
#    - datasources.csv       (the scenario's bulk-load connections)
#    - GLOSSARY_COMPANY in .env  (commented back out)
#
#  --all: ALSO removes the rest of the app's runtime state
#    - connections.json  settings.json  glossaries.json
#    - audit_log.json    registries/
#
#  Usage:   ./reset-scenario.sh          # scenario files only
#           ./reset-scenario.sh --all    # full runtime reset
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"
APP=glossary_generator
stamp=$(date +%Y%m%d-%H%M%S)

backup_rm() {  # backup_rm <file>
  if [ -f "$1" ]; then
    mv "$1" "$1.backup-$stamp"
    echo "  - $1  (backed up: $(basename "$1").backup-$stamp)"
  fi
}

echo ""
echo "Resetting the Glossary Generator to its clean, generic state"

backup_rm "$APP/domain_pack.json"
backup_rm "$APP/people.json"
backup_rm "$APP/tag_dictionary.json"
backup_rm "$APP/datasources.csv"

# comment GLOSSARY_COMPANY back out in .env (if present)
if [ -f "$APP/.env" ] && grep -q '^GLOSSARY_COMPANY=' "$APP/.env"; then
  sed -i.backup-"$stamp" 's/^GLOSSARY_COMPANY=/# GLOSSARY_COMPANY=/' "$APP/.env"
  echo "  ~ GLOSSARY_COMPANY commented out in $APP/.env"
fi

if [ "${1:-}" = "--all" ]; then
  echo ""
  echo "Full runtime reset (--all):"
  backup_rm "$APP/connections.json"
  backup_rm "$APP/settings.json"
  backup_rm "$APP/glossaries.json"
  backup_rm "$APP/audit_log.json"
  if [ -d "$APP/registries" ]; then
    mv "$APP/registries" "$APP/registries.backup-$stamp"
    echo "  - $APP/registries/  (backed up: registries.backup-$stamp)"
  fi
fi

echo ""
echo "Done. The app now runs generic (no scenario vocabulary, empty roster)."
echo "Install a scenario again with:  ./install-scenario.sh"
