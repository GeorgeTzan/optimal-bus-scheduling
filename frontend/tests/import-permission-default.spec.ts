import {test,expect,signIn} from './helpers/auth';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
test('a dispatcher opening imports starts on a template they can use',async({page,customer})=>{
  await page.goto('/?view=drivers');await page.getByRole('button',{name:'EN',exact:true}).click();await signIn(page);
  await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible();
  const script=path.resolve('tests/fixtures/identity-seed.py'),backend=path.resolve('../backend');
  const invite=JSON.parse(execFileSync('uv',['run','python',script,'invite',String(customer.tenant_id),'dispatcher'],{cwd:backend,env:{...process.env,PYTHONPATH:backend},encoding:'utf8'})) as {token:string};
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.goto('/accept-invitation#token='+invite.token);
  await page.getByLabel('Full name',{exact:true}).fill('Dispatcher');await page.getByLabel('New password',{exact:true}).fill('DispatcherStrongPassword123!');await page.getByRole('button',{name:'Create account',exact:true}).click();
  await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible();await page.goto('/?view=imports');
  await expect(page.getByRole('button',{name:'Timetable',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'Drivers',exact:true}).filter({has:page.locator('strong')})).toBeDisabled();
});
test('an unlinked driver is told to ask the office instead of seeing office navigation',async({page,customer})=>{
  await page.goto('/?view=drivers');await page.getByRole('button',{name:'EN',exact:true}).click();await signIn(page);
  await expect(page.getByRole('button',{name:'Sign out',exact:true})).toBeVisible();
  const script=path.resolve('tests/fixtures/identity-seed.py'),backend=path.resolve('../backend');
  const invite=JSON.parse(execFileSync('uv',['run','python',script,'invite',String(customer.tenant_id),'driver'],{cwd:backend,env:{...process.env,PYTHONPATH:backend},encoding:'utf8'})) as {token:string};
  await page.getByRole('button',{name:'Sign out',exact:true}).click();await page.goto('/accept-invitation#token='+invite.token);
  await page.getByLabel('Full name',{exact:true}).fill('Driver');await page.getByLabel('New password',{exact:true}).fill('DriverStrongPassword123!');await page.getByRole('button',{name:'Create account',exact:true}).click();
  // An unlinked driver is taken to the driver area, told to ask the office, and never sees office navigation.
  await expect(page).toHaveURL(/\/driver$/);
  await expect(page.getByRole('alert').filter({hasText:'not linked to a driver record yet'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Drivers',exact:true})).toHaveCount(0);
});
