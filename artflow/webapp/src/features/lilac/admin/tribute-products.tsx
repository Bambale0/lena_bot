import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { sameFields, type PricePlan, type Pricing, type TributeProduct } from "@/lib/studio-admin";
import { decimalMinorUnits, minorUnitsDecimal, positiveSafeInteger, validTributeUrl } from "@/lib/studio-system";
import { AdminFeedback, Confirmation, useAdminMutation, useAdminSession } from "./primitives";

interface Draft { id: string; plan: string; url: string; amount: string; enabled: boolean; }
interface Command { plan_key: string; payment_url: string; currency: "usd"; amount_minor: number; enabled: boolean; expected_revision: number; }
interface Change { id: number; before: TributeProduct | null; command: Command; plan: PricePlan; }
interface Catalog { items: TributeProduct[]; }
export function TributeProducts() {
  const session = useAdminSession(), mutation = useAdminMutation();
  const [products, setProducts] = useState<TributeProduct[]>([]), [plans, setPlans] = useState<PricePlan[]>([]), [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(false), [original, setOriginal] = useState<TributeProduct | null>(null), [change, setChange] = useState<Change | null>(null), [locked, setLocked] = useState(false), [notice, setNotice] = useState("");
  const [draft, setDraft] = useState<Draft>({ id: "", plan: "", url: "", amount: "", enabled: true });
  const read = () => Promise.all([session.requestWeb<Catalog>("/admin/payments/tribute-products"), session.requestWeb<Pricing>("/admin/pricing")]);
  const load = () => mutation.run(async () => {
    setEditing(false); setChange(null); setLocked(true); setLoaded(false); setNotice("");
    const [catalog, pricing] = await read(); setProducts(catalog.items); setPlans(pricing.price_plans); setLoaded(true); setLocked(false);
  });
  useEffect(() => { void load(); }, [session]);
  const open = (row: TributeProduct | null) => {
    setOriginal(row); setEditing(true); setNotice(""); mutation.setError("");
    setDraft(row ? { id: String(row.product_id), plan: row.plan_key, url: row.payment_url, amount: minorUnitsDecimal(row.amount_minor), enabled: row.enabled } : { id: "", plan: plans.find(plan => plan.is_active)?.key ?? "", url: "", amount: "", enabled: true });
  };
  const id = positiveSafeInteger(draft.id), cents = decimalMinorUnits(draft.amount), plan = plans.find(item => item.key === draft.plan);
  const valid = Boolean(id && cents && plan && (!draft.enabled || plan.is_active) && validTributeUrl(draft.url.trim()) && (!original || Number.isSafeInteger(original.revision) && original.revision >= 0 && original.amount_minor === cents && original.plan_key === draft.plan));
  const changed = !original || original.payment_url !== draft.url.trim() || original.enabled !== draft.enabled;
  const fresh = async (expected: Change) => {
    const [catalog, pricing] = await read(), actual = catalog.items.find(row => row.product_id === expected.id), currentPlan = pricing.price_plans.find(row => row.key === expected.plan.key);
    if (expected.before ? !actual || !sameFields(expected.before, actual) : Boolean(actual)) throw new Error("Каталог изменился. Обновите каталог и подтвердите заново.");
    if (!currentPlan || !sameFields({ credits: expected.plan.credits, price_rub: expected.plan.price_rub, is_active: expected.plan.is_active }, currentPlan)) throw new Error("Условия пакета изменились. Обновите каталог перед сохранением.");
  };
  const prepare = () => void mutation.run(async () => {
    if (!valid || !id || !cents || !plan || locked || !changed) return;
    const pending: Change = { id, before: original, plan, command: { plan_key: plan.key, payment_url: draft.url.trim(), currency: "usd", amount_minor: cents, enabled: draft.enabled, expected_revision: original?.revision ?? 0 } };
    try { await fresh(pending); setChange(pending); } catch (error) { setLocked(true); throw error; }
  });
  const verify = (row: TributeProduct | undefined, pending: Change) => {
    const { expected_revision, ...terms } = pending.command;
    const economics = pending.before ?? { credits: pending.plan.credits, amount_rub: pending.plan.price_rub };
    if (!row || row.product_id !== pending.id || row.revision !== expected_revision + 1 || !sameFields(terms, row) || row.credits !== economics.credits || row.amount_rub !== economics.amount_rub) throw new Error("Ответ не подтвердил продукт, цену и версию. Обновите каталог для сверки.");
  };
  const execute = () => void mutation.run(async () => {
    if (!change || locked) return;
    const pending = change;
    try {
      await fresh(pending);
      const result = await session.requestWeb<TributeProduct>(`/admin/payments/tribute-products/${pending.id}`, { method: "PUT", body: JSON.stringify(pending.command) }); verify(result, pending);
      const catalog = await session.requestWeb<Catalog>("/admin/payments/tribute-products"); verify(catalog.items.find(row => row.product_id === pending.id), pending);
      setProducts(catalog.items); setEditing(false); setNotice("Продукт Tribute сохранён и проверен.");
    } catch (error) { setLocked(true); throw error; }
    finally { if (session.active()) setChange(null); }
  });
  return <section className="lilac-panel grid gap-3"><h3>Каталог Tribute</h3><p>Привязка реального продукта к пакету. Цена, валюта и пакет существующего продукта неизменяемы; новые условия требуют нового ID. Включение нового продукта отключает старый для того же пакета. Сервер проверяет поставщика при включении.</p><AdminFeedback busy={mutation.busy} error={mutation.error} /><Button variant="outline" disabled={mutation.busy} onClick={() => void load()}>Обновить каталог</Button>
    {notice && <p role="status">{notice}</p>}{loaded && !products.length && <p>Продуктов Tribute пока нет.</p>}
    {products.map(row => <Button className="h-auto whitespace-normal justify-start" variant="outline" disabled={mutation.busy || locked} key={row.product_id} onClick={() => open(row)}>Tribute #{row.product_id} · {row.plan_key} · {minorUnitsDecimal(row.amount_minor) || "недопустимая цена"} USD · {row.enabled ? "включён" : "отключён"} · версия {row.revision}</Button>)}
    <Button disabled={mutation.busy || locked || !plans.length} onClick={() => open(null)}>Новый продукт Tribute</Button>
    {editing && <article className="lilac-panel grid gap-3"><label>ID продукта Tribute<Input type="text" inputMode="numeric" value={draft.id} readOnly={Boolean(original)} disabled={mutation.busy || locked} onChange={e => setDraft({ ...draft, id: e.target.value })} /></label>
      <label>Пакет Tribute<Select value={draft.plan} disabled={mutation.busy || locked || Boolean(original)} onChange={e => setDraft({ ...draft, plan: e.target.value })}>{!plan && <option value={draft.plan}>{draft.plan || "Выберите пакет"}</option>}{plans.map(row => <option key={row.key} value={row.key}>{row.label} · {row.key}{row.is_active ? "" : " · неактивен"}</option>)}</Select></label>
      {plan && <p>Пакет: {plan.credits} кр. · {plan.price_rub} ₽. {original && `Сохранённые условия: ${original.credits} кр. · ${original.amount_rub} ₽.`}</p>}
      <label>Ссылка Tribute<Input value={draft.url} maxLength={2048} disabled={mutation.busy || locked} onChange={e => setDraft({ ...draft, url: e.target.value })} /></label><small>Канонический адрес https://web.tribute.tg/p/… без параметров и фрагмента.</small>
      <label>Цена, USD<Input type="text" inputMode="decimal" value={draft.amount} readOnly={Boolean(original)} disabled={mutation.busy || locked} onChange={e => setDraft({ ...draft, amount: e.target.value })} /></label><p>Валюта: USD. До двух знаков после точки. ID и сумма должны быть безопасными целыми числами браузера.</p>
      <label className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={draft.enabled} disabled={mutation.busy || locked} onChange={e => setDraft({ ...draft, enabled: e.target.checked })} />Продукт включён</label><p>Ожидаемая версия: {original?.revision ?? 0}. Конфликт требует обновления и нового подтверждения.</p>
      <Button disabled={mutation.busy || locked || !valid || !changed} onClick={prepare}>Проверить продукт</Button>
    </article>}
    <Confirmation open={Boolean(change)} busy={mutation.busy} onCancel={() => setChange(null)} onConfirm={execute}><p>Сохранить продукт Tribute #{change?.id} для пакета {change?.command.plan_key}?</p><p>{change && minorUnitsDecimal(change.command.amount_minor)} USD · {change?.command.enabled ? "включён" : "отключён"} · версия {change?.command.expected_revision}</p><p className="break-all">{change?.command.payment_url}</p><p>При включении остальные продукты пакета будут отключены. Старые покупки сохраняют исходные условия.</p></Confirmation>
  </section>;
}
