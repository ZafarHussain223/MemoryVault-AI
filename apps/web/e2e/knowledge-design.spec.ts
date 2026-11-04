import {test, expect} from '@playwright/test';

test('knowledge examples keep source context and keyboard navigation across screen sizes', async ({page}) => {
  const errors:string[]=[];
  page.on('pageerror', error=>errors.push(error.message));
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/');
  const scene=page.locator('.knowledge-canvas');
  const insight=page.getByRole('region',{name:'Example detail'});
  const capture=page.getByRole('tab',{name:'01 Capture',exact:true});
  await capture.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab',{name:'02 Connect',exact:true})).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('tabpanel',{name:'02 Connect'})).toBeFocused();
  await insight.getByRole('button',{name:'FOLLOW THE CONNECTION'}).click();
  await expect(insight.getByRole('heading',{name:'Research highlights'})).toBeVisible();
  await expect(insight).toBeFocused();
  await insight.getByRole('button',{name:'BACK TO THE EXAMPLE'}).click();
  await expect(insight).toBeFocused();
  await page.getByRole('tab',{name:'03 Recall',exact:true}).click();
  await expect(insight.getByText('What helps learning stick?')).toBeVisible();
  await insight.getByRole('button',{name:/Learning notes/}).click();
  await expect(insight.getByRole('heading',{name:'Learning notes'})).toBeVisible();
  await scene.getByRole('button',{name:/ARTICLE The art of noticing/}).click();
  await expect(capture).toHaveAttribute('aria-selected','true');
  await insight.getByRole('button',{name:'READ THE THOUGHT'}).click();
  await expect(insight.getByRole('heading',{name:'The art of noticing'})).toBeVisible();
  await expect(insight.getByText('Keep the detail that changes how you see the next problem.')).toBeVisible();
  await capture.click();
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({path:'../../docs/screenshots/knowledge-desktop.png',animations:'disabled'});
  // Visit the full page so reveal observers expose every section before the overview.
  await page.evaluate(async()=>{for(let y=0;y<document.body.scrollHeight;y+=500){window.scrollTo({top:y,behavior:'instant'});await new Promise(r=>setTimeout(r,45));}});
  await page.locator('.how-section').screenshot({path:'../../docs/screenshots/knowledge-process.png',animations:'disabled'});
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await page.screenshot({path:'../../docs/screenshots/knowledge-full-page.png',fullPage:true,animations:'disabled'});
  for(const width of [768,390,375]){
    await page.setViewportSize({width,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
    await expect(scene.getByRole('button',{name:/ARTICLE The art of noticing/})).toBeVisible();
    if(width===390){await scene.screenshot({path:'../../docs/screenshots/knowledge-mobile-detail.png',animations:'disabled'});}
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/register');
  await expect(page.getByLabel('Your name')).toBeEnabled();
  await page.screenshot({path:'../../docs/screenshots/knowledge-register.png',animations:'disabled'});
  await page.getByRole('link',{name:'MemoryVault home'}).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link',{name:'BACK TO HOME'})).toBeFocused();
  expect(errors).toEqual([]);
});

test('knowledge cursor, scroll colour fill and motion preferences behave consistently',async({page})=>{
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/');
  const cursor=page.locator('.knowledge-cursor-layer');
  const begin=page.getByRole('link',{name:'BUILD YOUR SECOND BRAIN',exact:true}).first();
  await begin.hover();
  await expect(cursor).toHaveClass(/knowledge-cursor-visible/);
  await expect(cursor.locator('.knowledge-cursor-label')).toHaveText('BEGIN');
  await expect(cursor).toHaveClass(/knowledge-cursor-light/);
  await page.mouse.down();
  await expect(cursor.locator('.knowledge-cursor-ripple')).toHaveClass(/ink-click/);
  // Release away from the link to inspect feedback without navigating.
  await page.mouse.move(760,190);await page.mouse.up();
  await begin.hover();
  await page.screenshot({path:'../../docs/screenshots/knowledge-cursor.png',animations:'disabled'});
  await page.keyboard.press('Tab');
  await expect(page.locator('body')).not.toHaveClass(/knowledge-cursor-on/);
  const story=page.locator('.knowledge-story');
  const before=await story.evaluate(el=>Number((el as HTMLElement).style.getPropertyValue('--story-progress')));
  await story.evaluate(el=>window.scrollTo({top:el.getBoundingClientRect().top+scrollY+80,behavior:'instant'}));
  await expect.poll(()=>story.evaluate(el=>Number((el as HTMLElement).style.getPropertyValue('--story-progress')))).toBeGreaterThan(before+.4);
  await story.screenshot({path:'../../docs/screenshots/knowledge-story.png',animations:'disabled'});
  await page.getByRole('button',{name:'Turn animations off'}).click();
  await expect(page.locator('html')).toHaveAttribute('data-motion','off');
  await expect.poll(()=>story.evaluate(el=>el.style.getPropertyValue('--story-progress'))).toBe('1');
  await expect(cursor).toBeHidden();
  await page.reload();
  await expect(page.getByRole('button',{name:'Turn animations on'})).toBeVisible();
  await page.getByRole('button',{name:'Turn animations on'}).click();
  await page.emulateMedia({reducedMotion:'reduce'});
  await expect(page.getByRole('button',{name:'Reduced motion follows your device settings'})).toBeDisabled();
  await expect(cursor).toBeHidden();
  await page.emulateMedia({reducedMotion:'no-preference'});
  await expect(page.getByRole('button',{name:'Turn animations off'})).toBeEnabled();
  await begin.scrollIntoViewIfNeeded();
  await page.mouse.move(10,10);
  await begin.hover();
  await expect(cursor).toHaveClass(/knowledge-cursor-visible/);
  await begin.click();
  await expect(page.getByLabel('Email address')).toBeEnabled();
  await expect(page.locator('body')).not.toHaveClass(/knowledge-cursor-on/);
  await page.getByLabel('Email address').hover();
  expect(await page.getByLabel('Email address').evaluate(el=>getComputedStyle(el).cursor)).not.toBe('none');
});


test('custom cursor remains at the stationary pointer through wheel scrolling', async ({page}) => {
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Turn animations off'})).toBeEnabled();
  const cursor=page.locator('.knowledge-cursor-layer');
  const point=cursor.locator('.knowledge-cursor-point');
  await page.mouse.move(720,450);
  await expect(cursor).toHaveClass(/knowledge-cursor-visible/);
  const pointPosition=await point.evaluate(el=>(el as HTMLElement).style.transform);
  const startingScroll=await page.evaluate(()=>scrollY);
  // A wheel scroll does not move the pointer. It must not restore the native cursor.
  await page.mouse.wheel(0,600);
  await expect.poll(()=>page.evaluate(()=>scrollY)).toBeGreaterThan(startingScroll+200);
  await expect(cursor).toHaveClass(/knowledge-cursor-visible/);
  await expect(page.locator('body')).toHaveClass(/knowledge-cursor-on/);
  expect(await point.evaluate(el=>(el as HTMLElement).style.transform)).toBe(pointPosition);
  await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
  await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(0);
  await expect(cursor).toHaveClass(/knowledge-cursor-visible/);
  // Keyboard navigation must stay in native-cursor mode even if the page scrolls.
  await page.keyboard.press('Tab');
  await expect(cursor).not.toHaveClass(/knowledge-cursor-visible/);
  await page.evaluate(()=>window.scrollTo({top:500,behavior:'instant'}));
  await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(500);
  await expect(page.locator('body')).not.toHaveClass(/knowledge-cursor-on/);
  await page.mouse.move(721,450);
  await expect(cursor).toHaveClass(/knowledge-cursor-visible/);
  await page.emulateMedia({reducedMotion:'reduce'});
  await expect(cursor).toBeHidden();
  await page.mouse.wheel(0,300);
  await expect(page.locator('body')).not.toHaveClass(/knowledge-cursor-on/);
});
