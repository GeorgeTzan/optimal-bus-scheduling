import { test, expect } from "@playwright/test";
import { signIn } from "./helpers/auth";

test("the saved reference archive is explicitly opened and read only", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await page.getByText("More", { exact: true }).click();
  await page
    .getByRole("button", { name: "Reference archive", exact: true })
    .click();
  await expect(
    page.getByText("Reference archive · Read only", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Generate draft schedule", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Inspect 333001", exact: true })
    .click();
  await expect(
    page
      .getByRole("complementary", { name: "Trip Details" })
      .getByRole("button", { name: /Locked|Unlocked/ }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/studio-reference-archive.png",
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByText("Reference archive · Read only", { exact: true }),
  ).toBeVisible();
});
