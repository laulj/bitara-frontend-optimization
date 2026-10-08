#!/usr/bin/env bash
# Secret scan for THIS repository — one definition of "clean", shared by the local
# pre-push check, the CI workflow, and a human running it by hand.
#
# Wraps gitleaks (an existing CLI — no bespoke scanner) with this repository's rules in
# .gitleaks.toml. Reports land in reports/security/secret-scan-<runId>/.
#
# Usage:
#   bash scripts/scan-secrets.sh              # working tree only — fast, pre-commit
#   bash scripts/scan-secrets.sh --history    # + full git history — pre-push and CI
#
# Exit codes:  0 clean  ·  1 findings  ·  127 blocked (gitleaks not installed)
#
# The limit this tool cannot fix: gitleaks does not read binary files, so
# reports/**/raw/http/*.html.gz and *.png are invisible to it. Never commit a
# credential-bearing payload on the assumption that a scan covered it.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$REPO_ROOT/.gitleaks.toml"
MODE=${1:-}
RUN_ID=${GEO_RUN_ID:-$(date +%Y%m%d-%H%M%S)}
OUT="$REPO_ROOT/reports/security/secret-scan-$RUN_ID"
mkdir -p "$OUT"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "blocked: gitleaks not installed — see https://github.com/gitleaks/gitleaks (brew install gitleaks)" >&2
  exit 127
fi
if [ ! -f "$CONFIG" ]; then
  echo "blocked: config not found at $CONFIG" >&2
  exit 2
fi

echo "[scan] gitleaks $(gitleaks version 2>/dev/null | head -1)  config=${CONFIG#$REPO_ROOT/}"
echo "[scan] mode=${MODE:-tree}  reports=${OUT#$REPO_ROOT/}"

# --- 1. the working tree: what is about to be committed ------------------------------
gitleaks detect --no-git --source "$REPO_ROOT" --config "$CONFIG" \
  --redact --report-format sarif --report-path "$OUT/tree.sarif" --exit-code 1
tree_rc=$?

# --- 2. history: what is already committed -------------------------------------------
hist_rc=0
if [ "$MODE" = "--history" ]; then
  if git -C "$REPO_ROOT" rev-parse --verify HEAD >/dev/null 2>&1; then
    gitleaks detect --source "$REPO_ROOT" --config "$CONFIG" --log-opts=--all \
      --redact --report-format sarif --report-path "$OUT/history.sarif" --exit-code 1
    hist_rc=$?
  else
    echo "[scan] no commits yet — history scan NOT APPLICABLE (not a pass; run again after the first commit)"
  fi
fi

# --- 3. summary ----------------------------------------------------------------------
findings=0
tool_error=0
for report in "$OUT"/*.sarif; do
  [ -f "$report" ] || continue
  count=$(jq '[.runs[].results[]?] | length' "$report" 2>/dev/null || echo "?")
  echo "[scan] $(basename "$report"): ${count} finding(s)"
  [ "$count" = "?" ] || findings=$((findings + count))
done

for rc in "$tree_rc" "$hist_rc"; do
  [ "$rc" -gt 1 ] && tool_error=$rc
done

if [ "$tool_error" -ne 0 ]; then
  echo "[scan] BLOCKED: gitleaks exited $tool_error (scan error, not a clean result)" >&2
  exit "$tool_error"
fi
if [ "$findings" -gt 0 ]; then
  cat >&2 <<'EOF'
[scan] FAILED — findings above, redacted in the log.
       1. Treat the credential as compromised and ROTATE it first.
       2. Removing it from history is cleanup, not remediation: assume it was read.
       3. Inspect the full report (values are redacted there too, by design).
EOF
  exit 1
fi

echo "[scan] clean: no findings in the scanned scope"
