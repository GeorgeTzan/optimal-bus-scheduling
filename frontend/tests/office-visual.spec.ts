import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";

/** Captures of the real screens in Greek and English, light and dark, on desktop and a 390px phone. Reviewed by eye, not asserted pixel by pixel. */
async function seed(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const headers = { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" };
  const me = ((await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[])[0]!.id;
  for (const capability of ["maintenance.manage", "maintenance.release"])
    expect((await page.request.put("/api/v1/office/grants", { headers, data: { request_id: crypto.randomUUID(), membership_id: me, capability, is_active: true, expected_version: null } })).ok()).toBeTruthy();
  expect((await page.request.post("/api/v1/office/approval-routes", { headers, data: { request_id: crypto.randomUUID(), membership_id: me } })).ok()).toBeTruthy();
  const drivers = (await (await page.request.get("/api/v1/drivers?page_size=10")).json()).items as { id: number }[];
  const vehicles = (await (await page.request.get("/api/v1/vehicles?page_size=10")).json()).items as { id: number }[];
  await page.request.post("/api/v1/office/leave-requests", { headers, data: { request_id: crypto.randomUUID(), driver_id: drivers[0]!.id, start_local: "2026-10-12T00:00:00", end_local: "2026-10-14T00:00:00", category: "annual" } });
  await page.request.post("/api/v1/office/vehicle-periods", { headers, data: { request_id: crypto.randomUUID(), vehicle_id: vehicles[0]!.id, kind: "out_of_service", start_local: "2026-10-01T08:00:00", estimated_end_local: "2026-10-03T08:00:00" } });
  await page.reload();
}
async function office(page: Page, tab: string) {
  await page.getByRole("button", { name: /^(Office|Γραφείο)$/ }).click();
  await page.getByLabel(/Month|Μήνας/).fill("2026-10");
  await page.getByRole("button", { name: tab, exact: true }).click();
}

test("office screens in both languages, both themes, desktop and phone", async ({ page }) => {
  await seed(page);
  await office(page, "Leave");
  await expect(page.getByRole("row", { name: /Pending/ })).toBeVisible();
  await page.screenshot({ path: "test-results/visual-leave-en-light.png", fullPage: true });
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.screenshot({ path: "test-results/visual-leave-en-dark.png", fullPage: true });
  await page.getByRole("button", { name: "Vehicle maintenance" }).click();
  await expect(page.getByRole("row", { name: /Out of service/ }).first()).toBeVisible();
  await page.screenshot({ path: "test-results/visual-fleet-en-dark.png", fullPage: true });
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
  await page.getByRole("button", { name: "Άδειες", exact: true }).click();
  await expect(page.getByRole("row", { name: /Εκκρεμεί/ })).toBeVisible();
  await page.screenshot({ path: "test-results/visual-leave-el-light.png", fullPage: true });
  await page.getByRole("button", { name: "Απόφαση" }).first().click();
  await page.screenshot({ path: "test-results/visual-decide-el.png", fullPage: true });
  await page.getByRole("button", { name: "Κλείσιμο" }).first().click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/visual-leave-el-mobile.png", fullPage: true });
});
