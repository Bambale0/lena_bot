import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Copy, Heart, Library, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import { safeExternalUrl } from "@/lib/utils";

export interface LibraryPrompt { id: number; title: string; description?: string; prompt_text?: string; model?: string; preview_url?: string; category?: string; status?: string; reject_reason?: string; likes?: number; uses_count?: number; }
interface Props { api: MiniAppApi; onUse: (prompt: LibraryPrompt) => void; }
interface Catalogue { items: LibraryPrompt[]; total: number; }

export function LilacLibrary({ api, onUse }: Props) {
  const [mine, setMine] = useState(false), [page, setPage] = useState(1), [query, setQuery] = useState("");
  const [catalogue, setCatalogue] = useState<Catalogue>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [selected, setSelected] = useState<LibraryPrompt | null>(null), [adding, setAdding] = useState(false), [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(""), [description, setDescription] = useState(""), [prompt, setPrompt] = useState(""), [category, setCategory] = useState("other"), [publicConsent, setPublicConsent] = useState(false);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try { const result = await api.request<Catalogue>(mine ? "/prompts/my" : `/prompts?page=${page}&limit=20`, {}, signal);
      if (!signal?.aborted) setCatalogue({ items: Array.isArray(result.items) ? result.items : [], total: Number(result.total || 0) });
    } catch (e) { if (!signal?.aborted) setError(e instanceof Error ? e.message : "Не удалось загрузить библиотеку"); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [api, mine, page]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  const copyLink = async (item: LibraryPrompt) => {
    setBusy(true);
    try { const result = await api.request<{ link: string }>(`/prompts/${item.id}/link`); await navigator.clipboard.writeText(result.link); toast.success("Ссылка скопирована"); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Не удалось скопировать ссылку"); } finally { setBusy(false); }
  };
  const like = async (item: LibraryPrompt) => {
    setBusy(true);
    try { const result = await api.request<{ likes: number }>(`/prompts/${item.id}/like`, { method: "POST", body: "{}" }); setSelected({ ...item, likes: result.likes }); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Не удалось поставить отметку"); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (busy || !publicConsent || title.trim().length < 3 || prompt.trim().length < 10) return;
    setBusy(true);
    try { await api.request("/prompts", { method: "POST", body: JSON.stringify({ title: title.trim(), description: description.trim(), prompt_text: prompt.trim(), category }) });
      toast.success("Промпт отправлен на проверку"); setAdding(false); setTitle(""); setDescription(""); setPrompt(""); setPublicConsent(false); setMine(true); setPage(1); if (mine) await load();
    } catch (e) { toast.error(e instanceof Error ? e.message : "Не удалось отправить промпт"); } finally { setBusy(false); }
  };
  const deactivate = async (item: LibraryPrompt) => {
    if (busy) return; setBusy(true);
    try { await api.request(`/prompts/${item.id}/deactivate`, { method: "POST", body: "{}" }); setSelected(null); toast.success("Промпт снят с публикации"); await load(); }
    catch (e) { toast.error(e instanceof Error ? e.message : "Не удалось снять публикацию"); } finally { setBusy(false); }
  };
  const visible = catalogue.items.filter(item => `${item.title} ${item.description || ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="lilac-page"><header className="lilac-title"><p>Готовые задания</p><h1>Библиотека промптов</h1><span>Используйте идеи авторов или опубликуйте собственную.</span></header>
    <div className="lilac-segments"><button aria-pressed={!mine} onClick={() => { setMine(false); setPage(1); }}>Каталог</button><button aria-pressed={mine} onClick={() => { setMine(true); setPage(1); }}>Мои публикации</button></div>
    <Input aria-label="Поиск по текущей странице библиотеки" value={query} placeholder="Найти на этой странице" onChange={e => setQuery(e.target.value)} />
    <div className="lilac-section-title"><span>{catalogue.total} публикаций</span><Button variant="outline" onClick={() => setAdding(true)}><Plus />Добавить промпт</Button></div>
    {loading ? <p role="status">Загружаем библиотеку…</p> : error ? <div className="lilac-empty" role="alert"><p>{error}</p><Button onClick={() => void load()}><RefreshCw />Повторить</Button></div> : visible.length ? <div className="lilac-library-grid">{visible.map(item => <button key={item.id} className="lilac-prompt-card" onClick={() => setSelected(item)}>
      {safeExternalUrl(item.preview_url) ? <img src={safeExternalUrl(item.preview_url)} alt="" loading="lazy" /> : <span className="lilac-prompt-placeholder"><Library size={32} /></span>}
      <strong>{item.title}</strong><span>{item.description || "Открыть описание и параметры"}</span>{mine && <small>{({ approved: "Опубликовано", pending: "На проверке", rejected: "Не прошло проверку", deactivated: "Снято с публикации" } as Record<string, string>)[item.status || ""] || "Публикация"}</small>}
    </button>)}</div> : <div className="lilac-empty"><Library /><p>{query ? "Измените поисковый запрос." : mine ? "Ваши публикации появятся здесь после отправки." : "В библиотеке пока нет публикаций."}</p></div>}
    {!mine && <div className="lilac-pagination"><Button variant="outline" disabled={loading || page === 1} onClick={() => setPage(page - 1)}><ArrowLeft />Назад</Button><span>Страница {page}</span><Button variant="outline" disabled={loading || page * 20 >= catalogue.total} onClick={() => setPage(page + 1)}>Далее<ArrowRight /></Button></div>}
    <Sheet open={Boolean(selected)} title={selected?.title || "Промпт"} onOpenChange={open => { if (!open) setSelected(null); }} footer={selected && <Button className="w-full" disabled={selected.status !== "approved"} onClick={() => { if (selected.status !== "approved") return; onUse(selected); setSelected(null); }}>Использовать задание</Button>}>
      {selected && <div className="grid gap-3">{safeExternalUrl(selected.preview_url) && <img className="lilac-detail-preview" src={safeExternalUrl(selected.preview_url)} alt={selected.title} />}<p>{selected.description}</p>
        {selected.prompt_text ? <p className="lilac-prompt-text">{selected.prompt_text}</p> : <p>Описание подставится при запуске. Закрытый текст автора не раскрывается.</p>}
        {selected.reject_reason && <p role="status">Причина проверки: {selected.reject_reason}</p>}
        {mine && selected.status !== "deactivated" && <Button variant="outline" disabled={busy} onClick={() => void deactivate(selected)}>Снять мою публикацию</Button>}
        <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={busy || selected.status !== "approved"} onClick={() => void like(selected)}><Heart />{selected.likes || 0}</Button><Button variant="outline" disabled={busy || selected.status !== "approved"} onClick={() => void copyLink(selected)}><Copy />Скопировать ссылку</Button></div>
      </div>}
    </Sheet>
    <Sheet open={adding} title="Опубликовать промпт" description="Публикация будет доступна другим пользователям после проверки." onOpenChange={setAdding} footer={<Button className="w-full" disabled={busy || !publicConsent || title.trim().length < 3 || prompt.trim().length < 10} onClick={() => void submit()}>{busy ? "Отправляем…" : "Отправить на проверку"}</Button>}>
      <div className="grid gap-3"><label>Название<Input value={title} maxLength={120} onChange={e => setTitle(e.target.value)} /></label><label>Краткое описание<Textarea value={description} maxLength={500} onChange={e => setDescription(e.target.value)} /></label><label>Задание<Textarea value={prompt} maxLength={4000} onChange={e => setPrompt(e.target.value)} /></label><label>Категория<Select value={category} onChange={e => setCategory(e.target.value)}><option value="photo">Фото</option><option value="art">Арт</option><option value="business">Бизнес</option><option value="marketing">Маркетинг</option><option value="other">Разное</option></Select></label>
        <label className="lilac-consent"><input type="checkbox" checked={publicConsent} onChange={e => setPublicConsent(e.target.checked)} />Я понимаю, что публикую задание для других пользователей.</label>
      </div>
    </Sheet>
  </div>;
}
