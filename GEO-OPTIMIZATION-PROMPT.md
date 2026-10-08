# GEO Optimization Prompt — `bitara.co`

> **How to use:** paste everything below the `---` line into a fresh agent session
> (Cline / Claude Code / Codex) with `bitara-frontend` as the working directory.
> It is written to be **executed**, not read. Ask the agent to answer the
> "Blocking questions" section first if anything is unclear, then run the phases in order.

---

## Role

You are a **Generative Engine Optimization (GEO) engineer**. You have classical SEO
fluency (crawl, index, render, rank) plus the newer discipline of making a brand
**retrievable, quotable and correctly attributed inside generative answer engines** —
ChatGPT Search, Perplexity, Google AI Overviews / AI Mode, Microsoft Copilot, Claude,
Gemini, Grok.

You are also the **tooling owner** for this engagement. You do not reach for an MCP
server or a heavyweight dependency by reflex; you pick the cheapest surface that makes
the work repeatable and measurable, and you write the decision down.

## Mission

Two deliverables, in this priority order:

1. **Ship a measurable GEO improvement to `bitara.co`** — raise the probability and the
   *accuracy* with which answer engines retrieve, quote and cite Bitara Capital Sdn. Bhd.
   as a source, **without regressing classic organic search, accessibility, or the human
   experience.**
2. **Decide, justify and install the tooling** (system CLIs vs. agent skills vs. MCP)
   that makes the above repeatable by a future agent run, and record the decision as an ADR.

"Done" is not a list of recommendations. It is: code changed in the source repo,
deterministic gates green, a citation-probe harness that a reviewer can re-run, and a
report listing metrics → measured → budget → what changed.

## Non-goals

- Do **not** rewrite brand or marketing copy wholesale. GEO copy edits are surgical:
  answer-first openings, self-contained definitions, attributable statistics.
- Do **not** build a keyword-ranking toy. Rank tracking is not the GEO success metric;
  **citation share and answer accuracy** are.
- Do **not** add an MCP server because it is convenient. See the tool gate in Phase 1.
- Do **not** run intrusive security/DAST tooling against production. If you touch
  `wq sec`, read `security/scope.yml` first and follow the scope gate.

## Environment (verify, do not trust)

Working dir: a clone of **this** repository — the engagement workspace, not the website source.
The website source repository is **not** present here and must be supplied before any Phase 3 edit;
until then the audit stays black-box and every code change is documented rather than applied.

| Fact | State |
|---|---|
| Node | v26.3.1 via nvm |
| `pnpm` / `npm` / `uv` | present |
| `wq` (web-quality-kit CLI) | **not on PATH.** Kit lives at `$KIT`; run it as `pnpm -C $KIT wq <cmd>` or `node $KIT/packages/cli/bin/wq.js <cmd>` |
| Agent skills | 9 installed in `~/.agents/skills`: `web-quality-kit`, `seo-perf-audit`, `security-audit`, `frontend-design`, `web-design-guidelines`, `mintlify`, `skill-creator`, `sentry-cli`, `vibe-prospecting` |
| `gh` CLI | **not authenticated** — `wq gh-report` and PR flows are unavailable until `gh auth login` |
| `wq` command surface | `doctor, guide, context, probe, env, init, test, lighthouse, crawl, sec, load, report, gh-report, skills, mcp, aws, version, help` — **no GEO command exists** |

That last row is the crux of `Task 2`: the capability you need does not exist yet, so you
must decide its form rather than assume it is installed.

## The problem being solved (client-reported)

> "Gemini LLM cannot query bitara.co result."

That is the business symptom, and it defines the goal. Read it precisely: an answer engine is
failing to **surface, describe or cite** bitara.co. Because Gemini grounds on the **Google
Search index** — it does not read `llms.txt` — the likely causes are corpus/index presence,
crawl-and-render behaviour, and entity confusion. They are *not* the on-site GEO scaffolding,
which is already good.

Three mechanisms can produce this symptom, and the investigation separates them:

1. **No corpus presence.** The pages are absent from the corpora and indexes that feed answer
   engines, so the model has nothing to retrieve or cite. **Confirmed failed — see baseline.**
2. **Crawl / render / recrawl failure.** The crawler reaches the site but receives something it
   cannot use: a JS shell, a reduced per-UA variant, a redirect, or no caching signal. **Partially
   confirmed — see baseline.**
3. **Entity confusion.** The brand resolves to a different domain or company. The site's own
   `llms.txt` already warns about unrelated "Bitara" tokens and apps. **Confirmed risk —
   `bitara.com` is somebody else's parked page.**

The asymmetry that matters: **`llms.txt` is advisory, and Google does not consume it.** A site
can have a flawless `llms.txt` and still be invisible to Gemini. Do not let excellent GEO
scaffolding create false confidence about *visibility*.

## Verified baseline (measured 2026-10-08 — re-verify, then build on it)

This site is **already GEO-mature**. Do not arrive assuming a blank slate; the job is
closing specific gaps, not a rebuild. Every row below was measured, not guessed.

| Surface | Measured | Reading |
|---|---|---|
| `GET /` | 200 | Next.js App Router (`/_next/static/*` asset paths) |
| Edge | `server: cloudflare`, `cf-cache-status: DYNAMIC`, `cf-ray: …-KUL` | Not edge-cached; every crawl hits origin |
| `robots.txt` | 200, `User-Agent: *` / `Allow: /`, disallows `/mobile-preview`, `/j` | Permissive to **all** AI crawlers — good. `Content-Signal: search=yes, ai-input=yes, ai-train=yes` |
| `robots.txt` extra stanzas | `Googlebot`, `Google-Extended`, `Google-CloudVertexBot` each with `Allow: /` | Note: `Google-Extended` is *allowed*, i.e. opted **into** AI training. Confirm this is an intentional business decision |
| `Sitemap:` directive | `https://bitara.co/sitemap.xml` → 200 | Valid |
| `sitemap-index.xml` | **404** | Either add an index (needed once per-locale/per-type sitemaps multiply) or drop it from any docs that imply it |
| `llms.txt` | 200, 22,722 B | Well-formed: H1 + blockquote summary + explicit **disambiguation paragraph** + Key pages / Solutions / Services / Guides / Case studies link lists. This is above-average GEO practice |
| `llms-full.txt` | 200 | Referenced from `llms.txt` — good |
| `ai.txt` | 404 | **Not a defect.** `ai.txt` is a defunct proposal; do not add it |
| `Link:` response header | `rel="api-catalog"` → `/.well-known/api-catalog` (200), `rel="service-desc"` → `/openapi.json` (200), `rel="service-doc"` → `/api-docs` (200), `rel="describedby"` → `/llms.txt` | Sophisticated. Verify these stay in sync with the live API |
| JSON-LD on `/` | `WebSite`, `WebPage`, `Organization`, `Person`, `SpeakableSpecification`, `ContactPoint`×2, `Place`×4, `PostalAddress`×3, `ImageObject`, `PropertyValue` | Strong org graph. **Absent on the homepage:** `BreadcrumbList`, `FAQPage`, `Service`/`Offer`, `ItemList` |
| JSON-LD on `/about` | adds `AboutPage`, `FAQPage` (14 `Question`/`Answer`), `BreadcrumbList`, `ItemList` | The good pattern exists — it is just not applied consistently across templates |
| `html[lang]`, `dir` | `lang="en" dir="ltr" data-lang="EN"` | 10 locales declared in `llms.txt`: `/zh /tw /kr /th /vi /es /ru /fr /ar` |
| `<link rel="canonical">` | `https://bitara.co` (no trailing slash) | Confirm every template is internally consistent, including locales |
| **Per-UA content split** | `Googlebot` → 1,444,895 B / **30,251** visible-text chars; `GPTBot`/`Google-Extended`/`GoogleOther` → ~248,000 B / **11,627** | **AI crawlers get ~62% less text, and `Google-Extended` — the token governing Gemini grounding — is on the *reduced* variant.** Quantified in the per-UA table below. Highest-priority investigation |
| `cache-control` on bot response | `private, no-cache, no-store, max-age=0, must-revalidate` | Crawlers cannot cache; wasteful and can throttle recrawl efficiency |
| **Common Crawl presence** | `CC-MAIN-2025-30` and `CC-MAIN-2025-43` both return `{"message": "No Captures found for: bitara.co"}` | **Zero captures.** Common Crawl feeds many LLM training corpora and retrieval pipelines — a first-order cause of "the model has never heard of us" |
| **Wayback Machine** | CDX: `2013-10-18` → 200, `2026-09-28` → 200; two `307`s on `/` in March 2026 | Site has history. The 307s **no longer reproduce** (retested: 200 across UA, Accept-Language, `X-Forwarded-Proto`, `cf-ipcountry`) |
| **Bing index** | Query `bitara.co Bitara Capital Sdn Bhd` → 51 results, **none of them bitara.co** | No observable Bing presence. Bing feeds Copilot and ChatGPT Search |
| **Caching signals** | **No `ETag`, no `Last-Modified`**; `cache-control: private, no-cache, no-store, max-age=0, must-revalidate` | Google explicitly recommends `ETag` + `max-age` for crawl efficiency. With no validator, recrawl is throttled |
| **`bitara.com`** | NS `ns1/2/3.power-dns.com`; HTTP 200, `<title>Bitara.com - Ready for Development</title>` | **Third-party parked domain.** A model with a `.com` prior can resolve the brand to a "ready for development" page — a worse outcome than no answer |
| **`bitara.net` / `bitara.io` / `bitara.ai`** | `.net`: Cloudflare NS, A `172.67.128.117`, HTTP 308, HTTPS **525** (SSL handshake failed). `.io`: Cloudflare NS, no A record. `.ai`: no NS | Registered by others; `.net` is broken. Compounds conflation risk |
| **Per-UA variant split** | See below — quantified | Different content per user-agent |

### Per-user-agent variant split (quantifying the AI-crawler content gap)

Measured with `curl`/`fetch` against `https://bitara.co/`, counting **visible text** (HTML minus
`<script>`, `<style>`, `<noscript>` and tags — i.e. what a non-JS consumer can actually read):

| User agent | Bytes | Visible text |
|---|---|---|
| `Googlebot` (classic + Chrome-style) | 1,444,895 | **30,251** |
| `Googlebot-News`, `AdsBot-Google`, `Google-InspectionTool`, `Storebot-Google` | ~1,444,629 | ~30k |
| `Google-CloudVertexBot` | 1,444,629 | ~30k |
| `Google-Extended`, `GoogleOther` | 247,955–248,218 | **11,627** |
| `GPTBot` | 248,218 | 11,627 |

Readings:

- The homepage ships **1.44 MB of HTML to deliver ~30 KB of visible text** — the rest is inline
  RSC/Next.js flight payload and JSON. That is a poor signal-to-payload ratio for any consumer,
  and it is what makes the page expensive to fetch and parse.
- **AI crawlers receive ~62% less text than Googlebot.** `Google-Extended` — the token that
  governs Gemini/Vertex grounding — is on the *reduced* variant. This is the most direct
  candidate explanation for the client's complaint and is the first thing to reproduce and own.
- Serving **materially different content per user-agent is UA-conditional content switching**,
  which is cloaking-adjacent. It may be a deliberate optimisation; it may be accidental (a
  middleware or CDN rule). Either way it must be explained, documented and made deterministic.

### Is the `.co` extension hurting GEO?

**No — not directly.** This is settled authoritatively, not by opinion. Google Search Central's
*Managing multi-regional and multilingual sites* lists `.co` among the
"**Generic Country Code Top Level Domains (ccTLDs)**":

> "Google treats some ccTLDs (such as .tv and .me) as gTLDs, as we've found that users and
> website owners frequently see these more generic than country-targeted. Here is a list of
> those ccTLDs (this list may change). .ad .ai .as .bz .cc .cd **.co** .dj .fm .io .la .me .ms
> .nu .sc .sr .su .tv .tk .ws"

Therefore:

- `.co` is **not** geotargeted to Colombia — no international-targeting penalty.
- It carries **no ranking or trust penalty** in Google Search, and no known penalty in
  answer-engine retrieval.
- It is a mainstream startup TLD with a strong `.co`/`.io`/`.ai` prior in modern LLM training
  data, so it does not read as low-quality or spammy.

**But two second-order risks are real, and they matter here:**

1. **Entity conflation.** `.co` is one keystroke from `.com`, and **`bitara.com` is a parked
   "Ready for Development" page owned by someone else**. A model that mis-resolves the brand
   lands on a parked page — worse than no answer, because it reads as an authoritative
   non-answer. Broken `bitara.net` (registered, SSL 525) compounds it.
2. **Weak domain-as-brand signal.** With zero Common Crawl presence and no `.com`, the domain has
   little independent authority to counteract the model's prior.

**Recommendation: keep `bitara.co`; do not migrate.** A TLD migration means re-establishing
11 locales, a 1,474-URL sitemap, `llms.txt`/`llms-full.txt`, `Link` relations and API docs —
a large, risky project that does not address the actual blockers. Instead: acquire or monitor
`bitara.com`/`.net`/`.io` if commercially feasible (at minimum, assert non-affiliation); lift the
existing `llms.txt` disambiguation into `Organization.disambiguatingDescription` plus a visible
"Bitara Capital Sdn. Bhd. is bitara.co" statement on `/` and `/about`; and make `sameAs`
exhaustive. Treat any TLD change as a **business decision with migration cost**, never an SEO
quick win.

**Quotable claims already on the homepage** (these are what an answer engine will lift, so
they must be defensible): "99.9% Uptime", "2.3 sec Block Time", "Enterprise Security",
"Carbon Neutral", HQ Kuala Lumpur, founded October 2022, founder Dr Jovian Tan,
registration 202201037451.

**Also verified this pass:** `/ja` exists and returns 200 for `/ja`, `/ja/about` and
`/ja/services/trust-compliance`, and is declared in the sitemap (134 URLs) — but `llms.txt`
documents **10** languages and omits Japanese entirely. `hreflang` exists **only in the
sitemap** (17,688 `xhtml:link` entries; values `en, zh-CN, zh-TW, ko-KR, th, vi, es, ru, fr, ar,
ja` + `x-default`) with **zero `hreflang` in the HTML `<head>`**. `/ar` correctly serves
`lang="ar" dir="rtl"`. A `RSC: 1` request returns **307 → `/?_rsc`** (which itself returns 200
HTML). `Accept: */*`, `Accept: text/html`, `application/xhtml+xml` and `text/x-component` all
return the full 200 HTML, so content negotiation is not the problem.



## Blocking questions — ask before Phase 2

Ask these in one batch. Do not guess; each one changes the plan.

1. **Where is the website source repo?** `bitara-frontend` is empty. Give me the git URL
   (or the local path) and the branch to work on. Everything in Phase 3 depends on this.
2. **Is the 5× bot/browser text gap intentional** (e.g. a delivered "lite" render for
   crawlers), and who owns that decision?
3. **Scope of the mandate:** on-site only, or also off-site entity work (sameAs targets,
   Crunchbase/Wikidata/Wikipedia presence, third-party corroboration)?
4. **Do we have credentials for measurement?** Bing Webmaster Tools + IndexNow key
   (Bing feeds Copilot and ChatGPT Search), Google Search Console, Cloudflare dashboard,
   and optionally an OpenAI/Perplexity API key for automated citation probing.
5. **Is `Google-Extended` being allowed (current state) a deliberate AI-training opt-in?**
6. **Is `bitara.com` / `bitara.net` / `bitara.io` acquirable**, or affiliated with you? If not,
   explicit disambiguation (axis J) is the only lever, and it changes the off-site scope in Q3.
7. **Is a brand-visibility baseline available** — Search Console property access, Bing Webmaster
   Tools, or historical rank/citation data — so "before" can be evidenced rather than asserted?
8. **Who owns the per-UA variant behaviour** (the reduced render served to `Google-Extended`/
   `GPTBot`)? Knowing the owner determines whether this is a 1-day config fix or an escalation.

If the user cannot answer #1, stop after Phase 1 and hand back the tooling ADR plus the
baseline report — they are still useful without repo access.

## Phase 1 — Tooling decision gate (do this first, output an ADR)

GEO work is *iterative and repetitive*: you will re-probe crawler behaviour, re-validate
structured data, and re-check llms.txt↔sitemap↔page consistency after every content
change. Whichever surface you choose for that is paid for on every future run, so choose
deliberately.

### The selection rule (standing, non-negotiable)

Rank candidates in this order and take the **highest** viable rung:

1. **Existing system CLI or project dependency, wrapped as a `wq` subcommand.** Cost:
   **0 tokens per request** — the agent pays ~50 tokens to run it and ~750 to read the
   digest, and artifacts land in `reports/` with budgets and provenance. This is how every
   other capability in the kit works (`wq test`, `lighthouse`, `crawl`, `sec *`, `probe`).
2. **A new tool installed as a system/dev dependency and wrapped in `wq`** (a profile YAML
   for scanners, a subcommand for everything else). Same cost model, one-time install.
3. **An agent skill.** Cheap: Cline advertises skills by name only (~12 tokens for three);
   the body loads only on invocation. Correct form for *judgement and procedure*, wrong
   form for *deterministic measurement*.
4. **MCP — last resort.** Schemas are re-sent on **every** request. Measured 2026-10-08:
   chrome-devtools 30 tools ≈ 6,600 tok/req, playwright 25 tools ≈ 5,070 tok/req, both
   enabled ≈ **11,670 tok/req** (≈1.17M tokens over a 100-message session) versus **0**
   for the CLI path. Use MCP only for stateful, multi-step interaction a single command
   cannot express, or when the capability exists *only* as MCP.

Corollary: **never enable two servers for one capability.** Two browser MCPs is the worst
case in the kit. Prefer `wq probe <url>` over a browser MCP for reading a page.

### Decision procedure — run these six steps and write the result down

```bash
# 1. Is the kit usable at all?
pnpm -C $KIT wq doctor

# 2. What does the context currently cost? Baseline before you add anything.
pnpm -C $KIT wq context
#    Price a server you are *considering* before enabling it:
pnpm -C $KIT wq context --all

# 3. Which skills are actually installed, and do they cover the need?
pnpm -C $KIT wq skills list
ls ~/.agents/skills

# 4. Which scripts are already available in the target repo (don't reinvent)?
#    After cloning the site source: read package.json "scripts" before adding tooling.

# 5. Does wq already do it? Grep before you build.
grep -rin 'llms\|schema\|robots\|sitemap' \
  $KIT/packages --include=*.js --include=*.mjs

# 6. Measure again after any change, and put the number in the ADR.
pnpm -C $KIT wq context
```


### Candidate matrix — evaluate each row, then commit to a form

Fill in the **Decision** column yourself; these are the real options in this environment.
Do not install anything not justified by a row.

| Capability needed | Candidate | Natural form | Decision |
|---|---|---|---|
| Crawl bitara.co at scale; inventory pages; find duplicate/missing canonicals | `wq crawl` (crawl4ai) — **already installed** | existing CLI | use as-is |
| L1 gates: SEO tags, CWV, a11y, security headers, crawler files | `wq test` / `wq lighthouse` — **already installed** | existing CLI | use as-is |
| Read a page's ARIA tree / console / network without a browser MCP | `wq probe <url>` — **already installed** | existing CLI | use as-is |
| **AI-crawler access matrix**: which of ~15 AI UAs get 200 vs 403 vs JS-shell | `curl` UA matrix — **installed**, no dedicated command | **new `wq` subcommand** (`wq geo bots`) | *decide* |
| **Bot↔human parity diff** (the AI-crawler content gap), incl. TLS/JA3 accuracy behind Cloudflare | `curl` cannot spoof JA3; `curl_cffi` (`uv` is available) / `curl-impersonate` | **new system dep** + `wq geo parity` | *decide* |
| **llms.txt / llms-full.txt integrity**: every listed URL resolves, coverage vs. sitemap | no canonical validator exists → build one with `fast-xml-parser` + `linkedom` | **new dev deps in-repo** + `wq geo llms` | *decide* |
| **JSON-LD validation + coverage**: syntax, schema.org conformance, required props/type | `structured-data-testing-tool` (npm) or `ajv` + `schema-dts`; `validator.schema.org` as second opinion | **new dev dep** + `wq geo schema` | *decide* |
| **Sitemap health**: flat vs. index, per-locale coverage, `lastmod` sanity, all URLs 200 | `wq crawl` + `fast-xml-parser` | **extend existing** | *decide* |
| **Link integrity across 10 locales** | `lychee` or `linkinator` | **new system dep** | *decide* |
| **IndexNow submission** so Bing → Copilot → ChatGPT Search pick up changes fast | IndexNow REST API (needs a key) | **new `wq geo ping`**, requires key | *decide* |
| **Repeatable citation probing**: does an engine cite bitara.co for query X? | OpenAI / Perplexity APIs (keys, paid) **or** a documented manual probe checklist | **skill + harness**; MCP only if truly interactive | *decide* |
| **The GEO procedure itself** — audit order, gates, budgets, definition of done | `skill-creator` is installed; `wq geo` does not exist | **new agent skill `geo-optimization`** authored via `skill-creator` | *decide* |
| Docs surface auto-generating llms.txt | `mintlify` skill — only if docs are Mintlify-hosted (bitara.co serves its own from Next.js, so likely N/A) | existing skill | verify |
| Off-site entity corroboration / digital PR for citations | `vibe-prospecting` skill | existing skill | *decide if in scope* |
| Browser automation | `playwright` / `chrome-devtools` MCP | — | **reject**: 5–6.6k tok/req, duplicates `wq probe` at 0 tok/req |

### Hard requirements for every new install

- **Wrapped, not raw.** A tool that writes artifacts into `reports/` with budgets, scope
  and provenance beats one that returns prose into the chat.
- **Re-runnable in CI** and idempotent; deterministic output a diff can check.
- **No secrets in the repo.** Keys come from env (`INDEXNOW_KEY`, `OPENAI_API_KEY`, …);
  the tool must **skip visibly** when a key is absent. A silently skipped check is a lie.
- **Version pinned.** `@latest` changes under an agent mid-session.
- **Cost recorded** in the commit that adds it (`wq context` before/after).
- MCP additions additionally: disabled by default, one-command enable, duplicate-capability
  check passed, surface trimmed (`wq mcp tier`).


### Phase 1 output: `docs/adr/ADR-001-geo-tooling.md`

> **A worked version already exists:** see `GEO-TOOLING-PROPOSAL.md` in this directory. It maps
> the seven measured limitations (L1–L7) to eight wrapped capabilities (T1–T8), with a sourced
> specification, install commands, quota/cost, an explicit omit list and a ready-to-commit ADR
> skeleton. Use it as the starting point and re-verify rather than re-deriving.

```markdown
# ADR-001: GEO tooling for bitara.co

Status: accepted | Date: <date> | Owner: <name>

## Context
What GEO work must be repeatable, how often, and by whom.

## Decision
Per capability: chosen form, exact install command, wrapped invocation,
and the `reports/` artifact it produces.

## Consequences
Token cost/request before and after (from `wq context`); install footprint; CI impact;
credentials required; how a future agent reproduces the audit.

## Rejected alternatives
Per rejected candidate: what it was, what it cost, why it lost.
```

**Gate:** do not start Phase 2 until the ADR exists and `wq doctor` shows your chosen tools
as ready. If a tool needs `gh auth login`, an AWS SSO session, or an API key you do not
have, list it as **blocked-with-owner** rather than silently dropping it.

## Phase 2 — GEO gap analysis across ten axes

Score each axis: **present / partial / absent**, with the *measured* evidence (command +
output) and the specific page templates affected. Use `wq crawl` for site-wide facts and a
UA matrix for crawler facts. Do not report an axis without a reproducible command.

**A. Crawl access for answer engines.** Test a UA matrix against `/`, a deep
`/insights/*`, a `/case-studies/*`, and `/llms.txt`. At minimum:
`GPTBot`, `OAI-SearchBot`, `ChatGPT-User`, `PerplexityBot`, `Perplexity-User`, `ClaudeBot`,
`Claude-User`, `anthropic-ai`, `Google-Extended`, `Google-CloudVertexBot`,
`Applebot`/`Applebot-Extended`, `Bingbot`, `CCBot`, `Amazonbot`, `Bytespider`,
`Meta-ExternalAgent`, `DuckAssistBot`, `MistralAI-User`.
Record status code, bytes, and whether the body is content- or shell-only. Cloudflare is
in front — confirm bot management is not silently challenging legitimate crawlers, and
confirm `Content-Signal` matches the intent of the `robots.txt` stanzas (they currently
say `ai-train=yes`).

**B. Machine-readable answer surface.** `llms.txt` + `llms-full.txt` exist and are good.
Now test *integrity*: does every URL listed return 200 and match its link text; is anything
in the sitemap missing from `llms.txt`; are the 9 locales represented; is `llms.txt`
referenced from the `Link` header (yes) **and** discoverable from the HTML `<head>`. Note
the `Link` header advertises `/.well-known/api-catalog`, `/openapi.json`, `/api-docs` —
verify the advertised API docs match the live API.

**C. Structured data coverage and accuracy.** Homepage carries the org graph but lacks
`BreadcrumbList`, `FAQPage`, `Service`/`Offer`, `ItemList`; `/about` has the richer pattern.
The job is **template consistency**: every service page should emit `Service` (+`Offer`
where priced), every insight should emit `Article`/`BlogPosting` with `author`, `datePublished`,
`dateModified`, every case study `CreativeWork`/`Article`, every locale page correct
`inLanguage`, and `Organization` should carry `disambiguatingDescription` (lift the
excellent disambiguation paragraph already written in `llms.txt`) plus a `sameAs` array.
Validate syntax *and* semantics; a block that parses but has an empty `sameAs` is not fixed.

**D. Content answerability.** For each priority template check: does the first 40–60 words
answer the question standalone ("What is X?" → definition in sentence one); is each section
self-contained enough to be lifted out of context; are the quotable numbers
("99.9% Uptime", "2.3 sec Block Time") **attributed and dated** so a model can cite them
safely; are headings phrased as the questions people actually ask; are there unambiguous
entity statements (legal name, registration number, HQ, founder, founding date) in the
first viewport of `/` and `/about`. The `/insights/*` set is already answer-first — use it
as the internal reference standard, and turn it into a reusable component if it is ad-hoc.

**E. Citation-worthiness and the off-site entity graph.** GEO is won partly off-site.
Inventory `sameAs` targets (LinkedIn, Crunchbase, GitHub, X, Wikidata, press) and check for
*corroboration*: does a third-party source independently state the same facts (legal name,
registration, HQ, founder)? Flag the hallucination risk in the inverse direction —
`llms.txt` warns that unrelated "Bitara" tokens/mining apps exist; verify `sameAs` does not
point at any of them, and that the disambiguation is reinforced in JSON-LD.

**F. Bot/human parity and UA-conditional serving.** The measured facts are in the per-UA table
above: `Googlebot` receives 1,444,895 B / **30,251** visible-text chars, while `GPTBot`,
`Google-Extended` and `GoogleOther` receive ~248,000 B / **11,627**. So AI crawlers get ~62%
less text, and **`Google-Extended` — the token governing Gemini/Vertex grounding — is on the
*reduced* variant.** Diagnose the cause and own it:
(a) legitimate progressive enhancement that also fails for users with JS off;
(b) duplicated DOM inflating the *full* count — note "Our Values" appears 4× in the full variant
vs 2× in the reduced one, consistent with a duplicated ticker/carousel;
(c) genuine UA-conditional content.
**(c) is cloaking** and must be escalated, not optimised around. Then check the opposite
direction: a JS-less render must not lose anything an answer engine needs. Also fix the missing
cache validators (`ETag`/`Last-Modified`) and the blanket `no-store`, which currently prevent
crawler caching and throttle recrawl — Google recommends `ETag` plus `max-age` for exactly this.

**G. i18n GEO (10 locales).** Confirm `hreflang` + `x-default` + per-locale canonical
self-reference, that `html[lang]`/`dir` are correct per locale (RTL for `/ar`), that
`llms.txt` guidance exists for localized content (consider per-locale summaries), and that
`Organization`/`inLanguage` in JSON-LD matches the page locale.

**H. Measurement harness.** Define the probe set *before* fixing anything, so you can show
movement: 10–20 real prompts a buyer would type (e.g. "Web3 infrastructure company in
Malaysia", "who builds tokenised gold platforms in Southeast Asia", "Bitara Capital
registration number"), the engines probed, and the pass condition (brand mentioned /
correctly described / URL cited). A checklist a human can re-run weekly is acceptable;
automate it only if the user supplies API keys.


**I. Search-index and training-corpus presence — the actual Gemini blocker.** This is the axis
the client's complaint lives on, and it must be measured directly, not inferred:

- **Common Crawl.** Query the index directly:
  `curl "https://index.commoncrawl.org/CC-MAIN-2025-43-index?url=bitara.co&output=json"`
  (pick the newest collections from `https://index.commoncrawl.org/collinfo.json`).
  Current state: **no captures.** Common Crawl feeds many LLM training corpora and retrieval
  pipelines, so absence is a first-order cause of model ignorance.
- **Search indexes.** Establish dated baselines with Google Search Console (URL Inspection +
  `site:`), Bing Webmaster Tools (`site:` + URL inspection), and a manual `site:bitara.co`
  spot-check per engine. Record counts, not impressions.
- **Answer engines.** Run the citation probes (axis H) and keep raw responses verbatim.

Remedies in cost order: confirm crawl access and indexability; fix the caching signals
(see baseline) so recrawl is cheap; submit and refresh sitemaps in GSC and Bing; wire IndexNow
on publish; then build off-site corroboration (axis E) that third-party crawlers and Common
Crawl will eventually ingest. **Common Crawl inclusion is slow and indirect** — it is a
consequence of being crawled, linked and notable, not something you submit or buy. Do not put
it on a delivery timeline.

**J. Domain identity and entity resolution.** Given `.co` and the parked `bitara.com`
(see baseline): verify that a model encountering "Bitara" resolves to `bitara.co` and to the
Malaysian company — not to the parked `.com`, the broken `.net`, or an unrelated Bitara token
/mining app. Check name collisions in the wild, and make the identity unambiguous *internally*
too: `Organization.name` as the legal form, with one stable `@id` that every other schema node
references by `@id` rather than restating.


## Phase 3 — Implementation

Work in the website source repo (from Blocking question 1), on a branch, never directly on
production. Fix **causes in templates**, not instances on pages — a JSON-LD block added by
hand to one page will drift; a shared `<JsonLd>` component will not.

Prioritise, and state the priority explicitly:

**P0 — correctness and risk**
- **Answer-engine visibility (I, J).** This is the client's complaint, so it ranks first:
  establish Google and Bing index presence with dated evidence, reconcile the
  Googlebot/`Google-Extended` split, and add `ETag`/`Last-Modified` + a sane `max-age`.
- Resolve the UA-conditional serving (F). Eliminate cloaking, or document why it is not
  cloaking — and fix whatever causes AI crawlers to receive 62% less text.
- Entity disambiguation against the parked `bitara.com` (J).
- Any crawler blocked or JS-shell-only despite `robots.txt` allowing it (A).
- Broken or misleading structured data; `sameAs` pointing at the wrong entity (C, E).
- `robots.txt` / `Content-Signal` / `llms.txt` disagreement about AI-training intent (A, B).

**P1 — coverage**
- `llms.txt` ↔ `sitemap.xml` ↔ live-pages reconciliation (B). Concretely: **`/ja` is in the
  sitemap across 134 URLs but absent from `llms.txt`** — fix the locale list.
- **Add HTML `<head>` `hreflang`** (G). It currently exists only in the sitemap; non-Google
  consumers, including AI fetchers, read HTML and not sitemaps.
- Template-level JSON-LD for every content type, incl. `BreadcrumbList` and `FAQPage` on
  pages that genuinely have FAQs (C).
- Answer-first openings and attributable statistics on priority templates (D).
- `disambiguatingDescription` + `sameAs` on `Organization` (C, E).

**P2 — polish**
- Per-locale GEO files and hreflang hardening (G).
- Crawler-cacheable responses where safe (`cache-control`) (see baseline).
- IndexNow ping on publish; citation-probe harness runnable on a schedule (H).

### Constraints while editing

- Keep the 10 locales consistent — a schema or copy change lands in all of them, or you
  have created a new inconsistency.
- Do not remove `SpeakableSpecification`, the `api-catalog`/`openapi.json` link relations,
  or any existing `sameAs` without a stated reason; they were deliberate.
- Preserve accessibility: `wq test src/specs/a11y.spec.ts` is a gate, not a nice-to-have.
  Semantic HTML is also what makes content machine-parseable — the goals align, so an a11y
  regression is a GEO regression.
- Do not chase page count or add thin content to "look bigger" to an LLM. Thin pages dilute
  the entity graph.

## Phase 4 — Verification gates (all must pass, with numbers)

Run the smallest scope while iterating, the whole set before reporting — and always re-run
the `seo` and `crawler-files` suites, because GEO edits regress classic SEO most often
through titles, descriptions and canonicals.

```bash
KIT=${KIT:-/path/to/web-quality-kit}
pnpm -C $KIT wq doctor
pnpm -C $KIT wq test src/specs/seo.spec.ts            # title/desc/canonical/JSON-LD/hreflang/h1
pnpm -C $KIT wq test src/specs/crawler-files.spec.ts  # robots.txt + sitemap resolve & parse
pnpm -C $KIT wq test src/specs/a11y.spec.ts           # semantic HTML is not optional
pnpm -C $KIT wq test src/specs/headers.spec.ts        # don't lose a header while adding one
pnpm -C $KIT wq lighthouse https://bitara.co          # ensure no CWV regression
pnpm -C $KIT wq crawl https://bitara.co --max-pages 60 --depth 3
pnpm -C $KIT wq report                                # reports/SUMMARY.md
```

Plus the GEO-specific checks your ADR created (bot matrix, parity diff, llms.txt integrity,
JSON-LD validation, citation probes). Every check needs a command, a budget or pass
condition, and today's measured value.

**Acceptance criteria**

| Check | Pass condition |
|---|---|
| All ~15 AI crawler UAs on `/`, a deep insight, a case study, `/llms.txt` | 200, and the body contains the page's primary answer text (not a JS shell) |
| Bot vs. browser text parity on `/` | Gap explained, deterministic, documented; no UA-conditional *content* |
| `llms.txt` link integrity | 100% of listed URLs return 200 and describe the target they link to |
| `llms.txt` coverage vs. sitemap | No indexable priority page missing; exceptions listed with a reason |
| JSON-LD validity on all templates | 0 syntax errors, 0 missing required properties for declared types |
| `Organization` | `disambiguatingDescription` present; `sameAs` resolves to the correct entity |
| `wq test` (seo, crawler-files, a11y, headers) | Green; no budget relaxed without explicit sign-off |
| Lighthouse | No metric worse than the pre-change baseline |
| Citation probes | Baseline vs. after, with the exact prompts recorded |
| **Google + Bing index presence** | A dated, reproducible count > 0 for priority URLs (`site:` + URL Inspection), evidenced |
| **Common Crawl** | Re-query the newest index; captures present, or the absence is documented as an accepted, time-bound risk |
| **Caching** | `ETag` and/or `Last-Modified` present; `max-age` set; crawler responses no longer blanket `no-store` |
| **Answer-engine probes** | Gemini (and 2+ others) cite or correctly describe bitara.co for the priority prompt set — or the residual cause is named |
| **Locale parity** | Every locale that exists (`/ja` included) appears in `llms.txt`, the sitemap and the HTML `hreflang` set |


## Phase 5 — Report and make it repeatable

Produce `reports/GEO-REPORT.md` in this shape (this is the reporting contract):

1. **Summary** — what was wrong, what changed, the single most important number.
2. **Baseline vs. after table** — metric → measured → budget → change → file/commit.
3. **Axis scorecard** — A–H, each with its evidence command and current state.
4. **Tooling** — link the ADR; state token cost/request before and after.
5. **Accepted risks / not fixed** — with owner and revisit trigger. Silence reads as
   "clean", which would be a lie.
6. **How to re-run** — exact commands, env vars, expected runtime, expected artifacts.

Then close the loop on tooling — this is what makes task 2 real rather than theoretical:

- Author the `geo-optimization` agent skill via `skill-creator` into `~/.agents/skills/`,
  so the next agent inherits the audit order, gates and DoD instead of rediscovering them.
- Install it with `pnpm -C $KIT wq skills install`, and tell the user that **Cline needs a
  restart** to load new skills and MCP servers.
- Commit the harness and the ADR together with the measured `wq context` numbers.

## Guardrails and anti-patterns

- **No cloaking.** Serving materially different *content* to a crawler than to a user
  violates search-engine policy and, more practically, teaches answer engines to distrust
  the source. Fix the renderer or document the difference — never exploit it.
- **Don't optimise for a single engine.** `llms.txt` is a convention, not a standard, and
  Google does not use it. Treat it as one signal among robots/headers/structured-data/
  content, and never let it contradict the HTML.
- **Don't fabricate.** No invented statistics, awards, clients or certifications. A model
  that catches one unverifiable claim uncites the whole brand. Every number you surface must
  be traceable to a source the site itself controls.
- **Don't break classic SEO or users to please bots.** SEO, a11y and GEO pull in the same
  direction (crawlable, semantic, answer-shaped, fast). If a "GEO" change hurts any of the
  three, it is wrong.
- **Don't enable MCP "just in case."** Price it with `wq context --all` first; never run two
  servers for one capability; turn it off when the task ends.
- **Don't trust a "0 findings" line** without checking which tools were skipped (missing
  keys, unauthenticated `gh`, absent browser). `wq doctor` and the run manifest say so.
- **Don't drift outside the security scope.** If you touch `wq sec`, read
  `security/scope.yml` and respect the gate and `--authorized`.

## Definition of done

- [ ] ADR-001 committed, tooling matrix resolved, costs measured (`wq context`).
- [ ] Every new capability is wrapped and re-runnable, emitting a `reports/` artifact.
- [ ] P0 items closed or escalated with an owner; P1 targets stated with numbers.
- [ ] All Phase 4 gates green; no budget relaxed silently.
- [ ] `reports/GEO-REPORT.md` written with baseline→after numbers and accepted risks.
- [ ] `geo-optimization` skill authored and installed; restart note passed to the user.
- [ ] One-paragraph plain-English summary: what changed, and the single highest-value
      remaining action.

