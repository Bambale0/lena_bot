import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import { tabStorage } from "@/lib/draft-storage";
import { AdminSession, FinancialGuard, adminError, type AdminTransport } from "@/lib/studio-admin";

const Context = createContext<AdminSession | null>(null);
export function AdminBoundary({ api, ownerId, children }: { api: MiniAppApi; ownerId: number; children: ReactNode }) {
  return <SessionBoundary key={ownerId} api={api} ownerId={ownerId}>{children}</SessionBoundary>;
}
function SessionBoundary({ api, ownerId, children }: { api: AdminTransport; ownerId: number; children: ReactNode }) {
  const [denied, setDenied] = useState(false);
  const [session, setSession] = useState<AdminSession | null>(null);
  useEffect(() => {
    const current = new AdminSession(api, ownerId, () => setDenied(true));
    setDenied(false); setSession(current);
    return () => current.dispose();
  }, [api, ownerId]);
  if (denied) return <div className="lilac-panel" role="alert"><h2>Доступ администратора утрачен</h2><p>Привилегированные данные скрыты. Откройте приложение заново после восстановления доступа.</p></div>;
  if (!session || !session.active()) return <p role="status">Проверяем доступ…</p>;
  return <Context.Provider value={session}>{children}</Context.Provider>;
}
export function useAdminSession(): AdminSession {
  const session = useContext(Context);
  if (!session) throw new Error("AdminBoundary is required");
  return session;
}
/** Cancels a panel's in-flight preflight on navigation; auth failures still revoke its parent. */
export function AdminScope({ children }: { children: ReactNode }) {
  const parent = useAdminSession();
  return <SessionBoundary api={parent} ownerId={parent.ownerId}>{children}</SessionBoundary>;
}
/** Mutex covers preflight, confirmation execution and readback; never retries. */
export function useAdminMutation() {
  const session = useAdminSession(), mutex = useRef(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const run = async (operation: () => Promise<void>): Promise<boolean> => {
    if (mutex.current || !session.active()) return false;
    mutex.current = true; setBusy(true); setError("");
    try { await operation(); return session.active(); }
    catch (e) { if (session.active()) setError(adminError(e)); return false; }
    finally { mutex.current = false; if (session.active()) setBusy(false); }
  };
  return { busy, error, setError, run };
}
export function useFinancialGuard(scope: string) {
  const session = useAdminSession();
  const guard = useMemo(() => new FinancialGuard(session.ownerId, scope, tabStorage()), [session, scope]);
  const [pending, setPending] = useState(() => guard.pending());
  const begin = (action: string, targetId: number) => { try { guard.begin(action, targetId); } finally { setPending(guard.pending()); } };
  const clear = () => { guard.clear(); setPending(null); };
  return { pending, begin, clear };
}
export function AdminFeedback({ busy, error }: { busy?: boolean; error?: string }) {
  return <>{busy && <p role="status">Загружаем данные…</p>}{error && <p className="lilac-note" role="alert">{error}</p>}</>;
}
export function Confirmation({ open, title = "Подтверждение изменения", children, busy, onCancel, onConfirm }: {
  open: boolean; title?: string; children: ReactNode; busy: boolean; onCancel: () => void; onConfirm: () => void;
}) {
  return <Sheet open={open} role="alertdialog" title={title} onOpenChange={value => { if (!value && !busy) onCancel(); }} footer={<div className="flex flex-wrap gap-2"><Button variant="outline" disabled={busy} onClick={onCancel}>Отмена</Button><Button disabled={busy} onClick={onConfirm}>Подтвердить изменение</Button></div>}>{children}</Sheet>;
}
