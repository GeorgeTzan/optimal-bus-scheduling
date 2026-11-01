import {test,expect,signIn} from './helpers/auth';
test('a dispatcher can keep unsaved driver details when attempting to close the form',async({page})=>{
  await page.goto('/?view=drivers');await page.getByRole('button',{name:'EN',exact:true}).click();await signIn(page);
  await page.getByRole('button',{name:'Add driver',exact:true}).click();
  await page.getByLabel('First name',{exact:true}).fill('Unsaved name');
  let prompted=false;page.on('dialog',async dialog=>{prompted=true;await dialog.dismiss();});
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  expect(prompted).toBe(true);await expect(page.getByLabel('First name',{exact:true})).toHaveValue('Unsaved name');
});

test('unsaved timetable and date exception details are protected when closing',async({page})=>{
  await page.goto('/?view=timetables');await page.getByRole('button',{name:'EN',exact:true}).click();await signIn(page);
  await page.getByRole('button',{name:'Add timetable',exact:true}).click();
  await page.getByLabel('Trip reference',{exact:true}).fill('NOT-YET-SAVED');
  let prompts=0;page.on('dialog',async dialog=>{prompts++;await dialog.dismiss();});
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  expect(prompts).toBe(1);await expect(page.getByLabel('Trip reference',{exact:true})).toHaveValue('NOT-YET-SAVED');
  page.removeAllListeners('dialog');page.on('dialog',async dialog=>{await dialog.accept();});
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  await page.getByRole('row').filter({hasText:'333001'}).getByRole('button',{name:'Change one date',exact:true}).click();
  await page.getByLabel('Exception date',{exact:true}).fill('2026-11-03');
  page.removeAllListeners('dialog');page.on('dialog',async dialog=>{prompts++;await dialog.dismiss();});
  await page.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();
  expect(prompts).toBe(2);await expect(page.getByLabel('Exception date',{exact:true})).toHaveValue('2026-11-03');
});

test('closing an untouched station picker does not discard or warn about its parent timetable',async({page})=>{
  await page.goto('/?view=timetables');await page.getByRole('button',{name:'EN',exact:true}).click();await signIn(page);
  await page.getByRole('button',{name:'Add timetable',exact:true}).click();await page.getByLabel('Trip reference',{exact:true}).fill('PARENT');
  await page.getByLabel('Origin station',{exact:true}).fill('New station');await page.getByRole('button',{name:'Add origin station',exact:true}).click();
  let prompted=false;page.on('dialog',async dialog=>{prompted=true;await dialog.dismiss();});
  await page.getByRole('dialog',{name:'Add station'}).getByRole('button',{name:'Cancel',exact:true}).click();
  expect(prompted).toBe(false);await expect(page.getByRole('dialog',{name:'Add station'})).toHaveCount(0);await expect(page.getByLabel('Trip reference',{exact:true})).toHaveValue('PARENT');
});
