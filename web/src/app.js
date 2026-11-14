import './style.css';
import { loadPackage } from './data.js';
import { createMap } from './map.js';
import { filterMonthly, coverageState, commonComparison } from './science.js';
import { renderSeries, renderPrecipitation, renderCoverage } from './charts.js';
import mark from './mark.svg';

const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  map:'<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z"/><path d="M9 3v15M15 6v15"/>',
  chart:'<path d="M4 3v17h17M7 14l4-5 4 3 5-7"/>',
  layers:'<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  activity:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  flask:'<path d="M9 3h6M10 3v6L4 19c-1 2 2 2 2 2h12s3 0 2-2L14 9V3M8 14h8"/>',
  book:'<path d="M12 5C8 2 3 3 3 3v16s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2ZM12 5v16"/>',
  arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
  download:'<path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${icons[name] || icons.grid}</svg>`;
const fmt = (value, digits = 0) => value == null ? '—' : new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names = { calendar_month_median:'Mediana sazonal', harmonic_ridge:'Ridge harmônica', previous_year_same_calendar_month:'Mesmo mês de 2023' };
const methods = Object.keys(names);
const repo = 'https://github.com/Altaeir-13/FTL-Final-Project/blob/1440f3e/';
const $ = id => document.getElementById(id);
let data, map, showingAllEvents = false;
const params = new URLSearchParams(location.search);
const state = { pivot:params.get('pivot') || '8087', target:params.get('indice') === 'ndmi' ? 'ndmi_median' : 'ndvi_median', from:'2022-01', to:'2024-12' };
for (const key of ['from','to']) if (/^202[234]-(0[1-9]|1[0-2])$/.test(params.get(key) || '')) state[key] = params.get(key);
if (state.from > state.to) [state.from,state.to] = ['2022-01','2024-12'];

function shell() {
  $('app').innerHTML = `
    <aside class="sidebar">
      <a class="brand" href="#explorar" aria-label="AquaClima início"><img src="${mark}" alt=""/><span>AquaClima<small>OBSERVATÓRIO ESPECTRAL</small></span></a>
      <div class="project-label">WORKSPACE DE PESQUISA</div>
      <nav aria-label="Navegação principal">
        <a class="nav-link active" href="#explorar">${icon('map')}<span>Explorar pivôs</span><span class="nav-count">05</span></a>
        <a class="nav-link" href="#series">${icon('chart')}<span>Séries temporais</span></a>
        <a class="nav-link" href="#cobertura">${icon('grid')}<span>Cobertura e qualidade</span></a>
        <a class="nav-link" href="#mudancas">${icon('activity')}<span>Mudanças espectrais</span></a>
        <a class="nav-link" href="#modelos">${icon('flask')}<span>Modelos e avaliação</span></a>
        <a class="nav-link" href="#metodologia">${icon('book')}<span>Metodologia</span></a>
      </nav>
      <div class="sidebar-study"><span class="eyebrow">ÁREA DE ESTUDO</span><strong>Paracatu, MG</strong><span>Bacia do rio São Marcos</span><div class="study-coordinates">17,5° S &nbsp; 47,1° O</div><span class="study-tag">Cerrado brasileiro</span></div>
      <div class="sidebar-bottom"><div class="science-dot"></div><span>Pesquisa científica<small>5 pivôs de demonstração · Capstone</small></span></div>
    </aside>
    <div class="workspace">
      <header class="topbar"><span class="breadcrumb">AquaClima <span>/</span> <b>Observatório</b></span><span class="topbar-status">${icon('check')} Base científica congelada <span class="version-label">v1.0</span></span></header>
      <main id="main">
        <section id="explorar" class="intro"><div><div class="eyebrow">INTELIGÊNCIA GEOESPACIAL · 2022–2024</div><h1>Um olhar sobre a vegetação irrigada.</h1><p>Explore os históricos espectrais e a qualidade das observações de cinco pivôs centrais.</p></div><a class="secondary-button intro-link" href="#metodologia">Sobre a pesquisa ${icon('arrow')}</a></section>
        <div class="kpi-grid" aria-label="Resumo do estudo">
          <article class="kpi"><span class="kpi-icon">${icon('map')}</span><div><span>Pivôs monitorados</span><strong id="kpi-pivots">—</strong><small>Polígonos reais · ANA</small></div></article>
          <article class="kpi"><span class="kpi-icon">${icon('layers')}</span><div><span>Observações aceitas</span><strong id="kpi-observations">—</strong><small id="kpi-scenes">Sentinel-2 L2A</small></div></article>
          <article class="kpi"><span class="kpi-icon">${icon('grid')}</span><div><span>Cobertura espectral</span><strong id="kpi-coverage">—</strong><small id="kpi-slots">Espaços pivô/mês observados</small></div></article>
          <article class="kpi kpi-period"><span class="kpi-icon">${icon('chart')}</span><div><span>Janela de pesquisa</span><strong>2022<span class="date-dash">—</span>2024</strong><small>ANA · Sentinel-2 · CHIRPS v3</small></div></article>
        </div>
        <section class="filter-bar" aria-label="Filtros sincronizados"><label class="pivot-filter">Pivô selecionado<select id="pivot-select" aria-label="Selecionar pivô"></select></label><div class="filter-divider"></div><div class="period-filter"><span>Período de exploração</span><div class="period-buttons" role="group" aria-label="Atalhos de período"><button data-year="all">Todo o período</button><button data-year="2022">2022</button><button data-year="2023">2023</button><button data-year="2024">2024</button></div></div><details class="custom-period"><summary>Personalizar período</summary><div><label>De <input id="from-month" type="month" min="2022-01" max="2024-12"/></label><label>Até <input id="to-month" type="month" min="2022-01" max="2024-12"/></label><button id="apply-period" class="primary-button">Aplicar</button></div></details><span id="period-error" class="field-error" role="alert"></span></section>
        <div class="geography-grid">
          <section class="card map-card" aria-labelledby="map-title"><div class="card-heading"><div><span class="eyebrow">TERRITÓRIO</span><h2 id="map-title">Área de estudo</h2></div><span class="subtle-badge">${icon('layers')} Polígonos ANA · 2022</span></div><div id="map" aria-label="Mapa dos cinco pivôs centrais"></div><div class="map-caption"><span><i class="legend-swatch"></i> Pivôs centrais <i class="legend-swatch selected-swatch"></i> Selecionado</span><span>Cartografia vetorial · sem imagem de satélite</span></div></section>
          <section class="card pivot-card" aria-labelledby="pivot-title"><div class="card-heading"><div><span class="eyebrow">PIVÔ SELECIONADO</span><h2 id="pivot-title">ANA <span id="selected-id"></span></h2></div><span class="research-badge">Demonstração</span></div><div class="pivot-facts"><div><span>Área delimitada</span><strong id="selected-area">—</strong></div><div><span>Cobertura no período</span><strong id="selected-coverage">—</strong></div></div><div class="coverage-track"><span id="coverage-fill"></span></div><p id="selected-summary" class="quiet"></p><div class="pivot-list-heading">EXPLORAR OS CINCO PIVÔS <span>Área (ha)</span></div><div id="pivot-list" class="pivot-list"></div><div class="context-note">${icon('info')}<span>O destaque indica apenas a seleção. A cor não representa uma condição da irrigação.</span></div></section>
        </div>
        <section id="series" class="chart-grid">
          <article class="card series-card"><div class="card-heading"><div><span class="eyebrow">RESPOSTA ESPECTRAL</span><h2>Histórico da vegetação</h2></div><div class="index-tabs" role="group" aria-label="Índice espectral"><button data-target="ndvi_median">NDVI</button><button data-target="ndmi_median">NDMI</button></div></div><div class="chart-subtitle"><span id="series-context"></span><span class="units">Índice adimensional</span></div><div id="series-chart" class="chart"></div><div class="chart-footer"><span><i class="dot-key"></i> Mediana mensal observada</span><span><i class="gap-key"></i> Lacunas preservadas</span></div><details class="data-details"><summary>Consultar valores, cenas e proveniência</summary><div id="observations-table" class="table-scroll"></div></details></article>
          <article class="card rain-card"><div class="card-heading"><div><span class="eyebrow">CONTEXTO METEOROLÓGICO</span><h2>Precipitação mensal</h2></div><span class="subtle-badge">CHIRPS v3</span></div><div class="chart-subtitle"><span>Uma célula regional compartilhada</span><span class="units">mm/mês</span></div><div id="rain-chart" class="chart"></div><div class="rain-note">Célula de aproximadamente 0,05° para os cinco pivôs. Acumulado mensal completo disponível após o fim do mês; contexto retrospectivo.</div></article>
        </section>
        <section id="cobertura" class="card section-card"><div class="card-heading"><div><span class="eyebrow">TRANSPARÊNCIA DOS DADOS</span><h2>Cobertura e qualidade</h2><p>Cada posição corresponde a um pivô em um mês. Selecione uma célula para examinar a evidência.</p></div><span id="quality-total" class="subtle-badge"></span></div><div id="coverage-chart" class="coverage-chart"></div><p id="coverage-detail" class="detail-note" aria-live="polite">Selecione um mês na matriz de cobertura.</p><p class="quiet quality-rule">Aceitação por cena: ≥ 70% de área válida. Revisão de qualidade: mínimo mensal &lt; 80%. Ausência de observação e aquisição incompleta têm estados próprios.</p></section>
        <section id="mudancas" class="card section-card"><div class="card-heading"><div><span class="eyebrow">EVIDÊNCIAS DESCRITIVAS</span><h2>Mudanças espectrais observadas</h2><p>Diferenças entre meses observados. Cultura, fenologia e manejo podem influenciar os índices.</p></div><span id="events-count" class="subtle-badge"></span></div><div id="events-table" class="table-scroll"></div><button id="more-events" class="text-button">Ver todas as mudanças ${icon('arrow')}</button><div class="context-note">${icon('info')}<span>Uma mudança espectral não comprova falha de irrigação. Intervalos com lacunas não representam uma mudança medida em um único mês.</span></div></section>
        <section id="modelos" class="card section-card"><div class="card-heading"><div><span class="eyebrow">RECONSTRUÇÃO ESPECTRAL EXPLORATÓRIA</span><h2>Modelos e avaliação</h2><p>Treino em 2022–2023 · validação em 2024 · índices adimensionais</p></div><span id="model-index" class="research-badge"></span></div><div id="eligibility" class="eligibility-grid"></div><div class="comparison-heading"><h3>Comparar nos mesmos meses de referência</h3><label>Contraste<select id="comparison-select" aria-label="Contraste de modelos"><option value="all">Três métodos</option><option value="median-naive">Mediana × mesmo mês de 2023</option><option value="median-ridge">Mediana × Ridge</option><option value="ridge-naive">Ridge × mesmo mês de 2023</option></select></label></div><div id="comparison-table" class="table-scroll"></div><p id="comparison-months" class="detail-note"></p><p class="quiet">As métricas desta seção usam os conjuntos congelados de validação em 2024; o filtro de exploração não recalcula métricas. MAE é o erro absoluto médio. RMSE dá maior peso a erros grandes. Menor valor indica maior concordância espectral neste recorte.</p><details class="data-details"><summary>Ver métricas individuais e meses de avaliação</summary><div id="individual-models" class="individual-models"></div></details></section>
        <section id="metodologia" class="methodology"><div class="method-intro"><span class="eyebrow">CIÊNCIA ABERTA, INTERPRETAÇÃO RESPONSÁVEL</span><h2>Os dados têm uma história.<br/>E também limites.</h2><p>Uma demonstração científica com cinco pivôs próximos, sem identificação de cultura e sem rótulos independentes de falhas reais de irrigação.</p><a class="secondary-button" href="${repo}docs/recuperacao-2022.md" target="_blank" rel="noreferrer">Ler o relatório científico ${icon('arrow')}</a></div><div class="method-questions">${methodology()}</div></section>
        <section class="provenance-card"><div><span class="eyebrow">PROVENIÊNCIA VERIFICÁVEL</span><h3>Dataset 2022_2024_recovery_v1</h3><p>Contrato WebGIS 1.0.0 · resultados congelados em 11/11/2026 · hash verificado ao carregar.</p><details><summary>Identificadores de integridade</summary><dl id="package-info"></dl></details></div><a href="./data/manifest.json" download class="secondary-button">${icon('download')} Manifesto público</a></section>
        <footer class="page-footer"><span>AquaClima <b>·</b> Capstone Future Tech Leaders Brasil</span><span>ANA &nbsp; / &nbsp; Sentinel-2 L2A &nbsp; / &nbsp; CHIRPS v3</span><a href="https://github.com/Altaeir-13/FTL-Final-Project" target="_blank" rel="noreferrer">Código e documentação ↗</a></footer>
      </main>
      <div id="announcement" class="sr-only" role="status" aria-live="polite"></div>
    </div>`;
}

function methodology() {
  const items = [
    ['O que NDVI e NDMI representam?', 'NDVI = (NIR − vermelho) / (NIR + vermelho), associado ao vigor e à presença de vegetação. NDMI = (NIR − SWIR) / (NIR + SWIR), sensível ao conteúdo de água da vegetação e à estrutura do dossel. Ambos são adimensionais. Não são medidas diretas de consumo de água ou de eficiência da irrigação.', 'docs/metodologia.md'],
    ['Por que há meses sem observação?', 'Nuvens, sombras, pixels inválidos e disponibilidade dos catálogos limitam as observações. A seleção favorece dias claros e tem distribuição desigual entre as estações. Os meses ausentes são preservados e não recebem valor zero nem imputação.', 'docs/historico.md'],
    ['Como as cenas e os valores são selecionados?', 'A SCL local seleciona classes 4 e 5; cada cena aceita exige ao menos 70% de pixels conjuntos válidos. A seleção padrão usa até duas datas distintas por mês. O agregado mensal é a mediana das medianas espaciais de cenas aceitas, com pesos iguais. A recuperação incorporou somente PB 05.10 aprovado pela auditoria radiométrica.', 'docs/radiometria.md'],
    ['O que a precipitação CHIRPS informa?', 'CHIRPS v3 Final fornece uma estimativa regional do acumulado mensal, em milímetros. Os cinco pivôs compartilham a mesma célula de aproximadamente 0,05°. Esses registros não são cinco estações meteorológicas independentes. O acumulado completo não estava disponível antes do fim do mês.', 'docs/contratos-webgis.md'],
    ['Como funcionam os baselines?', 'A mediana sazonal usa o mesmo mês de dois anos de treino. A Ridge usa dois harmônicos e alpha fixo em 1, exigindo 18 meses e os 12 meses do calendário no treino. O benchmark ingênuo usa o mesmo mês de 2023 para reconstruir 2024. MAE e RMSE só são publicados com ao menos seis meses de referência; comparações usam a interseção dos meses. São reconstruções exploratórias, sem ajuste nesta aplicação.', 'docs/modelagem-recuperada.md'],
    ['Por que uma mudança não é um diagnóstico?', 'Culturas, estágios fenológicos, colheita, manejo, qualidade das cenas e intervalos sem dados podem alterar os índices. Não há rótulos de falhas reais de irrigação nem cultura identificada. Cinco pivôs próximos e séries dependentes não sustentam generalização estatística. O ano de 2025 foi excluído do ajuste e das métricas.', 'docs/recuperacao-2022.md'],
  ];
  return items.map(([title,text,doc]) => `<details><summary>${title}<span aria-hidden="true">+</span></summary><p>${text} <a href="${repo}${doc}" target="_blank" rel="noreferrer">Documento científico ↗</a></p></details>`).join('');
}

function selectPivot(id, mapSource = false) {
  if (!data.pivots.features.some(f => f.properties.pivot_id === id)) return;
  state.pivot = id;
  if (!mapSource) map.select(id);
  render();
  $('announcement').textContent = `Pivô ANA ${id} selecionado. Gráficos, cobertura, mudanças e modelos atualizados.`;
}

function render() {
  const selected = data.pivots.features.find(f => f.properties.pivot_id === state.pivot).properties;
  const rows = filterMonthly(data.monthly,state.pivot,state.from,state.to);
  const qrows = filterMonthly(data.quality,state.pivot,state.from,state.to);
  const present = rows.filter(r => r.monthly_status === 'ok').length;
  $('selected-id').textContent = state.pivot;
  $('selected-area').textContent = `${fmt(selected.area_ha, 2)} ha`;
  $('selected-coverage').textContent = `${fmt(present / rows.length * 100, 1)}%`;
  $('coverage-fill').style.width = `${present / rows.length * 100}%`;
  const limited = qrows.filter(r => coverageState(r) === 'limited').length;
  $('selected-summary').textContent = `${present} de ${rows.length} meses observados · ${rows.reduce((n,r) => n + r.n_accepted_scenes,0)} observações aceitas · ${limited} ${limited === 1 ? 'mês' : 'meses'} com qualidade limitada.`;
  $('pivot-select').value = state.pivot;
  $('from-month').value = state.from;
  $('to-month').value = state.to;
  $('pivot-list').innerHTML = data.pivots.features.map(f => `<button class="pivot-option ${f.properties.pivot_id === state.pivot ? 'selected' : ''}" data-pivot="${esc(f.properties.pivot_id)}" aria-pressed="${f.properties.pivot_id === state.pivot}"><span><i></i> ANA ${esc(f.properties.pivot_id)}</span><span>${fmt(f.properties.area_ha,2)} <b>↗</b></span></button>`).join('');
  document.querySelectorAll('[data-pivot]').forEach(b => b.addEventListener('click', () => selectPivot(b.dataset.pivot)));
  document.querySelectorAll('[data-year]').forEach(b => { const on = b.dataset.year === 'all' ? state.from === '2022-01' && state.to === '2024-12' : state.from === `${b.dataset.year}-01` && state.to === `${b.dataset.year}-12`; b.classList.toggle('active',on); b.setAttribute('aria-pressed',on); });
  document.querySelectorAll('[data-target]').forEach(b => { b.classList.toggle('active', b.dataset.target === state.target); b.setAttribute('aria-pressed', b.dataset.target === state.target); });
  $('series-context').textContent = `ANA ${state.pivot} · ${state.from} a ${state.to}`;
  renderSeries($('series-chart'),rows,state.target,data.observations.filter(r => r.pivot_id === state.pivot),qrows);
  renderPrecipitation($('rain-chart'),filterMonthly(data.precipitation,state.pivot,state.from,state.to));
  renderCoverage($('coverage-chart'),data.monthly,data.quality,data.pivots.features.map(f=>f.properties.pivot_id),state.from,state.to,(id,month) => {
    selectPivot(id);
    const r = data.monthly.find(x => x.pivot_id === id && x.month === month);
    const q = data.quality.find(x => x.pivot_id === id && x.month === month);
    const labels = { valid:'Observação válida', limited:'Qualidade limitada', missing:'Sem observação', incomplete:'Aquisição incompleta' };
    $('coverage-detail').textContent = `ANA ${id} · ${month} · ${labels[coverageState(q)]} · ${r.n_accepted_scenes} cenas aceitas de ${r.n_attempted_scenes} tentativas · área válida mínima: ${r.valid_pixel_pct_min == null ? 'ausente' : fmt(r.valid_pixel_pct_min,1)+'%'} · NDVI ${fmt(r.ndvi_median,4)} · NDMI ${fmt(r.ndmi_median,4)} · lote ${r.batch_status} · consulta ${r.query_complete ? 'completa' : 'incompleta'}.`;
  });
  const allRows = data.monthly.filter(r => r.month >= state.from && r.month <= state.to);
  $('quality-total').textContent = `${allRows.filter(r => r.monthly_status === 'ok').length}/${allRows.length} espaços observados`;
  renderObservationTable(rows,qrows);
  renderEvents();
  renderModels();
  const search = new URLSearchParams({pivot:state.pivot,indice:state.target === 'ndvi_median'?'ndvi':'ndmi',from:state.from,to:state.to});
  history.replaceState(null,'',`${location.pathname}?${search}${location.hash}`);
}

function renderObservationTable(rows, qrows) {
  $('observations-table').innerHTML = `<table><caption>Valores mensais reais e proveniência das cenas</caption><thead><tr><th>Mês</th><th>NDVI</th><th>NDMI</th><th>Cenas</th><th>Área válida mín.</th><th>Qualidade</th><th>Proveniência</th></tr></thead><tbody>${rows.map(r => {
    const q = qrows.find(q => q.month === r.month);
    const obs = data.observations.filter(o => o.pivot_id === state.pivot && o.month === r.month);
    return `<tr><th>${r.month}</th><td>${fmt(r.ndvi_median,4)}</td><td>${fmt(r.ndmi_median,4)}</td><td>${r.n_accepted_scenes}</td><td>${r.valid_pixel_pct_min == null ? '—' : fmt(r.valid_pixel_pct_min,1)+'%'}</td><td>${({valid:'Válida',limited:'Limitada',missing:'Sem observação',incomplete:'Aquisição incompleta'})[coverageState(q)]}</td><td>${obs.length ? `<details><summary>${obs.length} cenas</summary>${obs.map(o => `<div class="scene-evidence"><b>${o.date}</b><br/>${esc(o.scene_id)}<br/>Provedor: ${esc(o.provider ?? o.sentinel_source)}<br/>Coleção: ${esc(o.collection)}<br/>PB: ${esc(o.processing_baseline)}<br/>Método: ${esc(o.radiometric_method)}<br/>Índices: ${fmt(o.ndvi_median,6)} / ${fmt(o.ndmi_median,6)}<br/>Calibração: ${esc(o.calibration_sha256 || 'Não declarada nesta fonte')}</div>`).join('')}</details>` : 'Ausente'}</td></tr>`;
  }).join('')}</tbody></table>`;
}

function renderEvents() {
  const events = data.events.filter(e => e.pivot_id === state.pivot && e.index === state.target && e.from_month >= state.from && e.to_month <= state.to);
  $('events-count').textContent = `${events.length} mudanças · ${state.target === 'ndvi_median'?'NDVI':'NDMI'}`;
  const visible = showingAllEvents ? events : events.slice(0,6);
  $('events-table').innerHTML = events.length ? `<table><caption>ANA ${state.pivot} · mudanças espectrais observadas · ${state.from} a ${state.to}</caption><thead><tr><th>Período</th><th>Índice / pivô</th><th>Inicial → final</th><th>Diferença</th><th>Intervalo</th><th>Meses sem observação</th><th>Proveniência</th></tr></thead><tbody>${visible.map(e => `<tr><th>${e.from_month} → ${e.to_month}</th><td>${e.index === 'ndvi_median'?'NDVI':'NDMI'}<small>ANA ${esc(e.pivot_id)}</small></td><td>${fmt(e.from_value,4)} → ${fmt(e.to_value,4)}</td><td class="delta">${e.change > 0?'+':''}${fmt(e.change,4)}</td><td>${e.elapsed_calendar_months} ${e.elapsed_calendar_months === 1?'mês':'meses'}</td><td>${e.unobserved_months_between}</td><td><details><summary>Ver evidência</summary><p>events.csv · limiar ${fmt(e.absolute_change_threshold,2)} · cenas aceitas: ${e.from_accepted_scenes ?? '—'} → ${e.to_accepted_scenes ?? '—'} · lotes ${esc(e.from_batch_status)} / ${esc(e.to_batch_status)}</p><p class="hash-text">Pacote ${esc(data.manifest.source_package_sha256 || data.manifest.package_sha256)}</p></details></td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">Nenhuma mudança espectral acima do limiar descritivo neste pivô, índice e período. Isso não indica ausência de alterações agronômicas.</div>';
  $('more-events').hidden = events.length <= 6;
  $('more-events').innerHTML = `${showingAllEvents ? 'Mostrar menos' : `Ver todas as ${events.length} mudanças`} ${icon('arrow')}`;
}

function renderModels() {
  $('model-index').textContent = `ANA ${state.pivot} · ${state.target === 'ndvi_median'?'NDVI':'NDMI'}`;
  const individual = data.models.filter(r => r.pivot_id === state.pivot && r.target === state.target);
  $('eligibility').innerHTML = methods.map(method => {
    const r = individual.find(r => r.method === method);
    const ok = r && r.mae != null && r.rmse != null;
    return `<div class="eligibility-item"><span class="status-indicator ${ok?'eligible':'ineligible'}">${ok?'● Elegível':'○ Inelegível'}</span><strong>${names[method]}</strong><span>${ok?`${r.n_valid_pairs} meses de referência em 2024`:'Dados insuficientes para este modelo'}</span>${method === 'harmonic_ridge' && !ok?'<small>O treino não cobre os 12 meses do calendário.</small>':''}</div>`;
  }).join('');
  const group = {all:methods,'median-naive':[methods[0],methods[2]],'median-ridge':[methods[0],methods[1]],'ridge-naive':[methods[1],methods[2]]}[$('comparison-select').value];
  const comparison = commonComparison(data,state.pivot,state.target,group);
  const eligible = comparison.eligible;
  $('comparison-table').innerHTML = `<table><caption>Comparação congelada sobre meses comuns de 2024</caption><thead><tr><th>Método</th><th>MAE ↓</th><th>RMSE ↓</th><th>Meses comuns</th><th>Estado</th></tr></thead><tbody>${group.map(method => {
    const r = comparison.rows.find(r => r.method === method);
    return `<tr><th>${names[method]}</th><td>${eligible ? fmt(r?.mae,4) : '—'}</td><td>${eligible ? fmt(r?.rmse,4) : '—'}</td><td>${r?.n_common_months ?? 0}/12</td><td>${eligible ? '<span class="table-status">Referências comuns</span>' : 'Dados insuficientes para este contraste'}</td></tr>`;
  }).join('')}</tbody></table>`;
  $('comparison-months').textContent = eligible ? `Meses efetivamente comparados: ${comparison.months.join(' · ')}. Mínimo exigido: 6. Nenhum método foi reajustado.` : 'Não há seis meses pontuados por todos os métodos deste contraste. Para este pivô, consulte o contraste mediana × mesmo mês de 2023 quando elegível.';
  $('individual-models').innerHTML = `<p class="quiet">Cada método usa seu próprio conjunto de meses. As métricas abaixo devem ser lidas individualmente; use o quadro de meses comuns para comparações.</p>${methods.map(method => {
    const r = individual.find(r => r.method === method);
    const preds = data.model_predictions.filter(p => p.pivot_id === state.pivot && p.target === state.target && p.method === method && p.residual != null);
    return `<article><h4>${names[method]}</h4><p>MAE ${fmt(r?.mae,6)} · RMSE ${fmt(r?.rmse,6)} · ${r?.n_valid_pairs ?? '—'} meses avaliados · 2024</p><p>Meses: ${preds.length ? preds.map(p=>p.month).join(' · ') : 'dados insuficientes para este modelo'}</p><small>Experimento: ${esc(r?.experiment)} · estado: ${esc(r?.status)}</small></article>`;
  }).join('')}`;
}

function bind() {
  $('pivot-select').addEventListener('change', e => selectPivot(e.target.value));
  document.querySelectorAll('[data-year]').forEach(b => b.addEventListener('click',() => {
    state.from = b.dataset.year === 'all' ? '2022-01' : `${b.dataset.year}-01`;
    state.to = b.dataset.year === 'all' ? '2024-12' : `${b.dataset.year}-12`;
    $('period-error').textContent = ''; showingAllEvents = false; render();
  }));
  document.querySelectorAll('[data-target]').forEach(b => b.addEventListener('click',() => {state.target=b.dataset.target;showingAllEvents=false;render();}));
  $('apply-period').addEventListener('click',() => {
    const from = $('from-month').value, to = $('to-month').value;
    if (!/^202[234]-(0[1-9]|1[0-2])$/.test(from) || !/^202[234]-(0[1-9]|1[0-2])$/.test(to) || from > to) { $('period-error').textContent='Escolha um intervalo válido entre 2022-01 e 2024-12.'; return; }
    state.from=from; state.to=to; $('period-error').textContent=''; showingAllEvents=false; render();
  });
  $('more-events').addEventListener('click',()=>{showingAllEvents=!showingAllEvents;renderEvents();});
  $('comparison-select').addEventListener('change',renderModels);
  document.querySelectorAll('.nav-link').forEach(a => a.addEventListener('click',() => {document.querySelectorAll('.nav-link').forEach(n=>n.classList.toggle('active',n===a));}));
}

async function start() {
  try {
    data = await loadPackage();
    if (!data.pivots.features.some(f=>f.properties.pivot_id===state.pivot)) state.pivot='8087';
    shell();
    $('kpi-pivots').textContent=data.pivots.features.length;
    $('kpi-observations').textContent=data.observations.length;
    $('kpi-scenes').textContent=`${new Set(data.observations.map(r=>r.scene_id)).size} cenas Sentinel-2 L2A`;
    const present = data.monthly.filter(r=>r.monthly_status==='ok').length;
    $('kpi-coverage').textContent=`${fmt(present/data.monthly.length*100,1)}%`;
    $('kpi-slots').textContent=`${present} de ${data.monthly.length} espaços pivô/mês`;
    $('pivot-select').innerHTML=data.pivots.features.map(f=>`<option value="${esc(f.properties.pivot_id)}">ANA ${esc(f.properties.pivot_id)}</option>`).join('');
    $('package-info').innerHTML=`<dt>Pacote científico original</dt><dd>${esc(data.manifest.source_package_sha256 || data.manifest.package_sha256)}</dd><dt>Pacote público derivado</dt><dd>${esc(data.manifest.package_sha256)}</dd><dt>Agregação temporal</dt><dd>Mediana das medianas de cenas aceitas, com pesos iguais.</dd>`;
    map=createMap($('map'),data.pivots,id=>selectPivot(String(id),true));
    bind(); map.select(state.pivot); render();
    if (location.hash) requestAnimationFrame(()=>$(location.hash.slice(1))?.scrollIntoView());
  } catch (error) {
    $('app').innerHTML=`<main class="load-error"><img src="${mark}" alt=""/><h1>Não foi possível abrir o pacote científico.</h1><p>${esc(error.message)}</p><p>Confirme os arquivos do build e sirva a aplicação por HTTP.</p><button onclick="location.reload()">Tentar novamente</button></main>`;
    console.error(error);
  }
}
start();
