import { expect, test } from '@playwright/test';
import path from 'node:path';
const script=path.resolve(process.cwd(),'../landing/js/kling4-studio.js');
const model='kling-4.0/reference-to-video';

test('Studio extension uploads roles, enriches both quote and launch, and restores other models',async({page})=>{
 const calls: Record<string,unknown>[]=[];
 await page.route('**/kling4-studio-harness',route=>route.fulfill({contentType:'text/html',body:`<form class="account-composer"><select data-account-model-select><option value="${model}">Kling 4</option><option value="legacy">Legacy</option></select><textarea name="prompt">@image_1 Move gently</textarea><div data-reference-section>Generic uploader</div><div data-video-trim-row>Generic trim</div></form>`}));
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kling4/7/input.png'}}}));
 await page.route('**/api/web/generate/video**',route=>{calls.push(route.request().postDataJSON());return route.fulfill({status:202,json:{id:10,status:'processing'}});});
 await page.goto('/kling4-studio-harness');
 await page.addScriptTag({path:script});
 await page.getByLabel('Фото-референсы · до 10',{exact:true}).setInputFiles({name:'photo.png',mimeType:'image/png',buffer:Buffer.from('test')});
 await expect(page.getByText(/input.png/)).toBeVisible();
 const body={model,prompt:'@image_1 Move gently',duration:3,resolution:'720p'};
 await page.evaluate(async body=>{await fetch('/api/web/generate/video/quote',{method:'POST',body:JSON.stringify(body)});await fetch('/api/web/generate/video',{method:'POST',body:JSON.stringify({...body,quoted_credits:85.5})});},body);
 expect(calls).toHaveLength(2);
 for(const call of calls)expect((call.kling4 as any).image_urls).toEqual(['https://media.example.test/kling4/7/input.png']);
 expect(calls[1].intent_id).toMatch(/^[0-9a-f-]{36}$/);
 await page.locator('[data-account-model-select]').selectOption('legacy');
 await expect(page.locator('[data-reference-section]')).toBeVisible();
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
