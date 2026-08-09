import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAdvancedVideoPayload,
  supportsMiniappVideoModel,
  validateAdvancedVideoInput,
  videoScenario,
} from "../src/generationCapabilities.js";

test("motion-only models stay visible in Mini App", () => {
  const model = { key: "kling-3.0/motion-control", modes: ["motion"] };
  assert.equal(supportsMiniappVideoModel(model), true);
  assert.equal(videoScenario(model), "motion");
});

test("Gemini Omni payload preserves video and identity controls", () => {
  const model = {
    key: "gemini-omni-video",
    modes: ["text", "image", "video"],
    supports_video_input: true,
    max_refs: 7,
    max_audio_ids: 1,
    max_character_ids: 3,
    has_seed: true,
  };
  const payload = buildAdvancedVideoPayload({
    model,
    mode: "video",
    prompt: "cinematic portrait",
    duration: 8,
    aspectRatio: "16:9",
    resolution: "1080p",
    videoUrl: "https://cdn.example/source.mp4",
    videoStart: 2,
    videoEnd: 9,
    audioIds: ["voice-1"],
    characterIds: ["char-1", "char-2"],
    seed: 42,
  });

  assert.equal(payload.video_url, "https://cdn.example/source.mp4");
  assert.equal(payload.video_start, 2);
  assert.equal(payload.video_end, 9);
  assert.deepEqual(payload.audio_ids, ["voice-1"]);
  assert.deepEqual(payload.character_ids, ["char-1", "char-2"]);
  assert.equal(payload.seed, 42);
});

test("video trim validates backend 10 second limit", () => {
  const model = { key: "gemini-omni-video", modes: ["video"], supports_video_input: true };
  const errors = validateAdvancedVideoInput({
    model,
    mode: "video",
    videoUrl: "https://cdn.example/source.mp4",
    videoStart: 1,
    videoEnd: 12,
  });
  assert.ok(errors.some((message) => message.includes("10 секунд")));
});
