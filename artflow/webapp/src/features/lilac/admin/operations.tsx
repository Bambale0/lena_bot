import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { formatCredits, generationStatusLabel } from "@/lib/utils";
import { adminError, readGeneration, type FailureResult, type GenerationPage, type GenerationRow, type LedgerRow } from "@/lib/studio-admin";
import { AdminFeedback, Confirmation, useAdminMutation, useAdminSession, useFinancialGuard } from "./primitives";

const running = (row: GenerationRow) => row.status === "pending" || row.status === "processing";
export function AdminOperations() {
  const session = useAdminSession(), mutation = useAdminMutation(), guard = useFinancialGuard("generation");
  const [status, setStatus] = useState("all"), [kind, setKind] = useState("all"), [query, setQuery] = useState("");
  const [filter, setFilter] = useState({ status: "all", kind: "all", query: "", offset: 0 });
  const [page, setPage] = useState<GenerationPage | null>(null), [loading, setLoading] = useState(false), [error, setError] = useState("");
  const [selected, setSelected] = useState<GenerationRow | null>(null), [reason, setReason] = useState(""), [refund, setRefund] = useState(true);
  const [confirm, setConfirm] = useState(false), [result, setResult] = useState(""), [reconciled, setReconciled] = useState(false);
  const sequence = useRef(0);
  useEffect(() => {
    const controller = new AbortController(), version = ++sequence.current;
    setLoading(true); setPage(null); setError("");
    const params = new URLSearchParams({ status: filter.status, gen_type: filter.kind, q: filter.query, limit: "25", offset: String(filter.offset) });
    void session.requestWeb<GenerationPage>(`/admin/generations?${params}`, {}, controller.signal).then(row => {
      if (session.active() && sequence.current === version) setPage(row);
    }).catch(e => { if (!controller.signal.aborted && session.active()) setError(adminError(e)); }).finally(() => { if (!controller.signal.aborted && session.active()) setLoading(false); });
    return () => controller.abort();
  }, [session, filter]);
  const inspect = (row: GenerationRow) => void mutation.run(async () => {
    const fresh = await readGeneration(session, row.id);
    setSelected(fresh); setReason(""); setRefund(true); setResult("");
  });
  const check = () => void mutation.run(async () => {
    if (!selected || !reason.trim() || guard.pending) return;
    const fresh = await readGeneration(session, selected.id);
    if (!running(fresh)) { setSelected(fresh); throw new Error("Задача уже завершена. Обновите очередь."); }
    if (fresh.credits_spent !== selected.credits_spent || fresh.user_id !== selected.user_id) throw new Error("Данные задачи изменились. Откройте её заново.");
    setConfirm(true);
  });
  const execute = () => void mutation.run(async () => {
    if (!selected || !confirm || guard.pending) return;
    try {
      const fresh = await readGeneration(session, selected.id);
      if (!running(fresh)) { setSelected(fresh); throw new Error("Задача уже завершена. Изменение не отправлено."); }
      if (fresh.credits_spent !== selected.credits_spent || fresh.user_id !== selected.user_id) throw new Error("Данные задачи изменились. Откройте её заново.");
      guard.begin(refund ? "fail-refund" : "fail", selected.id);
      const response = await session.requestWeb<FailureResult>(`/admin/generations/${selected.id}/fail`, { method: "POST", body: JSON.stringify({ error: reason.trim(), refund }) });
      if (response.id !== selected.id || response.changed !== true || response.status !== "failed" || typeof response.refunded !== "boolean" || !Number.isFinite(response.refunded_credits) || response.refunded_credits < 0 || response.refunded !== (response.refunded_credits > 0)) throw new Error("Сервер не подтвердил результат. Сверьте задачу и журнал.");
      guard.clear(); setSelected(null);
      setResult(response.refunded ? `Возвращено: ${formatCredits(response.refunded_credits)} кр.` : "Задача отмечена ошибочной. Возврат не выполнялся.");
      setFilter({ ...filter });
    } finally { if (session.active()) setConfirm(false); }
  });
  const reconcile = () => void mutation.run(async () => {
    if (!guard.pending || !guard.pending.targetId) return;
    const row = await readGeneration(session, guard.pending.targetId);
    const ledger = await session.requestWeb<{ items: LedgerRow[] }>(`/admin/ledger?user_id=${row.user_id}&limit=100`);
    const entries = ledger.items.filter(entry => entry.source_type === "generation" && entry.source_id === String(row.id) && entry.entry_type === "admin_generation_refund" && entry.delta > 0);
    setResult(entries.length ? `Возврат подтверждён журналом: ${formatCredits(entries.reduce((sum, entry) => sum + entry.delta, 0))} кр.` : `Статус: ${generationStatusLabel(row.status)}. В последних 100 записях возврат не найден; это не доказывает отсутствие более старой записи.`);
    setReconciled(!running(row));
  });
  return <section className="lilac-panel grid gap-3"><h2>Очередь генераций</h2><p>Локальное завершение с ошибкой не отменяет запрос у поставщика.</p>
    {guard.pending && <div role="alert" className="lilac-panel"><h3>Результат операции не подтверждён</h3><p>Повтор заблокирован, включая перезагрузку. Задача #{guard.pending.targetId || "неизвестна"}. Проверьте её статус и журнал баланса.</p><Button disabled={mutation.busy || !guard.pending.targetId} onClick={reconcile}>Сверить задачу и баланс</Button>{reconciled && <Button variant="outline" disabled={mutation.busy} onClick={() => { try { guard.clear(); setReconciled(false); } catch (e) { mutation.setError(adminError(e)); } }}>Я сверил результат, разрешить новые операции</Button>}</div>}
    <form className="grid gap-2" onSubmit={e => { e.preventDefault(); setFilter({ status, kind, query: query.trim(), offset: 0 }); setSelected(null); }}>
      <label>Статус генераций<Select value={status} onChange={e => setStatus(e.target.value)}><option value="all">Все</option><option value="pending">Ожидают</option><option value="processing">В работе</option><option value="done">Готовы</option><option value="failed">Ошибка</option></Select></label>
      <label>Тип генераций<Select value={kind} onChange={e => setKind(e.target.value)}><option value="all">Все типы</option><option value="image">Изображение</option><option value="video">Видео</option><option value="music">Музыка</option></Select></label>
      <label>Поиск генераций<Input value={query} maxLength={128} onChange={e => setQuery(e.target.value)} placeholder="ID, задача поставщика, модель или пользователь" /></label><Button disabled={loading || mutation.busy} type="submit">Найти задачи</Button>
    </form>
    <AdminFeedback busy={loading || mutation.busy} error={error || mutation.error} />{result && <p role="status">{result}</p>}
    {page?.items.map(row => <Button key={row.id} variant="outline" className="h-auto min-h-11 whitespace-normal justify-start" disabled={mutation.busy} onClick={() => inspect(row)}>Задача #{row.id} · {row.model} · {generationStatusLabel(row.status)}</Button>)}
    {page && !page.items.length && <p>Задачи не найдены.</p>}
    {page && <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={loading || filter.offset === 0} onClick={() => setFilter({ ...filter, offset: Math.max(0, filter.offset - 25) })}>Предыдущие задачи</Button><span>{page.total ? `${filter.offset + 1}–${Math.min(filter.offset + page.items.length, page.total)} из ${page.total}` : "0 задач"}</span><Button variant="outline" disabled={loading || filter.offset + 25 >= page.total} onClick={() => setFilter({ ...filter, offset: filter.offset + 25 })}>Следующие задачи</Button></div>}
    {selected && <article className="lilac-panel grid gap-3"><h3>Задача #{selected.id}</h3><p>Аккаунт #{selected.user_id} · {generationStatusLabel(selected.status)} · {formatCredits(selected.credits_spent)} кр.</p><p className="break-words">Поставщик: {selected.task_id || "ID ещё нет"}</p><p className="break-words">{selected.prompt_hidden ? "Текст скрыт" : selected.prompt}</p><small>{selected.created_at} · {selected.finished_at}</small>{selected.error && <p>{selected.error}</p>}
      {running(selected) ? <><label>Причина завершения<Textarea value={reason} maxLength={500} disabled={mutation.busy} onChange={e => setReason(e.target.value)} /></label><label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={refund} disabled={mutation.busy} onChange={e => setRefund(e.target.checked)} />Вернуть списанные кредиты</label><Button disabled={mutation.busy || Boolean(guard.pending) || !reason.trim()} onClick={check}>Проверить завершение</Button></> : <p>Задача завершена; изменение недоступно.</p>}
    </article>}
    <Confirmation open={confirm} busy={mutation.busy} onCancel={() => setConfirm(false)} onConfirm={execute}><p>Отметить задачу #{selected?.id} ошибочной?</p><p>{reason.trim()}</p><p>{refund ? `Вернуть ${formatCredits(selected?.credits_spent || 0)} кр. владельцу задачи, если переход ещё доступен.` : "Без возврата кредитов."}</p><p>Запрос у поставщика не отменяется.</p></Confirmation>
  </section>;
}
