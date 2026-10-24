import { useCallback, useEffect, useState } from "react";
import { BookOpen, CheckCircle2, Clock, CreditCard, RefreshCw, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MiniAppApi } from "@/lib/api";
import { formatCredits, formatRelativeDate, safeExternalUrl } from "@/lib/utils";
import { openExternalUrl } from "@/lib/telegram";
import type { AppTab, UserProfile } from "@/lib/types";

export function LilacHelp({ api, onNavigate }: { api: MiniAppApi; onNavigate: (tab: AppTab) => void }) {
  const [help, setHelp] = useState<{ text: string; links: Array<{ label: string; url: string }> } | null>(null), [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    setError("");
    try { const result = await api.request<{ text?: string }>("/help", {}, signal); const doc = new DOMParser().parseFromString(result.text || "", "text/html");
      if (!signal?.aborted) setHelp({ text: doc.body.textContent || "", links: [...doc.querySelectorAll("a")].map(link => ({ label: link.textContent || "Открыть ссылку", url: safeExternalUrl(link.getAttribute("href")) })).filter(link => link.url) });
    } catch (e) { if (!signal?.aborted) setError(e instanceof Error ? e.message : "Не удалось загрузить помощь"); }
  }, [api]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  return <div className="lilac-page"><header className="lilac-title"><p>Мы рядом</p><h1>Помощь и поддержка</h1><span>От первого запуска до работы с результатом.</span></header>
    <div className="lilac-task-grid">{[{ label: "Выбрать нейросеть", tab: "models" }, { label: "Найти результат", tab: "works" }, { label: "Проверить оплату", tab: "billing" }, { label: "Спросить помощника", tab: "assistant" }].map(item => <button className="lilac-create-card" key={item.tab} onClick={() => onNavigate(item.tab as AppTab)}><BookOpen /><strong>{item.label}</strong></button>)}</div>
    <section className="lilac-panel"><h2>Справочник APIX</h2>{error ? <div role="alert"><p>{error}</p><Button variant="outline" onClick={() => void load()}>Повторить</Button></div> : !help ? <p role="status">Загружаем справку…</p> : <><p className="lilac-prompt-text">{help.text || "Справка временно недоступна."}</p>{help.links.map((link, i) => <Button key={i} variant="outline" onClick={() => openExternalUrl(link.url)}>{link.label}</Button>)}</>}</section>
    <div className="lilac-panel"><h2>Если генерация не завершилась</h2><p>Откройте работу и обновите статус. Для обращения в поддержку скопируйте номер задачи из её карточки.</p><Button variant="outline" onClick={() => onNavigate("works")}>Открыть мои работы</Button></div>
  </div>;
}

interface Transaction { id: number; amount_rub: number; credits: number; provider: string; status: string; created_at: string; }
export function LilacBilling({ api, user, onTopup }: { api: MiniAppApi; user: UserProfile; onTopup: () => void }) {
  const [transactions, setTransactions] = useState<Transaction[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try { const result = await api.requestWeb<{ transactions: Transaction[] }>("/billing/transactions?limit=100", {}, signal); if (!signal?.aborted) setTransactions(Array.isArray(result.transactions) ? result.transactions : []); }
    catch (e) { if (!signal?.aborted) setError(e instanceof Error ? e.message : "Не удалось загрузить платежи"); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [api]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  return <div className="lilac-page"><header className="lilac-title"><p>Кредиты и платежи</p><h1>Баланс</h1></header><section className="lilac-balance-card"><Wallet size={32} /><div><span>Доступно для создания</span><strong>{formatCredits(user.credits)} кредитов</strong></div><Button onClick={onTopup}>Пополнить баланс</Button></section>
    <div className="lilac-section-title"><h2>История платежей</h2><Button variant="ghost" size="icon" aria-label="Обновить платежи" disabled={loading} onClick={() => void load()}><RefreshCw className={loading ? "animate-spin" : ""} /></Button></div>
    <p className="lilac-note">Начисление проверяется автоматически. Итоговый баланс приходит с сервера.</p>
    {loading ? <p role="status">Загружаем платежи…</p> : error ? <div className="lilac-panel" role="alert"><p>{error}</p><Button onClick={() => void load()}>Повторить</Button></div> : !transactions.length ? <div className="lilac-empty"><CreditCard /><p>Платежей пока нет. Выберите пакет, когда захотите пополнить баланс.</p></div> : transactions.map(tx => <article key={tx.id} className="lilac-row">{tx.status === "paid" ? <CheckCircle2 /> : <Clock />}<span><strong>{formatCredits(tx.credits)} кредитов · {formatCredits(tx.amount_rub)} ₽</strong><small>{({ paid: "Оплачено", pending: "Ожидаем оплату", refunded: "Возврат", failed: "Не оплачено" } as Record<string, string>)[tx.status] || tx.status} · {tx.provider} · {formatRelativeDate(tx.created_at)}</small></span></article>)}
  </div>;
}
