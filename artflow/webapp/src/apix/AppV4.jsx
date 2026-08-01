import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  haptic,
  isTelegramRuntime,
  listItems,
  notify,
  openTelegramLink,
  photoPrompt,
  setupTelegramChrome,
  tgUser,
  uploadReference,
} from "./api.js";
import { demoFeed, demoImageModels, demoPlans, demoPrompts, demoUser, demoVideoModels } from "./demoData.js";

const BUILD_ID = "20260801-apix-v4-clean-shell";
const ACTIVE_STATUSES = new Set(["pending", "processing", "queued", "running"]);
const FINISHED_STATUSES = new Set(["done", "completed", "success"]);
const FAILED_STATUSES = new Set(["failed", "error", "cancelled"]);
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const REFERENCE_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const PHOTO_PROMPT_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

window.__APIX_MINIAPP_BUILD_ID__ = BUILD_ID;

function cx(...items) {
  return items.filter(Boolean).join(" ");
}

function Icon({ name }) {
  const common = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.8", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };
  const paths = {
    search: <><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /></>,
    home: <><path d="m3 11 9-7 9 7" /><path d="M5.5 10.5V20h13v-9.5" /><path d="M9.5 20v-5h5v5" /></>,
    plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
    sparkle: <><path d="M12 2.8 14.4 9l6.2 3-6.2 3L12 21.2 9.6 15l-6.2-3 6.2-3L12 2.8Z" /><path d="M19 3v4" /><path d="M17 5h4" /></>,
    prompt: <><path d="M5 5h14v10H8l-3 3V5Z" /><path d="M8 9h8" /><path d="M8 12h5" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4.5 21a7.5 7.5 0 0 1 15 0" /></>,
    image: <><rect x="4" y="5" width="16" height="14" rx="3" /><path d="m7 16 4-4 3 3 2-2 3 3" /><circle cx="9" cy="9" r="1" /></>,
    video: <><rect x="4" y="6" width="13" height="12" rx="3" /><path d="m17 10 4-2v8l-4-2" /></>,
    heart: <path d="M20.4 6.6a5 5 0 0 0-7.1 0L12 7.9l-1.3-1.3a5 5 0 1 0-7.1 7.1L12 22l8.4-8.3a5 5 0 0 0 0-7.1Z" />,
    eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
    repeat: <><path d="m17 2 4 4-4 4" /><path d="M3 11V9a3 3 0 0 1 3-3h15" /><path d="m7 22-4-4 4-4" /><path d="M21 13v2a3 3 0 0 1-3 3H3" /></>,
    bookmark: <path d="M6 4h12v17l-6-3-6 3V4Z" />,
    copy: <><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" /></>,
    close: <><path d="M6 6l12 12" /><path d="M18 6 6 18" /></>,
  };
  return <svg className="v4Icon" {...common}>{paths[name] || paths.sparkle}</svg>;
}

function modelKey(model) {
  return model?.key || model?.model_key || model?.id || model?.value || "";
}
function modelName(model) {
  return model?.display_name || model?.name || model?.title || modelKey(model) || "APIX Model";
}
function modelCost(model) {
  return Number(model?.cost_credits ?? model?.credits ?? model?.price_credits ?? 0);
}
function mediaUrls(item) {
  const out = [];
  for (const field of ["preview_urls", "result_urls", "media_urls"]) {
    if (Array.isArray(item?.[field])) out.push(...item[field].filter(Boolean));
  }
  for (const field of ["preview_url", "result_url", "image_url", "video_url", "cover_url"]) {
    if (item?.[field]) out.push(item[field]);
  }
  return [...new Set(out)];
}
function playableVideo(url = "") {
  return /\.(mp4|mov|webm)(?:$|\?)/i.test(url);
}
function isVideo(item, url = "") {
  return item?.gen_type === "video" || playableVideo(url);
}
function compact(value) {
  const n = Number(value || 0);
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`;
  return String(n);
}

function normalizeFileType(file) {
  return String(file?.type || "").split(";", 1)[0].toLowerCase();
}

function imageUploadError(file, allowedTypes) {
  if (!file) return "Файл не выбран";
  if (file.size > MAX_UPLOAD_BYTES) return "Файл слишком большой. Максимум 20 МБ.";
  const type = normalizeFileType(file);
  if (allowedTypes.has(type)) return "";
  if (type === "image/heic" || type === "image/heif") {
    return "Фото в HEIC пока не поддерживается. Сохрани его как JPG или PNG и попробуй снова.";
  }
  return "Поддерживаются только JPG, PNG, WebP" + (allowedTypes.has("image/gif") ? " и GIF." : ".");
}

function queryFeedId() {
  const value = new URLSearchParams(window.location.search).get("feed");
  if (!value || !/^[1-9]\\d*$/.test(value)) return null;
  return Number(value);
}

function useV4Data() {
  const [state, setState] = useState({ user: demoUser, feed: demoFeed, prompts: demoPrompts, imageModels: demoImageModels, videoModels: demoVideoModels, history: [], plans: demoPlans, loading: true, demo: true });
  const reload = useCallback(async () => {
    setState((current) => ({ ...current, loading: true }));
    const calls = await Promise.allSettled([
      api("/me"),
      api("/feed?source=recent&limit=60"),
      api("/prompts?source=popular&limit=30"),
      api("/models/image"),
      api("/models/video"),
      api("/history?limit=40"),
      api("/plans"),
    ]);
    const [user, feed, prompts, imageModels, videoModels, history, plans] = calls;
    const anyReal = calls.some((item) => item.status === "fulfilled");
    setState({
      user: user.status === "fulfilled" ? { ...demoUser, ...user.value } : demoUser,
      feed: feed.status === "fulfilled" ? listItems(feed.value) : demoFeed,
      prompts: prompts.status === "fulfilled" ? listItems(prompts.value) : demoPrompts,
      imageModels: imageModels.status === "fulfilled" ? listItems(imageModels.value) : demoImageModels,
      videoModels: videoModels.status === "fulfilled" ? listItems(videoModels.value) : demoVideoModels,
      history: history.status === "fulfilled" ? listItems(history.value) : [],
      plans: plans.status === "fulfilled" ? listItems(plans.value) : demoPlans,
      loading: false,
      demo: !anyReal || !isTelegramRuntime(),
    });
  }, []);
  useEffect(() => { reload(); }, [reload]);
  return { ...state, reload };
}

function Header({ user, onProfile, onTopup, onSearch }) {
  const tgu = tgUser();
  const photo = user?.photo_url || tgu?.photo_url || "";
  const initial = (user?.full_name || user?.username || tgu?.first_name || "A").trim().slice(0, 1).toUpperCase();
  return (
    <header className="v4Header">
      <button className="v4Circle" type="button" onClick={onSearch} aria-label="Поиск"><Icon name="search" /></button>
      <div className="v4Logo">APIX<span /></div>
      <div className="v4HeadActions">
        <button className="v4Balance" type="button" onClick={onTopup}><Icon name="sparkle" />{compact(user?.credits)}</button>
        <button className="v4Avatar" type="button" onClick={onProfile}>{photo ? <img src={photo} alt="" /> : initial}</button>
      </div>
    </header>
  );
}

function FeedCard({ item, index, onOpen, onLike, onRemix, onShare }) {
  const src = mediaUrls(item)[0] || "";
  const video = isVideo(item, src);
  const author = item.author || item.username || item.user?.username || "apix";
  return (
    <article className={cx("v4Card", index % 4 === 0 && "v4Tall", index % 5 === 1 && "v4Compact")}>
      <button className="v4CardMedia" type="button" onClick={() => onOpen(item)}>
        {src ? (playableVideo(src) ? <video src={src} muted playsInline preload="metadata" /> : <img src={src} alt="" loading={index < 2 ? "eager" : "lazy"} decoding="async" />) : <div className="v4ArtFallback" />}
        <span className="v4Badge">{index === 0 ? "Тренд" : video ? "Видео" : "Фото"}</span>
        {video && <span className="v4VideoTime">0:{12 + index}</span>}
      </button>
      <div className="v4CardInfo">
        <div className="v4Author">@{author}</div>
        <p>{item.prompt || item.title || "Премиальная генерация APIX"}</p>
        <div className="v4Actions">
          <button type="button" onClick={() => onLike(item)}><Icon name="heart" />{compact(item.likes_count)}</button>
          <button type="button" onClick={() => onShare(item)}><Icon name="eye" />{compact(item.shares_count)}</button>
          <button type="button" onClick={() => onRemix(item)}><Icon name="repeat" /></button>
          <button type="button"><Icon name="bookmark" /></button>
        </div>
      </div>
    </article>
  );
}

function Feed({ feed, loading, onOpen, onLike, onRemix, onShare }) {
  const [sort, setSort] = useState("for-you");
  const [type, setType] = useState("all");
  const list = useMemo(() => {
    const source = feed.length ? feed : demoFeed;
    const typed = source.filter((item) => type === "all" || (type === "video" ? isVideo(item, mediaUrls(item)[0]) : !isVideo(item, mediaUrls(item)[0])));
    if (sort === "popular") return [...typed].sort((a, b) => Number(b.likes_count || 0) - Number(a.likes_count || 0));
    if (sort === "new") return [...typed].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    return typed;
  }, [feed, sort, type]);
  return (
    <section className="v4Feed">
      <nav className="v4Tabs" aria-label="Лента">
        {[["for-you", "Для тебя"], ["new", "Новые"], ["popular", "Популярные"], ["following", "Подписки"]].map(([key, label]) => <button type="button" key={key} className={sort === key ? "active" : ""} onClick={() => setSort(key)}>{label}</button>)}
      </nav>
      <nav className="v4Filters" aria-label="Тип контента">
        {[["all", "Все"], ["image", "Фото"], ["video", "Видео"], ["mine", "Мои"]].map(([key, label]) => <button type="button" key={key} className={type === key ? "active" : ""} onClick={() => setType(key === "mine" ? "all" : key)}>{label}</button>)}
      </nav>
      {loading ? <div className="v4Grid">{Array.from({ length: 6 }).map((_, i) => <div className="v4Card v4Skeleton" key={i} />)}</div> : <div className="v4Grid">{list.slice(0, 10).map((item, index) => <FeedCard key={item.id || index} item={item} index={index} onOpen={onOpen} onLike={onLike} onRemix={onRemix} onShare={onShare} />)}</div>}
    </section>
  );
}

function Create({ imageModels, videoModels, selectedPrompt, onResult, onToast }) {
  const [mode, setMode] = useState("image");
  const [prompt, setPrompt] = useState(selectedPrompt || "");
  const [model, setModel] = useState("");
  const [ratio, setRatio] = useState("9:16");
  const [duration, setDuration] = useState(5);
  const [reference, setReference] = useState("");
  const [uploadingReference, setUploadingReference] = useState(false);
  const [buildingPhotoPrompt, setBuildingPhotoPrompt] = useState(false);
  const [improvingPrompt, setImprovingPrompt] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const fileInput = useRef(null);
  const photoPromptInput = useRef(null);
  const models = mode === "image" ? imageModels : videoModels;
  const currentModel = models.find((item) => modelKey(item) === model) || models[0] || null;
  const busy = uploadingReference || buildingPhotoPrompt || improvingPrompt || submitting;
  useEffect(() => { if (!model && models[0]) setModel(modelKey(models[0])); }, [models, model]);
  useEffect(() => { if (selectedPrompt) setPrompt(selectedPrompt); }, [selectedPrompt]);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const validationError = imageUploadError(file, REFERENCE_IMAGE_TYPES);
    if (validationError) {
      onToast(validationError);
      event.target.value = "";
      return;
    }
    setUploadingReference(true);
    try {
      const uploaded = await uploadReference(file);
      setReference(uploaded.url || uploaded.public_url || "");
      notify("success");
    } catch (error) { onToast(error.message || "Не удалось загрузить референс"); }
    finally { setUploadingReference(false); event.target.value = ""; }
  }
  async function handlePhotoPrompt(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    const validationError = imageUploadError(file, PHOTO_PROMPT_IMAGE_TYPES);
    if (validationError) {
      onToast(validationError);
      event.target.value = "";
      return;
    }
    setBuildingPhotoPrompt(true);
    try {
      const response = await photoPrompt(file);
      setPrompt(response.prompt || "");
      notify("success");
    } catch (error) { onToast(error.message || "Не удалось получить промпт по фото"); }
    finally { setBuildingPhotoPrompt(false); event.target.value = ""; }
  }
  async function improve() {
    if (!prompt.trim()) return;
    setImprovingPrompt(true);
    try {
      const response = await api("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt }) });
      setPrompt(response.prompt || response.improved_prompt || response.text || prompt);
      notify("success");
    } catch (error) { onToast(error.message || "Не удалось улучшить промпт"); }
    finally { setImprovingPrompt(false); }
  }
  async function submit() {
    if (!prompt.trim()) return onToast("Опиши идею перед запуском");
    setSubmitting(true);
    try {
      const payload = mode === "image"
        ? { prompt, model, model_key: model, aspect_ratio: ratio, count: 1, reference_url: reference || null }
        : { prompt, model, model_key: model, mode: reference ? "image" : "text", duration, image_url: reference || null, reference_url: reference || null };
      const response = await api(`/generate/${mode}`, { method: "POST", body: JSON.stringify(payload) });
      onResult(response);
      notify("success");
    } catch (error) { onToast(error.message || "Генерация не запустилась"); }
    finally { setSubmitting(false); }
  }

  return (
    <section className="v4Create">
      <div className="v4TitleRow"><h1>Создать</h1><span>быстрый поток</span></div>
      <div className="v4Segment">{[["image", "Изображение", "image"], ["video", "Видео", "video"]].map(([key, label, icon]) => <button key={key} type="button" className={mode === key ? "active" : ""} onClick={() => setMode(key)}><Icon name={icon} />{label}</button>)}</div>
      <label className="v4Prompt"><textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={1200} placeholder="Опишите кадр: стиль, объект, свет, настроение…" /><small>{prompt.length}/1200</small></label>
      <div className="v4Options">
        <label><span>Модель</span><select value={model} onChange={(e) => setModel(e.target.value)}>{models.map((item) => <option key={modelKey(item)} value={modelKey(item)}>{modelName(item)} · {modelCost(item)}◆</option>)}</select></label>
        <label><span>{mode === "image" ? "Формат" : "Длина"}</span>{mode === "image" ? <select value={ratio} onChange={(e) => setRatio(e.target.value)}>{["9:16", "1:1", "4:5", "16:9", "3:4"].map((item) => <option key={item}>{item}</option>)}</select> : <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>{[5, 8, 10].map((item) => <option key={item} value={item}>{item} сек</option>)}</select>}</label>
      </div>
      <div className="v4Reference"><button type="button" onClick={() => fileInput.current?.click()} disabled={busy}>{uploadingReference ? "Загружаю…" : "+ Референс"}</button><input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="URL референса" /><input hidden ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" onChange={handleUpload} /></div>
      <div className="v4CreateActions"><button type="button" onClick={() => photoPromptInput.current?.click()} disabled={busy}>{buildingPhotoPrompt ? "Анализирую…" : "Промпт по фото"}</button><button type="button" onClick={improve} disabled={busy}>{improvingPrompt ? "Улучшаю…" : "Улучшить"}</button><button className="v4Primary" type="button" onClick={submit} disabled={busy}>{submitting ? "Запускаю…" : `Создать · ${modelCost(currentModel) || "?"}◆`}</button><input hidden ref={photoPromptInput} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handlePhotoPrompt} /></div>
    </section>
  );
}

function Prompts({ prompts, onUse }) {
  const [query, setQuery] = useState("");
  const list = (prompts.length ? prompts : demoPrompts).filter((item) => `${item.title || ""} ${item.prompt || ""}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="v4Prompts"><div className="v4TitleRow"><h1>Промпты</h1><span>копируй и запускай</span></div><div className="v4SearchBox"><Icon name="search" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск промптов" /></div><div className="v4PromptList">{list.map((item, index) => <article className="v4PromptCard" key={item.id || index}>{mediaUrls(item)[0] && <img src={mediaUrls(item)[0]} alt="" loading="lazy" />}<div><h3>{item.title || item.name || "Промпт"}</h3><p>{item.prompt || item.text || item.description}</p><small>{compact(item.likes_count)} лайков · {compact(item.uses_count)} запусков</small></div><button type="button" onClick={() => onUse(item)}><Icon name="copy" /></button></article>)}</div></section>;
}

function Profile({ user, history, feed, onTopup }) {
  const works = history.length ? history : feed.slice(0, 6);
  return <section className="v4Profile"><div className="v4TitleRow"><h1>Профиль</h1><span>баланс и работы</span></div><div className="v4ProfileCard"><div className="v4ProfileAvatar">{user?.photo_url ? <img src={user.photo_url} alt="" /> : (user?.username || "A").slice(0, 1).toUpperCase()}</div><div><h2>@{user?.username || "apix_user"}</h2><p>{compact(user?.credits)} токенов</p></div><button type="button" onClick={onTopup}>Баланс</button></div><div className="v4MiniGrid">{works.map((item, index) => <div key={item.id || index}>{mediaUrls(item)[0] ? <img src={mediaUrls(item)[0]} alt="" /> : <div className="v4ArtFallback" />}</div>)}</div></section>;
}

function Result({ result, onOpen, onPublish, onReuse }) {
  const urls = mediaUrls(result || {});
  const src = urls[0];
  const status = String(result?.status || "pending").toLowerCase();
  const ready = FINISHED_STATUSES.has(status) || urls.length > 0;
  const failed = FAILED_STATUSES.has(status);
  return <section className="v4Result"><div className="v4TitleRow"><h1>Результат</h1><span>{ready ? "готово" : failed ? "ошибка" : "в процессе"}</span></div><div className="v4ResultStage">{ready && src ? (playableVideo(src) ? <video src={src} controls playsInline /> : <img src={src} alt="" />) : <div className="v4Pending"><Icon name={failed ? "close" : "sparkle"} /><b>{failed ? "Не удалось" : "Генерация идёт"}</b><p>{failed ? result?.error || "Попробуй изменить параметры" : "Статус обновится автоматически"}</p></div>}</div><p className="v4ResultPrompt">{result?.prompt || "Готовая работа появится здесь."}</p><div className="v4ResultActions"><button type="button" onClick={() => onOpen(result)}>Открыть</button><button type="button" onClick={() => onReuse(result)}>Ещё вариант</button><button type="button" className="v4Primary" onClick={() => onPublish(result)}>В ленту</button></div></section>;
}

function Viewer({ item, onClose, onRemix, onShare }) {
  if (!item) return null;
  const src = mediaUrls(item)[0];
  return <div className="v4Viewer" role="dialog" aria-modal="true" onClick={onClose}><div className="v4ViewerInner" onClick={(e) => e.stopPropagation()}><button className="v4Close" type="button" onClick={onClose}><Icon name="close" /></button>{src ? (playableVideo(src) ? <video src={src} controls autoPlay playsInline /> : <img src={src} alt="" />) : <div className="v4ArtFallback" />}<div className="v4ViewerMeta"><b>@{item.author || item.username || "apix"}</b><p>{item.prompt || item.title}</p><div><button type="button" onClick={() => onRemix(item)}><Icon name="repeat" />Повторить</button><button type="button" onClick={() => onShare(item)}>Поделиться</button></div></div></div></div>;
}

function Topup({ open, plans, onClose }) {
  if (!open) return null;
  const list = plans.length ? plans : demoPlans;
  return <div className="v4Sheet" role="dialog" aria-modal="true" onClick={onClose}><section onClick={(e) => e.stopPropagation()}><header><h2>Баланс</h2><button type="button" onClick={onClose}><Icon name="close" /></button></header><div className="v4Plans">{list.map((plan, index) => <button type="button" key={plan.id || index} onClick={() => openTelegramLink(plan.invoice_url || plan.pay_url || plan.url || "")}><b>{compact(plan.credits || plan.amount_credits || 0)}◆</b><span>{compact(plan.price_rub || plan.amount_rub || plan.price || 0)} ₽</span></button>)}</div></section></div>;
}

function BottomNav({ screen, setScreen }) {
  const items = [
    { key: "feed", icon: "home", label: "Лента" },
    { key: "create", icon: "plus", label: "Создать" },
    { key: "magic", icon: "sparkle", label: "" },
    { key: "prompts", icon: "prompt", label: "Промпты" },
    { key: "profile", icon: "user", label: "Профиль" },
  ];
  return <nav className="v4Nav" aria-label="Основная навигация">{items.map((item) => <button type="button" key={item.key} className={cx(screen === item.key && "active", item.key === "magic" && "magic")} onClick={() => setScreen(item.key === "magic" ? "create" : item.key)}><Icon name={item.icon} />{item.label && <span>{item.label}</span>}</button>)}</nav>;
}

export default function AppV4() {
  const data = useV4Data();
  const [screen, setScreen] = useState("feed");
  const [viewer, setViewer] = useState(null);
  const [topup, setTopup] = useState(false);
  const [toast, setToast] = useState("");
  const [selectedPrompt, setSelectedPrompt] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => setupTelegramChrome(), []);
  useEffect(() => {
    const feedId = queryFeedId();
    if (!feedId) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const response = await api(`/feed/${feedId}`);
        const item = response?.data || response;
        if (cancelled || !item?.id) return;
        setScreen("feed");
        setViewer(item);
      } catch {
        if (!cancelled) show("Пост не найден или ссылка устарела");
      }
    })();
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!result?.id || !ACTIVE_STATUSES.has(String(result.status || "").toLowerCase())) return undefined;
    const timer = window.setInterval(async () => {
      try {
        const next = await api(`/generations/${result.id}`);
        setResult((current) => ({ ...current, ...next }));
      } catch {}
    }, 3500);
    return () => window.clearInterval(timer);
  }, [result?.id, result?.status]);
  function show(message) {
    setToast(message);
    window.clearTimeout(window.__apixV4Toast);
    window.__apixV4Toast = window.setTimeout(() => setToast(""), 2800);
  }
  async function like(item) {
    if (!item?.id || String(item.id).startsWith("demo")) return;
    try { await api(`/feed/${item.id}/like`, { method: "POST" }); haptic("light"); } catch (error) { show(error.message || "Лайк не отправлен"); }
  }
  async function share(item) {
    if (!item?.id || String(item.id).startsWith("demo")) return show("Демо-ссылка недоступна");
    try { const res = await api(`/feed/${item.id}/link`); if (res.link) await navigator.clipboard?.writeText(res.link); show("Ссылка скопирована"); } catch (error) { show(error.message || "Не удалось поделиться"); }
  }
  function remix(item) { setSelectedPrompt(item?.prompt || ""); setScreen("create"); }
  async function publish(item) {
    if (!item?.id) return;
    try { await api(`/generations/${item.id}/share`, { method: "POST" }); show("Опубликовано"); data.reload(); } catch (error) { show(error.message || "Не удалось опубликовать"); }
  }
  function usePrompt(item) { setSelectedPrompt(item.prompt || item.text || item.description || ""); setScreen("create"); }

  const content = screen === "create" ? <Create imageModels={data.imageModels} videoModels={data.videoModels} selectedPrompt={selectedPrompt} onResult={(next) => { setResult(next); setScreen("result"); }} onToast={show} />
    : screen === "prompts" ? <Prompts prompts={data.prompts} onUse={usePrompt} />
      : screen === "profile" ? <Profile user={data.user} history={data.history} feed={data.feed} onTopup={() => setTopup(true)} />
        : screen === "result" ? <Result result={result} onOpen={setViewer} onPublish={publish} onReuse={remix} />
          : <Feed feed={data.feed} loading={data.loading} onOpen={setViewer} onLike={like} onRemix={remix} onShare={share} />;

  return <main className="v4App" data-build={BUILD_ID}><Header user={data.user} onSearch={() => setScreen("prompts")} onProfile={() => setScreen("profile")} onTopup={() => setTopup(true)} /><div className="v4Screen">{content}</div><BottomNav screen={screen} setScreen={setScreen} /><Viewer item={viewer} onClose={() => setViewer(null)} onRemix={remix} onShare={share} /><Topup open={topup} plans={data.plans} onClose={() => setTopup(false)} />{toast && <div className="v4Toast" role="status">{toast}</div>}</main>;
}
