import {test, expect, Page} from '@playwright/test';
const password='MemoryVault-browser-test-2026';
async function register(page:Page){
  const email=`browser-${Date.now()}-${Math.random().toString(36).slice(2)}@example.test`;
  await page.goto('/register');
  await page.getByLabel('Your name').fill('Browser Tester');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'CREATE YOUR VAULT'}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button',{name:'ENTER YOUR VAULT'}).click();
  await expect(page.getByRole('heading',{name:/GOOD TO HAVE/})).toBeVisible();
  return email;
}
async function createNote(page:Page,title:string,content:string){
  await page.goto('/app/vault');
  await page.getByRole('button',{name:'NEW NOTE',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Title',{exact:true}).fill(title);
  await dialog.getByRole('textbox',{name:'Your note'}).fill(content);
  await dialog.getByLabel('Tags, separated by commas').fill('research,solar');
  await dialog.getByRole('button',{name:'SAVE NOTE',exact:true}).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText(title,{exact:true})).toBeVisible();
}

test('landing navigation, knowledge interaction and reduced-motion mobile layout',async({page})=>{
  await page.setViewportSize({width:1280,height:1120});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:/YOUR KNOWLEDGE/})).toBeVisible();
  await expect(page.locator('body')).not.toHaveText(/Application error/);
  const connect=page.getByRole('tab',{name:'02 Connect',exact:true});
  await connect.click();
  await expect(connect).toHaveAttribute('aria-selected','true');
  await page.screenshot({path:'../../docs/screenshots/landing-desktop.png',fullPage:false});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('heading',{name:/YOUR KNOWLEDGE/})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await page.screenshot({path:'../../docs/screenshots/landing-mobile.png',fullPage:false});
  await page.getByRole('link',{name:'BUILD YOUR SECOND BRAIN',exact:true}).first().click();
  await expect(page.getByLabel('Email address')).toBeVisible();
});

test('register, persist profile, logout and log back in',async({page})=>{
  const email=await register(page);
  await page.goto('/app/settings');
  await expect(page.getByLabel('Email',{exact:true})).toHaveValue(email);
  await page.getByRole('button',{name:'SIGN OUT',exact:true}).last().click();
  await expect(page.getByLabel('Email address')).toBeVisible();
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'OPEN YOUR VAULT'}).click();
  await expect(page.getByRole('heading',{name:/GOOD TO HAVE/})).toBeVisible();
});

test('create, search, edit, retrieve sources, then delete a note',async({page})=>{
  await register(page);
  await createNote(page,'Solar field journal','Solar panels convert sunlight into electrical energy. Photon capture is useful.');
  await page.goto('/app/search');
  await page.getByRole('textbox',{name:'Search query'}).fill('Photon');
  await page.getByRole('button',{name:'SEARCH',exact:true}).click();
  await page.getByRole('button',{name:/Solar field journal/}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('textbox',{name:'Markdown note'}).fill('Wind turbines turn moving air into electrical energy. Aerodynamic lift is useful.');
  await dialog.getByRole('button',{name:'SAVE CHANGES'}).click();
  await dialog.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.getByRole('textbox',{name:'Search query'}).fill('Aerodynamic');
  await page.getByRole('button',{name:'SEARCH',exact:true}).click();
  await expect(page.getByRole('button',{name:/Solar field journal/})).toBeVisible();
  await page.goto('/app/chat');
  await page.getByRole('textbox',{name:'Ask a question'}).fill('How do wind turbines produce electrical energy?');
  await page.getByRole('button',{name:'Send question'}).click();
  await expect(page.getByText(/Retrieval-only mode:/)).toBeVisible();
  await expect(page.getByRole('button',{name:/Solar field journal/})).toBeVisible();
  await page.getByRole('button',{name:/Solar field journal/}).click();

  await dialog.getByRole('button',{name:'DELETE MEMORY',exact:true}).click();
  await dialog.getByRole('button',{name:'PERMANENTLY DELETE',exact:true}).click();
  await expect(dialog).toBeHidden();
  await page.goto('/app/search');
  await page.getByRole('textbox',{name:'Search query'}).fill('Aerodynamic');
  await page.getByRole('button',{name:'SEARCH',exact:true}).click();
  await expect(page.getByRole('heading',{name:'NO MATCHES YET.'})).toBeVisible();
});

test('collection membership and private ZIP export',async({page})=>{
  await register(page);
  await createNote(page,'Collected memory','This is a persistent source about renewable energy.');
  await page.goto('/app/collections');
  await page.getByRole('button',{name:'NEW COLLECTION',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Name',{exact:true}).fill('Energy research');
  await page.getByRole('dialog').getByRole('button',{name:'CREATE COLLECTION'}).click();
  await page.goto('/app/vault');
  await page.getByRole('button',{name:/Collected memory/}).click();
  await page.getByRole('dialog').getByLabel('Energy research').check();
  await page.getByRole('dialog').getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.getByRole('combobox',{name:'Collection filter'}).selectOption({label:'Energy research'});
  await expect(page.getByText('Collected memory',{exact:true})).toBeVisible();
  const download=page.waitForEvent('download');
  await page.goto('/app/settings');
  await page.getByRole('link',{name:/EXPORT/}).click();
  expect((await download).suggestedFilename()).toBe('memoryvault-export.zip');
});

test('keyboard command search and mobile workspace remain usable',async({page})=>{
  await register(page);
  await page.keyboard.press('Control+k');
  await expect(page.getByRole('dialog',{name:'FIND YOUR WAY'})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await expect.poll(async()=>{const box=await page.locator('.sidebar').boundingBox();return box ? box.x+box.width : 0}).toBeLessThanOrEqual(0);
  await page.screenshot({path:'../../docs/screenshots/mobile-workspace.png',fullPage:true});
});

test('upload a real PDF, wait for processing, search and open page citation',async({page})=>{
  await register(page);
  await page.getByRole('button',{name:'ADD MEMORY',exact:true}).click();
  const completed=page.waitForResponse(response=>response.url().endsWith('/uploads') && response.request().method()==='POST');
  await page.getByLabel('Choose files').setInputFiles('e2e/fixtures/photosynthesis.pdf');
  expect((await completed).status()).toBe(201);
  await page.getByRole('dialog').getByRole('button',{name:'Close dialog'}).click();
  await page.goto('/app/search');
  await page.getByRole('textbox',{name:'Search query'}).fill('Photosynthesis');
  await page.getByRole('button',{name:'SEARCH',exact:true}).click();
  const source=page.getByRole('button',{name:/photosynthesis.pdf.*PAGE 1/});
  await expect(source).toBeVisible();
  await source.click();
  await page.getByRole('tab',{name:'Extracted text',exact:true}).click();
  await expect(page.getByRole('dialog').getByText(/Photosynthesis converts sunlight/)).toBeVisible();
});

test('two browser accounts cannot retrieve each others private source',async({page,browser})=>{
  await register(page);
  await createNote(page,'Private quantum journal','Quantum coherence is private research for account one.');
  const first=await page.request.get('/api/v1/documents');
  const id=(await first.json()).items[0].id;
  const secondContext=await browser.newContext({baseURL:'http://127.0.0.1:3100'});
  const second=await secondContext.newPage();
  try{
    await register(second);
    const response=await second.request.get('/api/v1/documents/'+id);
    expect(response.status()).toBe(404);
    await second.goto('/app/search');
    await second.getByRole('textbox',{name:'Search query'}).fill('Quantum');
    await second.getByRole('button',{name:'SEARCH',exact:true}).click();
    await expect(second.getByRole('heading',{name:'NO MATCHES YET.'})).toBeVisible();
  }finally{await secondContext.close()}
});

test('streamed provider failure is visible and creates no fake completed answer',async({page})=>{
  await register(page);
  await createNote(page,'Failure source','Neural network notes are used to check an unavailable provider.');
  await page.goto('/app/chat');
  await page.route('**/api/v1/chat/stream',route=>route.fulfill({status:200,contentType:'text/event-stream',body:'event: error\ndata: {"message":"Test provider unavailable","status":502}\n\n'}));
  await page.getByRole('textbox',{name:'Ask a question'}).fill('Explain neural networks');
  await page.getByRole('button',{name:'Send question'}).click();
  await expect(page.getByRole('alert').filter({hasText:'Test provider unavailable'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Send question'})).toBeEnabled();
  expect((await (await page.request.get('/api/v1/conversations')).json()).length).toBe(0);
});

test('manual knowledge connections persist and can be removed without deleting sources',async({page})=>{
  await register(page);
  await createNote(page,'Energy foundations','Solar radiation provides energy for ecosystems.');
  await createNote(page,'Energy applications','Solar panels are an application of photoelectric energy conversion.');
  await page.goto('/app/graph');
  await page.getByRole('combobox',{name:'From memory',exact:true}).selectOption({label:'Energy foundations'});
  await page.getByRole('combobox',{name:'To memory',exact:true}).selectOption({label:'Energy applications'});
  await page.getByRole('combobox',{name:'Relationship',exact:true}).selectOption('prerequisite');
  await page.getByLabel('Why are they connected? (optional)').fill('Read the foundations before the application.');
  await page.getByRole('button',{name:'SAVE CONNECTION'}).click();
  await expect(page.getByText('Connection saved. You can remove it any time.')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Read the foundations before the application.')).toBeVisible();
  await page.getByRole('button',{name:'Remove connection from Energy foundations to Energy applications'}).click();
  await expect(page.getByText('Connection removed. Both memories remain in your vault.')).toBeVisible();
  const documents=await (await page.request.get('/api/v1/documents')).json();
  expect(documents.total).toBe(2);
});

test('note autosave persists and keeps a conflicting draft intact',async({page})=>{
  await register(page);
  await createNote(page,'Autosave notebook','This source starts with a first thought.');
  await page.getByRole('button',{name:/Autosave notebook/}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('textbox',{name:'Markdown note'}).fill('This thought was written without clicking save.');
  await expect(dialog.locator('.autosave-status')).toContainText('Saved');
  const documents=await (await page.request.get('/api/v1/documents')).json();
  const id=documents.items[0].id;
  const source=await (await page.request.get('/api/v1/documents/'+id)).json();
  expect(source.content).toBe('This thought was written without clicking save.');
  const auth=await (await page.request.get('/api/v1/auth/me')).json();
  const changed=await page.request.patch('/api/v1/documents/'+id,{headers:{'X-CSRF-Token':auth.csrf},data:{title:source.title,content:'A different tab saved this version.',tags:source.tags,version:source.version}});
  expect(changed.status()).toBe(200);
  await dialog.getByRole('textbox',{name:'Markdown note'}).fill('Keep this unsaved local draft.');
  await expect(dialog.getByRole('alert')).toContainText('draft');
  await expect(dialog.getByRole('textbox',{name:'Markdown note'})).toHaveValue('Keep this unsaved local draft.');
});

test('private profile photo and notification choices persist',async({page})=>{
  await register(page);
  await createNote(page,'A profile memory','This memory produces a genuine processing notification.');
  await page.goto('/app/settings');
  await expect(page.getByRole('button',{name:'UPLOAD PHOTO',exact:true})).toBeEnabled();
  await page.getByLabel('Choose profile photo').setInputFiles('e2e/fixtures/portrait.png');
  await expect(page.getByText('Profile photo saved.',{exact:true})).toBeVisible();
  const portrait=page.getByRole('img',{name:'Browser Tester profile photo',exact:true});
  await expect(portrait).toBeVisible();
  await expect.poll(()=>portrait.evaluate(image=>(image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator('.sidebar .profile-portrait img')).toBeVisible();
  await page.getByLabel('Interests, separated by commas').fill('Solar, Research');
  await page.getByRole('combobox',{name:'Primary use',exact:true}).selectOption('Researcher');
  await page.getByRole('button',{name:'SAVE PREFERENCES',exact:true}).click();
  await expect.poll(async()=> (await (await page.request.get('/api/v1/auth/me')).json()).user.preferences.interests).toEqual(['solar','research']);
  await page.getByLabel('Processing updates').uncheck();
  await page.getByRole('button',{name:'SAVE NOTIFICATION PREFERENCES'}).click();
  await expect.poll(async()=> (await (await page.request.get('/api/v1/notification-preferences')).json()).processing).toBe(false);
  await page.reload();
  await expect(page.getByLabel('Processing updates')).not.toBeChecked();
  await expect(portrait).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await page.getByRole('button',{name:'REMOVE PHOTO'}).click();
  await expect(page.getByText('Profile photo removed.',{exact:true})).toBeVisible();
  expect((await page.request.get('/api/v1/profile/photo')).status()).toBe(404);
});

test('reminders can be scheduled, rescheduled, completed and deleted',async({page})=>{
  await register(page);
  await createNote(page,'Remember this idea','Revisit this source before the next study session.');
  await page.getByRole('button',{name:'Notifications',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'WHAT’S NEW'});
  await dialog.getByLabel('Reminder title').fill('Review the source');
  await dialog.getByRole('combobox',{name:'Reminder memory',exact:true}).selectOption({label:'Remember this idea'});
  await dialog.getByRole('button',{name:'SCHEDULE REMINDER',exact:true}).click();
  await expect(dialog.getByText('Reminder scheduled.',{exact:true})).toBeVisible();
  let reminders=await (await page.request.get('/api/v1/reminders')).json();
  expect(reminders).toHaveLength(1);
  expect(reminders[0].document_id).toBeTruthy();
  const firstDue=reminders[0].due_at;
  await dialog.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.reload();
  await page.getByRole('button',{name:'Notifications',exact:true}).click();
  await dialog.getByRole('button',{name:'Reschedule: Review the source',exact:true}).click();
  const nextTime=await page.evaluate(()=>{const d=new Date(Date.now()+2*86400000);const pad=(n:number)=>String(n).padStart(2,'0');return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`});
  await dialog.getByLabel('Reminder date and time').fill(nextTime);
  await dialog.getByRole('button',{name:'RESCHEDULE REMINDER',exact:true}).click();
  await expect(dialog.getByText('Reminder rescheduled.',{exact:true})).toBeVisible();
  reminders=await (await page.request.get('/api/v1/reminders')).json();
  expect(reminders[0].due_at).not.toBe(firstDue);
  await page.setViewportSize({width:390,height:844});
  expect(await dialog.evaluate(node=>node.scrollWidth<=node.clientWidth+1)).toBeTruthy();
  await page.screenshot({path:'../../docs/screenshots/reminders-mobile.png',fullPage:false});
  await dialog.getByRole('button',{name:'Mark done: Review the source',exact:true}).click();
  await expect(dialog.getByText('Reminder marked done.',{exact:true})).toBeVisible();
  await dialog.getByText('Completed reminders (1)',{exact:true}).click();
  await dialog.getByRole('button',{name:'Delete completed reminder: Review the source',exact:true}).click();
  await expect(dialog.getByText('Reminder deleted.',{exact:true})).toBeVisible();
  expect(await (await page.request.get('/api/v1/reminders')).json()).toEqual([]);
});

test('analytics counts real activity and recall explains and remembers dismissals',async({page})=>{
  await register(page);
  for(const title of ['Foundational idea','Next idea','Third idea','Latest idea'])await createNote(page,title,'Solar energy is connected to research on renewable resources.');
  await page.getByRole('button',{name:/Foundational idea/}).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('dialog').getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.goto('/app/analytics');
  await expect(page.getByRole('heading',{name:'YOUR DAILY RHYTHM'})).toBeVisible();
  const data=await (await page.request.get('/api/v1/analytics?days=30')).json();
  expect(data.totals.memories).toBe(4);
  expect(data.activity.reduce((sum:number,day:{visits:number})=>sum+day.visits,0)).toBe(1);
  await page.getByRole('button',{name:'Memories opened',exact:true}).click();
  await expect(page.getByText('memories opened over 30 days',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'90 DAYS',exact:true}).click();
  await expect(page.getByText('memories opened over 90 days',{exact:true})).toBeVisible();
  await page.getByText('View daily totals as a table',{exact:true}).click();
  await expect(page.getByRole('table')).toBeVisible();
  await page.getByText('View daily totals as a table',{exact:true}).click();
  await page.setViewportSize({width:1280,height:1000});
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(0);
  await page.screenshot({path:'../../docs/screenshots/analytics-desktop.png',fullPage:true,animations:'disabled'});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await expect.poll(async()=>{const box=await page.locator('.sidebar').boundingBox();return box ? box.x+box.width : 0}).toBeLessThanOrEqual(0);
  await page.screenshot({path:'../../docs/screenshots/analytics-mobile.png',fullPage:true,animations:'disabled'});
  await page.goto('/app/recall');
  const card=page.getByRole('article').filter({has:page.getByRole('heading',{name:'Foundational idea',exact:true})});
  await expect(card.getByText(/Shares tags with your three newest memories/)).toBeVisible();
  await card.getByRole('button',{name:'DISMISS',exact:true}).click();
  await page.reload();
  await expect(page.getByRole('heading',{name:'LET YOUR KNOWLEDGE GROW.'})).toBeVisible();
});
