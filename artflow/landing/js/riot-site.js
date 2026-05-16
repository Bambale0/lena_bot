const root = document.getElementById("site-root");

const tokenKey = "apix_web_token";
const langKey = "apix_site_lang";
const queueKey = "apix_generation_queue";
const queuePollMs = 4500;

const routes = ["home", "examples", "features", "studio", "prompts", "feed", "works", "billing", "profile"];

const i18n = {
  ru: {
    navPublic: {
      home: "Главная",
      examples: "Примеры",
      features: "Возможности",
      prompts: "Идеи",
      feed: "Лента",
      billing: "Цены",
      profile: "Войти",
    },
    navApp: {
      home: "Рабочий стол",
      studio: "Студия",
      prompts: "Идеи",
      feed: "Лента",
      works: "Мои работы",
      billing: "Баланс",
      profile: "Профиль",
    },
  },
  en: {
    navPublic: {
      home: "Home",
      examples: "Examples",
      features: "Features",
      prompts: "Ideas",
      feed: "Gallery",
      billing: "Pricing",
      profile: "Login",
    },
    navApp: {
      home: "Dashboard",
      studio: "Studio",
      prompts: "Ideas",
      feed: "Gallery",
      works: "My Works",
      billing: "Balance",
      profile: "Profile",
    },
  },
};

const data = {
  health: null,
  authConfig: null,
  me: null,
  models: [],
  imageModels: [],
  videoModels: [],
  musicModels: [],
  plans: [],
  feed: [],
  prompts: [],
  history: [],
  errors: {},
};

const state = {
  renderId: 0,
  loadController: null,
  loadedAt: {},
  pendingPrompt: null,
  activePromptId: null,
  pendingReference: null,
  pendingFeedRemix: null,
  queue: readQueue(),
  queueTimer: null,
  studio: {
    mode: "image",
    step: "brief",
    refs: { image: [], video: [] },
  },
};

function token() {
  return localStorage.getItem(tokenKey) || "";
}

function lang() {
  return localStorage.getItem(langKey) === "en" ? "en" : "ru";
}

function isRu() {
  return lang() === "ru";
}

function routeName() {
  const name = location.hash.replace(/^#\/?/, "") || "home";
  return routes.includes(name) ? name : "home";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function readQueue() {
  try {
    const parsed = JSON.parse(localStorage.getItem(queueKey) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item && item.gen_id).slice(0, 20);
  } catch {
    return [];
  }
}

function persistQueue() {
  localStorage.setItem(queueKey, JSON.stringify(state.queue.slice(0, 20)));
}

function resultUrlFrom(item) {
  return item?.result_url || item?.result_urls?.[0] || "";
}

function isActiveStatus(status) {
  return ["pending", "processing", "queued", "running"].includes(String(status || "").toLowerCase());
}

function isDoneStatus(status) {
  return String(status || "").toLowerCase() === "done";
}

function queueItemFromGeneration(result, meta = {}) {
  const now = new Date().toISOString();
  const resultUrls = Array.isArray(result?.result_urls) ? result.result_urls.filter(Boolean) : [];
  return {
    local_id: meta.local_id || `q_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    gen_id: Number(result?.id || meta.gen_id || 0),
    mode: result?.gen_type || meta.mode || "image",
    model: result?.model || meta.model || "",
    prompt: result?.prompt || meta.prompt || "",
    status: result?.status || meta.status || "pending",
    result_url: result?.result_url || resultUrls[0] || meta.result_url || "",
    result_urls: resultUrls.length ? resultUrls : (meta.result_urls || []),
    credits_spent: Number(result?.credits_spent ?? meta.credits_spent ?? 0),
    created_at: result?.created_at || meta.created_at || now,
    updated_at: now,
    source: meta.source || "studio",
  };
}

function upsertQueueItem(item) {
  if (!item?.gen_id) return;
  const index = state.queue.findIndex((existing) => Number(existing.gen_id) === Number(item.gen_id));
  if (index >= 0) {
    state.queue[index] = { ...state.queue[index], ...item, updated_at: new Date().toISOString() };
  } else {
    state.queue.unshift(item);
  }
  state.queue = state.queue.slice(0, 20);
  persistQueue();
  renderQueuePanels();
  startQueuePolling();
}

function activeQueueItems() {
  return state.queue.filter((item) => item.gen_id && isActiveStatus(item.status));
}

function statusLabel(status) {
  const value = String(status || "pending").toLowerCase();
  const ru = {
    pending: "в очереди",
    processing: "создаётся",
    queued: "в очереди",
    running: "создаётся",
    done: "готово",
    failed: "ошибка",
  };
  const en = {
    pending: "queued",
    processing: "running",
    queued: "queued",
    running: "running",
    done: "done",
    failed: "failed",
  };
  return (isRu() ? ru : en)[value] || value;
}

function queueStatusClass(status) {
  const value = String(status || "").toLowerCase();
  if (value === "done") return "is-success";
  if (value === "failed") return "is-error";
  return "is-warning";
}

async function request(base, path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (token()) headers["X-Web-Auth-Token"] = token();
  const response = await fetch(`${base}${path}`, { ...options, headers });
  const json = await response.json().catch(() => ({ ok: false, error: isRu() ? "Сервис не ответил" : "The service did not answer" }));
  if (!response.ok || json.ok === false) throw new Error(json.error || json.detail || `HTTP ${response.status}`);
  return Object.prototype.hasOwnProperty.call(json, "data") ? json.data : json;
}

const webApi = (path, options) => request("/api/web", path, options);
const genApi = (path, options) => request("/api/v1", path, options);
const uploadApi = (options) => request("", "/upload", options);

function icon(name) {
  const paths = {
    image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="10" r="2"/><path d="m21 16-5.2-5.2a2 2 0 0 0-2.8 0L5 19"/>',
    video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
    music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    assistant: '<path d="M12 3 9.8 8.2 4 10l5.8 1.8L12 17l2.2-5.2L20 10l-5.8-1.8z"/><path d="M5 18h4"/><path d="M15 18h4"/>',
    upload: '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M5 20h14"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1"/><path d="M14 11a5 5 0 0 0-7.1 0l-2 2A5 5 0 0 0 12 20.1l1.1-1.1"/>',
    settings: '<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V22a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1A2 2 0 1 1 7.1 3.2l.1.1a1.7 1.7 0 0 0 1.9.3h.1a1.7 1.7 0 0 0 1-1.6V2a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.6h.1a1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.6 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
    play: '<circle cx="12" cy="12" r="10"/><path d="m10 8 6 4-6 4z"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    spark: '<path d="m12 3 1.6 4.8L18 10l-4.4 2.2L12 17l-1.6-4.8L6 10l4.4-2.2z"/><path d="M19 3v4"/><path d="M21 5h-4"/><path d="M5 17v4"/><path d="M7 19H3"/>',
    layers: '<path d="m12 2 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
  };
  return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.spark}</svg>`;
}

function markLoaded(key) {
  state.loadedAt[key] = Date.now();
}

function hasLoaded(key) {
  return Object.prototype.hasOwnProperty.call(state.loadedAt, key);
}

function resetPrivateData() {
  data.me = null;
  data.imageModels = [];
  data.videoModels = [];
  data.musicModels = [];
  data.history = [];
  ["me", "imageModels", "videoModels", "musicModels", "history"].forEach((key) => {
    delete state.loadedAt[key];
  });
}

function loadKeysForRoute(route) {
  const keys = new Set(["health", "authConfig"]);
  if (["home", "examples", "features"].includes(route)) keys.add("models");
  if (["home", "examples", "features", "billing"].includes(route)) keys.add("plans");
  if (["home", "examples", "feed"].includes(route)) keys.add("feed");
  if (["home", "prompts"].includes(route)) keys.add("prompts");
  if (token() && route === "home") {
    keys.add("imageModels");
    keys.add("videoModels");
    keys.add("musicModels");
    keys.add("history");
  }
  if (route === "studio") {
    keys.add("imageModels");
    keys.add("videoModels");
    keys.add("musicModels");
    keys.add("history");
  }
  if (route === "works") keys.add("history");
  if (token()) keys.add("me");
  return keys;
}

function jobForKey(key, signal) {
  const jobs = {
    health: () => webApi("/health", { signal }),
    authConfig: () => webApi("/auth/config", { signal }),
    models: () => webApi("/models", { signal }),
    plans: () => webApi("/price-plans", { signal }),
    feed: () => webApi("/feed?limit=9", { signal }),
    prompts: () => webApi("/prompts?limit=9", { signal }),
    me: () => webApi("/me", { signal }),
    imageModels: () => genApi("/models/image", { signal }),
    videoModels: () => genApi("/models/video", { signal }),
    musicModels: () => genApi("/models/music", { signal }),
    history: () => genApi("/history?limit=12", { signal }),
  };
  return jobs[key];
}

async function load(options = {}) {
  const route = options.route || routeName();
  const force = new Set(options.force || []);
  const signal = options.signal || null;
  const keys = loadKeysForRoute(route);

  if (!token()) resetPrivateData();

  force.forEach((key) => keys.add(key));
  const jobs = [...keys].filter((key) => force.has(key) || !hasLoaded(key)).map((key) => [key, jobForKey(key, signal)]).filter(([, fn]) => fn);

  await Promise.all(jobs.map(async ([key, fn]) => {
    try {
      data[key] = await fn();
      markLoaded(key);
      delete data.errors[key];
    } catch (error) {
      if (error.name === "AbortError") return;
      data.errors[key] = error.message;
      if (key === "me") data.me = null;
    }
  }));
}

function nav() {
  const current = routeName();
  const labels = data.me ? i18n[lang()].navApp : i18n[lang()].navPublic;
  return Object.entries(labels).map(([key, label]) => (
    `<a class="${current === key ? "is-active" : ""}" href="#/${key}"${current === key ? ' aria-current="page"' : ""}>${label}</a>`
  )).join("");
}

function shell(view) {
  const userLabel = data.me ? `@${data.me.username || data.me.tg_id}` : (isRu() ? "Войти" : "Login");
  return `
    <div class="shell">
      <header class="topbar">
        <a class="brand" href="#/home" aria-label="APIX Artflow">
          <span class="brand-badge">APIX</span>
          <span><b>Artflow</b><small>${isRu() ? "Веб-студия" : "Web studio"}</small></span>
        </a>
        <nav class="nav" aria-label="Основная навигация">${nav()}</nav>
        <button class="btn lang-toggle" type="button" data-lang-toggle>${lang().toUpperCase()}</button>
        <a class="btn primary" href="#/profile">${escapeHtml(userLabel)}</a>
      </header>
      <main class="main">${view}</main>
      <footer class="footer">${isRu() ? "APIX Artflow: красивая витрина до входа и полноценная творческая студия после авторизации." : "APIX Artflow: a polished showcase before login and a full creative studio after sign-in."}</footer>
    </div>
  `;
}

function mediaTypeFromUrl(url, fallback = "") {
  const value = String(url || "").split("?")[0].toLowerCase();
  if (fallback === "video" || /\.(mp4|webm|mov|m4v)$/i.test(value)) return "video";
  if (fallback === "music" || /\.(mp3|wav|ogg|m4a)$/i.test(value)) return "music";
  return "image";
}

function media(url, alt, options = {}) {
  const square = Boolean(options.square);
  const type = mediaTypeFromUrl(url, options.type);
  const label = escapeHtml(alt || (isRu() ? "Медиа" : "Media"));
  const fallback = `<div class="media-fallback">${icon(type === "video" ? "video" : type === "music" ? "music" : "image")}<span>${label}</span></div>`;
  if (!url) {
    return `<div class="media-frame ${square ? "square" : ""} is-missing" role="img" aria-label="${label}">${fallback}</div>`;
  }
  const safeUrl = escapeHtml(url);
  if (type === "video") {
    return `<div class="media-frame ${square ? "square" : ""}">${fallback}<video class="media" src="${safeUrl}" controls playsinline preload="metadata" onerror="this.closest('.media-frame').classList.add('is-missing')"></video></div>`;
  }
  if (type === "music") {
    return `<div class="media-frame ${square ? "square" : ""} music-frame">${fallback}<audio class="audio-player" src="${safeUrl}" controls preload="metadata" onerror="this.closest('.media-frame').classList.add('is-missing')"></audio></div>`;
  }
  return `<div class="media-frame ${square ? "square" : ""}">${fallback}<img class="media" src="${safeUrl}" alt="${label}" loading="lazy" onerror="this.closest('.media-frame').classList.add('is-missing')"></div>`;
}

function img(url, alt, square = false, type = "") {
  return media(url, alt, { square, type });
}

function empty(text, error) {
  return `<div class="empty">${escapeHtml(text)}${error ? `<br><span class="mono">${escapeHtml(error)}</span>` : ""}</div>`;
}

function feedCard(item) {
  const caption = item.prompt && data.me
    ? item.prompt
    : (isRu() ? "Готовая работа, созданная в APIX. Используйте как вдохновение для своей серии." : "A real work created in APIX. Use it as inspiration for your next series.");
  const type = item.gen_type || item.type || "";
  const canUseAsImageRef = item.result_url && mediaTypeFromUrl(item.result_url, type) === "image";
  return `
    <article class="dark">
      <p class="sticker">${escapeHtml(item.author || "anon")}</p>
      ${img(item.result_url, isRu() ? "Пример работы" : "Example work", false, type)}
      <h3>${escapeHtml(item.model ? (isRu() ? `Создано: ${item.model}` : `Made with ${item.model}`) : (isRu() ? "Готовый результат" : "Finished result"))}</h3>
      <p class="card-text">${escapeHtml(caption)}</p>
      <div class="metrics">
        <span class="metric">${Number(item.likes || 0)} ${isRu() ? "лайков" : "likes"}</span>
        <span class="metric">${Number(item.shares || 0)} ${isRu() ? "поделились" : "shares"}</span>
        <span class="metric">${Number(item.remix_count || 0)} ${isRu() ? "вариантов" : "remixes"}</span>
      </div>
      ${data.me ? `<div class="actions compact">
        <button class="btn feed-like" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Нравится" : "Like"}</button>
        <button class="btn feed-share" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Поделиться" : "Share"}</button>
        ${canUseAsImageRef ? `<button class="btn feed-reference" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Как референс" : "Use as ref"}</button><button class="btn feed-remix" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Ремикс" : "Remix"}</button>` : ""}
      </div>` : ""}
    </article>
  `;
}

function promptCard(item) {
  return `
    <article class="paper">
      <p class="sticker pink">${isRu() ? "идея" : "idea"}</p>
      ${img(item.preview_url, item.title || "Prompt", true)}
      <h3>${escapeHtml(item.title || (isRu() ? "Идея без названия" : "Untitled idea"))}</h3>
      <p class="card-text">${escapeHtml(item.description || item.prompt_text || "")}</p>
      <div class="metrics">
        <span class="metric">${Number(item.likes || 0)} ${isRu() ? "лайков" : "likes"}</span>
        <span class="metric">${Number(item.uses_count || 0)} ${isRu() ? "запусков" : "uses"}</span>
      </div>
      ${data.me ? `<div class="actions compact">
        <button class="btn prompt-use" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "В студию" : "Use"}</button>
        <button class="btn prompt-copy" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Копия" : "Copy"}</button>
        <button class="btn prompt-like" data-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Нравится" : "Like"}</button>
      </div>` : ""}
    </article>
  `;
}

function generationCard(item) {
  const canChain = data.me && item.status === "done" && resultUrlFrom(item) && item.gen_type === "image";
  return `
    <article class="dark">
      <p class="sticker ${item.status === "done" ? "" : "pink"}">${escapeHtml(item.status || (isRu() ? "статус" : "status"))}</p>
      ${img(item.result_url, isRu() ? "Результат" : "Result", false, item.gen_type)}
      <h3>${escapeHtml(item.model || (isRu() ? "Работа" : "Work"))}</h3>
      <p class="card-text">${escapeHtml(item.prompt || "")}</p>
      <div class="metrics">
        <span class="metric">${escapeHtml(item.gen_type || (isRu() ? "создание" : "creation"))}</span>
        <span class="metric">${Number(item.credits_spent || 0)} ${isRu() ? "кредитов" : "credits"}</span>
      </div>
      ${data.me ? `<div class="actions compact">
        <button class="btn generation-reuse" data-generation-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Повторить идею" : "Reuse idea"}</button>
        ${canChain ? `<button class="btn generation-next-image" data-generation-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Вариант" : "Variant"}</button><button class="btn generation-next-video" data-generation-id="${escapeHtml(item.id)}" type="button">${isRu() ? "Оживить" : "Animate"}</button>` : ""}
      </div>` : ""}
    </article>
  `;
}

function hero() {
  return `
    <section class="hero">
      <div>
        <p class="eyebrow">${isRu() ? "Творческая AI-студия" : "Creative AI studio"}</p>
        <h1>${isRu() ? "Создавайте" : "Create"} <span class="riot-word">${isRu() ? "визуалы" : "visuals"}</span>${isRu() ? ", видео и музыку" : ", video and music"}</h1>
        <p class="lead">${isRu() ? "APIX помогает быстро собрать идею, выбрать стиль, запустить создание и сохранить результат в личной истории. До входа можно посмотреть примеры и возможности, после входа открывается полноценная студия." : "APIX helps you shape an idea, choose a style, create content, and keep everything in your personal history. Browse examples first, then sign in to unlock the full studio."}</p>
        <div class="actions">
          <a class="btn primary" href="#/profile">${isRu() ? "Войти через Telegram" : "Sign in with Telegram"}</a>
          <a class="btn yellow" href="#/examples">${isRu() ? "Смотреть примеры" : "See examples"}</a>
          <a class="btn" href="#/prompts">${isRu() ? "Библиотека идей" : "Idea library"}</a>
        </div>
      </div>
      <div class="poster-wall" aria-hidden="true">
        <div class="poster one"><span>${isRu() ? "фото / видео / музыка" : "image / video / music"}</span><b>${isRu() ? "одна студия" : "one studio"}</b></div>
        <div class="poster two"><span>${isRu() ? "вход через Telegram" : "Telegram sign-in"}</span><b>${isRu() ? "общий баланс" : "shared balance"}</b></div>
        <div class="poster three"><span>${isRu() ? "живые примеры" : "real examples"}</span><b>${isRu() ? "готовые работы" : "finished work"}</b></div>
      </div>
    </section>
  `;
}

function statusBar() {
  return `
    <section class="status-bar">
      <article class="paper cyan"><p class="sticker pink">${isRu() ? "Сервис" : "Service"}</p><h3>${data.health ? (isRu() ? "Работает" : "Ready") : (isRu() ? "Недоступен" : "Unavailable")}</h3><p>${escapeHtml(data.errors.health || (isRu() ? "Можно смотреть примеры и входить в аккаунт" : "Browse examples and sign in"))}</p></article>
      <article class="paper"><p class="sticker">${isRu() ? "Аккаунт" : "Account"}</p><h3>${data.me ? (isRu() ? "Вход выполнен" : "Signed in") : (isRu() ? "Гость" : "Guest")}</h3><p>${escapeHtml(data.me?.username || data.errors.me || (isRu() ? "Войдите для создания" : "Sign in to create"))}</p></article>
      <article class="paper yellow"><p class="sticker pink">${isRu() ? "Баланс" : "Balance"}</p><h3>${data.me ? Number(data.me.credits || 0) : "-"}</h3><p>${isRu() ? "кредиты для создания" : "credits to create"}</p></article>
      <article class="paper pink"><p class="sticker">${isRu() ? "Инструменты" : "Tools"}</p><h3>${Array.isArray(data.models) ? data.models.length : 0}</h3><p>${isRu() ? "вариантов для контента" : "ways to make content"}</p></article>
    </section>
  `;
}

function section(title, eyebrow, body) {
  return `<section class="section"><div><p class="eyebrow">${escapeHtml(eyebrow)}</p><h2>${escapeHtml(title)}</h2></div>${body}</section>`;
}

function home() {
  if (data.me) return dashboard();
  const feed = Array.isArray(data.feed) ? data.feed.slice(0, 3) : [];
  const prompts = data.prompts?.items ? data.prompts.items.slice(0, 3) : [];
  return [
    hero(),
    statusBar(),
    section(isRu() ? "Что можно создать" : "What you can create", isRu() ? "Возможности" : "Possibilities", `
      <div class="grid">
        <article class="paper yellow"><h3>${isRu() ? "Изображения" : "Images"}</h3><p>${isRu() ? "Обложки, рекламные кадры, персонажи, продукты и визуальные идеи для соцсетей." : "Covers, campaign visuals, characters, product shots, and social media ideas."}</p><a class="btn primary" href="#/profile">${isRu() ? "Начать после входа" : "Start after sign-in"}</a></article>
        <article class="paper cyan"><h3>${isRu() ? "Видео" : "Video"}</h3><p>${isRu() ? "Короткие ролики, промо-сцены, движение камеры и оживление статичных изображений." : "Short clips, promo scenes, camera motion, and animation from still images."}</p><a class="btn primary" href="#/examples">${isRu() ? "Смотреть примеры" : "See examples"}</a></article>
        <article class="paper pink"><h3>${isRu() ? "Музыка и идеи" : "Music and ideas"}</h3><p>${isRu() ? "Треки, настроение, тексты для промптов и быстрый помощник для формулировок." : "Tracks, mood ideas, prompt writing, and a quick assistant for better wording."}</p><a class="btn yellow" href="#/features">${isRu() ? "Все возможности" : "Explore features"}</a></article>
      </div>
    `),
    section(isRu() ? "Реальные примеры работ" : "Real examples", isRu() ? "Создано в APIX" : "Made in APIX", showcaseCards()),
    section(isRu() ? "Живая лента" : "Live gallery", isRu() ? "Готовые работы" : "Finished work", `<div class="grid">${feed.length ? feed.map(feedCard).join("") : empty(isRu() ? "Пока нет публичных работ." : "No public works yet.", data.errors.feed)}</div>`),
    section(isRu() ? "Библиотека идей" : "Idea library", isRu() ? "Готовые промпты" : "Ready ideas", `<div class="grid">${prompts.length ? prompts.map(promptCard).join("") : empty(isRu() ? "Пока нет идей в библиотеке." : "No ideas in the library yet.", data.errors.prompts)}</div>`),
  ].join("");
}

function dashboard() {
  const recent = Array.isArray(data.history) ? data.history.slice(0, 3) : [];
  return [
    section(`${isRu() ? "Добро пожаловать" : "Welcome"}, ${data.me.full_name || data.me.username || "creator"}`, isRu() ? "Рабочий стол" : "Dashboard", `
      <div class="status-bar">
        <article class="paper yellow"><p class="sticker pink">${isRu() ? "Баланс" : "Balance"}</p><h3>${Number(data.me.credits || 0)}</h3><p>${isRu() ? "кредитов доступно" : "credits available"}</p></article>
        <article class="paper cyan"><p class="sticker pink">${isRu() ? "Фото" : "Images"}</p><h3>${data.imageModels.length}</h3><p>${isRu() ? "вариантов создания" : "creative tools"}</p></article>
        <article class="paper"><p class="sticker">${isRu() ? "Видео" : "Video"}</p><h3>${data.videoModels.length}</h3><p>${isRu() ? "вариантов создания" : "creative tools"}</p></article>
        <article class="paper pink"><p class="sticker">${isRu() ? "Музыка" : "Music"}</p><h3>${data.musicModels.length}</h3><p>${isRu() ? "музыкальных режимов" : "music options"}</p></article>
      </div>
    `),
    section(isRu() ? "Быстрый старт" : "Quick start", isRu() ? "Создать" : "Create", `
      <div class="grid">
        <article class="paper yellow"><h3>${isRu() ? "Новая картинка" : "New image"}</h3><p>${isRu() ? "Откройте студию, выберите стиль и опишите идею обычными словами." : "Open the studio, choose a style, and describe your idea in plain language."}</p><a class="btn primary" href="#/studio">${isRu() ? "Открыть студию" : "Open studio"}</a></article>
        <article class="paper cyan"><h3>${isRu() ? "Лента работ" : "Gallery"}</h3><p>${isRu() ? "Посмотрите, что уже создают другие, и сохраните идеи для своей серии." : "See what others are creating and save ideas for your own series."}</p><a class="btn primary" href="#/feed">${isRu() ? "Открыть ленту" : "Open gallery"}</a></article>
        <article class="paper"><h3>${isRu() ? "Библиотека идей" : "Idea library"}</h3><p>${isRu() ? "Возьмите готовую формулировку и отправьте её в студию." : "Pick a ready-made idea and send it into the studio."}</p><a class="btn primary" href="#/prompts">${isRu() ? "Открыть библиотеку" : "Open library"}</a></article>
      </div>
    `),
    section(isRu() ? "Последние работы" : "Recent work", isRu() ? "История" : "History", `<div class="grid">${recent.length ? recent.map(generationCard).join("") : empty(isRu() ? "История появится после первых созданий." : "Your history will appear after your first creations.", data.errors.history)}</div>`),
  ].join("");
}

function showcaseCards() {
  const realItems = Array.isArray(data.feed) ? data.feed.filter((item) => item.result_url).slice(0, 3) : [];
  if (realItems.length) {
    return `<div class="grid">${realItems.map((item, index) => `
      <article class="dark showcase-card">
        <p class="sticker ${index === 1 ? "pink" : ""}">${isRu() ? "Реальная работа" : "Real work"}</p>
        ${img(item.result_url, isRu() ? "Пример из ленты" : "Gallery example")}
        <h3>${escapeHtml(isRu() ? ["Визуальная серия", "Образ для кампании", "Идея для публикации"][index] : ["Visual series", "Campaign look", "Post idea"][index])}</h3>
        <p>${escapeHtml(isRu() ? "Это готовый пример из публичной ленты APIX. После входа вы сможете создавать свои варианты в таком же рабочем пространстве." : "This is a finished example from the public APIX gallery. After sign-in, you can create your own variations in the same workspace.")}</p>
      </article>
    `).join("")}</div>`;
  }
  const examples = isRu()
    ? [
        ["Обложка для запуска", "Соберите визуал для продукта, афиши или соцсетей за один короткий сценарий."],
        ["Серия персонажа", "Создайте образ, сохраните удачный результат и развивайте его дальше."],
        ["Музыкальное настроение", "Опишите атмосферу проекта и получите идею для трека или промо."],
      ]
    : [
        ["Launch cover", "Create a product, poster, or social visual from one short brief."],
        ["Character series", "Build a character look, keep the best result, and grow it further."],
        ["Music mood", "Describe the project atmosphere and get an idea for a track or promo."],
      ];
  return `<div class="grid">${examples.map(([title, text], index) => `
    <article class="dark">
      <p class="sticker ${index === 1 ? "pink" : ""}">${isRu() ? "Пример" : "Example"} ${index + 1}</p>
      ${img("", title)}
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(text)}</p>
    </article>
  `).join("")}</div>`;
}

function examples() {
  return section(isRu() ? "Примеры работ" : "Examples of work", isRu() ? "Создано в APIX" : "Made in APIX", showcaseCards());
}

function features() {
  return section(isRu() ? "Что внутри" : "What is inside", isRu() ? "Возможности" : "Features", `
    <div class="grid">
      <article class="paper yellow"><h3>${isRu() ? "Вход через Telegram" : "Telegram sign-in"}</h3><p>${isRu() ? "Один аккаунт для сайта и бота: общий баланс, история и реферальный код." : "One account for the site and the bot: shared balance, history, and referral code."}</p></article>
      <article class="paper cyan"><h3>${isRu() ? "Студия создания" : "Creation studio"}</h3><p>${isRu() ? "Отдельные понятные формы для изображений, видео, музыки и помощника." : "Clear separate flows for images, video, music, and the assistant."}</p></article>
      <article class="paper"><h3>${isRu() ? "Библиотека идей" : "Idea library"}</h3><p>${isRu() ? "Готовые формулировки можно лайкать, сохранять и отправлять в студию." : "Ready-made ideas can be liked, saved, and sent into the studio."}</p></article>
      <article class="paper pink"><h3>${isRu() ? "Лента работ" : "Gallery"}</h3><p>${isRu() ? "Смотрите реальные работы, вдохновляйтесь и делитесь удачными результатами." : "Browse real work, get inspired, and share strong results."}</p></article>
      <article class="paper"><h3>${isRu() ? "Личная история" : "Personal history"}</h3><p>${isRu() ? "Все созданные материалы остаются в личном разделе." : "Everything you create stays in your personal workspace."}</p></article>
      <article class="paper cyan"><h3>${isRu() ? "Баланс" : "Balance"}</h3><p>${isRu() ? "Пакеты кредитов и текущий баланс видны прямо на сайте." : "Credit packs and your current balance are visible on the site."}</p></article>
    </div>
  `);
}

function authRequired() {
  if (data.me) return "";
  return `
    <article class="paper pink auth-warning">
      <p class="sticker">AUTH</p>
      <h3>${isRu() ? "Нужен вход через Telegram" : "Telegram sign-in required"}</h3>
      <p>${isRu() ? "Создание, история работ и персональный баланс доступны только после входа." : "Creation, personal history, and balance are available after sign-in."}</p>
      <a class="btn yellow" href="#/profile">${isRu() ? "Войти" : "Sign in"}</a>
    </article>
  `;
}

function modelId(model) {
  return model?.key || model?.model_key || "";
}

function modelName(model) {
  return model?.display_name || modelId(model) || (isRu() ? "Стиль" : "Style");
}

function modelPrice(model) {
  const credits = Number(model?.credits || 0);
  return credits ? `${credits} ${isRu() ? "кр." : "cr"}` : (isRu() ? "по тарифу" : "priced on use");
}

function modelsForMode(mode) {
  if (mode === "video") return data.videoModels || [];
  if (mode === "music") return data.musicModels || [];
  if (mode === "assistant") return [];
  return data.imageModels || [];
}

function firstModelId(mode) {
  return modelId(modelsForMode(mode)[0]);
}

function modelDetails(model, mode) {
  if (!model) return isRu() ? "Выберите стиль для создания." : "Choose a style to create.";
  const details = [];
  const ratios = model.aspect_ratios || [];
  const durations = model.durations || [];
  const modes = model.modes || [];
  if (ratios.length) details.push(`${isRu() ? "форматы" : "formats"}: ${ratios.slice(0, 4).join(", ")}`);
  if (durations.length) details.push(`${isRu() ? "длина" : "length"}: ${durations.slice(0, 4).join(", ")}s`);
  if (modes.length) details.push(`${isRu() ? "основа" : "start"}: ${modes.map((item) => item === "image" ? (isRu() ? "картинка" : "image") : (isRu() ? "текст" : "text")).join(", ")}`);
  if (!details.length && mode === "music") details.push(isRu() ? "музыка по описанию настроения" : "music from a mood description");
  return details.join(" · ") || (isRu() ? "универсальный стиль" : "versatile style");
}

function labelForValue(value) {
  const text = String(value || "");
  const labels = {
    text: isRu() ? "текст" : "text",
    image: isRu() ? "картинка" : "image",
    low: isRu() ? "мягкое движение" : "soft motion",
    high: isRu() ? "активное движение" : "active motion",
    basic: isRu() ? "стандарт" : "standard",
    hd: "HD",
    pro: "Pro",
  };
  return labels[text] || text;
}

function optionObjects(values, labels = {}) {
  return (values || []).filter(Boolean).map((item) => {
    if (typeof item === "object") return { value: item.value, label: item.label || item.value };
    return { value: item, label: labels[item] || labelForValue(item) };
  });
}

function selectControl(name, title, values, fallback = "", attrs = "") {
  const options = optionObjects(values);
  if (!options.length) return "";
  return `
    <label><span>${escapeHtml(title)}</span>
      <select name="${escapeHtml(name)}" ${attrs}>
        ${fallback ? `<option value="">${escapeHtml(fallback)}</option>` : ""}
        ${options.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("")}
      </select>
    </label>
  `;
}

function capabilityBadges(model, mode) {
  if (!model) return "";
  const badges = [];
  const modes = model.modes || [];
  const refs = Number(model.max_refs || 0);
  if (modes.includes("text")) badges.push(isRu() ? "по тексту" : "text");
  if (modes.includes("image")) badges.push(isRu() ? "по фото" : "image");
  if (refs > 0) badges.push(`${refs} ${isRu() ? "фото" : "refs"}`);
  if (model.aspect_ratios?.length) badges.push(isRu() ? "форматы" : "formats");
  if (model.has_quality || model.quality_options?.length) badges.push(isRu() ? "качество" : "quality");
  if (model.durations?.length) badges.push(isRu() ? "длина" : "duration");
  if (model.resolutions?.length) badges.push(isRu() ? "размер" : "size");
  if (model.is_per_second) badges.push(isRu() ? "цена за секунду" : "per second");
  if (!badges.length && mode === "music") badges.push(isRu() ? "музыка" : "music");
  return `<div class="capability-badges">${badges.map((badge) => `<span>${escapeHtml(badge)}</span>`).join("")}</div>`;
}

function dynamicSettings(mode, model) {
  if (mode === "assistant") {
    return `<div class="status-message">${isRu() ? "Помощник отвечает текстом. Настройки модели не нужны." : "Assistant replies with text. No model settings needed."}</div>`;
  }
  if (mode === "music") {
    return `
      <div class="dynamic-settings-grid">
        <label class="check"><input name="instrumental" type="checkbox"> ${isRu() ? "без вокала" : "instrumental"}</label>
      </div>
      <div class="capability-note">${isRu() ? "Для музыки важнее всего настроение, жанр, темп и примерная атмосфера." : "For music, mood, genre, tempo, and atmosphere matter most."}</div>
    `;
  }
  if (!model) {
    return `<div class="status-message is-warning">${isRu() ? "Сначала выберите модель." : "Choose a model first."}</div>`;
  }

  const controls = [];
  if (mode === "image") {
    controls.push(selectControl("aspect_ratio", isRu() ? "Формат" : "Format", model.aspect_ratios || [], isRu() ? "Авто" : "Auto", "data-smart-aspect"));
    if (model.quality_options?.length) {
      controls.push(selectControl("quality", isRu() ? "Качество" : "Quality", model.quality_options, "", "data-smart-quality"));
    } else if (model.has_quality) {
      controls.push(`<label><span>${isRu() ? "Качество" : "Quality"}</span><input name="quality" value="basic" data-smart-quality></label>`);
    } else {
      controls.push(`<input type="hidden" name="quality" value="basic">`);
    }
    if (model.counts?.length && Math.max(...model.counts.map(Number)) > 1) {
      controls.push(selectControl("count", isRu() ? "Количество" : "Count", model.counts, "", "data-smart-count"));
    }
  } else if (mode === "video") {
    controls.push(selectControl("mode", isRu() ? "Основа" : "Start from", model.modes || ["text"], "", "data-smart-mode"));
    controls.push(selectControl("duration", isRu() ? "Длина" : "Length", model.durations?.length ? model.durations.map((value) => `${value}`) : ["5"], "", "data-smart-duration"));
    controls.push(selectControl("aspect_ratio", isRu() ? "Формат" : "Format", model.aspect_ratios || [], isRu() ? "Авто" : "Auto", "data-smart-aspect"));
    controls.push(selectControl("resolution", isRu() ? "Размер" : "Size", model.resolutions || [], isRu() ? "Авто" : "Auto", "data-smart-resolution"));
    const motion = model.mode_options?.length ? model.mode_options : model.motion_controls || [];
    controls.push(selectControl("grok_mode", isRu() ? "Движение" : "Motion", motion, "", "data-smart-motion"));
  }

  const visibleControls = controls.filter(Boolean);
  return `
    ${capabilityBadges(model, mode)}
    <div class="dynamic-settings-grid">${visibleControls.length ? visibleControls.join("") : `<div class="status-message">${isRu() ? "Эта модель работает без дополнительных настроек." : "This model works without extra settings."}</div>`}</div>
    <div class="capability-note" data-capability-note>${referenceHint(mode, model)}</div>
  `;
}

function referenceHint(mode, model) {
  if (!model) return "";
  const modes = model.modes || [];
  if (mode === "video" && modes.includes("image") && !modes.includes("text")) {
    return isRu() ? "Этой модели нужно фото: добавьте кадр на шаге «Фото»." : "This model needs an image: add a frame in the Media step.";
  }
  if (mode === "video" && modes.includes("image")) {
    return isRu() ? "Можно начать с текста или оживить фото. Если добавите фото, режим переключится на «картинка»." : "Start from text or animate an image. If you add an image, image mode is used.";
  }
  if (mode === "image" && Number(model.max_refs || 0) > 1) {
    return `${isRu() ? "Можно использовать до" : "You can use up to"} ${model.max_refs} ${isRu() ? "фото-референсов." : "image references."}`;
  }
  return isRu() ? "Настройки подстроены под выбранную модель." : "Settings match the selected model.";
}

function modelCard(model, mode, index) {
  const id = modelId(model);
  return `
    <button class="comic-model-card ${index === 0 ? "is-selected" : ""}" data-model-choice data-mode="${escapeHtml(mode)}" data-model="${escapeHtml(id)}" type="button">
      <b>${escapeHtml(modelName(model))}</b>
      <span>${escapeHtml(modelPrice(model))}</span>
      <small>${escapeHtml(modelDetails(model, mode))}</small>
    </button>
  `;
}

function modelDropdown(mode, title) {
  const items = modelsForMode(mode);
  return `
    <details class="comic-dropdown" data-model-dropdown="${escapeHtml(mode)}" ${mode === "image" ? "open" : ""}>
      <summary>${escapeHtml(title)} <span>${items.length}</span></summary>
      <div class="comic-model-list">
        ${items.length ? items.map((model, index) => modelCard(model, mode, index)).join("") : `<p class="muted">${isRu() ? "Стили скоро появятся." : "Styles will appear soon."}</p>`}
      </div>
    </details>
  `;
}

function studioModeTitle(mode) {
  return {
    image: isRu() ? "Изображение" : "Image",
    video: isRu() ? "Видео" : "Video",
    music: isRu() ? "Музыка" : "Music",
    assistant: isRu() ? "Помощник" : "Assistant",
  }[mode] || mode;
}

function studioModeDescription(mode) {
  return {
    image: isRu() ? "картинки, обложки, продукты, персонажи" : "images, covers, products, characters",
    video: isRu() ? "ролики из текста или фото-кадра" : "clips from text or an image frame",
    music: isRu() ? "треки по настроению и жанру" : "tracks from mood and genre",
    assistant: isRu() ? "помощь с идеями и формулировками" : "help with ideas and wording",
  }[mode] || "";
}

function studioModeIcon(mode) {
  return icon({ image: "image", video: "video", music: "music", assistant: "assistant" }[mode] || "spark");
}

function studioSteps() {
  return [
    ["brief", icon("spark"), isRu() ? "Идея" : "Idea", isRu() ? "Опишите задумку" : "Describe it"],
    ["media", icon("upload"), isRu() ? "Фото" : "Media", isRu() ? "Добавьте референс" : "Add a reference"],
    ["model", icon("layers"), isRu() ? "Модель" : "Model", isRu() ? "Чем создаём" : "Choose engine"],
    ["settings", icon("settings"), isRu() ? "Настройки" : "Settings", isRu() ? "Формат и режим" : "Format and mode"],
    ["review", icon("check"), isRu() ? "Проверка" : "Review", isRu() ? "Стоимость и старт" : "Cost and launch"],
  ];
}

function studioStepTitle(step) {
  return {
    brief: isRu() ? "Опишите идею" : "Describe the idea",
    media: isRu() ? "Референсы и исходники" : "References and source media",
    model: isRu() ? "Модель и стиль" : "Model and style",
    settings: isRu() ? "Настройки результата" : "Result settings",
    review: isRu() ? "Проверка перед запуском" : "Review before launch",
  }[step] || step;
}

function modeRefs(mode) {
  if (!state.studio.refs[mode]) state.studio.refs[mode] = [];
  return state.studio.refs[mode];
}

function mediaPreviewHtml(mode) {
  const refs = modeRefs(mode);
  if (!refs.length) {
    return `
      <div class="reference-empty">
        ${icon(mode === "video" ? "video" : "image")}
        <b>${isRu() ? "Референс пока не добавлен" : "No reference yet"}</b>
        <span>${mode === "video"
          ? (isRu() ? "Для видео можно добавить фото или кадр, от которого начнётся движение." : "For video, add an image or frame to animate from.")
          : (isRu() ? "Добавьте фото, если нужно сохранить внешний вид, одежду, объект или композицию." : "Add a photo when you want to keep a look, outfit, object, or composition.")}</span>
      </div>
    `;
  }
  return refs.map((ref) => `
    <div class="reference-thumb">
      ${media(ref.preview || ref.url, ref.name || (isRu() ? "Референс" : "Reference"), { type: "image" })}
      <button class="reference-remove" data-remove-ref="${escapeHtml(mode)}" data-url="${escapeHtml(ref.url)}" type="button" aria-label="${isRu() ? "Убрать референс" : "Remove reference"}">×</button>
    </div>
  `).join("");
}

function studioModeButtons() {
  return ["image", "video", "music", "assistant"].map((mode) => `
    <button class="studio-mode-card ${state.studio.mode === mode ? "is-active" : ""}" data-mode="${mode}" type="button">
      ${studioModeIcon(mode)}
      <span><b>${studioModeTitle(mode)}</b><small>${studioModeDescription(mode)}</small></span>
    </button>
  `).join("");
}

function studioStepButtons() {
  return studioSteps().map(([step, stepIcon, title, hint]) => `
    <button class="studio-step ${state.studio.step === step ? "is-active" : ""}" data-studio-step="${step}" type="button">
      ${stepIcon}
      <span><b>${escapeHtml(title)}</b><small>${escapeHtml(hint)}</small></span>
    </button>
  `).join("");
}

function studioStepSection(step, html) {
  return `<section class="studio-step-section ${state.studio.step === step ? "is-active" : ""}" data-step-section="${step}"><h4>${escapeHtml(studioStepTitle(step))}</h4>${html}</section>`;
}

function referenceControls(mode, inputName) {
  if (mode === "music" || mode === "assistant") {
    return `
      <div class="reference-empty">
        ${icon(mode === "music" ? "music" : "assistant")}
        <b>${mode === "music" ? (isRu() ? "Медиа не нужно" : "No media needed") : (isRu() ? "Пишите текстом" : "Text only")}</b>
        <span>${mode === "music" ? (isRu() ? "Опишите жанр, настроение, темп и примерную атмосферу." : "Describe genre, mood, tempo, and atmosphere.") : (isRu() ? "Помощник работает с вашей идеей и вопросом." : "The assistant works with your idea and question.")}</span>
      </div>
    `;
  }
  return `
    <div class="reference-tools" data-reference-tools="${mode}">
      <label class="upload-zone">
        ${icon("upload")}
        <span><b>${isRu() ? "Загрузить фото" : "Upload image"}</b><small>${isRu() ? "JPG, PNG, WebP до 20 MB" : "JPG, PNG, WebP up to 20 MB"}</small></span>
        <input type="file" accept="image/jpeg,image/png,image/webp" data-reference-file="${mode}" hidden>
      </label>
      <label><span>${isRu() ? "Или ссылка на фото" : "Or image URL"}</span><input name="${inputName}" data-reference-input="${mode}" placeholder="https://..."></label>
    </div>
  `;
}

function promptTools(mode) {
  if (mode === "assistant") return "";
  return `
    <div class="prompt-tools">
      <button class="btn" data-prompt-improve="${escapeHtml(mode)}" type="button">${icon("spark")}${isRu() ? "Улучшить идею" : "Improve idea"}</button>
      ${mode === "image" || mode === "video" ? `<label class="btn prompt-photo-btn">${icon("image")}${isRu() ? "Промпт по фото" : "Photo to prompt"}<input type="file" accept="image/jpeg,image/png,image/webp" data-photo-prompt-file="${escapeHtml(mode)}" hidden></label>` : ""}
    </div>
  `;
}

function stepActions(prev, next) {
  return `
    <div class="step-actions">
      ${prev ? `<button class="btn" data-prev-step="${escapeHtml(prev)}" type="button">${isRu() ? "Назад" : "Back"}</button>` : ""}
      ${next ? `<button class="btn primary" data-next-step="${escapeHtml(next)}" type="button">${isRu() ? "Дальше" : "Next"}</button>` : ""}
    </div>
  `;
}

function modelPickerHtml() {
  return `
    <div class="comic-picker model-switchboard" id="comic-model-picker">
      <div class="model-picker-head">
        <div>
          <h3>${isRu() ? "Выберите модель" : "Choose a model"}</h3>
          <p>${isRu() ? "Список реальных моделей подстраивается под выбранный поток." : "The real model list follows the selected flow."}</p>
        </div>
        <label class="model-search"><span>${isRu() ? "Поиск" : "Search"}</span><input data-model-search placeholder="${isRu() ? "Название или возможность" : "Name or capability"}"></label>
      </div>
      ${modelDropdown("image", isRu() ? "Для изображений" : "For images")}
      ${modelDropdown("video", isRu() ? "Для видео" : "For video")}
      ${modelDropdown("music", isRu() ? "Для музыки" : "For music")}
    </div>
  `;
}

function estimateCost(mode, model, form = null) {
  if (mode === "assistant") return 0;
  if (!model) return 0;
  if (mode === "image") {
    const quality = form ? formValue(form, "quality") : "";
    if (quality && model.quality_prices && model.quality_prices[quality] != null) {
      return Number(model.quality_prices[quality] || model.credits || 0);
    }
    return Number(model.credits || 0);
  }
  if (mode === "video") {
    const duration = Number((form ? formValue(form, "duration") : 0) || model.durations?.[0] || 5);
    const rate = Number(model.credits_per_sec || model.credits || 0);
    return model.is_per_second ? rate * duration : Number(model.credits || 0);
  }
  return Number(model.credits || 0);
}

function reviewSummary(mode) {
  const form = document.querySelector(`.studio-form[data-form="${mode}"]`);
  const model = form ? findModel(mode, formValue(form, "model")) : findModel(mode, firstModelId(mode));
  const prompt = form ? String(formValue(form, mode === "assistant" ? "message" : "prompt") || "").trim() : "";
  const refs = modeRefs(mode).filter((ref) => ref.url);
  const cost = estimateCost(mode, model, form);
  const feedRemix = state.pendingFeedRemix?.feedId ? (isRu() ? "ремикс из ленты" : "feed remix") : (isRu() ? "новая работа" : "new work");
  const lines = [
    [isRu() ? "Поток" : "Flow", studioModeTitle(mode)],
    [isRu() ? "Модель" : "Model", mode === "assistant" ? (isRu() ? "Помощник APIX" : "APIX assistant") : modelName(model)],
    [isRu() ? "Стоимость" : "Cost", cost ? `${cost} ${isRu() ? "кредитов" : "credits"}` : (isRu() ? "без списания" : "included")],
    [isRu() ? "Референсы" : "References", `${refs.length}/${Number(model?.max_refs || 0) || (mode === "image" || mode === "video" ? 1 : 0)}`],
    [isRu() ? "Сценарий" : "Source", feedRemix],
  ];
  return `
    <div class="review-summary-grid">
      ${lines.map(([label, value]) => `<span><b>${escapeHtml(label)}</b><em>${escapeHtml(value)}</em></span>`).join("")}
    </div>
    <div class="prompt-preview ${prompt ? "" : "is-empty"}">${escapeHtml(prompt || (isRu() ? "Идея появится здесь перед запуском." : "Your idea will appear here before launch."))}</div>
    ${reviewWarnings(mode, model, refs)}
  `;
}

function reviewWarnings(mode, model, refs) {
  const warnings = [];
  const modelModes = model?.modes || [];
  if ((mode === "video" && modelModes.includes("image") && !modelModes.includes("text") && !refs.length)) {
    warnings.push(isRu() ? "Этой модели нужен первый кадр." : "This model needs a first frame.");
  }
  if (mode === "image" && refs.length > Number(model?.max_refs || 1)) {
    warnings.push(isRu() ? "Слишком много референсов для выбранной модели." : "Too many references for this model.");
  }
  if (state.pendingFeedRemix?.feedId) {
    warnings.push(isRu() ? "Будет использована скрытая идея автора из ленты." : "The hidden source idea from the feed will be used.");
  }
  if (!warnings.length) {
    return `<div class="status-message is-success">${isRu() ? "Всё готово: проверьте идею и запускайте." : "Ready: review the idea and launch."}</div>`;
  }
  return `<div class="status-message is-warning">${warnings.map(escapeHtml).join("<br>")}</div>`;
}

function reviewList(mode) {
  const lines = [
    [icon("spark"), isRu() ? "Идея написана обычным языком" : "Idea is written in plain language"],
    [icon("layers"), isRu() ? "Стиль выбран слева в списке моделей" : "Style is selected in the model list"],
  ];
  if (mode === "image") lines.push([icon("image"), isRu() ? "Фото-референс добавлен, если он нужен" : "Image reference is added if needed"]);
  if (mode === "video") lines.push([icon("video"), isRu() ? "Для анимации из фото выбран режим «картинка»" : "For image animation, choose image mode"]);
  if (mode === "music") lines.push([icon("music"), isRu() ? "Настроение, жанр и темп указаны" : "Mood, genre, and tempo are included"]);
  return `<div class="review-list">${lines.map(([itemIcon, text]) => `<span>${itemIcon}${escapeHtml(text)}</span>`).join("")}</div>`;
}

function studioStatusPanel() {
  return `
    <div class="studio-preview">
      <div class="preview-head">
        <span>${icon("play")}</span>
        <div>
          <b>${isRu() ? "Предпросмотр" : "Preview"}</b>
          <small>${isRu() ? "Фото, видео и статус запуска" : "Media and launch status"}</small>
        </div>
      </div>
      <div class="reference-preview" id="reference-preview">${mediaPreviewHtml(state.studio.mode)}</div>
    </div>
    <div class="sequence-panel" id="sequence-panel">
      ${sequencePanelHtml()}
    </div>
    <div class="queue-panel" id="studio-queue-panel">
      ${queuePanelHtml({ limit: 3, compact: true })}
    </div>
    <div class="paper studio-result" id="studio-result" role="status" aria-live="polite" aria-atomic="true">
      <p class="sticker">${isRu() ? "Статус" : "Status"}</p>
      <h3>${isRu() ? "Готово к старту" : "Ready"}</h3>
      <p>${isRu() ? "Следуйте шагам слева: идея, фото, модель, настройки, проверка." : "Follow the steps: idea, media, model, settings, review."}</p>
    </div>
  `;
}

function studio() {
  if (!data.me) {
    return section(isRu() ? "Студия создания" : "Creation studio", isRu() ? "Закрыто" : "Locked", `
      <div class="grid two">
        ${authRequired()}
        <article class="dark">
          <p class="sticker">TELEGRAM</p>
          <h3>${isRu() ? "Вход открывает рабочее пространство" : "Sign in to unlock the workspace"}</h3>
          <p class="lead">${isRu() ? "После входа появятся отдельные формы для изображений, видео, музыки и помощника. Все созданные материалы сохранятся в вашей истории." : "After sign-in, you will see separate flows for images, video, music, and the assistant. Everything you create will be saved in your history."}</p>
          <a class="btn primary" href="#/profile">${isRu() ? "Войти через Telegram" : "Sign in with Telegram"}</a>
        </article>
      </div>
    `);
  }

  const firstImage = modelId(data.imageModels?.[0]);
  const firstVideo = modelId(data.videoModels?.[0]);
  const firstMusic = modelId(data.musicModels?.[0]) || "suno/v4.5";
  const defaultModel = data.imageModels?.[0] || null;
  return section(isRu() ? "Студия создания" : "Creation studio", isRu() ? "Создать" : "Create", `
    <div class="studio-layout studio-fsm" data-current-mode="${escapeHtml(state.studio.mode)}" data-current-step="${escapeHtml(state.studio.step)}">
      <aside class="paper yellow studio-sidebar studio-sidebar-left">
        <p class="sticker pink">${isRu() ? "Пульт студии" : "Studio panel"}</p>
        <div class="studio-sidebar-title">
          ${icon("spark")}
          <div><h3>${isRu() ? "Что создаём?" : "What are we making?"}</h3><p>${isRu() ? "Выберите поток и двигайтесь по шагам." : "Choose a flow and move through the steps."}</p></div>
        </div>
        <div class="mode-rail">${studioModeButtons()}</div>
        <div class="studio-steps" aria-label="${isRu() ? "Шаги студии" : "Studio steps"}">${studioStepButtons()}</div>
      </aside>

      <section class="dark studio-panel studio-workbench">
        <div class="selected-model-strip" id="selected-model-strip">
          <p class="sticker">${isRu() ? "Выбрано" : "Selected"}</p>
          <h3 data-selected-model-name>${escapeHtml(modelName(defaultModel))}</h3>
          <p data-selected-model-details>${escapeHtml(modelDetails(defaultModel, "image"))}</p>
          <span class="metric" data-selected-model-price>${escapeHtml(modelPrice(defaultModel))}</span>
          <div data-selected-capabilities>${capabilityBadges(defaultModel, "image")}</div>
        </div>
        ${studioStepSection("model", `${modelPickerHtml()}${stepActions("media", "settings")}`)}

        <form class="studio-form is-active" data-form="image">
          <input type="hidden" name="model" value="${escapeHtml(firstImage)}">
          ${studioStepSection("brief", `<label><span>${isRu() ? "Идея" : "Idea"}</span><textarea name="prompt" required placeholder="${isRu() ? "Например: предметная съёмка белых кроссовок на глянцевом столе, мягкий свет, чистый фон..." : "Example: product shot of white sneakers on a glossy table, soft light, clean background..."}"></textarea></label>${promptTools("image")}${stepActions("", "media")}`)}
          ${studioStepSection("media", `${referenceControls("image", "reference_url")}${stepActions("brief", "model")}`)}
          ${studioStepSection("settings", `<div class="dynamic-settings" data-dynamic-settings="image">${dynamicSettings("image", defaultModel)}</div>${stepActions("model", "review")}`)}
          ${studioStepSection("review", `<div class="review-summary" data-review-summary="image">${reviewSummary("image")}</div>${reviewList("image")}<button class="btn primary launch-btn" type="submit">${icon("play")}${isRu() ? "Создать изображение" : "Create image"}</button>`)}
        </form>

        <form class="studio-form" data-form="video">
          <input type="hidden" name="model" value="${escapeHtml(firstVideo)}">
          ${studioStepSection("brief", `<label><span>${isRu() ? "Сцена и движение" : "Scene and motion"}</span><textarea name="prompt" required placeholder="${isRu() ? "Например: камера медленно приближается к витрине, неон отражается на стекле, плавное движение..." : "Example: camera slowly moves toward a storefront, neon reflects on glass, smooth motion..."}"></textarea></label>${promptTools("video")}${stepActions("", "media")}`)}
          ${studioStepSection("media", `${referenceControls("video", "image_url")}${stepActions("brief", "model")}`)}
          ${studioStepSection("settings", `<div class="dynamic-settings" data-dynamic-settings="video">${dynamicSettings("video", data.videoModels?.[0] || null)}</div>${stepActions("model", "review")}`)}
          ${studioStepSection("review", `<div class="review-summary" data-review-summary="video">${reviewSummary("video")}</div>${reviewList("video")}<button class="btn primary launch-btn" type="submit">${icon("play")}${isRu() ? "Создать видео" : "Create video"}</button>`)}
        </form>

        <form class="studio-form" data-form="music">
          <input type="hidden" name="model" value="${escapeHtml(firstMusic)}">
          ${studioStepSection("brief", `<label><span>${isRu() ? "Настроение" : "Mood"}</span><textarea name="prompt" required placeholder="${isRu() ? "Например: энергичный synth-pop для fashion ролика, 120 bpm, светлый припев..." : "Example: energetic synth-pop for a fashion clip, 120 bpm, bright hook..."}"></textarea></label>${promptTools("music")}${stepActions("", "model")}`)}
          ${studioStepSection("media", `${referenceControls("music", "")}${stepActions("brief", "model")}`)}
          ${studioStepSection("settings", `<div class="dynamic-settings" data-dynamic-settings="music">${dynamicSettings("music", data.musicModels?.[0] || null)}</div>${stepActions("model", "review")}`)}
          ${studioStepSection("review", `<div class="review-summary" data-review-summary="music">${reviewSummary("music")}</div>${reviewList("music")}<button class="btn primary launch-btn" type="submit">${icon("play")}${isRu() ? "Создать музыку" : "Create music"}</button>`)}
        </form>

        <form class="studio-form" data-form="assistant">
          ${studioStepSection("brief", `<label><span>${isRu() ? "Вопрос" : "Question"}</span><textarea name="message" required placeholder="${isRu() ? "Помоги улучшить идею для fashion-съёмки, сделать её короче и понятнее..." : "Help me improve a fashion shoot idea and make it clearer..."}"></textarea></label>${stepActions("", "settings")}`)}
          ${studioStepSection("media", `${referenceControls("assistant", "")}${stepActions("brief", "settings")}`)}
          ${studioStepSection("settings", `<div class="dynamic-settings" data-dynamic-settings="assistant">${dynamicSettings("assistant", null)}</div>${stepActions("brief", "review")}`)}
          ${studioStepSection("review", `<div class="review-summary" data-review-summary="assistant">${reviewSummary("assistant")}</div>${reviewList("assistant")}<button class="btn primary launch-btn" type="submit">${icon("play")}${isRu() ? "Спросить помощника" : "Ask assistant"}</button>`)}
        </form>
      </section>

      <aside class="studio-sidebar studio-sidebar-right">
        ${studioStatusPanel()}
      </aside>
    </div>
  `);
}

function sequencePanelHtml() {
  const remix = state.pendingFeedRemix;
  return `
    <div class="paper sequence-card">
      <p class="sticker pink">${isRu() ? "Цепочка" : "Sequence"}</p>
      <h3>${isRu() ? "Последовательная генерация" : "Sequential creation"}</h3>
      <p>${isRu() ? "Создайте картинку, дождитесь готовности, затем сделайте вариант или оживите её в видео." : "Create an image, wait until it is ready, then make a variant or animate it into video."}</p>
      ${remix ? `<div class="status-message is-warning">${isRu() ? "Активен ремикс из ленты" : "Feed remix is active"} #${escapeHtml(remix.feedId)}</div><button class="btn" data-clear-feed-remix type="button">${isRu() ? "Отменить ремикс" : "Clear remix"}</button>` : ""}
    </div>
  `;
}

function queueCard(item, compact = false) {
  const url = resultUrlFrom(item);
  const status = statusLabel(item.status);
  const canChain = isDoneStatus(item.status) && url && item.mode === "image";
  return `
    <article class="queue-item ${queueStatusClass(item.status)}">
      <div class="queue-item-main">
        <span class="queue-dot" aria-hidden="true"></span>
        <div>
          <b>${escapeHtml(item.model || studioModeTitle(item.mode))}</b>
          <small>#${escapeHtml(item.gen_id)} · ${escapeHtml(status)} · ${Number(item.credits_spent || 0)} ${isRu() ? "кр." : "cr"}</small>
        </div>
      </div>
      ${!compact && url ? media(url, isRu() ? "Результат" : "Result", { type: item.mode }) : ""}
      ${!compact ? `<p class="card-text">${escapeHtml(item.prompt || "")}</p>` : ""}
      <div class="actions compact">
        <button class="btn queue-reuse" data-queue-gen="${escapeHtml(item.gen_id)}" type="button">${isRu() ? "Идея" : "Idea"}</button>
        ${canChain ? `<button class="btn queue-next-image" data-queue-gen="${escapeHtml(item.gen_id)}" type="button">${isRu() ? "Вариант" : "Variant"}</button><button class="btn queue-next-video" data-queue-gen="${escapeHtml(item.gen_id)}" type="button">${isRu() ? "Видео" : "Video"}</button>` : ""}
      </div>
    </article>
  `;
}

function queuePanelHtml(options = {}) {
  const limit = options.limit || 4;
  const compact = Boolean(options.compact);
  const items = state.queue.slice(0, limit);
  return `
    <div class="queue-head">
      <div>
        <p class="sticker">${isRu() ? "Очередь" : "Queue"}</p>
        <h3>${isRu() ? "Активные задачи" : "Active jobs"}</h3>
      </div>
      <button class="btn" data-refresh-queue type="button">${isRu() ? "Обновить" : "Refresh"}</button>
    </div>
    <div class="queue-list">
      ${items.length ? items.map((item) => queueCard(item, compact)).join("") : `<div class="empty">${isRu() ? "Активных задач нет. Запустите создание в студии." : "No active jobs. Start a creation in the studio."}</div>`}
    </div>
  `;
}

function renderQueuePanels() {
  const studioQueue = document.getElementById("studio-queue-panel");
  if (studioQueue) studioQueue.innerHTML = queuePanelHtml({ limit: 3, compact: true });
  const worksQueue = document.getElementById("works-queue-panel");
  if (worksQueue) worksQueue.innerHTML = queuePanelHtml({ limit: 12, compact: false });
  const sequence = document.getElementById("sequence-panel");
  if (sequence) sequence.innerHTML = sequencePanelHtml();
  bindQueueActions();
}

async function pollQueue() {
  if (!token()) return;
  const active = activeQueueItems();
  if (!active.length) return;
  await Promise.all(active.map(async (item) => {
    try {
      const result = await genApi(`/generations/${item.gen_id}`);
      upsertQueueItem(queueItemFromGeneration(result, item));
    } catch (error) {
      item.status = "failed";
      item.error = error.message;
      item.updated_at = new Date().toISOString();
    }
  }));
  persistQueue();
  renderQueuePanels();
  if (routeName() === "works" || routeName() === "studio" || routeName() === "home") {
    await load({ route: routeName(), force: ["history", "me"] });
  }
}

function startQueuePolling() {
  if (state.queueTimer) clearInterval(state.queueTimer);
  if (!token() || !activeQueueItems().length) {
    state.queueTimer = null;
    return;
  }
  state.queueTimer = setInterval(() => {
    pollQueue().catch(() => {});
  }, queuePollMs);
}

function queueItemById(id) {
  return state.queue.find((item) => Number(item.gen_id) === Number(id))
    || (Array.isArray(data.history) ? data.history.find((item) => Number(item.id) === Number(id)) : null);
}

function openStudioWithItem(item, targetMode) {
  if (!item) return;
  const url = resultUrlFrom(item);
  state.pendingPrompt = { mode: targetMode, text: item.prompt || "" };
  state.pendingReference = url ? { mode: targetMode, url, name: item.model || (isRu() ? "Результат" : "Result") } : null;
  state.pendingFeedRemix = null;
  state.studio.mode = targetMode;
  state.studio.step = targetMode === "music" ? "brief" : "media";
  if (routeName() === "studio") {
    render();
  } else {
    location.hash = "#/studio";
  }
}

function prompts() {
  const items = data.prompts?.items || [];
  return section(isRu() ? "Библиотека идей" : "Idea library", isRu() ? "Готовые формулировки" : "Ready-made ideas", `
    <div class="toolbar">
      <button class="btn prompt-filter" data-source="catalog" type="button">${isRu() ? "Все" : "All"}</button>
      <button class="btn prompt-filter" data-source="popular" type="button">${isRu() ? "Популярные" : "Popular"}</button>
      <button class="btn prompt-filter" data-source="best" type="button">${isRu() ? "Лучшие" : "Best"}</button>
      ${data.me ? `<button class="btn primary" id="toggle-prompt-submit" type="button">${isRu() ? "Добавить идею" : "Submit idea"}</button>` : `<a class="btn primary" href="#/profile">${isRu() ? "Войти, чтобы использовать" : "Sign in to use"}</a>`}
    </div>
    <div id="prompt-submit-panel" class="dark submit-panel" hidden>
      <form id="prompt-submit-form" class="studio-form is-active">
        <h3>${isRu() ? "Отправить идею" : "Submit an idea"}</h3>
        <label><span>${isRu() ? "Название" : "Title"}</span><input name="title" placeholder="${isRu() ? "Можно оставить пустым" : "Optional"}"></label>
        <label><span>${isRu() ? "Ссылка на превью" : "Preview link"}</span><input name="preview_url" placeholder="https://..."></label>
        <label><span>${isRu() ? "Текст идеи" : "Idea text"}</span><textarea name="prompt_text" required></textarea></label>
        <label><span>${isRu() ? "Метки" : "Tags"}</span><input name="tags" placeholder="${isRu() ? "кино, реализм" : "cinematic, realism"}"></label>
        <button class="btn primary" type="submit">${isRu() ? "Отправить на проверку" : "Send for review"}</button>
      </form>
    </div>
    <div class="grid">${items.length ? items.map(promptCard).join("") : empty(isRu() ? "Пока нет идей в библиотеке." : "No ideas in the library yet.", data.errors.prompts)}</div>
  `);
}

function feed() {
  const items = Array.isArray(data.feed) ? data.feed : [];
  return section(isRu() ? "Лента работ" : "Gallery", isRu() ? "Реальные примеры" : "Real examples", `
    <div class="toolbar">
      <button class="btn feed-filter" data-source="feed" type="button">${isRu() ? "Новые" : "Recent"}</button>
      <button class="btn feed-filter" data-source="top" type="button">${isRu() ? "Лучшие за день" : "Top today"}</button>
      ${data.me ? `<a class="btn primary" href="#/studio">${isRu() ? "Создать своё" : "Create your own"}</a>` : `<a class="btn primary" href="#/profile">${isRu() ? "Войти для действий" : "Sign in to interact"}</a>`}
    </div>
    <div class="grid">${items.length ? items.map(feedCard).join("") : empty(isRu() ? "Пока нет публичных работ." : "No public works yet.", data.errors.feed)}</div>
  `);
}

function works() {
  if (!data.me) {
    return section(isRu() ? "Мои работы" : "My works", isRu() ? "Закрыто" : "Locked", `
      <div class="grid two">
        ${authRequired()}
        <article class="dark">
          <p class="sticker">${isRu() ? "Личное" : "Private"}</p>
          <h3>${isRu() ? "История доступна после входа" : "History appears after sign-in"}</h3>
          <p>${isRu() ? "Работы привязаны к Telegram-аккаунту и общему балансу APIX." : "Your work is connected to your Telegram account and APIX balance."}</p>
        </article>
      </div>
    `);
  }

  const items = Array.isArray(data.history) ? data.history : [];
  return section(isRu() ? "Мои работы" : "My works", isRu() ? "История" : "History", `
    <div class="queue-wide" id="works-queue-panel">${queuePanelHtml({ limit: 12, compact: false })}</div>
    <div class="grid">${items.length ? items.map(generationCard).join("") : empty(isRu() ? "История появится после первых созданий." : "Your history will appear after your first creations.", data.errors.history)}</div>
  `);
}

function billing() {
  const plans = Array.isArray(data.plans) ? data.plans : [];
  return section(isRu() ? "Баланс и пакеты" : "Balance and packs", isRu() ? "Цены" : "Pricing", `
    <div class="grid">${plans.length ? plans.map((p) => `
      <article class="paper cyan">
        <p class="sticker pink">${escapeHtml(p.key)}</p>
        <h3>${escapeHtml(p.label)}</h3>
        <p><b>${Number(p.credits || 0)}</b> ${isRu() ? "кредитов" : "credits"}</p>
        <p class="mono">${Number(p.price_rub || 0)} RUB${p.price_stars ? ` / ${p.price_stars} Stars` : ""}</p>
      </article>`).join("") : empty(isRu() ? "Пакеты временно не загружены." : "Packs are not loaded yet.", data.errors.plans)}</div>
  `);
}

function telegramLoginSlot() {
  const username = data.authConfig?.bot_username;
  if (!username) return empty(isRu() ? "Вход через Telegram пока недоступен." : "Telegram sign-in is not available yet.", data.errors.authConfig);
  return `<div id="telegram-login-slot" class="telegram-slot" data-bot="${escapeHtml(username)}"></div>`;
}

function profile() {
  const user = data.me;
  return section(isRu() ? "Вход через Telegram" : "Telegram sign-in", isRu() ? "Профиль" : "Profile", `
    <div class="grid two">
      <article class="paper">
        <p class="sticker pink">${isRu() ? "Аккаунт" : "Account"}</p>
        <h3>${escapeHtml(user?.full_name || user?.username || (isRu() ? "Гость" : "Guest"))}</h3>
        <p class="mono">${user ? `tg ${escapeHtml(user.tg_id)}` : (isRu() ? "не подключено" : "not connected")}</p>
        <p>${user ? `${Number(user.credits || 0)} ${isRu() ? "кредитов" : "credits"}` : (isRu() ? "Войдите через Telegram, чтобы создавать прямо на сайте." : "Sign in with Telegram to create directly on the site.")}</p>
        ${user ? `<button class="btn" id="logout" type="button">${isRu() ? "Выйти" : "Logout"}</button>` : ""}
      </article>
      <article class="dark">
        <p class="sticker">TELEGRAM</p>
        <h3>${isRu() ? "Быстрый вход" : "Quick sign-in"}</h3>
        <p class="muted">${isRu() ? "После входа откроется студия, история, действия в ленте и библиотека идей." : "After sign-in, the studio, history, gallery actions, and idea library unlock."}</p>
        ${telegramLoginSlot()}
      </article>
    </div>
  `);
}

const views = { home, examples, features, studio, prompts, feed, works, billing, profile };

function resultSummary(result) {
  if (!result) return "";
  if (result.reply) return `<p class="result-text">${escapeHtml(result.reply)}</p>`;
  const id = result.id ? `#${result.id}` : "";
  const status = result.status ? escapeHtml(result.status) : (isRu() ? "запущено" : "started");
  return `<div class="result-summary"><span class="metric">${escapeHtml(id || status)}</span><span class="metric">${status}</span></div>`;
}

function showResult(title, text, result) {
  const box = document.getElementById("studio-result");
  if (!box) return;
  box.innerHTML = `
    <p class="sticker">${isRu() ? "Статус" : "Status"}</p>
    <h3>${escapeHtml(title)}</h3>
    <p>${escapeHtml(text)}</p>
    ${resultSummary(result)}
    ${result?.result_url ? media(result.result_url, isRu() ? "Результат" : "Result", { type: result.gen_type }) : ""}
  `;
}

function flash(title, text) {
  const box = document.createElement("div");
  const isError = /ошибка|error/i.test(title);
  box.className = "toast paper yellow";
  box.setAttribute("role", isError ? "alert" : "status");
  box.setAttribute("aria-live", isError ? "assertive" : "polite");
  box.setAttribute("aria-atomic", "true");
  box.innerHTML = `<h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p>`;
  document.body.appendChild(box);
  setTimeout(() => box.remove(), 3200);
}

function formValue(form, name) {
  return new FormData(form).get(name);
}

function setBusy(target, busy) {
  if (!target) return;
  target.classList?.toggle("is-busy", busy);
  if (busy) {
    target.setAttribute("aria-busy", "true");
  } else {
    target.removeAttribute("aria-busy");
  }
  if (target.matches?.("button")) {
    target.disabled = busy;
    return;
  }
  target.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
}

async function withBusy(target, fn) {
  if (!target || target.dataset.busy === "1") return null;
  target.dataset.busy = "1";
  setBusy(target, true);
  try {
    return await fn();
  } finally {
    delete target.dataset.busy;
    setBusy(target, false);
  }
}

async function submitStudio(form) {
  if (!data.me) {
    showResult(isRu() ? "Нужен вход" : "Sign-in required", isRu() ? "Войдите через Telegram в разделе профиля." : "Sign in with Telegram in the profile section.", null);
    return;
  }
  const mode = form.dataset.form;
  const selectedModel = findModel(mode, formValue(form, "model"));
  if (mode === "video") {
    const refs = modeRefs("video").map((ref) => ref.url).filter(Boolean);
    const selectedStart = formValue(form, "mode") || "text";
    const modelModes = selectedModel?.modes || [];
    const requiresImage = selectedStart === "image" || (modelModes.includes("image") && !modelModes.includes("text"));
    if (requiresImage && !refs.length && !formValue(form, "image_url")) {
      state.studio.step = "media";
      switchStudioStep("media");
      showResult(isRu() ? "Нужно фото" : "Image needed", isRu() ? "Эта настройка требует фото или кадр для старта видео." : "This setting needs an image or frame to start the video.", null);
      return;
    }
  }
  showResult(isRu() ? "Запускаю" : "Starting", isRu() ? "Отправляем вашу идею на создание..." : "Sending your idea for creation...", null);
  try {
    let result;
    if (mode === "image") {
      const refs = modeRefs("image").map((ref) => ref.url).filter(Boolean);
      const payload = {
        model: formValue(form, "model") || formValue(form, "fallback_model"),
        prompt: formValue(form, "prompt"),
        prompt_id: state.activePromptId || null,
        aspect_ratio: formValue(form, "aspect_ratio") || null,
        quality: formValue(form, "quality") || "basic",
        count: Number(formValue(form, "count") || 1),
        reference_url: formValue(form, "reference_url") || refs[0] || null,
        reference_urls: refs.slice(1),
      };
      if (state.pendingFeedRemix?.feedId) {
        result = await genApi(`/feed/${state.pendingFeedRemix.feedId}/remix`, {
          method: "POST",
          body: JSON.stringify({
            model: payload.model,
            mode: payload.reference_url ? "image" : "text",
            aspect_ratio: payload.aspect_ratio,
            quality: payload.quality,
            count: payload.count,
            image_url: payload.reference_url,
            reference_urls: payload.reference_urls,
          }),
        });
      } else {
        result = await genApi("/generate/image", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
    } else if (mode === "video") {
      const refs = modeRefs("video").map((ref) => ref.url).filter(Boolean);
      const imageUrl = formValue(form, "image_url") || refs[0] || null;
      const payload = {
        model: formValue(form, "model") || formValue(form, "fallback_model"),
        prompt: formValue(form, "prompt"),
        mode: imageUrl ? "image" : (formValue(form, "mode") || "text"),
        duration: Number(formValue(form, "duration") || 5),
        aspect_ratio: formValue(form, "aspect_ratio") || null,
        resolution: formValue(form, "resolution") || null,
        image_url: imageUrl,
        reference_urls: refs.slice(1),
        grok_mode: formValue(form, "grok_mode") || "normal",
      };
      if (state.pendingFeedRemix?.feedId) {
        result = await genApi(`/feed/${state.pendingFeedRemix.feedId}/remix`, {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } else {
        result = await genApi("/generate/video", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
    } else if (mode === "music") {
      const model = formValue(form, "model");
      const payload = {
        prompt: formValue(form, "prompt"),
        instrumental: Boolean(form.querySelector('[name="instrumental"]').checked),
      };
      if (model) payload.model = model;
      try {
        result = await genApi("/generate/music", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } catch (error) {
        if (!model || !/model|field|extra|unexpected|unknown|422/i.test(error.message)) throw error;
        delete payload.model;
        result = await genApi("/generate/music", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
    } else {
      result = await genApi("/assistant", {
        method: "POST",
        body: JSON.stringify({ message: formValue(form, "message"), history: [] }),
      });
    }
    if (result?.id) {
      upsertQueueItem(queueItemFromGeneration(result, {
        mode,
        source: state.pendingFeedRemix?.feedId ? "feed_remix" : "studio",
      }));
      state.pendingFeedRemix = null;
      state.activePromptId = null;
    }
    showResult(mode === "assistant" ? (isRu() ? "Ответ помощника" : "Assistant reply") : (isRu() ? "Создание запущено" : "Creation started"), isRu() ? "Работа появится в истории, когда будет готова." : "The work will appear in your history when it is ready.", result);
    await load({ route: routeName(), force: ["me", "history"] });
    renderQueuePanels();
  } catch (error) {
    showResult(isRu() ? "Не получилось" : "Something went wrong", error.message, null);
  }
}

function findModel(mode, id) {
  return modelsForMode(mode).find((model) => modelId(model) === id) || modelsForMode(mode)[0] || null;
}

function optionList(values, fallbackLabel) {
  const clean = (values || []).filter(Boolean);
  if (!clean.length) return `<option value="">${escapeHtml(fallbackLabel)}</option>`;
  return clean.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
}

function updateSmartControls(mode, model) {
  const form = document.querySelector(`.studio-form[data-form="${mode}"]`);
  if (!form) return;
  const dynamic = form.querySelector(`[data-dynamic-settings="${mode}"]`);
  if (dynamic) dynamic.innerHTML = dynamicSettings(mode, model);
  if (!model) return;
  const aspect = form.querySelector("[data-smart-aspect]");
  if (aspect) {
    aspect.innerHTML = `<option value="">${isRu() ? "Авто" : "Auto"}</option>${optionList(model.aspect_ratios || [], isRu() ? "Авто" : "Auto")}`;
  }
  const modeSelect = form.querySelector("[data-smart-mode]");
  if (modeSelect) {
    const modes = (model.modes || ["text"]).map((item) => ({
      value: item,
      label: item === "image" ? (isRu() ? "картинка" : "image") : (isRu() ? "текст" : "text"),
    }));
    modeSelect.innerHTML = modes.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
  }
  const duration = form.querySelector("[data-smart-duration]");
  if (duration) {
    const values = model.durations?.length ? model.durations : [5];
    duration.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}s</option>`).join("");
  }
  const resolution = form.querySelector("[data-smart-resolution]");
  if (resolution) {
    resolution.innerHTML = `<option value="">${isRu() ? "Авто" : "Auto"}</option>${optionList(model.resolutions || [], isRu() ? "Авто" : "Auto")}`;
  }
  const quality = form.querySelector("[data-smart-quality]");
  if (quality && quality.tagName === "SELECT") {
    const options = optionObjects(model.quality_options || []);
    quality.innerHTML = options.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
  }
  const count = form.querySelector("[data-smart-count]");
  if (count) {
    count.innerHTML = (model.counts || [1]).map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  }
  const motion = form.querySelector("[data-smart-motion]");
  if (motion) {
    const values = model.mode_options?.length ? model.mode_options : model.motion_controls || [];
    motion.innerHTML = optionObjects(values).map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
  }
  updateReviewSummary(mode);
}

function updateReviewSummary(mode) {
  const summary = document.querySelector(`[data-review-summary="${mode}"]`);
  if (summary) summary.innerHTML = reviewSummary(mode);
}

function updateAllReviewSummaries() {
  ["image", "video", "music", "assistant"].forEach(updateReviewSummary);
}

function updateSelectedModel(mode, id) {
  const model = findModel(mode, id);
  const form = document.querySelector(`.studio-form[data-form="${mode}"]`);
  if (form && model) {
    const input = form.querySelector('input[name="model"]');
    if (input) input.value = modelId(model);
  }
  document.querySelectorAll("[data-model-choice]").forEach((button) => {
    button.classList.toggle("is-selected", button.dataset.mode === mode && button.dataset.model === modelId(model));
  });
  const name = document.querySelector("[data-selected-model-name]");
  const details = document.querySelector("[data-selected-model-details]");
  const price = document.querySelector("[data-selected-model-price]");
  const capabilities = document.querySelector("[data-selected-capabilities]");
  if (name) name.textContent = mode === "assistant" ? (isRu() ? "Помощник APIX" : "APIX assistant") : modelName(model);
  if (details) details.textContent = mode === "assistant" ? (isRu() ? "Помогает улучшать идеи и тексты." : "Helps improve ideas and text.") : modelDetails(model, mode);
  if (price) price.textContent = mode === "assistant" ? (isRu() ? "включено" : "included") : modelPrice(model);
  if (capabilities) capabilities.innerHTML = mode === "assistant" ? "" : capabilityBadges(model, mode);
  updateSmartControls(mode, model);
  updateReviewSummary(mode);
}

function switchStudioMode(mode) {
  state.studio.mode = mode;
  const layout = document.querySelector(".studio-layout");
  if (layout) layout.dataset.currentMode = mode;
  document.querySelectorAll(".mode-tab").forEach((item) => item.classList.toggle("is-active", item.dataset.mode === mode));
  document.querySelectorAll(".studio-mode-card").forEach((item) => item.classList.toggle("is-active", item.dataset.mode === mode));
  document.querySelectorAll(".studio-form").forEach((form) => form.classList.toggle("is-active", form.dataset.form === mode));
  document.querySelectorAll("[data-model-dropdown]").forEach((dropdown) => {
    dropdown.open = dropdown.dataset.modelDropdown === mode;
    dropdown.hidden = mode === "assistant" ? true : dropdown.dataset.modelDropdown !== mode;
  });
  updateSelectedModel(mode, firstModelId(mode));
  syncReferenceInputs();
  updateMediaPreview();
  switchStudioStep(state.studio.step);
  updateReviewSummary(mode);
}

function switchStudioStep(step) {
  state.studio.step = step;
  const layout = document.querySelector(".studio-layout");
  if (layout) layout.dataset.currentStep = step;
  document.querySelectorAll("[data-studio-step]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.studioStep === step);
  });
  document.querySelectorAll("[data-step-section]").forEach((section) => {
    section.classList.toggle("is-active", section.dataset.stepSection === step);
  });
}

function updateMediaPreview() {
  const preview = document.getElementById("reference-preview");
  if (preview) {
    preview.innerHTML = mediaPreviewHtml(state.studio.mode);
    bindReferenceRemove();
  }
}

function bindReferenceRemove() {
  document.querySelectorAll("[data-remove-ref]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      state.studio.refs[button.dataset.removeRef] = modeRefs(button.dataset.removeRef).filter((ref) => ref.url !== button.dataset.url);
      syncReferenceInputs();
      updateMediaPreview();
      refreshDynamicSettings();
    });
  });
}

function syncReferenceInputs() {
  ["image", "video"].forEach((mode) => {
    const refs = modeRefs(mode);
    const primary = refs[0]?.url || "";
    const form = document.querySelector(`.studio-form[data-form="${mode}"]`);
    if (!form) return;
    const inputName = mode === "video" ? "image_url" : "reference_url";
    const input = form.querySelector(`[name="${inputName}"]`);
    if (input && input.value !== primary) input.value = primary;
  });
}

function currentStudioModel() {
  const mode = state.studio.mode;
  const form = document.querySelector(`.studio-form[data-form="${mode}"]`);
  const id = form?.querySelector('input[name="model"]')?.value || firstModelId(mode);
  return findModel(mode, id);
}

function refreshDynamicSettings() {
  const model = currentStudioModel();
  updateSmartControls(state.studio.mode, model);
}

function filterModelCards(query) {
  const needle = String(query || "").trim().toLowerCase();
  document.querySelectorAll("[data-model-choice]").forEach((button) => {
    const text = button.textContent.toLowerCase();
    button.hidden = Boolean(needle && !text.includes(needle));
  });
}

function promptTextarea(mode) {
  return document.querySelector(`.studio-form[data-form="${mode}"] textarea[name="${mode === "assistant" ? "message" : "prompt"}"]`);
}

async function improvePrompt(mode, button) {
  const textarea = promptTextarea(mode);
  const prompt = String(textarea?.value || "").trim();
  if (!prompt) {
    flash(isRu() ? "Нужна идея" : "Idea needed", isRu() ? "Сначала напишите короткое описание." : "Write a short idea first.");
    return;
  }
  await withBusy(button, async () => {
    const result = await genApi("/prompt/improve", {
      method: "POST",
      body: JSON.stringify({ prompt, kind: mode }),
    });
    if (textarea) {
      textarea.value = result.prompt || prompt;
      textarea.focus();
    }
    updateReviewSummary(mode);
    flash(isRu() ? "Идея улучшена" : "Idea improved", isRu() ? "Проверьте текст перед запуском." : "Review the text before launch.");
  });
}

async function promptFromPhoto(file, mode, trigger) {
  if (!file) return;
  if (!/^image\/(jpeg|png|webp)$/i.test(file.type || "")) {
    flash(isRu() ? "Ошибка" : "Error", isRu() ? "Поддерживаются JPG, PNG и WebP." : "JPG, PNG, and WebP are supported.");
    return;
  }
  await withBusy(trigger.closest?.(".prompt-photo-btn") || trigger, async () => {
    const fd = new FormData();
    fd.append("file", file);
    const result = await genApi("/photo-prompt", { method: "POST", body: fd });
    const textarea = promptTextarea(mode);
    if (textarea) {
      const current = String(textarea.value || "").trim();
      textarea.value = current ? `${current}\n\n${result.prompt}` : (result.prompt || "");
      textarea.focus();
    }
    updateReviewSummary(mode);
    flash(isRu() ? "Промпт готов" : "Prompt ready", isRu() ? "Описание фото добавлено в идею." : "The photo description was added to the idea.");
  });
}

function setReferenceFromUrl(mode, url, name = "") {
  const clean = String(url || "").trim();
  if (!clean) {
    state.studio.refs[mode] = [];
    return;
  }
  state.studio.refs[mode] = [{ url: clean, preview: clean, name: name || (isRu() ? "Ссылка на фото" : "Image link") }];
}

async function uploadReference(file, mode) {
  if (!file) return;
  if (!/^image\/(jpeg|png|webp)$/i.test(file.type || "")) {
    flash(isRu() ? "Ошибка" : "Error", isRu() ? "Поддерживаются JPG, PNG и WebP." : "JPG, PNG, and WebP are supported.");
    return;
  }
  const localPreview = URL.createObjectURL(file);
  state.studio.refs[mode] = [{ url: "", preview: localPreview, name: file.name }];
  updateMediaPreview();
  try {
    const fd = new FormData();
    fd.append("file", file);
    const uploaded = await uploadApi({ method: "POST", body: fd });
    state.studio.refs[mode] = [{ url: uploaded.url, preview: localPreview, name: file.name }];
    syncReferenceInputs();
    updateMediaPreview();
    updateReviewSummary(mode);
    flash(isRu() ? "Фото добавлено" : "Image added", isRu() ? "Референс готов к использованию." : "Reference is ready to use.");
  } catch (error) {
    state.studio.refs[mode] = [];
    syncReferenceInputs();
    updateMediaPreview();
    updateReviewSummary(mode);
    flash(isRu() ? "Ошибка" : "Error", error.message);
  }
}

function applyPendingPrompt() {
  if (routeName() !== "studio" || (!state.pendingPrompt && !state.pendingReference && !state.pendingFeedRemix)) return;
  const pending = state.pendingPrompt;
  const mode = state.pendingReference?.mode || pending?.mode || "image";
  state.studio.step = state.studio.step || "brief";
  switchStudioMode(mode);
  if (pending?.promptId) state.activePromptId = pending.promptId;
  if (state.pendingReference?.url) {
    setReferenceFromUrl(mode, state.pendingReference.url, state.pendingReference.name);
    state.pendingReference = null;
    syncReferenceInputs();
    updateMediaPreview();
  }
  const textarea = pending ? document.querySelector(`.studio-form[data-form="${mode}"] textarea[name="${mode === "assistant" ? "message" : "prompt"}"]`) : null;
  if (textarea && pending) {
    textarea.value = pending.text;
    textarea.focus();
    state.pendingPrompt = null;
  }
  updateAllReviewSummaries();
  renderQueuePanels();
}

function bindStudio() {
  document.querySelectorAll(".mode-tab, .studio-mode-card").forEach((button) => {
    button.addEventListener("click", () => {
      switchStudioMode(button.dataset.mode);
    });
  });
  document.querySelectorAll("[data-studio-step]").forEach((button) => {
    button.addEventListener("click", () => {
      switchStudioStep(button.dataset.studioStep);
    });
  });
  document.querySelectorAll("[data-next-step], [data-prev-step]").forEach((button) => {
    button.addEventListener("click", () => {
      switchStudioStep(button.dataset.nextStep || button.dataset.prevStep);
    });
  });
  document.querySelectorAll("[data-model-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      updateSelectedModel(button.dataset.mode, button.dataset.model);
    });
  });
  document.querySelectorAll("[data-model-search]").forEach((input) => {
    input.addEventListener("input", () => filterModelCards(input.value));
  });
  document.querySelectorAll("[data-prompt-improve]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await improvePrompt(button.dataset.promptImprove, button);
      } catch (error) {
        flash(isRu() ? "Ошибка" : "Error", error.message);
      }
    });
  });
  document.querySelectorAll("[data-photo-prompt-file]").forEach((input) => {
    input.addEventListener("change", async () => {
      try {
        await promptFromPhoto(input.files?.[0], input.dataset.photoPromptFile, input);
      } catch (error) {
        flash(isRu() ? "Ошибка" : "Error", error.message);
      } finally {
        input.value = "";
      }
    });
  });
  document.querySelectorAll("[data-reference-file]").forEach((input) => {
    input.addEventListener("change", async () => {
      await uploadReference(input.files?.[0], input.dataset.referenceFile);
      input.value = "";
    });
  });
  document.querySelectorAll("[data-reference-input]").forEach((input) => {
    input.addEventListener("change", () => {
      setReferenceFromUrl(input.dataset.referenceInput, input.value);
      syncReferenceInputs();
      updateMediaPreview();
      refreshDynamicSettings();
      updateReviewSummary(input.dataset.referenceInput);
    });
  });
  bindReferenceRemove();
  document.querySelectorAll(".studio-form").forEach((form) => {
    form.addEventListener("input", () => updateReviewSummary(form.dataset.form));
    form.addEventListener("change", (event) => {
      const input = event.target;
      updateReviewSummary(form.dataset.form);
      if (!input.closest?.(".dynamic-settings")) return;
      if (form.dataset.form === "video" && input.name === "mode" && input.value === "image") {
        state.studio.step = "media";
        switchStudioStep("media");
      }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await withBusy(form, () => submitStudio(form));
    });
  });
  switchStudioMode(state.studio.mode || "image");
  applyPendingPrompt();
  renderQueuePanels();
  startQueuePolling();
}

function bindCards() {
  document.querySelectorAll(".feed-like").forEach((button) => {
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        try {
          await webApi(`/feed/${button.dataset.id}/like`, { method: "POST" });
          flash(isRu() ? "Готово" : "Done", isRu() ? "Лайк сохранён." : "Like saved.");
          await load({ route: routeName(), force: ["feed"] });
          await render({ skipLoad: true });
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  });
  document.querySelectorAll(".feed-share").forEach((button) => {
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        try {
          await webApi(`/feed/${button.dataset.id}/share`, { method: "POST" });
          flash(isRu() ? "Готово" : "Done", isRu() ? "Отметили, что работой поделились." : "Share saved.");
          await load({ route: routeName(), force: ["feed"] });
          await render({ skipLoad: true });
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  });
  document.querySelectorAll(".feed-reference").forEach((button) => {
    button.addEventListener("click", () => {
      const item = (Array.isArray(data.feed) ? data.feed : []).find((entry) => Number(entry.id) === Number(button.dataset.id));
      if (!item?.result_url) {
        flash(isRu() ? "Нет результата" : "No result", isRu() ? "У этой работы нет доступного медиа." : "This work has no media available.");
        return;
      }
      openStudioWithItem({ ...item, gen_id: item.id, mode: "image" }, "image");
    });
  });
  document.querySelectorAll(".feed-remix").forEach((button) => {
    button.addEventListener("click", () => {
      const item = (Array.isArray(data.feed) ? data.feed : []).find((entry) => Number(entry.id) === Number(button.dataset.id));
      state.pendingFeedRemix = { feedId: Number(button.dataset.id), result_url: item?.result_url || "", prompt: item?.prompt || "" };
      state.pendingPrompt = { mode: "image", text: item?.prompt || "" };
      if (item?.result_url) state.pendingReference = { mode: "image", url: item.result_url, name: isRu() ? "Работа из ленты" : "Gallery work" };
      state.studio.mode = "image";
      state.studio.step = "model";
      if (routeName() === "studio") render(); else location.hash = "#/studio";
    });
  });
  document.querySelectorAll(".prompt-like").forEach((button) => {
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        try {
          await webApi(`/prompts/${button.dataset.id}/like`, { method: "POST" });
          flash(isRu() ? "Готово" : "Done", isRu() ? "Идея понравилась." : "Idea liked.");
          await load({ route: routeName(), force: ["prompts"] });
          await render({ skipLoad: true });
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  });
  document.querySelectorAll(".prompt-use").forEach((button) => {
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        try {
          const result = await webApi(`/prompts/${button.dataset.id}/use`, { method: "POST" });
          state.pendingPrompt = { mode: "image", text: result.prompt?.prompt_text || "", promptId: result.prompt?.id || null };
          state.activePromptId = result.prompt?.id || null;
          state.studio.step = "brief";
          if (routeName() === "studio") {
            await render();
          } else {
            location.hash = "#/studio";
          }
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  });
  document.querySelectorAll(".prompt-copy").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = data.prompts?.items?.find((entry) => Number(entry.id) === Number(button.dataset.id));
      try {
        await navigator.clipboard.writeText(item?.prompt_text || item?.description || "");
        flash(isRu() ? "Скопировано" : "Copied", isRu() ? "Текст идеи в буфере обмена." : "Idea text copied.");
      } catch {
        flash(isRu() ? "Не скопировано" : "Not copied", isRu() ? "Браузер не дал доступ к буферу." : "Clipboard access was blocked.");
      }
    });
  });
  document.querySelectorAll(".generation-reuse").forEach((button) => {
    button.addEventListener("click", () => {
      const item = queueItemById(button.dataset.generationId);
      openStudioWithItem({ ...item, result_url: "" }, item?.gen_type || item?.mode || "image");
    });
  });
  document.querySelectorAll(".generation-next-image").forEach((button) => {
    button.addEventListener("click", () => openStudioWithItem(queueItemById(button.dataset.generationId), "image"));
  });
  document.querySelectorAll(".generation-next-video").forEach((button) => {
    button.addEventListener("click", () => openStudioWithItem(queueItemById(button.dataset.generationId), "video"));
  });
}

function bindQueueActions() {
  document.querySelectorAll("[data-refresh-queue]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        await pollQueue();
        flash(isRu() ? "Очередь обновлена" : "Queue refreshed", isRu() ? "Проверили активные задачи." : "Active jobs checked.");
      });
    });
  });
  document.querySelectorAll(".queue-reuse").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      const item = queueItemById(button.dataset.queueGen);
      openStudioWithItem({ ...item, result_url: "" }, item?.mode || "image");
    });
  });
  document.querySelectorAll(".queue-next-image").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => openStudioWithItem(queueItemById(button.dataset.queueGen), "image"));
  });
  document.querySelectorAll(".queue-next-video").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => openStudioWithItem(queueItemById(button.dataset.queueGen), "video"));
  });
  document.querySelectorAll("[data-clear-feed-remix]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => {
      state.pendingFeedRemix = null;
      renderQueuePanels();
      updateAllReviewSummaries();
    });
  });
}

function bindLibrary() {
  document.querySelectorAll(".prompt-filter").forEach((button) => {
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        try {
          data.prompts = await webApi(`/prompts?source=${button.dataset.source}&limit=9`);
          markLoaded("prompts");
          root.innerHTML = shell(`<div class="view">${prompts()}</div>`);
          bind();
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  });
  document.querySelectorAll(".feed-filter").forEach((button) => {
    button.addEventListener("click", async () => {
      await withBusy(button, async () => {
        try {
          data.feed = await webApi(`/feed?source=${button.dataset.source}&limit=9`);
          markLoaded("feed");
          root.innerHTML = shell(`<div class="view">${feed()}</div>`);
          bind();
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  });
  const toggle = document.getElementById("toggle-prompt-submit");
  const panel = document.getElementById("prompt-submit-panel");
  if (toggle && panel) {
    toggle.addEventListener("click", () => {
      panel.hidden = !panel.hidden;
    });
  }
  const form = document.getElementById("prompt-submit-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const fd = new FormData(form);
      await withBusy(form, async () => {
        try {
          await webApi("/prompts", {
            method: "POST",
            body: JSON.stringify({
              title: fd.get("title") || null,
              preview_url: fd.get("preview_url") || null,
              prompt_text: fd.get("prompt_text"),
              tags: String(fd.get("tags") || "").split(",").map((x) => x.trim()).filter(Boolean),
            }),
          });
          flash(isRu() ? "Отправлено" : "Submitted", isRu() ? "Идея отправлена на проверку." : "Idea sent for review.");
          form.reset();
        } catch (error) {
          flash(isRu() ? "Ошибка" : "Error", error.message);
        }
      });
    });
  }
}

function bindTelegramLogin() {
  window.onTelegramAuth = async (user) => {
    try {
      const result = await webApi("/auth/telegram-login", { method: "POST", body: JSON.stringify(user) });
      localStorage.setItem(tokenKey, result.token);
      resetPrivateData();
      await render();
    } catch (error) {
      alert(`Telegram auth failed: ${error.message}`);
    }
  };

  const slot = document.getElementById("telegram-login-slot");
  if (!slot || slot.dataset.loaded) return;
  const bot = slot.dataset.bot;
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://telegram.org/js/telegram-widget.js?22";
  script.setAttribute("data-telegram-login", bot);
  script.setAttribute("data-size", "large");
  script.setAttribute("data-radius", "0");
  script.setAttribute("data-request-access", "write");
  script.setAttribute("data-onauth", "onTelegramAuth(user)");
  slot.dataset.loaded = "1";
  slot.appendChild(script);
}

function bindProfile() {
  const logout = document.getElementById("logout");
  if (logout) {
    logout.addEventListener("click", async () => {
      await withBusy(logout, async () => {
        localStorage.removeItem(tokenKey);
        resetPrivateData();
        await render();
      });
    });
  }
  bindTelegramLogin();
}

function bindLanguage() {
  const button = document.querySelector("[data-lang-toggle]");
  if (!button) return;
  button.addEventListener("click", async () => {
    localStorage.setItem(langKey, lang() === "ru" ? "en" : "ru");
    await render();
  });
}

function bind() {
  bindLanguage();
  bindStudio();
  bindProfile();
  bindCards();
  bindQueueActions();
  bindLibrary();
  startQueuePolling();
}

async function render(options = {}) {
  const id = ++state.renderId;
  const name = routeName();
  const keys = loadKeysForRoute(name);
  const needsLoad = [...keys].some((key) => !hasLoaded(key));
  let controller = null;

  if (options.skipLoad && state.loadController) {
    state.loadController.abort();
    state.loadController = null;
  }

  if (!options.skipLoad) {
    if (state.loadController) state.loadController.abort();
    controller = new AbortController();
    state.loadController = controller;
    if (needsLoad) {
      root.innerHTML = shell(`<section class="view" role="status" aria-live="polite"><article class="paper pink"><p class="sticker">${isRu() ? "Загрузка" : "Loading"}</p><h2>${isRu() ? "APIX студия" : "APIX studio"}</h2></article></section>`);
    }
    await load({ route: name, signal: controller.signal });
    if (controller.signal.aborted || id !== state.renderId) return;
    if (state.loadController === controller) state.loadController = null;
  }

  if (id !== state.renderId) return;
  root.innerHTML = shell(`<div class="view">${views[name]()}</div>`);
  bind();
}

window.addEventListener("hashchange", render);
render();
