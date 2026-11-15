// Independent regional catalogue; the frozen WebGIS 1.0.0 package is unchanged.
const HASH = /^[a-f0-9]{64}$/;
const assert = (condition, message) => { if (!condition) throw new Error(`Catálogo regional: ${message}`); };
export const REGIONAL_STATES = ['territorial_selection', 'exploratory_portability'];

export function validateRegionalCatalog(catalog) {
  assert(catalog?.catalog_version === '1.0.0', 'versão incompatível');
  assert(catalog.paracatu?.contract_version === '1.0.0' && catalog.paracatu?.dataset_version === '2022_2024_recovery_v1', 'referência congelada incompatível');
  assert(catalog.regional?.id === 'guadalupe-pi' && REGIONAL_STATES.includes(catalog.regional.status), 'estudo ou estado incompatível');
  const file = catalog.regional.package;
  assert(file && HASH.test(file.sha256) && Number.isSafeInteger(file.bytes) && file.bytes > 0, 'integridade ausente');
  assert(file.path === `packages/${file.sha256}/regional.json`, 'caminho fora do pacote regional');
  assert(Array.isArray(catalog.regional.images) && catalog.regional.images.every(image => /^images\/false-colour-202[34]-\d{2}-\d{2}\.png$/.test(image.path) && HASH.test(image.sha256) && Number.isSafeInteger(image.bytes) && image.bytes > 0), 'descritores de imagens inválidos');
  return catalog;
}

export function validateRegionalEvidence(evidence, catalog) {
  validateRegionalCatalog(catalog);
  assert(evidence?.region_id === catalog.regional.id, 'regiões divergentes');
  const selection = evidence.selection;
  assert(selection?.winner?.code === '2204501' && selection.winner.UF === 'PI', 'município divergente');
  assert(Array.isArray(selection.comparison) && selection.comparison.length >= 8, 'inventário comparativo ausente');
  assert(evidence.pivots?.type === 'FeatureCollection' && evidence.pivots.features.length >= 3, 'amostra ausente');
  const ids = evidence.pivots.features.map(feature => feature.properties?.pivot_id);
  assert(new Set(ids).size === ids.length && ids.every(id => /^PI:\d+$/.test(id)), 'pivôs duplicados ou de outra região');
  assert(evidence.pivots.features.every(feature => feature.properties.pivot_id === `PI:${feature.properties.FID}`
    && ['Polygon', 'MultiPolygon'].includes(feature.geometry?.type)), 'identidade ou geometria incompatível');
  if (catalog.regional.status === 'territorial_selection') {
    assert(evidence.pilot === null, 'seleção territorial não pode publicar observações como concluídas');
    return evidence;
  }
  const pilot = evidence.pilot;
  assert(pilot?.offline?.status === 'identical' && pilot.offline.http_requests === 0, 'reprodução offline não comprovada');
  assert(Array.isArray(pilot.observations) && Array.isArray(pilot.monthly), 'tabelas ausentes');
  const keys = new Set();
  for (const row of pilot.observations) {
    const key = `${row.pivot_id}:${row.date}:${row.scene_id}`;
    assert(!keys.has(key) && ids.includes(row.pivot_id), 'observação duplicada ou de outra região'); keys.add(key);
    assert(/^202[34]-\d{2}-\d{2}$/.test(row.date) && row.month === row.date.slice(0, 7), 'data fora do estudo');
    assert(['ndvi_median', 'ndmi_median'].every(name => Number.isFinite(row[name]) && Math.abs(row[name]) <= 1), 'índice inválido');
    assert(Number.isFinite(row.valid_pixel_pct) && row.valid_pixel_pct >= 70 && row.valid_pixel_pct <= 100, 'qualidade abaixo do protocolo');
  }
  const monthlyKeys = new Set();
  const median = values => { const sorted = values.slice().sort((a, b) => a - b); const index = Math.floor(sorted.length / 2); return sorted.length % 2 ? sorted[index] : (sorted[index - 1] + sorted[index]) / 2; };
  for (const row of pilot.monthly) {
    const key = `${row.pivot_id}:${row.month}`;
    assert(ids.includes(row.pivot_id) && !monthlyKeys.has(key) && /^202[34]-\d{2}$/.test(row.month), 'grade mensal inválida'); monthlyKeys.add(key);
    if (row.monthly_status !== 'ok') assert(row.ndvi_median === null && row.ndmi_median === null, 'ausência não pode ser imputada');
    const observations = pilot.observations.filter(observation => observation.pivot_id === row.pivot_id && observation.month === row.month);
    assert(row.n_accepted_scenes === observations.length, 'contagem mensal não corresponde às observações');
    if (observations.length) assert(row.monthly_status === 'ok' && ['ndvi_median','ndmi_median'].every(name => Math.abs(row[name] - median(observations.map(observation => observation[name]))) < 1e-10), 'mediana mensal divergente');
    if (row.precip_status === 'ok') assert(Number.isFinite(row.precip_mm) && row.precip_mm >= 0, 'precipitação inválida');
  }
  assert(pilot.observations.length === pilot.summary.accepted_observations, 'contagem observacional divergente');
  assert(pilot.monthly.length === pilot.summary.calendar_slots, 'contagem mensal divergente');
  assert(pilot.summary.accepted_scenes === new Set(pilot.observations.map(row => row.scene_id)).size, 'contagem de cenas divergente');
  assert(pilot.summary.observed_pivot_months === pilot.monthly.filter(row => row.monthly_status === 'ok').length, 'cobertura mensal divergente');
  assert(pilot.attempts?.length >= pilot.observations.length && pilot.attempts.every(row => ids.includes(row.pivot_id)
    && (row.status === 'ok' || (row.ndvi_median === null && row.ndmi_median === null))), 'tentativas ou rejeições inválidas');
  assert(new Set(pilot.observations.map(row => row.pivot_id)).size >= 3
    && new Set(pilot.observations.map(row => row.date)).size >= 2, 'portabilidade exige três pivôs e datas distintas');
  assert(pilot.monthly.some(row => row.precip_status === 'ok' && Number.isFinite(row.precip_mm)), 'precipitação regional ausente');
  if (catalog.regional.images.length) {
    const comparison = evidence.comparison;
    assert(comparison?.type === 'observed_false_colour_comparison' && comparison.scenes.length === 2 && catalog.regional.images.length === 2, 'comparação de imagens incompleta');
    const [first, second] = comparison.scenes;
    assert(first.crs === second.crs && JSON.stringify(first.transform) === JSON.stringify(second.transform)
      && JSON.stringify(first.shape) === JSON.stringify(second.shape), 'imagens em grades distintas');
    assert(comparison.stretch.min === 0 && comparison.stretch.max === .6 && comparison.grid_resolution_m === 20, 'parâmetros visuais divergentes');
    assert(comparison.scenes.every(scene => catalog.regional.images.some(image => image.date === scene.date && image.scene_id === scene.scene_id && image.sha256 === scene.image_sha256)), 'imagens divergem da proveniência');
  }
  return evidence;
}

export async function loadRegions(base = new URL('./regions/', document.baseURI)) {
  const get = async relative => {
    const response = await fetch(new URL(relative, base));
    if (!response.ok) throw new Error(`Catálogo regional indisponível (HTTP ${response.status}).`);
    return new Uint8Array(await response.arrayBuffer());
  };
  const decode = bytes => new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  const catalog = validateRegionalCatalog(JSON.parse(decode(await get('catalog.json'))));
  const descriptor = catalog.regional.package;
  const bytes = await get(descriptor.path);
  if (bytes.byteLength !== descriptor.bytes) throw new Error('Integridade inválida: tamanho do pacote regional.');
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2, '0')).join('');
  if (hash !== descriptor.sha256) throw new Error('Integridade inválida: SHA-256 do pacote regional.');
  const evidence = validateRegionalEvidence(JSON.parse(decode(bytes)), catalog);
  const images = [];
  for (const descriptor of catalog.regional.images) {
    const image = await get(descriptor.path);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', image)), byte => byte.toString(16).padStart(2, '0')).join('');
    if (image.byteLength !== descriptor.bytes || digest !== descriptor.sha256) throw new Error('Integridade inválida: imagem regional.');
    images.push({ ...descriptor, bytes: image });
  }
  return { catalog, evidence, images };
}
