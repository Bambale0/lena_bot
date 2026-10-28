import assert from "node:assert/strict";
import test from "node:test";
import { effectiveVideoAspectRatio } from "../../src/lib/draft-media.ts";
import { applyDraftPatch } from "../../src/lib/reference-selection.ts";
import type { GenerationDraft, ModelInfo } from "../../src/lib/types.ts";

test("a saved Grok recipe retains its format when the ordinary draft contains duplicate photo URLs", () => {
  const url = "https://media.example.test/photo.png";
  const model: ModelInfo = { key: "grok-imagine/image-to-video", display_name: "Grok Imagine Video", credits: 0.7,
    modes: ["image"], aspect_ratios: ["16:9", "9:16"], aspect_ratio_min_refs: 2 };
  const ordinary: GenerationDraft = { kind: "video", model: model.key, prompt: "Move the camera", promptId: null,
    sourceTitle: "", aspectRatio: "9:16", quality: "basic", count: 1, taskCount: 1, mode: "image", duration: 10,
    resolution: "720p", referenceUrls: [], referenceMaterials: [
      { id: "first", url, included: true }, { id: "second", url, included: true },
    ], videoUrl: "", videoStart: 0, videoEnd: null, audioIds: [], characterIds: [], seed: null, grokMode: "normal" };
  assert.equal(effectiveVideoAspectRatio(ordinary, model), null);

  const recipe = applyDraftPatch(ordinary, { promptId: 55 });
  const snapshot = structuredClone(recipe);
  assert.deepEqual(recipe.referenceUrls, [url, url]);
  assert.equal(effectiveVideoAspectRatio(recipe, model), "9:16");
  assert.deepEqual(recipe, snapshot);
  assert.equal(ordinary.referenceMaterials?.length, 2);
});
