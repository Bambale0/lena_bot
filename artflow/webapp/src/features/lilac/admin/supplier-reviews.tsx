import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { sameFields, type SupplierReview, type SupplierSettlement } from "@/lib/studio-admin";
import { validReviewNote } from "@/lib/studio-system";
import { AdminFeedback, AdminScope, Confirmation, useAdminMutation, useAdminSession, useFinancialGuard } from "./primitives";

type Resolution = "confirmed_not_accepted" | "cost_reconciled";
interface ReviewPage { items: SupplierReview[]; count: number; }
export function SupplierReviews() {
  const [family, setFamily] = useState("images");
  return <section className="lilac-panel grid gap-3"><h3>Сверка поставщиков</h3><p>Только расчёты с поставщиком после возврата. Баланс клиента не изменяется. Это не отмена удалённой генерации.</p><label>Очередь поставщиков<Select value={family} onChange={e => setFamily(e.target.value)}><option value="images">Изображения</option><option value="seedance">Seedance</option></Select></label><AdminScope key={family}><SupplierQueue family={family} /></AdminScope></section>;
}
function SupplierQueue({ family }: { family: string }) {
  const session = useAdminSession(), mutation = useAdminMutation(), guard = useFinancialGuard(`supplier-${family}`);
  const [items, setItems] = useState<SupplierReview[]>([]), [loaded, setLoaded] = useState(false), [selected, setSelected] = useState<SupplierReview | null>(null);
  const [note, setNote] = useState(""), [resolution, setResolution] = useState<Resolution>("confirmed_not_accepted");
  const [confirmation, setConfirmation] = useState<{ row: SupplierReview; note: string; resolution: Resolution } | null>(null), [notice, setNotice] = useState("");
  const [reconciled, setReconciled] = useState(false), [acknowledge, setAcknowledge] = useState(false);
  const path = `/admin/${family}/refund-supplier-reviews?limit=200`;
  const read = () => session.requestWeb<ReviewPage>(path);
  const load = () => mutation.run(async () => { setSelected(null); setConfirmation(null); setReconciled(false); setLoaded(false); const result = await read(); setItems(result.items); setLoaded(true); });
  useEffect(() => { void load(); }, [session]);
  const fresh = async (row: SupplierReview) => {
    const result = await read(), actual = result.items.find(item => item.generation_id === row.generation_id);
    if (!actual || !sameFields(row, actual)) throw new Error("Состояние сверки изменилось или отсутствует в ограниченной очереди. Обновите список; повтор автоматически не отправлен.");
  };
  const prepare = () => void mutation.run(async () => {
    if (!selected || guard.pending || !validReviewNote(note)) return;
    await fresh(selected); setConfirmation({ row: selected, note: note.trim(), resolution });
  });
  const execute = () => void mutation.run(async () => {
    if (!confirmation || guard.pending) return;
    const change = confirmation;
    try {
      await fresh(change.row);
      guard.begin(change.resolution, change.row.generation_id);
      const result = await session.requestWeb<SupplierSettlement>(`/admin/${family}/refund-supplier-review/${change.row.generation_id}`, { method: "PUT", body: JSON.stringify({ resolution: change.resolution, note: change.note }) });
      if (result.generation_id !== change.row.generation_id || result.review_state !== "settled" || result.customer_balance_unchanged !== true) throw new Error("Ответ не подтверждает окончательную сверку. Сначала сверьте результат.");
      guard.clear(); setNotice("Сверка поставщика подтверждена. Баланс клиента не изменён."); setSelected(null); setNote("");
      const actual = await read(); setItems(actual.items);
    } finally { if (session.active()) { setConfirmation(null); setReconciled(false); } }
  });
  const reconcile = () => void mutation.run(async () => {
    const actual = await read(); setItems(actual.items); setSelected(null); setReconciled(true);
  });
  const acknowledgeResult = () => void mutation.run(async () => {
    try {
      if (!guard.pending || guard.pending.targetId <= 0) return;
      const actual = await read(); setItems(actual.items);
      if (actual.items.some(item => item.generation_id === guard.pending!.targetId)) throw new Error("Сверка ещё открыта. Блокировка сохранена; обратитесь к ответственному администратору.");
      guard.clear(); setReconciled(false); setNotice("Блокировка снята по вашему подтверждению внешней сверки. Новая операция не отправлялась.");
    } finally { if (session.active()) setAcknowledge(false); }
  });
  const pendingPresent = Boolean(guard.pending && items.some(item => item.generation_id === guard.pending!.targetId));
  return <div className="grid gap-3"><AdminFeedback busy={mutation.busy} error={mutation.error} /><Button variant="outline" disabled={mutation.busy} onClick={() => void load()}>Обновить очередь сверки</Button><p>Показано до 200 открытых сверок. Отсутствие задачи здесь само по себе не доказывает её расчёт.</p>
    {guard.pending && <div className="lilac-panel grid gap-3" role="alert"><h4>Результат сверки не подтверждён</h4><p>Задача #{guard.pending.targetId || "неизвестна"}. Запрос мог выполниться. Повтор заблокирован, в том числе после перезагрузки.</p><Button disabled={mutation.busy || guard.pending.targetId <= 0} onClick={reconcile}>Сверить очередь поставщика</Button>{reconciled && <><p>{pendingPresent ? "Задача остаётся открытой. Блокировка сохранена." : "Задача отсутствует среди первых 200 открытых сверок. Это не подтверждение расчёта; сверьте внешний отчёт с ответственным администратором."}</p>{!pendingPresent && guard.pending.targetId > 0 && <Button variant="outline" disabled={mutation.busy} onClick={() => setAcknowledge(true)}>Я сверил внешний отчёт</Button>}</>}</div>}
    {notice && <p role="status">{notice}</p>}{loaded && items.length === 0 && <p>Открытых сверок в этой выборке нет.</p>}
    {items.map(row => <Button className="h-auto whitespace-normal justify-start" variant="outline" disabled={mutation.busy || Boolean(guard.pending)} key={row.generation_id} onClick={() => { setSelected(row); setNote(""); setNotice(""); }}>Сверка #{row.generation_id} · {row.model} · {row.state}</Button>)}
    {selected && <article className="lilac-panel grid gap-3"><h4>Поставщик · задача #{selected.generation_id}</h4><p>Аккаунт: {selected.user_id} · {selected.model} · {selected.provider ?? "провайдер не указан сервером"}</p><p>Состояние: {selected.state} · Последний статус: {selected.last_provider_status ?? "не указан"}</p><p>Исходная задача: {selected.original_task_id ?? "нет"} · Задача поставщика: {selected.provider_task_id ?? "нет"}</p><p>Возврат: {selected.refunded_at ?? "дата не указана"}</p>{selected.checks != null && <p>Проверок: {selected.checks} · Следующая: {selected.next_check_at ?? "не назначена"}</p>}
      <label>Результат сверки<Select value={resolution} disabled={mutation.busy} onChange={e => setResolution(e.target.value as Resolution)}><option value="confirmed_not_accepted">Поставщик не принял задачу</option><option value="cost_reconciled">Стоимость согласована</option></Select></label>
      <label>Комментарий сверки<textarea className="min-h-28 w-full rounded-xl border p-3" value={note} maxLength={1000} disabled={mutation.busy} onChange={e => setNote(e.target.value)} /></label><p>От 12 до 500 символов после удаления пробелов по краям.</p><Button disabled={mutation.busy || Boolean(guard.pending) || !validReviewNote(note)} onClick={prepare}>Проверить сверку</Button>
    </article>}
    <Confirmation open={Boolean(confirmation)} busy={mutation.busy} onCancel={() => setConfirmation(null)} onConfirm={execute}><p>Завершить сверку поставщика для задачи #{confirmation?.row.generation_id}?</p><p>{confirmation?.resolution === "cost_reconciled" ? "Стоимость согласована" : "Поставщик не принял задачу"}</p><p>{confirmation?.note}</p><p>Баланс клиента не изменяется. Окончательное решение защищено сервером от повторной сверки.</p></Confirmation>
    <Confirmation open={acknowledge} title="Подтверждение внешней сверки" busy={mutation.busy} onCancel={() => setAcknowledge(false)} onConfirm={acknowledgeResult}><p>Вы подтверждаете, что ответственный администратор сверил внешний отчёт для задачи #{guard.pending?.targetId}. Ограниченная очередь не доказывает расчёт. Снять блокировку новых сверок? Повторный PUT не отправляется.</p></Confirmation>
  </div>;
}
