import assert from "node:assert/strict";
import test from "node:test";
import { applyPhotoUploadEvent, cancelPhotoReplacement, parsePhotoPolicy, photoUploading, queuePhoto, safePhotoUrl, validatePhotoFile, validateUploadedPhoto } from "../../src/lib/photo-upload.ts";
import { PhotoUploadQueue, type PhotoUploadContext } from "../../src/lib/photo-upload-queue.ts";
import { inspectDraftMedia } from "../../src/lib/draft-media.ts";
import { deleteReferenceMaterial, referenceMaterials, selectGenerationInputs, setReferenceIncluded } from "../../src/lib/reference-selection.ts";
import { draftStorageKey, readUserDrafts, saveUserDrafts, selectionStorageKey, uploadStorageKey } from "../../src/lib/draft-storage.ts";
import type { GenerationDraft, PhotoUploadState } from "../../src/lib/types";
const draft = (): GenerationDraft => ({ kind: "image", model: "fixture", prompt: "Keep my input", promptId: null, sourceTitle: "", aspectRatio: "1:1", quality: "basic", count: 1, taskCount: 1, mode: "text", duration: 5, resolution: "720p", referenceUrls: [], videoUrl: "", videoStart: 0, videoEnd: null, audioIds: [], characterIds: [], seed: null, grokMode: "normal" });
const model = { key: "fixture", display_name: "Fixture", credits: 2, modes: ["text", "image"], max_refs: 4 };
const upload = (operationId = "op-a"): PhotoUploadState => ({ operationId, status: "queued", name: "file.png", size: 16, contentType: "image/png" });
const url = "https://media.example.test/result.png";
const png = new File([new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,0])], "file.png", { type: "image/png" });
const policy = { image_max_bytes: 100, image_formats: ["jpeg", "png", "webp"] };
const memory = () => { const m = new Map<string,string>(); return { getItem: (k:string) => m.get(k) ?? null, setItem: (k:string,v:string) => {m.set(k,v);} }; };

test("completion persists each photo independently and retains original order", () => {
  const original = draft();
  let d = queuePhoto(queuePhoto(queuePhoto(original, "a", upload("1")), "b", upload("2")), "c", upload("3"));
  d = applyPhotoUploadEvent(d, { type: "success", id: "a", operationId: "1", result: { url } });
  d = applyPhotoUploadEvent(d, { type: "failure", id: "b", operationId: "2", error: "network" });
  d = applyPhotoUploadEvent(d, { type: "success", id: "c", operationId: "3", result: { url: url+"?c" } });
  assert.deepEqual(referenceMaterials(d).map(x=>x.id), ["a","b","c"]);
  assert.deepEqual(selectGenerationInputs(d).referenceUrls, [url,url+"?c"]);
  assert.ok(inspectDraftMedia(d,model).issues.some(x=>x.code==="reference_upload_failed"));
  assert.deepEqual(original,draft());
});
test("failure and success from a superseded or removed operation do nothing", () => {
  const d = queuePhoto(draft(),"a",upload("new"));
  assert.equal(applyPhotoUploadEvent(d,{type:"success",id:"a",operationId:"old",result:{url}}),d);
  const removed=deleteReferenceMaterial(d,"a");
  assert.equal(applyPhotoUploadEvent(removed,{type:"success",id:"a",operationId:"new",result:{url}}),removed);
});
test("failed replacement retains original and inclusion until explicit keep or success", () => {
  const old={...draft(),referenceUrls:[],referenceMaterials:[{id:"a",url,included:false,name:"original.png"}]};
  let d=queuePhoto(old,"a",upload(),true);
  d=applyPhotoUploadEvent(d,{type:"failure",id:"a",operationId:"op-a",error:"network"});
  assert.equal(referenceMaterials(d)[0].url,url);
  assert.equal(referenceMaterials(d)[0].included,false);
  assert.deepEqual(cancelPhotoReplacement(d,"a"),old);
  const ready=applyPhotoUploadEvent(queuePhoto(old,"a",upload("retry"),true),{type:"success",id:"a",operationId:"retry",result:{url:url+"?new",size:32,content_type:"image/png"}});
  assert.equal(referenceMaterials(ready)[0].id,"a");assert.equal(referenceMaterials(ready)[0].included,false);
  assert.equal(referenceMaterials(ready)[0].url,url+"?new");
});
test("queued replacement never submits its previous URL", () => {
  const d=queuePhoto({...draft(),referenceUrls:[url]},"legacy-0",upload(),true);
  assert.deepEqual(selectGenerationInputs(d).referenceUrls,[]);
  assert.equal(photoUploading(d),true);
  assert.ok(inspectDraftMedia(d,model).issues.some(x=>x.code==="reference_upload_pending"));
});
test("excluding a failed file permits only the remaining acknowledged input", () => {
  let d=queuePhoto({...draft(),referenceUrls:[url]},"bad",upload());
  d=applyPhotoUploadEvent(d,{type:"failure",id:"bad",operationId:"op-a",error:"network"});
  d=setReferenceIncluded(d,"bad",false);
  assert.deepEqual(selectGenerationInputs(d).referenceUrls,[url]);
  assert.equal(inspectDraftMedia(d,model).issues.length,0);
});
test("hidden-template draft never gains a photo upload", () => {
  const d={...draft(),promptId:45};assert.equal(queuePhoto(d,"a",upload()),d);
});
test("v3 restores an interrupted file honestly; old mirrors contain ready inputs only", () => {
  let d=queuePhoto({...draft(),referenceUrls:[url]},"pending",upload());const s=memory();
  assert.equal(saveUserDrafts(s,7,{image:d}),true);
  const restored=readUserDrafts(s,7).image!;
  assert.deepEqual(referenceMaterials(restored).map(x=>x.url),[url,""]);
  assert.equal(referenceMaterials(restored)[1].upload?.error,"source_required");
  assert.deepEqual(JSON.parse(s.getItem(selectionStorageKey(7))!).drafts.image.referenceMaterials.map((x:any)=>x.url),[url]);
  assert.deepEqual(JSON.parse(s.getItem(draftStorageKey(7))!).drafts.image.referenceUrls,[url]);
  assert.deepEqual(readUserDrafts(s,8),{});
  assert.ok(!s.getItem(uploadStorageKey(7))!.includes("blob:"));
});
test("v3 keeps successful metadata across reload with no File object", () => {
  const s=memory(); const d=applyPhotoUploadEvent(queuePhoto(draft(),"a",upload()),{type:"success",id:"a",operationId:"op-a",result:{url,size:20,content_type:"image/png"}});
  assert.equal(saveUserDrafts(s,7,{image:d}),true);
  assert.deepEqual(readUserDrafts(s,7).image,d);
});
test("invalid v3 cannot fall back to a stale all-active older snapshot", () => {
  const s=memory(); saveUserDrafts(s,7,{image:{...draft(),referenceUrls:[url]}});
  s.setItem(uploadStorageKey(7),JSON.stringify({version:99,owner:7,drafts:{}}));
  assert.deepEqual(readUserDrafts(s,7),{});assert.equal(saveUserDrafts(s,7,{image:draft()}),false);
});
test("type and size are validated before transport using the server policy", async () => {
  assert.equal(await validatePhotoFile(png,policy),"image/png");
  await assert.rejects(validatePhotoFile(png,{...policy,image_max_bytes:1}),{code:"too_large"});
  await assert.rejects(validatePhotoFile(new File([],"empty.png"),policy),{code:"empty_file"});
  await assert.rejects(validatePhotoFile(new File(["not a picture"],"bad.png",{type:"image/png"}),policy),{code:"invalid_file"});
  assert.throws(()=>parsePhotoPolicy([]),{code:"policy_unavailable"});
  assert.throws(()=>validateUploadedPhoto({url:""},png,"image/png",policy),{code:"invalid_response"});
  assert.throws(()=>validateUploadedPhoto({url,kind:"video"},png,"image/png",policy),{code:"invalid_response"});
});
test("automatic previews reject non-public addresses and allow public https paths", () => {
  assert.equal(safePhotoUrl(url),true);assert.equal(safePhotoUrl("/api/files/photo.png"),true);
  for(const value of ["http://localhost/a","http://127.0.0.1/a","http://10.1.2.3/a","//example.test/a","blob:local","not a url"]){assert.equal(safePhotoUrl(value),false);}
});

function harness() {
  let state={image:draft(),video:{...draft(),kind:"video" as const},motion:{...draft(),kind:"motion" as const}};
  const context:PhotoUploadContext={owner:7,enabled:true,locked:false,drafts:state,models:{image:[model],video:[]},
    update:(kind,apply)=>{state={...state,[kind]:apply(state[kind])};context.drafts=state;},policy:async()=>policy,
    upload:async()=>({url,kind:"image",content_type:"image/png",size:png.size}),notice:()=>undefined};
  const queue=new PhotoUploadQueue(()=>context);return{context,queue,get:()=>state.image};
}
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
test("late network completion after cancel cannot resurrect a photo", async () => {
  const h=harness();let release!:(v:any)=>void;h.context.upload=()=>new Promise(resolve=>{release=resolve;});
  h.queue.add("image",[png]);await tick();const id=referenceMaterials(h.get())[0].id;
  h.queue.controls("image").cancel(id);release({url});await tick();
  assert.deepEqual(referenceMaterials(h.get()),[]);h.queue.dispose();
});
test("owner change cannot receive a previous owner's upload result", async () => {
  const h=harness();let release!:(v:any)=>void;h.context.upload=()=>new Promise(resolve=>{release=resolve;});
  h.queue.add("image",[png]);await tick();h.context.owner=8;
  h.context.update("image",()=>draft());h.queue.reconcile();release({url});await tick();
  assert.deepEqual(referenceMaterials(h.get()),[]);h.queue.dispose();
});
test("independent retry makes one transport attempt and preserves duplicate-name identities", async () => {
  const h=harness();let attempts=0;h.context.upload=async()=>{attempts++;if(attempts===2)throw new Error("network");return{url,kind:"image"};};
  h.queue.add("image",[png,png]);await tick();await tick();
  const items=referenceMaterials(h.get());assert.equal(items.length,2);assert.notEqual(items[0].id,items[1].id);
  h.queue.controls("image").retry(items[1].id);await tick();await tick();
  assert.equal(attempts,3);assert.equal(referenceMaterials(h.get()).filter(x=>!x.upload).length,2);h.queue.dispose();
});


test("object URLs are released after success, cancellation and disposing errors", async (t) => {
  const created:string[]=[]; const revoked:string[]=[];
  t.mock.method(URL,"createObjectURL",()=>{const value=`blob:fixture-${created.length}`;created.push(value);return value;});
  t.mock.method(URL,"revokeObjectURL",(value:string)=>{revoked.push(value);});
  const h=harness();h.queue.add("image",[png]);await tick();await tick();
  h.context.upload=async()=>{throw new Error("offline");};h.queue.add("image",[png]);await tick();await tick();
  assert.equal(revoked.length,1);h.queue.dispose();assert.deepEqual(revoked,created);
});
test("a template switch cannot accept an old ordinary upload completion", async () => {
  const h=harness();let release!:(v:any)=>void;h.context.upload=()=>new Promise(resolve=>{release=resolve;});
  h.queue.add("image",[png]);await tick();h.context.update("image",()=>({...draft(),promptId:44}));
  h.queue.reconcile();release({url});await tick();assert.equal(h.get().promptId,44);assert.deepEqual(h.get().referenceUrls,[]);h.queue.dispose();
});
test("transient source fields never enter v3 or its older mirrors", () => {
  const s=memory();const d=queuePhoto(draft(),"a",upload());
  const enhanced={...d,referenceMaterials:d.referenceMaterials!.map(x=>({...x, transientSource:"private-file-bytes",previewUrl:"blob:local"}))};
  assert.equal(saveUserDrafts(s,7,{image:enhanced}),true);
  for(const key of [draftStorageKey(7),selectionStorageKey(7),uploadStorageKey(7)]) {
    assert.ok(!s.getItem(key)!.includes("private-file-bytes"));assert.ok(!s.getItem(key)!.includes("blob:"));
  }
});


test("transport timeout aborts the request and leaves only this file retryable", async (t) => {
  t.mock.timers.enable({apis:["setTimeout"]});
  const h=harness();let begin!:()=>void;const started=new Promise<void>(resolve=>{begin=resolve;});
  h.context.upload=(_file,signal)=>new Promise((_resolve,reject)=>{signal.addEventListener("abort",()=>reject(new Error("aborted")),{once:true});begin();});
  h.queue.add("image",[png]);await started;t.mock.timers.tick(60_000);
  for(let i=0;i<6;i++)await Promise.resolve();
  assert.equal(referenceMaterials(h.get())[0].upload?.error,"timeout");
  assert.equal(h.queue.hasPending(),false);assert.equal(h.queue.controls("image").hasSource(referenceMaterials(h.get())[0].id),true);
  h.queue.dispose();
});
