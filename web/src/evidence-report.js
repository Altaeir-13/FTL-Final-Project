import { investigationId } from './investigation-data.js';

export const AQUACLIMA_VERSION = '1.1.0';
const REPOSITORY = 'https://github.com/Altaeir-13/FTL-Final-Project';
const METHODOLOGY = `${REPOSITORY}/blob/main/docs/investigacao-guiada-ftl.md`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const numeric = value => Number.isFinite(value) ? String(value).replace('.', ',') : 'Ausente';
const valueWithUnit = (value, unit) => Number.isFinite(value) ? `${numeric(value)} ${unit}` : 'Ausente';
const statusLabel = status => ({ completed: 'Estudo científico concluído', exploratory_portability: 'Prova exploratória de portabilidade · sem modelo regional validado' }[status] || status || 'Ausente');
let activeDialog;
let activePrintRoot;
let previousFocus;

function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}

/** Immutable copy; its generation time is deliberately outside scientific identity. */
export async function createEvidenceSnapshot(snapshot, generatedAt = new Date().toISOString()) {
  if (!snapshot?.study || !snapshot?.pivot || !snapshot?.a || !snapshot?.b || snapshot.a.id === snapshot.b.id) throw new Error('Selecione duas observações reais distintas antes de gerar a ficha.');
  if (!/^[a-f0-9]{64}$/.test(snapshot.study.packageHash || '')) throw new Error('A ficha exige um pacote científico identificado por SHA-256.');
  const date = new Date(generatedAt);
  if (!Number.isFinite(date.getTime())) throw new Error('Data de geração inválida.');
  const copy = structuredClone(snapshot);
  copy.investigationId = await investigationId(copy);
  copy.generatedAt = date.toISOString();
  copy.systemVersion = AQUACLIMA_VERSION;
  return freeze(copy);
}

function safeSourceLink(value) {
  if (typeof value !== 'string' || !/^https:\/\//i.test(value)) return esc(value || 'Ausente');
  try {
    const url = new URL(value);
    if (url.username || url.password) return 'Referência indisponível';
    return `<a href="${esc(url.href)}" target="_blank" rel="noreferrer">${esc(value)}</a>`;
  } catch { return esc(value); }
}

function imageSource(image) {
  if (!image?.url || typeof image.url !== 'string') return null;
  if (/^blob:(?:https?:\/\/|null\/)[^\s"'<>]+$/.test(image.url)) return image.url;
  // Published local derivatives only; remote images are never requested for a report.
  if (/^(?:\.\/)?regions\/images\/false-colour-202[34]-\d{2}-\d{2}\.png$/.test(image.url)) return image.url;
  return null;
}

function observationImage(endpoint, label, region) {
  const image = endpoint.image;
  const url = imageSource(image);
  const matches = region === 'guadalupe-pi' && endpoint.granularity === 'scene' && image?.date === endpoint.date
    && endpoint.scenes.some(scene => scene.scene_id === image.scene_id && scene.date === image.date);
  if (!url || !matches) return `<div class="evidence-image-unavailable"><strong>Observação ${label} · ${esc(endpoint.label)}</strong><p>Imagem comparativa não disponível para esta observação.</p></div>`;
  return `<figure><img src="${esc(url)}" alt="Sentinel-2 real em falsa cor, ${esc(image.date)}, grupo de cinco pivôs ANA de Guadalupe. O pivô investigado está identificado no grupo."/><figcaption><strong>${label} · ${esc(image.date)}</strong><span>Área do grupo de cinco pivôs ANA; o recorte não representa somente o pivô selecionado.</span><span>${esc(image.scene_id)}</span><span>Falsa cor: ${esc(image.composition || 'R=B08 (NIR), G=B04 (vermelho), B=B11 (SWIR1)')}.</span><span>${esc(image.crs)} · pixel ${esc(image.grid_resolution_m ?? 20)} m · estiramento fixo 0–0,6.</span><span>Contains modified Copernicus Sentinel data 2023–2024 · polígonos ANA 2022.</span><span>Fonte da imagem: ${safeSourceLink(image.source)}</span><span class="evidence-hash">Imagem SHA-256: ${esc(image.sha256)}</span></figcaption></figure>`;
}

function sceneDetails(endpoint, label) {
  return `<section class="evidence-scene-group"><h3>Observação ${label} · ${esc(endpoint.label)}</h3><p>Mês de referência: ${esc(endpoint.month)}. Datas efetivas de aquisição: ${esc(endpoint.dates?.length ? endpoint.dates.join(' · ') : endpoint.date || 'Ausentes')}.</p>${endpoint.scenes.length ? endpoint.scenes.map(scene => `<dl class="evidence-scene"><dt>Cena Sentinel-2</dt><dd>${esc(scene.scene_id)}</dd><dt>Data efetiva</dt><dd>${esc(scene.date || 'Ausente')}</dd><dt>Provedor / coleção / baseline</dt><dd>${esc(scene.provider || 'Ausente')} / ${esc(scene.collection || 'Ausente')} / ${esc(scene.processing_baseline || 'Ausente')}</dd><dt>Método de processamento</dt><dd>${esc(scene.method || scene.radiometric_method || 'Ausente')}</dd><dt>Identificador nativo / aquisição</dt><dd>${esc(scene.native_scene_id || 'Ausente')} / ${esc(scene.acquisition_key || 'Ausente')}</dd><dt>Produto original registrado</dt><dd>${esc(scene.product || 'Ausente')}</dd><dt>Fonte registrada</dt><dd>${safeSourceLink(scene.source)}</dd><dt>Hash de calibração, quando publicado</dt><dd class="evidence-hash">${esc(scene.calibration_sha256 || 'Ausente')}</dd><dt>Hash dos índices / manifesto do lote, quando publicados</dt><dd class="evidence-hash">${esc(scene.indices_sha256 || 'Ausente')} / ${esc(scene.batch_manifest_sha256 || 'Ausente')}</dd></dl>`).join('') : '<p>Identificadores e proveniência de cenas ausentes.</p>'}<p>CHIRPS: ${esc(endpoint.precipitation?.product || 'Produto não informado')} · fonte: ${safeSourceLink(endpoint.precipitation?.source)}. Célula (longitude / latitude): ${esc(numeric(endpoint.precipitation?.cell_lon))}° / ${esc(numeric(endpoint.precipitation?.cell_lat))}°; linha ${esc(numeric(endpoint.precipitation?.cell_row))}, coluna ${esc(numeric(endpoint.precipitation?.cell_col))}; resolução ${esc(valueWithUnit(endpoint.precipitation?.resolution_deg, 'graus'))}. Hash do raster meteorológico: ${esc(endpoint.precipitation?.raster_sha256 || 'Ausente no pacote público')}.</p></section>`;
}

/** All data strings are escaped; only verified local derivative URLs may become images. */
export function renderEvidenceReport(snapshot, generatedAt = snapshot.generatedAt) {
  const { study, pivot, a, b, interval } = snapshot;
  const generated = new Date(generatedAt);
  if (!Number.isFinite(generated.getTime())) throw new Error('Data de geração inválida.');
  const rows = [
    ['NDVI · adimensional', numeric(a.ndvi_median), numeric(b.ndvi_median), numeric(snapshot.delta_ndvi)],
    ['NDMI · adimensional', numeric(a.ndmi_median), numeric(b.ndmi_median), numeric(snapshot.delta_ndmi)],
    ['CHIRPS v3 · mm/mês', a.precip_status === 'ok' ? numeric(a.precip_mm) : 'Ausente', b.precip_status === 'ok' ? numeric(b.precip_mm) : 'Ausente', 'Não calculada'],
    ['Pixels conjuntos válidos · %', numeric(a.valid_pixel_pct), numeric(b.valid_pixel_pct), 'Não calculada'],
  ];
  return `<article id="evidence-document" class="evidence-document" aria-labelledby="evidence-title">
    <header class="evidence-heading"><p class="evidence-kicker">CIÊNCIA ABERTA · FUTURE TECH LEADERS BRASIL</p><h1 id="evidence-title">Ficha de Evidências — AquaClima</h1><p>Sistema AquaClima ${esc(snapshot.systemVersion || AQUACLIMA_VERSION)} · análise descritiva de observações publicadas</p></header>
    <dl class="evidence-identification"><dt>Território / nível de evidência</dt><dd>${esc(study.label)} · ${esc(statusLabel(study.status))}</dd><dt>Pivô ANA / município</dt><dd>${esc(pivot.id)} · ${esc(pivot.municipality || study.label)}${pivot.uf ? ` / ${esc(pivot.uf)}` : ''}</dd><dt>Área do polígono</dt><dd>${esc(valueWithUnit(pivot.area_ha, 'ha'))}</dd><dt>Período disponível / cobertura contínua</dt><dd>${esc(pivot.period?.from || 'Ausente')} a ${esc(pivot.period?.to || 'Ausente')} · ${esc(pivot.observedMonths ?? 'Ausente')}/${esc(pivot.calendarMonths ?? 'Ausente')} meses observados · ${esc(pivot.acceptedObservations ?? 'Ausente')} observações aceitas</dd><dt>Granularidade comparada</dt><dd>${study.granularity === 'month' ? 'Agregado mensal: mediana das medianas espaciais de cenas aceitas, com pesos iguais.' : 'Observação por cena: mediana espacial dos pixels válidos na data efetiva.'}</dd><dt>Observações A → B</dt><dd>${esc(a.label)} → ${esc(b.label)}</dd><dt>Identificador determinístico da investigação</dt><dd class="evidence-hash" data-report-id>${esc(snapshot.investigationId || 'Ausente')}</dd></dl>
    <section><h2>Valores observados e diferenças assinadas</h2><p>Δ = B − A, em unidades adimensionais. Não corresponde a variação percentual nem à diferença absoluta. Valores preservam a precisão numérica publicada.</p><table class="evidence-values"><caption>Índices, chuva e qualidade da seleção congelada nesta ficha</caption><thead><tr><th scope="col">Indicador</th><th scope="col">A · ${esc(a.label)}</th><th scope="col">B · ${esc(b.label)}</th><th scope="col">Δ (B − A)</th></tr></thead><tbody>${rows.map(([name,av,bv,delta]) => `<tr><th scope="row">${esc(name)}</th><td>${esc(av)}</td><td>${esc(bv)}</td><td>${esc(delta)}</td></tr>`).join('')}</tbody></table><p>${study.granularity === 'month' ? 'A qualidade informa o menor percentual de pixels válidos entre as cenas aceitas de cada mês.' : 'A qualidade informa os pixels conjuntos válidos na cena selecionada.'} Aceitação científica por cena: ≥70%. Abaixo de 80% exige atenção à qualidade.</p><p>Intervalo: ${esc(interval.calendarMonths)} meses de calendário${interval.days == null ? ' (agregados mensais; sem intervalo diário único)' : `; ${esc(interval.days)} dias entre aquisições`}. Meses sem observação entre A e B: ${esc(interval.unobservedMonths?.length ? interval.unobservedMonths.join(' · ') : 'Nenhum')}.</p><p>CHIRPS v3 é contexto regional do mês completo; não mede chuva nem consumo de água individualmente no pivô. Os acumulados de A e B não representam toda a precipitação entre as observações.</p></section>
    <section><h2>O que as evidências permitem concluir?</h2><p>${esc(snapshot.synthesis)}</p></section>
    <section class="evidence-imagery"><h2>Evidência visual disponível</h2><div class="evidence-image-pair">${observationImage(a, 'A', study.id)}${observationImage(b, 'B', study.id)}</div><p>Os PNGs são derivados visuais Sentinel-2 L2A, sem uso analítico. Mesma grade e parâmetros visuais nas duas imagens publicadas de Guadalupe. Cores não diagnosticam irrigação.</p></section>
    <section class="evidence-provenance"><h2>Identificadores e proveniência Sentinel-2</h2>${sceneDetails(a, 'A')}${sceneDetails(b, 'B')}</section>
    <section><h2>Limitações científicas</h2><ul>${(snapshot.limitations || []).map(item => `<li>${esc(item)}</li>`).join('')}</ul><p>Fenologia, colheita, manejo, solo exposto e condições ambientais podem contribuir para as diferenças. As evidências disponíveis não permitem atribuir uma causa específica. Não constituem laudo agronômico ou diagnóstico de irrigação.</p></section>
    <section class="evidence-utility"><h2>Possível utilidade da investigação</h2><p>Organizar evidências rastreáveis e identificar períodos para revisão por pesquisadores, estudantes e profissionais. Não comprova ganho econômico, economia de água ou falha de irrigação.</p></section>
    <footer class="evidence-footer"><h2>Reprodutibilidade</h2><dl><dt>Versão do pacote científico</dt><dd>${esc(study.version)}</dd><dt>Pacote SHA-256</dt><dd class="evidence-hash">${esc(study.packageHash)}</dd>${Object.entries(study.sourceFiles || {}).map(([name, hash]) => `<dt>Arquivo público ${esc(name)} · SHA-256</dt><dd class="evidence-hash">${esc(hash)}</dd>`).join('')}<dt>Parâmetros da investigação</dt><dd class="evidence-hash">${esc(JSON.stringify(snapshot.parameters || {}))}</dd><dt>Gerada em (UTC) — data da ficha, distinta das datas dos dados</dt><dd>${esc(generated.toISOString())}</dd></dl><p><a href="${METHODOLOGY}" target="_blank" rel="noreferrer">Metodologia e regras da investigação</a> · <a href="${REPOSITORY}" target="_blank" rel="noreferrer">Repositório AquaClima</a></p><p class="evidence-link">${REPOSITORY}/blob/main/docs/investigacao-guiada-ftl.md</p><p>O identificador científico deriva do território, pivô, observações, pacote e parâmetros. A data de geração não participa dessa identidade. Esta ficha preserva a seleção no momento da geração, independentemente de mudanças posteriores na interface.</p></footer>
  </article>`;
}

export function closeEvidenceReport() {
  if (!activeDialog) return;
  const dialog = activeDialog;
  activeDialog = undefined;
  activePrintRoot?.remove();
  activePrintRoot = undefined;
  document.body.classList.remove('evidence-report-open');
  dialog.close();
  dialog.remove();
  previousFocus?.focus?.({ preventScroll: true });
}

export async function openEvidenceReport(snapshot) {
  const copy = await createEvidenceSnapshot(snapshot);
  closeEvidenceReport();
  previousFocus = document.activeElement;
  const dialog = document.createElement('dialog');
  dialog.id = 'evidence-report';
  dialog.setAttribute('aria-labelledby', 'evidence-title');
  dialog.innerHTML = `<div class="evidence-toolbar"><div><strong>Prévia de impressão A4</strong><span>Seleção preservada nesta ficha. Use “Salvar como PDF” no navegador.</span></div><label><input type="checkbox" id="evidence-utility-toggle" checked/> Incluir possível utilidade</label><button type="button" id="evidence-print" class="primary-button">Imprimir / salvar como PDF</button><button type="button" id="evidence-close" class="secondary-button">Fechar ficha</button><span id="evidence-print-status" role="status"></span></div>${renderEvidenceReport(copy)}`;
  // Native top-layer dialogs can clip content across printed pages in Chromium.
  // A separate normal-flow copy holds exactly the same immutable document.
  const printRoot = document.createElement('div');
  printRoot.id = 'evidence-print-root';
  printRoot.className = 'evidence-print-root';
  printRoot.setAttribute('aria-hidden', 'true');
  const printDocument = dialog.querySelector('.evidence-document').cloneNode(true);
  for (const element of [printDocument, ...printDocument.querySelectorAll('[id],[data-report-id],[aria-labelledby]')]) {
    element.removeAttribute('id');
    element.removeAttribute('data-report-id');
    element.removeAttribute('aria-labelledby');
  }
  printRoot.append(printDocument);
  document.body.append(dialog);
  document.body.append(printRoot);
  activeDialog = dialog;
  activePrintRoot = printRoot;
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeEvidenceReport(); });
  dialog.querySelector('#evidence-close').addEventListener('click', closeEvidenceReport);
  dialog.querySelector('#evidence-utility-toggle').addEventListener('change', event => {
    dialog.querySelector('.evidence-utility').hidden = !event.target.checked;
    printRoot.querySelector('.evidence-utility').hidden = !event.target.checked;
  });
  dialog.querySelector('#evidence-print').addEventListener('click', async event => {
    const print = event.currentTarget;
    print.disabled = true;
    const images = [...dialog.querySelectorAll('img'), ...printRoot.querySelectorAll('img')];
    await Promise.all(images.map(image => image.decode().catch(() => {
      const message = document.createElement('p');
      message.textContent = 'Imagem indisponível para impressão; consulte os identificadores e o hash da seleção.';
      image.replaceWith(message);
    })));
    if (activeDialog !== dialog) return;
    print.disabled = false;
    dialog.querySelector('#evidence-print-status').textContent = 'Ficha pronta. A impressão é processada localmente pelo navegador.';
    window.print();
  });
  document.body.classList.add('evidence-report-open');
  dialog.showModal();
  dialog.querySelector('#evidence-print').focus();
  return copy;
}
