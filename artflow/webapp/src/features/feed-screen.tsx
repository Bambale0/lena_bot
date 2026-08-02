import { Heart, Play, RefreshCw, Repeat2, Share2, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { FeedItem } from "@/lib/types";
import { cn, firstMedia, safeExternalUrl } from "@/lib/utils";
import { openExternalUrl } from "@/lib/telegram";

interface FeedScreenProps {
  items: FeedItem[];
  source: "recent" | "top_day" | "top";
  loading: boolean;
  onSourceChange: (source: "recent" | "top_day" | "top") => void;
  onRefresh: () => void;
  onLike: (item: FeedItem) => void;
  onRemix: (item: FeedItem) => void;
}

const filters = [
  { value: "recent" as const, label: "Новые" },
  { value: "top_day" as const, label: "Топ дня" },
  { value: "top" as const, label: "Лучшие" },
];

function FeedScreen({ items, source, loading, onSourceChange, onRefresh, onLike, onRemix }: FeedScreenProps) {
  return (
    <div className="grid gap-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <Badge className="mb-2">Сообщество</Badge>
          <h1 className="text-3xl font-bold tracking-tight">Лента работ</h1>
          <p className="mt-1 text-sm text-muted-foreground">Только опубликованные результаты. Тяжёлые медиа загружаются порциями.</p>
        </div>
        <Button variant="outline" size="icon" disabled={loading} onClick={onRefresh} aria-label="Обновить ленту">
          <RefreshCw className={loading ? "animate-spin" : ""} />
        </Button>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {filters.map((filter) => (
          <button
            key={filter.value}
            type="button"
            className={cn(
              "apix-focus-ring min-h-10 shrink-0 rounded-xl border px-4 text-sm font-semibold transition",
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

      {items.length ? (
        <div className="apix-media-grid">
          {items.map((item) => {
            const media = safeExternalUrl(firstMedia(item));
            const isVideo = item.gen_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(media);
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
                    <div className="grid aspect-[4/5] place-items-center text-muted-foreground">Нет preview</div>
                  )}
                  {isVideo ? <span className="absolute inset-0 grid place-items-center"><span className="grid size-12 place-items-center rounded-full bg-black/55 text-white"><Play className="ml-0.5 size-5" /></span></span> : null}
                </button>

                <div className="grid gap-3 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-full bg-secondary">
                        {item.author_photo_url ? <img src={item.author_photo_url} alt="" className="size-full object-cover" /> : <UserRound className="size-4" />}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-semibold">{item.author || "Автор"}</span>
                        <span className="block truncate text-[10px] text-muted-foreground">{item.model}</span>
                      </span>
                    </div>
                    {item.aspect_ratio ? <Badge variant="outline">{item.aspect_ratio}</Badge> : null}
                  </div>

                  {item.prompt && !item.prompt_hidden ? (
                    <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground">{item.prompt}</p>
                  ) : null}

                  <div className="grid grid-cols-[1fr_auto_auto] gap-2">
                    <Button size="sm" onClick={() => onRemix(item)}>
                      <Repeat2 /> Повторить
                    </Button>
                    <Button variant="ghost" size="icon" aria-label="Лайк" onClick={() => onLike(item)}>
                      <Heart />
                    </Button>
                    <Button variant="ghost" size="icon" aria-label="Открыть результат" onClick={() => media && openExternalUrl(media)}>
                      <Share2 />
                    </Button>
                  </div>
                  <div className="flex gap-3 text-[11px] text-muted-foreground">
                    <span>♥ {item.likes_count || 0}</span>
                    <span>↗ {item.shares_count || 0}</span>
                    <span>↻ {item.remixes || 0}</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <div className="grid min-h-56 place-items-center rounded-2xl border border-dashed border-border text-center text-sm text-muted-foreground">
          {loading ? "Загружаем ленту…" : "В этой подборке пока нет работ"}
        </div>
      )}
    </div>
  );
}

export { FeedScreen };
