#!/usr/bin/env bash
# Verify the pinned tool env before any measurement runs.
# Prints one line per check; exits 127 if a prerequisite is missing (the caller records
# that as `blocked`, not as a pass).
set -uo pipefail

REPO_ROOT=${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
PY=${PY:-$REPO_ROOT/.venv/bin/python}

if [ ! -x "$PY" ]; then
  echo "blocked: no python interpreter at $PY"
  echo "         fix: bash scripts/geo/bootstrap.sh   (creates the pinned 3.12 venv)"
  exit 127
fi

if ! "$PY" - <<'PY'
import sys
import importlib.metadata as md

print("python", sys.version.split()[0])
missing = []
for pkg in ("cdx-toolkit", "curl_cffi", "requests"):
    try:
        print("ok", pkg, md.version(pkg))
    except Exception:
        missing.append(pkg)
if missing:
    print("blocked: missing package(s):", ", ".join(missing))
    print("         fix: bash scripts/geo/bootstrap.sh")
    raise SystemExit(127)
PY
then
  exit 127
fi

"$PY" -m py_compile \
  "$REPO_ROOT/scripts/geo/cc_baseline.py" \
  "$REPO_ROOT/scripts/geo/ua_parity.py" \
  "$REPO_ROOT/scripts/geo/compare_innertext.py" \
  "$REPO_ROOT/scripts/geo/verify_fixes.py" || exit 1
echo "ok python syntax (cc_baseline, ua_parity, compare_innertext, verify_fixes)"

if command -v node >/dev/null 2>&1; then
  if node --check "$REPO_ROOT/scripts/geo/render_parity.mjs"; then
    echo "ok node $(node --version) + render_parity.mjs syntax"
  else
    echo "blocked: render_parity.mjs failed node --check"; exit 1
  fi
else
  echo "note: node not found — the rendered-DOM step will be recorded as blocked"
fi

# curl is used by the plain-TLS control rows of ua_parity.py.
if command -v curl >/dev/null 2>&1; then
  echo "ok $(curl --version | head -1)"
else
  echo "note: curl not found — the plain-TLS control rows will report an error"
fi

echo "preflight complete"
