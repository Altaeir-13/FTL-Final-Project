import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseCSV } from '../src/science.js';
import { createStudies, availableObservations, imageForObservation, resolveSelection, compareSelection, canCompareObservations, signedDelta, investigationId, parseInvestigationURL, serializeInvestigationURL } from '../src/investigation-data.js';

const dataRoot = new URL('../data/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', dataRoot), 'utf8'));
const schemas = JSON.parse(await readFile(new URL(manifest.files.schemas.path, dataRoot), 'utf8'));
const paracatu = { manifest };
for (const name of ['monthly', 'observations', 'quality', 'pivots', 'provenance']) {
  const text = await readFile(new URL(manifest.files[name].path, dataRoot), 'utf8');
  paracatu[name] = manifest.files[name].format === 'csv' ? parseCSV(text, schemas.$defs[name]) : JSON.parse(text);
}
const regionalRoot = new URL('../regions/', import.meta.url);
const catalog = JSON.parse(await readFile(new URL('catalog.json', regionalRoot), 'utf8'));
const evidence = JSON.parse(await readFile(new URL(catalog.regional.package.path, regionalRoot), 'utf8'));
const regional = { catalog, evidence, images: catalog.regional.images.map(image => ({ ...image, url: `./regions/${image.path}` })) };
const studies = createStudies(paracatu, regional);
const monthlyStudy = studies[0];
const sceneStudy = studies[1];
const select = input => resolveSelection(studies, input);

test('territories expose actual separate evidence and no Caxias observations', () => {
  assert.deepEqual(studies.map(study => study.id), ['paracatu-mg', 'guadalupe-pi']);
  assert.equal(monthlyStudy.version, '2022_2024_recovery_v1');
  assert.equal(monthlyStudy.observations.length, 256);
  assert.equal(sceneStudy.observations.length, 29);
  assert.match(sceneStudy.status, /sem modelo regional validado/);
  assert.equal(studies.find(study => study.id === 'caxias-ma'), undefined);
  const selection = select({ region: 'caxias-ma', pivot: 'PI:5795' });
  assert.equal(selection.region, 'paracatu-mg');
  assert.equal(selection.pivot, '8087');
  assert.equal(selection.warnings.length, 2);
  assert.equal(createStudies(paracatu).length, 1);
});

test('monthly selection only offers accepted published aggregates and effective scene dates separately', () => {
  const options = availableObservations(monthlyStudy, '8087');
  assert.equal(options.length, 29);
  assert.ok(options.every(row => row.granularity === 'month' && row.date === null && row.dates.length > 0));
  assert.equal(options.find(row => row.id === '2022-01'), undefined);
  const july = options.find(row => row.id === '2023-07');
  const source = paracatu.monthly.find(row => row.pivot_id === '8087' && row.month === '2023-07');
  assert.equal(july.ndvi_median, source.ndvi_median);
  assert.equal(july.ndmi_median, source.ndmi_median);
  assert.equal(july.valid_pixel_pct, source.valid_pixel_pct_min);
  assert.deepEqual(july.dates, [...new Set(paracatu.observations.filter(row => row.pivot_id === '8087' && row.month === source.month).map(row => row.date))].sort());
  assert.equal(july.image, null);
});

test('regional selection uses actual accepted scenes and never offers a rejected date', () => {
  const rows = availableObservations(sceneStudy, 'PI:5802');
  assert.equal(rows.length, 5);
  assert.ok(rows.every(row => row.granularity === 'scene' && row.date === row.id && row.scenes.length === 1));
  assert.equal(rows.find(row => row.date === '2024-03-24'), undefined);
  assert.deepEqual(availableObservations(sceneStudy, '8087'), []);
  assert.deepEqual(availableObservations(monthlyStudy, 'PI:5795'), []);
});

test('invalid pivot, missing observations and identical selections resolve only to real distinct records', () => {
  const fixed = select({ region: 'guadalupe-pi', pivot: '8087', a: '2025-01-01', b: '2025-01-01', index: '<script>' });
  assert.equal(fixed.pivot, 'PI:5795');
  assert.equal(fixed.index, 'ndvi');
  assert.notEqual(fixed.a, fixed.b);
  assert.equal(fixed.warnings.length, 3);
  const duplicate = select({ region: 'guadalupe-pi', pivot: 'PI:5795', a: '2023-07-18', b: '2023-07-18' });
  assert.notEqual(duplicate.a, duplicate.b);
  assert.throws(() => compareSelection(studies, { ...duplicate, b: duplicate.a }), /distintas/);
  assert.throws(() => compareSelection(studies, { ...duplicate, pivot: '8087' }), /pivô inválido/);
  assert.throws(() => compareSelection(studies, { ...duplicate, a: '2024-01-01' }), /distintas/);
});

test('signed deltas match exact public values, preserve reversal and are never percentages', () => {
  const selection = select({ region: 'guadalupe-pi', pivot: 'PI:5795', a: '2023-07-18', b: '2024-07-22' });
  const result = compareSelection(studies, selection);
  const a = evidence.pilot.observations.find(row => row.pivot_id === selection.pivot && row.date === selection.a);
  const b = evidence.pilot.observations.find(row => row.pivot_id === selection.pivot && row.date === selection.b);
  assert.equal(result.a.ndvi_median, a.ndvi_median);
  assert.equal(result.b.ndmi_median, b.ndmi_median);
  assert.equal(result.delta_ndvi, b.ndvi_median - a.ndvi_median);
  assert.equal(result.delta_ndmi, b.ndmi_median - a.ndmi_median);
  const reverse = compareSelection(studies, { ...selection, a: selection.b, b: selection.a });
  assert.equal(reverse.delta_ndvi, -result.delta_ndvi);
  assert.equal(reverse.delta_ndmi, -result.delta_ndmi);
  assert.equal(result.interval.calendarMonths, 12);
  assert.equal(result.interval.days, 370);
  assert.equal(result.interval.unobservedMonths.length, 9);
  assert.match(result.synthesis, /B − A/);
  assert.match(result.synthesis, /unidade adimensional/);
  assert.ok(result.limitations.some(text => text.includes('não permitem atribuir uma causa')));
});

test('null deltas, unavailable precipitation and true zero are preserved explicitly', () => {
  assert.equal(signedDelta(null, .4), null);
  assert.equal(signedDelta(.4, undefined), null);
  assert.equal(signedDelta(0, .4), .4);
  const copy = structuredClone(studies);
  const first = copy[1].observations.find(row => row.pivot_id === 'PI:5795' && row.date === '2023-07-18');
  first.ndmi_median = null;
  const month = copy[1].monthly.find(row => row.pivot_id === first.pivot_id && row.month === first.month);
  month.precip_status = 'not_queried'; month.precip_mm = null;
  const secondMonth = copy[1].monthly.find(row => row.pivot_id === first.pivot_id && row.month === '2024-07');
  secondMonth.precip_status = 'ok'; secondMonth.precip_mm = 0;
  const result = compareSelection(copy, resolveSelection(copy, { region: 'guadalupe-pi', pivot: first.pivot_id, a: first.date, b: '2024-07-22' }));
  assert.equal(result.a.ndmi_median, null);
  assert.equal(result.delta_ndmi, null);
  assert.equal(result.a.precip_mm, null);
  assert.equal(result.b.precip_mm, 0);
  assert.match(result.synthesis, /diferença indisponível/);
  assert.match(result.synthesis, /indisponível\/0,00 mm/);
});

test('monthly calendar gaps and no invented exact monthly interval are explicit', () => {
  const result = compareSelection(studies, select({ region: 'paracatu-mg', pivot: '8087', a: '2022-03', b: '2022-07' }));
  assert.equal(result.interval.days, null);
  assert.equal(result.interval.calendarMonths, 4);
  assert.deepEqual(result.interval.unobservedMonths, ['2022-06']);
  assert.equal(result.pivot.observedMonths, 29);
  assert.equal(result.pivot.calendarMonths, 36);
  assert.equal(result.pivot.area_ha, paracatu.pivots.features.find(feature => feature.properties.pivot_id === '8087').properties.area_ha);
  assert.equal(result.pivot.acceptedObservations, paracatu.observations.filter(row => row.pivot_id === '8087').length);
});

test('provenance retains exact independent calibration and scene identifiers from source packages', () => {
  const result = compareSelection(studies, select({ region: 'guadalupe-pi', pivot: 'PI:5795', a: '2023-07-18', b: '2024-07-22' }));
  const source = evidence.pilot.scenes.find(row => row.scene_id === result.a.scenes[0].scene_id);
  assert.equal(result.a.scenes[0].calibration_sha256, source.xml_sha256);
  assert.equal(result.a.scenes[0].processing_baseline, '05.09');
  assert.equal(result.a.scenes[0].method, source.method);
  assert.equal(result.a.scenes[0].product, source.product);
  assert.equal(result.a.scenes[0].calibration_formula, source.calibration.formula);
  assert.equal(result.a.scenes[0].quantification_value, source.calibration.quantification_value);
  assert.equal(result.study.sourceFiles.precipitation, evidence.pilot.summary.files.precipitation.sha256);
  assert.equal(result.a.precipitation.raster_sha256, null, 'The public package does not claim a per-raster precipitation hash.');
  const monthly = compareSelection(studies, select({ pivot: '8087', a: '2022-07', b: '2023-07' }));
  for (const scene of monthly.a.scenes) {
    const observation = paracatu.observations.find(row => row.pivot_id === '8087' && row.scene_id === scene.scene_id);
    assert.equal(scene.calibration_sha256, observation.calibration_sha256);
    assert.equal(scene.source, observation.sentinel_source);
    assert.equal(scene.indices_sha256, observation.indices_sha256);
    assert.equal(scene.pivots_sha256, observation.pivots_sha256);
  }
  assert.equal(monthly.a.precipitation.source, paracatu.monthly.find(row => row.pivot_id === '8087' && row.month === '2022-07').chirps_source);
  assert.equal(monthly.a.precipitation.product, 'CHIRPS v3.0 Final monthly');
  assert.equal(monthly.study.sourceFiles.monthly, manifest.files.monthly.sha256);
});

test('multiple scenes acquired on the same day remain distinct IDs but cannot be compared as different dates', () => {
  const copy = structuredClone(sceneStudy);
  const original = copy.observations.find(row => row.pivot_id === 'PI:5795' && row.date === '2023-07-18');
  copy.observations.push({ ...original, scene_id: `${original.scene_id}_second` });
  const sameDay = availableObservations(copy, original.pivot_id).filter(row => row.date === original.date);
  assert.equal(sameDay.length, 2);
  assert.notEqual(sameDay[0].id, sameDay[1].id);
  assert.equal(canCompareObservations(sameDay[0], sameDay[1]), false);
  const fixed = resolveSelection([copy], { region: copy.id, pivot: original.pivot_id, a: sameDay[0].id, b: sameDay[1].id });
  assert.ok(!fixed.b.startsWith(original.date));
  assert.throws(() => compareSelection([copy], { ...fixed, a: sameDay[0].id, b: sameDay[1].id }), /distintas/);
  assert.equal(canCompareObservations(sameDay[0], availableObservations(monthlyStudy, '8087')[0]), false);
});

test('images require exact real date, scene and region, and retain whole-area context', () => {
  const rows = availableObservations(sceneStudy, 'PI:5795');
  assert.deepEqual(rows.filter(row => row.image).map(row => row.date), ['2023-07-18', '2024-07-22']);
  assert.equal(rows.find(row => row.date === '2023-01-29').image, null);
  const july = evidence.pilot.observations.find(row => row.pivot_id === 'PI:5795' && row.date === '2023-07-18');
  const image = imageForObservation(sceneStudy, 'PI:5795', july);
  assert.equal(image.sha256, catalog.regional.images[0].sha256);
  assert.match(image.context, /cinco pivôs/);
  assert.equal(imageForObservation(monthlyStudy, '8087', july), null);
  assert.equal(imageForObservation(sceneStudy, '8087', july), null);
  assert.equal(imageForObservation(sceneStudy, 'PI:5795', { ...july, date: '2023-01-29' }), null);
  const corrupt = structuredClone(sceneStudy); corrupt.images[0].sha256 = '0'.repeat(64);
  assert.equal(imageForObservation(corrupt, 'PI:5795', july), null);
});

test('deterministic scientific identity ignores print time and changes with relevant selection or package', async () => {
  const snapshot = compareSelection(studies, select({ region: 'guadalupe-pi', pivot: 'PI:5795', a: '2023-07-18', b: '2024-07-22' }));
  const before = JSON.stringify(snapshot);
  const first = await investigationId(snapshot);
  assert.match(first, /^AQ-[a-f0-9]{64}$/);
  assert.equal(first, await investigationId({ ...snapshot, generatedAt: '2030-01-01' }));
  const reverse = structuredClone(snapshot); [reverse.a, reverse.b] = [reverse.b, reverse.a];
  assert.notEqual(first, await investigationId(reverse));
  const changed = structuredClone(snapshot); changed.study.packageHash = '0'.repeat(64);
  assert.notEqual(first, await investigationId(changed));
  const index = structuredClone(snapshot); index.parameters.index = 'ndmi';
  assert.notEqual(first, await investigationId(index));
  assert.equal(JSON.stringify(snapshot), before);
});

test('investigation URL round trip retains exact selection, package and legacy period', () => {
  const selection = select({ region: 'guadalupe-pi', pivot: 'PI:5802', a: '2023-07-18', b: '2024-07-22', index: 'ndmi' });
  const serialized = serializeInvestigationURL(selection, '?from=2023-01&to=2024-12&secret=remove-me');
  const parsed = parseInvestigationURL(serialized, studies);
  for (const key of ['region', 'pivot', 'a', 'b', 'index', 'section', 'package']) assert.equal(parsed[key], selection[key]);
  assert.deepEqual(parsed.warnings, []);
  const params = new URLSearchParams(serialized);
  assert.equal(params.get('from'), '2023-01');
  assert.equal(params.get('to'), '2024-12');
  assert.equal(params.has('secret'), false);
  const old = parseInvestigationURL('?pivot=16708&indice=ndmi&from=2023-01&to=2023-12', studies);
  assert.equal(old.region, 'paracatu-mg');
  assert.equal(old.pivot, '16708');
  assert.equal(old.index, 'ndmi');
});

test('invalid URL input is bounded to actual observations and a different scientific package blocks comparison', () => {
  const parsed = parseInvestigationURL('?region=%3Cscript%3E&pivot=PI%3A5795&a=absent&b=absent&indice=javascript%3Aalert(1)', studies);
  assert.equal(parsed.region, 'paracatu-mg');
  assert.equal(parsed.pivot, '8087');
  assert.notEqual(parsed.a, parsed.b);
  assert.equal(parsed.index, 'ndvi');
  const mismatch = parseInvestigationURL('?region=guadalupe-pi&package=' + '0'.repeat(64), studies);
  assert.equal(mismatch.packageMismatch, true);
  assert.ok(mismatch.warnings.some(warning => warning.includes('comparação está bloqueada')));
  assert.throws(() => compareSelection(studies, mismatch), /pacote do link/);
});

test('regional isolation cannot be bypassed through construction or a valid-date URL', () => {
  const copy = structuredClone(regional); copy.evidence.pilot.observations[0].pivot_id = '8087';
  assert.throws(() => createStudies(paracatu, copy), /mistura de dados/);
  const otherPackage = structuredClone(regional); otherPackage.catalog.paracatu.package_sha256 = '0'.repeat(64);
  assert.throws(() => createStudies(paracatu, otherPackage), /referência de Paracatu/);
  const selection = select({ region: 'paracatu-mg', pivot: 'PI:5795', a: '2023-07-18', b: '2024-07-22' });
  assert.equal(selection.pivot, '8087');
  assert.match(selection.a, /^\d{4}-\d{2}$/);
  const source = JSON.stringify({ paracatu, regional });
  compareSelection(studies, select({ region: 'guadalupe-pi', pivot: 'PI:5795' }));
  assert.equal(JSON.stringify({ paracatu, regional }), source);
});
