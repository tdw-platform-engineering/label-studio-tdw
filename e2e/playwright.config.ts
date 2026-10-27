import { defineConfig } from '@playwright/test';

// Target a DEPLOYED instance. Override with LS_URL env.
const baseURL = process.env.LS_URL || 'https://labelstudio.dev-spectrum.tdwanalytics.co';

export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  retries: 1,
  reporter: [['list']],
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
