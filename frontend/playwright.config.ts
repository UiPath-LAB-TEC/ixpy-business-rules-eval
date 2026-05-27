import { defineConfig, devices } from '@playwright/test';

const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5174',
    ...devices['Desktop Chrome'],
    launchOptions: {
      executablePath: chromePath,
    },
  },
  webServer: {
    command: 'npm run dev -- --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174/dashboard',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
