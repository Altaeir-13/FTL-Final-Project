// Display helpers only: these functions never fit a model or change a scientific result.
const numericNames = new Set([
  'area_ha', 'ndvi_median', 'ndmi_median', 'valid_pixel_pct', 'valid_pixel_pct_min',
  'valid_pixel_pct_median', 'precip_mm', 'mae', 'rmse', 'bias_mean', 'coverage_fraction',
  'observed', 'predicted', 'residual', 'from_value', 'to_value', 'change',
  'absolute_change_threshold', 'elapsed_calendar_months', 'unobserved_months_between',
  'n_valid_pairs', 'expected_months', 'n_common_months', 'observation_day_span',
  'chirps_resolution_deg', 'chirps_cell_row', 'chirps_cell_col', 'chirps_cell_lon', 'chirps_cell_lat',
]);
const booleanNames = new Set(['query_complete', 'quality_review', 'consecutive_calendar_months']);

export function parseCSV(text, schema) {
  if (typeof text !== 'string') throw new TypeError('O CSV deve ser texto UTF-8.');
  const records = [];
  let row = [], field = '', quoted = false, closed = false;
  const input = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (quoted) {
      if (char === '"') {
        if (input[i + 1] === '"') { field += '"'; i++; }
        else { quoted = false; closed = true; }
      } else field += char;
    } else if (char === '"') {
      if (field || closed) throw new Error('CSV inválido: aspas fora do início do campo.');
      quoted = true;
    } else if (char === ',') {
      row.push(field); field = ''; closed = false;
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && input[i + 1] === '\n') i++;
      row.push(field);
      if (row.some(value => value !== '')) records.push(row);
      row = []; field = ''; closed = false;
    } else {
      if (closed) throw new Error('CSV inválido: conteúdo após aspas finais.');
      field += char;
    }
  }
  if (quoted) throw new Error('CSV inválido: campo com aspas não fechado.');
  if (field || row.length || closed) { row.push(field); records.push(row); }
  if (!records.length) return [];
  const header = records.shift();
  if (new Set(header).size !== header.length || header.some(key => !key)) throw new Error('Cabeçalho CSV inválido.');
  return records.map((values, index) => {
    if (values.length !== header.length) throw new Error(`CSV inválido: linha ${index + 2} com ${values.length} campos; esperados ${header.length}.`);
    return Object.fromEntries(header.map((key, col) => {
      const raw = values[col];
      if (raw === '') return [key, null];
      const property = schema?.properties?.[key];
      const types = Array.isArray(property?.type) ? property.type : [property?.type];
      // Contract versions and scene identifiers are strings, even when they resemble numbers.
      if (key === 'pivot_id' || key === 'processing_baseline' || types.includes('string')) return [key, raw];
      if (types.includes('boolean') || booleanNames.has(key)) {
        if (raw !== 'true' && raw !== 'false') throw new Error(`Booleano inválido em ${key}: ${raw}`);
        return [key, raw === 'true'];
      }
      if (types.includes('number') || types.includes('integer') || numericNames.has(key) || key.startsWith('n_') || key.endsWith('_count')) {
        if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)) throw new Error(`Número inválido em ${key}: ${raw}`);
        const value = Number(raw);
        if (!Number.isFinite(value) || (types.includes('integer') && !Number.isInteger(value))) throw new Error(`Número inválido em ${key}: ${raw}`);
        return [key, value];
      }
      return [key, raw];
    }));
  });
}

export function filterMonthly(rows, pivotId, from = '2022-01', to = '2024-12') {
  if (from > to) return [];
  return rows.filter(row => row.pivot_id === String(pivotId) && row.month >= from && row.month <= to)
    .slice().sort((a, b) => a.month.localeCompare(b.month));
}

export function coverageState(row) {
  if (!row) return 'missing';
  if ((row.batch_status != null && row.batch_status !== 'complete') || row.query_complete === false) return 'incomplete';
  if (row.monthly_status !== 'ok' || row.n_accepted_scenes === 0) return 'missing';
  if (row.quality_review === true || (row.valid_pixel_pct_min != null && row.valid_pixel_pct_min < 80)) return 'limited';
  return 'valid';
}

function monthOrdinal(month) {
  const [year, value] = month.split('-').map(Number);
  return year * 12 + value - 1;
}

export function seriesSegments(rows, target) {
  const segments = [];
  let current = [];
  for (const row of rows.slice().sort((a, b) => a.month.localeCompare(b.month))) {
    const valid = row.monthly_status === 'ok' && row[target] != null && Number.isFinite(row[target]);
    const previous = current.at(-1);
    if (!valid || (previous && monthOrdinal(row.month) - monthOrdinal(previous.month) !== 1)) {
      if (current.length) segments.push(current);
      current = [];
    }
    if (valid) current.push(row);
  }
  if (current.length) segments.push(current);
  return segments;
}

export function commonComparison(data, pivotId, target, group) {
  const source = Array.isArray(data) ? data : data.common_month_metrics ?? data.commonMetrics ?? [];
  const comparison = Array.isArray(group) ? group.slice().sort().join('__vs__') : group;
  const rows = source.filter(row => row.pivot_id === String(pivotId) && row.target === target && (!comparison || row.comparison === comparison));
  if (!rows.length) return { rows: [], months: [], eligible: false, reason: 'Comparação indisponível para este pivô e índice.' };
  const monthsOf = row => Array.isArray(row.common_months) ? row.common_months : JSON.parse(row.common_months || '[]');
  const months = monthsOf(rows[0]);
  const sameMonths = rows.every(row => JSON.stringify(monthsOf(row)) === JSON.stringify(months));
  const expectedMethods = comparison?.split('__vs__');
  const actualMethods = rows.map(row => row.method).sort();
  const completeMethods = expectedMethods ? JSON.stringify(actualMethods) === JSON.stringify(expectedMethods.slice().sort()) : new Set(actualMethods).size === actualMethods.length;
  const eligible = sameMonths && completeMethods && months.length >= 6 && new Set(months).size === months.length && rows.every(row => row.status === 'ok' && row.mae != null && row.rmse != null && row.n_common_months === months.length);
  return { rows, months, eligible, reason: eligible ? null : sameMonths ? 'Dados insuficientes para comparar nos mesmos meses de referência.' : 'Os conjuntos de meses divergem; comparação bloqueada.' };
}

export const methodLabels = {
  calendar_month_median: 'Mediana sazonal',
  harmonic_ridge: 'Ridge harmônica',
  previous_year_same_calendar_month: 'Mesmo mês de 2023',
};
