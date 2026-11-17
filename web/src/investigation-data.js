// Presentation-only views of the already validated public packages. No imputation,
// acquisition, aggregation or model fitting is performed by this module.
export const INVESTIGATION_VERSION = '1.0.0';
export const STUDY_IDS = ['paracatu-mg', 'guadalupe-pi'];
const HASH = /^[a-f0-9]{64}$/;
const MONTH = /^202[234]-(0[1-9]|1[0-2])$/;
const finite = value => Number.isFinite(value) ? value : null;
const assert = (condition, message) => { if (!condition) throw new Error(`Investigação: ${message}`); };
const ordinal = month => Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1;
const fmt = (value, digits = 4) => value == null ? 'indisponível' : new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);

export function createStudies(paracatu, regional = null) {
  assert(paracatu?.manifest?.contract_version === '1.0.0' && HASH.test(paracatu.manifest.package_sha256), 'contrato de Paracatu incompatível.');
  const studies = [{
    id: 'paracatu-mg', label: 'Paracatu, MG', status: 'Estudo científico concluído',
    version: paracatu.provenance.dataset_name, packageHash: paracatu.manifest.package_sha256,
    granularity: 'month', pivots: paracatu.pivots, monthly: paracatu.monthly,
    observations: paracatu.observations, quality: paracatu.quality, scenes: [], images: [],
    sourceFiles: Object.fromEntries(['observations', 'monthly', 'precipitation', 'quality', 'pivots'].map(name => [name, paracatu.manifest.files?.[name]?.sha256 ?? null])),
  }];
  if (regional?.evidence?.pilot && regional.catalog.regional.status === 'exploratory_portability') {
    assert(regional.evidence.region_id === 'guadalupe-pi' && HASH.test(regional.catalog.regional.package.sha256), 'pacote regional incompatível.');
    assert(regional.catalog.paracatu.package_sha256 === paracatu.manifest.package_sha256, 'referência de Paracatu divergente no catálogo.');
    const { evidence, catalog } = regional;
    studies.push({
      id: 'guadalupe-pi', label: 'Guadalupe, PI', status: 'Prova exploratória de portabilidade · sem modelo regional validado',
      version: catalog.regional.version, packageHash: catalog.regional.package.sha256,
      granularity: 'scene', pivots: evidence.pivots, monthly: evidence.pilot.monthly,
      observations: evidence.pilot.observations, quality: evidence.pilot.monthly,
      scenes: evidence.pilot.scenes, images: regional.images || [], comparison: evidence.comparison,
      sourceFiles: Object.fromEntries(Object.entries(evidence.pilot.summary.files).map(([name, file]) => [name, file.sha256])),
    });
  }
  for (const study of studies) {
    const ids = study.pivots.features.map(feature => feature.properties.pivot_id);
    assert(ids.every(id => study.id === 'paracatu-mg' ? /^\d+$/.test(id) : /^PI:\d+$/.test(id)), 'pivô de outra região.');
    assert(study.monthly.every(row => ids.includes(row.pivot_id)) && study.observations.every(row => ids.includes(row.pivot_id)), 'mistura de dados entre estudos.');
  }
  return studies;
}

function provenance(study, observation) {
  const scene = study.scenes.find(row => row.scene_id === observation.scene_id);
  return {
    scene_id: observation.scene_id, date: observation.date,
    provider: scene?.provider ?? observation.provider ?? null,
    collection: scene?.collection ?? observation.collection ?? null,
    processing_baseline: scene?.processing_baseline ?? observation.processing_baseline ?? null,
    method: scene?.method ?? observation.radiometric_method ?? null,
    source: observation.sentinel_source ?? null,
    native_scene_id: observation.native_scene_id ?? null,
    acquisition_key: observation.acquisition_key ?? null,
    product: scene?.product ?? null,
    calibration_sha256: scene?.xml_sha256 ?? observation.calibration_sha256 ?? null,
    calibration_formula: scene?.calibration?.formula ?? null,
    quantification_value: finite(scene?.calibration?.quantification_value),
    indices_sha256: observation.indices_sha256 ?? null,
    batch_manifest_sha256: observation.batch_manifest_sha256 ?? null,
    pivots_sha256: observation.pivots_sha256 ?? null,
  };
}

export function imageForObservation(study, pivotId, observation) {
  if (study.id !== 'guadalupe-pi' || study.granularity !== 'scene' || !study.pivots.features.some(feature => feature.properties.pivot_id === pivotId)) return null;
  const accepted = study.observations.find(row => row.pivot_id === pivotId && row.date === observation.date && row.scene_id === observation.scene_id);
  if (!accepted) return null;
  const scene = study.comparison?.scenes.find(row => row.date === accepted.date && row.scene_id === accepted.scene_id);
  const image = study.images.find(row => row.date === accepted.date && row.scene_id === accepted.scene_id && row.sha256 === scene?.image_sha256);
  if (!scene || !image) return null;
  return {
    date: scene.date, scene_id: scene.scene_id, sha256: image.sha256, path: image.path,
    url: image.url ?? `./regions/${image.path}`, source: scene.source,
    crs: scene.crs, processing_baseline: scene.processing_baseline,
    composition: study.comparison.composition, grid_resolution_m: study.comparison.grid_resolution_m,
    stretch: { ...study.comparison.stretch },
    context: 'Área conjunta dos cinco pivôs ANA de Guadalupe; o contorno identifica o pivô selecionado. Não é um recorte individual.',
  };
}

export function availableObservations(study, pivotId) {
  if (!study?.pivots.features.some(feature => feature.properties.pivot_id === pivotId)) return [];
  const observations = study.observations.filter(row => row.pivot_id === pivotId && (row.status == null || row.status === 'ok'));
  const normalize = (row, scenes, id) => {
    const monthly = study.monthly.find(month => month.pivot_id === pivotId && month.month === row.month);
    const quality = study.quality.find(month => month.pivot_id === pivotId && month.month === row.month);
    return {
      id, label: study.granularity === 'month' ? `${row.month} · agregado mensal` : `${row.date} · cena real`,
      granularity: study.granularity, month: row.month,
      date: study.granularity === 'scene' ? row.date : null,
      dates: [...new Set(scenes.map(scene => scene.date))].sort(),
      ndvi_median: finite(row.ndvi_median), ndmi_median: finite(row.ndmi_median),
      valid_pixel_pct: finite(study.granularity === 'month' ? quality?.valid_pixel_pct_min : row.valid_pixel_pct),
      quality_review: quality?.quality_review ?? (finite(row.valid_pixel_pct) != null && row.valid_pixel_pct < 80),
      batch_status: quality?.batch_status ?? monthly?.batch_status ?? null,
      query_complete: quality?.query_complete ?? monthly?.query_complete ?? null,
      n_attempted_scenes: quality?.n_attempted_scenes ?? monthly?.n_attempted_scenes ?? null,
      n_accepted_scenes: quality?.n_accepted_scenes ?? monthly?.n_accepted_scenes ?? null,
      precip_mm: monthly?.precip_status === 'ok' ? finite(monthly.precip_mm) : null,
      precip_status: monthly?.precip_status ?? 'missing',
      precipitation: {
        source: monthly?.chirps_source ?? null, product: monthly?.chirps_product ?? null,
        units: monthly?.chirps_units ?? null,
        cell_row: finite(monthly?.chirps_cell_row), cell_col: finite(monthly?.chirps_cell_col),
        cell_lon: finite(monthly?.chirps_cell_lon), cell_lat: finite(monthly?.chirps_cell_lat),
        resolution_deg: finite(monthly?.chirps_resolution_deg),
        raster_sha256: monthly?.chirps_sha256 ?? null,
      },
      scenes: scenes.map(scene => provenance(study, scene)),
      method: study.granularity === 'month' ? 'Mediana das medianas espaciais de cenas aceitas, com pesos iguais.' : 'Mediana espacial dos pixels conjuntos válidos da cena aceita.',
      image: study.granularity === 'scene' ? imageForObservation(study, pivotId, row) : null,
    };
  };
  if (study.granularity === 'month') return study.monthly
    .filter(row => row.pivot_id === pivotId && row.monthly_status === 'ok' && observations.some(scene => scene.month === row.month))
    .map(row => normalize(row, observations.filter(scene => scene.month === row.month), row.month))
    .sort((a, b) => a.month.localeCompare(b.month));
  return observations.map(row => normalize(row, [row], observations.filter(other => other.date === row.date).length === 1 ? row.date : `${row.date}|${row.scene_id}`))
    .sort((a, b) => a.id.localeCompare(b.id));
}

// Invalid links fall back to real observations and explicitly report the correction.
// A package mismatch is retained as a warning and blocks scientific comparison.
export function resolveSelection(studies, input = {}) {
  assert(studies.length > 0, 'nenhum estudo disponível.');
  const warnings = [];
  const study = studies.find(row => row.id === input.region) ?? studies[0];
  if (input.region && input.region !== study.id) warnings.push('Território indisponível; seleção restaurada para o estudo disponível.');
  const pivot = study.pivots.features.find(feature => feature.properties.pivot_id === input.pivot)?.properties.pivot_id ?? study.pivots.features[0].properties.pivot_id;
  if (input.pivot && input.pivot !== pivot) warnings.push('Pivô inválido para este território; seleção corrigida.');
  const rows = availableObservations(study, pivot);
  assert(rows.length >= 2, 'não há duas observações aceitas para este pivô.');
  const first = rows.find(row => row.id === input.a) ?? rows[0];
  const second = rows.find(row => row.id === input.b && canCompareObservations(first, row))
    ?? [...rows].reverse().find(row => canCompareObservations(first, row));
  assert(second, 'não há duas datas distintas aceitas para este pivô.');
  if (input.a && input.a !== first.id) warnings.push('Observação A ausente ou inválida; substituída por uma observação aceita.');
  if (input.b && input.b !== second.id) warnings.push('Observação B ausente, inválida ou idêntica a A; substituída por uma observação aceita distinta.');
  const packageMismatch = Boolean(input.package && input.package !== study.packageHash);
  if (packageMismatch) warnings.push('O pacote deste link difere do pacote publicado. A comparação está bloqueada; escolha novamente o território para iniciar outra investigação.');
  return {
    region: study.id, pivot, a: first.id, b: second.id,
    index: input.index === 'ndmi' || input.index === 'ndmi_median' ? 'ndmi' : 'ndvi',
    section: 'investigacao', package: packageMismatch ? input.package : study.packageHash,
    packageMismatch, warnings,
  };
}

export function signedDelta(before, after) {
  return Number.isFinite(before) && Number.isFinite(after) ? after - before : null;
}

export function canCompareObservations(a, b) {
  return Boolean(a && b && a.id !== b.id && a.granularity === b.granularity && (a.date == null || a.date !== b.date));
}

export function compareSelection(studies, selection) {
  const study = studies.find(row => row.id === selection.region);
  assert(study, 'território inválido.');
  assert(!selection.packageMismatch && (!selection.package || selection.package === study.packageHash), 'pacote do link não corresponde ao pacote publicado.');
  const feature = study.pivots.features.find(row => row.properties.pivot_id === selection.pivot);
  assert(feature, 'pivô inválido para o território.');
  const rows = availableObservations(study, selection.pivot);
  const a = rows.find(row => row.id === selection.a);
  const b = rows.find(row => row.id === selection.b);
  assert(canCompareObservations(a, b), 'selecione duas observações aceitas e distintas.');
  const monthly = study.monthly.filter(row => row.pivot_id === selection.pivot).sort((a, b) => a.month.localeCompare(b.month));
  const from = a.month < b.month ? a.month : b.month;
  const to = a.month > b.month ? a.month : b.month;
  const unobservedMonths = monthly.filter(row => row.month > from && row.month < to && row.monthly_status !== 'ok').map(row => row.month);
  const delta_ndvi = signedDelta(a.ndvi_median, b.ndvi_median);
  const delta_ndmi = signedDelta(a.ndmi_median, b.ndmi_median);
  const change = (label, delta) => delta == null ? `${label}: diferença indisponível.` : `${label}: ${delta > 0 ? 'aumento' : delta < 0 ? 'redução' : 'sem mudança'} de ${fmt(Math.abs(delta))} unidade adimensional (B − A = ${delta > 0 ? '+' : ''}${fmt(delta)}).`;
  const limitations = [
    'Essa mudança pode estar associada a diferentes processos agrícolas, incluindo fenologia, colheita, manejo, solo exposto e condições ambientais. Os dados disponíveis não permitem atribuir uma causa específica.',
    'Os índices não medem consumo ou economia de água e não diagnosticam falha de irrigação. Cultura, manejo e validação de campo estão indisponíveis.',
    'A precipitação CHIRPS é acumulado mensal de uma célula regional; pode incluir chuva posterior ao dia da cena. Não representa chuva medida no talhão.',
    'Lacunas permanecem ausentes, sem interpolação. A qualidade por pixels não elimina todas as fontes de incerteza.',
    ...(study.id === 'guadalupe-pi' ? ['A amostragem regional é exploratória, irregular e selecionada por disponibilidade. Não há modelo regional validado nem evidência de sazonalidade anual completa.', 'Os produtos regionais possuem baselines de processamento próprios. Não foi avaliada a mesma aquisição reprocessada nas diferentes baselines; não se afirma equivalência radiométrica absoluta.'] : ['Os resultados de Paracatu correspondem ao pacote científico congelado de 2022–2024. A comparação selecionada é descritiva e não modifica modelos ou métricas.']),
  ];
  return {
    study: { id: study.id, label: study.label, status: study.status, version: study.version, packageHash: study.packageHash, granularity: study.granularity, sourceFiles: { ...study.sourceFiles } },
    pivot: {
      id: selection.pivot, area_ha: finite(feature.properties.area_ha),
      municipality: feature.properties.MUNIC_NOME ?? study.label.split(',')[0], uf: feature.properties.UF ?? study.label.split(', ')[1],
      period: { from: monthly[0]?.month, to: monthly.at(-1)?.month },
      acceptedObservations: study.observations.filter(row => row.pivot_id === selection.pivot).length,
      observedMonths: monthly.filter(row => row.monthly_status === 'ok').length, calendarMonths: monthly.length,
    },
    a, b, delta_ndvi, delta_ndmi,
    interval: {
      calendarMonths: Math.abs(ordinal(b.month) - ordinal(a.month)),
      days: a.date && b.date ? Math.abs((Date.parse(`${b.date}T00:00:00Z`) - Date.parse(`${a.date}T00:00:00Z`)) / 86400000) : null,
      unobservedMonths,
    },
    synthesis: `Entre A (${a.label}) e B (${b.label}), ${change('NDVI', delta_ndvi)} ${change('NDMI', delta_ndmi)} Qualidade registrada: ${fmt(a.valid_pixel_pct, 2)}% em A e ${fmt(b.valid_pixel_pct, 2)}% em B${study.granularity === 'month' ? ' (mínimo das cenas aceitas no mês)' : ''}. Precipitação CHIRPS dos meses ${a.month}/${b.month}: ${fmt(a.precip_mm, 2)}/${fmt(b.precip_mm, 2)} mm.`,
    limitations,
    parameters: { presentation_version: INVESTIGATION_VERSION, granularity: study.granularity, delta: 'B-A', index: selection.index, missing_data: 'no_imputation' },
    selection: { region: study.id, pivot: selection.pivot, a: a.id, b: b.id, index: selection.index, section: 'investigacao', package: study.packageHash },
    images: [a.image, b.image],
  };
}

export async function investigationId(snapshot) {
  const identity = JSON.stringify({
    region: snapshot.study.id, pivot: snapshot.pivot.id,
    a: { id: snapshot.a.id, scenes: snapshot.a.scenes.map(scene => scene.scene_id).sort() },
    b: { id: snapshot.b.id, scenes: snapshot.b.scenes.map(scene => scene.scene_id).sort() },
    version: snapshot.study.version, package: snapshot.study.packageHash,
    parameters: Object.fromEntries(Object.entries(snapshot.parameters).sort(([a], [b]) => a.localeCompare(b))),
  });
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(identity));
  return `AQ-${Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')}`;
}

export function parseInvestigationURL(search, studies) {
  const params = new URLSearchParams(search);
  return resolveSelection(studies, {
    region: params.get('region') || 'paracatu-mg', pivot: params.get('pivot'),
    a: params.get('a'), b: params.get('b'), index: params.get('indice'), package: params.get('package'),
  });
}

export function serializeInvestigationURL(selection, current = '') {
  const params = new URLSearchParams(current);
  // Keep the legacy exploration period, but discard arbitrary/personal input.
  const output = new URLSearchParams();
  for (const key of ['from', 'to']) if (MONTH.test(params.get(key) || '')) output.set(key, params.get(key));
  for (const [key, value] of Object.entries({ region: selection.region, pivot: selection.pivot, a: selection.a, b: selection.b, indice: selection.index, section: 'investigacao', package: selection.package })) {
    if (typeof value === 'string') output.set(key, value);
  }
  return `?${output}`;
}
