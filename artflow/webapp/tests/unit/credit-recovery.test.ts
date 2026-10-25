import assert from "node:assert/strict";
import test from "node:test";
import { isInsufficientCreditError } from "../../src/lib/credit-recovery.ts";

test("recognizes actual pre-spend shortage responses without interpreting amounts", () => {
  for (const message of ["Insufficient credits: need 10, have 0", "Insufficient credits: need 1.5", "Недостаточно кредитов. Нужно 10 💋"]) {
    assert.equal(isInsufficientCreditError(Object.assign(new Error(message), { status: 402 })), true);
  }
});
test("provider failures, failed spending, auth and arbitrary 402 are not a topup diagnosis", () => {
  for (const [status, message] of [[402, "Failed to spend credits"], [402, "Payment required"], [402, "Provider account has insufficient credits"], [401, "Insufficient credits: need 10"], [503, "Insufficient credits: need 10"]]) {
    assert.equal(isInsufficientCreditError(Object.assign(new Error(String(message)), { status })), false);
  }
  assert.equal(isInsufficientCreditError(new Error("Insufficient credits: need 10")), false);
  assert.equal(isInsufficientCreditError(null), false);
});
