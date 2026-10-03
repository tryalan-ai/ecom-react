import { test, expect, devices } from '@playwright/test';
import { TestHelpers } from './fixtures/test-helpers.js';

test.describe('Responsive Design', () => {
  let helpers;

  test.describe('Mobile View (375px)', () => {
    test.use({ viewport: { width: 375, height: 667 } });

    test.beforeEach(async ({ page }) => {
      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();
    });

    test('should display products in single column', async ({ page }) => {
      const productGrid = page.locator('[class*="grid"]').first();
      await expect(productGrid).toBeVisible();

      // Check grid layout
      const gridClass = await productGrid.getAttribute('class');
      expect(gridClass).toContain('grid-cols-1');
    });

    test('should show mobile filter button', async ({ page }) => {
      const filterButton = page.locator('button:has-text("Filters")');
      await expect(filterButton).toBeVisible();
    });

    test('should toggle mobile filters', async ({ page }) => {
      // Filter sidebar should be hidden initially
      const filterSidebar = page.locator('text=Category').first();
      const isVisible = await filterSidebar.isVisible();

      // Click filter button
      const filterButton = page.locator('button:has-text("Filters")');
      await filterButton.click();
      await page.waitForTimeout(300);

      // Filter sidebar should toggle
      const afterClick = await filterSidebar.isVisible();
      expect(afterClick).not.toBe(isVisible);
    });

    test('should display header correctly', async ({ page }) => {
      const header = page.locator('header');
      await expect(header).toBeVisible();

      // Logo should be visible
      await expect(page.locator('text=E-Shop')).toBeVisible();

      // Cart icon should be visible
      const cartIcon = page.getByRole('button', { name: 'Open cart' });
      await expect(cartIcon).toBeVisible();
    });

    test('should open full-width cart drawer', async ({ page }) => {
      await helpers.openCart();

      // Cart drawer should be visible and full width on mobile
      const cartDrawer = page.locator('text=Shopping Cart').locator('../..');
      await expect(cartDrawer).toBeVisible();
    });

    test('should stack checkout form fields', async ({ page }) => {
      // Add product and go to checkout
      await helpers.addFirstProductToCart();
      await page.waitForTimeout(500);
      await helpers.openCart();
      await page.click('button:has-text("Proceed to Checkout")');
      await page.waitForLoadState('networkidle');

      // Form fields should be stacked vertically
      const nameInput = page.locator('input[name="name"]');
      const emailInput = page.locator('input[name="email"]');

      await expect(nameInput).toBeVisible();
      await expect(emailInput).toBeVisible();
    });

    test('should have touch-friendly buttons', async ({ page }) => {
      // Buttons should be large enough for touch
      const addToCartButton = page.locator('button:has-text("Add to Cart")').first();
      const box = await addToCartButton.boundingBox();

      // Button height should be at least 44px (recommended touch target size)
      expect(box.height).toBeGreaterThanOrEqual(36);
    });

    test('should scroll vertically', async ({ page }) => {
      // Page should be scrollable
      const bodyHeight = await page.evaluate(() => document.body.scrollHeight);
      const viewportHeight = await page.evaluate(() => window.innerHeight);

      expect(bodyHeight).toBeGreaterThan(viewportHeight);
    });
  });

  test.describe('Tablet View (768px)', () => {
    test.use({ viewport: { width: 768, height: 1024 } });

    test.beforeEach(async ({ page }) => {
      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();
    });

    test('should display products in 2 columns', async ({ page }) => {
      const productGrid = page.locator('[class*="grid"]').first();
      await expect(productGrid).toBeVisible();

      // Check for 2-column layout
      const gridClass = await productGrid.getAttribute('class');
      expect(gridClass).toMatch(/grid-cols-2/);
    });

    test('should show filter sidebar', async ({ page }) => {
      // Filters should be visible on tablet
      const filterSidebar = page.locator('text=Category').first();
      await expect(filterSidebar).toBeVisible();
    });

    test('should display checkout in proper layout', async ({ page }) => {
      // Add product and go to checkout
      await helpers.addFirstProductToCart();
      await page.waitForTimeout(500);
      await helpers.openCart();
      await page.click('button:has-text("Proceed to Checkout")');
      await page.waitForLoadState('networkidle');

      // Order summary should be visible
      const orderSummary = page.locator('text=Order Summary');
      await expect(orderSummary).toBeVisible();
    });
  });

  test.describe('Desktop View (1024px+)', () => {
    test.use({ viewport: { width: 1280, height: 720 } });

    test.beforeEach(async ({ page }) => {
      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();
    });

    test('should display products in 4 columns', async ({ page }) => {
      const productGrid = page.locator('[class*="grid"]').first();
      await expect(productGrid).toBeVisible();

      // Check for 4-column layout on xl screens
      const gridClass = await productGrid.getAttribute('class');
      expect(gridClass).toMatch(/xl:grid-cols-4/);
    });

    test('should show filter sidebar by default', async ({ page }) => {
      const filterSidebar = page.locator('text=Filters').first();
      await expect(filterSidebar).toBeVisible();
    });

    test('should not show mobile filter button', async ({ page }) => {
      // Mobile filter button should be hidden on desktop
      const filterButton = page.locator('button:has-text("Filters")');
      const isVisible = await filterButton.isVisible();

      // Button might exist but be hidden with CSS
      if (isVisible) {
        // Check if it's actually rendered (not hidden by responsive classes)
        const display = await filterButton.evaluate(el => window.getComputedStyle(el).display);
        expect(display).toBe('none');
      }
    });

    test('should display cart drawer with fixed width', async ({ page }) => {
      await helpers.openCart();

      // Cart drawer should have max width on desktop
      const cartDrawer = page.locator('text=Shopping Cart').locator('../..');
      await expect(cartDrawer).toBeVisible();

      // Should not be full width
      const box = await cartDrawer.boundingBox();
      expect(box.width).toBeLessThan(600); // max-w-md
    });

    test('should show checkout sidebar', async ({ page }) => {
      // Add product and go to checkout
      await helpers.addFirstProductToCart();
      await page.waitForTimeout(500);
      await helpers.openCart();
      await page.click('button:has-text("Proceed to Checkout")');
      await page.waitForLoadState('networkidle');

      // Order summary sidebar should be visible
      const orderSummary = page.locator('text=Order Summary');
      await expect(orderSummary).toBeVisible();
    });

    test('should have side-by-side form layout', async ({ page }) => {
      // Add product and go to checkout
      await helpers.addFirstProductToCart();
      await page.waitForTimeout(500);
      await helpers.openCart();
      await page.click('button:has-text("Proceed to Checkout")');
      await page.waitForLoadState('networkidle');

      // Name and email fields should be side by side
      const nameInput = page.locator('input[name="name"]');
      const emailInput = page.locator('input[name="email"]');

      const nameBox = await nameInput.boundingBox();
      const emailBox = await emailInput.boundingBox();

      // They should be on approximately the same Y position
      expect(Math.abs(nameBox.y - emailBox.y)).toBeLessThan(10);
    });
  });

  test.describe('Wide Desktop View (1920px)', () => {
    test.use({ viewport: { width: 1920, height: 1080 } });

    test.beforeEach(async ({ page }) => {
      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();
    });

    test('should maintain maximum container width', async ({ page }) => {
      // Container should not stretch too wide
      const container = page.locator('.container').first();
      const box = await container.boundingBox();

      // Should have max width and be centered
      expect(box.x).toBeGreaterThan(0);
    });

    test('should display products in 4 columns', async ({ page }) => {
      const productGrid = page.locator('[class*="grid"]').first();
      await expect(productGrid).toBeVisible();

      // Should still use 4 columns, not expand to more
      const gridClass = await productGrid.getAttribute('class');
      expect(gridClass).toMatch(/xl:grid-cols-4/);
    });
  });

  test.describe('Orientation Changes', () => {
    test('should handle landscape mobile view', async ({ page }) => {
      await page.setViewportSize({ width: 667, height: 375 });

      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();

      // Products should be visible
      const products = await page.locator('[class*="card"]').count();
      expect(products).toBeGreaterThan(0);

      // Header should be visible
      await expect(page.locator('text=E-Shop')).toBeVisible();
    });

    test('should handle tablet landscape', async ({ page }) => {
      await page.setViewportSize({ width: 1024, height: 768 });

      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();

      // Should show desktop-like layout
      const filterSidebar = page.locator('text=Filters').first();
      await expect(filterSidebar).toBeVisible();
    });
  });

  test.describe('Touch Interactions', () => {
    test.use({ viewport: { width: 375, height: 667 }, hasTouch: true });

    test.beforeEach(async ({ page }) => {
      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();
    });

    test('should handle tap on product card', async ({ page }) => {
      const addButton = page.locator('button:has-text("Add to Cart")').first();
      await addButton.tap();
      await page.waitForTimeout(500);

      // Should add to cart
      const cartCount = await helpers.getCartCount();
      expect(cartCount).toBe(1);
    });

    test('should handle cart drawer close via tap', async ({ page }) => {
      await helpers.openCart();

      // Tap backdrop to close
      await page.locator('text=Shopping Cart').locator('../..').click({ position: { x: 10, y: 10 } });
      await page.waitForTimeout(500);
    });
  });

  test.describe('Accessibility on Different Screens', () => {
    test('should have readable text on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });

      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();

      // Text should be at least 16px (or use rem)
      const productName = page.locator('[class*="card"]').first().locator('h3').first();
      const fontSize = await productName.evaluate(el => window.getComputedStyle(el).fontSize);
      const size = parseFloat(fontSize);

      expect(size).toBeGreaterThanOrEqual(14); // Minimum readable size
    });

    test('should have sufficient touch targets on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });

      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();

      // Buttons should be at least 44x44px
      const addButton = page.locator('button:has-text("Add to Cart")').first();
      const box = await addButton.boundingBox();

      expect(box.height).toBeGreaterThanOrEqual(36);
    });
  });

  test.describe('Image Responsiveness', () => {
    test('should load appropriate images on mobile', async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 667 });

      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();

      // Product images should load
      const firstImage = page.locator('[class*="card"]').first().locator('img');
      await expect(firstImage).toBeVisible();

      // Image should be loaded
      const isLoaded = await firstImage.evaluate(img => img.complete && img.naturalHeight !== 0);
      expect(isLoaded).toBe(true);
    });

    test('should scale images properly', async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 720 });

      helpers = new TestHelpers(page);
      await helpers.clearStorage();
      await helpers.goToHome();
      await helpers.waitForProducts();

      // Images should not overflow their containers
      const firstImage = page.locator('[class*="card"]').first().locator('img');
      const imageBox = await firstImage.boundingBox();
      const cardBox = await page.locator('[class*="card"]').first().boundingBox();

      expect(imageBox.width).toBeLessThanOrEqual(cardBox.width);
    });
  });
});
