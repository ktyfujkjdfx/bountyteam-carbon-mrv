import { defineConfig } from '@playwright/test';

const port = Number(process.env.E2E_PORT ?? 4173);
const channel = process.env.E2E_BROWSER_CHANNEL ?? 'msedge';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? `http://127.0.0.1:${port}`,
    channel,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  ...(process.env.E2E_BASE_URL
    ? {}
    : {
        webServer: {
          command: `npx vite preview --host 127.0.0.1 --port ${port} --strictPort`,
          url: `http://127.0.0.1:${port}`,
          reuseExistingServer: false,
          timeout: 60_000,
        },
      }),
});
