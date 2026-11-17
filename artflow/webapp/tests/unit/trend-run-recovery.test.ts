import assert from "node:assert/strict";
import { test } from "node:test";
import { clearPendingTrendRun, parseRecoverableTrendRuns, readPendingTrendRun, savePendingTrendRun, trendRunNeedsReadOnlyRecovery, TREND_RUN_UNCERTAIN_MESSAGE } from "../../src/lib/trend-run-recovery.ts";

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


function memoryStorage() {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => { map.set(key, value); },
    removeItem: (key: string) => { map.delete(key); },
  };
}

test("write-ahead paid trend guard survives reload and is isolated to authenticated actor", () => {
  const storage = memoryStorage();
  const run = { trendId: 14, requestKey: "trend-14-opaque-key-01", startedAt: 123456 };
  assert.equal(savePendingTrendRun(storage, 17, run), true);
  assert.deepEqual(readPendingTrendRun(storage, 17), run);
  assert.equal(readPendingTrendRun(storage, 18), null);
  assert.equal(storage.map.size, 1);
  const stored = [...storage.map.values()].join("");
  assert.ok(stored.includes(run.requestKey));
  for (const secret of ["asset_id", "initData", "prompt", "quoted_credits", "amount_rub", "token"]) {
    assert.equal(stored.includes(secret), false);
  }
  assert.equal(savePendingTrendRun(storage, 17, { ...run, requestKey: "trend-14-another-key" }), false);
  assert.deepEqual(readPendingTrendRun(storage, 17), run);
});

test("lost response and read-only processing/not_found statuses never silently erase guard", () => {
  const storage = memoryStorage();
  const run = { trendId: 14, requestKey: "trend-14-lost-response", startedAt: 1111 };
  assert.equal(savePendingTrendRun(storage, 17, run), true);
  // Both statuses are inconclusive even when a GET returns HTTP 200.
  for (const state of ["not_found", "processing", "uncertain", "unavailable"]) {
    assert.notEqual(state, "complete");
    assert.deepEqual(readPendingTrendRun(storage, 17), run);
    assert.equal(savePendingTrendRun(storage, 17, { ...run, requestKey: "trend-14-retry" }), false);
  }
  assert.equal(clearPendingTrendRun(storage, 17, { ...run, requestKey: "trend-14-other" }), false);
  assert.deepEqual(readPendingTrendRun(storage, 17), run);
  assert.equal(clearPendingTrendRun(storage, 17, run), true);
  assert.equal(readPendingTrendRun(storage, 17), null);
});

test("storage failure or damaged guard fails closed instead of permitting a second paid POST", () => {
  const run = { trendId: 14, requestKey: "trend-14-blocked-key", startedAt: 1111 };
  assert.equal(readPendingTrendRun(null, 17)?.requestKey, "");
  assert.equal(savePendingTrendRun(null, 17, run), false);
  assert.equal(savePendingTrendRun({ getItem() { return null; }, setItem() {}, removeItem() {} }, 17, run), false);
  assert.equal(savePendingTrendRun({ getItem() { throw Error("denied"); }, setItem() {}, removeItem() {} }, 17, run), false);
  const storage = memoryStorage();
  storage.map.set("apix:pending-trend-run:v1:17", "broken");
  assert.deepEqual(readPendingTrendRun(storage, 17), { trendId: 0, requestKey: "", startedAt: 0 });
  assert.equal(savePendingTrendRun(storage, 17, run), false);
  storage.map.set("apix:pending-trend-run:v1:17", JSON.stringify({ ...run, trendId: -2 }));
  assert.equal(readPendingTrendRun(storage, 17)?.requestKey, "");
  assert.equal(clearPendingTrendRun(storage, 17, run), false);
  assert.equal(savePendingTrendRun(storage, 0, run), false);
});

test("old attempt cannot clear a different actor's or newer paid submission", () => {
  const storage = memoryStorage();
  const original = { trendId: 7, requestKey: "trend-7-first-key", startedAt: 111 };
  const next = { trendId: 7, requestKey: "trend-7-next-key", startedAt: 222 };
  assert.equal(savePendingTrendRun(storage, 12, next), true);
  assert.equal(clearPendingTrendRun(storage, 13, next), false);
  assert.equal(clearPendingTrendRun(storage, 12, original), false);
  assert.deepEqual(readPendingTrendRun(storage, 12), next);
  assert.equal(clearPendingTrendRun(storage, 12, next), true);
});

test("server claim inventory accepts only bounded, typed GET-only recovery identities", () => {
  const runs = [
    { trend_id: 12, request_key: "claim-for-trend-12", state: "processing" },
    { trend_id: 9, request_key: "claim-for-trend-9", state: "uncertain" },
  ];
  assert.deepEqual(parseRecoverableTrendRuns({ runs }), runs);
  assert.deepEqual(parseRecoverableTrendRuns({ runs: [] }), []);
  for (const invalid of [
    null,
    {},
    { runs: null },
    { runs: new Array(21).fill(runs[0]) },
    { runs: [{ ...runs[0], trend_id: -1 }] },
    { runs: [{ ...runs[0], request_key: "short" }] },
    { runs: [{ ...runs[0], request_key: "control" + String.fromCharCode(10) + "char" }] },
    { runs: [{ ...runs[0], state: "complete" }] },
    { runs: [{ ...runs[0], state: "unknown" }] },
  ]) {
    assert.equal(parseRecoverableTrendRuns(invalid), null);
  }
});

test("server inventory never upgrades an inconclusive claim into a safe retry", () => {
  const item = { trend_id: 15, request_key: "lost-reply-claim", state: "uncertain" };
  const recovered = parseRecoverableTrendRuns({ runs: [item] });
  assert.equal(recovered?.length, 1);
  assert.equal(recovered?.[0]?.state, "uncertain");
  assert.equal(trendRunNeedsReadOnlyRecovery(504), true);
});
