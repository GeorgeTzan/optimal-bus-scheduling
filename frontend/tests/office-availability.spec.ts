import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";

async function openOffice(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByLabel("Month").fill("2026-10");
}

test("an administrator grants maintenance access, then records weekly working time that survives reload", async ({ page }) => {
  await openOffice(page);
  await expect(page.getByRole("button", { name: "Vehicle maintenance" })).toHaveCount(0);
  await page.getByRole("button", { name: "Access", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Office access" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /: Working time and leave/ }).first()).toBeChecked();
  const maintenance = page.getByRole("checkbox", { name: /: Maintenance$/ }).first();
  await expect(maintenance).not.toBeChecked();
  await maintenance.click();
  await expect(maintenance).toBeChecked();
  await expect(page.getByRole("button", { name: "Vehicle maintenance" })).toBeVisible();
  await page.getByRole("button", { name: "Driver working time" }).click();
  await page.getByRole("button", { name: "Weekly working time" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Add a driver").fill("Nikos Dimos · DR0");
  await expect(dialog.getByRole("list", { name: "Selected drivers" })).toContainText("Nikos Dimos");
  await dialog.getByLabel("Valid from").fill("2027-01-01");
  await dialog.getByLabel(/Valid until/).fill("2027-03-31");
  await expect(dialog.getByText(/1 patterns will be saved: 08:00–16:00, 5 days a week/)).toBeVisible();
  await dialog.getByRole("button", { name: "Save working time" }).click();
  await expect(dialog).toBeHidden();
  const row = page.getByRole("row", { name: /08:00–16:00/ });
  await expect(row).toContainText("Nikos Dimos");
  await page.screenshot({ path: "test-results/office-working-time.png", fullPage: true });
  await page.reload();
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByRole("button", { name: "Driver working time" }).click();
  await expect(page.getByRole("row", { name: /08:00–16:00/ })).toContainText("2027-03-31");
  page.once("dialog", (confirm) => void confirm.accept());
  await page.getByRole("row", { name: /08:00–16:00/ }).getByRole("button", { name: /Retire working time/ }).click();
  await expect(page.getByRole("row", { name: /08:00–16:00/ })).toHaveCount(0);
});

test("an unsaved working-time form asks before it is closed and a failed save keeps the entries", async ({ page }) => {
  await openOffice(page);
  await page.getByRole("button", { name: "Driver working time" }).click();
  await page.getByRole("button", { name: "Period or absence" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Driver", { exact: true }).fill("Eleni Papadopoulou · DR1");
  await dialog.getByLabel(/From/).fill("2026-10-05T08:00");
  await page.route("**/api/v1/office/driver-periods", (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog.getByLabel(/From/)).toHaveValue("2026-10-05T08:00");
  let asked = "";
  page.once("dialog", (confirm) => { asked = confirm.message(); void confirm.dismiss(); });
  await dialog.getByRole("button", { name: "Close" }).first().click();
  await expect.poll(() => asked).toMatch(/unsaved|μη αποθηκευμένες/i);
  await expect(dialog).toBeVisible();
});
