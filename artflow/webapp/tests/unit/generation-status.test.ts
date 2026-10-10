import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

import { generationStatusLabel, isPendingTask } from "../../src/lib/utils.ts";
import type { GenerationTask } from "../../src/lib/types.ts";

test("shared task status keeps internal recovery neutral and pollable until terminal", () => {
  assert.equal(generationStatusLabel("reconciliation_required"), generationStatusLabel("processing"));
  for (const status of ["created", "queued", "pending", "processing", "running", "reconciliation_required"]) {
    assert.equal(isPendingTask({ status } as GenerationTask), true, status);
  }
  for (const status of ["done", "completed", "failed"]) {
    assert.equal(isPendingTask({ status } as GenerationTask), false, status);
  }
  assert.equal(isPendingTask(null), false);
  assert.equal(generationStatusLabel("done"), "Готово");
  assert.equal(generationStatusLabel("failed"), "Ошибка");
});

test("legacy Mini App shows ordinary waiting without exposing provider status", () => {
  const source = readFileSync(new URL("../../src/main.jsx", import.meta.url), "utf8");
  const format = source.match(/function formatGenerationStatus\(status\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(format, "production status formatter must be available");
  const label = vm.runInNewContext(`${format}; formatGenerationStatus`);
  assert.equal(label("reconciliation_required"), label("processing"));
  assert.equal(label("processing"), "В обработке");
  assert.equal(label("done"), "Готово");
  assert.equal(label("failed"), "Ошибка");
});
