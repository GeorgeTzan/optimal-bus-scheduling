import { test, expect, signIn } from "./helpers/auth";

test("Drivers offers bulk import, preserves its context and returns after a real multi-row save", async ({
  page,
}) => {
  await page.goto("/?view=drivers");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page
    .getByRole("button", { name: "Import from Excel/CSV", exact: true })
    .click({ timeout: 5000 });
  await expect(
    page.locator('.import-choices button[aria-pressed="true"]'),
  ).toHaveText(/Drivers/);
  await page.reload();
  await expect(
    page.getByRole("heading", {
      name: "Bring your records together",
      exact: true,
    }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download Excel template", exact: true })
    .click();
  expect((await download).suggestedFilename()).toContain("drivers");
  await page.getByLabel("Choose your file", { exact: true }).setInputFiles({
    name: "new-drivers.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Staff reference,First name,Last name,Phone,Licence number,Home station,Active\nBULK700,Alex,Dimitriou,,,,\nBULK701,Maria,Kosta,,,,\n",
    ),
  });
  await page.getByRole("button", { name: "Review file", exact: true }).click();
  await page
    .getByRole("button", { name: "Continue to summary", exact: true })
    .click();
  await page.getByRole("button", { name: "Save records", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your records are saved", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Return to drivers", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Drivers", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("main")).toContainText("Alex Dimitriou");
  await expect(page.getByRole("main")).toContainText("Maria Kosta");
});

test("Timetables opens the actual timetable template and keeps the choice on reload", async ({
  page,
}) => {
  await page.goto("/?view=timetables");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page
    .getByRole("button", { name: "Import from Excel/CSV", exact: true })
    .click({ timeout: 5000 });
  await expect(
    page.locator('.import-choices button[aria-pressed="true"]'),
  ).toHaveText(/Timetable/);
  await page.reload();
  const template = page.waitForResponse((r) =>
    r.url().includes("/api/v1/imports/templates/timetable?"),
  );
  await page
    .getByRole("button", { name: "Download Excel template", exact: true })
    .click();
  expect((await template).status()).toBe(200);
  await page
    .getByRole("button", { name: "Return to timetables", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your timetables", exact: true }),
  ).toBeVisible();
});
