import { Film, Flame, ImageIcon, Link2, RefreshCw, Repeat2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { copyTrendLink, openTrendRunner } from "@/features/trend-runner";
import type { TrendItem } from "@/lib/types";
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

const filters = [
  { value: "all" as const, label: "Все", icon: Flame },
  { value: "image" as const, label: "Фото", icon: ImageIcon },
  { value: "video" as const, label: "Видео", icon: Film },
];

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

function TrendsScreen({
  items,
  filter,
  loading,
  onFilterChange,
  onRefresh,
}: TrendsScreenProps) {
  const filtered = filter === "all" ? items : items.filter((item) => item.kind === filter);
  const imageItems = filtered.filter((item) => item.kind === "image");
  const videoItems = filtered.filter((item) => item.kind === "video");

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

      {filtered.length ? (
        <div className="grid gap-4">
          <TrendGroup title="Фото-тренды" emoji="🖼️" items={imageItems} />
          <TrendGroup title="Видео-тренды" emoji="🎬" items={videoItems} />
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
