import { useEffect, useMemo, useRef, useState } from "react";
import { Film, Flame, ImageIcon, Link2, Plus, RefreshCw, Repeat2, Upload, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { copyTrendLink, openTrendRunner } from "@/features/trend-runner";
import { MiniAppApi } from "@/lib/api";
import { readTelegramInitData } from "@/lib/telegram";
import type { ModelInfo, TrendItem } from "@/lib/types";
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
type TrendCategory = {
  value: string;
  label: string;
  emoji: string;
};

const TREND_CATEGORIES: TrendCategory[] = [
  { value: "featured", label: "Тренды", emoji: "🔥" },
  { value: "photo-video", label: "Фото → видео", emoji: "🎬" },
  { value: "portrait", label: "Портреты", emoji: "✨" },
  { value: "cartoon", label: "Мультфильм", emoji: "🎨" },
  { value: "animals", label: "С животными", emoji: "🦁" },
  { value: "holidays", label: "Праздники", emoji: "🎉" },
  { value: "style", label: "Образы", emoji: "💫" },
];

const filters = [
  { value: "all" as const, label: "Все", icon: Flame },
  { value: "image" as const, label: "Фото", icon: ImageIcon },
  { value: "video" as const, label: "Видео", icon: Film },
];

function normalizeModels(value: unknown): ModelInfo[] {
  if (Array.isArray(value)) return value as ModelInfo[];
  if (value && typeof value === "object") {
    const items = (value as Record<string, unknown>).items;
    if (Array.isArray(items)) return items as ModelInfo[];
  }
  return [];
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

function TrendCard({ trend, index }: { trend: TrendItem; index: number }) {
  const media = safeExternalUrl(trend.preview_url);
  const isVideo = trend.kind === "video";
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
      </div>
    </Card>
  );
}

function TrendGroup({ title, emoji, items }: { title: string; emoji: string; items: TrendItem[] }) {
  if (!items.length) return null;
  return (
    <section className="grid gap-2">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-bold">{emoji} {title}</h2>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      <div className="apix-media-grid">
        {items.map((trend, index) => <TrendCard key={trend.id} trend={trend} index={index} />)}
      </div>
    </section>
  );
}

function TrendAdminForm({ client, onCreated }: { client: MiniAppApi; onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<TrendKind>("image");
  const [category, setCategory] = useState("animals");
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
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [videoModels, setVideoModels] = useState<ModelInfo[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const models = kind === "video" ? videoModels : imageModels;

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
      setCategory("animals");
      toast.success(category === "animals" ? "Тренд добавлен в «С животными»" : "Тренд опубликован");
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
          {TREND_CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.emoji} {item.label}</option>)}
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
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Сценарий<select className="min-h-10 rounded-lg border border-border bg-background px-2 text-xs text-foreground" value={scenario} onChange={(event) => setScenario(event.target.value)}><option value="image">Фото → видео</option><option value="text">Текст → видео</option></select></label>
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Длительность<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" type="number" min={2} max={30} value={duration} onChange={(event) => setDuration(Number(event.target.value || 5))} /></label>
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Формат<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={ratio} onChange={(event) => setRatio(event.target.value)} placeholder="9:16" /></label>
          <label className="grid gap-1 text-[10px] font-semibold text-muted-foreground">Разрешение<input className="min-h-10 rounded-lg border border-border bg-background px-3 text-xs" value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="720p" /></label>
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
      <Button disabled={busy || uploading || loadingModels || !model} onClick={() => void submit()}>{busy ? "Публикую…" : category === "animals" ? "🦁 Опубликовать в «С животными»" : "Опубликовать тренд"}</Button>
    </Card>
  );
}

function TrendsScreen({
  items,
  filter,
  loading,
  onFilterChange,
  onRefresh,
}: TrendsScreenProps) {
  const client = useMemo(() => new MiniAppApi(readTelegramInitData()), []);
  const [isAdmin, setIsAdmin] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("all");

  useEffect(() => {
    client.request<{ is_admin?: boolean }>("/me")
      .then((user) => setIsAdmin(Boolean(user.is_admin)))
      .catch(() => setIsAdmin(false));
  }, [client]);

  const kindFiltered = filter === "all" ? items : items.filter((item) => item.kind === filter);
  const filtered = categoryFilter === "all" ? kindFiltered : kindFiltered.filter((item) => (item.category || "featured") === categoryFilter);
  const availableCategories = TREND_CATEGORIES.filter((category) => kindFiltered.some((item) => (item.category || "featured") === category.value));

  useEffect(() => {
    if (categoryFilter === "all") return;
    if (!availableCategories.some((item) => item.value === categoryFilter)) setCategoryFilter("all");
  }, [availableCategories, categoryFilter]);

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight sm:text-xl">Тренды</h1>
            <Badge variant="outline">{filtered.length}</Badge>
          </div>
          <details className="apix-help max-w-xl">
            <summary>Как повторить тренд</summary>
            <p className="pb-2">Выберите шаблон, загрузите одно фото — upload и генерация запустятся автоматически. Модель, скрытый промпт и provider-параметры остаются на backend.</p>
          </details>
        </div>
        <Button variant="outline" size="icon" className="size-9 min-h-9" disabled={loading} onClick={onRefresh} aria-label="Обновить тренды">
          <RefreshCw className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      {isAdmin ? <TrendAdminForm client={client} onCreated={onRefresh} /> : null}

      <div className="flex gap-1 overflow-x-auto pb-0.5">
        {filters.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            className={cn(
              "apix-focus-ring flex min-h-8 shrink-0 items-center gap-1.5 rounded-lg border px-3 text-xs font-semibold transition",
              filter === value
                ? "border-primary/40 bg-primary/15 text-primary"
                : "border-border bg-card/55 text-muted-foreground",
            )}
            onClick={() => onFilterChange(value)}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>

      {availableCategories.length ? (
        <div className="flex gap-1 overflow-x-auto pb-0.5" aria-label="Категории трендов">
          <button
            type="button"
            className={cn("apix-focus-ring min-h-8 shrink-0 rounded-lg border px-3 text-[10px] font-semibold", categoryFilter === "all" ? "border-primary/40 bg-primary/15 text-primary" : "border-border bg-card/55 text-muted-foreground")}
            onClick={() => setCategoryFilter("all")}
          >
            Все категории
          </button>
          {availableCategories.map((item) => (
            <button
              key={item.value}
              type="button"
              className={cn("apix-focus-ring min-h-8 shrink-0 rounded-lg border px-3 text-[10px] font-semibold", categoryFilter === item.value ? "border-primary/40 bg-primary/15 text-primary" : "border-border bg-card/55 text-muted-foreground")}
              onClick={() => setCategoryFilter(item.value)}
            >
              {item.emoji} {item.label}
            </button>
          ))}
        </div>
      ) : null}

      {filtered.length ? (
        <div className="grid gap-4">
          {TREND_CATEGORIES.map((category) => (
            <TrendGroup
              key={category.value}
              title={category.label}
              emoji={category.emoji}
              items={filtered.filter((item) => (item.category || "featured") === category.value)}
            />
          ))}
          <TrendGroup
            title="Другие"
            emoji="✨"
            items={filtered.filter((item) => !TREND_CATEGORIES.some((category) => category.value === (item.category || "featured")))}
          />
        </div>
      ) : (
        <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-border text-center text-xs text-muted-foreground">
          {loading ? "Загружаем тренды…" : "В этой категории пока нет трендов"}
        </div>
      )}
    </div>
  );
}

export { TrendsScreen };
