import React, { useEffect, useMemo, useState } from "react";
import Icon from "./icons.jsx";
import {
  api,
  copyText,
  feedPreviewCandidates,
  formatCompact,
  generationPreviewUrls,
  isVideoMedia,
  publicPrompt,
} from "./api.js";
import {
  EmptyState,
  Loading,
  MediaViewer,
  ProgressiveMedia,
  triggerHaptic,
} from "./components.jsx";

const SORT_FILTERS = [
  ["for-you", "Для тебя"],
  ["new", "Новые"],
  ["popular", "Популярные"],
];

const TYPE_FILTERS = [
  ["all", "Все", null],
  ["image", "Фото", "image"],
  ["video", "Видео", "video"],
  ["mine", "Мои", "user"],
];

function engagementScore(item) {
  return Number(item.likes_count || 0)
    + Number(item.remixes || 0) * 3
    + Number(item.shares_count || 0) * 2;
}

function FeedCard({ item, index, onOpen, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(Boolean(item.liked_by_me));
  const [likes, setLikes] = useState(Number(item.likes_count || 0));
  const [busy, setBusy] = useState(false);
  const previewCount = Math.max(1, generationPreviewUrls(item).length);
  const primarySources = feedPreviewCandidates(item, 0);
  const video = isVideoMedia(item, primarySources[0]);
  const shape = ["portrait", "portrait", "square", "tall", "tall", "wide"][index % 6];

  async function like(event) {
    event.stopPropagation();
    if (busy || liked) return;
    setBusy(true);
    try {
      const result = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLiked(true);
      setLikes(Number(result.likes_count ?? likes + 1));
      triggerHaptic("light");
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поставить лайк" });
    } finally {
      setBusy(false);
    }
  }

  async function share(event) {
    event.stopPropagation();
    try {
      const result = await api(`/feed/${item.id}/link`);
      if (!await copyText(result.link || "")) throw new Error("Не удалось скопировать ссылку");
      onNotice({ type: "success", message: "Ссылка скопирована" });
      triggerHaptic("medium");
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поделиться" });
    }
  }

  async function remove(event) {
    event.stopPropagation();
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
    <article className={`cxFeedCard cxFeedCard--${shape}`}>
      <ProgressiveMedia
        item={item}
        index={0}
        sources={primarySources}
        className="cxFeedCard__media"
        onClick={() => onOpen(item, 0)}
        compact
      />
      <span className="cxFeedCard__shade"/>

      <header className="cxFeedCard__top">
        <span>@{item.author || "creator"}</span>
        <div>
          {previewCount > 1 && <small>{previewCount}</small>}
          <b>{video ? "Видео" : "Фото"}</b>
          {item.is_mine && <button type="button" onClick={remove} aria-label="Удалить"><Icon name="more" size={17}/></button>}
        </div>
      </header>

      {video && <span className="cxFeedCard__play"><Icon name="play" size={19}/></span>}

      <footer className="cxFeedCard__footer">
        <div className="cxFeedCard__statbar">
          <button type="button" className={liked ? "liked" : ""} onClick={like} disabled={busy} aria-label="Нравится">
            <Icon name="heart" size={16}/><span>{formatCompact(likes)}</span>
          </button>
          <span><Icon name="eye" size={16}/>{formatCompact(item.views_count || item.remixes)}</span>
          <button type="button" onClick={(event) => { event.stopPropagation(); onRemix(item); }} aria-label="Повторить">
            <Icon name="reload" size={16}/><span>{formatCompact(item.remixes)}</span>
          </button>
        </div>
        <button className="cxFeedCard__share" type="button" onClick={share} aria-label="Поделиться"><Icon name="share" size={17}/></button>
      </footer>
    </article>
  );
}

export default function FeedScreen({ feed, loading, onReload, onNavigate, onPreset, onNotice, searchRequested = 0 }) {
  const [sort, setSort] = useState("for-you");
  const [type, setType] = useState("all");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [viewer, setViewer] = useState(null);
  const [items, setItems] = useState(feed);

  useEffect(() => setItems(feed), [feed]);
  useEffect(() => {
    if (!searchRequested) return;
    setSearchOpen(true);
  }, [searchRequested]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let result = items.filter((item) => {
      if (needle) {
        const haystack = `${item.author || ""} ${item.model || ""} ${publicPrompt(item)}`.toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      const first = generationPreviewUrls(item)[0] || "";
      if (type === "image" && isVideoMedia(item, first)) return false;
      if (type === "video" && !isVideoMedia(item, first)) return false;
      if (type === "mine" && !item.is_mine) return false;
      return true;
    });

    if (sort === "new") {
      result = [...result].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    }
    if (sort === "popular") {
      result = [...result].sort((a, b) => engagementScore(b) - engagementScore(a));
    }
    return result;
  }, [items, query, sort, type]);

  function remix(item) {
    onPreset({
      id: `remix-${item.id}-${Date.now()}`,
      remix: item,
      kind: item.gen_type === "video" ? "video" : "image",
      hiddenPrompt: true,
    });
    onNavigate("create");
  }

  async function likeFromViewer(item) {
    try {
      await api(`/feed/${item.id}/like`, { method: "POST" });
      setItems((current) => current.map((value) => value.id === item.id
        ? { ...value, liked_by_me: true, likes_count: Number(value.likes_count || 0) + 1 }
        : value));
      onNotice({ type: "success", message: "Добавлено в понравившиеся" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поставить лайк" });
    }
  }

  async function shareFromViewer(item) {
    try {
      const result = await api(`/feed/${item.id}/link`);
      if (!await copyText(result.link || "")) throw new Error("Не удалось скопировать ссылку");
      onNotice({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поделиться" });
    }
  }

  return (
    <section className="cxScreen cxFeedScreen">
      <div className="cxFilterGroup">
        <div className="cxFilterRail cxFilterRail--primary">
          {SORT_FILTERS.map(([key, label]) => (
            <button key={key} type="button" className={sort === key ? "active" : ""} onClick={() => setSort(key)}>{label}</button>
          ))}
        </div>
        <button className="cxFilterIcon" type="button" onClick={() => setSearchOpen((value) => !value)} aria-label="Поиск и фильтры">
          <Icon name="sliders" size={19}/>
        </button>
      </div>

      <div className="cxFilterRail cxFilterRail--secondary">
        {TYPE_FILTERS.map(([key, label, icon]) => (
          <button key={key} type="button" className={type === key ? "active" : ""} onClick={() => setType(key)}>
            {icon && <Icon name={icon} size={14}/>}<span>{label}</span>{key === "mine" && <small>{items.filter((item) => item.is_mine).length}</small>}
          </button>
        ))}
      </div>

      {searchOpen && (
        <label className="cxSearchField">
          <Icon name="search" size={19}/>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Автор, модель или идея" autoFocus/>
          {query && <button type="button" onClick={() => setQuery("")}><Icon name="close" size={16}/></button>}
        </label>
      )}

      {loading ? <Loading label="Собираем ленту"/> : filtered.length ? (
        <div className="cxMasonry">
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
        <EmptyState
          icon="image"
          title="Здесь пока тихо"
          text="Создай первую работу или измени фильтр."
          action={<button className="cxPrimaryButton" type="button" onClick={() => onNavigate("create")}><Icon name="sparkle" size={18}/>Создать</button>}
        />
      )}

      <button className="cxRefreshButton" type="button" onClick={onReload}><Icon name="reload" size={17}/>Обновить ленту</button>

      {viewer && (
        <MediaViewer
          entry={viewer}
          onClose={() => setViewer(null)}
          onLike={likeFromViewer}
          onRemix={(item) => { setViewer(null); remix(item); }}
          onShare={shareFromViewer}
        />
      )}
    </section>
  );
}
