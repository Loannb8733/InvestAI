import { test, expect } from "@playwright/test";

test.describe("Authentication Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
  });

  test("should display login page", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /connexion|login/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/mot de passe|password/i)).toBeVisible();
  });

  test("should show error on invalid credentials", async ({ page }) => {
    await page.getByLabel(/email/i).fill("invalid@test.com");
    await page.getByLabel(/mot de passe|password/i).fill("wrongpassword");
    await page.getByRole("button", { name: /connexion|se connecter|login/i }).click();

    await expect(page.getByText(/erreur|invalid|incorrect/i)).toBeVisible({ timeout: 10000 });
  });

  test("should show validation errors for empty form", async ({ page }) => {
    await page.getByRole("button", { name: /connexion|se connecter|login/i }).click();

    await expect(page.getByText(/email invalide|requis/i)).toBeVisible();
  });

  test("should navigate to register page", async ({ page }) => {
    await page.getByRole("link", { name: /créer un compte|inscription|register/i }).click();
    await expect(page).toHaveURL(/register/);
  });

  test("should navigate to forgot password page", async ({ page }) => {
    await page.getByRole("link", { name: /mot de passe oublié|forgot/i }).click();
    await expect(page).toHaveURL(/forgot-password/);
  });

  test("should redirect unauthenticated users to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/login/);
  });
});

test.describe("Registration Flow", () => {
  test("should display registration form", async ({ page }) => {
    await page.goto("/register");
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/prénom|first name/i)).toBeVisible();
  });

  test("should validate email format", async ({ page }) => {
    await page.goto("/register");
    await page.getByLabel(/email/i).fill("not-an-email");
    await page.getByRole("button", { name: /créer|inscription|register/i }).click();

    await expect(page.getByText(/email invalide/i)).toBeVisible();
  });
});
