import type { RepeatPayment } from "../features/feed-repeat-payment";

type StoragePort = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const key = (actorId: number) => `apix:pending-topup:v1:${actorId}`;
const unknownPayment = (): RepeatPayment => ({ startedAt: 0, provider: null, planKey: null, transactionId: null, checkoutUrl: null });

export function sameTopupAttempt(first: RepeatPayment, second: RepeatPayment): boolean {
  return first.startedAt === second.startedAt && first.provider === second.provider
    && first.planKey === second.planKey && first.transactionId === second.transactionId;
}

export function clearPendingTopup(storage: StoragePort | null, actorId: number, expected: RepeatPayment): boolean {
  const current = readPendingTopup(storage, actorId);
  return Boolean(current && sameTopupAttempt(current, expected) && savePendingTopup(storage, actorId, null));
}

/** Only identity of the attempt is durable. URLs, credentials and bodies never are. */
export function readPendingTopup(storage: StoragePort | null, actorId: number): RepeatPayment | null {
  if (!storage || !Number.isSafeInteger(actorId) || actorId <= 0) return null;
  try {
    const raw = storage.getItem(key(actorId));
    if (!raw) return null;
    try {
      const value = JSON.parse(raw);
      if (!value || typeof value !== "object") return unknownPayment();
      return { startedAt: typeof value.startedAt === "number" ? value.startedAt : 0,
        provider: ["tbank", "crypto", "tribute", "lava"].includes(value.provider) ? value.provider : null,
        planKey: typeof value.planKey === "string" ? value.planKey : null,
        transactionId: Number.isSafeInteger(value.transactionId) && value.transactionId > 0 ? value.transactionId : null,
        checkoutUrl: null };
    } catch { return unknownPayment(); }
  } catch { return unknownPayment(); }
}

export function savePendingTopup(storage: StoragePort | null, actorId: number, payment: RepeatPayment | null): boolean {
  if (!storage || !Number.isSafeInteger(actorId) || actorId <= 0) return false;
  try {
    if (!payment) { storage.removeItem(key(actorId)); return storage.getItem(key(actorId)) === null; }
    const encoded = JSON.stringify({ startedAt: payment.startedAt, provider: payment.provider, planKey: payment.planKey, transactionId: payment.transactionId });
    storage.setItem(key(actorId), encoded);
    return storage.getItem(key(actorId)) === encoded;
  } catch { return false; }
}
