// Audit the exact static artifact shipped to the GitHub Pages project path.
// Documentation/provenance URLs are allowed; fetched runtime assets are local.
import { readFile, readdir, realpath } from 'node:fs/promises';
import { resolve, relative, sep, posix } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { validatePackage, sha256 } from './validate-data.mjs';

export const PAGES_BASE = '/FTL-Final-Project/';
const webRoot = fileURLToPath(new URL('../', import.meta.url));
const snapshotRoot = resolve(webRoot, 'data');
const origin = 'https://aquaclima.invalid';
const assetName = /^[A-Za-z0-9_-]+-[A-Za-z0-9_-]+\.(?:js|css|svg|png|jpe?g|webp|ico|woff2?)$/i;
const textExtensions = new Set(['.html', '.js', '.css', '.svg']);
const assert = (condition, message) => { if (!condition) throw new Error(`Build estático WebGIS: ${message}`); };
const decode = bytes => new TextDecoder('utf-8', { fatal: true }).decode(bytes);

async function walk(directory, prefix = '') {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const name = `${prefix}${entry.name}`;
    assert(!entry.isSymbolicLink(), `link simbólico não permitido: ${name}`);
    if (entry.isDirectory()) files.push(...await walk(resolve(directory, entry.name), `${name}/`));
    else { assert(entry.isFile(), `tipo de arquivo não permitido: ${name}`); files.push(name); }
  }
  return files.sort();
}

function checkPrivateText(text, name) {
  assert(!/(?<![A-Za-z])[A-Za-z]:[\\/]|\/(?:Users|home|private\/var)\//i.test(text), `${name}: caminho privado do ambiente`);
  assert(!/[?&](?:sig|token|access_token|api_key|x-amz-signature|se|sp|sv)=|Bearer\s+[A-Za-z0-9._-]+|AKIA[0-9A-Z]{16}/i.test(text), `${name}: credencial ou assinatura temporária`);
  assert(!/\b(?:api_key|access_token|password|client_secret)\s*[:=]\s*["'][^"']+["']/i.test(text), `${name}: possível segredo embutido`);
  assert(!/[#@]\s*sourceMappingURL\s*=/.test(text), `${name}: source map não permitido`);
}

function checkRuntimeCalls(text, name) {
  const external = String.raw`(?:https?:)?\/\/`;
  const calls = [
    new RegExp(String.raw`\b(?:fetch|importScripts)\s*\(\s*["'\x60]${external}`, 'i'),
    new RegExp(String.raw`\bimport\s*\(\s*["'\x60]${external}`, 'i'),
    new RegExp(String.raw`\b(?:WebSocket|EventSource|Worker|SharedWorker|TileLayer|tileLayer)\s*\(\s*["'\x60]${external}`, 'i'),
    new RegExp(String.raw`\.\s*open\s*\(\s*["'](?:GET|POST|PUT|HEAD)["']\s*,\s*["'\x60]${external}`, 'i'),
    new RegExp(String.raw`\.\s*src\s*=\s*["'\x60]${external}`, 'i'),
  ];
  assert(!calls.some(pattern => pattern.test(text)), `${name}: dependência remota em chamada de runtime (CDN, tiles ou servidor externo)`);
  // Literal imports execute when the module loads; unlike library help URLs,
  // they represent actual runtime dependencies.
  assert(!/\bimport\s*(?:[^;\n]*?\sfrom\s*)?["'](?:https?:)?\/\//i.test(text), `${name}: import remoto não permitido`);
  assert(!/["']\/(?:assets|data)\//.test(text), `${name}: caminho na raiz do domínio fora de ${PAGES_BASE}`);
}

function attrs(text) {
  return Object.fromEntries([...text.matchAll(/([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g)]
    .map(match => [match[1].toLowerCase(), match[2] ?? match[3] ?? match[4]]));
}

function markupReferences(text, name) {
  const references = [];
  for (const match of text.matchAll(/<([a-zA-Z][\w:-]*)\b([^>]*)>/g)) {
    const tag = match[1].toLowerCase(); const attributes = attrs(match[2]);
    assert(tag !== 'base', `${name}: elemento base não permitido; use o caminho explícito de projeto`);
    if (attributes.src) references.push({ value: attributes.src, entry: name === 'index.html' });
    if (attributes.poster) references.push({ value: attributes.poster, entry: name === 'index.html' });
    if (tag === 'link' && /(?:^|\s)(?:stylesheet|icon|modulepreload|preload|manifest)(?:\s|$)/.test(attributes.rel ?? '')) {
      assert(attributes.href, `${name}: recurso link sem href`);
      references.push({ value: attributes.href, entry: name === 'index.html' });
    }
    if (['image', 'use'].includes(tag) && (attributes.href || attributes['xlink:href'])) {
      references.push({ value: attributes.href || attributes['xlink:href'], entry: false });
    }
    if (attributes.srcset) {
      for (const source of attributes.srcset.split(',')) references.push({ value: source.trim().split(/\s+/)[0], entry: name === 'index.html' });
    }
    // Ordinary anchor href values link scientific documents; they are not loaded
    // as page assets and are intentionally not treated as network dependencies.
  }
  return references;
}

function cssReferences(text) {
  const refs = [...text.matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^\s)]*))\s*\)/gi)]
    .map(match => ({ value: match[1] ?? match[2] ?? match[3], entry: false }));
  for (const match of text.matchAll(/@import\s*(?:url\([^)]*\)|["']([^"']+)["'])/gi)) {
    if (match[1]) refs.push({ value: match[1], entry: false });
  }
  return refs;
}

function javascriptReferences(text) {
  const refs = [];
  for (const match of text.matchAll(/["']((?:\/FTL-Final-Project\/|\.\.?\/|\/)?assets\/[A-Za-z0-9_./-]+\.(?:js|css|svg|png|jpe?g|webp|ico|woff2?))["']/gi)) {
    refs.push({ value: match[1], entry: false, fromBase: match[1].startsWith('assets/') });
  }
  for (const pattern of [/\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
    /\bimport\s*(?:[^;\n]*?\sfrom\s*)?["']([^"']+)["']/g,
    /\bexport\s+[^;\n]*?\sfrom\s*["']([^"']+)["']/g]) {
    for (const match of text.matchAll(pattern)) refs.push({ value: match[1], entry: false });
  }
  return refs;
}

function localReference(reference, source) {
  const value = reference.value;
  if (!value || value.startsWith('#')) return null;
  // Vite/Leaflet inline small icons; an embedded bitmap/font needs no request.
  if (/^data:(?:image\/[-+.\w]+|font\/[-+.\w]+|application\/font-woff)(?:;[^,]*)?,/i.test(value)) return null;
  assert(!/^(?:[A-Za-z][\w+.-]*:|\/\/)/.test(value), `${source}: asset remoto ou protocolo não permitido: ${value}`);
  assert(!/[\\%]/.test(value), `${source}: caminho de asset inválido`);
  if (reference.entry) assert(value.startsWith(`${PAGES_BASE}assets/`), `${source}: asset de entrada deve usar ${PAGES_BASE}assets/`);
  const sourceURL = `${origin}${PAGES_BASE}${source}`;
  const target = new URL(value, reference.fromBase ? `${origin}${PAGES_BASE}` : sourceURL);
  assert(target.origin === origin && target.pathname.startsWith(`${PAGES_BASE}assets/`)
    && !target.search, `${source}: asset fora do caminho de projeto ${PAGES_BASE}`);
  const path = target.pathname.slice(PAGES_BASE.length);
  assert(!path.split('/').some(part => part === '..' || part === 'node_modules') && assetName.test(posix.basename(path)), `${source}: nome de asset não permitido: ${path}`);
  return path;
}

export async function verifyDist(directory = resolve(webRoot, 'dist')) {
  const root = await realpath(resolve(directory));
  const files = await walk(root); const fileSet = new Set(files);
  assert(fileSet.has('index.html') && fileSet.has('.nojekyll'), 'index.html ou .nojekyll obrigatório ausente');
  assert((await readFile(resolve(root, '.nojekyll'))).length === 0, '.nojekyll deve ser vazio');
  const data = await validatePackage(resolve(root, 'data'), { publicOnly: true });
  const snapshot = await validatePackage(snapshotRoot, { publicOnly: true });
  const expectedData = ['data/manifest.json', ...Object.values(data.manifest.files).map(file => `data/${file.path}`)];
  const permittedData = new Set(expectedData);
  for (const name of files) {
    const allowed = name === 'index.html' || name === '.nojekyll' || permittedData.has(name)
      || (name.startsWith('assets/') && name.split('/').length === 2 && assetName.test(posix.basename(name)));
    assert(allowed, `arquivo não permitido na publicação: ${name}`);
    const actual = await realpath(resolve(root, name));
    assert(!relative(root, actual).startsWith(`..${sep}`), `arquivo fora do artefato: ${name}`);
  }
  assert(data.manifestBytes.equals(snapshot.manifestBytes), 'manifesto dist difere do snapshot versionado');
  for (const file of Object.values(snapshot.manifest.files)) {
    const output = await readFile(resolve(root, 'data', file.path));
    assert(output.equals(snapshot.payloads[posix.basename(file.path)]), `${file.path}: cópia científica não é byte a byte`);
  }
  const html = decode(await readFile(resolve(root, 'index.html')));
  assert(/<html\b[^>]*lang=["']pt-BR["']/i.test(html), 'documento deve declarar lang="pt-BR"');
  assert(/<script\b[^>]*type=["']module["'][^>]*src=/i.test(html), 'entrada JavaScript module ausente');
  assert(/<link\b[^>]*rel=["']stylesheet["']/i.test(html), 'folha de estilo de entrada ausente');
  const reachable = new Set(); const queue = ['index.html']; let totalBytes = 0;
  while (queue.length) {
    const name = queue.shift(); const bytes = await readFile(resolve(root, name));
    if (!textExtensions.has(posix.extname(name))) continue;
    const text = decode(bytes); checkPrivateText(text, name);
    const extension = posix.extname(name);
    if (extension === '.js' || extension === '.html') checkRuntimeCalls(text, name);
    const refs = extension === '.css' ? cssReferences(text) : extension === '.js' ? javascriptReferences(text) : markupReferences(text, name);
    for (const reference of refs) {
      const target = localReference(reference, name);
      if (!target) continue;
      assert(fileSet.has(target), `asset local obrigatório ausente: ${target} (referenciado por ${name})`);
      if (!reachable.has(target)) { reachable.add(target); queue.push(target); }
    }
  }
  for (const name of files) {
    if (name.startsWith('assets/')) assert(reachable.has(name), `asset não referenciado não permitido: ${name}`);
    totalBytes += (await readFile(resolve(root, name))).length;
  }
  return { directory: root, base: PAGES_BASE, files: files.length, assets: reachable.size,
    total_bytes: totalBytes, package_sha256: data.manifest.package_sha256,
    source_package_sha256: data.manifest.source_package_sha256,
    artifact_sha256: sha256(Buffer.from(await Promise.all(files.map(async name => `${name}\0${sha256(await readFile(resolve(root, name)))}`)).then(rows => rows.join('\n')))) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const result = await verifyDist(process.argv[2] ? resolve(process.argv[2]) : undefined);
    console.log(`Artefato estático verificado: ${result.files} arquivos, ${result.assets} assets, base ${result.base}, SHA-256 ${result.artifact_sha256}`);
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
