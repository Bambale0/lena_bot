import assert from "node:assert/strict";
import test from "node:test";
import { draftStorageKey, readUserDrafts, saveUserDrafts } from "../../src/lib/draft-storage.ts";
import { editorParent, previewEnabled, primaryTab, UX2_TABS } from "../../src/lib/ux2.ts";

const draft = () => ({ kind: "image" as const, model: "fixture-image", prompt: "My draft", promptId: null, sourceTitle: "",
  aspectRatio: "9:16", quality: "basic", count: 1, taskCount: 1, mode: "image", duration: 5, resolution: "720p",
  referenceUrls: ["https://media.example.test/photo.png"], videoUrl: "", videoStart: 0, videoEnd: null,
  audioIds: [], characterIds: [], seed: null, grokMode: "normal" });
function storage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); } };
}

test("ordinary draft round trips with its media and parameters", () => {
  const s = storage();
  assert.equal(saveUserDrafts(s, 7, { image: draft() }), true);
  assert.deepEqual(readUserDrafts(s, 7).image, draft());
});
test("draft restoration is scoped to its authenticated owner", () => {
  const s = storage(); saveUserDrafts(s, 7, { image: draft() });
  assert.deepEqual(readUserDrafts(s, 8), {});
  s.setItem(draftStorageKey(8), s.getItem(draftStorageKey(7))!);
  assert.deepEqual(readUserDrafts(s, 8), {});
});
test("template draft is never saved over an ordinary draft", () => {
  const s = storage(); saveUserDrafts(s, 7, { image: draft() });
  saveUserDrafts(s, 7, { image: { ...draft(), promptId: 44, prompt: "Template content" } });
  assert.equal(readUserDrafts(s, 7).image?.prompt, "My draft");
  assert.ok(!s.getItem(draftStorageKey(7))!.includes("Template content"));
});
test("serialization contains only permitted draft fields", () => {
  const s = storage();
  saveUserDrafts(s, 7, { image: { ...draft(), unexpectedMetadata: "not-a-draft-field" } as ReturnType<typeof draft> });
  assert.ok(!s.getItem(draftStorageKey(7))!.includes("unexpectedMetadata"));
});
test("clearing an ordinary draft clears its saved input", () => {
  const s = storage(); saveUserDrafts(s, 7, { image: draft() });
  saveUserDrafts(s, 7, { image: { ...draft(), prompt: "", referenceUrls: [] } });
  assert.deepEqual(readUserDrafts(s, 7), {});
});
for (const raw of ["{bad", "null", JSON.stringify({ version: 2, owner: 7 }), "x".repeat(128 * 1024 + 1)]) {
  test(`invalid stored document is ignored (${raw.length} characters)`, () => {
    const s = storage(); s.setItem(draftStorageKey(7), raw);
    assert.deepEqual(readUserDrafts(s, 7), {});
  });
}
test("unavailable storage does not break editing", () => {
  const s = { getItem(): string | null { throw new Error("unavailable"); }, setItem() { throw new Error("quota"); } };
  assert.deepEqual(readUserDrafts(s, 7), {});
  assert.equal(saveUserDrafts(s, 7, { image: draft() }), false);
  assert.equal(saveUserDrafts(null, 7, { image: draft() }), false);
});
test("preview needs server capability and explicit opt in", () => {
  const user = { id: 7, credits: 0, miniapp_ux2_available: false };
  assert.equal(previewEnabled(user, "?ux=2", "2"), false);
  const admin = { ...user, miniapp_ux2_available: true };
  assert.equal(previewEnabled(admin, "", null), false);
  assert.equal(previewEnabled(admin, "?ux=2", null), true);
  assert.equal(previewEnabled(admin, "?ux=1", "2"), false);
});
test("nested destinations retain their five-section parent", () => {
  assert.deepEqual(UX2_TABS, ["feed", "trends", "create", "works", "profile"]);
  for (const tab of ["photo", "video", "motion", "services"] as const) {
    assert.equal(primaryTab(tab), "create"); assert.equal(editorParent(tab), "create");
  }
  assert.equal(primaryTab("settings"), "profile");
  assert.equal(editorParent("settings"), "profile");
  assert.equal(editorParent("works"), null);
});
