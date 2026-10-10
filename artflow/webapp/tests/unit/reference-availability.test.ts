import test from "node:test";
import assert from "node:assert/strict";
import { parseReferenceAvailability, referenceAvailabilityMessage } from "../../src/lib/reference-availability.ts";
for (const state of ["available", "missing", "unknown", "forbidden", "temporary_error"] as const) {
  test(`preserves explicit availability state ${state}`, () => {
    assert.equal(parseReferenceAvailability({ status: state }), state);
    assert.ok(referenceAvailabilityMessage(state));
    assert.ok(referenceAvailabilityMessage(state, true));
  });
}
for (const raw of [null, [], {}, { status: true }, { status: "refreshable" }, { status: "ok" }]) {
  test(`malformed response is not a positive check: ${JSON.stringify(raw)}`, () => {
    assert.equal(parseReferenceAvailability(raw), "temporary_error");
  });
}
