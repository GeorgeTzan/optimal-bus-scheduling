import { signIn, test, expect } from "./helpers/auth";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

const day = "2026-10-31";

async function csrf(page: Page) {
  return {
    "X-CSRF-Token":
      (await page.context().cookies()).find(
        (cookie) => cookie.name === "ktel_csrf",
      )?.value ?? "",
  };
}

async function publishWithGap(page: Page) {
  await page.goto("/?service_date=" + day);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const headers = await csrf(page);
  const post = async (url: string, data: object) => {
    const response = await page.request.post(url, { headers, data });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  };
  let revision = await (
    await page.request.get(
      "/api/v1/scheduling/revisions/active?service_date=" + day,
    )
  ).json();
  const trip = revision.source_trips.find(
    (item: { trip_code: string }) => item.trip_code === "333002",
  );
  revision = await post(
    `/api/v1/scheduling/revisions/${revision.revision_id}/patches`,
    {
      version: revision.version,
      patches: [{ trip_id: trip.id, new_resource_id: "UNASSIGNED" }],
    },
  );
  for (const action of ["request-approval", "approve", "publish"])
    revision = await post(
      `/api/v1/scheduling/revisions/${revision.revision_id}/${action}`,
      {
        version: revision.version,
        ...(action === "publish" ? { uncovered_reason: "no_driver" } : {}),
      },
    );
}

async function joinAs(page: Page, tenantId: number, role: string) {
  const backend = path.resolve("../backend");
  const invite = JSON.parse(
    execFileSync(
      "uv",
      [
        "run",
        "python",
        path.resolve("tests/fixtures/identity-seed.py"),
        "invite",
        String(tenantId),
        role,
      ],
      {
        cwd: backend,
        env: { ...process.env, PYTHONPATH: backend },
        encoding: "utf8",
      },
    ),
  ) as { token: string };
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.goto("/accept-invitation#token=" + invite.token);
  await page.getByLabel("Full name", { exact: true }).fill("Reports " + role);
  await page
    .getByLabel("New password", { exact: true })
    .fill("ReportsStrongPassword123!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
}

test("management sees the three sections and downloads both files", async ({
  page,
  customer,
}) => {
  await publishWithGap(page);
  await joinAs(page, customer.tenant_id, "management");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Reports", exact: true })
    .click();
  await page.getByLabel("Month", { exact: true }).fill("2026-10");
  for (const name of [
    "Overtime against the yearly limit",
    "Monthly comparison",
    "Coverage by line",
  ])
    await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  await expect(
    page.getByText("Planned figures from published schedules", { exact: false }),
  ).toBeVisible();
  await expect(page.getByText("Within limits").first()).toBeVisible();
  await page.getByRole("button", { name: /Central depot – Harbour/ }).click();
  const days = page.getByRole("region", { name: /Affected days/ });
  await expect(days).toContainText("333002");
  await expect(days).toContainText("No driver available");
  await expect(days).toContainText("Canonical browser operator");
  for (const [name, extension] of [
    ["Excel", "xlsx"],
    ["PDF", "pdf"],
  ] as const) {
    const waiting = page.waitForEvent("download");
    await page.getByRole("button", { name, exact: true }).click();
    const download = await waiting;
    expect(download.suggestedFilename()).toMatch(/reports-\d{4}-\d{2}\.(xlsx|pdf)/);
    expect(download.suggestedFilename().endsWith(extension)).toBeTruthy();
  }
  await expect(page.getByText(/Last export/)).toContainText("Reports management");
  await page.getByLabel("Month", { exact: true }).fill("2026-11");
  await expect(
    page.getByText("There are no published days in November 2026"),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "Overtime against the yearly limit",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("at most 120.0").first()).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Monthly comparison", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Coverage by line", exact: true }),
  ).toHaveCount(0);
});

test("dispatcher has no Reports entry", async ({ page, customer }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(
    page
      .getByRole("navigation")
      .getByRole("button", { name: "Reports", exact: true }),
  ).toBeVisible();
  await joinAs(page, customer.tenant_id, "dispatcher");
  await page.goto("/?view=reports");
  await expect(
    page
      .getByRole("navigation")
      .getByRole("button", { name: "Scheduling Studio", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation")
      .getByRole("button", { name: "Reports", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Coverage by line" }),
  ).toHaveCount(0);
});

test("phone shows cards", async ({ page }) => {
  await publishWithGap(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?view=reports");
  await page.getByLabel("Month", { exact: true }).fill("2026-10");
  await expect(
    page.getByRole("heading", { name: "Coverage by line", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBeTruthy();
  await expect(page.locator(".team-table td[data-label]").first()).toBeVisible();
});

test("publish with an uncovered trip asks for a reason", async ({ page }) => {
  await page.goto("/?service_date=" + day);
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const revision = await (
    await page.request.get(
      "/api/v1/scheduling/revisions/active?service_date=" + day,
    )
  ).json();
  const trip = revision.source_trips.find(
    (item: { trip_code: string }) => item.trip_code === "333002",
  );
  const patched = await page.request.post(
    `/api/v1/scheduling/revisions/${revision.revision_id}/patches`,
    {
      headers: {
        "X-CSRF-Token":
          (await page.context().cookies()).find(
            (cookie) => cookie.name === "ktel_csrf",
          )?.value ?? "",
      },
      data: {
        version: revision.version,
        patches: [{ trip_id: trip.id, new_resource_id: "UNASSIGNED" }],
      },
    },
  );
  expect(patched.ok(), await patched.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page
    .getByRole("button", { name: "Αίτηση έγκρισης", exact: true })
    .click();
  await page.getByRole("button", { name: "Έγκριση", exact: true }).click();
  const publish = page.getByRole("button", { name: "Δημοσίευση", exact: true });
  await publish.click();
  const dialog = page.getByRole("dialog", {
    name: "Γιατί μένουν δρομολόγια χωρίς οδηγό;",
  });
  await expect(dialog).toBeVisible();
  const confirm = dialog.getByRole("button", {
    name: "Επιβεβαίωση",
    exact: true,
  });
  await expect(confirm).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(publish).toBeFocused();
  await publish.click();
  await dialog.getByLabel("Άλλο", { exact: true }).check();
  await expect(confirm).toBeDisabled();
  await dialog
    .getByLabel("Δεν υπήρχε διαθέσιμος οδηγός", { exact: true })
    .check();
  await expect(confirm).toBeEnabled();
  const note = dialog.getByRole("textbox");
  await note.fill("Έκτακτη απουσία");
  await page.route(
    "**/api/v1/scheduling/revisions/*/publish",
    (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Το πρόγραμμα άλλαξε." }),
      }),
    { times: 1 },
  );
  await confirm.click();
  await expect(dialog.getByRole("alert")).toHaveText("Το πρόγραμμα άλλαξε.");
  await expect(
    dialog.getByLabel("Δεν υπήρχε διαθέσιμος οδηγός", { exact: true }),
  ).toBeChecked();
  await expect(note).toHaveValue("Έκτακτη απουσία");
  await confirm.click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Δημοσιευμένο", { exact: true })).toBeVisible();
});
