const { test, expect } = require('../fixtures')

async function fillStepOne(dialog, email) {
  await dialog.locator('input[name="first_name"]').fill('Sam')
  await dialog.locator('input[name="last_name"]').fill('Signup')
  await dialog.locator('input[name="date_of_birth"]').fill('1992-03-04')
  await dialog.locator('input[name="email"]').fill(email)
  await dialog.locator('input[name="kin_first_name"]').fill('Kin')
  await dialog.locator('input[name="kin_last_name"]').fill('Person')
  await dialog.locator('input[name="kin_mobile"]').fill('07700900000')
  await dialog.locator('input[name="kin_email"]').fill('kin@example.com')
  await dialog.locator('input[name="no_health_issues"]').check()
  await dialog.getByRole('button', { name: 'Next' }).click()
}

test('member record request — happy path', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Become a member' }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Become a member' })).toBeVisible()

  await fillStepOne(dialog, `signup+${Date.now()}@example.com`)
  await dialog.locator('input[name="password"]').fill('password123')
  await dialog.locator('input[name="confirm_password"]').fill('password123')
  await dialog.locator('input[name="agree_terms"]').check()
  await dialog.locator('input[name="dp_legal"]').check()
  await dialog.locator('input[name="dp_services"]').check()
  await dialog.getByRole('button', { name: 'Submit request' }).click()

  await expect(dialog.getByRole('heading', { name: 'Request sent' })).toBeVisible()
})

test('mismatched passwords are rejected client-side', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Become a member' }).first().click()
  const dialog = page.getByRole('dialog')

  await fillStepOne(dialog, `mismatch+${Date.now()}@example.com`)
  await dialog.locator('input[name="password"]').fill('password123')
  await dialog.locator('input[name="confirm_password"]').fill('different1')
  await dialog.locator('input[name="agree_terms"]').check()
  await dialog.locator('input[name="dp_legal"]').check()
  await dialog.locator('input[name="dp_services"]').check()
  await dialog.getByRole('button', { name: 'Submit request' }).click()

  await expect(dialog.getByText('The two passwords do not match.')).toBeVisible()
})
