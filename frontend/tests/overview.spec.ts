import { signIn, test, expect } from "./helpers/auth";

test("overview never claims feasibility from an unassigned-trip counter", async ({
  page,
}) => {
  await page.goto("/?service_date=2026-10-31");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Overview", exact: true })
    .click();
  await expect(
    page.getByText("Unassigned Trips", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("100% feasibility", { exact: true })).toHaveCount(
    0,
  );
});
