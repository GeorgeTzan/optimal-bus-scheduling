import { test, expect, signIn, runCustomerWorker } from "./helpers/auth";
import type { Page } from "@playwright/test";

async function studio(page: Page) {
  await page.goto("/?service_date=2026-10-31");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page.getByText("Planning options", { exact: true }).click();
  await page.getByLabel("CV iterations").selectOption("1");
  await page.getByText("Planning options", { exact: true }).click();
}
async function queue(page: Page) {
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/optimization/runs") &&
      r.request().method() === "POST",
    { timeout: 7000 },
  );
  await page
    .getByRole("button", { name: "Generate draft schedule", exact: true })
    .click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  return (await response.json()) as { run_id: string };
}

test("a browser without randomUUID still queues a real draft request", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(globalThis.crypto, "randomUUID", {
      value: undefined,
      configurable: true,
    }),
  );
  await studio(page);
  await queue(page);
});

test("a completed CV proposal is visible and survives reload without applying itself", async ({
  page,
}) => {
  await studio(page);
  const version = await page.getByTestId("revision-version").textContent();
  await queue(page);
  runCustomerWorker(page);
  await expect(
    page.getByRole("button", { name: "Review proposal", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await expect(
    page.getByRole("button", { name: "Apply candidate", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("revision-version")).toHaveText(version!);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Review proposal", exact: true }),
  ).toBeVisible();
  await expect(page.locator("progress")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Review proposal", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Apply candidate", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("revision-version")).toHaveText(version!);
});

test("finishing a search cannot take the operator away from Drivers", async ({
  page,
}) => {
  await studio(page);
  const { run_id } = await queue(page);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Drivers", exact: true })
    .click();
  runCustomerWorker(page);
  const status = await (
    await page.request.get("/api/optimization/runs/" + run_id)
  ).json();
  expect(status.status).toBe("completed");
  await expect(
    page.getByRole("heading", { name: "Drivers", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Scheduling Studio", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Review proposal", exact: true }),
  ).toBeVisible({ timeout: 15000 });
});

test("a rejected real request explains recovery and allows a successful retry", async ({
  page,
}) => {
  await studio(page);
  await page.route("**/api/optimization/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const body = route.request().postDataJSON();
    body.config.iterations = 0;
    const response = await route.fetch({ postData: JSON.stringify(body) });
    expect(response.status()).toBe(422);
    await route.fulfill({ response });
  });
  await page
    .getByRole("button", { name: "Generate draft schedule", exact: true })
    .click();
  await expect(page.locator(".notice.error[role=alert]")).toContainText(
    "Check the search settings",
  );
  await page.unrouteAll({ behavior: "wait" });
  await queue(page);
});

test("retrying after a lost acceptance response recovers the same queued job", async ({
  page,
}) => {
  await studio(page);
  let acceptedId = "";
  await page.route("**/api/optimization/runs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    expect(response.status()).toBe(202);
    acceptedId = ((await response.json()) as { run_id: string }).run_id;
    await route.abort("failed");
  });
  await page
    .getByRole("button", { name: "Generate draft schedule", exact: true })
    .click();
  await expect(page.locator(".notice.error[role=alert]")).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
  const recovered = await queue(page);
  expect(recovered.run_id).toBe(acceptedId);
});

test("a missing saved run does not permanently disable generating a new proposal", async ({
  page,
  customer,
}) => {
  await studio(page);
  const revision = await (
    await page.request.get(
      "/api/v1/scheduling/revisions/active?service_date=2026-10-31",
    )
  ).json();
  await page.evaluate(
    ({ tenant, revisionId }) =>
      localStorage.setItem(
        `ktel_job_${tenant}_${revisionId}`,
        "00000000-0000-4000-8000-000000000000",
      ),
    { tenant: customer.tenant_id, revisionId: revision.revision_id },
  );
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Generate draft schedule", exact: true }),
  ).toBeEnabled({ timeout: 10000 });
  await queue(page);
});

test("fast completion cannot leave the visible candidate list at an earlier empty response", async ({
  page,
}) => {
  await studio(page);
  let release!: () => void, fetched!: () => void;
  const done = new Promise<void>((resolve) => {
    release = resolve;
  });
  const earlier = new Promise<void>((resolve) => {
    fetched = resolve;
  });
  let first = true;
  await page.route("**/api/optimization/runs/*/candidates", async (route) => {
    if (!first) {
      await route.continue();
      return;
    }
    first = false;
    const response = await route.fetch();
    expect(
      ((await response.json()) as { candidates: unknown[] }).candidates,
    ).toHaveLength(0);
    fetched();
    await done;
    await route.fulfill({ response });
  });
  await page.route(/\/api\/optimization\/runs\/[^/]+$/, async (route) => {
    await done;
    const response = await route.fetch();
    await route.fulfill({ response });
  });
  try {
    const { run_id } = await queue(page);
    await earlier;
    runCustomerWorker(page);
    release();
    const actual = await (
      await page.request.get("/api/optimization/runs/" + run_id + "/candidates")
    ).json();
    expect(actual.candidates.length).toBeGreaterThan(0);
    await expect(
      page.getByRole("button", { name: /Draft options/ }),
    ).toHaveText("Draft options" + actual.candidates.length, {
      timeout: 12000,
    });
  } finally {
    release();
    await page.unrouteAll({ behavior: "wait" });
  }
});

test("Overview presents a real dated next step instead of a competing solver action", async ({
  page,
}) => {
  await page.goto("/?view=dashboard&service_date=2026-10-31");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  const next = page.getByRole("region", {
    name: "Your next step",
    exact: true,
  });
  await expect(
    next.getByRole("button", { name: "Open Scheduling Studio", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("100% feasibility", { exact: true })).toHaveCount(
    0,
  );
  await next
    .getByRole("button", { name: "Open Scheduling Studio", exact: true })
    .click();
  await expect(page.getByTestId("revision-version")).toBeVisible();
});
