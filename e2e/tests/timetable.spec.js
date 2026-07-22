const { test, expect } = require('../fixtures')

test.describe('Timetable', () => {
  test('shows the hero and upcoming classes with live availability', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Move better')
    await expect(page.getByRole('heading', { name: 'Sunday Reset' })).toBeVisible()
    await expect(page.getByText(/spaces left/).first()).toBeVisible()
  })

  test('booking while logged out steers you to memberships', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Book Small-Group Barbell' }).click()
    // No membership token -> a status notice appears instead of the booking modal.
    await expect(page.locator('[role="status"]')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Confirm your class' })).toHaveCount(0)
  })
})
