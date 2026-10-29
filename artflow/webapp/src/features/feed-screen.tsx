import { useCallback, useEffect, useMemo, useRef, useState, type Ref } from "react";
import { createPortal } from "react-dom";
import {
  ChevronLeft,
  ChevronRight,
  Film,
  Heart,
  ImageIcon,
  Images,
  LoaderCircle,
  Maximize2,
  Play,
  RefreshCw,
  Repeat2,
  Share2,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { RepeatCount } from "@/components/repeat-count";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { openTrendRunner } from "@/features/trend-runner";
import type { FeedItem, TrendItem } from "@/lib/types";
import { notifyHaptic, readTelegramInitData } from "@/lib/telegram";
import { cn, safeExternalUrl } from "@/lib/utils";

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
  onRemix: (item: FeedItem, sourceMediaUrl?: string) => void;
}

interface MediaViewerState {
  urls: string[];
  index: number;
  title: string;
  meta: string;
  item: FeedItem;
}

const WORK_RENDER_BATCH = 30;
const TREND_RENDER_BATCH = 24;
const MY_FEED_FETCH_LIMIT = 500;

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
  const media = uniqueMediaUrls(item)[0];
  return item.gen_type === "video" || mediaLooksVideo(media);
}

function mediaLooksVideo(url: string | null | undefined): boolean {
  return /\.(mp4|webm|mov|m4v)(\?|$)/i.test(String(url || ""));
}

function uniqueSafeUrls(candidates: (string | null | undefined)[]): string[] {
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

function uniqueMediaUrls(item: FeedItem): string[] {
  const results = uniqueSafeUrls(item.result_urls || []);
  if (results.length) return results;
  const result = safeExternalUrl(item.result_url);
  if (result) return [result];
  // Public and legacy responses may expose output-bound media only through preview URLs.
  const previews = uniqueSafeUrls(item.preview_urls || []);
  return previews.length ? previews : uniqueSafeUrls([item.preview_url]);
}

function cardPreview(item: FeedItem): { url: string; poster: string; video: boolean } {
  const previews = uniqueSafeUrls([item.preview_url, ...(item.preview_urls || [])]);
  const original = uniqueMediaUrls(item)[0] || "";
  // A legacy preview can point at a different output; match the viewer's first result.
  if (!itemLooksVideo(item)) return { url: original, poster: "", video: false };
  const poster = previews.find((url) => url !== original && !mediaLooksVideo(url)) || "";
  return { url: original, poster, video: true };
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
  const [myItems, setMyItems] = useState<FeedItem[]>([]);
  const [myLoading, setMyLoading] = useState(false);
  const [visibleWorkCount, setVisibleWorkCount] = useState(WORK_RENDER_BATCH);
  const [viewer, setViewer] = useState<MediaViewerState | null>(null);
  const [viewerFailedUrl, setViewerFailedUrl] = useState<string | null>(null);
  const [trends, setTrends] = useState<TrendItem[]>([]);
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [trendKind, setTrendKind] = useState<TrendKindFilter>("all");
  const [trendCategory, setTrendCategory] = useState("all");
  const [visibleTrendCount, setVisibleTrendCount] = useState(TREND_RENDER_BATCH);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const viewerDialogRef = useRef<HTMLDivElement | null>(null);
  const viewerReturnFocus = useRef<HTMLElement | null>(null);
  const viewerOpen = viewer !== null;

  const loadMyFeed = useCallback(async () => {
    setMyLoading(true);
    try {
      const response = await fetch(`/api/v1/me/feed?limit=${MY_FEED_FETCH_LIMIT}`, { headers: authHeaders() });
      if (!response.ok) throw new Error(await apiErrorMessage(response));
      const payload = (await response.json()) as unknown;
      setMyItems(Array.isArray(payload) ? payload as FeedItem[] : []);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить мои работы");
    } finally {
      setMyLoading(false);
    }
  }, []);

  useEffect(() => {
    if (workFilter === "mine") void loadMyFeed();
  }, [loadMyFeed, workFilter]);

  const visibleItems = useMemo(() => {
    if (workFilter === "mine") return myItems;
    return items.filter((item) => {
      if (workFilter === "video") return itemLooksVideo(item);
      if (workFilter === "image") return !itemLooksVideo(item);
      return true;
    });
  }, [items, myItems, workFilter]);

  const renderedItems = useMemo(() => {
    if (workFilter === "mine") return visibleItems;
    return visibleItems.slice(0, visibleWorkCount);
  }, [visibleItems, visibleWorkCount, workFilter]);

  const canRevealMoreWorks = workFilter !== "mine" && renderedItems.length < visibleItems.length;
  const worksLoading = workFilter === "mine" ? myLoading : loading;

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

  const renderedTrends = useMemo(() => {
    return visibleTrends.slice(0, visibleTrendCount);
  }, [visibleTrendCount, visibleTrends]);

  const canRevealMoreTrends = renderedTrends.length < visibleTrends.length;

  useEffect(() => {
    setVisibleWorkCount(WORK_RENDER_BATCH);
  }, [source, workFilter]);

  useEffect(() => {
    if (
      contentMode !== "works" ||
      workFilter === "all" ||
      workFilter === "mine" ||
      loading ||
      loadingMore ||
      visibleItems.length > 0 ||
      !hasMore ||
      !onLoadMore
    ) {
      return;
    }
    onLoadMore();
  }, [contentMode, hasMore, loading, loadingMore, onLoadMore, visibleItems.length, workFilter]);

  useEffect(() => {
    setVisibleTrendCount(TREND_RENDER_BATCH);
  }, [trendCategory, trendKind]);

  useEffect(() => {
    const target = sentinelRef.current;
    if (!target || contentMode !== "works") return undefined;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting || worksLoading || loadingMore) return;
        if (canRevealMoreWorks) {
          setVisibleWorkCount((current) => Math.min(current + WORK_RENDER_BATCH, visibleItems.length));
          return;
        }
        if (workFilter !== "mine" && hasMore && onLoadMore) onLoadMore();
      },
      { root: null, rootMargin: "640px 0px", threshold: 0 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [canRevealMoreWorks, contentMode, hasMore, loadingMore, onLoadMore, visibleItems.length, workFilter, worksLoading]);

  useEffect(() => {
    const dialog = viewerDialogRef.current;
    if (!viewerOpen || !dialog) return undefined;
    const returnTarget = viewerReturnFocus.current;
    let lastFocus: HTMLElement | null = null;
    let suspended = false;
    const focusableSelector = 'button:not([disabled]),a[href],video[controls],[tabindex]:not([tabindex="-1"])';
    const isVisible = (node: HTMLElement) => !node.closest('[hidden],[inert],[aria-hidden="true"]') && node.getClientRects().length > 0;
    const anotherDialogOpen = () => Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"][aria-modal="true"],[role="alertdialog"][aria-modal="true"]')).some((node) => node !== dialog && isVisible(node));
    const focusable = () => Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector)).filter((node) => node.getAttribute("tabindex") !== "-1" && isVisible(node));
    const focusViewer = () => {
      if (anotherDialogOpen()) return;
      const target = lastFocus?.isConnected && dialog.contains(lastFocus) ? lastFocus : dialog.querySelector<HTMLElement>('[data-feed-viewer-close]') || dialog;
      target.focus({ preventScroll: true });
    };
    const syncLayer = () => {
      const next = anotherDialogOpen();
      if (next === suspended) return;
      suspended = next;
      // The repeat/payment Sheet owns focus and Telegram Back while it is open.
      dialog.inert = next;
      if (next) dialog.setAttribute("aria-hidden", "true");
      else {
        dialog.removeAttribute("aria-hidden");
        focusViewer();
      }
    };
    const onFocusIn = (event: FocusEvent) => {
      if (event.target instanceof HTMLElement && dialog.contains(event.target)) lastFocus = event.target;
      else if (!anotherDialogOpen()) focusViewer();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || anotherDialogOpen()) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setViewer(null);
        return;
      }
      if (event.key === "Tab") {
        const controls = focusable();
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first || !last) {
          event.preventDefault();
          dialog.focus();
        } else if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      if (event.target instanceof HTMLVideoElement) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        setViewerFailedUrl(null);
        setViewer((current) => current ? { ...current, index: Math.max(0, Math.min(current.urls.length - 1, current.index + (event.key === "ArrowLeft" ? -1 : 1))) } : current);
      }
    };
    const observer = new MutationObserver(syncLayer);
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "aria-hidden", "inert"] });
    const frame = window.requestAnimationFrame(() => { syncLayer(); focusViewer(); });
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
      if (returnTarget?.isConnected && !anotherDialogOpen()) returnTarget.focus({ preventScroll: true });
    };
  }, [viewerOpen]);

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

  const openViewer = useCallback((item: FeedItem, index = 0, trigger?: HTMLElement) => {
    const urls = uniqueMediaUrls(item);
    if (!urls.length) return;
    viewerReturnFocus.current = trigger || (typeof HTMLElement !== "undefined" && document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setViewerFailedUrl(null);
    setViewer({
      urls,
      index: Math.min(index, urls.length - 1),
      title: item.prompt && !item.prompt_hidden ? item.prompt : item.model,
      meta: [item.author || "Автор", item.model, item.aspect_ratio || ""].filter(Boolean).join(" · "),
      item,
    });
  }, []);

  const repeatTrend = useCallback((trend: TrendItem) => {
    notifyHaptic("success");
    openTrendRunner(trend);
  }, []);

  return (
    <div className="apix-feed-gallery">
      <header className="apix-feed-toolbar feed-gallery-toolbar">
        <div className="feed-gallery-heading">
          <h1>Лента</h1>
          <div className="feed-gallery-modes" role="group" aria-label="Содержимое ленты">
            {[
              { value: "works" as const, label: "Работы" },
              { value: "trends" as const, label: "Тренды" },
            ].map((tab) => (
              <button key={tab.value} type="button" className="apix-focus-ring" aria-pressed={contentMode === tab.value} onClick={() => setContentMode(tab.value)}>
                {tab.label}
              </button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="feed-gallery-refresh"
            disabled={contentMode === "works" ? worksLoading : trendsLoading}
            onClick={contentMode === "works" ? (workFilter === "mine" ? () => void loadMyFeed() : onRefresh) : () => void loadTrends()}
            aria-label="Обновить ленту"
          >
            <RefreshCw className={cn((contentMode === "works" ? worksLoading : trendsLoading) && "animate-spin")} />
          </Button>
        </div>

        <div className="feed-gallery-controls">
          {contentMode === "works" ? (
            <>
              <div className="feed-gallery-filter-group" role="group" aria-label="Тип работ">
                {workFilters.map((filter) => (
                  <button key={filter.value} type="button" className="apix-focus-ring" aria-pressed={workFilter === filter.value} onClick={() => setWorkFilter(filter.value)}>
                    {filter.label}
                  </button>
                ))}
              </div>
              <div className="feed-gallery-filter-group feed-gallery-sort" role="group" aria-label="Сортировка работ">
                {sourceFilters.map((filter) => (
                  <button key={filter.value} type="button" className="apix-focus-ring" aria-pressed={source === filter.value} onClick={() => onSourceChange(filter.value)}>
                    {filter.label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div className="feed-gallery-filter-group" role="group" aria-label="Тип трендов">
                {trendKindFilters.map(({ value, label, icon: Icon }) => (
                  <button key={value} type="button" className="apix-focus-ring" aria-pressed={trendKind === value} onClick={() => setTrendKind(value)}>
                    <Icon aria-hidden="true" />{label}
                  </button>
                ))}
              </div>
              <div className="feed-gallery-filter-group feed-gallery-categories" role="group" aria-label="Категория трендов">
                {trendCategories.map((category) => (
                  <button key={category.key} type="button" className="apix-focus-ring" aria-pressed={trendCategory === category.key} onClick={() => setTrendCategory(category.key)}>
                    <span aria-hidden="true">{category.emoji}</span><span>{category.title}</span><span className="feed-filter-count">{category.count}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </header>

      {contentMode === "works" ? (
        visibleItems.length ? (
          <>
            <div className="apix-media-grid apix-feed-mosaic feed-gallery-grid" aria-busy={worksLoading}>
              {renderedItems.map((item, index) => {
                const mediaUrls = uniqueMediaUrls(item);
                const preview = cardPreview(item);
                const isVideo = itemLooksVideo(item);
                const remixing = remixingId === item.id;
                const author = item.author || "Автор";
                const authorPhoto = safeExternalUrl(item.author_photo_url);
                return (
                  <Card key={item.id} className="apix-feed-card feed-gallery-card" role="article" aria-label={`Работа автора ${author}`}>
                    <div className="apix-feed-media feed-card-media">
                      <FeedPreview key={`${preview.url}:${preview.poster}`} url={preview.url} poster={preview.poster} video={preview.video} eager={index < 4} />
                      <button
                        type="button"
                        className="apix-focus-ring feed-card-open"
                        aria-label="Открыть внутри приложения"
                        disabled={!mediaUrls.length}
                        onClick={(event) => openViewer(item, 0, event.currentTarget)}
                      />
                      <div className="feed-card-badges" aria-hidden="true">
                        {isVideo ? <span><Film />Видео</span> : mediaUrls.length > 1 ? <span><Images />{mediaUrls.length} фото</span> : null}
                      </div>
                      {isVideo && preview.url ? <span className="feed-card-play" aria-hidden="true"><Play /></span> : null}
                      <div className="feed-card-tools">
                        <button type="button" className="apix-focus-ring feed-card-icon-button" aria-label="Лайк" onClick={(event) => { event.stopPropagation(); onLike(item); }}>
                          <Heart aria-hidden="true" />
                        </button>
                        <button type="button" className="apix-focus-ring feed-card-icon-button" aria-label="Открыть внутри приложения" disabled={!mediaUrls.length} onClick={(event) => { event.stopPropagation(); openViewer(item, 0, event.currentTarget); }}>
                          <Maximize2 aria-hidden="true" />
                        </button>
                      </div>
                    </div>

                    <div className="feed-card-caption">
                      <button type="button" className="apix-focus-ring feed-card-author" aria-label={`Открыть работу автора ${author}`} disabled={!mediaUrls.length} onClick={(event) => openViewer(item, 0, event.currentTarget)}>
                        <span className="feed-card-avatar" aria-hidden="true">
                          <UserRound />
                          {authorPhoto ? <img src={authorPhoto} alt="" loading="lazy" decoding="async" onError={(event) => { event.currentTarget.hidden = true; }} /> : null}
                        </span>
                        <span className="feed-card-author-name">{author}</span>
                        {item.is_mine ? <span className="feed-card-owned">Моё</span> : null}
                      </button>
                      <div className="feed-card-details">
                        <span className="feed-card-model" title={item.model}>{item.model}</span>
                        {item.aspect_ratio ? <span className="feed-card-ratio">{item.aspect_ratio}</span> : null}
                      </div>
                      <div className="feed-card-stats">
                        {typeof item.likes_count === "number" && Number.isInteger(item.likes_count) && item.likes_count >= 0 ? <span className="feed-card-stat" aria-label={`Лайков: ${item.likes_count}`}><Heart aria-hidden="true" /><span>{item.likes_count}</span></span> : null}
                        {typeof item.shares_count === "number" && Number.isInteger(item.shares_count) && item.shares_count >= 0 ? <span className="feed-card-stat" aria-label={`Поделились: ${item.shares_count}`}><Share2 aria-hidden="true" /><span>{item.shares_count}</span></span> : null}
                        <RepeatCount count={item.remixes} className="feed-card-repeat-count" />
                      </div>
                      <button type="button" className="apix-focus-ring feed-card-repeat" disabled={remixing} onClick={(event) => { event.stopPropagation(); onRemix(item, mediaUrls[0]); }}>
                        <Repeat2 aria-hidden="true" className={cn(remixing && "animate-spin")} /><span>{remixing ? "Запуск" : "Повторить"}</span>
                      </button>
                    </div>
                  </Card>
                );
              })}
            </div>

            <div ref={sentinelRef} className="feed-gallery-more" role="status">
              {worksLoading || (workFilter !== "mine" && loadingMore) ? (
                <span><LoaderCircle className="animate-spin" aria-hidden="true" />Подгружаем ещё…</span>
              ) : canRevealMoreWorks ? (
                <Button variant="ghost" onClick={() => setVisibleWorkCount((current) => Math.min(current + WORK_RENDER_BATCH, visibleItems.length))}>Показать ещё</Button>
              ) : workFilter !== "mine" && hasMore && onLoadMore ? (
                <Button variant="ghost" onClick={onLoadMore}>Загрузить ещё</Button>
              ) : (
                <span>Это всё по текущей подборке</span>
              )}
            </div>
          </>
        ) : (
          <div className="feed-gallery-empty" role="status">
            {worksLoading || (workFilter !== "mine" && loadingMore) ? <><LoaderCircle className="animate-spin" aria-hidden="true" /><p>Ищем работы по фильтру…</p></> : <><Images aria-hidden="true" /><h2>Работ пока нет</h2><p>Выберите другой фильтр или обновите ленту.</p></>}
          </div>
        )
      ) : (
        <TrendCategorySurface trends={renderedTrends} loading={trendsLoading} canRevealMore={canRevealMoreTrends} onRevealMore={() => setVisibleTrendCount((current) => Math.min(current + TREND_RENDER_BATCH, visibleTrends.length))} onRepeat={(trend) => repeatTrend(trend)} />
      )}

      {/* Escape the feed containing block; keep the gallery below repeat/payment sheets. */}
      {viewer ? createPortal(
        <MediaViewer
          viewer={viewer}
          dialogRef={viewerDialogRef}
          failedUrl={viewerFailedUrl}
          onMediaError={setViewerFailedUrl}
          onClose={() => setViewer(null)}
          onChangeIndex={(index) => { setViewerFailedUrl(null); setViewer((current) => current ? { ...current, index } : current); }}
          onRemix={onRemix}
          remixingId={remixingId}
        />,
        document.body,
      ) : null}
    </div>
  );
}

function FeedPreview({ url, poster = "", video, eager = false }: { url: string; poster?: string; video: boolean; eager?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (!url || failed) {
    return <div className="feed-media-fallback">
      {video ? <Film aria-hidden="true" /> : <ImageIcon aria-hidden="true" />}
      <span>{failed ? "Превью недоступно" : "Нет превью"}</span>
    </div>;
  }
  return video ? (
    <video src={url} poster={poster || undefined} muted playsInline preload="metadata" onError={() => setFailed(true)} />
  ) : (
    <img src={url} alt="" loading={eager ? "eager" : "lazy"} fetchPriority={eager ? "high" : "auto"} decoding="async" onError={() => setFailed(true)} />
  );
}

function TrendCategorySurface({
  trends,
  loading,
  canRevealMore,
  onRevealMore,
  onRepeat,
}: {
  trends: TrendItem[];
  loading: boolean;
  canRevealMore: boolean;
  onRevealMore: () => void;
  onRepeat: (trend: TrendItem) => void;
}) {
  if (!trends.length) {
    return <div className="feed-gallery-empty" role="status">
      {loading ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}
      <p>{loading ? "Загружаем тренды…" : "В этой категории пока нет трендов"}</p>
    </div>;
  }

  return (
    <div className="feed-trend-surface">
      <div className="apix-media-grid apix-trend-category-grid feed-gallery-grid" aria-busy={loading}>
        {trends.map((trend, index) => {
          const media = safeExternalUrl(trend.preview_url);
          const isVideo = trend.kind === "video";
          return (
            <Card key={trend.id} className="apix-feed-card feed-gallery-card" role="article" aria-label={trend.title}>
              <div className="apix-feed-media feed-card-media">
                <FeedPreview key={media} url={media} video={isVideo} eager={index < 4} />
                <div className="feed-card-badges" aria-hidden="true"><span>{isVideo ? <Film /> : <ImageIcon />}{isVideo ? "Видео" : "Фото"}</span></div>
              </div>
              <div className="feed-card-caption feed-trend-caption">
                <p className="feed-trend-category">{trend.category_emoji ? <span aria-hidden="true">{trend.category_emoji}</span> : null}{trend.category_title || (isVideo ? "Видео" : "Фото")}</p>
                <h2>{trend.title}</h2>
                {trend.description ? <details className="feed-trend-description"><summary>Описание</summary><p>{trend.description}</p></details> : null}
                <div className="feed-card-stats">
                  {typeof trend.uses_count === "number" && Number.isInteger(trend.uses_count) && trend.uses_count >= 0 ? <span className="feed-card-stat feed-card-repeat-count whitespace-nowrap"><Repeat2 aria-hidden="true" /><span>Использований: {trend.uses_count}</span></span> : null}
                </div>
                <button type="button" className="apix-focus-ring feed-card-repeat" onClick={() => onRepeat(trend)}><Repeat2 aria-hidden="true" /><span>Повторить тренд</span></button>
              </div>
            </Card>
          );
        })}
      </div>
      {canRevealMore ? <div className="feed-gallery-more"><Button variant="ghost" onClick={onRevealMore}>Показать ещё тренды</Button></div> : null}
    </div>
  );
}

function MediaViewer({
  viewer,
  dialogRef,
  failedUrl = null,
  onMediaError,
  onClose,
  onChangeIndex,
  onRemix,
  remixingId,
}: {
  viewer: MediaViewerState | null;
  dialogRef?: Ref<HTMLDivElement>;
  failedUrl?: string | null;
  onMediaError?: (url: string) => void;
  onClose: () => void;
  onChangeIndex: (index: number) => void;
  onRemix: (item: FeedItem, sourceMediaUrl?: string) => void;
  remixingId: number | null;
}) {
  if (!viewer) return null;
  const url = viewer.urls[viewer.index] || "";
  const isVideo = itemLooksVideo(viewer.item) || mediaLooksVideo(url);
  const canPrev = viewer.index > 0;
  const canNext = viewer.index < viewer.urls.length - 1;
  const remixing = remixingId === viewer.item.id;

  return (
    <div ref={dialogRef} className="apix-media-viewer feed-gallery-viewer" role="dialog" aria-modal="true" aria-label="Просмотр работы" tabIndex={-1}>
      <button type="button" className="feed-viewer-backdrop" tabIndex={-1} aria-label="Закрыть просмотр" onClick={onClose} />
      <div className="feed-viewer-content">
        <header className="feed-viewer-header">
          <div className="feed-viewer-heading">
            <h2>{viewer.title || "Работа"}</h2>
            <p>{viewer.meta}</p>
            <RepeatCount count={viewer.item.remixes} className="feed-viewer-repeats" />
          </div>
          <Button variant="ghost" size="icon" className="feed-viewer-close" data-feed-viewer-close onClick={onClose} aria-label="Закрыть"><X aria-hidden="true" /></Button>
        </header>

        <div className="feed-viewer-stage">
          {canPrev ? <Button variant="ghost" size="icon" className="feed-viewer-step feed-viewer-prev" onClick={() => onChangeIndex(viewer.index - 1)} aria-label="Предыдущее фото"><ChevronLeft /></Button> : null}
          {!url || failedUrl === url ? (
            <div className="feed-media-fallback feed-viewer-fallback" role="status">
              {isVideo ? <Film aria-hidden="true" /> : <ImageIcon aria-hidden="true" />}
              <p>Не удалось загрузить {isVideo ? "видео" : "фото"}</p><span>Закройте просмотр и попробуйте снова.</span>
            </div>
          ) : isVideo ? (
            <video key={url} src={url} controls autoPlay playsInline className="feed-viewer-result" onError={() => onMediaError?.(url)} />
          ) : (
            <img key={url} src={url} alt={viewer.title || "Работа"} decoding="async" className="feed-viewer-result" onError={() => onMediaError?.(url)} />
          )}
          {canNext ? <Button variant="ghost" size="icon" className="feed-viewer-step feed-viewer-next" onClick={() => onChangeIndex(viewer.index + 1)} aria-label="Следующее фото"><ChevronRight /></Button> : null}
        </div>

        <footer className="feed-viewer-footer">
          {viewer.urls.length > 1 ? (
            <div className="feed-viewer-pages" role="group" aria-label="Варианты работы">
              {viewer.urls.map((item, index) => <button key={item} type="button" className="apix-focus-ring" aria-pressed={index === viewer.index} aria-label={`Открыть вариант ${index + 1}`} onClick={() => onChangeIndex(index)}><span aria-hidden="true">{index + 1}</span></button>)}
            </div>
          ) : null}
          <Button className="feed-viewer-repeat" disabled={remixing} onClick={() => onRemix(viewer.item, url)}>
            <Repeat2 aria-hidden="true" className={cn(remixing && "animate-spin")} />{remixing ? "Запуск повтора" : "Повторить эту работу"}
          </Button>
        </footer>
      </div>
    </div>
  );
}

export { FeedScreen };
