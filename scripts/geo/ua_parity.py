#!/usr/bin/env python
"""T6 / closes L6 — classify the per-user-agent variant split as header-driven or
fingerprint-driven.

Why this exists
---------------
The 2026-10-08 pass measured `Googlebot` → 30,251 visible-text chars but
`GPTBot`/`Google-Extended`/`GoogleOther` → 11,627 (~62% less), with `Google-Extended` —
the token governing Gemini/Vertex grounding — on the *reduced* variant. Plain `curl`
cannot say whether that split is caused by the **User-Agent header** or by the
**TLS/JA3 fingerprint** (L6, GEO-TOOLING-PROPOSAL.md §1). Behind Cloudflare those are
different fixes with different owners: a header rule is a config decision, a
fingerprint rule is bot-management.

Method — a 2x2 factorial, so neither factor is confounded with the other:

                     | browser UA        | Googlebot UA
    -----------------+-------------------+--------------------
    Chrome TLS (JA3) | A (baseline)      | B
    plain curl TLS   | C                 | D

  * header-driven      → A != B  (same TLS, only the UA changed)
  * fingerprint-driven → A != C  (same UA, only the TLS changed)

Extra rows put the other AI-crawler UAs (GPTBot, GoogleOther, Google-CloudVertexBot,
Google-Extended) on the Chrome-TLS row so the reduced-variant membership list is
complete rather than a single sample.

Honesty rules baked in:
  * every row is repeated (`--repeats`, default 2) and the repeats are compared, so a
    flapping edge result is visible instead of averaged away;
  * `Vary` is recorded — if the origin declares `Vary: User-Agent` the split is
    intentional by definition, not an accident to be guessed at;
  * a non-200 is recorded as measured-with-status, never silently treated as content.

Usage
-----
    $KIT/tools/geo/.venv/bin/python scripts/geo/ua_parity.py --run-id <id> [--url https://bitara.co/]

Artifacts: <out>/ua-parity.json, <out>/raw/http/<variant>.{headers.json,html.gz}
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --- pinned identifiers -------------------------------------------------------------
# One fixed Chrome UA is used for every "browser UA" row so the UA is not a variable
# when we compare TLS profiles. The same string is sent by the plain-curl row.
CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
GOOGLEBOT_UA = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
                "Googlebot/2.1; +http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36")
GOOGLE_EXTENDED_UA = "Mozilla/5.0 (compatible; Google-Extended/1.0; +http://www.google.com/bot.html)"
GPTBOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot"
GOOGLEOTHER_UA = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
                  "GoogleOther/1.0; +http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36")
VERTEXBOT_UA = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
                "Google-CloudVertexBot/1.0; +http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36")

UA_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
              "Accept-Language": "en-US,en;q=0.9"}

# label, client, tls, ua, default_headers, note
VARIANTS = [
    ("ref_cffi_chrome_default", "cffi", "chrome", None, None,
     "reference: curl_cffi impersonating Chrome with its own UA/headers"),
    ("A_chromeTLS_chromeUA", "cffi", "chrome", CHROME_UA, False,
     "browser TLS + browser UA (factorial baseline)"),
    ("B_chromeTLS_googlebot", "cffi", "chrome", GOOGLEBOT_UA, False,
     "browser TLS + Googlebot UA -> the header-driven test"),
    ("B2_chromeTLS_googlebot_chromehdr", "cffi", "chrome", GOOGLEBOT_UA, True,
     "browser TLS + Googlebot UA + Chrome client hints (what a naive UA swap looks like)"),
    ("C_plainTLS_chromeUA", "curl", "plain", CHROME_UA, None,
     "plain curl TLS + browser UA -> the fingerprint-driven control"),
    ("D_plainTLS_googlebot", "curl", "plain", GOOGLEBOT_UA, None,
     "plain curl TLS + Googlebot UA (the row the 2026-10-08 pass is believed to have used)"),
    ("E_chromeTLS_gptbot", "cffi", "chrome", GPTBOT_UA, False, "reduced-variant membership"),
    ("F_chromeTLS_googleother", "cffi", "chrome", GOOGLEOTHER_UA, False, "reduced-variant membership"),
    ("G_chromeTLS_cloudvertexbot", "cffi", "chrome", VERTEXBOT_UA, False,
     "the UA the site's own robots.txt names for Vertex grounding"),
    ("H_chromeTLS_googleextended", "cffi", "chrome", GOOGLE_EXTENDED_UA, False,
     "[INFERRED] Google-Extended is a robots.txt token, not a documented request UA; "
     "included only because the prior pass measured this row"),
]

SCRIPT_TAG_RE = re.compile(r"<(script|style|noscript|template)\b.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r\f\v]+")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_RE = re.compile(r"<h1\b", re.I)
H2_RE = re.compile(r"<h2\b", re.I)


def log(msg: str) -> None:
    print(f"[ua] {msg}", flush=True)


def visible_text(raw: str) -> str:
    """Same reduction the 2026-10-08 pass used: drop script/style/noscript/template,
    then tags, so the numbers stay comparable with the documented baseline."""
    stripped = SCRIPT_TAG_RE.sub(" ", raw)
    stripped = TAG_RE.sub(" ", stripped)
    return WS_RE.sub(" ", html.unescape(stripped)).strip()


def summarise(raw_text: str, raw_bytes: bytes) -> dict:
    text = visible_text(raw_text)
    title = TITLE_RE.search(raw_text)
    return {
        "bytes": len(raw_bytes),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "visible_text_chars": len(text),
        "visible_text_words": len(text.split()),
        "title": html.unescape(title.group(1).strip()) if title else None,
        "h1_count": len(H1_RE.findall(raw_text)),
        "h2_count": len(H2_RE.findall(raw_text)),
        "anchor_count": len(re.findall(r"<a\b[^>]*href=", raw_text, re.I)),
        "script_count": len(re.findall(r"<script\b", raw_text, re.I)),
        "rsc_flight_chunks": raw_text.count("self.__next_f.push"),
        "next_static_assets": len(set(re.findall(r"/_next/static/[A-Za-z0-9._/-]+", raw_text))),
        "visible_text_head": text[:240],
    }


SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key",
    "x-auth-token", "x-amz-security-token", "cf-access-jwt-assertion",
}


def pick_headers(headers: dict) -> dict:
    """Record only headers that carry no credential material.

    This repository publishes its artifacts, so a captured header value is a published
    header value. The whitelist already excluded these names; the SENSITIVE_HEADERS check
    makes that guarantee explicit, so a future edit that adds a header to `wanted` for
    debugging cannot silently start writing tokens into reports/.

    Voluntarily self-constraining, not relying on a scanner: the CI secret scan
    (scripts/scan-secrets.sh) cannot inspect the gzipped bodies in raw/http/ at all.
    """
    wanted = ["cache-control", "cf-cache-status", "cf-ray", "vary", "etag", "last-modified",
              "content-encoding", "content-length", "content-type", "server", "link",
              "x-powered-by", "age", "expires", "date", "x-nextjs-cache", "x-vercel-cache"]
    lower = {k.lower(): v for k, v in headers.items()}
    picked = {k: lower[k] for k in wanted if k in lower and k not in SENSITIVE_HEADERS}
    picked["_all_names"] = sorted(lower.keys())
    # Names only — recorded so a reader can see that a credential-bearing header was
    # present and withheld, without the value ever reaching disk.
    picked["_redacted_headers"] = sorted(n for n in lower if n in SENSITIVE_HEADERS)
    picked["_vary_has_user_agent"] = "user-agent" in lower.get("vary", "").lower()
    return picked


def fetch_cffi(url: str, ua: str | None, default_headers, timeout: int = 45) -> dict:
    from curl_cffi import requests as cr

    kwargs = {"impersonate": "chrome", "timeout": timeout, "allow_redirects": True}
    if ua is not None:
        kwargs["headers"] = {"User-Agent": ua, **UA_HEADERS}
    if default_headers is not None and ua is not None:
        kwargs["default_headers"] = default_headers
    started = time.time()
    try:
        resp = cr.get(url, **kwargs)
    except TypeError as exc:  # pragma: no cover - older curl_cffi
        log(f"  default_headers unsupported ({exc}); retrying with impersonated headers")
        kwargs.pop("default_headers", None)
        resp = cr.get(url, **kwargs)
    return {
        "http_status": resp.status_code,
        "http_version": getattr(resp, "http_version", None),
        "elapsed_ms": int((time.time() - started) * 1000),
        "headers": dict(resp.headers),
        "body_bytes": resp.content,
        "final_url": str(resp.url),
    }


def fetch_curl(url: str, ua: str, timeout: int = 45) -> dict:
    """Plain system curl: no impersonation, so the TLS/JA3 is curl's own."""
    import tempfile

    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        body_path = Path(tmp) / "body"
        head_path = Path(tmp) / "head"
        cmd = ["curl", "-sS", "--compressed", "--http1.1", "-L", "--max-time", str(timeout),
               "-A", ua, "-H", f"Accept: {UA_HEADERS['Accept']}",
               "-H", f"Accept-Language: {UA_HEADERS['Accept-Language']}",
               # write-out gives the *final* status/version after redirects; parsing the
               # header dump for it fails because "HTTP/" also appears in the status line
               # itself ("HTTP/1.1 200 OK"), which yielded the literal "1.1".
               "-w", "%{http_code} %{http_version} %{size_download}",
               "-D", str(head_path), "-o", str(body_path), url]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        body = body_path.read_bytes() if body_path.exists() else b""
        raw_head = head_path.read_text(errors="replace") if head_path.exists() else ""

    headers = {}
    for line in raw_head.splitlines():
        if ":" in line and not line.lower().startswith("http/"):
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    parts = proc.stdout.strip().split()
    status = int(parts[0]) if parts and parts[0].isdigit() else None
    return {
        "http_status": status,
        "http_version": parts[1] if len(parts) > 1 else None,
        "download_bytes_reported": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None,
        "elapsed_ms": int((time.time() - started) * 1000),
        "headers": headers,
        "body_bytes": body,
        "final_url": url,
        "curl_stderr": proc.stderr.strip()[:300],
        "curl_command": " ".join(cmd[:6] + ["<UA>", url]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=os.environ.get("GEO_RUN_ID"))
    parser.add_argument("--out")
    parser.add_argument("--url", default="https://bitara.co/")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--only", default="", help="comma-separated variant labels to run")
    args = parser.parse_args()

    if not args.run_id:
        print("error: --run-id or GEO_RUN_ID is required", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path("reports/geo") / args.run_id
    raw_dir = out / "raw" / "http"
    raw_dir.mkdir(parents=True, exist_ok=True)

    import curl_cffi

    wanted = {v.strip() for v in args.only.split(",") if v.strip()}
    report = {
        "tool": "scripts/geo/ua_parity.py (T6 / closes L6)",
        "run_id": args.run_id,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "url": args.url,
        "repeats": args.repeats,
        "curl_cffi_version": curl_cffi.__version__,
        "impersonate_target": "chrome",
        "curl_version": subprocess.run(["curl", "--version"], capture_output=True, text=True)
                                .stdout.splitlines()[0],
        "chrome_ua_pinned": CHROME_UA,
        "variants": [],
        "analysis": {},
    }

    for label, client, tls, ua, default_headers, note in VARIANTS:
        if wanted and label not in wanted:
            continue
        samples = []
        for repeat in range(args.repeats):
            log(f"{label} repeat {repeat + 1}/{args.repeats}")
            try:
                if client == "cffi":
                    raw = fetch_cffi(args.url, ua, default_headers)
                else:
                    raw = fetch_curl(args.url, ua or CHROME_UA)
            except Exception as exc:
                samples.append({"repeat": repeat + 1, "error": repr(exc)[:400]})
                log(f"  ERROR {exc!r}")
                continue

            body_bytes = raw.pop("body_bytes")
            text = body_bytes.decode("utf-8", errors="replace")
            sample = {"repeat": repeat + 1, **raw, "headers": pick_headers(raw["headers"]),
                      **summarise(text, body_bytes)}
            samples.append(sample)
            with gzip.open(raw_dir / f"{label}__r{repeat + 1}.html.gz", "wb") as fh:
                fh.write(body_bytes)
        report["variants"].append({
            "label": label, "client": client, "tls_profile": tls, "note": note,
            "user_agent": ua, "default_headers": default_headers, "samples": samples,
        })

    # --- factorial analysis ----------------------------------------------------------
    # Byte hashes are NOT the instrument here: the page is dynamic, so two identical
    # requests hash differently (see identical_requests_differ_in_bytes). The stable
    # signal is the *content class* — the visible-text size — with repeat stability
    # reported alongside so a flapping result is visible rather than averaged away.
    def samples_of(label: str) -> list:
        variant = next((v for v in report["variants"] if v["label"] == label), None)
        return [s for s in (variant or {}).get("samples", []) if "error" not in s]

    def class_of(label: str) -> dict:
        ss = samples_of(label)
        if not ss:
            variant = next((v for v in report["variants"] if v["label"] == label), None)
            return {"measurable": False,
                    "reason": ((variant or {}).get("samples") or [{}])[0].get("error", "not run")}
        chars = [s["visible_text_chars"] for s in ss]
        return {
            "measurable": True,
            "visible_text_chars": chars,
            "content_class": chars[0],
            "content_stable_across_repeats": len(set(chars)) == 1,
            "byte_stable_across_repeats": len({s["sha256"] for s in ss}) == 1,
            "bytes": [s["bytes"] for s in ss],
        }

    ran = [v["label"] for v in report["variants"]]
    classes = {label: class_of(label) for label in ran}
    baseline = classes.get("A_chromeTLS_chromeUA", {"measurable": False})
    base_chars = baseline.get("content_class")
    reduced = sorted(l for l, c in classes.items()
                     if c["measurable"] and base_chars and c["content_class"] < 0.8 * base_chars)
    full = sorted(l for l, c in classes.items()
                  if c["measurable"] and base_chars and c["content_class"] >= 0.8 * base_chars)
    identical_requests_differ = any(not c["byte_stable_across_repeats"]
                                    for c in classes.values() if c["measurable"])
    header_driven = bool(reduced and baseline.get("content_stable_across_repeats"))

    fp_a, fp_c = classes.get("C_plainTLS_chromeUA", {}), classes.get("D_plainTLS_googlebot", {})
    fp_measurable = bool(fp_a.get("measurable") and fp_c.get("measurable"))
    fingerprint_test = {
        "measurable": fp_measurable,
        "reason_if_not": None if fp_measurable else {
            "C_plainTLS_chromeUA": fp_a.get("reason", "not run"),
            "D_plainTLS_googlebot": fp_c.get("reason", "not run")},
        "A_vs_C": {"A": baseline.get("visible_text_chars"), "C": fp_a.get("visible_text_chars")},
        "B_vs_D": {"B": classes.get("B_chromeTLS_googlebot", {}).get("content_class"),
                   "D": fp_c.get("content_class")},
    }
    fingerprint_driven = bool(
        fp_measurable and (
            fp_a.get("content_class") != base_chars
            or fp_c.get("content_class") != classes.get("B_chromeTLS_googlebot", {}).get("content_class")))

    vary_values = sorted({s.get("headers", {}).get("vary")
                          for v in report["variants"] for s in v["samples"]
                          if s.get("headers", {}).get("vary")})

    report["analysis"] = {
        "instrument": "visible_text_chars content class (raw bytes are per-request non-deterministic)",
        "identical_requests_differ_in_bytes": identical_requests_differ,
        "content_classes": {l: c.get("content_class") for l, c in classes.items()},
        "full_variant_labels": full,
        "reduced_variant_labels": reduced,
        "header_driven": header_driven,
        "fingerprint_driven": fingerprint_driven,
        "fingerprint_test_measurable": fp_measurable,
        "fingerprint_test": fingerprint_test,
        "vary_values_observed": vary_values,
        "origin_declares_vary_user_agent": any(
            s.get("headers", {}).get("_vary_has_user_agent")
            for v in report["variants"] for s in v["samples"]),
    }
    if header_driven and not fp_measurable:
        verdict = (f"HEADER-DRIVEN (confirmed): one TLS profile yields {len(full)} full-class and "
                   f"{len(reduced)} reduced-class response(s) purely by User-Agent — "
                   f"reduced={reduced}, full={full}. UA-conditional content switching, "
                   f"cloaking-adjacent. The fingerprint side is NOT MEASURED "
                   f"({fingerprint_test['reason_if_not']}), so 'fingerprint-driven' is neither "
                   f"confirmed nor excluded.")
    elif header_driven and fingerprint_driven:
        verdict = "BOTH header- and fingerprint-driven: two independent causes to fix."
    elif header_driven:
        verdict = ("HEADER-DRIVEN: same TLS profile, different content per User-Agent — "
                   "UA-conditional content switching (cloaking-adjacent); a rule to be found and owned.")
    elif not fp_measurable:
        verdict = ("NOT MEASURED: the fingerprint control (plain curl) failed and no reduced "
                   "class was found, so neither factor can be separated.")
    elif fingerprint_driven:
        verdict = ("FINGERPRINT-DRIVEN: same User-Agent, different content per TLS/HTTP client — "
                   "Cloudflare/bot-management is choosing the variant.")
    else:
        verdict = ("NO SPLIT REPRODUCED for this URL: identical content class across Chrome and "
                   "Googlebot UAs and across TLS profiles.")
    report["analysis"]["verdict"] = verdict
    log(f"verdict: {verdict}")

    (out / "ua-parity.json").write_text(json.dumps(report, indent=2, default=str))
    log(f"wrote {out / 'ua-parity.json'}")
    return 0 if (header_driven or fp_measurable) else 1


if __name__ == "__main__":
    sys.exit(main())
