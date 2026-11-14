import { parseCSV } from './science.js';

const REQUIRED = ['pivots','observations','monthly','precipitation','quality','models','model_predictions','model_parameters','events','provenance','schemas','common_month_metrics','common_month_predictions','comparison_report','publication'];
export async function loadPackage(base = new URL('./data/', document.baseURI)) {
  async function get(relative) {
    if (typeof relative !== 'string' || !/^[a-zA-Z0-9_./-]+$/.test(relative) || relative.includes('..') || relative.startsWith('/')) throw new Error('Caminho inválido no manifesto.');
    const response = await fetch(new URL(relative, base));
    if (!response.ok) throw new Error(`Não foi possível carregar ${relative} (HTTP ${response.status}).`);
    return new Uint8Array(await response.arrayBuffer());
  }
  const decode = bytes => new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  const manifest = JSON.parse(decode(await get('manifest.json')));
  if (manifest.contract_version !== '1.0.0' || REQUIRED.some(name => !manifest.files?.[name])) throw new Error('Pacote incompatível: contrato WebGIS 1.0.0 incompleto.');
  const raw = Object.fromEntries(await Promise.all(Object.entries(manifest.files).map(async ([name, file]) => {
    const bytes = await get(file.path);
    if (bytes.byteLength !== file.bytes) throw new Error(`Integridade inválida: tamanho de ${name}.`);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    if (digest !== file.sha256) throw new Error(`Integridade inválida: SHA-256 de ${name}.`);
    return [name, decode(bytes)];
  })));
  const schemas = JSON.parse(raw.schemas);
  const data = { manifest };
  for (const [name, text] of Object.entries(raw)) data[name] = manifest.files[name].format === 'csv' ? parseCSV(text, schemas.$defs[name]) : JSON.parse(text);
  if (data.monthly.length !== 180 || data.observations.length !== 256 || data.pivots.features.length !== 5) throw new Error('O pacote não corresponde à demonstração científica congelada.');
  return data;
}
