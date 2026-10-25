import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";
import { consumerMediaUrl, publicationTags, uploadedImage } from "./consumer-forms";
import { useConsumerWrite } from "./use-consumer-write";

export function LilacPromptPublication({ api, onClose, onPublished }: { api: MiniAppApi; onClose: () => void; onPublished: () => void }) {
  const [models, setModels] = useState<ModelInfo[]>([]), [model, setModel] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true), [catalogError, setCatalogError] = useState("");
  const [title, setTitle] = useState(""), [description, setDescription] = useState(""), [prompt, setPrompt] = useState(""), [tags, setTags] = useState("");
  const [cover, setCover] = useState(""), [coverFailed, setCoverFailed] = useState(false), [coverUploaded, setCoverUploaded] = useState(false), [consent, setConsent] = useState(false);
  const write = useConsumerWrite();
  useEffect(() => {
    const controller = new AbortController(); const deadline = window.setTimeout(() => { controller.abort(); setCatalogLoading(false); setCatalogError("Не удалось дождаться каталога"); }, 20_000);
    Promise.all(["image", "video", "music"].map(kind => api.request<ModelInfo[]>(`/models/${kind}`, {}, controller.signal)))
      .then(groups => { if (!controller.signal.aborted) { const rows = groups.flat().filter(row => row.key && row.key.length <= 64); setModels(rows); setModel(rows[0]?.key || ""); if (!rows.length) setCatalogError("Нет доступных моделей"); } })
      .catch(e => { if (!controller.signal.aborted) setCatalogError(e instanceof Error ? e.message : "Не удалось загрузить модели"); })
      .finally(() => { window.clearTimeout(deadline); if (!controller.signal.aborted) setCatalogLoading(false); });
    return () => { window.clearTimeout(deadline); controller.abort(); };
  }, [api]);
  const upload = (file: File | undefined) => {
    if (!file || write.busy || write.unauthorized) return;
    setCover(""); setCoverFailed(true); setCoverUploaded(false);
    if (!file.size || !file.type.startsWith("image/")) { write.setError("Выберите непустое изображение для обложки."); return; }
    void write.run(signal => api.uploadMedia(file, signal).then(uploadedImage), url => { setCover(url); setCoverFailed(false); setCoverUploaded(true); });
  };
  const validCover = !cover || Boolean(consumerMediaUrl(cover));
  const valid = title.trim().length >= 3 && prompt.trim().length >= 10 && consent && models.some(row => row.key === model) && validCover && !coverFailed && !catalogLoading && !catalogError;
  const submit = () => {
    if (!valid) return;
    void write.run(async signal => {
      // The catalog can change while the form is open; never publish an unavailable model.
      const current = await Promise.all(["image", "video", "music"].map(kind => api.request<ModelInfo[]>(`/models/${kind}`, {}, signal)));
      if (!current.flat().some(row => row.key === model)) throw new Error("Модель больше недоступна. Закройте форму и обновите каталог.");
      return api.requestWeb<{ id: number }>("/prompts", { method: "POST", body: JSON.stringify({ title: title.trim(), description: description.trim(), prompt_text: prompt.trim(), model, tags: publicationTags(tags), preview_url: cover ? consumerMediaUrl(cover) : null }) }, signal);
    }, result => { if (!Number.isSafeInteger(result.id) || result.id <= 0) throw new Error("Сервер не подтвердил публикацию. Проверьте список своих публикаций."); onPublished(); });
  };
  return <Sheet open className="lilac-consumer-form" title="Опубликовать промпт" description="Публикация будет доступна другим пользователям после проверки." onOpenChange={open => { if (!open) onClose(); }} footer={<Button className="w-full" disabled={!valid || write.busy || write.unauthorized} onClick={submit}>{write.busy ? "Отправляем…" : "Отправить на проверку"}</Button>}>
    <div className="grid gap-3">{write.error && <p role="alert">{write.error}</p>}{write.unauthorized && <p role="alert">Доступ изменился. Закройте форму и войдите снова.</p>}{catalogLoading && <p role="status">Загружаем модели…</p>}{catalogError && <p role="alert">{catalogError}. Закройте форму и попробуйте снова.</p>}
      <fieldset className="grid min-w-0 gap-3" disabled={write.busy || write.unauthorized}>
        <label>Название<Input value={title} maxLength={120} onChange={e => setTitle(e.target.value)} /></label>
        <label>Краткое описание<Textarea value={description} maxLength={500} onChange={e => setDescription(e.target.value)} /></label>
        <label>Задание<Textarea value={prompt} maxLength={4000} onChange={e => setPrompt(e.target.value)} /></label>
        <label>Модель публикации<Select aria-label="Модель публикации" value={model} disabled={catalogLoading || !models.length} onChange={e => setModel(e.target.value)}>{models.map(row => <option key={row.key} value={row.key}>{row.display_name}</option>)}</Select></label>
        <label>Теги через запятую<Input value={tags} onChange={e => setTags(e.target.value)} placeholder="портрет, свет" /></label>
        <p className="lilac-note">Категория определяется по заданию и тегам.</p>
        <label>Обложка публикации<Input type="file" accept="image/*" onChange={e => { upload(e.target.files?.[0]); e.target.value = ""; }} /></label>
        <label>Ссылка на обложку (необязательно)<Input type="url" value={cover} maxLength={2048} onChange={e => { setCover(e.target.value); setCoverFailed(false); setCoverUploaded(false); }} /></label>
        {!validCover && <p role="alert">Укажите безопасную HTTPS-ссылку на изображение или уберите обложку.</p>}
        {cover && validCover && <p role="status">{coverUploaded ? "Обложка загружена" : "Обложка добавлена по ссылке"}</p>}
        {(cover || coverFailed) && <Button variant="outline" onClick={() => { setCover(""); setCoverFailed(false); write.setError(""); }}>Убрать обложку</Button>}
        <label className="lilac-consent"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />Я понимаю, что публикую задание и обложку для других пользователей.</label>
      </fieldset>
    </div>
  </Sheet>;
}
