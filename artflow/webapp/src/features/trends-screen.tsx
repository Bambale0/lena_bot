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
    <div className="grid gap-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <Badge className="mb-2">Каталог сценариев</Badge>
          <h1 className="text-3xl font-bold tracking-tight">Тренды</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Нажмите «Повторить»: модель и параметры перенесутся в рабочую форму, а скрытый prompt останется на backend.
          </p>
        </div>
        <Button variant="outline" size="icon" disabled={loading} onClick={onRefresh} aria-label="Обновить тренды">
          <RefreshCw className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {filters.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            className={cn(
              "apix-focus-ring flex min-h-10 shrink-0 items-center gap-2 rounded-xl border px-4 text-sm font-semibold transition",
              filter === value
                ? "border-primary/40 bg-primary/15 text-primary"
                : "border-border bg-card/55 text-muted-foreground",
            )}
            onClick={() => onFilterChange(value)}
          >
            <Icon className="size-4" />
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
                <div className={cn("overflow-hidden bg-muted", index % 5 === 0 ? "aspect-[3/4]" : "aspect-[4/5]") }>
                  {media ? (
                    isVideo ? (
                      <video src={media} muted playsInline loop preload="metadata" className="size-full object-cover" />
                    ) : (
                      <img src={media} alt="" loading="lazy" className="size-full object-cover" />
                    )
                  ) : (
                    <div className="grid size-full place-items-center text-muted-foreground">
                      {isVideo ? <Film /> : <ImageIcon />}
                    </div>
                  )}
                </div>
                <div className="grid gap-3 p-3">
                  <div>
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      <Badge variant="outline">{trend.category_emoji || (isVideo ? "🎬" : "🖼️")} {trend.category_title || trend.kind}</Badge>
                      {trend.uses_count ? <Badge variant="secondary">{trend.uses_count} повторов</Badge> : null}
                    </div>
                    <h2 className="text-sm font-semibold leading-snug">{trend.title}</h2>
                    {trend.description ? <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-muted-foreground">{trend.description}</p> : null}
                  </div>
                  <Button disabled={preparingId === trend.id} onClick={() => onPrepare(trend)}>
                    {preparingId === trend.id ? (
                      <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    ) : (
                      <Repeat2 />
                    )}
                    Повторить
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <div className="grid min-h-56 place-items-center rounded-2xl border border-dashed border-border text-center text-sm text-muted-foreground">
          {loading ? "Загружаем тренды…" : "В этой категории пока нет трендов"}
        </div>
      )}
    </div>
  );
}

export { TrendsScreen };
