// Read-only release audit: compare the deployed bytes with the verified build.
// This never starts a server or acquires scientific source imagery.
import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { verifyDist } from './verify-dist.mjs';

const web = fileURLToPath(new URL('../', import.meta.url));
const origin = 'https://altaeir-13.github.io/FTL-Final-Project/';
const dist = resolve(web,'dist');
const output = resolve(web,'../docs/evidencias/release-publica/integridade-publica.json');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const artifact = await verifyDist(dist);
async function walk(directory, prefix='') {
  const entries = await readdir(directory,{withFileTypes:true});
  const files=[];
  for(const entry of entries) {
    if(entry.isSymbolicLink()) throw Error('Link simbólico inesperado no artefato.');
    const path=`${prefix}${entry.name}`;
    if(entry.isDirectory()) files.push(...await walk(resolve(directory,entry.name),`${path}/`));
    else files.push(path);
  }
  return files.sort();
}
const localFiles=await walk(dist);
const files=localFiles.filter(path=>path!=='.nojekyll'), verified=[];
const markerResponse=await fetch(new URL('.nojekyll',origin),{cache:'no-store',signal:AbortSignal.timeout(30_000)});
const markerBytes=await readFile(resolve(dist,'.nojekyll'));
if(markerBytes.length!==0 || ![200,404].includes(markerResponse.status)) throw Error('Marcador de deployment inesperado.');
if(markerResponse.ok && (await markerResponse.arrayBuffer()).byteLength!==0) throw Error('Marcador público divergente.');
for(let index=0;index<files.length;index+=5) {
  verified.push(...await Promise.all(files.slice(index,index+5).map(async path=>{
    const url=new URL(path,origin).href;
    const response=await fetch(url,{cache:'no-store',signal:AbortSignal.timeout(30_000)});
    if(!response.ok || response.url!==url) throw Error(`Arquivo público indisponível: ${path} HTTP ${response.status}`);
    const remote=Buffer.from(await response.arrayBuffer());
    const local=await readFile(resolve(dist,path));
    if(!remote.equals(local)) throw Error(`Bytes publicados divergem do artefato verificado: ${path}`);
    return {path,url,bytes:remote.length,sha256:digest(remote),http_status:response.status,identical:true};
  })));
}
const publicHash=digest(Buffer.from(verified.map(file=>`${file.path}\0${file.sha256}`).join('\n')));
const result={reference_date:'2026-11-17',checked_at_utc:new Date().toISOString(),site:origin,
  deployed_commit:'ad107d0c29c63ad9eb9f91a5970d96906676e3df',deployment_workflow:44067496065,
  server_started:false,all_served_files_identical:true,public_files_sha256:publicHash,
  verified_build_artifact_sha256:artifact.artifact_sha256,
  deployment_only_marker:{path:'.nojekyll',build_bytes:markerBytes.length,build_sha256:digest(markerBytes),http_status:markerResponse.status,role:'Build marker; not a required runtime resource.'},
  paracatu_package_sha256:artifact.package_sha256,regional_package_sha256:artifact.regional_sha256,
  files:verified};
await mkdir(resolve(output,'..'),{recursive:true});
await writeFile(output,JSON.stringify(result,null,2)+'\n');
console.log(`Publicação íntegra: ${verified.length} arquivos servidos idênticos; build SHA-256 ${artifact.artifact_sha256}; .nojekyll HTTP ${markerResponse.status}`);
