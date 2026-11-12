import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseCSV, filterMonthly, coverageState, seriesSegments, commonComparison } from '../src/science.js';

test('CSV preserves identifier zeros, baseline precision, null values and quoted fields', () => {
  const [row] = parseCSV('pivot_id,processing_baseline,ndvi_median,query_complete,scene_id,precip_mm\n0007,05.10,,true,"scene,""A""",0\n');
  assert.equal(row.pivot_id, '0007'); assert.equal(row.processing_baseline, '05.10');
  assert.equal(row.ndvi_median, null); assert.equal(row.query_complete, true);
  assert.equal(row.scene_id, 'scene,"A"'); assert.equal(row.precip_mm, 0);
});

test('CSV schema drives typing and accepts multiline values', () => {
  const [row] = parseCSV('pivot_id,n_accepted_scenes,note\r\n08087,2,"first\nsecond"\r\n', { properties: { pivot_id: { type: 'string' }, n_accepted_scenes: { type: 'integer' } } });
  assert.equal(row.pivot_id, '08087'); assert.equal(row.n_accepted_scenes, 2); assert.equal(row.note, 'first\nsecond');
  assert.throws(() => parseCSV('a,b\n1'), /campos/);
  assert.throws(() => parseCSV('a\n"broken'), /fechado/);
  assert.throws(() => parseCSV('query_complete\nmaybe'), /Booleano/);
});

test('period and pivot filtering is inclusive and preserves missing observations', () => {
  const rows = [{ pivot_id: '8087', month: '2022-02', ndvi_median: null }, { pivot_id: '8087', month: '2022-01' }, { pivot_id: '16708', month: '2022-02' }];
  assert.deepEqual(filterMonthly(rows, '8087', '2022-02', '2022-03'), [rows[0]]);
  assert.equal(filterMonthly(rows, '8087', '2023-01', '2022-01').length, 0);
  assert.equal(rows[0].ndvi_median, null);
});

test('quality distinguishes limited observation, absence and incomplete acquisition', () => {
  const good = { monthly_status: 'ok', n_accepted_scenes: 2, query_complete: true, batch_status: 'complete', valid_pixel_pct_min: 100 };
  assert.equal(coverageState(good), 'valid');
  assert.equal(coverageState({ ...good, valid_pixel_pct_min: 79 }), 'limited');
  assert.equal(coverageState({ ...good, n_accepted_scenes: 0, quality_review: true }), 'missing');
  assert.equal(coverageState({ ...good, query_complete: false }), 'incomplete');
});

test('series never connects gaps, including absent rows and skipped calendar months', () => {
  const make = (month, value) => ({ month, ndvi_median: value, monthly_status: value == null ? 'no_accepted_observation' : 'ok' });
  const segments = seriesSegments([make('2022-01', .3), make('2022-02', .4), make('2022-03', null), make('2022-04', .5), make('2022-07', .2)], 'ndvi_median');
  assert.deepEqual(segments.map(segment => segment.map(row => row.month)), [['2022-01', '2022-02'], ['2022-04'], ['2022-07']]);
});

test('common model comparison requires identical months and never fills ineligible metrics', () => {
  const months = ['2024-03', '2024-04', '2024-05', '2024-07', '2024-08', '2024-09', '2024-10'];
  const group = 'calendar_month_median__vs__harmonic_ridge';
  const base = { pivot_id: '8087', target: 'ndvi_median', comparison: group, common_months: JSON.stringify(months), status: 'ok', n_common_months: 7, mae: .3, rmse: .4 };
  const data = [{ ...base, method: 'calendar_month_median' }, { ...base, method: 'harmonic_ridge' }];
  assert.equal(commonComparison(data, '8087', 'ndvi_median', group).eligible, true);
  assert.equal(commonComparison([{ ...base, mae: null, rmse: null, status: 'insufficient_common_validation_months' }], '8087', 'ndvi_median', group).eligible, false);
  assert.equal(commonComparison([data[0], { ...data[1], common_months: JSON.stringify(months.slice(1)) }], '8087', 'ndvi_median', group).eligible, false);
  assert.equal(commonComparison(data.slice(0, 1), '8087', 'ndvi_median', group).eligible, false);
  assert.equal(commonComparison(data, '17382', 'ndvi_median', group).eligible, false);
});

test('real frozen package parsing, chart data and model eligibility remain faithful', async () => {
  const root = new URL('../data/', import.meta.url);
  const manifest = JSON.parse(await readFile(new URL('manifest.json', root), 'utf8'));
  const monthly = parseCSV(await readFile(new URL(manifest.files.monthly.path, root), 'utf8'));
  const observations = parseCSV(await readFile(new URL(manifest.files.observations.path, root), 'utf8'));
  const models = parseCSV(await readFile(new URL(manifest.files.models.path, root), 'utf8'));
  assert.equal(monthly.length, 180); assert.equal(observations.length, 256);
  assert.equal(monthly.filter(row => row.monthly_status === 'ok').length, 141);
  const selected = filterMonthly(monthly, '8087', '2022-01', '2024-12');
  assert.equal(selected.length, 36);
  assert.equal(seriesSegments(selected, 'ndvi_median').flat().length, 29);
  assert.equal(selected.find(row => row.month === '2022-01').ndvi_median, null);
  for (const pivotId of ['17373', '17382', '19997']) {
    const ridge = models.filter(row => row.pivot_id === pivotId && row.method === 'harmonic_ridge');
    assert.equal(ridge.length, 2); assert.ok(ridge.every(row => row.mae === null && row.rmse === null));
  }
  const metrics = parseCSV(await readFile(new URL(manifest.files.common_month_metrics.path, root), 'utf8'));
  const result = commonComparison(metrics, '8087', 'ndvi_median', ['calendar_month_median', 'harmonic_ridge', 'previous_year_same_calendar_month']);
  assert.equal(result.eligible, true);
  assert.deepEqual(result.months, ['2024-03', '2024-04', '2024-05', '2024-07', '2024-08', '2024-09', '2024-10']);
  assert.ok(Math.abs(result.rows.find(row => row.method === 'harmonic_ridge').mae - 0.296783) < 1e-6);
});

test('rendered spectral points, gaps and rainfall correspond to source rows', async () => {
  const { renderSeries, renderPrecipitation, renderCoverage } = await import('../src/charts.js');
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; this.style = {}; this.dataset = {}; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    addEventListener() {}
    all(tag) { return this.children.filter(node => node instanceof Element).flatMap(node => [...(node.tag === tag ? [node] : []), ...node.all(tag)]); }
  }
  const previous = globalThis.document;
  globalThis.document = { createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag), createTextNode: text => ({ textContent: text }) };
  try {
    const container = new Element('div');
    const make = (month, value, precip) => ({ pivot_id: '0007', month, monthly_status: value == null ? 'no_accepted_observation' : 'ok', ndvi_median: value, n_accepted_scenes: value == null ? 0 : 1, valid_pixel_pct_min: 100, query_complete: true, batch_status: 'complete', precip_status: precip == null ? 'missing' : 'ok', precip_mm: precip });
    const rows = [make('2024-01', .12, 32), make('2024-02', null, null), make('2024-03', .5, 0)];
    renderSeries(container, rows, 'ndvi_median');
    assert.deepEqual(container.all('circle').map(point => point.attributes['data-value']), ['0.12', '0.5']);
    assert.equal(container.all('path').length, 0, 'Dois pontos separados por ausência não recebem uma linha.');
    container.clientWidth = 330;
    renderPrecipitation(container, rows);
    assert.equal(container.all('svg')[0].attributes.viewBox, '0 0 330 190', 'O gráfico usa a largura real do cartão, preservando o tamanho dos rótulos.');
    assert.ok(container.all('text').every(label => Number(label.attributes['font-size']) >= 10), 'Rótulos científicos usam ao menos 10px.');
    const bars = container.all('rect');
    assert.deepEqual(bars.map(bar => bar.attributes['data-value']), ['32', '', '0']);
    assert.equal(bars[1].attributes.height, '120', 'Ausência recebe marcador próprio.');
    assert.equal(bars[2].attributes.height, '0', 'Zero real permanece zero.');
    renderCoverage(container, rows, [], ['0007'], '2024-01', '2024-03');
    assert.deepEqual(container.all('button').map(button => button.dataset.state), ['valid', 'missing', 'valid']);
  } finally { globalThis.document = previous; }
});
