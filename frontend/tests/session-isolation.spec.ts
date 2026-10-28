import { signIn, test, expect } from "./helpers/auth";

test("an obsolete schedule response cannot populate a later authenticated workspace", async ({
  page,
}) => {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  let delivered!: () => void;
  const delivery = new Promise<void>((resolve) => {
    delivered = resolve;
  });
  let calls = 0;
  await page.route("**/api/v1/scheduling/revisions/active**", async (route) => {
    calls++;
    if (calls === 1) {
      const response = await route.fetch();
      await held;
      try {
        await route.fulfill({ response });
      } finally {
        delivered();
      }
    } else
      await route.fulfill({
        status: 404,
        json: { detail: "No revision for this session" },
      });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await signIn(page);
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page);
  await expect(
    page.getByText("Your own schedule, one day at a time.", { exact: true }),
  ).toBeVisible();
  release();
  await delivery;
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      ),
  );
  await expect(page.getByTestId("revision-version")).toHaveCount(0);
  await expect(
    page.getByText("Your own schedule, one day at a time.", { exact: true }),
  ).toBeVisible();
});

test('a delayed conflict refresh cannot replace the newly selected service day',async({page})=>{
  await page.goto('/?service_date=2026-10-31');await page.getByRole('button',{name:'EN',exact:true}).click();await signIn(page);
  await expect(page.getByTestId('revision-version')).toBeVisible();
  let release!:()=>void, reached!:()=>void, delivered!:()=>void;const held=new Promise<void>(r=>release=r),started=new Promise<void>(r=>reached=r),finished=new Promise<void>(r=>delivered=r);
  await page.route('**/api/v1/scheduling/revisions/*/patches',async route=>{await route.fulfill({status:409,json:{detail:'Changed elsewhere'}});});
  await page.route('**/api/v1/scheduling/revisions/active?**',async route=>{
    if(route.request().url().includes('2026-10-31')){const response=await route.fetch();reached();await held;await route.fulfill({response});delivered();}else await route.continue();
  });
  try{
    await page.getByRole('button',{name:'Inspect 333001',exact:true}).click();
    const inspector=page.getByRole('complementary',{name:'Trip Details'});
    await inspector.getByRole('button',{name:'Resource',exact:true}).click();
    const select=inspector.getByLabel('Bus · Driver',{exact:true});const values=await select.locator('option').evaluateAll(options=>options.map(o=>(o as HTMLOptionElement).value));
    const selected=await select.inputValue();await select.selectOption(values.find(value=>value&&value!==selected) ?? values[1]!);
    await started;
    await page.getByLabel('Service date',{exact:true}).fill('2026-11-03');
    await expect(page.getByText('Your own schedule, one day at a time.',{exact:true})).toBeVisible();
    release();await finished;await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await expect(page.getByTestId('revision-version')).toHaveCount(0);
    await expect(page.getByText('Your own schedule, one day at a time.',{exact:true})).toBeVisible();
  }finally{release();await page.unrouteAll({behavior:'wait'});}
});
