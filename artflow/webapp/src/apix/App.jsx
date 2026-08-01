import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  haptic,
  initData,
  isTelegramRuntime,
  listItems,
  notify,
  openTelegramLink,
  photoPrompt,
  setupTelegramChrome,
  tg,
  tgUser,
  uploadReference,
} from "./api.js";
import { demoFeed, demoImageModels, demoPlans, demoPrompts, demoUser, demoVideoModels } from "./demoData.js";

const BUILD_ID = "20260801-apix-premium-integrated-v1";
const ACTIVE_STATUSES = new Set(["pending", "processing", "queued", "running"]);
const FINISHED_STATUSES = new Set(["done", "completed", "success"]);
const FAILED_STATUSES = new Set(["failed", "error", "cancelled"]);

window.__APIX_MINIAPP_BUILD_ID__ = BUILD_ID;

function cls(...parts) {
  return parts.filter(Boolean).join(" ");
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

function itemMediaUrls(item) {
  const urls = [];
  for (const field of ["preview_urls", "result_urls", "media_urls"]) {
    if (Array.isArray(item?.[field])) urls.push(...item[field].filter(Boolean));
  }
  for (const field of ["preview_url", "result_url", "image_url", "video_url"]) {
    if (item?.[field]) urls.push(item[field]);
  }
  return [...new Set(urls)];
}

function isVideo(item, url = "") {
  return item?.gen_type === "video" || /\.(mp4|mov|webm)(?:$|\?)/i.test(url);
}

function compactNumber(value) {
  const n = Number(value || 0);
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K`;
  return String(n);
}

function useResources() {
  const [state, setState] = useState({
    user: demoUser,
    feed: demoFeed,
    prompts: demoPrompts,
    imageModels: demoImageModels,
    videoModels: demoVideoModels,
    history: [],
    plans: demoPlans,
    loading: true,
    demo: true,
    error: "",
  });

  const reload = useCallback(async () => {
    setState((current) => ({ ...current, loading: true }));
    const requests = await Promise.allSettled([
      api("/me"),
      api("/feed?source=recent&limit=60"),
      api("/prompts?source=popular&limit=30"),
      api("/models/image"),
      api("/models/video"),
      api("/history?limit=40"),
      api("/plans"),
    ]);

    const [user, feed, prompts, imageModels, videoModels, history, plans] = requests;
    const anyReal = requests.some((item) => item.status === "fulfilled");
    const firstError = requests.find((item) => item.status === "rejected")?.reason?.message || "";

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
      error: firstError,
    });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}

function AppHeader({ user, demo, onTopup, onProfile }) {
  const telegramUser = tgUser();
  const initials = (user?.full_name || user?.username || telegramUser?.first_name || "A").trim().slice(0, 1).toUpperCase();
  const photo = user?.photo_url || telegramUser?.photo_url || "";

  return (
    <header className="apixTop" aria-label="APIX">
      <div className="apixMicroBar">
        <span>{demo ? "preview mode" : "live studio"}</span>
        <i />
        <span>{demo ? "API fallback" : "Telegram Mini App"}</span>
      </div>
      <div className="apixTopRow">
        <button className="apixSearch" type="button" aria-label="Поиск">⌕</button>
        <div className="apixLogo">APIX</div>
        <div className="apixTopActions">
          <button className="apixBalance" type="button" onClick={onTopup}>◆ {compactNumber(user?.credits)}</button>
          <button className="apixAvatar" type="button" onClick={onProfile} aria-label="Профиль">
            {photo ? <img src={photo} alt="" /> : initials}
          </button>
        </div>
      </div>
    </header>
  );
}

function Hero({ screen, onCreate }) {
  const data = {
    feed: ["Лента", "AI-искусство нового поколения", "Вдохновляйся. Создавай. Делись с миром."],
    create: ["Создать", "Опиши идею — APIX соберёт визуал", "Модель, формат, референс и результат в одном потоке."],
    prompts: ["Промпты", "Готовые идеи для ваших шедевров", "Подборки, стили и быстрый запуск в один клик."],
    profile: ["Профиль", "Твои работы, баланс и рост", "История генераций, публикации и рефералы."],
    result: ["Результат", "Готовая генерация", "Публикуй, сохраняй или делай следующий шаг."],
  }[screen] || ["Лента", "AI-искусство нового поколения", ""];

  return (
    <section className="apixHero">
      <div className="apixHeroCopy">
        <span className="apixEyebrow">✦ Главная подборка</span>
        <h1>{data[0]}</h1>
        <p><b>{data[1]}</b><br />{data[2]}</p>
        {screen === "feed" && <button type="button" className="apixHeroCta" onClick={onCreate}>Смотреть подборку <span>›</span></button>}
      </div>
      <div className="apixHeroOrb" aria-hidden="true"><span /></div>
    </section>
  );
}

function FeedCard({ item, index, onOpen, onLike, onRemix, onShare }) {
  const urls = itemMediaUrls(item);
  const first = urls[0] || "";
  const video = isVideo(item, first);
  const title = item.prompt || item.title || "Премиальная генерация APIX";
  const author = item.author || item.username || item.user?.username || "apix";

  return (
    <article className={cls("feedTile", index % 3 === 0 && "tall", index % 5 === 0 && "wideTone")} style={{ "--tone": index % 6 }}>
      <button className="feedMedia" type="button" onClick={() => onOpen(item)} aria-label="Открыть публикацию">
        {first ? (
          video ? <video src={first} muted playsInline preload="metadata" /> : <img src={first} alt="" loading="lazy" decoding="async" />
        ) : <div className="generatedArt" />}
        {video && <span className="mediaBadge">▶ 0:{12 + index}</span>}
        {!first && <span className="mediaBadge">AI</span>}
      </button>
      <div className="tileBadge">{index === 0 ? "🔥 Тренд" : video ? "Видео" : "Фото"}</div>
      <div className="tileAuthor"><span className="authorAvatar">{author.slice(0, 1).toUpperCase()}</span><b>{author}</b><small>{index < 2 ? "2 ч назад" : "Вчера"}</small></div>
      <div className="tileBody">
        <p>{title}</p>
        <div className="tileActions">
          <button type="button" onClick={() => onLike(item)}>♡ {compactNumber(item.likes_count)}</button>
          <button type="button" onClick={() => onShare(item)}>↗ {compactNumber(item.shares_count)}</button>
          <button type="button" onClick={() => onRemix(item)}>↻</button>
          <button type="button" aria-label="Сохранить">▱</button>
        </div>
      </div>
    </article>
  );
}

function FeedScreen({ feed, loading, onOpen, onLike, onRemix, onShare, onCreate }) {
  const [sort, setSort] = useState("feed");
  const [type, setType] = useState("all");

  const filtered = useMemo(() => {
    const source = feed.length ? feed : demoFeed;
    const typed = source.filter((item) => type === "all" || (type === "video" ? isVideo(item, itemMediaUrls(item)[0]) : !isVideo(item, itemMediaUrls(item)[0])));
    if (sort === "popular") return [...typed].sort((a, b) => Number(b.likes_count || 0) - Number(a.likes_count || 0));
    if (sort === "new") return [...typed].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    return typed;
  }, [feed, sort, type]);

  return (
    <>
      <Hero screen="feed" onCreate={onCreate} />
      <nav className="apixTabs" aria-label="Сортировка ленты">
        {[["feed", "Лента"], ["popular", "Популярное"], ["new", "Новое"], ["following", "Подписки"], ["for-you", "Для тебя"]].map(([key, label]) => (
          <button key={key} className={sort === key ? "active" : ""} onClick={() => setSort(key)} type="button">{label}</button>
        ))}
      </nav>
      <section className="feedFeature">
        <div><span>✧ Главная подборка</span><h2>AI-искусство нового поколения</h2><p>Глянцевые работы, видео и промпты из APIX.</p></div>
        <button type="button" onClick={onCreate}>Создать работу <span>›</span></button>
      </section>
      <nav className="apixChips" aria-label="Тип контента">
        {[["all", "Все"], ["image", "Фото"], ["video", "Видео"], ["mine", "Мои"]].map(([key, label]) => (
          <button key={key} className={type === key ? "active" : ""} onClick={() => setType(key === "mine" ? "all" : key)} type="button">{label}</button>
        ))}
      </nav>
      {loading ? <SkeletonGrid /> : <div className="feedGrid">{filtered.slice(0, 9).map((item, index) => <FeedCard key={item.id || index} item={item} index={index} onOpen={onOpen} onLike={onLike} onRemix={onRemix} onShare={onShare} />)}</div>}
    </>
  );
}

function StudioScreen({ imageModels, videoModels, selectedPrompt, onResult, onNotice }) {
  const [mode, setMode] = useState("image");
  const [prompt, setPrompt] = useState(selectedPrompt || "");
  const [model, setModel] = useState("");
  const [ratio, setRatio] = useState("9:16");
  const [duration, setDuration] = useState(5);
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef(null);

  const models = mode === "image" ? imageModels : videoModels;
  const currentModel = models.find((item) => modelKey(item) === model) || models[0] || null;

  useEffect(() => {
    if (!model && models[0]) setModel(modelKey(models[0]));
  }, [models, model]);

  useEffect(() => {
    if (selectedPrompt) setPrompt(selectedPrompt);
  }, [selectedPrompt]);

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const uploaded = await uploadReference(file);
      setReference(uploaded.url || uploaded.public_url || "");
      notify("success");
    } catch (error) {
      onNotice(error.message || "Не удалось загрузить референс");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function handlePhotoPrompt(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const response = await photoPrompt(file);
      setPrompt(response.prompt || "");
      notify("success");
    } catch (error) {
      onNotice(error.message || "Не удалось получить промпт по фото");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function improve() {
    if (!prompt.trim()) return;
    setBusy(true);
    try {
      const response = await api("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt }) });
      setPrompt(response.prompt || response.improved_prompt || response.text || prompt);
      notify("success");
    } catch (error) {
      onNotice(error.message || "Не удалось улучшить промпт");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!prompt.trim()) {
      onNotice("Опиши идею перед запуском");
      return;
    }
    setBusy(true);
    try {
      const payload = mode === "image"
        ? { prompt, model, model_key: model, aspect_ratio: ratio, count: 1, reference_url: reference || null }
        : { prompt, model, model_key: model, mode: reference ? "image" : "text", duration, image_url: reference || null, reference_url: reference || null };
      const response = await api(`/generate/${mode}`, { method: "POST", body: JSON.stringify(payload) });
      onResult(response);
      notify("success");
    } catch (error) {
      onNotice(error.message || "Генерация не запустилась");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Hero screen="create" />
      <section className="studioCard">
        <div className="modeSwitch">
          {[["image", "Изображение"], ["video", "Видео"]].map(([key, label]) => <button type="button" key={key} className={mode === key ? "active" : ""} onClick={() => setMode(key)}>{label}</button>)}
        </div>
        <label className="promptBox"><span>Опишите вашу идею</span><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Например: футуристический город на закате, неоновые огни, дождь, отражения в лужах..." maxLength={1200} /></label>
        <div className="studioGridControls">
          <label><span>Модель</span><select value={model} onChange={(event) => setModel(event.target.value)}>{models.map((item) => <option key={modelKey(item)} value={modelKey(item)}>{modelName(item)} · {modelCost(item)}◆</option>)}</select></label>
          <label><span>{mode === "image" ? "Формат" : "Длительность"}</span>{mode === "image" ? <select value={ratio} onChange={(event) => setRatio(event.target.value)}>{["9:16", "1:1", "4:5", "16:9", "3:4"].map((item) => <option key={item}>{item}</option>)}</select> : <select value={duration} onChange={(event) => setDuration(Number(event.target.value))}>{[5, 8, 10].map((item) => <option key={item} value={item}>{item} сек</option>)}</select>}</label>
        </div>
        <div className="referenceRow">
          <button type="button" onClick={() => fileInput.current?.click()}>＋ Референс</button>
          <label className="inlineInput"><input value={reference} onChange={(event) => setReference(event.target.value)} placeholder="URL референса" /></label>
          <input ref={fileInput} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={handleUpload} />
        </div>
        <div className="studioActions">
          <label className="ghostUpload">Промпт по фото<input hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={handlePhotoPrompt} /></label>
          <button type="button" onClick={improve} disabled={busy}>Улучшить</button>
          <button type="button" className="primaryAction" onClick={submit} disabled={busy}>Создать ◆ {modelCost(currentModel) || "?"}</button>
        </div>
      </section>
    </>
  );
}

function PromptsScreen({ prompts, onUsePrompt }) {
  const [query, setQuery] = useState("");
  const list = prompts.length ? prompts : demoPrompts;
  const filtered = list.filter((item) => `${item.title || ""} ${item.prompt || ""}`.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <Hero screen="prompts" />
      <div className="promptSearch"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск промптов..." /></div>
      <div className="promptList">
        {filtered.map((item, index) => (
          <article className="promptCard" key={item.id || index}>
            <div className="promptThumb"><div className="generatedArt" style={{ "--tone": index % 6 }} /></div>
            <div><b>{item.title || item.name || `Промпт #${item.id}`}</b><p>{item.prompt || item.text || item.description}</p><small>♡ {compactNumber(item.likes_count)} · ↻ {compactNumber(item.uses_count)}</small></div>
            <button type="button" onClick={() => onUsePrompt(item)}>Запустить</button>
          </article>
        ))}
      </div>
    </>
  );
}

function ProfileScreen({ user, history, feed, onTopup }) {
  const ownWorks = history.length ? history : feed.slice(0, 4);
  return (
    <>
      <Hero screen="profile" />
      <section className="profilePanel">
        <div className="profileAvatar">{user?.photo_url ? <img src={user.photo_url} alt="" /> : (user?.full_name || user?.username || "A").slice(0, 1).toUpperCase()}</div>
        <h2>@{user?.username || "apix_user"}</h2>
        <p>Premium creator · {compactNumber(user?.credits)} кристаллов</p>
        <div className="profileStats"><span><b>{ownWorks.length}</b>Работы</span><span><b>5.2K</b>Подписчики</span><span><b>{compactNumber(user?.referral_balance)}</b>Реф.</span></div>
        <button type="button" className="primaryAction" onClick={onTopup}>Пополнить баланс</button>
      </section>
      <section className="miniGallery">
        {ownWorks.slice(0, 6).map((item, index) => <div className="miniTile" key={item.id || index}>{itemMediaUrls(item)[0] ? <img src={itemMediaUrls(item)[0]} alt="" /> : <div className="generatedArt" style={{ "--tone": index % 6 }} />}</div>)}
      </section>
    </>
  );
}

function ResultScreen({ result, onPublish, onReuse, onOpen }) {
  const status = String(result?.status || "pending").toLowerCase();
  const urls = itemMediaUrls(result || {});
  const ready = FINISHED_STATUSES.has(status) || urls.length > 0;
  const failed = FAILED_STATUSES.has(status);
  return (
    <>
      <Hero screen="result" />
      <section className="resultPanel">
        <div className="resultStage">{ready && urls[0] ? (isVideo(result, urls[0]) ? <video src={urls[0]} controls playsInline /> : <img src={urls[0]} alt="" />) : <div className={cls("resultPending", failed && "failed")}><b>{failed ? "Не удалось" : "Генерация в очереди"}</b><span>{failed ? result?.error || "Проверь параметры и попробуй снова" : "Статус обновится автоматически"}</span></div>}</div>
        <div className="resultMeta"><span>{result?.model || "APIX"}</span><span>{status}</span></div>
        <p>{result?.prompt || "Готовый результат появится здесь."}</p>
        <div className="resultActions"><button type="button" onClick={() => onOpen(result)}>Открыть</button><button type="button" onClick={() => onPublish(result)}>В ленту</button><button type="button" className="primaryAction" onClick={() => onReuse(result)}>Ещё вариант</button></div>
      </section>
    </>
  );
}

function Viewer({ item, onClose, onRemix, onShare }) {
  if (!item) return null;
  const urls = itemMediaUrls(item);
  const first = urls[0];
  return (
    <div className="viewer" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="viewerCard" onClick={(event) => event.stopPropagation()}>
        <button className="viewerClose" type="button" onClick={onClose}>×</button>
        <div className="viewerMedia">{first ? (isVideo(item, first) ? <video src={first} controls playsInline autoPlay /> : <img src={first} alt="" />) : <div className="generatedArt" />}</div>
        <div className="viewerInfo"><b>@{item.author || item.username || "apix"}</b><p>{item.prompt || item.title || "Премиальная генерация APIX"}</p><div><button type="button" onClick={() => onRemix(item)}>↻ Повторить</button><button type="button" onClick={() => onShare(item)}>↗ Поделиться</button></div></div>
      </div>
    </div>
  );
}

function TopupSheet({ open, plans, onClose }) {
  if (!open) return null;
  const list = plans.length ? plans : demoPlans;
  return (
    <div className="sheetOverlay" role="dialog" aria-modal="true" onClick={onClose}>
      <section className="topupSheet" onClick={(event) => event.stopPropagation()}>
        <header><h2>Пополнить баланс</h2><button type="button" onClick={onClose}>×</button></header>
        <div className="plansGrid">{list.map((plan, index) => <button type="button" className="planCard" key={plan.id || index} onClick={() => openTelegramLink(plan.invoice_url || plan.pay_url || plan.url || "")}><b>◆ {compactNumber(plan.credits || plan.amount_credits || plan.stars || 0)}</b><span>+{compactNumber(plan.bonus_credits || plan.bonus || 0)} бонус</span><strong>{compactNumber(plan.price_rub || plan.amount_rub || plan.price || 0)} ₽</strong></button>)}</div>
      </section>
    </div>
  );
}

function BottomNav({ screen, setScreen }) {
  const items = [["feed", "⌂", "Лента"], ["trends", "♨", "Тренды"], ["create", "+", ""], ["prompts", "☻", "AI"], ["profile", "◉", "Профиль"]];
  return <nav className="bottomNav" aria-label="Основная навигация">{items.map(([key, icon, label]) => <button key={key} type="button" className={cls(screen === key && "active", key === "create" && "center")} onClick={() => setScreen(key === "trends" ? "feed" : key)}><b>{icon}</b>{label && <span>{label}</span>}</button>)}</nav>;
}

function SkeletonGrid() {
  return <div className="feedGrid">{Array.from({ length: 6 }).map((_, index) => <div className={cls("feedTile", "skeleton", index % 2 === 0 && "tall")} key={index} />)}</div>;
}

export default function App() {
  const resources = useResources();
  const [screen, setScreen] = useState("feed");
  const [viewer, setViewer] = useState(null);
  const [topupOpen, setTopupOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedPrompt, setSelectedPrompt] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => setupTelegramChrome(), []);

  useEffect(() => {
    if (!result?.id || !ACTIVE_STATUSES.has(String(result.status || "").toLowerCase())) return undefined;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const next = await api(`/generations/${result.id}`);
        if (!cancelled) setResult((current) => ({ ...current, ...next }));
        const status = String(next.status || "").toLowerCase();
        if (FINISHED_STATUSES.has(status) || FAILED_STATUSES.has(status)) window.clearInterval(timer);
      } catch {}
    }, 3500);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [result?.id, result?.status]);

  function toast(message) {
    setNotice(message);
    window.clearTimeout(window.__apixNoticeTimer);
    window.__apixNoticeTimer = window.setTimeout(() => setNotice(""), 3200);
  }

  async function likeFeed(item) {
    if (!item?.id || String(item.id).startsWith("demo")) return;
    try {
      await api(`/feed/${item.id}/like`, { method: "POST" });
      haptic("light");
    } catch (error) {
      toast(error.message || "Лайк не отправлен");
    }
  }

  async function shareFeed(item) {
    if (!item?.id || String(item.id).startsWith("demo")) return toast("В демо ссылка недоступна");
    try {
      const response = await api(`/feed/${item.id}/link`);
      if (response.link) await navigator.clipboard?.writeText(response.link);
      notify("success");
      toast("Ссылка скопирована");
    } catch (error) {
      toast(error.message || "Не удалось поделиться");
    }
  }

  async function remixFeed(item) {
    setSelectedPrompt(item?.prompt || "");
    setScreen("create");
  }

  async function publishResult(item) {
    if (!item?.id) return;
    try {
      await api(`/generations/${item.id}/share`, { method: "POST" });
      notify("success");
      toast("Опубликовано в ленте");
      resources.reload();
    } catch (error) {
      toast(error.message || "Не удалось опубликовать");
    }
  }

  function usePrompt(promptItem) {
    setSelectedPrompt(promptItem.prompt || promptItem.text || promptItem.description || "");
    setScreen("create");
  }

  const content = screen === "create"
    ? <StudioScreen imageModels={resources.imageModels} videoModels={resources.videoModels} selectedPrompt={selectedPrompt} onResult={(next) => { setResult(next); setScreen("result"); }} onNotice={toast} />
    : screen === "prompts"
      ? <PromptsScreen prompts={resources.prompts} onUsePrompt={usePrompt} />
      : screen === "profile"
        ? <ProfileScreen user={resources.user} history={resources.history} feed={resources.feed} onTopup={() => setTopupOpen(true)} />
        : screen === "result"
          ? <ResultScreen result={result} onOpen={setViewer} onPublish={publishResult} onReuse={(item) => { setSelectedPrompt(item?.prompt || selectedPrompt); setScreen("create"); }} />
          : <FeedScreen feed={resources.feed} loading={resources.loading} onOpen={setViewer} onLike={likeFeed} onRemix={remixFeed} onShare={shareFeed} onCreate={() => setScreen("create")} />;

  return (
    <main className="apixApp">
      <AppHeader user={resources.user} demo={resources.demo} onTopup={() => setTopupOpen(true)} onProfile={() => setScreen("profile")} />
      {resources.demo && <div className="demoNotice">Демо-режим: реальные данные появятся внутри Telegram Mini App.</div>}
      <div className="screenWrap">{content}</div>
      <BottomNav screen={screen} setScreen={setScreen} />
      <Viewer item={viewer} onClose={() => setViewer(null)} onRemix={remixFeed} onShare={shareFeed} />
      <TopupSheet open={topupOpen} plans={resources.plans} onClose={() => setTopupOpen(false)} />
      {notice && <div className="toast" role="status">{notice}</div>}
    </main>
  );
}
