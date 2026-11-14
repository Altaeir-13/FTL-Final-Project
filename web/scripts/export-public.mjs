// This command only copies frozen scientific contracts. It never fits a model,
// acquires imagery, edits scientific inputs, or recalculates a published result.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseCSV } from './csv.mjs';
import { validatePackage, validatePublicText, sha256, packageDigest, REQUIRED,
  SOURCE_PACKAGE_SHA256, DATASET_NAME, SCIENTIFIC_COMMIT, COMPARISON_HASHES } from './validate-data.mjs';

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const defaultSource = resolve(webRoot, '../data/recovery/curated/2022_2024_recovery_v1/webgis');
const extensionHashes = COMPARISON_HASHES;
const jsonBytes = value => Buffer.from(`${JSON.stringify(value, null, 2)}\n`, 'utf8');

async function writeUnchanged(path, bytes) {
  try { if ((await readFile(path)).equals(bytes)) return; } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await mkdir(dirname(path), { recursive: true }); await writeFile(path, bytes);
}

export async function exportPublic(source = defaultSource, output = resolve(webRoot, 'data')) {
  const scientific = await validatePackage(source);
  const payloads = { ...scientific.payloads };
  const files = structuredClone(scientific.manifest.files);
  const comparisonDirectory = resolve(source, '../comparison');
  for (const [name, expectedHash] of Object.entries(extensionHashes)) {
    const format = name === 'comparison_report' ? 'json' : 'csv';
    const bytes = await readFile(resolve(comparisonDirectory, `${name}.${format}`));
    if (sha256(bytes) !== expectedHash) throw new Error(`Comparação congelada com hash divergente: ${name}`);
    validatePublicText(bytes.toString('utf8'), name);
    payloads[`${name}.${format}`] = bytes;
    files[name] = { bytes: bytes.length, sha256: expectedHash, format,
      rows: format === 'csv' ? parseCSV(bytes.toString('utf8')).length : null, record_schema: null };
  }
  const publication = {
    public_export_version: '1.0.0',
    dataset_name: DATASET_NAME,
    scientific_commit: SCIENTIFIC_COMMIT,
    source_package_sha256: SOURCE_PACKAGE_SHA256,
    source_manifest_sha256: sha256(scientific.manifestBytes),
    export_policy: 'Allowlisted contract files and frozen common-month comparisons only. Scientific file bytes are unchanged. No raw rasters, caches, credentials, environment paths or signed URLs.',
    original_files: Object.fromEntries(REQUIRED.map(name => [name, {
      sha256: files[name].sha256, bytes: files[name].bytes,
    }])),
    comparison_files: extensionHashes,
    extension_contract: {
      version: '1.0.0',
      source: 'aquaclima.modeling.comparison frozen outputs',
      core_contract_version: '1.0.0',
      core_schemas_unchanged: true,
      common_month_metrics: {
        key: ['comparison', 'pivot_id', 'target', 'method'],
        common_months: 'JSON array of YYYY-MM strings; exact intersection of scored 2024 months',
        missing_values: 'Empty CSV fields are null; metrics unavailable below six common months',
        units: { mae: 'dimensionless', rmse: 'dimensionless', bias_mean: 'dimensionless' },
      },
      common_month_predictions: {
        key: ['comparison', 'pivot_id', 'target', 'method', 'month'],
        residual: 'observed minus predicted',
      },
    },
    privacy_review: {
      result: 'passed',
      absolute_paths: 0,
      credential_patterns: 0,
      signed_or_parameterized_urls: 0,
      source_contract_fields_removed: [],
      relative_inventory_paths: 'Retained as scientific artifact identifiers; these are not fetchable public assets.',
      note: 'ANA public attributes and public source catalogue URLs are retained. Browser runtime does not request these remote URLs.',
    },
  };
  payloads['publication.json'] = jsonBytes(publication);
  files.publication = { bytes: payloads['publication.json'].length, sha256: sha256(payloads['publication.json']),
    format: 'json', rows: null, record_schema: null };
  const digest = packageDigest(payloads);
  for (const [name, file] of Object.entries(files)) {
    const filename = `${name}.${file.format}`;
    file.path = `packages/${digest}/${filename}`;
    if (file.record_schema) file.record_schema = `packages/${digest}/schemas.json#/$defs/${name}`;
    await writeUnchanged(resolve(output, file.path), payloads[filename]);
  }
  const manifest = {
    contract_version: '1.0.0', package_sha256: digest,
    source_package_sha256: SOURCE_PACKAGE_SHA256,
    crs: 'EPSG:4326', coordinate_order: ['longitude', 'latitude'], files,
  };
  await writeUnchanged(resolve(output, 'manifest.json'), jsonBytes(manifest));
  const result = await validatePackage(output, { publicOnly: true });
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const result = await exportPublic(process.argv[2] ? resolve(process.argv[2]) : undefined,
      process.argv[3] ? resolve(process.argv[3]) : undefined);
    console.log(`Snapshot público validado: ${result.manifest.package_sha256} (${Object.keys(result.manifest.files).length} arquivos)`);
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
