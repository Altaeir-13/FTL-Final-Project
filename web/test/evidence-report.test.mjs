import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseCSV } from '../src/science.js';
import { createStudies, resolveSelection, compareSelection } from '../src/investigation-data.js';
import { AQUACLIMA_VERSION, createEvidenceSnapshot, renderEvidenceReport } from '../src/evidence-report.js';

const loadJSON = async path => JSON.parse(await readFile(new URL(path, import.meta.url), 'utf8'));
const manifest = await loadJSON('../data/manifest.json');
const paracatu = { manifest };
for (const name of ['pivots', 'provenance', 'monthly', 'observations', 'quality']) {
  const text = await readFile(new URL(`../data/${manifest.files[name].path}`, import.meta.url), 'utf8');
  paracatu[name] = manifest.files[name].format === 'csv' ? parseCSV(text) : JSON.parse(text);
}
const catalog = await loadJSON('../regions/catalog.json');
const evidence = await loadJSON(`../regions/${catalog.regional.package.path}`);
const studies = createStudies(paracatu, { catalog, evidence, images: catalog.regional.images });
const comparison = (region = 'paracatu-mg', extra = {}) => compareSelection(studies, resolveSelection(studies, { region, ...extra }));
const now = '2026-11-17T04:30:00.000Z';

test('evidence report preserves real selection, values, signed deltas and complete package identity', async () => {
  const source = comparison();
  const snapshot = await createEvidenceSnapshot(source, now);
  const html = renderEvidenceReport(snapshot);
  assert.match(html, /Ficha de Evidências — AquaClima/);
  assert.ok(html.includes(AQUACLIMA_VERSION));
  assert.ok(html.includes(source.study.version));
  assert.ok(html.includes(source.study.packageHash));
  assert.ok(html.includes(String(source.a.ndvi_median).replace('.', ',')));
  assert.ok(html.includes(String(source.b.ndvi_median).replace('.', ',')));
  assert.ok(html.includes(String(source.b.ndvi_median - source.a.ndvi_median).replace('.', ',')));
  for (const scene of source.a.scenes) assert.ok(html.includes(scene.scene_id));
  assert.ok(html.includes('Estudo científico concluído'));
  assert.ok(html.includes(source.a.dates[0]));
  assert.match(html, /mediana das medianas espaciais/);
  assert.match(html, /Gerada em \(UTC\)/);
  assert.match(snapshot.investigationId, /^AQ-[a-f0-9]{64}$/);
  assert.equal(snapshot.generatedAt, now);
});

test('report freezes the selection independently from later UI mutations and print time', async () => {
  const source = comparison();
  const first = await createEvidenceSnapshot(source, now);
  const original = first.a.ndvi_median;
  const second = await createEvidenceSnapshot(source, '2026-11-18T04:30:00Z');
  assert.equal(first.investigationId, second.investigationId);
  source.a.ndvi_median = -0.999;
  source.a.scenes[0].scene_id = 'changed';
  source.study.label = 'changed';
  assert.equal(first.a.ndvi_median, original);
  assert.notEqual(first.a.scenes[0].scene_id, 'changed');
  assert.notEqual(first.study.label, 'changed');
  assert.ok(Object.isFrozen(first));
  assert.ok(Object.isFrozen(first.a.scenes[0]));
  assert.throws(() => { first.a.ndvi_median = 5; }, TypeError);
});

test('the two verified Guadalupe images appear only for their selected observations', async () => {
  const source = comparison('guadalupe-pi', { a: '2023-07-18', b: '2024-07-22' });
  const html = renderEvidenceReport(await createEvidenceSnapshot(source, now));
  assert.equal((html.match(/<img /g) || []).length, 2);
  assert.ok(html.includes('2023-07-18'));
  assert.ok(html.includes('2024-07-22'));
  assert.ok(html.includes('grupo de cinco pivôs ANA'));
  assert.ok(html.includes(catalog.regional.images[0].sha256));
  const absent = comparison('guadalupe-pi', { a: '2023-01-29', b: '2024-07-22' });
  const absentHtml = renderEvidenceReport(await createEvidenceSnapshot(absent, now));
  assert.equal((absentHtml.match(/<img /g) || []).length, 1);
  assert.match(absentHtml, /Imagem comparativa não disponível para esta observação\./);
  const monthlyHtml = renderEvidenceReport(await createEvidenceSnapshot(comparison(), now));
  assert.equal((monthlyHtml.match(/<img /g) || []).length, 0);
});

test('report rejects cross-date or remote images and escapes text and provenance', async () => {
  const source = comparison('guadalupe-pi', { a: '2023-07-18', b: '2024-07-22' });
  source.a.image.date = '2023-01-29';
  source.b.image.url = 'https://external.invalid/image.png';
  source.study.label = '<script>alert(1)</script>';
  source.a.scenes[0].source = 'javascript:alert(2)';
  source.a.scenes[0].method = '<img src=x onerror=alert(3)>';
  const html = renderEvidenceReport(await createEvidenceSnapshot(source, now));
  assert.doesNotMatch(html, /<script|<img |href="javascript:/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.match(html, /&lt;img src=x onerror=alert\(3\)&gt;/);
  assert.doesNotMatch(html, /external\.invalid/);
});

test('missing values remain explicit, zero rain is retained, and invalid snapshots fail', async () => {
  const source = comparison();
  source.a.ndmi_median = null;
  source.delta_ndmi = null;
  source.a.precip_status = 'ok';
  source.a.precip_mm = 0;
  source.b.precip_status = 'missing';
  source.b.precip_mm = null;
  source.a.valid_pixel_pct = null;
  const html = renderEvidenceReport(await createEvidenceSnapshot(source, now));
  assert.match(html, /<td>0<\/td><td>Ausente<\/td>/);
  assert.match(html, /NDMI · adimensional<\/th><td>Ausente<\/td>/);
  assert.doesNotMatch(html, /NaN|undefined/);
  await assert.rejects(() => createEvidenceSnapshot({ ...source, b: source.a }, now), /distintas/);
  await assert.rejects(() => createEvidenceSnapshot(source, 'invalid'), /Data de geração inválida/);
  await assert.rejects(() => createEvidenceSnapshot({ ...source, study: { ...source.study, packageHash: 'bad' } }, now), /SHA-256/);
});
