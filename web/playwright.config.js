import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const port = Number(process.env.PORT || 4173);
const publicBaseURL = process.env.PLAYWRIGHT_BASE_URL?.trim();
let baseURL = `http://127.0.0.1:${port}/FTL-Final-Project/`;
if (publicBaseURL) {
  const target = new URL(publicBaseURL);
  if (target.protocol !== 'https:' || target.hostname !== 'altaeir-13.github.io' || target.pathname !== '/FTL-Final-Project/' || target.port || target.username || target.password || target.search || target.hash) {
    throw new Error('PLAYWRIGHT_BASE_URL deve ser https://altaeir-13.github.io/FTL-Final-Project/ (HTTPS, caminho do projeto e barra final, sem credenciais, query ou fragmento).');
  }
  baseURL = target.href;
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: process.env.CI ? 2 : 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: 'test-results',
  use: {
    baseURL,
    ...devices['Desktop Chrome'],
    viewport: { width: 1440, height: 1000 },
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  // Public QA uses the deployed site directly and must never start or reuse a
  // local server that could hide missing GitHub Pages assets or dependencies.
  ...(!publicBaseURL ? { webServer: {
    command: 'node serve.mjs',
    cwd: fileURLToPath(new URL('.', import.meta.url)),
    url: baseURL,
    reuseExistingServer: true,
    timeout: 30_000,
    env: { PORT: String(port) },
  } } : {}),
});
