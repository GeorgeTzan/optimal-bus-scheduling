import { signIn, test, expect } from "./helpers/auth";

test("studio renders both locales, themes, grouping and narrow screens", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const timeline = page.getByTestId("schedule-timeline");
  expect(await timeline.locator(".resource-row").count()).toBeLessThan(25); // bounded viewport rendering
  await expect(page.locator(".timeline-trip").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/studio-desktop-light.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  await page.screenshot({
    path: "test-results/studio-inspector-light.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("main")
    .getByRole("button", { name: "Drivers", exact: true })
    .click();
  await expect(page.locator(".resource-axis")).toContainText("DRIVER / BUS");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveClass("dark");
  await page.screenshot({
    path: "test-results/studio-desktop-dark.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Αλλαγή πόρου", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/studio-greek-dark.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.screenshot({
    path: "test-results/studio-tablet-dark.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "Κλείσιμο", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/studio-mobile-dark.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
});
