import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { parseCSV, filterMonthly, coverageState } from '../src/science.js';

const dataRoot = new URL('../data/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', dataRoot), 'utf8'));
const frozen = {};
for (const name of ['monthly', 'observations', 'precipitation', 'quality', 'events', 'models']) {
  frozen[name] = parseCSV(await readFile(new URL(manifest.files[name].path, dataRoot), 'utf8'));
}
const ids = ['8087', '16708', '17373', '17382', '19997'];
const failures = new WeakMap();
const format = value => Number(value).toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const productionDependency = url => /\/(?:@vite|@react-refresh|@id|@fs|src|node_modules)(?:\/|$)|(?:__vite_ping|__webpack_hmr|sockjs)/i.test(url.pathname)
  || /\/(?:tiles?|api)(?:\/|$)|\.(?:pbf|mvt)(?:$|\?)/i.test(url.pathname);

test.beforeEach(async ({ page, baseURL }) => {
  const result = { console: [], runtime: [], external: [], http: [], outsideBase: [], developmentOrTiles: [], insecure: [], sockets: [] };
  failures.set(page, result);
  const origin = new URL(baseURL).origin;
  page.on('console', message => { if (message.type() === 'error') result.console.push(message.text()); });
  page.on('pageerror', error => result.runtime.push(error.message));
  page.on('request', request => {
    const url = new URL(request.url());
    if (/^https?:$/.test(url.protocol)) {
      if (url.origin !== origin) result.external.push(request.url());
      if (!url.href.startsWith(baseURL)) result.outsideBase.push(request.url());
      if (productionDependency(url)) result.developmentOrTiles.push(request.url());
      if (new URL(baseURL).protocol === 'https:' && url.protocol !== 'https:') result.insecure.push(request.url());
    }
  });
  page.on('response', response => { if (response.status() >= 400) result.http.push(`${response.status()} ${response.url()}`); });
  page.on('websocket', socket => result.sockets.push(socket.url()));
});

test.afterEach(async ({ page }, testInfo) => {
  const result = failures.get(page);
  if (testInfo.status !== testInfo.expectedStatus) await testInfo.attach('browser-diagnostics', { body: JSON.stringify(result, null, 2), contentType: 'application/json' });
  expect(result.external, 'A demonstração não faz requisições HTTP externas.').toEqual([]);
  expect(result.outsideBase, 'Documentos, assets e dados permanecem no caminho publicado do projeto.').toEqual([]);
  expect(result.developmentOrTiles, 'O runtime não usa servidor de desenvolvimento, backend ou tiles.').toEqual([]);
  expect(result.insecure, 'A demonstração pública carrega somente recursos HTTPS.').toEqual([]);
  expect(result.sockets, 'O build estático não depende de HMR ou serviços WebSocket.').toEqual([]);
  expect(result.runtime, 'Nenhuma exceção JavaScript não tratada.').toEqual([]);
  if (!testInfo.annotations.some(annotation => annotation.type === 'expected-load-failure')) {
    expect(result.console, 'Nenhum erro no console.').toEqual([]);
    expect(result.http, 'Todos os assets e contratos devem carregar no caminho do projeto.').toEqual([]);
  }
});

async function open(page, suffix = '') {
  await page.goto(`./${suffix}`);
  await expect(page.locator('#kpi-observations')).toHaveText('256');
}

async function expectPoints(page, pivotId, target, from = '2022-01', to = '2024-12') {
  const expected = filterMonthly(frozen.monthly, pivotId, from, to).filter(row => row.monthly_status === 'ok' && row[target] != null);
  const points = page.locator('#series-chart circle[data-value]');
  await expect(points).toHaveCount(expected.length);
  const actual = await points.evaluateAll(elements => elements.map(element => ({ month: element.getAttribute('data-month'), value: Number(element.getAttribute('data-value')), target: element.getAttribute('data-target') })));
  expect(actual).toEqual(expected.map(row => ({ month: row.month, value: row[target], target })));
}

test('overview and all five selections use frozen observations and real geometries', async ({ page }) => {
  await open(page);
  await expect(page.locator('#kpi-pivots')).toHaveText('5');
  await expect(page.locator('#kpi-scenes')).toHaveText('57 cenas Sentinel-2 L2A');
  await expect(page.locator('#kpi-coverage')).toHaveText('78,3%');
  await expect(page.locator('#kpi-slots')).toHaveText('141 de 180 espaços pivô/mês');
  await expect(page.locator('#map path[role="button"]')).toHaveCount(5);
  for (const id of ids) {
    await page.locator('#pivot-select').selectOption(id);
    await expect(page.locator('#selected-id')).toHaveText(id);
    await expect(page.locator('#series-context')).toContainText(`ANA ${id}`);
    await expect(page.locator('#model-index')).toContainText(`ANA ${id}`);
    await expectPoints(page, id, 'ndvi_median');
    await expect(page.locator(`#pivot-list button[data-pivot="${id}"]`)).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: new RegExp(`Selecionar pivô ANA ${id},`) })).toHaveAttribute('aria-pressed', 'true');
  }
});

test('NDVI/NDMI tabs, years and custom periods synchronize chart values without filling gaps', async ({ page }) => {
  await open(page);
  await page.getByRole('button', { name: 'NDMI', exact: true }).click();
  await expectPoints(page, '8087', 'ndmi_median');
  const lowestMonth = await page.locator('#series-chart circle[data-value]').evaluateAll(points => points.reduce((lowest, point) => Number(point.getAttribute('cy')) > Number(lowest.getAttribute('cy')) ? point : lowest).getAttribute('data-month'));
  const lowPoint = page.locator(`#series-chart circle[data-month="${lowestMonth}"]`);
  const tooltip = page.locator('#series-chart .ac-chart-tooltip');
  const expectTooltipInside = async () => {
    await expect(tooltip).toBeVisible();
    await expect(tooltip).toContainText('NDMI:');
    const [tip, chart] = await Promise.all([tooltip.boundingBox(), page.locator('#series-chart').boundingBox()]);
    expect(tip.x).toBeGreaterThanOrEqual(chart.x - 1);
    expect(tip.y).toBeGreaterThanOrEqual(chart.y - 1);
    expect(tip.x + tip.width).toBeLessThanOrEqual(chart.x + chart.width + 1);
    expect(tip.y + tip.height).toBeLessThanOrEqual(chart.y + chart.height + 1);
  };
  await lowPoint.hover();
  await expectTooltipInside();
  await page.mouse.move(0, 0);
  await lowPoint.focus();
  await expectTooltipInside();
  await lowPoint.press('Escape');
  await expect(tooltip).toBeHidden();
  await page.locator('button[data-year="2022"]').click();
  await expect(page.locator('#series-context')).toHaveText('ANA 8087 · 2022-01 a 2022-12');
  await expectPoints(page, '8087', 'ndmi_median', '2022-01', '2022-12');
  const gaps = page.locator('#series-chart rect');
  await expect(gaps).toHaveCount(5);
  await expect(page.locator('#rain-chart rect')).toHaveCount(12);
  await page.locator('details.custom-period > summary').click();
  await page.locator('#from-month').fill('2023-03');
  await page.locator('#to-month').fill('2023-07');
  await page.locator('#apply-period').click();
  await expectPoints(page, '8087', 'ndmi_median', '2023-03', '2023-07');
  await expect(page.locator('#rain-chart rect')).toHaveCount(5);
  await expect(page.locator('#coverage-chart button')).toHaveCount(25);
  await page.locator('#from-month').fill('2024-12');
  await page.locator('#to-month').fill('2022-01');
  await page.locator('#apply-period').click();
  await expect(page.locator('#period-error')).toContainText('intervalo válido');
  await expect(page.locator('#series-context')).toHaveText('ANA 8087 · 2023-03 a 2023-07');
  await page.locator('#from-month').fill('2025-01');
  await page.locator('#to-month').fill('2025-12');
  await page.locator('#apply-period').click();
  await expect(page.locator('#period-error')).toContainText('2024-12');
  await expectPoints(page, '8087', 'ndmi_median', '2023-03', '2023-07');
});

test('rainfall and quality distinguish regional context, missing months and limited quality', async ({ page }) => {
  await open(page);
  const expectedRain = filterMonthly(frozen.precipitation, '8087');
  const actualRain = await page.locator('#rain-chart rect').evaluateAll(elements => elements.map(element => ({ month: element.getAttribute('data-month'), value: Number(element.getAttribute('data-value')), unit: element.getAttribute('data-unit') })));
  expect(actualRain).toEqual(expectedRain.map(row => ({ month: row.month, value: row.precip_mm, unit: 'mm' })));
  await expect(page.locator('.rain-note')).toContainText('0,05°');
  await expect(page.locator('.rain-note')).toContainText('após o fim do mês');
  await expect(page.locator('#coverage-chart button')).toHaveCount(180);
  const states = await page.locator('#coverage-chart button').evaluateAll(buttons => buttons.map(button => ({ pivot: button.dataset.pivot, month: button.dataset.month, state: button.dataset.state })));
  for (const state of states) expect(state.state).toBe(coverageState(frozen.quality.find(row => row.pivot_id === state.pivot && row.month === state.month)));
  await page.locator('#coverage-chart button[data-pivot="8087"][data-month="2022-01"]').click();
  await expect(page.locator('#coverage-detail')).toContainText('2022-01');
  await expect(page.locator('#coverage-detail')).toContainText('NDVI —');
  await expect(page.locator('#coverage-detail')).toContainText('0 cenas aceitas');
  const limited = frozen.quality.find(row => coverageState(row) === 'limited');
  expect(limited).toBeTruthy();
  await page.locator(`#coverage-chart button[data-pivot="${limited.pivot_id}"][data-month="${limited.month}"]`).click();
  await expect(page.locator('#selected-id')).toHaveText(limited.pivot_id);
  await expect(page.locator('#coverage-detail')).toContainText(limited.month);
});

test('common-month models show real Ridge metrics and insufficient training explicitly', async ({ page }) => {
  await open(page);
  const ridge = page.locator('#eligibility .eligibility-item').filter({ hasText: 'Ridge harmônica' });
  await expect(ridge).toContainText('Elegível');
  await expect(ridge).toContainText('10 meses');
  const ridgeComparison = page.locator('#comparison-table tbody tr').filter({ hasText: 'Ridge harmônica' });
  await expect(ridgeComparison).toContainText('0,2968');
  await expect(ridgeComparison).toContainText('7/12');
  await expect(page.locator('#comparison-months')).toContainText('2024-03 · 2024-04 · 2024-05 · 2024-07 · 2024-08 · 2024-09 · 2024-10');
  await page.locator('#pivot-select').selectOption('17373');
  await expect(ridge).toContainText('Dados insuficientes para este modelo');
  await expect(ridge).toContainText('12 meses do calendário');
  await expect(ridgeComparison.locator('td').nth(0)).toHaveText('—');
  await expect(ridgeComparison.locator('td').nth(1)).toHaveText('—');
  await page.locator('#comparison-select').selectOption('median-naive');
  await expect(page.locator('#comparison-table tbody tr')).toHaveCount(2);
  await expect(page.locator('#comparison-table')).toContainText('Referências comuns');
  await expect(page.locator('#comparison-months')).toContainText('2024-03');
  const metricsBefore = await page.locator('#comparison-table').innerText();
  await page.locator('button[data-year="2022"]').click();
  await expect.poll(() => page.locator('#comparison-table').innerText()).toBe(metricsBefore);
});

test('events show observed changes, exact endpoints, gaps and provenance', async ({ page }) => {
  await open(page);
  const expected = frozen.events.filter(event => event.pivot_id === '8087' && event.index === 'ndvi_median');
  await expect(page.locator('#events-count')).toHaveText(`${expected.length} mudanças · NDVI`);
  const event = expected[0];
  const first = page.locator('#events-table tbody tr').first();
  await expect(first).toContainText(`${event.from_month} → ${event.to_month}`);
  await expect(first).toContainText(`${format(event.from_value)} → ${format(event.to_value)}`);
  await expect(first.locator('td').nth(4)).toHaveText(String(event.unobserved_months_between));
  await first.getByText('Ver evidência', { exact: true }).click();
  await expect(first).toContainText('events.csv');
  await expect(first).toContainText(manifest.source_package_sha256);
  if (expected.length > 6) {
    await page.locator('#more-events').click();
    await expect(page.locator('#events-table tbody tr')).toHaveCount(expected.length);
  }
  await expect(page.locator('#mudancas')).toContainText('Uma mudança espectral não comprova falha de irrigação.');
});

test('map polygons support keyboard selection, focus controls and optional layer visibility', async ({ page }) => {
  await open(page);
  await page.getByRole('button', { name: 'Enquadrar todos os pivôs', exact: true }).click();
  const polygon = page.getByRole('button', { name: /Selecionar pivô ANA 19997,/ });
  await polygon.focus();
  await polygon.press('Enter');
  await expect(page.locator('#selected-id')).toHaveText('19997');
  await expect(polygon).toHaveAttribute('aria-pressed', 'true');
  await expectPoints(page, '19997', 'ndvi_median');
  await page.getByRole('button', { name: 'Centralizar pivô selecionado', exact: true }).click();
  await page.getByRole('button', { name: 'Ampliar mapa', exact: true }).click();
  await page.getByRole('button', { name: 'Reduzir mapa', exact: true }).click();
  const layer = page.getByRole('checkbox', { name: 'Exibir camada de pivôs ANA' });
  await layer.uncheck();
  await expect(page.locator('#map path[role="button"]')).toHaveCount(0);
  await layer.check();
  await expect(page.locator('#map path[role="button"]')).toHaveCount(5);
  const other = page.getByRole('button', { name: /Selecionar pivô ANA 17382,/ });
  await other.focus(); await other.press('Space');
  await expect(page.locator('#selected-id')).toHaveText('17382');
});

test('project subpath assets, shareable filters and hash navigation survive reload', async ({ page, baseURL }) => {
  await open(page, '?pivot=16708&indice=ndmi&from=2023-01&to=2023-12#modelos');
  await expect(page.locator('#selected-id')).toHaveText('16708');
  await expect(page.getByRole('button', { name: 'NDMI', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expectPoints(page, '16708', 'ndmi_median', '2023-01', '2023-12');
  expect(new URL(page.url()).hash).toBe('#modelos');
  await page.reload();
  await expect(page.locator('#selected-id')).toHaveText('16708');
  await expectPoints(page, '16708', 'ndmi_median', '2023-01', '2023-12');
  await page.getByRole('link', { name: 'Cobertura e qualidade', exact: true }).click();
  expect(new URL(page.url()).hash).toBe('#cobertura');
  const resourceURLs = await page.evaluate(() => performance.getEntriesByType('resource').map(resource => resource.name).filter(url => /^https?:/.test(url)));
  expect(resourceURLs.length).toBeGreaterThan(10);
  expect(resourceURLs.every(url => url.startsWith(baseURL))).toBe(true);
  const manifestResponse = await page.request.get('./data/manifest.json');
  expect(manifestResponse.ok()).toBe(true);
  expect((await manifestResponse.json()).package_sha256).toBe(manifest.package_sha256);
});

test('production runtime remains functional when localhost services, tiles and CDNs are unavailable', async ({ page, baseURL }) => {
  const blocked = [];
  // Block every runtime resource outside the exact deployment directory. In
  // public mode this also makes any localhost or HTTP dependency fail closed.
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    if (/^https?:$/.test(url.protocol) && (!url.href.startsWith(baseURL) || productionDependency(url))) {
      blocked.push(url.href);
      return route.abort('blockedbyclient');
    }
    return route.continue();
  });
  await open(page);
  await page.locator('#pivot-select').selectOption('16708');
  await page.getByRole('button', { name: 'NDMI', exact: true }).click();
  await expectPoints(page, '16708', 'ndmi_median');
  await page.getByRole('button', { name: 'Enquadrar todos os pivôs', exact: true }).click();
  await expect(page.locator('#map path[role="button"]')).toHaveCount(5);
  const assets = await page.evaluate(() => [
    ...[...document.querySelectorAll('script[src]')].map(node => node.src),
    ...[...document.querySelectorAll('link[rel="stylesheet"][href]')].map(node => node.href),
  ]);
  expect(assets.length).toBeGreaterThanOrEqual(2);
  expect(assets.every(url => url.startsWith(`${baseURL}assets/`)), 'JavaScript e CSS são bundles locais dentro do projeto.').toBe(true);
  expect(blocked, 'O aplicativo não tentou usar serviços locais, CDNs, backend ou tiles.').toEqual([]);
  if (new URL(baseURL).protocol === 'https:') {
    expect(new URL(page.url()).origin).toBe('https://altaeir-13.github.io');
    expect(new URL(page.url()).pathname).toBe('/FTL-Final-Project/');
    expect(assets.some(url => /localhost|127\.0\.0\.1|\[::1\]/i.test(url))).toBe(false);
  }
});

test('390px mobile layout stays inside the viewport and all primary interactions work', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  const width = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(width.page).toBeLessThanOrEqual(width.viewport + 1);
  await page.locator('#pivot-select').selectOption('17373');
  await page.getByRole('button', { name: 'NDMI', exact: true }).click();
  await page.locator('button[data-year="2024"]').click();
  await expectPoints(page, '17373', 'ndmi_median', '2024-01', '2024-12');
  await expect(page.locator('#selected-id')).toHaveText('17373');
  await page.getByRole('link', { name: 'Modelos e avaliação', exact: true }).click();
  await expect(page.locator('#eligibility')).toContainText('Dados insuficientes para este modelo');
  const after = await page.evaluate(() => ({ page: document.documentElement.scrollWidth, viewport: innerWidth }));
  expect(after.page).toBeLessThanOrEqual(after.viewport + 1);
});

test('scientific notes meet WCAG text contrast and reduced motion is respected', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page);
  const measurements = await page.evaluate(() => {
    const parse = value => {
      const values = value.match(/[\d.]+/g)?.map(Number);
      if (!values || values.length < 3) throw new Error(`Cor CSS não suportada no teste: ${value}`);
      return [...values.slice(0, 3), values[3] ?? 1];
    };
    const over = (foreground, background) => foreground.slice(0, 3).map((value, index) => value * foreground[3] + background[index] * (1 - foreground[3]));
    const luminance = color => color.map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
    const selectors = ['.rain-note', '.pivot-card .context-note span', '#mudancas .context-note span', '#selected-summary', '.kpi div > span', '.kpi small', '#comparison-table tbody td:nth-of-type(1)', '#comparison-table tbody td:nth-of-type(2)'];
    return selectors.flatMap(selector => [...document.querySelectorAll(selector)].map(element => {
      const ancestors = [];
      for (let node = element; node; node = node.parentElement) ancestors.unshift(node);
      let background = [255, 255, 255];
      const backgroundImages = [], opacities = [];
      for (const node of ancestors) {
        const style = getComputedStyle(node);
        background = over(parse(style.backgroundColor), background);
        if (style.backgroundImage !== 'none') backgroundImages.push(style.backgroundImage);
        if (Number(style.opacity) !== 1) opacities.push(style.opacity);
      }
      const color = over(parse(getComputedStyle(element).color), background);
      const foregroundLuminance = luminance(color), backgroundLuminance = luminance(background);
      const ratio = (Math.max(foregroundLuminance, backgroundLuminance) + .05) / (Math.min(foregroundLuminance, backgroundLuminance) + .05);
      return { selector, text: element.textContent.trim().slice(0, 80), color, background, ratio, backgroundImages, opacities };
    }));
  });
  expect(measurements.length).toBeGreaterThanOrEqual(15);
  for (const measurement of measurements) {
    expect(measurement.backgroundImages, `A medição representativa exige fundo de cor composto: ${measurement.selector}`).toEqual([]);
    expect(measurement.opacities, `A medição representativa exige texto sem opacidade de grupo: ${measurement.selector}`).toEqual([]);
    expect(measurement.ratio, `Contraste insuficiente para ${measurement.selector}: ${measurement.text}; frente ${measurement.color}, fundo ${measurement.background}`).toBeGreaterThanOrEqual(4.5);
  }
  const motion = await page.evaluate(() => ({
    requested: matchMedia('(prefers-reduced-motion: reduce)').matches,
    scrolling: getComputedStyle(document.documentElement).scrollBehavior,
    navigationTransition: getComputedStyle(document.querySelector('.nav-link')).transitionDuration,
    mapTransition: getComputedStyle(document.querySelector('#map path[role="button"]')).transitionDuration,
    navigationAnimation: getComputedStyle(document.querySelector('.nav-link')).animationName,
  }));
  expect(motion).toEqual({ requested: true, scrolling: 'auto', navigationTransition: '0s', mapTransition: '0s', navigationAnimation: 'none' });
});

test('missing mandatory data fails visibly instead of rendering invented values', async ({ page }) => {
  test.info().annotations.push({ type: 'expected-load-failure', description: '404 deliberado em monthly.csv.' });
  await page.route('**/data/**/monthly.csv', route => route.fulfill({ status: 404, contentType: 'text/plain', body: 'Pacote ausente para teste de falha.' }));
  await page.goto('./');
  await expect(page.getByRole('heading', { name: 'Não foi possível abrir o pacote científico.' })).toBeVisible();
  await expect(page.locator('.load-error')).toContainText('HTTP 404');
  await expect(page.locator('#kpi-observations')).toHaveCount(0);
});

test('corrupted scientific bytes fail the browser SHA-256 validation', async ({ page }) => {
  test.info().annotations.push({ type: 'expected-load-failure', description: 'Byte modificado deliberadamente; tamanho preservado.' });
  const original = await readFile(new URL(manifest.files.monthly.path, dataRoot));
  const corrupted = Buffer.from(original);
  corrupted[corrupted.length - 2] = corrupted[corrupted.length - 2] === 97 ? 98 : 97;
  await page.route('**/data/**/monthly.csv', route => route.fulfill({ status: 200, contentType: 'text/csv; charset=utf-8', body: corrupted }));
  await page.goto('./');
  await expect(page.getByRole('heading', { name: 'Não foi possível abrir o pacote científico.' })).toBeVisible();
  await expect(page.locator('.load-error')).toContainText('SHA-256 de monthly');
  await expect(page.locator('#series-chart')).toHaveCount(0);
});
