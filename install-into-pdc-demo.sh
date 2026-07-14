#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Glossary Generator — install/update the PDC-Demo lab checkout
#
# PDC-Demo IS this repo's checkout on the lab VM. This script:
#   - clones it (first run on a fresh VM) or fast-forward-pulls it
#   - clones/updates PDC-Scenarios inside it and pulls ONLY the selected
#     vertical (sparse): its data kit, domain pack and courseware
#   - detects the already-selected vertical from the sparse state, so a
#     bare re-run refreshes everything
#
#   ./install-into-pdc-demo.sh                     # uses ~/PDC-Demo
#   ./install-into-pdc-demo.sh CSCU                # select/switch vertical
#   ./install-into-pdc-demo.sh /path/to/PDC-Demo RETAIL
#   PDC_DEMO_DIR=/srv/PDC-Demo ./install-into-pdc-demo.sh
#
# One-liner on a fresh VM (no checkout needed):
#   curl -fsSL https://raw.githubusercontent.com/jporeilly/PDC-Glossary-Generator/main/install-into-pdc-demo.sh | bash -s -- CSCU
#
# The Policy Generator has the same script in its repo — run either; both
# keep the shared PDC-Scenarios checkout fresh.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_URL="${GLOSSARY_REPO_URL:-https://github.com/jporeilly/PDC-Glossary-Generator.git}"
SCEN_URL="${SCENARIOS_REPO_URL:-https://github.com/jporeilly/PDC-Scenarios.git}"

# --- colours (auto-off when not a TTY or NO_COLOR is set) ------------------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  B=$'\033[1m'; DIM=$'\033[2m'; RS=$'\033[0m'
  TEAL=$'\033[38;5;37m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'
else
  B=""; DIM=""; RS=""; TEAL=""; GREEN=""; YELLOW=""; RED=""
fi
ok(){   printf "  ${GREEN}✓${RS} %s\n" "$1"; }
warn(){ printf "  ${YELLOW}!${RS} %s\n" "$1"; }
die(){  printf "  ${RED}✗ %s${RS}\n" "$1" >&2; exit 1; }

DEMO="${PDC_DEMO_DIR:-$HOME/PDC-Demo}"
VERTICAL="${VERTICAL:-}"
for arg in "$@"; do
  if [ -d "$arg" ] || [ "${arg#/}" != "$arg" ] || [ "${arg#~}" != "$arg" ]; then DEMO="$arg"
  else VERTICAL="$(printf '%s' "$arg" | tr '[:lower:]' '[:upper:]')"
  fi
done

printf "\n${TEAL}${B}  Glossary Generator — install/update PDC-Demo${RS}\n"
printf "${DIM}  The lab checkout + the selected vertical from PDC-Scenarios.${RS}\n\n"

printf "${B}  Pre-flight${RS}\n"
command -v git >/dev/null 2>&1 || die "git is not installed."
ok "git $(git --version | awk '{print $3}')"

# --- the PDC-Demo checkout (this repo) ---------------------------------------
printf "${B}  PDC-Demo (Glossary checkout)${RS}\n"
if [ -d "$DEMO/.git" ]; then
  [ -d "$DEMO/glossary_generator" ] || die "$DEMO is a git checkout but not the Glossary repo"
  git -C "$DEMO" pull -q --ff-only || die "pull failed — local changes in $DEMO? Commit/stash them and re-run."
  ok "Updated to $(git -C "$DEMO" rev-parse --short HEAD)"
elif [ -e "$DEMO" ] && [ -n "$(ls -A "$DEMO" 2>/dev/null)" ]; then
  die "$DEMO exists but is not a git checkout — move it aside and re-run."
else
  printf "  ${DIM}first run — cloning…${RS}\n"
  git clone -q "$REPO_URL" "$DEMO"
  ok "Cloned to $DEMO"
fi
VER="$(cat "$DEMO/glossary_generator/VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
[ -n "$VER" ] && ok "App version: $VER"
echo

# --- vertical (PDC-Scenarios) -------------------------------------------------
printf "${B}  Vertical (PDC-Scenarios)${RS}\n"
SCEN_DIR="$DEMO/PDC-Scenarios"
if [ ! -d "$SCEN_DIR/.git" ] && [ -n "$VERTICAL" ]; then
  printf "  ${DIM}cloning PDC-Scenarios (sparse, %s only)…${RS}\n" "$VERTICAL"
  git -C "$DEMO" clone -q --filter=blob:none --no-checkout "$SCEN_URL" PDC-Scenarios
  git -C "$SCEN_DIR" sparse-checkout set "data_sources/lab" "data_sources/$VERTICAL" "courseware/$VERTICAL" "diagrams"
  git -C "$SCEN_DIR" checkout -q
  if ! grep -qx "PDC-Scenarios/" "$DEMO/.git/info/exclude" 2>/dev/null; then
    echo "PDC-Scenarios/" >> "$DEMO/.git/info/exclude"
  fi
fi
if [ -d "$SCEN_DIR/.git" ]; then
  git -C "$SCEN_DIR" pull -q --ff-only >/dev/null 2>&1 || warn "PDC-Scenarios pull failed (local changes?)"
  CUR="$(git -C "$SCEN_DIR" sparse-checkout list 2>/dev/null | sed -n 's#^data_sources/##p' | grep -v '^lab$' | head -1 || true)"
  [ -n "$VERTICAL" ] || VERTICAL="$CUR"
  if [ -n "$VERTICAL" ]; then
    if (cd "$SCEN_DIR" && bash select-vertical.sh "$VERTICAL" >/dev/null); then
      ok "Vertical $VERTICAL — data kit + domain pack + courseware pulled"
    else
      warn "select-vertical.sh $VERTICAL failed — is '$VERTICAL' a valid scenario id?"
    fi
  else
    warn "No vertical selected yet — pick one: $0 CSCU   (or RETAIL/HEALTH/MFG)"
  fi
  # migrate a lab .env stranded in the old in-repo location (pre-1.8.13)
  if [ -f "$DEMO/data_sources/lab/.env" ] && [ -d "$SCEN_DIR/data_sources/lab" ] \
     && [ ! -f "$SCEN_DIR/data_sources/lab/.env" ]; then
    cp "$DEMO/data_sources/lab/.env" "$SCEN_DIR/data_sources/lab/.env"
    ok "Migrated lab .env from the old data_sources/lab location"
  fi
else
  warn "No PDC-Scenarios checkout — pass a vertical to set one up: $0 CSCU"
fi
echo

printf "${B}  Next${RS}\n"
if [ -n "$VERTICAL" ] && [ -d "$SCEN_DIR" ]; then
  printf "  ${TEAL}1. Lab sources:  cd $SCEN_DIR/data_sources/lab && make up && make load SCENARIO=$VERTICAL${RS}\n"
  printf "  ${TEAL}2. Install pack: cd $SCEN_DIR && GLOSSARY_APP_DIR=$DEMO/glossary_generator ./install-scenario.sh $VERTICAL${RS}\n"
  printf "  ${TEAL}3. App:          cd $DEMO/glossary_generator && ./run.sh${RS}\n"
else
  printf "  ${TEAL}select a vertical first:  $0 CSCU${RS}\n"
fi
printf "  ${DIM}Policy Generator: its install-into-pdc-demo.sh installs the second app the same way.${RS}\n\n"
