import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Sheet } from "@/components/ui/sheet";
import type { MiniAppApi } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";
import type { ImageSeries } from "./image-series";
import { initialSeriesSettings, seriesOptions, seriesValidation, uploadedImage, type SeriesSettings } from "./consumer-forms";
import { useConsumerWrite } from "./use-consumer-write";

const modeNames: Record<string, string> = { text: "По описанию", image: "По исходным фото", multimodal: "Описание и исходные материалы" };
export function LilacCreateImageSeries({ api, models: initialModels, onClose, onCreated }: { api: MiniAppApi; models: ModelInfo[]; onClose: () => void; onCreated: (series: ImageSeries) => void }) {
  const [models, setModels] = useState(initialModels), [loading, setLoading] = useState(true), [catalogError, setCatalogError] = useState("");
  const [settings, setSettings] = useState<SeriesSettings>(() => initialModels[0] ? initialSeriesSettings(initialModels[0]) : { model: "", mode: "", aspect_ratio: null, quality: "basic", count: 1 });
  const [prompt, setPrompt] = useState(""), [references, setReferences] = useState<string[]>([]), [uploadFailed, setUploadFailed] = useState(false);
  const [replacement, setReplacement] = useState<ImageSeries | null>(null);
  const write = useConsumerWrite();
  const model = models.find(row => row.key === settings.model), options = model ? seriesOptions(model) : null;
  const issue = seriesValidation(settings, model, references);
  const valid = !loading && !catalogError && !issue && !uploadFailed;
  useEffect(() => {
    const controller = new AbortController();
    const deadline = window.setTimeout(() => { controller.abort(); setCatalogError("Не удалось дождаться каталога. Закройте форму и попробуйте снова."); setLoading(false); }, 20_000);
    api.request<ModelInfo[]>("/models/image", {}, controller.signal).then(rows => {
      if (!controller.signal.aborted) { setModels(rows); if (rows[0]) setSettings(initialSeriesSettings(rows[0])); else setCatalogError("Нет доступных моделей. Закройте форму и обновите каталог."); }
    }).catch(e => { if (!controller.signal.aborted) setCatalogError(e instanceof Error ? e.message : "Не удалось загрузить модели"); })
      .finally(() => { window.clearTimeout(deadline); if (!controller.signal.aborted) setLoading(false); });
    return () => { window.clearTimeout(deadline); controller.abort(); };
  }, [api]);
  const upload = (files: FileList | null) => {
    if (!files?.length || write.busy || write.unauthorized || !options) return;
    const selected = Array.from(files); setUploadFailed(true);
    if (selected.some(file => !file.size || !file.type.startsWith("image/"))) { write.setError("Выберите непустые изображения для серии."); return; }
    if (selected.length + references.length > options.maxRefs) { write.setError(`Можно использовать исходных фото: ${options.maxRefs}. Уберите лишние файлы.`); return; }
    void write.run(async signal => {
      const urls: string[] = [];
      for (const file of selected) urls.push(uploadedImage(await api.uploadMedia(file, signal)));
      return urls;
    }, urls => { setReferences(current => [...new Set([...current, ...urls])]); setUploadFailed(false); });
  };
  const save = (confirmed: ImageSeries | null = null) => {
    if (!valid) return;
    void write.run(async signal => {
      const freshModels = await api.request<ModelInfo[]>("/models/image", {}, signal);
      const invalid = seriesValidation(settings, freshModels.find(row => row.key === settings.model), references);
      if (invalid) throw new Error(invalid);
      const active = await api.requestWeb<ImageSeries | null>("/image-sessions/active", {}, signal);
      if (confirmed) {
        if (JSON.stringify(active) !== JSON.stringify(confirmed)) throw new Error("Активная серия изменилась. Закройте подтверждение и проверьте её заново.");
      } else if (active?.id) return { replacement: active };
      const result = await api.requestWeb<ImageSeries>("/image-sessions", { method: "POST", body: JSON.stringify({ ...settings, base_prompt: prompt.trim() || null, reference_urls: references }) }, signal);
      if (!Number.isSafeInteger(result.id) || result.id <= 0 || result.model !== settings.model) throw new Error("Сервер не подтвердил создание серии. Обновите список перед повторной отправкой.");
      return { result };
    }, outcome => { if (outcome.replacement) setReplacement(outcome.replacement); else if (outcome.result) onCreated(outcome.result); });
  };
  return <>
    <Sheet open={!replacement} className="lilac-consumer-form" title="Создать серию фото" onOpenChange={open => { if (!open) onClose(); }} footer={<Button className="w-full" disabled={!valid || write.busy || write.unauthorized} onClick={() => save()}>{write.busy ? "Сохраняем…" : "Сохранить серию"}</Button>}>
      <div className="grid gap-3"><p>Генерация не запускается, поцелуи не списываются. Сохраняются только параметры новой серии. Текущий черновик фото остаётся у вас.</p>
        {write.error && <p role="alert">{write.error}</p>}{write.unauthorized && <p role="alert">Доступ изменился. Закройте форму и войдите снова.</p>}{loading && <p role="status">Загружаем модели…</p>}{catalogError && <p role="alert">{catalogError}</p>}
        <fieldset className="grid min-w-0 gap-3" disabled={write.busy || write.unauthorized || loading}>
          <label>Модель серии<Select aria-label="Модель серии" value={settings.model} onChange={e => { const next = models.find(row => row.key === e.target.value); if (next) setSettings(initialSeriesSettings(next)); }}>{models.map(row => <option key={row.key} value={row.key}>{row.display_name}</option>)}</Select></label>
          <label>Режим серии<Select aria-label="Режим серии" value={settings.mode} onChange={e => setSettings(current => ({ ...current, mode: e.target.value, aspect_ratio: (model?.aspect_ratio_modes || options?.modes || []).includes(e.target.value) ? current.aspect_ratio : null }))}>{options?.modes.map(mode => <option key={mode} value={mode}>{modeNames[mode] || mode}</option>)}</Select></label>
          <label>Формат серии<Select aria-label="Формат серии" value={settings.aspect_ratio || ""} onChange={e => setSettings(current => ({ ...current, aspect_ratio: e.target.value || null }))}><option value="">Автоматически</option>{options?.ratios.map(ratio => <option key={ratio} value={ratio}>{ratio}</option>)}</Select></label>
          <label>Качество серии<Select aria-label="Качество серии" value={settings.quality} onChange={e => setSettings(current => ({ ...current, quality: e.target.value }))}>{options?.qualities.map(option => <option key={option.value} value={option.value}>{option.label || option.value}</option>)}</Select></label>
          <label>Количество фото в серии<Select aria-label="Количество фото в серии" value={settings.count} onChange={e => setSettings(current => ({ ...current, count: Number(e.target.value) }))}>{options?.counts.map(count => <option key={count} value={count}>{count}</option>)}</Select></label>
          <label>Описание серии (необязательно)<Textarea value={prompt} maxLength={4000} onChange={e => setPrompt(e.target.value)} /></label>
          {options && options.maxRefs > 0 && <><label>Исходные фото серии<Input type="file" multiple accept="image/*" onChange={e => { upload(e.target.files); e.target.value = ""; }} /></label><p className="lilac-note">Можно добавить фото: {options.maxRefs}. Пустую серию можно сохранить и без исходников.</p></>}
          {references.length > 0 && <p role="status">Загружено фото: {references.length}</p>}
          {(references.length > 0 || uploadFailed) && <Button variant="outline" onClick={() => { setReferences([]); setUploadFailed(false); write.setError(""); }}>Убрать исходные фото</Button>}
          {issue && <p role="alert">{issue}</p>}
        </fieldset>
      </div>
    </Sheet>
    <Sheet open={Boolean(replacement)} className="lilac-consumer-form" title="Заменить активную серию?" onOpenChange={open => { if (!open) { write.cancel(); setReplacement(null); write.setError(""); } }} footer={<Button disabled={write.busy || write.unauthorized} onClick={() => save(replacement)}>{write.busy ? "Сохраняем…" : "Заменить серию"}</Button>}>
      <p>Предыдущая серия #{replacement?.id} будет завершена и заменена новой. Её работы сохранятся в проектах. Черновик фото не меняется. Генерация не запускается, списания нет.</p>
      <p className="lilac-note">Сервер не блокирует изменения из другой вкладки между проверкой и сохранением. Не меняйте активную серию одновременно в нескольких вкладках.</p>
      {write.error && <p role="alert">{write.error}</p>}
    </Sheet>
  </>;
}
