import { createHash } from 'node:crypto';
import { readFile, realpath, readdir } from 'node:fs/promises';
import { resolve, relative, basename, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseCSV } from './csv.mjs';

export const SOURCE_PACKAGE_SHA256 = '16094dc7ef7ae3e6881b86bc0cbb0ff7b146f0558fc0947957865026882360a3';
export const DATASET_NAME = '2022_2024_recovery_v1';
export const SCIENTIFIC_COMMIT = '1440f3e5b28736d12ded226d6baa6b5ca9005262';
export const COMPARISON_HASHES = {
  common_month_metrics: '797e0af9b7269f4a4ef517653e4a09e058322fcd9fb1ce286c246f090c071ba8',
  common_month_predictions: '148332efc4f15f8137a87ce43aa1ebec201640a254059d779f9835aa06de3785',
  comparison_report: 'c1ca4634a5e0eff6a399ca590b4ba92152ec5b9de82a7d0435b2416a84b4dee6',
};
export const REQUIRED = ['pivots', 'observations', 'monthly', 'precipitation', 'quality', 'models',
  'model_predictions', 'model_parameters', 'events', 'provenance', 'schemas'];
export const EXTENSIONS = ['common_month_metrics', 'common_month_predictions', 'comparison_report', 'publication'];
const hashes = /^[0-9a-f]{64}$/;
const hosts = new Set(['portal1.snirh.gov.br', 'earth-search.aws.element84.com',
  'planetarycomputer.microsoft.com', 'data.chc.ucsb.edu', 'edcintl.cr.usgs.gov', 'json-schema.org']);
const assert = (condition, message) => { if (!condition) throw new Error(`Contrato WebGIS: ${message}`); };
export const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const approx = (a, b, tolerance = 1e-8) => Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) <= tolerance;
const key = (row, columns) => JSON.stringify(columns.map(column => row[column]));
const monthNumber = month => Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7));
const median = values => { const sorted = [...values].sort((a, b) => a - b); const i = Math.floor(sorted.length / 2); return sorted.length % 2 ? sorted[i] : (sorted[i - 1] + sorted[i]) / 2; };

export function packageDigest(payloads) {
  const digest = createHash('sha256');
  for (const [name, bytes] of Object.entries(payloads).sort(([a], [b]) => a.localeCompare(b, 'en'))) {
    digest.update(Buffer.from(`${name}\0`, 'utf8')); digest.update(createHash('sha256').update(bytes).digest());
  }
  return digest.digest('hex');
}

export function validatePublicText(text, name) {
  assert(!/(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9.-]{2,}\\\\[A-Za-z0-9._ -]+|\/(?:Users|home|private\/var)\//i.test(text), `${name}: caminho absoluto privado`);
  assert(!/(?:[?&](?:sig|token|access_token|api_key|x-amz-signature|se|sp|sv)=)|(?:Bearer\s+[A-Za-z0-9._-]+)|(?:AKIA[0-9A-Z]{16})/i.test(text), `${name}: credencial ou assinatura temporária`);
  for (const match of text.matchAll(/https?:\/\/[^\s"\\,<>]+/g)) {
    const url = new URL(match[0]);
    assert(url.protocol === 'https:' && hosts.has(url.hostname) && !url.username && !url.password && !url.search,
      `${name}: URL fora da lista pública permitida ou com parâmetros`);
  }
}

function validateSchema(value, schema, location) {
  const types = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
  const matches = type => type === 'null' ? value === null : type === 'integer' ? Number.isInteger(value)
    : type === 'number' ? typeof value === 'number' && Number.isFinite(value) : type === 'array' ? Array.isArray(value)
    : type === 'object' ? value !== null && typeof value === 'object' && !Array.isArray(value) : typeof value === type;
  if (types.length) assert(types.some(matches), `${location}: tipo inválido (${types.join('|')})`);
  if ('const' in schema) assert(value === schema.const, `${location}: constante inválida`);
  if (schema.enum) assert(schema.enum.includes(value), `${location}: valor fora do enum`);
  if (value === null) return;
  if (typeof value === 'number') {
    if ('minimum' in schema) assert(value >= schema.minimum, `${location}: abaixo do mínimo`);
    if ('maximum' in schema) assert(value <= schema.maximum, `${location}: acima do máximo`);
    if ('exclusiveMinimum' in schema) assert(value > schema.exclusiveMinimum, `${location}: abaixo do mínimo exclusivo`);
  }
  if (typeof value === 'string') {
    if (schema.minLength) assert(value.length >= schema.minLength, `${location}: texto vazio`);
    if (schema.pattern) assert(new RegExp(schema.pattern).test(value), `${location}: formato inválido`);
    if (schema.format === 'date') assert(/^\d{4}-\d{2}-\d{2}$/.test(value)
      && !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value, `${location}: data inválida`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems) assert(value.length >= schema.minItems, `${location}: lista vazia`);
    if (schema.items) value.forEach((item, i) => validateSchema(item, schema.items, `${location}[${i}]`));
  } else if (typeof value === 'object') {
    for (const field of schema.required ?? []) assert(Object.hasOwn(value, field), `${location}: campo obrigatório ${field}`);
    for (const [field, definition] of Object.entries(schema.properties ?? {})) {
      if (Object.hasOwn(value, field)) validateSchema(value[field], definition, `${location}.${field}`);
    }
  }
}

function uniqueRows(rows, columns, name) {
  const keys = rows.map(row => key(row, columns));
  assert(new Set(keys).size === keys.length, `${name}: chave duplicada`);
  assert(rows.every(row => columns.every(column => row[column] !== null && row[column] !== undefined)), `${name}: chave ausente`);
}

function validateGeometry(feature) {
  const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
  assert(polygons.length > 0, 'GeoJSON: polígono vazio');
  for (const polygon of polygons) {
    assert(polygon.length > 0, 'GeoJSON: anel ausente');
    for (const ring of polygon) {
      assert(ring.length >= 4 && JSON.stringify(ring[0]) === JSON.stringify(ring.at(-1)), 'GeoJSON: anel aberto');
      for (const point of ring) assert(point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1])
        && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 90, 'GeoJSON: coordenadas inválidas');
    }
  }
}

export async function validatePackage(directory, { publicOnly = false, frozen = true } = {}) {
  const root = await realpath(resolve(directory));
  const manifestBytes = await readFile(resolve(root, 'manifest.json'));
  validatePublicText(manifestBytes.toString('utf8'), 'manifest');
  const manifest = JSON.parse(manifestBytes.toString('utf8'));
  assert(manifest.contract_version === '1.0.0', 'versão esperada 1.0.0');
  assert(hashes.test(manifest.package_sha256 ?? ''), 'package_sha256 inválido');
  assert(manifest.crs === 'EPSG:4326' && JSON.stringify(manifest.coordinate_order) === '["longitude","latitude"]', 'CRS/ordem de coordenadas inválidos');
  assert(manifest.files && typeof manifest.files === 'object', 'files ausente');
  for (const name of REQUIRED) assert(manifest.files[name], `arquivo obrigatório ausente: ${name}`);
  const publicPackage = Boolean(manifest.files.publication);
  if (publicOnly) assert(publicPackage, 'manifesto público sem registro de publicação');
  if (publicPackage) {
    for (const name of EXTENSIONS) assert(manifest.files[name], `extensão pública ausente: ${name}`);
    const rootEntries = await readdir(root);
    assert(rootEntries.length === 2 && rootEntries.includes('manifest.json') && rootEntries.includes('packages'),
      'arquivo ou diretório não permitido na raiz pública');
    const packages = await readdir(resolve(root, 'packages'));
    assert(packages.length === 1 && packages[0] === manifest.package_sha256,
      'a publicação permite somente o pacote ativo declarado no manifesto');
  }
  const payloads = {}; const documents = {}; const tables = {}; const paths = new Set();
  for (const [name, file] of Object.entries(manifest.files)) {
    assert([...REQUIRED, ...EXTENSIONS].includes(name), `arquivo fora da lista permitida: ${name}`);
    assert(file && typeof file === 'object' && hashes.test(file.sha256 ?? ''), `${name}: hash inválido`);
    assert(typeof file.path === 'string' && !file.path.includes('\\') && !file.path.includes(':')
      && !file.path.includes('%') && !file.path.startsWith('/') && !file.path.split('/').some(p => p === '..' || !p), `${name}: caminho inseguro`);
    const expected = `${name}.${name === 'pivots' ? 'geojson' : ['observations', 'monthly', 'precipitation', 'quality', 'models', 'model_predictions', 'events', 'common_month_metrics', 'common_month_predictions'].includes(name) ? 'csv' : 'json'}`;
    assert(file.path === `packages/${manifest.package_sha256}/${expected}`, `${name}: caminho/nome incoerente`);
    assert(!paths.has(file.path), `${name}: caminho duplicado`); paths.add(file.path);
    let actual; try { actual = await realpath(resolve(root, file.path)); } catch { throw new Error(`Contrato WebGIS: arquivo obrigatório ausente: ${name}`); }
    assert(!relative(root, actual).startsWith(`..${sep}`) && !relative(root, actual).startsWith('..'), `${name}: symlink fora do pacote`);
    const bytes = await readFile(actual);
    assert(Number.isInteger(file.bytes) && file.bytes === bytes.length, `${name}: tamanho divergente`);
    assert(sha256(bytes) === file.sha256, `${name}: SHA-256 divergente`);
    assert(file.format === expected.split('.').at(-1), `${name}: formato divergente`);
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    validatePublicText(text, name);
    payloads[expected] = bytes;
    if (file.format !== 'csv') documents[name] = JSON.parse(text);
  }
  assert(packageDigest(payloads) === manifest.package_sha256, 'SHA-256 do pacote divergente');
  const actualFiles = await readdir(resolve(root, 'packages', manifest.package_sha256));
  assert(actualFiles.length === Object.keys(payloads).length && actualFiles.every(name => payloads[name]), 'arquivo não declarado no pacote');
  assert(documents.schemas.contract_version === '1.0.0' && documents.schemas.$schema === 'https://json-schema.org/draft/2020-12/schema', 'schemas incompatíveis');
  for (const [name, file] of Object.entries(manifest.files)) {
    if (file.format === 'csv') {
      const schema = documents.schemas.$defs[name];
      if (REQUIRED.includes(name)) assert(schema, `${name}: esquema ausente`);
      tables[name] = parseCSV(payloads[basename(file.path)].toString('utf8'), schema);
      assert(tables[name].length === file.rows, `${name}: número de linhas divergente`);
      if (schema) {
        assert(file.record_schema === `packages/${manifest.package_sha256}/schemas.json#/$defs/${name}`, `${name}: referência ao esquema inválida`);
        tables[name].forEach((row, i) => validateSchema(row, schema, `${name}[${i}]`));
        uniqueRows(tables[name], schema['x-primary-key'], name);
      }
    }
  }
  validateSchema(documents.pivots, documents.schemas.$defs.pivots, 'pivots');
  assert(manifest.files.pivots.record_schema === `packages/${manifest.package_sha256}/schemas.json#/$defs/pivots`, 'pivots: referência ao esquema inválida');
  documents.pivots.features.forEach(validateGeometry);
  assert(manifest.files.pivots.rows === documents.pivots.features.length, 'contagem GeoJSON divergente');
  const ids = documents.pivots.features.map(f => f.properties.pivot_id);
  assert(new Set(ids).size === ids.length, 'GeoJSON: pivô duplicado');
  for (const [name, rows] of Object.entries(tables)) assert(rows.every(row => ids.includes(row.pivot_id)), `${name}: pivô desconhecido`);
  validateScience(tables, documents, ids, frozen);
  if (publicPackage) {
    assert(manifest.source_package_sha256 === SOURCE_PACKAGE_SHA256
      && documents.publication.source_package_sha256 === SOURCE_PACKAGE_SHA256
      && documents.publication.scientific_commit === SCIENTIFIC_COMMIT, 'origem científica congelada divergente');
    assert(REQUIRED.every(name => documents.publication.original_files[name]), 'registro de arquivos científicos incompleto');
    for (const [name, original] of Object.entries(documents.publication.original_files)) {
      assert(manifest.files[name]?.sha256 === original.sha256 && manifest.files[name]?.bytes === original.bytes,
        `${name}: exportação pública alterou bytes do contrato científico`);
    }
    const core = Object.fromEntries(REQUIRED.map(name => [basename(manifest.files[name].path), payloads[basename(manifest.files[name].path)]]));
    assert(packageDigest(core) === SOURCE_PACKAGE_SHA256, 'conteúdo científico público difere do pacote congelado');
    for (const name of ['common_month_metrics', 'common_month_predictions', 'comparison_report']) {
      assert(documents.publication.comparison_files[name] === manifest.files[name].sha256
        && manifest.files[name].sha256 === COMPARISON_HASHES[name], 'comparação pública diverge do registro de origem congelado');
    }
  } else if (frozen) assert(manifest.package_sha256 === SOURCE_PACKAGE_SHA256, 'pacote diferente da versão científica congelada');
  return { manifest, manifestBytes, payloads, tables, documents, directory: root };
}

function validateScience(t, d, ids, frozen) {
  const provenance = d.provenance;
  assert(provenance.contract_version === '1.0.0' && provenance.dataset_name === DATASET_NAME, 'dataset/proveniência incompatível');
  const months = provenance.months;
  assert(Array.isArray(months) && months.length > 0 && months.every((m, i) => /^\d{4}-(0[1-9]|1[0-2])$/.test(m)
    && (i === 0 || monthNumber(m) === monthNumber(months[i - 1]) + 1)), 'grade mensal descontínua');
  for (const name of ['monthly', 'precipitation', 'quality']) {
    assert(t[name].length === ids.length * months.length, `${name}: grade incompleta`);
    for (const id of ids) assert(months.every(month => t[name].some(row => row.pivot_id === id && row.month === month)), `${name}: espaço mensal ausente`);
  }
  const monthly = new Map(t.monthly.map(row => [key(row, ['pivot_id', 'month']), row]));
  const indexAt = (id, month) => monthly.get(JSON.stringify([id, month]));
  for (const row of t.observations) {
    assert(row.status === 'ok' && row.date.slice(0, 7) === row.month && months.includes(row.month), 'observação aceita/data/mês incoerente');
    assert(row.valid_pixel_pct >= 70 && row.valid_pixel_pct <= 100, 'observação abaixo do limiar científico');
    assert(typeof row.processing_baseline === 'string', 'processing_baseline convertido para número');
  }
  for (const row of t.monthly) {
    const obs = t.observations.filter(o => o.pivot_id === row.pivot_id && o.month === row.month);
    assert(obs.length === row.n_accepted_scenes && row.n_attempted_scenes >= row.n_accepted_scenes, 'contagem mensal divergente');
    assert((row.monthly_status === 'ok') === (obs.length > 0), 'estado mensal incoerente');
    for (const target of ['ndvi_median', 'ndmi_median']) assert(obs.length ? approx(median(obs.map(o => o[target])), row[target]) : row[target] === null,
      `${row.pivot_id}/${row.month}/${target}: mediana ou ausência divergente`);
    const quality = t.quality.find(q => q.pivot_id === row.pivot_id && q.month === row.month);
    for (const field of ['monthly_status', 'batch_status', 'query_complete', 'n_attempted_scenes', 'n_accepted_scenes', 'valid_pixel_pct_min', 'valid_pixel_pct_median']) {
      assert(quality[field] === row[field], `quality: ${field} diverge de monthly`);
    }
    assert(quality.quality_review === (obs.length === 0 || row.valid_pixel_pct_min < 80), 'regra de revisão divergente');
    const rain = t.precipitation.find(q => q.pivot_id === row.pivot_id && q.month === row.month);
    assert(rain.precip_mm === row.precip_mm && rain.precip_status === row.precip_status, 'precipitação diverge de monthly');
  }
  for (const month of months) {
    const rainfall = t.precipitation.filter(row => row.month === month);
    assert(new Set(rainfall.map(row => row.precip_mm)).size === 1, 'chuva regional diverge entre os cinco pivôs');
  }
  for (const row of t.events) {
    const before = indexAt(row.pivot_id, row.from_month); const after = indexAt(row.pivot_id, row.to_month);
    const elapsed = monthNumber(row.to_month) - monthNumber(row.from_month);
    assert(before && after && approx(before[row.index], row.from_value) && approx(after[row.index], row.to_value)
      && approx(row.change, row.to_value - row.from_value), 'evento não corresponde aos valores observados');
    assert(elapsed >= 1 && elapsed === row.elapsed_calendar_months && row.unobserved_months_between === elapsed - 1
      && row.consecutive_calendar_months === (elapsed === 1), 'evento com intervalo/lacunas incoerentes');
    assert(row.absolute_change_threshold > 0 && Math.abs(row.change) >= row.absolute_change_threshold, 'evento abaixo do limiar congelado');
  }
  for (const report of Object.values(provenance.experiment_reports)) {
    assert(report.monthly_input_sha256 === provenance.source_files.monthly.sha256, 'modelo ligado a outra tabela mensal');
  }
  for (const prediction of t.model_predictions) {
    assert(/^2024-/.test(prediction.month), 'predição fora da validação congelada');
    if (prediction.observed !== null) assert(approx(prediction.observed, indexAt(prediction.pivot_id, prediction.month)[prediction.target]), 'referência da predição divergente');
    if (prediction.residual !== null) assert(approx(prediction.residual, prediction.observed - prediction.predicted), 'resíduo incoerente');
  }
  for (const model of t.models) {
    assert(approx(model.coverage_fraction, model.n_valid_pairs / model.expected_months), 'cobertura do modelo incoerente');
    if (!['ok', 'retrospective_exploratory'].includes(model.status)) assert(model.mae === null && model.rmse === null, 'modelo inelegível com métricas');
  }
  if (t.common_month_metrics) validateComparison(t, d);
  if (frozen) {
    assert(ids.length === 5 && [...ids].sort().join(',') === '16708,17373,17382,19997,8087', 'cinco pivôs congelados divergentes');
    assert(t.observations.length === 256 && new Set(t.observations.map(o => o.scene_id)).size === 57, 'contagens científicas congeladas divergentes');
    assert(months.length === 36 && months[0] === '2022-01' && months.at(-1) === '2024-12'
      && t.monthly.filter(row => row.monthly_status === 'ok').length === 141, 'cobertura científica congelada divergente');
    assert(provenance.source_files.monthly.sha256 === 'd78469f3dd13287d390aa75cceaa745e1dbf9ed83a1b4efbf18a17718e64fc7a'
      && provenance.source_files.observations.sha256 === '0b1341b57615a5503a68fc8e3e54983f96fd6129ab463c63a517dce6cf05a780', 'hashes do dataset científico divergentes');
  }
}

function validateComparison(t, d) {
  assert(d.comparison_report.monthly_input_sha256 === d.provenance.source_files.monthly.sha256
    && d.comparison_report.min_common_months_for_metrics === 6, 'comparação ligada a outra versão científica');
  uniqueRows(t.common_month_metrics, ['comparison', 'pivot_id', 'target', 'method'], 'common_month_metrics');
  uniqueRows(t.common_month_predictions, ['comparison', 'pivot_id', 'target', 'method', 'month'], 'common_month_predictions');
  for (const metric of t.common_month_metrics) {
    const months = JSON.parse(metric.common_months); const methods = metric.comparison.split('__vs__');
    assert(Array.isArray(months) && new Set(months).size === months.length && months.length === metric.n_common_months, 'meses comuns incoerentes');
    const eligible = month => methods.every(method => t.model_predictions.some(p => p.pivot_id === metric.pivot_id
      && p.target === metric.target && p.method === method && p.month === month && p.observed !== null && p.predicted !== null && p.residual !== null));
    const actualCommon = d.provenance.months.filter(m => m.startsWith('2024-') && eligible(m));
    assert(JSON.stringify(months) === JSON.stringify(actualCommon), 'contraste não usa interseção exata dos meses de referência');
    const rows = t.common_month_predictions.filter(p => p.comparison === metric.comparison && p.pivot_id === metric.pivot_id
      && p.target === metric.target && p.method === metric.method);
    assert(rows.length === months.length && rows.every(p => months.includes(p.month)), 'predições comuns divergentes');
    for (const row of rows) {
      const source = t.model_predictions.find(p => p.pivot_id === row.pivot_id && p.target === row.target && p.method === row.method && p.month === row.month);
      assert(source && ['observed', 'predicted', 'residual'].every(field => approx(row[field], source[field])), 'comparação modificou predição congelada');
    }
    if (months.length < 6) assert(metric.mae === null && metric.rmse === null && metric.status === 'insufficient_common_validation_months', 'métrica publicada sem seis meses comuns');
    else {
      const mae = rows.reduce((s, r) => s + Math.abs(r.residual), 0) / rows.length;
      const rmse = Math.sqrt(rows.reduce((s, r) => s + r.residual ** 2, 0) / rows.length);
      assert(metric.status === 'ok' && approx(metric.mae, mae) && approx(metric.rmse, rmse), 'métrica comum diverge dos resíduos congelados');
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const directory = resolve(process.argv[2] ?? fileURLToPath(new URL('../data/', import.meta.url)));
    const result = await validatePackage(directory, { publicOnly: !process.argv.includes('--source') });
    console.log(`Contrato 1.0.0 e SHA-256 válidos: ${result.manifest.package_sha256} (${Object.keys(result.manifest.files).length} arquivos)`);
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
