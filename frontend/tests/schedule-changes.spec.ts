import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";
const day = "2026-10-31";
async function headers(page: Page) {
  return {
    "X-CSRF-Token":
      (await page.context().cookies()).find((c) => c.name === "ktel_csrf")
        ?.value ?? "",
  };
}
async function setup(page: Page, published: boolean) {
  await page.goto("/?service_date=" + day);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  let revision = await (
    await page.request.get(
      "/api/v1/scheduling/revisions/active?service_date=" + day,
    )
  ).json();
  const second = revision.source_trips.find(
    (trip: { trip_code: string }) => trip.trip_code === "333002",
  );
  let response = await page.request.post(
    `/api/v1/scheduling/revisions/${revision.revision_id}/patches`,
    {
      headers: await headers(page),
      data: {
        version: revision.version,
        patches: [{ trip_id: second.id, new_resource_id: "UNASSIGNED" }],
      },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  revision = await response.json();
  if (published)
    for (const action of ["request-approval", "approve", "publish"]) {
      response = await page.request.post(
        `/api/v1/scheduling/revisions/${revision.revision_id}/${action}`,
        { headers: await headers(page), data: { version: revision.version } },
      );
      expect(response.ok(), await response.text()).toBeTruthy();
      revision = await response.json();
    }
  await page.reload();
  await expect(page.getByTestId("revision-version")).toBeVisible();
  return revision;
}

test("draft trip reassignment is checked first and stays at its original time", async ({
  page,
}) => {
  const revision = await setup(page, false);
  const trip = revision.source_trips.find(
    (item: { trip_code: string }) => item.trip_code === "333001",
  );
  const current = revision.assignments.find(
    (item: { trip_id: string }) => item.trip_id === trip.id,
  ).resource_id;
  const target = revision.source_resources.find(
    (item: { resource_id: string }) => item.resource_id !== current,
  );
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  await page.getByRole("button", { name: "Move trip", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Review schedule change" });
  await dialog
    .getByLabel("Destination assignment", { exact: true })
    .selectOption(target.resource_id);
  await dialog
    .getByRole("button", { name: "Check change", exact: true })
    .click();
  await expect(dialog).toContainText("08:00");
  expect(
    (
      await (
        await page.request.get(
          `/api/v1/scheduling/revisions/${revision.revision_id}`,
        )
      ).json()
    ).version,
  ).toBe(revision.version);
  await dialog
    .getByRole("button", { name: "Save change", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  const saved = await (
    await page.request.get(
      `/api/v1/scheduling/revisions/${revision.revision_id}`,
    )
  ).json();
  expect(
    saved.assignments.find(
      (item: { trip_id: string }) => item.trip_id === trip.id,
    ).resource_id,
  ).toBe(target.resource_id);
  expect(
    saved.problem.trips.find((item: { id: string }) => item.id === trip.id)
      .start_minutes,
  ).toBe(
    revision.problem.trips.find((item: { id: string }) => item.id === trip.id)
      .start_minutes,
  );
});

test("dragging a published trip opens review without changing its scheduled time or publication", async ({
  page,
}) => {
  const revision = await setup(page, true);
  const trip = revision.source_trips.find(
    (item: { trip_code: string }) => item.trip_code === "333001",
  );
  const current = revision.assignments.find(
    (item: { trip_id: string }) => item.trip_id === trip.id,
  ).resource_id;
  const target = revision.source_resources.find(
    (item: { resource_id: string }) => item.resource_id !== current,
  );
  await page
    .locator(`[data-trip-id="${trip.id}"]`)
    .dragTo(page.locator(`[data-resource-id="${target.resource_id}"]`));
  const dialog = page.getByRole("dialog", { name: "Review schedule change" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByLabel("Destination assignment", { exact: true }),
  ).toHaveValue(target.resource_id);
  await dialog
    .getByLabel("Reason for change", { exact: true })
    .fill("Driver unavailable.");
  await dialog
    .getByLabel("I confirmed the selected trips have not started", {
      exact: true,
    })
    .check();
  await dialog
    .getByRole("button", { name: "Check change", exact: true })
    .click();
  await expect(dialog).toContainText("08:00");
  await dialog
    .getByRole("button", { name: "Create reviewed draft", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("Draft", { exact: true }).first()).toBeVisible();
  const original = await (
    await page.request.get(
      `/api/v1/scheduling/revisions/${revision.revision_id}`,
    )
  ).json();
  expect(original.status).toBe("published");
  expect(
    original.assignments.find(
      (item: { trip_id: string }) => item.trip_id === trip.id,
    ).resource_id,
  ).toBe(current);
});

test("a cancelled trip stays visible with its reason in the resulting draft", async ({
  page,
}) => {
  await setup(page, true);
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  await page.getByRole("button", { name: "Cancel trip", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Review schedule change" });
  await dialog
    .getByLabel("Reason for change", { exact: true })
    .fill("Vehicle unavailable.");
  await dialog
    .getByLabel("I confirmed the selected trips have not started", {
      exact: true,
    })
    .check();
  await dialog
    .getByRole("button", { name: "Check change", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Create reviewed draft", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Cancelled trips" }),
  ).toContainText("333001");
  await expect(
    page.getByRole("region", { name: "Cancelled trips" }),
  ).toContainText("Vehicle unavailable.");
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Cancelled trips" }),
  ).toContainText("333001");
});
