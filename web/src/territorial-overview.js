import brazil from './brazil-states.json' with { type: 'json' };

// Presentation metadata only. Scientific packages and their coordinates are unchanged.
export const TERRITORIAL_SOURCE = Object.freeze({
  version: '1.0.0',
  referenceDate: '2026-11-16',
  name: 'IBGE · malha simplificada de Unidades da Federação · referência 2022',
  url: 'https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?intrarregiao=UF&formato=application/vnd.geo%2Bjson&qualidade=minima&periodo=2022',
  sha256: '07c671aa87aa1ab296c446de6294df9827112782537b996c0a160284907e7c0f',
  bytes: 98502,
  crs: 'EPSG:4326',
  projection: 'Equiretangular, latitude/longitude; visão de contexto sem medição de distâncias.',
  attribution: 'Fonte: IBGE, API de malhas geográficas. Simplificação mínima fornecida pelo produtor; uso de contexto territorial.',
});

export const TERRITORIAL_POINTS = Object.freeze([
  Object.freeze({ id: 'caxias-ma', label: 'Caxias, MA', role: 'Origem e motivação regional', status: 'origin',
    coordinates: Object.freeze([-43.358539429000018, -4.8616749898404166]), reference: 'Sede municipal pública · código IBGE 2103000',
    source: 'https://portal1.snirh.gov.br/arcgis/rest/services/DADOSABERTOS/Sede_Municipais/MapServer/0',
    description: 'Origem territorial do pesquisador. Não há observações espectrais processadas de Caxias neste aplicativo.', studyId: null }),
  Object.freeze({ id: 'paracatu-mg', label: 'Paracatu, MG', role: 'Estudo científico concluído', status: 'completed',
    coordinates: Object.freeze([-47.13244427899997, -17.518604780499942]), reference: 'Centro da extensão dos cinco polígonos ANA publicados; não é a sede municipal',
    source: 'https://github.com/Altaeir-13/FTL-Final-Project/blob/ffb7ba41d5286fd58c47acd8007903fd38b799d4/web/data/packages/7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d/pivots.geojson',
    description: 'Validação científica concluída em cinco pivôs. Histórico de 2022–2024 e modelos congelados.', studyId: 'paracatu-mg' }),
  Object.freeze({ id: 'guadalupe-pi', label: 'Guadalupe, PI', role: 'Prova exploratória de portabilidade', status: 'exploratory',
    coordinates: Object.freeze([-43.602979431999984, -6.796705381999942]), reference: 'Centro da extensão dos cinco polígonos ANA publicados; não é a sede municipal',
    source: 'https://github.com/Altaeir-13/FTL-Final-Project/blob/ffb7ba41d5286fd58c47acd8007903fd38b799d4/docs/evidencias/guadalupe-pi/pivots.geojson',
    description: 'Procedimento executado em cinco pivôs e seis datas de 2023–2024. Sem modelo regional validado.', studyId: 'guadalupe-pi' }),
]);

const labels = { '21': 'MA', '22': 'PI', '31': 'MG' };
const svgNS = 'http://www.w3.org/2000/svg';
export function projectTerritorialPoint([longitude, latitude]) {
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) throw new TypeError('Coordenada territorial inválida.');
  return [28 + (longitude + 74) * 10.45, 24 + (6 - latitude) * 10.45];
}

export function territorialPath(geometry) {
  if (!['Polygon', 'MultiPolygon'].includes(geometry?.type)) throw new TypeError('Geometria territorial incompatível.');
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  return polygons.flatMap(polygon => polygon.map(ring => ring.map((point, i) => {
    const [x, y] = projectTerritorialPoint(point);
    return `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ') + ' Z')).join(' ');
}

function svgElement(name, attributes = {}, value) {
  const element = document.createElementNS(svgNS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  if (value != null) element.textContent = value;
  return element;
}

export function mountTerritorialOverview(container, { onOpenStudy = () => {} } = {}) {
  container.classList.add('territorial-overview');
  container.setAttribute('aria-labelledby', 'territorial-title');
  container.innerHTML = `<div class="territorial-heading"><div><span class="eyebrow">TRAJETÓRIA DO PROJETO · BRASIL</span><h2 id="territorial-title">Caxias → Paracatu → Guadalupe</h2><p>Três territórios, três papéis na pesquisa.</p></div><span class="subtle-badge">Contexto territorial · sem cobertura nacional</span></div><div class="territorial-layout"><div class="territorial-map-container"></div><div class="territorial-locations"><div class="territorial-legend" aria-label="Legenda dos papéis territoriais"></div><p class="territorial-point-detail" role="status"></p><details><summary>Fontes e referências geográficas</summary><div class="territorial-sources"></div></details></div></div><p class="territorial-narrative">O AquaClima iniciou sua validação em Paracatu, Minas Gerais, onde a concentração de pivôs facilitou a construção e a auditoria do pipeline. Em seguida, a metodologia foi aplicada exploratoriamente a Guadalupe, no Piauí, após uma seleção territorial orientada por dados oficiais. Essa expansão aproxima a pesquisa da região de Caxias, Maranhão.</p><p class="territorial-footnote">Os marcadores representam a sede pública de Caxias e a localização das amostras de pivôs. A trajetória indica a motivação e as etapas da pesquisa; não representa rotas, expansão operacional ou validação em todo o Brasil.</p>`;
  const mapContainer = container.querySelector('.territorial-map-container');
  const legend = container.querySelector('.territorial-legend');
  const detail = container.querySelector('.territorial-point-detail');
  const sources = container.querySelector('.territorial-sources');
  const svg = svgElement('svg', { viewBox: '0 0 500 470', 'aria-labelledby': 'territorial-map-title territorial-map-description', role: 'group' });
  svg.append(svgElement('title', { id: 'territorial-map-title' }, 'Brasil: estados e três referências territoriais do AquaClima'));
  svg.append(svgElement('desc', { id: 'territorial-map-description' }, 'Caxias no Maranhão é a origem do pesquisador; Paracatu em Minas Gerais tem estudo científico concluído; Guadalupe no Piauí tem prova exploratória. Use Tab e Enter nos marcadores para explorar.'));
  for (const feature of brazil.features) {
    const code = String(feature.properties.codarea);
    const path = svgElement('path', { d: territorialPath(feature.geometry), class: `territorial-state${labels[code] ? ' territorial-state-highlight' : ''}`, 'fill-rule': 'evenodd' });
    path.append(svgElement('title', {}, `Unidade da Federação · código IBGE ${code}${labels[code] ? ` · ${labels[code]}` : ''}`));
    svg.append(path);
  }
  for (const [code, location] of Object.entries({ '21': [-45.8, -5.9], '22': [-41.5, -9.3], '31': [-44.8, -19.5] })) {
    const [x, y] = projectTerritorialPoint(location);
    svg.append(svgElement('text', { x, y, class: 'territorial-uf-label', 'aria-hidden': 'true' }, labels[code]));
  }
  const markers = new Map();
  const buttons = new Map();
  const activate = point => {
    detail.textContent = `${point.label}: ${point.description}`;
    markers.forEach((marker, id) => marker.setAttribute('aria-pressed', String(id === point.id)));
    buttons.forEach((button, id) => button.setAttribute('aria-pressed', String(id === point.id)));
    if (point.studyId) onOpenStudy(point.studyId);
  };
  for (const point of TERRITORIAL_POINTS) {
    const [x, y] = projectTerritorialPoint(point.coordinates);
    const marker = svgElement('g', { class: `territorial-marker ${point.status}`, tabindex: '0', role: 'button', 'aria-label': `${point.label}: ${point.role}${point.studyId ? '. Abrir investigação.' : '. Sem dados espectrais.'}`, 'aria-pressed': 'false' });
    marker.append(svgElement('circle', { cx: x, cy: y, r: 13, class: 'territorial-marker-halo' }));
    marker.append(point.status === 'origin' ? svgElement('path', { d: `M${x},${y - 7} L${x + 7},${y + 6} L${x - 7},${y + 6} Z` }) : point.status === 'exploratory' ? svgElement('path', { d: `M${x},${y - 8} L${x + 8},${y} L${x},${y + 8} L${x - 8},${y} Z` }) : svgElement('circle', { cx: x, cy: y, r: 7 }));
    const offsetY = point.status === 'origin' ? -15 : point.status === 'exploratory' ? 22 : 7;
    marker.append(svgElement('text', { x: x + 15, y: y + offsetY, class: 'territorial-marker-label' }, point.label));
    marker.addEventListener('click', () => activate(point));
    marker.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(point); } });
    svg.append(marker); markers.set(point.id, marker);
    const button = document.createElement('button'); button.type = 'button'; button.className = `territorial-location ${point.status}`; button.dataset.territory = point.id; button.setAttribute('aria-pressed', 'false');
    const name = document.createElement('strong'); name.textContent = `${point.status === 'origin' ? '△' : point.status === 'exploratory' ? '◇' : '●'} ${point.label}`;
    const role = document.createElement('span'); role.textContent = point.role;
    const action = document.createElement('small'); action.textContent = point.studyId ? 'Abrir investigação →' : 'Referência pública · sem dados espectrais';
    button.append(name, role, action); button.addEventListener('click', () => activate(point)); legend.append(button); buttons.set(point.id, button);
    const source = document.createElement('p'); const link = document.createElement('a'); link.href = point.source; link.target = '_blank'; link.rel = 'noreferrer'; link.textContent = `${point.label} · fonte ↗`; source.append(link, document.createTextNode(`. ${point.reference}. WGS84: ${point.coordinates.join(', ')}.`)); sources.append(source);
  }
  const attribution = document.createElement('p'); const link = document.createElement('a'); link.href = TERRITORIAL_SOURCE.url; link.target = '_blank'; link.rel = 'noreferrer'; link.textContent = TERRITORIAL_SOURCE.name; attribution.append(link, document.createTextNode(`. ${TERRITORIAL_SOURCE.projection} Camada de apresentação ${TERRITORIAL_SOURCE.version}. SHA-256: ${TERRITORIAL_SOURCE.sha256}.`)); sources.prepend(attribution);
  const attributionCaption = document.createElement('p'); attributionCaption.className = 'territorial-map-attribution'; attributionCaption.textContent = 'IBGE · UF 2022 · projeção equiretangular · dados locais';
  mapContainer.append(svg, attributionCaption);
  detail.textContent = 'Escolha Paracatu ou Guadalupe para abrir uma investigação com dados reais. Caxias indica somente a origem e a motivação regional.';
  return { select(id) { const point = TERRITORIAL_POINTS.find(point => point.id === id); if (point) activate(point); } };
}
