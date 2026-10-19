// Production smoke test of the DDI-Net 3.0 website in a real browser (Playwright, Chromium).
//
//   SITE_URL=https://ddi-net.vercel.app EXPECTED_API=https://ddinet-api.onrender.com \
//   OUT_DIR=site-smoke node scripts/release/site_smoke.cjs
//
// Run by .github/workflows/site-smoke.yml on a GitHub-hosted runner. It only
// reads the site (page loads, clicks, downloads); it changes nothing. Each of
// the 20 release checks prints PASS or FAIL; the exit code is 1 if any failed.
// Screenshots, PDFs and the JSON export are written to OUT_DIR (uploaded as a
// workflow artifact). Response bodies are not printed.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const SITE = (process.env.SITE_URL || 'https://ddi-net.vercel.app').replace(/\/$/, '');
const API = (process.env.EXPECTED_API || 'https://ddinet-api.onrender.com').replace(/\/$/, '');
const OUT = process.env.OUT_DIR || 'site-smoke';
fs.mkdirSync(OUT, { recursive: true });

const results = [];
const check = (n, ok, name, detail = '') => {
  results.push({ n, ok: !!ok, name, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${String(n).padStart(2)}. ${name}${detail ? '  — ' + detail : ''}`);
};
const norm = (s) => (s || '').replace(/\s+/g, ' ');
const pdfText = (p) => { try { return norm(execFileSync('pdftotext', ['-layout', p, '-']).toString()); } catch { return ''; } };
const NO_SPECIFIC = { en: 'No specific clinical outcome established from available evidence.', ru: 'По доступным данным конкретное клиническое последствие не установлено.' };
const TITLE_A = { en: 'Is there a documented interaction?', ru: 'Есть ли задокументированное взаимодействие?' };
const SAFE_CLAIM = (text) => text.split(/(?<=[.!?])\s*/).some((s) => /\bsafe\b|безопасн/i.test(s) && !/\b(not|cannot|never|no)\b|не |нельзя|нет /i.test(s));

(async () => {
  const browser = await chromium.launch();
  const errors = [];          // page errors and console errors, all pages
  const apiCalls = [];        // { host, path, status }
  const apiBodies = [];       // raw API response text (checked, never printed)
  const reports = {};         // pair -> parsed /api/v3/report JSON

  const newPage = async (lang, viewport = { width: 1360, height: 900 }) => {
    const ctx = await browser.newContext({ viewport, acceptDownloads: true, timezoneId: 'UTC' });
    await ctx.addInitScript((l) => { try { localStorage.setItem('ddinet.lang', l); localStorage.removeItem('ddinet.mode'); } catch {} }, lang);
    const p = await ctx.newPage();
    p.on('pageerror', (e) => errors.push(`pageerror: ${String(e).slice(0, 200)}`));
    p.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text().slice(0, 200)}`); });
    p.on('response', async (r) => {
      const u = new URL(r.url());
      if (u.pathname.startsWith('/api/')) {
        apiCalls.push({ host: `${u.protocol}//${u.host}`, path: u.pathname, status: r.status() });
        try {
          const t = await r.text();
          apiBodies.push(t);
          if (u.pathname === '/api/v3/report' && r.status() === 200) {
            const j = JSON.parse(t);
            reports[`${j.drug_a?.id}+${j.drug_b?.id}`] = j;
          }
        } catch {}
      }
    });
    return { ctx, p };
  };
  const exportReady = (p, lang) => p.waitForFunction((l) => [...document.querySelectorAll('button')]
    .some((b) => b.textContent.includes(l) && !b.disabled), lang === 'ru' ? 'Экспорт PDF' : 'Export PDF', { timeout: 150000 });
  const download = async (p, name, file) => {
    const [d] = await Promise.all([p.waitForEvent('download', { timeout: 180000 }), p.getByRole('button', { name }).first().click()]);
    const dest = path.join(OUT, file || d.suggestedFilename());
    await d.saveAs(dest);
    return dest;
  };

  // 1. Homepage
  try {
    const { ctx, p } = await newPage('en');
    const r = await p.goto(`${SITE}/`, { waitUntil: 'networkidle', timeout: 90000 });
    const t = norm(await p.textContent('body'));
    await p.screenshot({ path: `${OUT}/01_home.png` });
    check(1, r && r.status() === 200 && /DDI-Net/i.test(t), 'Homepage loads', `HTTP ${r && r.status()}, DDI-Net 3.0 header=${/DDI-NET|DDI-Net/.test(t)}`);
    await ctx.close();
  } catch (e) { check(1, false, 'Homepage loads', String(e).slice(0, 160)); }

  // 2. Drug search (type a name, pick the option, the pair loads)
  try {
    const { ctx, p } = await newPage('en');
    await p.goto(`${SITE}/#/analyzer`, { waitUntil: 'domcontentloaded' });
    const input = p.locator('input[aria-label*="—"]').nth(1);
    await input.waitFor({ timeout: 60000 });
    await p.waitForFunction(() => [...document.querySelectorAll('input')].some((i) => !/load/i.test(i.placeholder)), null, { timeout: 60000 });
    await input.fill('fluconazole');
    const opt = p.getByRole('option', { name: /fluconazole/i }).first();
    await opt.waitFor({ timeout: 20000 });
    await opt.click();
    await p.waitForTimeout(500);
    const hash = await p.evaluate(() => location.hash);
    check(2, /DB00196/.test(hash), 'Drug search works (type "fluconazole", pick it)', `url=${hash}`);
    await ctx.close();
  } catch (e) { check(2, false, 'Drug search works', String(e).slice(0, 160)); }

  // 3–12, 14, 16–18: the three pairs (EN), with the full feature set on warfarin + fluconazole
  const pairs = [['DB00682', 'DB00196', 'warfarin_fluconazole', 3, 'Warfarin + fluconazole analysis'],
                 ['DB00682', 'DB00945', 'warfarin_aspirin', 4, 'Warfarin + aspirin analysis'],
                 ['DB00641', 'DB01211', 'simvastatin_clarithromycin', 5, 'Simvastatin + clarithromycin analysis']];
  let wfPage = null, wfCtx = null, outcomeOk = true, outcomeDetail = [], mechOk = true, safeOk = true, bioOk = true;
  for (const [a, b, tag, n, name] of pairs) {
    try {
      const { ctx, p } = await newPage('en');
      await p.goto(`${SITE}/#/analyzer?a=${a}&b=${b}`, { waitUntil: 'domcontentloaded' });
      await exportReady(p, 'en');
      await p.waitForTimeout(800);
      const main = norm(await p.textContent('main'));
      await p.screenshot({ path: `${OUT}/${tag}_simple_en.png`, fullPage: true });
      const rep = reports[`${a}+${b}`] || reports[`${b}+${a}`];
      check(n, !!rep && main.includes(TITLE_A.en) && rep.outcomes,
        name, rep ? `status=${rep.outcomes?.interaction_status}, FDA labels=${(rep.sources_checked || []).find((c) => c.source === 'openfda_label')?.status}` : 'no /api/v3/report 200 response');
      if (rep) {
        const shown = rep.outcomes.outcomes.filter((o) => !o.research_only);
        const clinical = shown.filter((o) => o.effect_level === 'clinical_outcome');
        if (clinical.length) {
          const quotesOnPage = clinical.every((o) => o.supports.some((s) => main.includes(norm(s.excerpt).slice(0, 60))));
          const labelsOnPage = clinical.every((o) => main.includes(norm(o.label.en)));
          outcomeOk = outcomeOk && quotesOnPage && labelsOnPage;
          outcomeDetail.push(`${tag}: ${clinical.length} outcome(s), labels shown=${labelsOnPage}, quotes shown=${quotesOnPage}`);
        } else {
          const ns = main.includes(NO_SPECIFIC.en);
          outcomeOk = outcomeOk && ns;
          outcomeDetail.push(`${tag}: no clinical outcome, no-specific sentence shown=${ns}`);
        }
        const routeDocumented = rep.outcomes.chains.some((c) => c.links.some((l) => l.relation === 'may_lead_to' && l.provenance === 'documented'));
        // Simple mode shows only chains with a documented step (hypotheses are Research-only), each with its legend.
        const shownChains = rep.outcomes.chains.filter((c) => !c.research_only).length;
        mechOk = mechOk && !routeDocumented && (shownChains === 0 || /plausible but unconfirmed|verified biological annotation/i.test(main));
        bioOk = bioOk && main.includes('What does BIO-GINE add?') && rep.model?.available === true;
      }
      safeOk = safeOk && !SAFE_CLAIM(main);
      if (tag === 'warfarin_fluconazole') { wfPage = p; wfCtx = ctx; } else { await ctx.close(); }
    } catch (e) { check(n, false, name, String(e).slice(0, 160)); }
  }
  check(6, bioOk, 'BIO-GINE prediction displayed (block E, research score)');
  check(7, outcomeOk, 'Documented clinical outcomes appear with citations (or the exact no-specific sentence)', outcomeDetail.join('; '));
  check(8, mechOk, 'Mechanism explanations qualified (no exposure→outcome step shown as documented)');
  check(9, safeOk, 'No unsupported safety claims on the pages');

  // 11, 12, 16, 17, 18 on warfarin + fluconazole
  let quick = null, full = null, json = null;
  if (wfPage) {
    try {
      const simplePressed = await wfPage.locator('button[aria-pressed]', { hasText: 'Simple' }).first().getAttribute('aria-pressed').catch(() => null);
      const before = norm(await wfPage.textContent('main')).length;
      check(11, simplePressed === 'true' && before > 1000, 'Simple Mode works (default view)', `aria-pressed=${simplePressed}`);
      quick = await download(wfPage, /^Quick PDF/);
      full = await download(wfPage, 'Export PDF');
      json = await download(wfPage, /^JSON/);
      const btn = wfPage.locator('button[aria-pressed]', { hasText: 'Research mode' });
      await btn.click(); await wfPage.waitForTimeout(1000);
      const after = norm(await wfPage.textContent('main')).length;
      await wfPage.screenshot({ path: `${OUT}/warfarin_fluconazole_research_en.png`, fullPage: true });
      check(12, (await btn.getAttribute('aria-pressed')) === 'true' && after > before * 1.5, 'Research Mode works', `page text ${before} → ${after} chars`);
    } catch (e) { check(12, false, 'Simple/Research mode and exports', String(e).slice(0, 160)); }
    const qt = quick ? pdfText(quick) : '', ft = full ? pdfText(full) : '';
    const isPdf = (f) => f && fs.readFileSync(f).subarray(0, 5).toString() === '%PDF-';
    check(16, isPdf(quick) && qt.length > 500, 'Quick PDF downloads and renders', quick ? `${path.basename(quick)}, ${fs.statSync(quick).size} bytes, text ${qt.length} chars` : 'no download');
    check(17, isPdf(full) && ft.length > 2000, 'Full PDF downloads and renders', full ? `${path.basename(full)}, ${fs.statSync(full).size} bytes, text ${ft.length} chars` : 'no download');
    let jOk = false, jDet = 'no download';
    try { const j = JSON.parse(fs.readFileSync(json, 'utf8')); jOk = !!j.payload?.report?.outcomes; jDet = `${path.basename(json)}, outcomes block=${jOk}`; } catch (e) { jDet = String(e).slice(0, 100); }
    check(18, jOk, 'JSON export works', jDet);
    await wfCtx.close();
  } else {
    for (const [n, nm] of [[11, 'Simple Mode'], [12, 'Research Mode'], [16, 'Quick PDF'], [17, 'Full PDF'], [18, 'JSON export']]) check(n, false, nm, 'warfarin + fluconazole page did not load');
  }

  // 13. Multi-drug
  try {
    const { ctx, p } = await newPage('en');
    await p.goto(`${SITE}/#/multi`, { waitUntil: 'domcontentloaded' });
    const add = p.getByRole('textbox', { name: 'Add a drug' });
    await add.waitFor({ timeout: 60000 });
    for (const q of ['warfarin', 'fluconazole', 'simvastatin', 'clarithromycin', 'acetylsalicylic acid', 'metformin']) { await add.fill(q); await p.waitForTimeout(400); await add.press('Enter'); }
    await p.click('button:has-text("Check pairs")');
    await p.waitForSelector('svg[aria-label="pairwise network"]', { timeout: 150000 });
    await p.waitForTimeout(800);
    await p.screenshot({ path: `${OUT}/multi_6_drugs_en.png`, fullPage: true });
    const multi = apiCalls.find((c) => c.path === '/api/v3/multi');
    check(13, multi && multi.status === 200, 'Multi-drug analysis works (6 drugs, 15 pairs)', `api status=${multi && multi.status}`);
    await ctx.close();
  } catch (e) { check(13, false, 'Multi-drug analysis works', String(e).slice(0, 160)); }

  // 14, 15. English and Russian
  const enOk = results.find((r) => r.n === 3)?.ok;
  check(14, !!enOk, 'English works', 'Analyzer rendered with English headings');
  try {
    const { ctx, p } = await newPage('ru');
    await p.goto(`${SITE}/#/analyzer?a=DB00682&b=DB00196`, { waitUntil: 'domcontentloaded' });
    await exportReady(p, 'ru');
    await p.waitForTimeout(800);
    const main = norm(await p.textContent('main'));
    await p.screenshot({ path: `${OUT}/warfarin_fluconazole_simple_ru.png`, fullPage: true });
    check(15, main.includes(TITLE_A.ru) && !SAFE_CLAIM(main), 'Russian works', `RU heading present=${main.includes(TITLE_A.ru)}`);
    await ctx.close();
  } catch (e) { check(15, false, 'Russian works', String(e).slice(0, 160)); }

  // 19. Mobile
  try {
    const { ctx, p } = await newPage('en', { width: 390, height: 844 });
    await p.goto(`${SITE}/#/analyzer?a=DB00682&b=DB00196`, { waitUntil: 'domcontentloaded' });
    await exportReady(p, 'en');
    const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    await p.screenshot({ path: `${OUT}/warfarin_fluconazole_mobile_en.png` });
    check(19, overflow <= 0, 'Mobile layout works (390 px, no horizontal scroll)', `overflow=${overflow}px`);
    await ctx.close();
  } catch (e) { check(19, false, 'Mobile layout works', String(e).slice(0, 160)); }

  // 10. No CRESCENDDI anywhere: API responses, PDFs, JSON
  const restricted = (s) => /crescenddi|reference_set_outcome/i.test(s || '');
  const exp = [quick, full].map((f) => (f ? pdfText(f) : '')).join(' ') + (json ? fs.readFileSync(json, 'utf8') : '');
  check(10, !apiBodies.some(restricted) && !restricted(exp), 'No CRESCENDDI records exposed (API responses, PDFs, JSON)',
    `${apiBodies.length} API responses checked`);

  // 20. Console / network, and the API the production build actually calls
  const hosts = [...new Set(apiCalls.map((c) => c.host))];
  const bad = apiCalls.filter((c) => c.status >= 500 || c.status === 0);
  check(20, errors.length === 0 && bad.length === 0 && hosts.length === 1 && hosts[0] === API,
    'No console/network errors; the site calls the expected API',
    `API host(s)=${JSON.stringify(hosts)} (expected ${API}), API calls=${apiCalls.length}, 5xx=${bad.length}, console errors=${errors.length}`);
  for (const e of errors.slice(0, 10)) console.log(`      ${e}`);

  await browser.close();
  results.sort((x, y) => x.n - y.n);
  const fails = results.filter((r) => !r.ok);
  console.log(`\n${results.length - fails.length}/${results.length} production site checks passed.`);
  if (process.env.GITHUB_STEP_SUMMARY) {
    const rows = results.map((r) => `| ${r.n} | ${r.ok ? '✅ PASS' : '❌ FAIL'} | ${r.name} | ${r.detail.replace(/\|/g, '/')} |`);
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, [`## DDI-Net production site smoke test: ${results.length - fails.length}/${results.length} passed`, '',
      `Site: ${SITE} — expected API: ${API}`, '', '| # | Result | Check | Detail |', '|---|---|---|---|', ...rows, ''].join('\n'));
  }
  process.exit(fails.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
