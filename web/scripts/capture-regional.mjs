// Authentic browser captures of the production build; no composited interface.
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const webRoot = fileURLToPath(new URL('../', import.meta.url));
const output = resolve(webRoot, '../docs/images');
const port = 4186;
const base = `http://127.0.0.1:${port}/FTL-Final-Project/`;
const server = spawn(process.execPath, ['serve.mjs'], { cwd:webRoot, env:{ ...process.env, PORT:String(port) }, windowsHide:true, stdio:'ignore' });
let browser;
try {
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if ((await fetch(base)).ok) break; } catch { /* the local server is starting */ }
    if (attempt === 99) throw new Error('Servidor de captura indisponível.');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  await mkdir(output, { recursive:true });
  browser = await chromium.launch({ channel:process.env.PLAYWRIGHT_CHANNEL || 'msedge', headless:true });
  const page = await browser.newPage({ viewport:{ width:1440, height:1100 }, deviceScaleFactor:1, reducedMotion:'reduce' });
  await page.goto(base);
  await page.locator('#study-select').waitFor();
  await page.screenshot({ path:resolve(output, 'webgis-studies.png') });
  await page.locator('#study-select').selectOption('guadalupe-pi');
  await page.locator('#regional-map path[role="button"]').first().waitFor();
  await page.locator('#regional-study-detail').screenshot({ path:resolve(output, 'webgis-regional.png') });
  await page.locator('.regional-image-comparison').screenshot({ path:resolve(output, 'webgis-real-comparison.png') });
  await page.setViewportSize({ width:390, height:844 });
  await page.locator('#estudos').scrollIntoViewIfNeeded();
  await page.screenshot({ path:resolve(output, 'webgis-regional-mobile.png') });
  console.log('Capturas reais salvas em docs/images/webgis-{studies,regional,real-comparison,regional-mobile}.png');
} finally {
  if (browser) await browser.close();
  server.kill();
}
