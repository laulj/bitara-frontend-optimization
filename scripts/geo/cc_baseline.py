#!/usr/bin/env python
"""T5 / closes L5 — the Common Crawl baseline for bitara.co, reproducibly.

Why this exists
---------------
The 2026-10-08 manual pass hit a **504 Gateway Time-out** on one collection and had to
discover collection ids by hand from `collinfo.json`, so the headline finding
("Common Crawl has zero captures of bitara.co") was not yet trustworthy
(GEO-TOOLING-PROPOSAL.md §1, L5). This script removes both problems:

  * collections are **discovered** from `index.commoncrawl.org/collinfo.json`
    (through `cdx_toolkit.commoncrawl.get_cc_endpoints`), not hand-listed;
  * every request **retries with backoff**, and
  * every (collection, target) pair gets an explicit status, so a 5xx or a timeout can
    only ever be reported as `not-measured` — never as `no-captures`.

That last point is the kit's rule: *a skipped check is not a clean result*. A single
"no captures" line implies we proved absence, and we may only claim that for the
collections we actually got a definitive 404 from.

Usage
-----
    $KIT/tools/geo/.venv/bin/python scripts/geo/cc_baseline.py \
        --run-id 20261008-190000 [--targets bitara.co,bitara.com,...] [--max-collections 4]

Artifacts: <out>/cc-baseline.json, <out>/raw/cc/<collection>__<target>.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

CC_MIRROR = "https://index.commoncrawl.org"

# The two collections the original (untrustworthy) pass queried. Kept in the default
# set so the re-run is a like-for-like comparison, not a different question.
PRIOR_PASS_COLLECTIONS = ["CC-MAIN-2025-30", "CC-MAIN-2025-43"]

# From GEO-OPTIMIZATION-PROMPT.md "Verified baseline": bitara.com is a parked page,
# bitara.net is registered by others. They are measured as *conflation* evidence, so a
# model with a .com prior is shown to resolve somewhere real and wrong.
DEFAULT_TARGETS = ["bitara.co", "bitara.com", "bitara.net", "bitara.io"]

RETRY_STATUSES = {429, 500, 502, 503, 504}
ATTEMPTS = 4
BACKOFF_S = [2, 4, 8]
TIMEOUT_S = 45


def log(msg: str) -> None:
    print(f"[cc] {msg}", flush=True)


def discover_collections() -> tuple[list[str], str]:
    """Return every collection id Common Crawl advertises, newest first.

    Uses cdx-toolkit's own discovery so the id list is never hand-maintained; falls back
    to a direct collinfo.json fetch only if the toolkit raises.
    """
    try:
        from cdx_toolkit.commoncrawl import get_cc_endpoints

        endpoints = get_cc_endpoints(CC_MIRROR)
        ids = []
        for endpoint in endpoints:
            match = re.search(r"(CC-MAIN-\d{4}-\d+)", endpoint)
            if match:
                ids.append(match.group(1))
        if ids:
            return sorted(set(ids), reverse=True), "cdx_toolkit.commoncrawl.get_cc_endpoints"
    except Exception as exc:  # pragma: no cover - network dependent
        log(f"cdx-toolkit discovery failed ({exc!r}); falling back to a direct fetch")

    resp = requests.get(f"{CC_MIRROR}/collinfo.json", timeout=TIMEOUT_S)
    resp.raise_for_status()
    ids = [entry["id"] for entry in resp.json() if entry.get("id")]
    return sorted(set(ids), reverse=True), "requests GET collinfo.json (fallback)"


def probe(collection: str, target: str, raw_dir: Path, limit: int = 5) -> dict:
    """Query one collection for one target and classify the outcome honestly.

    Statuses:
      captures      200 with at least one parsed row
      no-captures   404 with Common Crawl's own "No Captures found" body (definitive)
      not-measured  anything else after ATTEMPTS tries (5xx, timeout, unparseable body)
    """
    url = f"{CC_MIRROR}/{collection}-index"
    params = {"url": target, "output": "json", "limit": str(limit)}
    record = {
        "collection": collection,
        "target": target,
        "endpoint": url,
        "attempts": [],
        "status": "not-measured",
        "captures": [],
        "capture_count": None,
        "reason": None,
    }
    raw_file = raw_dir / f"{collection}__{re.sub(r'[^A-Za-z0-9.-]', '_', target)}.json"

    for attempt in range(ATTEMPTS):
        started = time.time()
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT_S)
            body = resp.text
            elapsed_ms = int((time.time() - started) * 1000)
            record["attempts"].append(
                {"attempt": attempt + 1, "http_status": resp.status_code, "elapsed_ms": elapsed_ms,
                 "body_head": body[:300]}
            )

            if resp.status_code == 200 and body.lstrip().startswith(("{", "[")):
                rows = [json.loads(line) for line in body.splitlines()
                        if line.strip().startswith("{")]
                record["status"] = "captures" if rows else "no-captures"
                record["captures"] = rows[:limit]
                record["capture_count"] = len(rows)
                record["reason"] = "200 with captures" if rows else "200 but zero rows returned"
                raw_file.write_text(body)
                return record

            if resp.status_code == 404 and "No Captures found" in body:
                record["status"] = "no-captures"
                record["capture_count"] = 0
                record["reason"] = "404 No Captures found (definitive)"
                raw_file.write_text(body)
                return record

            record["reason"] = f"HTTP {resp.status_code}: {body[:160]}"
        except Exception as exc:
            record["attempts"].append({"attempt": attempt + 1, "http_status": None,
                                       "error": repr(exc)[:300]})
            record["reason"] = repr(exc)[:300]

        if attempt < ATTEMPTS - 1:
            time.sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])

    return record


def toolkit_detail(collection: str, target: str, limit: int = 5) -> dict:
    """Cross-check a 200 through cdx-toolkit's own code path (retries + pagination)."""
    try:
        import cdx_toolkit

        fetcher = cdx_toolkit.CDXFetcher(source="cc", crawl=collection)
        hits = fetcher.get(target, limit=limit)
        return {
            "tool": "cdx_toolkit.CDXFetcher.get",
            "version": getattr(cdx_toolkit, "__version__", "unknown"),
            "count": len(hits),
            "captures": [
                {k: getattr(hit, k, None) for k in
                 ("timestamp", "urlkey", "url", "mime", "status", "digest", "length")}
                for hit in hits[:limit]
            ],
        }
    except Exception as exc:
        return {"tool": "cdx_toolkit.CDXFetcher.get", "error": repr(exc)[:300], "count": None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=os.environ.get("GEO_RUN_ID"))
    parser.add_argument("--out")
    parser.add_argument("--targets", default=",".join(DEFAULT_TARGETS))
    parser.add_argument("--collections", default="")
    parser.add_argument("--max-collections", type=int, default=4,
                        help="how many of the newest collections to sample")
    args = parser.parse_args()

    if not args.run_id:
        print("error: --run-id or GEO_RUN_ID is required", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path("reports/geo") / args.run_id
    raw_dir = out / "raw" / "cc"
    raw_dir.mkdir(parents=True, exist_ok=True)

    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    advertised, discovery_method = discover_collections()
    log(f"{len(advertised)} collections advertised; discovered via {discovery_method}")

    if args.collections:
        collections = [c.strip() for c in args.collections.split(",") if c.strip()]
    else:
        newest = advertised[: args.max_collections]
        collections = list(dict.fromkeys(
            newest + [c for c in PRIOR_PASS_COLLECTIONS if c in advertised]))
        missing = [c for c in PRIOR_PASS_COLLECTIONS if c not in advertised]
        if missing:
            log(f"WARNING: prior-pass collections no longer advertised: {missing}")
    log(f"sampling {len(collections)}: {collections}")

    report = {
        "tool": "scripts/geo/cc_baseline.py (T5 / closes L5)",
        "run_id": args.run_id,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mirror": CC_MIRROR,
        "discovery_method": discovery_method,
        "collections_advertised": len(advertised),
        "collections_advertised_ids": advertised,
        "collections_sampled": collections,
        "coverage_note": (
            "absence is only claimed for the sampled collections; the remaining "
            f"{max(0, len(advertised) - len(collections))} advertised collections were not queried"
        ),
        "results": [],
    }

    # Newest collections get every target (including the .com/.net/.io conflation
    # neighbours); older ones only get bitara.co, to bound the request count.
    newest_two = set(advertised[:2])
    for collection in collections:
        wanted = targets if collection in newest_two else ["bitara.co"]
        for target in wanted:
            record = probe(collection, target, raw_dir)
            if record["status"] == "captures":
                record["toolkit_cross_check"] = toolkit_detail(collection, target)
            log(f"  {collection} {target}: {record['status']} "
                f"({record['capture_count'] if record['capture_count'] is not None else 'n/a'})")
            report["results"].append(record)

    definitive = [r for r in report["results"] if r["status"] == "no-captures"]
    with_hits = [r for r in report["results"] if r["status"] == "captures"]
    unmeasured = [r for r in report["results"] if r["status"] == "not-measured"]
    report["summary"] = {
        "no_captures_for_bitara_co": sorted(
            r["collection"] for r in definitive if r["target"] == "bitara.co"),
        "captures_for_bitara_co": {r["collection"]: r["capture_count"]
                                  for r in with_hits if r["target"] == "bitara.co"},
        "conflation_neighbours": {
            f"{r['collection']}:{r['target']}": r["status"]
            for r in report["results"] if r["target"] != "bitara.co"
        },
        "not_measured": [f"{r['collection']}:{r['target']} ({r['reason']})" for r in unmeasured],
        "verdict": None,
    }
    if report["summary"]["captures_for_bitara_co"]:
        report["summary"]["verdict"] = (
            "CAPTURES EXIST — the prior 'zero captures' finding does not reproduce.")
    else:
        # Residual uncertainty is judged per target. A 504 on a *conflation neighbour*
        # must not soften the bitara.co claim, and vice versa.
        cc_unmeasured = [f"{r['collection']}:{r['target']}" for r in unmeasured
                         if r["target"] == "bitara.co"]
        n_definitive = len(report["summary"]["no_captures_for_bitara_co"])
        if cc_unmeasured:
            report["summary"]["verdict"] = (
                f"PARTIAL for bitara.co — {n_definitive} collection(s) returned a definitive "
                f"404, but {len(cc_unmeasured)} could not be measured ({cc_unmeasured}), so "
                "'zero captures' is confirmed-with-residual-uncertainty, not closed.")
        else:
            report["summary"]["verdict"] = (
                f"CONFIRMED for bitara.co: {n_definitive} of {len(collections)} sampled "
                f"collection(s) returned a definitive 404 and none was unmeasurable "
                f"(n/a: {[f'{r['collection']}:{r['target']}' for r in unmeasured] or 'none'}).")
            if unmeasured:
                report["summary"]["verdict"] += (
                    " NOTE: a conflation-neighbour query was not measured; that affects the "
                    "neighbour claim only, not bitara.co.")

    (out / "cc-baseline.json").write_text(json.dumps(report, indent=2))
    log(f"verdict: {report['summary']['verdict']}")
    log(f"wrote {out / 'cc-baseline.json'}")
    return 0 if not unmeasured else 1


if __name__ == "__main__":
    sys.exit(main())
