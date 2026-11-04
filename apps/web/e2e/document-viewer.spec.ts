import {test,expect,Page} from '@playwright/test';
async function register(page:Page){
 await page.goto('/register');
 await page.getByLabel('Your name').fill('Reader Tester');
 await page.getByLabel('Email address').fill(`reader-${Date.now()}-${Math.random().toString(36).slice(2)}@example.test`);
 await page.getByLabel('Password',{exact:true}).fill('Reader-test-password-2026');
 await page.getByRole('button',{name:'CREATE YOUR VAULT'}).click();
 await page.getByRole('button',{name:'ENTER YOUR VAULT'}).click();
 await expect(page.getByRole('heading',{name:/GOOD TO HAVE/})).toBeVisible();
}
async function upload(page:Page,name:string,buffer:Buffer,mimeType:string){
 await page.getByRole('button',{name:'ADD MEMORY',exact:true}).click();
 const completed=page.waitForResponse(r=>r.url().endsWith('/uploads')&&r.request().method()==='POST');
 await page.getByLabel('Choose files').setInputFiles({name,mimeType,buffer});
 const response=await completed;expect(response.status()).toBe(201);
 const doc=await response.json();
 await page.getByRole('dialog').getByRole('button',{name:'Close dialog'}).click();
 await page.goto('/app/vault');await page.getByRole('button',{name:new RegExp(name.replace('.','\\.'))}).first().click();
 return doc;
}
test('complete long text has original view, final section and safe metadata editing',async({page})=>{
 await register(page);
 const text='FIRST BOOK SECTION\n'+'memory knowledge '.repeat(24000)+'\nFINAL COMPLETE BOOK ORCHID';
 const doc=await upload(page,'complete-book.txt',Buffer.from(text),'text/plain');
 const reader=page.getByRole('region',{name:'Document reader'});
 await expect(reader.getByRole('tab',{name:'Original',exact:true})).toHaveAttribute('aria-selected','true');
 await expect(page.getByTestId('original-file-frame')).toBeVisible();
 const original=await page.request.get(`/api/v1/documents/${doc.id}/original`,{headers:{Range:'bytes=0-10'}});
 expect(original.status()).toBe(206);expect((await original.body()).toString()).toBe(text.slice(0,11));
 expect(original.headers()['x-frame-options']).toBe('SAMEORIGIN');
 await reader.getByRole('tab',{name:'Extracted text',exact:true}).click();
 await expect(reader.getByLabel('Extracted document text')).toContainText('FIRST BOOK SECTION');
 await reader.getByRole('button',{name:'LAST SECTION',exact:true}).click();
 await expect(reader.getByLabel('Extracted document text')).toContainText('FINAL COMPLETE BOOK ORCHID');
 const dialog=page.getByRole('dialog');
 await expect(dialog.getByRole('button',{name:'SAVE CHANGES',exact:true})).toHaveCount(1);
 await dialog.getByLabel('Title',{exact:true}).fill('Renamed complete book');
 const saved=page.waitForResponse(r=>r.url().endsWith('/documents/'+doc.id)&&r.request().method()==='PATCH');
 await dialog.getByRole('button',{name:'SAVE CHANGES',exact:true}).click();expect((await saved).status()).toBe(200);
 await expect(dialog.getByRole('heading',{name:'Renamed complete book'})).toBeVisible();
 await expect(reader.getByText('48,007 extracted words',{exact:true})).toBeVisible();
 await reader.getByRole('button',{name:'LAST SECTION',exact:true}).click();
 await expect(reader.getByLabel('Extracted document text')).toContainText('FINAL COMPLETE BOOK ORCHID');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
 await page.screenshot({path:'../../docs/screenshots/document-reader-mobile.png'});
});
test('PowerPoint uploads show a private original-layout preview and slide text',async({page})=>{
 test.setTimeout(240000);
 await register(page);
 await page.getByRole('button',{name:'ADD MEMORY',exact:true}).click();
 const completed=page.waitForResponse(r=>r.url().endsWith('/uploads')&&r.request().method()==='POST');
 await page.getByLabel('Choose files').setInputFiles('e2e/fixtures/complete-slides.pptx');
 const response=await completed;expect(response.status()).toBe(201);const doc=await response.json();
 await page.getByRole('dialog').getByRole('button',{name:'Close dialog'}).click();
 await page.goto('/app/vault');await page.getByRole('button',{name:/complete-slides.pptx/}).first().click();
 await expect(page.getByTestId('original-file-frame')).toBeVisible({timeout:210000});
 const preview=await page.request.get(`/api/v1/documents/${doc.id}/preview`,{headers:{Range:'bytes=0-4'}});
 expect(preview.status()).toBe(206);expect((await preview.body()).toString()).toBe('%PDF-');
 expect(preview.headers()['x-frame-options']).toBe('SAMEORIGIN');
 await page.getByTestId('original-file-frame').scrollIntoViewIfNeeded();
 await page.screenshot({path:'../../docs/screenshots/powerpoint-original.png'});
 await page.getByRole('tab',{name:'Extracted text',exact:true}).click();
 await expect(page.getByLabel('Extracted document text')).toContainText('FINAL SLIDE SOLAR BATTERY');
 await page.screenshot({path:'../../docs/screenshots/powerpoint-reader.png'});
});
