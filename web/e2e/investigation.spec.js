import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { parseCSV } from '../src/science.js';

// Expectations are read independently from the immutable public source tables.
const manifest = JSON.parse(await readFile(new URL('../data/manifest.json', import.meta.url), 'utf8'));
const monthly = parseCSV(await readFile(new URL(`../data/${manifest.files.monthly.path}`, import.meta.url), 'utf8'));
const observations = parseCSV(await readFile(new URL(`../data/${manifest.files.observations.path}`, import.meta.url), 'utf8'));
const catalog = JSON.parse(await readFile(new URL('../regions/catalog.json', import.meta.url), 'utf8'));
const regional = JSON.parse(await readFile(new URL(`../regions/${catalog.regional.package.path}`, import.meta.url), 'utf8'));
const diagnostics = new WeakMap();
const numberText = value => String(value).replace('.', ',');
const regionalRows = pivot => regional.pilot.observations.filter(row => row.pivot_id === pivot);

test.beforeEach(async ({ page, baseURL }) => {
  const result = { errors: [], exceptions: [], external: [], failed: [] };
  diagnostics.set(page, result);
  const origin = new URL(baseURL).origin;
  page.on('console', message => { if (message.type() === 'error') result.errors.push(message.text()); });
  page.on('pageerror', issue => result.exceptions.push(issue.message));
  page.on('request', request => {
    const url = new URL(request.url());
    if (/^https?:$/.test(url.protocol) && url.origin !== origin) result.external.push(request.url());
  });
  page.on('response', response => { if (response.status() >= 400) result.failed.push(`${response.status()} ${response.url()}`); });
});

test.afterEach(async ({ page }, info) => {
  const result = diagnostics.get(page);
  if (info.status !== info.expectedStatus) await info.attach('investigation-diagnostics', { body: JSON.stringify(result, null, 2), contentType: 'application/json' });
  expect(result.errors, 'No console errors in the integrated production experience.').toEqual([]);
  expect(result.exceptions, 'No uncaught JavaScript exceptions.').toEqual([]);
  expect(result.external, 'All mandatory assets and scientific requests stay local.').toEqual([]);
  expect(result.failed, 'Every scientific and visual asset loads.').toEqual([]);
});

async function open(page, suffix = '') {
  await page.goto(`./${suffix}`);
  await expect(page.locator('#investigation-region')).toBeVisible();
  await expect(page.locator('#investigation-id')).toHaveText(/^AQ-[a-f0-9]{64}$/);
}

async function pair(page, a, b) {
  // If A currently equals the new B, change B first; native disabled options forbid identical endpoints.
  const currentB = await page.locator('#investigation-b').inputValue();
  if (currentB === a) await page.locator('#investigation-b').selectOption(b);
  await page.locator('#investigation-a').selectOption(a);
  await page.locator('#investigation-b').selectOption(b);
  await expect(page.locator('#investigation-id')).toHaveText(/^AQ-[a-f0-9]{64}$/);
}

async function exactComparison(page, a, b) {
  for (const index of ['ndvi', 'ndmi']) {
    const av = a[`${index}_median`], bv = b[`${index}_median`];
    await expect(page.locator(`[data-field="${index}-a"]`)).toHaveAttribute('data-value', String(av));
    await expect(page.locator(`[data-field="${index}-b"]`)).toHaveAttribute('data-value', String(bv));
    await expect(page.locator(`[data-field="delta-${index}"]`)).toHaveAttribute('data-value', String(bv - av));
  }
}

test('territorial Brazil has 27 states and opens only the two scientifically distinct studies', async ({ page }) => {
  await open(page);
  await expect(page.locator('#territorio .territorial-state')).toHaveCount(27);
  await expect(page.locator('#territorio .territorial-marker')).toHaveCount(3);
  await page.locator('[data-territory="caxias-ma"]').click();
  await expect(page.locator('.territorial-point-detail')).toContainText('Não há observações espectrais processadas de Caxias');
  await expect(page.locator('#investigation-region')).toHaveValue('paracatu-mg');
  await page.locator('[data-territory="guadalupe-pi"]').click();
  await expect(page.locator('#investigation-region')).toHaveValue('guadalupe-pi');
  await expect(page.locator('#investigation-status')).toContainText('sem modelo regional validado');
  await expect(page.locator('#regional-study-detail')).toBeVisible();
  await page.locator('#territorio .territorial-marker[aria-label^="Paracatu"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#investigation-region')).toHaveValue('paracatu-mg');
  await expect(page.locator('#investigation-status')).toHaveText('Estudo científico concluído');
  await expect(page.locator('#territorio')).toContainText('IBGE');
});

test('Paracatu comparison uses actual accepted monthly aggregates, signed deltas, rain and full scene provenance', async ({ page }) => {
  await open(page);
  const pivot = '8087';
  const rows = monthly.filter(row => row.pivot_id === pivot && row.monthly_status === 'ok');
  const a = rows.find(row => row.month === '2023-07'), b = rows.find(row => row.month === '2024-07');
  expect(a).toBeTruthy(); expect(b).toBeTruthy();
  await expect(page.locator('#investigation-a option')).toHaveCount(rows.length);
  const options = await page.locator('#investigation-a option').evaluateAll(items => items.map(item => item.value));
  expect(options).toEqual(rows.map(row => row.month));
  const absent = monthly.find(row => row.pivot_id === pivot && row.monthly_status !== 'ok');
  expect(options).not.toContain(absent.month);
  await pair(page, a.month, b.month);
  await exactComparison(page, a, b);
  await expect(page.locator('#investigation-granularity')).toContainText('Agregados mensais publicados');
  await expect(page.locator('#investigation-interval')).not.toContainText('dias');
  await expect(page.locator('#investigation-b option:checked')).toHaveValue(b.month);
  await expect(page.locator(`#investigation-b option[value="${a.month}"]`)).toHaveAttribute('disabled', '');
  const rowsUI = page.locator('#investigation-values tbody tr');
  await expect(rowsUI.nth(2)).toContainText(numberText(a.precip_mm));
  await expect(rowsUI.nth(2)).toContainText(numberText(b.precip_mm));
  await expect(rowsUI.nth(3)).toContainText(numberText(a.valid_pixel_pct_min));
  await page.locator('.investigation-provenance > summary').click();
  for (const row of observations.filter(row => row.pivot_id === pivot && [a.month,b.month].includes(row.month))) {
    await expect(page.locator('#investigation-provenance')).toContainText(row.scene_id);
    await expect(page.locator('#investigation-provenance')).toContainText(row.date);
  }
  await expect(page.locator('#investigation-limits')).toContainText('não permitem atribuir uma causa específica');
  await page.locator('#investigation-pivot').selectOption('16708');
  await expect(page.locator('#selected-id')).toHaveText('16708');
  await expect(page.locator('#pivot-select')).toHaveValue('16708');
  await page.locator('#pivot-select').selectOption('17373');
  await expect(page.locator('#investigation-pivot')).toHaveValue('17373');
});

test('Guadalupe scene selection shows exactly the published real images and never a rejected or substituted acquisition', async ({ page }) => {
  await open(page);
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await page.locator('#investigation-pivot').selectOption('PI:5795');
  const rows = regionalRows('PI:5795');
  await expect(page.locator('#investigation-a option')).toHaveCount(rows.length);
  await expect(page.locator('#investigation-granularity')).toContainText('Observações por cena');
  const a = rows.find(row => row.date === '2023-07-18'), b = rows.find(row => row.date === '2024-07-22');
  await pair(page, a.date, b.date);
  await exactComparison(page, a, b);
  const images = page.locator('#investigation-images img');
  await expect(images).toHaveCount(2);
  await expect.poll(() => images.evaluateAll(items => items.every(item => item.complete && item.naturalWidth > 0))).toBe(true);
  await expect(images.nth(0)).toHaveAttribute('alt', /2023-07-18/);
  await expect(images.nth(1)).toHaveAttribute('alt', /2024-07-22/);
  await expect(page.locator('#investigation-images')).toContainText(a.scene_id);
  await expect(page.locator('#investigation-images')).toContainText(b.scene_id);
  await expect(page.locator('#investigation-images')).toContainText('grupo dos cinco pivôs');
  const days = (Date.parse(b.date) - Date.parse(a.date)) / 86400000;
  await expect(page.locator('#investigation-interval')).toContainText(`${days} dias`);
  await page.locator('#investigation-a').selectOption('2023-01-29');
  await expect(page.locator('#investigation-images img')).toHaveCount(1);
  await expect(page.locator('#investigation-images .investigation-image-missing')).toHaveText(/Imagem comparativa não disponível para esta observação\./);
  const actual = rows.find(row => row.date === '2023-01-29');
  await exactComparison(page, actual, b);
  await page.locator('#investigation-pivot').selectOption('PI:5802');
  await expect(page.locator('#investigation-a option')).toHaveCount(5);
  await expect(page.locator('#investigation-a option[value="2024-03-24"]')).toHaveCount(0);
  await expect(page.locator('#regional-pivot-select')).toHaveValue('PI:5802');
});

test('A4 evidence report freezes exact current values, matching images, scientific identity and complete provenance', async ({ page }) => {
  await open(page);
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await pair(page, '2023-07-18', '2024-07-22');
  const pivot = await page.locator('#investigation-pivot').inputValue();
  const [a,b] = ['2023-07-18','2024-07-22'].map(date => regionalRows(pivot).find(row => row.date === date));
  const identity = await page.locator('#investigation-id').textContent();
  await page.locator('#generate-evidence').click();
  const report = page.locator('#evidence-report');
  await expect(report).toBeVisible();
  await expect(report.locator('[data-report-id]')).toHaveText(identity);
  await expect(report).toContainText('Ficha de Evidências — AquaClima');
  await expect(report).toContainText(catalog.regional.package.sha256);
  await expect(report).toContainText(catalog.regional.version);
  await expect(report).toContainText(pivot);
  await expect(report.locator('.evidence-image-pair img')).toHaveCount(2);
  for (const [index,key] of ['ndvi_median','ndmi_median'].entries()) {
    const cells = report.locator('.evidence-values tbody tr').nth(index).locator('td');
    await expect(cells.nth(0)).toHaveText(numberText(a[key]));
    await expect(cells.nth(1)).toHaveText(numberText(b[key]));
    await expect(cells.nth(2)).toHaveText(numberText(b[key]-a[key]));
  }
  await expect(report).toContainText(a.scene_id); await expect(report).toContainText(b.scene_id);
  await expect(report).toContainText('Gerada em (UTC)');
  const immutable = await report.locator('#evidence-document').innerHTML();
  // A background selection event models subsequent coordinator updates while the report stays open.
  await page.evaluate(() => { const select = document.querySelector('#investigation-pivot'); select.value = 'PI:5804'; select.dispatchEvent(new Event('change', { bubbles:true })); });
  await expect(page.locator('#investigation-pivot')).toHaveValue('PI:5804');
  expect(await report.locator('#evidence-document').innerHTML()).toBe(immutable);
  await page.locator('#evidence-utility-toggle').uncheck();
  await expect(report.locator('.evidence-utility')).toBeHidden();
  await expect(page.locator('#evidence-print-root .evidence-utility')).toBeHidden();
  await page.locator('#evidence-utility-toggle').check();
  const printRoot = page.locator('#evidence-print-root');
  await expect(printRoot).toBeHidden();
  expect(await printRoot.locator('.evidence-values').textContent()).toBe(await report.locator('.evidence-values').textContent());
  await expect(printRoot.locator('img')).toHaveCount(2);
  await page.evaluate(() => { window.evidencePrintRequests = 0; window.print = () => { window.evidencePrintRequests++; }; });
  await page.locator('#evidence-print').click();
  await expect.poll(() => page.evaluate(() => window.evidencePrintRequests)).toBe(1);
  await expect(page.locator('#evidence-print-status')).toContainText('processada localmente pelo navegador');
  await page.emulateMedia({ media:'print' });
  const print = await page.evaluate(() => ({ app:getComputedStyle(document.querySelector('#app')).display, toolbar:getComputedStyle(document.querySelector('.evidence-toolbar')).display, dialog:getComputedStyle(document.querySelector('#evidence-report')).display, root:getComputedStyle(document.querySelector('#evidence-print-root')).display, table:getComputedStyle(document.querySelector('#evidence-print-root .evidence-values')).breakInside, row:getComputedStyle(document.querySelector('#evidence-print-root .evidence-values tr')).breakInside, color:getComputedStyle(document.querySelector('#evidence-print-root h1')).color, horizontal:document.documentElement.scrollWidth <= innerWidth + 1 }));
  expect(print).toEqual({ app:'none',toolbar:'none',dialog:'none',root:'block',table:'avoid',row:'avoid',color:'rgb(0, 0, 0)',horizontal:true });
  await page.emulateMedia({ media:'screen' });
  await page.locator('#evidence-close').click();
  await expect(report).toHaveCount(0);
  await expect(printRoot).toHaveCount(0);
  await expect(page.locator('#generate-evidence')).toBeFocused();
});

test('shared investigation survives reload and preserves legacy pivot, index and exploration periods', async ({ page }) => {
  await open(page, '?pivot=16708&indice=ndmi&from=2023-01&to=2024-10');
  await expect(page.locator('#pivot-select')).toHaveValue('16708');
  await expect(page.locator('#investigation-pivot')).toHaveValue('16708');
  await expect(page.locator('#investigation-index')).toHaveValue('ndmi');
  await expect(page.locator('#from-month')).toHaveValue('2023-01');
  await expect(page.locator('#to-month')).toHaveValue('2024-10');
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await pair(page, '2023-07-18', '2024-07-22');
  await page.locator('#investigation-index').selectOption('ndmi');
  const identity = await page.locator('#investigation-id').textContent();
  await page.locator('#share-investigation').click();
  const shared = await page.locator('#investigation-share').inputValue();
  const url = new URL(shared);
  expect(url.searchParams.get('region')).toBe('guadalupe-pi');
  expect(url.searchParams.get('a')).toBe('2023-07-18');
  expect(url.searchParams.get('b')).toBe('2024-07-22');
  expect(url.searchParams.get('package')).toBe(catalog.regional.package.sha256);
  expect(url.searchParams.get('from')).toBe('2023-01');
  expect(url.hash).toBe('#investigacao');
  await page.goto(shared);
  await expect(page.locator('#investigation-id')).toHaveText(identity);
  await expect(page.locator('#investigation-region')).toHaveValue('guadalupe-pi');
  await expect(page.locator('#investigation-index')).toHaveValue('ndmi');
  await expect(page.locator('#investigation-images img')).toHaveCount(2);
  await page.reload();
  await expect(page.locator('#investigation-id')).toHaveText(identity);
});

test('invalid and cross-region URL entries are corrected and a different package blocks export until explicitly changed', async ({ page }) => {
  await open(page, '?region=guadalupe-pi&pivot=8087&a=2024-03-24&b=2024-03-24&indice=%3Cscript%3E&token=private');
  await expect(page.locator('#investigation-warning')).toContainText('Pivô inválido');
  await expect(page.locator('#investigation-pivot')).toHaveValue('PI:5795');
  expect(await page.locator('#investigation-a').inputValue()).not.toBe(await page.locator('#investigation-b').inputValue());
  await expect(page.locator('#investigation-index')).toHaveValue('ndvi');
  expect(new URL(page.url()).searchParams.has('token')).toBe(false);
  await page.goto(`./?region=guadalupe-pi&pivot=PI%3A5795&a=2023-07-18&b=2024-07-22&package=${'0'.repeat(64)}`);
  await expect(page.locator('#investigation-warning')).toContainText('comparação está bloqueada');
  await expect(page.locator('.investigation-analysis')).toBeHidden();
  await expect(page.locator('#generate-evidence')).toBeHidden();
  await page.locator('#investigation-current-package').click();
  await expect(page.locator('.investigation-analysis')).toBeVisible();
  await expect(page.locator('#generate-evidence')).toBeVisible();
  await expect(page.locator('#investigation-package')).toContainText(catalog.regional.package.sha256);
});

test('five manual demo steps navigate the real WebGIS and back, restart and Escape restore the prior selection', async ({ page }) => {
  await open(page, '?pivot=16708&indice=ndmi&from=2023-01&to=2023-12#investigacao');
  const before = { url:page.url(), a:await page.locator('#investigation-a').inputValue(), b:await page.locator('#investigation-b').inputValue(), identity:await page.locator('#investigation-id').textContent() };
  await page.locator('#start-demo').click();
  await expect(page.locator('.demo-step-counter')).toHaveText('Passo 1 de 5');
  await expect(page.locator('[data-demo="back"]')).toBeDisabled();
  await page.locator('[data-demo="next"]').click();
  await expect(page.locator('#demo-title')).toHaveText('O estudo de Paracatu');
  await expect(page.locator('#map path[role="button"]')).toHaveCount(5);
  await page.locator('[data-demo="next"]').click();
  await expect(page.locator('#demo-title')).toHaveText('Uma investigação');
  await expect(page.locator('#investigation-region')).toHaveValue('paracatu-mg');
  const mainPivot = await page.locator('#investigation-pivot').inputValue();
  const [ma,mb] = await Promise.all(['a','b'].map(key => page.locator(`#investigation-${key}`).inputValue()));
  await exactComparison(page, monthly.find(row => row.pivot_id === mainPivot && row.month === ma), monthly.find(row => row.pivot_id === mainPivot && row.month === mb));
  await page.locator('#generate-evidence').click();
  await expect(page.locator('#evidence-report')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#evidence-report')).toHaveCount(0);
  await expect(page.locator('.demo-dock')).toBeVisible();
  await expect(page.locator('.demo-step-counter')).toHaveText('Passo 3 de 5');
  await page.locator('[data-demo="next"]').click();
  await expect(page.locator('#demo-title')).toHaveText('Expansão para Guadalupe');
  await expect(page.locator('#investigation-region')).toHaveValue('guadalupe-pi');
  await expect(page.locator('#investigation-images img')).toHaveCount(2);
  await page.locator('[data-demo="back"]').click();
  await expect(page.locator('.demo-step-counter')).toHaveText('Passo 3 de 5');
  await page.locator('[data-demo="next"]').click();
  await page.locator('[data-demo="next"]').click();
  await expect(page.locator('#demo-title')).toHaveText('Conclusões e limitações');
  await expect(page.locator('.demo-dock progress')).toHaveAttribute('value','5');
  await expect(page.locator('[data-demo="next"]')).toBeDisabled();
  await page.locator('[data-demo="restart"]').click();
  await expect(page.locator('.demo-step-counter')).toHaveText('Passo 1 de 5');
  await page.keyboard.press('Escape');
  await expect(page.locator('.demo-dock')).toBeHidden();
  expect(page.url()).toBe(before.url);
  await expect(page.locator('#investigation-pivot')).toHaveValue('16708');
  await expect(page.locator('#investigation-a')).toHaveValue(before.a);
  await expect(page.locator('#investigation-b')).toHaveValue(before.b);
  await expect(page.locator('#investigation-id')).toHaveText(before.identity);
  await expect(page.locator('#from-month')).toHaveValue('2023-01');
  await expect(page.locator('#to-month')).toHaveValue('2023-12');
  await expect(page.locator('#start-demo')).toBeFocused();
  await page.locator('#start-demo').click();
  await page.locator('[data-demo="end"]').click();
  await expect(page.locator('.demo-dock')).toBeHidden();
});

test('mobile investigation, evidence preview and keyboard demo fit the viewport with local runtime assets', async ({ page }) => {
  await page.setViewportSize({ width:390,height:844 });
  await page.emulateMedia({ reducedMotion:'reduce' });
  await open(page);
  await page.locator('[data-territory="guadalupe-pi"]').click();
  await pair(page,'2023-07-18','2024-07-22');
  await expect(page.locator('#investigation-images img')).toHaveCount(2);
  const viewportFits = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
  expect(await viewportFits()).toBe(true);
  await page.locator('#generate-evidence').click();
  await expect(page.locator('#evidence-report')).toBeVisible();
  expect(await viewportFits()).toBe(true);
  expect(await page.locator('#evidence-report').evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.locator('#evidence-report')).toHaveCount(0);
  await page.locator('#start-demo').click();
  await expect(page.locator('.demo-dock')).toBeVisible();
  await page.locator('[data-demo="next"]').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.demo-step-counter')).toHaveText('Passo 2 de 5');
  expect(await viewportFits()).toBe(true);
  await page.keyboard.press('Escape');
  await expect(page.locator('.demo-dock')).toBeHidden();
});

test('Paracatu interactions during regional loading and from an active regional study preserve a valid synchronized investigation', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release=resolve; });
  await page.route('**/regions/catalog.json', async route => { await gate; await route.continue(); });
  await page.goto(`./?region=guadalupe-pi&pivot=PI%3A5795&a=2023-07-18&b=2024-07-22&package=${catalog.regional.package.sha256}`);
  await expect(page.locator('#kpi-observations')).toHaveText('256');
  await page.locator('#pivot-select').selectOption('16708');
  await page.locator('[data-target="ndmi_median"]').click();
  release();
  await expect(page.locator('#investigation-region')).toHaveValue('paracatu-mg');
  await expect(page.locator('#investigation-pivot')).toHaveValue('16708');
  await expect(page.locator('#investigation-index')).toHaveValue('ndmi');
  await expect(page.locator('.investigation-analysis')).toBeVisible();
  await expect(page.locator('#investigation-package')).toContainText(manifest.package_sha256);
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await page.locator('#pivot-select').selectOption('17373');
  await expect(page.locator('#investigation-region')).toHaveValue('paracatu-mg');
  await expect(page.locator('#investigation-pivot')).toHaveValue('17373');
  await expect(page.locator('#study-select')).toHaveValue('paracatu-mg');
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await page.locator('[data-target="ndvi_median"]').click();
  await expect(page.locator('#investigation-region')).toHaveValue('paracatu-mg');
  await expect(page.locator('#investigation-index')).toHaveValue('ndvi');
});
