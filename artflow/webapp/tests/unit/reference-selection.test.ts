import assert from "node:assert/strict";
import test from "node:test";
import { draftStorageKey, readUserDrafts, saveUserDrafts } from "../../src/lib/draft-storage.ts";
import type { GenerationDraft } from "../../src/lib/types.ts";
import { referenceMaterials, selectGenerationInputs, setReferenceIncluded, deleteReferenceMaterial, replaceReferenceMaterials, appendReferenceUrls, applyDraftPatch, modelSnapshotKey } from "../../src/lib/reference-selection.ts";

const urls = ["https://media.example.test/first.png", "https://media.example.test/second.png"];
function draft(): GenerationDraft { return { kind: "image", model: "test", prompt: "Mine", promptId: null, sourceTitle: "",
  aspectRatio: "9:16", quality: "basic", count: 1, taskCount: 1, mode: "image", duration: 5, resolution: "720p",
  referenceUrls: [...urls], videoUrl: "", videoStart: 0, videoEnd: null, audioIds: [], characterIds: [], seed: null, grokMode: "normal" }; }

test("v1 photos are all-active with distinct local ids", () => {
  const items = referenceMaterials(draft());
  assert.equal(new Set(items.map(x => x.id)).size, 2);
  assert.deepEqual(items.map(x => x.included), [true, true]);
});
test("excluding never deletes and request projection contains only active data", () => {
  const source = draft(); const snapshot = JSON.stringify(source);
  const selected = setReferenceIncluded(source, "legacy-1", false);
  assert.equal(JSON.stringify(source), snapshot);
  assert.deepEqual(selected.referenceUrls, []);
  assert.deepEqual(referenceMaterials(selected).map(x => x.url), urls);
  const request = selectGenerationInputs(selected);
  assert.deepEqual(request.referenceUrls, [urls[0]]);
  assert.ok(!("referenceMaterials" in request));
  assert.ok(!JSON.stringify(request).includes(urls[1]));
  request.referenceUrls.push("modified");
  assert.equal(referenceMaterials(selected).length, 2);
});
test("include and delete have different effects and do not mutate", () => {
  const selected = setReferenceIncluded(draft(), "legacy-1", false);
  assert.deepEqual(selectGenerationInputs(setReferenceIncluded(selected, "legacy-1", true)).referenceUrls, urls);
  const deleted = deleteReferenceMaterial(selected, "legacy-1");
  assert.deepEqual(referenceMaterials(deleted).map(x => x.url), [urls[0]]);
  assert.equal(referenceMaterials(selected).length, 2);
});
test("reorder preserves identity and excluded state even with identical file names", () => {
  const source = { ...draft(), referenceUrls: ["https://a.example.test/photo.png", "https://b.example.test/photo.png"] };
  const selected = setReferenceIncluded(source, "legacy-1", false);
  const reordered = replaceReferenceMaterials(selected, [...source.referenceUrls].reverse());
  assert.deepEqual(referenceMaterials(reordered).map(x => [x.id, x.included]), [["legacy-1", false], ["legacy-0", true]]);
});
test("duplicate urls remain independent items when supplied by a saved draft", () => {
  const selected = setReferenceIncluded({ ...draft(), referenceUrls: [urls[0], urls[0]] }, "legacy-0", false);
  const reordered = replaceReferenceMaterials(selected, [urls[0], urls[0]]);
  assert.deepEqual(referenceMaterials(reordered).map(x => x.included), [false, true]);
  assert.deepEqual(selectGenerationInputs(reordered).referenceUrls, [urls[0]]);
  assert.equal(referenceMaterials(deleteReferenceMaterial(reordered, "legacy-0")).length, 1);
});
test("duplicate upload cannot silently reinclude a parked photo", () => {
  const selected = setReferenceIncluded(draft(), "legacy-1", false);
  const uploaded = appendReferenceUrls(selected, [urls[1], "https://media.example.test/third.png"], () => "new-id");
  assert.deepEqual(referenceMaterials(uploaded).map(x => [x.id, x.included]), [["legacy-0", true], ["legacy-1", false], ["new-id", true]]);
});
test("legacy projection edits leave parked media intact", () => {
  const selected = setReferenceIncluded(draft(), "legacy-1", false);
  const clearedActive = applyDraftPatch(selected, { referenceUrls: [], prompt: "Changed" });
  assert.deepEqual(referenceMaterials(clearedActive).map(x => [x.url, x.included]), [[urls[1], false]]);
  assert.equal(clearedActive.prompt, "Changed");
  assert.deepEqual(selectGenerationInputs(clearedActive).referenceUrls, []);
});
test("hidden templates cannot acquire ordinary selection state", () => {
  const hidden = { ...draft(), promptId: 44 };
  assert.equal(setReferenceIncluded(hidden, "legacy-1", false), hidden);
  const selected = setReferenceIncluded(draft(), "legacy-1", false);
  const template = applyDraftPatch(selected, { promptId: 44, prompt: "Hidden" });
  assert.equal(template.referenceMaterials, undefined);
  assert.deepEqual(template.referenceUrls, [urls[0]]);
});
test("model fingerprint includes price and caps but ignores property order", () => {
  const a = { key: "a", credits: 2, max_refs: 1 } as any;
  assert.equal(modelSnapshotKey(a), modelSnapshotKey({ max_refs: 1, credits: 2, key: "a" } as any));
  assert.notEqual(modelSnapshotKey(a), modelSnapshotKey({ ...a, credits: 3 }));
  assert.notEqual(modelSnapshotKey(a), modelSnapshotKey({ ...a, max_refs: 0 }));
});


function memory() {
  const values = new Map<string, string>();
  return { values, getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
}
const v2key = (owner: number) => `apix:ux2:drafts:v2:${owner}`;

test("selected draft persists full v2 state and active-only v1 rollback projection", () => {
  const storage = memory(); const selected = setReferenceIncluded(draft(), "legacy-1", false);
  assert.equal(saveUserDrafts(storage, 7, { image: selected }), true);
  assert.deepEqual(readUserDrafts(storage, 7).image, selected);
  const full = JSON.parse(storage.getItem(v2key(7))!);
  assert.equal(full.version, 2);
  assert.deepEqual(full.drafts.image.referenceUrls, []);
  assert.deepEqual(full.drafts.image.referenceMaterials.map((x: any) => x.included), [true, false]);
  const legacy = JSON.parse(storage.getItem(draftStorageKey(7))!);
  assert.deepEqual(legacy.drafts.image.referenceUrls, [urls[0]]);
  assert.ok(!JSON.stringify(legacy).includes(urls[1]));
});
test("parked-only draft is not mistaken for an empty deleted draft", () => {
  const storage = memory(); let selected = { ...draft(), prompt: "" };
  for (const item of referenceMaterials(selected)) selected = setReferenceIncluded(selected, item.id, false);
  assert.equal(saveUserDrafts(storage, 7, { image: selected }), true);
  assert.equal(referenceMaterials(readUserDrafts(storage, 7).image!).length, 2);
  assert.deepEqual(selectGenerationInputs(readUserDrafts(storage, 7).image!).referenceUrls, []);
});
test("v1 migration marks all photos active without truncating over-limit drafts", () => {
  const storage = memory(); saveUserDrafts(storage, 7, { image: draft() });
  const restored = readUserDrafts(storage, 7).image!;
  assert.deepEqual(referenceMaterials(restored).map(x => x.included), [true, true]);
  const selected = setReferenceIncluded(restored, "legacy-1", false);
  saveUserDrafts(storage, 7, { image: selected });
  assert.deepEqual(referenceMaterials(readUserDrafts(storage, 7).image!), referenceMaterials(selected));
});
test("v2 snapshots are owner-scoped even when copied to another storage key", () => {
  const storage = memory(); saveUserDrafts(storage, 7, { image: setReferenceIncluded(draft(), "legacy-1", false) });
  storage.setItem(v2key(8), storage.getItem(v2key(7))!);
  assert.deepEqual(readUserDrafts(storage, 8), {});
});
for (const raw of ["{bad", JSON.stringify({ version: 99, owner: 7, drafts: {} })]) {
  test(`unsupported v2 snapshot neither falls back to all-active v1 nor gets overwritten: ${raw}`, () => {
    const storage = memory(); saveUserDrafts(storage, 7, { image: draft() });
    storage.setItem(v2key(7), raw);
    assert.deepEqual(readUserDrafts(storage, 7), {});
    assert.equal(saveUserDrafts(storage, 7, { image: draft() }), false);
    assert.equal(storage.getItem(v2key(7)), raw);
  });
}
test("legacy rollback editing cannot reactivate parked v2 media on restore", () => {
  const storage = memory(); saveUserDrafts(storage, 7, { image: setReferenceIncluded(draft(), "legacy-1", false) });
  storage.setItem(draftStorageKey(7), JSON.stringify({ version: 1, owner: 7, drafts: { image: draft() } }));
  assert.deepEqual(selectGenerationInputs(readUserDrafts(storage, 7).image!).referenceUrls, [urls[0]]);
});
test("malformed included flags and duplicate ids are never restored as active", () => {
  for (const items of [
    [{ id: "1", url: urls[0], included: "false" }],
    [{ id: "1", url: urls[0], included: true }, { id: "1", url: urls[1], included: false }],
  ]) {
    const storage = memory();
    storage.setItem(v2key(7), JSON.stringify({ version: 2, owner: 7, drafts: { image: { ...draft(), referenceUrls: [], referenceMaterials: items } } }));
    assert.deepEqual(readUserDrafts(storage, 7), {});
  }
});
test("hidden templates never overwrite a selected ordinary snapshot", () => {
  const storage = memory(); const selected = setReferenceIncluded(draft(), "legacy-1", false);
  saveUserDrafts(storage, 7, { image: selected });
  saveUserDrafts(storage, 7, { image: { ...draft(), promptId: 44, prompt: "Hidden content" } });
  assert.deepEqual(selectGenerationInputs(readUserDrafts(storage, 7).image!).referenceUrls, [urls[0]]);
  assert.ok(!storage.getItem(v2key(7))!.includes("Hidden content"));
});
test("failed compatibility write cannot claim safe persistent selection", () => {
  const storage = memory(); const selected = setReferenceIncluded(draft(), "legacy-1", false);
  const failing = { getItem: storage.getItem, setItem: (key: string, value: string) => { if (key === draftStorageKey(7)) throw new Error("blocked"); storage.setItem(key, value); } };
  assert.equal(saveUserDrafts(failing, 7, { image: selected }), false);
});


test("selection serialization strips unrelated fields from individual items", () => {
  const storage = memory(); const selected = setReferenceIncluded(draft(), "legacy-1", false);
  selected.referenceMaterials = selected.referenceMaterials!.map(item => ({ ...item, unrelated: "not-a-material-field" }));
  assert.equal(saveUserDrafts(storage, 7, { image: selected }), true);
  assert.ok(!storage.getItem(v2key(7))!.includes("not-a-material-field"));
});
test("canonical quota failure reports false and does not overwrite the last full snapshot", () => {
  const storage = memory(); const selected = setReferenceIncluded(draft(), "legacy-1", false);
  saveUserDrafts(storage, 7, { image: selected });
  const before = storage.getItem(v2key(7));
  const failing = { getItem: storage.getItem, setItem: (key: string, value: string) => { if (key === v2key(7)) throw new Error("quota"); storage.setItem(key, value); } };
  assert.equal(saveUserDrafts(failing, 7, { image: setReferenceIncluded(selected, "legacy-0", false) }), false);
  assert.equal(storage.getItem(v2key(7)), before);
  assert.deepEqual(JSON.parse(storage.getItem(draftStorageKey(7))!).drafts.image.referenceUrls, []);
});
