import { test, expect, type APIRequestContext } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { totpCode } from "./helpers/totp";

const backend = path.resolve("../backend");
const seed = (script: string, args: string[]) =>
  execFileSync(
    "uv",
    ["run", "python", path.resolve(`tests/fixtures/${script}`), ...args],
    {
      cwd: backend,
      env: { ...process.env, PYTHONPATH: backend },
      encoding: "utf8",
    },
  );

async function acceptInvitation(
  request: APIRequestContext,
  link: string,
  password: string,
) {
  const token = link.split("#token=")[1]!;
  const accepted = await request.post("/api/auth/accept-invitation", {
    data: { token, password, full_name: "Panel customer administrator" },
  });
  expect(accepted.ok(), await accepted.text()).toBeTruthy();
}

test("an operator signs in with a code, creates, suspends and reactivates a customer", async ({
  page,
  browser,
  request,
}) => {
  const operator = JSON.parse(seed("platform-seed.py", ["create"])) as {
    email: string;
    password: string;
    secret: string;
  };
  const tenants: number[] = [];
  try {
    await page.goto("/platform");
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await page.getByLabel("Email address").fill(operator.email);
    await page.getByLabel("Password").fill(operator.password);
    await page
      .getByLabel("Verification code (6 digits)")
      .fill(totpCode(operator.secret));
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(
      page.getByRole("heading", { name: "Customers", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "All customers" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: /Timetables|Δρομολόγια/ }),
    ).toHaveCount(0);

    const name = `Browser identity test ${crypto.randomUUID().replaceAll("-", "")}`;
    const adminEmail = `${crypto.randomUUID().replaceAll("-", "")}@example.org`;
    await page.getByRole("button", { name: "New customer" }).click();
    await page.getByLabel("Organization name").fill(name);
    await page.getByLabel("Region").fill("Crete");
    await page.getByLabel("First administrator email").fill(adminEmail);
    await page.getByLabel("Trial ends on").fill("2020-01-31");
    await page.getByRole("button", { name: "Create customer" }).click();
    const link = page.getByRole("textbox", { name: "Invitation link" });
    await expect(link).toHaveValue(/accept-invitation#token=/);
    const invitation = await link.inputValue();
    const row = page.getByRole("row").filter({ hasText: name });
    await expect(row.getByText("Trial", { exact: true })).toBeVisible();
    await expect(row.getByText("Trial ended")).toBeVisible();
    tenants.push(
      Number((await row.getAttribute("data-testid"))!.replace("customer-", "")),
    );
    await page.getByRole("button", { name: "Close" }).click();
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "All customers" }),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "Invitation link" }),
    ).toHaveCount(0);

    await expect(row.getByText("Never signed in")).toBeVisible();
    await expect(row.getByText("Solver failures")).toHaveCount(0);
    await page.getByRole("button", { name: `Health ${name}` }).click();
    const panel = page.getByRole("region", { name: `Health of ${name}` });
    await expect(panel.getByTestId("health-last")).toHaveText("Never");
    for (const key of ["drivers", "vehicles", "timetables", "published"])
      await expect(panel.getByTestId(`health-${key}`)).toHaveText("0");
    await expect(panel.getByTestId("health-uncovered")).toHaveText("—");

    const password = "PanelCustomerPassword123!";
    await acceptInvitation(request, invitation, password);
    await page.reload();
    const refreshed = page.getByRole("row").filter({ hasText: name });
    await expect(refreshed.getByText("Never signed in")).toHaveCount(0);
    await expect(refreshed.getByText("Healthy")).toBeVisible();

    seed("platform-seed.py", ["fail-mail", String(tenants[0])]);
    await page.reload();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: name })
        .getByText("Mail failures"),
    ).toBeVisible();
    await page.getByRole("button", { name: `Health ${name}` }).click();
    await expect(
      page
        .getByRole("region", { name: `Health of ${name}` })
        .getByTestId("health-mail"),
    ).toHaveText("1");

    await page.getByRole("button", { name: `Manage ${name}` }).click();
    await page
      .getByRole("form", { name: `Subscription ${name}` })
      .getByLabel("Status")
      .selectOption("suspended");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: name })
        .getByText("Suspended", { exact: true }),
    ).toBeVisible();

    const tenantContext = await browser.newContext();
    const tenantPage = await tenantContext.newPage();
    await tenantPage.goto("/");
    await tenantPage.locator('input[type="email"]').fill(adminEmail);
    await tenantPage.locator('input[type="password"]').fill(password);
    await tenantPage.getByRole("button", { name: /Σύνδεση/ }).click();
    await expect(tenantPage.locator(".auth-error")).toHaveText(
      "Η πρόσβαση του οργανισμού σας έχει ανασταλεί. Επικοινωνήστε με τον πάροχο της πλατφόρμας.",
    );
    await tenantPage.getByRole("button", { name: "EN", exact: true }).click();
    await tenantPage.getByRole("button", { name: /Sign in/ }).click();
    await expect(tenantPage.locator(".auth-error")).toHaveText(
      "Your organization's access is suspended. Contact the platform provider.",
    );

    await page.getByRole("button", { name: `Manage ${name}` }).click();
    await page
      .getByRole("form", { name: `Subscription ${name}` })
      .getByLabel("Status")
      .selectOption("active");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: name })
        .getByText("Active", { exact: true }),
    ).toBeVisible();

    await tenantPage.getByRole("button", { name: /Sign in/ }).click();
    await expect(
      tenantPage.getByRole("button", { name: "Sign out", exact: true }),
    ).toBeVisible();
    await tenantContext.close();

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page.getByLabel("Verification code (6 digits)")).toBeVisible();
  } finally {
    const cleaned = JSON.parse(
      seed("platform-seed.py", ["cleanup", operator.email]),
    ) as { tenants: number[] };
    for (const tenant of new Set([...tenants, ...cleaned.tenants]))
      seed("identity-seed.py", ["cleanup", String(tenant)]);
  }
});

test("a consented read-only support session is visible to the customer and ends when access is revoked", async ({
  page,
  browser,
  request,
}) => {
  const operator = JSON.parse(seed("platform-seed.py", ["create"])) as {
    email: string;
    password: string;
    secret: string;
  };
  const tenants: number[] = [];
  try {
    await page.goto("/platform");
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await page.getByLabel("Email address").fill(operator.email);
    await page.getByLabel("Password").fill(operator.password);
    await page
      .getByLabel("Verification code (6 digits)")
      .fill(totpCode(operator.secret));
    await page.getByRole("button", { name: "Sign in" }).click();
    const name = `Browser identity test ${crypto.randomUUID().replaceAll("-", "")}`;
    const adminEmail = `${crypto.randomUUID().replaceAll("-", "")}@example.org`;
    await page.getByRole("button", { name: "New customer" }).click();
    await page.getByLabel("Organization name").fill(name);
    await page.getByLabel("First administrator email").fill(adminEmail);
    await page.getByRole("button", { name: "Create customer" }).click();
    const invitation = await page
      .getByRole("textbox", { name: "Invitation link" })
      .inputValue();
    const row = page.getByRole("row").filter({ hasText: name });
    tenants.push(
      Number((await row.getAttribute("data-testid"))!.replace("customer-", "")),
    );
    await page.getByRole("button", { name: "Close" }).click();
    const password = "PanelCustomerPassword123!";
    await acceptInvitation(request, invitation, password);

    await page.getByRole("button", { name: `Health ${name}` }).click();
    const health = page.getByRole("region", { name: `Health of ${name}` });
    await expect(health.getByTestId("support-consent")).toHaveText(
      "The customer has not allowed support access.",
    );

    const tenantContext = await browser.newContext();
    const admin = await tenantContext.newPage();
    await admin.goto("/");
    await admin.getByRole("button", { name: "EN", exact: true }).click();
    await admin.locator('input[type="email"]').fill(adminEmail);
    await admin.locator('input[type="password"]').fill(password);
    await admin.getByRole("button", { name: /Sign in/ }).click();
    await admin.getByRole("button", { name: "Team", exact: true }).click();
    await admin.getByRole("button", { name: "Allow support access" }).click();
    await expect(admin.getByTestId("support-access-state")).toContainText(
      "Support access is allowed until",
    );

    await page.reload();
    await page.getByRole("button", { name: `Health ${name}` }).click();
    await health.getByLabel("Reason").fill("Customer reports a missing duty");
    await health.getByLabel("Ticket (optional)").fill("T-77");
    await health.getByRole("button", { name: "Start session" }).click();
    await expect(health.getByTestId("support-active")).toContainText(
      "Read-only session active until",
    );
    await expect(health.getByTestId("support-mail")).toContainText(
      "Administrator notice:",
    );

    await page.goto("/");
    await expect(page.getByTestId("support-banner")).toContainText(
      "Platform support is viewing this organization",
    );
    await page.getByRole("button", { name: "Drivers", exact: true }).click();
    await expect(page.getByRole("button", { name: "Add driver" })).toHaveCount(
      0,
    );
    await expect(
      page.getByRole("button", { name: "Sign out", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Team", exact: true }),
    ).toHaveCount(0);

    await admin.clock.install();
    let identityReads = 0;
    admin.on("request", (request) => {
      if (request.url().endsWith("/api/auth/me")) identityReads += 1;
    });
    await admin.reload();
    await expect(admin.getByTestId("support-banner")).toContainText(
      "Platform support is viewing this organization",
    );
    const readsBefore = identityReads;
    await admin.clock.fastForward(61 * 60_000);
    await expect(admin.getByTestId("support-banner")).toHaveCount(0);
    expect(identityReads).toBeGreaterThan(readsBefore);
    await admin.reload();
    await admin.getByRole("button", { name: "Team", exact: true }).click();
    const history = admin.getByRole("table", {
      name: "Support access history",
    });
    await expect(history.getByText("Support session started")).toBeVisible();
    await expect(
      history.getByText("Customer reports a missing duty · #T-77"),
    ).toBeVisible();
    await expect(history.getByText("Viewed").first()).toBeVisible();
    const views = history.locator("details").first();
    await expect(views).not.toHaveAttribute("open", "");
    await expect(views.getByText("GET /auth/me").first()).toBeHidden();
    await views.locator("summary").click();
    await expect(views.getByText("GET /auth/me").first()).toBeVisible();
    await expect(history.getByText("Platform support").first()).toBeVisible();

    await admin.getByRole("button", { name: "Revoke access" }).click();
    await expect(admin.getByTestId("support-access-state")).toHaveText(
      "Support access is off.",
    );
    await admin.reload();
    await expect(admin.getByTestId("support-banner")).toHaveCount(0);
    await tenantContext.close();

    await page.reload();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.getByTestId("support-banner")).toHaveCount(0);
    await page.goto("/platform");
    await expect(
      page.getByRole("heading", { name: "All customers" }),
    ).toBeVisible();
  } finally {
    const cleaned = JSON.parse(
      seed("platform-seed.py", ["cleanup", operator.email]),
    ) as { tenants: number[] };
    for (const tenant of new Set([...tenants, ...cleaned.tenants]))
      seed("identity-seed.py", ["cleanup", String(tenant)]);
  }
});
