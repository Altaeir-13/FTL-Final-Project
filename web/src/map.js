import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './map.css';

const normalStyle = { color: '#24796e', weight: 2, fillColor: '#6da99a', fillOpacity: 0.30 };
const selectedStyle = { color: '#596a16', weight: 3, fillColor: '#cee578', fillOpacity: 0.68 };
const number = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function control(position, className, build) {
  const item = L.control({ position });
  item.onAdd = () => {
    const element = L.DomUtil.create('div', className);
    L.DomEvent.disableClickPropagation(element);
    L.DomEvent.disableScrollPropagation(element);
    build(element);
    return element;
  };
  return item;
}

/** Cartography from contract geometry only. No external tiles or invented context. */
export function createMap(container, geojson, onSelect) {
  container.classList.add('ac-map');
  container.setAttribute('aria-label', 'Mapa dos cinco pivôs ANA. Use Tab para selecionar polígonos, setas para navegar e + ou − para ampliar.');
  const map = L.map(container, {
    zoomControl: true,
    attributionControl: true,
    scrollWheelZoom: false,
    keyboard: true,
    minZoom: 11,
    maxZoom: 18,
    zoomSnap: 0.25,
  });
  map.attributionControl.setPrefix(false);
  map.attributionControl.addAttribution('ANA · polígonos 2022 · WGS84');
  map.zoomControl.setPosition('topright');
  map.zoomControl._zoomInButton.title = 'Ampliar mapa';
  map.zoomControl._zoomInButton.setAttribute('aria-label', 'Ampliar mapa');
  map.zoomControl._zoomOutButton.title = 'Reduzir mapa';
  map.zoomControl._zoomOutButton.setAttribute('aria-label', 'Reduzir mapa');

  map.createPane('acGraticule');
  map.getPane('acGraticule').style.zIndex = 210;
  map.getPane('acGraticule').style.pointerEvents = 'none';
  map.createPane('acGridLabels');
  map.getPane('acGridLabels').style.zIndex = 215;
  map.getPane('acGridLabels').style.pointerEvents = 'none';
  const graticule = L.layerGroup().addTo(map);
  const labels = L.layerGroup().addTo(map);
  const layers = new Map();
  const markers = new Map();
  const preparedPaths = new WeakSet();
  let selectedId = null;

  function choose(pivotId) {
    const id = String(pivotId);
    select(id);
    onSelect(id);
  }

  const polygons = L.geoJSON(geojson, {
    style: normalStyle,
    onEachFeature(feature, layer) {
      const id = String(feature.properties.pivot_id);
      layers.set(id, layer);
      const detail = document.createElement('div');
      detail.append(
        textElement('strong', '', `Pivô ANA ${id}`),
        textElement('div', '', `${number.format(feature.properties.area_ha)} ha · Paracatu, MG`),
        textElement('small', '', 'Clique ou pressione Enter para explorar'),
      );
      layer.bindTooltip(detail, { direction: 'top', className: 'ac-map-tooltip', sticky: true });
      layer.on('click', () => choose(id));
      layer.on('mouseover', () => {
        if (id !== selectedId) layer.setStyle({ fillOpacity: 0.52 });
      });
      layer.on('mouseout', () => layer.setStyle(id === selectedId ? selectedStyle : normalStyle));
      layer.on('add', () => {
        const path = layer.getElement();
        if (!path) return;
        path.setAttribute('tabindex', '0');
        path.setAttribute('role', 'button');
        path.setAttribute('aria-label', `Selecionar pivô ANA ${id}, ${number.format(feature.properties.area_ha)} hectares`);
        path.setAttribute('aria-pressed', String(id === selectedId));
        if (preparedPaths.has(path)) return;
        preparedPaths.add(path);
        path.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            event.stopPropagation();
            choose(id);
          }
        });
      });
    },
  }).addTo(map);

  for (const [id, layer] of layers) {
    const label = textElement('span', 'ac-map-pivot-label', id);
    const marker = L.marker(layer.getBounds().getCenter(), {
      icon: L.divIcon({ className: 'ac-map-label-anchor', html: label, iconSize: null }),
      interactive: false,
      keyboard: false,
    }).addTo(labels);
    markers.set(id, marker);
  }

  const allBounds = polygons.getBounds();
  map.setMaxBounds(allBounds.pad(12));

  function fitAll() {
    map.fitBounds(allBounds, { padding: [44, 44], animate: false, maxZoom: 15.5 });
  }

  function select(pivotId) {
    const id = String(pivotId);
    if (!layers.has(id)) return;
    selectedId = id;
    for (const [key, layer] of layers) {
      const selected = key === id;
      layer.setStyle(selected ? selectedStyle : normalStyle);
      layer.getElement()?.setAttribute('aria-pressed', String(selected));
      markers.get(key)?.getElement()?.classList.toggle('ac-map-label-selected', selected);
      if (selected) layer.bringToFront();
    }
    const center = layers.get(id).getBounds().getCenter();
    if (!map.getBounds().pad(-0.14).contains(center)) map.panTo(center, { animate: false });
  }

  control('topleft', 'ac-map-location', element => {
    element.append(textElement('span', 'ac-map-location-eyebrow', 'ÁREA DE ESTUDO'));
    element.append(textElement('strong', '', 'Paracatu · Minas Gerais'));
    element.append(textElement('span', 'ac-map-location-sub', 'Bacia do rio São Marcos'));
  }).addTo(map);

  control('topright', 'ac-map-actions', element => {
    const fit = textElement('button', '', '⌖');
    fit.type = 'button';
    fit.title = 'Enquadrar todos os pivôs';
    fit.setAttribute('aria-label', 'Enquadrar todos os pivôs');
    fit.addEventListener('click', fitAll);
    const focus = textElement('button', '', '◎');
    focus.type = 'button';
    focus.title = 'Centralizar pivô selecionado';
    focus.setAttribute('aria-label', 'Centralizar pivô selecionado');
    focus.addEventListener('click', () => {
      if (selectedId) map.fitBounds(layers.get(selectedId).getBounds(), { padding: [68, 68], animate: false, maxZoom: 16.5 });
    });
    element.append(fit, focus);
  }).addTo(map);

  control('bottomleft', 'ac-map-legend', element => {
    const line = document.createElement('div');
    line.append(textElement('i', 'ac-map-swatch', ''), textElement('span', '', 'Pivôs ANA'));
    const selected = document.createElement('div');
    selected.append(textElement('i', 'ac-map-swatch ac-map-swatch-selected', ''), textElement('span', '', 'Selecionado'));
    const toggleLabel = document.createElement('label');
    const toggle = document.createElement('input');
    toggle.type = 'checkbox';
    toggle.checked = true;
    toggle.setAttribute('aria-label', 'Exibir camada de pivôs ANA');
    toggle.addEventListener('change', () => {
      if (toggle.checked) { polygons.addTo(map); labels.addTo(map); }
      else { map.removeLayer(polygons); map.removeLayer(labels); }
    });
    toggleLabel.append(toggle, textElement('span', '', 'Exibir polígonos'));
    element.append(line, selected, toggleLabel);
  }).addTo(map);

  control('bottomright', 'ac-map-orientation', element => {
    element.setAttribute('aria-label', 'Norte para cima');
    element.append(textElement('strong', '', 'N'), textElement('span', 'ac-map-north-arrow', '↑'));
  }).addTo(map);
  L.control.scale({ imperial: false, metric: true, position: 'bottomleft', maxWidth: 100 }).addTo(map);

  const coordinates = control('bottomright', 'ac-map-coordinates', element => {
    function show(latlng) { element.textContent = `${latlng.lat.toFixed(4)}° · ${latlng.lng.toFixed(4)}°`; }
    show(allBounds.getCenter());
    map.on('mousemove', event => show(event.latlng));
    map.on('moveend', () => show(map.getCenter()));
  });
  coordinates.addTo(map);

  function drawGraticule() {
    graticule.clearLayers();
    const bounds = map.getBounds();
    const span = Math.max(bounds.getEast() - bounds.getWest(), bounds.getNorth() - bounds.getSouth());
    const target = span / 5;
    const magnitude = 10 ** Math.floor(Math.log10(target));
    const spacing = [1, 2, 5, 10].map(value => value * magnitude).find(value => value >= target);
    const gridStyle = { pane: 'acGraticule', color: '#afbeb4', opacity: 0.46, weight: 1, dashArray: '3 6', interactive: false };
    for (let longitude = Math.ceil(bounds.getWest() / spacing) * spacing; longitude < bounds.getEast(); longitude += spacing) {
      L.polyline([[bounds.getSouth(), longitude], [bounds.getNorth(), longitude]], gridStyle).addTo(graticule);
    }
    for (let latitude = Math.ceil(bounds.getSouth() / spacing) * spacing; latitude < bounds.getNorth(); latitude += spacing) {
      L.polyline([[latitude, bounds.getWest()], [latitude, bounds.getEast()]], gridStyle).addTo(graticule);
    }
  }
  map.on('moveend zoomend resize', drawGraticule);
  fitAll();
  drawGraticule();
  const observer = new ResizeObserver(() => map.invalidateSize({ animate: false }));
  observer.observe(container);

  return {
    select,
    fitAll,
    invalidateSize() { map.invalidateSize({ animate: false }); },
    destroy() { observer.disconnect(); map.remove(); },
  };
}
