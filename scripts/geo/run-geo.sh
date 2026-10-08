#!/usr/bin/env bash
# GEO measurement runner — the credential-free half of the bitara.co GEO engagement.
#
# Runs T5 (Common Crawl baseline), T6 (per-UA parity), the rendered-DOM cross-check and
# (when available) `wq probe`, all into one reports/geo/<runId>/ directory, and writes a
# manifest recording every step's exit code. A step that fails or cannot run is recorded
# as failed/blocked with its reason — never omitted. Rule: a skipped check is not a pass.
#
# Portable by design: no machine-specific paths. Locations are resolved from this file's
# own position and environment variables.
#
#   REPO_ROOT   auto-detected (this script's grandparent directory)
#   GEO_VENV    default $REPO_ROOT/.venv        (create it: scripts/geo/bootstrap.sh)
#   PY          default $GEO_VENV/bin/python
#   KIT         OPTIONAL path to a web-quality-kit checkout — only used for `wq probe`
#   URL         default https://bitara.co/
#   GEO_RUN_ID  default <timestamp>
#   GEO_OUT     default $REPO_ROOT/reports/geo/$GEO_RUN_ID
#
# Exit codes per step: 0 ok · 127 blocked (prerequisite missing) · other = failed.
#
# Usage:  bash scripts/geo/run-geo.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GEO_VENV=${GEO_VENV:-$REPO_ROOT/.venv}
PY=${PY:-$GEO_VENV/bin/python}
KIT=${KIT:-}
URL=${URL:-https://bitara.co/}
RUN_ID=${GEO_RUN_ID:-$(date +%Y%m%d-%H%M%S)}
OUT=${GEO_OUT:-$REPO_ROOT/reports/geo/$RUN_ID}
export GEO_RUN_ID="$RUN_ID"

mkdir -p "$OUT/raw" "$OUT/logs"
: > "$OUT/logs/steps.tsv"

log() { printf '[run-geo] %s\n' "$*"; }

record() {                                  # record <name> <code> <logfile>
  printf '%s\t%s\t%s\n' "$1" "$2" "$(basename "$3")" >> "$OUT/logs/steps.tsv"
  if [ "$2" -eq 0 ]; then log "OK      $1"
  elif [ "$2" -eq 127 ]; then log "BLOCKED $1 -> $3"
  else log "FAILED  $1 (exit $2) -> $3"; fi
}

step() {                                    # step <name> <logfile> <cmd...>
  local name=$1 logfile=$2; shift 2
  log "START $name"
  "$@" > "$logfile" 2>&1
  local code=$?
  record "$name" "$code" "$logfile"
  return 0                                  # keep going: one failure must not hide others
}

blocked() {                                 # blocked <name> <reason>
  local name=$1 reason=$2 logfile="$OUT/logs/$1.log"
  printf 'blocked: %s\n' "$reason" > "$logfile"
  record "$name" 127 "$logfile"
}

wq_available() {
  command -v wq >/dev/null 2>&1 && return 0
  [ -n "$KIT" ] && [ -f "$KIT/packages/cli/bin/wq.js" ] && return 0
  return 127
}

wq_probe() {
  if command -v wq >/dev/null 2>&1; then
    wq probe "$URL" --out "$OUT/probe-browser"
  else
    node "$KIT/packages/cli/bin/wq.js" probe "$URL" --out "$OUT/probe-browser"
  fi
}

log "runId=$RUN_ID  url=$URL"
log "repo=$REPO_ROOT"
log "venv=$GEO_VENV"
log "kit=${KIT:-<not set — the wq probe step will be recorded as blocked>}"

# --- 1. prerequisite + syntax gate ---------------------------------------------------
step "preflight_pinned_env" "$OUT/logs/preflight.log" \
  env PY="$PY" REPO_ROOT="$REPO_ROOT" bash "$REPO_ROOT/scripts/geo/preflight.sh"

# --- 2. T5 — Common Crawl baseline (no credentials) ---------------------------------
if [ -x "$PY" ]; then
  step "T5_common_crawl_baseline" "$OUT/logs/cc.log" \
    "$PY" "$REPO_ROOT/scripts/geo/cc_baseline.py" --run-id "$RUN_ID" --out "$OUT"
  step "T6_ua_parity" "$OUT/logs/ua-parity.log" \
    "$PY" "$REPO_ROOT/scripts/geo/ua_parity.py" --run-id "$RUN_ID" --out "$OUT" --url "$URL"
else
  blocked "T5_common_crawl_baseline" "no python at $PY — run: bash scripts/geo/bootstrap.sh"
  blocked "T6_ua_parity" "no python at $PY — run: bash scripts/geo/bootstrap.sh"
fi

# --- 3. Step 3d — rendered DOM cross-check (needs node + playwright) -----------------
if command -v node >/dev/null 2>&1; then
  step "step3d_render_parity" "$OUT/logs/render-parity.log" \
    env REPO_ROOT="$REPO_ROOT" KIT="$KIT" node "$REPO_ROOT/scripts/geo/render_parity.mjs" \
      --out "$OUT" --url "$URL"
else
  blocked "step3d_render_parity" "node not found on PATH"
fi

# --- 4. Optional — browser read-back via the kit's `wq probe` (0 tokens/request) -----
if wq_available; then
  step "wq_probe" "$OUT/logs/wq-probe.log" wq_probe
else
  blocked "wq_probe" "wq not on PATH and KIT not set — optional step (install web-quality-kit, or export KIT=/path/to/web-quality-kit)"
fi

# --- 5. manifest ----------------------------------------------------------------------
# Written by whatever python is available, so the manifest exists even when the pinned
# env does not. All paths inside are relative to the run directory on purpose: the
# manifest travels with the repo and must not leak the machine it was produced on.
PY_MANIFEST=$([ -x "$PY" ] && echo "$PY" || echo python3)

"$PY_MANIFEST" - "$OUT" "$RUN_ID" "$URL" <<'PY'
import datetime
import json
import pathlib
import subprocess
import sys

out, run_id, url = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]


def first_line(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()[0]
    except Exception:
        return "unavailable"


steps = []
for line in (out / "logs" / "steps.tsv").read_text().splitlines():
    if not line.strip():
        continue
    name, code, logname = line.split("\t")
    code = int(code)
    steps.append({
        "step": name,
        "exit_code": code,
        "status": "ok" if code == 0 else ("blocked" if code == 127 else "failed"),
        "log": f"logs/{logname}",
    })


def load(name):
    path = out / name
    return json.loads(path.read_text()) if path.exists() else None


manifest = {
    "run_id": run_id,
    "url": url,
    "measured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "paths_relative_to": "the repository root (no machine-specific paths are recorded)",
    "env": {
        "uv": first_line(["uv", "--version"]),
        "python_host": first_line(["python3", "--version"]),
        "node": first_line(["node", "--version"]),
    },
    "steps": steps,
    "artifacts": sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()),
    "readings": {},
    "blocked_without_credentials": [
        "L1 Google index status — needs GSC property access (owner: client)",
        "L2 Bing index status — needs Bing Webmaster key (owner: client)",
        "L3 site: counts — needs Google CSE key + CX (owner: client)",
        "L4 citation probing — needs GOOGLE_API_KEY / ANTHROPIC_API_KEY (owner: client)",
        "L7 Cloudflare-side cause — needs CLOUDFLARE_API_TOKEN + zone (owner: client)",
    ],
}

cc, ua, rp = load("cc-baseline.json"), load("ua-parity.json"), load("render-parity.json")
if cc:
    manifest["readings"]["common_crawl"] = cc.get("summary")
if ua:
    manifest["readings"]["ua_parity"] = {
        "header_driven": ua["analysis"].get("header_driven"),
        "fingerprint_driven": ua["analysis"].get("fingerprint_driven"),
        "fingerprint_test_measurable": ua["analysis"].get("fingerprint_test_measurable"),
        "content_classes": ua["analysis"].get("content_classes"),
        "full_variant_labels": ua["analysis"].get("full_variant_labels"),
        "reduced_variant_labels": ua["analysis"].get("reduced_variant_labels"),
        "origin_declares_vary_user_agent": ua["analysis"].get("origin_declares_vary_user_agent"),
        "verdict": ua["analysis"].get("verdict"),
    }
if rp:
    manifest["readings"]["render_parity"] = rp.get("analysis")

(out / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest["readings"], indent=2))
PY

log "wrote $OUT/manifest.json"
log "step status:"
awk -F'\t' '{ printf "  %-28s %s\n", $1, ($2=="0" ? "ok" : ($2=="127" ? "BLOCKED" : "FAILED("$2")")) }' "$OUT/logs/steps.tsv"
log "artifacts:"
find "$OUT" -type f | sed "s|$OUT/|  |" | sort | head -40
