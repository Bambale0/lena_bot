import assert from "node:assert/strict";
import test from "node:test";
import { checkoutAmountLabel, checkoutOptions } from "../../src/features/feed-repeat-payment.ts";

test("checkout uses only the recommended plan's explicit eligible providers", () => {
  assert.deepEqual(checkoutOptions({ payment_options: [
    { provider: "tribute", amount: 2, currency: "USD" },
  ] }), [{ provider: "tribute", amount: 2, currency: "USD" }]);
  assert.deepEqual(checkoutOptions({}), []);
  assert.deepEqual(checkoutOptions(null), []);
  assert.deepEqual(checkoutOptions({ payment_options: [
    { provider: "unknown", amount: 10, currency: "RUB" },
    { provider: "crypto", amount: 10, currency: "RUB" },
    { provider: "tribute", amount: null, currency: "USD" },
    { provider: "tbank", amount: -10, currency: "RUB" },
    { provider: { toString: 5 }, amount: 10, currency: "RUB" },
    null,
  ] }), []);
});

test("prices show provider charge currency and disclose an unknown Lava offer price", () => {
  assert.equal(checkoutAmountLabel({ provider: "tbank", amount: 100, currency: "RUB" }), "100 ₽");
  assert.equal(checkoutAmountLabel({ provider: "crypto", amount: 1.11, currency: "USDT" }), "1.11 USDT");
  assert.equal(checkoutAmountLabel({ provider: "tribute", amount: 2, currency: "USD" }), "2 USD");
  assert.equal(checkoutAmountLabel({ provider: "lava", amount: null, currency: "RUB" }), "сумма в ₽ на странице оплаты");
  assert.deepEqual(checkoutOptions({ payment_options: [{ provider: "lava", amount: null, currency: "RUB" }] }), [
    { provider: "lava", amount: null, currency: "RUB" },
  ]);
});
