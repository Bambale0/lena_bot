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
 await page.getByLabel('Референсы · фото, видео, аудио',{exact:true}).setInputFiles({name:'reference.png',mimeType:'image/png',buffer:Buffer.from('image-fixture')});
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
test('new orders show one Kling 4 and automatic references only',async({page},info)=>{
 await prepare(page);
 const select=page.getByRole('combobox',{name:'Модель',exact:true});
 await select.selectOption(reference);
 await expect(select.locator(`option[value="${keyframe}"]`)).toHaveCount(0);
 await expect(select.locator(`option[value="${reference}"]`)).toHaveText(/^Kling 4 ·/);
 await expect(page.getByLabel('Референсы · фото, видео, аудио',{exact:true})).toBeAttached();
 await expect(page.getByLabel('Первый кадр',{exact:true})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
 await page.screenshot({path:info.outputPath('kling4-unified.png'),fullPage:true});
});
test('ordinary catalog does not expose Kling 4 or material controls',async({page})=>{
 await prepare(page,false);
 await expect(page.getByRole('combobox',{name:'Модель',exact:true}).locator('option')).not.toContainText(['Kling 4']);
 await expect(page.getByRole('region',{name:'Материалы Kling 4'})).toHaveCount(0);
});

test('parked generic media and Omni IDs do not block Kling quote confirmation',async({page})=>{
 await page.addInitScript(()=>{
  sessionStorage.setItem('apix:ux2:drafts:v1:7',JSON.stringify({version:1,owner:7,drafts:{video:{kind:'video',model:'kling-4.0/reference-to-video',prompt:'A calm landscape',promptId:null,sourceTitle:'',aspectRatio:'auto',quality:'basic',count:1,taskCount:1,mode:'text',duration:3,resolution:'720p',referenceUrls:['https://expired.example.test/old.png'],videoUrl:'https://expired.example.test/old.mp4',videoStart:10,videoEnd:1,audioIds:['audio'],characterIds:['character'],seed:1,grokMode:'normal'}}}));
 });
 await prepare(page);
 await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption(reference);
 await page.getByRole('textbox',{name:/^Промпт/}).fill('A calm landscape');
 await page.getByRole('complementary').getByRole('button',{name:'Создать',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();
});

test('mixed references route automatically and preserve the exact price confirmation',async({page})=>{
 const posts=await prepare(page);
 let uploads=0;
 await page.route('**/api/web/kling4/assets',route=>{const kind=['image','video','audio'][uploads++];return route.fulfill({json:{ok:true,data:{url:`https://media.example.test/${kind}`,kind}}});});
 await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption(reference);
 await page.getByRole('textbox',{name:/^Промпт/}).fill('A scene with @image_1 and @video_1. @Voice_1 speaks.');
 await page.getByLabel('Референсы · фото, видео, аудио',{exact:true}).setInputFiles(['ref.png','clip.mp4','voice.wav'].map(name=>({name,mimeType:'application/octet-stream',buffer:Buffer.from('fixture')})));
 await expect(page.getByText('Голос @Voice_1:',{exact:false})).toBeVisible();
 await page.getByRole('complementary').getByRole('button',{name:'Создать',exact:true}).click();
 await expect(page.getByRole('dialog')).toBeVisible();expect(posts).toHaveLength(0);
 await page.getByRole('dialog').getByRole('button',{name:/Запустить за/}).click();
 await expect.poll(()=>posts.length).toBe(1);
 expect(posts[0].model).toBe(reference);
 expect(posts[0].kling4).toMatchObject({image_urls:['https://media.example.test/image'],video_urls:['https://media.example.test/video'],voices:[{name:'Voice_1',audio_url:'https://media.example.test/audio'}]});
 expect(posts[0].quoted_credits).toBe(85.5);
});

test('failed batch retains completed uploads and invalid asset kind fails closed',async({page})=>{
 const posts=await prepare(page);let uploads=0;
 await page.route('**/api/web/kling4/assets',route=>++uploads===1?route.fulfill({json:{ok:true,data:{url:'https://media.example.test/kept.png',kind:'image'}}}):route.fulfill({status:503,json:{ok:false,error:'Upload unavailable'}}));
 await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption(reference);
 await page.getByRole('textbox',{name:/^Промпт/}).fill('A calm scene');
 const input=page.getByLabel('Референсы · фото, видео, аудио',{exact:true});
 await input.setInputFiles(['first.png','second.png'].map(name=>({name,mimeType:'image/png',buffer:Buffer.from('fixture')})));
 await expect(page.getByRole('alert').filter({hasText:'Upload unavailable'})).toBeVisible();
 await expect(page.getByText('1. kept.png',{exact:true})).toBeVisible();
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:'https://media.example.test/unknown.png'}}}));
 await input.setInputFiles({name:'unknown.png',mimeType:'image/png',buffer:Buffer.from('fixture')});
 await expect(page.getByRole('alert').filter({hasText:'Сервер не подтвердил тип материала'})).toBeVisible();
 await page.getByRole('complementary').getByRole('button',{name:'Создать',exact:true}).click();
 await page.getByRole('dialog').getByRole('button',{name:/Запустить за/}).click();
 await expect.poll(()=>posts.length).toBe(1);
 expect((posts[0].kling4 as any).image_urls).toEqual(['https://media.example.test/kept.png']);
});

test('eleventh automatic image is refused before storage',async({page})=>{
 await prepare(page);let uploads=0;
 await page.route('**/api/web/kling4/assets',route=>route.fulfill({json:{ok:true,data:{url:`https://media.example.test/${++uploads}.png`,kind:'image'}}}));
 await page.getByRole('combobox',{name:'Модель',exact:true}).selectOption(reference);
 await page.getByLabel('Референсы · фото, видео, аудио',{exact:true}).setInputFiles(Array.from({length:11},(_,i)=>({name:`${i}.png`,mimeType:'image/png',buffer:Buffer.from('fixture')})));
 await expect(page.getByRole('alert').filter({hasText:'Не больше 10'})).toBeVisible();expect(uploads).toBe(10);
});

test('saved legacy keyframe draft retains frame roles and original model at checkout',async({page})=>{
 await page.addInitScript(()=>sessionStorage.setItem('apix:ux2:drafts:v1:7',JSON.stringify({version:1,owner:7,drafts:{video:{kind:'video',model:'kling-4.0/keyframe-to-video',prompt:'@first_frame Move gently',promptId:null,sourceTitle:'',aspectRatio:'auto',quality:'basic',count:1,taskCount:1,mode:'text',duration:3,resolution:'720p',referenceUrls:[],videoUrl:'',videoStart:0,videoEnd:null,audioIds:[],characterIds:[],seed:null,grokMode:'normal',kling4:{first_frame_url:'https://media.example.test/first.png',keyframe_urls:[]}}}})));
 const posts=await prepare(page);
 await expect(page.getByLabel('Первый кадр',{exact:true})).toBeAttached();
 await expect(page.getByLabel('Промежуточные кадры',{exact:true})).toBeAttached();
 await expect(page.getByLabel('Референсы · фото, видео, аудио',{exact:true})).toHaveCount(0);
 await page.getByRole('complementary').getByRole('button',{name:'Создать',exact:true}).click();
 await page.getByRole('dialog').getByRole('button',{name:/Запустить за/}).click();
 await expect.poll(()=>posts.length).toBe(1);expect(posts[0].model).toBe(keyframe);
 expect((posts[0].kling4 as any).first_frame_url).toBe('https://media.example.test/first.png');
});
