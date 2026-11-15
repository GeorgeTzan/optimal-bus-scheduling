import { test, expect, signIn } from "./helpers/auth";

test.use({ viewport: { width: 390, height: 844 } });

test("on a phone the menu opens from the header, moves focus into it, closes with Escape and returns focus", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav).not.toBeInViewport();
  const opener = page.getByRole("button", { name: "Open menu" });
  await opener.click();
  await expect(nav).toBeInViewport();
  await expect(nav.getByRole("button").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(nav).not.toBeInViewport();
  await expect(opener).toBeFocused();
  await opener.click();
  await nav.getByRole("button", { name: "Team", exact: true }).click();
  await expect(nav).not.toBeInViewport();
  await expect(page.getByRole("heading", { name: "Team and access" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.locator(".team-table td[data-label='Email']").first()).toBeInViewport();
});
