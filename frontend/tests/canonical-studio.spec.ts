import { giveWorkingTime } from "./helpers/working-time";
import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("an operator imports real records, confirms a day, creates and publishes a CV draft", async ({
  page,
}) => {
  test.setTimeout(120000);
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
      .fill("Canonical operator");
    await page
      .getByLabel("New password", { exact: true })
      .fill("CanonicalOperatorPassword123!");
    await page
      .getByRole("button", { name: "Create account", exact: true })
      .click();
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Data imports", exact: true })
      .click();
    const content = execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        `
import sys
from app.domain.imports.templates import generate_template
records={
 'stations':[{'code':'001','name_el':'Κεντρικός','name_en':'Central depot','is_depot':True},{'code':'002','name_el':'Λιμάνι','name_en':'Harbour'}],
 'drivers':[{'code':'00007','first_name':'Nikos','last_name':'Dimos','home_station':'001'}],
 'vehicles':[{'code':'BUS01','registration_plate':'KRA-4321','bus_type':'02','home_station':'001'}],
 'timetable':[{'trip_code':'KT001','origin':'001','destination':'002','departure_time':'08:00','arrival_time':'09:00','arrival_day_offset':0,'operating_weekdays':[0,1,2,3,4,5,6],'valid_from':'2026-01-01','valid_until':'2028-12-31','allowed_bus_types':['02']},{'trip_code':'KT002','origin':'002','destination':'001','departure_time':'10:00','arrival_time':'11:00','arrival_day_offset':0,'operating_weekdays':[0,1,2,3,4,5,6],'valid_from':'2026-01-01','valid_until':'2028-12-31','allowed_bus_types':['02']}],
 'pairings':[{'service_date':'2026-06-01','driver_ref':'00007','vehicle_ref':'BUS01','home_station':'001'}],
 'transfers':[{'origin':'001','destination':'002','minutes':30},{'origin':'002','destination':'001','minutes':35}]}
sys.stdout.buffer.write(generate_template('all','en',records))`,
      ],
      { cwd: backend },
    );
    await page.getByLabel("Choose your file", { exact: true }).setInputFiles({
      name: "operations.xlsx",
      mimeType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      buffer: content,
    });
    await page
      .getByRole("button", { name: "Review file", exact: true })
      .click();
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
      .getByRole("navigation")
      .getByRole("button", { name: "Timetables", exact: true })
      .click();
    await page
      .getByText("Keep linked trips on one vehicle", { exact: true })
      .click();
    await page.getByLabel("Incoming trip", { exact: true }).fill("KT001");
    const choices = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/timetables?") &&
        response.url().includes("q=KT001"),
    );
    await page.getByLabel("Following trip", { exact: true }).fill("KT001");
    await choices;
    await expect(
      page.getByRole("button", { name: "Link trips", exact: true }),
    ).toBeDisabled();
    await page.getByLabel("Following trip", { exact: true }).fill("KT002");
    await expect(
      page.getByLabel("Following trip", { exact: true }),
    ).toHaveValue("KT002");
    await page.getByRole("button", { name: "Link trips", exact: true }).click();
    await expect(
      page.getByRole("list", { name: "Saved trip connections" }),
    ).toContainText("KT001 → KT002");
    await giveWorkingTime(page);
    await page
      .getByRole("navigation")
      .getByRole("button", { name: "Service day", exact: true })
      .click();
    await page.getByLabel("Service date", { exact: true }).fill("2026-06-01");
    await page.getByRole("button", { name: "Confirm", exact: true }).click();
    await page
      .getByRole("button", { name: "Prepare service day", exact: true })
      .click();
    await expect(page.getByTestId("prepared-trip-list")).toContainText("KT001");
    await expect(
      page.getByRole("button", { name: "Open Scheduling Studio", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Open Scheduling Studio", exact: true })
      .click();
    await expect(page.getByTestId("schedule-timeline")).toContainText(
      "Central depot",
    );
    await expect(page.getByTestId("schedule-timeline")).toContainText(
      "Harbour",
    );
    await expect(page.getByTestId("schedule-timeline")).toContainText(
      "Nikos Dimos",
    );
    await page
      .getByRole("button", { name: "Inspect KT001", exact: true })
      .click();
    await expect(
      page.getByRole("complementary", { name: "Trip Details" }),
    ).toContainText("08:00");
    await page.getByText("Planning options", { exact: true }).click();
    await page.getByLabel("CV iterations").selectOption("1");
    await page.getByText("Planning options", { exact: true }).click();
    const queued = page.waitForResponse(
      (response) =>
        response.url().includes("/api/optimization/runs") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Generate draft schedule", exact: true })
      .click();
    const queuedResponse = await queued;
    expect(queuedResponse.status()).toBe(202);
    const runId = ((await queuedResponse.json()) as { run_id: string }).run_id;
    execFileSync(
      "uv",
      [
        "run",
        "python",
        "-m",
        "app.domain.jobs.worker",
        "--tenant-id",
        String(invite.tenant_id),
        "--once",
      ],
      {
        cwd: backend,
        env: { ...process.env, PYTHONPATH: backend },
        timeout: 30000,
      },
    );
    await page.getByRole("button", { name: /Draft options/ }).click();
    await page
      .getByRole("button", { name: "Apply candidate", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Request approval", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Approve schedule", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Publish schedule", exact: true })
      .click();
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(`**/api/optimization/runs/${runId}`, async (route) => {
      const response = await route.fetch();
      await gate;
      await route.fulfill({ response });
    });
    try {
      await page.reload();
      await expect(page.getByText("Published", { exact: true })).toBeVisible();
      await expect(page.locator("progress")).toHaveCount(0);
    } finally {
      release();
      await page.unrouteAll({ behavior: "wait" });
    }
    await expect(
      page.locator(".trip-table").getByRole("row").filter({ hasText: "KT001" }),
    ).toContainText("KRA-4321");
    await page
      .getByRole("button", { name: "Inspect KT001", exact: true })
      .click();
    await expect(page.getByTestId("schedule-timeline")).toContainText(
      "Harbour",
    );
    await page.screenshot({
      path: "test-results/studio-canonical-published.png",
      fullPage: true,
    });
    const ownRevision = await (
      await page.request.get(
        "/api/v1/scheduling/revisions/active?service_date=2026-06-01",
      )
    ).json();
    const secondInvite = JSON.parse(run(["create"])) as {
      tenant_id: number;
      token: string;
    };
    const other = await page
      .context()
      .browser()!
      .newContext({ baseURL: "http://127.0.0.1:3000" });
    try {
      const accepted = await other.request.post("/api/auth/accept-invitation", {
        data: {
          token: secondInvite.token,
          password: "SecondCanonicalPassword123!",
          full_name: "Second operator",
        },
      });
      expect(accepted.ok()).toBeTruthy();
      const otherPage = await other.newPage();
      await otherPage.goto("/");
      await otherPage.getByRole("button", { name: "EN", exact: true }).click();
      await expect(
        otherPage.getByRole("heading", { name: /Let’s get ready/ }),
      ).toBeVisible();
      expect(
        (
          await other.request.get(
            `/api/v1/scheduling/revisions/${ownRevision.revision_id}`,
          )
        ).status(),
      ).toBe(404);
      expect(
        (await (await other.request.get("/api/v1/drivers")).json()).total,
      ).toBe(0);
      await expect(otherPage.getByTestId("revision-version")).toHaveCount(0);
    } finally {
      await other.close();
      run(["cleanup", String(secondInvite.tenant_id)]);
    }
  } finally {
    run(["cleanup", String(invite.tenant_id)]);
  }
});
