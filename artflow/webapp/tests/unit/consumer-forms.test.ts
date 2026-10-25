import test from "node:test";
import assert from "node:assert/strict";
import { consumerMediaUrl, initialSeriesSettings, publicationTags, seriesValidation, uploadedImage } from "../../src/features/lilac/consumer-forms.ts";
import type { ModelInfo } from "../../src/lib/types.ts";

const model: ModelInfo = { key: "photo", display_name: "Фото", credits: 5, modes: ["text", "image"], max_refs: 2, counts: [1, 2], aspect_ratios: ["1:1"], quality_options: [{ value: "basic" }, { value: "high" }] };

test("public cover rejects unsafe protocols credentials cleartext and malformed addresses", () => {
  for (const raw of ["javascript:alert(1)", "data:image/png,x", "https://user:secret@example.test/image.png", "http://example.test/image.png", "not-a-url", "//example.test/image.png"]) assert.equal(consumerMediaUrl(raw), "", raw);
  assert.equal(consumerMediaUrl(" https://media.example.test/image.png "), "https://media.example.test/image.png");
});

test("upload must identify an image and provide a safe media URL", () => {
  assert.equal(uploadedImage({ url: "https://media.example.test/a.png", kind: "image" }), "https://media.example.test/a.png");
  for (const result of [{ url: "https://media.example.test/a.mp3", kind: "audio" }, { url: "https://media.example.test/a.png" }, { url: "javascript:x", kind: "image" }, { url: "https://media.example.test/a.png", kind: "image", content_type: "text/html" }]) assert.throws(() => uploadedImage(result));
});

test("publication tags are trimmed nonempty and unique in original order", () => assert.deepEqual(publicationTags(" портрет, свет, ,портрет "), ["портрет", "свет"]));

test("series rejects removed model unsupported settings capacity and unsafe media without changing inputs", () => {
  const settings = initialSeriesSettings(model);
  assert.equal(seriesValidation(settings, model, []), "");
  assert.ok(seriesValidation(settings, undefined, []));
  for (const changed of [{ ...settings, mode: "video" }, { ...settings, count: 6 }, { ...settings, quality: "unknown" }, { ...settings, aspect_ratio: "3:4" }]) assert.ok(seriesValidation(changed, model, []));
  const refs = ["https://media.example.test/1.png", "https://media.example.test/2.png", "https://media.example.test/3.png"];
  assert.ok(seriesValidation(settings, model, refs)); assert.equal(refs.length, 3);
  assert.ok(seriesValidation(settings, model, ["javascript:x"]));
  assert.ok(seriesValidation(settings, { ...model, max_refs: 0 }, [refs[0]]));
  assert.ok(seriesValidation(settings, { ...model, aspect_ratio_modes: ["image"] }, []));
  assert.equal(seriesValidation({ ...settings, aspect_ratio: null }, { ...model, aspect_ratio_modes: ["image"] }, []), "");
});
