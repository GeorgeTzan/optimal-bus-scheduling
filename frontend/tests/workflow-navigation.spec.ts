import { test, expect, signIn } from "./helpers/auth";

test("a dispatcher keeps the Drivers page and search through reload and browser history", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Drivers", exact: true })
    .click();
  await page.getByPlaceholder("Search by name or reference…").fill("Dimos");
  await expect(page.getByRole("main")).toContainText("Nikos Dimos");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Drivers", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByPlaceholder("Search by name or reference…"),
  ).toHaveValue("Dimos");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Fleet", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Fleet", exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "Drivers", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByPlaceholder("Search by name or reference…"),
  ).toHaveValue("Dimos");
  await page.goForward();
  await expect(
    page.getByRole("heading", { name: "Fleet", exact: true }),
  ).toBeVisible();
});

test("a saved Drivers link accepts a bounded search and rejects invalid date and pagination", async ({
  page,
}) => {
  await page.goto("/?view=drivers&q=Dimos&page=-2&service_date=2026-02-31");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "Drivers", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByPlaceholder("Search by name or reference…"),
  ).toHaveValue("Dimos");
  await expect(page.getByRole("main")).toContainText("Nikos Dimos");
  expect(new URL(page.url()).searchParams.has("service_date")).toBe(false);
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
});
