import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, ChevronUp, Eye, EyeOff, Film, Flame, FolderOpen, ImageIcon, Link2, LoaderCircle, Plus, RefreshCw, Repeat2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { isPinterestServiceTrend } from "@/features/pinterest-service";
import { copyTrendLink, openTrendRunner } from "@/features/trend-runner";
import { ApiError, MiniAppApi } from "@/lib/api";
import { readTelegramInitData } from "@/lib/telegram";
import type { AdminTrendCategory, AdminTrendCategoryCatalog, ModelInfo, TrendCategoryItemsPage, TrendCategoryPage, TrendCategoryShelf, TrendItem, TrendUserField } from "@/lib/types";
import { cn, safeExternalUrl } from "@/lib/utils";

interface TrendsScreenProps {
  items: TrendItem[];
  filter: "all" | "image" | "video";
  loading: boolean;
  preparingId?: number | null;
  onFilterChange: (filter: "all" | "image" | "video") => void;
  onRefresh: () => void;
  onPrepare: (trend: TrendItem) => void;
}

type TrendKind = "image" | "video";
const filters = [
  { value: "all" as const, label: "Все", icon: Flame },
  { value: "image" as const, label: "Фото", icon: ImageIcon },
  { value: "video" as const, label: "Видео", icon: Film },
];

const TEMPLATE_FIELD_PRESETS = ["Возраст", "Имя", "Надпись", "Дата", "Число", "Одежда"] as const;
const NUMBER_FIELD_HINTS = ["возраст", "число", "цифр", "количество", "номер", "рост", "вес", "лет", "год", "свеч"];
const DATE_FIELD_HINTS = ["дата", "date", "день рождения", "birthday"];

function trendFieldFromLabel(label: string): TrendUserField {
  const clean = label.replace(/[{}]/g, "").trim().slice(0, 48);
  const normalized = clean.toLowerCase();
  const type: TrendUserField["type"] = DATE_FIELD_HINTS.some((hint) => normalized.includes(hint))
    ? "date"
    : NUMBER_FIELD_HINTS.some((hint) => normalized.includes(hint))
      ? "number"
      : "text";
  return { key: clean, label: clean, type, required: true, max_length: 160 };
}

function TrendFieldPicker({
  fields,
  onChange,
}: {
  fields: TrendUserField[];
  onChange: (fields: TrendUserField[]) => void;
}) {
  const [customField, setCustomField] = useState("");

  const addField = (label: string) => {
    const field = trendFieldFromLabel(label);
    if (!field.key || fields.length >= 6 || fields.some((item) => item.key.toLowerCase() === field.key.toLowerCase())) return;
    onChange([...fields, field]);
    setCustomField("");
  };

  return (
    <div className="grid gap-2 rounded-xl border border-primary/20 bg-primary/5 p-3">
      <div>
        <p className="text-xs font-semibold text-foreground">Поля для пользователя</p>
        <p className="text-[10px] text-muted-foreground">При повторе человек сможет менять только эти значения. Скрытый prompt не показывается.</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {TEMPLATE_FIELD_PRESETS.map((preset) => {
          const active = fields.some((field) => field.key.toLowerCase() === preset.toLowerCase());
          return (
            <Button
              key={preset}
              type="button"
              size="sm"
              variant="outline"
              className="min-h-8 px-2 text-[10px]"
              disabled={active || fields.length >= 6}
              onClick={() => addField(preset)}
            >
              ＋ {preset}
            </Button>
          );
        })}
      </div>
      <div className="grid grid-cols-[1fr_auto] gap-2">
        <input
          value={customField}
          maxLength={48}
          className="min-h-9 min-w-0 rounded-lg border border-border bg-background px-3 text-xs"
          placeholder="Другое поле, например: Цвет волос"
          onChange={(event) => setCustomField(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addField(customField);
            }
          }}
        />
        <Button type="button" size="sm" variant="outline" disabled={!customField.trim() || fields.length >= 6} onClick={() => addField(customField)}>
          Добавить
        </Button>
      </div>
      {fields.length ? (
        <div className="flex flex-wrap gap-1.5">
          {fields.map((field) => (
            <span key={field.key} className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-1 text-[10px] font-semibold">
              {field.label}
              <button
                type="button"
                className="grid size-5 place-items-center rounded-full text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                aria-label={`Удалить поле ${field.label}`}
                onClick={() => onChange(fields.filter((item) => item.key !== field.key))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      ) : <p className="text-[10px] text-muted-foreground">Если менять ничего не нужно — оставь блок пустым.</p>}
    </div>
  );
}

function normalizeModels(value: unknown): ModelInfo[] {
  if (Array.isArray(value)) return value as ModelInfo[];
  if (value && typeof value === "object") {
    const items = (value as Record<string, unknown>).items;
    if (Array.isArray(items)) return items as ModelInfo[];
  }
  return [];
}

function modelDurations(model?: ModelInfo): number[] {
  if (model?.duration_options?.length) return model.duration_options;
  if (model?.durations?.length) return model.durations;
  return [5, 10];
}

function TrendPreview({ item }: { item: Pick<TrendItem, "kind" | "preview_url" | "title"> }) {
  const media = safeExternalUrl(item.preview_url || "");
  if (!media) {
    return <div className="grid aspect-[4/5] w-full place-items-center rounded-xl bg-muted text-muted-foreground">{item.kind === "video" ? <Film /> : <ImageIcon />}</div>;
  }
  if (item.kind === "video") {
    return <video src={media} controls muted playsInline preload="metadata" className="max-h-[420px] w-full rounded-xl bg-black object-contain" />;
  }
  return <img src={media} alt={item.title || "Trend"} loading="lazy" className="max-h-[420px] w-full rounded-xl bg-black object-contain" />;
}

function TrendCard({
  trend,
  index,
  isAdmin,
  client,
  onUpdated,
}: {
  trend: TrendItem;
  index: number;
  isAdmin: boolean;
  client: MiniAppApi;
  onUpdated: () => void;
}) {
  const media = safeExternalUrl(trend.preview_url);
  const isVideo = trend.kind === "video";
  const [editingFields, setEditingFields] = useState(false);
  const [userFields, setUserFields] = useState<TrendUserField[]>([]);
  const [savingFields, setSavingFields] = useState(false);

  const openFields = () => {
    setUserFields((trend.user_fields || []).map((field) => trendFieldFromLabel(field.label || field.key)).slice(0, 6));
    setEditingFields(true);
  };

  const saveFields = async () => {
    if (savingFields) return;
    setSavingFields(true);
    try {
      await client.request<TrendItem>(`/admin/trends/${trend.id}/update`, {
        method: "POST",
        body: JSON.stringify({ user_fields: userFields }),
      });
      toast.success("Поля тренда сохранены");
      setEditingFields(false);
      onUpdated();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось сохранить поля");
    } finally {
      setSavingFields(false);
    }
  };
  return (
    <Card className="overflow-hidden shadow-none">
      <button
        type="button"
        className={cn("relative block w-full overflow-hidden bg-muted text-left", index % 5 === 0 ? "aspect-[3/4]" : "aspect-[4/5]")}
        onClick={() => openTrendRunner(trend)}
      >
        {media ? (
          isVideo ? (
            <video src={media} muted playsInline preload="metadata" className="size-full object-cover" />
          ) : (
            <img src={media} alt="" loading="lazy" className="size-full object-cover" />
          )
        ) : (
          <div className="grid size-full place-items-center text-muted-foreground">{isVideo ? <Film /> : <ImageIcon />}</div>
        )}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 to-transparent px-2 pb-2 pt-12 text-white">
          <div className="mb-1 flex items-center gap-1 text-[8px] opacity-85">
            <span>{trend.category_emoji || (isVideo ? "🎬" : "🖼️")}</span>
            <span className="truncate">{trend.category_title || (isVideo ? "Видео-тренд" : "Фото-тренд")}</span>
            {trend.uses_count ? <span className="ml-auto">↻ {trend.uses_count}</span> : null}
          </div>
          <h2 className="line-clamp-2 text-[11px] font-semibold leading-tight">{trend.title}</h2>
        </div>
      </button>
      <div className="grid gap-1.5 p-1.5">
        {trend.description ? <p className="line-clamp-2 text-[10px] text-muted-foreground">{trend.description}</p> : null}
        <div className="grid grid-cols-[1fr_auto] gap-1.5">
          <Button className="min-h-8 px-2 text-[10px]" onClick={() => openTrendRunner(trend)}>
            <Repeat2 className="size-3.5" />
            Повторить
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-8 min-h-8"
            aria-label="Скопировать ссылку на тренд"
            onClick={async () => {
              try {
                await copyTrendLink(trend);
                toast.success("Ссылка скопирована");
              } catch (error) {
                toast.error(error instanceof Error ? error.message : "Не удалось скопировать ссылку");
              }
            }}
          >
            <Link2 className="size-3.5" />
          </Button>
        </div>
        {isAdmin ? (
          <Button variant="outline" className="min-h-8 text-[10px]" onClick={() => editingFields ? setEditingFields(false) : openFields()}>
            {editingFields ? "Закрыть настройку полей" : "⚙ Поля при повторе"}
          </Button>
        ) : null}
        {isAdmin && editingFields ? (
          <div className="grid gap-2">
            <TrendFieldPicker fields={userFields} onChange={setUserFields} />
            <Button className="min-h-9 text-xs" disabled={savingFields} onClick={() => void saveFields()}>
              {savingFields ? "Сохраняю…" : "Сохранить поля"}
            </Button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function TrendGroup({
  title,
  emoji,
  items,
  isAdmin,
  client,
  onUpdated,
}: {
  title: string;
  emoji: string;
  items: TrendItem[];
  isAdmin: boolean;
  client: MiniAppApi;
  onUpdated: () => void;
}) {
  if (!items.length) return null;
  return (
    <section className="grid gap-2">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-bold">{emoji} {title}</h2>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      <div className="apix-media-grid">
        {items.map((trend, index) => (
          <TrendCard key={trend.id} trend={trend} index={index} isAdmin={isAdmin} client={client} onUpdated={onUpdated} />
        ))}
      </div>
    </section>
  );
}

function TrendAdminForm({ client, categories, onCreated }: { client: MiniAppApi; categories: TrendCategoryShelf[]; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<TrendKind>("image");
  const [category, setCategory] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [model, setModel] = useState("");
  const [promptTemplate, setPromptTemplate] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [scenario, setScenario] = useState("image");
  const [duration, setDuration] = useState(5);
  const [ratio, setRatio] = useState("");
  const [quality, setQuality] = useState("");
  const [resolution, setResolution] = useState("");
  const [userFields, setUserFields] = useState<TrendUserField[]>([]);
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [videoModels, setVideoModels] = useState<ModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const models = kind === "video" ? videoModels : imageModels;
  const selectedModel = useMemo(() => models.find((item) => item.key === model), [model, models]);
  const durationOptions = useMemo(() => modelDurations(selectedModel), [selectedModel]);
  const durationIndex = Math.max(0, durationOptions.indexOf(duration));
  const selectedDuration = durationOptions[durationIndex] ?? duration;

  useEffect(() => {
    if (!categories.length) { setCategory(""); return; }
    if (!categories.some(item => item.key === category)) setCategory(categories[0].key);
  }, [categories, category]);

  useEffect(() => {
    if (!open || imageModels.length || videoModels.length || loadingModels) return;
    setLoadingModels(true);
    Promise.all([
      client.request<unknown>("/models/image"),
      client.request<unknown>("/models/video"),
    ])
      .then(([images, videos]) => {
        setImageModels(normalizeModels(images));
        setVideoModels(normalizeModels(videos));
      })
      .catch((error) => toast.error(error instanceof Error ? error.message : "Не удалось загрузить модели"))
      .finally(() => setLoadingModels(false));
  }, [client, imageModels.length, loadingModels, open, videoModels.length]);

  useEffect(() => {
    if (!models.length) {
      setModel("");
      return;
    }
    if (!models.some((item) => item.key === model)) setModel(models[0].key);
  }, [model, models]);

  useEffect(() => {
    if (kind !== "video") return;
    if (!durationOptions.includes(duration)) setDuration(durationOptions[0] || 5);
  }, [duration, durationOptions, kind]);

  async function uploadPreview(file: File) {
    if (uploading) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("kind", kind);
      form.append("file", file);
      const result = await client.request<{ url?: string }>("/admin/trends/upload", { method: "POST", body: form });
      if (!result.url) throw new Error("Backend не вернул preview URL");
      setPreviewUrl(result.url);
      toast.success("Preview загружен");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить preview");
    } finally {
      setUploading(false);
    }
  }

  async function submit() {
    if (busy) return;
    if (title.trim().length < 3 || !promptTemplate.trim() || !previewUrl || !model) {
      toast.error("Заполни название, модель, preview и скрытый prompt");
      return;
    }
    setBusy(true);
    try {
      await client.request<TrendItem>("/admin/trends", {
        method: "POST",
        body: JSON.stringify({
          kind,
          title: title.trim(),
          description: description.trim(),
          prompt_template: promptTemplate.trim(),
          preview_url: previewUrl,
          model,
          user_fields: userFields,
          settings: {
            category,
            scenario: kind === "video" ? scenario : undefined,
            duration: kind === "video" ? Number(duration) : undefined,
            ratio: ratio || undefined,
            quality: kind === "image" ? quality || undefined : undefined,
            resolution: kind === "video" ? resolution || undefined : undefined,
            requires_reference: kind === "image" || scenario === "image",
          },
        }),
      });
      setTitle("");
      setDescription("");
      setPromptTemplate("");
      setPreviewUrl("");
      setCategory(categories[0]?.key || "");
      setUserFields([]);
      toast.success("Тренд опубликован");
      setOpen(false);
      onCreated();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось опубликовать тренд");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <Button className="w-full sm:w-auto" onClick={() => setOpen(true)}>
        <Plus className="size-4" />
        Добавить тренд
      </Button>
    );
  }

  return (
    <Card className="grid gap-3 p-3 shadow-none">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold">Добавить тренд</h2>
          <p className="text-[10px] text-muted-foreground">Категория «С животными» теперь поддерживается напрямую.</p>
        </div>
        <Button variant="ghost" size="icon" className="size-8 min-h-8" onClick={() => setOpen(false)} aria-label="Закрыть форму">
          <X className="size-4" />
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-1">
        <Button variant={kind === "image" ? "default" : "outline"} onClick={() => setKind("image")}>🖼 Фото</Button>
        <Button variant={kind === "video" ? "default" : "outline"} onClick={() => setKind("video")}>🎬 Видео</Button>
      </div>

      <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">
        Категория
        <select className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs text-foreground" value={category} onChange={(event) => setCategory(event.target.value)}>
          {categories.map((item) => <option key={item.key} value={item.key}>{item.title}</option>)}
        </select>
      </label>

      <input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Название — до 60 символов" maxLength={60} />
      <textarea className="min-h-20 rounded-lg border border-border bg-background p-3 text-xs" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Публичное описание — до 200 символов" maxLength={200} />

      <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">
        Модель
        <select className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs text-foreground" value={model} onChange={(event) => setModel(event.target.value)} disabled={loadingModels || !models.length}>
          {models.map((item) => <option key={item.key} value={item.key}>{item.display_name}</option>)}
        </select>
      </label>

      {kind === "video" ? (
        <div className="grid gap-2">
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Сценарий<select className="min-h-10 rounded-lg border border-border bg-background px-2 text-xs text-foreground" value={scenario} onChange={(event) => setScenario(event.target.value)}><option value="image">Фото → видео</option><option value="text">Текст → видео</option></select></label>
          <div className="grid gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] font-semibold text-muted-foreground">Длительность</span>
              <Badge variant="outline">{selectedDuration} сек</Badge>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(0, durationOptions.length - 1)}
              step={1}
              value={durationIndex}
              disabled={durationOptions.length <= 1}
              aria-label="Длительность видео-тренда"
              aria-valuetext={`${selectedDuration} секунд`}
              className="apix-focus-ring h-8 w-full cursor-pointer accent-primary disabled:cursor-default disabled:opacity-60"
              onChange={(event) => {
                const nextDuration = durationOptions[Number(event.target.value)];
                if (nextDuration != null) setDuration(nextDuration);
              }}
            />
            <div className="flex items-center justify-between gap-1 text-[10px] text-muted-foreground">
              {durationOptions.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={cn("apix-focus-ring rounded px-1 py-0.5 transition", value === selectedDuration ? "font-semibold text-primary" : "hover:text-foreground")}
                  onClick={() => setDuration(value)}
                >
                  {value} сек
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Формат<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={ratio} onChange={(event) => setRatio(event.target.value)} placeholder="9:16" /></label>
            <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Разрешение<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="720p" /></label>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Формат<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={ratio} onChange={(event) => setRatio(event.target.value)} placeholder="4:5 или 9:16" /></label>
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Качество<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={quality} onChange={(event) => setQuality(event.target.value)} placeholder="basic / 2K / 4K" /></label>
        </div>
      )}

      <Button variant="outline" disabled={uploading} onClick={() => fileRef.current?.click()}>
        <Upload className="size-4" />
        {uploading ? "Загружаю…" : previewUrl ? "Заменить preview" : "Загрузить preview"}
      </Button>
      <input
        ref={fileRef}
        type="file"
        hidden
        accept={kind === "video" ? "video/mp4,video/webm,video/quicktime" : "image/jpeg,image/png,image/webp"}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void uploadPreview(file);
        }}
      />
      {previewUrl ? <TrendPreview item={{ kind, preview_url: previewUrl, title }} /> : null}

      <textarea className="min-h-32 rounded-lg border border-border bg-background p-3 text-xs" value={promptTemplate} onChange={(event) => setPromptTemplate(event.target.value)} placeholder="Скрытый канонический prompt — до 8000 символов" maxLength={8000} />
      <TrendFieldPicker fields={userFields} onChange={setUserFields} />
      <p className="-mt-1 text-[10px] text-muted-foreground">Например, выбери «Число» и «Одежда». Можно использовать <code>{"{{Число}}"}</code> / <code>{"{{Одежда}}"}</code> в prompt, но это не обязательно: backend всё равно добавит выбранные значения как приоритетные изменения.</p>
      <Button disabled={busy || uploading || loadingModels || !model || !category} onClick={() => void submit()}>{busy ? "Публикую…" : "Опубликовать тренд"}</Button>
    </Card>
  );
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update(); query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

function LiveTrendMedia({ trend }: { trend: TrendItem }) {
  const frame = useRef<HTMLSpanElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const reduced = useReducedMotion();
  const [visible, setVisible] = useState(false);
  const [failed, setFailed] = useState(false);
  const src = safeExternalUrl(trend.preview_url || "");
  useEffect(() => {
    const node = frame.current;
    if (!node || trend.kind !== "video" || !src || failed) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(Boolean(entry?.isIntersecting)), { root: null, threshold: 0.05 });
    observer.observe(node);
    return () => observer.disconnect();
  }, [failed, src, trend.kind]);
  useEffect(() => {
    const node = video.current;
    if (!node) return;
    if (visible && !reduced) void node.play().catch(() => undefined);
    else node.pause();
  }, [reduced, visible]);
  if (!src || failed) return <span ref={frame} className="trend-live-fallback"><SparklesFallback kind={trend.kind} /></span>;
  if (trend.kind === "video") return <span ref={frame} className="trend-live-media">{visible ? <video ref={video} src={src} muted loop playsInline preload="metadata" onError={() => setFailed(true)} /> : null}</span>;
  return <span ref={frame} className="trend-live-media"><img src={src} alt="" loading="lazy" onError={() => setFailed(true)} /></span>;
}

function SparklesFallback({ kind }: { kind: TrendKind }) {
  return kind === "video" ? <Film aria-hidden="true" /> : <ImageIcon aria-hidden="true" />;
}

function ShelfTrendTile({ trend }: { trend: TrendItem }) {
  return <button type="button" className="trend-live-tile" aria-label={`Повторить: ${trend.title}`} onClick={() => openTrendRunner(trend)}>
    <LiveTrendMedia trend={trend} />
    <span className="trend-live-copy"><strong>{trend.title}</strong><small>{trend.description || (trend.kind === "video" ? "Видео" : "Фото")}</small><span><Repeat2 size={14} /> Повторить</span></span>
  </button>;
}

function CategoryShelf({ shelf, filter, onOpen }: { shelf: TrendCategoryShelf; filter: TrendsScreenProps["filter"]; onOpen: () => void }) {
  const previews = filter === "all" ? shelf.preview_items : shelf.preview_items.filter(item => item.kind === filter);
  if (!previews.length) return null;
  return <section className="trend-category-shelf" data-category-key={shelf.key}>
    <div className="trend-category-heading"><div><h2>{shelf.title}</h2><p>{shelf.trend_count} {shelf.trend_count === 1 ? "пример" : "примеров"}</p></div>
      <button type="button" aria-label={`Смотреть все: ${shelf.title}`} onClick={onOpen}>Смотреть все <FolderOpen size={16} /></button></div>
    <div className="trend-live-rail">{previews.slice(0, 5).map(trend => <ShelfTrendTile key={trend.id} trend={trend} />)}</div>
  </section>;
}

function CategoryManager({ client, onChanged }: { client: MiniAppApi; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState<AdminTrendCategoryCatalog | null>(null);
  const [title, setTitle] = useState("");
  const [renames, setRenames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmKey, setConfirmKey] = useState<string | null>(null);
  const [promptId, setPromptId] = useState("");
  const [targetKey, setTargetKey] = useState("");
  const load = async () => {
    setBusy(true); setError("");
    try {
      const next = await client.getAdminTrendCategories();
      setCatalog(next); setRenames(Object.fromEntries(next.items.map(item => [item.key, item.title])));
      if (!targetKey && next.items.length) setTargetKey(next.items[0].key);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Не удалось загрузить категории"); }
    finally { setBusy(false); }
  };
  useEffect(() => { if (open && !catalog && !busy) void load(); }, [open, catalog, busy]);
  const mutationError = (caught: unknown) => {
    setError(caught instanceof ApiError && caught.status === 409 ? "Каталог изменился. Черновик сохранён — обновите список и повторите." : caught instanceof Error ? caught.message : "Изменение не сохранено");
  };
  const create = async () => {
    if (!catalog || busy || !title.trim()) return;
    setBusy(true); setError("");
    try {
      const result = await client.createTrendCategory(title.trim(), catalog.revision);
      setCatalog({ revision: result.revision, items: [...catalog.items, result.category] });
      setRenames(current => ({ ...current, [result.category.key]: result.category.title })); setTitle(""); onChanged();
    } catch (caught) { mutationError(caught); } finally { setBusy(false); }
  };
  const update = async (item: AdminTrendCategory, patch: { title?: string; is_visible?: boolean; confirm_populated?: boolean }) => {
    if (!catalog || busy) return;
    setBusy(true); setError("");
    try {
      const result = await client.updateTrendCategory(item.key, { ...patch, expected_revision: catalog.revision });
      setCatalog({ revision: result.revision, items: catalog.items.map(row => row.key === item.key ? { ...row, ...result.category } : row) });
      setConfirmKey(null); onChanged();
    } catch (caught) { mutationError(caught); } finally { setBusy(false); }
  };
  const move = async (index: number, offset: number) => {
    if (!catalog || busy) return;
    const target = index + offset;
    if (target < 0 || target >= catalog.items.length) return;
    const items = [...catalog.items]; [items[index], items[target]] = [items[target], items[index]];
    setBusy(true); setError("");
    try { const next = await client.reorderTrendCategories(items.map(item => item.key), catalog.revision); setCatalog(next); onChanged(); }
    catch (caught) { mutationError(caught); } finally { setBusy(false); }
  };
  const reassign = async () => {
    if (!catalog || busy || !targetKey || !/^\d+$/.test(promptId)) return;
    setBusy(true); setError("");
    try { const result = await client.reassignTrendCategory(targetKey, Number(promptId), catalog.revision); setCatalog({ ...catalog, revision: result.revision }); setPromptId(""); onChanged(); }
    catch (caught) { mutationError(caught); } finally { setBusy(false); }
  };
  if (!open) return <Button variant="outline" className="w-full sm:w-auto" onClick={() => setOpen(true)}>Управление категориями</Button>;
  return <Card className="trend-category-manager">
    <div className="trend-manager-title"><div><h2>Категории трендов</h2><p>Версия {catalog?.revision ?? "—"}</p></div><Button size="icon" variant="ghost" aria-label="Закрыть управление категориями" onClick={() => setOpen(false)}><X /></Button></div>
    {error && <div role="alert" className="trend-manager-error">{error} <button onClick={() => void load()}>Обновить</button></div>}
    <div className="trend-manager-create"><label>Название новой категории<input aria-label="Название новой категории" value={title} maxLength={80} onChange={event => setTitle(event.target.value)} /></label><Button disabled={busy || !catalog || !title.trim()} onClick={() => void create()}>Создать категорию</Button></div>
    {busy && !catalog ? <p><LoaderCircle className="inline animate-spin" /> Загружаем…</p> : null}
    <div className="trend-manager-list">{catalog?.items.map((item, index) => <div className="trend-manager-row" key={item.key}>
      <div className="trend-manager-order"><button aria-label={`Поднять ${item.title}`} disabled={busy || index === 0} onClick={() => void move(index, -1)}><ChevronUp /></button><button aria-label={`Опустить ${item.title}`} disabled={busy || index === catalog.items.length - 1} onClick={() => void move(index, 1)}><ChevronDown /></button></div>
      <label><span>{item.trend_count} всего · {item.published_count} опубликовано</span><input aria-label={`Название ${item.title}`} value={renames[item.key] ?? item.title} maxLength={80} onChange={event => setRenames(current => ({ ...current, [item.key]: event.target.value }))} /></label>
      <div className="trend-manager-actions"><Button variant="outline" disabled={busy || !(renames[item.key] || "").trim() || renames[item.key] === item.title} onClick={() => void update(item, { title: renames[item.key] })}>Переименовать</Button><Button variant="outline" aria-label={`${item.is_visible ? "Скрыть" : "Показать"} ${item.title}`} onClick={() => item.is_visible && item.trend_count ? setConfirmKey(item.key) : void update(item, { is_visible: !item.is_visible })}>{item.is_visible ? <EyeOff /> : <Eye />}{item.is_visible ? "Скрыть" : "Показать"}</Button></div>
      {confirmKey === item.key && <div className="trend-hide-confirm"><p>Скрыть папку с {item.trend_count} примерами? Новые запуски сразу станут недоступны.</p><Button variant="destructive" onClick={() => void update(item, { is_visible: false, confirm_populated: true })}>Подтвердить скрытие</Button><Button variant="outline" onClick={() => setConfirmKey(null)}>Отмена</Button></div>}
    </div>)}</div>
    <div className="trend-manager-reassign"><h3>Перенести тренд</h3><input aria-label="ID тренда" inputMode="numeric" value={promptId} onChange={event => setPromptId(event.target.value.replace(/\D/g, ""))} placeholder="ID тренда" /><select aria-label="Новая категория тренда" value={targetKey} onChange={event => setTargetKey(event.target.value)}>{catalog?.items.map(item => <option key={item.key} value={item.key}>{item.title}</option>)}</select><Button disabled={busy || !promptId || !targetKey} onClick={() => void reassign()}>Перенести</Button></div>
  </Card>;
}

function TrendsScreen({ filter, loading, onFilterChange, onRefresh }: TrendsScreenProps) {
  const client = useMemo(() => new MiniAppApi(readTelegramInitData()), []);
  const initialFolder = typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("trendCategory") || "";
  const [isAdmin, setIsAdmin] = useState(false);
  const [shelves, setShelves] = useState<TrendCategoryShelf[]>([]);
  const [shelfCursor, setShelfCursor] = useState<string | null>(null);
  const [shelfMore, setShelfMore] = useState(false);
  const [shelfLoading, setShelfLoading] = useState(true);
  const [shelfError, setShelfError] = useState("");
  const [folderKey, setFolderKey] = useState(initialFolder);
  const [folder, setFolder] = useState<TrendCategoryItemsPage | null>(null);
  const [folderLoading, setFolderLoading] = useState(false);
  const [folderError, setFolderError] = useState("");
  const shelfScroll = useRef(0);

  const loadShelves = async (append = false) => {
    setShelfLoading(true); setShelfError("");
    try {
      const page = await client.getTrendCategories(append ? shelfCursor || undefined : undefined);
      setShelves(current => append ? [...current, ...page.items] : page.items);
      setShelfCursor(page.next_cursor || null); setShelfMore(page.has_more);
    } catch (caught) { setShelfError(caught instanceof Error ? caught.message : "Не удалось загрузить категории"); }
    finally { setShelfLoading(false); }
  };
  useEffect(() => { void loadShelves(false); }, []);
  useEffect(() => {
    client.request<{ is_admin?: boolean }>("/me/permissions").then(user => setIsAdmin(Boolean(user.is_admin))).catch(() => setIsAdmin(false));
  }, [client]);
  useEffect(() => {
    const sync = () => setFolderKey(new URLSearchParams(window.location.search).get("trendCategory") || "");
    window.addEventListener("popstate", sync); return () => window.removeEventListener("popstate", sync);
  }, []);
  useEffect(() => {
    if (!folderKey) { setFolder(null); return; }
    let active = true; setFolderLoading(true); setFolderError(""); setFolder(null);
    client.getTrendCategoryItems(folderKey).then(page => { if (active) setFolder(page); }).catch(caught => { if (active) setFolderError(caught instanceof Error ? caught.message : "Не удалось открыть папку"); }).finally(() => { if (active) setFolderLoading(false); });
    return () => { active = false; };
  }, [client, folderKey]);
  const openFolder = (key: string) => {
    const main = document.querySelector<HTMLElement>(".apix-shell > main"); shelfScroll.current = main?.scrollTop || window.scrollY;
    const url = new URL(window.location.href); url.searchParams.set("trendCategory", key); history.pushState({}, "", url); setFolderKey(key);
  };
  const closeFolder = () => {
    const url = new URL(window.location.href); url.searchParams.delete("trendCategory"); history.pushState({}, "", url); setFolderKey("");
    requestAnimationFrame(() => { const main = document.querySelector<HTMLElement>(".apix-shell > main"); if (main) main.scrollTop = shelfScroll.current; else window.scrollTo({ top: shelfScroll.current }); });
  };
  const loadMoreFolder = async () => {
    if (!folder || folderLoading || !folder.has_more) return;
    setFolderLoading(true); setFolderError("");
    try { const next = await client.getTrendCategoryItems(folder.category.key, folder.next_cursor || undefined); setFolder({ ...next, items: [...folder.items, ...next.items] }); }
    catch (caught) { setFolderError(caught instanceof Error ? caught.message : "Не удалось загрузить следующую страницу"); }
    finally { setFolderLoading(false); }
  };
  const refresh = () => { onRefresh(); void loadShelves(false); if (folderKey) { setFolderKey(""); requestAnimationFrame(() => setFolderKey(folderKey)); } };
  const visibleShelves = shelves.map(shelf => ({ ...shelf, preview_items: shelf.preview_items.filter(item => !isPinterestServiceTrend(item)) })).filter(shelf => filter === "all" ? shelf.preview_items.length : shelf.preview_items.some(item => item.kind === filter));
  const folderItems = (folder?.items || []).filter(item => !isPinterestServiceTrend(item) && (filter === "all" || item.kind === filter));

  if (folderKey) return <div className="trend-folder-page">
    <button type="button" className="trend-folder-back" aria-label="Назад к категориям" onClick={closeFolder}><ArrowLeft /> Назад к категориям</button>
    <header><p>Папка трендов</p><h1>{folder?.category.title || "Загружаем…"}</h1><span>Выберите пример, добавьте свои материалы и подтвердите стоимость.</span></header>
    <div className="trend-kind-filters">{filters.map(({ value, label, icon: Icon }) => <button key={value} className={filter === value ? "active" : ""} onClick={() => onFilterChange(value)}><Icon />{label}</button>)}</div>
    {folderLoading && !folder ? <div className="trend-state"><LoaderCircle className="animate-spin" /> Загружаем папку…</div> : null}
    {folderError && !folder ? <div className="trend-state" role="alert"><p>{folderError}</p><Button onClick={() => { setFolderKey(""); requestAnimationFrame(() => setFolderKey(folderKey)); }}>Повторить</Button></div> : null}
    {folder && !folderItems.length ? <div className="trend-state"><FolderOpen /><p>В этой папке пока нет подходящих примеров.</p></div> : null}
    {folderItems.length ? <div className="trend-folder-grid">{folderItems.map(item => <ShelfTrendTile key={item.id} trend={item} />)}</div> : null}
    {folderError && folder ? <div className="trend-page-error" role="alert">{folderError}</div> : null}
    {folder?.has_more ? <Button className="trend-load-more" variant="outline" disabled={folderLoading} onClick={() => void loadMoreFolder()}>{folderLoading ? "Загружаем…" : "Показать ещё"}</Button> : null}
  </div>;

  return <div className="trend-shelves-page">
    <header className="trend-shelves-header"><div><p>Готовые сценарии</p><h1>Тренды по категориям</h1><span>Откройте папку или сразу повторите понравившийся пример.</span></div><Button variant="outline" size="icon" disabled={loading || shelfLoading} onClick={refresh} aria-label="Обновить тренды"><RefreshCw className={loading || shelfLoading ? "animate-spin" : ""} /></Button></header>
    <div className="trend-kind-filters">{filters.map(({ value, label, icon: Icon }) => <button key={value} className={filter === value ? "active" : ""} onClick={() => onFilterChange(value)}><Icon />{label}</button>)}</div>
    {isAdmin ? <div className="trend-admin-tools"><CategoryManager client={client} onChanged={refresh} /><TrendAdminForm client={client} categories={shelves} onCreated={refresh} /></div> : null}
    {shelfLoading && !shelves.length ? <div className="trend-shelf-skeleton" aria-label="Загружаем категории"><i /><i /><i /></div> : null}
    {shelfError && !shelves.length ? <div className="trend-state" role="alert"><p>{shelfError}</p><Button onClick={() => void loadShelves(false)}>Попробовать снова</Button></div> : null}
    {!shelfLoading && !shelfError && !visibleShelves.length ? <div className="trend-state"><FolderOpen /><p>Категории пока пусты. Можно создать работу по своей идее.</p></div> : null}
    <div className="trend-shelves-list">{visibleShelves.map(shelf => <CategoryShelf key={shelf.key} shelf={shelf} filter={filter} onOpen={() => openFolder(shelf.key)} />)}</div>
    {shelfError && shelves.length ? <div className="trend-page-error" role="alert">{shelfError}</div> : null}
    {shelfMore ? <Button variant="outline" className="trend-load-more" disabled={shelfLoading} onClick={() => void loadShelves(true)}>{shelfLoading ? "Загружаем…" : "Показать ещё категории"}</Button> : null}
  </div>;
}

export { TrendsScreen };
