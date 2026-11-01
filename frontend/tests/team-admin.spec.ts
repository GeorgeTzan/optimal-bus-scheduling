import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect, signIn } from "./helpers/auth";

test("an administrator invites, resends, revokes, onboards, changes roles and deactivates people, and a dispatcher never sees the Team screen", async ({ page, browser, request, customer }) => {
  const backend = path.resolve("../backend"), script = path.resolve("tests/fixtures/identity-seed.py");
  const run = (args: string[]) => execFileSync("uv", ["run", "python", script, ...args], { cwd: backend, env: { ...process.env, PYTHONPATH: backend }, encoding: "utf8" });
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Team", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Team and access" })).toBeVisible();
  const own = page.getByRole("row").filter({ hasText: "(you)" });
  await expect(own).toHaveCount(1);
  await expect(own.getByRole("button")).toHaveCount(0);
  await expect(own.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByText("No pending invitations.")).toBeVisible();

  const email = `staff-${Date.now()}@example.org`;
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Send invitation" }).click();
  const pending = page.getByRole("row").filter({ hasText: email });
  await expect(pending).toContainText("Queued. No email has been sent because email delivery is not set up.");
  expect(await page.content()).not.toContain("token=");
  await page.getByRole("button", { name: `Resend to ${email}` }).click();
  const resentNotice = page.getByRole("status").filter({ hasText: "Queued. No email has been sent" });
  await expect(resentNotice).toBeVisible();
  await expect(resentNotice).not.toContainText("renewed"); await expect(resentNotice).not.toContainText("resent"); // nothing was sent, so the notice must not say so
  await expect(page.getByRole("row").filter({ hasText: email })).toHaveCount(1);
  await page.getByRole("button", { name: `Revoke for ${email}` }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("No pending invitations.")).toBeVisible();

  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("row").filter({ hasText: email })).toBeVisible();
  const { token } = JSON.parse(run(["mail", String(customer.tenant_id), email])) as { token: string };
  const accepted = await request.post("/api/auth/accept-invitation", { data: { token, password: "StaffPortalPassword123!", full_name: "Staff Person" } });
  expect(accepted.ok(), await accepted.text()).toBeTruthy();
  await page.reload();
  await page.getByRole("navigation").getByRole("button", { name: "Team", exact: true }).click();
  await expect(page.getByText("No pending invitations.")).toBeVisible();
  const member = page.getByRole("row").filter({ hasText: email });
  await expect(member).toContainText("Active");

  // A refused action keeps its message and the typed email on screen.
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.locator(".auth-error")).toContainText("already in your team");
  await page.waitForTimeout(1500);
  await expect(page.locator(".auth-error")).toContainText("already in your team");
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue(email);
  await page.getByLabel("Email", { exact: true }).fill("");

  // A dispatcher never sees the Team item or its screen.
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const staff = await context.newPage();
  try {
    await staff.goto("/?view=team");
    await staff.getByRole("button", { name: "EN", exact: true }).click();
    await staff.locator('input[type="email"]').fill(email);
    await staff.locator('input[type="password"]').fill("StaffPortalPassword123!");
    await staff.getByRole("button", { name: /Sign in/i }).click();
    await expect(staff.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
    await expect(staff.getByRole("navigation").getByRole("button", { name: "Team", exact: true })).toHaveCount(0);
    await expect(staff.getByRole("heading", { name: "Team and access" })).toHaveCount(0);

    // Role changes: a plain change applies at once, becoming Administrator asks first, and the member's session ends.
    await member.getByRole("combobox").selectOption("viewer");
    await expect(page.getByRole("status").filter({ hasText: "Role changed." })).toBeVisible();
    await member.getByRole("combobox").selectOption("admin");
    await expect(page.getByRole("dialog")).toContainText("will be able to manage everyone's access");
    await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Role changed." })).toBeVisible();
    await expect(member.getByRole("combobox")).toHaveValue("admin");
    await page.screenshot({ path: "test-results/team-members-en-light.png", fullPage: true });
    await member.getByRole("combobox").selectOption("dispatcher");
    await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
    await expect(member.getByRole("combobox")).toHaveValue("dispatcher");
    await staff.reload();
    await expect(staff.getByRole("button", { name: /Sign in/i })).toBeVisible(); // sessions ended by the role change

    await page.getByRole("button", { name: "Deactivate Staff Person" }).click();
    await expect(page.getByRole("dialog")).toContainText("Their sessions end now");
    await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
    await expect(member).toContainText("Deactivated");
    await page.getByRole("button", { name: "Reactivate Staff Person" }).click();
    await expect(member).toContainText("Active");
  } finally {
    await context.close();
  }

  // Greek, dark and phone captures.
  await page.getByRole("button", { name: "ΕΛ" }).click();
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.getByRole("heading", { name: "Ομάδα και πρόσβαση" })).toBeVisible();
  await page.screenshot({ path: "test-results/team-members-el-dark.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/team-members-phone.png", fullPage: true });
});
