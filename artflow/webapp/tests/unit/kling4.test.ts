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

test('Kling bodies exclude preserved legacy media and unsupported controls',async()=>{
 const {kling4Body}=await import('../../src/lib/kling4.ts');
 assert.deepEqual(kling4Body({model:'kling-4.0/reference-to-video'}),{kling4:{},image_url:null,reference_urls:[],video_url:null,video_start:0,video_end:null,audio_ids:[],character_ids:[],seed:null});
});

test('automatic mixed references remain immutable and use server-confirmed kind',async()=>{
 const {appendKling4Reference}=await import('../../src/lib/kling4.ts');
 const original={elements:[{name:'Voice_1',image_urls:['a','b']}]};
 const photo=appendKling4Reference(original,{url:'image',kind:'image'});
 const video=appendKling4Reference(photo,{url:'video',kind:'video'});
 const audio=appendKling4Reference(video,{url:'audio',kind:'audio'});
 assert.deepEqual(original,{elements:[{name:'Voice_1',image_urls:['a','b']}]});
 assert.deepEqual(audio.image_urls,['image']);assert.deepEqual(audio.video_urls,['video']);
 assert.deepEqual(audio.voices,[{name:'Voice_2',audio_url:'audio'}]);
 assert.throws(()=>appendKling4Reference(audio,{url:'bad'}),/не подтвердил тип/);
 assert.throws(()=>appendKling4Reference(audio,{url:'bad',kind:'document'}),/не подтвердил тип/);
});

test('pre-upload caps cover every automatic collection and combined materials',async()=>{
 const {checkKling4ReferenceCapacity,kling4FileKind}=await import('../../src/lib/kling4.ts');
 assert.equal(kling4FileKind({name:'PHOTO.JPG'}),'image');
 assert.equal(kling4FileKind({name:'movie.mov'}),'video');
 assert.equal(kling4FileKind({name:'speech.oga'}),'audio');
 assert.throws(()=>kling4FileKind({name:'program.exe'}),/Поддерживаются/);
 assert.throws(()=>checkKling4ReferenceCapacity({image_urls:Array(10).fill('a')},'image'),/10/);
 assert.throws(()=>checkKling4ReferenceCapacity({video_urls:Array(5).fill('a')},'video'),/5/);
 assert.throws(()=>checkKling4ReferenceCapacity({voices:Array(3).fill({name:'Voice',audio_url:'a'})},'audio'),/3/);
 assert.throws(()=>checkKling4ReferenceCapacity({image_urls:Array(9).fill('a'),video_urls:Array(4).fill('a'),voices:Array(2).fill({name:'Voice',audio_url:'a'})},'image'),/15/);
});
