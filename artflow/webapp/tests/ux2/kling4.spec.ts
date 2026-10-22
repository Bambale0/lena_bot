import { expect, test, type Page } from '@playwright/test';
const reference='kling-4.0/reference-to-video';
const keyframe='kling-4.0/keyframe-to-video';
const models=[reference,keyframe].map(key=>({key,display_name:key===reference?'Kling 4 · Референсы':'Kling 4 · Ключевые кадры',modes:['text','image'],credits:28.5,is_per_second:true,credits_per_sec:28.5,max_refs:10,durations:Array.from({length:28},(_,i)=>i+3),resolutions:['720p','1080p'],has_quality:true,aspect_ratios:['auto','16:9','9:16','1:1','21:9']}));
async function prepare(page: Page,admin=true) {
 const posts: Record<string,unknown>[]=[];let upload=0;
 await page.addInitScript(()=>{window.Telegram={WebApp:{initData:'kling4-test',initDataUnsafe:{user:{id:123,first_name:'Tester'}},ready(){},expand(){},colorScheme:'dark',HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}} as any;});
 await page.route('**/telegram-web-app.js',route=>route.fulfill({body:'',contentType:'application/javascript'}));
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/api/v1/me')return route.fulfill({json:{id:7,tg_id:123,credits:5000,language:'ru',miniapp_ux2_available:true}});
  if(path==='/api/v1/models/image')return route.fulfill({json:[{key:'image',display_name:'Image',modes:['text'],credits:1}]});
  if(path==='/api/v1/models/video')return route.fulfill({json:admin?models:[{...models[0],key:'legacy-video',display_name:'Legacy'}]});
  if(path==='/api/web/kling4/assets')return route.fulfill({json:{ok:true,data:{url:`https://media.example.test/kling4/7/${++upload}.png`,kind:'image'}}});
  if(path==='/api/v1/generate/video/quote')return route.fulfill({json:{cost_credits:85.5,balance_credits:5000,can_run:true,output_seconds:3,reference_seconds:0,billable_seconds:3}});
  if(path==='/api/v1/generate/video'){posts.push(route.request().postDataJSON());return route.fulfill({status:202,json:{id:100,model:reference,gen_type:'video',status:'processing',credits_spent:85.5}});}
  if(path.endsWith('/auth/config'))return route.fulfill({json:{bot_username:'test_bot'}});
  return route.fulfill({json:[]});
 });
 await page.goto('/?ux=2');
 await page.getByRole('tab',{name:'Создать',exact:true}).click();
 await page.getByRole('button',{name:'Видео Из описания или ваших материалов',exact:true}).click();
 return posts;
}
test('admin reference editor sends structured materials after exact quote',async({page},info)=>{
 const posts=await prepare(page);
 await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption(reference);
 await page.getByRole('textbox',{name:/^Промпт/}).fill('@image_1 A ball moves smoothly');
 await page.getByLabel('Фото-референсы · до 10',{exact:true}).setInputFiles({name:'reference.png',mimeType:'image/png',buffer:Buffer.from('image-fixture')});
 await expect(page.getByText('1.png',{exact:false}).first()).toBeVisible();
 await page.getByRole('complementary').getByRole('button',{name:'Создать',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
 await page.getByRole('dialog').getByRole('button',{name:/Запустить за/}).click();
 await expect.poll(()=>posts.length).toBe(1);
 expect((posts[0].kling4 as any).image_urls).toEqual(['https://media.example.test/kling4/7/1.png']);
 expect(posts[0].quoted_credits).toBe(85.5);
 expect(posts[0].intent_id).toMatch(/^[0-9a-f-]{36}$/);
 await page.screenshot({path:info.outputPath('kling4-admin-reference.png'),fullPage:true});
});
test('keyframe editor exposes ordered roles and no character controls',async({page},info)=>{
 await prepare(page);
 await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption(keyframe);
 await expect(page.getByLabel('Первый кадр',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Промежуточные кадры',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Последний кадр',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Добавить элемент'})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
 await page.screenshot({path:info.outputPath('kling4-keyframes.png'),fullPage:true});
});
test('ordinary catalog does not expose Kling 4 or material controls',async({page})=>{
 await prepare(page,false);
 await expect(page.getByRole('combobox',{name:'Модель',exact:true}).locator('option')).not.toContainText(['Kling 4']);
 await expect(page.getByRole('region',{name:'Материалы Kling 4'})).toHaveCount(0);
});
