import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { MiniAppApi } from "@/lib/api";
import type { GenerationTask } from "@/lib/types";
import { formatCredits } from "@/lib/utils";
import { creditErrorToast } from "@/lib/credit-error-toast";

type Operation = "cover" | "extend" | "add_vocals" | "add_instrumental";
interface Source { url: string; duration_seconds?: number; filename?: string; }

/** Source audio is uploaded once; retries reuse its server-issued URL. */
export function LilacAudioTools({ api, onCreated, model, onBalanceOpen }: { api: MiniAppApi; onCreated?: (task: GenerationTask) => void; model?: { key: string; credits: number }; onBalanceOpen?: () => void }) {
  const [operation, setOperation] = useState<Operation>("cover");
  const [file, setFile] = useState<File | null>(null), [source, setSource] = useState<Source | null>(null);
  const [prompt, setPrompt] = useState(""), [title, setTitle] = useState(""), [style, setStyle] = useState(""), [continueAt, setContinueAt] = useState("");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const position = Number(continueAt);
  const validPosition = operation !== "extend" || Number.isFinite(position) && position > 0 && position <= 480 && (!source?.duration_seconds || position < source.duration_seconds);
  const titleRequired = operation === "add_vocals" || operation === "add_instrumental" || Boolean(style.trim());
  const styleRequired = operation === "add_vocals" || (["cover", "extend"].includes(operation) && Boolean(title.trim()));
  const validDetails = (!titleRequired || Boolean(title.trim())) && (!styleRequired || Boolean(style.trim()));
  const submit = async () => {
    if (busy || !model || !prompt.trim() || (!file && !source) || !validPosition || !validDetails) return;
    setBusy(true); setError("");
    try {
      let uploaded = source;
      if (!uploaded && file) { const form = new FormData(); form.append("file", file); uploaded = await api.request<Source>("/music/source-audio", { method: "POST", body: form }); setSource(uploaded); }
      if (!uploaded?.url) throw new Error("Не удалось получить исходное аудио. Загрузите файл снова.");
      if (operation === "extend" && uploaded.duration_seconds && position >= uploaded.duration_seconds) throw new Error("Точка продолжения должна быть раньше конца исходного аудио.");
      const task = await api.request<GenerationTask>("/music/from-audio", { method: "POST", body: JSON.stringify({ operation, model: model.key, upload_url: uploaded.url, prompt: prompt.trim(), title: title.trim() || undefined, style: style.trim() || undefined, instrumental, continue_at: operation === "extend" ? position : undefined, source_duration: uploaded.duration_seconds }) });
      onCreated?.(task); toast.success("Задача обработки аудио создана");
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось обработать аудио"); creditErrorToast(e, "Не удалось обработать аудио", onBalanceOpen); }
    finally { setBusy(false); }
  };
  return <section className="lilac-audio-tools"><h2>Из вашего аудио</h2><p className="lilac-note">Создайте кавер, продолжите запись или добавьте вокал. Используйте свои записи или аудио с разрешением правообладателя.</p>
    <label>Что сделать<Select aria-label="Обработка аудио" value={operation} disabled={busy} onChange={e => setOperation(e.target.value as Operation)}><option value="cover">Создать кавер</option><option value="extend">Продолжить аудио</option><option value="add_vocals">Добавить вокал</option><option value="add_instrumental">Добавить инструментал</option></Select></label>
    <label>Исходное аудио<input aria-label="Исходное аудио" type="file" accept="audio/*" disabled={busy} onChange={e => { setFile(e.target.files?.[0] || null); setSource(null); setError(""); }} /></label>
    {source && <p role="status">Загружено: {source.filename || file?.name}{source.duration_seconds ? ` · ${source.duration_seconds} сек` : ""}</p>}
    <label>Задание для обработки<Textarea value={prompt} maxLength={5000} disabled={busy} onChange={e => setPrompt(e.target.value)} placeholder="Опишите стиль и желаемые изменения" /></label>
    <div className="grid gap-3 sm:grid-cols-2"><label>Название{titleRequired ? " (обязательно)" : ""}<Input aria-label="Название обработки" required={titleRequired} value={title} maxLength={100} disabled={busy} onChange={e => setTitle(e.target.value)} /></label><label>Музыкальный стиль{styleRequired ? " (обязательно)" : ""}<Input aria-label="Стиль обработки" required={styleRequired} value={style} maxLength={1000} disabled={busy} onChange={e => setStyle(e.target.value)} /></label></div>
    {["cover", "extend"].includes(operation) && <label className="lilac-consent"><input type="checkbox" checked={instrumental} disabled={busy} onChange={e => setInstrumental(e.target.checked)} />Без вокала</label>}
    {!validDetails && <p role="status">Для этого режима заполните обязательные название и стиль. Для кавера и продолжения можно оставить оба поля пустыми.</p>}
    {operation === "extend" && <label>Продолжить с секунды<Input type="number" min="0.1" max="480" step="0.1" value={continueAt} disabled={busy} onChange={e => setContinueAt(e.target.value)} /><small>Раньше конца записи, не более 480 секунд.</small></label>}
    {error && <p role="alert">{error}</p>}
    <p className="lilac-note">{model ? `Стоимость: ${formatCredits(model.credits)} кредитов по выбранной выше модели.` : "Выберите доступную музыкальную модель выше."} Сервер повторно проверит файл, тариф и баланс.</p>
    <Button disabled={busy || !model || (!file && !source) || !prompt.trim() || !validPosition || !validDetails} onClick={() => void submit()}>{busy ? "Загружаем и создаём…" : "Создать из аудио"}</Button>
  </section>;
}
