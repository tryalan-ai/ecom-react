import { test, expect } from '@playwright/test';
import { TestHelpers } from './fixtures/test-helpers.js';

test.describe('Product Catalog', () => {
  let helpers;

  test.beforeEach(async ({ page }) => {
    helpers = new TestHelpers(page);
    await helpers.clearStorage();
    await helpers.goToHome();
  });

  test('should load and display products', async ({ page }) => {
    // Wait for products to load
    await helpers.waitForProducts();

    // Check that products are displayed
    const productCount = await helpers.getProductCardsCount();
    expect(productCount).toBeGreaterThan(0);

    // Verify product card elements
    const firstProduct = page.locator('.card').first();
    await expect(firstProduct.locator('img')).toBeVisible();
    await expect(firstProduct.locator('text=/\\$/').first()).toBeVisible(); // Price
  });

  test('should display product count', async ({ page }) => {
    await helpers.waitForProducts();

    // Check for results count text
    const resultsText = page.locator('text=/Showing \\d+ of \\d+ products/');
    await expect(resultsText).toBeVisible();
  });

  test('should display product details correctly', async ({ page }) => {
    await helpers.waitForProducts();

    const firstProduct = page.locator('[class*="card"]').first();

    // Check for required product elements
    await expect(firstProduct.locator('img')).toBeVisible(); // Image
    await expect(firstProduct.locator('text=/[A-Za-z]/').first()).toBeVisible(); // Brand/Name
    await expect(firstProduct.locator('text=/\\$/').first()).toBeVisible(); // Price
    await expect(firstProduct.locator('button:has-text("Add to Cart")')).toBeVisible(); // Add to cart button
  });

  test('should show ratings on product cards', async ({ page }) => {
    await helpers.waitForProducts();

    const firstProduct = page.locator('[class*="card"]').first();

    // Check for rating (number between 0-5)
    const rating = firstProduct.locator('text=/\\d\\.\\d/').first();
    await expect(rating).toBeVisible();
  });

  test('should show sale badge on discounted products', async ({ page }) => {
    await helpers.waitForProducts();

    // Look for products with sale badges
    const saleBadge = page.locator('text=/-\\d+%/').first();

    // If there are sale products, verify badge is visible
    const count = await page.locator('text=/-\\d+%/').count();
    if (count > 0) {
      await expect(saleBadge).toBeVisible();
    }
  });

  test('should handle out of stock products', async ({ page }) => {
    await helpers.waitForProducts();

    // Look for out of stock products
    const outOfStockButton = page.locator('button:has-text("Out of Stock")').first();
    const count = await page.locator('button:has-text("Out of Stock")').count();

    if (count > 0) {
      await expect(outOfStockButton).toBeDisabled();
    }
  });

  test('should display header with logo', async ({ page }) => {
    const logo = page.locator('header').locator('text=E-Shop');
    await expect(logo).toBeVisible();
  });

  test('should display cart icon in header', async ({ page }) => {
    const cartButton = page.getByRole('button', { name: 'Open cart' });
    await expect(cartButton).toBeVisible();
  });

  test('should show empty cart badge initially', async ({ page }) => {
    const cartCount = await helpers.getCartCount();
    expect(cartCount).toBe(0);
  });

  test('should display footer', async ({ page }) => {
    const footer = page.locator('footer');
    await expect(footer).toBeVisible();
    await expect(footer.locator('text=/© \\d{4}/')).toBeVisible();
  });
});
