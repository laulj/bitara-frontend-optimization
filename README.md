# bitara-frontend-optimization

Generative Engine Optimization (GEO) engagement for **Bitara Capital Sdn. Bhd.** (`bitara.co`) —
the measurement harness, the raw findings, and an executable fix plan.

The client-reported symptom was: *"Gemini LLM cannot query bitara.co result."* The diagnosis is
that this is a **visibility and identity** problem, not an on-page SEO problem: the site's GEO
scaffolding (`robots.txt`, `llms.txt`, `llms-full.txt`, sitemap, `Link` relations, org JSON-LD) is
already above average. This repository holds the evidence for that claim and the plan to close the
gaps it exposes.

> **Status:** no change has been made to the site. The website source repository has not been
> supplied, so every task in the plan is written to be executable and marked `blocked: source repo`
> rather than applied. One task — `P0-4` — is runnable today.

## What is here

| Path | What it is |
|---|---|
| `docs/GEO-FIX-PLAN.md` | **The plan.** 10 task cards (P0-1…P2-3), each with evidence, how to locate the cause, the change, acceptance commands with numbers, and what is forbidden. Read §1–§3 first, then the cards. |
| `docs/geo-fix-plan.json` | The same plan as machine-readable state for a coding agent: task `status`, `blocked_by[{reason,owner}]`, `locate`, `acceptance.assertions`. |
| `docs/adr/ADR-001-geo-tooling.md` | Why this tooling and not another; what it closed; measured context cost; rejected alternatives. |
| `scripts/geo/` | The measurement harness (below). |
| `reports/geo/20261008-193000/` | The measured run: `findings.md`, `manifest.json`, and the JSON/TXT evidence it rests on. |
| `GEO-OPTIMIZATION-PROMPT.md`, `GEO-TOOLING-PROPOSAL.md`, `GEO-PROPOSAL-PROMPT.md` | The engagement's method: how the audit is scoped, which tools were chosen, and the prompt that generates the client-facing proposal. |

## Quickstart

```bash
bash scripts/geo/bootstrap.sh              # creates ./.venv (Python 3.12) — no credentials needed
GEO_RUN_ID=$(date +%Y%m%d-%H%M%S) bash scripts/geo/run-geo.sh
```

Everything lands in `reports/geo/<runId>/`. No machine-specific paths are baked in: the harness
resolves its own repository root, defaults its virtualenv to `./.venv`, and takes an optional
`KIT=/path/to/web-quality-kit` for the browser read-back step. Prerequisites: `uv` (required),
`node` + Playwright (rendered-DOM step), `curl` (plain-TLS control rows).

A step that cannot run is recorded as `blocked` with its reason and exit code 127 — never omitted.
**A skipped check is not a pass.**

| Step | What it measures | Needs |
|---|---|---|
| T5 `cc_baseline.py` | Common Crawl captures across sampled collections, every negative proven by a definitive 404 rather than a timeout | venv only |
| T6 `ua_parity.py` | The per-User-Agent content split as a 2×2 factorial (browser TLS vs plain curl × browser UA vs Googlebot UA), so header- and fingerprint-driven causes are not confounded | venv + curl |
| `render_parity.mjs` | The same URL rendered in Chromium under each UA — separates "less HTML" from "less rendered content" | node + Playwright |
| `compare_innertext.py` | Whether the reduced variant is a lexical *subset with fewer repeats* or genuinely different content | the two `innerText` dumps |
| `wq probe` | Optional browser read-back at 0 tokens/request | an external web-quality-kit checkout |

## Headline findings

1. **AI crawlers receive a smaller page, and the cause is the User-Agent header, not TLS.** Two
   stable content classes on one TLS profile: Chrome / `Googlebot` / `Google-CloudVertexBot` receive
   the full page (30,101 visible-text chars), while `GPTBot` / `GoogleOther` / `Google-Extended`
   receive a reduced one (11,554). The fingerprint control ran and rules out a JA3 rule.
   `Google-Extended` is the token governing Gemini/Vertex grounding.
2. **The reduced variant is a lexical subset with fewer repeats** — 246 tokens absent versus 208
   merely *fewer instances*, and only 3 tokens unique to the bot side. Nothing is served to crawlers
   that a browser cannot see. Duplicated list/ticker rendering in the full variant is the leading
   hypothesis — a hypothesis until the template code is read.
3. **Zero Common Crawl captures**, confirmed across six sampled collections (of 127 advertised),
   every negative from a definitive 404.
4. **No cache validators**: no `ETag`, no `Last-Modified`, and a blanket
   `private, no-cache, no-store, max-age=0, must-revalidate` on a dynamically rendered route.
5. **Entity conflation is the real domain risk** — `bitara.com` is a parked "Ready for Development"
   page. The `.co` TLD is *not* the issue (Google treats `.co` as a generic ccTLD, i.e. as a gTLD);
   migration is explicitly not recommended.

## Blocked, with owners

| Blocked | Needs | Owner |
|---|---|---|
| Every code change | the website source repository | client |
| Whether the per-UA split is intentional | an answer plus a named owner | client |
| L1 Google index status | Search Console property access | client |
| L2 / L3 Bing + `site:` counts | Bing Webmaster Tools key, Google CSE key + CX | client |
| L4 citation probing | `GOOGLE_API_KEY` (Gemini first), then other engines | client |
| L7 cause of the split at the edge | Cloudflare zone, read-only | client |
| Recrawl signalling | `INDEXNOW_KEY` | client |

## Rules of engagement

No cloaking — UA-conditional content is eliminated or explicitly owned, never optimised around.
Never fabricate a statistic, a `sameAs` target or a timeline. Do not break SEO or accessibility to
please bots; they pull in the same direction. Keep `bitara.co`. Do not promise Common Crawl
inclusion on a schedule — it is slow, indirect and not client-controllable.

## Secret hygiene

GitHub already scans public repositories for known credential patterns and can **block a push**
that contains one. Enable both before the first push — they are repository settings, not code:

> Settings → Code security and analysis → **Secret scanning** ✅ and **Push protection** ✅

That native control does not cover everything this repository produces, because the harness
writes raw HTTP responses and header dumps into `reports/`:

- **Binary artifacts are invisible to pattern scanners.** Verified here: a GitHub token is detected
  in a plain file and **missed inside a `.gz` of that same file**, and `gitleaks` lists zero
  `.gz`/`.png` files when scanning the tree. So `reports/**/raw/http/*.html.gz` is *not* covered —
  the control there is redaction at write time, or not committing the payload at all.
- **Non-vendor secrets** — an internal hostname, a zone id, a service-account file, client data —
  match no generic ruleset.

Hence a small, repository-specific layer rather than a bespoke scanner:

| Control | Where | What it does |
|---|---|---|
| `bash scripts/scan-secrets.sh` | local | working-tree scan before committing; `--history` before pushing |
| `.gitleaks.toml` | repo config | extends gitleaks' default rules with artifact-shaped rules (`authorization` / `set-cookie` values, this engagement's env vars, a service-account JSON) plus an allowlist for the placeholders this repo publishes. Deliberately does **not** allowlist `reports/` — here that directory is the evidence, and the most likely place for a leaked header value |
| `.github/workflows/secret-scan.yml` | CI | the same script on every push/PR with full history, weekly; plus verified-secret scanning (trufflehog) and open GitHub secret-scanning alerts |

Two rules that matter more than the tooling:

1. **Rotate first, clean up second.** Once a credential is committed, assume it was read —
   removing it from history is not remediation.
2. **Do not commit a credential-bearing file and rely on the scan.** For binaries that advice is
   unenforceable, which is why the harness redacts sensitive header values as it writes them
   (`ua_parity.py`, `SENSITIVE_HEADERS`) and why the 7 MB probe screenshot is gitignored.

## Notes on this publication

Paths inside the captured run artifacts (logs, `manifest.json`, probe output) were rewritten from
absolute machine paths to `<repo>` / `$KIT` placeholders when this repository was published. No
measured value was altered — only location strings. No credentials are present: every key this
engagement needs is supplied through environment variables at run time and is never committed.
