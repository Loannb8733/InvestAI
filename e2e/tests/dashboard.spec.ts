import { test, expect, Page } from "@playwright/test";

async function loginAsTestUser(page: Page) {
  const email = process.env.E2E_TEST_EMAIL || "test@investai.local";
  const password = process.env.E2E_TEST_PASSWORD || "TestPassword123!";

  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/mot de passe|password/i).fill(password);
  await page.getByRole("button", { name: /connexion|se connecter|login/i }).click();
  await page.waitForURL("/", { timeout: 15000 });
}

test.describe("Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsTestUser(page);
  });

  test("should display portfolio summary widgets", async ({ page }) => {
    // Dashboard should have key financial widgets
    await expect(page.getByText(/valeur totale|total value|patrimoine/i)).toBeVisible({ timeout: 10000 });
  });

  test("should display allocation chart", async ({ page }) => {
    // Look for allocation/répartition section
    await expect(page.getByText(/répartition|allocation/i)).toBeVisible({ timeout: 10000 });
  });

  test("should display performance chart", async ({ page }) => {
    await expect(page.getByText(/performance|évolution/i)).toBeVisible({ timeout: 10000 });
  });

  test("should handle empty portfolio gracefully", async ({ page }) => {
    // Should not crash, should show empty state or onboarding
    await expect(page.locator("body")).not.toContainText("Error");
  });
});

test.describe("Dashboard Interactions", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsTestUser(page);
  });

  test("should allow changing time period", async ({ page }) => {
    // Look for period selectors (7j, 30j, 90j, 1an)
    const periodButton = page.getByRole("button", { name: /30j|30d|1m/i });
    if (await periodButton.isVisible()) {
      await periodButton.click();
      // Should not crash
      await expect(page.locator("body")).not.toContainText("Error");
    }
  });
});
