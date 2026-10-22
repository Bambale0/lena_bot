import { expect, test } from '@playwright/test';
import path from 'node:path';
const script=path.resolve(process.cwd(),'../landing/js/kling4-studio.js');
const model='kling-4.0/reference-to-video';

test('Studio extension uploads roles, enriches both quote and launch, and restores other models',async({page})=>{
 const calls: Record<string,unknown>[]=[];
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option><option value="legacy">Legacy</option></select><textarea name="prompt" maxlength="30000">@image_1 Move gently</textarea><div data-reference-section>Generic uploader</div><div data-video-trim-row>Generic trim</div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/input.png'}}}));
 await page.route('**/api/web/generate/video**',route=>{calls.push(route.request().postDataJSON());return route.fulfill({status:202,json:{id:10,status:'processing'}});});
 await page.goto('/kling4-studio-harness');
 await page.addScriptTag({path:script});
 await page.getByLabel('Фото-референсы · до 10',{exact:true}).setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from('test')});
 await expect(page.getByText(/input.png/)).toBeVisible();
 const body={model,prompt:'@image_1 Move gently',duration:3,resolution:'720p',reference_urls:['https://media.example.test/miniapp/old.png'],video_url:'https://media.example.test/miniapp/old.mp4'};
 await page.evaluate(async body=>{await fetch('/api/web/generate/video/quote',{method:'POST',body:JSON.stringify(body)});await fetch('/api/web/generate/video',{method:'POST',body:JSON.stringify({...body,quoted_credits:85.5})});},body);
 expect(calls).toHaveLength(2);
 for(const call of calls){expect((call.kling4 as any).image_urls).toEqual(['https://media.example.test/kling4/7/input.png']);expect(call.reference_urls).toEqual([]);expect(call.video_url).toBeNull();}
 expect(calls[1].intent_id).toMatch(/^[0-9a-f-]{36}$/);
 await page.locator('[data-account-model-select]').selectOption('legacy');
 await expect(page.locator('[data-reference-section]')).toBeVisible();
 await expect(page.locator('[name=prompt]')).toHaveAttribute('maxlength','30000');
 await expect(page.getByRole('region',{name:'Материалы Kling 4'})).toBeHidden();
});

test('Studio restores an owned typed recipe with quality, duration and ordered frames',async({page})=>{
 const keyframe='kling-4.0/keyframe-to-video';
 await page.route('**/kling4-studio-harness**',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${keyframe}">Kling 4</option></select><textarea name="prompt"></textarea><select name="duration"><option>3</option><option>10</option></select><select name="resolution"><option>720p</option><option>1080p</option></select><select name="aspect_ratio"><option>auto</option></select><div data-reference-section>Generic uploader</div></form>`}));
 await page.route('**/api/web/kling4/recipe/42',route=>route.fulfill({json:{ok:true,data:{model:keyframe,prompt:'@first_frame to @last_frame',kling4:{duration:10,resolution:'1080p',first_frame_url:'https://media.example.test/kling4/7/first.png',keyframe_urls:['https://media.example.test/kling4/7/middle.png'],last_frame_url:'https://media.example.test/kling4/7/last.png'}}}}));
 await page.goto('/kling4-studio-harness?kling4_repeat=42');
 await page.addScriptTag({path:script});
 await expect(page.locator('[name=prompt]')).toHaveValue('@first_frame to @last_frame');
 await expect(page.locator('[name=duration]')).toHaveValue('10');
 await expect(page.locator('[name=resolution]')).toHaveValue('1080p');
 for(const name of ['first.png','middle.png','last.png'])await expect(page.getByText(new RegExp(name))).toBeVisible();
});

test('Studio discards media drafts when the signed-in account changes',async({page})=>{
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<script>window.state={user:{id:7}}</script><form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option></select><textarea name="prompt"></textarea><div data-reference-section></div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/private.png'}}}));
 await page.goto('/kling4-studio-harness');await page.addScriptTag({path:script});
 await page.getByLabel('Фото-референсы · до 10',{exact:true}).setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from('test')});
 await expect(page.getByText(/private.png/)).toBeVisible();
 await page.evaluate(()=>{(window as any).state.user.id=8;document.dispatchEvent(new Event('change'));});
 await expect(page.getByText(/private.png/)).toHaveCount(0);
});

test('Studio stops a private multi-file batch when the account changes',async({page})=>{
 let requests=0;
 let release: ()=>void=()=>{};
 const pending=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<script>window.state={user:{id:7}}</script><form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option></select><textarea name="prompt"></textarea><div data-reference-section></div></form>`}));
 await page.route('**/api/web/kling4/assets',async route=>{requests++;expect(route.request().postData()).toContain('name="owner_id"');await pending;try{await route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/private.png'}}});}catch{/* Account change aborts the active upload. */}});
 await page.goto('/kling4-studio-harness');await page.addScriptTag({path:script});
 await page.getByLabel('Фото-референсы · до 10',{exact:true}).setInputFiles(['first.png','second.png'].map(name=>({name,mimeType:'image/png',buffer:Buffer.from('private')})));
 await expect.poll(()=>requests).toBe(1);
 await page.evaluate(()=>{(window as any).state.user.id=8;document.dispatchEvent(new Event('change'));});release();
 await expect(page.getByLabel('Фото-референсы · до 10',{exact:true})).toBeEnabled();
 expect(requests).toBe(1);
 await expect(page.getByText(/private.png/)).toHaveCount(0);
});

test('Failed Kling repeat does not block another model quote',async({page})=>{
 await page.route('**/kling4-studio-harness**',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="legacy">Legacy</option></select><textarea name="prompt"></textarea></form>`}));
 await page.route('**/api/web/kling4/recipe/42',route=>route.fulfill({status:404,json:{ok:false,error:'Recipe unavailable'}}));
 await page.route('**/api/web/generate/video/quote',route=>route.fulfill({json:{cost_credits:1}}));
 await page.goto('/kling4-studio-harness?kling4_repeat=42');await page.addScriptTag({path:script});
 const status=await page.evaluate(async()=>{const response=await fetch('/api/web/generate/video/quote',{method:'POST',body:JSON.stringify({model:'legacy',prompt:'Scene'})});return response.status;});
 expect(status).toBe(200);
});

test('existing Studio extensions converge on H3 and allow both Kling editors',async({page})=>{
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="minimax-h3/text-to-video">H3</option><option value="${model}">Kling references</option><option value="kling-4.0/keyframe-to-video">Kling keyframes</option></select><textarea name="prompt"></textarea><label><span>Quality</span><select name="resolution"><option>2K</option></select></label><select name="duration"><option>6</option></select><select name="aspect_ratio"><option>adaptive</option></select><div data-reference-section></div><div data-optional-section><div class="composer-disclosure-body"></div></div></form>`}));
 await page.goto('/kling4-studio-harness');
 // Stop a broken observer from starving the browser; the assertion still fails.
 await page.evaluate(()=>{const Native=window.MutationObserver;(window as any).observerLoops=0;window.MutationObserver=class extends Native{constructor(callback:MutationCallback){let count=0;super((records,observer)=>{if(++count>50){(window as any).observerLoops++;observer.disconnect();return;}callback(records,observer);});}};});
 for(const file of ['minimax-h3-studio.js','seedance25-studio.js','kling4-studio.js'])await page.addScriptTag({path:path.resolve(process.cwd(),'../landing/js',file)});
 await expect.poll(()=>page.evaluate(()=>(window as any).observerLoops)).toBe(0);
 await page.locator('[data-account-model-select]').selectOption(model);
 await expect(page.getByLabel('Фото-референсы · до 10',{exact:true})).toBeVisible();
 await page.locator('[data-account-model-select]').selectOption('kling-4.0/keyframe-to-video');
 await expect(page.getByLabel('Первый кадр',{exact:true})).toBeVisible();
 expect(await page.evaluate(()=>(window as any).observerLoops)).toBe(0);
});
