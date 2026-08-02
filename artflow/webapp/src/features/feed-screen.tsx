import { useMemo, useState } from "react";
import { Heart, Play, RefreshCw, Repeat2, Share2, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { FeedItem } from "@/lib/types";
import { cn, firstMedia, safeExternalUrl } from "@/lib/utils";
import { openExternalUrl } from "@/lib/telegram";

type FeedSource = "recent" | "top_day" | "top";
type WorkFilter = "all" | "image" | "video" | "mine";

interface FeedScreenProps {
  items: FeedItem[];
  source: FeedSource;
  loading: boolean;
  title?: string;
  subtitle?: string;
  repeatFirst?: boolean;
  remixingId?: number | null;
  onSourceChange: (source: FeedSource) => void;
  onRefresh: () => void;
  onLike: (item: FeedItem) => void;
  onRemix: (item: FeedItem) => void;
}

const sourceFilters = [
  { value: "recent" as const, label: "Новые" },
  { value: "top_day" as const, label: "Топ дня" },
  { value: "top" as const, label: "Лучшие" },
];

const workFilters = [
  { value: "all" as const, label: "Все" },
  { value: "image" as const, label: "Фото" },
  { value: "video" as const, label: "Видео" },
  { value: "mine" as const, label: "Мои" },
];

function itemLooksVideo(item: FeedItem): boolean {
  const media = firstMedia(item);
  return item.gen_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(media);
}

function FeedScreen({
  items,
  source,
  loading,
  title = "Лента",
  subtitle = "Все опубликованные работы. Повтор запускается по скрытому промпту автора.",
  repeatFirst = false,
  remixingId = null,
  onSourceChange,
  onRefresh,
  onLike,
  onRemix,
}: FeedScreenProps) {
  const [workFilter, setWorkFilter] = useState<WorkFilter>("all");

  const visibleItems = useMemo(() => {
    return items.filter((item) => {
      if (workFilter === "mine") return Boolean(item.is_mine);
      if (workFilter === "video") return itemLooksVideo(item);
      if (workFilter === "image") return !itemLooksVideo(item);
      return true;
    });
  }, [items, workFilter]);

  return (
    <div className="grid gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight sm:text-xl">{title}</h1>
            <Badge variant="outline">{visibleItems.length}/{items.length}</Badge>
          </div>
          <details className="apix-help max-w-xl">
            <summary>Что здесь</summary>
            <p className="pb-2">{subtitle}</p>
          </details>
        </div>
        <Button variant="outline" size="icon" className="size-9 min-h-9" disabled={loading} onClick={onRefresh} aria-label="Обновить ленту">
          <RefreshCw className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      <div className="grid gap-1.5">
        <div className="flex gap-1 overflow-x-auto pb-0.5">
          {sourceFilters.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={cn(
                "apix-focus-ring min-h-8 shrink-0 rounded-lg border px-3 text-xs font-semibold transition",
                source === filter.value
                  ? "border-primary/40 bg-primary/15 text-primary"
                  : "border-border bg-card/55 text-muted-foreground",
              )}
              onClick={() => onSourceChange(filter.value)}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="flex gap-1 overflow-x-auto pb-0.5">
          {workFilters.map((filter) => (
            <button
              key={filter.value}
              type="button"
              className={cn(
                "apix-focus-ring min-h-8 shrink-0 rounded-lg border px-3 text-xs font-semibold transition",
                workFilter === filter.value
                  ? "border-cyan-400/45 bg-cyan-400/15 text-cyan-700 dark:text-cyan-200"
                  : "border-border bg-card/55 text-muted-foreground",
              )}
              onClick={() => setWorkFilter(filter.value)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {visibleItems.length ? (
        <div className="apix-media-grid">
          {visibleItems.map((item) => {
            const media = safeExternalUrl(firstMedia(item));
            const isVideo = itemLooksVideo(item);
            const remixing = remixingId === item.id;
            return (
              <Card key={item.id} className="overflow-hidden shadow-none">
                <button
                  type="button"
                  className="apix-focus-ring relative block w-full overflow-hidden bg-muted"
                  onClick={() => media && openExternalUrl(media)}
                >
                  {media ? (
                    isVideo ? (
                      <video src={media} muted playsInline preload="metadata" className="max-h-[520px] w-full object-cover" />
                    ) : (
                      <img src={media} alt="" loading="lazy" className="max-h-[520px] w-full object-cover" />
                    )
                  ) : (
                    <div className="grid aspect-[4/5] place-items-center text-xs text-muted-foreground">Нет preview</div>
                  )}
                  {isVideo ? <span className="absolute inset-0 grid place-items-center"><span className="grid size-9 place-items-center rounded-full bg-black/55 text-white"><Play className="ml-0.5 size-4" /></span></span> : null}
                  <span className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-gradient-to-t from-black/75 to-transparent px-2 pb-1.5 pt-7 text-white">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="grid size-5 shrink-0 place-items-center overflow-hidden rounded-full bg-white/20">
                        {item.author_photo_url ? <img src={item.author_photo_url} alt="" className="size-full object-cover" /> : <UserRound className="size-3" />}
                      </span>
                      <span className="truncate text-[9px] font-semibold">{item.author || "Автор"}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1 text-[8px] opacity-85">
                      {item.is_mine ? <span>моё</span> : null}
                      {item.aspect_ratio ? <span>{item.aspect_ratio}</span> : null}
                    </span>
                  </span>
                </button>

                <div className="grid gap-1.5 p-1.5">
                  {item.prompt && !item.prompt_hidden ? (
                    <details className="apix-help border-0">
                      <summary className="py-1 text-[10px]">Промпт</summary>
                      <p className="line-clamp-6 pb-1 text-[10px]">{item.prompt}</p>
                    </details>
                  ) : null}

                  <div className={cn("grid gap-1", repeatFirst ? "grid-cols-[1fr_34px_34px]" : "grid-cols-[34px_34px_1fr]") }>
                    {repeatFirst ? (
                      <Button size="sm" className="min-h-8 px-2 text-[10px]" disabled={remixing} onClick={() => onRemix(item)}>
                        <Repeat2 className={cn("size-3.5", remixing && "animate-spin")} /> {remixing ? "Запуск" : "Повторить"}
                      </Button>
                    ) : null}
                    <Button variant="ghost" size="icon" className="size-8 min-h-8" aria-label="Лайк" onClick={() => onLike(item)}>
                      <Heart className="size-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" className="size-8 min-h-8" aria-label="Открыть результат" onClick={() => media && openExternalUrl(media)}>
                      <Share2 className="size-3.5" />
                    </Button>
                    {!repeatFirst ? (
                      <Button size="sm" className="min-h-8 px-2 text-[10px]" disabled={remixing} onClick={() => onRemix(item)}>
                        <Repeat2 className={cn("size-3.5", remixing && "animate-spin")} /> {remixing ? "Запуск" : "Повторить"}
                      </Button>
                    ) : null}
                  </div>
                  <div className="flex gap-2 px-1 text-[9px] text-muted-foreground">
                    <span>♥ {item.likes_count || 0}</span>
                    <span>↗ {item.shares_count || 0}</span>
                    <span>↻ {item.remixes || 0}</span>
                    <span className="ml-auto truncate">{item.model}</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-border text-center text-xs text-muted-foreground">
          {loading ? "Загружаем работы…" : "По этому фильтру работ пока нет"}
        </div>
      )}
    </div>
  );
}

export { FeedScreen };
