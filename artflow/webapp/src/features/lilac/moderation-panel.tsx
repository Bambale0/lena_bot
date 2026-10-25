import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import type { LibraryPrompt } from "./library-screen";
import { useAdminSession } from "./admin/primitives";

export function LilacModeration({ api }: { api: MiniAppApi }) {
  const session = useAdminSession();
  const [open, setOpen] = useState(false), [items, setItems] = useState<LibraryPrompt[]>([]);
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [action, setAction] = useState<{ item: LibraryPrompt; kind: "approve" | "reject" } | null>(null), [reason, setReason] = useState("");
  const lifetime = useRef(new AbortController()), mutation = useRef(false);
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; return () => controller.abort(); }, [api]);
  const load = async () => {
    const signal = lifetime.current.signal; setLoading(true); setError("");
    try { const row = await session.requestWeb<{ items: LibraryPrompt[] }>("/admin/prompts?status=pending", { cache: "no-store" }, signal); if (!signal.aborted) setItems(Array.isArray(row.items) ? row.items : []); }
    catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Не удалось загрузить очередь"); }
    finally { if (!signal.aborted) setLoading(false); }
  };
  const execute = async () => {
    if (!session.active() || !action || mutation.current || action.kind === "reject" && reason.trim().length < 3) return;
    const signal = lifetime.current.signal; mutation.current = true; setBusy(true); setError("");
    try { await session.requestWeb(`/admin/prompts/${action.item.id}/${action.kind}`, { method: "POST", body: JSON.stringify(action.kind === "reject" ? { reason: reason.trim() } : {}) }, signal);
      if (!signal.aborted) { setAction(null); await load(); }
    } catch (e) { if (!signal.aborted) setError(e instanceof Error ? e.message : "Ответ не подтверждён. Обновите очередь перед повтором."); }
    finally { mutation.current = false; if (!signal.aborted) setBusy(false); }
  };
  return <section className="lilac-panel"><h2>Публикации авторов</h2><p>Проверяйте задания перед появлением в общей библиотеке.</p><Button variant="outline" onClick={() => { setOpen(true); void load(); }}>Проверить публикации</Button>
    <Sheet open={open} title="Проверка публикаций" onOpenChange={value => { if (!busy) { setOpen(value); setAction(null); } }}>
      {error && <p role="alert">{error}</p>}{loading ? <p role="status">Загружаем очередь…</p> : action ? <div className="grid gap-3"><h3>{action.item.title}</h3><p>{action.kind === "approve" ? "Задание станет доступно другим пользователям. Опубликовать?" : "Укажите причину, которую увидит автор."}</p>{action.kind === "reject" && <label>Причина отклонения<Textarea value={reason} maxLength={500} disabled={busy} onChange={e => setReason(e.target.value)} /></label>}<Button disabled={busy || action.kind === "reject" && reason.trim().length < 3} onClick={() => void execute()}>{busy ? "Сохраняем…" : action.kind === "approve" ? "Подтвердить публикацию" : "Подтвердить отклонение"}</Button><Button variant="outline" disabled={busy} onClick={() => setAction(null)}>Назад к очереди</Button></div> : <div className="grid gap-3">{items.map(item => <article className="lilac-panel" key={item.id}><h3>{item.title}</h3><p>{item.description}</p><p className="lilac-prompt-text">{item.prompt_text || "Закрытый текст"}</p><Button disabled={busy} onClick={() => { setReason(""); setAction({ item, kind: "approve" }); }}>Одобрить публикацию</Button><Button variant="outline" disabled={busy} onClick={() => { setReason(""); setAction({ item, kind: "reject" }); }}>Отклонить публикацию</Button></article>)}{!error && !items.length && <p>Все публикации проверены.</p>}<Button variant="outline" disabled={busy} onClick={() => void load()}>Обновить очередь</Button></div>}
    </Sheet>
  </section>;
}
