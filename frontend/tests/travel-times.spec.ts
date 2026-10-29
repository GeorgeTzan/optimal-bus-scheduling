import { test, expect, signIn } from "./helpers/auth";

async function openDay(page: import("@playwright/test").Page) {
  await page.goto("/?view=planning&service_date=2026-10-31");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByLabel("Service date", { exact: true }).fill("2026-10-31");
  await expect(
    page.getByRole("heading", { name: "Travel between trips", exact: true }),
  ).toBeVisible();
  return page.getByRole("region", {
    name: "Travel between trips",
    exact: true,
  });
}

test("saved travel times stay visible and editable, and changed inputs mark Studio for review", async ({
  page,
}) => {
  const editor = await openDay(page);
  await expect(page.locator(".planning-pairing")).toHaveCount(0);
  await page.getByRole("button",{name:"Show confirmed crews (2)",exact:true}).click();
  await expect(page.locator(".planning-pairing")).toHaveCount(2);
  await page.getByRole("button",{name:"Hide confirmed crews",exact:true}).click();
  await editor
    .getByRole("button", { name: "Why is this needed?", exact: true })
    .click();
  await expect(editor).toContainText("without passengers");
  const forward = editor.getByLabel("Minutes: Central depot → Harbour", {
    exact: true,
  });
  const reverse = editor.getByLabel("Minutes: Harbour → Central depot", {
    exact: true,
  });
  await expect(forward).toHaveValue("30");
  await expect(reverse).toHaveValue("35");
  await forward.fill("42");
  let warned = false;
  page.once("dialog", (dialog) => {
    warned = true;
    void dialog.dismiss();
  });
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Drivers", exact: true })
    .click();
  expect(warned).toBe(true);
  await expect(forward).toHaveValue("42");
  const saved = page.waitForResponse(
    (r) =>
      r.url().includes("/api/v1/transfers/editor") &&
      r.request().method() === "POST",
  );
  await editor
    .getByRole("button", { name: "Save travel times", exact: true })
    .click();
  expect((await saved).status()).toBe(200);
  await page.reload();
  await expect(page.getByLabel("Service date", { exact: true })).toHaveValue(
    "2026-10-31",
  );
  await expect(forward).toHaveValue("42");
  await expect(reverse).toHaveValue("35");
  await page.screenshot({path:"test-results/travel-times-editable.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/travel-times-mobile.png",fullPage:true});
  await page.setViewportSize({width:1600,height:1000});
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Scheduling Studio", exact: true })
    .click();
  await expect(
    page.getByText(/The day's inputs changed after this draft/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Generate draft schedule", exact: true }),
  ).toBeDisabled();
});

test("a missing direction saves independently and reverse copying is explicit", async ({
  page,
}) => {
  let editor = await openDay(page);
  const csrf = (await page.context().cookies()).find(
    (c) => c.name === "ktel_csrf",
  )!.value;
  const headers = { "X-CSRF-Token": csrf };
  const templates = await (await page.request.get("/api/v1/timetables")).json();
  const first = templates.items[0];
  const stationResponse = await page.request.post("/api/v1/stations", {
    headers,
    data: { code: "003", name_el: "Κιάτο", name_en: "Kiato" },
  });
  expect(stationResponse.status()).toBe(201);
  const station = await stationResponse.json();
  const created = await page.request.post("/api/v1/timetables", {
    headers,
    data: {
      trip_code: "BULK-T003",
      origin_station_id: first.origin.id,
      destination_station_id: station.id,
      departure_time: "11:00",
      arrival_time: "12:00",
      arrival_day_offset: 0,
      operating_weekdays: [0, 1, 2, 3, 4, 5, 6],
      valid_from: "2026-01-01",
      valid_until: "2028-12-31",
      allowed_bus_types: ["02"],
    },
  });
  expect(created.status()).toBe(201);
  await page.reload();
  editor = page.getByRole("region", {
    name: "Travel between trips",
    exact: true,
  });
  const forward = editor.getByLabel("Minutes: Central depot → Kiato", {
      exact: true,
    }),
    reverse = editor.getByLabel("Minutes: Kiato → Central depot", {
      exact: true,
    });
  await forward.fill("25");
  await expect(reverse).toHaveValue("");
  await editor
    .getByRole("button", { name: "Save travel times", exact: true })
    .click();
  await expect(editor.getByRole("status")).toContainText("Travel times saved");
  await page.reload();
  await expect(forward).toHaveValue("25");
  await expect(reverse).toHaveValue("");
  await editor
    .getByLabel("Use the same time for return: Central depot ↔ Kiato", {
      exact: true,
    })
    .check();
  await expect(reverse).toHaveValue("25");
  await editor
    .getByRole("button", { name: "Save travel times", exact: true })
    .click();
  await expect(editor.getByRole("status")).toContainText("Travel times saved");
  await editor
    .getByRole("button", { name: "Import from Excel/CSV", exact: true })
    .click();
  const template = page.waitForResponse((r) =>
    r.url().includes("/api/v1/imports/templates/transfers?"),
  );
  await page
    .getByRole("button", { name: "Download Excel template", exact: true })
    .click();
  expect((await template).status()).toBe(200);
});

test("an operator chooses a previous crew date and copies it only for review", async ({
  page,
}) => {
  await openDay(page);
  await page.getByLabel("Service date", { exact: true }).fill("2026-11-02");
  await page
    .getByLabel("Copy crews from date", { exact: true })
    .fill("2026-10-31");
  await page
    .getByRole("button", { name: "Copy crews for review", exact: true })
    .click();
  await expect(page.locator(".planning-pairing")).toHaveCount(2);
  await expect(page.locator(".planning-pairing.needs-review")).toHaveCount(2);
  await page.reload();
  await expect(page.getByLabel("Service date", { exact: true })).toHaveValue(
    "2026-11-02",
  );
  await expect(page.locator(".planning-pairing.needs-review")).toHaveCount(2);
});
