#!/usr/bin/env bash
# Verify what can be verified about whether the GEO fixes landed — from a fresh clone, with no
# client credentials. See scripts/geo/verify_fixes.py for what each check means.
#
#   bash scripts/geo/verify-fixes.sh                 # human-readable table
#   bash scripts/geo/verify-fixes.sh --json          # machine-readable (for CI or a diff)
#   bash scripts/geo/verify-fixes.sh --only P0-1     # one task
#
# Exit: 0 no measurable check failed · 1 at least one fix is missing · 2 environment not bootstrapped
#       · 3 the target was unreachable (nothing verified — not a clean result)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GEO_VENV=${GEO_VENV:-$REPO_ROOT/.venv}
PY=${PY:-$GEO_VENV/bin/python}

if [ ! -x "$PY" ]; then
  echo "blocked: no python interpreter at $PY"
  echo "         fix: bash scripts/geo/bootstrap.sh   (creates the pinned 3.12 venv)"
  exit 2
fi

exec "$PY" "$REPO_ROOT/scripts/geo/verify_fixes.py" "$@"
