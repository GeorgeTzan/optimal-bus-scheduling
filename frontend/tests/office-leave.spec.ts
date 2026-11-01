import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";

async function csrf(page: Page) {
  return { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" };
}
/** The shared fixture already grants record-keeping; the administrator becomes the default leave approver through the real API. */
async function prepare(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("button", { name: "Office", exact: true }).click();
  const headers = await csrf(page);
  const members = (await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[];
  const me = members[0]!.id;
  expect((await page.request.post("/api/v1/office/approval-routes", { headers, data: { request_id: crypto.randomUUID(), membership_id: me } })).ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByLabel("Month").fill("2026-10");
}

test("leave is requested, approved, cancelled and kept after reload", async ({ page }) => {
  await prepare(page);
  await expect(page.getByText("No leave requests this month.")).toBeVisible();
  await page.getByRole("button", { name: "New request" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Driver", { exact: true }).fill("Eleni Papadopoulou · DR1");
  await dialog.getByLabel(/From/).fill("2026-10-12T00:00");
  await dialog.getByLabel(/Until/).fill("2026-10-14T00:00");
  await dialog.getByRole("button", { name: "Record request" }).click();
  await expect(dialog).toBeHidden();
  const row = page.getByRole("row", { name: /Eleni Papadopoulou/ });
  await expect(row).toContainText("Pending");
  await row.getByRole("button", { name: "Decide" }).click();
  const decide = page.getByRole("dialog");
  await expect(decide.getByText(/does not move or cancel trips/)).toBeVisible();
  await decide.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(decide).toBeHidden();
  await expect(row).toContainText("Approved");
  await page.screenshot({ path: "test-results/office-leave.png", fullPage: true });
  await page.reload();
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByLabel("Month").fill("2026-10");
  await expect(page.getByRole("row", { name: /Eleni Papadopoulou/ })).toContainText("Approved");
  await page.getByRole("row", { name: /Eleni Papadopoulou/ }).getByRole("button", { name: "Cancel leave" }).click();
  await page.getByRole("dialog").getByLabel("Reason").fill("Plans changed");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel leave" }).click();
  await expect(page.getByRole("row", { name: /Eleni Papadopoulou/ })).toContainText("Cancelled");
});

test("a failed save keeps the entered leave details and the approve action stays reachable on a phone", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "New request" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Driver", { exact: true }).fill("Nikos Dimos · DR0");
  await dialog.getByLabel(/From/).fill("2026-10-20T00:00");
  await dialog.getByLabel(/Until/).fill("2026-10-21T00:00");
  await page.route("**/api/v1/office/leave-requests", (route) => route.request().method() === "POST" ? route.fulfill({ status: 500, contentType: "application/json", body: "{}" }) : route.continue());
  await dialog.getByRole("button", { name: "Record request" }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog.getByLabel(/From/)).toHaveValue("2026-10-20T00:00");
  await page.unroute("**/api/v1/office/leave-requests");
  await dialog.getByRole("button", { name: "Record request" }).click();
  await expect(dialog).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  const decide = page.getByRole("row", { name: /Nikos Dimos/ }).getByRole("button", { name: "Decide" });
  await decide.scrollIntoViewIfNeeded();
  await expect(decide).toBeVisible();
  await page.screenshot({ path: "test-results/office-leave-mobile.png", fullPage: true });
});
