import { giveWorkingTime } from "./helpers/working-time";
import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("guided timetable and service-day setup persists real clocks, crew and travel inputs", async ({
  page,
}) => {
  page.setDefaultTimeout(10000);
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
      .fill("Timetable operator");
    await page
      .getByLabel("New password", { exact: true })
      .fill("TimetableOperatorPassword123!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Add your first driver", exact: true })
      .click();
    await page.getByRole("button", { name: "Add driver", exact: true }).click();
    await page.getByLabel("First name", { exact: true }).fill("Νίκος");
    await page.getByLabel("Last name", { exact: true }).fill("Δήμου");
    await page
      .getByRole("button", { name: "Save driver", exact: true })
      .click();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Fleet", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Add vehicle", exact: true })
      .click();
    await page.getByLabel("Registration", { exact: true }).fill("KRA-1234");
    await page.getByLabel("Vehicle type", { exact: true }).fill("02");
    await page
      .getByRole("button", { name: "Save vehicle", exact: true })
      .click();
    await expect(
      page
        .getByRole("navigation")
        .getByRole("button", { name: "Timetables", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Timetables", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Add timetable", exact: true })
      .click();
    await page.getByLabel("Trip reference", { exact: true }).fill("T001");
    for (const [field, name] of [
      ["Origin station", "Αφετηρία"],
      ["Destination station", "Προορισμός"],
    ]) {
      await page.getByLabel(field!, { exact: true }).fill(name!);
      await expect(page.getByLabel(field!, { exact: true })).toHaveValue(name!);
      await page
        .getByRole("button", {
          name:
            field === "Origin station"
              ? "Add origin station"
              : "Add destination station",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", { name: "Save station", exact: true })
        .click();
      await expect(
        page.getByRole("dialog", { name: "Add station", exact: true }),
      ).toBeHidden();
    }
    await page.getByLabel("Departure time", { exact: true }).fill("08:00");
    await page.getByLabel("Arrival time", { exact: true }).fill("09:00");
    await page.screenshot({
      path: "test-results/timetable-route-step.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.getByLabel("Monday", { exact: true }).check();
    await page.getByLabel("Valid from", { exact: true }).fill("2026-01-01");
    await page.getByLabel("Valid until", { exact: true }).fill("2028-12-31");
    await page.getByRole("checkbox", { name: /02/ }).check();
    await page.screenshot({
      path: "test-results/timetable-calendar-step.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Save timetable", exact: true })
      .click();
    await expect(
      page.getByRole("row").filter({ hasText: "T001" }),
    ).toBeVisible();
    await expect(
      page
        .getByRole("row")
        .filter({ hasText: "T001" })
        .getByRole("button", { name: "Change one date", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/timetable-roster.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", { name: "Edit", exact: true }),
    ).toBeInViewport({ ratio: 0.9 });
    await page.screenshot({
      path: "test-results/timetable-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Service day", exact: true })
      .click();
    await page.getByLabel("Service date", { exact: true }).fill("2026-06-01");
    await giveWorkingTime(page);
    await page
      .getByRole("button", { name: "Add pairing", exact: true })
      .click();
    await page
      .getByLabel("Driver", { exact: true })
      .fill("Νίκος Δήμου · D00001");
    await page.getByLabel("Vehicle", { exact: true }).fill("KRA-1234 · V00001");
    await page
      .getByLabel("Starting base", { exact: true })
      .fill("Αφετηρία · S00001");
    await page
      .getByRole("button", { name: "Confirm pairing", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Add pairing", exact: true }),
    ).toBeHidden();
    await page.getByRole("button",{name:"Show confirmed crews (1)",exact:true}).click();
    await expect(page.getByText("Νίκος Δήμου", { exact: true })).toBeVisible();
    await page
      .getByLabel("Minutes: Αφετηρία → Προορισμός", { exact: true })
      .fill("30");
    await page
      .getByRole("button", { name: "Save travel times", exact: true })
      .click();
    await expect(
      page.getByLabel("Minutes: Αφετηρία → Προορισμός", { exact: true }),
    ).toHaveValue("30");
    await expect(
      page.getByText("Saved: 30 minutes", { exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Minutes: Προορισμός → Αφετηρία", { exact: true })
      .fill("35");
    await page
      .getByRole("button", { name: "Save travel times", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Prepare service day", exact: true })
      .click();
    await expect(page.getByTestId("prepared-trip-list")).toContainText("T001");
    await expect(page.getByTestId("prepared-trip-list")).toContainText("08:00");
    await page.reload();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Service day", exact: true })
      .click();
    await expect(page.getByLabel("Service date", { exact: true })).toHaveValue(
      "2026-06-01",
    );
    await expect(page.getByTestId("prepared-trip-list")).toContainText("T001");
    await page.screenshot({
      path: "test-results/service-day-prepared.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    await expect(
      page.getByRole("button", { name: "Add pairing", exact: true }),
    ).toBeInViewport();
    await page.screenshot({
      path: "test-results/service-day-mobile.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "ΕΛ", exact: true }).click();
    await page
      .getByRole("button", { name: "Toggle theme", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Έλεγχος & αποθήκευση ημέρας",
        exact: true,
      }),
    ).toBeVisible();
    await page.screenshot({
      path: "test-results/service-day-greek-dark.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.getByRole("button", { name: "EN", exact: true }).click();
    await page
      .getByRole("button", { name: "Toggle theme", exact: true })
      .click();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Timetables", exact: true })
      .click();
    await page
      .getByRole("row")
      .filter({ hasText: "T001" })
      .getByRole("button", { name: "Edit", exact: true })
      .click();
    await page.getByLabel("Departure time", { exact: true }).fill("03:10");
    await page.getByLabel("Arrival time", { exact: true }).fill("03:40");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await page.getByLabel("Sunday", { exact: true }).check();
    await page
      .getByRole("button", { name: "Save timetable", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Edit timetable", exact: true }),
    ).toBeHidden();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Service day", exact: true })
      .click();
    await page.getByLabel("Service date", { exact: true }).fill("2026-10-25");
    for (const occurrence of ["0", "1"]) {
      await page
        .getByRole("button", { name: "Review clock time", exact: true })
        .first()
        .click();
      await page
        .getByLabel("Which occurrence?", { exact: true })
        .selectOption(occurrence);
      await page
        .getByRole("button", { name: "Save date exception", exact: true })
        .click();
      await expect(
        page.getByRole("dialog", {
          name: "Review local clock time",
          exact: true,
        }),
      ).toBeHidden();
    }
    await expect(
      page.getByRole("button", { name: "Review clock time", exact: true }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Add pairing", exact: true })
      .click();
    await page
      .getByLabel("Driver", { exact: true })
      .fill("Νίκος Δήμου · D00001");
    await page.getByLabel("Vehicle", { exact: true }).fill("KRA-1234 · V00001");
    await page
      .getByLabel("Starting base", { exact: true })
      .fill("Αφετηρία · S00001");
    await page
      .getByRole("button", { name: "Confirm pairing", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Add pairing", exact: true }),
    ).toBeHidden();
    await page
      .getByRole("button", { name: "Prepare service day", exact: true })
      .click();
    await expect(page.getByTestId("prepared-trip-list")).toContainText(
      "90 min",
    );
    await page.screenshot({
      path: "test-results/service-day-dst-reviewed.png",
      fullPage: true,
    });
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Timetables", exact: true })
      .click();
    await page
      .getByRole("row")
      .filter({ hasText: "T001" })
      .getByRole("button", { name: "Change one date", exact: true })
      .click();
    await page.getByLabel("Exception date", { exact: true }).fill("2026-10-25");
    await page
      .getByLabel("What changes?", { exact: true })
      .selectOption("cancel");
    await page
      .getByRole("button", { name: "Save date exception", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Change one date", exact: true }),
    ).toBeHidden();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Service day", exact: true })
      .click();
    await expect(
      page.getByText(
        "No services run on this date. Choose another day or update your timetable.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.getByTestId("prepared-trip-list")).toHaveCount(0);
  } finally {
    run(["cleanup", String(invite.tenant_id)]);
  }
});
