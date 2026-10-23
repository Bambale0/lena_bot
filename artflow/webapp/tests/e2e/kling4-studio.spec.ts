import { expect, test } from '@playwright/test';
import path from 'node:path';
const script=path.resolve(process.cwd(),'../landing/js/kling4-studio.js');
const model='kling-4.0/reference-to-video';

test('Studio extension uploads roles, enriches both quote and launch, and restores other models',async({page})=>{
 const calls: Record<string,unknown>[]=[];
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option><option value="legacy">Legacy</option></select><textarea name="prompt" maxlength="30000">@image_1 Move gently</textarea><div data-reference-section>Generic uploader</div><div data-video-trim-row>Generic trim</div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/input.png',kind:'image'}}}));
 await page.route('**/api/web/generate/video**',route=>{calls.push(route.request().postDataJSON());return route.fulfill({status:202,json:{id:10,status:'processing'}});});
 await page.goto('/kling4-studio-harness');
 await page.addScriptTag({path:script});
 await page.getByLabel('Референсы · фото, видео, аудио',{exact:true}).setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from('test')});
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
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/private.png',kind:'image'}}}));
 await page.goto('/kling4-studio-harness');await page.addScriptTag({path:script});
 await page.getByLabel('Референсы · фото, видео, аудио',{exact:true}).setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from('test')});
 await expect(page.getByText(/private.png/)).toBeVisible();
 await page.evaluate(()=>{(window as any).state.user.id=8;document.dispatchEvent(new Event('change'));});
 await expect(page.getByText(/private.png/)).toHaveCount(0);
});

test('Studio stops a private multi-file batch when the account changes',async({page})=>{
 let requests=0;
 let release: ()=>void=()=>{};
 const pending=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<script>window.state={user:{id:7}}</script><form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option></select><textarea name="prompt"></textarea><div data-reference-section></div></form>`}));
 await page.route('**/api/web/kling4/assets',async route=>{requests++;expect(route.request().postData()).toContain('name="owner_id"');await pending;try{await route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/private.png',kind:'image'}}});}catch{/* Account change aborts the active upload. */}});
 await page.goto('/kling4-studio-harness');await page.addScriptTag({path:script});
 await page.getByLabel('Референсы · фото, видео, аудио',{exact:true}).setInputFiles(['first.png','second.png'].map(name=>({name,mimeType:'image/png',buffer:Buffer.from('private')})));
 await expect.poll(()=>requests).toBe(1);
 await page.evaluate(()=>{(window as any).state.user.id=8;document.dispatchEvent(new Event('change'));});release();
 await expect(page.getByLabel('Референсы · фото, видео, аудио',{exact:true})).toBeEnabled();
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

test('existing Studio extensions converge and expose one new Kling reference flow',async({page})=>{
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="minimax-h3/text-to-video">H3</option><option value="${model}">Kling references</option><option value="kling-4.0/keyframe-to-video">Kling keyframes</option></select><textarea name="prompt"></textarea><label><span>Quality</span><select name="resolution"><option>2K</option></select></label><select name="duration"><option>6</option></select><select name="aspect_ratio"><option>adaptive</option></select><div data-reference-section></div><div data-optional-section><div class="composer-disclosure-body"></div></div></form>`}));
 await page.goto('/kling4-studio-harness');
 // Stop a broken observer from starving the browser; the assertion still fails.
 await page.evaluate(()=>{const Native=window.MutationObserver;(window as any).observerLoops=0;window.MutationObserver=class extends Native{constructor(callback:MutationCallback){let count=0;super((records,observer)=>{if(++count>50){(window as any).observerLoops++;observer.disconnect();return;}callback(records,observer);});}};});
 for(const file of ['minimax-h3-studio.js','seedance25-studio.js','kling4-studio.js'])await page.addScriptTag({path:path.resolve(process.cwd(),'../landing/js',file)});
 await expect.poll(()=>page.evaluate(()=>(window as any).observerLoops)).toBe(0);
 await page.locator('[data-account-model-select]').selectOption(model);
 await expect(page.getByLabel('Референсы · фото, видео, аудио',{exact:true})).toBeVisible();
 await expect(page.locator('[data-account-model-select] option[value=\"kling-4.0/keyframe-to-video\"]')).toHaveCount(0);
 expect(await page.evaluate(()=>(window as any).observerLoops)).toBe(0);
});

test('slow public landing cannot erase the already loaded private admin catalog',async({page})=>{
 let release: ()=>void=()=>{};const pending=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/kling4-catalog-harness',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));
 await page.route('**/api/web/**',async route=>{
  const pathname=new URL(route.request().url()).pathname;
  if(pathname==='/api/web/landing'){await pending;return route.fulfill({json:{ok:true,data:{models:{image:[],video:[],music:[]},examples:[],prompts:{items:[]},plans:[{id:123}]}}});}
  const data=pathname==='/api/web/me'?{id:7,credits:1000,is_admin:false}:pathname==='/api/web/models/video'?[{key:model,display_name:'Kling 4',modes:['text','image'],credits:28.5}]:pathname==='/api/web/auth/config'?{}:[];
  return route.fulfill({json:{ok:true,data}});
 });
 await page.goto('/kling4-catalog-harness');
 await page.addScriptTag({path:path.resolve(process.cwd(),'../landing/js/prototype-premium.js')});
 const keys=()=>page.evaluate(()=>((window as any).eval('state.modelsByKind.video')).map((item:any)=>item.key));
 await expect.poll(keys).toContain(model);
 const landing=page.waitForResponse('**/api/web/landing');release();await landing;
 await expect.poll(()=>page.evaluate(()=>(window as any).eval('state.plans.some(item=>item.id===123)'))).toBe(true);
 expect(await keys()).toContain(model);
 await page.evaluate(()=>(window as any).eval('clearPublicData()'));
 expect(await keys()).toContain(model);
 await page.evaluate(()=>(window as any).eval('forgetAuthSession()'));
 expect(await keys()).not.toContain(model);
});

for(const stage of ["me","models/video"])for(const nextOwner of [null,7,8])test(`late private ${stage} cannot cross logout/session change to ${nextOwner}`,async({page})=>{
 let release: ()=>void=()=>{};const pending=new Promise<void>(resolve=>{release=resolve;});let started=false;
 await page.route('**/kling4-catalog-harness',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));
 await page.route('**/api/web/**',async route=>{
  const pathname=new URL(route.request().url()).pathname;
  if(pathname==='/api/web/'+stage){started=true;await pending;}
  const data=pathname==='/api/web/me'?{id:7,credits:1000,is_admin:false}:pathname==='/api/web/models/video'?[{key:model,display_name:'Kling 4',modes:['text'],credits:28.5}]:pathname==='/api/web/landing'?{models:{image:[],video:[],music:[]},examples:[],prompts:{items:[]},plans:[]}:pathname==='/api/web/auth/config'?{}:[];
  return route.fulfill({json:{ok:true,data}});
 });
 await page.goto('/kling4-catalog-harness');await page.addScriptTag({path:path.resolve(process.cwd(),'../landing/js/prototype-premium.js')});
 await expect.poll(()=>started).toBe(true);
 await page.evaluate(next=>{(window as any).eval('forgetAuthSession()');if(next!==null)(window as any).eval(`rememberAuthSession({user:{id:${next}}})`);},nextOwner);
 const response=page.waitForResponse('**/api/web/'+stage);release();await response;
 // Wait until the stale batch has settled without granting it a current session.
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 const result=await page.evaluate(()=>(window as any).eval('({user:state.user?.id??null,owner:state.modelCatalogOwner,keys:state.models.map(item=>item.key)})'));
 expect(result.user).toBe(nextOwner);expect(result.owner).toBeNull();expect(result.keys).not.toContain(model);
});

for(const failedKind of ['image','video','music'])test(`public ${failedKind} fallback and logout DOM survive failed private category`,async({page})=>{
 let release: ()=>void=()=>{};const pending=new Promise<void>(resolve=>{release=resolve;});
 await page.route('**/kling4-catalog-harness**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body><div data-model-grid></div><select data-account-model-select></select></body></html>'}));
 await page.route('**/api/web/**',async route=>{
  const pathname=new URL(route.request().url()).pathname;
  if(pathname==='/api/web/landing'){await pending;return route.fulfill({json:{ok:true,data:{models:Object.fromEntries(['image','video','music'].map(kind=>[kind,[{key:`public-${kind}`,display_name:`Public ${kind}`,gen_type:kind,credits:1,modes:['text']}]])),examples:[],prompts:{items:[]},plans:[{id:123}]}}});}
  if(pathname==='/api/web/models/'+failedKind)return route.fulfill({status:503,json:{ok:false,error:'Private category unavailable'}});
  const data=pathname==='/api/web/me'?{id:7,credits:1000,is_admin:false}:pathname==='/api/web/models/video'?[{key:model,display_name:'Kling 4',modes:['text'],credits:28.5}]:pathname==='/api/web/models/image'?[{key:'private-image',display_name:'Private image',modes:['text'],credits:1}]:pathname==='/api/web/auth/config'?{}:[];
  return route.fulfill({json:{ok:true,data}});
 });
 await page.goto('/kling4-catalog-harness?type=video');await page.addScriptTag({path:path.resolve(process.cwd(),'../landing/js/prototype-premium.js')});
 await expect.poll(()=>page.evaluate(()=>(window as any).eval('state.modelCatalogOwner'))).toBe(7);
 release();await expect.poll(()=>page.evaluate(()=>(window as any).eval('state.plans.some(item=>item.id===123)'))).toBe(true);
 const keys=()=>page.evaluate(()=>(window as any).eval('Object.fromEntries(Object.entries(state.modelsByKind).map(([kind,items])=>[kind,items.map(item=>item.key)]))'));
 expect((await keys())[failedKind]).toContain(`public-${failedKind}`);
 if(failedKind!=='video')await expect(page.locator(`[data-account-model-select] option[value="${model}"]`)).toHaveCount(1);
 await page.evaluate(()=>(window as any).eval('forgetAuthSession()'));
 await expect(page.locator(`[data-account-model-select] option[value="${model}"]`)).toHaveCount(0);
 await expect(page.locator('[data-account-model-select] option[value="public-video"]')).toHaveCount(1);
 await expect(page.locator('[data-model-grid]')).not.toContainText('Kling 4');
 expect((await keys()).video).toEqual(['public-video']);
});

test('Studio mixed references route by server kind and retain partial batch on failure',async({page})=>{
 let uploads=0;const calls: any[]=[];
 await page.route('**/kling4-auto-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4 · Референсы</option><option value="kling-4.0/keyframe-to-video">Kling frames</option></select><textarea name="prompt"></textarea><div data-reference-section></div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>{const kind=['image','video','audio'][uploads++];return kind?route.fulfill({json:{ok:true,data:{url:`https://media.example.test/${kind}`,kind}}}):route.fulfill({status:503,json:{ok:false,error:'Upload unavailable'}});});
 await page.route('**/api/web/generate/video/quote',route=>{calls.push(route.request().postDataJSON());return route.fulfill({json:{cost_credits:85.5}});});
 await page.goto('/kling4-auto-harness');await page.addScriptTag({path:script});
 await expect(page.locator('[data-account-model-select] option[value="kling-4.0/keyframe-to-video"]')).toHaveCount(0);
 const input=page.getByLabel('Референсы · фото, видео, аудио',{exact:true});
 await input.setInputFiles(['ref.png','clip.mp4','voice.wav','fail.png'].map(name=>({name,mimeType:'application/octet-stream',buffer:Buffer.from('fixture')})));
 await expect(page.getByRole('status')).toContainText('Upload unavailable');
 await expect(page.getByText('Голос @Voice_1:',{exact:false})).toBeVisible();
 await page.evaluate(async model=>{await fetch('/api/web/generate/video/quote',{method:'POST',body:JSON.stringify({model,prompt:'Scene',duration:3,resolution:'720p'})});},model);
 expect(calls[0].kling4).toMatchObject({image_urls:['https://media.example.test/image'],video_urls:['https://media.example.test/video'],voices:[{name:'Voice_1',audio_url:'https://media.example.test/audio'}]});
});

test('Studio refuses over-limit references before upload and rejects unknown server kind',async({page})=>{
 let uploads=0;
 await page.route('**/kling4-auto-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option></select><textarea name="prompt"></textarea><div data-reference-section></div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:`https://media.example.test/${++uploads}.png`,kind:'image'}}}));
 await page.goto('/kling4-auto-harness');await page.addScriptTag({path:script});
 const input=()=>page.getByLabel('Референсы · фото, видео, аудио',{exact:true});
 await input().setInputFiles(Array.from({length:11},(_,i)=>({name:`${i}.png`,mimeType:'image/png',buffer:Buffer.from('fixture')})));
 await expect(page.getByRole('status')).toContainText('Не больше 10');expect(uploads).toBe(10);
 await page.getByRole('button',{name:'Убрать',exact:true}).first().click();
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/unknown.png'}}}));
 await input().setInputFiles({name:'unknown.png',mimeType:'image/png',buffer:Buffer.from('fixture')});
 await expect(page.getByRole('status')).toContainText('Сервер не подтвердил тип материала');
 await expect(page.getByText(/unknown.png/)).toHaveCount(0);
});

test('site catalog shows one Kling 4 while preserving legacy history routing',async({page})=>{
 await page.route('**/kling4-catalog-harness**',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body><div data-model-grid></div><select data-account-model-select></select></body></html>'}));
 await page.route('**/api/web/**',route=>{
  const pathname=new URL(route.request().url()).pathname;
  const data=pathname==='/api/web/me'?{id:7,credits:1000}:pathname==='/api/web/models/video'?[model,'kling-4.0/keyframe-to-video'].map(key=>({key,gen_type:'video',display_name:key===model?'Kling 4 · Референсы':'Kling 4 · Ключевые кадры',credits:28.5,modes:['text','image']})):pathname==='/api/web/landing'?{models:{image:[],video:[],music:[]},examples:[],prompts:{items:[]},plans:[]}:[];
  return route.fulfill({json:{ok:true,data}});
 });
 await page.goto('/kling4-catalog-harness?type=video');await page.addScriptTag({path:path.resolve(process.cwd(),'../landing/js/prototype-premium.js')});
 await expect(page.locator(`[data-account-model-select] option[value="${model}"]`)).toHaveText('Kling 4');
 await expect(page.locator('[data-account-model-select] option[value="kling-4.0/keyframe-to-video"]')).toHaveCount(0);
 await expect(page.locator('[data-model-grid]')).not.toContainText('Ключевые кадры');
 await expect(page.locator('[data-model-grid] .model-card')).toHaveCount(1);
});

test('removing optional voice audio keeps the Studio editable',async({page})=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/kling4-auto-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option></select><textarea name="prompt"></textarea><div data-reference-section></div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/voice.wav',kind:'audio'}}}));
 await page.goto('/kling4-auto-harness');await page.addScriptTag({path:script});
 await page.getByText('Персонажи и голоса',{exact:true}).click();
 await page.getByRole('button',{name:'Добавить голос',exact:true}).click();
 await page.getByLabel('Аудио Voice_1 · 5–30 сек',{exact:true}).setInputFiles({name:'voice.wav',mimeType:'audio/wav',buffer:Buffer.from('fixture')});
 await page.getByRole('button',{name:'Убрать',exact:true}).click();
 expect(errors).toEqual([]);
 await expect(page.getByLabel('Аудио Voice_1 · 5–30 сек',{exact:true})).toBeVisible();
});
