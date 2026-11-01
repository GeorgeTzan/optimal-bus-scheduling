import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";

async function prepare(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("button", { name: "Office", exact: true }).click();
  const headers = { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" };
  const me = ((await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[])[0]!.id;
  for (const capability of ["maintenance.manage", "maintenance.release"])
    expect((await page.request.put("/api/v1/office/grants", { headers, data: { request_id: crypto.randomUUID(), membership_id: me, capability, is_active: true, expected_version: null } })).ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByRole("button", { name: "Vehicle maintenance" }).click();
  await page.getByLabel("Month").fill("2026-10");
}

test("an out-of-service vehicle stays open past its estimate until it is explicitly released", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "New entry" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Vehicle", { exact: true }).fill("KRA-4320 · BUS0");
  await dialog.getByLabel(/^From/).fill("2026-10-01T08:00");
  await dialog.getByLabel(/Estimated return/).fill("2026-10-03T08:00");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog).toBeHidden();
  const row = page.getByRole("row", { name: /KRA-4320/ });
  await expect(row).toContainText("Out of service");
  await expect(row).toContainText("Open");
  await page.reload();
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByRole("button", { name: "Vehicle maintenance" }).click();
  await page.getByLabel("Month").fill("2026-10");
  await expect(page.getByRole("row", { name: /KRA-4320/ })).toContainText("Open");
  await page.screenshot({ path: "test-results/office-maintenance.png", fullPage: true });
  await page.getByRole("row", { name: /KRA-4320/ }).getByRole("button", { name: "Release" }).click();
  const release = page.getByRole("dialog");
  await expect(release.getByText(/does not certify its mechanical condition/)).toBeVisible();
  await release.getByLabel(/When it returned/).fill("2026-10-05T08:00");
  await release.getByLabel("Note").fill("Brakes repaired at the workshop");
  await release.getByRole("button", { name: "Release", exact: true }).click();
  await expect(release).toBeHidden();
  await expect(page.getByRole("row", { name: /KRA-4320/ })).toContainText("Released");
});

test("a future release time is refused with an explanation and keeps the form", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "New entry" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Vehicle", { exact: true }).fill("KRA-4321 · BUS1");
  await dialog.getByLabel(/^From/).fill("2026-10-01T08:00");
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("row", { name: /KRA-4321/ }).getByRole("button", { name: "Release" }).click();
  const release = page.getByRole("dialog");
  await release.getByLabel(/When it returned/).fill("2099-01-01T08:00");
  await release.getByLabel("Note").fill("Too early to say");
  await release.getByRole("button", { name: "Release", exact: true }).click();
  await expect(release.getByRole("alert")).toContainText(/not in the future/);
  await expect(release.getByLabel("Note")).toHaveValue("Too early to say");
});
