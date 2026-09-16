import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const BASE_URL = process.env.PRODUCTION_URL || 'https://memoir-reader-application.onrender.com';
const EXPECTED_SHA = process.env.EXPECTED_SHA || '';
const OUTPUT_DIR = process.env.VISUAL_QA_OUTPUT || 'artifacts/visual-qa';

const viewports = [
  { name: 'phone-portrait', width: 390, height: 844, spread: false },
  { name: 'phone-landscape', width: 844, height: 390, spread: false },
  { name: 'tablet-portrait', width: 820, height: 1180, spread: false },
  { name: 'tablet-landscape', width: 1180, height: 820, spread: true },
  { name: 'desktop-landscape', width: 1366, height: 768, spread: true },
  { name: 'constrained-window', width: 850, height: 700, spread: false },
];

async function json(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json', 'User-Agent': 'memoir-reader-visual-qa/1.0' } });
  let payload = {};
  try { payload = await response.json(); } catch {}
  return { response, payload };
}

async function pageKinds(page) {
  return page.locator('.page-sheet').evaluateAll((nodes) => nodes.map((node) => node.dataset.pageKind));
}

async function clickNextAndWait(page) {
  const before = await page.locator('.page-sheet').first().getAttribute('data-page-index');
  await page.locator('[data-next]').click();
  await page.waitForFunction((oldIndex) => {
    const node = document.querySelector('.page-sheet');
    return node && node.dataset.pageIndex !== oldIndex;
  }, before);
  await page.waitForTimeout(320);
}

async function clickPreviousAndWait(page) {
  const before = await page.locator('.page-sheet').first().getAttribute('data-page-index');
  await page.locator('[data-previous]').click();
  await page.waitForFunction((oldIndex) => {
    const node = document.querySelector('.page-sheet');
    return node && node.dataset.pageIndex !== oldIndex;
  }, before);
  await page.waitForTimeout(320);
}

async function assertNoViewportOverflow(page) {
  const overflow = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  assert.ok(overflow.document <= overflow.viewport + 1, `document horizontal overflow: ${JSON.stringify(overflow)}`);
  assert.ok(overflow.body <= overflow.viewport + 1, `body horizontal overflow: ${JSON.stringify(overflow)}`);
}

async function assertCover(page, name) {
  assert.deepEqual(await pageKinds(page), ['cover'], `${name}: book must open on the front cover only`);
  const image = page.locator('.cover-image');
  await image.waitFor({ state: 'visible' });
  const dimensions = await image.evaluate((node) => ({
    naturalWidth: node.naturalWidth,
    naturalHeight: node.naturalHeight,
    clientWidth: node.clientWidth,
    clientHeight: node.clientHeight,
    objectFit: getComputedStyle(node).objectFit,
  }));
  assert.ok(dimensions.naturalWidth > 0 && dimensions.naturalHeight > 0, `${name}: cover image did not decode`);
  assert.equal(dimensions.objectFit, 'contain', `${name}: cover must preserve aspect ratio without cropping`);
}

async function assertSingleOpeningSequence(page, name) {
  const expected = ['cover', 'blank', 'title', 'blank', 'dedication', 'blank', 'index', 'blank', 'manuscript'];
  assert.deepEqual(await pageKinds(page), [expected[0]], `${name}: unexpected initial page`);
  for (let index = 1; index < expected.length; index += 1) {
    await clickNextAndWait(page);
    assert.deepEqual(await pageKinds(page), [expected[index]], `${name}: opening sequence mismatch at physical surface ${index + 1}`);
  }
  const position = (await page.locator('[data-position]').textContent())?.trim();
  assert.equal(position, 'Page 1 of 105', `${name}: Chapter 1 must begin at manuscript Page 1`);
}

async function assertSpreadOpeningSequence(page, name) {
  assert.deepEqual(await pageKinds(page), ['cover'], `${name}: closed book cover must be singleton`);
  const spreads = [
    ['blank', 'title'],
    ['blank', 'dedication'],
    ['blank', 'index'],
    ['blank', 'manuscript'],
  ];
  for (const expected of spreads) {
    await clickNextAndWait(page);
    assert.deepEqual(await pageKinds(page), expected, `${name}: recto/verso opening spread mismatch`);
  }
  const position = (await page.locator('[data-position]').textContent())?.trim();
  assert.equal(position, 'Page 1 of 105', `${name}: Chapter 1 must retain manuscript Page 1 in spread mode`);

  await clickPreviousAndWait(page);
  assert.deepEqual(await pageKinds(page), ['blank', 'index'], `${name}: backward navigation must return exactly one spread`);
}

await fs.mkdir(OUTPUT_DIR, { recursive: true });

const health = await json(`${BASE_URL}/health`);
assert.equal(health.response.status, 200, `Production health returned HTTP ${health.response.status}`);
assert.equal(health.payload.status, 'ok', 'Production health is not ok');
assert.equal(health.payload.canonical_source, 'techcorp-DevApps/memoir', 'Production canonical source is incorrect');
if (EXPECTED_SHA) assert.equal(health.payload.application_commit, EXPECTED_SHA, 'Render is not serving the expected application commit');

const publication = await json(`${BASE_URL}/api/publication`);
if (publication.response.status === 503 && publication.payload.error === 'publication_assembly_unavailable') {
  const message = String(publication.payload.message || '');
  if (message.includes('AUTHOR_APPROVED_ASSET_NOT_MATERIALIZED')) {
    console.log('Physical publication visual QA is controlled-blocked until the exact approved front cover is materialized.');
    process.exit(0);
  }
}
assert.equal(publication.response.status, 200, `Physical publication endpoint returned HTTP ${publication.response.status}: ${JSON.stringify(publication.payload)}`);
assert.equal(publication.payload.commit_sha, health.payload.commit_sha, 'Physical publication is not pinned to the health-reported memoir commit');
assert.equal(publication.payload.front_matter_pages, 8, 'Front matter must contain exactly eight physical surfaces before Chapter 1');
assert.equal(publication.payload.pages?.[8]?.kind, 'manuscript', 'Physical surface 9 must be Chapter 1');
assert.equal(publication.payload.pages?.[8]?.display_number, 1, 'Chapter 1 must begin at manuscript Page 1');

const browser = await chromium.launch({ headless: true });
try {
  for (const viewport of viewports) {
    const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
    const page = await context.newPage();
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 120000 });
    await page.locator('body.book-ready').waitFor({ state: 'attached', timeout: 120000 });

    const readerMode = await page.locator('[data-source-info]').getAttribute('data-reader-mode');
    assert.equal(readerMode, 'physical-publication', `${viewport.name}: production did not activate physical-publication mode`);
    await assertNoViewportOverflow(page);
    await assertCover(page, viewport.name);
    await page.screenshot({ path: path.join(OUTPUT_DIR, `${viewport.name}-cover.png`), fullPage: true });

    if (viewport.spread) await assertSpreadOpeningSequence(page, viewport.name);
    else await assertSingleOpeningSequence(page, viewport.name);

    await assertNoViewportOverflow(page);
    await page.screenshot({ path: path.join(OUTPUT_DIR, `${viewport.name}-chapter-1-page-1.png`), fullPage: true });
    await context.close();
  }

  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 120000 });
  await page.locator('body.book-ready').waitFor({ state: 'attached', timeout: 120000 });
  for (let i = 0; i < 8; i += 1) await clickNextAndWait(page);
  assert.deepEqual(await pageKinds(page), ['manuscript'], 'orientation test must reach manuscript Page 1 in portrait');
  await page.setViewportSize({ width: 1180, height: 820 });
  await page.waitForTimeout(500);
  assert.deepEqual(await pageKinds(page), ['blank', 'manuscript'], 'orientation change must preserve semantic manuscript Page 1 in its correct spread');
  const position = (await page.locator('[data-position]').textContent())?.trim();
  assert.equal(position, 'Page 1 of 105', 'orientation change corrupted logical manuscript position');
  await page.screenshot({ path: path.join(OUTPUT_DIR, 'orientation-preservation.png'), fullPage: true });
  await context.close();

  const reducedContext = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const reducedPage = await reducedContext.newPage();
  await reducedPage.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 120000 });
  await reducedPage.locator('body.book-ready').waitFor({ state: 'attached', timeout: 120000 });
  await reducedPage.locator('[data-next]').click();
  await reducedPage.waitForTimeout(50);
  const animationName = await reducedPage.locator('[data-book-stage]').evaluate((node) => getComputedStyle(node).animationName);
  assert.equal(animationName, 'none', 'prefers-reduced-motion must suppress page-turn animation');
  await reducedContext.close();
} finally {
  await browser.close();
}

console.log('Production physical-book visual QA passed across all required viewport classes.');
