import React, { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./icons.jsx";
import { fallbackArtFor } from "./fallbackArtV2.js";
import {
  feedDisplayCandidates,
  formatCompact,
  formatCredits,
  generationPreviewUrls,
  isVideoMedia,
  publicPrompt,
  telegram,
  telegramUser,
} from "./api.js";

export function Avatar({ user, size = "md" }) {
  const [failed, setFailed] = useState(false);
  const tgUser = telegramUser();
  const name = user?.full_name || user?.username || tgUser?.first_name || "APIX";
  const photo = user?.photo_url || tgUser?.photo_url;
  const initial = String(name).trim().slice(0, 1).toUpperCase();
  return <span className={`cxAvatar cxAvatar--${size}`} aria-label={name}>{photo && !failed ? <img src={photo} alt="" onError={() => setFailed(true)}/> : <span>{initial}</span>}</span>;
}

export function AppHeader({ screen, user, onCreate, onTopup }) {
  const embedded = Boolean(telegram()?.initData);
  const title = { feed: "Лента", create: "Создать", prompts: "Промпты", profile: "Профиль" }[screen] || "Лента";
  return <>
    <header className={`cxBrandBar ${embedded ? "cxBrandBar--embedded" : ""}`}>
      {!embedded && <span className="cxWordmark" aria-label="APIX"><span>APIX</span><i>✦</i></span>}
      <div className="cxBrandBar__actions">
        <Avatar user={user} size="sm"/>
        <button className="cxBalancePill" type="button" onClick={onTopup} aria-label="Пополнить баланс"><Icon name="sparkle" size={16}/><span>{formatCredits(user?.credits)}</span><b><Icon name="plus" size={15}/></b></button>
      </div>
    </header>
    <section className={`cxPageHero cxPageHero--${screen}`}>
      <div className="cxPageHero__title"><span className="cxHeroSpark"><Icon name="sparkle" size={17}/></span><h1>{title}<i/></h1></div>
      {screen === "feed" && <button className="cxCreateQuick" type="button" onClick={onCreate}><Icon name="plus" size={19}/><span>Создать</span></button>}
    </section>
  </>;
}

export function BottomNavigation({ screen, onNavigate }) {
  const items = [["feed","home","Лента"],["create","plus","Создать"],["orb","sparkle",""],["prompts","prompt","Промпты"],["profile","user","Профиль"]];
  return <nav className="cxBottomNav" aria-label="Основная навигация">{items.map(([id, icon, label]) => id === "orb" ? <button key={id} className="cxOrbButton" type="button" onClick={() => onNavigate("create")} aria-label="Создать"><span className="cxOrbButton__glow"/><span className="cxOrbButton__core"><Icon name="sparkle" size={27}/></span></button> : <button key={id} type="button" className={screen === id ? "active" : ""} onClick={() => onNavigate(id)}><span><Icon name={icon} size={22}/></span><small>{label}</small></button>)}</nav>;
}

export function Loading({ label = "Загружаем" }) { return <div className="cxLoading" role="status"><span className="cxLoading__orb"><Icon name="sparkle" size={24}/></span><b>{label}</b><i/><i/><i/></div>; }
export function EmptyState({ icon = "sparkle", title, text, action }) { return <div className="cxEmpty"><span><Icon name={icon} size={30}/></span><h2>{title}</h2>{text && <p>{text}</p>}{action}</div>; }

export function Notice({ notice, onClose }) {
  useEffect(() => { if (!notice) return undefined; const timer = window.setTimeout(onClose, 3600); return () => window.clearTimeout(timer); }, [notice, onClose]);
  if (!notice) return null;
  return <div className={`cxNotice cxNotice--${notice.type || "info"}`} role={notice.type === "error" ? "alert" : "status"}><Icon name={notice.type === "error" ? "close" : "sparkle"} size={18}/><span>{notice.message}</span><button type="button" onClick={onClose}><Icon name="close" size={16}/></button></div>;
}

export function MediaPlaceholder({ item, compact = false, index = 0 }) {
  const prompt = publicPrompt(item);
  return <div className={`cxMediaPlaceholder ${compact ? "compact" : ""}`}><img src={fallbackArtFor(item?.id || index)} alt=""/><span className="cxMediaPlaceholder__shade"/>{!compact && <><b>Работа сохранена</b><p>{prompt ? prompt.slice(0, 90) : "Превью пока недоступно"}</p></>}</div>;
}

export function ProgressiveMedia({ item, index = 0, sources = [], className = "", onClick, controls = false, autoPlay = false, compact = false }) {
  const fallback = useMemo(() => fallbackArtFor(item?.id || index), [item?.id, index]);
  const unique = useMemo(() => [...new Set([...sources.filter(Boolean), fallback])], [sources, fallback]);
  const [sourceIndex, setSourceIndex] = useState(0);
  const source = unique[sourceIndex];
  const isFallback = source === fallback;
  const video = !isFallback && isVideoMedia(item, source);
  const tone = Math.abs(Number(item?.id || index || 0)) % 6;
  useEffect(() => setSourceIndex(0), [item?.id, index, unique.join("|")]);
  function fail() { setSourceIndex((value) => Math.min(value + 1, unique.length - 1)); }
  if (!source) return <MediaPlaceholder item={item} compact={compact} index={index}/>;
  const Wrapper = onClick ? "button" : "div";
  return <Wrapper className={`cxProgressiveMedia ${isFallback ? "is-fallback" : ""} ${className}`} data-fallback-tone={tone} type={onClick ? "button" : undefined} onClick={onClick}>{video ? <video src={source} muted={!controls} controls={controls} autoPlay={autoPlay} playsInline preload="metadata" onError={fail}/> : <img src={source} alt={isFallback ? "Декоративная обложка работы" : ""} loading={autoPlay ? "eager" : "lazy"} decoding="async" onError={fail}/>} {video && !controls && <span className="cxMediaPlay"><Icon name="play" size={20}/></span>}</Wrapper>;
}

export function MediaViewer({ entry, onClose, onLike, onRemix, onShare }) {
  const item = entry?.item;
  const previewCount = Math.max(1, generationPreviewUrls(item).length);
  const [index, setIndex] = useState(entry?.index || 0);
  const touch = useRef(null);
  useEffect(() => setIndex(entry?.index || 0), [entry?.item?.id, entry?.index]);
  useEffect(() => { if (!item) return undefined; const previous = document.body.style.overflow; document.body.style.overflow = "hidden"; const keydown = (event) => { if (event.key === "Escape") onClose(); if (event.key === "ArrowLeft") setIndex((value) => Math.max(0, value - 1)); if (event.key === "ArrowRight") setIndex((value) => Math.min(previewCount - 1, value + 1)); }; window.addEventListener("keydown", keydown); return () => { document.body.style.overflow = previous; window.removeEventListener("keydown", keydown); }; }, [item, previewCount, onClose]);
  if (!item) return null;
  const safeIndex = Math.min(index, previewCount - 1);
  const prompt = publicPrompt(item);
  const sources = feedDisplayCandidates(item, safeIndex);
  function touchStart(event) { touch.current = event.touches?.[0]?.clientX ?? null; }
  function touchEnd(event) { const start = touch.current; const end = event.changedTouches?.[0]?.clientX; touch.current = null; if (start == null || end == null || Math.abs(end - start) < 45) return; if (end < start && safeIndex < previewCount - 1) setIndex((value) => value + 1); if (end > start && safeIndex > 0) setIndex((value) => value - 1); }
  return <div className="cxViewer" role="dialog" aria-modal="true"><ProgressiveMedia item={item} index={safeIndex} sources={sources} className="cxViewer__media" controls autoPlay/><div className="cxViewer__shade"/><header className="cxViewer__header"><button type="button" onClick={onClose} aria-label="Закрыть"><Icon name="close" size={26}/></button><div><Avatar user={{ username: item.author }} size="sm"/><span>@{item.author || "creator"}</span><i/></div><button type="button" onClick={() => onShare(item)} aria-label="Поделиться"><Icon name="share" size={22}/></button></header><div className="cxViewer__gesture" onTouchStart={touchStart} onTouchEnd={touchEnd}>{safeIndex > 0 && <button type="button" className="prev" onClick={() => setIndex((value) => value - 1)}><Icon name="back"/></button>}{safeIndex < previewCount - 1 && <button type="button" className="next" onClick={() => setIndex((value) => value + 1)}><Icon name="chevron"/></button>}</div><section className="cxViewer__content"><span className="cxViewer__tag"><Icon name="sparkle" size={14}/>{item.model || (item.gen_type === "video" ? "Видео" : "Фото")}</span><h2>{prompt ? prompt.slice(0, 60) : "Новая работа"}</h2><p>{item.gen_type === "video" ? "Видео" : "Кинематик"} <i/> {item.aspect_ratio || "9:16"}</p><div className="cxViewer__stats"><span><Icon name="heart" size={16}/>{formatCompact(item.likes_count)}</span><span><Icon name="eye" size={16}/>{formatCompact(item.views_count || item.remixes)}</span><span><Icon name="reload" size={16}/>{formatCompact(item.remixes)}</span></div><div className="cxViewer__actions"><button type="button" onClick={() => onLike(item)}><Icon name="heart" size={19}/>Нравится</button><button type="button" className="primary" onClick={() => onRemix(item)}><Icon name="sparkle" size={19}/>Повторить</button><button type="button" onClick={() => onShare(item)}><Icon name="share" size={19}/>Поделиться</button></div></section></div>;
}

export function DemoBanner() { if (telegramUser()) return null; return <div className="cxDemoBanner"><Icon name="sparkle" size={17}/><span>Демо-режим. Генерации и платежи доступны внутри Telegram.</span></div>; }
export function triggerHaptic(type = "light") { telegram()?.HapticFeedback?.impactOccurred?.(type); }
