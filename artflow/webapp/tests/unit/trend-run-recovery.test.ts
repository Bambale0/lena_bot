import assert from "node:assert/strict";
import { test } from "node:test";
import { trendRunNeedsReadOnlyRecovery, TREND_RUN_UNCERTAIN_MESSAGE } from "../../src/lib/trend-run-recovery.ts";

test("ambiguous paid trend POST results require status lookup, never blind retry", () => {
  for (const status of [undefined, 408, 409, 429, 500, 502, 503, 504]) {
    assert.equal(trendRunNeedsReadOnlyRecovery(status), true, String(status));
  }
});

test("definitive client rejects remain distinct from ambiguous outcomes", () => {
  for (const status of [400, 401, 402, 403, 404, 422]) {
    assert.equal(trendRunNeedsReadOnlyRecovery(status), false, String(status));
  }
  assert.match(TREND_RUN_UNCERTAIN_MESSAGE, /не запускаем/i);
  assert.match(TREND_RUN_UNCERTAIN_MESSAGE, /статус/i);
});
