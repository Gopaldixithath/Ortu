// Shared Playwright test fixture: blocks the external ChatnCall webchat loader
// (flaky third-party script) and exposes the seed credentials the specs use.
// Keep CREDS in sync with backend/scripts/e2e_server.py.
const base = require('@playwright/test')

const CREDS = {
  email: 'e2e@example.com',
  password: 'e2ePassword123',
  membershipToken: 'e2e-membership-token-0000000000',
  adminKey: 'e2e-admin-key',
}

const test = base.test.extend({
  page: async ({ page }, use) => {
    await page.route(/chatncall\.ai/, (route) => route.abort())
    await use(page)
  },
})

module.exports = { test, expect: base.expect, CREDS }
