import { signIn, test, expect } from "./helpers/auth";

test("persists a dispatcher edit through reload and shows server verification", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const trip = page.getByRole("button", {
    name: "Inspect 333001",
    exact: true,
  });
  await trip.click();
  const inspector = page.getByRole("complementary", { name: "Trip Details" });
  const lock = inspector.getByRole("button", { name: /Unlocked|Locked/ });
  const previous = await lock.textContent();
  await lock.click();
  await expect(lock).not.toHaveText(previous!);
  const persisted = await lock.textContent();
  await page.reload();
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  await expect(
    page
      .getByRole("complementary")
      .getByRole("button", { name: /Unlocked|Locked/ }),
  ).toHaveText(persisted!);
  await page
    .getByRole("complementary")
    .getByRole("button", { name: "Legality", exact: true })
    .click();
  await expect(
    page.getByText("Independent server verification", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/scheduling-inspector-light.png",
    fullPage: true,
    animations: "disabled",
  });
});

test("manual reassignment shows server overlap findings and survives reload", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const response = await page.request.get(
    "/api/v1/scheduling/revisions/active",
  );
  const rev = await response.json();
  const trip = rev.problem.trips.find(
    (t: { id: string }) =>
      t.id ===
      rev.source_trips.find(
        (t: { trip_code: string }) => t.trip_code === "333001",
      ).id,
  );
  const original = rev.assignments.find(
    (a: { trip_id: string }) => a.trip_id === trip.id,
  );
  const overlapping = rev.problem.trips.find(
    (t: { id: string; start_minutes: number; end_minutes: number }) => {
      const a = rev.assignments.find(
        (a: { trip_id: string }) => a.trip_id === t.id,
      );
      return (
        t.id !== trip.id &&
        t.start_minutes < trip.end_minutes &&
        t.end_minutes > trip.start_minutes &&
        a.resource_id !== "UNASSIGNED" &&
        a.resource_id !== original.resource_id
      );
    },
  );
  const target = rev.assignments.find(
    (a: { trip_id: string }) => a.trip_id === overlapping.id,
  ).resource_id;
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  const inspector = page.getByRole("complementary", { name: "Trip Details" });
  if (original.is_locked) {
    await inspector
      .getByRole("button", { name: "Locked", exact: true })
      .click();
    await expect(
      inspector.getByRole("button", { name: "Unlocked", exact: true }),
    ).toBeEnabled();
  }
  await inspector
    .getByRole("button", { name: "Resource", exact: true })
    .click();
  await inspector
    .getByLabel("Bus · Driver", { exact: true })
    .selectOption(target);
  await inspector
    .getByRole("button", { name: "Legality", exact: true })
    .click();
  await expect(inspector.getByRole("alert")).toContainText(
    "RULE_NO_TEMPORAL_OVERLAP",
  );
  await expect(
    page.getByRole("button", { name: "Request approval", exact: true }),
  ).toBeDisabled();
  await page.reload();
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  await inspector
    .getByRole("button", { name: "Resource", exact: true })
    .click();
  await expect(
    inspector.getByLabel("Bus · Driver", { exact: true }),
  ).toHaveValue(target);
  await inspector
    .getByLabel("Bus · Driver", { exact: true })
    .selectOption(original.resource_id);
  await expect(
    inspector.getByRole("button", { name: "Unlocked", exact: true }),
  ).toBeEnabled();
  if (original.is_locked)
    await inspector
      .getByRole("button", { name: "Unlocked", exact: true })
      .click();
});
