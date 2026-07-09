#!/usr/bin/env bash
# ============================================================
#  PDC Glossary Generator — scenario installer
#
#  Lists the scenarios under data_sources/ (anything with a
#  scenario.json), lets you pick one (or pass its id), then
#  installs that scenario's files into the app's RUNTIME config.
#  The app itself (code, git tree) is never touched — these are
#  all git-ignored runtime files:
#
#    - domain_pack.json   <- the scenario vocabulary
#    - people.json        <- the steward roster seed
#    - .env               <- GLOSSARY_COMPANY set
#    - tag_dictionary.json backed up + removed (forces reseed)
#
#  Usage:   ./install-scenario.sh          # interactive menu
#           ./install-scenario.sh CSCU     # direct (or RETAIL)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

APP=glossary_generator
DS=data_sources
command -v python3 >/dev/null 2>&1 && PY=python3 || PY=python

# JSON field reader (no jq dependency)
jget() { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8')).get(sys.argv[2],''))" "$1" "$2"; }

# ---- discover scenarios -----------------------------------------------------
ids=()
for m in "$DS"/*/scenario.json; do
  [ -f "$m" ] || continue
  ids+=("$(jget "$m" id)")
done
[ ${#ids[@]} -gt 0 ] || { echo "No scenarios found under $DS/"; exit 1; }

# ---- pick one ---------------------------------------------------------------
choice="${1:-}"
if [ -z "$choice" ]; then
  echo ""
  echo "  PDC Glossary Generator — available scenarios"
  echo ""
  i=1
  for id in "${ids[@]}"; do
    m="$DS/$id/scenario.json"
    printf "  %d) %-6s %s — %s\n" "$i" "$id" "$(jget "$m" name)" "$(jget "$m" industry)"
    printf "     %s\n" "$(jget "$m" description)"
    i=$((i+1))
  done
  echo ""
  read -rp "  Select a scenario [1-${#ids[@]}]: " n
  case "$n" in (*[!0-9]*|'') echo "Not a number."; exit 1;; esac
  [ "$n" -ge 1 ] && [ "$n" -le ${#ids[@]} ] || { echo "Out of range."; exit 1; }
  choice="${ids[$((n-1))]}"
fi

m="$DS/$choice/scenario.json"
[ -f "$m" ] || { echo "Unknown scenario '$choice' (no $m)"; exit 1; }
name=$(jget "$m" name); company=$(jget "$m" company)
pack="$DS/$choice/$(jget "$m" pack)"; people="$DS/$choice/$(jget "$m" people)"
[ -f "$pack" ]   || { echo "Pack not found: $pack"; exit 1; }
[ -f "$people" ] || { echo "Roster not found: $people"; exit 1; }

echo ""
echo "Installing scenario: $name"
stamp=$(date +%Y%m%d-%H%M%S)

# ---- 1. domain pack ---------------------------------------------------------
[ -f "$APP/domain_pack.json" ] && cp "$APP/domain_pack.json" "$APP/domain_pack.json.backup-$stamp"
cp "$pack" "$APP/domain_pack.json"
echo "  + $APP/domain_pack.json"

# ---- 2. steward roster (backs up an existing one) ---------------------------
if [ -f "$APP/people.json" ]; then
  cp "$APP/people.json" "$APP/people.json.backup-$stamp"
  echo "  ~ existing people.json backed up (people.json.backup-$stamp)"
fi
cp "$people" "$APP/people.json"
echo "  + $APP/people.json"

# ---- 3. force a dictionary reseed from the new pack -------------------------
if [ -f "$APP/tag_dictionary.json" ]; then
  mv "$APP/tag_dictionary.json" "$APP/tag_dictionary.json.backup-$stamp"
  echo "  ~ tag_dictionary.json backed up + removed (reseeds on next start)"
fi

# ---- 4. GLOSSARY_COMPANY in .env ---------------------------------------------
env_file="$APP/.env"
[ -f "$env_file" ] || { [ -f "$APP/.env.example" ] && cp "$APP/.env.example" "$env_file"; }
touch "$env_file"
if grep -q "^[#[:space:]]*GLOSSARY_COMPANY=" "$env_file"; then
  "$PY" - "$env_file" "$company" <<'PYEOF'
import io, re, sys
p, company = sys.argv[1], sys.argv[2]
s = io.open(p, encoding="utf-8").read()
s = re.sub(r"(?m)^[#\s]*GLOSSARY_COMPANY=.*$", 'GLOSSARY_COMPANY="%s"' % company, s, count=1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
PYEOF
else
  printf '\nGLOSSARY_COMPANY="%s"\n' "$company" >> "$env_file"
fi
echo "  + GLOSSARY_COMPANY=\"$company\"  ($env_file)"

echo ""
echo "Done. Next steps:"
echo "  1. Stand up the lab:      cd $DS/lab && make up && make load SCENARIO=$choice"
echo "  2. Start the app:         cd $APP && ./run.sh"
echo "  3. In the app:            Dictionary page -> confirm the vocabulary reseeded"
echo "  4. Courseware:            $(jget "$m" courseware)/"
echo ""
echo "One scenario at a time — rerun this script to switch (it backs everything up)."
