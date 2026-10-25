import assert from "node:assert/strict";
import test from "node:test";
import { clearPendingTopup, readPendingTopup, savePendingTopup, sameTopupAttempt } from "../../src/lib/topup-recovery.ts";

test("pending topup stores only actor-scoped identity and never checkout URL or private data", () => {
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); } };
  const payment = { startedAt: 123, provider: "tbank" as const, planKey: "small", transactionId: 55, checkoutUrl: "https://pay.example.test/private" };
  assert.equal(savePendingTopup(storage, 7, payment), true);
  assert.deepEqual(readPendingTopup(storage, 7), { ...payment, checkoutUrl: null });
  assert.equal(readPendingTopup(storage, 8), null);
  assert.equal([...values.values()].join("").includes("private"), false);
  assert.equal(savePendingTopup(storage, 7, null), true);
  assert.equal(readPendingTopup(storage, 7), null);
  values.set("apix:pending-topup:v1:7", "broken");
  assert.equal(readPendingTopup(storage, 7)?.transactionId, null);
  assert.ok(readPendingTopup(storage, 7));
});

test("unavailable or non-roundtripping storage never admits an invoice write", () => {
  const pending = { startedAt: 1, provider: null, planKey: null, transactionId: null, checkoutUrl: null };
  assert.equal(savePendingTopup(null, 7, pending), false);
  assert.equal(savePendingTopup({ getItem() { return null; }, setItem() {}, removeItem() {} }, 7, pending), false);
  assert.equal(savePendingTopup({ getItem() { throw new Error("blocked"); }, setItem() {}, removeItem() {} }, 7, pending), false);
});

test("a receipt for attempt A cannot clear newer attempt B even with the same plan and timestamp", () => {
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } };
  const first = { startedAt: 123, provider: "tbank" as const, planKey: "small", transactionId: 55, checkoutUrl: null };
  const second = { ...first, transactionId: 56 };
  assert.equal(sameTopupAttempt(first, { ...first, checkoutUrl: "https://pay.example.test/55" }), true);
  assert.equal(sameTopupAttempt(first, second), false);
  assert.equal(savePendingTopup(storage, 7, second), true);
  assert.equal(clearPendingTopup(storage, 7, first), false);
  assert.equal(readPendingTopup(storage, 7)?.transactionId, 56);
  assert.equal(clearPendingTopup(storage, 7, second), true);
  assert.equal(readPendingTopup(storage, 7), null);
});
