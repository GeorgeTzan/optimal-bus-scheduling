import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect, signIn } from "./helpers/auth";

test("an administrator invites a driver from the driver record, revokes, re-invites, and the accepted sign-in shows as linked until unlinked", async ({ page, request, customer }) => {
  const backend = path.resolve("../backend"),
    script = path.resolve("tests/fixtures/identity-seed.py");
  const run = (args: string[]) => execFileSync("uv", ["run", "python", script, ...args], { cwd: backend, env: { ...process.env, PYTHONPATH: backend }, encoding: "utf8" });
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByRole("navigation").getByRole("button", { name: "Drivers", exact: true }).click();
  await page.getByPlaceholder("Search by name or reference…").fill("Dimos");
  await page.getByRole("button", { name: /Invite to sign in: Nikos Dimos/ }).click();  // visible on the row, no need to find it inside Edit
  const access = page.getByRole("region", { name: "Driver sign-in" });
  await expect(access).toContainText("cannot sign in yet");
  const email = `driver-${Date.now()}@example.org`;
  await access.getByLabel("Driver email").fill(email);
  await access.getByRole("button", { name: "Invite to sign in" }).click();
  await expect(access).toContainText("Invitation pending for");
  await expect(access).toContainText("No email has been sent because email delivery is not set up");
  await expect(access).not.toContainText("token=");
  await access.getByRole("button", { name: "Revoke invitation" }).click();
  await expect(access).toContainText("cannot sign in yet");
  await access.getByLabel("Driver email").fill(email);
  await access.getByRole("button", { name: "Invite to sign in" }).click();
  await expect(access).toContainText("Invitation pending for");
  const { token } = JSON.parse(run(["mail", String(customer.tenant_id), email])) as { token: string };
  const accepted = await request.post("/api/auth/accept-invitation", { data: { token, password: "DriverPortalPassword123!", full_name: "Nikos Dimos" } });
  expect(accepted.ok(), await accepted.text()).toBeTruthy();
  await page.reload();
  await page.getByRole("navigation").getByRole("button", { name: "Drivers", exact: true }).click();
  await page.getByPlaceholder("Search by name or reference…").fill("Dimos");
  await page.getByRole("button", { name: "Edit" }).first().click();
  await expect(page.getByRole("region", { name: "Driver sign-in" })).toContainText(email);
  await page.getByRole("button", { name: "Unlink sign-in" }).click();
  await page.getByRole("button", { name: "Confirm unlink" }).click();
  await expect(page.getByRole("region", { name: "Driver sign-in" })).toContainText("cannot sign in yet");
  await page.screenshot({ path: "test-results/driver-invite-record.png", fullPage: true });
});
