import { readFile, readdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { validateRegionalCatalog, validateRegionalEvidence } from '../src/regions.js';
import { sha256, validatePublicText } from './validate-data.mjs';

async function walk(root, prefix = '') {
  const paths = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) throw new Error('Catálogo regional: link simbólico proibido.');
    const name = `${prefix}${entry.name}`;
    if (entry.isDirectory()) paths.push(...await walk(resolve(root, entry.name), `${name}/`));
    else if (entry.isFile()) paths.push(name);
    else throw new Error('Catálogo regional: arquivo inválido.');
  }
  return paths.sort();
}

export async function validateRegions(root = fileURLToPath(new URL('../regions/', import.meta.url))) {
  const catalogBytes = await readFile(resolve(root, 'catalog.json'));
  validatePublicText(catalogBytes.toString('utf8'), 'catalog.json');
  const catalog = validateRegionalCatalog(JSON.parse(catalogBytes));
  const descriptor = catalog.regional.package;
  const payloadBytes = await readFile(resolve(root, descriptor.path));
  if (payloadBytes.length !== descriptor.bytes || sha256(payloadBytes) !== descriptor.sha256) throw new Error('Catálogo regional: SHA-256/tamanho divergente.');
  validatePublicText(payloadBytes.toString('utf8'), 'regional.json');
  const evidence = validateRegionalEvidence(JSON.parse(payloadBytes), catalog);
  const images = [];
  for (const image of catalog.regional.images) {
    const bytes = await readFile(resolve(root, image.path));
    if (bytes.length !== image.bytes || sha256(bytes) !== image.sha256 || bytes.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a') throw new Error('Catálogo regional: imagem PNG divergente.');
    images.push({ descriptor: image, bytes });
  }
  const paths = ['catalog.json', descriptor.path, ...catalog.regional.images.map(image => image.path)].sort();
  if (JSON.stringify(await walk(root)) !== JSON.stringify(paths)) throw new Error('Catálogo regional: arquivos não declarados.');
  return { catalog, evidence, images, files: paths, catalogBytes, payloadBytes };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await validateRegions(process.argv[2]); console.log('Catálogo e pacote regional íntegros.');
}
