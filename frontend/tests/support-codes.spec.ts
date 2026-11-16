import { expect, test } from "@playwright/test";
import { supportCodeMessages } from "../src/features/auth/support-codes";

test("support and suspension codes have Greek and English text", () => {
  for (const code of [
    "support_read_only",
    "support_not_available",
    "organization_suspended",
    "support_access_not_enabled",
  ]) {
    const [greek, english] = supportCodeMessages[code] ?? ["", ""];
    expect(greek).toMatch(/[Α-Ωα-ω]/);
    expect(english).toMatch(/^[A-Za-z]/);
  }
});
