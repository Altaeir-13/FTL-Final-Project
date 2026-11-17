export const DEMO_STEPS = Object.freeze([
  Object.freeze({ id: 'problem', title: 'O problema', target: 'territorio', text: 'A vegetação irrigada muda ao longo do tempo. A investigação precisa distinguir uma mudança observada de uma lacuna, com qualidade e origem dos dados conhecidas.' }),
  Object.freeze({ id: 'paracatu', title: 'O estudo de Paracatu', target: 'explorar', text: 'Explore os cinco polígonos reais, o histórico de 2022–2024, a cobertura e os resultados científicos congelados. Os modelos foram avaliados cronologicamente em 2024.' }),
  Object.freeze({ id: 'investigation', title: 'Uma investigação', target: 'investigacao', text: 'Compare duas observações publicadas. Leia os índices, as diferenças assinadas, a chuva regional, os pixels válidos e a proveniência. Gere uma ficha com exatamente esta seleção.' }),
  Object.freeze({ id: 'guadalupe', title: 'Expansão para Guadalupe', target: 'investigacao', text: 'A motivação de Caxias conduziu à seleção territorial e à prova exploratória de Guadalupe. Compare as duas cenas reais de julho já publicadas e seus limites. Não há modelo regional validado.' }),
  Object.freeze({ id: 'limits', title: 'Conclusões e limitações', target: 'investigacao', text: 'O AquaClima organiza evidências geoespaciais auditáveis e demonstra portabilidade na amostra. Fenologia, colheita, manejo, solo exposto e ambiente podem alterar os índices; atribuir uma causa requer dados independentes e validação de campo.' }),
]);

export function demoTransition(current = { active: false, index: 0 }, action) {
  const index = Number.isInteger(current.index) ? Math.max(0, Math.min(DEMO_STEPS.length - 1, current.index)) : 0;
  switch (action) {
    case 'start': case 'restart': return { active: true, index: 0 };
    case 'end': return { active: false, index };
    case 'next': return { active: Boolean(current.active), index: current.active ? Math.min(DEMO_STEPS.length - 1, index + 1) : index };
    case 'back': return { active: Boolean(current.active), index: current.active ? Math.max(0, index - 1) : index };
    default: throw new TypeError('Ação de demonstração desconhecida.');
  }
}

/** A non-modal dock keeps the real WebGIS available. No timers drive the tour. */
export function mountDemoMode({ button, captureState = () => null, onStep = () => {}, onRestore = () => {} }) {
  if (!button) throw new TypeError('Botão de demonstração ausente.');
  let state = { active: false, index: 0 }, previous = null, previousFocus = null, pending = false;
  const dock = document.createElement('aside');
  dock.className = 'demo-dock'; dock.hidden = true; dock.setAttribute('aria-label', 'Demonstração FTL');
  dock.innerHTML = `<div class="demo-content"><span class="eyebrow">MODO DEMONSTRAÇÃO FTL · CERCA DE 3 MINUTOS</span><p class="demo-step-counter" aria-live="polite"></p><h2 id="demo-title" tabindex="-1"></h2><p class="demo-description"></p><progress max="5" value="1" aria-label="Progresso da demonstração"></progress><small>Controle manual: avance no seu ritmo. Escape encerra e restaura a navegação anterior.</small></div><div class="demo-controls"><button type="button" data-demo="back">Voltar</button><button type="button" class="primary-button" data-demo="next">Avançar</button><button type="button" data-demo="restart">Reiniciar</button><button type="button" data-demo="end">Encerrar</button></div><p class="demo-error" role="alert" hidden></p>`;
  document.body.append(dock);
  const counter = dock.querySelector('.demo-step-counter'), title = dock.querySelector('#demo-title'), description = dock.querySelector('.demo-description'), progress = dock.querySelector('progress'), error = dock.querySelector('.demo-error');
  const controls = Object.fromEntries([...dock.querySelectorAll('[data-demo]')].map(element => [element.dataset.demo, element]));
  function render() {
    dock.hidden = !state.active; document.body.classList.toggle('demo-active', state.active); button.setAttribute('aria-expanded', String(state.active));
    const step = DEMO_STEPS[state.index];
    counter.textContent = `Passo ${state.index + 1} de ${DEMO_STEPS.length}`; title.textContent = step.title; description.textContent = step.text; progress.value = state.index + 1;
    controls.back.disabled = pending || state.index === 0; controls.next.disabled = pending || state.index === DEMO_STEPS.length - 1; controls.restart.disabled = pending;
  }
  async function dispatch(action) {
    if (pending) return;
    if (!state.active && !['start', 'restart'].includes(action)) return;
    if (!state.active) { previous = structuredClone(captureState()); previousFocus = document.activeElement; }
    state = demoTransition(state, action); error.hidden = true; pending = true; render();
    try {
      if (state.active) {
        await onStep({ ...DEMO_STEPS[state.index], index: state.index });
        title.focus({ preventScroll: true });
      } else {
        await onRestore(structuredClone(previous)); previous = null;
        if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
      }
    } catch (issue) {
      error.textContent = `Não foi possível ${state.active ? 'abrir este passo' : 'restaurar a navegação'}: ${issue.message}`; error.hidden = false;
    } finally { pending = false; render(); }
  }
  const start = () => dispatch('start'); button.addEventListener('click', start);
  // A modal evidence preview owns Escape until it is closed; do not end the tour underneath it.
  const escape = event => { if (state.active && event.key === 'Escape' && !event.defaultPrevented && !document.querySelector('dialog[open]')) { event.preventDefault(); dispatch('end'); } };
  document.addEventListener('keydown', escape);
  Object.entries(controls).forEach(([action, element]) => element.addEventListener('click', () => dispatch(action)));
  render();
  return { start, next: () => dispatch('next'), back: () => dispatch('back'), restart: () => dispatch('restart'), end: () => dispatch('end'), getState: () => ({ ...state }), destroy() { button.removeEventListener('click', start); document.removeEventListener('keydown', escape); document.body.classList.remove('demo-active'); dock.remove(); } };
}
