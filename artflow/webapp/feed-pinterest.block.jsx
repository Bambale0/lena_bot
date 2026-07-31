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

function feedPreviewIsVideo(item, url = "") {
  return item?.gen_type === "video" || /\.(mp4|webm|mov)(?:$|\?)/i.test(url);
}

function feedItemIsVideo(item) {
  return feedPreviewIsVideo(item, generationPreviewUrls(item)[0] || "");
}

function feedPopularity(item) {
  const likes = Number(item?.likes_count || 0);
  const shares = Number(item?.shares_count || 0);
  const remixes = Number(item?.remixes || 0);
  return likes + shares * 3 + remixes * 4;
}

function FeedMediaThumb({ item, previewUrl, resultUrl, idx, onError }) {
  if (!feedPreviewIsVideo(item, previewUrl)) {
    return (
      <MediaThumb
        url={previewUrl}
        openUrl={resultUrl || previewUrl}
        type="image"
        idx={idx}
        className="feedCompactImg"
        onOpen={openExternalUrl}
        onError={onError}
      />
    );
  }

  function openVideo() {
    openExternalUrl(resultUrl || previewUrl);
  }

  function handleVideoKeyDown(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openVideo();
    }
  }

  return (
    <button
      type="button"
      className="feedMediaCell feedVideoCell"
      onClick={openVideo}
      onKeyDown={handleVideoKeyDown}
      aria-label="Открыть видео"
    >
      <video
        src={previewUrl}
        className="feedCompactImg"
        muted
        playsInline
        preload="metadata"
        onError={onError}
      />
      <span className="feedVideoPlay" aria-hidden="true">▶</span>
    </button>
  );
}

function FeedCard({ item, idx, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(Boolean(item.liked_by_me));
  const [likes, setLikes] = useState(item.likes_count || 0);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const shares = Number(item.shares_count || 0);
  const remixes = Number(item.remixes || 0);
  const resultUrls = generationResultUrls(item);
  const previewUrls = generationPreviewUrls(item);
  const visibleUrls = previewUrls.filter((url) => !failedUrls.has(url)).slice(0, 4);
  const prompt = generationPromptHidden(item) ? "" : publicPromptText(item.prompt || "").trim();
  const caption = prompt.length > 92 ? `${prompt.slice(0, 89).trim()}…` : prompt;
  const isVideo = feedItemIsVideo(item);
  const hasStats = likes > 0 || remixes > 0 || shares > 0;

  useEffect(() => {
    setFailedUrls(new Set());
  }, [item.id]);

  async function handleLike() {
    if (liked || busy) return;
    setBusy(true);
    try {
      const res = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLikes(res.likes_count ?? likes + 1);
      setLiked(true);
      tg()?.HapticFeedback?.impactOccurred("light");
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось поставить лайк" });
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyLink() {
    try {
      const res = await api(`/feed/${item.id}/link`);
      const copied = await copyText(res.link || "");
      if (!copied) throw new Error("Не удалось скопировать ссылку");
      tg()?.HapticFeedback?.notificationOccurred("success");
      setLinkCopied(true);
      onNotice?.({ type: "success", message: "Ссылка на публикацию скопирована" });
      setTimeout(() => setLinkCopied(false), 2000);
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось получить ссылку" });
    }
  }

  async function handleRemove() {
    if (!item.is_mine || removing) return;
    const ok = window.confirm("Удалить эту публикацию из общей ленты?");
    if (!ok) return;
    setRemoving(true);
    try {
      await api(`/feed/${item.id}/remove`, { method: "POST" });
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Публикация удалена из ленты" });
      onRemoved?.(item.id);
    } catch (e) {
      tg()?.HapticFeedback?.notificationOccurred("error");
      onNotice?.({ type: "error", message: e.message || "Не удалось удалить публикацию" });
    } finally {
      setRemoving(false);
    }
  }

  function hideBrokenMedia(url) {
    setFailedUrls((current) => {
      const next = new Set(current);
      next.add(url);
      return next;
    });
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
            resultUrl={resultUrls[mediaIdx] || url}
            idx={idx + mediaIdx}
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
        {resultUrls.length > 4 && <span className="feedMoreBadge">+{resultUrls.length - 4}</span>}
      </div>

      {caption && <p className="feedCompactCaption">{caption}</p>}

      <div className="feedCardActionRow" aria-label="Действия с публикацией">
        <button className="feedCreateSimilarAction" onClick={() => onRemix?.(item)}>
          <b>↻</b><span>Создать</span>
        </button>
        <button
          className={`feedQuickAction ${liked ? "liked" : ""}`}
          onClick={handleLike}
          disabled={busy || liked}
          aria-label={liked ? "Лайк поставлен" : "Поставить лайк"}
          title={liked ? "Лайк поставлен" : "Нравится"}
        >
          <b>{liked ? "♥" : "♡"}</b><span>{liked ? "Готово" : "Лайк"}</span>
        </button>
        <button
          className={`feedQuickAction ${linkCopied ? "successAction" : ""}`}
          onClick={handleCopyLink}
          aria-label="Скопировать ссылку на публикацию"
          title="Поделиться"
        >
          <b>{linkCopied ? "✓" : "↗"}</b><span>{linkCopied ? "Готово" : "Ссылка"}</span>
        </button>
      </div>

      {item.is_mine && (
        <button className="feedOwnAction" onClick={handleRemove} disabled={removing}>
          {removing ? "Удаляю…" : "Удалить из ленты"}
        </button>
      )}
    </article>
  );
}

function Feed({ feed, feedLoading, prompts, setScreen, onRemix, onNotice, onRemoved, scope = "all", onPromptUse, onOpenPrompts }) {
  const [sortMode, setSortMode] = useState("recommended");
  const [typeMode, setTypeMode] = useState("all");
  const [mineOnly, setMineOnly] = useState(false);

  const scopedFeed = useMemo(() => {
    const source = scope === "midjourney"
      ? (feed || []).filter((item) => isMidjourneyModel(item.model))
      : (feed || []);
    return source.filter((item) => generationPreviewUrls(item).length > 0);
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
  const activeSort = FEED_SORTS.find((filter) => filter.key === sortMode) || FEED_SORTS[0];
  const activeType = FEED_TYPES.find((filter) => filter.key === typeMode) || FEED_TYPES[0];

  return (
    <>
      <div className="feedPageHeader">
        <div>
          <h1>{isMjScope ? "Midjourney лента" : "Лента"}</h1>
          <p>{filtered.length} публикаций · {activeType.label.toLowerCase()} · {mineOnly ? "мои" : activeSort.label.toLowerCase()}</p>
        </div>
        <button className="feedCreateButton" onClick={() => setScreen(isMjScope ? "midjourney" : "studio")}>
          ＋ Создать
        </button>
      </div>

      <section className="feedToolbar" aria-label="Фильтры и сортировка публикаций">
        <div className="feedToolbarHead">
          <span>Сортировка</span>
          <small>{filtered.length}</small>
        </div>

        <div className="feedSortRail" role="tablist" aria-label="Сортировка публикаций">
          {FEED_SORTS.map((filter) => (
            <button
              key={filter.key}
              className={sortMode === filter.key ? "active" : ""}
              onClick={() => setSortMode(filter.key)}
              role="tab"
              aria-selected={sortMode === filter.key}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <div className="feedFilterRow">
          <div className="feedTypeTabs" role="tablist" aria-label="Тип публикаций">
            {FEED_TYPES.map((filter) => (
              <button
                key={filter.key}
                className={typeMode === filter.key ? "active" : ""}
                onClick={() => setTypeMode(filter.key)}
                role="tab"
                aria-selected={typeMode === filter.key}
              >
                {filter.label}
              </button>
            ))}
          </div>

          <button
            className={`feedMineToggle ${mineOnly ? "active" : ""}`}
            onClick={() => setMineOnly((value) => !value)}
            aria-pressed={mineOnly}
          >
            Мои <span>{myCount}</span>
          </button>
        </div>
      </section>

      {feedLoading ? <Spinner /> : (
        <div className="feedList">
          {filtered.map((item, index) => (
            <FeedCard
              key={item.id || index}
              item={item}
              idx={index}
              onRemix={onRemix}
              onNotice={onNotice}
              onRemoved={onRemoved}
            />
          ))}

          {filtered.length === 0 && (
            <div className="feedEmptyState">
              <b>{mineOnly ? "У тебя пока нет публикаций по этому фильтру" : "По этому фильтру пока ничего нет"}</b>
              <span>{mineOnly ? "Опубликуй готовую работу или отключи фильтр «Мои»." : "Попробуй другой тип или сортировку."}</span>
            </div>
          )}
        </div>
      )}
    </>
  );
}
