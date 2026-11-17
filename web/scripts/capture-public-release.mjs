// Read-only release QA: connects exclusively to the deployed GitHub Pages URL.
// No local server, data substitution, injected HTML, or reconstructed screenshots.
import { chromium, expect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { parseCSV } from '../src/science.js';

const base = 'https://altaeir-13.github.io/FTL-Final-Project/';
const output = fileURLToPath(new URL('../../docs/evidencias/release-publica/', import.meta.url));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const textNumber = value => value == null ? 'Ausente' : String(value).replace('.', ',');
const result = {
  qa_version: '1.0.0', started_at_utc: new Date().toISOString(), public_url: base,
  scope: 'Published site only; no local server and no scientific or interface data substitution.',
  reference_main_commit: 'ad107d0', reference_deployment_run: '44067496065',
  browser: 'Microsoft Edge / Chromium headless', desktop_viewport: { width: 1440, height: 1100 },
  mobile_viewport: { width: 390, height: 844 }, console_errors: [], runtime_errors: [],
  blocked_requests: [], failed_responses: [], requests: [], public_sources: [], investigations: [], outputs: [],
};

function allowed(value) {
  const url = new URL(value, base);
  if (url.protocol !== 'https:' || !url.href.startsWith(base) || url.username || url.password || url.port) throw new Error(`Public QA rejected a non-project request: ${url.href}`);
  return url.href;
}

let browser;
try {
  await mkdir(output, { recursive: true });
  browser = await chromium.launch({ channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless: true });
  result.browser_version = browser.version();
  const context = await browser.newContext({ viewport: result.desktop_viewport, reducedMotion: 'reduce' });
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('blob:') || url.startsWith('data:')) return route.continue();
    try { allowed(url); return route.continue(); }
    catch { result.blocked_requests.push(url); return route.abort(); }
  });
  const page = await context.newPage();
  page.on('console', message => { if (message.type() === 'error') result.console_errors.push(message.text()); });
  page.on('pageerror', error => result.runtime_errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url())) result.requests.push({ method: request.method(), url: request.url(), resource_type: request.resourceType() });
  });
  page.on('response', response => { if (response.status() >= 400) result.failed_responses.push({ status: response.status(), url: response.url() }); });
  async function publicBytes(relative, descriptor) {
    const url = allowed(relative);
    const response = await context.request.get(url);
    if (!response.ok()) throw new Error(`Public source failed: ${response.status()} ${url}`);
    const bytes = await response.body();
    const hash = sha256(bytes);
    if (descriptor && (bytes.length !== descriptor.bytes || hash !== descriptor.sha256)) throw new Error(`Public source integrity differs: ${relative}`);
    result.public_sources.push({ url, bytes: bytes.length, sha256: hash });
    return bytes;
  }
  const manifest = JSON.parse(await publicBytes('data/manifest.json'));
  const frozen = {};
  for (const name of ['monthly', 'observations', 'quality']) {
    const descriptor = manifest.files[name];
    if (!descriptor?.path?.startsWith('packages/') || descriptor.path.includes('..')) throw new Error('Unexpected public scientific descriptor.');
    frozen[name] = parseCSV((await publicBytes(`data/${descriptor.path}`, descriptor)).toString('utf8'));
  }
  const catalog = JSON.parse(await publicBytes('regions/catalog.json'));
  const regionalDescriptor = catalog.regional.package;
  const regional = JSON.parse(await publicBytes(`regions/${regionalDescriptor.path}`, regionalDescriptor));
  for (const image of catalog.regional.images) await publicBytes(`regions/${image.path}`, image);
  result.scientific_packages = { paracatu: manifest.package_sha256, guadalupe: regionalDescriptor.sha256 };

  async function saveCapture(locator, filename) {
    await locator.screenshot({ path: resolve(output, filename), animations: 'disabled' });
  }
  async function verifyIndices(a, b) {
    for (const index of ['ndvi', 'ndmi']) {
      await expect(page.locator(`[data-field="${index}-a"]`)).toHaveAttribute('data-value', String(a[`${index}_median`]));
      await expect(page.locator(`[data-field="${index}-b"]`)).toHaveAttribute('data-value', String(b[`${index}_median`]));
      await expect(page.locator(`[data-field="delta-${index}"]`)).toHaveAttribute('data-value', String(b[`${index}_median`] - a[`${index}_median`]));
    }
  }
  async function saveReport({ region, pivot, a, b, hash, filename, expectedImages, scenes, precip, quality }) {
    await verifyIndices(a, b);
    const currentURL = new URL(page.url()); currentURL.hash = 'investigacao';
    const investigationId = await page.locator('#investigation-id').textContent();
    await page.locator('#generate-evidence').click();
    const report = page.locator('#evidence-report[open]');
    await expect(report).toBeVisible();
    await expect(report.locator('[data-report-id]')).toHaveText(investigationId);
    await expect(report).toContainText(hash);
    await expect(report).toContainText(pivot);
    for (const [index, key] of ['ndvi_median', 'ndmi_median'].entries()) {
      const cells = report.locator('.evidence-values tbody tr').nth(index).locator('td');
      await expect(cells.nth(0)).toHaveText(textNumber(a[key]));
      await expect(cells.nth(1)).toHaveText(textNumber(b[key]));
      await expect(cells.nth(2)).toHaveText(textNumber(b[key] - a[key]));
    }
    const rainCells = report.locator('.evidence-values tbody tr').nth(2).locator('td');
    const qualityCells = report.locator('.evidence-values tbody tr').nth(3).locator('td');
    for (let index = 0; index < 2; index++) {
      await expect(rainCells.nth(index)).toHaveText(textNumber(precip[index]));
      await expect(qualityCells.nth(index)).toHaveText(textNumber(quality[index]));
    }
    for (const scene of scenes) await expect(report).toContainText(scene);
    const printRoot = page.locator('#evidence-print-root');
    await expect(printRoot.locator('img')).toHaveCount(expectedImages);
    await expect(report.locator('img')).toHaveCount(expectedImages);
    expect(await printRoot.locator('.evidence-values').textContent()).toBe(await report.locator('.evidence-values').textContent());
    await page.locator('#evidence-report img, #evidence-print-root img').evaluateAll(images => Promise.all(images.map(image => image.decode())));
    const generation = (await report.textContent()).match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z/)?.[0];
    if (!generation) throw new Error('Report generation date absent.');
    if (region === 'guadalupe-pi') await saveCapture(page, 'ficha-guadalupe-previa.png');
    // Native browser print pipeline uses the public app's exact immutable normal-flow copy.
    await page.pdf({ path: resolve(output, filename), format: 'A4', preferCSSPageSize: true, printBackground: true, tagged: true });
    result.investigations.push({ region, pivot, a: a.date || a.month, b: b.date || b.month, package_sha256: hash, investigation_id: investigationId, generation_utc: generation, public_investigation_url: currentURL.href,
      values: { ndvi_a: a.ndvi_median, ndvi_b: b.ndvi_median, delta_ndvi: b.ndvi_median-a.ndvi_median, ndmi_a: a.ndmi_median, ndmi_b: b.ndmi_median, delta_ndmi: b.ndmi_median-a.ndmi_median, precip_mm_a: precip[0], precip_mm_b: precip[1], valid_pixel_pct_a: quality[0], valid_pixel_pct_b: quality[1] }, scene_ids: scenes, matching_images: expectedImages, output_pdf: filename });
    await page.locator('#evidence-close').click();
  }

  await page.goto(`${base}?region=paracatu-mg&pivot=8087&a=2023-07&b=2024-07&indice=ndvi&package=${manifest.package_sha256}#territorio`, { waitUntil: 'networkidle' });
  await expect(page.locator('#investigation-id')).toHaveText(/^AQ-[a-f0-9]{64}$/);
  await expect(page.locator('#territorio .territorial-state')).toHaveCount(27);
  await saveCapture(page.locator('#territorio'), 'territorio-desktop.png');
  await saveCapture(page.locator('#investigacao'), 'investigacao-paracatu-desktop.png');
  const pc = ['2023-07', '2024-07'].map(month => frozen.monthly.find(row => row.pivot_id === '8087' && row.month === month));
  const pcQuality = ['2023-07', '2024-07'].map(month => frozen.quality.find(row => row.pivot_id === '8087' && row.month === month));
  await saveReport({ region: 'paracatu-mg', pivot: '8087', a: pc[0], b: pc[1], hash: manifest.package_sha256,
    filename: 'ficha-evidencias-paracatu.pdf', expectedImages: 0, precip: pc.map(row => row.precip_mm), quality: pcQuality.map(row => row.valid_pixel_pct_min),
    scenes: frozen.observations.filter(row => row.pivot_id === '8087' && ['2023-07','2024-07'].includes(row.month)).map(row => row.scene_id) });
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await page.locator('#investigation-pivot').selectOption('PI:5795');
  await page.locator('#investigation-a').selectOption('2023-07-18');
  await page.locator('#investigation-b').selectOption('2024-07-22');
  await expect(page.locator('#investigation-id')).toHaveText(/^AQ-[a-f0-9]{64}$/);
  await page.locator('#investigation-images img').evaluateAll(images => Promise.all(images.map(image => image.decode())));
  await saveCapture(page.locator('#investigacao'), 'investigacao-guadalupe-desktop.png');
  const gp = ['2023-07-18','2024-07-22'].map(date => regional.pilot.observations.find(row => row.pivot_id === 'PI:5795' && row.date === date));
  await saveReport({ region: 'guadalupe-pi', pivot: 'PI:5795', a: gp[0], b: gp[1], hash: regionalDescriptor.sha256,
    filename: 'ficha-evidencias-guadalupe.pdf', expectedImages: 2, quality: gp.map(row => row.valid_pixel_pct),
    precip: gp.map(row => regional.pilot.monthly.find(month => month.pivot_id === row.pivot_id && month.month === row.month).precip_mm), scenes: gp.map(row => row.scene_id) });
  const beforeDemo = page.url();
  await page.locator('#start-demo').click();
  for (let step = 0; step < 3; step++) await page.locator('[data-demo=next]').click();
  await expect(page.locator('#demo-title')).toHaveText('Expansão para Guadalupe');
  await expect(page.locator('#investigation-images img')).toHaveCount(2);
  await saveCapture(page, 'demonstracao-publica-desktop.png');
  await page.keyboard.press('Escape');
  await expect(page.locator('.demo-dock')).toBeHidden();
  expect(page.url()).toBe(beforeDemo);
  await page.setViewportSize(result.mobile_viewport);
  await page.locator('#territorio').scrollIntoViewIfNeeded();
  await saveCapture(page.locator('#territorio'), 'territorio-mobile.png');
  await page.locator('#investigation-title').evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }));
  await saveCapture(page, 'investigacao-guadalupe-mobile.png');
  await page.locator('#investigation-images').evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }));
  await saveCapture(page, 'investigacao-guadalupe-mobile-imagens.png');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  result.public_assets = await page.evaluate(() => [...document.querySelectorAll('script[src],link[rel="stylesheet"][href]')].map(element => element.src || element.href));
  result.public_assets.forEach(allowed);
  if ([result.console_errors,result.runtime_errors,result.blocked_requests,result.failed_responses].some(items => items.length)) throw new Error('Public QA contains errors or non-project requests. See capture diagnostics.');
  const files = ['territorio-desktop.png','investigacao-paracatu-desktop.png','investigacao-guadalupe-desktop.png','ficha-guadalupe-previa.png','demonstracao-publica-desktop.png','territorio-mobile.png','investigacao-guadalupe-mobile.png','investigacao-guadalupe-mobile-imagens.png','ficha-evidencias-paracatu.pdf','ficha-evidencias-guadalupe.pdf'];
  for (const file of files) { const bytes = await readFile(resolve(output,file)); result.outputs.push({ file, bytes: bytes.length, sha256: sha256(bytes) }); }
  result.completed_at_utc = new Date().toISOString(); result.status = 'passed';
  console.log(JSON.stringify({ status: result.status, public_url: base, outputs: result.outputs.length, investigations: result.investigations.map(row => ({ region:row.region, id:row.investigation_id })) }, null, 2));
} catch (error) {
  result.status = 'failed'; result.failure = error.message;
  throw error;
} finally {
  await browser?.close();
  await writeFile(resolve(output,'capturas-publicas.json'), JSON.stringify(result,null,2)+'\n');
}
