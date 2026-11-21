import { expect, test } from '@playwright/test'

async function signIn(page: any, username = 'employee01', password = 'demo123') {
  await page.goto('/')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in securely' }).click()
}

test('employee gets a cited knowledge answer', async ({ page }) => {
  await signIn(page)
  await page.getByLabel('Support request').fill('How do I report phishing?')
  await page.getByLabel('Send request').click()
  await expect(page.getByText(/Based on the approved SOP/)).toBeVisible()
  await expect(page.getByText(/approved source/)).toBeVisible()
})

test('password reset requires confirmation and resolves', async ({ page }) => {
  await signIn(page)
  await page.getByLabel('Support request').fill('Reset my password')
  await page.getByLabel('Send request').click()
  await expect(page.getByText('Confirmation required')).toBeVisible()
  await page.getByRole('button', { name: 'Confirm action' }).click()
  await expect(page.getByText('Resolved', { exact: true }).last()).toBeVisible()
})

test('unsupported issue escalates and appears in operations', async ({ page }) => {
  await signIn(page)
  await page.getByLabel('Support request').fill('My quantum toaster is smoking')
  await page.getByLabel('Send request').click()
  await expect(page.getByText(/Ticket TKT-/)).toBeVisible()
  await page.getByRole('button', { name: /Demo Employee/ }).click()
  await signIn(page, 'support', 'support123')
  await expect(page.getByText('Service desk performance')).toBeVisible()
  await expect(page.getByText('Latest escalations')).toBeVisible()
})
