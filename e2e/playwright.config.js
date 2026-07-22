const { defineConfig, devices } = require('@playwright/test')
const path = require('path')

// Point the E2E backend at the freshly-built SPA and a throwaway DB.
const STATIC_DIR = path.resolve(__dirname, '../frontend/dist')

module.exports = defineConfig({
  testDir: './tests',
  // One shared, seeded database is served for the whole run, so tests must not
  // race each other: run serially and do not retry against mutated state.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      testIgnore: /mobile\.spec\.js/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } },
    },
    {
      // Pixel 5 = Android/Chromium (matches the reported device, no extra browser).
      name: 'mobile',
      testMatch: /mobile\.spec\.js/,
      use: { ...devices['Pixel 5'] },
    },
  ],
  webServer: {
    command: `${process.env.E2E_PYTHON || 'python'} ../backend/scripts/e2e_server.py`,
    url: 'http://127.0.0.1:8000/healthz',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { ORTU_STATIC_DIR: STATIC_DIR },
  },
})
