import { expect, test } from "@playwright/test";
import {
  healthFlags,
  type Health,
} from "../src/features/platform/platform-api";

const health: Health = {
  tenant_id: 1,
  last_sign_in: new Date().toISOString(),
  drivers: 0,
  vehicles: 0,
  timetables: 0,
  published_days_30d: 0,
  solver_failed_7d: 0,
  mail_failed_7d: 0,
  uncovered_share_latest: null,
};

test("health flags are empty only when health is known and clean", () => {
  expect(healthFlags(health)).toEqual({ failing: [], inactive: false });
  expect(healthFlags({ ...health, mail_failed_7d: 1 }).failing).toEqual([
    "mail",
  ]);
  expect(healthFlags({ ...health, last_sign_in: null }).inactive).toBe(true);
});
