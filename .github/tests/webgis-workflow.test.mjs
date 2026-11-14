import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';

const workflow = (await readFile(new URL('../workflows/webgis.yml', import.meta.url), 'utf8')).replace(/\r\n/g, '\n');
const frontend = workflow.split('\n  frontend:\n')[1]?.split('\n  deploy:\n')[0];
const deployment = workflow.split('\n  deploy:\n')[1];

test('CI keeps the pinned Playwright supported Ubuntu runner instead of a moving latest image', () => {
  const runners = [...workflow.matchAll(/^    runs-on: (.+)$/gm)].map(match => match[1]);
  assert.deepEqual(runners, ['ubuntu-24.04', 'ubuntu-24.04', 'ubuntu-24.04']);
  assert.doesNotMatch(workflow, /ubuntu-latest|ubuntu-26\.04/);
});

test('CI runs on main pushes and every pull request without path filters', () => {
  const triggers = workflow.split('\non:\n')[1]?.split('\npermissions:\n')[0];
  assert.match(triggers, /push:\s*\n\s+branches: \[main\]/);
  assert.match(triggers, /\n  pull_request:\s*\n  workflow_dispatch:/);
  assert.doesNotMatch(triggers, /paths:|pull_request_target|codex\/|tags:/);
});

test('Pages artifact and deployment allow only main pushes or manual main runs', () => {
  const uploadGuard = frontend.match(/- name: Prepare Pages artifact\s*\n\s+if: (.+)/)?.[1];
  const deployGuard = deployment.match(/\n    if: (.+)/)?.[1];
  assert.ok(uploadGuard, 'Pages artifact must have an explicit branch/event gate');
  assert.ok(deployGuard, 'Pages deployment must have an explicit branch/event gate');
  const scenarios = [
    ['push', 'refs/heads/main', true],
    ['workflow_dispatch', 'refs/heads/main', true],
    ['pull_request', 'refs/heads/main', false],
    ['pull_request', 'refs/pull/12/merge', false],
    ['push', 'refs/heads/codex/aquaclima-webgis', false],
    ['workflow_dispatch', 'refs/heads/codex/aquaclima-webgis', false],
    ['push', 'refs/heads/development/historical-acquisition', false],
    ['workflow_dispatch', 'refs/heads/development/historical-acquisition', false],
    ['push', 'refs/tags/main', false],
    ['pull_request_target', 'refs/heads/main', false],
    ['workflow_run', 'refs/heads/main', false],
  ];
  for (const expression of [uploadGuard, deployGuard]) {
    for (const [event_name, ref, expected] of scenarios) {
      const actual = vm.runInNewContext(expression, { github: { event_name, ref } }, { timeout: 100 });
      assert.equal(actual, expected, `${event_name} on ${ref} must ${expected ? 'allow' : 'block'} publication`);
    }
  }
});

test('deployment waits for science and frontend and has scoped Pages permissions', () => {
  assert.match(workflow, /\npermissions:\n  contents: read\n/);
  assert.match(deployment, /needs: \[science, frontend\]/);
  assert.match(deployment, /permissions:\n      contents: read\n      pages: write\n      id-token: write/);
  assert.match(deployment, /environment:\n      name: github-pages/);
  assert.doesNotMatch(workflow.split('\n  deploy:\n')[0], /pages: write|id-token: write|contents: write/);
});

test('only verified static output becomes the Pages artifact', () => {
  const build = frontend.indexOf('run: npm run build');
  const verify = frontend.indexOf('run: npm run verify:dist');
  const browser = frontend.indexOf('run: npm run test:browser');
  const upload = frontend.indexOf('uses: actions/upload-pages-artifact@v4');
  assert.ok(build >= 0 && verify > build && browser > verify && upload > browser);
  assert.match(frontend, /uses: actions\/upload-pages-artifact@v4\n        with:\n          path: web\/dist/);
  assert.match(deployment, /uses: actions\/configure-pages@v5/);
  assert.match(deployment, /uses: actions\/deploy-pages@v4/);
});
