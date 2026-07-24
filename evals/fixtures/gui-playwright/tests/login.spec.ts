import { expect, test } from "@playwright/test";

test("fixture login renders a local protected area", async ({ page }) => {
  await page.setContent('<main><h1>Fixture login</h1><button>Continue</button></main>');
  await expect(page.getByRole("heading", { name: "Fixture login" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue" })).toBeEnabled();
});
