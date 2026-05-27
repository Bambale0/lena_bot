const root = document.getElementById("site-root");

const tokenKey = "apix_web_token";
const langKey = "apix_site_lang";
const queueKey = "apix_work_queue";
const reducedMotionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");

const state = {
  route: routeName(),
  token: localStorage.getItem(tokenKey) || "",
  lang: localStorage.getItem(langKey) === "en" ? "en" : "ru",
  me: null,
  authConfig: null,
  imageModels: [],
  videoModels: [],
  musicModels: [],
  pricePlans: [],
  prompts: [],
  feed: [],
  history: [],
  billing: null,
  adminPrompts: [],
  queue: readQueue(),
  modal: null,
  toast: null,
  loading: false,
  studioMode: "image",
  modelSelection: { image: "", video: "", music: "" },
  studioDraft: { image: "", video: "", music: "" },
  quickDraft: { image: "", video: "", music: "" },
  socket: null,
};

const ru = () => state.lang === "ru";
const txt = {
  ru: {
    login: "Войти через Telegram",
    start: "Начать",
    create: "Создать",
    generate: "Создать",
    openStudio: "Открыть Studio",
    account: "Аккаунт",
    logout: "Выйти",
  },
  en: {
    login: "Login with Telegram",
    start: "Start",
    create: "Create",
    generate: "Generate",
    openStudio: "Open Studio",
    account: "Account",
    logout: "Logout",
  },
};

const pick = (value) => (typeof value === "object" && value ? value[state.lang] || value.ru || value.en || "" : value);

const demoTemplates = [
  {
    title: { ru: "Запуск продукта", en: "Product launch" },
    prompt: {
      ru: "Серия кадров для нового продукта: тёмный фон, точные блики, единый стиль кампании, версии для соцсетей и сайта.",
      en: "Premium product image series: clean dark set, controlled reflections, consistent campaign style, versions for social and web.",
    },
  },
  {
    title: { ru: "Бьюти-редакция", en: "Beauty editorial" },
    prompt: {
      ru: "Редакционный бьюти-кадр: мягкий ключевой свет, фактура кожи, чистая ретушь, цвет бренда без перегруза эффектами.",
      en: "Editorial beauty visual: soft key light, detailed skin, refined retouching, controlled brand color, no excessive effects.",
    },
  },
  {
    title: { ru: "Видео-тизер", en: "Motion teaser" },
    prompt: {
      ru: "Короткий тизер из главного кадра: плавное приближение, лёгкая глубина, продукт остаётся в центре кадра.",
      en: "Short teaser from a hero still: smooth push-in, subtle parallax, product locked in frame, ready for Reels and stories.",
    },
  },
  {
    title: { ru: "Контент-пак", en: "Content pack" },
    prompt: {
      ru: "Набор материалов для кампании: обложка, баннер, вертикальный кадр, видео-заставка и версия для галереи.",
      en: "Campaign asset pack: cover, banner, vertical visual, video intro and public gallery version.",
    },
  },
];

const showcases = [
  {
    title: { ru: "Серия кампании", en: "Campaign series" },
    text: { ru: "единый стиль для 8-12 кадров", en: "consistent style for 8-12 visuals" },
    label: { ru: "продуктовые кадры", en: "product stills" },
    icon: "image",
    image: "images/apix-campaign-board.svg",
  },
  {
    title: { ru: "Фото в видео", en: "Image to video" },
    text: { ru: "движение по примеру без потери композиции", en: "motion from an example without losing composition" },
    label: { ru: "движение камеры", en: "camera motion" },
    icon: "video",
    image: "images/apix-reference-motion.svg",
  },
  {
    title: { ru: "Библиотека материалов", en: "Asset library" },
    text: { ru: "история, версии, публикации и ремикс", en: "history, versions, publishing and remix" },
    label: { ru: "контент-система", en: "content ops" },
    icon: "layers",
    image: "images/apix-library-system.svg",
  },
  {
    title: { ru: "Стоимость и очередь", en: "Cost and queue" },
    text: { ru: "кредиты, статусы и готовность результата", en: "credits, status and result readiness" },
    label: { ru: "контроль запуска", en: "production control" },
    icon: "tune",
    image: "images/apix-credits-control.svg",
  },
];

const audienceCards = [
  {
    title: { ru: "Маркетинг", en: "Marketing" },
    text: { ru: "Продуктовые кадры, баннеры, промо-серии и варианты под разные аудитории.", en: "Product shots, banners, promo series and quick variants for different audiences." },
    icon: "image",
  },
  {
    title: { ru: "Соцсети и авторы", en: "Social and creators" },
    text: { ru: "Вертикальные кадры, видео-тизеры, обложки и контент для регулярных публикаций.", en: "Vertical visuals, teaser videos, covers and content for a steady publishing calendar." },
    icon: "video",
  },
  {
    title: { ru: "Продакшн", en: "Production" },
    text: { ru: "Примеры, стиль, настройки, очередь, стоимость и результат в одном рабочем поле.", en: "Examples, style, settings, queue, cost and final result on one working surface." },
    icon: "tune",
  },
];

const platformRows = [
  { name: "Quick Create", title: { ru: "Старт с готового сценария", en: "Start from a clear scenario" }, text: { ru: "Изображение, видео, музыка или оживление примера без лишних настроек.", en: "Image, video, music or example-based motion without extra setup." } },
  { name: "PRO Studio", title: { ru: "Точный контроль запуска", en: "Precise output control" }, text: { ru: "Стиль, размер, качество, количество, длительность, примеры и очередь.", en: "Style, size, quality, count, duration, examples and queue." } },
  { name: "Content Manager", title: { ru: "Порядок после результата", en: "Order after generation" }, text: { ru: "История, галерея, шаблоны, ремикс и повторное использование материалов.", en: "History, gallery publishing, templates, remix and reusable assets." } },
];

const pricingPlans = [
  { name: "Start", price: "390 ₽", credits: 300, text: { ru: "Первые кадры, проверка идей и варианты для одной кампании.", en: "First visuals, idea tests and quick variants for a campaign." } },
  { name: "Studio", price: "1 490 ₽", credits: 1400, text: { ru: "Регулярная работа: серии изображений, видео, музыка и библиотека.", en: "Regular work: image series, video, music and an asset library." } },
  { name: "Business", price: "4 990 ₽", credits: 5200, text: { ru: "Большие кампании, контент-план, очередь задач и командные сценарии.", en: "Larger campaigns, content planning, production queue and team workflows." } },
];

const visualWallItems = [
  { title: { ru: "Описание", en: "Brief" }, text: { ru: "цель, площадка, аудитория", en: "goal, format, audience" }, status: { ru: "Готово", en: "Ready" } },
  { title: { ru: "Пример", en: "Example" }, text: { ru: "фото, бренд, прошлый материал", en: "photo, brand, previous asset" }, status: { ru: "Учтён", en: "Matched" } },
  { title: { ru: "Создание", en: "Generate" }, text: { ru: "изображение, видео, музыка и очередь", en: "image, video, music and queue" }, status: { ru: "В работе", en: "Live" } },
  { title: { ru: "Публикация", en: "Publish" }, text: { ru: "галерея, шаблон, история", en: "gallery, template, history" }, status: { ru: "Чисто", en: "Clean" } },
];

const workflowSteps = [
  { title: { ru: "Описание", en: "Brief" }, text: { ru: "Опишите продукт, площадку, аудиторию и нужный формат.", en: "Describe product, channel, audience and output format." } },
  { title: { ru: "Пример", en: "Reference" }, text: { ru: "Добавьте фото, прошлый материал или стиль бренда.", en: "Add a photo, previous asset or brand style to guide the output." } },
  { title: { ru: "Запуск", en: "Generate" }, text: { ru: "Выберите тип генерации и проверьте стоимость в кредитах.", en: "Run an image, video or music job with clear credit cost." } },
  { title: { ru: "Отбор", en: "Review" }, text: { ru: "Оцените результат, сделайте ремикс или продолжите в видео.", en: "Review the result, remix, create a variation or continue into motion." } },
  { title: { ru: "Публикация", en: "Publish" }, text: { ru: "Сохраните в библиотеку, галерею или шаблон.", en: "Save to library, publish to gallery or reuse as a template." } },
];

function routeName() {
  const value = location.hash.replace(/^#\/?/, "").split("/")[0];
  return value || "home";
}

function saveQueue() {
  localStorage.setItem(queueKey, JSON.stringify(state.queue.slice(0, 24)));
}

function readQueue() {
  try {
    const items = JSON.parse(localStorage.getItem(queueKey) || "[]");
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
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

function formatCredits(value) {
  return Number(value || 0).toLocaleString(ru() ? "ru-RU" : "en-US", { maximumFractionDigits: 2 });
}

function unwrap(json) {
  return Object.prototype.hasOwnProperty.call(json || {}, "data") ? json.data : json;
}

async function request(base, path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (state.token) headers["X-Web-Auth-Token"] = state.token;
  const response = await fetch(`${base}${path}`, { ...options, headers });
  const json = await response.json().catch(() => ({}));
  if (!response.ok || json.ok === false) throw new Error(json.error || json.detail || `HTTP ${response.status}`);
  return unwrap(json);
}

const web = (path, options) => request("/api/web", path, options);

let heroParticleCleanup = null;
let revealObserver = null;

function modelList(mode = state.studioMode) {
  if (mode === "video") return state.videoModels;
  if (mode === "music") return state.musicModels;
  return state.imageModels;
}

function optionTags(values, selected) {
  const items = Array.isArray(values) ? values.filter((value) => value !== null && value !== undefined && value !== "") : [];
  return items.map((value) => {
    const option = typeof value === "object" ? value : { value, label: value };
    return `<option value="${escapeHtml(option.value)}" ${String(option.value) === String(selected || "") ? "selected" : ""}>${escapeHtml(option.label || option.value)}</option>`;
  }).join("");
}

function selectedModelKey(mode = state.studioMode) {
  return state.modelSelection[mode] || modelList(mode)[0]?.key || "";
}

function currentModel(mode = state.studioMode, key = selectedModelKey(mode)) {
  const models = modelList(mode);
  return models.find((item) => item.key === key) || models[0] || null;
}

function mergeGeneration(generation) {
  if (!generation || !generation.id) return;
  const id = Number(generation.id);
  const existingQueue = state.queue.find((item) => Number(item.id || item.generation_id) === id);
  if (existingQueue) Object.assign(existingQueue, generation);
  else if (isActive(generation.status)) state.queue.unshift(generation);

  const historyIndex = state.history.findIndex((item) => Number(item.id) === id);
  if (historyIndex >= 0) state.history[historyIndex] = { ...state.history[historyIndex], ...generation };
  else if (!isActive(generation.status)) state.history.unshift(generation);
  state.history = state.history.slice(0, 48);
  state.queue = state.queue.filter((item) => isActive(item.status)).slice(0, 24);
  saveQueue();
}

function mergeActiveQueue(items) {
  (items || []).forEach(mergeGeneration);
  state.queue = state.queue.filter((item) => isActive(item.status)).slice(0, 24);
  saveQueue();
}

function connectRealtime() {
  if (!state.token || state.socket) return;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/v1/ws/generations?token=${encodeURIComponent(state.token)}`);
  state.socket = socket;
  socket.addEventListener("message", (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === "generation.snapshot") mergeActiveQueue(payload.items || []);
    if (payload.type === "generation.updated") mergeGeneration(payload);
    if (payload.type === "generation.snapshot" || payload.type === "generation.updated") {
      if (state.me) loadPrivate({ quiet: true }).then(render).catch(() => render());
      else render();
    }
  });
  socket.addEventListener("close", () => {
    if (state.socket === socket) state.socket = null;
    if (state.token && state.me) setTimeout(connectRealtime, 5000);
  });
}

function closeRealtime() {
  if (!state.socket) return;
  const socket = state.socket;
  state.socket = null;
  socket.close();
}

function icon(name) {
  const paths = {
    home: '<path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    spark: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 3v4"/><path d="M21 5h-4"/>',
    image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="10" r="2"/><path d="m21 16-5.2-5.2a2 2 0 0 0-2.8 0L5 19"/>',
    video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3z"/>',
    music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    upload: '<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M20 16v4H4v-4"/>',
    library: '<path d="M4 19.5V5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-1.5Z"/><path d="M8 7h6"/>',
    layers: '<path d="m12 2 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
    wallet: '<path d="M4 7h16v12H4z"/><path d="M16 12h4"/><path d="M4 7V5h13"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    tune: '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M2 14h4"/><path d="M10 8h4"/><path d="M18 16h4"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    arrow: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  };
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.spark}</svg>`;
}

async function boot() {
  state.loading = true;
  render();
  await Promise.allSettled([
    web("/auth/config").then((v) => { state.authConfig = v; }),
    web("/prompts?limit=12").then((v) => { state.prompts = v.items || v || []; }),
    web("/feed?limit=12").then((v) => { state.feed = Array.isArray(v) ? v : v.items || []; }),
  ]);
  if (state.token) await loadPrivate();
  state.loading = false;
  render();
  connectRealtime();
  pollQueue();
}

async function loadPrivate({ quiet = false } = {}) {
  await Promise.allSettled([
    web("/me").then((v) => { state.me = v; }).catch(() => { state.token = ""; localStorage.removeItem(tokenKey); }),
    web("/models/image").then((v) => { state.imageModels = Array.isArray(v) ? v : []; }),
    web("/models/video").then((v) => { state.videoModels = Array.isArray(v) ? v : []; }),
    web("/models/music").then((v) => { state.musicModels = Array.isArray(v) ? v : []; }),
    web("/history?limit=48").then((v) => { state.history = Array.isArray(v) ? v : []; }),
    web("/generations/active").then((v) => { mergeActiveQueue(Array.isArray(v) ? v : []); }).catch(() => {}),
    web("/billing/plans").then((v) => { state.pricePlans = Array.isArray(v) ? v : []; }).catch(() => {}),
    web("/billing/transactions?limit=20").then((v) => { state.billing = v; }).catch(() => {}),
    web("/admin/prompts?status=pending").then((v) => { state.adminPrompts = v.items || []; }).catch(() => {}),
  ]);
  ["image", "video", "music"].forEach((mode) => {
    if (!currentModel(mode, state.modelSelection[mode])) {
      state.modelSelection[mode] = modelList(mode)[0]?.key || "";
    }
  });
  if (!state.token) closeRealtime();
  if (!quiet) connectRealtime();
}

window.onTelegramAuth = async (user) => {
  try {
    const result = await web("/auth/telegram-login", { method: "POST", body: JSON.stringify(user) });
    state.token = result.token;
    localStorage.setItem(tokenKey, result.token);
    state.me = result.user;
    await loadPrivate();
    state.route = "quick";
    location.hash = "#/quick";
    connectRealtime();
    toast(ru() ? "Вход выполнен" : "Signed in", ru() ? "Telegram подключен к APIX Studio." : "Telegram is connected to APIX Studio.");
  } catch (error) {
    toast(ru() ? "Ошибка входа" : "Login failed", error.message);
  }
};

function telegramSlot(instance = "main") {
  const bot = state.authConfig?.bot_username;
  if (!bot) return `<div class="auth-fallback">${ru() ? "Telegram Login не настроен. Укажите BOT_USERNAME на сервере." : "Telegram Login is not configured. Set BOT_USERNAME on the server."}</div>`;
  const id = `telegram-login-slot-${instance}`.replace(/[^a-z0-9_-]/gi, "");
  setTimeout(() => {
    const slot = document.getElementById(id);
    if (!slot || slot.dataset.loaded) return;
    slot.dataset.loaded = "1";
    const script = document.createElement("script");
    script.async = true;
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", bot);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "12");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    slot.appendChild(script);
  }, 0);
  return `<div id="${id}" class="telegram-slot"></div>`;
}

function nav() {
  const items = [
    ["home", ru() ? "Главная" : "Home", "home"],
    ["quick", "Quick", "spark"],
    ["studio", "Studio", "tune"],
    ["library", ru() ? "Библиотека" : "Library", "library"],
    ["templates", ru() ? "Шаблоны" : "Templates", "layers"],
    ["gallery", ru() ? "Галерея" : "Gallery", "image"],
    ["billing", ru() ? "Баланс" : "Billing", "wallet"],
    ["profile", ru() ? "Профиль" : "Profile", "user"],
    ["content", ru() ? "Контент" : "Content", "check"],
  ];
  return items.map(([route, label, ico]) => `<a class="${state.route === route ? "active" : ""}" href="#/${route}">${icon(ico)}<span>${label}</span></a>`).join("");
}

function shell(content) {
  const authed = Boolean(state.me);
  return `
    <div class="${authed ? "app-layout" : "public-layout"}">
      ${authed ? "" : publicChrome()}
      ${authed ? `<aside class="sidebar"><a class="brand side-brand" href="#/quick"><img class="logo-img" src="images/apix-premium-mark.svg" alt="APIX"><strong>APIX Studio<small>${formatCredits(state.me?.credits)} credits</small></strong></a><nav class="side-nav">${nav()}</nav><button class="btn ghost logout" type="button">${txt[state.lang].logout}</button></aside>` : publicTopbar()}
      <div class="workspace">
        ${authed ? appTopbar() : ""}
        <main>${content}</main>
      </div>
      ${modal()}
      ${state.toast ? `<div class="toast"><b>${escapeHtml(state.toast.title)}</b><span>${escapeHtml(state.toast.body)}</span></div>` : ""}
    </div>
  `;
}

function publicNavItems() {
  return [
    ["structure", ru() ? "Возможности" : "Features"],
    ["visuals", ru() ? "Визуал" : "Visuals"],
    ["workflow", ru() ? "Процесс" : "Workflow"],
    ["studio-preview", "Studio"],
    ["pricing", ru() ? "Тарифы" : "Pricing"],
  ];
}

function publicChrome() {
  return `<div class="scroll-progress" aria-hidden="true"><span></span></div>`;
}

function publicTopbar() {
  return `<header class="topbar"><a class="brand" href="#/home"><img class="logo-img" src="images/apix-premium-mark.svg" alt="APIX"><strong>APIX Studio<small>${ru() ? "Генерация изображений, видео и музыки" : "Image, video and music generation"}</small></strong></a><nav aria-label="${ru() ? "Главная навигация" : "Primary navigation"}">${publicNavItems().map(([id, label]) => `<a href="#/home" data-scroll="${id}">${label}</a>`).join("")}<a href="#/gallery">${ru() ? "Галерея" : "Gallery"}</a></nav><div class="top-actions"><button class="lang" type="button">${state.lang.toUpperCase()}</button>${authMenu()}<a class="btn primary" href="#/quick">${txt[state.lang].start}${icon("arrow")}</a></div></header>`;
}

function authMenu() {
  return `<div class="auth-menu" data-auth-menu><button class="auth-trigger" type="button" aria-haspopup="menu" aria-expanded="false" aria-controls="auth-menu-panel">${icon("user")}<span>${txt[state.lang].account}</span>${icon("chevron")}</button><div class="auth-panel" id="auth-menu-panel" role="menu" aria-label="${ru() ? "Меню авторизации" : "Authorization menu"}" hidden><div class="auth-panel-head"><b>${ru() ? "Вход в APIX" : "Sign in to APIX"}</b><span>${ru() ? "Telegram откроет студию, баланс и историю работ." : "Telegram opens studio, billing and generation history."}</span></div><button class="auth-action open-modal" data-modal="login" type="button" role="menuitem">${icon("lock")}<span>${txt[state.lang].login}</span></button><a href="#/quick" role="menuitem">${icon("spark")}<span>${ru() ? "Создать" : "Quick create"}</span></a><a href="#/billing" role="menuitem">${icon("wallet")}<span>${ru() ? "Тарифы и баланс" : "Pricing and billing"}</span></a><a href="#/templates" role="menuitem">${icon("layers")}<span>${ru() ? "Шаблоны" : "Templates"}</span></a></div></div>`;
}

function appTopbar() {
  return `<header class="appbar"><div class="search">${icon("spark")}<input placeholder="${ru() ? "Найти работу, шаблон или модель" : "Find work, template or model"}"></div><button class="btn ghost open-modal" data-modal="project">${ru() ? "Новый проект" : "New project"}</button><button class="lang" type="button">${state.lang.toUpperCase()}</button></header>`;
}

function home() {
  return `
    <section class="hero" id="top">
      <div class="hero-art" aria-hidden="true"></div>
      <div class="hero-noise" aria-hidden="true"></div>
      <div class="hero-copy">
        <p class="eyebrow">${icon("spark")}${ru() ? "Студия изображений, видео и музыки" : "AI image, video and music studio"}</p>
        <h1>APIX Studio</h1>
        <p class="lead">${ru() ? "Премиальная веб-студия для визуального контента: создавайте рекламные кадры, оживляйте примеры, запускайте видео и храните всё в одной библиотеке." : "A premium web studio for creative production: generate campaign visuals, animate examples, create video and keep every asset in one library."}</p>
        <div class="actions"><a class="btn primary" href="#/quick">${txt[state.lang].start}${icon("arrow")}</a><button class="btn ghost open-modal" data-modal="login" type="button">${txt[state.lang].login}</button></div>
        <div class="hero-meta"><span>${icon("check")}${ru() ? "Быстрое создание без лишних полей" : "Focused Quick Create"}</span><span>${icon("check")}${ru() ? "Studio с контролем очереди" : "Studio with queue control"}</span><span>${icon("check")}${ru() ? "Вход и баланс через Telegram" : "Telegram login and billing"}</span></div>
      </div>
      <aside class="hero-stage" aria-label="APIX animated studio scene">
        <canvas class="hero-particles" data-hero-particles aria-hidden="true"></canvas>
        <div class="hero-showcase tilt-card">
          <img src="images/apix-hero-studio-scene.svg" alt="APIX creative studio workspace">
          <div class="hero-hotspots" aria-label="${ru() ? "Сценарии студии" : "Studio scenarios"}">
            <button type="button" aria-label="${ru() ? "Создать изображение" : "Create image"}">${icon("image")}</button>
            <button type="button" aria-label="${ru() ? "Оживить пример" : "Animate example"}">${icon("video")}</button>
            <button type="button" aria-label="${ru() ? "Сохранить в библиотеку" : "Save to library"}">${icon("layers")}</button>
          </div>
          <div class="render-meter" aria-hidden="true"><span></span></div>
        </div>
      </aside>
    </section>
    ${trustBar()}
    ${showcaseSection()}
    ${visualWallSection()}
    ${audienceSection()}
    ${quickSection()}
    ${workflowSection()}
    ${studioSection()}
    ${contentSection()}
    ${pricingSection()}
    ${finalCta()}
    ${footer()}
  `;
}

function studioMini() {
  const modes = ru()
    ? ["Серия кадров", "Фото в видео", "Видео-тизер", "Отбор работ"]
    : ["Image series", "Photo motion", "Video teaser", "Content review"];
  const notes = ru()
    ? ["единый стиль", "по примеру", "готово к экспорту", "для публикации"]
    : ["consistent style", "from example", "ready to share", "publish-ready"];
  return `<div class="card-top"><span></span><span></span><span></span></div><p class="kicker">${ru() ? "ЖИВАЯ СТУДИЯ" : "LIVE WORKSPACE"}</p><h2>${ru() ? "Рабочий центр контента" : "Creative command deck"}</h2><p>${ru() ? "Один экран собирает идею, примеры, стоимость, очередь, результат и следующий шаг." : "One surface keeps the idea, examples, cost, queue, result and next action together."}</p><div class="mode-grid">${modes.map((x, i) => `<article><b>${icon(i === 3 ? "layers" : i > 0 ? "video" : "image")}${x}</b><small>${notes[i]}</small></article>`).join("")}</div><div class="progress-card"><span>${ru() ? "Очередь" : "Queue"}</span><b>${state.queue.filter((x) => isActive(x.status)).length || 3} ${ru() ? "активных задач" : "active jobs"}</b><i></i></div>`;
}

function trustBar() {
  const items = [
    [ru() ? "Вход" : "Login", ru() ? "Telegram без пароля" : "Telegram, no password"],
    [ru() ? "Создание" : "Creation", ru() ? "изображения, видео, музыка" : "image, video, music"],
    [ru() ? "Контроль" : "Control", ru() ? "модели, кредиты, очередь" : "models, credits, queue"],
    [ru() ? "Публикация" : "Publishing", ru() ? "история, галерея, ремикс" : "history, gallery, remix"],
  ];
  return `<section class="trust-bar" aria-label="${ru() ? "Структура APIX" : "APIX structure"}">${items.map(([label, text]) => `<article><span>${label}</span><b>${text}</b></article>`).join("")}</section>`;
}

function quickSection() {
  const cards = [
    [{ ru: "Создать изображение", en: "Create an image" }, { ru: "Рекламный кадр, обложка, продуктовый снимок или серия в одном стиле.", en: "Ad visual, cover, product shot or a consistent image series." }, "image"],
    [{ ru: "Оживить пример", en: "Animate an example" }, { ru: "Фото становится видео с контролем длительности и формата.", en: "A photo becomes a video teaser with duration and format control." }, "video"],
    [{ ru: "Собрать видео", en: "Build a video" }, { ru: "Идея, стиль, очередь и стоимость видны до запуска.", en: "Idea, style, queue and clear cost before launch." }, "video"],
    [{ ru: "Создать музыку", en: "Create music" }, { ru: "Музыкальная идея для ролика, заставки или бренд-контента.", en: "A music idea for a reel, intro or branded content piece." }, "music"],
  ];
  return `<section class="section" id="quick"><div class="section-head"><p class="eyebrow">${icon("spark")}Quick Create</p><h2>${ru() ? "Создание начинается с задачи" : "Creation starts with a task"}</h2><p>${ru() ? "Выберите сценарий: изображение, оживление примера, видео или музыка. Точные настройки ждут в PRO Studio." : "Choose a scenario: image, example motion, video or music. Fine controls stay available in PRO Studio."}</p></div><div class="quick-grid">${cards.map(([a, b, c], i) => `<article class="quick-card quick-card-${i + 1} tilt-card"><span>${icon(c)}</span><h3>${pick(a)}</h3><p>${pick(b)}</p><a href="#/quick">${ru() ? "Открыть" : "Open"}</a></article>`).join("")}</div></section>`;
}

function visualWallSection() {
  return `<section class="section visual-wall-section" id="visuals"><div class="section-head centered"><p class="eyebrow">${icon("image")}${ru() ? "Визуальный процесс" : "Visual workflow"}</p><h2>${ru() ? "От идеи до публикации" : "From idea to publish"}</h2><p>${ru() ? "APIX связывает описание, примеры, настройки, очередь и библиотеку в одну рабочую доску. Видно, что создаётся, сколько стоит и где лежит результат." : "APIX connects ideas, examples, settings, queue and library into one production board. You see what is being created, what it costs and where each result lands."}</p></div><div class="visual-wall"><article class="visual-main tilt-card"><img src="images/apix-production-flow.svg" alt="APIX production workflow"><div class="visual-hotspots" aria-label="${ru() ? "Точки процесса" : "Workflow points"}"><button type="button" aria-label="${ru() ? "Описание" : "Brief"}">${icon("spark")}</button><button type="button" aria-label="${ru() ? "Пример" : "Example"}">${icon("image")}</button><button type="button" aria-label="${ru() ? "Публикация" : "Publish"}">${icon("layers")}</button></div></article><div class="visual-side">${visualWallItems.map((item, index) => `<article class="visual-step tilt-card"><span>0${index + 1}</span><div><h3>${pick(item.title)}</h3><p>${pick(item.text)}</p></div><b>${pick(item.status)}</b></article>`).join("")}</div><article class="visual-preview tilt-card"><img src="images/apix-motion-preview.svg" alt="Motion preview"><div><span>${ru() ? "Движение кадра" : "Motion preview"}</span><h3>${ru() ? "Пример остаётся на виду" : "The example stays visible"}</h3><p>${ru() ? "Композиция, формат и следующий шаг понятны до запуска." : "Composition, format and the next action are clear before creation starts."}</p></div></article></div></section>`;
}

function audienceSection() {
  return `<section class="section structure-section" id="structure"><div class="section-head"><p class="eyebrow">${icon("layers")}${ru() ? "Для кого" : "Who it is for"}</p><h2>${ru() ? "Полный цикл контента в APIX" : "The full content cycle in APIX"}</h2><p>${ru() ? "До входа понятно, что умеет продукт. После авторизации доступны студия, история, баланс, очередь и публикация." : "Before login, the product is clear. After Telegram sign-in, studio, history, balance, queue and publishing are ready."}</p></div><div class="audience-grid">${audienceCards.map((item) => `<article><span>${icon(item.icon)}</span><h3>${pick(item.title)}</h3><p>${pick(item.text)}</p></article>`).join("")}</div>${platformMap()}</section>`;
}

function platformMap() {
  return `<div class="platform-map">${platformRows.map((item, index) => `<article><span>0${index + 1}</span><div><b>${item.name}</b><h3>${pick(item.title)}</h3><p>${pick(item.text)}</p></div></article>`).join("")}</div>`;
}

function studioSection() {
  return `<section class="section" id="studio-preview"><div class="section-head"><p class="eyebrow">${icon("tune")}PRO Studio</p><h2>${ru() ? "Контроль без перегруза" : "Control without clutter"}</h2><p>${ru() ? "Превью в центре, инспектор справа, проекты слева, очередь снизу. Видно тип задачи, модель, стоимость и следующий шаг." : "Preview in the center, inspector on the right, projects on the left, queue at the bottom. Type, model, cost and next action stay visible."}</p></div>${studioShell(false)}</section>`;
}

function contentSection() {
  return `<section class="section"><div class="section-head"><p class="eyebrow">${icon("check")}Content Manager</p><h2>${ru() ? "Шаблоны, отбор и публикации" : "Templates, review and publishing"}</h2><p>${ru() ? "Статусы, превью, готовность шаблонов и действия собраны в одном списке." : "Statuses, previews, template readiness and actions stay in one review list."}</p></div>${contentBoard()}</section>`;
}

function showcaseSection() {
  return `<section class="showcase-strip" aria-label="APIX production scenarios">${showcases.map((item, index) => `<article class="showcase-card showcase-${index + 1} tilt-card"><div class="showcase-art"><img src="${item.image}" alt="${escapeHtml(pick(item.title))}"><span>${icon(item.icon)}</span></div><p>${pick(item.label)}</p><h3>${pick(item.title)}</h3><small>${pick(item.text)}</small></article>`).join("")}</section>`;
}

function workflowSection() {
  return `<section class="section workflow-section" id="workflow"><div class="section-head"><p class="eyebrow">${icon("layers")}${ru() ? "Процесс" : "Workflow"}</p><h2>${ru() ? "Понятный путь от идеи до материала" : "A clear path from idea to asset"}</h2><p>${ru() ? "Пользователь видит идею, пример, запуск, отбор и публикацию. Создание становится рабочим процессом, а не случайной кнопкой." : "Idea, example, creation, review and publishing stay visible. Creation becomes a workflow, not a random button."}</p></div><div class="workflow-timeline">${workflowSteps.map((item, index) => `<article><span>0${index + 1}</span><h3>${pick(item.title)}</h3><p>${pick(item.text)}</p></article>`).join("")}</div></section>`;
}

function pricingSection() {
  return `<section class="section pricing" id="pricing"><div class="section-head"><p class="eyebrow">${icon("wallet")}${ru() ? "Тарифы" : "Pricing"}</p><h2>${ru() ? "Стоимость видна до запуска" : "Credits are clear before generation starts"}</h2><p>${ru() ? "Кредиты списываются за реальные задачи. В кабинете доступны баланс, история операций и пополнение." : "Credits are tied to real jobs. The workspace keeps balance, transaction history and top-up."}</p></div><div class="price-grid">${pricingPlans.map((plan, i) => `<article class="${i === 1 ? "is-featured" : ""}"><span>${plan.name}</span><b>${plan.price}</b><p>${plan.credits.toLocaleString(ru() ? "ru-RU" : "en-US")} credits</p><small>${pick(plan.text)}</small><a class="btn ${i === 1 ? "primary" : "ghost"}" href="#/billing">${ru() ? "Выбрать" : "Choose"}</a></article>`).join("")}</div></section>`;
}

function finalCta() {
  return `<section class="final-cta"><div><p class="eyebrow">${icon("spark")}APIX Studio</p><h2>${ru() ? "Выберите сценарий и создавайте" : "Pick a scenario and create"}</h2><p>${ru() ? "Войдите через Telegram, откройте Quick Create или PRO Studio и держите результаты, кредиты и публикации в одном месте." : "Sign in with Telegram, open Quick Create or PRO Studio, and keep results, credits and publishing in one place."}</p></div><div class="actions"><a class="btn primary" href="#/quick">${txt[state.lang].start}${icon("arrow")}</a><button class="btn ghost open-modal" data-modal="login" type="button">${txt[state.lang].login}</button></div></section>`;
}

function footer() {
  return `<footer class="footer"><b>APIX Studio</b><span>${ru() ? "Генерация изображений, видео и музыки с входом через Telegram." : "Image, video and music generation with Telegram login."}</span><a href="#/billing">${ru() ? "Тарифы" : "Pricing"}</a></footer>`;
}

function requireAuth(inner) {
  if (state.me) return inner;
  return `<section class="section auth-screen"><div class="auth-card"><img class="hero-logo" src="images/apix-premium-mark.svg" alt="APIX"><h1>${ru() ? "Войдите через Telegram" : "Login with Telegram"}</h1><p class="lead">${ru() ? "Откроются Quick Create, PRO Studio, библиотека, баланс и публикации." : "Unlock Quick Create, PRO Studio, library, billing and publishing."}</p>${telegramSlot("auth")}</div></section>`;
}

function quick() {
  return requireAuth(`<section class="section"><div class="section-head"><p class="eyebrow">${icon("spark")}Quick Create</p><h2>${ru() ? "Что создаём?" : "What are we creating?"}</h2><p>${ru() ? "Выберите тип задачи, модель, формат и пример. Стоимость видна до запуска." : "Choose task type, model, format and example. Cost is visible before launch."}</p></div><div class="workflow-grid studio-quick-grid">${quickForm("image")}${quickForm("video")}${quickForm("music")}</div>${queueDock()}</section>`);
}

function quickForm(mode) {
  const models = modelList(mode);
  const model = currentModel(mode) || models[0] || {};
  const title = mode === "image"
    ? (ru() ? "Создать изображение" : "Create image")
    : mode === "video"
      ? (ru() ? "Создать видео" : "Create video")
      : (ru() ? "Создать музыку" : "Create music");
  return `<form class="flow-card gen-form studio-form" data-mode="${mode}"><p class="eyebrow">${icon(mode)}${mode}</p><h3>${title}</h3><label><span>${ru() ? "Описание" : "Idea"}</span><textarea name="prompt" required placeholder="${ru() ? "Сцена, продукт, стиль, свет и нужный результат" : "Scene, product, style, light and desired result"}">${escapeHtml(state.quickDraft[mode] || "")}</textarea></label>${modelPicker(mode, model.key)}${generationControls(mode, model)}<button class="btn primary" type="submit">${txt[state.lang].generate}</button></form>`;
}

function studioView() {
  return requireAuth(`<section class="section studio-page"><div class="section-head"><p class="eyebrow">${icon("tune")}PRO Studio</p><h2>${ru() ? "Полный процесс создания" : "Complete creation workflow"}</h2><p>${ru() ? "Примеры, модели, настройки, очередь, результаты и повторное использование материалов." : "Examples, models, settings, queue, results and asset reuse."}</p></div>${studioShell(true)}</section>`);
}

function modelPicker(mode, selected = "") {
  const models = modelList(mode);
  return `<label><span>${ru() ? "Модель" : "Model"}</span><select name="model" class="model-select" data-mode="${mode}">${models.map((m) => `<option value="${escapeHtml(m.key)}" ${m.key === selected ? "selected" : ""}>${escapeHtml(m.display_name || m.key)} · ${Number(m.credits || 0)} cr</option>`).join("")}</select></label>`;
}

function generationControls(mode, model = {}) {
  if (mode === "music") {
    return `<label class="toggle-row"><input type="checkbox" name="instrumental" value="1"><span>${ru() ? "Инструментальный трек" : "Instrumental track"}</span></label>`;
  }
  const ratio = optionTags(model.aspect_ratios || [], model.aspect_ratios?.[0]);
  const reference = `<label><span>${ru() ? "Ссылка на пример" : "Example URL"}</span><input name="reference" placeholder="https://..."></label><label class="file-drop"><span>${icon("upload")}${ru() ? "Загрузить пример" : "Upload example"}</span><input name="reference_file" type="file" accept="image/png,image/jpeg,image/webp"></label>`;
  if (mode === "image") {
    const qualities = model.quality_options?.length ? optionTags(model.quality_options, model.quality_options[0]?.value) : `<option value="basic">basic</option>`;
    const counts = optionTags(model.counts?.length ? model.counts : [1], model.counts?.[0] || 1);
    return `<div class="composer-grid"><label><span>${ru() ? "Формат" : "Aspect"}</span><select name="aspect_ratio">${ratio || `<option value="">auto</option>`}</select></label><label><span>${ru() ? "Качество" : "Quality"}</span><select name="quality">${qualities}</select></label><label><span>${ru() ? "Количество" : "Count"}</span><select name="count">${counts}</select></label></div>${reference}`;
  }
  const modes = optionTags(model.modes?.length ? model.modes : ["text"], model.modes?.[0] || "text");
  const durations = optionTags(model.durations?.length ? model.durations : [5], model.durations?.[0] || 5);
  const resolutions = optionTags(model.resolutions?.length ? model.resolutions : [""], model.resolutions?.[0] || "");
  return `<div class="composer-grid"><label><span>${ru() ? "Режим" : "Mode"}</span><select name="mode">${modes}</select></label><label><span>${ru() ? "Длительность" : "Duration"}</span><select name="duration">${durations}</select></label><label><span>${ru() ? "Формат" : "Aspect"}</span><select name="aspect_ratio">${ratio || `<option value="">auto</option>`}</select></label><label><span>${ru() ? "Разрешение" : "Resolution"}</span><select name="resolution">${resolutions || `<option value="">auto</option>`}</select></label></div>${reference}<label><span>${ru() ? "Ссылка на видео" : "Video URL"}</span><input name="video_url" placeholder="https://..."></label>`;
}

function studioShell(active) {
  const models = modelList();
  const current = currentModel();
  const preview = state.queue[0] || state.history[0] || {};
  return `<div class="studio-shell ${active ? "is-live" : ""}"><aside class="rail"><b>${ru() ? "Проекты" : "Projects"}</b><span class="active">${ru() ? "Кампания 04" : "Campaign 04"}</span><span>${ru() ? "Продуктовые кадры" : "Product shots"}</span><span>${ru() ? "Видео-тесты" : "Video tests"}</span><hr><b>${ru() ? "Очередь" : "Queue"}</b>${state.queue.slice(0, 4).map((item) => `<span>${escapeHtml(item.model || item.gen_type || "job")}<small>${escapeHtml(item.status || "")}</small></span>`).join("") || `<span>${ru() ? "Пусто" : "Empty"}</span>`}</aside><main class="canvas"><div class="canvas-preview result-preview">${renderMedia(preview, "images/apix-campaign-board.svg")}<div class="floating-result">${escapeHtml(preview.status || "ready")} · ${escapeHtml(preview.gen_type || state.studioMode)}</div></div>${active ? studioComposer(models) : `<div class="queue"><span>${icon("image")} Image</span><span>${icon("video")} Video</span><span>${icon("music")} Music</span></div>`}</main><aside class="inspector"><b>${icon("tune")}${ru() ? "Инспектор" : "Inspector"}</b><button class="seg ${state.studioMode === "image" ? "active" : ""}" data-mode="image" type="button">Image</button><button class="seg ${state.studioMode === "video" ? "active" : ""}" data-mode="video" type="button">Video</button><button class="seg ${state.studioMode === "music" ? "active" : ""}" data-mode="music" type="button">Music</button><label>${ru() ? "Модель" : "Model"}<span>${escapeHtml(current?.display_name || current?.key || "Default")}</span></label><label>${ru() ? "Стоимость" : "Cost"}<span>${Number(current?.credits || 0)} credits</span></label><label>${ru() ? "Доступно моделей" : "Models"}<span>${models.length}</span></label><button class="btn ghost open-modal" data-modal="settings" type="button">${ru() ? "Настройки" : "Settings"}</button></aside></div>`;
}

function studioComposer(models) {
  const current = currentModel(state.studioMode) || models[0] || {};
  return `<form class="studio-composer gen-form studio-form" data-mode="${state.studioMode}"><textarea name="prompt" required placeholder="${ru() ? "Сцена, стиль, свет, движение и нужный результат..." : "Scene, style, lighting, motion and desired output..."}">${escapeHtml(state.studioDraft[state.studioMode] || "")}</textarea>${modelPicker(state.studioMode, current.key)}${generationControls(state.studioMode, current)}<div class="studio-actions"><button class="btn primary" type="submit">${txt[state.lang].generate}</button><button class="btn ghost improve-prompt" type="button" data-kind="${state.studioMode}">${ru() ? "Уточнить промпт" : "Improve prompt"}</button></div></form>${queueDock()}`;
}

function queueDock() {
  const items = state.queue.slice(0, 6);
  return `<div class="queue-dock"><div><b>${ru() ? "Очередь" : "Queue"}</b><span>${items.length || 0}</span></div><div class="queue-list">${items.length ? items.map((item) => `<article><span class="${isActive(item.status) ? "pulse" : ""}"></span><b>#${item.id || item.gen_id}</b><p>${escapeHtml(item.prompt || item.mode || "generation")}</p><small>${escapeHtml(item.status || "pending")}</small></article>`).join("") : `<p>${ru() ? "Пока нет активных задач." : "No active jobs yet."}</p>`}</div></div>`;
}

function isActive(status) {
  return ["pending", "processing", "queued", "running"].includes(String(status || "").toLowerCase());
}

function library() {
  return requireAuth(`<section class="section"><div class="section-head"><p class="eyebrow">${icon("library")}${ru() ? "Библиотека" : "Library"}</p><h2>${ru() ? "Ваши материалы" : "Your assets"}</h2><p>${ru() ? "История генераций, результаты, ремиксы и публикация в галерею." : "Generation history, results, remixes and gallery publishing."}</p></div><div class="asset-grid">${state.history.length ? state.history.map(assetCard).join("") : empty(ru() ? "Создайте первый результат в Quick Create или PRO Studio." : "Create your first result in Quick Create or PRO Studio.")}</div></section>`);
}

function renderMedia(item = {}, fallback = "") {
  const url = item.result_url || item.result_urls?.[0] || fallback;
  if (!url) return `<div class="thumb"></div>`;
  const type = String(item.gen_type || item.type || "");
  if (type === "video") return `<video src="${escapeHtml(url)}" muted loop playsinline controls></video>`;
  if (type === "music") return `<div class="audio-result">${icon("music")}<audio src="${escapeHtml(url)}" controls></audio></div>`;
  return `<img src="${escapeHtml(url)}" alt="">`;
}

function assetCard(item) {
  const ready = String(item.status || "done") === "done";
  const isMine = state.history.some((asset) => Number(asset.id) === Number(item.id));
  return `<article class="asset-card">${renderMedia(item)}<h3>${escapeHtml(item.model || item.gen_type || item.type || "AI result")}</h3><p>${escapeHtml(item.prompt || "")}</p><div class="asset-meta"><span>${escapeHtml(item.status || item.type || "ready")}</span><span>${Number(item.credits_spent || 0)} cr</span></div><div class="row-actions"><button class="open-detail" data-id="${escapeHtml(item.id)}" type="button">${ru() ? "Детали" : "Details"}</button><button class="remix" data-prompt="${escapeHtml(item.prompt || "")}" data-id="${escapeHtml(item.id || "")}" type="button">Remix</button>${ready && isMine ? `<button class="asset-action" data-action="publish" data-id="${escapeHtml(item.id)}" type="button">${ru() ? "Опубликовать" : "Publish"}</button>` : ""}</div></article>`;
}

function templates() {
  const items = state.prompts.length ? state.prompts : demoTemplates.map((item, id) => ({ id, title: pick(item.title), prompt_text: pick(item.prompt), tags: ["premium", "studio"] }));
  return `<section class="section"><div class="section-head"><p class="eyebrow">${icon("layers")}${ru() ? "Шаблоны" : "Templates"}</p><h2>${ru() ? "Готовые основы для запуска" : "Ready ideas to launch"}</h2><p>${ru() ? "Готовые идеи для изображений, видео и серий." : "Ready ideas for images, video and series."}</p></div><div class="asset-grid">${items.map((p) => `<article class="asset-card template-card"><div class="thumb"></div><h3>${escapeHtml(p.title || "Template")}</h3><p>${escapeHtml(p.prompt_text || "")}</p><div class="row-actions"><button class="use-template" data-prompt="${escapeHtml(p.prompt_text || "")}" type="button">${ru() ? "Использовать" : "Use"}</button><button type="button">${ru() ? "Сохранить" : "Save"}</button></div></article>`).join("")}</div></section>`;
}

function gallery() {
  return `<section class="section"><div class="section-head"><p class="eyebrow">${icon("image")}${ru() ? "Галерея" : "Gallery"}</p><h2>${ru() ? "Публичные работы" : "Public works"}</h2><p>${ru() ? "Работы APIX, которые можно открыть, изучить и отправить в ремикс." : "APIX works you can open, study and remix."}</p></div><div class="asset-grid">${state.feed.length ? state.feed.map(assetCard).join("") : demoTemplates.map((item) => assetCard({ model: pick(item.title), prompt: pick(item.prompt) })).join("")}</div></section>`;
}

function billing() {
  const balance = state.me?.credits ?? 0;
  const tx = state.billing?.transactions || [];
  const plans = state.pricePlans.length ? state.pricePlans : pricingPlans.map((plan, index) => ({ key: `demo_${index}`, label: plan.name, price_rub_display: plan.price, credits: plan.credits }));
  return `<section class="section"><div class="section-head"><p class="eyebrow">${icon("wallet")}${ru() ? "Баланс" : "Billing"}</p><h2>${formatCredits(balance)} credits</h2><p>${ru() ? "Здесь баланс, пополнение и история операций." : "Balance, top-up and transaction history live here."}</p></div><div class="price-grid">${plans.map((plan, i) => `<article><span>${escapeHtml(plan.label || plan.title || plan.key)}</span><b>${escapeHtml(plan.price_rub_display || `${plan.price_rub || ""} ₽`)}</b><p>${Number(plan.credits || 0)} credits</p><button class="btn ${i === 1 ? "primary" : "ghost"} topup-action" data-plan="${escapeHtml(plan.key)}" data-provider="tbank" type="button">${ru() ? "Пополнить" : "Top up"}</button></article>`).join("")}</div><div class="table-card"><h3>${ru() ? "История" : "History"}</h3>${tx.length ? tx.map((x) => `<p><b>${escapeHtml(x.provider)}</b><span>${formatCredits(x.credits)} cr · ${escapeHtml(x.status)}</span></p>`).join("") : empty(ru() ? "Операций пока нет." : "No transactions yet.")}</div></section>`;
}

function profile() {
  if (!state.me) return requireAuth("");
  return `<section class="section"><div class="section-head"><p class="eyebrow">${icon("user")}${ru() ? "Профиль" : "Profile"}</p><h2>${escapeHtml(state.me.full_name || state.me.username || "APIX creator")}</h2><p>Telegram ID: ${escapeHtml(state.me.tg_id || "")}</p></div><div class="workflow-grid"><article class="flow-card"><h3>${ru() ? "Аккаунт" : "Account"}</h3><p>${formatCredits(state.me.credits)} credits</p><p>${escapeHtml(state.me.referral_link || "")}</p><button class="btn ghost logout" type="button">${txt[state.lang].logout}</button></article><article class="flow-card"><h3>${ru() ? "Настройки" : "Settings"}</h3><label><span>${ru() ? "Язык" : "Language"}</span><select class="language-select"><option value="ru">RU</option><option value="en">EN</option></select></label><button class="btn primary open-modal" data-modal="settings" type="button">${ru() ? "Открыть" : "Open"}</button></article></div></section>`;
}

function content() {
  return requireAuth(`<section class="section"><div class="section-head"><p class="eyebrow">${icon("check")}Content Manager</p><h2>${ru() ? "Очередь публикаций" : "Publishing queue"}</h2><p>${ru() ? "Шаблоны, превью, статусы и действия для отбора." : "Templates, previews, statuses and review actions."}</p></div>${contentBoard()}</section>`);
}

function contentBoard() {
  const rows = state.adminPrompts.length ? state.adminPrompts : demoTemplates.map((item, id) => ({ id, title: pick(item.title), prompt_text: pick(item.prompt), status: id ? "review" : "ready" }));
  return `<div class="manager"><div class="manager-stats"><article><span>${ru() ? "На проверке" : "In review"}</span><b>${rows.length}</b><p>${ru() ? "шаблонов ждут решения" : "templates awaiting decision"}</p></article><article><span>${ru() ? "Превью OK" : "Preview OK"}</span><b>92%</b><p>${ru() ? "карточек с чистыми обложками" : "cards with clean covers"}</p></article><article><span>${ru() ? "Опубликовано" : "Published"}</span><b>146</b><p>${ru() ? "готовых шаблонов" : "ready templates"}</p></article></div><div class="review-board">${rows.map((row, i) => `<article><div class="thumb thumb-${(i % 3) + 1}"></div><div><span>${escapeHtml(row.status || "review")}</span><h3>${escapeHtml(row.title || "Template")}</h3><p>${escapeHtml(row.prompt_text || "")}</p></div><div class="row-actions"><button type="button">${ru() ? "Принять" : "Approve"}</button><button type="button">${ru() ? "Детали" : "Details"}</button></div></article>`).join("")}</div></div>`;
}

function empty(text) {
  return `<div class="empty">${escapeHtml(text)}</div>`;
}

function modal() {
  if (!state.modal) return "";
  if (state.modal === "login") {
    return `<div class="modal-backdrop"><section class="modal auth-modal" role="dialog" aria-modal="true" aria-labelledby="login-title"><button class="modal-close modal-x" type="button" aria-label="${ru() ? "Закрыть" : "Close"}">${icon("close")}</button><p class="eyebrow">${icon("lock")}${ru() ? "Авторизация" : "Authorization"}</p><h2 id="login-title">${txt[state.lang].login}</h2><p>${ru() ? "Telegram подтверждает аккаунт и открывает Quick Create, PRO Studio, историю, баланс и публикации." : "Telegram confirms your account and opens Quick Create, PRO Studio, history, billing and publishing."}</p><div class="auth-benefits"><span>${icon("check")}${ru() ? "Без пароля" : "No password"}</span><span>${icon("check")}${ru() ? "Баланс привязан к аккаунту" : "Balance tied to account"}</span><span>${icon("check")}${ru() ? "История работ сохраняется" : "Generation history is saved"}</span></div>${telegramSlot("modal")}</section></div>`;
  }
  const title = state.modal === "project" ? (ru() ? "Новый проект" : "New project") : state.modal === "settings" ? (ru() ? "Настройки Studio" : "Studio settings") : (ru() ? "Детали" : "Details");
  return `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true"><button class="modal-close modal-x" type="button" aria-label="${ru() ? "Закрыть" : "Close"}">${icon("close")}</button><p class="eyebrow">${icon("spark")}APIX</p><h2>${title}</h2><p>${ru() ? "Параметры, действия и состояния для выбранного раздела." : "Settings, actions and states for the selected area."}</p><label><span>${ru() ? "Название" : "Title"}</span><input placeholder="${title}"></label><div class="actions"><button class="btn primary modal-close" type="button">OK</button><button class="btn ghost modal-close" type="button">${ru() ? "Закрыть" : "Close"}</button></div></section></div>`;
}

function toast(title, body) {
  state.toast = { title, body };
  render();
  setTimeout(() => { state.toast = null; render(); }, 3200);
}

async function submitGeneration(form) {
  if (!state.me) {
    state.modal = "login";
    render();
    return;
  }
  const data = new FormData(form);
  const mode = form.dataset.mode || "image";
  const model = String(data.get("model") || currentModel(mode)?.key || "");
  const prompt = String(data.get("prompt") || "").trim();
  if (form.classList.contains("studio-composer")) state.studioDraft[mode] = prompt;
  else state.quickDraft[mode] = prompt;
  const reference = String(data.get("reference") || "").trim();
  const file = data.get("reference_file");
  const local = { id: `local_${Date.now()}`, mode, model, prompt, status: "pending", created_at: new Date().toISOString() };
  state.queue.unshift(local);
  saveQueue();
  render();
  try {
    if (!model) throw new Error(ru() ? "Нет доступной модели" : "No available model");
    let referenceUrl = reference;
    if (file && file instanceof File && file.size > 0) {
      local.status = "uploading";
      saveQueue();
      const upload = new FormData();
      upload.append("file", file);
      const uploaded = await web("/uploads/reference", { method: "POST", body: upload });
      referenceUrl = uploaded.url || referenceUrl;
    }
    const body = buildGenerationBody(mode, model, prompt, referenceUrl, data);
    const result = await web(`/generate/${mode}`, { method: "POST", body: JSON.stringify(body) });
    Object.assign(local, result, { status: result.status || "pending" });
    mergeGeneration(local);
    saveQueue();
    toast(ru() ? "Задача в очереди" : "Job queued", `#${result.id || result.generation_id || local.id}`);
    await loadPrivate({ quiet: true });
    pollQueue();
  } catch (error) {
    local.status = "failed";
    local.error = error.message;
    saveQueue();
    toast(ru() ? "Ошибка генерации" : "Generation failed", error.message);
  }
  render();
}

function buildGenerationBody(mode, model, prompt, referenceUrl, data) {
  if (mode === "music") {
    return {
      prompt,
      instrumental: data.get("instrumental") === "1" || data.get("instrumental") === "on",
    };
  }
  if (mode === "video") {
    const selectedMode = String(data.get("mode") || (referenceUrl ? "image" : "text"));
    return {
      model,
      prompt,
      mode: selectedMode,
      duration: Number(data.get("duration") || 5),
      aspect_ratio: String(data.get("aspect_ratio") || "") || null,
      resolution: String(data.get("resolution") || "") || null,
      image_url: referenceUrl && selectedMode === "image" ? referenceUrl : null,
      video_url: String(data.get("video_url") || "") || null,
      reference_urls: [],
    };
  }
  return {
    model,
    prompt,
    aspect_ratio: String(data.get("aspect_ratio") || "") || null,
    quality: String(data.get("quality") || "basic"),
    count: Number(data.get("count") || 1),
    reference_url: referenceUrl || null,
    reference_urls: [],
  };
}

async function pollQueue() {
  const active = state.queue.filter((item) => isActive(item.status) && Number(item.id || item.generation_id));
  await Promise.allSettled(active.map(async (item) => {
    const id = item.id || item.generation_id;
    const updated = await web(`/generations/${id}`);
    Object.assign(item, updated);
    mergeGeneration(updated);
  }));
  saveQueue();
  if (active.length) {
    await loadPrivate({ quiet: true });
    render();
    setTimeout(pollQueue, 4500);
  }
}

function currentView() {
  const views = { home, quick, studio: studioView, library, templates, gallery, billing, profile, content };
  return (views[state.route] || home)();
}

function render() {
  cleanupPublicInteractions();
  root.innerHTML = shell(currentView());
  bind();
}

function cleanupPublicInteractions() {
  if (heroParticleCleanup) {
    heroParticleCleanup();
    heroParticleCleanup = null;
  }
  if (revealObserver) {
    revealObserver.disconnect();
    revealObserver = null;
  }
}

function closeAuthMenus() {
  document.querySelectorAll("[data-auth-menu]").forEach((menu) => {
    const trigger = menu.querySelector(".auth-trigger");
    const panel = menu.querySelector(".auth-panel");
    if (!trigger || !panel) return;
    trigger.setAttribute("aria-expanded", "false");
    panel.hidden = true;
  });
}

function handleDocumentClick(event) {
  if (!event.target.closest("[data-auth-menu]")) closeAuthMenus();
}

function handleDocumentKeydown(event) {
  if (event.key === "Escape") {
    closeAuthMenus();
    if (state.modal) {
      state.modal = null;
      render();
    }
  }
}

function updateScrollChrome() {
  const progress = document.querySelector(".scroll-progress span");
  const floating = document.querySelector(".floating-nav");
  const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
  const ratio = Math.min(1, Math.max(0, window.scrollY / max));
  if (progress) progress.style.transform = `scaleX(${ratio})`;
  if (floating) floating.classList.toggle("is-visible", window.scrollY > 260 && state.route === "home" && !state.me);
}

function prefersReducedMotion() {
  return Boolean(reducedMotionQuery?.matches);
}

function initHeroParticles() {
  const canvas = document.querySelector("canvas[data-hero-particles]");
  if (!canvas || heroParticleCleanup) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const stage = canvas.closest(".hero-stage") || canvas;

  const palette = [
    ["rgba(125, 211, 255, .95)", "rgba(125, 211, 255, .22)"],
    ["rgba(197, 156, 255, .95)", "rgba(197, 156, 255, .2)"],
    ["rgba(94, 234, 212, .86)", "rgba(94, 234, 212, .18)"],
    ["rgba(255, 209, 102, .78)", "rgba(255, 209, 102, .14)"],
  ];
  const pointer = { x: 0, y: 0, active: false };
  let particles = [];
  let frame = 0;
  let resizeFrame = 0;
  let width = 1;
  let height = 1;
  let reduced = prefersReducedMotion();

  Object.assign(canvas.style, {
    position: "absolute",
    inset: "0",
    zIndex: "0",
    width: "100%",
    height: "100%",
    pointerEvents: "none",
    mixBlendMode: "screen",
  });

  function createParticle(index) {
    const [color, glow] = palette[index % palette.length];
    const angle = Math.random() * Math.PI * 2;
    const distance = .18 + Math.random() * .42;
    const depth = .5 + Math.random() * .9;
    return {
      x: width * (.5 + Math.cos(angle) * distance),
      y: height * (.5 + Math.sin(angle) * distance * .72),
      baseX: width * (.5 + Math.cos(angle) * distance),
      baseY: height * (.5 + Math.sin(angle) * distance * .72),
      vx: (Math.random() - .5) * (.18 + depth * .18),
      vy: (Math.random() - .5) * (.14 + depth * .16),
      radius: 1 + Math.random() * 2.6,
      phase: Math.random() * Math.PI * 2,
      speed: .5 + Math.random() * 1.2,
      depth,
      color,
      glow,
    };
  }

  function createParticles() {
    const density = Math.round((width * height) / 7600);
    const count = reduced ? Math.min(30, Math.max(18, density)) : Math.min(84, Math.max(38, density));
    particles = Array.from({ length: count }, (_, index) => createParticle(index));
  }

  function drawGlow(cx, cy, radius, stops) {
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    stops.forEach(([stop, color]) => gradient.addColorStop(stop, color));
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
  }

  function draw(time = 0, animate = false) {
    const t = time / 1000;
    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    drawGlow(width * .62, height * .38, Math.max(width, height) * .72, [
      [0, "rgba(125, 211, 255, .16)"],
      [.42, "rgba(197, 156, 255, .08)"],
      [1, "rgba(125, 211, 255, 0)"],
    ]);
    drawGlow(width * .28, height * .72, Math.max(width, height) * .55, [
      [0, "rgba(94, 234, 212, .1)"],
      [.54, "rgba(255, 209, 102, .045)"],
      [1, "rgba(94, 234, 212, 0)"],
    ]);

    particles.forEach((particle, index) => {
      if (animate) {
        const driftX = Math.cos(particle.phase + t * particle.speed) * 12;
        const driftY = Math.sin(particle.phase + t * (particle.speed + .18)) * 9;
        const dx = pointer.x - particle.x;
        const dy = pointer.y - particle.y;
        const distance = Math.hypot(dx, dy) || 1;
        const force = pointer.active ? Math.max(0, 1 - distance / 170) : 0;
        particle.baseX += particle.vx;
        particle.baseY += particle.vy;
        if (particle.baseX < -32) particle.baseX = width + 32;
        if (particle.baseX > width + 32) particle.baseX = -32;
        if (particle.baseY < -32) particle.baseY = height + 32;
        if (particle.baseY > height + 32) particle.baseY = -32;
        particle.x += (particle.baseX + driftX - particle.x) * .035 - (dx / distance) * force * 3.8;
        particle.y += (particle.baseY + driftY - particle.y) * .035 - (dy / distance) * force * 3.8;
      }

      for (let j = index + 1; j < particles.length; j += 1) {
        const other = particles[j];
        const gap = Math.hypot(particle.x - other.x, particle.y - other.y);
        const maxGap = 104 + (particle.depth + other.depth) * 22;
        if (gap > maxGap) continue;
        ctx.beginPath();
        ctx.strokeStyle = `rgba(190, 220, 255, ${((1 - gap / maxGap) * .18).toFixed(3)})`;
        ctx.lineWidth = .45 + (particle.depth + other.depth) * .18;
        ctx.moveTo(particle.x, particle.y);
        ctx.lineTo(other.x, other.y);
        ctx.stroke();
      }

      const pulse = .84 + Math.sin(t * particle.speed + particle.phase) * .16;
      const radius = particle.radius * particle.depth * pulse;
      const halo = ctx.createRadialGradient(particle.x, particle.y, 0, particle.x, particle.y, radius * 8);
      halo.addColorStop(0, particle.glow);
      halo.addColorStop(.5, "rgba(125, 211, 255, .045)");
      halo.addColorStop(1, "rgba(125, 211, 255, 0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, radius * 8, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = particle.color;
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, radius, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }

  function animate(time = 0) {
    draw(time, true);
    frame = window.requestAnimationFrame(animate);
  }

  function start() {
    window.cancelAnimationFrame(frame);
    if (reduced) {
      draw(performance.now(), false);
      return;
    }
    frame = window.requestAnimationFrame(animate);
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    createParticles();
    draw(performance.now(), false);
  }

  function requestResize() {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(() => {
      resize();
      start();
    });
  }

  function move(event) {
    const rect = canvas.getBoundingClientRect();
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    pointer.active = true;
  }

  function leave() {
    pointer.active = false;
  }

  function handleMotionChange() {
    reduced = prefersReducedMotion();
    resize();
    start();
  }

  resize();
  start();
  stage.addEventListener("pointermove", move);
  stage.addEventListener("pointerleave", leave);
  stage.addEventListener("pointercancel", leave);
  window.addEventListener("resize", requestResize, { passive: true });
  if (reducedMotionQuery?.addEventListener) {
    reducedMotionQuery.addEventListener("change", handleMotionChange);
  } else {
    reducedMotionQuery?.addListener?.(handleMotionChange);
  }

  heroParticleCleanup = () => {
    window.cancelAnimationFrame(frame);
    window.cancelAnimationFrame(resizeFrame);
    stage.removeEventListener("pointermove", move);
    stage.removeEventListener("pointerleave", leave);
    stage.removeEventListener("pointercancel", leave);
    window.removeEventListener("resize", requestResize);
    if (reducedMotionQuery?.removeEventListener) {
      reducedMotionQuery.removeEventListener("change", handleMotionChange);
    } else {
      reducedMotionQuery?.removeListener?.(handleMotionChange);
    }
  };
}

function bindTiltCards() {
  const pointerFine = window.matchMedia?.("(hover: hover) and (pointer: fine)")?.matches ?? true;
  const disabled = prefersReducedMotion() || !pointerFine;
  document.querySelectorAll(".tilt-card").forEach((card) => {
    if (card.dataset.tiltReady === "1") return;
    card.dataset.tiltReady = "1";
    card.style.setProperty("--tilt-x", "0deg");
    card.style.setProperty("--tilt-y", "0deg");
    card.style.setProperty("--glow-x", "50%");
    card.style.setProperty("--glow-y", "50%");
    card.style.transformStyle = "preserve-3d";
    card.style.isolation = "isolate";
    card.style.willChange = "transform";
    if (getComputedStyle(card).position === "static") card.style.position = "relative";

    let glow = card.querySelector(":scope > .tilt-glow");
    if (!glow) {
      glow = document.createElement("span");
      glow.className = "tilt-glow";
      glow.setAttribute("aria-hidden", "true");
      Object.assign(glow.style, {
        position: "absolute",
        inset: "0",
        zIndex: "0",
        borderRadius: "inherit",
        pointerEvents: "none",
        opacity: "0",
        background: "radial-gradient(circle at var(--glow-x) var(--glow-y), rgba(255,255,255,.3), rgba(125,211,255,.18) 20%, rgba(240,167,255,.1) 42%, transparent 68%)",
        mixBlendMode: "screen",
        transition: "opacity .22s ease",
      });
      card.appendChild(glow);
    }

    if (disabled) return;

    card.addEventListener("pointermove", (event) => {
      const rect = card.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
      const tiltX = (0.5 - y) * 8;
      const tiltY = (x - 0.5) * 10;
      const shadowX = (x - .5) * -22;
      const shadowY = (y - .5) * -18;
      card.style.setProperty("--tilt-x", `${tiltX.toFixed(2)}deg`);
      card.style.setProperty("--tilt-y", `${tiltY.toFixed(2)}deg`);
      card.style.setProperty("--glow-x", `${Math.round(x * 100)}%`);
      card.style.setProperty("--glow-y", `${Math.round(y * 100)}%`);
      card.style.transform = "perspective(1000px) rotateX(var(--tilt-x)) rotateY(var(--tilt-y)) translate3d(0, -4px, 0)";
      card.style.boxShadow = `0 30px 90px rgba(0, 0, 0, .44), ${shadowX.toFixed(1)}px ${shadowY.toFixed(1)}px 46px rgba(125, 211, 255, .13), inset 0 1px 0 rgba(255,255,255,.12)`;
      glow.style.opacity = "1";
    });

    const resetTilt = () => {
      card.style.setProperty("--tilt-x", "0deg");
      card.style.setProperty("--tilt-y", "0deg");
      card.style.setProperty("--glow-x", "50%");
      card.style.setProperty("--glow-y", "50%");
      card.style.transform = "";
      card.style.boxShadow = "";
      glow.style.opacity = "0";
    };
    card.addEventListener("pointerleave", resetTilt);
    card.addEventListener("pointercancel", resetTilt);
  });
}

function revealElement(element) {
  if (element.classList.contains("is-revealed")) {
    element.style.opacity = "1";
    element.style.willChange = "";
    return;
  }
  const delay = Number(element.dataset.revealDelay || 0);
  element.classList.add("is-revealed");
  element.style.opacity = "1";

  if (prefersReducedMotion() || typeof element.animate !== "function") {
    element.style.willChange = "";
    return;
  }

  const animation = element.animate([
    { opacity: 0, transform: "translate3d(0, 28px, 0) scale(.985)", filter: "blur(10px)" },
    { opacity: 1, transform: "translate3d(0, 0, 0) scale(1)", filter: "blur(0)" },
  ], {
    duration: 720,
    delay,
    easing: "cubic-bezier(.2, .75, .2, 1)",
    fill: "both",
  });
  animation.finished.then(() => {
    if (!element.isConnected) return;
    element.style.opacity = "";
    element.style.willChange = "";
  }).catch(() => {});
}

function initReveal() {
  const selectors = [
    ".public-layout main > .hero",
    ".public-layout .trust-bar",
    ".public-layout .showcase-card",
    ".public-layout main > .section",
    ".public-layout .quick-card",
    ".public-layout .audience-grid article",
    ".public-layout .platform-map article",
    ".public-layout .visual-wall > article",
    ".public-layout .visual-step",
    ".public-layout .workflow-timeline article",
    ".public-layout .price-grid article",
    ".public-layout .final-cta",
    ".public-layout .footer",
  ];
  const targets = Array.from(new Set(document.querySelectorAll(selectors.join(","))));
  if (!targets.length) return;

  if (prefersReducedMotion() || !("IntersectionObserver" in window)) {
    targets.forEach((node) => {
      node.classList.add("is-revealed");
      node.style.opacity = "";
      node.style.willChange = "";
    });
    return;
  }

  revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      revealElement(entry.target);
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: .12 });

  targets.forEach((node, index) => {
    node.classList.remove("is-revealed");
    node.dataset.revealDelay = String(Math.min(220, (index % 6) * 45));
    node.style.opacity = "0";
    node.style.willChange = "opacity, transform, filter";
    if (node.getBoundingClientRect().top < window.innerHeight * .92) {
      revealElement(node);
    } else {
      revealObserver.observe(node);
    }
  });
}

function bind() {
  document.querySelectorAll(".lang").forEach((button) => button.addEventListener("click", () => {
    state.lang = state.lang === "ru" ? "en" : "ru";
    localStorage.setItem(langKey, state.lang);
    render();
  }));
  document.querySelectorAll(".logout").forEach((button) => button.addEventListener("click", () => {
    localStorage.removeItem(tokenKey);
    state.token = "";
    state.me = null;
    closeRealtime();
    location.hash = "#/home";
    render();
  }));
  document.querySelectorAll(".gen-form").forEach((form) => form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitGeneration(form);
  }));
  document.querySelectorAll(".gen-form textarea[name='prompt']").forEach((textarea) => textarea.addEventListener("input", () => {
    const form = textarea.closest(".gen-form");
    const mode = form?.dataset.mode || state.studioMode;
    if (form?.classList.contains("studio-composer")) state.studioDraft[mode] = textarea.value;
    else state.quickDraft[mode] = textarea.value;
  }));
  document.querySelectorAll(".model-select").forEach((select) => select.addEventListener("change", () => {
    const mode = select.dataset.mode || state.studioMode;
    state.modelSelection[mode] = select.value;
    const form = select.closest(".gen-form");
    const prompt = form?.querySelector("textarea[name='prompt']")?.value || "";
    if (form?.classList.contains("studio-composer")) state.studioDraft[mode] = prompt;
    else state.quickDraft[mode] = prompt;
    render();
  }));
  document.querySelectorAll(".improve-prompt").forEach((button) => button.addEventListener("click", async () => {
    const form = button.closest("form");
    const textarea = form?.querySelector("textarea[name='prompt']");
    const prompt = textarea?.value?.trim();
    if (!textarea || !prompt) return;
    button.disabled = true;
    try {
      const result = await web("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt, kind: button.dataset.kind || state.studioMode }) });
      textarea.value = result.prompt || prompt;
      if (form?.classList.contains("studio-composer")) state.studioDraft[state.studioMode] = textarea.value;
      toast(ru() ? "Промпт уточнён" : "Prompt improved", ru() ? "Можно запускать генерацию." : "Ready to generate.");
    } catch (error) {
      toast(ru() ? "Ошибка промпта" : "Prompt error", error.message);
    } finally {
      button.disabled = false;
    }
  }));
  document.querySelectorAll(".seg").forEach((button) => button.addEventListener("click", () => {
    const textarea = document.querySelector(".studio-composer textarea[name='prompt']");
    if (textarea) state.studioDraft[state.studioMode] = textarea.value;
    state.studioMode = button.dataset.mode || "image";
    render();
  }));
  document.querySelectorAll(".asset-action").forEach((button) => button.addEventListener("click", async () => {
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (!id || !action) return;
    button.disabled = true;
    try {
      await web(`/generations/${id}/${action}`, { method: "POST" });
      await loadPrivate({ quiet: true });
      toast(ru() ? "Готово" : "Done", ru() ? "Материал опубликован в галерею и библиотеку." : "Asset published to gallery and library.");
      render();
    } catch (error) {
      toast(ru() ? "Ошибка публикации" : "Publish failed", error.message);
    } finally {
      button.disabled = false;
    }
  }));
  document.querySelectorAll(".topup-action").forEach((button) => button.addEventListener("click", async () => {
    const planKey = button.dataset.plan;
    const provider = button.dataset.provider || "tbank";
    if (!planKey || planKey.startsWith("demo_")) return;
    button.disabled = true;
    try {
      const result = await web(`/billing/topup/${provider}`, { method: "POST", body: JSON.stringify({ plan_key: planKey }) });
      const url = result.pay_url || result.invoice_link;
      if (url) window.location.href = url;
      else toast(ru() ? "Счёт создан" : "Invoice created", `#${result.transaction_id || ""}`);
    } catch (error) {
      toast(ru() ? "Ошибка оплаты" : "Payment failed", error.message);
    } finally {
      button.disabled = false;
    }
  }));
  document.querySelectorAll(".open-modal").forEach((button) => button.addEventListener("click", () => {
    state.modal = button.dataset.modal || "details";
    closeAuthMenus();
    render();
  }));
  document.querySelectorAll(".modal-close").forEach((button) => button.addEventListener("click", () => {
    state.modal = null;
    render();
  }));
  document.querySelectorAll(".auth-trigger").forEach((button) => button.addEventListener("click", () => {
    const menu = button.closest("[data-auth-menu]");
    const panel = menu?.querySelector(".auth-panel");
    const expanded = button.getAttribute("aria-expanded") === "true";
    closeAuthMenus();
    button.setAttribute("aria-expanded", expanded ? "false" : "true");
    if (panel) panel.hidden = expanded;
  }));
  document.querySelectorAll("[data-scroll]").forEach((link) => link.addEventListener("click", (event) => {
    const id = link.dataset.scroll;
    const scroll = () => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    closeAuthMenus();
    if (state.route !== "home") {
      event.preventDefault();
      state.route = "home";
      location.hash = "#/home";
      render();
      setTimeout(scroll, 30);
    } else {
      event.preventDefault();
      scroll();
    }
  }));
  document.querySelectorAll(".use-template,.remix").forEach((button) => button.addEventListener("click", () => {
    state.route = "studio";
    location.hash = "#/studio";
    state.studioDraft[state.studioMode] = button.dataset.prompt || "";
    setTimeout(() => {
      const textarea = document.querySelector(".studio-composer textarea");
      if (textarea) textarea.value = button.dataset.prompt || "";
    }, 50);
  }));
  document.querySelectorAll(".open-detail").forEach((button) => button.addEventListener("click", () => {
    state.modal = "details";
    render();
  }));
  document.removeEventListener("click", handleDocumentClick);
  document.removeEventListener("keydown", handleDocumentKeydown);
  window.removeEventListener("scroll", updateScrollChrome);
  document.addEventListener("click", handleDocumentClick);
  document.addEventListener("keydown", handleDocumentKeydown);
  window.addEventListener("scroll", updateScrollChrome, { passive: true });
  initHeroParticles();
  bindTiltCards();
  initReveal();
  updateScrollChrome();
}

window.addEventListener("hashchange", () => {
  state.route = routeName();
  render();
});

boot();
