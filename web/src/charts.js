import { coverageState, seriesSegments } from './science.js';

const SVG = 'http://www.w3.org/2000/svg';
const ns = (tag, attrs = {}, text) => {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
};
const html = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const fmt = (value, places = 3) => value == null ? 'Ausente' : Number(value).toLocaleString('pt-BR', { minimumFractionDigits: places, maximumFractionDigits: places });
const monthName = month => new Date(`${month}-15T12:00:00Z`).toLocaleDateString('pt-BR', { month: 'short', year: 'numeric', timeZone: 'UTC' }).replace('.', '');
const stateLabels = { valid: 'Observação válida', missing: 'Sem observação', limited: 'Qualidade limitada: revisão', incomplete: 'Aquisição incompleta' };
const stateColors = { valid: '#25816d', missing: '#e5e9e5', limited: '#d5a349', incomplete: '#b1a0c7' };
const sizeObservers = new WeakMap();

function observeSize(container, redraw) {
  if (typeof ResizeObserver === 'undefined' || !container.clientWidth) return;
  const previous = sizeObservers.get(container);
  if (previous) { previous.redraw = redraw; previous.width = container.clientWidth; return; }
  const state = { width: container.clientWidth, redraw };
  state.observer = new ResizeObserver(entries => {
    const width = entries[0]?.contentRect.width;
    if (width && Math.abs(width - state.width) > 1) {
      state.width = width;
      requestAnimationFrame(() => state.redraw());
    }
  });
  sizeObservers.set(container, state);
  state.observer.observe(container);
}

function shell(container, label, height) {
  container.replaceChildren();
  container.style.position = 'relative';
  // Match the SVG coordinate system to its card so text remains readable at real
  // CSS pixel sizes instead of shrinking a 900px canvas into a narrow card.
  const width = Math.max(260, container.clientWidth || 900);
  const layout = { width, height, left: 44, right: 12, plotWidth: width - 56 };
  const svg = ns('svg', { viewBox: `0 0 ${width} ${height}`, role: 'group', 'aria-label': label, width: '100%', height, style: 'display:block;overflow:visible;font-family:inherit;max-width:100%' });
  const tooltip = html('div', '', 'ac-chart-tooltip');
  tooltip.setAttribute('role', 'status');
  Object.assign(tooltip.style, { display: 'none', position: 'absolute', zIndex: '5', maxWidth: '300px', background: '#142e29', color: '#fff', padding: '10px 13px', borderRadius: '7px', pointerEvents: 'none', fontSize: '12px', lineHeight: '1.6', whiteSpace: 'pre-line', boxShadow: '0 5px 20px #0002' });
  container.append(svg, tooltip);
  return { svg, tooltip, layout };
}

function pointInfo(node, label, tooltip, container) {
  node.setAttribute('tabindex', '0');
  node.setAttribute('aria-label', label);
  node.append(ns('title', {}, label));
  const show = event => {
    tooltip.textContent = label;
    tooltip.style.display = 'block';
    const rect = container.getBoundingClientRect?.() ?? { left: 0, top: 0, width: container.clientWidth || 900, height: 262 };
    const nodeRect = node.getBoundingClientRect?.() ?? { left: rect.left, bottom: rect.top };
    const left = event.clientX ? event.clientX - rect.left : nodeRect.left - rect.left;
    const top = event.clientY ? event.clientY - rect.top : nodeRect.bottom - rect.top;
    const padding = 8;
    // Measure after showing the text, with a stable available width. Cards clip
    // overflow, so a tooltip near the bottom must open above its observed point.
    tooltip.style.boxSizing = 'border-box';
    tooltip.style.maxWidth = `${Math.min(300, Math.max(0, rect.width - padding * 2))}px`;
    tooltip.style.left = `${padding}px`;
    tooltip.style.top = `${padding}px`;
    const measured = tooltip.getBoundingClientRect?.();
    const width = measured?.width || tooltip.offsetWidth || Math.min(300, rect.width - padding * 2);
    const height = measured?.height || tooltip.offsetHeight || 120;
    const below = top + 12;
    const preferredTop = below + height <= rect.height - padding ? below : top - height - 12;
    tooltip.style.left = `${Math.max(padding, Math.min(left + 10, rect.width - width - padding))}px`;
    tooltip.style.top = `${Math.max(padding, Math.min(preferredTop, rect.height - height - padding))}px`;
  };
  const hide = () => { tooltip.style.display = 'none'; };
  node.addEventListener('pointerenter', show);
  node.addEventListener('focus', show);
  node.addEventListener('pointerleave', hide);
  node.addEventListener('blur', hide);
  node.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
}

function axes(svg, rows, y, tickValues, formatter, layout, unit) {
  const { width, height, left, right, plotWidth } = layout;
  for (const value of tickValues) {
    const position = y(value);
    svg.append(ns('line', { x1: left, x2: width - right, y1: position, y2: position, stroke: '#e7ece7', 'stroke-dasharray': value === 0 ? '' : '3 4' }));
    svg.append(ns('text', { x: left - 10, y: position + 4, 'text-anchor': 'end', fill: '#65776b', 'font-size': '11' }, formatter(value)));
  }
  svg.append(ns('text', { x: left, y: 13, fill: '#65776b', 'font-size': 10 }, unit));
  const maxLabels = Math.max(2, Math.floor(plotWidth / 54));
  const step = [1, 2, 3, 6, 12, 24].find(value => value >= rows.length / maxLabels) ?? 36;
  rows.forEach((row, index) => {
    const x = left + (index + .5) * (plotWidth / Math.max(rows.length, 1));
    const previousRegularTick = Math.floor(index / step) * step;
    const showLast = index === rows.length - 1 && index - previousRegularTick >= step * .65;
    if (index % step === 0 || showLast) {
      const label = `${monthName(row.month).slice(0, 3)}/${row.month.slice(2, 4)}`;
      svg.append(ns('text', { x: Math.max(left + 18, Math.min(width - right - 18, x)), y: height - 10, 'text-anchor': 'middle', fill: '#65776b', 'font-size': '11' }, label));
    }
    if (row.month.endsWith('-01') && index > 0) svg.append(ns('line', { x1: x - plotWidth / rows.length / 2, x2: x - plotWidth / rows.length / 2, y1: 24, y2: height - 35, stroke: '#cbd6cd', 'stroke-dasharray': '3 5' }));
  });
}

function empty(container) {
  container.replaceChildren(html('p', 'Nenhum mês disponível no período selecionado.', 'ac-empty'));
}

export function renderSeries(container, rows, target, observations = [], quality = []) {
  observeSize(container, () => renderSeries(container, rows, target, observations, quality));
  if (!rows.length) { empty(container); return; }
  const ordered = rows.slice().sort((a, b) => a.month.localeCompare(b.month));
  const indexLabel = target === 'ndmi_median' ? 'NDMI' : 'NDVI';
  const { svg, tooltip, layout } = shell(container, `Série mensal de ${indexLabel}; lacunas permanecem sem linha`, 262);
  const x = row => layout.left + (ordered.findIndex(value => value.month === row.month) + .5) * layout.plotWidth / ordered.length;
  const y = value => 24 + (1 - value) * 100;
  axes(svg, ordered, y, [-1, -.5, 0, .5, 1], value => fmt(value, 1), layout, `${indexLabel} · adimensional`);
  const widths = layout.plotWidth / ordered.length;
  const qualityMap = new Map(quality.map(row => [`${row.pivot_id}/${row.month}`, row]));
  for (const row of ordered) {
    if (row[target] == null || row.monthly_status !== 'ok') {
      const missing = ns('rect', { x: x(row) - widths * .42, y: 25, width: widths * .84, height: 199, fill: '#e7ebe5', opacity: '.65', rx: 2 });
      pointInfo(missing, `${monthName(row.month)}\n${indexLabel}: ausente\n${stateLabels[coverageState(row)]}\n${row.n_accepted_scenes ?? 0} cenas aceitas`, tooltip, container);
      svg.append(missing);
    }
  }
  for (const segment of seriesSegments(ordered, target)) {
    if (segment.length > 1) svg.append(ns('path', { d: segment.map((row, i) => `${i ? 'L' : 'M'}${x(row)},${y(row[target])}`).join(' '), fill: 'none', stroke: '#227d68', 'stroke-width': 2.5, 'stroke-linejoin': 'round' }));
  }
  for (const row of ordered) {
    if (row.monthly_status !== 'ok' || row[target] == null) continue;
    const qualityRow = qualityMap.get(`${row.pivot_id}/${row.month}`) ?? row;
    const limited = coverageState(qualityRow) === 'limited';
    const circle = ns('circle', { cx: x(row), cy: y(row[target]), r: 4.6, fill: limited ? '#d5a349' : '#227d68', stroke: '#fff', 'stroke-width': 2, 'data-month': row.month, 'data-value': row[target], 'data-target': target });
    const accepted = observations.filter(obs => obs.pivot_id === row.pivot_id && obs.month === row.month);
    const dates = accepted.length ? accepted.map(obs => obs.date).join(', ') : [row.first_observation_date, row.last_observation_date].filter(Boolean).join(' a ');
    const label = `${monthName(row.month)} · ANA ${row.pivot_id}\n${indexLabel}: ${fmt(row[target], 4)} (adimensional)\n${row.n_accepted_scenes} cenas aceitas\nPixels válidos mínimos: ${fmt(qualityRow.valid_pixel_pct_min, 1)}%\n${stateLabels[coverageState(qualityRow)]}${dates ? `\nDatas: ${dates}` : ''}`;
    pointInfo(circle, label, tooltip, container);
    svg.append(circle);
  }
  const note = html('div', undefined, 'ac-chart-legend');
  Object.assign(note.style, { display: 'flex', flexWrap: 'wrap', gap: '16px', fontSize: '11px', color: '#65766b', padding: '4px 0 0 12px' });
  note.append(html('span', '● Mediana mensal observada'), html('span', '● Revisão de qualidade (<80% válidos)'), html('span', '▥ Faixa cinza: mês sem observação'));
  note.children[0].style.color = '#227d68'; note.children[1].style.color = '#a47727';
  container.append(note);
}

export function renderPrecipitation(container, rows) {
  observeSize(container, () => renderPrecipitation(container, rows));
  if (!rows.length) { empty(container); return; }
  const ordered = [...new Map(rows.map(row => [row.month, row])).values()].sort((a, b) => a.month.localeCompare(b.month));
  const { svg, tooltip, layout } = shell(container, 'Precipitação mensal regional CHIRPS em milímetros acumulados', 190);
  const maximum = Math.max(100, ...ordered.filter(row => row.precip_mm != null).map(row => row.precip_mm));
  const top = Math.ceil(maximum / 100) * 100;
  const y = value => 25 + (1 - value / top) * 120;
  axes(svg, ordered, y, [0, top / 2, top], value => fmt(value, 0), layout, 'CHIRPS · mm/mês');
  const width = layout.plotWidth / ordered.length;
  for (let i = 0; i < ordered.length; i++) {
    const row = ordered[i];
    const valid = row.precip_status === 'ok' && row.precip_mm != null;
    const bar = ns('rect', { x: layout.left + i * width + width * .18, y: valid ? y(row.precip_mm) : 25, width: width * .64, height: valid ? Math.max(0, 145 - y(row.precip_mm)) : 120, fill: valid ? '#80a6bc' : '#e5e9e5', rx: 2, 'data-month': row.month, 'data-value': valid ? row.precip_mm : '', 'data-unit': 'mm' });
    pointInfo(bar, `${monthName(row.month)}\n${valid ? `${fmt(row.precip_mm, 2)} mm acumulados` : 'Precipitação ausente'}\nCélula regional compartilhada (~0,05°)\nAcumulado completo após o encerramento do mês`, tooltip, container);
    svg.append(bar);
  }
}

export function renderCoverage(container, allMonthly, quality, pivotIds, from = '2022-01', to = '2024-12', onSelect = () => {}) {
  container.replaceChildren();
  const rows = allMonthly.filter(row => row.month >= from && row.month <= to);
  const months = [...new Set(rows.map(row => row.month))].sort();
  if (!months.length) { empty(container); return; }
  const qualityMap = new Map(quality.map(row => [`${row.pivot_id}/${row.month}`, row]));
  const monthlyMap = new Map(rows.map(row => [`${row.pivot_id}/${row.month}`, row]));
  const scroll = html('div', undefined, 'ac-coverage-scroll');
  Object.assign(scroll.style, { overflowX: 'auto', maxWidth: '100%', paddingBottom: '6px' });
  const table = html('table', undefined, 'ac-coverage-table');
  Object.assign(table.style, { width: '100%', minWidth: `${110 + months.length * 21}px`, borderSpacing: '3px', borderCollapse: 'separate', fontSize: '10px', textAlign: 'center' });
  const caption = html('caption', 'Cobertura espectral mensal por pivô; selecione uma célula para explorar seu pivô.');
  Object.assign(caption.style, { textAlign: 'left', color: '#758378', paddingBottom: '10px', fontSize: '11px' });
  table.append(caption);
  const thead = html('thead'), years = html('tr'), labels = html('tr');
  const corner = html('th', 'PIVÔ ANA'); corner.rowSpan = 2;
  Object.assign(corner.style, { textAlign: 'left', width: '88px', color: '#6e7d73', fontWeight: '500' });
  years.append(corner);
  for (const year of [...new Set(months.map(month => month.slice(0, 4)))]) {
    const th = html('th', year); th.colSpan = months.filter(month => month.startsWith(year)).length;
    Object.assign(th.style, { paddingBottom: '5px', color: '#516559', fontSize: '11px', fontWeight: '500' }); years.append(th);
  }
  for (const month of months) { const th = html('th', monthName(month).slice(0, 3)); th.scope = 'col'; th.title = monthName(month); th.style.fontWeight = '400'; th.style.color = '#849087'; labels.append(th); }
  thead.append(years, labels); table.append(thead);
  const body = html('tbody');
  for (const pivot of pivotIds) {
    const pivotId = String(typeof pivot === 'object' ? pivot.pivot_id ?? pivot.properties?.pivot_id : pivot);
    const tr = html('tr');
    const th = html('th', pivotId); th.scope = 'row'; Object.assign(th.style, { textAlign: 'left', fontSize: '12px', paddingRight: '10px', fontWeight: '500', color: '#345246' }); tr.append(th);
    for (const month of months) {
      const row = qualityMap.get(`${pivotId}/${month}`) ?? monthlyMap.get(`${pivotId}/${month}`);
      const state = coverageState(row);
      const td = html('td'), button = html('button', '', `ac-coverage-cell ac-coverage-${state}`);
      button.type = 'button'; button.dataset.state = state; button.dataset.month = month; button.dataset.pivot = pivotId;
      const label = `ANA ${pivotId} · ${monthName(month)}: ${stateLabels[state]}. ${row?.n_accepted_scenes ?? 0} cenas aceitas${row?.valid_pixel_pct_min != null ? `; mínimo ${fmt(row.valid_pixel_pct_min, 1)}% de pixels válidos` : ''}.`;
      button.title = label; button.setAttribute('aria-label', label);
      Object.assign(button.style, { display: 'block', width: '100%', minWidth: '16px', height: '22px', background: stateColors[state], border: '0', borderRadius: '3px', cursor: 'pointer' });
      if (state === 'missing') button.style.backgroundImage = 'repeating-linear-gradient(135deg,transparent,transparent 3px,#cfd6ce 3px,#cfd6ce 4px)';
      button.addEventListener('click', () => onSelect(pivotId, month));
      td.append(button); tr.append(td);
    }
    body.append(tr);
  }
  table.append(body); scroll.append(table); container.append(scroll);
  const legend = html('div', undefined, 'ac-coverage-legend');
  Object.assign(legend.style, { display: 'flex', flexWrap: 'wrap', gap: '15px', paddingTop: '12px', fontSize: '11px', color: '#6b7d71' });
  for (const [state, label] of Object.entries(stateLabels)) {
    const item = html('span'); Object.assign(item.style, { display: 'inline-flex', gap: '6px', alignItems: 'center' });
    const swatch = html('span'); Object.assign(swatch.style, { width: '9px', height: '9px', borderRadius: '2px', background: stateColors[state], border: state === 'missing' ? '1px solid #b9c4b7' : '0' });
    item.append(swatch, document.createTextNode(label)); legend.append(item);
  }
  container.append(legend);
}
