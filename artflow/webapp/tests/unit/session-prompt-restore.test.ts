import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";

const source = readFileSync(new URL("../../../landing/js/prototype-premium.js", import.meta.url), "utf8");
function functionSource(name: string, following: string): string {
  return source.slice(source.indexOf(`function ${name}(`), source.indexOf(`function ${following}(`));
}
const reason = "Промпт недоступен для восстановления. Введите описание заново.";

test("restored unknown session visibly explains why its prompt is unavailable", () => {
  const root = { hidden: true, innerHTML: "" };
  runInNewContext(functionSource("renderActiveImageSession", "applyActiveImageSession") + "renderActiveImageSession();", {
    $: () => root,
    state: { user: { id: 1 }, generationKind: "image", activeImageSession: { id: 2, model: "test", prompt_hidden: true, prompt_unavailable_reason: reason } },
    uniqueSafeUrls: () => [], escapeHtml: String, cleanModelName: String,
  });
  assert.equal(root.hidden, false);
  assert.ok(root.innerHTML.includes(reason));
});

test("continuing an unknown session keeps typed input and explains reentry", () => {
  const prompt = { value: "new user text" };
  const toasts: unknown[][] = [];
  runInNewContext(functionSource("applyActiveImageSession", "archiveActiveImageSession").replace(/async\s*$/, "") + "applyActiveImageSession();", {
    state: { activeImageSession: { id: 2, model: "test", prompt_hidden: true, prompt_unavailable_reason: reason } },
    document: { querySelector: () => ({ querySelector: (name: string) => name === "[name='prompt']" ? prompt : null }) },
    renderModels() {}, uniqueSafeUrls: () => [], setGenerationFlow() {}, updateGenerationEstimate() {}, refreshCustomSelects() {},
    toast: (...args: unknown[]) => toasts.push(args),
  });
  assert.equal(prompt.value, "new user text");
  assert.equal(toasts[0]?.[0], reason);
});

test("continuing a trusted own session restores its text", () => {
  const prompt = { value: "" };
  runInNewContext(functionSource("applyActiveImageSession", "archiveActiveImageSession").replace(/async\s*$/, "") + "applyActiveImageSession();", {
    state: { activeImageSession: { id: 2, model: "test", prompt_hidden: false, base_prompt: "my saved text" } },
    document: { querySelector: () => ({ querySelector: (name: string) => name === "[name='prompt']" ? prompt : null }) },
    renderModels() {}, uniqueSafeUrls: () => [], setGenerationFlow() {}, updateGenerationEstimate() {}, refreshCustomSelects() {}, toast() {},
  });
  assert.equal(prompt.value, "my saved text");
});
