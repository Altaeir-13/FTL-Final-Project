import { loadRegions } from './regions.js';
import { createMap } from './map.js';
import { renderSeries, renderPrecipitation } from './charts.js';
import { filterMonthly } from './science.js';

const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));
const fmt = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const documents = 'https://github.com/Altaeir-13/FTL-Final-Project/blob/main/docs/';

export async function mountStudies(container, { onStudy = () => {}, onPivot = () => {} } = {}) {
  try {
    const { catalog, evidence, images } = await loadRegions();
    const imageURLs = images.map(image => ({ ...image, url: URL.createObjectURL(new Blob([image.bytes], { type: 'image/png' })) }));
    window.addEventListener('pagehide', event => { if (!event.persisted) imageURLs.forEach(image => URL.revokeObjectURL(image.url)); });
    const { selection, pilot } = evidence;
    const winner = selection.winner;
    const exploratory = catalog.regional.status === 'exploratory_portability';
    container.innerHTML = `
      <div class="studies-heading"><div><span class="eyebrow">DO TERRITÓRIO À EVIDÊNCIA</span><h2 id="studies-title">Dois estudos, diferentes níveis de evidência.</h2></div><label>Explorar estudo<select id="study-select"><option value="paracatu-mg">Paracatu, MG · concluído</option><option value="guadalupe-pi">Guadalupe, PI · ${exploratory ? 'exploratório' : 'seleção territorial'}</option></select></label></div>
      <div class="study-cards"><article class="study-card completed"><div><span class="study-state">ESTUDO CONCLUÍDO</span><span class="study-number">01</span></div><h3>Paracatu, MG</h3><p>Pipeline desenvolvido e avaliado em um polo consolidado de irrigação.</p><strong>5 pivôs · 256 observações · 2022–2024</strong><p>Modelos e métricas congelados. Explore o mapa, as lacunas e a avaliação abaixo.</p><button data-study="paracatu-mg" aria-pressed="true">Consultar estudo de Paracatu <span aria-hidden="true">↗</span></button></article>
      <article class="study-card exploratory"><div><span class="study-state">${exploratory ? 'PROVA EXPLORATÓRIA' : 'SELEÇÃO TERRITORIAL'}</span><span class="study-number">02</span></div><h3>Guadalupe, PI</h3><p>Expansão investigada a partir de Caxias, Maranhão, com critérios registrados.</p><strong>${winner.ana_count} pivôs ANA · ${evidence.pivots.features.length} na amostra · ${fmt(winner.caxias_km, 0)} km de Caxias</strong><p>${exploratory ? `${pilot.summary.accepted_observations} observações reais; prova de portabilidade sem modelos regionais.` : 'Inventário e disponibilidade de cenas conferidos. A seleção ainda não demonstra monitoramento.'}</p><button data-study="guadalupe-pi" aria-pressed="false">Consultar investigação regional <span aria-hidden="true">↗</span></button></article></div>
      <div id="paracatu-study-detail" class="study-summary"><strong>Você está no estudo concluído de Paracatu.</strong><p>Os filtros do observatório abaixo se referem exclusivamente a Paracatu, MG. Versão <code>2022_2024_recovery_v1</code>, contrato WebGIS 1.0.0.</p><a href="#explorar">Abrir observatório de Paracatu ↓</a></div>
      <div id="regional-study-detail" class="regional-detail" hidden><div class="regional-intro"><div><span class="eyebrow">GUADALUPE · PIAUÍ</span><h3>${exploratory ? 'Portabilidade observada em uma amostra regional.' : 'Uma região selecionada, antes da validação por pixel.'}</h3><p>${exploratory ? 'NDVI, NDMI e chuva descrevem esta prova limitada. Não foram ajustados modelos nem calculadas métricas de generalização regional.' : 'As geometrias e as cenas em catálogo tornam a prova viável; nuvens e calibração ainda precisam ser verificadas no processamento.'}</p></div><span class="regional-status">${exploratory ? 'Exploratório · não generalizado' : 'Auditoria territorial concluída'}</span></div>
      <div class="regional-kpis"><div><strong>${winner.eligible_count}/${winner.ana_count}</strong><span>Pivôs válidos com ≥25 ha</span></div><div><strong>${fmt(winner.scores.weighted_total * 100, 2)}</strong><span>Pontuação de seleção /100</span></div><div><strong>${winner.usable_dates}</strong><span>Datas preliminares em catálogo</span></div><div><strong>${fmt(winner.cluster_radius_m / 1000, 2)} km</strong><span>Raio do grupo selecionado</span></div></div>
      <p class="regional-note">As ${winner.usable_months.length} posições mensais com cenas preliminares não equivalem a meses com índices aceitos. Distância de ${fmt(winner.caxias_km, 2)} km em linha reta até a sede pública de Caxias.</p>
      <div class="regional-geography"><div id="regional-map"></div><div class="regional-pivots"><h4>Polígonos reais ANA · 2022</h4><label>Pivô de Guadalupe<select id="regional-pivot-select">${evidence.pivots.features.map(feature => `<option value="${esc(feature.properties.pivot_id)}">${esc(feature.properties.pivot_id)} · ${fmt(feature.properties.area_ha, 2)} ha</option>`).join('')}</select></label><p id="regional-pivot-description"></p><p>Cartografia vetorial em WGS84, sem imagem de satélite ou basemap externo. Os polígonos não indicam atividade de irrigação na data da demonstração.</p><span class="regional-status">Dados separados de Paracatu</span></div></div>
      ${evidence.comparison ? `<section class="regional-image-comparison" aria-labelledby="comparison-images-title"><span class="eyebrow">DUAS DATAS · MESMA ÁREA · MESMA ESCALA VISUAL</span><h3 id="comparison-images-title">Imagens Sentinel-2 reais em falsa cor.</h3><p>Vermelho = infravermelho próximo (B08), verde = vermelho (B04), azul = SWIR1 (B11). Contornos e rótulos correspondem aos cinco polígonos ANA selecionados.</p><div class="regional-image-pair">${evidence.comparison.scenes.map(scene => `<figure><img src="${imageURLs.find(image => image.scene_id === scene.scene_id).url}" alt="Composição falsa cor Sentinel-2 de Guadalupe em ${scene.date}, com contornos ANA dos cinco pivôs."/><figcaption><strong>${scene.date}</strong><span>100% de pixels conjuntos válidos em cada pivô</span><details><summary>Aquisição e georreferência</summary><p>${esc(scene.scene_id)}<br/>${esc(scene.crs)} · pixel de 20 m · PB ${esc(scene.processing_baseline)}</p><p><a href="${esc(scene.source)}" target="_blank" rel="noreferrer">Item original Earth Search ↗</a></p><p class="hash-text">PNG SHA-256: ${scene.image_sha256}</p></details></figcaption></figure>`).join('')}</div><p class="image-comparison-note">Mesma grade georreferenciada em EPSG:32723 e estiramento fixo de reflectância 0–0,6 nas duas datas. Bandas de 10 m agregadas à grade de 20 m; pixels fora das classes SCL 4/5 ou com reflectância inválida aparecem em cinza. Os PNGs são derivados visuais, sem uso analítico. As cores não diagnosticam falhas de irrigação.</p></section>` : ''}
      ${exploratory ? `<section class="regional-observations"><div class="regional-chart-heading"><div><h3>Índices reais da prova regional</h3><p>${pilot.summary.accepted_observations} observações de ${pilot.summary.accepted_scenes} cenas · ${pilot.summary.observed_months.length} meses com índices · ${pilot.summary.observed_pivot_months}/${pilot.summary.calendar_slots} espaços pivô/mês observados (${fmt(pilot.summary.observed_pivot_months / pilot.summary.calendar_slots * 100, 1)}% da grade contínua)</p></div><label>Índice regional<select id="regional-index"><option value="ndvi_median">NDVI</option><option value="ndmi_median">NDMI</option></select></label></div><p class="regional-note">Meses alvo: ${pilot.summary.target_months.join(' · ')}. A grade contínua preserva meses não adquiridos e observações rejeitadas; as lacunas não são preenchidas.</p><div class="regional-charts"><div><h4>Resposta espectral · adimensional</h4><div id="regional-series-chart" class="chart"></div></div><div><h4>Contexto CHIRPS v3 · mm/mês</h4><div id="regional-rain-chart" class="chart"></div></div></div><p class="regional-note">Precipitação é estimativa regional; não mede consumo do pivô. Poucas datas não demonstram sazonalidade anual. Cenas aceitas exigem ≥70% de pixels válidos.</p><details class="data-details"><summary>Ver tentativas, rejeições, índices e proveniência regional</summary><div id="regional-observation-table" class="table-scroll"></div></details><div class="regional-reproduction"><strong>Reprodução offline: ${pilot.offline.files_checked} arquivos idênticos, zero requisições HTTP.</strong><span>${fmt(pilot.execution.transferred_bytes / 1e6, 2)} MB transferidos nesta aquisição · ${fmt(pilot.execution.stored_bytes / 1e6, 2)} MB armazenados localmente</span></div></section>` : ''}
      <details class="regional-audit"><summary>Comparar os ${selection.comparison.length} municípios investigados</summary><div class="table-scroll"><table><caption>Inventário ANA e pontuação territorial MA/PI</caption><thead><tr><th>Município</th><th>Pivôs ANA</th><th>Elegíveis ≥25 ha</th><th>Distância Caxias</th><th>Meses preliminares /24</th><th>Escore /100</th></tr></thead><tbody>${selection.comparison.map(row => `<tr><th>${esc(row.name)}, ${row.UF}</th><td>${row.ana_count}</td><td>${row.eligible_count}</td><td>${row.caxias_km == null ? '—' : `${fmt(row.caxias_km, 1)} km`}</td><td>${row.usable_months?.length ?? 'Não consultado'}</td><td>${row.scores ? fmt(row.scores.weighted_total * 100, 2) : 'Inelegível'}</td></tr>`).join('')}</tbody></table></div><p>Pesos: geometria 25%, disponibilidade 25%, continuidade 20%, proximidade 15%, custo 15%. As fórmulas e evidências estão no <a href="${documents}selecao-regional-ma-pi.md" target="_blank" rel="noreferrer">relatório de seleção ↗</a>.</p></details>
      <div class="regional-provenance"><p><strong>Fonte:</strong> <a href="${esc(selection.source)}" target="_blank" rel="noreferrer">ANA/SNIRH Pivôs Centrais 2022 ↗</a> · seleção registrada antes da aquisição. Caxias é a referência territorial; zero registros associados na edição consultada não significa ausência de irrigação.</p><details><summary>Integridade e proveniência deste estudo</summary><p>Versão: ${catalog.regional.version} · estado: ${catalog.regional.status}</p><p class="hash-text">Pacote regional SHA-256: ${catalog.regional.package.sha256}</p><p class="hash-text">Decisão SHA-256: ${selection.decision_sha256}</p>${exploratory ? `<p class="hash-text">Política SHA-256: ${esc(pilot.summary.policy_sha256)}</p><p>Fonte espectral: Element 84 Earth Search · Sentinel-2 L2A C1 · radiometria de cada produto conferida, sem transferência automática da calibração Planetary Computer de Paracatu.</p>` : ''}</details><a href="./regions/catalog.json" download>Baixar catálogo independente ↓</a></div></div>`;
    const $ = id => container.querySelector(`#${id}`);
    let regionalMap;
    let pivot = evidence.pivots.features[0].properties.pivot_id;
    function updatePivot(id, notify = true) {
      pivot = id;
      $('regional-pivot-select').value = id;
      const feature = evidence.pivots.features.find(feature => feature.properties.pivot_id === id);
      $('regional-pivot-description').textContent = `${id} · FID ${feature.properties.FID} · ${fmt(feature.properties.area_ha, 2)} ha · município IBGE 2204501.`;
      if (notify) onPivot(id);
      if (!pilot) return;
      const rows = filterMonthly(pilot.monthly, id, '2023-01', '2024-12');
      const observations = pilot.observations.filter(row => row.pivot_id === id);
      const attempts = pilot.attempts.filter(row => row.pivot_id === id);
      renderSeries($('regional-series-chart'), rows, $('regional-index').value, observations, rows);
      renderPrecipitation($('regional-rain-chart'), rows);
      $('regional-observation-table').innerHTML = `<table><caption>Tentativas regionais do pivô ${esc(id)}, incluindo rejeições</caption><thead><tr><th>Data</th><th>NDVI</th><th>NDMI</th><th>Pixels válidos / estado</th><th>Chuva mensal</th><th>Aquisição / proveniência</th></tr></thead><tbody>${attempts.map(row => {
        const month = rows.find(month => month.month === row.month);
        const scene = pilot.scenes.find(scene => scene.scene_id === row.scene_id);
        return `<tr><th>${row.date}</th><td>${fmt(row.ndvi_median, 4)}</td><td>${fmt(row.ndmi_median, 4)}</td><td>${fmt(row.valid_pixel_pct, 1)}%<small>${row.status === 'ok' ? 'Aceita' : 'Rejeitada · pixels válidos insuficientes'}</small></td><td>${month?.precip_status === 'ok' ? `${fmt(month.precip_mm, 1)} mm` : 'Ausente'}</td><td><details><summary>${esc(row.scene_id)}</summary><p>${esc(scene?.provider || row.provider || row.sentinel_source)} · ${esc(scene?.collection || row.collection)} · PB ${esc(scene?.processing_baseline || row.processing_baseline)}</p><p>${esc(scene?.method || row.radiometric_method)}</p><p class="hash-text">${esc(scene?.product)}</p></details></td></tr>`;
      }).join('')}</tbody></table>`;
    }
    function selectStudy(id, notify = true) {
      const regional = id === 'guadalupe-pi';
      $('study-select').value = id;
      $('paracatu-study-detail').hidden = regional;
      $('regional-study-detail').hidden = !regional;
      container.querySelectorAll('[data-study]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.study === id)));
      if (regional) {
        if (!regionalMap) regionalMap = createMap($('regional-map'), evidence.pivots, updatePivot, { label: 'Guadalupe, PI', title: 'Guadalupe · Piauí', subtitle: exploratory ? 'Amostra exploratória · 2023–2024' : 'Amostra selecionada · ANA 2022', ariaLabel: 'Mapa dos cinco pivôs ANA selecionados em Guadalupe, PI.' });
        regionalMap.invalidateSize(); regionalMap.select(pivot); updatePivot(pivot, false);
      }
      if (notify) onStudy(id);
    }
    $('study-select').addEventListener('change', event => selectStudy(event.target.value));
    container.querySelectorAll('[data-study]').forEach(button => button.addEventListener('click', () => selectStudy(button.dataset.study)));
    $('regional-pivot-select').addEventListener('change', event => { regionalMap.select(event.target.value); updatePivot(event.target.value); });
    $('regional-index')?.addEventListener('change', () => updatePivot(pivot));
    return {
      loaded: { catalog, evidence, images: imageURLs },
      selectStudy: id => selectStudy(id, false),
      selectPivot(id, index) {
        if (!evidence.pivots.features.some(feature => feature.properties.pivot_id === id)) return;
        if (index) $('regional-index').value = index === 'ndmi' ? 'ndmi_median' : 'ndvi_median';
        selectStudy('guadalupe-pi', false);
        regionalMap.select(id); updatePivot(id, false);
      },
      getState: () => ({ study: $('study-select').value, pivot, index: $('regional-index')?.value, mapView:regionalMap?.getView() }),
      restoreView: view => regionalMap?.setView(view),
    };
  } catch (error) {
    container.innerHTML = `<div class="regional-unavailable" role="status"><h2>Investigação regional indisponível.</h2><p>${esc(error.message)} O estudo congelado de Paracatu continua disponível abaixo.</p></div>`;
  }
}
