const { test, expect, CREDS } = require('../fixtures')

test('studio login opens the dashboard, lists members and approves a request', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Studio login' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Studio login' })).toBeVisible()
  await dialog.locator('input[type="password"]').fill(CREDS.adminKey)
  await dialog.getByRole('button', { name: 'Open studio dashboard' }).click()

  await expect(dialog.getByRole('heading', { name: 'Studio dashboard' })).toBeVisible()
  await dialog.getByRole('button', { name: 'Members' }).click()
  await expect(dialog.getByText(CREDS.email)).toBeVisible()

  // Approve the seeded pending request if it is still pending.
  const approve = dialog.getByRole('button', { name: 'Approve' })
  if (await approve.count()) {
    await approve.first().click()
    await expect(dialog.locator('.formSuccess')).toBeVisible()
  }
})
