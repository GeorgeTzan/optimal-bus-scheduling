import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";

const day = "2026-10-31"; // the disposable customer's seeded service day
const addDays = (iso: string, count: number) => new Date(Date.parse(`${iso}T12:00:00Z`) + count * 86_400_000).toISOString().slice(0, 10);

async function csrf(page: Page) {
  return { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" };
}

test("a linked driver sees only own duties on a phone, acknowledges them, requests and cancels leave, and loses access when unlinked", async ({ page, browser, customer }) => {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Athens" }).format(new Date());
  test.skip(day < addDays(today, -1) || day > addDays(today, 14), "the seeded service day must fall inside the driver's duty window (yesterday to 14 days ahead)");
  const backend = path.resolve("../backend"), script = path.resolve("tests/fixtures/identity-seed.py");
  const run = (args: string[]) => execFileSync("uv", ["run", "python", script, ...args], { cwd: backend, env: { ...process.env, PYTHONPATH: backend }, encoding: "utf8" });
  // Office: publish the day, set an approver, invite the driver from the record.
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
  let revision = await (await page.request.get("/api/v1/scheduling/revisions/active?service_date=" + day)).json();
  for (const action of ["request-approval", "approve", "publish"]) {
    const response = await page.request.post(`/api/v1/scheduling/revisions/${revision.revision_id}/${action}`, { headers: await csrf(page), data: { version: revision.version } });
    expect(response.ok(), await response.text()).toBeTruthy();
    revision = await response.json();
  }
  const me = ((await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[])[0]!.id;
  expect((await page.request.post("/api/v1/office/approval-routes", { headers: await csrf(page), data: { request_id: crypto.randomUUID(), membership_id: me } })).ok()).toBeTruthy();
  const drivers = (await (await page.request.get("/api/v1/drivers?page_size=100")).json()).items as { id: number; first_name: string }[];
  const nikos = drivers.find((driver) => driver.first_name === "Nikos")!;
  const email = `driver-${Date.now()}@example.org`;
  const invited = await page.request.post("/api/v1/identity/invitations", { headers: await csrf(page), data: { email, role: "driver", driver_id: nikos.id, request_id: crypto.randomUUID() } });
  expect(invited.status(), await invited.text()).toBe(202);
  const { token } = JSON.parse(run(["mail", String(customer.tenant_id), email])) as { token: string };

  // Driver, on a phone: accept the invitation and land in the driver area.
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const phone = await context.newPage();
  try {
    await phone.goto("/accept-invitation#token=" + token);
    await phone.getByRole("button", { name: "EN", exact: true }).click();
    await phone.getByLabel("Full name", { exact: true }).fill("Nikos Dimos");
    await phone.getByLabel("New password", { exact: true }).fill("DriverPortalPassword123!");
    await phone.getByRole("button", { name: "Create account", exact: true }).click();
    await expect(phone).toHaveURL(/\/driver$/);
    await expect(phone.getByRole("heading", { name: "My duties" })).toBeVisible();
    const cards = phone.locator(".driver-duty");
    await expect(cards).toHaveCount(1);
    await expect(phone.getByRole("main")).not.toContainText(/Eleni|Papadopoulou/);
    await expect(phone.getByRole("navigation", { name: "Sections" })).toBeVisible();
    await expect(phone.getByRole("button", { name: "Drivers", exact: true })).toHaveCount(0);
    expect(await phone.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await phone.screenshot({ path: "test-results/driver-duties-en-light.png", fullPage: true });

    await cards.first().getByRole("button", { name: "Acknowledge" }).click();
    await expect(phone.getByRole("status").filter({ hasText: "Acknowledgment recorded" })).toBeVisible();
    await expect(cards.first()).toContainText("Acknowledged");
    await phone.reload();
    await expect(phone.locator(".driver-duty").first()).toContainText("Acknowledged");

    // Leave: request, offline refusal that saves nothing, decision by the office, cancellation of a waiting request.
    await phone.getByRole("button", { name: "Leave", exact: true }).click();
    await phone.getByLabel("From").fill(addDays(today, 3));
    await phone.getByLabel(/Until/).fill(addDays(today, 4));
    await context.setOffline(true);
    await phone.getByRole("button", { name: "Request leave" }).click();
    await expect(phone.locator(".auth-error")).toContainText("No connection. Nothing was saved.");
    await expect(phone.getByText("You have no requests in this period.")).toBeVisible();
    await context.setOffline(false);
    await phone.getByRole("button", { name: "Request leave" }).click();
    await expect(phone.getByRole("status").filter({ hasText: "Request sent" })).toBeVisible();
    await expect(phone.locator(".driver-leave-list li")).toHaveCount(1);
    await expect(phone.locator(".driver-leave-list")).toContainText("Waiting");
    const office = (await (await page.request.get(`/api/v1/office/leave-requests?date_from=${addDays(today, 0)}&date_to=${addDays(today, 10)}`)).json()).items as { id: number; version: number }[];
    const decided = await page.request.post(`/api/v1/office/leave-requests/${office[0]!.id}/decision`, { headers: await csrf(page), data: { request_id: crypto.randomUUID(), expected_version: office[0]!.version, decision: "approved", note: "Enjoy" } });
    expect(decided.ok(), await decided.text()).toBeTruthy();
    await phone.reload();
    await phone.getByRole("button", { name: "Leave", exact: true }).click();
    await expect(phone.locator(".driver-leave-list")).toContainText("Approved");
    await expect(phone.locator(".driver-leave-list")).toContainText("Enjoy");
    await expect(phone.getByRole("button", { name: "Cancel request" })).toHaveCount(0);
    await phone.getByLabel("From").fill(addDays(today, 8));
    await phone.getByLabel(/Until/).fill(addDays(today, 8));
    await phone.getByRole("button", { name: "Request leave" }).click();
    await expect(phone.locator(".driver-leave-list li")).toHaveCount(2);
    await phone.getByRole("button", { name: "Cancel request" }).click();
    await expect(phone.locator(".driver-leave-list")).toContainText("Cancelled");
    await phone.screenshot({ path: "test-results/driver-leave-en-light.png", fullPage: true });

    // Greek and dark, same screens.
    await phone.getByRole("button", { name: "ΕΛ" }).click();
    await phone.getByRole("button", { name: "Αλλαγή θέματος" }).click();
    await expect(phone.getByRole("heading", { name: "Άδειες" })).toBeVisible();
    await phone.screenshot({ path: "test-results/driver-leave-el-dark.png", fullPage: true });
    await phone.getByRole("button", { name: "Οι υπηρεσίες μου" }).click();
    await expect(phone.locator(".driver-duty").first()).toContainText("Επιβεβαιώθηκε");
    await phone.screenshot({ path: "test-results/driver-duties-el-dark.png", fullPage: true });

    // An administrator is never shown the driver area; an unlinked driver loses access at once.
    await page.goto("/driver");
    await expect(page).toHaveURL(/\/$/);
    const unlinked = await page.request.post(`/api/v1/identity/drivers/${nikos.id}/unlink`, { headers: await csrf(page), data: { request_id: crypto.randomUUID() } });
    expect(unlinked.ok(), await unlinked.text()).toBeTruthy();
    await phone.reload();
    await expect(phone.getByRole("button", { name: /Sign in|Σύνδεση/ })).toBeVisible();
  } finally {
    await context.close();
  }
});

test("signing out and in as another driver on the same phone never shows the previous person's error or name", async ({ page, browser, customer }) => {
  const backend = path.resolve("../backend"), script = path.resolve("tests/fixtures/identity-seed.py");
  const run = (args: string[]) => execFileSync("uv", ["run", "python", script, ...args], { cwd: backend, env: { ...process.env, PYTHONPATH: backend }, encoding: "utf8" });
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
  const drivers = (await (await page.request.get("/api/v1/drivers?page_size=100")).json()).items as { id: number; first_name: string }[];
  const linkedEmail = `linked-${Date.now()}@example.org`;
  const invited = await page.request.post("/api/v1/identity/invitations", { headers: await csrf(page), data: { email: linkedEmail, role: "driver", driver_id: drivers.find((d) => d.first_name === "Nikos")!.id, request_id: crypto.randomUUID() } });
  expect(invited.status(), await invited.text()).toBe(202);
  const linkedToken = (JSON.parse(run(["mail", String(customer.tenant_id), linkedEmail])) as { token: string }).token;
  const unlinkedToken = (JSON.parse(run(["invite", String(customer.tenant_id), "driver"])) as { token: string }).token;
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const phone = await context.newPage();
  try {
    // B is accepted first through the API so the same phone can sign in as B later.
    const accepted = await phone.request.post("/api/auth/accept-invitation", { data: { token: linkedToken, password: "DriverPortalPassword123!", full_name: "Linked Driver" } });
    expect(accepted.ok(), await accepted.text()).toBeTruthy();
    await phone.request.post("/api/auth/logout", { headers: { "X-CSRF-Token": (await context.cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" } });
    await phone.goto("/accept-invitation#token=" + unlinkedToken);
    await phone.getByRole("button", { name: "EN", exact: true }).click();
    await phone.getByLabel("Full name", { exact: true }).fill("Unlinked Driver");
    await phone.getByLabel("New password", { exact: true }).fill("DriverPortalPassword123!");
    await phone.getByRole("button", { name: "Create account", exact: true }).click();
    await expect(phone.getByRole("alert").filter({ hasText: "not linked to a driver record yet" })).toBeVisible();
    await phone.getByRole("button", { name: "Sign out" }).click();  // no reload: the same mounted page must not keep the previous person's state
    await phone.locator('input[type="email"]').fill(linkedEmail);
    await phone.locator('input[type="password"]').fill("DriverPortalPassword123!");
    await phone.getByRole("button", { name: /Sign in/i }).click();
    await expect(phone.getByRole("heading", { name: "My duties" })).toBeVisible();
    await expect(phone.getByText("not linked to a driver record yet")).toHaveCount(0);
    await expect(phone.getByText("Unlinked Driver")).toHaveCount(0);
    await expect(phone.getByText("Nikos Dimos")).toBeVisible();
  } finally {
    await context.close();
  }
});
