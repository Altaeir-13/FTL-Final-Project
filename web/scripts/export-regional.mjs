// Explicit scientific export. Production builds consume only the reviewed snapshot.
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import { resolve, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseCSV } from '../src/science.js';
import { sha256 } from './validate-data.mjs';
import { validateRegions } from './validate-regions.mjs';

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const repository = resolve(webRoot, '..');
const selectionRoot = resolve(repository, 'data/regions/selection');
const pilotRoot = resolve(repository, 'data/regions/guadalupe-pi');
const output = resolve(webRoot, 'regions');
const json = async path => JSON.parse(await readFile(path, 'utf8'));
const pick = (row, columns) => Object.fromEntries(columns.filter(key => key in row).map(key => [key, row[key]]));
// Pandas scientific exports use True/False; the public payload uses JSON booleans.
const scientificCSV = text => parseCSV(text, { properties: { query_complete: { type: 'string' } } }).map(row => {
  if ('query_complete' in row && row.query_complete !== null) {
    if (!['True','False','true','false'].includes(row.query_complete)) throw new Error('Booleano científico inválido.');
    row.query_complete = row.query_complete.toLowerCase() === 'true';
  }
  return row;
});
const decision = await json(resolve(selectionRoot, 'decision.json'));
const comparison = await json(resolve(selectionRoot, 'comparison.json'));
const method = await json(resolve(selectionRoot, 'method.json'));
const sample = await json(resolve(selectionRoot, 'sample-2204501.geojson'));
const fields = ['UF','name','code','ana_count','eligible_count','area_ha','invalid_or_repaired','centroid_mismatches','boundary_crossings','sample_FIDs','cluster_radius_m','caxias_km','usable_dates','usable_months','tiles','eligible','scores'];
const evidence = {
  region_id: 'guadalupe-pi',
  selection: { decided_at_utc: decision.decided_at_utc, winner: pick(decision.winner, fields),
    comparison: comparison.map(row => pick(row, fields)), method,
    source: decision.source, decision_sha256: sha256(await readFile(resolve(selectionRoot, 'decision.json'))),
    inventory_sha256: sha256(await readFile(resolve(selectionRoot, 'inventory.geojson'))),
    decision_inventory_sha256: decision.inventory_sha256,
    reference: { label: 'Sede municipal de Caxias, MA', longitude: -43.358539429, latitude: -4.86167498984,
      role: 'territorial_motivation', source: 'https://portal1.snirh.gov.br/arcgis/rest/services/DADOSABERTOS/Sede_Municipais/MapServer/0' } },
  pivots: { type: 'FeatureCollection', features: sample.features.map(feature => ({ type: 'Feature', id: feature.properties.pivot_id,
    properties: pick(feature.properties, ['FID','pivot_id','region_id','UF','MUNIC_CD','MUNIC_NOME','area_ha']), geometry: feature.geometry })) },
  pilot: null,
};
let status = 'territorial_selection';
const images = [];
if (process.argv.includes('--pilot')) {
  const summary = await json(resolve(pilotRoot, 'curated/v1/summary.json'));
  const offline = await json(resolve(pilotRoot, 'offline-verification.json'));
  const execution = await json(resolve(pilotRoot, 'execution.json'));
  const observationFields = ['pivot_id','date','month','scene_id','ndvi_median','ndmi_median','valid_pixel_pct','provider','sentinel_source','collection','processing_baseline','radiometric_method','acquisition_key'];
  const monthlyFields = ['pivot_id','month','ndvi_median','ndmi_median','n_accepted_scenes','n_attempted_scenes','valid_pixel_pct_min','valid_pixel_pct_median','monthly_status','batch_status','query_complete','precip_mm','precip_status','chirps_source','chirps_provider','chirps_url','chirps_resolution_deg','chirps_cell_lon','chirps_cell_lat'];
  const observations = scientificCSV(await readFile(resolve(pilotRoot, 'curated/v1/observations.csv'), 'utf8')).map(row => pick(row, observationFields));
  const attempts = scientificCSV(await readFile(resolve(pilotRoot, 'curated/v1/attempts.csv'), 'utf8')).map(row => pick(row, [...observationFields, 'status']));
  const monthly = scientificCSV(await readFile(resolve(pilotRoot, 'curated/v1/monthly.csv'), 'utf8')).map(row => pick(row, monthlyFields));
  const scenes = [];
  for (const month of summary.target_months) {
    const report = await json(resolve(pilotRoot, 'batches', month, 'radiometry.json'));
    scenes.push(...report.products.map(product => ({ month, ...pick(product, ['scene_id','collection','provider','product','processing_baseline','method','xml_sha256','calibration','bands']) })));
  }
  evidence.pilot = { summary, offline, observations, attempts, monthly, scenes,
    execution: pick(execution, ['transferred_bytes','http_requests','stored_bytes','new_run_transfer_bytes','new_run_stored_bytes','failures']) };
  status = 'exploratory_portability';
  const comparisonRoot = resolve(repository, 'docs/evidencias/guadalupe-pi/comparison');
  const provenance = await json(resolve(comparisonRoot, 'provenance.json'));
  evidence.comparison = provenance;
  for (const scene of provenance.scenes) {
    if (!/^false-colour-202[34]-\d{2}-\d{2}\.png$/.test(scene.image)) throw new Error('Nome de imagem regional inválido.');
    const imageBytes = await readFile(resolve(comparisonRoot, scene.image));
    if (sha256(imageBytes) !== scene.image_sha256) throw new Error('Imagem diverge da proveniência.');
    images.push({ path: `images/${scene.image}`, sha256: scene.image_sha256, bytes: imageBytes.length, date: scene.date, scene_id: scene.scene_id });
    await mkdir(resolve(output, 'images'), { recursive: true });
    await writeFile(resolve(output, 'images', scene.image), imageBytes);
  }
}
const bytes = Buffer.from(`${JSON.stringify(evidence, null, 2)}\n`);
const hash = sha256(bytes);
const relative = `packages/${hash}/regional.json`;
const catalog = { catalog_version: '1.0.0', reference_date: '2026-11-15',
  paracatu: { id: 'paracatu-mg', label: 'Paracatu, MG', status: 'completed', contract_version: '1.0.0',
    dataset_version: '2022_2024_recovery_v1', manifest_path: '../data/manifest.json',
    package_sha256: '7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d' },
  regional: { id: 'guadalupe-pi', label: 'Guadalupe, PI', status, version: '2023_2024_exploratory_v1',
    package: { path: relative, bytes: bytes.length, sha256: hash }, images } };
let previous;
try { previous = await json(resolve(output, 'catalog.json')); } catch (error) { if (error.code !== 'ENOENT') throw error; }
await mkdir(dirname(resolve(output, relative)), { recursive: true });
await writeFile(resolve(output, relative), bytes);
await writeFile(resolve(output, 'catalog.json'), `${JSON.stringify(catalog, null, 2)}\n`);
if (previous?.regional?.package?.sha256 !== hash && /^[a-f0-9]{64}$/.test(previous?.regional?.package?.sha256 ?? '')) {
  const old = resolve(output, 'packages', previous.regional.package.sha256);
  if (!old.startsWith(`${resolve(repository, 'web/regions/packages')}${sep}`)) throw new Error('Diretório antigo fora do snapshot regional.');
  await rm(old, { recursive: true });
}
await validateRegions(output);
console.log(`Snapshot regional ${status}: ${hash}, ${bytes.length} bytes.`);
