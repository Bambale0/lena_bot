import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";

/** One in-flight operation, finite deadline, no replay and no state after close/account change. */
export function useConsumerWrite() {
  const current = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const locked = useRef(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [unauthorized, setUnauthorized] = useState(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; current.current?.abort(); }; }, []);
  const run = async <T,>(operation: (signal: AbortSignal) => Promise<T>, success: (value: T, signal: AbortSignal) => void | Promise<void>) => {
    if (current.current || locked.current || !mounted.current) return;
    const controller = new AbortController(); current.current = controller; setBusy(true); setError("");
    const deadline = window.setTimeout(() => { controller.abort(); if (mounted.current) setError("Время ожидания истекло. Обновите данные и проверьте результат перед повторной отправкой."); }, 20_000);
    try {
      const value = await operation(controller.signal);
      if (mounted.current && !controller.signal.aborted) await success(value, controller.signal);
    } catch (e) {
      if (mounted.current && !controller.signal.aborted) {
        if (e instanceof ApiError && [401, 403].includes(e.status)) { locked.current = true; setUnauthorized(true); }
        setError(e instanceof Error ? e.message : "Не удалось сохранить. Проверьте подключение и обновите данные.");
      }
    } finally {
      window.clearTimeout(deadline);
      if (current.current === controller) current.current = null;
      if (mounted.current) setBusy(false);
    }
  };
  return { run, cancel: () => current.current?.abort(), busy, error, setError, unauthorized };
}
