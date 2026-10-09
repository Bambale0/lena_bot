import test from "node:test";
import assert from "node:assert/strict";
import { inspectDraftMedia, switchDraftModel } from "../../src/lib/draft-media.ts";
import type { GenerationDraft, ModelInfo } from "../../src/lib/types.ts";
const model: ModelInfo = { key: "a", display_name: "A", credits: 2, modes: ["text", "image", "video"], max_refs: 3, supports_video_input: true, aspect_ratios: ["1:1", "9:16"], quality_options: [{ value: "basic" }], counts: [1, 2], durations: [5, 10], resolutions: ["720p"], max_audio_ids: 2, max_character_ids: 2, has_seed: true };
const draft = (): GenerationDraft => ({ kind: "image", model: "a", prompt: "My idea", promptId: null, sourceTitle: "", aspectRatio: "9:16", quality: "basic", count: 2, taskCount: 1, mode: "image", duration: 10, resolution: "720p", referenceUrls: ["https://media.example.test/1.png", "https://media.example.test/2.png"], videoUrl: "", videoStart: 2, videoEnd: 7, audioIds: [], characterIds: [], seed: 3, grokMode: "normal" });

test("switch preserves all media, order and compatible options without mutating input", () => {
 const original = draft(); const snapshot = structuredClone(original);
 const result = switchDraftModel(original, { ...model, key: "b" });
 assert.deepEqual(original, snapshot); assert.equal(result.model, "b");
 for (const key of ["prompt", "aspectRatio", "quality", "mode", "duration", "count", "resolution", "videoStart", "videoEnd", "seed"] as const) assert.equal(result[key], original[key]);
 assert.deepEqual(result.referenceUrls, original.referenceUrls); assert.notEqual(result.referenceUrls, original.referenceUrls);
 assert.deepEqual(inspectDraftMedia(result, model).issues, []);
});
test("smaller capacity never truncates the canonical references", () => {
 const next = switchDraftModel(draft(), { ...model, key: "one", max_refs: 1 });
 assert.equal(next.referenceUrls.length, 2);
 assert.ok(inspectDraftMedia(next, { ...model, key: "one", max_refs: 1 }).issues.some(x => x.code === "reference_limit"));
});
test("explicit zero reference capacity is not converted to one", () => {
 const info = inspectDraftMedia(draft(), { ...model, max_refs: 0 });
 assert.equal(info.maxReferences, 0); assert.equal(info.referenceInputsSupported, false); assert.ok(info.issues.length);
});
for (const value of [undefined, Number.NaN, -1, 1.5, "3"] as unknown[]) {
 test(`unknown or invalid capacity fails closed with existing photos (${String(value)})`, () => {
  const info = inspectDraftMedia(draft(), { ...model, max_refs: value as number });
  assert.equal(info.maxReferences, null); assert.ok(info.issues.some(x => x.code === "reference_capacity_unknown"));
 });
}
test("source-video combined capacity uses explicit zero", () => {
 const d = { ...draft(), kind: "video" as const, mode: "video", videoUrl: "https://media.example.test/source.mp4" };
 const info = inspectDraftMedia(d, { ...model, max_refs_with_video: 0 });
 assert.equal(info.maxReferences, 0); assert.ok(info.issues.some(x => x.code === "reference_limit"));
});
test("text-only roundtrip and source video keep all inputs and trim", () => {
 const d = { ...draft(), kind: "video" as const, mode: "video", videoUrl: "https://media.example.test/source.mp4", audioIds: ["a1"], characterIds: ["c1"] };
 const target = { ...model, key: "text", modes: ["text"], max_refs: 0, supports_video_input: false, max_audio_ids: 0, max_character_ids: 0 };
 const changed = switchDraftModel(d, target);
 assert.equal(changed.videoUrl, d.videoUrl); assert.equal(changed.videoStart, 2); assert.equal(changed.videoEnd, 7);
 assert.deepEqual(changed.audioIds, ["a1"]); assert.deepEqual(changed.characterIds, ["c1"]);
 assert.ok(inspectDraftMedia(changed, target).issues.some(x => x.code === "video_unsupported"));
 assert.deepEqual(switchDraftModel(changed, model).referenceUrls, d.referenceUrls);
});
test("no model cannot authorize a launch", () => {
 assert.ok(inspectDraftMedia(draft(), undefined).issues.some(x => x.code === "model_unavailable"));
});
test("incompatible ordinary parameters adopt metadata defaults, without erasing inputs", () => {
 const next = switchDraftModel(draft(), { ...model, modes: ["text"], aspect_ratios: ["4:5"], quality_options: [{ value: "high" }], counts: [1], durations: [7], resolutions: ["1080p"], has_seed: false });
 assert.equal(next.mode, "text"); assert.equal(next.aspectRatio, "4:5"); assert.equal(next.quality, "high");
 assert.equal(next.count, 1); assert.equal(next.duration, 7); assert.equal(next.resolution, "1080p"); assert.equal(next.seed, null);
 assert.equal(next.referenceUrls.length, 2);
});
test("hidden template draft is not transformed by ordinary-draft helper", () => {
 const d = { ...draft(), promptId: 55 }; assert.equal(switchDraftModel(d, model), d);
});


test("multimodal capability accepts ordinary photo references without an image mode", () => {
 const d = { ...draft(), kind: "video" as const, mode: "text" };
 const multimodal: ModelInfo = { ...model, modes: ["text", "multimodal"], requires_reference_images: false, max_refs: 30 };
 const info = inspectDraftMedia(d, multimodal);
 assert.equal(info.referenceInputsSupported, true);
 assert.equal(info.maxReferences, 30);
 assert.deepEqual(info.issues, []);
});


test("explicit video text mode cannot silently discard preserved photo references", () => {
 const d = { ...draft(), kind: "video" as const, mode: "text" };
 const info = inspectDraftMedia(d, model);
 assert.ok(info.issues.some(issue => issue.code === "reference_mode_unsupported"));
});

test("metadata-driven auto routing accepts photos in the collection mode", () => {
 const d = { ...draft(), kind: "video" as const, mode: "text" };
 const info = inspectDraftMedia(d, { ...model, auto_route_by_inputs: true });
 assert.deepEqual(info.issues, []);
});
