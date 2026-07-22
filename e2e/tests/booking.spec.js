const { test, expect, CREDS } = require('../fixtures')

test('a logged-in member books a class from the timetable', async ({ page, context }) => {
  // Seed the membership token so the app treats us as signed in.
  await context.addInitScript((token) => {
    localStorage.setItem('ortu_membership_token', token)
  }, CREDS.membershipToken)

  await page.goto('/')
  await page.getByRole('button', { name: 'Book Small-Group Barbell' }).click()

  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'Confirm your class' })).toBeVisible()
  await dialog.getByRole('button', { name: 'Confirm booking' }).click()

  await expect(page.locator('[role="status"]')).toContainText('booked')
})
