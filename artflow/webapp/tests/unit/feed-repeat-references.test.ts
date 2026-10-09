import assert from "node:assert/strict";
import test from "node:test";
import { feedUserReferenceCapacity } from "../../src/features/feed-repeat-references.ts";

test("image source reserves exactly one model reference slot", () => {
  assert.equal(feedUserReferenceCapacity({ max_refs: 4 }, false), 3);
  assert.equal(feedUserReferenceCapacity({ max_refs: 1 }, false), 0);
  assert.equal(feedUserReferenceCapacity({ max_refs: 0 }, false), 0);
  assert.equal(feedUserReferenceCapacity(undefined, false), 0);
});

test("a supported video source does not consume a photo slot", () => {
  assert.equal(feedUserReferenceCapacity({ max_refs: 4, supports_video_input: true }, true), 4);
  assert.equal(feedUserReferenceCapacity({ max_refs: 4, supports_video_input: false }, true), 0);
});

test("unknown or invalid capacities never permit uploads", () => {
  for (const max_refs of [undefined, -1, 0.5, NaN, Infinity]) {
    assert.equal(feedUserReferenceCapacity({ max_refs }, false), 0);
    assert.equal(feedUserReferenceCapacity({ max_refs, supports_video_input: true }, true), 0);
  }
});

test("provider shared-media quota limits photos beside a source video", () => {
  const model = { max_refs: 7, supports_video_input: true, max_refs_with_video: 5 };
  assert.equal(feedUserReferenceCapacity(model, true), 5);
  assert.equal(feedUserReferenceCapacity(model, false), 6);
  assert.equal(feedUserReferenceCapacity({ ...model, max_refs_with_video: 99 }, true), 7);
  assert.equal(feedUserReferenceCapacity({ ...model, max_refs_with_video: -1 }, true), 0);
});
