import { expect, test } from '@playwright/test';

test('fixture demo pages have no console errors and review note persists', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await page.goto('/documents');
  await expect(page.getByRole('heading', { name: 'Documents' })).toBeVisible();
  await page.goto('/review/fail_balancing.pdf');
  await expect(page.getByRole('heading', { name: 'fail_balancing.pdf' })).toBeVisible();
  await page.getByRole('button', { name: /credit_amounts_equal_subtotal_credits/ }).click();
  await expect(page.getByText('Credit line items equal subtotal credits')).toBeVisible();
  await page.getByLabel('Review notes').fill('playwright persisted note');
  await page.getByRole('button', { name: 'Save Review' }).click();
  await expect(page.getByText('Saved')).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /credit_amounts_equal_subtotal_credits/ }).click();
  await expect(page.getByLabel('Review notes')).toHaveValue('playwright persisted note');
  await page.goto('/analytics');
  await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible();
  await page.goto('/runs');
  await expect(page.getByRole('heading', { name: 'Runs / Logs' })).toBeVisible();

  expect(errors).toEqual([]);
});
