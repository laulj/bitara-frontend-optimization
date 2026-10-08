#!/usr/bin/env python
"""Verify what CAN be verified about whether the GEO fixes landed — from outside, no client
credentials required.

This is the executable form of Phase 4 in `GEO-OPTIMIZATION-PROMPT.md`, mapped onto the task
IDs in `docs/GEO-FIX-PLAN.md`. Every check reports one of:

    PASS      measured, and the fix is in place
    FAIL      measured, and the fix is NOT in place
    BLOCKED   could not be measured (missing credential / unreachable / needs a browser).
              BLOCKED is NOT a pass — it means "unknown", and it names who can unblock it.
    ADVISORY  a heuristic judgement call (e.g. "does the first sentence answer the question?").
              Reported for a human to read; it never fails the run.

Exit codes:  0 every measurable check passed
             1 at least one measurable check FAILED
             2 no interpreter/dependency (run scripts/geo/bootstrap.sh)
             3 the target was unreachable (nothing was verified — not a clean result)

What this CANNOT verify, and says so out loud: whether Google or Bing have indexed the site,
and whether Gemini/ChatGPT/Perplexity now cite it. Those need client credentials (or a human
pasting prompts into a chat app). No amount of on-page checking substitutes for them, so the
script prints them as BLOCKED with an owner instead of implying the engine question is settled.

Usage:
    bash scripts/geo/verify-fixes.sh                       # human-readable table
    bash scripts/geo/verify-fixes.sh --json                # machine-readable only
    bash scripts/geo/verify-fixes.sh --url https://… --baseline reports/geo/<runId>
    bash scripts/geo/verify-fixes.sh --only P0-1,P0-2      # a subset, by task id

Artifacts: reports/verify/<runId>/{verified.json, verification.md, samples/}
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
GOOGLEBOT_UA = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; "
                "+http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36")
GPTBOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot"
GOOGLEOTHER_UA = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GoogleOther/1.0; "
                  "+http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36")
GOOGLE_EXTENDED_UA = "Mozilla/5.0 (compatible; Google-Extended/1.0; +http://www.google.com/bot.html)"
VERTEXBOT_UA = ("Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; "
                "Google-CloudVertexBot/1.0; +http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36")

# The UAs the 2026-10-08 baseline found on the reduced variant, plus the two that got the full
# page (controls). A fix is verified when this whole set lands on one content class.
UA_MATRIX = [
    ("Chrome (control)", CHROME_UA),
    ("Googlebot (control)", GOOGLEBOT_UA),
    ("GPTBot", GPTBOT_UA),
    ("GoogleOther", GOOGLEOTHER_UA),
    ("Google-Extended", GOOGLE_EXTENDED_UA),
    ("Google-CloudVertexBot", VERTEXBOT_UA),
]

UA_HEADERS = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
              "Accept-Language": "en-US,en;q=0.9"}
SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}

SCRIPT_TAG_RE = re.compile(r"<(script|style|noscript|template)\b.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r\f\v]+")
LD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def log(msg: str) -> None:
    print(msg, flush=True)


def visible_text(html: str) -> str:
    """Same reduction as the baseline harness, so numbers are comparable with the committed run."""
    text = SCRIPT_TAG_RE.sub(" ", html)
    text = TAG_RE.sub(" ", text)
    import html as html_mod
    return WS_RE.sub(" ", html_mod.unescape(text)).strip()


def fetch(url: str, ua: str | None = None, timeout: int = 45) -> dict:
    """One HTTP request with a browser-like TLS profile (the baseline's method)."""
    from curl_cffi import requests as cr

    kwargs: dict = {"timeout": timeout, "allow_redirects": True, "impersonate": "chrome"}
    if ua:
        kwargs["headers"] = {"User-Agent": ua, **UA_HEADERS}
        # Drop the impersonated browser's own headers so a bot UA is not mixed with Chrome
        # client hints — the same isolation the baseline harness used.
        kwargs["default_headers"] = False
    started = time.time()
    try:
        resp = cr.get(url, **kwargs)
        body = resp.content
        return {
            "ok": resp.status_code == 200,
            "status": resp.status_code,
            "headers": {k.lower(): v for k, v in dict(resp.headers).items()},
            "text": body.decode("utf-8", errors="replace"),
            "bytes": len(body),
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:
        return {"ok": False, "status": None, "headers": {}, "text": "", "bytes": 0,
                "error": repr(exc)[:300],
                "elapsed_ms": int((time.time() - started) * 1000)}


class Results:
    """Collects check outcomes. BLOCKED and ADVISORY are first-class, not silent."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, check_id: str, task: str, title: str, status: str,
            expected: str = "", measured: str = "", detail: str = "") -> None:
        assert status in {"PASS", "FAIL", "BLOCKED", "ADVISORY", "INFO"}, status
        self.items.append({"check": check_id, "task": task, "title": title, "status": status,
                           "expected": expected, "measured": measured, "detail": detail})
        icon = {"PASS": "✓", "FAIL": "✗", "BLOCKED": "■", "ADVISORY": "~", "INFO": "·"}[status]
        log(f"  {icon} [{task}] {title}: {status}"
            + (f" — measured={measured}" if measured else "")
            + (f" (expected {expected})" if expected and status == "FAIL" else ""))

    def counts(self) -> dict:
        out = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "ADVISORY": 0, "INFO": 0}
        for item in self.items:
            out[item["status"]] += 1
        return out


def parse_json_ld(html: str) -> list:
    blocks = []
    for raw in LD_RE.findall(html):
        try:
            blocks.append(json.loads(raw))
        except Exception:
            continue
    return blocks


def flatten_json_ld(blocks: list) -> str:
    return json.dumps(blocks, ensure_ascii=False)


def head_hreflangs(html: str) -> set[str]:
    """Real <link rel="alternate" hreflang=...> tags only.

    Next.js streams page metadata into the RSC flight payload too, so a naive `hreflang="…"`
    regex over the head matches the serialised copy inside a <script> and reports locales that
    are not actually link tags. Strip scripts first, then require both attributes on a <link>.
    """
    head = html.split("</head>", 1)[0] if "</head>" in html else html
    head = SCRIPT_TAG_RE.sub(" ", head)
    found = set()
    for tag in re.findall(r"<link\b[^>]*>", head, re.I):
        if not re.search(r'rel=["\']?alternate', tag, re.I):
            continue
        match = re.search(r'hreflang=["\']([^"\']+)', tag, re.I)
        if match:
            found.add(match.group(1))
    return found


def sitemap_locales(sitemap_xml: str) -> set[str]:
    return set(re.findall(r'hreflang=["\']([^"\']+)["\']', sitemap_xml, re.I))


def sitemap_urls(sitemap_xml: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap_xml)


def load_baseline(repo_root: Path, explicit: str | None) -> tuple[dict | None, str]:
    """The committed earlier run, used to show movement rather than just current state.

    Returns (data, reference) so the report names which run it compared against — a bare
    "baseline: None" in a report is a bug: it hides whether any comparison happened.
    """
    if explicit:
        given = Path(explicit)
        path = given / "manifest.json" if given.is_dir() else given
        if path.exists():
            return json.loads(path.read_text()), str(given)
        return None, f"{explicit} (not found)"
    candidates = sorted((repo_root / "reports" / "geo").glob("*/manifest.json"))
    if not candidates:
        return None, "none found — run scripts/geo/run-geo.sh to create one"
    latest = candidates[-1]
    return json.loads(latest.read_text()), f"latest committed run ({latest.parent.name})"


# --- P0-1: the per-User-Agent content split -------------------------------------------------
def check_crawler_parity(base: str, res: Results, samples: Path, baseline: dict | None) -> None:
    classes, blocked, meta = {}, [], {}
    for label, ua in UA_MATRIX:
        r = fetch(f"{base}/", ua=ua)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", label).strip("-").lower()
        if not r["ok"]:
            blocked.append(f"{label}=HTTP {r['status']}")
            (samples / f"ua-{slug}.json").write_text(json.dumps(
                {"label": label, "status": r["status"], "error": r.get("error")}, indent=2))
            continue
        text = visible_text(r["text"])
        classes[label] = len(text)
        title_match = re.search(r"<title[^>]*>(.*?)</title>", r["text"], re.S | re.I)
        meta[label] = {"label": label, "status": r["status"], "bytes": r["bytes"],
                       "visible_text_chars": len(text),
                       "title": title_match.group(1) if title_match else None,
                       "visible_text_head": text[:200], "vary": r["headers"].get("vary")}
        (samples / f"ua-{slug}.json").write_text(json.dumps(meta[label], indent=2))

    control = classes.get("Chrome (control)")
    if not control:
        res.add("crawler-parity", "P0-1", "Every AI crawler receives the same page as Chrome",
                "BLOCKED", detail="the Chrome control could not be fetched, so nothing can be compared")
        return

    reduced = {k: v for k, v in classes.items() if v < 0.98 * control}
    measured = ", ".join(f"{k}={v}" for k, v in sorted(classes.items(), key=lambda kv: kv[1]))

    if reduced:
        res.add("crawler-parity", "P0-1", "Every AI crawler receives the same page as Chrome",
                "FAIL", expected=f"all == {control} visible-text chars", measured=measured,
                detail="reduced variant still served to: " + ", ".join(
                    f"{k} ({v} chars, {v / control:.0%} of Chrome)" for k, v in reduced.items()))
    elif blocked:
        res.add("crawler-parity", "P0-1", "Every AI crawler receives the same page as Chrome",
                "BLOCKED", expected=f"all == {control} visible-text chars", measured=measured,
                detail="not measured for: " + "; ".join(blocked))
    else:
        res.add("crawler-parity", "P0-1", "Every AI crawler receives the same page as Chrome",
                "PASS", measured=f"all {len(classes)} UAs == {control} chars")

    # Honesty check: if a split exists it MUST be advertised, or a cache can serve the wrong
    # variant to the wrong client — a cache-poisoning hazard independent of the cloaking policy.
    vary = next((m["vary"] for m in meta.values() if m.get("vary")), "") or ""
    if reduced:
        advertised = "user-agent" in vary.lower()
        res.add("crawler-parity-vary", "P0-1", "UA-dependent variance is advertised (Vary)",
                "PASS" if advertised else "FAIL",
                expected="Vary: User-Agent", measured=vary or "(no Vary header)",
                detail="" if advertised else
                       "a variant the response does not advertise can be cached and served to the wrong client")
    else:
        res.add("crawler-parity-vary", "P0-1", "UA-dependent variance is advertised (Vary)", "INFO",
                measured=vary or "(no Vary header)",
                detail="no split measured, so there is no variance to advertise")

    prior = ((baseline or {}).get("readings", {}).get("ua_parity", {}) or {}).get("content_classes") or {}
    if prior:
        res.add("crawler-parity-movement", "P0-1", "Movement since the baseline run", "INFO",
                measured=f"baseline={sorted(set(prior.values()))} → now={sorted(set(classes.values()))}",
                detail="baseline reduced-class UAs: " + ", ".join(
                    k for k, v in prior.items() if v == min(prior.values())))


# --- P0-2: cache validators and cacheability ------------------------------------------------
def check_caching(base: str, res: Results, samples: Path) -> None:
    first = fetch(f"{base}/")
    if not first["ok"] or not first["headers"]:
        res.add("cache-validators", "P0-2", "Cache validators (ETag / Last-Modified)", "BLOCKED",
                detail=f"homepage not fetchable (HTTP {first['status']})")
        return

    h = first["headers"]
    (samples / "home-response-headers.json").write_text(json.dumps(
        {k: v for k, v in sorted(h.items()) if k not in SENSITIVE_HEADERS}, indent=2))

    etag, lastmod = h.get("etag"), h.get("last-modified")
    res.add("cache-validators", "P0-2", "Cache validators (ETag / Last-Modified)",
            "PASS" if (etag or lastmod) else "FAIL",
            expected="ETag and/or Last-Modified",
            measured=f"etag={etag or 'absent'}, last-modified={lastmod or 'absent'}",
            detail="" if (etag or lastmod) else
                   "without validators a crawler cannot revalidate cheaply, which throttles recrawl")

    cc = h.get("cache-control", "")
    has_maxage = bool(re.search(r"(s-maxage|max-age)\s*=\s*[1-9]", cc))
    no_store = "no-store" in cc.lower()
    res.add("cache-control", "P0-2", "Cacheable: max-age set and no blanket no-store",
            "PASS" if (has_maxage and not no_store) else "FAIL",
            expected="public with max-age/s-maxage, no no-store",
            measured=cc or "(no Cache-Control header)",
            detail="" if (has_maxage and not no_store) else
                   ("blanket no-store: neither the edge nor a crawler may cache anything"
                    if no_store else "no non-zero max-age/s-maxage found"))

    second = fetch(f"{base}/")
    edge = (second["headers"].get("cf-cache-status")
            or second["headers"].get("x-vercel-cache")
            or (f"age={second['headers']['age']}" if "age" in second["headers"] else ""))
    edge_ok = bool(re.match(r"(HIT|REVALIDATED|STALE)", edge or "", re.I))
    res.add("edge-cacheability", "P0-2", "Second request served from the edge cache",
            "PASS" if edge_ok else "FAIL", expected="cf-cache-status HIT or REVALIDATED",
            measured=edge or "(no edge cache header)",
            detail="" if edge_ok else
                   "the edge re-fetches the origin on every crawl — note this can also be a Cloudflare "
                   "zone setting rather than an origin code change")


# --- P0-3: entity identity and disambiguation ------------------------------------------------
IDENTITY_PATHS = ["/", "/about"]


def check_entity_identity(base: str, res: Results, samples: Path) -> None:
    missing, checked, identifiers = [], 0, False
    for path in IDENTITY_PATHS:
        r = fetch(f"{base}{path}")
        if not r["ok"]:
            missing.append(f"{path}=HTTP {r['status']}")
            continue
        checked += 1
        flat = flatten_json_ld(parse_json_ld(r["text"]))
        (samples / f"jsonld{path.replace('/', '_') or '_root'}.json").write_text(flat or "[]")
        for field in ("disambiguatingDescription", "sameAs"):
            if field not in flat:
                missing.append(f"{path}:{field}")
        if "202201037451" in flat:
            identifiers = True
        if re.search(r"bitara\.co", flat, re.I) is None:
            missing.append(f"{path}:no-bitara.co-reference")

    if not checked:
        res.add("entity-identity", "P0-3", "Organization carries disambiguation + sameAs + legal id",
                "BLOCKED", detail="neither / nor /about could be fetched")
        return
    res.add("entity-identity", "P0-3", "Organization carries disambiguation + sameAs + legal id",
            "PASS" if not missing else "FAIL",
            expected="disambiguatingDescription + non-empty sameAs + registration 202201037451",
            measured=f"{checked} page(s) parsed; missing={missing or 'none'}",
            detail="" if not missing else
                   "a block that parses but omits these does not disambiguate the entity from the parked .com")
    res.add("entity-legal-identifier", "P0-3", "Registration number present in structured data",
            "PASS" if identifiers else "FAIL", expected="202201037451",
            measured="present" if identifiers else "absent")

    hit = fetch(f"{base}/about")
    if hit["ok"]:
        head = " ".join(visible_text(hit["text"])[:600].split())
        statement = bool(re.search(r"bitara\.co", head, re.I))
        res.add("entity-visible-statement", "P0-3", "Visible 'is bitara.co' statement near the top",
                "ADVISORY", expected="a readable sentence in the first viewport",
                measured=("found in the first ~600 chars" if statement else "not found in the first ~600 chars"),
                detail="heuristic: judge it by eye — the statement must be text, present without JS, "
                       "and must also name the look-alike domains as unaffiliated")


# --- P1-1: hreflang in the HTML head, and llms.txt locale parity ------------------------------
def check_i18n(base: str, res: Results, samples: Path) -> None:
    sitemap = fetch(f"{base}/sitemap.xml")
    home = fetch(f"{base}/")
    if not sitemap["ok"] or not home["ok"]:
        res.add("hreflang-in-head", "P1-1", "HTML <head> hreflang covers the sitemap locale set",
                "BLOCKED", detail=f"sitemap HTTP {sitemap['status']}, homepage HTTP {home['status']}")
        return

    smap, head = sitemap_locales(sitemap["text"]), head_hreflangs(home["text"])
    (samples / "hreflang.json").write_text(json.dumps(
        {"sitemap": sorted(smap), "head": sorted(head)}, indent=2))
    missing = sorted(smap - head)
    res.add("hreflang-in-head", "P1-1", "HTML <head> hreflang covers the sitemap locale set",
            "PASS" if head and not missing else "FAIL",
            expected=f"{len(smap)} locale value(s) incl. x-default (as in the sitemap)",
            measured=f"head={len(head)} value(s): {sorted(head)}",
            detail="" if (head and not missing) else
                   f"absent from the HTML head but present in the sitemap: {missing or 'the whole set'} — "
                   "AI fetchers read HTML, not sitemaps")

    prefixes = sorted(set(re.findall(r"bitara\.co/([a-z]{2})(?:/|$)", sitemap["text"])))
    llms = fetch(f"{base}/llms.txt")
    if not llms["ok"] or not prefixes:
        res.add("llms-locale-parity", "P1-1", "llms.txt mentions every locale in the sitemap",
                "BLOCKED",
                detail=f"llms.txt HTTP {llms['status']}; {len(prefixes)} locale prefix(es) found in the sitemap")
    else:
        absent = [p for p in prefixes if not re.search(rf"/{re.escape(p)}[/\s)\">]", llms["text"])]
        res.add("llms-locale-parity", "P1-1", "llms.txt mentions every locale in the sitemap",
                "PASS" if not absent else "FAIL",
                expected=f"all {len(prefixes)} locale(s): {prefixes}",
                measured=f"missing={absent or 'none'}",
                detail="" if not absent else "the site contradicts itself about which locales exist")

    ai_txt = fetch(f"{base}/ai.txt")
    res.add("ai-txt-absent", "—", "ai.txt is absent (correct: it is a defunct proposal)", "INFO",
            measured=f"HTTP {ai_txt['status']}",
            detail="adding an ai.txt would be noise, not an improvement")


# --- P1-2: template-level structured-data coverage -------------------------------------------
TEMPLATE_PATTERNS = [
    ("insights", r"/insights?/", {"Article", "BlogPosting", "NewsArticle"}),
    ("case-studies", r"/case-stu|/casestudy", {"CreativeWork", "Article", "BlogPosting"}),
    ("services", r"/services?/|/solutions?/", {"Service", "Offer", "Product"}),
]


def check_template_jsonld(base: str, res: Results, samples: Path, sitemap_text: str) -> None:
    urls = sitemap_urls(sitemap_text)
    if not urls:
        res.add("jsonld-templates", "P1-2", "Required @types per page template", "BLOCKED",
                detail="the sitemap yielded no URLs to sample")
        return

    for name, pattern, required in TEMPLATE_PATTERNS:
        matched = [u for u in urls if re.search(pattern, u, re.I)][:2]
        if not matched:
            res.add(f"jsonld-{name}", "P1-2", f"{name} pages emit {'/'.join(sorted(required))}", "INFO",
                    detail="no sitemap URL matched this template — nothing to verify, which is itself "
                           "worth confirming with the client")
            continue
        problems, seen = [], set()
        for url in matched:
            page = fetch(url)
            if not page["ok"]:
                problems.append(f"{url}=HTTP {page['status']}")
                continue
            flat = flatten_json_ld(parse_json_ld(page["text"]))
            types = set(re.findall(r'"@type"\s*:\s*"([^"]+)"', flat))
            seen |= types
            if not (types & required):
                problems.append(f"{url.rsplit('/', 1)[-1] or url}: no {'/'.join(sorted(required))}")
            if "BreadcrumbList" not in types:
                problems.append(f"{url.rsplit('/', 1)[-1] or url}: no BreadcrumbList")
        res.add(f"jsonld-{name}", "P1-2",
                f"{name} pages emit {'/'.join(sorted(required))} + BreadcrumbList",
                "PASS" if not problems else "FAIL",
                expected=f"required types {sorted(required)} + BreadcrumbList",
                measured=f"sampled {len(matched)}; @types seen={sorted(seen)}",
                detail="; ".join(problems))


# --- P1-3: answer-first openings — a human judgement, measured as a heuristic ------------------
DEFINITIONAL = re.compile(
    r"\b(is a|is an|is the|provides|offers|builds|specialis|specializ|develops|delivers|"
    r"helps|designs|operates)\b", re.I)


def check_answer_first(base: str, res: Results, sitemap_text: str) -> None:
    pages = [("homepage", "/"), ("about", "/about")]
    for i, url in enumerate([u for u in sitemap_urls(sitemap_text)
                             if re.search(r"/insights?/", u, re.I)][:1]):
        pages.append((f"insight[{i}]", url[len(base):] or "/"))

    for label, path in pages:
        page = fetch(f"{base}{path}")
        if not page["ok"]:
            res.add(f"answer-first-{label}", "P1-3", f"{label}: opens with a standalone answer",
                    "BLOCKED", detail=f"HTTP {page['status']}")
            continue
        opening = " ".join(visible_text(page["text"]).split()[:60])
        res.add(f"answer-first-{label}", "P1-3", f"{label}: opens with a standalone answer", "ADVISORY",
                expected="a definitional sentence inside the first 60 words",
                measured="definitional cue found" if DEFINITIONAL.search(opening) else "no cue found",
                detail=f"opening: {opening[:140]}…")


# --- P2-1: IndexNow key file ------------------------------------------------------------------
def check_indexnow(base: str, res: Results) -> None:
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    if not key:
        res.add("indexnow-key-served", "P2-1", "IndexNow key file is served", "BLOCKED",
                detail="no INDEXNOW_KEY in the environment — export the client's key to verify. "
                       "IndexNow covers Bing/Yandex/Seznam/Naver and never Google")
        return
    r = fetch(f"{base}/{key}.txt")
    ok = r["ok"] and key in r["text"]
    res.add("indexnow-key-served", "P2-1", "IndexNow key file is served",
            "PASS" if ok else "FAIL", expected=f"HTTP 200 at /{key}.txt containing the key",
            measured=f"HTTP {r['status']}",
            detail="" if ok else "a ping is rejected unless the key file is reachable")


# --- informational: crawler files, corpus presence --------------------------------------------
def check_crawler_files(base: str, res: Results, samples: Path) -> None:
    robots = fetch(f"{base}/robots.txt")
    if robots["ok"]:
        (samples / "robots.txt").write_text(robots["text"])
        signal = re.search(r"(?im)^Content-Signal:.*$", robots["text"])
        blanket_disallow = bool(re.search(r"(?im)^\s*User-agent:\s*\*\s*$[\s\S]{0,40}?^\s*Disallow:\s*/\s*$",
                                          robots["text"]))
        res.add("robots-txt", "—", "robots.txt reachable and permissive to AI crawlers",
                "PASS" if not blanket_disallow else "FAIL",
                measured=signal.group(0) if signal else "no Content-Signal",
                detail="" if not blanket_disallow else "a blanket Disallow: / would block the AI crawlers")
    else:
        res.add("robots-txt", "—", "robots.txt reachable and permissive to AI crawlers", "BLOCKED",
                detail=f"HTTP {robots['status']}")

    for path, label in (("/llms.txt", "llms.txt"), ("/llms-full.txt", "llms-full.txt")):
        r = fetch(f"{base}{path}")
        res.add(f"machine-file-{label}", "—", f"{label} is served", "PASS" if r["ok"] else "FAIL",
                expected="HTTP 200", measured=f"HTTP {r['status']}, {r['bytes']} bytes")


def check_common_crawl(res: Results) -> None:
    """Informational on purpose: presence is not client-controllable, so it is never a gate."""
    try:
        info = fetch("https://index.commoncrawl.org/collinfo.json", timeout=30)
        ids = re.findall(r'"(CC-MAIN-\d{4}-\d+)"', info["text"]) if info["ok"] else []
        if not ids:
            res.add("common-crawl", "L5", "Common Crawl captures", "BLOCKED",
                    detail="collinfo.json unreachable, so the corpus question is unmeasured")
            return
        newest = sorted(set(ids), reverse=True)[0]
        q = fetch(f"https://index.commoncrawl.org/{newest}-index?url=bitara.co&output=json", timeout=45)
        if q["status"] == 404 and "No Captures found" in q["text"]:
            res.add("common-crawl", "L5", "Common Crawl captures (informational)", "INFO",
                    measured=f"{newest}: no captures",
                    detail="expected. Inclusion follows being crawled, linked and notable — it cannot be "
                           "submitted or bought, so it must never sit on a delivery timeline")
        elif q["ok"]:
            res.add("common-crawl", "L5", "Common Crawl captures (informational)", "INFO",
                    measured=f"{newest}: captures present", detail="worth recording as a dated milestone")
        else:
            res.add("common-crawl", "L5", "Common Crawl captures (informational)", "BLOCKED",
                    measured=f"{newest}: HTTP {q['status']}", detail="not measured — not a negative")
    except Exception as exc:
        res.add("common-crawl", "L5", "Common Crawl captures (informational)", "BLOCKED",
                detail=f"not measured: {exc!r}"[:200])


CREDENTIAL_BLOCKED = [
    ("google-index-status", "L1", "Google index status (the client's own complaint)",
     "needs Search Console access — a service account added to the property",
     "owner: client (and it is the single highest-value unblock in this engagement)"),
    ("bing-index-status", "L2", "Bing/Copilot index status",
     "needs a Bing Webmaster Tools API key", "owner: client (Bing feeds Copilot and ChatGPT Search)"),
    ("serp-site-counts", "L3", "site: counts from an engine that does not challenge bots",
     "needs a Google Custom Search JSON API key + engine id", "owner: client"),
    ("answer-engine-citations", "L4", "Whether Gemini/ChatGPT/Perplexity now cite bitara.co",
     "needs GOOGLE_API_KEY (Gemini first) or ANTHROPIC_API_KEY; then run the geo-citation-probe skill",
     "owner: client — this is the actual measured outcome of the engagement, and it cannot be "
     "substituted by any on-page check"),
    ("cloudflare-zone-cause", "L7", "Who authors the per-UA variant at the edge",
     "needs read-only Cloudflare API access to the zone", "owner: client"),
]


def write_reports(out: Path, res: Results, base: str, baseline_ref: str) -> dict:
    counts = res.counts()
    if counts["FAIL"]:
        verdict = "FAIL"
    elif counts["BLOCKED"]:
        verdict = "ON-PAGE CHECKS PASS — engine outcome NOT VERIFIED (see the blocked list)"
    else:
        verdict = "PASS"

    payload = {
        "tool": "scripts/geo/verify_fixes.py",
        "url": base,
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baseline": baseline_ref,
        "verdict": verdict,
        "counts": counts,
        "note": "BLOCKED = not measurable (never a pass). ADVISORY = a human judgement. "
                "INFO = context, not a gate.",
        "checks": res.items,
        "not_verifiable_from_outside": [
            {"check": c, "limitation": l, "title": t, "needs": n, "owner": o}
            for c, l, t, n, o in CREDENTIAL_BLOCKED
        ],
    }
    (out / "verified.json").write_text(json.dumps(payload, indent=2))

    lines = [
        f"# GEO fix verification — {base}", "",
        f"- when: {payload['verified_at']}",
        f"- verdict: **{verdict}**",
        f"- counts: {counts}",
        f"- baseline compared against: {baseline_ref}", "",
        "Legend — **PASS** fix in place · **FAIL** fix missing · **BLOCKED** not measurable "
        "(not a pass) · **ADVISORY** human judgement · **INFO** context", "",
        "| task | check | status | measured | detail |", "|---|---|---|---|---|",
    ]
    for item in res.items:
        measured = str(item["measured"]).replace("|", "/")[:90]
        detail = str(item["detail"]).replace("|", "/")[:150]
        lines.append(f"| {item['task']} | {item['title']} | {item['status']} | {measured} | {detail} |")
    lines += ["", "## Not verifiable from outside this machine", ""]
    for c, l, t, n, o in CREDENTIAL_BLOCKED:
        lines.append(f"- **{t}** _({l})_ — {n}. {o}")
    lines += ["", "## How to read this", "",
              "- A **FAIL** means that task's fix is not in place yet, as measured just now.",
              "- A **BLOCKED** line means nobody has measured it. It is not evidence of success.",
              "- The engagement's actual outcome question — whether Gemini cites the site — is the",
              "  `answer-engine-citations` line. Until a key exists, no on-page result answers it.", ""]
    (out / "verification.md").write_text("\n".join(lines) + "\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=os.environ.get("GEO_URL", "https://bitara.co"))
    parser.add_argument("--baseline", default=None,
                        help="a reports/geo/<runId> directory or manifest.json to compare against")
    parser.add_argument("--only", default="", help="comma-separated task ids, e.g. P0-1,P0-2")
    parser.add_argument("--out", default=None)
    parser.add_argument("--json", action="store_true", help="print machine-readable output only")
    parser.add_argument("--skip-common-crawl", action="store_true",
                        help="skip the informational corpus check (saves ~10s)")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    repo_root = Path(__file__).resolve().parents[2]
    run_id = os.environ.get("GEO_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else repo_root / "reports" / "verify" / run_id
    samples = out / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    out_flag = out.relative_to(repo_root) if str(out).startswith(str(repo_root)) else out

    baseline, baseline_ref = load_baseline(repo_root, args.baseline)

    reachable = fetch(f"{base}/")
    if not reachable["ok"]:
        log(f"blocked: {base}/ returned HTTP {reachable['status']} — nothing was verified, "
            "so this run is NOT a clean result")
        return 3

    res = Results()
    wanted = {t.strip().upper() for t in args.only.split(",") if t.strip()}

    def want(task: str) -> bool:
        return not wanted or task in wanted

    log(f"verifying {base}   (baseline: {baseline_ref})")
    log(f"artifacts -> {out_flag}")
    log("")
    log("checks:")

    if want("P0-1"):
        check_crawler_parity(base, res, samples, baseline)
    if want("P0-2"):
        check_caching(base, res, samples)
    if want("P0-3"):
        check_entity_identity(base, res, samples)
    if want("P1-1"):
        check_i18n(base, res, samples)

    sitemap = fetch(f"{base}/sitemap.xml")
    sm_text = sitemap["text"] if sitemap["ok"] else ""
    if want("P1-2"):
        check_template_jsonld(base, res, samples, sm_text)
    if want("P1-3"):
        check_answer_first(base, res, sm_text)
    if want("P2-1"):
        check_indexnow(base, res)

    check_crawler_files(base, res, samples)
    if not args.skip_common_crawl:
        check_common_crawl(res)
    for check_id, limitation, title, needs, owner in CREDENTIAL_BLOCKED:
        res.add(check_id, limitation, title, "BLOCKED", detail=f"{needs} — {owner}")

    payload = write_reports(out, res, base, baseline_ref)
    counts = payload["counts"]

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if counts["FAIL"] == 0 else 1

    log("")
    log("─" * 78)
    log(f"VERDICT: {payload['verdict']}")
    log(f"  pass={counts['PASS']}  fail={counts['FAIL']}  blocked={counts['BLOCKED']}  "
        f"advisory={counts['ADVISORY']}  info={counts['INFO']}")

    fails = [i for i in res.items if i["status"] == "FAIL"]
    if fails:
        log("")
        log("Fixes NOT in place (measured just now):")
        for item in fails:
            log(f"  ✗ [{item['task']}] {item['title']} — expected {item['expected']}")

    blocked = [i for i in res.items if i["status"] == "BLOCKED"]
    if blocked:
        log("")
        log("Not measured — these are NOT passes:")
        for item in blocked:
            log(f"  ■ [{item['task']}] {item['title']} — {item['detail'][:110]}")

    log("")
    log(f"Reports: {out_flag}/verification.md and {out_flag}/verified.json")
    log("BLOCKED lines stay blocked until the client supplies the credential named on each.")
    return 0 if counts["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
