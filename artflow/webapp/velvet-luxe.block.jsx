// @section FEED_CONSTANTS
const FEED_SORTS = [
  ["for-you", "Для тебя"],
  ["new", "Новые"],
  ["popular", "Популярные"],
];

const FEED_TYPES = [
  ["all", "Все"],
  ["image", "Фото"],
  ["video", "Видео"],
  ["mine", "Мои"],
];
// @endsection

// @section APP_HEADER
function AppHeader({ screen, user, onSearch, onTopup, onCreate }) {
  const titles = {
    feed: "Лента",
    create: "Создать",
    prompts: "Промпты",
    profile: "Профиль",
  };

  return (
    <header className="vnHeader luxeHeader">
      <div className="luxeTopbar">
        <div className="luxeWordmark" aria-label="APIX">
          <span>APIX</span>
          <Icon name="sparkle" size={17}/>
        </div>
        <nav className="luxeAccountBar">
          <Avatar user={user} size="small"/>
          <button type="button" className="vnCreditButton luxeCredit" onClick={onTopup} aria-label="Открыть баланс">
            <Icon name="sparkle" size={15}/>
            <span>{formatCredits(user?.credits)}</span>
            <b>＋</b>
          </button>
        </nav>
      </div>

      <div className="luxeHeroRow">
        <div className="luxePageTitle">
          <h1>{titles[screen] || "APIX"}</h1>
          <i/>
        </div>
        <div className="luxeHeroActions">
          {screen === "feed" && (
            <button type="button" className="luxeIconButton" onClick={onSearch} aria-label="Поиск">
              <Icon name="search" size={21}/>
            </button>
          )}
          {(screen === "feed" || screen === "prompts") && (
            <button type="button" className="luxeCreateButton" onClick={onCreate}>
              <Icon name="plus" size={19}/>
              <span>Создать</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
// @endsection

// @section BOTTOM_NAVIGATION
function BottomNavigation({ screen, onNavigate }) {
  const tab = (id, icon, label, extra = "") => (
    <button
      key={`${id}-${extra}`}
      type="button"
      className={`${screen === id ? "active" : ""} ${extra}`.trim()}
      onClick={() => onNavigate(id)}
      aria-label={label || "Создать"}
    >
      <span className="vnNavIcon"><Icon name={icon} size={22}/></span>
      {label && <small>{label}</small>}
    </button>
  );

  return (
    <nav className="vnBottomNav luxeBottomNav" aria-label="Основная навигация">
      {tab("feed", "home", "Лента")}
      {tab("create", "plus", "Создать", "luxeCreateTab")}
      <button type="button" className={`luxeOrb ${screen === "create" ? "active" : ""}`} onClick={() => onNavigate("create")} aria-label="Создать">
        <span className="luxeOrbGlow"/>
        <span className="luxeOrbCore"><Icon name="sparkle" size={29}/></span>
      </button>
      {tab("prompts", "prompt", "Промпты")}
      {tab("profile", "user", "Профиль")}
    </nav>
  );
}
// @endsection

// @section FEED_MEDIA
function FeedMedia({ item, url, index, onOpen }) {
  const video = isVideoMedia(item, url);
  const imageEndpoint = item?.id ? `/api/v1/feed/${item.id}/preview.webp?index=${index}` : "";
  const candidates = video
    ? [url].filter(Boolean)
    : [imageEndpoint, url].filter((value, candidateIndex, source) => value && source.indexOf(value) === candidateIndex);
  const [sourceIndex, setSourceIndex] = useState(0);

  useEffect(() => setSourceIndex(0), [item?.id, url, index]);

  const source = candidates[sourceIndex] || "";
  const failed = sourceIndex >= candidates.length;

  if (failed || (!source && video)) return <MediaFallback compact/>;

  const handleError = () => setSourceIndex((value) => value + 1);

  return (
    <button className="vnFeedMediaButton luxeFeedMediaButton" type="button" onClick={() => onOpen(item, index)} aria-label="Открыть публикацию">
      {video ? (
        <video src={source} muted playsInline preload="metadata" onError={handleError}/>
      ) : (
        <img src={source} alt={`Работа @${item.author || "creator"}`} loading="lazy" decoding="async" onError={handleError}/>
      )}
      {video && <span className="vnPlay luxePlay"><Icon name="play" size={22}/></span>}
    </button>
  );
}
// @endsection

// @section FEED_CARD
function FeedCard({ item, index, onOpen, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(Boolean(item.liked_by_me));
  const [likes, setLikes] = useState(Number(item.likes_count || 0));
  const [busy, setBusy] = useState(false);
  const previews = generationPreviewUrls(item).slice(0, 4);
  const preview = previews[0] || "";
  const prompt = publicPrompt(item);
  const video = isVideoMedia(item, preview);
  const shape = ["portrait", "standard", "cinema", "tall", "standard", "portrait"][index % 6];

  async function like(event) {
    event?.stopPropagation?.();
    if (busy || liked) return;
    setBusy(true);
    try {
      const result = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLiked(true);
      setLikes(Number(result.likes_count ?? likes + 1));
      telegram()?.HapticFeedback?.impactOccurred?.("light");
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поставить лайк" });
    } finally {
      setBusy(false);
    }
  }

  async function share(event) {
    event?.stopPropagation?.();
    try {
      const result = await api(`/feed/${item.id}/link`);
      if (!await copyText(result.link || "")) throw new Error("Не удалось скопировать ссылку");
      telegram()?.HapticFeedback?.notificationOccurred?.("success");
      onNotice({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поделиться" });
    }
  }

  async function remove(event) {
    event?.stopPropagation?.();
    if (!item.is_mine || !window.confirm("Удалить публикацию из ленты?")) return;
    try {
      await api(`/feed/${item.id}/remove`, { method: "POST" });
      onRemoved(item.id);
      onNotice({ type: "success", message: "Публикация удалена" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось удалить публикацию" });
    }
  }

  return (
    <article className={`vnFeedCard luxeFeedCard ${shape}`}>
      <div className="vnFeedMedia single luxeFeedMedia">
        <FeedMedia item={item} url={preview} index={0} onOpen={onOpen}/>

        <div className="vnCardTop luxeCardTop">
          <span>@{item.author || "creator"}</span>
          <div>
            <b>{video ? "Видео" : "Фото"}</b>
            {previews.length > 1 && <em>+{previews.length - 1}</em>}
          </div>
        </div>

        <div className="luxeCardShade"/>
        <div className="vnCardMetrics luxeCardMetrics">
          <button type="button" className={liked ? "liked" : ""} onClick={like} disabled={busy} aria-label="Нравится">
            <Icon name="heart" size={14}/><span>{formatCompact(likes)}</span>
          </button>
          <button type="button" onClick={(event) => { event.stopPropagation(); onRemix(item); }} aria-label="Повторить">
            <Icon name="reload" size={14}/><span>{formatCompact(item.remixes || 0)}</span>
          </button>
          {Number(item.shares_count || 0) > 0 && <span><Icon name="share" size={14}/>{formatCompact(item.shares_count)}</span>}
        </div>

        <div className="luxeCardQuick">
          <button type="button" onClick={share} aria-label="Поделиться"><Icon name="share" size={16}/></button>
          {item.is_mine && <button type="button" onClick={remove} aria-label="Удалить"><Icon name="trash" size={15}/></button>}
        </div>
      </div>
      {prompt && <p className="vnFeedCaption luxeFeedCaption">{prompt.length > 78 ? `${prompt.slice(0, 75)}…` : prompt}</p>}
    </article>
  );
}
// @endsection

// @section FEED_VIEWER
function FeedViewer({ entry, onClose, onRemix, onShare, onNotice }) {
  const [index, setIndex] = useState(entry?.index || 0);
  const [displayFailed, setDisplayFailed] = useState(false);
  const [liked, setLiked] = useState(Boolean(entry?.item?.liked_by_me));
  const [likes, setLikes] = useState(Number(entry?.item?.likes_count || 0));
  const touch = useRef(null);
  const item = entry?.item;
  const previews = item ? generationPreviewUrls(item) : [];
  const mediaCount = Math.max(previews.length, 1);

  useEffect(() => {
    setIndex(entry?.index || 0);
    setDisplayFailed(false);
    setLiked(Boolean(entry?.item?.liked_by_me));
    setLikes(Number(entry?.item?.likes_count || 0));
  }, [entry?.item?.id, entry?.index]);

  useEffect(() => {
    if (!item) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keyboard = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
      if (event.key === "ArrowRight") setIndex((value) => Math.min(mediaCount - 1, value + 1));
    };
    window.addEventListener("keydown", keyboard);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", keyboard);
    };
  }, [item, mediaCount, onClose]);

  if (!item) return null;

  const safeIndex = Math.min(index, mediaCount - 1);
  const previewUrl = previews[safeIndex] || "";
  const video = isVideoMedia(item, previewUrl);
  const displayUrl = video ? previewUrl : `/api/v1/feed/${item.id}/display.webp?index=${safeIndex}`;
  const prompt = publicPrompt(item);

  async function like() {
    if (liked) return;
    try {
      const result = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLiked(true);
      setLikes(Number(result.likes_count ?? likes + 1));
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поставить лайк" });
    }
  }

  function swipeStart(event) { touch.current = event.touches?.[0]?.clientX ?? null; }
  function swipeEnd(event) {
    const start = touch.current;
    const end = event.changedTouches?.[0]?.clientX;
    touch.current = null;
    if (start == null || end == null || Math.abs(end - start) < 50) return;
    if (end < start && safeIndex < mediaCount - 1) setIndex((value) => value + 1);
    if (end > start && safeIndex > 0) setIndex((value) => value - 1);
  }

  return (
    <div className="vnViewer luxeViewer" role="dialog" aria-modal="true">
      <header className="luxeViewerHeader">
        <button type="button" className="luxeViewerClose" onClick={onClose}><Icon name="close" size={24}/></button>
        <div className="luxeViewerAuthor">
          <span>{String(item.author || "A").slice(0, 1).toUpperCase()}</span>
          <b>@{item.author || "creator"}</b>
          <i/>
        </div>
        <button type="button" className="luxeViewerShare" onClick={() => onShare(item)}><Icon name="share" size={20}/></button>
      </header>

      <div className="vnViewerStage luxeViewerStage" onTouchStart={swipeStart} onTouchEnd={swipeEnd}>
        {displayFailed ? <MediaFallback/> : video ? (
          <video src={displayUrl} controls autoPlay playsInline onError={() => setDisplayFailed(true)}/>
        ) : (
          <img src={displayUrl} alt="" decoding="async" onError={() => setDisplayFailed(true)}/>
        )}
        <div className="luxeViewerVignette"/>
        {safeIndex > 0 && <button className="prev" type="button" onClick={() => setIndex((value) => value - 1)}><Icon name="back"/></button>}
        {safeIndex < mediaCount - 1 && <button className="next" type="button" onClick={() => setIndex((value) => value + 1)}><Icon name="chevron"/></button>}
      </div>

      <footer className="luxeViewerFooter">
        <div className="luxeViewerMeta">
          <span className="luxeViewerTag"><Icon name="sparkle" size={14}/>{item.model || (video ? "Видео" : "Фото")}</span>
          {prompt && <h2>{prompt.length > 54 ? `${prompt.slice(0, 51)}…` : prompt}</h2>}
          <div className="luxeViewerStats">
            <span><Icon name="heart" size={15}/>{formatCompact(likes)}</span>
            <span><Icon name="reload" size={15}/>{formatCompact(item.remixes || 0)}</span>
            {Number(item.shares_count || 0) > 0 && <span><Icon name="share" size={15}/>{formatCompact(item.shares_count)}</span>}
          </div>
        </div>
        <div className="luxeViewerActions">
          <button type="button" className={liked ? "active" : ""} onClick={like}><Icon name="heart" size={19}/><span>{liked ? "Нравится" : "Нравится"}</span></button>
          <button type="button" className="primary" onClick={() => { onClose(); onRemix(item); }}><Icon name="sparkle" size={19}/><span>Повторить</span></button>
          <button type="button" onClick={() => onShare(item)}><Icon name="share" size={19}/><span>Поделиться</span></button>
        </div>
        {mediaCount > 1 && (
          <div className="luxeViewerThumbs">
            {Array.from({ length: mediaCount }).map((_, thumbIndex) => {
              const thumb = previews[thumbIndex] || `/api/v1/feed/${item.id}/preview.webp?index=${thumbIndex}`;
              return <button key={thumbIndex} type="button" className={safeIndex === thumbIndex ? "active" : ""} onClick={() => setIndex(thumbIndex)}><img src={thumb} alt=""/></button>;
            })}
          </div>
        )}
      </footer>
    </div>
  );
}
// @endsection

// @section FEED_SCREEN
function FeedScreen({ feed, loading, onReload, onNavigate, onPreset, onNotice }) {
  const [sort, setSort] = useState("for-you");
  const [type, setType] = useState("all");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [viewer, setViewer] = useState(null);
  const [items, setItems] = useState(feed);

  useEffect(() => setItems(feed), [feed]);

  const filtered = useMemo(() => {
    let source = items.filter((item) => item?.gen_type !== "music");
    if (query.trim()) {
      const needle = query.trim().toLowerCase();
      source = source.filter((item) => `${item.author || ""} ${publicPrompt(item)} ${item.model || ""}`.toLowerCase().includes(needle));
    }
    if (type === "image") source = source.filter((item) => !isVideoMedia(item, generationPreviewUrls(item)[0]));
    if (type === "video") source = source.filter((item) => isVideoMedia(item, generationPreviewUrls(item)[0]));
    if (type === "mine") source = source.filter((item) => item.is_mine);
    if (sort === "new") source = [...source].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    if (sort === "popular") source = [...source].sort((a, b) => {
      const score = (value) => Number(value.likes_count || 0) + Number(value.remixes || 0) * 3 + Number(value.shares_count || 0) * 2;
      return score(b) - score(a);
    });
    return source;
  }, [items, sort, type, query]);

  function remix(item) {
    onPreset({ remix: item, kind: item.gen_type === "video" ? "video" : "image", prompt: "", hiddenPrompt: true });
    onNavigate("create");
  }

  async function share(item) {
    try {
      const result = await api(`/feed/${item.id}/link`);
      if (!await copyText(result.link || "")) throw new Error("Не удалось скопировать ссылку");
      onNotice({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поделиться" });
    }
  }

  return (
    <section className="vnScreen vnFeedScreen luxeFeedScreen">
      <div className="luxeFeedControls">
        <div className="luxeSortTabs" role="tablist" aria-label="Сортировка публикаций">
          {FEED_SORTS.map(([key, label]) => <button key={key} type="button" className={sort === key ? "active" : ""} onClick={() => setSort(key)}>{label}{key === "for-you" && <i/>}</button>)}
        </div>
        <div className="luxeTypeRow">
          <div className="luxeTypeTabs" role="tablist" aria-label="Тип публикации">
            {FEED_TYPES.map(([key, label]) => <button key={key} type="button" className={type === key ? "active" : ""} onClick={() => setType(key)}>{key === "image" && <Icon name="image" size={15}/>} {key === "video" && <Icon name="video" size={15}/>} {key === "mine" && <Icon name="user" size={15}/>}<span>{label}</span></button>)}
          </div>
          <button type="button" className="luxeFilterToggle" onClick={() => setSearchOpen((value) => !value)} aria-label="Поиск и фильтры"><Icon name="sliders" size={19}/></button>
        </div>
      </div>

      {searchOpen && (
        <div className="vnSearchBar luxeSearchBar">
          <Icon name="search" size={18}/>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Автор, модель или идея" autoFocus/>
          {query && <button type="button" onClick={() => setQuery("")}><Icon name="close" size={16}/></button>}
        </div>
      )}

      {loading ? <Loading label="Собираем ленту"/> : filtered.length ? (
        <div className="vnMasonry luxeMasonry">
          {filtered.map((item, index) => (
            <FeedCard key={item.id || index} item={item} index={index} onOpen={(selected, mediaIndex) => setViewer({ item: selected, index: mediaIndex })} onRemix={remix} onNotice={onNotice} onRemoved={(id) => setItems((current) => current.filter((entry) => entry.id !== id))}/>
          ))}
        </div>
      ) : (
        <Empty icon="image" title={type === "mine" ? "Публикаций пока нет" : "Здесь пока тихо"} text={type === "mine" ? "Опубликуй готовую работу — она появится здесь." : "Создай первую работу или измени фильтр."} action={<button className="vnGradientButton" type="button" onClick={() => onNavigate("create")}>Создать</button>}/>
      )}

      <button className="vnRefresh luxeRefresh" type="button" onClick={onReload}><Icon name="reload" size={17}/>Обновить ленту</button>
      {viewer && <FeedViewer entry={viewer} onClose={() => setViewer(null)} onRemix={remix} onShare={share} onNotice={onNotice}/>} 
    </section>
  );
}
// @endsection
