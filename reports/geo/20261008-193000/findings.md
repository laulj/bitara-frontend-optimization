# Findings — GEO measurement run `20261008-193000`

All `[MEASURED]` on 2026-10-08 against the live site. Artifacts in this directory; reproduce with
`bash scripts/geo/bootstrap.sh && GEO_RUN_ID=<new> bash scripts/geo/run-geo.sh`.

> Absolute machine paths inside the captured artifacts (logs, `manifest.json`, probe output) were
> rewritten to `<repo>` / `$KIT` placeholders when this repository was published. No measured value
> was altered; only location strings.

## Run status

| Step | Exit | Artifact |
|---|---|---|
| `preflight_py_compile` | 0 | `logs/preflight.log` |
| `T5_common_crawl_baseline` | 0 | `cc-baseline.json`, `raw/cc/` |
| `T6_ua_parity` | 0 | `ua-parity.json`, `raw/http/` |
| `step3d_render_parity` | 0 | `render-parity.json`, `raw/render/` |
| `wq_probe` | 0 | `probe-browser/` |

L5 and L6 are both closed by this run.

## F1 — Common Crawl: zero captures, all negatives definitive

`cc-baseline.json`: `CONFIRMED for bitara.co: 6 of 6 sampled collection(s) returned a definitive 404
and none was unmeasurable`. Collections: `CC-MAIN-2026-39/-34/-30/-25`, `CC-MAIN-2025-30/-43`, out of
**127 advertised**. Every negative came from Common Crawl's own `No Captures found` body, not from a
timeout — so the finding no longer rests on an unverified assumption (the prior pass 504'd).

Caveat to keep attached: absence is proven for the **sampled** collections only, and Common Crawl
inclusion is slow, indirect and not client-controllable. Do not put it on a delivery timeline.

Conflation neighbours in the same collections: `bitara.net` and `bitara.io` → no captures;
`bitara.com` → no captures on `CC-MAIN-2026-34`. So the parked `.com` risk is **not** mediated by
Common Crawl — it is a model-prior problem, which is why the entity work (P0-3) matters.

## F2 — The per-UA split is header-driven, and the fingerprint control now rules TLS out

`ua-parity.json`. Two stable content classes on one Chrome TLS profile:

| Class | visible-text chars | bytes | User-Agents |
|---|---|---|---|
| full | 30,101 | ~1,445,262 | Chrome, `Googlebot`, `Google-CloudVertexBot`, + plain-`curl` with a Googlebot UA |
| reduced | 11,554 | ~248,585 | `GPTBot`, `GoogleOther`, `Google-Extended` |

- `header_driven: true`; `fingerprint_driven: false` **and measured** — the plain-`curl` control ran
  successfully this time, and plain curl with a **Googlebot** UA received the *full* class. The split
  is therefore not "any non-browser client" and not a TLS/JA3 rule; it is specific User-Agents.
- `origin_declares_vary_user_agent: false` — the origin's `Vary` is `rsc, next-router-state-tree,
  next-router-prefetch, next-router-segment-prefetch, Accept-Encoding`. The switch is therefore
  authored where the page cannot advertise it (middleware or the edge).
- `identical_requests_differ_in_bytes: true` — two identical requests hash differently, so **byte
  hashes are not a valid instrument here** and were replaced by the content class. This is why the
  earlier draft's `identical_sha256` test was wrong.

## F3 — The reduced variant is a lexical subset with fewer repeats

`render-parity.json` + `scripts/geo/compare_innertext.py`:

| UA | innerText chars | DOM elements | vs Chrome |
|---|---|---|---|
| Googlebot | 19,235 | 4,242 | identical (0 lexical difference) |
| Google-CloudVertexBot | 19,235 | 4,241 | ~identical |
| GPTBot | 12,097 | 1,318 | **1 heading differs**, 246 tokens absent (mass 323), 208 fewer-instance tokens (mass 656), 3 tokens unique to the bot side |

Reading: the loss is dominated by **fewer repetitions of list-type content**, not by missing sections,
and nothing is served to bots that a browser cannot see. Class **(b)** — the full variant is inflated
by duplicated/ticker rendering — is the leading hypothesis, but it is **not proven**: this test cannot
separate "the section renders fewer items" from "the section is absent". That decision needs the
template code (or the edge config), which is why `P0-1` remains blocked.

## F4 — Not defects (do not "fix")

`ai.txt` 404s correctly; `robots.txt` is permissive to all AI crawlers with
`Content-Signal: search=yes, ai-input=yes, ai-train=yes`; content negotiation is clean; no `noindex`;
`/ar` is correctly `dir="rtl"`; `sitemap.xml` 200 with 1,474 URLs and 17,688 hreflang entries;
`llms.txt` well-formed at 22,722 B.

## Still not measured (blocked, with owner)

L1 Google index (GSC access, client) · L2 Bing index (BWT key, client) · L3 `site:` counts (CSE key,
client) · L4 citation probing (API keys, client) · L7 the cause of the per-UA split at the edge
(Cloudflare zone, client). L5 and L6 are **closed**.
