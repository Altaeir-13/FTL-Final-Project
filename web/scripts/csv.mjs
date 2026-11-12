// CSV decoding follows the versioned scientific schemas; identifiers stay textual.
const numericColumns = new Set([
  'area_ha', 'ndvi_median', 'ndmi_median', 'valid_pixel_pct', 'ndvi_valid_pixel_pct',
  'ndmi_valid_pixel_pct', 'pivot_pixels', 'joint_valid_pixels', 'scene_cloud_pct',
  'catalog_candidate_count', 'n_attempted_scenes', 'n_accepted_scenes', 'n_accepted_dates',
  'valid_pixel_pct_min', 'valid_pixel_pct_median', 'observation_day_span', 'precip_mm',
  'chirps_resolution_deg', 'chirps_cell_row', 'chirps_cell_col', 'chirps_cell_lon',
  'chirps_cell_lat', 'c1_catalog_candidate_count', 'recovery_catalog_product_count',
  'n_valid_pairs', 'expected_months', 'coverage_fraction', 'mae', 'rmse', 'bias_mean',
  'observed', 'predicted', 'residual', 'from_value', 'to_value', 'change',
  'absolute_change_threshold', 'elapsed_calendar_months', 'unobserved_months_between',
  'n_common_months',
]);
const booleanColumns = new Set(['query_complete', 'quality_review', 'consecutive_calendar_months']);

export function parseCSV(text, schema = {}) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const records = []; let row = []; let value = ''; let quoted = false; let endedQuote = false;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') { value += '"'; i++; }
      else if (char === '"') { quoted = false; endedQuote = true; }
      else value += char;
    } else if (char === '"') {
      if (value || endedQuote) throw new Error('CSV: aspas fora de campo delimitado');
      quoted = true;
    } else if (char === ',' || char === '\n' || char === '\r') {
      row.push(value); value = ''; endedQuote = false;
      if (char !== ',') {
        if (char === '\r' && text[i + 1] === '\n') i++;
        records.push(row); row = [];
      }
    } else {
      if (endedQuote) throw new Error('CSV: conteúdo após aspas finais');
      value += char;
    }
  }
  if (quoted) throw new Error('CSV: campo delimitado não terminado');
  if (value || row.length || endedQuote) { row.push(value); records.push(row); }
  if (!records.length) throw new Error('CSV vazio');
  const headers = records.shift();
  if (headers.some(name => !name) || new Set(headers).size !== headers.length) throw new Error('CSV: cabeçalho inválido');
  return records.map((cells, rowIndex) => {
    if (cells.length !== headers.length) throw new Error(`CSV: linha ${rowIndex + 2} com quantidade de campos inválida`);
    return Object.fromEntries(headers.map((name, i) => {
      let cell = cells[i];
      if (cell === '') return [name, null];
      const definition = schema.properties?.[name] ?? {};
      const types = Array.isArray(definition.type) ? definition.type : [definition.type];
      if (types.includes('boolean') || booleanColumns.has(name)) {
        if (cell !== 'true' && cell !== 'false') throw new Error(`CSV: booleano inválido em ${name}`);
        cell = cell === 'true';
      } else if (types.includes('number') || types.includes('integer') || numericColumns.has(name)) {
        if (!/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(cell) || !Number.isFinite(Number(cell))) {
          throw new Error(`CSV: número inválido em ${name}`);
        }
        cell = Number(cell);
      }
      return [name, cell];
    }));
  });
}
