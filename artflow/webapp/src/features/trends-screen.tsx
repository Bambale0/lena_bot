import { Film, Flame, ImageIcon, RefreshCw, Repeat2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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

function TrendsScreen({
  items,
  filter,
  loading,
  preparingId,
  onFilterChange,
  onRefresh,
  onPrepare,
}: TrendsScreenProps) {
  const filtered = filter === "all" ? items : items.filter((item) => item.kind === filter);

  return (
    <div className="grid gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight sm:text-xl">Тренды</h1>
            <Badge variant="outline">{filtered.length}</Badge>
          </div>
          <details className="apix-help max-w-xl">
            <summary>Как повторить тренд</summary>
            <p className="pb-2">Модель и параметры попадут в форму, скрытый промпт останется на backend.</p>
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
        <div className="apix-media-grid">
          {filtered.map((trend, index) => {
            const media = safeExternalUrl(trend.preview_url);
            const isVideo = trend.kind === "video";
            return (
              <Card key={trend.id} className="overflow-hidden shadow-none">
                <div className={cn("relative overflow-hidden bg-muted", index % 5 === 0 ? "aspect-[3/4]" : "aspect-[4/5]") }>
                  {media ? (
                    isVideo ? (
                      <video src={media} muted playsInline loop preload="metadata" className="size-full object-cover" />
                    ) : (
                      <img src={media} alt="" loading="lazy" className="size-full object-cover" />
                    )
                  ) : (
                    <div className="grid size-full place-items-center text-muted-foreground">{isVideo ? <Film /> : <ImageIcon />}</div>
                  )}
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-2 pb-2 pt-10 text-white">
                    <div className="mb-1 flex items-center gap-1 text-[8px] opacity-85">
                      <span>{trend.category_emoji || (isVideo ? "🎬" : "🖼️")}</span>
                      <span className="truncate">{trend.category_title || trend.kind}</span>
                      {trend.uses_count ? <span className="ml-auto">↻ {trend.uses_count}</span> : null}
                    </div>
                    <h2 className="line-clamp-2 text-[11px] font-semibold leading-tight">{trend.title}</h2>
                  </div>
                </div>
                <div className="grid gap-1.5 p-1.5">
                  {trend.description ? (
                    <details className="apix-help border-0">
                      <summary className="py-1 text-[10px]">Описание</summary>
                      <p className="line-clamp-6 pb-1 text-[10px]">{trend.description}</p>
                    </details>
                  ) : null}
                  <Button className="min-h-8 px-2 text-[10px]" disabled={preparingId === trend.id} onClick={() => onPrepare(trend)}>
                    {preparingId === trend.id ? (
                      <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    ) : (
                      <Repeat2 className="size-3.5" />
                    )}
                    Повторить
                  </Button>
                </div>
              </Card>
            );
          })}
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
