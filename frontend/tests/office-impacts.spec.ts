import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";

const day = "2026-10-31";
async function csrf(page: Page) {
  return { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" };
}
async function open(page: Page, query = "") {
  await page.goto("/" + query);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
}

test("approved leave shows how many trips need review, lists them, and leads to the existing change tools without changing anything", async ({ page }) => {
  await open(page, "?service_date=" + day);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const headers = await csrf(page);
  let revision = await (await page.request.get("/api/v1/scheduling/revisions/active?service_date=" + day)).json();
  for (const action of ["request-approval", "approve", "publish"]) {
    const response = await page.request.post(`/api/v1/scheduling/revisions/${revision.revision_id}/${action}`, { headers, data: { version: revision.version } });
    expect(response.ok(), await response.text()).toBeTruthy();
    revision = await response.json();
  }
  const me = ((await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[])[0]!.id;
  expect((await page.request.post("/api/v1/office/approval-routes", { headers, data: { request_id: crypto.randomUUID(), membership_id: me } })).ok()).toBeTruthy();
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByLabel("Month").fill("2026-10");
  await page.getByRole("button", { name: "New request" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel("Driver", { exact: true }).fill("Nikos Dimos · DR0");
  await form.getByLabel(/From/).fill(day + "T00:00");
  await form.getByLabel(/Until/).fill("2026-11-01T00:00");
  await form.getByRole("button", { name: "Record request" }).click();
  await expect(form).toBeHidden();
  await page.getByRole("row", { name: /Nikos Dimos/ }).getByRole("button", { name: "Decide" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true }).click();
  const notice = page.getByRole("status").filter({ hasText: "Saved." });
  await expect(notice).toContainText("1 trip needs review");
  await expect(notice).toContainText("No trip was changed");
  await notice.getByRole("button", { name: "Review the trips" }).click();
  await expect(page.getByRole("heading", { name: "Affected trips" })).toBeVisible();
  const row = page.getByRole("row", { name: /333001/ });
  await expect(row).toContainText("Published");
  await expect(row).toContainText("Driver");
  await page.screenshot({ path: "test-results/office-impacts.png", fullPage: true });
  const current = await (await page.request.get("/api/v1/scheduling/revisions/" + revision.revision_id)).json();
  expect(current.status).toBe("published");
  await page.setViewportSize({ width: 390, height: 844 });
  const open_ = row.getByRole("button", { name: "Open in Scheduling Studio" });
  await open_.scrollIntoViewIfNeeded();
  await expect(open_).toBeVisible();
  await page.screenshot({ path: "test-results/office-impacts-mobile.png", fullPage: true });
  await open_.click();
  await expect(page.getByTestId("revision-version")).toBeVisible();
});

test("service day explains missing working time with one next action", async ({ page }) => {
  await open(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const headers = await csrf(page);
  const create = async (path: string, data: object) => {
    const response = await page.request.post("/api/v1/" + path, { headers, data });
    expect(response.ok(), (await response.text()).slice(0, 400)).toBeTruthy();
    return response.json();
  };
  const stations = (await (await page.request.get("/api/v1/stations?page_size=10")).json()).items as { id: number; version: number }[];
  const driver = await create("drivers", { code: "DR9", first_name: "Petros", last_name: "Nomikos", home_station_id: stations[0]!.id });
  const vehicle = await create("vehicles", { code: "BUS9", registration_plate: "KRA-4329", bus_type: "02", home_station_id: stations[0]!.id });
  await create("pairings", { driver_id: driver.id, vehicle_id: vehicle.id, home_station_id: stations[0]!.id, service_date: "2026-10-30", confirm: true,
    driver_version: 1, vehicle_version: 1, home_station_version: stations[0]!.version });
  await page.goto("/?view=planning&service_date=2026-10-30");
  await expect(page.getByText(/Working time is not recorded for the drivers below/)).toBeVisible();
  await expect(page.getByText("Petros Nomikos")).toBeVisible();
  await page.screenshot({ path: "test-results/service-day-working-time.png", fullPage: true });
  await page.getByRole("button", { name: "Record working time" }).click();
  await expect(page.getByRole("heading", { name: "Office", exact: true })).toBeVisible();
});

test("a day with two absent drivers is repaired in one reviewed change and then publishes cleanly", async ({ page }) => {
  await open(page, "?service_date=" + day);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const headers = await csrf(page);
  const post = async (path: string, data: object) => {
    const response = await page.request.post(path, { headers, data });
    expect(response.ok(), (await response.text()).slice(0, 400)).toBeTruthy();
    return response.json();
  };
  let revision = await (await page.request.get("/api/v1/scheduling/revisions/active?service_date=" + day)).json();
  for (const action of ["request-approval", "approve", "publish"]) revision = await post(`/api/v1/scheduling/revisions/${revision.revision_id}/${action}`, { version: revision.version });
  const me = ((await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[])[0]!.id;
  await post("/api/v1/office/approval-routes", { request_id: crypto.randomUUID(), membership_id: me });
  const drivers = (await (await page.request.get("/api/v1/drivers?page_size=10")).json()).items as { id: number }[];
  for (const driver of drivers) {
    const leave = await post("/api/v1/office/leave-requests", { request_id: crypto.randomUUID(), driver_id: driver.id, start_local: day + "T00:00:00", end_local: "2026-11-01T00:00:00", category: "annual" });
    await post(`/api/v1/office/leave-requests/${leave.id}/decision`, { request_id: crypto.randomUUID(), expected_version: leave.version, decision: "approved", note: null });
  }
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByLabel("Month").fill("2026-10");
  await page.getByRole("button", { name: "Affected trips", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "2 trips need review" })).toBeVisible();
  await page.getByRole("button", { name: `Repair ${day} in one change` }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("listitem")).toHaveCount(2);
  await dialog.getByLabel("Action for 333001").selectOption("move");
  await dialog.getByLabel("Crew for 333001").selectOption({ index: 1 });
  await dialog.getByLabel("Reason").fill("Both drivers are on leave");
  await dialog.getByLabel("I confirm none of these trips has started.").check();
  await dialog.getByRole("button", { name: "Check", exact: true }).click();
  await expect(dialog.getByRole("alert").filter({ hasText: "Cannot be saved yet" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Save draft" })).toBeDisabled();
  await dialog.getByLabel("Action for 333001").selectOption("unassign");
  await dialog.getByLabel("I confirm none of these trips has started.").check();
  await dialog.getByRole("button", { name: "Check", exact: true }).click();
  await expect(dialog.getByText("Checks passed.")).toBeVisible();
  await page.screenshot({ path: "test-results/office-repair-two-drivers.png", fullPage: true });
  await dialog.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByTestId("revision-version")).toBeVisible();
  let successor = await (await page.request.get("/api/v1/scheduling/revisions/active?service_date=" + day)).json();
  expect(successor.status).toBe("draft");
  expect(successor.revision_id).not.toBe(revision.revision_id);
  for (const action of ["request-approval", "approve", "publish"]) successor = await post(`/api/v1/scheduling/revisions/${successor.revision_id}/${action}`, { version: successor.version });
  await page.getByRole("button", { name: "Office", exact: true }).click();
  await page.getByLabel("Month").fill("2026-10");
  await page.getByRole("button", { name: "Affected trips", exact: true }).click();
  await expect(page.getByText("No affected trips this month.")).toBeVisible();
});
