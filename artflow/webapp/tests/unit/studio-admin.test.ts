import assert from "node:assert/strict";
import test from "node:test";
import { AdminSession, FinancialGuard, changedFields, sameFields } from "../../src/lib/studio-admin.ts";

test("authorization revokes entire session and suppresses late reads and subsequent writes", async () => {
  let revoked = 0, sends = 0;
  let release!: (value: unknown) => void;
  const transport = { request: async <T>(path: string) => {
    sends++;
    if (path === "/deny") throw Object.assign(new Error("denied"), { status: 403 });
    return new Promise(resolve => { release = resolve; }) as Promise<T>;
  }, requestWeb: async <T>() => ({} as T) };
  const session = new AdminSession(transport, 7, () => revoked++);
  const late = session.request("/slow");
  await assert.rejects(session.request("/deny"));
  release({ private: "stale" });
  await assert.rejects(late);
  await assert.rejects(session.request("/write", { method: "POST" }));
  assert.equal(revoked, 1); assert.equal(sends, 2);
});

test("requests have finite timeout even when a transport never resolves", async () => {
  const never = async <T>() => new Promise<T>(() => {});
  const session = new AdminSession({ request: never, requestWeb: never }, 7, () => {}, 10);
  await assert.rejects(session.requestWeb("/slow"), /время/);
});

test("financial marker survives reconstruction and unavailable storage blocks send", () => {
  const rows = new Map<string, string>();
  const storage = { getItem: (k: string) => rows.get(k) ?? null, setItem: (k: string, v: string) => { rows.set(k, v); }, removeItem: (k: string) => { rows.delete(k); } };
  const guard = new FinancialGuard(7, "generation", storage);
  guard.begin("fail-refund", 73);
  assert.deepEqual(new FinancialGuard(7, "generation", storage).pending(), { ownerId: 7, action: "fail-refund", targetId: 73 });
  assert.throws(() => guard.begin("fail-refund", 74));
  assert.throws(() => new FinancialGuard(7, "generation", null).begin("fail-refund", 73));
  guard.clear(); assert.equal(guard.pending(), null);
});

test("pricing differences omit unchanged fields and fresh-state comparisons detect overwrite", () => {
  assert.deepEqual(changedFields({ credits: 5, display_name: "Name" }, { credits: 8, display_name: "Name" }), { credits: 8 });
  assert.equal(sameFields({ credits: 5 }, { credits: 7 }), false);
  assert.equal(sameFields({ credits: 5 }, { credits: 5, id: 3 }), true);
});
