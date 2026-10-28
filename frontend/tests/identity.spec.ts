import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect } from "@playwright/test";

test("sign-in starts blank and uses private revocable cookies through reload and logout", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.locator('input[type="email"]')).toHaveValue("");
  await expect(page.locator('input[type="password"]')).toHaveValue("");
  await page.getByLabel("Email address", { exact: true }).fill("admin@ktel.gr");
  await page.getByLabel("Password", { exact: true }).fill("admin123");
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/auth/login") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  const { access_token } = await (await submitted).json();
  await expect(
    page.getByRole("navigation").getByRole("button", {name: "Scheduling Studio", exact: true}),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("ktel_token")),
  ).toBeNull();
  expect(
    await page.evaluate(() => localStorage.getItem("ktel_user")),
  ).toBeNull();
  const cookies = await page.context().cookies();
  expect(cookies.find((c) => c.name === "ktel_session")?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "ktel_session=",
  );
  await page.reload();
  await expect(
    page.getByRole("navigation").getByRole("button", {name: "Scheduling Studio", exact: true}),
  ).toBeVisible();
  const logout = page.waitForResponse((r) =>
    r.url().endsWith("/api/auth/logout"),
  );
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  expect((await logout).status()).toBe(204);
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  const expired = await request.get("/api/auth/me", {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  expect(expired.status()).toBe(401);
});

test("password recovery gives a clear next step and invalid invitation is actionable", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await page
    .getByLabel("Email address", { exact: true })
    .fill("unknown-account@example.org");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("Check your email");
  await page.goto("/accept-invitation#token=invalid");
  await expect(
    page.getByRole("alert").filter({ hasText: "This link" }),
  ).toContainText("Ask your administrator");
  await expect(
    page.getByRole("button", { name: "Create account" }),
  ).toHaveCount(0);
});

test("a real organization invitation creates its first administrator without demo data", async ({
  page,
}) => {
  const backend = path.resolve("../backend");
  const script = path.resolve("tests/fixtures/identity-seed.py");
  const run = (args: string[]) =>
    execFileSync("uv", ["run", "python", script, ...args], {
      cwd: backend,
      env: { ...process.env, PYTHONPATH: backend },
      encoding: "utf8",
    });
  const invite = JSON.parse(run(["create"])) as {
    tenant_id: number;
    token: string;
    email: string;
  };
  try {
    await page.goto("/accept-invitation#token=" + invite.token);
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await expect(page.getByText(invite.email, { exact: true })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await page
      .getByLabel("Full name", { exact: true })
      .fill("New organization administrator");
    await page
      .getByLabel("New password", { exact: true })
      .fill("BrowserIdentityPassword123!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Sign out", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("revision-version")).toHaveCount(0);
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Sign out", exact: true }),
    ).toBeVisible();
    const profile = await page.request.get("/api/auth/me");
    const user = await profile.json();
    expect(user.ktel_id).toBe(invite.tenant_id);
    expect(user.role).toBe("admin");
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await page.goto("/accept-invitation#token=" + invite.token);
    await expect(
      page.getByRole("alert").filter({ hasText: "This link" }),
    ).toContainText("already used");
  } finally {
    run(["cleanup", String(invite.tenant_id)]);
  }
});
