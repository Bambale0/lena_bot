// ── Feed screen ───────────────────────────────────────────────────────────────

const FEED_FILTERS = [
  { key: "recommended", label: "Для тебя" },
  { key: "new", label: "Новые" },
  { key: "popular", label: "Популярные" },
  { key: "repeated", label: "Повторяемые" },
  { key: "mine", label: "Мои" },
];

function feedCreatedAt(item) {
  const value = Date.parse(item?.created_at || "");
  return Number.isFinite(value) ? value : 0;
}

function feedPopularity(item) {
  const likes = Number(item?.likes_count || 0);
  const shares = Number(item?.shares_count || 0);
  const remixes = Number(item?.remixes || 0);
  return likes + shares * 3 + remixes * 4;
}

function FeedCard({ item, idx, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(false);
  const [likes, setLikes] = useState(item.likes_count || 0);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const shares = item.shares_count || 0;
  const remixes = item.remixes || 0;
  const resultUrls = generationResultUrls(item);
  const previewUrls = generationPreviewUrls(item);
  const visibleUrls = previewUrls.filter((url) => !failedUrls.has(url)).slice(0, 4);
  const prompt = generationPromptHidden(item) ? "" : publicPromptText(item.prompt || "").trim();
  const caption = prompt.length > 105 ? `${prompt.slice(0, 102).trim()}…` : prompt;
  const isVideo = item.gen_type === "video" || visibleUrls.some((url) => /\.(mp4|webm|mov)(?:$|\?)/i.test(url));

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
    const ok = window.confirm("Удалить этот пост из ленты? Он исчезнет из общей ленты.");
    if (!ok) return;
    setRemoving(true);
    try {
      await api(`/feed/${item.id}/remove`, { method: "POST" });
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Пост удалён из ленты" });
      onRemoved?.(item.id);
    } catch (e) {
      tg()?.HapticFeedback?.notificationOccurred("error");
      onNotice?.({ type: "error", message: e.message || "Не удалось удалить пост" });
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
          <MediaThumb
            key={`${url}-${mediaIdx}`}
            url={url}
            openUrl={resultUrls[mediaIdx] || url}
            type={/\.(mp4|webm|mov)(?:$|\?)/i.test(url) ? "video" : "image"}
            idx={idx + mediaIdx}
            className="feedCompactImg"
            onOpen={openExternalUrl}
            onError={() => hideBrokenMedia(url)}
          />
        ))}
        <div className="feedCompactTop">
          <span className="feedCompactAuthor">@{item.author || "anon"}</span>
          <span className="feedKindBadge">{isVideo ? "Видео" : "Фото"}</span>
        </div>
        <div className="feedCompactStats" aria-label="Статистика публикации">
          <span>♥ {likes}</span>
          <span>↻ {remixes}</span>
          {shares > 0 && <span>↗ {shares}</span>}
        </div>
        {item.is_mine && <span className="feedMineBadge">Твоя работа</span>}
        {resultUrls.length > 4 && <span className="feedMoreBadge">+{resultUrls.length - 4}</span>}
      </div>

      {caption && <p className="feedCompactCaption">{caption}</p>}

      <div className="feedCompactActions">
        <button className="feedRepeatAction" onClick={() => onRemix?.(item)}>
          <b>↻</b><span>Повторить</span>
        </button>
        <div className="feedSecondaryActions">
          <button
            className={`feedTextAction ${liked ? "liked" : ""}`}
            onClick={handleLike}
            disabled={busy}
            aria-label="Поставить лайк"
          >
            <b>{liked ? "♥" : "♡"}</b><span>{liked ? "Понравилось" : "Нравится"}</span>
          </button>
          <button
            className={`feedTextAction ${linkCopied ? "successAction" : ""}`}
            onClick={handleCopyLink}
            aria-label="Скопировать ссылку на публикацию"
          >
            <b>{linkCopied ? "✓" : "↗"}</b><span>{linkCopied ? "Скопировано" : "Поделиться"}</span>
          </button>
        </div>
        {item.is_mine && (
          <button className="feedRemoveAction" onClick={handleRemove} disabled={removing}>
            {removing ? "Удаляю…" : "Удалить публикацию"}
          </button>
        )}
      </div>
    </article>
  );
}

function Feed({ feed, feedLoading, prompts, setScreen, onRemix, onNotice, onRemoved, scope = "all", onPromptUse, onOpenPrompts }) {
  const [mode, setMode] = useState("recommended");
  const scopedFeed = useMemo(() => {
    const items = scope === "midjourney" ? (feed || []).filter((item) => isMidjourneyModel(item.model)) : (feed || []);
    return items.filter((item) => generationPreviewUrls(item).length > 0);
  }, [feed, scope]);
  const myCount = scopedFeed.filter((item) => item.is_mine).length;
  const filtered = useMemo(() => {
    const indexed = scopedFeed.map((item, index) => ({ item, index }));
    const visible = mode === "mine" ? indexed.filter(({ item }) => item.is_mine) : indexed;

    if (mode === "new") {
      visible.sort((a, b) => feedCreatedAt(b.item) - feedCreatedAt(a.item) || a.index - b.index);
    } else if (mode === "popular") {
      visible.sort((a, b) => feedPopularity(b.item) - feedPopularity(a.item) || feedCreatedAt(b.item) - feedCreatedAt(a.item));
    } else if (mode === "repeated") {
      visible.sort((a, b) => Number(b.item.remixes || 0) - Number(a.item.remixes || 0) || feedPopularity(b.item) - feedPopularity(a.item));
    }

    return visible.map(({ item }) => item);
  }, [scopedFeed, mode]);
  const isMjScope = scope === "midjourney";
  const activeFilter = FEED_FILTERS.find((filter) => filter.key === mode) || FEED_FILTERS[0];

  return (
    <>
      <div className="feedPageHeader">
        <div>
          <h1>{isMjScope ? "Midjourney лента" : "Лента"}</h1>
          <p>{filtered.length} публикаций · {activeFilter.label.toLowerCase()}</p>
        </div>
        <button className="feedCreateButton" onClick={() => setScreen(isMjScope ? "midjourney" : "studio")}>
          ＋ Создать
        </button>
      </div>

      <div className="feedFilterSection">
        <span className="feedFilterTitle">Фильтр публикаций</span>
        <div className="feedFilterBar" role="tablist" aria-label="Фильтр публикаций">
          {FEED_FILTERS.map((filter) => (
            <button
              key={filter.key}
              className={`${mode === filter.key ? "active" : ""} ${filter.key === "mine" ? "mine" : ""}`.trim()}
              onClick={() => setMode(filter.key)}
              role="tab"
              aria-selected={mode === filter.key}
            >
              {filter.label}
              {filter.key === "mine" && <span>{myCount}</span>}
            </button>
          ))}
        </div>
      </div>

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
              <b>{mode === "mine" ? "Здесь появятся твои публикации" : "По этому фильтру пока ничего нет"}</b>
              <span>{mode === "mine" ? "Опубликуй готовую работу — она появится здесь." : "Выбери другой фильтр или создай новую работу."}</span>
            </div>
          )}
        </div>
      )}
    </>
  );
}
