import { test, expect, Page } from "@playwright/test";

/**
 * Helper to login and get an authenticated session.
 * Uses test user credentials from environment or defaults.
 */
async function loginAsTestUser(page: Page) {
  const email = process.env.E2E_TEST_EMAIL || "test@investai.local";
  const password = process.env.E2E_TEST_PASSWORD || "TestPassword123!";

  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/mot de passe|password/i).fill(password);
  await page.getByRole("button", { name: /connexion|se connecter|login/i }).click();

  // Wait for redirect to dashboard
  await page.waitForURL("/", { timeout: 15000 });
}

test.describe("Authenticated Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsTestUser(page);
  });

  test("should display dashboard after login", async ({ page }) => {
    await expect(page.getByText(/tableau de bord|dashboard|patrimoine/i)).toBeVisible();
  });

  test("should navigate to portfolio page", async ({ page }) => {
    await page.getByRole("link", { name: /portefeuille|portfolio/i }).first().click();
    await expect(page).toHaveURL(/portfolio/);
  });

  test("should navigate to transactions page", async ({ page }) => {
    await page.getByRole("link", { name: /transactions/i }).first().click();
    await expect(page).toHaveURL(/transactions/);
  });

  test("should navigate to analytics page", async ({ page }) => {
    await page.getByRole("link", { name: /analytics|analyse/i }).first().click();
    await expect(page).toHaveURL(/analytics/);
  });

  test("should navigate to predictions page", async ({ page }) => {
    await page.getByRole("link", { name: /prédictions|predictions/i }).first().click();
    await expect(page).toHaveURL(/predictions/);
  });

  test("should navigate to alerts page", async ({ page }) => {
    await page.getByRole("link", { name: /alertes|alerts/i }).first().click();
    await expect(page).toHaveURL(/alerts/);
  });

  test("should navigate to settings page", async ({ page }) => {
    await page.getByRole("link", { name: /paramètres|settings/i }).first().click();
    await expect(page).toHaveURL(/settings/);
  });

  test("should handle 404 pages", async ({ page }) => {
    await page.goto("/this-page-does-not-exist");
    await expect(page.getByText(/404|page introuvable|not found/i)).toBeVisible();
  });
});
