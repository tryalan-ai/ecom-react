import { expect } from '@playwright/test';

/**
 * Test utilities for e-commerce tests
 */

export class TestHelpers {
  constructor(page) {
    this.page = page;
  }

  /**
   * Navigate to home page
   */
  async goToHome() {
    await this.page.goto('/', { waitUntil: 'load', timeout: 30000 });
    await this.page.waitForTimeout(1000); // Give page time to render
  }

  /**
   * Clear localStorage (cart and checkout data)
   */
  async clearStorage() {
    try {
      await this.page.evaluate(() => {
        localStorage.clear();
      });
    } catch (error) {
      // Ignore localStorage errors if page hasn't loaded yet
      // Will be cleared when page navigates
    }
  }

  /**
   * Wait for products to load
   */
  async waitForProducts() {
    // Wait for products to load - give plenty of time for API call and rendering
    await this.page.waitForTimeout(5000);
  }

  /**
   * Get product cards count
   */
  async getProductCardsCount() {
    try {
      return await this.page.locator('.card').count();
    } catch (error) {
      return 0;
    }
  }

  /**
   * Add first available product to cart
   */
  async addFirstProductToCart() {
    const addToCartButton = this.page.locator('button:has-text("Add to Cart")').first();
    await addToCartButton.click();
    await this.page.waitForTimeout(500); // Wait for toast notification
  }

  /**
   * Open cart drawer
   */
  async openCart() {
    await this.page.getByRole('button', { name: 'Open cart' }).click();
    await this.page.waitForSelector('text=Shopping Cart', { timeout: 5000 });
  }

  /**
   * Get cart item count from badge
   */
  async getCartCount() {
    const badge = this.page.getByTestId('cart-badge');
    try {
      const count = await badge.textContent({ timeout: 1000 });
      return parseInt(count || '0');
    } catch {
      // Badge not visible means count is 0
      return 0;
    }
  }

  /**
   * Fill shipping form
   */
  async fillShippingForm(data = {}) {
    const defaultData = {
      name: 'John Doe',
      email: 'john.doe@example.com',
      phone: '1234567890',
      address: '123 Main St',
      apartment: 'Apt 4B',
      city: 'New York',
      state: 'NY',
      zipCode: '10001',
      country: 'United States'
    };

    const formData = { ...defaultData, ...data };

    await this.page.fill('input[name="name"]', formData.name);
    await this.page.fill('input[name="email"]', formData.email);
    await this.page.fill('input[name="phone"]', formData.phone);
    await this.page.fill('input[name="address"]', formData.address);
    await this.page.fill('input[name="apartment"]', formData.apartment);
    await this.page.fill('input[name="city"]', formData.city);
    await this.page.selectOption('select[name="state"]', formData.state);
    await this.page.fill('input[name="zipCode"]', formData.zipCode);
    await this.page.selectOption('select[name="country"]', formData.country);
  }

  /**
   * Fill payment form
   */
  async fillPaymentForm(data = {}) {
    const defaultData = {
      cardNumber: '4532 1234 5678 9010',
      cardholderName: 'John Doe',
      expirationDate: '12/25',
      cvv: '123'
    };

    const formData = { ...defaultData, ...data };

    await this.page.fill('input[name="cardNumber"]', formData.cardNumber);
    await this.page.fill('input[name="cardholderName"]', formData.cardholderName);
    await this.page.fill('input[name="expirationDate"]', formData.expirationDate);
    await this.page.fill('input[name="cvv"]', formData.cvv);
  }

  /**
   * Apply filter by category
   */
  async applyCategory(category) {
    const checkbox = this.page.locator(`input[id*="category"]`).locator(`.. >> text="${category}"`);
    await checkbox.click();
    await this.page.waitForTimeout(500); // Wait for filter to apply
  }

  /**
   * Apply price range filter
   */
  async applyPriceRange(min, max) {
    await this.page.fill('input[placeholder="Min"]', min.toString());
    await this.page.fill('input[placeholder="Max"]', max.toString());
    await this.page.click('button:has-text("Apply")');
    await this.page.waitForTimeout(500);
  }

  /**
   * Apply brand filter
   */
  async applyBrand(brand) {
    const checkbox = this.page.locator(`input[id*="brand"]`).locator(`.. >> text="${brand}"`);
    await checkbox.click();
    await this.page.waitForTimeout(500);
  }

  /**
   * Search for products
   */
  async searchProducts(searchTerm) {
    await this.page.fill('input[placeholder*="Search"]', searchTerm);
    await this.page.press('input[placeholder*="Search"]', 'Enter');
    await this.page.waitForTimeout(500);
  }

  /**
   * Change sort order
   */
  async changeSortOrder(sortBy) {
    await this.page.selectOption('select', sortBy);
    await this.page.waitForTimeout(500);
  }

  /**
   * Take screenshot with name
   */
  async screenshot(name) {
    await this.page.screenshot({ path: `test-results/${name}.png`, fullPage: true });
  }

  /**
   * Wait for navigation with loading state
   */
  async waitForNavigation() {
    await this.page.waitForLoadState('networkidle');
  }
}

/**
 * Data fixtures for testing
 */
export const testData = {
  validShippingInfo: {
    name: 'Test User',
    email: 'test@example.com',
    phone: '5551234567',
    address: '456 Test Ave',
    apartment: 'Unit 10',
    city: 'Los Angeles',
    state: 'CA',
    zipCode: '90001',
    country: 'United States'
  },

  invalidShippingInfo: {
    name: '',
    email: 'invalid-email',
    phone: '123',
    address: '',
    city: '',
    state: '',
    zipCode: 'abc',
    country: 'United States'
  },

  validPaymentInfo: {
    cardNumber: '4532 1234 5678 9010',
    cardholderName: 'Test User',
    expirationDate: '12/25',
    cvv: '123'
  },

  invalidPaymentInfo: {
    cardNumber: '1111 1111 1111 1111',
    cardholderName: '',
    expirationDate: '13/20',
    cvv: '12'
  },

  promoCodes: {
    valid10: 'SAVE10',
    valid20: 'SAVE20',
    invalid: 'INVALID123'
  }
};
