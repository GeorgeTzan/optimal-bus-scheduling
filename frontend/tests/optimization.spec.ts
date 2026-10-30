import { signIn, test, expect, runCustomerWorker } from "./helpers/auth";

test("queues real CV, observes authenticated SSE and restores the run after reload", async ({
  page,
}) => {
  test.setTimeout(180000);
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(page.getByTestId("revision-version")).toBeVisible();
  const originalVersion = await page
    .getByTestId("revision-version")
    .textContent();
  await page.getByText("Planning options", { exact: true }).click();
  await page.getByLabel("CV iterations").selectOption("1");
  await page.getByText("Planning options", { exact: true }).click();
  const submission = page.waitForResponse(
    (r) =>
      r.url().includes("/api/optimization/runs") &&
      r.request().method() === "POST",
  );
  const stream = page.waitForResponse((r) => r.url().includes("/api/events?"));
  await page
    .getByRole("button", { name: "Generate draft schedule", exact: true })
    .click();
  const queued = await submission;
  expect(queued.status()).toBe(202);
  const connection = await stream;
  expect(connection.status()).toBe(200);
  expect(connection.request().headers()["authorization"]).toBeUndefined();
  expect(
    (await page.context().cookies()).find((c) => c.name === "ktel_session")
      ?.httpOnly,
  ).toBe(true);
  await expect(page.locator("progress")).toBeVisible();
  runCustomerWorker(page);
  await page.reload();
  await expect(page.getByTestId("revision-version")).toBeVisible();
  await page.getByRole("button", { name: /Draft options/ }).click();
  await expect(
    page.getByRole("button", { name: "Apply candidate", exact: true }),
  ).toBeVisible({ timeout: 140000 });
  await expect(page.locator("progress")).toHaveCount(0, { timeout: 140000 });
  await expect(page.getByTestId("revision-version")).toHaveText(
    originalVersion!,
  );
  await page.screenshot({
    path: "test-results/studio-real-cv-candidate.png",
    fullPage: true,
    animations: "disabled",
  });
});
