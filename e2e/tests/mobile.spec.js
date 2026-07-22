const { test, expect } = require('../fixtures')

// Guards the regression we fixed: on a phone the page must not scroll sideways,
// and the (fixed, right-anchored) webchat widget must stay on screen.
test('the page does not scroll horizontally on a phone', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  const { scrollW, innerW } = await page.evaluate(() => {
    const el = document.scrollingElement || document.documentElement
    return { scrollW: el.scrollWidth, innerW: window.innerWidth }
  })
  expect(scrollW).toBeLessThanOrEqual(innerW + 1)
})

test('the webchat widget stays within the viewport on mobile', async ({ page }) => {
  await page.goto('/')
  // The real loader is blocked in tests; inject a stub carrying the loader's own
  // inline styles so we exercise our @media(max-width:480px) overrides.
  await page.evaluate(() => {
    const panel = document.createElement('div')
    panel.id = 'chatncall-webchat-panel'
    Object.assign(panel.style, {
      position: 'fixed', right: '24px', bottom: '86px', width: '380px',
      maxWidth: 'calc(100vw - 32px)', height: '480px', display: 'block', zIndex: '99999',
    })
    document.body.appendChild(panel)
  })

  const box = await page.locator('#chatncall-webchat-panel').boundingBox()
  const innerW = await page.evaluate(() => window.innerWidth)
  expect(box.x).toBeGreaterThanOrEqual(0)
  expect(box.x + box.width).toBeLessThanOrEqual(innerW + 1)
})
