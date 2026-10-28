import { expect, type Page } from "@playwright/test";

/** States working time explicitly, as an organization must before a draft can be created: grant, then all-day patterns for every driver. */
export async function giveWorkingTime(page: Page) {
  const headers = { "X-CSRF-Token": (await page.context().cookies()).find((c) => c.name === "ktel_csrf")?.value ?? "" };
  const members = (await (await page.request.get("/api/v1/identity/members")).json()).members as { id: number }[];
  const granted = await page.request.put("/api/v1/office/grants", {
    headers,
    data: { request_id: crypto.randomUUID(), membership_id: members[0]!.id, capability: "availability.manage", is_active: true, expected_version: null },
  });
  expect([200, 409]).toContain(granted.status());
  const drivers = (await (await page.request.get("/api/v1/drivers?page_size=100")).json()).items as { id: number }[];
  const saved = await page.request.post("/api/v1/office/working-patterns", {
    headers,
    data: {
      request_id: crypto.randomUUID(),
      items: drivers.flatMap((driver) =>
        [["2026-01-01", "2026-12-31"], ["2027-01-01", "2027-12-31"]].map(([valid_from, valid_until]) => ({
          driver_id: driver.id, weekday_mask: 127, local_start: "00:00", local_end: "23:59", ends_next_day: true, valid_from, valid_until,
        })),
      ),
    },
  });
  expect(saved.ok(), await saved.text()).toBeTruthy();
}
