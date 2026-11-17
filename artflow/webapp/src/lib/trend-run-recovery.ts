/** A POST may have been charged even when its response was lost. Never blindly replay it. */
export function trendRunNeedsReadOnlyRecovery(httpStatus?: number): boolean {
  return httpStatus === undefined || httpStatus >= 500 || [408, 409, 429].includes(httpStatus);
}

export const TREND_RUN_UNCERTAIN_MESSAGE =
  "Результат запуска пока не подтверждён. Новую генерацию не запускаем: задача уже могла быть создана. Проверь статус или историю работ.";

/** This is an actor-scoped recovery guard, not authorization or proof of a charge. */
export type PendingTrendRun = {
  trendId: number;
  requestKey: string;
  startedAt: number;
};

type StoragePort = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const pendingKey = (actorId: number) => `apix:pending-trend-run:v1:${actorId}`;
const validActor = (id: number) => Number.isSafeInteger(id) && id > 0;
const validRun = (value: PendingTrendRun) =>
  Number.isSafeInteger(value.trendId) && value.trendId > 0
  && typeof value.requestKey === "string"
  && /^[A-Za-z0-9._:-]{8,128}$/.test(value.requestKey)
  && Number.isSafeInteger(value.startedAt) && value.startedAt > 0;
// A damaged or inaccessible guard is not evidence that another payable POST is safe.
const unknownRun = (): PendingTrendRun => ({ trendId: 0, requestKey: "", startedAt: 0 });

export function readPendingTrendRun(storage: StoragePort | null, actorId: number): PendingTrendRun | null {
  if (!validActor(actorId)) return unknownRun();
  if (!storage) return unknownRun();
  try {
    const raw = storage.getItem(pendingKey(actorId));
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return unknownRun();
    const item = parsed as PendingTrendRun;
    return validRun(item)
      ? { trendId: item.trendId, requestKey: item.requestKey, startedAt: item.startedAt }
      : unknownRun();
  } catch { return unknownRun(); }
}

/** Write-ahead guard: the POST cannot begin unless its identity is persisted. */
export function savePendingTrendRun(storage: StoragePort | null, actorId: number, run: PendingTrendRun): boolean {
  if (!storage || !validActor(actorId) || !validRun(run)) return false;
  try {
    // Never replace an unresolved attempt, even if its key or data are corrupt.
    if (storage.getItem(pendingKey(actorId)) !== null) return false;
    const value = JSON.stringify(run);
    storage.setItem(pendingKey(actorId), value);
    return storage.getItem(pendingKey(actorId)) === value;
  } catch { return false; }
}

/** A prior result must not clear a newer unresolved payable attempt. */
export function clearPendingTrendRun(storage: StoragePort | null, actorId: number, expected: PendingTrendRun): boolean {
  if (!storage || !validActor(actorId) || !validRun(expected)) return false;
  try {
    const current = readPendingTrendRun(storage, actorId);
    if (current?.requestKey !== expected.requestKey || current.trendId !== expected.trendId) return false;
    storage.removeItem(pendingKey(actorId));
    return storage.getItem(pendingKey(actorId)) === null;
  } catch { return false; }
}

/** Backend evidence for GET-only recovery; never a receipt or permission to retry. */
export type RecoverableTrendRun = {
  trend_id: number;
  request_key: string;
  state: "processing" | "uncertain";
};

export function parseRecoverableTrendRuns(value: unknown): RecoverableTrendRun[] | null {
  if (!value || typeof value !== "object") return null;
  const runs = (value as { runs?: unknown }).runs;
  if (!Array.isArray(runs) || runs.length > 20) return null;
  const result: RecoverableTrendRun[] = [];
  for (const entry of runs) {
    if (!entry || typeof entry !== "object") return null;
    const claim = entry as Record<string, unknown>;
    if (!Number.isSafeInteger(claim.trend_id) || (claim.trend_id as number) <= 0
      || typeof claim.request_key !== "string"
      || claim.request_key.length < 8 || claim.request_key.length > 128
      || /[\x00-\x1f]/.test(claim.request_key)
      || (claim.state !== "processing" && claim.state !== "uncertain")) return null;
    result.push({
      trend_id: claim.trend_id as number,
      request_key: claim.request_key,
      state: claim.state,
    });
  }
  return result;
}
