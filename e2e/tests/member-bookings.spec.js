const { test, expect, CREDS } = require('../fixtures')

test('password login shows the dashboard and cancels a booking', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'My bookings' }).first().click()

  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'My ORTU bookings' })).toBeVisible()
  await dialog.locator('input[type="email"]').fill(CREDS.email)
  await dialog.locator('input[type="password"]').fill(CREDS.password)
  await dialog.getByRole('button', { name: 'Log in' }).click()

  await expect(dialog.getByText('Welcome back')).toBeVisible()
  await expect(dialog.getByText('Unlimited classes')).toBeVisible()

  // Cancelling triggers a native confirm() dialog — accept it.
  page.on('dialog', (d) => d.accept())
  const row = dialog.locator('.memberBooking', { hasText: 'Sunday Reset' })
  await row.getByRole('button', { name: 'Cancel booking' }).click()

  await expect(dialog.locator('.memberBooking', { hasText: 'Sunday Reset' })).toHaveCount(0)
})
