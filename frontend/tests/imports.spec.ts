import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("guided spreadsheet review survives reload, corrects a cell and saves real records", async ({
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
    await page.getByLabel("Full name", { exact: true }).fill("Import operator");
    await page
      .getByLabel("New password", { exact: true })
      .fill("ImportOperatorPassword123!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Data imports", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Bring your records together",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Review file", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/import-choose.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: "test-results/import-choose-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page
      .getByRole("main")
      .getByRole("button", { name: "Drivers", exact: true })
      .click();
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download Excel template", exact: true })
      .click();
    expect((await download).suggestedFilename()).toContain("drivers");
    const file = execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        "import sys; from app.domain.imports.templates import generate_template; sys.stdout.buffer.write(generate_template('drivers','en',[{'code':'00017','last_name':'Dimos'}]))",
      ],
      { cwd: backend },
    );
    await page.getByLabel("Choose your file", { exact: true }).setInputFiles({
      name: "drivers.xlsx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: file,
    });
    await page
      .getByRole("button", { name: "Review file", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Review your records", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("drivers.xlsx", { exact: true })).toBeVisible();
    await page.screenshot({
      path: "test-results/import-review.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
    await page.screenshot({
      path: "test-results/import-review-mobile.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
    await expect(
      page.getByRole("heading", {
        name: "Ελέγξτε τα στοιχεία σας",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator(".import-row-issue").first()).toContainText(
      "Συμπληρώστε",
    );
    await page.screenshot({
      path: "test-results/import-review-greek-dark.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await page.getByRole("button", { name: "Toggle theme" }).click();
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Review your records", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Review row 2", exact: true })
      .click();
    await expect(page.getByLabel("First name", { exact: true })).toBeFocused();
    await page.getByLabel("First name", { exact: true }).fill("Nikos");
    await page
      .getByRole("button", { name: "Save correction", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Continue to summary", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Ready to save", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Save records", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Your records are saved",
        exact: true,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/import-saved.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "View drivers", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "Nikos Dimos" }),
    ).toContainText("00017");
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Data imports", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Your recent imports", exact: true }),
    ).toBeVisible();
    const corrected = execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        "import sys; from app.domain.imports.templates import generate_template; sys.stdout.buffer.write(generate_template('drivers','en',[{'code':'00017','first_name':'Nikolaos','last_name':'Dimos'}],file_format='csv'))",
      ],
      { cwd: backend },
    );
    await page.getByLabel("Choose your file", { exact: true }).setInputFiles({
      name: "updated.csv",
      mimeType: "text/csv",
      buffer: corrected,
    });
    await page
      .getByRole("button", { name: "Review file", exact: true })
      .click();
    await expect(
      page.locator(".import-counts > div").filter({ hasText: "Updates" }),
    ).toContainText("1");
    await page
      .getByRole("button", { name: "Review row 2", exact: true })
      .click();
    await expect(page.locator(".import-differences")).toContainText("Nikos");
    await expect(page.locator(".import-differences")).toContainText("Nikolaos");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Continue to summary", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Save records", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Your records are saved",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "All imports", exact: true })
      .click();
    await page.getByLabel("Choose your file", { exact: true }).setInputFiles({
      name: "retry.csv",
      mimeType: "text/csv",
      buffer: corrected,
    });
    await page
      .getByRole("button", { name: "Review file", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Your records are saved",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "View drivers", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "Nikolaos Dimos" }),
    ).toHaveCount(1);
  } finally {
    run(["cleanup", String(invite.tenant_id)]);
  }
});

test("a slow upload can finish without replacing the operator's new destination", async ({
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
  let release = () => {};
  try {
    await page.goto("/accept-invitation#token=" + invite.token);
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await page
      .getByLabel("Full name", { exact: true })
      .fill("Navigation operator");
    await page
      .getByLabel("New password", { exact: true })
      .fill("NavigationOperatorPassword123!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Data imports", exact: true })
      .click();
    await page
      .getByLabel("Choose your file", { exact: true })
      .setInputFiles({
        name: "drivers.csv",
        mimeType: "text/csv",
        buffer: Buffer.from("Code,First name,Last name\nDELAY,Slow,Response\n"),
      });
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let received = () => {};
    const staged = new Promise<void>((resolve) => {
      received = resolve;
    });
    await page.route("**/api/v1/imports", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      received();
      await gate;
      await route.fulfill({ response });
    });
    await page
      .getByRole("button", { name: "Review file", exact: true })
      .click();
    await staged;
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Drivers", exact: true })
      .click();
    const completed = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/imports") &&
        response.request().method() === "POST",
    );
    release();
    await completed;
    await page.waitForTimeout(150);
    await expect(
      page.getByRole("heading", { name: "Drivers", exact: true }),
    ).toBeVisible();
    expect(new URL(page.url()).searchParams.get("view")).not.toBe("imports");
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Data imports", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Your recent imports", exact: true }),
    ).toBeVisible();
    await page
      .locator(".import-history")
      .getByRole("button")
      .filter({ hasText: "drivers.csv" })
      .click();
    await expect(
      page.getByRole("button", { name: "Review row 2", exact: true }),
    ).toContainText("Slow Response");
  } finally {
    release();
    await page.unrouteAll({ behavior: "wait" });
    run(["cleanup", String(invite.tenant_id)]);
  }
});
