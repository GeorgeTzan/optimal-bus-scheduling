import { test, expect, signIn } from "./helpers/auth";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
const day = "2026-10-31";
async function headers(page: Page) {
  return {
    "X-CSRF-Token":
      (await page.context().cookies()).find((c) => c.name === "ktel_csrf")
        ?.value ?? "",
  };
}
async function publish(page: Page) {
  let response = await page.request.get(
    "/api/v1/scheduling/revisions/active?service_date=" + day,
  );
  expect(response.ok()).toBeTruthy();
  let revision = await response.json();
  for (const action of ["request-approval", "approve", "publish"]) {
    response = await page.request.post(
      `/api/v1/scheduling/revisions/${revision.revision_id}/${action}`,
      { headers: await headers(page), data: { version: revision.version } },
    );
    expect(response.ok(), await response.text()).toBeTruthy();
    revision = await response.json();
  }
}
async function open(page: Page) {
  await page.goto("/?view=operations&service_date=" + day);
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
}

test("published trips support optional delay and resolution history through reload", async ({
  page,
}) => {
  await open(page);
  await publish(page);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Daily Operations", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Planned · no staff confirmation", { exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "Record update for 333001", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Record a staff update" });
  await dialog.getByLabel("Update type", { exact: true }).selectOption("delay");
  await dialog.getByLabel("Delay (minutes)", { exact: true }).fill("12");
  await dialog
    .getByLabel("Details", { exact: true })
    .fill("Driver reported roadworks.");
  await dialog
    .getByRole("button", { name: "Save update", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await page.reload();
  await page
    .getByRole("button", { name: "Trip details for 333001", exact: true })
    .click();
  await expect(
    page.getByText("Driver reported roadworks.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Mark resolved", exact: true })
    .click();
  const resolution = page.getByRole("dialog", { name: "Resolve report" });
  await resolution
    .getByLabel("Resolution note", { exact: true })
    .fill("Driver confirmed traffic is moving.");
  await resolution
    .getByRole("button", { name: "Save resolution", exact: true })
    .click();
  await expect(resolution).toHaveCount(0);
  await page.reload();
  await page
    .getByRole("button", { name: "Trip details for 333001", exact: true })
    .click();
  await expect(
    page.getByText("Driver confirmed traffic is moving.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Mark resolved", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Planned · no staff confirmation", { exact: true }),
  ).toHaveCount(2);
  await page.screenshot({
    path: "../docs/screenshots/2026-11-01/operations-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../docs/screenshots/2026-11-01/operations-mobile.png",
    fullPage: true,
  });
});

test("an unpublished day opens independently of any active draft", async ({
  page,
}) => {
  await open(page);
  await page.getByLabel("Service date", { exact: true }).fill("2026-11-03");
  await expect(
    page.getByRole("heading", {
      name: "No published schedule for this day",
      exact: true,
    }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Service date", { exact: true })).toHaveValue(
    "2026-11-03",
  );
  await page
    .getByRole("button", { name: "Open Scheduling Studio", exact: true })
    .click();
  await expect(
    page.getByText("Your own schedule, one day at a time.", { exact: true }),
  ).toBeVisible();
});

test("conflicting reports preserve entered details and require an explicit refreshed review", async ({
  page,
}) => {
  await open(page);
  await publish(page);
  await page.reload();
  const before = await (
    await page.request.get("/api/v1/operations/day?service_date=" + day)
  ).json();
  await page
    .getByRole("button", { name: "Record update for 333001", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Record a staff update" });
  await dialog.getByLabel("Update type", { exact: true }).selectOption("note");
  await dialog
    .getByLabel("Details", { exact: true })
    .fill("My unsent details.");
  const concurrent = await page.request.post("/api/v1/operations/reports", {
    headers: await headers(page),
    data: {
      publication_id: before.publication.publication_id,
      trip_id: before.items[0].trip_id,
      expected_version: 0,
      request_id: crypto.randomUUID(),
      kind: "note",
      description: "Other dispatcher update.",
    },
  });
  expect(concurrent.status()).toBe(201);
  await dialog
    .getByRole("button", { name: "Save update", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("Another update");
  await expect(dialog.getByLabel("Details", { exact: true })).toHaveValue(
    "My unsent details.",
  );
  await dialog
    .getByRole("button", { name: "Refresh trip for review", exact: true })
    .click();
  await expect(dialog).toContainText("Other dispatcher update.");
  await dialog
    .getByRole("button", { name: "Use this latest version", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Save update", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
});

test("a reader can inspect published trips but cannot record reports", async ({
  page,
  customer,
}) => {
  await open(page);
  await publish(page);
  const script = path.resolve("tests/fixtures/identity-seed.py");
  const invite = JSON.parse(
    execFileSync(
      "uv",
      ["run", "python", script, "invite", String(customer.tenant_id), "viewer"],
      {
        cwd: path.resolve("../backend"),
        env: { ...process.env, PYTHONPATH: path.resolve("../backend") },
        encoding: "utf8",
      },
    ),
  ) as { token: string };
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.goto("/accept-invitation#token=" + invite.token);
  await page.getByLabel("Full name", { exact: true }).fill("Operations reader");
  await page
    .getByLabel("New password", { exact: true })
    .fill("ReaderStrongPassword123!");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByRole("button",{name:"Sign out",exact:true})).toBeVisible();
  await page.goto("/?view=operations&service_date=" + day);
  await expect(
    page.getByRole("heading", { name: "Daily Operations", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Record update for/ }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Trip details for 333001", exact: true })
    .click();
  await expect(
    page.getByText("No staff updates for this trip.", { exact: true }),
  ).toBeVisible();
});

test('a newer publication is signaled without moving an open report to it',async({page})=>{
  await open(page);await publish(page);await page.reload();
  await page.getByRole('button',{name:'Record update for 333001',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Record a staff update'});await dialog.getByLabel('Update type',{exact:true}).selectOption('note');await dialog.getByLabel('Details',{exact:true}).fill('For the original publication.');
  const before=await(await page.request.get('/api/v1/operations/day?service_date='+day)).json();
  const transfers=await(await page.request.get('/api/v1/transfers/editor?service_date='+day)).json();const direction=transfers.items[0].forward;
  const changed=await page.request.post('/api/v1/transfers/editor',{headers:await headers(page),data:{items:[{origin_station_id:direction.origin_station_id,destination_station_id:direction.destination_station_id,origin_version:direction.origin_version,destination_version:direction.destination_version,expected_version:direction.version,minutes:direction.minutes+1}]}});expect(changed.ok()).toBeTruthy();
  const created=await page.request.post('/api/v1/scheduling/revisions',{headers:await headers(page),data:{service_date:day}});expect(created.ok()).toBeTruthy();const revision=await created.json();
  const assigned=await page.request.post(`/api/v1/scheduling/revisions/${revision.revision_id}/patches`,{headers:await headers(page),data:{version:revision.version,patches:revision.assignments.map((row:{trip_id:string},index:number)=>({trip_id:row.trip_id,new_resource_id:revision.source_resources[index].resource_id}))}});expect(assigned.ok()).toBeTruthy();await publish(page);
  await dialog.getByRole('button',{name:'Save update',exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.getByText('A newer publication is available. These updates remain with this version.',{exact:true})).toBeVisible();
  const selected=await page.getByRole('combobox',{name:'Publication version',exact:true}).inputValue();expect(selected).toBe(before.publication.publication_id);
  await expect(page.getByText('For the original publication.',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Open newer publication',exact:true}).click();
  await expect(page.getByText('For the original publication.',{exact:true})).toHaveCount(0);
  await page.reload();await expect(page.getByText('For the original publication.',{exact:true})).toHaveCount(0);
});

test('a lost report response can be safely retried without duplicating history',async({page})=>{
  await open(page);await publish(page);await page.reload();await page.getByRole('button',{name:'Record update for 333001',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Record a staff update'});await dialog.getByLabel('Update type',{exact:true}).selectOption('note');await dialog.getByLabel('Details',{exact:true}).fill('One durable update.');
  await page.route('**/api/v1/operations/reports',async route=>{const accepted=await route.fetch();expect(accepted.status()).toBe(201);await route.abort('failed');});
  await dialog.getByRole('button',{name:'Save update',exact:true}).click();await expect(dialog.getByRole('alert')).toBeVisible();
  await page.unrouteAll({behavior:'wait'});await dialog.getByRole('button',{name:'Save update',exact:true}).click();await expect(dialog).toHaveCount(0);
  const result=await(await page.request.get('/api/v1/operations/day?service_date='+day)).json();expect(result.items[0].events).toHaveLength(1);
});

test('changing the day through browser history closes an untouched report for the previous day',async({page})=>{
  await open(page);await publish(page);await page.reload();
  await expect(page.getByRole('button',{name:'Record update for 333001',exact:true})).toBeVisible();
  await page.getByLabel('Service date',{exact:true}).fill('2026-11-03');
  await expect(page.getByRole('heading',{name:'No published schedule for this day',exact:true})).toBeVisible();
  await page.goBack();await page.getByRole('button',{name:'Record update for 333001',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Record a staff update'})).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('dialog',{name:'Record a staff update'})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'No published schedule for this day',exact:true})).toBeVisible();
});

test('rejecting browser history navigation preserves an unsaved report and the selected publication',async({page})=>{
  await open(page);await publish(page);await page.reload();
  await page.getByLabel('Service date',{exact:true}).fill('2026-11-03');
  await expect(page.getByRole('heading',{name:'No published schedule for this day',exact:true})).toBeVisible();
  await page.goBack();await page.getByRole('button',{name:'Record update for 333001',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Record a staff update'});await dialog.getByLabel('Details',{exact:true}).fill('Do not lose this report.');
  let prompted=false;page.on('dialog',async confirmation=>{prompted=true;await confirmation.dismiss();});
  await page.goForward();await expect.poll(()=>prompted).toBe(true);
  await expect(dialog.getByLabel('Details',{exact:true})).toHaveValue('Do not lose this report.');
  await expect(page).toHaveURL(/service_date=2026-10-31/);
});

test('a successor shows and resolves a report recorded on its earlier publication',async({page})=>{
  await open(page);await publish(page);await page.reload();
  const before=await(await page.request.get('/api/v1/operations/day?service_date='+day)).json();
  const report=await page.request.post('/api/v1/operations/reports',{headers:await headers(page),data:{publication_id:before.publication.publication_id,trip_id:before.items[0].trip_id,expected_version:0,request_id:crypto.randomUUID(),kind:'delay',delay_minutes:12,description:'Earlier publication delay.'}});expect(report.status()).toBe(201);
  const departed=await page.request.post('/api/v1/operations/reports',{headers:await headers(page),data:{publication_id:before.publication.publication_id,trip_id:before.items[0].trip_id,expected_version:1,request_id:crypto.randomUUID(),kind:'departure',description:'Departure confirmed by team.'}});expect(departed.status()).toBe(201);
  const changed=await page.request.post('/api/v1/scheduling/changes',{headers:await headers(page),data:{publication_id:before.publication.publication_id,version:(await(await page.request.get('/api/v1/scheduling/revisions/'+before.publication.revision_id)).json()).version,reason:'Review later trip',reviewed_not_started:[before.items[1].trip_id],patches:[{trip_id:before.items[1].trip_id,new_resource_id:'UNASSIGNED'}],request_id:crypto.randomUUID()}});expect(changed.status(),await changed.text()).toBe(201);let rev=await changed.json();
  for(const action of ['request-approval','approve','publish']){const response=await page.request.post(`/api/v1/scheduling/revisions/${rev.revision_id}/${action}`,{headers:await headers(page),data:{version:rev.version}});expect(response.ok(),await response.text()).toBeTruthy();rev=await response.json();}
  await page.goto('/?view=operations&service_date='+day);await page.getByRole('button',{name:'Trip details for 333001',exact:true}).click();
  await expect(page.getByText('Departure · reported on an earlier publication',{exact:true})).toBeVisible();
  const linked=page.getByRole('region',{name:'Earlier publication updates'});
  await expect(linked).toContainText('Earlier publication delay.');await expect(linked).toContainText('Earlier publication');
  await linked.getByRole('button',{name:'Mark resolved',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Resolve report'});await dialog.getByLabel('Resolution note',{exact:true}).fill('Resolved from the current board.');
  await dialog.getByRole('button',{name:'Save resolution',exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(linked).toContainText('Resolved from the current board.');await page.reload();
  await page.getByRole('button',{name:'Trip details for 333001',exact:true}).click();await expect(page.getByRole('region',{name:'Earlier publication updates'})).toContainText('Resolved from the current board.');
});
