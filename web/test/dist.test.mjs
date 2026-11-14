import test from 'node:test';
import assert from 'node:assert/strict';
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyDist, PAGES_BASE } from '../scripts/verify-dist.mjs';

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const reviewRoot = resolve(webRoot, '../.local-review');
const scriptName = 'assets/app-Verify123.js';
const styleName = 'assets/style-Verify123.css';
const markName = 'assets/mark-Verify123.svg';

async function artifact(t, { script = '', style = '', html } = {}) {
  await mkdir(reviewRoot, { recursive: true });
  const directory = await mkdtemp(resolve(reviewRoot, 'web-dist-'));
  t.after(async () => {
    assert.ok(directory.startsWith(`${reviewRoot}${sep}`));
    await rm(directory, { recursive: true, force: true });
  });
  await mkdir(resolve(directory, 'assets'));
  await cp(resolve(webRoot, 'data'), resolve(directory, 'data'), { recursive: true });
  await writeFile(resolve(directory, '.nojekyll'), '');
  await writeFile(resolve(directory, 'index.html'), html ?? `<!doctype html><html lang="pt-BR"><head><script type="module" src="${PAGES_BASE}${scriptName}"></script><link rel="stylesheet" href="${PAGES_BASE}${styleName}"></head><body><div id="app"></div></body></html>`);
  await writeFile(resolve(directory, scriptName), `const mark="${PAGES_BASE}${markName}";${script}`);
  await writeFile(resolve(directory, styleName), `body{color:#112d2b;background-image:url("data:image/svg+xml,%3Csvg/%3E")} ${style}`);
  await writeFile(resolve(directory, markName), '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0h10v10H0Z"/></svg>');
  return directory;
}

test('static verifier accepts only local reachable assets at the explicit GitHub Pages project base', async t => {
  const directory = await artifact(t);
  const result = await verifyDist(directory);
  assert.equal(result.base, '/FTL-Final-Project/');
  assert.equal(result.assets, 3);
  assert.equal(result.files, 21);
  assert.equal(result.source_package_sha256, '16094dc7ef7ae3e6881b86bc0cbb0ff7b146f0558fc0947957865026882360a3');
  assert.equal(result.package_sha256, '7a072a6e29688039b5b775663262ecf6338b35c41386264e75ee789f93068a4d');
});

test('copied scientific payloads and complete artifact digest are deterministic', async t => {
  const first = await artifact(t); const second = await artifact(t);
  const resultA = await verifyDist(first); const resultB = await verifyDist(second);
  assert.equal(resultA.artifact_sha256, resultB.artifact_sha256);
  assert.equal(resultA.total_bytes, resultB.total_bytes);
  const sourceManifest = await readFile(resolve(webRoot, 'data/manifest.json'));
  assert.deepEqual(await readFile(resolve(first, 'data/manifest.json')), sourceManifest);
});

test('missing JavaScript, CSS and JavaScript-referenced image each fail explicitly', async t => {
  for (const asset of [scriptName, styleName, markName]) {
    const directory = await artifact(t); await rm(resolve(directory, asset));
    await assert.rejects(verifyDist(directory), /asset local obrigatório ausente/);
  }
});

test('entry assets cannot use relative paths or hosting domain root', async t => {
  for (const badBase of ['./', '/']) {
    const directory = await artifact(t);
    const index = await readFile(resolve(directory, 'index.html'), 'utf8');
    await writeFile(resolve(directory, 'index.html'), index.replaceAll(PAGES_BASE, badBase));
    await assert.rejects(verifyDist(directory), /asset de entrada deve usar|caminho na raiz do domínio/);
  }
});

test('HTML/CSS remote dependencies and literal network calls fail, while documentation strings are allowed', async t => {
  const remoteScript = await artifact(t, { script: 'fetch("https://tiles.example.org/grid");' });
  await assert.rejects(verifyDist(remoteScript), /dependência remota em chamada de runtime/);
  const remoteTiles = await artifact(t, { script: 'L.tileLayer("https://tiles.example.org/{z}/{x}/{y}.png");' });
  await assert.rejects(verifyDist(remoteTiles), /dependência remota em chamada de runtime/);
  const remoteCSS = await artifact(t, { style: '@import "https://cdn.example.org/font.css";' });
  await assert.rejects(verifyDist(remoteCSS), /asset remoto/);
  const remoteHTML = await artifact(t);
  const index = await readFile(resolve(remoteHTML, 'index.html'), 'utf8');
  await writeFile(resolve(remoteHTML, 'index.html'), index.replace(`${PAGES_BASE}${scriptName}`, 'https://cdn.example.org/app.js'));
  await assert.rejects(verifyDist(remoteHTML), /asset remoto/);
  const helpOnly = await artifact(t, { script: 'const docs="https://leafletjs.com";const svgNS="http://www.w3.org/2000/svg";const example="http://localhost:3000";' });
  await assert.doesNotReject(verifyDist(helpOnly));
});

test('only declared data and referenced build assets may be published', async t => {
  for (const extra of ['.env', 'credentials.json', 'assets/app-Verify123.js.map', 'node_modules/library.js', 'assets/unreferenced-Extra123.js']) {
    const directory = await artifact(t);
    if (extra.startsWith('node_modules/')) await mkdir(resolve(directory, 'node_modules'));
    await writeFile(resolve(directory, extra), 'fixture');
    await assert.rejects(verifyDist(directory), /arquivo não permitido|asset não referenciado/);
  }
});

test('private environment paths, credentials and source-map comments cannot enter a runtime bundle', async t => {
  for (const script of ['const source="C:\\Users\\researcher\\secret";', 'const token="Bearer abcdefsecret";', '//# sourceMappingURL=app.js.map']) {
    const directory = await artifact(t, { script });
    await assert.rejects(verifyDist(directory), /caminho privado|credencial|source map/);
  }
});

test('corruption of the copied scientific package fails integrity validation', async t => {
  const directory = await artifact(t);
  const manifest = JSON.parse(await readFile(resolve(directory, 'data/manifest.json'), 'utf8'));
  const file = resolve(directory, 'data', manifest.files.models.path);
  const bytes = await readFile(file); bytes[20] ^= 1;
  await writeFile(file, bytes);
  await assert.rejects(verifyDist(directory), /SHA-256 divergente/);
});
