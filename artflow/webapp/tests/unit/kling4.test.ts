import assert from 'node:assert/strict';
import test from 'node:test';
import { renameKling4Mentions } from '../../src/lib/kling4.ts';
test('renaming a material keeps longer mentions intact',()=>{
 const old={elements:[{name:'Hero',image_urls:['a','b']},{name:'Hero_2',image_urls:['c','d']}]};
 const next={elements:[{name:'Actor',image_urls:['a','b']},{name:'Hero_2',image_urls:['c','d']}]};
 assert.equal(renameKling4Mentions(old,next,'@Hero meets @Hero_2.'),'@Actor meets @Hero_2.');
});

test('automatic names remain unique after deletion and across voices',async()=>{
 const {nextKling4Name}=await import('../../src/lib/kling4.ts');
 assert.equal(nextKling4Name({elements:[{name:'Hero_2'}],voices:[{name:'hero_1',audio_url:'voice'}]},'Hero'),'Hero_3');
});
