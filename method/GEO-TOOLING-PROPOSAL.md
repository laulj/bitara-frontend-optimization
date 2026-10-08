# GEO Tooling Proposal — removing the measurement limitations on `bitara.co`

> **What this is:** the working Phase-1 tooling decision (limitations L1–L7 → capabilities T1–T8)
> that the ADR was built from. A generation input, not a deliverable.
>
> **Superseded by** [`docs/adr/ADR-001-geo-tooling.md`](../docs/adr/ADR-001-geo-tooling.md), which
> records what was actually installed, what it closed, and the measured rejection reasons. **Where
> the two differ, the ADR wins** — it is the decision of record. This file is kept because it is the
> only place the seven limitations are argued in full.

> Companion to `GEO-OPTIMIZATION-PROMPT.md` (Phase 1 tooling gate) and
> `GEO-PROPOSAL-PROMPT.md` (the client's proposal). This document answers one question:
> **which tools do we install so that the limitations found during the investigation stop
> being limitations?**
>
> Every capability below was verified in this environment on 2026-10-08. Facts drawn from
> vendor documentation are labelled `[SOURCED]` with the URL; anything installed was actually
> installed and imported before being recommended.

## 1. The limitations, stated precisely

The investigation hit seven measurement blocks, two of them hard stops that make the client's
symptom unprovable. These are not opinions — each one blocked a specific measurement.

| # | Limitation | How it was hit | Severity |
|---|---|---|---|
| **L1** | **Google index status is unmeasurable from outside** | `site:bitara.co` could not be queried programmatically; `www.google.com/search` returned a redirect/consent shell, not results. So "Google has not indexed the site" is currently an *inference*, not a measurement | **Critical** — it is the client's exact complaint |
| **L2** | **Bing/Copilot index status is only weakly measurable** | The one query that did return (`bitara.co Bitara Capital Sdn Bhd`) gave 51 results with zero bitara.co — a signal, but a single uncontrolled sample | High |
| **L3** | **`site:` counts are blocked by bot challenges** | DuckDuckGo → "complete the following challenge"; Mojeek → "JavaScript is required". Both had to be recorded as **"not measured"**, which is the honest but useless outcome | High |
| **L4** | **Answer-engine citation probing was manual and non-deterministic** | The 15-prompt probe set in `GEO-PROPOSAL-PROMPT.md` can only be run by hand, in a browser, with no artifact, no diff and no repeatability. That defeats the whole before/after claim | **Critical** — nothing can be proven improved |
| **L5** | **Common Crawl queries are flaky and manual** | `CC-MAIN-2025-38` returned a **504 Gateway Time-out**; collection IDs must be discovered by hand from `collinfo.json`; Wayback returned **429 Too Many Requests** | Medium — false "no captures" is a real risk |
| **L6** | **`curl` cannot reproduce a real browser/crawler TLS fingerprint** | Behind Cloudflare, a plain `curl` request is not equivalent to Chrome's JA3/JA4. Part of the per-UA split may be fingerprint-driven, not header-driven, and we cannot currently tell | Medium |
| **L7** | **Cannot see whether Cloudflare itself is generating the per-UA content split** | The `Googlebot` vs `Google-Extended` divergence is observable but its *cause* is not, without zone access | Medium |

## 2. The rule this proposal obeys

The kit's standing tool-selection order, unchanged:

1. **Existing system CLI, wrapped by `wq`** — 0 tokens/request, artifacts in `reports/`.
2. **New tool installed as a system/dev dependency and wrapped in `wq`** — same cost model.
3. **Agent skill** — cheap (~12 tokens/request for names only); right for judgement, wrong for measurement.
4. **MCP — last resort.** Measured cost: chrome-devtools ≈ 6,600 tok/req, playwright ≈ 5,070 tok/req.

**Consequence for this proposal: nothing here is an MCP server.** Every limitation above is a
deterministic, artefact-producing measurement — precisely the shape the CLI rung exists for.

## 3. Limitation → tool mapping

| Limitation | Tool that removes it | Form | Rung |
|---|---|---|---|
| L1 Google index status | **Google Search Console API** — `urlInspection.index.inspect`, `searchanalytics.query` | new `wq geo index --provider google` | 2 |
| L2 Bing/Copilot index status | **Bing Webmaster Tools REST API** — `GetUrlInfo`, `GetQueryStats`, `SubmitUrlBatch` | new `wq geo index --provider bing` | 2 |
| L3 `site:` counts blocked | **Google Programmable Search (Custom Search JSON API)**; **BWT API** for Bing | new `wq geo serp` | 2 |
| L4 Manual citation probing | **Gemini API `google_search` grounding**; **Anthropic `web_search`**; OpenAI Responses `web_search`; Perplexity Sonar | new `wq geo cite` + a `geo-citation-probe` **skill** | 2 + 3 |
| L5 Common Crawl flakiness | **`cdx-toolkit`** (retries, backoff, collection discovery; also covers Wayback) | new `wq geo corpus` | 2 |
| L6 TLS/JA3 fidelity | **`curl_cffi`** (Chrome/Firefox impersonation) or `curl-impersonate` | new `wq geo parity` | 2 |
| L7 Cloudflare-side cause | **Cloudflare API** (read zone + bot-management settings) | new `wq geo cf` — needs zone access | 2 |
| Recrawl signalling (no limitation, but closes the loop) | **IndexNow** — Bing, Yandex, Seznam, Naver. **Not Google** | new `wq geo ping` | 2 |

**Net new dependencies: 4.** One Node package (`googleapis`) and three Python installs
(`cdx-toolkit`, `curl_cffi`, and `google-genai` + `anthropic` together in one pinned venv).
IndexNow, the BWT REST calls and the CSE calls are plain `fetch` with no dependency at all.

## 4. Tool specifications

### T1 — Google Search Console API (`wq geo index --provider google`)

- **Removes:** L1. Turns "Google probably hasn't indexed us" into a per-URL, dated fact.
- **Endpoints:** `searchconsole.urlInspection.index.inspect` (per-URL index status: verdict,
  coverage state, the canonical Google selected, crawl time) and
  `searchconsole.searchanalytics.query` (clicks/impressions/queries — the baseline for
  "is anyone finding us at all").
- **Quota** `[SOURCED]`: URL inspection is **2,000 QPD / 600 QPM per site** (project cap
  10,000,000 QPD). Search Analytics: 1,200 QPM per site and per user. All other resources:
  20 QPS / 200 QPM per user.
  Source: https://developers.google.com/webmaster-tools/limits (updated 2025-08-28).
- **Auth:** OAuth 2.0. For CI, use a **service-account JSON added as a user of the GSC
  property** — never a browser flow.
- **Client:** `googleapis` (official Node, **v184.0.0** verified on npm) — keeps the kit in one
  runtime, no Python needed for this one.
- **Env:** `GSC_SA_JSON` (path to service-account JSON), `GSC_SITE` (e.g. `sc-domain:bitara.co`).
- **Failure mode:** if the service account is not a property user, print
  `blocked: GSC service account lacks property access` and exit non-zero. Never silently skip.

### T2 — Bing Webmaster Tools REST API (`wq geo index --provider bing`)

- **Removes:** L2 — gives a real Bing index answer instead of one uncontrolled search.
- **Endpoints:** `GetUrlInfo` (per-URL index status — Bing's analogue of URL Inspection),
  `GetQueryStats` (query/traffic baseline), `GetCrawlStats`, `SubmitUrl` / `SubmitUrlBatch`,
  and sitemap submission.
- **Auth:** API key from Bing Webmaster Tools settings, or OAuth 2.0.
- **Env:** `BING_WEBMASTER_API_KEY`.
- **Deprecation warning** `[SOURCED]`: "Legacy SOAP and POX APIs will be retired on
  **August 31, 2026**. Migrate to our REST APIs to avoid service disruption."
  Source: https://learn.microsoft.com/en-us/bingwebmaster/ (updated 2026-08-07). **Use REST.**
- **Why it matters for the client:** Bing feeds Microsoft Copilot, and Bing's index is a
  material input to ChatGPT Search. Bing presence is not a side quest.

### T3 — Google Programmable Search / Custom Search JSON API (`wq geo serp`)

- **Removes:** L3 for Google, legitimately — the challenge-free, terms-compliant route.
- **Capability:** the JSON API supports a **`siteSearch`** parameter, so `site:bitara.co` counts
  become an API call with a dated artefact instead of a scraped page.
- **Quota:** 100 queries/day free; paid beyond.
- **Env:** `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX`.
- **Bing side:** use **T2** (`GetQueryStats`), not the Bing Web Search API.
- **Explicitly rejected for this job** `[SOURCED]`: the Bing Web Search API terms state it "may
  only be used as a result of a direct user query or search, or as a result of an action within
  an app or experience that logically can be interpreted as a user's search request."
  Automated rank probing falls outside that. Source:
  https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/overview


### T4 — LLM citation probing (`wq geo cite`) — the highest-value tool here

This is what converts the client's complaint into a number.

**Primary: Gemini API with Google Search grounding** `[SOURCED]` — chosen because it is the
*same grounding path* the client is complaining about, so it measures the actual mechanism.

- Config: `tools = [{"type": "google_search"}]` (older models use `google_search_retrieval`;
  for all current models use `google_search`).
- Responses carry structured citations with **`Title`, `URL`, `StartIndex`, `EndIndex`** plus
  the cited text span — so we can assert "Gemini cited `bitara.co/...` at character 412",
  rather than "the answer felt good".
- Supported on the `gemini-3.x` and `gemini-2.5` families.
- Pricing: billed **per search query the model decides to execute** (Gemini 3 models); multiple
  queries in one prompt = multiple billable uses.
- Source: https://ai.google.dev/gemini-api/docs/google-search (updated 2026-09-23).
- **Env:** `GOOGLE_API_KEY`.

**Secondary: Anthropic `web_search`** `[SOURCED]` — server-side tool with three versions:
`web_search_20250305` (basic), `web_search_20260209` (adds dynamic filtering),
`web_search_20260318` (adds response inclusion control). Responses include `citations` and
`web_search_tool_result` blocks containing `web_search_result` objects with `title` and `url`.
Pricing: **$10 per 1,000 searches**, plus token costs.
Source: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool
- **Env:** `ANTHROPIC_API_KEY`.

**Worth wiring behind the same interface:** OpenAI Responses API `web_search`
(`OPENAI_API_KEY`) and Perplexity Sonar (`PERPLEXITY_API_KEY`). *Verify the exact response field
names against the current docs before the harness depends on them, and fail loudly rather than
writing an empty result.*

**Cost at the proposed cadence:** 15 prompts × 4 engines = 60 requests per run. Anthropic is
**$0.15 per run** at 15 searches; Gemini grounding is a few dollars per run at most depending
on executed queries. Weekly for 8 weeks ≈ **under $5 total** — rounding, not a budget line.

**The skill that goes with it (rung 3):** `geo-citation-probe`, authored with `skill-creator`
into `~/.agents/skills/`. The CLI produces the artefact; the skill encodes *interpretation*:
how to score `mentioned / described correctly / URL cited`, how to tell "the engine has no data"
apart from "the engine has wrong data", and how to avoid over-reading a single sample.

### T5 — `cdx-toolkit` (`wq geo corpus`)

- **Removes:** L5. Discovers Common Crawl collections from `collinfo.json`, paginates the CDX
  index, and **retries with backoff** — exactly what failed by hand
  (`504 Gateway Time-out` on `CC-MAIN-2025-38`, `429` on the Wayback API).
- **Covers both** Common Crawl and the Wayback CDX API, so capture history and site age come
  from one tool.
- **Install (verified in this environment):** `uv tool install cdx-toolkit` → provides `cdxt`,
  `cdx_iter`, `cdx_size`. No auth.

### T6 — `curl_cffi` (`wq geo parity`)

- **Removes:** L6. Impersonates real Chrome/Firefox TLS fingerprints so we can tell whether the
  per-UA content split is **header-driven or fingerprint-driven** — a distinction that decides
  who owns the fix.
- **Install (verified):** `uv pip install curl_cffi` → **0.16.3**.
- **Why it matters:** behind Cloudflare, `curl` and Chrome are not the same client. If the
  reduced variant is triggered by JA3/JA4 rather than user-agent, no amount of header tuning in
  `wq geo bots` would have found it.
- `curl-impersonate` is the native alternative; `curl_cffi` wins here because `uv` is already
  present and the binding is scriptable.

### T7 — Cloudflare API (`wq geo cf`) — tests the L7 hypothesis

- **Removes:** L7, with caveats. Reads zone settings, bot-management configuration and any
  AI-crawler rules to answer: is **Cloudflare**, not the origin, generating the `Googlebot` vs
  `Google-Extended` divergence?
- **Auth:** read-only scoped token. Env: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID`.
- **This is a dependency, not a tool gap:** it needs zone access the client must grant. Without
  it this question stays **open**, and must be reported as open — not as clean.

### T8 — IndexNow (`wq geo ping`)

- **Purpose:** push changed URLs to Bing/Yandex/Seznam/Naver immediately rather than waiting for
  recrawl — which matters more than usual here, given `no-store` and no cache validators.
- **Auth:** a key file at `https://bitara.co/{key}.txt`. Env: `INDEXNOW_KEY`.
- **Implement with plain `fetch`** — no dependency required.
- **Honest scope:** **IndexNow does not cover Google.** Google has no general-purpose push API;
  its Indexing API is documented for job-posting and broadcast-event structured data, **not**
  general pages — so do not propose it here. Google's route is sitemap submission plus
  crawl-budget hygiene (which the `ETag`/`max-age` fix in T9-class work provides).


## 5. Bootstrap — verified in this environment

Environment facts that shape the install: Node **v26.3.1**, `pnpm`, `uv` **0.12.9** and `uvx`,
`python3` **3.14.7**, `jq`, `dig`, `aws` and `gh` present; **`gcloud` and `pipx` are NOT
installed**. The kit lives at `$KIT` and `wq` is **not on
PATH**.

```bash
# The measurement harness now owns its own pinned tool env — see scripts/geo/bootstrap.sh.
# Nothing below requires an external checkout; `wq` is optional and only adds the browser
# read-back step (which is recorded as blocked when absent).
bash scripts/geo/bootstrap.sh        # → ./.venv (Python 3.12), pinned requirements

# Equivalent by hand (the venv lives in this repo, not in the kit):
#   uv venv .venv --python 3.12
#   uv pip install --python .venv -r scripts/geo/requirements.txt

# Optional: cdx-toolkit's standalone CLIs (cdxt, cdx_iter, cdx_size)
WITH_CDXT_CLI=1 bash scripts/geo/bootstrap.sh

# Node-side, deferred until T1 is unblocked (the kit workspace, if you use one):
#   KIT=${KIT:-/path/to/web-quality-kit}
#   pnpm -C "$KIT" add -D googleapis            # verified available: v184.0.0
```

**Verified by actual install on 2026-10-08:**

| Package | Result |
|---|---|
| `googleapis` (npm) | resolves to **184.0.0** |
| `cdx-toolkit` (PyPI) | installed; `cdxt`, `cdx_iter`, `cdx_size` all present |
| `curl_cffi` (PyPI) | installed, **0.16.3**, imports clean |
| `google-genai` (PyPI) | installed, imports clean |
| `anthropic` (PyPI) | installed, imports clean |

**Pin the tooling interpreter to Python 3.12.** The host default is 3.14.7, which is very new;
3.12 was used here specifically so wheels for `curl_cffi` and `cdx-toolkit` resolve. Encoding it
in the venv stops a future `uv` run from silently picking 3.14 and failing.

**Credentials matrix** — env-only, never committed:

| Env var | Enables | If absent |
|---|---|---|
| `GSC_SA_JSON`, `GSC_SITE` | T1 Google index + search analytics | skip: `blocked: no GSC service account` |
| `BING_WEBMASTER_API_KEY` | T2 Bing index + submission | skip: `blocked: no BWT key` |
| `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` | T3 `site:` counts | skip: `blocked: no CSE credentials` |
| `GOOGLE_API_KEY` | T4 Gemini grounding probes | skip that engine, keep the others |
| `ANTHROPIC_API_KEY` | T4 Claude probes | skip that engine |
| `OPENAI_API_KEY`, `PERPLEXITY_API_KEY` | T4 additional engines | skip those engines |
| `INDEXNOW_KEY` | T8 push notifications | skip: `blocked: no IndexNow key` |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` | T7 zone audit | L7 stays **open** |

Rule: **a skipped check is reported as skipped, with its reason.** The kit's own lesson — "a
skipped scanner is not a clean result" — applies verbatim here.

## 6. What to explicitly NOT install (the omit list)

Considered and rejected. Recording this stops the next agent re-litigating it.

| Rejected | Why |
|---|---|
| **Any MCP server** (playwright, chrome-devtools, browser) | 5,070–6,600 tok/req each, re-sent on every request; `wq probe` covers page reading at **0 tok/req**. No limitation above needs stateful interaction |
| **`gcloud` CLI** | Heavyweight and `MISSING` here. GSC auth needs a service-account JSON, which `googleapis` consumes directly — `gcloud` would add an auth surface for nothing |
| **`pipx`** | Not installed, and redundant: `uv tool install` does the same job with a tool already present |
| **Bing Web Search API** | `[SOURCED]` its terms restrict use to direct user-query/search-like experiences; automated probing is out of scope. Use T2 |
| **Google Indexing API for general URLs** | Documented for JobPosting/BroadcastEvent structured data, not general pages. Policy risk for marginal gain |
| **`ai.txt` generator / validator** | Defunct proposal. The site correctly 404s `/ai.txt`; adding it would be noise |
| **`ddgs` / `duckduckgo_search` as the primary SERP path** | It is exactly what just got bot-challenged. Acceptable only as an opportunistic fallback, and any challenge must be logged as *not measured* |
| **Any "GEO rank tracker" SaaS without an API and an artefact** | Returns prose into the chat: no `reports/` file, no budget, no diff, no provenance |
| **Two tools for one capability** | e.g. `curl-impersonate` *and* `curl_cffi`; or rival LLM-probe libraries. One each |
| **Python 3.14 as the tooling interpreter** | Very new; risks wheel resolution for `curl_cffi`/`cdx-toolkit`. Pin 3.12 |


## 7. Residual limitations — what no tool fixes

State these in the report rather than implying the harness is complete.

1. **Engine answers are non-deterministic.** A probe is a *sample*, not a measurement of a stable
   quantity. Mitigate with repeated runs and date-stamped records; never quote a single run as
   "the" result.
2. **The Gemini API is a proxy for the Gemini app.** Consumer Gemini and the API grounding path
   share infrastructure but are not identical. Report the API as a *proxy* and keep a small
   manual app check alongside it — that is where the client's users actually are.
3. **Google AI Overviews cannot be probed by API.** There is no official endpoint. Keep the manual
   checklist for AI Overviews specifically.
4. **Common Crawl inclusion is not directly actionable.** It is a downstream consequence of
   crawlability, links and notability, and it lags by months. Do not put it on a timeline.
5. **`site:` counts are approximate** even through the official API — estimates, not inventory.
   Report them as dated trends, never as absolute page counts.
6. **Cloudflare's role stays unproven until T7 runs.** Until then the cause of the per-UA split
   is `[INFERRED]`, not `[MEASURED]`.

## 8. ADR skeleton — ready to commit as `ADR-001-geo-tooling.md`

```markdown
# ADR-001: GEO measurement tooling for bitara.co

Status: proposed | Date: 2026-10-08 | Owner: <name>

## Context
Seven measurements are impossible from outside the stack (L1-L7, GEO-TOOLING-PROPOSAL.md §1),
and the client-reported symptom ("Gemini cannot query bitara.co") cannot be evidenced without
index, corpus and citation data.

## Decision
Adopt eight wrapped capabilities and no MCP servers:
  T1 googleapis (Node)              -> wq geo index --provider google
  T2 Bing Webmaster REST (fetch)    -> wq geo index --provider bing
  T3 Custom Search JSON API (fetch) -> wq geo serp
  T4 google-genai + anthropic (venv) -> wq geo cite  [+ geo-citation-probe skill]
  T5 cdx-toolkit                    -> wq geo corpus
  T6 curl_cffi                      -> wq geo parity
  T7 Cloudflare API                 -> wq geo cf      (blocked pending zone access)
  T8 IndexNow (fetch)               -> wq geo ping

## Consequences
- New deps: googleapis (npm); cdx-toolkit, curl_cffi, google-genai, anthropic (venv, py3.12).
- Artifacts land in reports/geo/<runId>/; no raw prose in the chat.
- Runtime cost: under $5 for the 8-week probe cadence (Anthropic $10/1k searches).
- Context cost unchanged at ~0 tokens/request (no MCP enabled) — record `wq context` before/after.

## Rejected alternatives
Bing Web Search API and Google Indexing API (terms/policy); any MCP server (5-6.6k tok/req,
duplicated by `wq probe`); gcloud and pipx (redundant); Python 3.14 interpreter (wheel risk);
SaaS rank trackers without artifacts. See §6.

## Open items
T7 needs CLOUDFLARE_API_TOKEN + zone access before L7 closes.
T1 needs the GSC service account added as a property user.
```

## 9. Rollout order (so value lands before the paperwork finishes)

1. **T6 + T8 + the caching fix** — no credentials required; closes L6 and removes the recrawl
   throttle. Highest value per unit of effort, so it goes first.
2. **T5** — no credentials; closes L5 and re-establishes the Common Crawl baseline credibly
   (the manual query already half-failed with a 504).
3. **T4 with Gemini only** — one key, and it directly instruments the client's complaint.
4. **T1 + T2** — needs client-supplied property access; unlocks the index baselines.
5. **T3, then T7** — `site:` counts, then the Cloudflare hypothesis.
6. **Author the `geo-citation-probe` skill** and commit the ADR with measured `wq context`
   numbers from before and after.

## 10. Summary — the one-table answer

| Limitation | Removed by | New dependency | Credential |
|---|---|---|---|
| L1 Google index | GSC API (`googleapis`) | yes (npm) | service account |
| L2 Bing index | Bing Webmaster REST | **no** (fetch) | BWT key |
| L3 `site:` blocked | Google CSE JSON API | **no** (fetch) | CSE key + CX |
| L4 citation probing | Gemini grounding + Anthropic web_search | yes (venv) | API keys |
| L5 Common Crawl | `cdx-toolkit` | yes (venv/tool) | none |
| L6 TLS fingerprint | `curl_cffi` | yes (venv) | none |
| L7 Cloudflare cause | Cloudflare API | **no** (fetch) | CF token |
| recrawl signalling | IndexNow | **no** (fetch) | IndexNow key |

**Four new dependencies, zero MCP servers, under $5 of runtime cost for the whole measurement
programme.** Three of the eight capabilities need no dependency at all.

