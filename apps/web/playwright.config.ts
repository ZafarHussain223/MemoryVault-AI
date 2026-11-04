import {defineConfig, devices} from '@playwright/test';
import path from 'node:path';
const root = path.resolve(__dirname, '../..');
const python = process.env.MV_TEST_PYTHON || 'python';
export default defineConfig({
  testDir: './e2e', fullyParallel: false, workers: 1, timeout: 60000,
  expect: {timeout: 10000}, reporter: [['list'], ['html', {open:'never'}]],
  use: {baseURL:'http://127.0.0.1:3100', trace:'retain-on-failure', screenshot:'only-on-failure'},
  projects: [{name:'chromium',use:{...devices['Desktop Chrome'],channel:process.platform==='win32'?'chrome':undefined}}],
  webServer: process.env.MV_E2E_EXTERNAL_SERVERS ? undefined : [
    {command:`"${python}" scripts/e2e_api.py`,cwd:root,url:'http://127.0.0.1:8100/api/v1/health',timeout:60000,reuseExistingServer:false},
    {command:'npm run dev -- --port 3100',url:'http://127.0.0.1:3100',timeout:180000,reuseExistingServer:false,
      env:{API_URL:'http://127.0.0.1:8100',NEXT_DIST_DIR:'.next-e2e',NEXT_TELEMETRY_DISABLED:'1'}}
  ],
});
