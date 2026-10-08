#!/usr/bin/env bash
# Create the pinned Python 3.12 tool env this harness needs. No credentials required.
#
# The interpreter is pinned deliberately: the host default (3.14.x) is new enough that
# wheels for curl_cffi / cdx-toolkit may not resolve. See ADR-001.
#
# Usage:  bash scripts/geo/bootstrap.sh        # venv at $REPO/.venv
#         GEO_VENV=/somewhere bash scripts/geo/bootstrap.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GEO_VENV=${GEO_VENV:-$REPO_ROOT/.venv}
REQS="$REPO_ROOT/scripts/geo/requirements.txt"

echo "[bootstrap] repo      : $REPO_ROOT"
echo "[bootstrap] venv      : $GEO_VENV"
echo "[bootstrap] python    : 3.12 (pinned)"

if ! command -v uv >/dev/null 2>&1; then
  echo "[bootstrap] blocked: uv not installed — see https://docs.astral.sh/uv/" >&2
  exit 127
fi
if [ ! -f "$REQS" ]; then
  echo "[bootstrap] blocked: requirements file not found at $REQS" >&2
  exit 2
fi

uv venv "$GEO_VENV" --python 3.12 || exit 1
uv pip install --python "$GEO_VENV/bin/python" -r "$REQS" || exit 1

"$GEO_VENV/bin/python" - <<'PY'
import sys
import importlib.metadata as md
print("[bootstrap] python", sys.version.split()[0])
for pkg in ("cdx-toolkit", "curl_cffi", "requests", "google-genai", "anthropic"):
    try:
        print(f"[bootstrap]   ok {pkg} {md.version(pkg)}")
    except Exception as exc:                      # pragma: no cover
        print(f"[bootstrap]   MISSING {pkg}: {exc}")
PY

# Optional: the standalone cdx-toolkit CLIs (cdxt, cdx_iter, cdx_size). Only useful for
# ad-hoc corpus queries; the harness itself uses the library. uv warns when ~/.local/bin
# is not on PATH — that is expected and harmless.
if [ "${WITH_CDXT_CLI:-0}" = "1" ]; then
  echo "[bootstrap] installing cdx-toolkit CLIs (uv tool)…"
  uv tool install cdx-toolkit || echo "[bootstrap] warn: uv tool install failed (optional step)"
fi

echo "[bootstrap] done. Run: bash scripts/geo/run-geo.sh"
