# Bitara Capital — GEO fix plan (`bitara.co`)

**Purpose:** one plan, two readers, both able to act on it.

| Reader | Read | Why |
|---|---|---|
| **Human** (engagement lead, client, engineering owner) | §1–§3, then each task card's *Evidence / Change / Owner* fields | to decide, staff and approve |
| **LLM executor** (a coding agent in the site repo) | everything in order, but treat §2 (gates), §3 (rules) and each card's *Locate / Change / Verify / Forbidden* fields as executable instructions | to make the change deterministically and prove it |

Every number here is `[MEASURED]` and traces to an artifact in `reports/geo/20261008-193000/`.
Nothing here re-litigates the settled baseline (`HANDOFF-PROMPT.md`). Inference is labelled.

> **Blocker that shapes the whole plan:** the website source repository has not been supplied, so
> no task may be *applied* yet. Each card is written so that repo access is the **only** missing
> input — when the repo lands, an executor starts at §5 with `P0-1` and needs no re-briefing.

---

## 1. Evidence base — the measured state this plan reacts to

Run `20261008-193000` via `scripts/geo/run-geo.sh`; raw artifacts in `reports/geo/20261008-193000/`.

**E1 — AI crawlers receive a smaller page, and the split is User-Agent-driven.**
`ua-parity.json`: two stable content classes on one TLS profile (Chrome/curl_cffi JA3):

| Class | Visible-text chars | Bytes | User-Agents receiving it |
|---|---|---|---|
| **full** | 30,101 | ~1,445,262 | Chrome (baseline), `Googlebot`, `Google-CloudVertexBot` |
| **reduced** | 11,554 | ~248,585 | `GPTBot`, `GoogleOther`, `Google-Extended` |

`[MEASURED]` The origin does **not** declare `Vary: User-Agent` (observed: `rsc,
next-router-state-tree, next-router-prefetch, next-router-segment-prefetch, Accept-Encoding`), so
the switch is authored where the page cannot advertise it — middleware or edge.
`[MEASURED]` Bytes differ between two *identical* requests, so byte hashes are not a usable
instrument; the content class replaced them (`ua-parity.json → analysis.instrument`).
`[MEASURED]` The plain-`curl` fingerprint control failed to complete, so
**fingerprint-driven is unmeasured** — neither confirmed nor excluded. `[INFERRED]` With
`Googlebot` receiving the full class, a UA rule (not bot-management) is the likelier author.

**E2 — the reduced variant loses rendered content, not just markup.**
`render-parity.json` — same URL rendered in Chromium per UA:

| UA | innerText chars | words | DOM elements | headings | rendered HTML chars |
|---|---|---|---|---|---|
| Chrome | 19,235 | 2,617 | 4,242 | 50 | 1,477,445 |
| Googlebot | 19,235 | 2,617 | 4,242 | 50 | 1,477,445 |
| Google-CloudVertexBot | 19,235 | 2,617 | 4,241 | 50 | 1,477,179 |
| **GPTBot** | **12,097** | **1,653** | **1,318** | **41** | **281,170** |

GPTBot sees 62.9% of the browser's rendered text and 31% of its DOM elements **after hydration** —
so it is not a "less server HTML, same DOM" artefact. Which sections vanish is in
`raw/render/render_gptbotUA.headings.json` vs `render_chromeUA.headings.json`
(`analysis.heading_diff_vs_chromeUA`).

**E2b — the reduced variant is a lexical *subset* with fewer repeats, not a different page.**
`scripts/geo/compare_innertext.py` over the rendered `innerText` dumps:

| Comparison | absent tokens | fewer-instance tokens | unique to the bot side | reading |
|---|---|---|---|---|
| Chrome → Googlebot | 0 | 0 | 0 | identical rendered text |
| Chrome → GPTBot | 246 (mass 323) | 208 (mass 656) | **3** (`operates`, `preferences`, `we'll`) | subset with fewer instances |

`[MEASURED]` So the loss is dominated by **fewer repetitions of list/ticker content** (market
strip, capability lists) rather than missing sections, and nothing is served to bots that a browser
cannot see (3 unique tokens is tokenisation noise from different line wrapping). Only **one**
heading differs between the variants. This makes **(b) "the full variant is inflated by duplicated
list rendering" the leading hypothesis — but it stays a hypothesis** until the template code or edge
config is read: this test cannot distinguish "the section renders fewer items" from "the section is
absent", and that distinction decides whether this is dedupe work or an escalation.

**E3 — Common Crawl absence is now trustworthy.** `cc-baseline.json`: 6 sampled collections out of
127 advertised (`CC-MAIN-2025-30`, `-2025-43`, `-2026-25/-30/-34/-39`), every `bitara.co` negative
from a **definitive 404**; zero captures. One query (`bitara.com` on `CC-MAIN-2026-39`) 504'd and
is recorded `not-measured` — it affects the neighbour claim only, not `bitara.co`.

**E4 — no cache validators, no cacheability.** `ua-parity.json` samples: no `ETag`, no
`Last-Modified`, `cache-control: private, no-cache, no-store, max-age=0, must-revalidate`,
`cf-cache-status: DYNAMIC`.

**E5 — conflation.** `bitara.com` serves `<title>Bitara.com - Ready for Development</title>`;
`bitara.net` is registered by others. The brand's own disambiguation paragraph already exists in
`llms.txt` (22,722 B) and has never been promoted into structured data.

**E6 — the locale surface is internally inconsistent.** `/ja` exists and is in the sitemap (134
URLs) but is absent from `llms.txt`, which claims 10 languages. `hreflang` exists **only** in the
sitemap (17,688 `xhtml:link` entries), **zero** in the HTML `<head>`.

**Not defects — do not "fix":** `ai.txt` 404s correctly; `robots.txt` is permissive to all AI
crawlers and carries `Content-Signal: search=yes, ai-input=yes, ai-train=yes`; content negotiation
is clean (every `Accept` variant returns full 200 HTML); no `noindex` anywhere; `/ar` is correctly
`dir="rtl"`; the March-2026 `307`s do not reproduce.

---

## 2. Gates — run before and after every change


```bash
# GEO harness — the before/after artifacts (this is the proof of movement).
# Self-contained: bootstrap creates the pinned env, run-geo.sh resolves everything else.
bash scripts/geo/bootstrap.sh                  # once → ./.venv (Python 3.12)
GEO_RUN_ID=<runId> bash scripts/geo/run-geo.sh # writes reports/geo/<runId>/

# Optional extra gates — these need a web-quality-kit checkout, and they are NOT part of the
# GEO acceptance criteria; they exist to prove classic SEO/a11y/headers did not regress.
KIT=${KIT:-/path/to/web-quality-kit}
pnpm -C "$KIT" wq test src/specs/seo.spec.ts
pnpm -C "$KIT" wq test src/specs/crawler-files.spec.ts
pnpm -C "$KIT" wq test src/specs/a11y.spec.ts
pnpm -C "$KIT" wq test src/specs/headers.spec.ts
pnpm -C "$KIT" lighthouse https://bitara.co
pnpm -C "$KIT" crawl https://bitara.co --max-pages 60 --depth 3
pnpm -C "$KIT" report            # reports/SUMMARY.md
```

Set `WQ_BASE_URL=https://bitara.co` if the suite default differs. Diff the two runs'
`manifest.json` → `readings` blocks; that diff, not prose, is the deliverable.

---

## 3. Rules the executor inherits (non-negotiable)

1. **No cloaking.** Different *content* per user-agent is eliminated, or explicitly owned and
   documented. Never optimise *around* it, and never add UA branches to feed bots more text —
   that is the same defect with the sign flipped.
2. **Never fabricate** statistics, clients, awards, certifications, `sameAs` URLs or timelines.
   Every number surfaced must trace to a source the site controls.
3. **Do not break SEO, a11y or users to please bots.** Crawlable, semantic, answer-shaped, fast and
   accessible all point the same way; a GEO change that harms any of them is wrong.
4. **Fix causes in templates**, never instances on a page. Hand-added JSON-LD drifts; a shared
   component does not.
5. **Keep `bitara.co`.** `.co` is a generic ccTLD Google treats as a gTLD; conflation is the real
   issue. Never propose a migration.
6. **Every locale is one surface.** A change lands in all locales (11 in the sitemap, `/ja`
   included) or it has created a new inconsistency.
7. **Never remove** `SpeakableSpecification`, the `api-catalog` / `openapi.json` / `api-docs`
   `Link` relations, or an existing `sameAs`, without a stated reason — they were deliberate.
8. **No MCP servers.** Browser MCPs measured 11,669 tokens/request; `wq probe` replaces them at 0.
9. **Do not promise Common Crawl inclusion on a schedule** — slow, indirect, not client-controllable.
10. **A skipped check is a failure, not a pass.** Missing credential → report `blocked: <reason>`
    and exit non-zero. Never let an unrun check read as clean.
11. **Do not leave the security scope.** Touching `wq sec` means reading `security/scope.yml` and
    respecting the gate and `--authorized`.
12. **One task = one branch = one commit = one gate re-run.** No batched "GEO improvements"
    commit; it makes the diff unattributable.

---

## 4. Task index

| ID | Task | Priority | Status | Blocked by |
|---|---|---|---|---|
| **P0-1** | Remove the UA-conditional reduced variant (or own it) | P0 | `blocked: source repo` | repo + client Q2/Q8 |
| **P0-2** | Restore cache validators and cacheability | P0 | `blocked: source repo` | repo |
| **P0-3** | Entity disambiguation against the parked `bitara.com` | P0 | `blocked: source repo` | repo |
| **P0-4** | Full AI-crawler UA matrix (axis A) | P0 | **ready now** | none |
| **P1-1** | `hreflang` into the HTML `<head>`; reconcile `/ja` in `llms.txt` | P1 | `blocked: source repo` | repo |
| **P1-2** | Template-level JSON-LD coverage | P1 | `blocked: source repo` | repo |
| **P1-3** | Answer-first openings + attributable statistics | P1 | `blocked: source repo` | repo |
| **P2-1** | IndexNow on publish; sitemap submission | P2 | `blocked: credentials` | `INDEXNOW_KEY`, GSC/BWT |
| **P2-2** | Off-site entity graph (`sameAs`, Wikidata/Crunchbase, PR) | P2 | `blocked: client decision` | client Q3/Q6 |
| **P2-3** | Citation probes (L4) and index baselines (L1/L2/L3) | P2 | `blocked: credentials` | client keys |

`P0-4` is the only task executable with today's access — and it produces the evidence that `P0-1` is
verified against, so it runs first.

---

### P0-1 — Remove the User-Agent-conditional reduced variant (or explicitly own it)

**Priority** P0 · **Status** `blocked: source repo` · **Owner** site engineering (escalate if
intentional) · **Evidence** E1, E2

**Why first:** `Google-Extended` — the token governing Gemini/Vertex grounding — sits on the reduced
class, and that class loses 37% of rendered text and 69% of DOM elements. It is the most direct
candidate explanation of the client's complaint, and serving materially different content per UA is
cloaking-adjacent. It must be explained, documented and made deterministic.

**Step 1 — triage before touching anything (mandatory).** Classify the cause; the fix depends on it,
and the wrong fix makes the site worse.

```bash
jq '.analysis.heading_diff_vs_chromeUA' reports/geo/<run>/render-parity.json
diff reports/geo/<run>/raw/render/render_chromeUA.headings.json \
     reports/geo/<run>/raw/render/render_gptbotUA.headings.json
# E2b: is the lost text repetition or absence? Run this first — it shapes the fix.
.venv/bin/python scripts/geo/compare_innertext.py \
    reports/geo/<run>/raw/render/render_chromeUA.innerText.txt \
    reports/geo/<run>/raw/render/render_gptbotUA.innerText.txt
```

| Class | How to recognise it | Correct fix |
|---|---|---|
| **(a) progressive enhancement** | missing sections are client-only (`useEffect`, dynamic import) and equally missing with JS off | server-render that content so *every* consumer gets it — it also fixes JS-off users (§3 rule 3) |
| **(b) the full variant is inflated** ⬅ **leading hypothesis per E2b** | E2b shows few-instance mass > absent mass and ≈0 unique bot-side vocabulary (a repeated marquee/carousel/ticker; baseline: "Our Values" 4× vs 2×) | **dedupe the full variant**; never add content to the bot side |
| **(c) genuine UA-conditional content** | real content on the bot side that browsers never see, or whole sections absent with no JS-off explanation | **escalate and own it** — do not optimise around it (§3 rule 1) |

**Step 2 — locate the author.**

```bash
rg -n "GPTBot|Google-Extended|GoogleOther|Google-CloudVertexBot|CCBot|PerplexityBot" \
   -g '!node_modules' -g '!*.lock' .
rg -n "user-agent|userAgent|user_agent" middleware.ts middleware.js next.config.* app lib src 2>/dev/null
rg -n "navigator\.userAgent" -g '!node_modules' .
```

If the repo is clean, the switch is at the edge → that is L7: request Cloudflare zone access and
check rules, Workers, Bot Fight Mode / bot management, and any feature that rewrites HTML.

**Step 3 — change.** For (a)/(b): one template-level change, applied to every locale. For (c): no
code change — a written decision, plus `Vary: User-Agent` if the split is to remain (an
unadvertised variant is a cache-poisoning hazard as well as a cloaking one).

**Acceptance — all four, with numbers:**

```bash
jq '.analysis.reduced_variant_labels' reports/geo/<after>/ua-parity.json      # expect []
jq '.analysis.content_classes'        reports/geo/<after>/ua-parity.json      # expect ONE value
jq '.analysis.relative_to_chromeUA'   reports/geo/<after>/render-parity.json  # every ratio >= 0.98
jq '.results[] | {label, dom_elements}' reports/geo/<after>/render-parity.json # within 2% of Chrome
# the decisive one: no lexical difference left between the Chrome and AI-crawler renders
.venv/bin/python scripts/geo/compare_innertext.py \
    reports/geo/<after>/raw/render/render_chromeUA.innerText.txt \
    reports/geo/<after>/raw/render/render_gptbotUA.innerText.txt   # expect "no lexical loss"
```

**Forbidden:** adding UA branches to *increase* bot content; serving a special page to crawlers;
"fixing" Gemini visibility by double-serving. **Artifacts:** `reports/geo/<after>/ua-parity.json`,
`render-parity.json`, and the diff pasted into the commit message.

---

### P0-2 — Restore cache validators and cacheability

**Priority** P0 · **Status** `blocked: source repo` · **Owner** site engineering ·
**Evidence** E4

**Why:** `[MEASURED]` no `ETag`, no `Last-Modified`, and
`cache-control: private, no-cache, no-store, max-age=0, must-revalidate` with
`cf-cache-status: DYNAMIC`. `[SOURCED]` That exact directive string is what Next.js emits for a
**dynamically rendered** route. Without validators, crawlers cannot revalidate cheaply and recrawl
is throttled; with `no-store`, neither the edge nor a crawler may cache anything.

**Locate — find out *why* `/` is dynamic.**

```bash
rg -n "cookies\(\)|headers\(\)|noStore|unstable_noStore|searchParams|dynamic\s*=|revalidate" \
   app/ middleware.ts 2>/dev/null
rg -n "Cache-Control|cache-control|s-maxage|stale-while-revalidate" -g '!node_modules' .
```

**Change (choose one, state which in the commit):**

1. **Preferred — make public marketing routes cacheable.** In App Router, either
   `export const revalidate = <seconds>` on the route, or remove the `cookies()`/`headers()`/
   `searchParams` access that forces dynamic rendering. Static output gets `ETag` from the host.
2. **Keep it dynamic, but cache it at the edge.** Set explicit headers (e.g. in `next.config.js`
   `headers()` or `middleware.ts`) for **public** routes only:
   `Cache-Control: public, max-age=0, s-maxage=600, stale-while-revalidate=86400`, and let
   Cloudflare generate/serve an `ETag` once the response is cacheable.

**Do not** change `cache-control` for personalised, authenticated or preview routes — that is how
you leak one user's page to another. Restrict the change to the public content templates.

**Acceptance:**

```bash
curl -sS -D - -o /dev/null https://bitara.co/ | grep -iE 'etag|last-modified|cache-control|cf-cache-status'
# expect: ETag and/or Last-Modified present; a max-age/s-maxage value; no blanket no-store
curl -sS -D - -o /dev/null https://bitara.co/ | grep -i cf-cache-status   # expect HIT on the 2nd request
pnpm -C "$KIT" wq test src/specs/headers.spec.ts                          # no regression
```

**Forbidden:** caching anything session-specific; setting a long `max-age` on HTML (use `s-maxage` +
`stale-while-revalidate` so the browser does not serve stale pages to users). **Artifacts:** the
`curl` header dump saved into the run directory, before and after.

---

### P0-3 — Entity disambiguation against the parked `bitara.com`

**Priority** P0 · **Status** `blocked: source repo` · **Owner** site engineering + client ·
**Evidence** E5

**Why:** a `.com`-biased model resolves "Bitara" to a parked page
(`<title>Bitara.com - Ready for Development</title>`), which is worse than no answer because it reads
as an authoritative non-answer. The site already wrote the fix in prose (`llms.txt` disambiguation
paragraph, 22,722 B) and never promoted it into structured data or a visible statement.

**Locate:**

```bash
rg -n "sameAs|disambiguatingDescription|@id|Organization" -g '!node_modules' app lib src components 2>/dev/null
rg -n "Bitara Capital" app/ --glob '*about*' 2>/dev/null   # find the org copy template
sed -n '1,60p' https://bitara.co/llms.txt     # source text for disambiguatingDescription
```

**Change (template level, all locales):**

1. One stable node id — `"@id": "https://bitara.co/#organization"` — and every other node
   (`WebSite`, `WebPage`, `Person`, `Service`, articles) references it by `@id` instead of restating
   the organisation.
2. On that node: `disambiguatingDescription` (lift the `llms.txt` paragraph verbatim),
   `legalName: "Bitara Capital Sdn. Bhd."`, `identifier` (registration `202201037451`),
   `foundingDate`, `founder`, `address`, and a `sameAs` array covering every **verified** property
   (LinkedIn, Crunchbase, GitHub, X, Wikidata,…). If a profile does not exist, do not invent it —
   list the gap as an action item instead.
3. A visible, crawlable sentence in the first viewport of `/` and `/about`: *"Bitara Capital Sdn.
   Bhd. is bitara.co"* plus the non-affiliation statement (not `bitara.com`, not `bitara.net`, not
   affiliated with any Bitara token or mining app). Text, not an image; present without JS.

**Acceptance:**

```bash
# structured data parses and carries the required keys, on every locale of / and /about
python3 - <<'PY'
import json,urllib.request,re
for path in ["/", "/about", "/ja/about", "/ar/about"]:
    html = urllib.request.urlopen("https://bitara.co"+path).read().decode()
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    nodes = [json.loads(b) for b in blocks]
    flat = json.dumps(nodes)
    assert "disambiguatingDescription" in flat, f"{path}: no disambiguatingDescription"
    assert "sameAs" in flat, f"{path}: no sameAs"
    assert "202201037451" in flat, f"{path}: no registration identifier"
    print(path, "ok", len(blocks), "blocks")
PY
pnpm -C "$KIT" wq test src/specs/seo.spec.ts    # JSON-LD check stays green
```

**Blocked sub-check:** the decisive test — Group C prompts ("Which company owns the domain
bitara.co?", "Is there a Bitara token?") returning bitara.co — needs `GOOGLE_API_KEY` (T4). Until
then this task closes on the assertion above, and the probe is recorded `blocked: no
GOOGLE_API_KEY`, owned by the client. **Forbidden:** inventing `sameAs` URLs; claiming affiliation
with the parked domains; adding disambiguation *only* to `/`. **Artifacts:** the JSON-LD dumps per
locale.

---

### P0-4 — Full AI-crawler UA matrix (axis A) — *runnable today, no repo needed*

**Priority** P0 · **Status** **ready now** · **Owner** engagement lead ·
**Evidence** E1, E2

**Why:** the split is currently known from three bot UAs. Before `P0-1` is closed, the membership of
the reduced class must be complete — otherwise a fix can pass the test and still leave `CCBot` or
`PerplexityBot` on a reduced page, and the acceptance criterion for `P0-1` is unsound.

**Change (in this workspace, not the site repo):**

1. Add `--ua-set <file.json>` to `scripts/geo/ua_parity.py`: read a list of
   `{"label": …, "user_agent": …}`, run **one** repeat each on the Chrome TLS profile, classify each
   against the Chrome baseline content class (full / reduced), and write `ua-matrix.json`:
   `{label, user_agent, http_status, bytes, visible_text_chars, content_class, reduced, cache_control, vary}`.
2. Create `scripts/geo/ua-sets/axis-a.json` with the axis-A list: `GPTBot`, `OAI-SearchBot`,
   `ChatGPT-User`, `PerplexityBot`, `Perplexity-User`, `ClaudeBot`, `Claude-User`, `anthropic-ai`,
   `Googlebot`, `Google-Extended`, `GoogleOther`, `Google-CloudVertexBot`, `Applebot`,
   `Applebot-Extended`, `Bingbot`, `CCBot`, `Amazonbot`, `Bytespider`, `Meta-ExternalAgent`,
   `DuckAssistBot`, `MistralAI-User`.
3. Cross-check `robots.txt` and `Content-Signal` against the matrix: any UA that `robots.txt` allows
   but that receives a reduced page is a `P0-1` escalation, and any UA that is disallowed while
   `Content-Signal` says `ai-train=yes` is an intent contradiction to be resolved by the client.

**Acceptance:** `reports/geo/<run>/ua-matrix.json` has one row per UA with `http_status: 200`
(or a recorded reason), and the reduced-class membership is an explicit list — not "the ones we
happened to test". **Forbidden:** adding UAs to the matrix to make the result look better; treating a
non-200 as "not reduced" (it is `not-measured`).

---

### P1-1 — `hreflang` into the HTML `<head>`; reconcile `/ja` in `llms.txt`

**Priority** P1 · **Status** `blocked: source repo` · **Owner** site engineering · **Evidence** E6

**Why:** `[MEASURED]` `hreflang` exists only in the sitemap (17,688 `xhtml:link` entries) and is
**absent from the HTML `<head>`** of every page. Non-Google consumers — including AI fetchers — read
HTML, not sitemaps. Separately, `/ja` returns 200 and is in the sitemap (134 URLs) but is missing
from `llms.txt`, which claims 10 languages: the site contradicts itself about which locales exist.

**Locate:**

```bash
rg -n "hreflang|alternates|languages|x-default" -g '!node_modules' app lib 2>/dev/null
rg -n "locales|i18n|ja\b" i18n.* next.config.* middleware.ts 2>/dev/null
curl -sS https://bitara.co/llms.txt | rg -n "languages|Japanese|ja\b" | head
```

**Change:**

1. Per-route `generateMetadata` emitting `alternates.canonical` (self-referencing per locale) and
   `alternates.languages` for **all** locales plus `x-default`, from the same source of truth the
   sitemap uses — so the two can never drift.
2. `llms.txt`: add Japanese to the language list and to the relevant link sections, so the file
   matches the sitemap's locale set.
3. `sitemap-index.xml` returns 404 — either add the index (needed once per-locale/per-type sitemaps
   multiply) or remove it from any documentation that implies it exists. Do not leave the ambiguity.

**Acceptance:**

```bash
# distinct hreflang values in the HTML head == locale set in the sitemap (+x-default)
for p in / /ja/about /ar/about /zh/about; do
  echo "$p: $(curl -sS https://bitara.co$p | grep -o 'hreflang="[^"]*"' | sort -u | wc -l)"
done
curl -sS https://bitara.co/sitemap.xml | grep -o 'hreflang="[^"]*"' | sort -u | wc -l   # same number
curl -sS https://bitara.co/llms.txt | grep -c 'ja'                                       # Japanese present
pnpm -C "$KIT" wq test src/specs/seo.spec.ts        # hreflang + canonical assertions stay green
```

**Forbidden:** emitting `hreflang` from a hand-maintained list inside a component (it will drift from
the sitemap — the whole point is one source of truth); pointing `x-default` at a locale that does not
exist. **Artifacts:** the four head dumps plus the sitemap counts.

---

### P1-2 — Template-level JSON-LD coverage

**Priority** P1 · **Status** `blocked: source repo` · **Owner** site engineering ·
**Evidence** E1/E5 baseline: homepage org graph is strong but lacks `BreadcrumbList`, `FAQPage`,
`Service`/`Offer`, `ItemList`; `/about` already shows the richer pattern.

**Why:** the correct pattern exists on `/about` and is simply not applied consistently. Answer engines
lift structured facts; a `Service` node with an `Offer` is what makes a service page quotable.

**Change — one shared component, no per-page blocks:**

| Template | Required nodes |
|---|---|
| every page | `BreadcrumbList`; `inLanguage` matching the page locale |
| service pages | `Service` (+ `Offer` where priced), linked to the org `@id` |
| insights | `Article`/`BlogPosting` with `author`, `datePublished`, `dateModified` |
| case studies | `CreativeWork`/`Article` with `about` referencing the org |
| pages with real Q&A | `FAQPage` — **only** where the questions genuinely exist on the page |
| homepage | `ItemList` where a real list is rendered |

Implement as `<JsonLd data={…} />`, driven by each route's data — not hand-written script tags.

**Acceptance:**

```bash
pnpm -C "$KIT" wq crawl https://bitara.co --max-pages 60 --depth 3
# assert, per URL pattern, that the required @type set is present and that every block parses
pnpm -C "$KIT" wq test src/specs/seo.spec.ts     # JSON-LD assertions stay green
```

**Forbidden:** emitting an empty `sameAs`/`author` that parses but says nothing (a block that parses
but is semantically empty is **not** fixed); adding `FAQPage` markup for questions not visible on the
page — that is a policy violation, not an optimisation.

---

### P1-3 — Answer-first openings and attributable statistics

**Priority** P1 · **Status** `blocked: source repo` · **Owner** site engineering + client (facts) ·
**Evidence** baseline: quotable claims already on the homepage — "99.9% Uptime", "2.3 sec Block
Time", "Enterprise Security", "Carbon Neutral", HQ Kuala Lumpur, founded October 2022, founder
Dr Jovian Tan, registration 202201037451.

**Change:**

1. Each priority template opens with a 40–60-word standalone answer (definition in sentence one) —
   the `/insights/*` set already does this; promote that pattern into a reusable component rather
   than leaving it ad-hoc.
2. Every statistic carries its **source and date in the same section**, so a model can cite it
   without hedging. Unattributable numbers get removed or attributed — never left floating.
3. Headings phrased as the question a buyer asks; each section self-contained enough to be lifted out
   of context.
4. Entity statement in the first viewport of `/` and `/about` (shared with `P0-3`).

**Acceptance:** a `content-audit` check over the priority templates asserting (a) a definitional
sentence within the first 60 words, (b) every numeric claim in the body has an adjacent source+date.
Record the per-template result as a table in the run artifacts; a manual sign-off is acceptable only
if it is written down per template.

**Forbidden:** inventing a metric, a client, a certification or a date; padding word count to "look
bigger" to an LLM (thin pages dilute the entity graph); moving facts into images.

---

### P2-1 — IndexNow on publish; sitemap submission

**Priority** P2 · **Status** `blocked: credentials` · **Owner** client (free key) + site engineering
· **Evidence** E4

Wire an IndexNow ping (`BING`, `Yandex`, `Seznam`, `Naver` — **not Google**) into the publish step,
and submit/refresh sitemaps in GSC and Bing Webmaster Tools. IndexNow mitigates the recrawl throttle
caused by the missing validators, but it is a *signal*, not an index guarantee. Keys are env-only
(`INDEXNOW_KEY`); absent key → `blocked: no INDEXNOW_KEY`, never a silent skip.

### P2-2 — Off-site entity graph

**Priority** P2 · **Status** `blocked: client decision` · **Owner** client · **Evidence** E5

Inventory and complete `sameAs` targets (LinkedIn, Crunchbase, GitHub, X, Wikidata), then seek
third-party corroboration of the same facts (legal name, registration, HQ, founder) — a
`.com`-biased model is corrected by corroboration, not by on-page edits alone. Verify no `sameAs`
points at an unrelated Bitara token/mining app. **Owner must be named**: this is the one task that
cannot be closed by engineering alone.

### P2-3 — Citation probes and index baselines

**Priority** P2 · **Status** `blocked: credentials` · **Owner** client · **Evidence** L1–L4

Run the `geo-citation-probe` skill (installed this session) against the 15-prompt set, three runs per
prompt per engine, and establish dated index baselines via GSC URL Inspection / Bing URL Info. Until
`GOOGLE_API_KEY` (Gemini first, per the rollout order) and the GSC/BWT credentials exist, every one
of these is reported `blocked: <reason>` and the run exits non-zero — a probed-but-challenged engine
is `not measured`, never "zero results".

---

## 5. Executor protocol (for the coding agent)

This is the loop. It is deliberately mechanical so that two runs of the same task produce the same
diff.

**5.1 Preconditions — check each, and stop if one fails.**

```bash
test -d .git                     || echo "blocked: no repository"
rg --version >/dev/null          || echo "blocked: no ripgrep"
git status --porcelain | head    # clean tree, or explain the dirty files before starting
test -d "$KIT"                   || echo "blocked: kit not found at $KIT"
```

**5.2 Select the task.** Highest priority first, in this order: `P0-4` → `P0-1` → `P0-2` → `P0-3` →
`P1-1` → `P1-2` → `P1-3` → `P2-*`. Within a task, take the `Step 1` triage before any edit. If a task
is `blocked`, **skip it and record the block** — do not substitute a smaller edit that looks like the
fix.

**5.3 Before editing.** `git checkout -b geo/<task-id>-<slug>`; run §2 gates and save the artifacts
under `reports/geo/<before-run-id>/`. If the gate suite is already red before your change, record the
pre-existing failures and stop — you cannot attribute a delta from a broken baseline.

**5.4 Edit.** Template level, all locales (§3 rules 4, 6). One task per branch (§3 rule 12).

**5.5 Acceptance.** Run the card's acceptance block. Every assertion must be shown with its measured
value. A command that could not run is written as `blocked: <reason>`, never omitted, and the task
stays open (§3 rule 10).

**5.6 After editing.** Re-run §2 gates into `reports/geo/<after-run-id>/` and diff
`manifest.json.readings`. Then update the state file:

```bash
# docs/geo-fix-plan.json — set the task's status, and always fill these three fields
#   status:     done | blocked | in-progress
#   evidence:   paths to the before/after artifacts
#   blocked_by: reason + owner  (when status = blocked)
jq '.tasks[] | select(.id=="P0-1")' docs/geo-fix-plan.json
```

**5.7 Stop and escalate** (do not work around): class **(c)** UA-conditional content is confirmed;
the only way to pass an acceptance check would be to serve bots something users do not get; a gate
regresses and fixing it would require relaxing a budget; a `sameAs` target cannot be verified.

**5.8 Commit** with the template: `geo(P0-1): <what changed>` + the before/after numbers + the
artifact paths. Never squash multiple task ids into one commit.

**5.9 Two runs, one diff.** Nothing is reported as improved unless
`reports/geo/<before>/manifest.json` and `reports/geo/<after>/manifest.json` are both on disk and the
changed readings are quoted with their numbers.

---

## 6. Definition of done

- [ ] `P0-4` matrix exists: complete AI-crawler membership of the reduced class.
- [ ] `P0-1` closed: no reduced class, rendered parity ≥ 0.98, DOM within 2% — or escalated with a
      named owner and a written decision.
- [ ] `P0-2` closed: `ETag`/`Last-Modified` present, `max-age`/`s-maxage` sane, no blanket `no-store`
      on public routes.
- [ ] `P0-3` closed: `disambiguatingDescription` + non-empty `sameAs` + legal identifier on every
      locale of `/` and `/about`, plus the visible statement.
- [ ] `P1-*` closed with numbers (hreflang count == sitemap locale set; `/ja` in `llms.txt`; JSON-LD
      coverage per template; answer-first openings recorded per template).
- [ ] All §2 gates green; no budget relaxed silently.
- [ ] Every blocked item carries a reason **and** an owner; nothing is silently dropped.
- [ ] `reports/GEO-REPORT.md` written: summary, baseline→after table, axis scorecard A–J, tooling +
      token cost, accepted risks with owners, and the exact re-run commands.
- [ ] One-paragraph plain-English status the client can forward.

**The single most important number to watch:** the reduced-class membership list from `P0-4`, and
whether it is empty after `P0-1`. Everything else in this plan is secondary to that list, because it
is the difference between Gemini knowing what `bitara.co` says and Gemini quoting a smaller page — or
a parked `.com`.
