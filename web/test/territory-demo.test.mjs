import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { TERRITORIAL_POINTS, TERRITORIAL_SOURCE, projectTerritorialPoint, territorialPath } from '../src/territorial-overview.js';
import { DEMO_STEPS, demoTransition } from '../src/demo-mode.js';

const readJSON = async name => JSON.parse(await readFile(new URL(name, import.meta.url), 'utf8'));

test('territorial presentation bundles the attributed 27-state IBGE geometry byte for byte', async () => {
  const bytes = await readFile(new URL('../src/brazil-states.json', import.meta.url));
  assert.equal(bytes.length, TERRITORIAL_SOURCE.bytes);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), TERRITORIAL_SOURCE.sha256);
  const brazil = JSON.parse(bytes);
  assert.equal(brazil.type, 'FeatureCollection');
  assert.equal(brazil.features.length, 27);
  assert.deepEqual(brazil.features.map(feature => feature.properties.codarea).sort(), ['11','12','13','14','15','16','17','21','22','23','24','25','26','27','28','29','31','32','33','35','41','42','43','50','51','52','53']);
  assert.match(TERRITORIAL_SOURCE.url, /^https:\/\/servicodados\.ibge\.gov\.br\/api\/v3\/malhas/);
  for (const feature of brazil.features) {
    const path = territorialPath(feature.geometry);
    assert.match(path, /^M[\d.]+,[\d.]+ L/);
    assert.ok(!/NaN|Infinity|undefined/.test(path));
  }
});

test('territorial references distinguish Caxias origin from the two processed studies', () => {
  assert.deepEqual(TERRITORIAL_POINTS.map(point => point.id), ['caxias-ma', 'paracatu-mg', 'guadalupe-pi']);
  const [caxias, paracatu, guadalupe] = TERRITORIAL_POINTS;
  assert.equal(caxias.studyId, null);
  assert.equal(caxias.status, 'origin');
  assert.match(caxias.description, /Não há observações espectrais processadas/);
  assert.match(caxias.reference, /Sede municipal pública/);
  assert.deepEqual(caxias.coordinates, [-43.358539429000018, -4.8616749898404166]);
  assert.equal(paracatu.status, 'completed');
  assert.equal(guadalupe.status, 'exploratory');
  assert.match(guadalupe.description, /Sem modelo regional validado/);
  assert.ok(TERRITORIAL_POINTS.every(point => Object.isFrozen(point) && Object.isFrozen(point.coordinates)));
});

test('study markers derive from the exact published polygons without replacing their geometry', async () => {
  const paracatu = await readJSON('../data/packages/7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d/pivots.geojson');
  const catalog = await readJSON('../regions/catalog.json');
  const regional = await readJSON(`../regions/${catalog.regional.package.path}`);
  function boundsCenter(geojson) {
    const points = [];
    const walk = coordinates => typeof coordinates[0] === 'number' ? points.push(coordinates) : coordinates.forEach(walk);
    geojson.features.forEach(feature => walk(feature.geometry.coordinates));
    return [0,1].map(axis => (Math.min(...points.map(point => point[axis])) + Math.max(...points.map(point => point[axis]))) / 2);
  }
  assert.deepEqual(TERRITORIAL_POINTS[1].coordinates, boundsCenter(paracatu));
  assert.deepEqual(TERRITORIAL_POINTS[2].coordinates, boundsCenter(regional.pivots));
  for (const point of TERRITORIAL_POINTS) {
    const [x,y] = projectTerritorialPoint(point.coordinates);
    assert.ok(x > 0 && x < 500 && y > 0 && y < 470);
  }
  assert.throws(() => projectTerritorialPoint([NaN, 0]), /inválida/);
  assert.throws(() => projectTerritorialPoint([999, 0]), /inválida/);
  assert.throws(() => territorialPath({ type: 'Point', coordinates: [0,0] }), /incompatível/);
});

test('FTL demo follows five deterministic manual steps and respects boundaries', () => {
  assert.deepEqual(DEMO_STEPS.map(step => step.id), ['problem','paracatu','investigation','guadalupe','limits']);
  assert.deepEqual(DEMO_STEPS.map(step => step.target), ['territorio','explorar','investigacao','investigacao','investigacao']);
  let state = demoTransition(undefined, 'start');
  assert.deepEqual(state, { active: true, index: 0 });
  state = demoTransition(state, 'back'); assert.equal(state.index, 0);
  for (let index = 1; index < 5; index++) { state = demoTransition(state, 'next'); assert.equal(state.index, index); }
  assert.deepEqual(demoTransition(state, 'next'), { active: true, index: 4 });
  assert.deepEqual(demoTransition(state, 'back'), { active: true, index: 3 });
  assert.deepEqual(demoTransition(state, 'restart'), { active: true, index: 0 });
  const stopped = demoTransition(state, 'end');
  assert.deepEqual(stopped, { active: false, index: 4 });
  assert.deepEqual(demoTransition(stopped, 'next'), stopped);
  assert.throws(() => demoTransition(state, 'automaticTimer'), /desconhecida/);
  assert.ok(DEMO_STEPS.every(step => Object.isFrozen(step)));
});
