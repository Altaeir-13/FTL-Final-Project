// Captures only the production artifact; never injects or composites UI content.
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { verifyDist } from './verify-dist.mjs';
const root = fileURLToPath(new URL('../', import.meta.url));
const images = resolve(root, '../docs/images');
const qa = resolve(root, '../build/phase7-print');
const base = 'http://127.0.0.1:4197/FTL-Final-Project/';
const server = spawn(process.execPath, ['serve.mjs'], { cwd:root, env:{ ...process.env, PORT:'4197' }, windowsHide:true, stdio:'ignore' });
let browser;
try {
  for (let attempt=0; attempt<100; attempt++) {
    try { if ((await fetch(base)).ok) break; } catch { /* starting server */ }
    if (attempt===99) throw new Error('Servidor de produção indisponível.');
    await new Promise(resolve => setTimeout(resolve,100));
  }
  await mkdir(images,{recursive:true}); await mkdir(qa,{recursive:true});
  browser=await chromium.launch({ channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless:true });
  const page=await browser.newPage({ viewport:{width:1440,height:1100},reducedMotion:'reduce' });
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`${base}?pivot=8087&a=2023-07&b=2024-07#territorio`);
  await page.locator('#investigation-a').waitFor();
  await page.locator('#territorio').screenshot({path:resolve(images,'phase7-territorio.png')});
  await page.locator('#investigacao').screenshot({path:resolve(images,'phase7-investigacao-paracatu.png')});
  await page.locator('#generate-evidence').click();
  await page.locator('#evidence-report[open]').waitFor();
  await page.pdf({path:resolve(qa,'ficha-paracatu.pdf'),format:'A4',preferCSSPageSize:true,printBackground:true});
  await page.locator('#evidence-close').click();
  await page.locator('#investigation-region').selectOption('guadalupe-pi');
  await page.locator('#investigation-a').selectOption('2023-07-18');
  await page.locator('#investigation-b').selectOption('2024-07-22');
  await page.locator('#investigation-images img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
  await page.locator('#investigacao').screenshot({path:resolve(images,'phase7-investigacao-guadalupe.png')});
  await page.locator('#generate-evidence').click();
  await page.locator('#evidence-report[open]').waitFor();
  await page.locator('#evidence-report img').evaluateAll(imgs=>Promise.all(imgs.map(img=>img.decode())));
  await page.screenshot({path:resolve(images,'phase7-ficha.png')});
  await page.pdf({path:resolve(qa,'ficha-guadalupe.pdf'),format:'A4',preferCSSPageSize:true,printBackground:true});
  const identity=await page.locator('[data-report-id]').textContent();
  await page.locator('#evidence-close').click();
  await page.locator('#start-demo').click();
  for(let step=0;step<3;step++) await page.locator('[data-demo=next]').click();
  await page.locator('#investigacao').scrollIntoViewIfNeeded();
  await page.screenshot({path:resolve(images,'phase7-demonstracao.png')});
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:390,height:844});
  await page.locator('#investigacao').scrollIntoViewIfNeeded();
  await page.screenshot({path:resolve(images,'phase7-mobile.png')});
  if(errors.length) throw new Error(errors.join('\n'));
  const files=['phase7-territorio.png','phase7-investigacao-paracatu.png','phase7-investigacao-guadalupe.png','phase7-ficha.png','phase7-demonstracao.png','phase7-mobile.png'];
  const artifact = await verifyDist(resolve(root,'dist'));
  const evidence={reference_date:'2026-11-16',artifact:'Vite production build',artifact_sha256:artifact.artifact_sha256,browser:'Chromium / Microsoft Edge',report_investigation_id:identity,captures:[]};
  for(const file of files){const bytes=await readFile(resolve(images,file));evidence.captures.push({file,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});}
  await writeFile(resolve(qa,'captures.json'),JSON.stringify(evidence,null,2)+'\n');
  console.log(`Capturas reais em docs/images/phase7-*.png. Fichas A4 em build/phase7-print/. Investigação ${identity}`);
} finally { await browser?.close();server.kill(); }
