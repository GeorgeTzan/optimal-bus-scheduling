import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("a new operator adds drivers and vehicles through guided real forms and keeps them after reload", async ({
  page,
}) => {
  const backend = path.resolve("../backend"),
    script = path.resolve("tests/fixtures/identity-seed.py");
  const run = (args: string[]) =>
    execFileSync("uv", ["run", "python", script, ...args], {
      cwd: backend,
      env: { ...process.env, PYTHONPATH: backend },
      encoding: "utf8",
    });
  const invite = JSON.parse(run(["create"])) as {
    tenant_id: number;
    token: string;
  };
  try {
    await page.goto("/accept-invitation#token=" + invite.token);
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await page
      .getByLabel("Full name", { exact: true })
      .fill("Resource operator");
    await page
      .getByLabel("New password", { exact: true })
      .fill("ResourceOperatorPassword123!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Add your first driver", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/setup-welcome.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Add your first driver", exact: true })
      .click();
    await page.getByRole("button", { name: "Add driver", exact: true }).click();
    await page.getByLabel("First name", { exact: true }).fill("Nikos");
    await page.getByLabel("Last name", { exact: true }).fill("Dimos");
    await page.screenshot({
      path: "test-results/driver-entry.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Save driver", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "Nikos Dimos" }),
    ).toBeVisible();
    await page.reload();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Drivers", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "Nikos Dimos" }),
    ).toBeVisible();
    await page
      .getByRole("row")
      .filter({ hasText: "Nikos Dimos" })
      .getByRole("button", { name: "Edit" })
      .click();
    await page.getByLabel("First name", { exact: true }).fill("Nikolaos");
    await page
      .getByRole("button", { name: "Save driver", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "Nikolaos Dimos" }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/driver-roster.png",
      fullPage: true,
    });
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Fleet", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Add vehicle", exact: true })
      .click();
    await page.getByLabel("Registration", { exact: true }).fill("KRA-1234");
    await page.getByLabel("Vehicle type", { exact: true }).fill("01");
    await page
      .getByRole("button", { name: "Save vehicle", exact: true })
      .click();
    const row = page.getByRole("row").filter({ hasText: "KRA-1234" });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Not recorded");
    await page.screenshot({
      path: "test-results/vehicle-roster.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Στόλος", exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", { name: "Επεξεργασία", exact: true }),
    ).toBeInViewport();
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: "test-results/resources-mobile.png",
      fullPage: true,
    });
  } finally {
    run(["cleanup", String(invite.tenant_id)]);
  }
});
