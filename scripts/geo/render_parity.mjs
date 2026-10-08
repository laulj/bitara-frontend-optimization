#!/usr/bin/env node
/**
 * Step 3d cross-check — does the reduced per-UA variant lose *content*, or only *HTML*?
 *
 * `ua_parity.py` measures the wire bytes. A Next.js App Router page ships a large
 * RSC flight payload plus streamed markup, so "Googlebot got 1.4 MB and GPTBot got
 * 248 kB" does **not** by itself prove an AI crawler sees less content — it may only
 * prove it sees less *pre-rendered* HTML for the same DOM. Claiming the former from a
 * byte count would be exactly the over-reading HANDOFF-PROMPT.md warns against.
 *
 * So: render the same URL in a real browser under each UA and compare the *rendered
 * DOM + innerText*. Chromium's TLS is Chromium's, so this is the "browser TLS" row of
 * the 2x2 — a rendered counterpart to variants A/B/E of ua_parity.py.
 *
 * Playwright is imported from the kit's own dependency tree (no new install).
 * Usage: node scripts/geo/render_parity.mjs --out reports/geo/<runId> [--url ...]
 */
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Portable by design: nothing here depends on where this repo was cloned.
const REPO_ROOT =
  process.env.REPO_ROOT ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const KIT = process.env.KIT ?? ''; // optional external web-quality-kit checkout

const argv = process.argv.slice(2);
const value = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : fallback;
};

const url = value('url', 'https://bitara.co/');
const outDir = value('out');
if (!outDir) {
  console.error('[render] error: --out <dir> is required');
  process.exit(2);
}

const CHROME_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
const GOOGLEBOT_UA =
  'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36';
const GPTBOT_UA =
  'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot';
const VERTEXBOT_UA =
  'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Google-CloudVertexBot/1.0; +http://www.google.com/bot.html) Chrome/141.0.0.0 Safari/537.36';

const UAS = [
  ['render_chromeUA', CHROME_UA],
  ['render_googlebotUA', GOOGLEBOT_UA],
  ['render_gptbotUA', GPTBOT_UA],
  ['render_cloudvertexbotUA', VERTEXBOT_UA],
];

/**
 * Resolve Playwright from wherever it exists on this machine, in order of preference:
 *   1. PLAYWRIGHT_ENTRY  — explicit path to playwright/index.mjs
 *   2. PLAYWRIGHT_DIR    — directory containing index.mjs
 *   3. this repo's own node_modules (npm i -D playwright)
 *   4. an external web-quality-kit checkout, if KIT is set (pnpm store or node_modules)
 * Failing all four it throws with the list of attempts, and the caller records `blocked`
 * rather than silently reporting "no difference".
 */
function playwrightCandidates() {
  const candidates = [];
  if (process.env.PLAYWRIGHT_ENTRY) {
    candidates.push({ entry: process.env.PLAYWRIGHT_ENTRY, how: 'PLAYWRIGHT_ENTRY' });
  }
  if (process.env.PLAYWRIGHT_DIR) {
    candidates.push({ entry: path.join(process.env.PLAYWRIGHT_DIR, 'index.mjs'), how: 'PLAYWRIGHT_DIR' });
  }
  try {
    const require = createRequire(path.join(REPO_ROOT, 'package.json'));
    candidates.push({ entry: require.resolve('playwright'), how: 'repo node_modules' });
  } catch {
    candidates.push({ entry: null, how: 'repo node_modules (not installed)' });
  }
  if (KIT) {
    const store = path.join(KIT, 'node_modules', '.pnpm');
    if (fs.existsSync(store)) {
      for (const dir of fs.readdirSync(store).filter((n) => /^playwright@\d/.test(n)).sort().reverse()) {
        candidates.push({
          entry: path.join(store, dir, 'node_modules', 'playwright', 'index.mjs'),
          how: `KIT pnpm store (${dir})`,
        });
      }
    }
    candidates.push({ entry: path.join(KIT, 'node_modules', 'playwright', 'index.mjs'), how: 'KIT node_modules' });
  }
  return candidates;
}

async function loadPlaywright() {
  const tried = [];
  for (const candidate of playwrightCandidates()) {
    if (!candidate.entry || !fs.existsSync(candidate.entry)) {
      tried.push(`${candidate.how}: not found`);
      continue;
    }
    try {
      const mod = await import(pathToFileURL(candidate.entry).href);
      if (mod?.chromium) return { mod, resolvedFrom: `${candidate.how} → ${candidate.entry}` };
      tried.push(`${candidate.how}: module has no chromium export`);
    } catch (error) {
      tried.push(`${candidate.how}: ${String(error).slice(0, 140)}`);
    }
  }
  const failure = new Error('playwright unavailable');
  failure.tried = tried;
  throw failure;
}

let playwrightModule;
let resolvedFrom;
try {
  ({ mod: playwrightModule, resolvedFrom } = await loadPlaywright());
} catch (error) {
  // Report blocked, never "no difference": an unrun render must not read as a clean pass.
  const blocked = {
    tool: 'scripts/geo/render_parity.mjs (Step 3d cross-check)',
    measured_at: new Date().toISOString(),
    url,
    status: 'blocked',
    blocked_reason:
      'playwright unavailable — install it (npm i -D playwright@1.63.0 && npx playwright install chromium) ' +
      'or point PLAYWRIGHT_DIR / PLAYWRIGHT_ENTRY at an existing copy',
    tried: error.tried ?? [String(error)],
    results: [],
    analysis: {
      reading: 'NOT MEASURED — playwright unavailable, so the "less content" question stays open.',
    },
  };
  fs.mkdirSync(path.join(outDir, 'raw', 'render'), { recursive: true });
  fs.writeFileSync(path.join(outDir, 'render-parity.json'), JSON.stringify(blocked, null, 2));
  console.error(`[render] blocked: ${blocked.blocked_reason}`);
  for (const line of blocked.tried) console.error(`[render]   tried ${line}`);
  process.exit(127);
}
const { chromium } = playwrightModule;

const browser = await chromium.launch();
const results = [];
for (const [label, userAgent] of UAS) {
  const context = await browser.newContext({ userAgent, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const entry = { label, user_agent: userAgent };
  try {
    const response = await page.goto(url, { waitUntil: 'load', timeout: 60000 });
    entry.http_status = response?.status() ?? null;
    entry.redirected_to = page.url();
    await page.waitForTimeout(3000); // let hydration settle before reading the DOM
    Object.assign(
      entry,
      await page.evaluate(() => ({
        rendered_html_chars: document.documentElement.outerHTML.length,
        inner_text_chars: (document.body?.innerText ?? '').replace(/\s+/g, ' ').trim().length,
        inner_text_words: (document.body?.innerText ?? '').trim().split(/\s+/).filter(Boolean).length,
        inner_text_full: document.body?.innerText ?? '',
        dom_elements: document.querySelectorAll('*').length,
        headings: [...document.querySelectorAll('h1,h2,h3,h4')]
          .map((el) => el.textContent.trim()).filter(Boolean).length,
        headings_list: [...document.querySelectorAll('h1,h2,h3,h4')]
          .map((el) => `${el.tagName.toLowerCase()}: ${el.textContent.trim()}`).filter(Boolean),
        anchors: document.querySelectorAll('a[href]').length,
        images: document.querySelectorAll('img').length,
        json_ld_blocks: document.querySelectorAll('script[type="application/ld+json"]').length,
        lang: document.documentElement.lang || null,
        title: document.title || null,
        visible_text_head: (document.body?.innerText ?? '').replace(/\s+/g, ' ').trim().slice(0, 300),
      })),
    );
    // Raw per-UA DOM evidence: which sections survive the reduced variant is exactly what
    // the fix needs to know, and a diff cannot be recomputed from aggregate counts.
    const rawDir = path.join(outDir, 'raw', 'render');
    fs.mkdirSync(rawDir, { recursive: true });
    fs.writeFileSync(path.join(rawDir, `${label}.innerText.txt`), entry.inner_text_full ?? '');
    fs.writeFileSync(
      path.join(rawDir, `${label}.headings.json`),
      JSON.stringify(entry.headings_list ?? [], null, 2),
    );
  } catch (error) {
    entry.error = String(error).slice(0, 500);
  }
  await context.close();
  results.push(entry);
  console.log(
    `[render] ${label}: status=${entry.http_status ?? 'n/a'} innerText=${entry.inner_text_chars ?? 'n/a'}`,
  );
}
await browser.close();

const base = results.find((r) => r.label === 'render_chromeUA');
const analysis = {
  playwright_entry: resolvedFrom,
  url,
  relative_to_chromeUA: results
    .filter((r) => r.label !== 'render_chromeUA' && typeof r.inner_text_chars === 'number')
    .map((r) => ({
      label: r.label,
      inner_text_ratio: base?.inner_text_chars
        ? +(r.inner_text_chars / base.inner_text_chars).toFixed(3)
        : null,
      rendered_html_ratio: base?.rendered_html_chars
        ? +(r.rendered_html_chars / base.rendered_html_chars).toFixed(3)
        : null,
    })),
};
const ratios = analysis.relative_to_chromeUA.map((r) => r.inner_text_ratio).filter((n) => n !== null);
analysis.heading_diff_vs_chromeUA = results
  .filter((r) => r.label !== 'render_chromeUA' && Array.isArray(r.headings_list))
  .map((r) => ({
    label: r.label,
    missing_headings: (base?.headings_list ?? []).filter((h) => !r.headings_list.includes(h)),
    extra_headings: r.headings_list.filter((h) => !(base?.headings_list ?? []).includes(h)),
  }));
analysis.reading = !ratios.length
  ? 'NOT MEASURED — a render failed; the "less content" question stays open.'
  : ratios.every((n) => n > 0.95)
    ? 'RENDERED CONTENT IS EQUIVALENT across the UA split: the wire-byte gap is a streaming/markup-size artefact, NOT an AI-crawler content disadvantage. Do not describe it as "AI crawlers get 62% less content".'
    : 'RENDERED CONTENT DIFFERS by UA: the split removes content a browser would see, which is the serious reading.';

const payload = {
  tool: 'scripts/geo/render_parity.mjs (Step 3d cross-check)',
  measured_at: new Date().toISOString(),
  url,
  results,
  analysis,
};
fs.mkdirSync(path.join(outDir, 'raw', 'render'), { recursive: true });
fs.writeFileSync(path.join(outDir, 'render-parity.json'), JSON.stringify(payload, null, 2));
console.log(`[render] ${analysis.reading}`);
console.log(`[render] wrote ${path.join(outDir, 'render-parity.json')}`);
