import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import { asArray, asRecord } from "../../src/lib/utils.ts";

// Exercise the production API class while isolating unrelated browser portals.
// Transpile its constructor parameter property, which Node's strip-only loader
// cannot execute; utility functions and FormData remain real.
const compiled = ts.transpileModule(
  readFileSync(new URL("../../src/lib/api.ts", import.meta.url), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } },
).outputText;
const apiModule = { exports: {} };
new Function("exports", "require", compiled)(apiModule.exports, (name: string) => {
  if (name === "@/lib/utils") return { asArray, asRecord };
  if (name === "@/lib/telegram" || name === "@/features/feed-remix-runner") return {};
  throw new Error(`Unexpected API dependency: ${name}`);
});
const { MiniAppApi } = apiModule.exports as { MiniAppApi: new (data: string) => {
  videoPrompt(file: File): Promise<{ prompt: string }>;
} };

function fileWithSize(size: number): File {
  const file = new File(["fixture"], "clip.mp4", { type: "video/mp4" });
  // Synthetic metadata avoids allocating a 100 MiB buffer just to test a cap.
  Object.defineProperty(file, "size", { value: size });
  return file;
}

test("video prompt rejects over-limit files before upload", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response(JSON.stringify({ prompt: "late" })));
  await assert.rejects(new MiniAppApi("fixture").videoPrompt(fileWithSize(100 * 1024 * 1024 + 1)), /100 МБ/);
  assert.equal(fetch.mock.callCount(), 0);
});

test("video prompt accepts the exact 100 MiB file cap and preserves multipart auth", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async (_url, init) => {
    assert.equal(_url, "/api/v1/video-prompt");
    assert.equal(init?.method, "POST");
    assert.equal(new Headers(init?.headers).get("X-Telegram-Init-Data"), "fixture");
    assert.ok(init?.body instanceof FormData);
    assert.equal((init.body.get("file") as File).name, "clip.mp4");
    return new Response(JSON.stringify({ prompt: "valid prompt" }));
  });
  const result = await new MiniAppApi("fixture").videoPrompt(fileWithSize(100 * 1024 * 1024));
  assert.equal(result.prompt, "valid prompt");
  assert.equal(fetch.mock.callCount(), 1);
});
