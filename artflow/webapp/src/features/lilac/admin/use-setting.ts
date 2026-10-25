import { useEffect, useState } from "react";
import { changedFields, sameFields } from "@/lib/studio-admin";
import { useAdminMutation, useAdminSession } from "./primitives";

interface Change<V> { before: V; next: V; revision?: number; }
/** Explicit two-stage confirmation, fresh comparisons and readback. No replay after an error. */
export function useSetting<T extends object, V extends object>(path: string, fields: (value: T) => V, revision?: (value: T) => number) {
  const session = useAdminSession(), mutation = useAdminMutation();
  const [data, setData] = useState<T | null>(null), [change, setChange] = useState<Change<V> | null>(null);
  const [locked, setLocked] = useState(false), [notice, setNotice] = useState("");
  const load = () => mutation.run(async () => {
    setData(null); setChange(null); setNotice(""); setLocked(true);
    const result = await session.requestWeb<T>(path);
    if (revision && (!Number.isSafeInteger(revision(result)) || revision(result) < 0)) throw new Error("Сервер не вернул допустимую версию. Сохранение заблокировано.");
    setData(result); setLocked(false);
  });
  useEffect(() => { void load(); }, [session, path]);
  const fresh = async (expected: Change<V>) => {
    const result = await session.requestWeb<T>(path);
    if (!sameFields(expected.before, fields(result)) || revision && revision(result) !== expected.revision) throw new Error("Исходные настройки изменились. Обновите настройку и подтвердите заново.");
  };
  const prepare = (next: V) => void mutation.run(async () => {
    if (!data || locked || !Object.keys(changedFields(fields(data), next)).length) return;
    setNotice("");
    const pending = { before: fields(data), next, revision: revision?.(data) };
    try { await fresh(pending); setChange(pending); } catch (error) { setLocked(true); throw error; }
  });
  const execute = () => void mutation.run(async () => {
    if (!change || locked) return;
    const pending = change;
    try {
      await fresh(pending);
      // These PUT DTOs require their complete command fields; do not omit required fields.
      const body = revision ? { ...pending.next, expected_revision: pending.revision } : pending.next;
      const result = await session.requestWeb<T>(path, { method: "PUT", body: JSON.stringify(body) });
      if (!sameFields(pending.next, fields(result)) || revision && revision(result) !== pending.revision! + 1) throw new Error("Ответ не подтверждает изменение. Обновите настройку и сверьте результат.");
      const actual = await session.requestWeb<T>(path);
      if (!sameFields(pending.next, fields(actual)) || revision && revision(actual) !== revision(result)) throw new Error("Повторное чтение не подтвердило изменение. Обновите настройку.");
      setData(actual); setNotice("Настройка сохранена и проверена.");
    } catch (error) { setLocked(true); throw error; }
    finally { if (session.active()) setChange(null); }
  });
  return { ...mutation, data, change, notice, locked, load, prepare, execute, cancel: () => setChange(null), changed: (next: V) => Boolean(data && Object.keys(changedFields(fields(data), next)).length) };
}
