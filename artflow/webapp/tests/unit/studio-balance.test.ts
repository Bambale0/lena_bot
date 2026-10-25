import assert from "node:assert/strict";
import { test } from "node:test";
import { publishStudioBalance, readStudioBalance, subscribeStudioBalance } from "../../src/lib/studio-balance.ts";

test("balance bridge has a stable immutable snapshot and revokes stale actor actions", () => {
  let opened = 0, updates = 0;
  const stop = subscribeStudioBalance(() => updates++);
  publishStudioBalance({ actorId: 7, credits: 12, language: "ru", open: false, onOpen: () => opened++ });
  const first = readStudioBalance()!;
  assert.equal(first, readStudioBalance()); assert.equal(Object.isFrozen(first), true);
  first.onOpen(); assert.equal(opened, 1);
  publishStudioBalance(null); first.onOpen(); assert.equal(opened, 1);
  publishStudioBalance({ actorId: 9, credits: 3, language: "en", open: false, onOpen: () => opened++ });
  first.onOpen(); assert.equal(opened, 1); readStudioBalance()!.onOpen(); assert.equal(opened, 2);
  assert.equal(updates, 3); stop(); publishStudioBalance(null); assert.equal(updates, 3);
});
