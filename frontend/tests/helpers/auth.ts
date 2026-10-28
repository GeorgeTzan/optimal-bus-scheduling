import { test as base, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
const customers = new WeakMap<
  Page,
  { email: string; password: string; tenant_id: number }
>();
export { expect };
export const test = base.extend<{ customer: { tenant_id: number } }>({
  customer: [
    async ({ page, request }, use) => {
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
        email: string;
      };
      const password = "BrowserCanonicalPassword123!";
      try {
        const accepted = await request.post("/api/auth/accept-invitation", {
          data: {
            token: invite.token,
            password,
            full_name: "Canonical browser operator",
          },
        });
        expect(accepted.ok(), await accepted.text()).toBeTruthy();
        const { access_token } = await accepted.json();
        const csrf =
          (await request.storageState()).cookies.find(
            (cookie) => cookie.name === "ktel_csrf",
          )?.value ?? "";
        const headers = {
          Authorization: `Bearer ${access_token}`,
          "X-CSRF-Token": csrf,
        };
        async function create(entity: string, data: object) {
          const response = await request.post(`/api/v1/${entity}`, {
            headers,
            data,
          });
          expect(
            response.ok(),
            (await response.text()).slice(0, 500),
          ).toBeTruthy();
          return response.json();
        }
        const origin = await create("stations", {
          code: "001",
          name_el: "Κεντρικός",
          name_en: "Central depot",
          is_depot: true,
        });
        const destination = await create("stations", {
          code: "002",
          name_el: "Λιμάνι",
          name_en: "Harbour",
        });
        const service_date = "2026-10-31";
        // Working time is stated explicitly, as an organization must before a draft can be created.
        const members = await request.get("/api/v1/identity/members", { headers });
        const me = ((await members.json()).members as { id: number }[])[0]!.id;
        const granted = await request.put("/api/v1/office/grants", {
          headers,
          data: { request_id: crypto.randomUUID(), membership_id: me, capability: "availability.manage", is_active: true, expected_version: null },
        });
        expect(granted.ok(), await granted.text()).toBeTruthy();
        const driverIds: number[] = [];
        for (const [index, code] of ["333001", "333002"].entries()) {
          const driver = await create("drivers", {
            code: `DR${index}`,
            first_name: index ? "Eleni" : "Nikos",
            last_name: index ? "Papadopoulou" : "Dimos",
            home_station_id: origin.id,
          });
          const vehicle = await create("vehicles", {
            code: `BUS${index}`,
            registration_plate: `KRA-432${index}`,
            bus_type: "02",
            home_station_id: origin.id,
          });
          driverIds.push(driver.id);
          await create("pairings", {
            driver_id: driver.id,
            vehicle_id: vehicle.id,
            home_station_id: origin.id,
            service_date,
            confirm: true,
            driver_version: 1,
            vehicle_version: 1,
            home_station_version: 1,
          });
          await create("timetables", {
            trip_code: code,
            origin_station_id: origin.id,
            destination_station_id: destination.id,
            departure_time: index ? "08:15" : "08:00",
            arrival_time: index ? "09:15" : "09:00",
            arrival_day_offset: 0,
            operating_weekdays: [0, 1, 2, 3, 4, 5, 6],
            valid_from: "2026-01-01",
            valid_until: "2028-12-31",
            allowed_bus_types: ["02"],
          });
        }
        const working = await request.post("/api/v1/office/working-patterns", {
          headers,
          data: {
            request_id: crypto.randomUUID(),
            items: driverIds.map((driver_id) => ({
              driver_id, weekday_mask: 127, local_start: "00:00", local_end: "23:59", ends_next_day: true,
              valid_from: "2026-01-01", valid_until: "2026-12-31",
            })),
          },
        });
        expect(working.ok(), await working.text()).toBeTruthy();
        await create("transfers/batch", {
          items: [
            {
              origin_station_id: origin.id,
              destination_station_id: destination.id,
              minutes: 30,
            },
            {
              origin_station_id: destination.id,
              destination_station_id: origin.id,
              minutes: 35,
            },
          ],
        });
        const revision = await create("scheduling/revisions", { service_date });
        await create(`scheduling/revisions/${revision.revision_id}/patches`, {
          version: revision.version,
          patches: revision.assignments.map(
            (assignment: { trip_id: string }, index: number) => ({
              trip_id: assignment.trip_id,
              new_resource_id: revision.problem.resources[index].resource_id,
              is_locked: false,
            }),
          ),
        });
        customers.set(page, {
          email: invite.email,
          password,
          tenant_id: invite.tenant_id,
        });
        await use({ tenant_id: invite.tenant_id });
      } finally {
        customers.delete(page);
        run(["cleanup", String(invite.tenant_id)]);
      }
    },
    { auto: true },
  ],
});
export async function signIn(page: Page) {
  const customer = customers.get(page);
  await page
    .locator('input[type="email"]')
    .fill(customer?.email ?? "admin@ktel.gr");
  await page
    .locator('input[type="password"]')
    .fill(customer?.password ?? "admin123");
  await page.getByRole("button", { name: /Sign in|Σύνδεση/i }).click();
}
export function runCustomerWorker(page: Page) {
  const customer = customers.get(page);
  if (!customer) throw new Error("No disposable customer");
  execFileSync(
    "uv",
    [
      "run",
      "python",
      "-m",
      "app.domain.jobs.worker",
      "--tenant-id",
      String(customer.tenant_id),
      "--once",
    ],
    { cwd: path.resolve("../backend"), timeout: 30000 },
  );
}
