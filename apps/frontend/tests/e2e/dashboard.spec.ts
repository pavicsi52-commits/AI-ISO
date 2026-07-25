import { expect, test } from "@playwright/test";

test("dashboard loads and shows the AI-IOS header", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("banner").getByText("AI-IOS")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
});

test("dashboard fetches live health data from the gateway", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Checking gateway status")).toBeVisible();
  await expect(page.getByText("healthy")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("gateway", { exact: true })).toBeVisible();
});

test("theme toggle switches between light and dark", async ({ page }) => {
  await page.goto("/");

  const html = page.locator("html");
  const toggle = page.getByRole("button", { name: "Toggle theme" });

  const initiallyDark = await html.evaluate((el) => el.classList.contains("dark"));
  await toggle.click();
  await expect(html).toHaveClass(initiallyDark ? /^(?!.*dark).*$/ : /dark/);
});
