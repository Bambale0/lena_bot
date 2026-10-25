import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { changedFields, sameFields, type ModelCost, type PricePlan, type Pricing } from "@/lib/studio-admin";
import { AdminFeedback, Confirmation, useAdminMutation, useAdminSession } from "./primitives";

type Values = { display_name?: string; label?: string; credits: number; price_rub?: number; price_stars?: number | null; sort_order?: number; is_active: boolean };
interface Edit { id: number; kind: "model" | "plan"; key: string; type?: string; original: Values; }
interface Draft { name: string; credits: string; rub: string; stars: string; order: string; active: boolean; }
const titles: Record<string, string> = { display_name: "Название", label: "Название", credits: "Кредиты", price_rub: "Цена, ₽", price_stars: "Stars (историческое поле)", sort_order: "Порядок", is_active: "Активен" };
function original(row: ModelCost | PricePlan): Values {
  return "model_key" in row ? { display_name: row.display_name, credits: row.credits, is_active: row.is_active } : { label: row.label, credits: row.credits, price_rub: row.price_rub, price_stars: row.price_stars, sort_order: row.sort_order, is_active: row.is_active };
}
function values(edit: Edit | null, draft: Draft): Values | null {
  if (!edit || !draft.name.trim() || draft.name.trim().length > 128 || !draft.credits.trim()) return null;
  const credits = Number(draft.credits);
  if (!Number.isFinite(credits) || credits < 0 || credits > 1_000_000 || edit.kind === "plan" && credits === 0) return null;
  if (edit.kind === "model") return { display_name: draft.name.trim(), credits, is_active: draft.active };
  const rub = Number(draft.rub), order = Number(draft.order), stars = draft.stars.trim() ? Number(draft.stars) : null;
  if (!draft.rub.trim() || !Number.isFinite(rub) || rub <= 0 || rub > 100_000_000 || !draft.order.trim() || !Number.isInteger(order) || Math.abs(order) > 10_000 || stars !== null && (!Number.isInteger(stars) || stars < 1 || stars > 1_000_000)) return null;
  return { label: draft.name.trim(), credits, price_rub: rub, price_stars: stars, sort_order: order, is_active: draft.active };
}
export function AdminPricing() {
  const session = useAdminSession(), mutation = useAdminMutation();
  const [pricing, setPricing] = useState<Pricing | null>(null), [edit, setEdit] = useState<Edit | null>(null), [confirm, setConfirm] = useState<Partial<Values> | null>(null);
  const [draft, setDraft] = useState<Draft>({ name: "", credits: "", rub: "", stars: "", order: "", active: false }), [notice, setNotice] = useState("");
  const load = () => mutation.run(async () => { setEdit(null); setConfirm(null); setPricing(await session.requestWeb<Pricing>("/admin/pricing")); });
  useEffect(() => { void load(); }, [session]);
  const open = (row: ModelCost | PricePlan) => {
    const data = original(row);
    setEdit({ id: row.id, kind: "model_key" in row ? "model" : "plan", key: "model_key" in row ? row.model_key : row.key, type: "gen_type" in row ? row.gen_type : undefined, original: data });
    setDraft({ name: data.display_name ?? data.label ?? "", credits: String(data.credits), rub: String(data.price_rub ?? ""), stars: String(data.price_stars ?? ""), order: String(data.sort_order ?? ""), active: data.is_active });
    mutation.setError(""); setNotice("");
  };
  const fresh = async (target: Edit) => {
    const data = await session.requestWeb<Pricing>("/admin/pricing");
    const row = (target.kind === "model" ? data.models : data.price_plans).find(item => item.id === target.id);
    if (!row || !sameFields(target.original, original(row))) throw new Error("Исходные цены изменились. Обновите список и проверьте изменения заново.");
  };
  const next = values(edit, draft), changes = edit && next ? changedFields(edit.original, next) : null;
  const check = () => void mutation.run(async () => {
    if (!edit || !changes || !Object.keys(changes).length) return;
    await fresh(edit); setConfirm(changes);
  });
  const execute = () => void mutation.run(async () => {
    if (!edit || !confirm) return;
    const target = edit, patch = confirm;
    try {
      await fresh(target);
      await session.requestWeb(`/admin/${target.kind === "model" ? "model-costs" : "price-plans"}/${target.id}`, { method: "PATCH", body: JSON.stringify(patch) });
      const data = await session.requestWeb<Pricing>("/admin/pricing");
      const row = (target.kind === "model" ? data.models : data.price_plans).find(item => item.id === target.id);
      if (!row || !sameFields(patch, row)) throw new Error("Ответ не подтверждён актуальными ценами. Обновите список и сверьте результат.");
      setPricing(data); setNotice("Цены сохранены и проверены повторным чтением.");
    } finally { if (session.active()) { setConfirm(null); setEdit(null); } }
  });
  return <section className="lilac-panel grid gap-3"><h2>Цены и пакеты</h2><p>Проверяем текущие значения перед подтверждением и отправляем только изменённые поля. Сервер не предоставляет версию этих цен: одновременное изменение другим администратором всё ещё возможно.</p>
    <Button variant="outline" disabled={mutation.busy} onClick={() => void load()}>Обновить цены</Button><AdminFeedback busy={mutation.busy} error={mutation.error} />{notice && <p role="status">{notice}</p>}
    <h3>Модели</h3>{pricing?.models.map(row => <Button variant="outline" key={row.id} className="h-auto min-h-11 whitespace-normal justify-start" disabled={mutation.busy} onClick={() => open(row)}>{row.display_name} · {row.model_key}</Button>)}{pricing?.models.length === 0 && <p>Моделей нет.</p>}
    <h3>Пакеты</h3>{pricing?.price_plans.map(row => <Button variant="outline" key={row.id} className="h-auto min-h-11 whitespace-normal justify-start" disabled={mutation.busy} onClick={() => open(row)}>{row.label} · {row.key}</Button>)}{pricing?.price_plans.length === 0 && <p>Пакетов нет.</p>}
    {edit && <div className="lilac-panel grid gap-3"><p className="break-words">Ключ: {edit.key} {edit.type && `· Тип: ${edit.type}`} (только чтение)</p>
      <label>Название<Input value={draft.name} maxLength={128} disabled={mutation.busy} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
      <label>{edit.kind === "model" ? "Стоимость, кредиты" : "Кредиты в пакете"}<Input type="number" step="any" min={edit.kind === "model" ? 0 : undefined} value={draft.credits} disabled={mutation.busy} onChange={e => setDraft({ ...draft, credits: e.target.value })} /></label>
      {edit.kind === "plan" && <><p>Изменение кредитов или рублёвой цены может отключить старую оплату Tribute. Потребуется новый продукт Tribute с новой привязкой и неизменяемыми условиями цены.</p><label>Цена, рубли<Input type="number" step="any" value={draft.rub} disabled={mutation.busy} onChange={e => setDraft({ ...draft, rub: e.target.value })} /></label><label>Stars — историческое поле<Input type="number" step="1" value={draft.stars} disabled={mutation.busy} onChange={e => setDraft({ ...draft, stars: e.target.value })} /></label><small>Оплата Stars отключена. Пустое значение очищает только это необязательное поле.</small><label>Порядок пакета<Input type="number" step="1" value={draft.order} disabled={mutation.busy} onChange={e => setDraft({ ...draft, order: e.target.value })} /></label></>}
      <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={draft.active} disabled={mutation.busy} onChange={e => setDraft({ ...draft, active: e.target.checked })} />Активен</label>
      {!next && <p>Заполните название и допустимые числовые значения. Обязательные поля нельзя оставлять пустыми.</p>}<Button disabled={mutation.busy || !changes || !Object.keys(changes).length} onClick={check}>Проверить цены</Button>
    </div>}
    <Confirmation open={Boolean(confirm)} busy={mutation.busy} onCancel={() => setConfirm(null)} onConfirm={execute}><p>Изменить цены: {edit?.key}</p>{confirm && Object.entries(confirm).map(([key, value]) => <p key={key}>{titles[key]}: {String(edit?.original[key as keyof Values] ?? "пусто")} → {String(value ?? "пусто")}</p>)}</Confirmation>
  </section>;
}
