# ADR-001: GEO measurement tooling for bitara.co

Status: **accepted — partially blocked** | Date: 2026-10-08 | Owner: engagement lead (unassigned)
| Blocked on: Bitara Capital Sdn. Bhd. (credentials + source repo + per-UA variant ownership)

Skeleton adopted from `method/GEO-TOOLING-PROPOSAL.md` §8, then filled with what was actually measured
in this session. Where the proposal and this ADR disagree, **this ADR records what happened** —
the proposal was a plan.

## Context

Seven measurements are impossible from outside the stack (L1–L7, `method/GEO-TOOLING-PROPOSAL.md` §1),
and the client-reported symptom — *"Gemini LLM cannot query bitara.co result"* — cannot be
evidenced without index, corpus and citation data. Two of the seven blocks are hard stops:

- **L5** made the headline finding unsound: the manual pass 504'd on one Common Crawl
  collection, so *"no captures"* was an inference, not a measurement — and a false negative
  there would have been reported to the client as fact.
- **L6** made the per-UA split unclassifiable: plain `curl` cannot distinguish a **User-Agent
  header rule** from a **TLS/JA3 fingerprint rule** behind Cloudflare. Different owners,
  different fixes, so guessing was not an option.

The kit's own rule applies throughout: **a skipped check is not a clean result.**

## Decision

Adopt eight wrapped capabilities and **no MCP servers**:

```
T1 googleapis (Node)               -> wq geo index --provider google   [blocked: GSC property]
T2 Bing Webmaster REST (fetch)     -> wq geo index --provider bing     [blocked: BWT key]
T3 Custom Search JSON API (fetch)  -> wq geo serp                      [blocked: CSE key + CX]
T4 google-genai + anthropic (venv) -> wq geo cite  [+ geo-citation-probe skill]
                                                                       [blocked: API keys]
T5 cdx-toolkit                     -> wq geo corpus                    EXECUTED (this session)
T6 curl_cffi                       -> wq geo parity                    EXECUTED (this session)
T7 Cloudflare API                  -> wq geo cf                        [blocked: zone access]
T8 IndexNow (fetch)                -> wq geo ping                      [not started]
```

**What was actually executed, credential-free** (run `20261008-190000`, artifacts in
`reports/geo/20261008-190000/`):

| Capability | Form used | Artifact |
|---|---|---|
| T5 Common Crawl baseline | `scripts/geo/cc_baseline.py` — cdx-toolkit collection discovery + retry/backoff, raw `requests` for per-collection status | `cc-baseline.json`, `raw/cc/*.json` |
| T6 per-UA parity | `scripts/geo/ua_parity.py` — curl_cffi `impersonate="chrome"` vs plain curl, 2×2 factorial | `ua-parity.json`, `raw/http/*.html.gz` |
| Step 3d rendered cross-check | `scripts/geo/render_parity.mjs` — kit Playwright with UA override | `render-parity.json` |
| Browser read-back | `wq probe https://bitara.co/` (0 tokens/request) | `probe-browser/` |
| Skill (rung 3) | `skills/geo-citation-probe/SKILL.md` → `~/.agents/skills/`, registered in `.skill-lock.json` | installed |

**Known deviation from the rung order, stated rather than hidden:** T5/T6 currently run as
scripts under `scripts/geo/`, not yet as `wq geo corpus` / `wq geo parity` subcommands. Wrapping
them in `wq` is the correct end state (rung 2), but the wrappers were deliberately not written
before a second run exists to shape their interface. They are invoked through a pinned interpreter
resolved by `scripts/geo/run-geo.sh` (default `$REPO/.venv`, created by `scripts/geo/bootstrap.sh`),
so they are reproducible on any machine and need no external checkout.

## Environment bootstrapped — verified by execution, not assumption

| Action | Result |
|---|---|
| `uv venv .venv --python 3.12` (via `scripts/geo/bootstrap.sh`) | **3.12.14** — pinned so a later `uv` run cannot silently pick the host's 3.14.7 and fail wheel resolution |
| `uv pip install … cdx-toolkit curl_cffi google-genai anthropic` | `cdx_toolkit 0.9.39`, `curl_cffi 0.16.3`, `google.genai` + `anthropic` import clean |
| `uv tool install cdx-toolkit` | `cdxt`, `cdx_iter`, `cdx_size` installed to `~/.local/bin` — **that directory is not on `PATH`** (uv warned); use `~/.local/bin/cdxt` or the venv |
| `wq doctor` | exit 0; 3 outstanding items, **none GEO-related**: `gh:auth`, `aws:auth`, `ghcr.io/zaproxy/zaproxy:stable` not pulled |

**Documented gap:** `wq doctor` knows the kit's own tools, not this venv — it prints a clean
verdict while `cdx-toolkit`/`curl_cffi` are missing. That is exactly the "a skipped check reads
as clean" failure the kit forbids, so `scripts/geo/run-geo.sh` runs its **own preflight** step
(imports + `py_compile` + `node --check`) and records its exit code in `logs/steps.tsv`. Until
T5/T6 are wrapped as `wq geo *`, this venv is outside `wq doctor`'s field of view.

## Consequences

**Dependencies added:** `cdx-toolkit`, `curl_cffi`, `google-genai`, `anthropic` — one pinned
Python 3.12 venv at `$REPO/.venv` (created by `scripts/geo/bootstrap.sh`, pinned in
`scripts/geo/requirements.txt`), plus the optional `cdx-toolkit` CLIs as uv tools. **L5 and L6
close with no credentials at all.**

**Dependency deliberately deferred:** the npm `googleapis` package (T1). Every T1–T4 call needs a
client credential that does not exist yet, so installing it now would add an unused dependency
with no measurement behind it. It lands in the same commit that unblocks T1.

**Context cost — measured with `wq context`, before and after:**

| | Before this session | After this session |
|---|---|---|
| Enabled MCP servers | 0 (`chrome-devtools`, `github`, `sentry`, `playwright` all disabled) | 0 — unchanged |
| Per-request MCP cost | **~0 tokens** | **~0 tokens** |
| Skills advertised | 3 → ~12 tokens/request | 4 → **~16 tokens/request** (ids only) |
| `geo-citation-probe` body | — | ~2,398 tokens **only when invoked**; 0 reference files |

The entire measurement programme cost **+4 tokens/request** and nothing else. For contrast, the
rejected alternative — enabling both browser MCPs — measures **11,669 tokens/request**
(`chrome-devtools` 30 tools ≈ 6,597; `playwright` 25 tools ≈ 5,072), i.e. ~1.17M tokens over a
100-message session, re-sent on every message whether or not a browser is involved. `wq probe`
covers the same ground at 0.

**Artifact contract:** everything lands in `reports/geo/<runId>/` with a `manifest.json` that
records each step's exit code and the blocked list. No finding is reported from a run whose
artifact is not on disk.

**Runtime cost:** under $5 for the 8-week probe cadence (unchanged; Anthropic web search
≈ $10/1k searches). This session incurred no API cost.

## Outcome — what the tooling actually resolved (run `20261008-193000`)

| Limitation | Result |
|---|---|
| **L5** Common Crawl flakiness | **CLOSED.** 127 collections discovered from `collinfo.json`; 6 sampled; `bitara.co` returned a definitive 404 in all 6, with **no unmeasured collection**. The prior pass's 504 is gone, so the "zero captures" finding is now a measurement rather than an inference. Residual: absence is proven only for the sampled collections, and that caveat is written into the artifact. |
| **L6** TLS/JA3 fidelity | **CLOSED.** The plain-`curl` fingerprint control ran successfully: plain curl with a **Googlebot** UA received the **full** class, while `GPTBot`/`GoogleOther`/`Google-Extended` received the reduced class. So the split is header-driven and *not* fingerprint-driven — and that negative is measured, not assumed. |
| **L7** Edge cause | **Still open** — needs `CLOUDFLARE_API_TOKEN` + zone. Honest wording until then: *the split exists, is UA-driven, and its author is unknown.* |
| L1–L4 | **Still open** — client credentials. |

**Correction recorded because it changed a conclusion:** the first version of `ua_parity.py`
decided "header-driven" from byte-hash inequality between two *different* UAs, while two identical
requests already hashed differently (the page is dynamic). That was a false positive waiting to
happen, and the same code read an unmeasured fingerprint control as a clean negative — the exact
failure mode §3 rule 10 forbids. Both were fixed before any finding was published: the instrument is
now the content class with repeat-stability reporting, and an unmeasured factor is reported as
`not measured` rather than `false`. See `reports/geo/20261008-193000/findings.md` F2.

## Rejected alternatives

Unchanged from `method/GEO-TOOLING-PROPOSAL.md` §6, and re-affirmed here because the cost of each was
measurable in this session:

| Rejected | Why |
|---|---|
| **Any MCP server** (playwright, chrome-devtools, browser) | Measured **11,669 tokens/request** for the pair, re-sent on every message. `wq probe` read the same page at **0**. No limitation in L1–L7 needs stateful interaction |
| **Bing Web Search API** | `[SOURCED]` its terms restrict automated probing; T2 (Bing Webmaster) is the legitimate path |
| **Google Indexing API for general URLs** | Documented for `JobPosting`/`BroadcastEvent` only — policy risk for no gain |
| **`gcloud` CLI** | `MISSING` here, and GSC auth needs a service-account JSON that `googleapis` consumes directly |
| **`pipx`** | Not installed and redundant: `uv tool install` already covers it |
| **`ai.txt` generator** | Defunct proposal; the site correctly 404s `/ai.txt` |
| **`ddgs`/`duckduckgo_search` as the primary SERP path** | It is exactly what got bot-challenged. Opportunistic fallback only, and a challenge is logged `not measured` |
| **Any GEO rank-tracker SaaS without an API and an artifact** | No `reports/` file, no diff, no provenance |
| **Two tools for one capability** | One impersonator (`curl_cffi`), one corpus client (`cdx-toolkit`) |
| **Python 3.14 as the tooling interpreter** | Host default 3.14.7 is very new; 3.12 was pinned to guarantee wheel resolution |

## Blocked items — each with an owner, none silently dropped

| # | Blocked measurement | Needs | Owner | Effect while blocked |
|---|---|---|---|---|
| L1 | Google index status | GSC property access + service account (`GSC_SA_JSON`, `GSC_SITE`) | **Client** | The client's exact complaint stays an inference |
| L2 | Bing/Copilot index status | `BING_WEBMASTER_API_KEY` | **Client** | One uncontrolled Bing sample only |
| L3 | `site:` counts | `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` | **Client** | DuckDuckGo/Mojeek challenges stay `not measured` |
| L4 | Citation probing | `GOOGLE_API_KEY` (Gemini first, per §9 rollout), then `ANTHROPIC_API_KEY` | **Client** | No before/after citation claim is possible |
| L7 | Cause of the per-UA split at the edge | `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ZONE_ID` (read-only) | **Client** | Only the *existence* and *shape* of the split is provable, not its author |
| — | Recrawl signalling | `INDEXNOW_KEY` | **Client** (free key) | T8 not started |
| — | Any code change to the site | **The website source repository** | **Client** | Audit stays black-box; fixes are documented, not applied |
| — | Whether the per-UA variant is intentional | An answer, plus a named owner | **Client** | Determines config fix vs. escalation |
| — | `gh` authentication | `gh auth login` (account `laulj`) | **Us** (interactive) | No `wq gh-report` |
| — | `cdxt` on `PATH` | `uv tool update-shell` or an absolute path | **Us** (interactive) | Cosmetic; the venv path works |
| — | ZAP image for DAST | `docker pull ghcr.io/zaproxy/zaproxy:stable` | **Us** | Security layer untouched; SCOPE-GATED by `security/scope.yml` regardless |

## Open items

1. **T7** needs `CLOUDFLARE_API_TOKEN` + zone access before L7 can close. Until then the honest
   wording is *"the split exists and is measurable; who authors it is unknown"*.
2. **T1** needs the GSC service account added as a property user.
3. **Wrap T5/T6 as `wq geo corpus` / `wq geo parity`** once the second run exists (rung 2), and
   add a `wq geo` preflight so `wq doctor` stops reporting this environment as fully ready.
4. **T8 (IndexNow)** is free and unblocked once a key exists — it removes the recrawl throttle
   caused by the missing `ETag`/`Last-Modified`, but it does **not** touch Google.
5. **Re-run `scripts/geo/run-geo.sh` after any fix** and diff `manifest.json` + the JSON
   readings; that diff, not prose, is the proof of movement.
