import assert from "node:assert/strict";
import test from "node:test";
import { decimalMinorUnits, positiveSafeInteger, recoverySeconds, validNativeWanId, validTributeUrl, validReviewNote } from "../../src/lib/studio-system.ts";

test("USD conversion preserves cents exactly and rejects unsafe or fractional cents", () => {
  for (const [input, want] of [["10.99", 1099], ["0.29", 29], ["1", 100], ["1.2", 120], ["90071992547409.91", Number.MAX_SAFE_INTEGER]] as const) assert.equal(decimalMinorUnits(input), want);
  for (const input of ["", "-1", "0", "0.001", "1e3", "1.234", "Infinity", "90071992547409.92"]) assert.equal(decimalMinorUnits(input), null);
});
test("settings integers do not silently coerce empty, exponents or overflow", () => {
  assert.equal(positiveSafeInteger("73"), 73);
  for (const input of ["", "0", "-1", "1.5", "1e2", "9007199254740992"]) assert.equal(positiveSafeInteger(input), null);
  assert.equal(recoverySeconds("600"), 600); assert.equal(recoverySeconds("86400"), 86400);
  for (const input of ["", "599", "86401", "600.1"]) assert.equal(recoverySeconds(input), null);
});
test("Wan preserves model variant and supplier notes and Tribute links validate canonically", () => {
  assert.equal(validNativeWanId("wan-3.0", "standard"), true); assert.equal(validNativeWanId("wan-3.0-prime", "prime"), true);
  assert.equal(validNativeWanId("wan-3.0-prime", "standard"), false); assert.equal(validNativeWanId("evil", "standard"), false);
  assert.equal(validReviewNote("   "), false); assert.equal(validReviewNote("  Отчёт поставщика сверен  "), true);
  assert.equal(validReviewNote("🙂".repeat(6)), false);
  assert.equal(validReviewNote("🙂".repeat(500)), true);
  assert.equal(validReviewNote("🙂".repeat(501)), false);
  assert.equal(validTributeUrl("https://web.tribute.tg/p/Ab12"), true);
  for (const url of ["https://web.tribute.tg.evil/p/Ab12", "http://web.tribute.tg/p/Ab12", "https://web.tribute.tg/p/Ab12?x=1", "https://u@web.tribute.tg/p/Ab12"]) assert.equal(validTributeUrl(url), false);
});
