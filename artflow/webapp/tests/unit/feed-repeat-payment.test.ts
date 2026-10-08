import assert from "node:assert/strict";
import test from "node:test";
import {
  canReopenPayment,
  clearRepeatDraft,
  paymentFromResponse,
  paymentResolution,
  readRepeatDraft,
  repeatDraftKey,
  saveRepeatDraft,
  type RepeatDraft,
  type RepeatPayment,
} from "../../src/features/feed-repeat-payment.ts";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}
const pending: RepeatPayment = {
  startedAt: 1000, provider: "tbank", planKey: "starter", transactionId: null, checkoutUrl: null,
};
const draft: RepeatDraft = {
  savedAt: 1000, references: ["https://example.test/face.jpg"], changeRequest: "Белый костюм",
  modelKey: "nano-banana-2", mode: "image", aspectRatio: "1:1", quality: "2K", count: 1,
  duration: 5, resolution: "720p", grokMode: "normal", payment: null,
};

test("pending invoice creation and edits survive expiry without response or checkout URL", () => {
  const storage = memoryStorage();
  assert.equal(saveRepeatDraft(storage, 7, 201, { ...draft, payment: pending }), true);
  const restored = readRepeatDraft(storage, 7, 201, 1000 + 48 * 60 * 60 * 1000);
  assert.deepEqual(restored?.payment, pending);
  assert.equal(restored?.changeRequest, "Белый костюм");
  assert.deepEqual(restored?.references, ["https://example.test/face.jpg"]);
});

test("ordinary abandoned drafts expire and pending drafts stay actor and source scoped", () => {
  const storage = memoryStorage();
  saveRepeatDraft(storage, 7, 201, draft);
  assert.equal(readRepeatDraft(storage, 7, 201, 1000 + 2 * 60 * 60 * 1000), null);
  saveRepeatDraft(storage, 7, 201, { ...draft, payment: pending });
  assert.equal(readRepeatDraft(storage, 8, 201, 1001), null);
  assert.equal(readRepeatDraft(storage, 7, 202, 1001), null);
});

test("close or successful generation cannot remove unresolved checkout", () => {
  const storage = memoryStorage();
  saveRepeatDraft(storage, 7, 201, { ...draft, payment: pending });
  clearRepeatDraft(storage, 7, 201);
  assert.equal(readRepeatDraft(storage, 7, 201, 1001)?.payment?.planKey, "starter");
  saveRepeatDraft(storage, 7, 201, draft);
  clearRepeatDraft(storage, 7, 201);
  assert.equal(readRepeatDraft(storage, 7, 201, 1001), null);
});

test("failed storage prevents claiming payment recovery is durable", () => {
  const blocked = { getItem: () => null, setItem: () => { throw new Error("blocked"); }, removeItem: () => {} };
  assert.equal(saveRepeatDraft(blocked, 7, 201, { ...draft, payment: pending }), false);
  assert.equal(saveRepeatDraft(null, 7, 201, { ...draft, payment: pending }), false);
});

test("checkout response keeps only reusable HTTPS URL and internal transaction identity", () => {
  const payment = paymentFromResponse(pending, {
    pay_url: "https://pay.example.test/same-checkout", transaction_id: 44,
    provider_token: "must-not-save", external_id: "provider-private", credits: 10,
  });
  assert.deepEqual(payment, { ...pending, transactionId: 44, checkoutUrl: "https://pay.example.test/same-checkout" });
  for (const pay_url of ["javascript:alert(1)", "https://secret:password@example.test/checkout", "http://example.test/pay"]) {
    assert.equal(paymentFromResponse(pending, { pay_url }).checkoutUrl, null);
  }
});

test("only exact owned transaction and provider can settle pending payment", () => {
  const payment = { ...pending, transactionId: 44 };
  assert.equal(paymentResolution(payment, [{ id: 44, provider: "tbank", status: "paid" }]), "paid");
  assert.equal(paymentResolution(payment, [{ id: 44, provider: "tbank", status: "failed" }]), "failed");
  assert.equal(paymentResolution(payment, [{ id: 44, provider: "tbank", status: "refunded" }]), "refunded");
  for (const transactions of [
    [], [{ id: 44, provider: "tbank", status: "pending" }],
    [{ id: 45, provider: "tbank", status: "paid" }], [{ id: 44, provider: "lava", status: "paid" }],
    [{ id: 44, provider: "tbank", status: "cancelled" }],
  ]) assert.equal(paymentResolution(payment, transactions), "pending");
  assert.equal(paymentResolution(pending, [{ id: 44, provider: "tbank", status: "paid" }]), "pending");
  assert.equal(paymentResolution({ ...payment, provider: "crypto" }, [{ id: 44, provider: "cryptobot", status: "paid" }]), "paid");
});

test("legacy Telegram pending draft migrates only using verified actor identity", () => {
  const storage = memoryStorage();
  storage.setItem("apix:feed-repeat-draft:123:201", JSON.stringify({ ...draft, paymentWaiting: true }));
  assert.equal(readRepeatDraft(storage, 7, 201, 1001), null);
  const restored = readRepeatDraft(storage, 7, 201, 48 * 60 * 60 * 1000, 123);
  assert.ok(restored?.payment);
  assert.equal(restored?.changeRequest, "Белый костюм");
});

test("unscoped legacy pending guard never restores another user's editing data", () => {
  const storage = memoryStorage();
  storage.setItem("apix:feed-repeat-draft:session:201", JSON.stringify({ ...draft, paymentWaiting: true }));
  const restored = readRepeatDraft(storage, 7, 201, 1001);
  assert.ok(restored?.payment);
  assert.deepEqual(restored?.references, []);
  assert.equal(restored?.changeRequest, "");
});

test("saved draft strips hidden payloads and malformed pending records stay unresolved", () => {
  const storage = memoryStorage();
  saveRepeatDraft(storage, 7, 201, { ...draft, payment: pending, prompt: "hidden", token: "secret" } as RepeatDraft);
  const raw = storage.getItem(repeatDraftKey(7, 201))!;
  assert.equal(raw.includes("hidden"), false);
  assert.equal(raw.includes("secret"), false);
  storage.setItem(repeatDraftKey(7, 201), JSON.stringify({ ...draft, payment: { unexpected: true } }));
  assert.ok(readRepeatDraft(storage, 7, 201, 1001)?.payment);
});


test("only invoice-backed providers can reopen a checkout, never a reusable Tribute product", () => {
  const checkout = { ...pending, checkoutUrl: "https://pay.example.test/original", transactionId: 44 };
  assert.equal(canReopenPayment(checkout), true);
  assert.equal(canReopenPayment({ ...checkout, provider: "crypto" }), true);
  assert.equal(canReopenPayment({ ...checkout, provider: "lava" }), true);
  assert.equal(canReopenPayment({ ...checkout, provider: "tribute", transactionId: null }), false);
  assert.equal(canReopenPayment({ ...checkout, provider: null }), false);
  assert.equal(canReopenPayment(pending), false);
});
