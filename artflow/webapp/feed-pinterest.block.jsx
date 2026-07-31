// ── Feed screen ───────────────────────────────────────────────────────────────

const FEED_SORTS = [
  { key: "recommended", label: "Для тебя" },
  { key: "new", label: "Новые" },
  { key: "popular", label: "Популярные" },
  { key: "repeated", label: "Повторы" },
];

const FEED_TYPES = [
  { key: "all", label: "Все" },
  { key: "image", label: "Фото" },
  { key: "video", label: "Видео" },
];

function feedCreatedAt(item) {
  const value = Date.parse(item?.created_at || "");
  return Number.isFinite(value) ? value : 0;
}

function feedTileUrls(item) {
  const urls = Array.isArray(item?.preview_urls) ? item.preview_urls.filter(Boolean) : [];
  if (!urls.length && item?.preview_url) urls.push(item.preview_url);
  return urls;
}

function feedPreviewIsVideo(item, url = "") {
  return item?.gen_type === "video" || /\.(mp4|webm|mov)(?:$|\?)/i.test(url);
}

function feedItemIsVideo(item) {
  return feedPreviewIsVideo(item, feedTileUrls(item)[0] || "");
}

function feedPopularity(item) {
  const likes = Number(item?.likes_count || 0);
  const shares = Number(item?.shares_count || 0);
  const remixes = Number(item?.remixes || 0);
  return likes + shares * 3 + remixes * 4;
}

function FeedMediaThumb({ item, previewUrl, idx, onOpen, onError }) {
  const isVideo = feedPreviewIsVideo(item, previewUrl);
  return (
    <button
      type="button"
      className={`feedMediaCell ${isVideo ? "feedVideoCell" : "feedImageCell"}`}
      onClick={() => onOpen?.(item, idx)}
      aria-label={isVideo ? "Открыть видео" : "Открыть изображение"}
    >
      {isVideo ? (
        <video
          src={previewUrl}
          className="feedCompactImg"
          muted
          playsInline
          preload="metadata"
          onError={onError}
        />
      ) : (
        <img
          src={previewUrl}
          className="feedCompactImg"
          alt=""
          loading="lazy"
          decoding="async"
          fetchPriority="low"
          onError={onError}
        />
      )}
      {isVideo && <span className="feedVideoPlay" aria-hidden="true">▶</span>}
    </button>
  );
}

function FeedViewer({ entry, onClose, onRemix, onNotice }) {
  const item = entry?.item;
  const previewUrls = item ? feedTileUrls(item) : [];
  const [index, setIndex] = useState(entry?.index || 0);
  const touchStartX = useRef(null);

  useEffect(() => {
    setIndex(entry?.index || 0);
  }, [entry?.item?.id, entry?.index]);

  useEffect(() => {
    if (!item) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event) {
      if (event.key === "Escape") onClose?.();
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
      if (event.key === "ArrowRight") setIndex((value) => Math.min(previewUrls.length - 1, value + 1));
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [item?.id, previewUrls.length, onClose]);

  if (!item || !previewUrls.length) return null;

  const safeIndex = Math.min(index, previewUrls.length - 1);
  const previewUrl = previewUrls[safeIndex] || "";
  const isVideo = feedPreviewIsVideo(item, previewUrl);
  const displayUrl = isVideo
    ? previewUrl
    : `/api/v1/feed/${item.id}/display.webp?index=${safeIndex}`;
  const canPrev = safeIndex > 0;
  const canNext = safeIndex < previewUrls.length - 1;
  const prompt = generationPromptHidden(item) ? "" : publicPromptText(item.prompt || "").trim();

  function handleTouchStart(event) {
    touchStartX.current = event.touches?.[0]?.clientX ?? null;
  }

  function handleTouchEnd(event) {
    const start = touchStartX.current;
    const end = event.changedTouches?.[0]?.clientX;
    touchStartX.current = null;
    if (start == null || end == null || Math.abs(end - start) < 48) return;
    if (end < start && canNext) setIndex((value) => value + 1);
    if (end > start && canPrev) setIndex((value) => value - 1);
  }

  async function copyLink() {
    try {
      const payload = await api(`/feed/${item.id}/link`);
      const copied = await copyText(payload.link || "");
      if (!copied) throw new Error("Не удалось скопировать ссылку");
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice?.({ type: "error", message: error.message || "Не удалось скопировать ссылку" });
    }
  }

  return (
    <div className="feedViewer" role="dialog" aria-modal="true" aria-label="Просмотр публикации" onClick={onClose}>
      <div className="feedViewerTop">
        <span>@{item.author || "anon"}</span>
        {previewUrls.length > 1 && <small>{safeIndex + 1} / {previewUrls.length}</small>}
        <button type="button" onClick={onClose} aria-label="Закрыть">×</button>
      </div>

      <div
        className="feedViewerStage"
        onClick={(event) => event.stopPropagation()}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {isVideo ? (
          <video src={displayUrl} controls autoPlay playsInline className="feedViewerMedia" />
        ) : (
          <img src={displayUrl} alt="" className="feedViewerMedia" decoding="async" />
        )}

        {canPrev && (
          <button className="feedViewerNav prev" type="button" onClick={() => setIndex((value) => value - 1)} aria-label="Предыдущее изображение">‹</button>
        )}
        {canNext && (
          <button className="feedViewerNav next" type="button" onClick={() => setIndex((value) => value + 1)} aria-label="Следующее изображение">›</button>
        )}
      </div>

      <div className="feedViewerBottom" onClick={(event) => event.stopPropagation()}>
        {prompt && <p>{prompt}</p>}
        <div>
          <button className="primary" type="button" onClick={() => { onClose?.(); onRemix?.(item); }}>↻ Повторить</button>
          <button type="button" onClick={copyLink}>↗ Поделиться</button>
        </div>
      </div>
    </div>
  );
}

function FeedCard({ item, idx, onOpen, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(Boolean(item.liked_by_me));
  const [likes, setLikes] = useState(Number(item.likes_count || 0));
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const shares = Number(item.shares_count || 0);
  const remixes = Number(item.remixes || 0);
  const previewUrls = feedTileUrls(item);
  const visibleUrls = previewUrls.filter((url) => !failedUrls.has(url)).slice(0, 4);
  const prompt = generationPromptHidden(item) ? "" : publicPromptText(item.prompt || "").trim();
  const caption = prompt.length > 82 ? `${prompt.slice(0, 79).trim()}…` : prompt;
  const isVideo = feedItemIsVideo(item);
  const hasStats = likes > 0 || remixes > 0 || shares > 0;

  useEffect(() => {
    setFailedUrls(new Set());
  }, [item.id]);

  async function handleLike() {
    if (liked || busy) return;
    setBusy(true);
    try {
      const response = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLikes(Number(response.likes_count ?? likes + 1));
      setLiked(true);
      tg()?.HapticFeedback?.impactOccurred("light");
    } catch (error) {
      onNotice?.({ type: "error", message: error.message || "Не удалось поставить лайк" });
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyLink() {
    try {
      const response = await api(`/feed/${item.id}/link`);
      const copied = await copyText(response.link || "");
      if (!copied) throw new Error("Не удалось скопировать ссылку");
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice?.({ type: "error", message: error.message || "Не удалось скопировать ссылку" });
    }
  }

  async function handleRemove() {
    if (!item.is_mine || removing) return;
    if (!window.confirm("Удалить эту публикацию из общей ленты?")) return;
    setRemoving(true);
    try {
      await api(`/feed/${item.id}/remove`, { method: "POST" });
      onRemoved?.(item.id);
    } catch (error) {
      onNotice?.({ type: "error", message: error.message || "Не удалось удалить публикацию" });
    } finally {
      setRemoving(false);
    }
  }

  function hideBrokenMedia(url) {
    setFailedUrls((current) => new Set([...current, url]));
  }

  if (!previewUrls.length || (!visibleUrls.length && failedUrls.size)) return null;

  return (
    <article className="feedCompactCard">
      <div className={`feedCompactMedia ${visibleUrls.length > 1 ? "multi" : "single"}`}>
        {visibleUrls.map((url, mediaIdx) => (
          <FeedMediaThumb
            key={`${url}-${mediaIdx}`}
            item={item}
            previewUrl={url}
            idx={mediaIdx}
            onOpen={onOpen}
            onError={() => hideBrokenMedia(url)}
          />
        ))}

        <div className="feedCompactTop">
          <span className="feedCompactAuthor">@{item.author || "anon"}</span>
          <span className="feedKindBadge">{isVideo ? "Видео" : "Фото"}</span>
        </div>

        {hasStats && (
          <div className="feedCompactStats" aria-label="Статистика публикации">
            {likes > 0 && <span>♥ {likes}</span>}
            {remixes > 0 && <span>↻ {remixes}</span>}
            {shares > 0 && <span>↗ {shares}</span>}
          </div>
        )}
        {item.is_mine && <span className="feedMineBadge">Твоя</span>}
        {previewUrls.length > 4 && <span className="feedMoreBadge">+{previewUrls.length - 4}</span>}
      </div>

      {caption && <p className="feedCompactCaption">{caption}</p>}

      <div className="feedCardActionRow" aria-label="Действия с публикацией">
        <button className="feedRepeatAction" type="button" onClick={() => onRemix?.(item)}>↻ <span>Повторить</span></button>
        <button className={`feedIconAction ${liked ? "liked" : ""}`} type="button" onClick={handleLike} disabled={busy || liked} aria-label="Нравится">{liked ? "♥" : "♡"}</button>
        <button className="feedIconAction" type="button" onClick={handleCopyLink} aria-label="Поделиться">↗</button>
        {item.is_mine && <button className="feedMoreAction" type="button" onClick={handleRemove} disabled={removing} aria-label="Удалить из ленты">⋯</button>}
      </div>
    </article>
  );
}

function Feed({ feed, feedLoading, prompts, setScreen, onRemix, onNotice, onRemoved, scope = "all", onPromptUse, onOpenPrompts }) {
  const [sortMode, setSortMode] = useState("recommended");
  const [typeMode, setTypeMode] = useState("all");
  const [mineOnly, setMineOnly] = useState(false);
  const [viewer, setViewer] = useState(null);

  const scopedFeed = useMemo(() => {
    const source = scope === "midjourney"
      ? (feed || []).filter((item) => isMidjourneyModel(item.model))
      : (feed || []);
    return source.filter((item) => feedTileUrls(item).length > 0);
  }, [feed, scope]);

  const myCount = scopedFeed.filter((item) => item.is_mine).length;

  const filtered = useMemo(() => {
    const indexed = scopedFeed
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => !mineOnly || item.is_mine)
      .filter(({ item }) => typeMode === "all" || (typeMode === "video" ? feedItemIsVideo(item) : !feedItemIsVideo(item)));

    if (sortMode === "new") {
      indexed.sort((a, b) => feedCreatedAt(b.item) - feedCreatedAt(a.item) || a.index - b.index);
    } else if (sortMode === "popular") {
      indexed.sort((a, b) => feedPopularity(b.item) - feedPopularity(a.item) || feedCreatedAt(b.item) - feedCreatedAt(a.item));
    } else if (sortMode === "repeated") {
      indexed.sort((a, b) => Number(b.item.remixes || 0) - Number(a.item.remixes || 0) || feedPopularity(b.item) - feedPopularity(a.item));
    }

    return indexed.map(({ item }) => item);
  }, [scopedFeed, sortMode, typeMode, mineOnly]);

  const isMjScope = scope === "midjourney";

  return (
    <>
      <div className="feedPageHeader">
        <div>
          <h1>{isMjScope ? "Midjourney" : "Лента"}</h1>
          <p>{filtered.length} публикаций</p>
        </div>
        <button className="feedCreateButton" onClick={() => setScreen(isMjScope ? "midjourney" : "studio")}>＋ Создать</button>
      </div>

      <section className="feedToolbar" aria-label="Фильтры публикаций">
        <div className="feedSortRail" role="tablist" aria-label="Сортировка публикаций">
          {FEED_SORTS.map((filter) => (
            <button key={filter.key} className={sortMode === filter.key ? "active" : ""} onClick={() => setSortMode(filter.key)} role="tab" aria-selected={sortMode === filter.key}>{filter.label}</button>
          ))}
        </div>
        <div className="feedFilterRow">
          <div className="feedTypeTabs" role="tablist" aria-label="Тип публикаций">
            {FEED_TYPES.map((filter) => (
              <button key={filter.key} className={typeMode === filter.key ? "active" : ""} onClick={() => setTypeMode(filter.key)} role="tab" aria-selected={typeMode === filter.key}>{filter.label}</button>
            ))}
          </div>
          <button className={`feedMineToggle ${mineOnly ? "active" : ""}`} onClick={() => setMineOnly((value) => !value)} aria-pressed={mineOnly}>Мои <span>{myCount}</span></button>
        </div>
      </section>

      {feedLoading ? <Spinner /> : (
        <div className="feedList">
          {filtered.map((item, index) => (
            <FeedCard
              key={item.id || index}
              item={item}
              idx={index}
              onOpen={(openedItem, mediaIndex) => setViewer({ item: openedItem, index: mediaIndex })}
              onRemix={onRemix}
              onNotice={onNotice}
              onRemoved={onRemoved}
            />
          ))}
          {filtered.length === 0 && (
            <div className="feedEmptyState"><b>По этому фильтру пока ничего нет</b><span>Попробуй другой тип или сортировку.</span></div>
          )}
        </div>
      )}

      <FeedViewer entry={viewer} onClose={() => setViewer(null)} onRemix={onRemix} onNotice={onNotice} />
    </>
  );
}
