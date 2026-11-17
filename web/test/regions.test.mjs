import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdir, mkdtemp, cp, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateRegions } from '../scripts/validate-regions.mjs';
import { validateRegionalCatalog, validateRegionalEvidence, loadRegions } from '../src/regions.js';
import { eventContext } from '../src/science.js';

const root = fileURLToPath(new URL('../regions/', import.meta.url));
const snapshot = await validateRegions(root);
const reviewRoot = resolve(root, '../../.local-review');

test('independent regional snapshot preserves actual counts, rejected attempt and offline provenance', () => {
  const { evidence, catalog } = snapshot;
  assert.equal(catalog.regional.status, 'exploratory_portability');
  assert.equal(evidence.selection.winner.ana_count, 12);
  assert.equal(evidence.pilot.observations.length, 29);
  assert.equal(evidence.pilot.attempts.length, 30);
  assert.equal(evidence.pilot.monthly.length, 115);
  assert.equal(evidence.pilot.summary.observed_months.length, 6);
  const rejected = evidence.pilot.attempts.find(row => row.status !== 'ok');
  assert.equal(rejected.pivot_id, 'PI:5802');
  assert.equal(rejected.date, '2024-03-24');
  assert.equal(rejected.ndvi_median, null);
  assert.ok(rejected.valid_pixel_pct < 70);
  assert.equal(evidence.pilot.offline.http_requests, 0);
  assert.ok(evidence.pilot.scenes.every(scene => /^[a-f0-9]{64}$/.test(scene.xml_sha256)));
});

test('regional catalogue rejects traversal, unsupported states and frozen-version changes', () => {
  for (const edit of [catalog => catalog.regional.package.path = '../data/manifest.json',
    catalog => catalog.regional.status = 'commercially_validated',
    catalog => catalog.paracatu.dataset_version = '2025_adjusted']) {
    const catalog = structuredClone(snapshot.catalog); edit(catalog);
    assert.throws(() => validateRegionalCatalog(catalog), /Catálogo regional/);
  }
});

test('rehashing cannot publish mixed regions, imputations or unverified portability', () => {
  for (const edit of [evidence => evidence.pilot.observations[0].pivot_id = '8087',
    evidence => evidence.pilot.observations[0].valid_pixel_pct = 69,
    evidence => evidence.pilot.offline.status = 'pending',
    evidence => evidence.pilot.monthly.find(row => row.monthly_status !== 'ok').ndvi_median = 0,
    evidence => evidence.pilot.monthly.find(row => row.monthly_status === 'ok').ndvi_median += .1,
    evidence => evidence.pivots.features[0].properties.FID = 5797]) {
    const evidence = structuredClone(snapshot.evidence); edit(evidence);
    assert.throws(() => validateRegionalEvidence(evidence, snapshot.catalog), /Catálogo regional/);
  }
  const catalog = structuredClone(snapshot.catalog); catalog.regional.status = 'territorial_selection';
  assert.throws(() => validateRegionalEvidence(snapshot.evidence, catalog), /seleção territorial/);
});

test('browser loader verifies regional bytes and rejects same-length corruption', async t => {
  const previous = globalThis.fetch;
  t.after(() => { globalThis.fetch = previous; });
  let corrupted = false;
  globalThis.fetch = async url => {
    const catalogRequest = url.pathname.endsWith('/catalog.json');
    const image = snapshot.images.find(image => url.pathname.endsWith(image.descriptor.path));
    const bytes = Buffer.from(catalogRequest ? snapshot.catalogBytes : image ? image.bytes : snapshot.payloadBytes);
    if (!catalogRequest && !image && corrupted) bytes[bytes.length - 2] ^= 1;
    return new Response(bytes, { status: 200 });
  };
  const loaded = await loadRegions(new URL('https://example.invalid/regions/'));
  assert.equal(loaded.evidence.pilot.observations.length, 29);
  corrupted = true;
  await assert.rejects(loadRegions(new URL('https://example.invalid/regions/')), /SHA-256/);
});

test('undeclared regional files and physical corruption cannot enter publication', async t => {
  await mkdir(reviewRoot, { recursive: true });
  const directory = await mkdtemp(resolve(reviewRoot, 'regions-'));
  t.after(async () => {
    assert.ok(directory.startsWith(`${reviewRoot}${sep}`));
    await rm(directory, { recursive: true, force: true });
  });
  await cp(root, directory, { recursive: true });
  await writeFile(resolve(directory, 'unreviewed.csv'), 'fake');
  await assert.rejects(validateRegions(directory), /não declarados/);
  await rm(resolve(directory, 'unreviewed.csv'));
  const file = resolve(directory, snapshot.catalog.regional.package.path);
  const bytes = await readFile(file); bytes[bytes.length - 2] ^= 1; await writeFile(file, bytes);
  await assert.rejects(validateRegions(directory), /SHA-256/);
});

test('temporal context uses exact pivot/month endpoints and retains absent rainfall', () => {
  const data = { monthly: [{ pivot_id:'a', month:'2024-01', precip_status:'ok', precip_mm:0 }, { pivot_id:'b', month:'2024-02', precip_status:'ok', precip_mm:80 }],
    quality: [{ pivot_id:'a', month:'2024-01', monthly_status:'ok', n_accepted_scenes:1, valid_pixel_pct_min:85 }],
    observations: [{ pivot_id:'a', month:'2024-01', scene_id:'real-a' }, { pivot_id:'b', month:'2024-01', scene_id:'other-region' }] };
  const context = eventContext(data, { pivot_id:'a', from_month:'2024-01', to_month:'2024-02' });
  assert.equal(context.before.precip_mm, 0);
  assert.equal(context.before.valid_pixel_pct, 85);
  assert.deepEqual(context.before.scenes, ['real-a']);
  assert.equal(context.after.precip_mm, null);
  assert.equal(context.after.quality, 'missing');
});
