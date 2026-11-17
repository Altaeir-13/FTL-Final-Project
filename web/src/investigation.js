import { availableObservations, canCompareObservations, resolveSelection, compareSelection, parseInvestigationURL, serializeInvestigationURL, investigationId } from './investigation-data.js';
import { openEvidenceReport } from './evidence-report.js';
import './investigation.css';
import './evidence-report.css';

const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[char]));
const value = number => number == null ? 'Ausente' : String(number).replace('.', ',');
const signed = number => number == null ? 'Ausente' : `${number > 0 ? '+' : ''}${value(number)}`;
const quality = number => number == null ? 'Ausente' : `${value(number)}%`;

/** Coordinates selections only; all science comes from the verified public packages. */
export function mountInvestigation(container, { studies, search = location.search, onChange = () => {} }) {
  let selection = parseInvestigationURL(search, studies);
  let snapshot;
  let revision = 0;
  container.innerHTML = `
    <div class="investigation-heading"><div><span class="eyebrow">DO POLÍGONO À FICHA · SEM INTERPOLAÇÃO</span><h2 id="investigation-title">Investigação espectral</h2><p>Escolha duas observações aceitas e examine a mudança, o contexto e os limites.</p></div><a href="#territorio" class="secondary-button">Ver territórios ↑</a></div>
    <p id="investigation-warning" role="status" class="investigation-warning" hidden></p><button id="investigation-current-package" class="secondary-button" hidden>Abrir pacote publicado atual</button>
    <div class="investigation-steps">
      <fieldset><legend>1 · Escolha do território</legend><label>Estudo<select id="investigation-region"></select></label><p id="investigation-status"></p></fieldset>
      <fieldset><legend>2 · Escolha do pivô</legend><label>Pivô ANA<select id="investigation-pivot"></select></label><p id="investigation-pivot-info"></p><a id="investigation-map-link">Ver polígono selecionado no mapa ↓</a></fieldset>
      <fieldset class="investigation-observations"><legend>3 · Escolha das observações</legend><p id="investigation-granularity"></p><div class="observation-selectors"><label>Observação A<select id="investigation-a"></select></label><label>Observação B<select id="investigation-b"></select></label><label>Índice de interesse<select id="investigation-index"><option value="ndvi">NDVI</option><option value="ndmi">NDMI</option></select></label></div><p>Somente registros aceitos. As duas seleções devem ser diferentes; não há valores interpolados.</p></fieldset>
    </div>
    <section class="investigation-analysis" aria-labelledby="analysis-title"><h3 id="analysis-title">4 · Análise da mudança</h3><p id="investigation-interval"></p><div class="table-scroll"><table id="investigation-values"><caption>Valores publicados e diferença assinada B − A</caption><thead><tr><th>Variável</th><th id="observation-a-label">A</th><th id="observation-b-label">B</th><th>Diferença B − A</th></tr></thead><tbody></tbody></table></div><p class="investigation-note">NDVI e NDMI são adimensionais. A diferença é assinada, sem conversão para porcentagem. CHIRPS v3 é o acumulado do mês inteiro em uma célula regional; pode incluir chuva posterior ao dia da cena e não mede consumo do pivô.</p><div id="investigation-images" class="investigation-images"></div><details class="investigation-provenance"><summary>Datas efetivas, qualidade, fontes e proveniência</summary><div id="investigation-provenance"></div></details></section>
    <section class="investigation-conclusion" aria-labelledby="evidence-conclusion"><span class="eyebrow">5 · INTERPRETAÇÃO DESCRITIVA</span><h3 id="evidence-conclusion">O que as evidências permitem concluir?</h3><p id="investigation-synthesis"></p><ul id="investigation-limits"></ul></section>
    <div class="investigation-actions"><button id="generate-evidence" class="primary-button">Gerar ficha de evidências</button><button id="share-investigation" class="secondary-button">Compartilhar investigação</button><label id="investigation-share-label" hidden>Link da investigação<input id="investigation-share" type="url" readonly/></label><p id="investigation-share-status" role="status"></p></div>
    <details class="investigation-integrity"><summary>Identidade reproduzível e pacote científico</summary><dl><dt>Identificador determinístico</dt><dd id="investigation-id">Calculando…</dd><dt>Versão e hash SHA-256 do pacote</dt><dd id="investigation-package"></dd></dl></details>`;
  const $ = id => container.querySelector(`#${id}`);
  const regionSelect = $('investigation-region');
  regionSelect.innerHTML = studies.map(study => `<option value="${esc(study.id)}">${esc(study.label)}</option>`).join('');

  function render(notify = true) {
    const currentRevision = ++revision;
    const study = studies.find(item => item.id === selection.region);
    const blocked = selection.packageMismatch;
    snapshot = compareSelection(studies, blocked ? { ...selection, packageMismatch: false, package: study.packageHash } : selection);
    for (const element of container.querySelectorAll('.investigation-analysis,.investigation-conclusion,.investigation-actions,.investigation-integrity')) element.hidden = blocked;
    $('investigation-current-package').hidden = !blocked;
    const { a, b, pivot } = snapshot;
    regionSelect.value = selection.region;
    $('investigation-status').textContent = snapshot.study.status;
    $('investigation-pivot').innerHTML = study.pivots.features.map(feature => `<option value="${esc(feature.properties.pivot_id)}">${esc(feature.properties.pivot_id)} · ${esc(value(feature.properties.area_ha))} ha</option>`).join('');
    $('investigation-pivot').value = selection.pivot;
    $('investigation-pivot-info').textContent = `${pivot.municipality}, ${pivot.uf} · ${value(pivot.area_ha)} ha · ${pivot.period.from} a ${pivot.period.to} · ${pivot.acceptedObservations} observações aceitas · ${pivot.observedMonths}/${pivot.calendarMonths} meses observados (${(pivot.observedMonths / pivot.calendarMonths * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%).`;
    $('investigation-map-link').href = selection.region === 'paracatu-mg' ? '#map-title' : '#regional-map';
    $('investigation-granularity').textContent = selection.region === 'paracatu-mg'
      ? 'Agregados mensais publicados: mediana das medianas de cenas aceitas, com pesos iguais. O mês de referência não é a data de uma cena.'
      : 'Observações por cena: mediana espacial no pivô, em sua data efetiva de aquisição. A chuva corresponde ao mês de referência.';
    const available = availableObservations(study, selection.pivot);
    for (const key of ['a', 'b']) {
      const other = available.find(item => item.id === selection[key === 'a' ? 'b' : 'a']);
      $(`investigation-${key}`).innerHTML = available.map(item => `<option value="${esc(item.id)}"${!canCompareObservations(other,item) ? ' disabled' : ''}>${esc(item.label)}</option>`).join('');
      $(`investigation-${key}`).value = selection[key];
    }
    $('investigation-index').value = selection.index;
    $('observation-a-label').textContent = `A · ${a.label}`;
    $('observation-b-label').textContent = `B · ${b.label}`;
    $('investigation-values').querySelector('tbody').innerHTML = [
      ['NDVI', a.ndvi_median, b.ndvi_median, snapshot.delta_ndvi, 'ndvi'],
      ['NDMI', a.ndmi_median, b.ndmi_median, snapshot.delta_ndmi, 'ndmi'],
    ].map(([name, first, second, delta, key]) => `<tr${selection.index === key ? ' class="investigation-highlight"' : ''}><th>${name} · adimensional</th><td data-value="${first ?? ''}" data-field="${key}-a">${value(first)}</td><td data-value="${second ?? ''}" data-field="${key}-b">${value(second)}</td><td data-value="${delta ?? ''}" data-field="delta-${key}">${signed(delta)}</td></tr>`).join('') + `<tr><th>CHIRPS v3 · mm/mês</th><td>${value(a.precip_mm)}</td><td>${value(b.precip_mm)}</td><td>Contexto mensal</td></tr><tr><th>${selection.region === 'paracatu-mg' ? 'Pixels válidos · mínimo entre cenas' : 'Pixels válidos · cena'} (%)</th><td>${quality(a.valid_pixel_pct)}</td><td>${quality(b.valid_pixel_pct)}</td><td>Indicador de qualidade</td></tr>`;
    $('investigation-interval').textContent = `Intervalo entre A e B: ${Math.abs(snapshot.interval.calendarMonths)} meses de calendário${snapshot.interval.days == null ? '' : ` · ${Math.abs(snapshot.interval.days)} dias`}. Meses interiores sem observação: ${snapshot.interval.unobservedMonths.length}${snapshot.interval.unobservedMonths.length ? ` (${snapshot.interval.unobservedMonths.join(' · ')})` : ''}. A sequência pode atravessar lacunas; não mede uma mudança contínua.`;
    $('investigation-images').innerHTML = [a, b].map((observation, index) => `<figure>${observation.image ? `<img src="${esc(observation.image.url)}" alt="Sentinel-2 real em falsa cor, ${esc(observation.date)}, grupo dos cinco pivôs ANA de Guadalupe; o pivô ${esc(pivot.id)} integra o grupo."/><figcaption><strong>${index === 0 ? 'A' : 'B'} · ${esc(observation.label)}</strong><p>Visão do grupo dos cinco pivôs, com contornos ANA; inclui ${esc(pivot.id)}. Falsa cor B08/B04/B11 · EPSG:32723 · 20 m · estiramento fixo 0–0,6.</p><p>${esc(observation.image.scene_id)} · Contains modified Copernicus Sentinel data 2023–2024.</p></figcaption>` : `<div class="investigation-image-missing"><strong>${index === 0 ? 'A' : 'B'} · ${esc(observation.label)}</strong><p>Imagem comparativa não disponível para esta observação.</p></div>`}</figure>`).join('');
    $('investigation-provenance').innerHTML = [a, b].map((observation, index) => `<section><h4>${index === 0 ? 'A' : 'B'} · ${esc(observation.label)}</h4><p>Mês de referência: ${esc(observation.month)} · datas efetivas: ${esc(observation.dates.join(' · '))} · pixels válidos ${quality(observation.valid_pixel_pct)}.</p><p>Lote: ${esc(observation.batch_status ?? 'Ausente')} · consulta completa: ${observation.query_complete == null ? 'Ausente' : observation.query_complete ? 'Sim' : 'Não'} · revisão de qualidade: ${observation.quality_review ? 'Sim' : 'Não'} · ${value(observation.n_accepted_scenes)}/${value(observation.n_attempted_scenes)} cenas aceitas/tentadas no mês.</p><p>CHIRPS: ${esc(observation.precip_status)} · ${value(observation.precip_mm)} mm. ${esc(observation.precipitation ? JSON.stringify(observation.precipitation) : '')}</p>${observation.scenes.map(scene => `<dl>${Object.entries(scene).map(([key, entry]) => `<dt>${esc(key)}</dt><dd>${esc(typeof entry === 'object' && entry !== null ? JSON.stringify(entry) : entry ?? 'Ausente')}</dd>`).join('')}</dl>`).join('')}</section>`).join('');
    $('investigation-synthesis').textContent = snapshot.synthesis;
    $('investigation-limits').innerHTML = snapshot.limitations.map(text => `<li>${esc(text)}</li>`).join('');
    $('investigation-package').textContent = `${snapshot.study.version} · ${snapshot.study.packageHash}`;
    $('investigation-id').textContent = 'Calculando…';
    investigationId(snapshot).then(id => { if (currentRevision === revision) $('investigation-id').textContent = id; }).catch(() => { $('investigation-id').textContent = 'Identificador indisponível.'; });
    const warnings = selection.warnings || [];
    $('investigation-warning').hidden = !warnings.length;
    $('investigation-warning').textContent = warnings.join(' ');
    $('investigation-share-label').hidden = true;
    $('investigation-share-status').textContent = '';
    if (!blocked) {
      history.replaceState(null, '', `${location.pathname}${serializeInvestigationURL(selection, location.search)}${location.hash}`);
      if (notify) onChange({ ...selection }, snapshot);
    }
  }

  function setSelection(input, { notify = true } = {}) {
    selection = resolveSelection(studies, { ...selection, ...input, package: input.package ?? (input.region && input.region !== selection.region ? undefined : selection.package) });
    render(notify);
  }
  regionSelect.addEventListener('change', event => setSelection({ region: event.target.value, pivot: undefined, a: undefined, b: undefined }));
  $('investigation-pivot').addEventListener('change', event => setSelection({ pivot: event.target.value, a: undefined, b: undefined }));
  $('investigation-current-package').addEventListener('click', () => setSelection({ package: studies.find(study => study.id === selection.region).packageHash }));
  for (const key of ['a', 'b', 'index']) $(`investigation-${key}`).addEventListener('change', event => setSelection({ [key]: event.target.value }));
  $('generate-evidence').addEventListener('click', async () => {
    try { await openEvidenceReport(snapshot); }
    catch (error) { $('investigation-warning').hidden = false; $('investigation-warning').textContent = `Ficha indisponível: ${error.message}`; }
  });
  $('share-investigation').addEventListener('click', async () => {
    const url = new URL(location.href); url.hash = 'investigacao';
    $('investigation-share-label').hidden = false;
    $('investigation-share').value = url.href;
    $('investigation-share').select();
    try { await navigator.clipboard.writeText(url.href); $('investigation-share-status').textContent = 'Link copiado. Inclui seleção e hash do pacote publicado.'; }
    catch { $('investigation-share-status').textContent = 'Copie o link do campo acima.'; }
  });
  render();
  return { setSelection, getSelection: () => ({ ...selection }), getSnapshot: () => structuredClone(snapshot) };
}
