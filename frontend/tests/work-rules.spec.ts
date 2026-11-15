import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect, signIn } from "./helpers/auth";

async function openRules(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Work rules", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Driver work limits" })).toBeVisible();
}

test("admin saves a stricter limit and reloads it", async ({ page }) => {
  await openRules(page);
  const limit = page.getByLabel("Maximum daily work", { exact: true });
  const row = page.getByRole("row").filter({ has: limit });
  await expect(limit).toHaveValue("10:00");
  await expect(row).toContainText("legal");
  await expect(page.getByText("To be confirmed by a lawyer")).toBeVisible();
  await limit.fill("9:30");
  await expect(row).toContainText("stricter");
  await expect(page.getByLabel("Rest day after an overnight")).not.toBeChecked();
  await page.getByLabel("Rest day after an overnight").check();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await page.reload();
  await page.getByRole("navigation").getByRole("button", { name: "Work rules", exact: true }).click();
  await expect(page.getByLabel("Maximum daily work", { exact: true })).toHaveValue("9:30");
  await expect(page.getByLabel("Rest day after an overnight")).toBeChecked();
  await page.getByRole("button", { name: "Reset Maximum daily work to legal" }).click();
  await expect(page.getByLabel("Maximum daily work", { exact: true })).toHaveValue("10:00");
  await page.screenshot({ path: "test-results/work-rules-en.png", fullPage: true });
});

test("looser value shows red and cannot save", async ({ page }) => {
  await openRules(page);
  const limit = page.getByLabel("Maximum daily work", { exact: true });
  const row = page.getByRole("row").filter({ has: limit });
  await limit.fill("10:30");
  await expect(row).toContainText("looser than law");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await limit.fill("9:00");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  const rest = page.getByLabel("Daily rest", { exact: true });
  await rest.fill("11:00");
  await expect(page.getByRole("row").filter({ has: rest })).toContainText("looser than law");
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await rest.fill("13");
  await expect(page.getByRole("row").filter({ has: rest })).toContainText("stricter");
  await expect(page.getByLabel("Normal daily work")).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "Normal daily work" })).toContainText("8:00");
});

test("language switch keeps unsaved edits and Greek shows Greek citations", async ({ page }) => {
  await openRules(page);
  const limit = page.getByLabel("Maximum daily work", { exact: true });
  await limit.fill("9:30");
  await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
  await expect(page.getByLabel("Μέγιστη ημερήσια εργασία", { exact: true })).toHaveValue("9:30");
  const row = page.getByRole("row").filter({ has: page.getByLabel("Μέγιστη ημερήσια εργασία", { exact: true }) });
  await expect(row).toContainText("ΠΔ 54/1998 άρ.");
  await expect(row).not.toContainText("Art.");
});

test("a stale version shows a message and reloads", async ({ page }) => {
  await openRules(page);
  await page.route("**/api/v1/work-rules", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    const body = route.request().postDataJSON();
    await route.continue({ postData: JSON.stringify({ ...body, expected_version: 99 }) });
  });
  const limit = page.getByLabel("Maximum daily work", { exact: true });
  await limit.fill("9:30");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator(".auth-error")).toContainText("changed by someone else");
  await expect(limit).toHaveValue("10:00");
});

test("a server looser-than-law refusal lands on the field", async ({ page }) => {
  await openRules(page);
  await page.route("**/api/v1/work-rules", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    const body = route.request().postDataJSON();
    await route.continue({ postData: JSON.stringify({ ...body, overrides: { daily_work_max: 700 } }) });
  });
  const limit = page.getByLabel("Maximum daily work", { exact: true });
  await limit.fill("9:30");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  const row = page.getByRole("row").filter({ has: limit });
  await expect(row.getByRole("alert")).toContainText("cannot be looser than the law");
});

test("dispatcher sees read-only table", async ({ page, customer }) => {
  const script = path.resolve("tests/fixtures/identity-seed.py");
  const invite = JSON.parse(
    execFileSync("uv", ["run", "python", script, "invite", String(customer.tenant_id), "dispatcher"], {
      cwd: path.resolve("../backend"),
      env: { ...process.env, PYTHONPATH: path.resolve("../backend") },
      encoding: "utf8",
    }),
  ) as { token: string };
  await page.context().clearCookies();
  await page.goto("/accept-invitation#token=" + invite.token);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await page.getByLabel("Full name", { exact: true }).fill("Rules reader");
  await page.getByLabel("New password", { exact: true }).fill("ReaderStrongPassword123!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
  await page.goto("/?view=rules");
  await expect(page.getByRole("heading", { name: "Driver work limits" })).toBeVisible();
  await expect(page.getByRole("row").filter({ has: page.getByRole("cell", { name: "Maximum daily work", exact: true }) })).toContainText("10:00");
  await expect(page.locator("table input")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

const PRIOR = "2026-11-02";
const NEXT = "2026-11-03";

async function call(page: import("@playwright/test").Page, method: "post" | "put", url: string, data: object) {
  const csrf = (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "";
  const response = await page.request[method](url, { headers: { "X-CSRF-Token": csrf }, data });
  expect(response.ok(), (await response.text()).slice(0, 400)).toBeTruthy();
  return response.json();
}

async function items(page: import("@playwright/test").Page, entity: string) {
  const response = await page.request.get(`/api/v1/${entity}?page_size=100`);
  expect(response.ok()).toBeTruthy();
  return ((await response.json()) as { items: { id: number; code: string; version: number }[] }).items;
}

async function openStudio(page: import("@playwright/test").Page, day: string) {
  await page.goto(`/?service_date=${day}`);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
}

async function crew(revision: { source_resources: { resource_id: string; driver_code: string }[] }, code: string) {
  return revision.source_resources.find((r) => r.driver_code === code)!.resource_id;
}

async function breach(page: import("@playwright/test").Page, nextCrew: "DR0" | "DR1", publishNext: boolean) {
  await openStudio(page, "2026-10-31");
  const stations = await items(page, "stations");
  const [drivers, vehicles] = [await items(page, "drivers"), await items(page, "vehicles")];
  const origin = stations.find((s) => s.code === "001")!;
  const destination = stations.find((s) => s.code === "002")!;
  for (const [code, from, to, weekday] of [["LATE", "21:10", "22:10", 0], ["EARLY", "06:00", "07:00", 1]] as const)
    await call(page, "post", "/api/v1/timetables", {
      trip_code: code, origin_station_id: origin.id, destination_station_id: destination.id,
      departure_time: from, arrival_time: to, arrival_day_offset: 0, operating_weekdays: [weekday],
      valid_from: "2026-01-01", valid_until: "2028-12-31", allowed_bus_types: ["02"],
    });
  for (const day of [PRIOR, NEXT])
    for (const [index, driver] of drivers.entries())
      await call(page, "post", "/api/v1/pairings", {
        driver_id: driver.id, vehicle_id: vehicles[index]!.id, home_station_id: origin.id, service_date: day, confirm: true,
        driver_version: driver.version, vehicle_version: vehicles[index]!.version, home_station_version: origin.version,
      });
  const assign = async (revision: any, trip: string, code: string) =>
    call(page, "post", `/api/v1/scheduling/revisions/${revision.revision_id}/patches`, {
      version: revision.version,
      patches: [{ trip_id: revision.source_trips.find((t: any) => t.trip_code === trip).id, new_resource_id: await crew(revision, code) }],
    });
  const move = async (revision: any) => {
    for (const action of ["request-approval", "approve", "publish"])
      revision = await call(page, "post", `/api/v1/scheduling/revisions/${revision.revision_id}/${action}`, { version: revision.version });
    return revision;
  };
  const monday = await call(page, "post", "/api/v1/scheduling/revisions", { service_date: PRIOR });
  await move(await assign(monday, "LATE", "DR0"));
  const tuesday = await assign(await call(page, "post", "/api/v1/scheduling/revisions", { service_date: NEXT }), "EARLY", nextCrew);
  if (publishNext) await move(tuesday);
  await page.goto(`/?service_date=${NEXT}`);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  return tuesday;
}

test("legal finding blocks request approval", async ({ page }) => {
  await breach(page, "DR0", false);
  await page.locator(".data-tabs").getByRole("button", { name: /^Work rules/ }).click();
  const row = page.getByRole("listitem").filter({ hasText: "Earliest start" });
  await expect(row).toContainText("Law");
  await expect(row).toContainText("Nikos Dimos:");
  await expect(row).toContainText("EARLY 06:00");
  await expect(row).toContainText("Only 7:30 rest after the previous duty (limit 10:00). Earliest start: 03/11, 08:20.");
  await page.screenshot({ path: "test-results/studio-work-rules-en.png", fullPage: true });
  await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Νωρίτερη έναρξη" })).toContainText("Νόμος");
  await page.screenshot({ path: "test-results/studio-work-rules-el.png", fullPage: true });
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(row.getByRole("button", { name: "Override…" })).toHaveCount(0);
  const request = page.getByRole("button", { name: "Request approval", exact: true });
  await expect(request).toBeDisabled();
  await expect(request).toHaveAttribute("title", /1/);
  await row.getByRole("button", { name: "Show", exact: true }).click();
  await expect(page.locator(".timeline-trip.is-selected")).toHaveCount(1);
  await expect(page.locator(".timeline-trip.has-conflict")).toHaveCount(1);
});

test("override a warning with reason removes it", async ({ page }) => {
  await openStudio(page, "2026-10-31");
  const drivers = await items(page, "drivers");
  const profile = await (await page.request.get(`/api/v1/work-rules/drivers/${drivers[0]!.id}/profile`)).json();
  await call(page, "put", `/api/v1/work-rules/drivers/${drivers[0]!.id}/profile`, {
    expected_version: profile.version, overnight_allowed: true, split_shift_allowed: true, must_return_to_base: true,
    preferred_route_ids: [], forbidden_route_ids: [],
  });
  await page.reload();
  await page.locator(".data-tabs").getByRole("button", { name: /^Work rules/ }).click();
  const row = page.getByRole("listitem").filter({ hasText: "Company" });
  await expect(row).toHaveCount(1);
  await row.getByRole("button", { name: "Override…" }).click();
  const dialog = page.getByRole("dialog", { name: "Override company rule" });
  const submit = dialog.getByRole("button", { name: "Override", exact: true });
  await expect(submit).toBeDisabled();
  await dialog.getByLabel("Reason", { exact: true }).fill("Depot agreed the late return.");
  await submit.click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("listitem").filter({ hasText: "Company" })).toHaveCount(0);
  await page.reload();
  await page.locator(".data-tabs").getByRole("button", { name: /^Work rules/ }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Company" })).toHaveCount(0);
});

test("urgent change shows work-rule finding before save", async ({ page }) => {
  await breach(page, "DR1", true);
  await page.getByRole("button", { name: "Inspect EARLY", exact: true }).click();
  await page.getByRole("button", { name: "Move trip", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Review schedule change" });
  const revision = await (await page.request.get(`/api/v1/scheduling/revisions/active?service_date=${NEXT}`)).json();
  await dialog.getByLabel("Destination assignment", { exact: true }).selectOption(await crew(revision, "DR0"));
  const emergency = dialog.getByLabel("Emergency (up to 11 h)");
  await expect(emergency).toBeDisabled();
  await dialog.getByLabel("Reason for change", { exact: true }).fill("Driver called in sick.");
  await dialog.getByLabel("I confirmed the selected trips have not started").check();
  await expect(emergency).toBeEnabled();
  await emergency.check();
  const sent = page.waitForRequest((r) => r.url().endsWith("/changes/preview"));
  await dialog.getByRole("button", { name: "Check change", exact: true }).click();
  expect((await sent).postDataJSON().emergency).toBe(true);
  const row = dialog.getByRole("listitem").filter({ hasText: "Earliest start" });
  await expect(row).toContainText("Law");
  await expect(dialog.getByRole("button", { name: "Create reviewed draft" })).toHaveCount(0);
});

async function openRecord(page: import("@playwright/test").Page, nav: "Drivers" | "Fleet" | "Timetables", text: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: nav, exact: true }).click();
  await page.getByRole("row").filter({ hasText: text }).getByRole("button", { name: "Edit", exact: true }).click();
}

test("forbid a route for a driver and see it in the studio warning", async ({ page }) => {
  await openRecord(page, "Drivers", "Nikos Dimos");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Preferences & restrictions", exact: true }).click();
  await expect(dialog.getByText("Central depot")).toBeVisible();
  const forbid = dialog.getByLabel("Add a forbidden route", { exact: true });
  await forbid.selectOption({ label: "Central depot → Harbour" });
  await expect(dialog.getByRole("button", { name: "Remove Central depot → Harbour" })).toBeVisible();
  await expect(dialog.getByLabel("Add a preferred route", { exact: true }).locator("option", { hasText: "Central depot → Harbour" })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Save preferences", exact: true }).click();
  await expect(dialog.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await page.screenshot({ path: "test-results/driver-profile-en.png", fullPage: true });
  await expect(dialog.getByRole("textbox", { name: "First name" })).toBeHidden();
  await page.goto("/?service_date=2026-10-31");
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page.locator(".data-tabs").getByRole("button", { name: /^Work rules/ }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "barred from a route" }).first()).toBeVisible();
});

test("enter a baseline and see yearly overtime", async ({ page }) => {
  const year = new Date().getFullYear();
  await openRecord(page, "Drivers", "Nikos Dimos");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Preferences & restrictions", exact: true }).click();
  await expect(dialog.getByTestId("week-overtime")).toContainText("0:00");
  await dialog.getByLabel("Baseline as of", { exact: true }).fill(`${year}-01-10`);
  await dialog.getByLabel("Overtime so far this year (hours)", { exact: true }).fill("12:30");
  await dialog.getByLabel("Last duty ended", { exact: true }).fill(`${year}-01-10T22:00`);
  await dialog.getByLabel("Last weekly rest ended", { exact: true }).fill(`${year}-01-08T06:00`);
  await dialog.getByLabel("Weekly rest was taken at the home base").check();
  await dialog.getByLabel("Owed compensatory rest (hours)", { exact: true }).fill("3");
  const sent = page.waitForRequest((r) => r.url().endsWith("/baseline") && r.method() === "PUT");
  await dialog.getByRole("button", { name: "Save baseline", exact: true }).click();
  const body = (await sent).postDataJSON();
  expect(body).toMatchObject({ expected_version: 0, overtime_minutes: 750, owed_rest_minutes: 180, last_weekly_rest_at_base: true });
  expect(body.last_duty_end).toBe(`${year}-01-10T20:00:00.000Z`);
  await expect(dialog.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await expect(dialog.getByTestId("week-overtime")).toContainText("12:30");
  await page.reload();
  await page.getByRole("navigation").getByRole("button", { name: "Drivers", exact: true }).click();
  await page.getByRole("row").filter({ hasText: "Nikos Dimos" }).getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Preferences & restrictions", exact: true }).click();
  await expect(page.getByRole("dialog").getByLabel("Overtime so far this year (hours)")).toHaveValue("12:30");
  await expect(page.getByRole("dialog").getByLabel("Last duty ended")).toHaveValue(`${year}-01-10T22:00`);
});

test("a locked baseline explains the publication", async ({ page }) => {
  await openRecord(page, "Drivers", "Nikos Dimos");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Preferences & restrictions", exact: true }).click();
  await page.route("**/api/v1/work-rules/drivers/*/baseline", async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: { code: "baseline_locked", message: "x" } }) });
  });
  await dialog.getByLabel("Baseline as of", { exact: true }).fill("2026-01-10");
  await dialog.getByRole("button", { name: "Save baseline", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("already published on or after this date");
});

test("a future baseline date is refused", async ({ page }) => {
  await openRecord(page, "Drivers", "Nikos Dimos");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Preferences & restrictions", exact: true }).click();
  await dialog.getByLabel("Baseline as of", { exact: true }).fill(`${new Date().getFullYear() + 1}-01-10`);
  await dialog.getByRole("button", { name: "Save baseline", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("The baseline date must be before today.");
});

test("vehicle forbidden route saves", async ({ page }) => {
  await openRecord(page, "Fleet", "KRA-4320");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Route restrictions", exact: true }).click();
  await dialog.getByLabel("Add a forbidden route", { exact: true }).selectOption({ label: "Central depot → Harbour" });
  await dialog.getByRole("button", { name: "Save route restrictions", exact: true }).click();
  await expect(dialog.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  const vehicles = (await (await page.request.get("/api/v1/vehicles?page_size=100")).json()).items as { id: number; code: string }[];
  const id = vehicles.find((v) => v.code === "BUS0")!.id;
  const saved = await (await page.request.get(`/api/v1/work-rules/vehicles/${id}/forbidden-routes`)).json();
  expect(saved.route_ids).toHaveLength(1);
});

test("route service type saves", async ({ page }) => {
  await openRecord(page, "Timetables", "333001");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Service type", { exact: true })).toHaveValue("intercity");
  await dialog.getByLabel("Service type", { exact: true }).selectOption({ label: "Urban" });
  await dialog.getByRole("button", { name: "Continue", exact: true }).click();
  await dialog.getByRole("button", { name: "Save timetable", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  const items = (await (await page.request.get("/api/v1/timetables?page_size=100")).json()).items as { trip_code: string; service_type: string }[];
  expect(items.find((t) => t.trip_code === "333001")!.service_type).toBe("urban");
});

test("baseline times follow the tenant timezone", async ({ page }) => {
  const year = new Date().getFullYear();
  await page.route("**/api/v1/office/capabilities", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), timezone: "America/New_York" } });
  });
  await openRecord(page, "Drivers", "Nikos Dimos");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Preferences & restrictions", exact: true }).click();
  await dialog.getByLabel("Baseline as of", { exact: true }).fill(`${year}-01-10`);
  await dialog.getByLabel("Last duty ended", { exact: true }).fill(`${year}-01-10T22:00`);
  const sent = page.waitForRequest((r) => r.url().endsWith("/baseline") && r.method() === "PUT");
  await dialog.getByRole("button", { name: "Save baseline", exact: true }).click();
  expect((await sent).postDataJSON().last_duty_end).toBe(`${year}-01-11T03:00:00.000Z`);
  await expect(dialog.getByLabel("Last duty ended", { exact: true })).toHaveValue(`${year}-01-10T22:00`);
});
