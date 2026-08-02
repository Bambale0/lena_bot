import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Film,
  Heart,
  ImageIcon,
  LoaderCircle,
  Maximize2,
  Play,
  RefreshCw,
  Repeat2,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { FeedItem, PreparedTrend, TrendItem } from "@/lib/types";
import { cn, firstMedia, safeExternalUrl } from "@/lib/utils";
import { notifyHaptic, readTelegramInitData } from "@/lib/telegram";

type FeedSource = "recent" | "top_day" | "top";
type WorkFilter = "all" | "image" | "video" | "mine";
type ContentMode = "works" | "trends";
type TrendKindFilter = "all" | "image" | "video";

interface FeedScreenProps {
  items: FeedItem[];
  source: FeedSource;
  loading: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  remixingId?: number | null;
  onSourceChange: (source: FeedSource) => void;
  onRefresh: () => void;
  onLoadMore?: () => void;
  onLike: (item: FeedItem) => void;
  onRemix: (item: FeedItem) => void;
}

interface MediaViewerState {
  urls: string[];
  index: number;
  title: string;
  meta: string;
  item: FeedItem;
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

const trendKindFilters = [
  { value: "all" as const, label: "Все", icon: Sparkles },
  { value: "image" as const, label: "Фото", icon: ImageIcon },
  { value: "video" as const, label: "Видео", icon: Film },
];

function itemLooksVideo(item: FeedItem): boolean {
  const media = firstMedia(item);
  return item.gen_type === "video" || mediaLooksVideo(media);
}

function mediaLooksVideo(url: string | null | undefined): boolean {
  return /\.(mp4|webm|mov|m4v)(\?|$)/i.test(String(url || ""));
}

function uniqueMediaUrls(item: FeedItem): string[] {
  const candidates = [
    ...(item.result_urls || []),
    item.result_url,
    ...(item.preview_urls || []),
    item.preview_url,
    firstMedia(item),
  ];
  const seen = new Set<string>();
  const urls: string[] = [];
  for (const candidate of candidates) {
    const url = safeExternalUrl(candidate);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    urls.push(url);
  }
  return urls;
}

function cardMediaShape(index: number, isVideo: boolean): string {
  if (isVideo) return index % 5 === 0 ? "aspect-[16/10]" : "aspect-[4/5]";
  if (index % 11 === 0) return "aspect-[3/4]";
  if (index % 7 === 0) return "aspect-square";
  if (index % 5 === 0) return "aspect-[2/3]";
  if (index % 3 === 0) return "aspect-[5/6]";
  return "aspect-[4/5]";
}

function trendCategoryKey(trend: TrendItem): string {
  return String(trend.category || trend.category_title || trend.kind || "other").trim().toLowerCase() || "other";
}

function trendCategoryTitle(trend: TrendItem): string {
  return String(trend.category_title || trend.category || (trend.kind === "video" ? "Видео" : "Фото"));
}

function authHeaders(): Record<string, string> {
  const initData = readTelegramInitData();
  return initData ? { "X-Telegram-Init-Data": initData } : {};
}

async function apiErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as Record<string, unknown>;
    const detail = payload.detail;
    if (typeof detail === "string" && detail) return detail;
    const error = payload.error;
    if (error && typeof error === "object" && typeof (error as Record<string, unknown>).message === "string") {
      return String((error as Record<string, unknown>).message);
    }
  } catch {
    // Fallback below.
  }
  return `Ошибка API ${response.status}`;
}

function settingString(settings: Record<string, unknown>, keys: string[], fallback: string): string {
  for (const key of keys) {
    const value = settings[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return fallback;
}

function settingNumber(settings: Record<string, unknown>, key: string, fallback: number): number {
  const value = Number(settings[key]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function FeedScreen({
  items,
  source,
  loading,
  loadingMore = false,
  hasMore = false,
  remixingId = null,
  onSourceChange,
  onRefresh,
  onLoadMore,
  onLike,
  onRemix,
}: FeedScreenProps) {
  const [contentMode, setContentMode] = useState<ContentMode>("works");
  const [workFilter, setWorkFilter] = useState<WorkFilter>("all");
  const [viewer, setViewer] = useState<MediaViewerState | null>(null);
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendKind, setTrendKind] = useState<TrendKindFilter>("all");
  const [trendCategory, setTrendCategory] = useState("all");
  const [preparingTrendId, setPreparingTrendId] = useState<number | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const visibleItems = useMemo(() => {
    return items.filter((item) => {
      if (workFilter === "mine") return Boolean(item.is_mine);
      if (workFilter === "video") return itemLooksVideo(item);
      if (workFilter === "image") return !itemLooksVideo(item);
      return true;
    });
  }, [items, workFilter]);

  const filteredTrendBase = useMemo(() => {
    return trends.filter((trend) => trendKind === "all" || trend.kind === trendKind);
  }, [trendKind, trends]);

  const trendCategories = useMemo(() => {
    const map = new Map<string, { key: string; title: string; emoji: string; count: number }>();
    for (const trend of filteredTrendBase) {
      const key = trendCategoryKey(trend);
      const current = map.get(key);
      if (current) {
        current.count += 1;
      } else {
        map.set(key, {
          key,
          title: trendCategoryTitle(trend),
          emoji: trend.category_emoji || (trend.kind === "video" ? "🎬" : "🖼️"),
          count: 1,
        });
      }
    }
    return [
      { key: "all", title: "Все", emoji: "✨", count: filteredTrendBase.length },
      ...Array.from(map.values()).sort((a, b) => b.count - a.count || a.title.localeCompare(b.title, "ru")),
    ];
  }, [filteredTrendBase]);

  const visibleTrends = useMemo(() => {
    if (trendCategory === "all") return filteredTrendBase;
    return filteredTrendBase.filter((trend) => trendCategoryKey(trend) === trendCategory);
  }, [filteredTrendBase, trendCategory]);

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || !onLoadMore || !hasMore || contentMode !== "works") return undefined;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting && !loading && !loadingMore) onLoadMore();
      },
      { root: null, rootMargin: "720px 0px", threshold: 0 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [contentMode, hasMore, loading, loadingMore, onLoadMore, visibleItems.length]);

  useEffect(() => {
    if (!viewer) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setViewer(null);
      if (event.key === "ArrowLeft") setViewer((current) => current ? { ...current, index: Math.max(0, current.index - 1) } : current);
      if (event.key === "ArrowRight") setViewer((current) => current ? { ...current, index: Math.min(current.urls.length - 1, current.index + 1) } : current);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [viewer]);

  const loadTrends = useCallback(async () => {
    if (trendsLoading) return;
    setTrendsLoading(true);
    try {
      const response = await fetch("/api/v1/trends?limit=96", { headers: authHeaders() });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      const payload = (await response.json()) as unknown;
      setTrends(Array.isArray(payload) ? payload as TrendItem[] : []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить тренды");
    } finally {
      setTrendsLoading(false);
    }
  }, [trendsLoading]);

  useEffect(() => {
    if (contentMode === "trends" && !trends.length && !trendsLoading) void loadTrends();
  }, [contentMode, loadTrends, trends.length, trendsLoading]);

  useEffect(() => {
    setTrendCategory("all");
  }, [trendKind]);

  const openViewer = useCallback((item: FeedItem, index = 0) => {
    const urls = uniqueMediaUrls(item);
    if (!urls.length) return;
    setViewer({
      urls,
      index: Math.min(index, urls.length - 1),
      title: item.prompt && !item.prompt_hidden ? item.prompt : item.model,
      meta: [item.author || "Автор", item.model, item.aspect_ratio || ""].filter(Boolean).join(" · "),
      item,
    });
  }, []);

  const repeatTrend = useCallback(async (trend: TrendItem) => {
    if (preparingTrendId) return;
    setPreparingTrendId(trend.id);
    try {
      const prepareResponse = await fetch(`/api/v1/trends/${trend.id}/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: "{}",
      });
      if (!prepareResponse.ok) throw new Error(await apiErrorMessage(prepareResponse));
      const prepared = (await prepareResponse.json()) as PreparedTrend;
      const settings = prepared.settings || {};
      const endpoint = prepared.kind === "video" ? "/api/v1/generate/video" : "/api/v1/generate/image";
      const body = prepared.kind === "video"
        ? {
            model: prepared.model,
            prompt: "Использовать скрытый трендовый промпт",
            prompt_id: prepared.prompt_id,
            mode: settingString(settings, ["scenario", "mode"], "text"),
            duration: settingNumber(settings, "duration", 5),
            aspect_ratio: settingString(settings, ["ratio", "aspect_ratio"], "16:9"),
            resolution: settingString(settings, ["resolution"], "720p"),
          }
        : {
            model: prepared.model,
            prompt: "Использовать скрытый трендовый промпт",
            prompt_id: prepared.prompt_id,
            aspect_ratio: settingString(settings, ["ratio", "aspect_ratio"], "1:1"),
            quality: settingString(settings, ["quality"], "basic"),
          };
      const generationResponse = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(body),
      });
      if (!generationResponse.ok) throw new Error(await apiErrorMessage(generationResponse));
      notifyHaptic("success");
      toast.success("Тренд запущен. Задача появится в истории.");
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось запустить тренд");
    } finally {
      setPreparingTrendId(null);
    }
  }, [preparingTrendId]);

  return (
    <div className="grid gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight sm:text-xl">Лента</h1>
            <Badge variant="outline">{contentMode === "works" ? `${visibleItems.length}/${items.length}` : visibleTrends.length}</Badge>
          </div>
          <details className="apix-help max-w-xl">
            <summary>Как работает лента</summary>
            <p className="pb-2">Работы открываются внутри Mini App. Вкладка трендов группирует сценарии по категориям, а повтор остаётся внутри карточек.</p>
          </details>
        </div>
        <Button
          variant="outline"
          size="icon"
          className="size-9 min-h-9"
          disabled={contentMode === "works" ? loading : trendsLoading}
          onClick={contentMode === "works" ? onRefresh : () => void loadTrends()}
          aria-label="Обновить ленту"
        >
          <RefreshCw className={(contentMode === "works" ? loading : trendsLoading) ? "animate-spin" : ""} />
        </Button>
      </div>

      <div className="sticky top-[48px] z-30 grid gap-1.5 rounded-xl border border-border/70 bg-background/88 p-1.5 backdrop-blur-xl">
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted/45 p-1">
          {[
            { value: "works" as const, label: "Работы" },
            { value: "trends" as const, label: "Тренды" },
          ].map((tab) => (
            <button
              key={tab.value}
              type="button"
              className={cn(
                "apix-focus-ring min-h-8 rounded-md px-3 text-xs font-bold transition",
                contentMode === tab.value ? "bg-background text-foreground shadow-sm" : "text-muted-foreground",
              )}
              onClick={() => setContentMode(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {contentMode === "works" ? (
          <>
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
          </>
        ) : (
          <>
            <div className="flex gap-1 overflow-x-auto pb-0.5">
              {trendKindFilters.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  className={cn(
                    "apix-focus-ring flex min-h-8 shrink-0 items-center gap-1.5 rounded-lg border px-3 text-xs font-semibold transition",
                    trendKind === value
                      ? "border-primary/40 bg-primary/15 text-primary"
                      : "border-border bg-card/55 text-muted-foreground",
                  )}
                  onClick={() => setTrendKind(value)}
                >
                  <Icon className="size-3.5" />
                  {label}
                </button>
              ))}
            </div>

            <div className="flex gap-1 overflow-x-auto pb-0.5">
              {trendCategories.map((category) => (
                <button
                  key={category.key}
                  type="button"
                  className={cn(
                    "apix-focus-ring flex min-h-8 shrink-0 items-center gap-1 rounded-lg border px-3 text-xs font-semibold transition",
                    trendCategory === category.key
                      ? "border-fuchsia-400/45 bg-fuchsia-400/15 text-fuchsia-700 dark:text-fuchsia-200"
                      : "border-border bg-card/55 text-muted-foreground",
                  )}
                  onClick={() => setTrendCategory(category.key)}
                >
                  <span>{category.emoji}</span>
                  <span>{category.title}</span>
                  <span className="text-[10px] opacity-70">{category.count}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {contentMode === "works" ? (
        visibleItems.length ? (
          <>
            <div className="apix-media-grid apix-feed-mosaic">
              {visibleItems.map((item, index) => {
                const mediaUrls = uniqueMediaUrls(item);
                const media = mediaUrls[0] || "";
                const isVideo = itemLooksVideo(item);
                const remixing = remixingId === item.id;
                const isFeatured = index % 9 === 0;
                return (
                  <Card key={item.id} className={cn("apix-feed-card overflow-hidden shadow-none", isFeatured && "apix-feed-card-featured")}>
                    <button
                      type="button"
                      className={cn("apix-focus-ring group relative block w-full overflow-hidden bg-muted", cardMediaShape(index, isVideo))}
                      onClick={() => openViewer(item)}
                    >
                      {media ? (
                        isVideo ? (
                          <video src={media} muted playsInline preload="metadata" className="size-full object-cover transition duration-500 group-active:scale-[1.02]" />
                        ) : (
                          <img src={media} alt="" loading="lazy" className="size-full object-cover transition duration-500 group-active:scale-[1.02]" />
                        )
                      ) : (
                        <div className="grid size-full place-items-center text-xs text-muted-foreground">Нет preview</div>
                      )}
                      <span className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(255,255,255,.22),transparent_26%),linear-gradient(to_top,rgba(0,0,0,.78),transparent_52%)]" />
                      {isVideo ? <span className="absolute inset-0 grid place-items-center"><span className="grid size-10 place-items-center rounded-full bg-black/55 text-white backdrop-blur"><Play className="ml-0.5 size-4" /></span></span> : null}
                      <span className="absolute right-2 top-2 grid size-7 place-items-center rounded-full bg-black/45 text-white opacity-85 backdrop-blur">
                        <Maximize2 className="size-3.5" />
                      </span>
                      <span className="absolute inset-x-0 bottom-0 grid gap-1 px-2 pb-2 pt-10 text-white">
                        <span className="flex items-center justify-between gap-1">
                          <span className="flex min-w-0 items-center gap-1.5">
                            <span className="grid size-5 shrink-0 place-items-center overflow-hidden rounded-full bg-white/20">
                              {item.author_photo_url ? <img src={item.author_photo_url} alt="" className="size-full object-cover" /> : <UserRound className="size-3" />}
                            </span>
                            <span className="truncate text-[9px] font-semibold">{item.author || "Автор"}</span>
                          </span>
                          <span className="flex shrink-0 items-center gap-1 text-[8px] opacity-85">
                            {isFeatured ? <span>выбор</span> : null}
                            {item.is_mine ? <span>моё</span> : null}
                            {item.aspect_ratio ? <span>{item.aspect_ratio}</span> : null}
                          </span>
                        </span>
                        {isFeatured && item.prompt && !item.prompt_hidden ? <span className="line-clamp-2 text-left text-[10px] font-semibold leading-tight opacity-95">{item.prompt}</span> : null}
                      </span>
                    </button>

                    <div className="grid gap-1.5 p-1.5">
                      {item.prompt && !item.prompt_hidden && !isFeatured ? (
                        <details className="apix-help border-0">
                          <summary className="py-1 text-[10px]">Промпт</summary>
                          <p className="line-clamp-6 pb-1 text-[10px]">{item.prompt}</p>
                        </details>
                      ) : null}

                      <div className="grid grid-cols-[1fr_34px_34px] gap-1">
                        <Button size="sm" className="min-h-8 px-2 text-[10px]" disabled={remixing} onClick={() => onRemix(item)}>
                          <Repeat2 className={cn("size-3.5", remixing && "animate-spin")} /> {remixing ? "Запуск" : "Повторить"}
                        </Button>
                        <Button variant="ghost" size="icon" className="size-8 min-h-8" aria-label="Лайк" onClick={() => onLike(item)}>
                          <Heart className="size-3.5" />
                        </Button>
                        <Button variant="ghost" size="icon" className="size-8 min-h-8" aria-label="Открыть внутри приложения" onClick={() => openViewer(item)}>
                          <Maximize2 className="size-3.5" />
                        </Button>
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

            <div ref={sentinelRef} className="grid min-h-16 place-items-center pb-2 text-xs text-muted-foreground">
              {loadingMore ? (
                <span className="inline-flex items-center gap-2"><LoaderCircle className="size-4 animate-spin" /> Подгружаем ещё…</span>
              ) : hasMore && onLoadMore ? (
                <Button variant="ghost" size="sm" onClick={onLoadMore}>Загрузить ещё</Button>
              ) : (
                <span>Это всё по текущей подборке</span>
              )}
            </div>
          </>
        ) : (
          <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-border text-center text-xs text-muted-foreground">
            {loading ? "Загружаем работы…" : "По этому фильтру работ пока нет"}
          </div>
        )
      ) : (
        <TrendCategorySurface
          trends={visibleTrends}
          loading={trendsLoading}
          preparingTrendId={preparingTrendId}
          onRepeat={(trend) => void repeatTrend(trend)}
        />
      )}

      <MediaViewer viewer={viewer} onClose={() => setViewer(null)} onChangeIndex={(index) => setViewer((current) => current ? { ...current, index } : current)} onRemix={(item) => onRemix(item)} remixingId={remixingId} />
    </div>
  );
}

function TrendCategorySurface({
  trends,
  loading,
  preparingTrendId,
  onRepeat,
}: {
  trends: TrendItem[];
  loading: boolean;
  preparingTrendId: number | null;
  onRepeat: (trend: TrendItem) => void;
}) {
  if (!trends.length) {
    return (
      <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-border text-center text-xs text-muted-foreground">
        {loading ? "Загружаем тренды…" : "В этой категории пока нет трендов"}
      </div>
    );
  }

  return (
    <div className="apix-media-grid apix-trend-category-grid">
      {trends.map((trend, index) => {
        const media = safeExternalUrl(trend.preview_url);
        const isVideo = trend.kind === "video";
        return (
          <Card key={trend.id} className={cn("apix-feed-card overflow-hidden shadow-none", index % 6 === 0 && "apix-feed-card-featured")}>
            <div className={cn("relative overflow-hidden bg-muted", cardMediaShape(index, isVideo))}>
              {media ? (
                isVideo ? (
                  <video src={media} muted playsInline loop preload="metadata" className="size-full object-cover" />
                ) : (
                  <img src={media} alt="" loading="lazy" className="size-full object-cover" />
                )
              ) : (
                <div className="grid size-full place-items-center text-muted-foreground">{isVideo ? <Film /> : <ImageIcon />}</div>
              )}
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(255,255,255,.22),transparent_30%),linear-gradient(to_top,rgba(0,0,0,.82),transparent_60%)]" />
              {isVideo ? <span className="absolute inset-0 grid place-items-center"><span className="grid size-10 place-items-center rounded-full bg-black/55 text-white"><Play className="ml-0.5 size-4" /></span></span> : null}
              <div className="absolute inset-x-0 bottom-0 px-2 pb-2 pt-10 text-white">
                <div className="mb-1 flex items-center gap-1 text-[8px] opacity-85">
                  <span>{trend.category_emoji || (isVideo ? "🎬" : "🖼️")}</span>
                  <span className="truncate">{trend.category_title || trend.category || trend.kind}</span>
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
              <Button className="min-h-8 px-2 text-[10px]" disabled={preparingTrendId === trend.id} onClick={() => onRepeat(trend)}>
                {preparingTrendId === trend.id ? (
                  <span className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                ) : (
                  <Repeat2 className="size-3.5" />
                )}
                Повторить тренд
              </Button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}

function MediaViewer({
  viewer,
  onClose,
  onChangeIndex,
  onRemix,
  remixingId,
}: {
  viewer: MediaViewerState | null;
  onClose: () => void;
  onChangeIndex: (index: number) => void;
  onRemix: (item: FeedItem) => void;
  remixingId: number | null;
}) {
  if (!viewer) return null;
  const url = viewer.urls[viewer.index] || "";
  const isVideo = itemLooksVideo(viewer.item) || mediaLooksVideo(url);
  const canPrev = viewer.index > 0;
  const canNext = viewer.index < viewer.urls.length - 1;
  const remixing = remixingId === viewer.item.id;

  return (
    <div className="apix-media-viewer fixed inset-0 z-[80] grid bg-black/92 text-white backdrop-blur-xl" role="dialog" aria-modal="true">
      <button type="button" className="absolute inset-0 cursor-zoom-out" aria-label="Закрыть просмотр" onClick={onClose} />
      <div className="relative z-10 grid min-h-0 grid-rows-[auto_1fr_auto] p-2 pt-[max(8px,env(safe-area-inset-top))]">
        <div className="flex items-center justify-between gap-2 rounded-2xl bg-white/8 px-2 py-1.5 backdrop-blur">
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold">{viewer.title || "Работа"}</p>
            <p className="truncate text-[10px] text-white/65">{viewer.meta}</p>
          </div>
          <Button variant="ghost" size="icon" className="size-9 min-h-9 text-white hover:bg-white/10" onClick={onClose} aria-label="Закрыть">
            <X className="size-5" />
          </Button>
        </div>

        <div className="relative grid min-h-0 place-items-center py-2">
          {canPrev ? (
            <Button variant="ghost" size="icon" className="absolute left-1 z-20 size-10 rounded-full bg-black/35 text-white hover:bg-black/55" onClick={() => onChangeIndex(viewer.index - 1)} aria-label="Предыдущее фото">
              <ChevronLeft />
            </Button>
          ) : null}
          {isVideo ? (
            <video src={url} controls autoPlay playsInline className="max-h-[calc(100dvh-132px-env(safe-area-inset-top)-env(safe-area-inset-bottom))] max-w-full rounded-2xl object-contain shadow-2xl" />
          ) : (
            <img src={url} alt="" className="max-h-[calc(100dvh-132px-env(safe-area-inset-top)-env(safe-area-inset-bottom))] max-w-full rounded-2xl object-contain shadow-2xl" />
          )}
          {canNext ? (
            <Button variant="ghost" size="icon" className="absolute right-1 z-20 size-10 rounded-full bg-black/35 text-white hover:bg-black/55" onClick={() => onChangeIndex(viewer.index + 1)} aria-label="Следующее фото">
              <ChevronRight />
            </Button>
          ) : null}
        </div>

        <div className="grid gap-1.5 pb-[max(8px,env(safe-area-inset-bottom))]">
          {viewer.urls.length > 1 ? (
            <div className="flex justify-center gap-1">
              {viewer.urls.map((item, index) => (
                <button
                  key={item}
                  type="button"
                  className={cn("size-1.5 rounded-full transition", index === viewer.index ? "bg-white" : "bg-white/35")}
                  onClick={() => onChangeIndex(index)}
                  aria-label={`Открыть вариант ${index + 1}`}
                />
              ))}
            </div>
          ) : null}
          <Button className="min-h-10 rounded-xl" disabled={remixing} onClick={() => onRemix(viewer.item)}>
            <Repeat2 className={cn("size-4", remixing && "animate-spin")} /> {remixing ? "Запуск повтора" : "Повторить эту работу"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export { FeedScreen };
