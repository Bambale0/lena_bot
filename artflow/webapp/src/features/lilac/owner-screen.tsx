import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import { formatCredits } from "@/lib/utils";
import { tabStorage } from "@/lib/draft-storage";
import { LilacModeration } from "./moderation-panel";
import { AdminBoundary, useAdminSession } from "./admin/primitives";
import { LilacAdminWorkspace } from "./admin/workspace";

interface Account { id: number; tg_id: number; full_name?: string; username?: string; credits: number; is_banned: boolean; }
interface Withdrawal { id: number; amount_rub: number; status: string; payout_details: string; user: Account; }
interface Detail {
  user: Account;
  stats: { generations_count?: number; payments_count?: number; paid_rub?: number; referrals?: { l1?: number; l2?: number; l3?: number } };
  ledger: Array<{ id: number; delta: number; balance_after?: number; entry_type?: string; note?: string; created_at?: string }>;
  transactions?: Array<{ id: number; provider: string; status: string; amount_rub?: number; credits?: number; created_at?: string }>;
  generations?: Array<{ id: number; model: string; gen_type: string; status: string; credits_spent?: number; created_at?: string }>;
  withdrawals?: Array<{ id: number; amount_rub: number; status: string; payout_details?: string; admin_note?: string; created_at?: string }>;
}
interface Action { path: string; body: Record<string, unknown>; title: string; }
interface PendingAdjustment { targetId: number; title: string; }

export function LilacOwner({ api, ownerId, systemPanel }: { api: MiniAppApi; ownerId: number; systemPanel?: ReactNode }) {
  return <AdminBoundary api={api} ownerId={ownerId}><OwnerContent api={api} ownerId={ownerId} systemPanel={systemPanel} /></AdminBoundary>;
}
function OwnerContent({ api, ownerId, systemPanel }: { api: MiniAppApi; ownerId: number; systemPanel?: ReactNode }) {
  const session = useAdminSession();
  const pendingKey = `apix:lilac:owner-adjustment:${ownerId}`;
  const [pending, setPending] = useState<PendingAdjustment | null>(() => {
    try { const raw = tabStorage()?.getItem(pendingKey); if (!raw) return null;
      const row = JSON.parse(raw); return Number.isSafeInteger(row.targetId) && row.targetId > 0 && typeof row.title === "string" ? row : { targetId: 0, title: "Незавершённая корректировка" };
    } catch { return { targetId: 0, title: "Состояние корректировки недоступно" }; }
  });
  const mutation = useRef(false);
  const [ledgerReviewed, setLedgerReviewed] = useState(false);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [users, setUsers] = useState<Account[]>([]), [withdrawals, setWithdrawals] = useState<Withdrawal[]>([]);
  const [query, setQuery] = useState(""), [status, setStatus] = useState("pending");
  const [detail, setDetail] = useState<Detail | null>(null), [amount, setAmount] = useState(""), [note, setNote] = useState("");
  const [action, setAction] = useState<Action | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const load = async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try {
      const [overview, accounts, requests] = await Promise.all([session.request<{ summary: Record<string, number> }>("/admin/overview", {}, signal), session.request<{ items: Account[] }>(`/admin/users?query=${encodeURIComponent(query)}&limit=25`, {}, signal), session.request<{ items: Withdrawal[] }>(`/admin/withdrawals?status=${status}`, {}, signal)]);
      if (!signal?.aborted) { setSummary(overview.summary); setUsers(accounts.items); setWithdrawals(requests.items); }
    } catch (e) { if (!signal?.aborted) setError(e instanceof Error ? e.message : "Нет доступа к управлению"); }
    finally { if (!signal?.aborted) setLoading(false); }
  };
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [session, status]);
  const openAccount = async (id: number) => {
    if (busy || !session.active()) return;
    setBusy(true);
    try { setDetail(await session.request<Detail>(`/admin/users/${id}`, { cache: "no-store" })); setAmount(""); setNote(""); if (pending?.targetId === id) setLedgerReviewed(true); }
    catch (e) { if (session.active()) toast.error(e instanceof Error ? e.message : "Не удалось открыть аккаунт"); }
    finally { setBusy(false); }
  };
  const execute = async () => {
    if (!action || busy || mutation.current || pending || !session.active()) return;
    const creditTarget = /^\/admin\/users\/(\d+)\/credits$/.exec(action.path);
    if (creditTarget) {
      const marker = { targetId: Number(creditTarget[1]), title: action.title };
      try { const storage = tabStorage(); if (!storage) throw new Error(); storage.setItem(pendingKey, JSON.stringify(marker)); }
      catch { toast.error("Нельзя безопасно сохранить состояние операции. Корректировка не отправлена."); return; }
      setPending(marker); setLedgerReviewed(false);
    }
    mutation.current = true;
    setBusy(true);
    try {
      await session.request(action.path, { method: "POST", body: JSON.stringify(action.body) });
      if (creditTarget) { try { tabStorage()?.removeItem(pendingKey); setPending(null); } catch { /* Keep pending until explicit ledger review. */ } }
      setAction(null); setDetail(null); toast.success("Изменение сохранено"); await load();
    } catch (e) {
      if (!session.active()) return;
      setAction(null);
      toast.error(creditTarget ? "Ответ не подтверждён. Не повторяйте корректировку — сначала проверьте историю баланса." : e instanceof Error ? e.message : "Не удалось сохранить изменение");
    }
    finally { mutation.current = false; setBusy(false); }
  };
  const acknowledge = () => {
    if (!pending || !ledgerReviewed || busy) return;
    try { const storage = tabStorage(); if (!storage) throw new Error(); storage.removeItem(pendingKey); setPending(null); setLedgerReviewed(false); }
    catch { toast.error("Не удалось снять блокировку. Повторный запрос не отправлен."); }
  };
  const metrics: Array<[string, string]> = [["users_total", "Пользователи"], ["generations_7d", "Генерации за 7 дней"], ["revenue_7d", "Доход за 7 дней, ₽"], ["pending_withdrawals_count", "Заявки на вывод"]];
  return <div className="lilac-page"><header className="lilac-title"><p>Только для администратора</p><h1>Управление APIX</h1><span>Данные и операции проверяются сервером. Изменение баланса и статуса требует подтверждения.</span></header>
    {pending && <div className="lilac-panel" role="alert"><h2>Результат корректировки не подтверждён</h2><p>{pending.title}</p><p>Запрос мог выполниться. Повтор заблокирован, в том числе после перезагрузки. Сверьте баланс и историю изменений; ответственный администратор должен решить, нужна ли новая операция.</p>{pending.targetId > 0 && <Button disabled={busy} onClick={() => void openAccount(pending.targetId)}>Проверить историю корректировки</Button>}{ledgerReviewed && <Button variant="outline" disabled={busy} onClick={acknowledge}>Я сверил историю, разрешить новые операции</Button>}</div>}
    {loading && <p role="status">Загружаем кабинет…</p>}{error && <div role="alert"><p>{error}</p><Button onClick={() => void load()}>Повторить</Button></div>}
    <div className="lilac-task-grid">{metrics.map(([key, label]) => <div className="lilac-create-card" key={key}><strong>{formatCredits(summary[key] || 0)}</strong><span>{label}</span></div>)}</div>
    <LilacModeration key={ownerId} api={api} />
    <LilacAdminWorkspace api={api} ownerId={ownerId} systemPanel={systemPanel} />
    <section><h2>Пользователи</h2><form className="flex gap-2" onSubmit={e => { e.preventDefault(); void load(); }}><Input aria-label="Поиск пользователя" value={query} onChange={e => setQuery(e.target.value)} placeholder="Имя, username или ID" /><Button type="submit" disabled={loading}>Найти</Button></form>
      {users.map(user => <button className="lilac-row" disabled={busy} key={user.id} onClick={() => void openAccount(user.id)}><span><strong>{user.full_name || user.username || `ID ${user.id}`}</strong><small>{formatCredits(user.credits)} кр. · {user.is_banned ? "Заблокирован" : "Активен"}</small></span></button>)}
      {!loading && !error && !users.length && <p className="lilac-note">Пользователи не найдены.</p>}
    </section>
    <section><h2>Заявки на вывод</h2><Select aria-label="Статус заявок на вывод" value={status} onChange={e => setStatus(e.target.value)}><option value="pending">Ожидают решения</option><option value="approved">Подтверждённые</option><option value="rejected">Отклонённые</option><option value="all">Все</option></Select>
      {withdrawals.map(item => <div className="lilac-withdrawal" key={item.id}><strong>#{item.id} · {item.user.full_name || item.user.username || item.user.id} · {formatCredits(item.amount_rub)} ₽</strong><p className="break-words">{item.payout_details}</p><p>{item.status}</p>{item.status === "pending" && <div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => { setDetail(null); setAction({ path: `/admin/withdrawals/${item.id}/review`, body: { action: "approve" }, title: `Подтвердить заявку #${item.id} на ${formatCredits(item.amount_rub)} ₽?` }); }}>Подтвердить заявку</Button><Button variant="outline" disabled={busy} onClick={() => { setDetail(null); setAction({ path: `/admin/withdrawals/${item.id}/review`, body: { action: "reject" }, title: `Отклонить заявку #${item.id}?` }); }}>Отклонить</Button></div>}</div>)}
      {!loading && !error && !withdrawals.length && <p className="lilac-note">В этой категории заявок нет.</p>}
      <p className="lilac-note">Подтверждение меняет статус заявки. Оно не означает автоматический перевод денег.</p>
    </section>
    <Sheet open={Boolean(detail)} title={detail?.user.full_name || "Аккаунт пользователя"} onOpenChange={open => { if (!open) setDetail(null); }}>
      {detail && <div className="grid gap-3"><p>ID {detail.user.id} · Telegram {detail.user.tg_id}</p><p>Баланс: {formatCredits(detail.user.credits)} кр.</p><label>Корректировка кредитов<Input aria-label="Корректировка кредитов" type="number" step="any" value={amount} onChange={e => setAmount(e.target.value)} /><small>Положительное число — начислить; отрицательное — списать.</small></label><label>Комментарий<Input value={note} maxLength={500} onChange={e => setNote(e.target.value)} /></label>
        <p>Генераций: {detail.stats?.generations_count || 0} · Платежей: {detail.stats?.payments_count || 0} · Оплачено: {formatCredits(detail.stats?.paid_rub || 0)} ₽</p>
        <p>Рефералы по уровням: {detail.stats?.referrals?.l1 || 0} / {detail.stats?.referrals?.l2 || 0} / {detail.stats?.referrals?.l3 || 0}</p>
        <details><summary>Платежи</summary>{detail.transactions?.length ? detail.transactions.map(row => <div className="lilac-panel" key={row.id}><strong>Платёж #{row.id}</strong><p>{row.provider} · {row.status} · {formatCredits(row.amount_rub || 0)} ₽ · {formatCredits(row.credits || 0)} кр.</p><small>{row.created_at}</small></div>) : <p>Платежей пока нет.</p>}</details>
        <details><summary>Генерации</summary>{detail.generations?.length ? detail.generations.map(row => <div className="lilac-panel" key={row.id}><strong>Задача #{row.id}</strong><p>{row.model} · {row.gen_type} · {row.status} · {formatCredits(row.credits_spent || 0)} кр.</p><small>{row.created_at}</small></div>) : <p>Генераций пока нет.</p>}</details>
        <details><summary>Вывод средств пользователя</summary>{detail.withdrawals?.length ? detail.withdrawals.map(row => <div className="lilac-panel" key={row.id}><strong>Заявка #{row.id} · {formatCredits(row.amount_rub)} ₽</strong><p>{row.status} · {row.payout_details}</p>{row.admin_note && <p>{row.admin_note}</p>}<small>{row.created_at}</small></div>) : <p>Заявок пока нет.</p>}</details>
        <Button disabled={busy || Boolean(pending) || !Number.isFinite(Number(amount)) || Number(amount) === 0 || !note.trim()} onClick={() => { setAction({ path: `/admin/users/${detail.user.id}/credits`, body: { amount: Number(amount), note: note.trim() }, title: `Изменить баланс пользователя #${detail.user.id} на ${amount} кредитов?` }); setDetail(null); }}>Проверить изменение баланса</Button>
        <Button variant="outline" disabled={busy} onClick={() => { setAction({ path: `/admin/users/${detail.user.id}/ban`, body: { banned: !detail.user.is_banned }, title: `${detail.user.is_banned ? "Разблокировать" : "Заблокировать"} пользователя #${detail.user.id}?` }); setDetail(null); }}>{detail.user.is_banned ? "Разблокировать" : "Заблокировать"}</Button>
        <h3>Последние изменения баланса</h3>{detail.ledger?.map(row => <div key={row.id}><p>#{row.id} · {row.delta > 0 ? "+" : ""}{formatCredits(row.delta)} · {row.note || "Изменение баланса"}</p><small>{row.entry_type} · {row.balance_after != null ? `Остаток ${formatCredits(row.balance_after)} кр. · ` : ""}{row.created_at}</small></div>)}
      </div>}
    </Sheet>
    <Sheet open={Boolean(action)} title="Подтверждение действия" onOpenChange={open => { if (!open && !busy) setAction(null); }} footer={<div className="flex gap-2"><Button variant="outline" disabled={busy} onClick={() => setAction(null)}>Отмена</Button><Button disabled={busy || Boolean(pending)} onClick={() => void execute()}>{busy ? "Сохраняем…" : "Подтвердить действие"}</Button></div>}><p>{action?.title}</p></Sheet>
  </div>;
}
