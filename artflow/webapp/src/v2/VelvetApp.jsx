import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  asItems,
  copyText,
  formatCompact,
  formatCredits,
  formatDate,
  generationFromRealtime,
  generationPreviewUrls,
  generationResultUrls,
  isVideoMedia,
  openTelegramLink,
  prepareTelegram,
  publicPrompt,
  telegram,
  telegramInitData,
  telegramUser,
  uploadReference,
  useResource,
} from "./api.js";

const FALLBACK_USER = {
  username: "",
  full_name: "",
  photo_url: "",
  credits: 0,
  referral_balance: 0,
  is_admin: false,
};

const STYLE_PRESETS = [
  { key: "cinematic", label: "Кинематик", hint: "cinematic lighting, premium color grading, detailed" },
  { key: "neon", label: "Неон", hint: "neon light, glossy reflections, night atmosphere" },
  { key: "realism", label: "Реализм", hint: "photorealistic, natural skin, realistic light" },
  { key: "art", label: "Арт", hint: "concept art, expressive composition, museum quality" },
];

const FEED_FILTERS = [
  ["for-you", "Для тебя"],
  ["popular", "Популярное"],
  ["image", "Фото"],
  ["video", "Видео"],
  ["art", "Арт"],
];

function Icon({ name, size = 22, strokeWidth = 1.8 }) {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  };

  const paths = {
    home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9"/><path d="M9 20v-6h6v6"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    sparkle: <><path d="M12 3c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7Z"/><path d="M19 3v4M17 5h4"/></>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    sliders: <><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></>,
    prompt: <><path d="M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M8 9h8M8 13h5"/></>,
    user: <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8Z"/>,
    share: <><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4"/></>,
    bookmark: <path d="M6 3h12v18l-6-4-6 4V3Z"/>,
    play: <path d="m8 5 11 7-11 7V5Z"/>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    chevron: <path d="m9 18 6-6-6-6"/>,
    back: <path d="m15 18-6-6 6-6"/>,
    image: <><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9" r="1.5"/><path d="m21 15-5-5L5 20"/></>,
    video: <><rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 10 4-3v10l-4-3"/></>,
    camera: <><path d="M14.5 5 13 3h-2L9.5 5H5a2 2 0 0 0-2 2v11h18V7a2 2 0 0 0-2-2h-4.5Z"/><circle cx="12" cy="12" r="4"/></>,
    wallet: <><path d="M4 5h15a2 2 0 0 1 2 2v12H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/><path d="M16 10h5v5h-5a2.5 2.5 0 0 1 0-5Z"/></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></>,
    trash: <><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14"/></>,
    reload: <><path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M6.1 9A7 7 0 0 1 18 6l2 6M17.9 15A7 7 0 0 1 6 18l-2-6"/></>,
    external: <><path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h6"/></>,
    crown: <><path d="m3 7 4 4 5-7 5 7 4-4-2 11H5L3 7Z"/><path d="M5 21h14"/></>,
    more: <><circle cx="5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1" fill="currentColor" stroke="none"/></>,
  };

  return <svg {...props}>{paths[name] || paths.sparkle}</svg>;
}

function Avatar({ user, size = "normal" }) {
  const [failed, setFailed] = useState(false);
  const name = user?.full_name || user?.username || telegramUser()?.first_name || "A";
  const photo = user?.photo_url || telegramUser()?.photo_url;
  const initial = String(name).trim().slice(0, 1).toUpperCase();

  return (
    <span className={`vnAvatar ${size}`}>
      {photo && !failed
        ? <img src={photo} alt="" onError={() => setFailed(true)} />
        : <span>{initial}</span>}
    </span>
  );
}

function Loading({ label = "Загружаем" }) {
  return <div className="vnLoading"><span/><p>{label}</p></div>;
}

function Empty({ icon = "sparkle", title, text, action }) {
  return (
    <div className="vnEmpty">
      <div className="vnEmptyIcon"><Icon name={icon} size={28}/></div>
      <b>{title}</b>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

function Notice({ notice, onClose }) {
  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(onClose, 3800);
    return () => window.clearTimeout(timer);
  }, [notice, onClose]);

  if (!notice) return null;
  return (
    <div className={`vnNotice ${notice.type || "info"}`} role={notice.type === "error" ? "alert" : "status"}>
      <Icon name={notice.type === "error" ? "close" : "sparkle"} size={18}/>
      <span>{notice.message}</span>
      <button type="button" onClick={onClose}><Icon name="close" size={16}/></button>
    </div>
  );
}

function AppHeader({ screen, user, onSearch, onTopup }) {
  const titles = {
    feed: "Лента",
    create: "Создать",
    prompts: "Промпты",
    profile: "Профиль",
  };

  return (
    <header className="vnHeader">
      <div>
        <span className="vnBrandSpark"><Icon name="sparkle" size={15}/></span>
        <h1>{titles[screen] || "APIX"}</h1>
        {screen === "feed" && <i/>}
      </div>
      <nav>
        {screen === "feed" && <button type="button" onClick={onSearch} aria-label="Поиск"><Icon name="search"/></button>}
        <button type="button" className="vnCreditButton" onClick={onTopup} aria-label="Баланс">
          <span>{formatCredits(user?.credits)}</span><b>💋</b>
        </button>
        <Avatar user={user} size="small"/>
      </nav>
    </header>
  );
}

function BottomNavigation({ screen, onNavigate }) {
  const items = [
    ["feed", "home", "Лента"],
    ["create", "sparkle", "Создать"],
    ["prompts", "prompt", "Промпты"],
    ["profile", "user", "Профиль"],
  ];

  return (
    <nav className="vnBottomNav" aria-label="Основная навигация">
      {items.map(([id, icon, label]) => (
        <button
          key={id}
          type="button"
          className={`${screen === id ? "active" : ""} ${id === "create" ? "create" : ""}`}
          onClick={() => onNavigate(id)}
        >
          {id === "create" && <span className="vnCreateHalo"/>}
          <span className="vnNavIcon"><Icon name={icon} size={id === "create" ? 27 : 22}/></span>
          <small>{label}</small>
        </button>
      ))}
    </nav>
  );
}

function MediaFallback({ compact = false }) {
  return (
    <div className={`vnMediaFallback ${compact ? "compact" : ""}`}>
      <Icon name="image" size={compact ? 22 : 32}/>
      {!compact && <span>Превью временно недоступно</span>}
    </div>
  );
}

function FeedMedia({ item, url, index, onOpen }) {
  const [failed, setFailed] = useState(false);
  const video = isVideoMedia(item, url);

  if (!url || failed) return <MediaFallback compact/>;

  return (
    <button className="vnFeedMediaButton" type="button" onClick={() => onOpen(item, index)}>
      {video ? (
        <video src={url} muted playsInline preload="metadata" onError={() => setFailed(true)}/>
      ) : (
        <img src={url} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)}/>
      )}
      {video && <span className="vnPlay"><Icon name="play" size={20}/></span>}
    </button>
  );
}

function FeedCard({ item, index, onOpen, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(Boolean(item.liked_by_me));
  const [likes, setLikes] = useState(Number(item.likes_count || 0));
  const [busy, setBusy] = useState(false);
  const previews = generationPreviewUrls(item).slice(0, 4);
  const prompt = publicPrompt(item);
  const video = isVideoMedia(item, previews[0]);

  async function like() {
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

  async function share() {
    try {
      const result = await api(`/feed/${item.id}/link`);
      const copied = await copyText(result.link || "");
      if (!copied) throw new Error("Не удалось скопировать ссылку");
      telegram()?.HapticFeedback?.notificationOccurred?.("success");
      onNotice({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поделиться" });
    }
  }

  async function remove() {
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
    <article className={`vnFeedCard ${index % 5 === 0 ? "featured" : ""}`}>
      <div className={`vnFeedMedia ${previews.length > 1 ? "multi" : "single"}`}>
        {previews.length
          ? previews.map((url, mediaIndex) => (
              <FeedMedia key={`${url}-${mediaIndex}`} item={item} url={url} index={mediaIndex} onOpen={onOpen}/>
            ))
          : <MediaFallback/>}

        <div className="vnCardTop">
          <span>@{item.author || "creator"}</span>
          <b>{video ? "Видео" : "Фото"}</b>
        </div>

        <div className="vnCardMetrics">
          {likes > 0 && <span><Icon name="heart" size={13}/>{formatCompact(likes)}</span>}
          {Number(item.remixes || 0) > 0 && <span><Icon name="reload" size={13}/>{formatCompact(item.remixes)}</span>}
          {Number(item.shares_count || 0) > 0 && <span><Icon name="share" size={13}/>{formatCompact(item.shares_count)}</span>}
        </div>
      </div>

      {prompt && <p className="vnFeedCaption">{prompt.length > 90 ? `${prompt.slice(0, 87)}…` : prompt}</p>}

      <div className="vnCardActions">
        <button type="button" className="primary" onClick={() => onRemix(item)}><Icon name="sparkle" size={17}/>Повторить</button>
        <button type="button" className={liked ? "liked" : ""} onClick={like} disabled={busy} aria-label="Нравится"><Icon name="heart" size={19}/></button>
        <button type="button" onClick={share} aria-label="Поделиться"><Icon name="share" size={18}/></button>
        {item.is_mine && <button type="button" onClick={remove} aria-label="Удалить"><Icon name="trash" size={17}/></button>}
      </div>
    </article>
  );
}

function FeedViewer({ entry, onClose, onRemix, onShare, onNotice }) {
  const [index, setIndex] = useState(entry?.index || 0);
  const [displayFailed, setDisplayFailed] = useState(false);
  const touch = useRef(null);
  const item = entry?.item;
  const previews = item ? generationPreviewUrls(item) : [];

  useEffect(() => {
    setIndex(entry?.index || 0);
    setDisplayFailed(false);
  }, [entry?.item?.id, entry?.index]);

  useEffect(() => {
    if (!item) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const keyboard = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1));
      if (event.key === "ArrowRight") setIndex((value) => Math.min(previews.length - 1, value + 1));
    };
    window.addEventListener("keydown", keyboard);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", keyboard);
    };
  }, [item, previews.length, onClose]);

  if (!item || !previews.length) return null;

  const safeIndex = Math.min(index, previews.length - 1);
  const previewUrl = previews[safeIndex];
  const video = isVideoMedia(item, previewUrl);
  const displayUrl = video
    ? previewUrl
    : `/api/v1/feed/${item.id}/display.webp?index=${safeIndex}`;
  const prompt = publicPrompt(item);

  function swipeStart(event) {
    touch.current = event.touches?.[0]?.clientX ?? null;
  }

  function swipeEnd(event) {
    const start = touch.current;
    const end = event.changedTouches?.[0]?.clientX;
    touch.current = null;
    if (start == null || end == null || Math.abs(end - start) < 50) return;
    if (end < start && safeIndex < previews.length - 1) setIndex((value) => value + 1);
    if (end > start && safeIndex > 0) setIndex((value) => value - 1);
  }

  return (
    <div className="vnViewer" role="dialog" aria-modal="true">
      <header>
        <div><span>@{item.author || "creator"}</span>{previews.length > 1 && <small>{safeIndex + 1}/{previews.length}</small>}</div>
        <button type="button" onClick={onClose}><Icon name="close"/></button>
      </header>

      <div className="vnViewerStage" onTouchStart={swipeStart} onTouchEnd={swipeEnd}>
        {displayFailed ? <MediaFallback/> : video ? (
          <video src={displayUrl} controls autoPlay playsInline onError={() => setDisplayFailed(true)}/>
        ) : (
          <img src={displayUrl} alt="" decoding="async" onError={() => setDisplayFailed(true)}/>
        )}
        {safeIndex > 0 && <button className="prev" type="button" onClick={() => setIndex((value) => value - 1)}><Icon name="back"/></button>}
        {safeIndex < previews.length - 1 && <button className="next" type="button" onClick={() => setIndex((value) => value + 1)}><Icon name="chevron"/></button>}
      </div>

      <footer>
        {prompt && <p>{prompt}</p>}
        <div>
          <button type="button" className="vnGradientButton" onClick={() => { onClose(); onRemix(item); }}><Icon name="sparkle" size={18}/>Повторить</button>
          <button type="button" onClick={() => onShare(item)}><Icon name="share" size={18}/>Поделиться</button>
        </div>
      </footer>
    </div>
  );
}

function FeedScreen({ feed, loading, onReload, onNavigate, onPreset, onNotice }) {
  const [filter, setFilter] = useState("for-you");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [viewer, setViewer] = useState(null);
  const [items, setItems] = useState(feed);

  useEffect(() => setItems(feed), [feed]);

  const filtered = useMemo(() => {
    const source = items.filter((item) => generationPreviewUrls(item).length > 0);
    const searched = query.trim()
      ? source.filter((item) => `${item.author || ""} ${publicPrompt(item)} ${item.model || ""}`.toLowerCase().includes(query.trim().toLowerCase()))
      : source;

    if (filter === "image") return searched.filter((item) => !isVideoMedia(item, generationPreviewUrls(item)[0]));
    if (filter === "video") return searched.filter((item) => isVideoMedia(item, generationPreviewUrls(item)[0]));
    if (filter === "art") return searched.filter((item) => /art|gpt|midjourney|seedream|flux/i.test(`${item.model || ""} ${publicPrompt(item)}`));
    if (filter === "popular") return [...searched].sort((a, b) => {
      const score = (value) => Number(value.likes_count || 0) + Number(value.remixes || 0) * 3 + Number(value.shares_count || 0) * 2;
      return score(b) - score(a);
    });
    return searched;
  }, [items, filter, query]);

  function remix(item) {
    onPreset({
      remix: item,
      kind: item.gen_type === "video" ? "video" : "image",
      prompt: "",
      hiddenPrompt: true,
    });
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
    <section className="vnScreen vnFeedScreen">
      <div className="vnFeedToolbar">
        <div className="vnFilterRail">
          {FEED_FILTERS.map(([key, label]) => (
            <button key={key} type="button" className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>{label}</button>
          ))}
        </div>
        <button type="button" className="vnFilterButton" onClick={() => setSearchOpen((value) => !value)} aria-label="Фильтры"><Icon name="sliders" size={19}/></button>
      </div>

      {searchOpen && (
        <div className="vnSearchBar">
          <Icon name="search" size={18}/>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Автор, модель или идея" autoFocus/>
          {query && <button type="button" onClick={() => setQuery("")}><Icon name="close" size={16}/></button>}
        </div>
      )}

      {loading ? <Loading label="Собираем ленту"/> : filtered.length ? (
        <div className="vnMasonry">
          {filtered.map((item, index) => (
            <FeedCard
              key={item.id || index}
              item={item}
              index={index}
              onOpen={(selected, mediaIndex) => setViewer({ item: selected, index: mediaIndex })}
              onRemix={remix}
              onNotice={onNotice}
              onRemoved={(id) => setItems((current) => current.filter((item) => item.id !== id))}
            />
          ))}
        </div>
      ) : (
        <Empty
          icon="image"
          title="Здесь пока тихо"
          text="Создай первую работу или измени фильтр."
          action={<button className="vnGradientButton" type="button" onClick={() => onNavigate("create")}>Создать</button>}
        />
      )}

      <button className="vnRefresh" type="button" onClick={onReload}><Icon name="reload" size={18}/>Обновить</button>

      {viewer && <FeedViewer entry={viewer} onClose={() => setViewer(null)} onRemix={remix} onShare={share} onNotice={onNotice}/>} 
    </section>
  );
}

function normalizeOptions(values, fallback = []) {
  const source = Array.isArray(values) && values.length ? values : fallback;
  return source.map((value) => typeof value === "object" ? value : { value, label: String(value) });
}

function modelCost(model, kind, settings) {
  if (!model) return 0;
  if (kind === "image") {
    return Number(model.quality_prices?.[settings.quality] ?? model.credits ?? 0) * Number(settings.count || 1);
  }
  if (model.is_per_second) return Number(model.credits_per_sec || model.credits || 0) * Number(settings.duration || 0);
  if (model.key === "gemini-omni-video") {
    const resolution = settings.resolution === "2160p" ? "4k" : settings.resolution;
    return Number(model.price_table?.[resolution]?.[settings.duration] ?? model.credits ?? 0);
  }
  return Number(model.credits || 0);
}

function ResultPanel({ generation, onOpen, onPublish, onSave, onRepeat, onNotice }) {
  const [publishing, setPublishing] = useState(false);
  const [saving, setSaving] = useState(false);
  if (!generation) return null;

  const urls = generationResultUrls(generation);
  const done = generation.status === "done";
  const pending = generation.status === "pending" || generation.status === "processing";

  async function publish() {
    if (!generation.id || publishing) return;
    setPublishing(true);
    try {
      await api(`/generations/${generation.id}/share`, { method: "POST" });
      onPublish?.();
      onNotice({ type: "success", message: "Работа опубликована в ленте" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось опубликовать" });
    } finally {
      setPublishing(false);
    }
  }

  async function save() {
    if (!generation.id || saving) return;
    setSaving(true);
    try {
      await api(`/generations/${generation.id}/share-library`, { method: "POST" });
      onSave?.();
      onNotice({ type: "success", message: "Промпт сохранён" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось сохранить промпт" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={`vnResultPanel ${generation.status}`}>
      <header>
        <div><span className="vnLiveDot"/><b>{pending ? "Создаём магию" : done ? "Готово" : "Не получилось"}</b></div>
        {generation.id > 0 && <small>#{generation.id}</small>}
      </header>

      {pending && <div className="vnGenerationPulse"><span/><span/><span/></div>}
      {generation.error && <p className="vnErrorText">{generation.error}</p>}

      {done && urls.length > 0 && (
        <div className={`vnResultGrid ${urls.length > 1 ? "multi" : ""}`}>
          {urls.map((url, index) => isVideoMedia(generation, url)
            ? <video key={url} src={url} controls playsInline/>
            : <button key={url} type="button" onClick={() => onOpen({ item: generation, index })}><img src={url} alt="Результат"/></button>)}
        </div>
      )}

      {done && (
        <div className="vnResultActions">
          <button type="button" className="vnGradientButton" onClick={onRepeat}><Icon name="reload" size={17}/>Ещё вариант</button>
          {generation.gen_type !== "video" && <button type="button" onClick={publish} disabled={publishing}><Icon name="share" size={17}/>{publishing ? "..." : "В ленту"}</button>}
          {generation.prompt_actions_allowed !== false && <button type="button" onClick={save} disabled={saving}><Icon name="bookmark" size={17}/>{saving ? "..." : "Сохранить"}</button>}
        </div>
      )}
    </section>
  );
}

function CreateScreen({ user, imageModels, videoModels, preset, generation, onGenerate, onClearPreset, onTopup, onNotice, onFeedReload }) {
  const [kind, setKind] = useState("image");
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("cinematic");
  const [modelKey, setModelKey] = useState("");
  const [mode, setMode] = useState("text");
  const [ratio, setRatio] = useState("9:16");
  const [quality, setQuality] = useState("basic");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(5);
  const [resolution, setResolution] = useState("720p");
  const [modeOption, setModeOption] = useState("normal");
  const [referenceUrls, setReferenceUrls] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [improving, setImproving] = useState(false);
  const [viewer, setViewer] = useState(null);
  const inputRef = useRef(null);

  const models = useMemo(() => kind === "video"
    ? videoModels.filter((model) => (model.modes || []).some((item) => item === "text" || item === "image"))
    : imageModels,
  [kind, imageModels, videoModels]);

  const current = models.find((model) => model.key === modelKey) || models[0] || null;
  const modes = current?.modes || ["text"];
  const ratios = normalizeOptions(current?.aspect_ratios, ["1:1", "3:4", "4:5", "9:16", "16:9"]);
  const qualities = normalizeOptions(current?.quality_options, ["basic"]);
  const counts = normalizeOptions(current?.counts, [1]);
  const durations = normalizeOptions(current?.durations || current?.duration_options, [5]);
  const resolutions = normalizeOptions(current?.resolutions, ["720p"]);
  const modeOptions = normalizeOptions(current?.mode_options, ["normal"]);
  const maxRefs = Math.max(1, Number(current?.max_refs || 1));
  const estimatedCost = modelCost(current, kind, { quality, count, duration, resolution });

  useEffect(() => {
    if (!models.length) {
      setModelKey("");
      return;
    }
    if (!models.some((model) => model.key === modelKey)) setModelKey(models[0].key);
  }, [models, modelKey]);

  useEffect(() => {
    if (!current) return;
    const nextModes = current.modes || ["text"];
    setMode(nextModes.includes("text") ? "text" : nextModes[0]);
    setRatio((current.aspect_ratios || ["9:16"])[0]);
    setQuality(normalizeOptions(current.quality_options, ["basic"])[0]?.value || "basic");
    setCount(Number((current.counts || [1])[0]));
    setDuration(Number((current.durations || current.duration_options || [5])[0]));
    setResolution((current.resolutions || ["720p"])[0]);
    setModeOption((current.mode_options || ["normal"])[0]);
    setReferenceUrls((urls) => urls.slice(0, Math.max(1, Number(current.max_refs || 1))));
  }, [current?.key]);

  useEffect(() => {
    if (!preset) return;
    const nextKind = preset.kind === "video" ? "video" : "image";
    setKind(nextKind);
    if (!preset.hiddenPrompt) setPrompt(preset.prompt || "");
    if (preset.modelKey) setModelKey(preset.modelKey);
    if (preset.remix) {
      const urls = generationResultUrls(preset.remix).slice(0, 4);
      setReferenceUrls(urls);
      setMode("image");
    }
  }, [preset?.id, preset?.prompt, preset?.modelKey, preset?.remix?.id]);

  async function improvePrompt() {
    if (!prompt.trim() || improving) return;
    setImproving(true);
    try {
      const result = await api("/prompt/improve", {
        method: "POST",
        body: JSON.stringify({ prompt, kind }),
      });
      setPrompt(result.prompt || prompt);
      onNotice({ type: "success", message: "Промпт улучшен" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось улучшить промпт" });
    } finally {
      setImproving(false);
    }
  }

  async function addReferences(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length || uploading) return;
    setUploading(true);
    try {
      const available = Math.max(0, maxRefs - referenceUrls.length);
      const urls = [];
      for (const file of files.slice(0, available)) urls.push(await uploadReference(file));
      setReferenceUrls((currentUrls) => [...currentUrls, ...urls].slice(0, maxRefs));
      onNotice({ type: "success", message: `Загружено: ${urls.length}` });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось загрузить референс" });
    } finally {
      setUploading(false);
    }
  }

  function submit() {
    if (!current) return;
    if (!prompt.trim() && current.key !== "midjourney-blend" && !preset?.remix) {
      onNotice({ type: "warning", message: "Опиши, что нужно создать" });
      return;
    }
    if (mode === "image" && !referenceUrls.length) {
      onNotice({ type: "warning", message: "Добавь референс" });
      return;
    }
    if (Number(user.credits || 0) < estimatedCost) {
      onTopup();
      return;
    }

    const selectedStyle = STYLE_PRESETS.find((item) => item.key === style);
    const finalPrompt = prompt.trim()
      ? `${prompt.trim()}${selectedStyle ? `, ${selectedStyle.hint}` : ""}`
      : "";

    onGenerate({
      kind,
      remix: preset?.remix || null,
      payload: {
        model: current.key,
        prompt: finalPrompt,
        prompt_id: preset?.promptId || null,
        mode,
        aspect_ratio: ratio,
        quality,
        count,
        duration,
        resolution,
        grok_mode: modeOptions.length > 1 ? modeOption : undefined,
        image_url: referenceUrls[0] || null,
        reference_url: referenceUrls[0] || null,
        reference_urls: referenceUrls.slice(1),
      },
    });
  }

  return (
    <section className="vnScreen vnCreateScreen">
      {preset && (
        <div className="vnPresetNotice">
          <Icon name="sparkle" size={17}/>
          <span>{preset.remix ? "Повтор публикации" : "Промпт подставлен"}</span>
          <button type="button" onClick={() => { onClearPreset(); setReferenceUrls([]); }}><Icon name="close" size={16}/></button>
        </div>
      )}

      <div className="vnCreateType">
        <button type="button" className={kind === "image" ? "active" : ""} onClick={() => setKind("image")}><Icon name="image" size={18}/>Фото</button>
        <button type="button" className={kind === "video" ? "active" : ""} onClick={() => setKind("video")}><Icon name="video" size={18}/>Видео</button>
        <button type="button" className={kind === "image" && style === "art" ? "active" : ""} onClick={() => { setKind("image"); setStyle("art"); }}><Icon name="sparkle" size={18}/>Арт</button>
      </div>

      <div className="vnPromptComposer">
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Опишите, что хотите создать..."
          maxLength={8000}
        />
        <div>
          <span>{prompt.length}/8000</span>
          <button type="button" onClick={improvePrompt} disabled={!prompt.trim() || improving} aria-label="Улучшить промпт"><Icon name="sparkle" size={20}/></button>
        </div>
      </div>

      <section className="vnOptionSection">
        <header><h2>Стиль</h2></header>
        <div className="vnStyleRail">
          {STYLE_PRESETS.map((item) => (
            <button key={item.key} type="button" className={style === item.key ? "active" : ""} onClick={() => setStyle(item.key)}>
              <span className={`vnStylePreview ${item.key}`}><Icon name="sparkle" size={19}/></span>
              <b>{item.label}</b>
            </button>
          ))}
        </div>
      </section>

      <section className="vnOptionSection">
        <header><h2>Модель</h2><small>{models.length}</small></header>
        <div className="vnModelRail">
          {models.map((model) => (
            <button key={model.key} type="button" className={current?.key === model.key ? "active" : ""} onClick={() => setModelKey(model.key)}>
              <span><Icon name={kind === "video" ? "video" : "sparkle"} size={18}/></span>
              <div><b>{model.display_name || model.key}</b><small>{formatCredits(model.credits)} 💋</small></div>
            </button>
          ))}
        </div>
      </section>

      {modes.length > 1 && (
        <section className="vnOptionSection compact">
          <header><h2>Источник</h2></header>
          <div className="vnSegmented">
            {modes.filter((item) => item === "text" || item === "image").map((item) => (
              <button key={item} type="button" className={mode === item ? "active" : ""} onClick={() => setMode(item)}>{item === "text" ? "По тексту" : "По фото"}</button>
            ))}
          </div>
        </section>
      )}

      {mode === "image" && (
        <section className="vnReferences">
          <header><h2>Референсы</h2><small>{referenceUrls.length}/{maxRefs}</small></header>
          <div className="vnReferenceGrid">
            {referenceUrls.map((url, index) => (
              <div key={`${url}-${index}`}>
                <img src={url} alt="Референс"/>
                <button type="button" onClick={() => setReferenceUrls((items) => items.filter((_, itemIndex) => itemIndex !== index))}><Icon name="close" size={14}/></button>
              </div>
            ))}
            {referenceUrls.length < maxRefs && (
              <button type="button" onClick={() => inputRef.current?.click()} disabled={uploading}><Icon name="plus" size={22}/><span>{uploading ? "Загрузка" : "Добавить"}</span></button>
            )}
          </div>
          <input ref={inputRef} type="file" accept="image/*" multiple={maxRefs > 1} hidden onChange={addReferences}/>
        </section>
      )}

      <section className="vnOptionSection compact">
        <header><h2>Соотношение сторон</h2></header>
        <div className="vnRatioRail">
          {ratios.map((option) => (
            <button key={option.value} type="button" className={ratio === option.value ? "active" : ""} onClick={() => setRatio(option.value)}>
              <span className={`ratioShape r${String(option.value).replace(":", "x")}`}/><small>{option.label}</small>
            </button>
          ))}
        </div>
      </section>

      <button type="button" className="vnAdvancedToggle" onClick={() => setAdvanced((value) => !value)}>
        <span>Дополнительно</span><Icon name="chevron" size={18}/>
      </button>

      {advanced && (
        <div className="vnAdvancedPanel">
          {kind === "image" && qualities.length > 1 && <OptionSelect label="Качество" options={qualities} value={quality} onChange={setQuality}/>} 
          {kind === "image" && counts.length > 1 && <OptionSelect label="Количество" options={counts} value={count} onChange={(value) => setCount(Number(value))}/>} 
          {kind === "video" && durations.length > 0 && <OptionSelect label="Длительность" options={durations.map((item) => ({ ...item, label: `${item.label} сек` }))} value={duration} onChange={(value) => setDuration(Number(value))}/>} 
          {kind === "video" && resolutions.length > 1 && <OptionSelect label="Разрешение" options={resolutions} value={resolution} onChange={setResolution}/>} 
          {kind === "video" && modeOptions.length > 1 && <OptionSelect label="Режим" options={modeOptions} value={modeOption} onChange={setModeOption}/>} 
        </div>
      )}

      <button type="button" className="vnGenerateButton" onClick={submit} disabled={!current || generation?.status === "pending" || generation?.status === "processing"}>
        <span>Создать</span><i><Icon name="sparkle" size={18}/>{formatCredits(estimatedCost)} 💋</i>
      </button>
      <p className="vnTokenHint">Магия стоит токенов</p>

      <ResultPanel
        generation={generation}
        onOpen={setViewer}
        onPublish={onFeedReload}
        onSave={() => {}}
        onRepeat={submit}
        onNotice={onNotice}
      />

      {viewer && <GenerationViewer entry={viewer} onClose={() => setViewer(null)}/>} 
    </section>
  );
}

function OptionSelect({ label, options, value, onChange }) {
  return (
    <label className="vnSelectField">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function GenerationViewer({ entry, onClose }) {
  const item = entry?.item;
  const urls = item ? generationResultUrls(item) : [];
  const [index, setIndex] = useState(entry?.index || 0);
  if (!item || !urls.length) return null;
  const safeIndex = Math.min(index, urls.length - 1);
  const url = urls[safeIndex];
  const video = isVideoMedia(item, url);

  return (
    <div className="vnViewer" role="dialog" aria-modal="true">
      <header><div><span>Результат</span>{urls.length > 1 && <small>{safeIndex + 1}/{urls.length}</small>}</div><button type="button" onClick={onClose}><Icon name="close"/></button></header>
      <div className="vnViewerStage">
        {video ? <video src={url} controls autoPlay playsInline/> : <img src={url} alt="Результат"/>}
        {safeIndex > 0 && <button className="prev" type="button" onClick={() => setIndex((value) => value - 1)}><Icon name="back"/></button>}
        {safeIndex < urls.length - 1 && <button className="next" type="button" onClick={() => setIndex((value) => value + 1)}><Icon name="chevron"/></button>}
      </div>
      <footer><p>{publicPrompt(item)}</p><div><button type="button" className="vnGradientButton" onClick={onClose}>Готово</button></div></footer>
    </div>
  );
}

function PromptCard({ item, onUse, onCopy, featured = false }) {
  const preview = item.preview_url || item.image_url || generationPreviewUrls(item)[0];
  const text = item.prompt_text || item.prompt || item.description || "";
  return (
    <article className={`vnPromptCard ${featured ? "featured" : ""}`}>
      {preview ? <img src={preview} alt="" loading="lazy"/> : <span className="vnPromptArt"><Icon name="sparkle" size={24}/></span>}
      <div>
        <header><b>{item.title || "Промпт"}</b><button type="button" onClick={() => onCopy(text)} aria-label="Копировать"><Icon name="bookmark" size={17}/></button></header>
        <p>{text.length > 120 ? `${text.slice(0, 117)}…` : text}</p>
        <footer><span>{item.category || item.model || "AI"}</span><small>{formatCompact(item.uses_count || item.likes_count || 0)}</small><button type="button" onClick={() => onUse(item)}>Использовать<Icon name="chevron" size={14}/></button></footer>
      </div>
    </article>
  );
}

function PromptsScreen({ prompts, loading, onUse, onNotice }) {
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState("popular");
  const [photoPrompt, setPhotoPrompt] = useState("");
  const [photoBusy, setPhotoBusy] = useState(false);
  const fileRef = useRef(null);

  const filtered = useMemo(() => {
    const source = prompts.filter((item) => {
      const text = `${item.title || ""} ${item.prompt_text || item.prompt || ""} ${item.description || ""}`.toLowerCase();
      return !query.trim() || text.includes(query.trim().toLowerCase());
    });
    if (tab === "mine") return source.filter((item) => item.is_mine || item.owner_is_me);
    if (tab === "new") return [...source].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    return [...source].sort((a, b) => Number(b.uses_count || b.likes_count || 0) - Number(a.uses_count || a.likes_count || 0));
  }, [prompts, query, tab]);

  async function copy(value) {
    if (await copyText(value)) onNotice({ type: "success", message: "Промпт скопирован" });
  }

  async function analyzePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setPhotoBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/v1/photo-prompt", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": telegramInitData() },
        body: form,
      });
      if (!response.ok) throw new Error("Не удалось разобрать фото");
      const result = await response.json();
      setPhotoPrompt(result.prompt || "");
      onNotice({ type: "success", message: "Промпт готов" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось создать промпт" });
    } finally {
      setPhotoBusy(false);
    }
  }

  return (
    <section className="vnScreen vnPromptsScreen">
      <div className="vnSearchBar visible">
        <Icon name="search" size={18}/>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск промптов..."/>
        <button type="button"><Icon name="sliders" size={17}/></button>
      </div>

      <div className="vnPromptTabs">
        <button type="button" className={tab === "popular" ? "active" : ""} onClick={() => setTab("popular")}>Популярные</button>
        <button type="button" className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>Новые</button>
        <button type="button" className={tab === "mine" ? "active" : ""} onClick={() => setTab("mine")}>Мои</button>
      </div>

      <section className="vnPhotoPromptTool">
        <div><span><Icon name="camera" size={21}/></span><div><b>Промпт по фото</b><p>Загрузи референс — AI восстановит описание.</p></div></div>
        <button type="button" onClick={() => fileRef.current?.click()} disabled={photoBusy}>{photoBusy ? "Анализ..." : "Загрузить"}</button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={analyzePhoto}/>
        {photoPrompt && <div className="vnPhotoPromptResult"><p>{photoPrompt}</p><div><button type="button" onClick={() => copy(photoPrompt)}>Копировать</button><button type="button" className="vnGradientButton" onClick={() => onUse({ title: "Промпт по фото", prompt_text: photoPrompt })}>Создать</button></div></div>}
      </section>

      {loading ? <Loading label="Загружаем идеи"/> : filtered.length ? (
        <div className="vnPromptList">
          {filtered.map((item, index) => <PromptCard key={item.id || index} item={item} featured={index === 0} onUse={onUse} onCopy={copy}/>) }
        </div>
      ) : <Empty icon="prompt" title="Ничего не найдено" text="Измени запрос или открой популярные промпты."/>}
    </section>
  );
}

function ProfileScreen({ user, history, myFeed, referrals, onNavigate, onTopup, onNotice }) {
  const [tab, setTab] = useState("posts");
  const [viewer, setViewer] = useState(null);
  const posts = myFeed.filter((item) => generationPreviewUrls(item).length > 0);
  const saved = history.filter((item) => item.is_prompt_library || item.is_public_feed);
  const visible = tab === "posts" ? posts : tab === "history" ? history : saved;

  async function shareReferral() {
    const link = referrals?.referral_link || user?.referral_link;
    if (!link) {
      onNotice({ type: "warning", message: "Реферальная ссылка пока недоступна" });
      return;
    }
    if (await copyText(link)) onNotice({ type: "success", message: "Реферальная ссылка скопирована" });
  }

  return (
    <section className="vnScreen vnProfileScreen">
      <article className="vnProfileHero">
        <div className="vnProfileGlow"/>
        <header><Avatar user={user} size="large"/><button type="button"><Icon name="sliders" size={19}/></button></header>
        <h2>{user.full_name || user.username || "Creator"}</h2>
        <p>@{user.username || "apix_creator"}</p>
        <span className="vnProBadge"><Icon name="crown" size={14}/>PRO CREATOR</span>
        <div className="vnProfileStats">
          <div><b>{posts.length}</b><span>Создано</span></div>
          <div><b>{formatCompact(referrals?.counts?.l1 || 0)}</b><span>Партнёры</span></div>
          <div><b>{formatCredits(user.credits)}</b><span>Токены</span></div>
        </div>
        <button type="button" className="vnGradientButton" onClick={onTopup}><Icon name="wallet" size={18}/>Пополнить баланс</button>
      </article>

      <div className="vnProfileQuick">
        <button type="button" onClick={() => setTab("history")}><Icon name="history"/><span>История</span></button>
        <button type="button" onClick={shareReferral}><Icon name="share"/><span>Партнёрам</span></button>
        <button type="button" onClick={() => openTelegramLink(user.support_url || "https://t.me/apix_ai_bot")}><Icon name="prompt"/><span>Поддержка</span></button>
        <button type="button" onClick={() => onNavigate("create")}><Icon name="sparkle"/><span>Создать</span></button>
      </div>

      <div className="vnProfileTabs">
        <button type="button" className={tab === "posts" ? "active" : ""} onClick={() => setTab("posts")}>Публикации</button>
        <button type="button" className={tab === "saved" ? "active" : ""} onClick={() => setTab("saved")}>Сохранённое</button>
        <button type="button" className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>История</button>
      </div>

      {visible.length ? (
        <div className="vnProfileGrid">
          {visible.map((item, index) => {
            const url = generationPreviewUrls(item)[0];
            return (
              <button key={item.id || index} type="button" onClick={() => setViewer({ item, index: 0 })}>
                {isVideoMedia(item, url) ? <video src={url} muted playsInline preload="metadata"/> : <img src={url} alt="" loading="lazy"/>}
                {item.status && item.status !== "done" && <span>{item.status === "failed" ? "Ошибка" : "В работе"}</span>}
              </button>
            );
          })}
        </div>
      ) : <Empty icon="grid" title="Пока пусто" text="Созданные работы появятся здесь."/>}

      {viewer && <GenerationViewer entry={viewer} onClose={() => setViewer(null)}/>} 
    </section>
  );
}

function TopupModal({ onClose, onNotice, onPaid }) {
  const plans = useResource(() => api(`/plans?_=${Date.now()}`, { cache: "no-store" }), []);
  const methods = useResource(() => api(`/payment-methods?_=${Date.now()}`, { cache: "no-store" }), []);
  const [plan, setPlan] = useState("");
  const [method, setMethod] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!plan && plans.data[0]?.key) setPlan(plans.data[0].key);
  }, [plans.data, plan]);

  useEffect(() => {
    if (!method && methods.data[0]) setMethod(methods.data[0]);
  }, [methods.data, method]);

  async function pay() {
    if (!plan || !method || busy) return;
    setBusy(true);
    try {
      const endpoint = method === "crypto" ? "/topup/crypto" : method === "stars" ? "/topup/stars" : method === "lava" ? "/topup/lava" : "/topup/tbank";
      const result = await api(endpoint, { method: "POST", body: JSON.stringify({ plan_key: plan }) });
      const url = result.invoice_link || result.pay_url;
      if (!url) throw new Error("Платёжная ссылка не получена");
      openTelegramLink(url);
      onPaid?.();
      onClose();
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось открыть оплату" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="vnModalBackdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="vnModal" role="dialog" aria-modal="true" aria-label="Пополнение баланса">
        <header><div><span><Icon name="crown" size={19}/></span><div><h2>Пополнить баланс</h2><p>Больше генераций, выше качество.</p></div></div><button type="button" onClick={onClose}><Icon name="close"/></button></header>
        {plans.loading ? <Loading/> : <div className="vnPlanGrid">{plans.data.map((item) => <button key={item.key} type="button" className={plan === item.key ? "active" : ""} onClick={() => setPlan(item.key)}><b>{item.title || item.label}</b><span>{item.credits} 💋</span><small>{item.price_rub_display || `${item.price_rub || 0} ₽`}</small></button>)}</div>}
        <div className="vnPaymentMethods">{methods.data.map((item) => <button key={item} type="button" className={method === item ? "active" : ""} onClick={() => setMethod(item)}>{item === "tbank" ? "Т-Банк" : item === "stars" ? "Stars" : item === "crypto" ? "Crypto" : "Lava"}</button>)}</div>
        <button type="button" className="vnGenerateButton" onClick={pay} disabled={!plan || !method || busy}><span>{busy ? "Открываем..." : "Продолжить"}</span><i><Icon name="external" size={17}/></i></button>
      </section>
    </div>
  );
}

export default function VelvetApp() {
  const [screen, setScreen] = useState("feed");
  const [notice, setNotice] = useState(null);
  const [topupOpen, setTopupOpen] = useState(false);
  const [preset, setPreset] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [pollId, setPollId] = useState(null);

  const me = useResource(() => api("/me"), FALLBACK_USER);
  const imageModels = useResource(() => api("/models/image").then((value) => asItems(value).length ? asItems(value) : value), []);
  const videoModels = useResource(() => api("/models/video").then((value) => asItems(value).length ? asItems(value) : value), []);
  const feed = useResource(() => api("/feed?source=recent&limit=60").then(asItems), []);
  const prompts = useResource(() => api("/prompts?limit=60").then(asItems), []);
  const history = useResource(() => api("/history?limit=60").then(asItems), []);
  const myFeed = useResource(() => api("/me/feed?limit=100").then(asItems), []);
  const referrals = useResource(() => api("/referrals"), {});

  const telegramProfile = telegramUser();
  const user = useMemo(() => ({
    ...FALLBACK_USER,
    ...(me.data || {}),
    username: me.data?.username || telegramProfile?.username || "",
    full_name: me.data?.full_name || [telegramProfile?.first_name, telegramProfile?.last_name].filter(Boolean).join(" ") || "",
    photo_url: me.data?.photo_url || telegramProfile?.photo_url || "",
  }), [me.data, telegramProfile]);

  useEffect(() => {
    prepareTelegram();
    document.documentElement.dataset.theme = "velvet-neon";
  }, []);

  useEffect(() => {
    if (!pollId) return undefined;
    let failures = 0;
    const timer = window.setInterval(async () => {
      try {
        const result = await api(`/generations/${pollId}`);
        failures = 0;
        setGeneration(result);
        if (result.status === "done" || result.status === "failed") {
          window.clearInterval(timer);
          setPollId(null);
          me.reload();
          history.reload();
        }
      } catch (error) {
        failures += 1;
        if (failures >= 5) {
          window.clearInterval(timer);
          setPollId(null);
          setNotice({ type: "error", message: "Статус временно недоступен. Проверь историю позже." });
        }
      }
    }, 3500);
    return () => window.clearInterval(timer);
  }, [pollId]);

  useEffect(() => {
    const initData = telegramInitData();
    if (!initData) return undefined;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws/generations`);
    socket.addEventListener("open", () => socket.send(JSON.stringify({ type: "auth", init_data: initData })));
    socket.addEventListener("message", (event) => {
      try {
        const next = generationFromRealtime(JSON.parse(event.data));
        if (!next) return;
        setGeneration((current) => !current?.id || Number(current.id) === Number(next.id) ? { ...(current || {}), ...next } : current);
        if (next.status === "done" || next.status === "failed") {
          setPollId((id) => Number(id) === Number(next.id) ? null : id);
          me.reload();
          history.reload();
        }
      } catch {}
    });
    return () => socket.close();
  }, []);

  async function generate({ kind, payload, remix }) {
    setGeneration({ id: 0, status: "pending", gen_type: kind });
    try {
      let result;
      if (remix) {
        const body = {
          model: payload.model,
          prompt: "",
          mode: payload.mode || "text",
          duration: payload.duration,
          aspect_ratio: payload.aspect_ratio,
          resolution: payload.resolution,
          image_url: payload.image_url,
          reference_urls: payload.reference_urls || [],
          grok_mode: payload.grok_mode,
          quality: payload.quality,
          count: payload.count,
        };
        result = await api(`/feed/${remix.id}/remix`, { method: "POST", body: JSON.stringify(body) });
      } else {
        const endpoint = kind === "video" ? "/generate/video" : "/generate/image";
        const body = kind === "video"
          ? {
              model: payload.model,
              prompt: payload.prompt,
              prompt_id: payload.prompt_id || null,
              mode: payload.mode,
              duration: payload.duration,
              aspect_ratio: payload.aspect_ratio,
              resolution: payload.resolution,
              image_url: payload.image_url,
              reference_urls: payload.reference_urls || [],
              grok_mode: payload.grok_mode,
            }
          : {
              model: payload.model,
              prompt: payload.prompt,
              prompt_id: payload.prompt_id || null,
              aspect_ratio: payload.aspect_ratio,
              quality: payload.quality,
              count: payload.count,
              reference_url: payload.reference_url,
              reference_urls: payload.reference_urls || [],
            };
        result = await api(endpoint, { method: "POST", body: JSON.stringify(body) });
      }
      setGeneration(result);
      setPollId(result.id);
      setPreset(null);
      me.reload();
      telegram()?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      setGeneration({ id: 0, status: "failed", gen_type: kind, error: error.message });
      if (error.status === 402) setTopupOpen(true);
      else setNotice({ type: "error", message: error.message || "Не удалось запустить генерацию" });
    }
  }

  function usePrompt(item) {
    setPreset({
      id: `prompt-${item.id || Date.now()}`,
      prompt: item.prompt_text || item.prompt || item.description || "",
      promptId: item.id || null,
      modelKey: item.model || item.model_key || "",
      kind: item.kind === "video" || item.gen_type === "video" ? "video" : "image",
    });
    setScreen("create");
  }

  return (
    <div className="vnApp">
      <div className="vnAmbient one"/><div className="vnAmbient two"/><div className="vnNoise"/>
      <AppHeader screen={screen} user={user} onSearch={() => setScreen("feed")} onTopup={() => setTopupOpen(true)}/>

      {!telegramInitData() && (
        <div className="vnDemoBanner"><Icon name="sparkle" size={16}/><span>Демо-режим: открой Mini App из Telegram для генераций и оплаты.</span></div>
      )}

      <main>
        {screen === "feed" && <FeedScreen feed={feed.data} loading={feed.loading} onReload={feed.reload} onNavigate={setScreen} onPreset={setPreset} onNotice={setNotice}/>} 
        {screen === "create" && <CreateScreen user={user} imageModels={imageModels.data} videoModels={videoModels.data} preset={preset} generation={generation} onGenerate={generate} onClearPreset={() => setPreset(null)} onTopup={() => setTopupOpen(true)} onNotice={setNotice} onFeedReload={() => { feed.reload(); myFeed.reload(); }}/>} 
        {screen === "prompts" && <PromptsScreen prompts={prompts.data} loading={prompts.loading} onUse={usePrompt} onNotice={setNotice}/>} 
        {screen === "profile" && <ProfileScreen user={user} history={history.data} myFeed={myFeed.data} referrals={referrals.data} onNavigate={setScreen} onTopup={() => setTopupOpen(true)} onNotice={setNotice}/>} 
      </main>

      <BottomNavigation screen={screen} onNavigate={setScreen}/>
      <Notice notice={notice} onClose={() => setNotice(null)}/>
      {topupOpen && <TopupModal onClose={() => setTopupOpen(false)} onNotice={setNotice} onPaid={me.reload}/>} 
    </div>
  );
}
