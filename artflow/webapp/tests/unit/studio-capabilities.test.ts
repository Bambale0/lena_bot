import test from "node:test";
import assert from "node:assert/strict";
import { supportsPlan, checkoutPrice } from "../../src/lib/billing-methods.ts";
import { attachmentName } from "../../src/lib/download.ts";

const rubles = { key: "starter", title: "Starter", credits: 100, price_rub: 200 };
test("checkout uses the selected plan's real currency and Lava mapping", () => {
  assert.equal(supportsPlan("tbank", rubles), true);
  assert.equal(supportsPlan("tribute", rubles), false);
  assert.equal(supportsPlan("crypto", rubles), false);
  assert.equal(supportsPlan("lava", rubles, ["other"]), false);
  assert.equal(supportsPlan("lava", rubles, [rubles.key]), true);
  assert.equal(checkoutPrice("tribute", rubles), "");
  assert.equal(checkoutPrice("crypto", rubles), "");
  assert.ok(checkoutPrice("tbank", rubles).includes("200"));
});
test("invalid or zero prices fail closed, without ruble fallback", () => {
  for (const invalid of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, undefined]) {
    const plan = { ...rubles, price_rub: invalid, price_tribute_usd: invalid, price_usdt: invalid };
    for (const method of ["tbank", "lava", "tribute", "crypto"] as const) {
      assert.equal(supportsPlan(method, plan, [plan.key]), false);
      assert.equal(checkoutPrice(method, plan), "");
    }
  }
});
test("authenticated attachment keeps UTF8 filenames and strips paths", () => {
  assert.equal(attachmentName('attachment; filename="fallback.png"; filename*=UTF-8\'\'%D1%84%D0%BE%D1%82%D0%BE.png', 81), "фото.png");
  assert.equal(attachmentName('attachment; filename="../../private.png"', 81), ".._.._private.png");
  assert.equal(attachmentName("attachment; filename*=UTF-8''%ZZ", 81), "apix-result-81");
  assert.equal(attachmentName(null, 81), "apix-result-81");
});
