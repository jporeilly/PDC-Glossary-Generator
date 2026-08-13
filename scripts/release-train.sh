#!/usr/bin/env bash
# The release train, with EXPLICIT guards on every step.
#
# Why not `set -e -o pipefail`: proven ineffective in the environment these
# trains run in — a multi-line script sailed straight past `pytest | tail -1`
# failing (1.37.6 shipped during a flaky suite failure; the collect-installer
# version guard was the only tripwire left). Guards you can see, on every
# step, with full output captured — never a truncated pipe deciding what the
# log gets to know.
#
# Usage: bash scripts/release-train.sh "commit message"
# Run from the repo root. Version comes from glossary_generator/VERSION —
# bump the six stamps and write the CHANGELOG entry BEFORE running this.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MSG="${1:?usage: release-train.sh \"commit message\"}"
VER="$(tr -d ' \r\n' < "$ROOT/glossary_generator/VERSION")"
LOG="$ROOT/dist/train-$VER.log"
mkdir -p "$ROOT/dist"

step() {  # step <name> <cmd...>: run, log fully, halt loudly on failure
  local name="$1"; shift
  echo "== $name" | tee -a "$LOG"
  if ! "$@" >> "$LOG" 2>&1; then
    echo "TRAIN_FAIL at $name — full output in $LOG (tail follows)"
    tail -30 "$LOG"
    exit 1
  fi
}

cd "$ROOT" || exit 1

step "cargo version sync" bash -c "cd desktop/src-tauri && cargo update -p pdc-glossary-desktop --offline"
step "frontend build"     npm --prefix frontend run build
step "test suite"         python -m pytest glossary_generator/tests -q
step "git add"            git add -A
step "git commit"         git commit -m "$MSG

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
step "git push"           git push origin main
step "lab tarball"        bash -c "cd ../PDC-Glossary-Lab && python scripts/make-tarball.py --checkout ../PDC-Glossary"
step "installer"          bash -c "cd desktop && npm run dist"

echo "TRAIN_OK $VER"
grep -E "installer ->|sha256" "$LOG" | tail -2
