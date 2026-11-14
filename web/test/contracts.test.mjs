import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { resolve, basename, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseCSV } from '../scripts/csv.mjs';
import { validatePackage, validatePublicText, packageDigest, sha256, SOURCE_PACKAGE_SHA256 } from '../scripts/validate-data.mjs';
import { exportPublic } from '../scripts/export-public.mjs';

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const dataRoot = resolve(webRoot, 'data');
const reviewRoot = resolve(webRoot, '../.local-review');
const scientific = await validatePackage(dataRoot, { publicOnly: true });

async function fixture(t, mutate) {
  await mkdir(reviewRoot, { recursive: true });
  const directory = await mkdtemp(resolve(reviewRoot, 'web-contracts-'));
  t.after(async () => {
    // Only remove the unique fixture directory created above within this checkout.
    assert.ok(directory.startsWith(`${reviewRoot}${sep}`));
    await rm(directory, { recursive: true, force: true });
  });
  const manifest = structuredClone(scientific.manifest);
  const payloads = Object.fromEntries(Object.entries(scientific.payloads).map(([name, bytes]) => [name, Buffer.from(bytes)]));
  const context = { manifest, payloads };
  await mutate(context);
  for (const [name, file] of Object.entries(manifest.files)) {
    const bytes = payloads[basename(file.path)];
    const target = resolve(directory, file.path);
    if (bytes && target.startsWith(`${directory}${sep}`)) {
      await mkdir(dirname(target), { recursive: true }); await writeFile(target, bytes);
    }
  }
  await writeFile(resolve(directory, 'manifest.json'), JSON.stringify(manifest));
  return directory;
}

function repack(context) {
  const digest = packageDigest(context.payloads); context.manifest.package_sha256 = digest;
  for (const [name, file] of Object.entries(context.manifest.files)) {
    const filename = basename(file.path); const bytes = context.payloads[filename];
    file.path = `packages/${digest}/${filename}`; file.bytes = bytes.length; file.sha256 = sha256(bytes);
    if (file.record_schema) file.record_schema = `packages/${digest}/schemas.json#/$defs/${name}`;
  }
}

function editTable(context, filename, edit) {
  const rows = parseCSV(context.payloads[filename].toString('utf8'));
  edit(rows);
  const columns = Object.keys(rows[0]);
  const cell = value => {
    if (value === null) return '';
    const text = String(value); return /[,"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  context.payloads[filename] = Buffer.from(`${columns.join(',')}\n${rows.map(row => columns.map(column => cell(row[column])).join(',')).join('\n')}\n`);
  repack(context);
}

test('frozen public package validates complete manifest, SHA-256, schemas and scientific references', () => {
  assert.equal(scientific.manifest.contract_version, '1.0.0');
  assert.equal(scientific.manifest.source_package_sha256, SOURCE_PACKAGE_SHA256);
  assert.equal(scientific.documents.pivots.features.length, 5);
  assert.equal(scientific.tables.observations.length, 256);
  assert.equal(scientific.tables.monthly.length, 180);
  assert.equal(scientific.tables.monthly.filter(row => row.monthly_status === 'ok').length, 141);
  assert.equal(new Set(scientific.tables.observations.map(row => row.scene_id)).size, 57);
  assert.equal(Object.keys(scientific.manifest.files).length, 15);
});

test('CSV decodes empty as null, zero as zero, identifiers and processing baseline as text', () => {
  const [row] = parseCSV('pivot_id,processing_baseline,month,ndvi_median,ndmi_median,query_complete\n00001,05.10,2022-01,,0,true\n');
  assert.equal(row.pivot_id, '00001'); assert.equal(row.processing_baseline, '05.10');
  assert.equal(row.ndvi_median, null); assert.equal(row.ndmi_median, 0); assert.equal(row.query_complete, true);
});

test('CSV handles quoted commas, escaped quotes and embedded newlines, and rejects broken input', () => {
  assert.deepEqual(parseCSV('pivot_id,note\n01,"A, B ""quoted""\nline"\n'), [{ pivot_id: '01', note: 'A, B "quoted"\nline' }]);
  for (const text of ['a,a\n1,2\n', 'a,b\n1\n', 'a\n"bad', 'a\n"v"trailing\n']) assert.throws(() => parseCSV(text), /CSV/);
  assert.throws(() => parseCSV('query_complete\nTRUE\n'), /booleano/);
  assert.throws(() => parseCSV('ndvi_median\nNaN\n'), /número/);
});

test('required file missing from manifest fails explicitly', async t => {
  const dir = await fixture(t, ({ manifest }) => { delete manifest.files.events; });
  await assert.rejects(validatePackage(dir), /arquivo obrigatório ausente: events/);
});

test('missing physical file fails explicitly', async t => {
  const dir = await fixture(t, ({ payloads }) => { delete payloads['monthly.csv']; });
  await assert.rejects(validatePackage(dir), /arquivo obrigatório ausente: monthly/);
});

test('same-length file corruption is rejected by SHA-256', async t => {
  const dir = await fixture(t, ({ payloads }) => { payloads['events.csv'][20] ^= 1; });
  await assert.rejects(validatePackage(dir), /SHA-256 divergente/);
});

test('truncated file fails size verification', async t => {
  const dir = await fixture(t, ({ payloads }) => { payloads['events.csv'] = payloads['events.csv'].subarray(0, 100); });
  await assert.rejects(validatePackage(dir), /tamanho divergente/);
});

test('version and path traversal are rejected before reading outside package', async t => {
  const wrongVersion = await fixture(t, ({ manifest }) => { manifest.contract_version = '2.0.0'; });
  await assert.rejects(validatePackage(wrongVersion), /versão esperada/);
  const badPath = await fixture(t, ({ manifest }) => { manifest.files.events.path = '../outside.csv'; });
  await assert.rejects(validatePackage(badPath), /caminho inseguro/);
});

test('rehashed monthly imputation cannot turn absent observations into zero', async t => {
  const dir = await fixture(t, context => editTable(context, 'monthly.csv', rows => {
    rows.find(row => row.ndvi_median === null).ndvi_median = 0;
  }));
  await assert.rejects(validatePackage(dir), /mediana ou ausência divergente/);
});

test('rehashed ineligible model cannot publish zero metrics', async t => {
  const dir = await fixture(t, context => editTable(context, 'models.csv', rows => {
    const row = rows.find(row => row.status !== 'ok' && row.status !== 'retrospective_exploratory'); row.mae = 0; row.rmse = 0;
  }));
  await assert.rejects(validatePackage(dir), /modelo inelegível com métricas/);
});

test('common-month comparisons retain the exact intersection of scored reference months', async t => {
  const dir = await fixture(t, context => editTable(context, 'common_month_metrics.csv', rows => {
    const row = rows.find(row => row.n_common_months === 7); const months = JSON.parse(row.common_months);
    months[0] = '2024-02'; row.common_months = JSON.stringify(months);
  }));
  await assert.rejects(validatePackage(dir), /interseção exata/);
});

test('public data privacy policy accepts recorded public URLs and rejects secrets or environment paths', () => {
  assert.doesNotThrow(() => validatePublicText('https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/scene', 'fixture'));
  for (const text of ['C:\\Users\\researcher\\file.csv', '/home/user/private.json',
    'https://planetarycomputer.microsoft.com/file?sig=secret', 'https://example.com/private',
    'Bearer abcdefsecret', 'https://data.chc.ucsb.edu/file?access_token=secret']) {
    assert.throws(() => validatePublicText(text, 'fixture'), /Contrato WebGIS/);
  }
});

test('published core files match the immutable scientific package identity', () => {
  const core = Object.fromEntries(Object.keys(scientific.documents.publication.original_files).map(name => {
    const filename = basename(scientific.manifest.files[name].path); return [filename, scientific.payloads[filename]];
  }));
  assert.equal(packageDigest(core), SOURCE_PACKAGE_SHA256);
  assert.equal(scientific.documents.publication.privacy_review.source_contract_fields_removed.length, 0);
});

test('public build rejects sidecar files and undeclared historical packages', async t => {
  const extraFile = await fixture(t, () => {});
  await writeFile(resolve(extraFile, 'local-settings.txt'), 'fixture');
  await assert.rejects(validatePackage(extraFile, { publicOnly: true }), /não permitido na raiz pública/);
  const oldPackage = await fixture(t, () => {});
  await mkdir(resolve(oldPackage, 'packages', 'stale-snapshot'));
  await assert.rejects(validatePackage(oldPackage, { publicOnly: true }), /somente o pacote ativo/);
});

test('public export reproduces every published byte from frozen allowlisted inputs', async t => {
  const directory = await fixture(t, () => {});
  const source = resolve(directory, 'reconstructed-source/webgis');
  const originalFiles = Object.fromEntries(Object.keys(scientific.documents.publication.original_files).sort().map(name => {
    const file = structuredClone(scientific.manifest.files[name]);
    const filename = basename(file.path);
    file.path = `packages/${SOURCE_PACKAGE_SHA256}/${filename}`;
    if (file.record_schema) file.record_schema = `packages/${SOURCE_PACKAGE_SHA256}/schemas.json#/$defs/${name}`;
    return [name, file];
  }));
  const originalManifest = { contract_version: '1.0.0', package_sha256: SOURCE_PACKAGE_SHA256,
    crs: 'EPSG:4326', coordinate_order: ['longitude', 'latitude'], files: originalFiles };
  const sourceBytes = Buffer.from(`${JSON.stringify(originalManifest, null, 2)}\n`);
  assert.equal(sha256(sourceBytes), scientific.documents.publication.source_manifest_sha256);
  await mkdir(source, { recursive: true });
  await writeFile(resolve(source, 'manifest.json'), sourceBytes);
  for (const file of Object.values(originalFiles)) {
    await mkdir(dirname(resolve(source, file.path)), { recursive: true });
    await writeFile(resolve(source, file.path), scientific.payloads[basename(file.path)]);
  }
  const comparison = resolve(source, '../comparison');
  await mkdir(comparison, { recursive: true });
  for (const name of ['common_month_metrics.csv', 'common_month_predictions.csv', 'comparison_report.json']) {
    await writeFile(resolve(comparison, name), scientific.payloads[name]);
  }
  const result = await exportPublic(source, resolve(directory, 'export'));
  assert.equal(result.manifest.package_sha256, scientific.manifest.package_sha256);
  assert.deepEqual(result.manifestBytes, scientific.manifestBytes);
  for (const [name, bytes] of Object.entries(result.payloads)) assert.deepEqual(bytes, scientific.payloads[name], name);
  const second = await exportPublic(source, resolve(directory, 'export'));
  assert.deepEqual(second.manifestBytes, result.manifestBytes);
});
