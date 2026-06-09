const API_BASE = "/api/web";
const TOKEN_KEY = "apix-premium-web-token";
const LANG_KEY = "apix-premium-language";
const FULL_FEED_LIMIT = 240;
const PROMPT_LIBRARY_LIMIT = 60;

const state = {
  token: "",
  authConfig: null,
  user: null,
  examples: [],
  models: [],
  modelsByKind: { image: [], video: [], music: [] },
  activeExample: 0,
  modelType: "all",
  generationKind: "image",
  queue: [],
  history: [],
  prompts: [],
  adminPrompts: [],
  assistantHistory: [],
  help: null,
  billing: null,
  plans: [],
  paymentMethods: [],
  referrals: null,
  activeImageSession: null,
  paymentOptions: [],
  promptSource: "catalog",
  feedSource: "feed",
  socket: null,
  fallbackMode: false,
  routeModelKey: "",
  routeFlow: "",
  routePrompt: "",
  openSelectProxy: null,
  pendingGenerationForm: null,
  generationStatus: null,
  generationStatusPollTimer: null,
  completedGenerationNotices: {},
  routeReferenceUrl: "",
  routeReferenceUrls: [],
  routeSourceReferenceUrl: "",
  routeFeedRemixId: "",
  mediaViewerItems: [],
  mediaViewerIndex: 0,
};

function currentLanguage() {
  const lang = String(state.user?.language || localStorage.getItem(LANG_KEY) || "ru").toLowerCase();
  return lang === "en" ? "en" : "ru";
}

function syncLanguageUi() {
  const lang = currentLanguage();
  document.documentElement.lang = lang;
  $$("[data-language]").forEach((button) => {
    const active = String(button.dataset.language || "ru").toLowerCase() === lang;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const PROMPT_INJECTION_CATEGORIES = [
  {
    title: "Стиль кадра",
    items: [
      { key: "cinematic", label: "Кино", copy: "Кадр с глубиной и выразительной подачей.", hint: "cinematic frame, film still, expressive depth", kinds: ["image", "video"] },
      { key: "editorial", label: "Журнал", copy: "Полированный fashion-стиль и уверенная поза.", hint: "editorial fashion look, polished magazine styling", kinds: ["image", "video"] },
      { key: "luxury", label: "Премиум", copy: "Дорогие материалы и спокойная эстетика.", hint: "luxury visual language, premium materials, elegant mood", kinds: ["image", "video"] },
      { key: "lifestyle", label: "Натурально", copy: "Живой момент без тяжёлой постановки.", hint: "natural lifestyle scene, relaxed authentic moment", kinds: ["image", "video"] },
      { key: "product", label: "Товар", copy: "Чёткий герой, чистый фон и коммерческая ясность.", hint: "clean product photography, crisp hero object, commercial clarity", kinds: ["image", "video"] },
      { key: "beauty", label: "Бьюти", copy: "Акцент на лице, коже и аккуратном крупном плане.", hint: "beauty campaign, refined skin texture, elegant close-up", kinds: ["image", "video"] },
    ],
  },
  {
    title: "Свет",
    items: [
      { key: "soft-light", label: "Мягкий", copy: "Рассеянный свет, нежные тени и приятный контраст.", hint: "soft diffused light, gentle shadows, flattering contrast", kinds: ["image", "video"] },
      { key: "golden-hour", label: "Закат", copy: "Тёплое сияние и мягкие длинные тени.", hint: "warm golden hour light, natural glow, long soft shadows", kinds: ["image", "video"] },
      { key: "studio-light", label: "Студия", copy: "Контролируемый свет и чистая экспозиция.", hint: "controlled studio lighting, clean highlights, balanced exposure", kinds: ["image", "video"] },
      { key: "neon", label: "Неон", copy: "Яркие акценты, отражения и ночная атмосфера.", hint: "neon accents, glossy reflections, vibrant night atmosphere", kinds: ["image", "video"] },
      { key: "dramatic", label: "Драма", copy: "Глубокие тени, боковой свет и сильный контраст.", hint: "dramatic side light, deep contrast, cinematic shadows", kinds: ["image", "video"] },
    ],
  },
  {
    title: "Композиция",
    items: [
      { key: "centered", label: "Центр", copy: "Главный объект сразу читается в кадре.", hint: "centered composition, clear subject hierarchy, uncluttered frame", kinds: ["image", "video"] },
      { key: "rule-thirds", label: "Трети", copy: "Больше воздуха и естественный баланс сцены.", hint: "rule of thirds composition, balanced negative space", kinds: ["image", "video"] },
      { key: "close-up", label: "Крупно", copy: "Сильный фокус на лице, предмете или детали.", hint: "close-up framing, strong focal point, intimate detail", kinds: ["image", "video"] },
      { key: "wide-shot", label: "Широко", copy: "Больше пространства, окружения и глубины.", hint: "wide establishing frame, environmental context, spacious depth", kinds: ["image", "video"] },
      { key: "dynamic", label: "Динамика", copy: "Энергичный угол и более живое движение кадра.", hint: "dynamic angle, diagonal lines, energetic composition", kinds: ["image", "video"] },
    ],
  },
  {
    title: "Цвет и настроение",
    items: [
      { key: "pastel", label: "Пастель", copy: "Мягкая палитра, лёгкость и нежное настроение.", hint: "soft pastel palette, airy gentle mood, low saturation", kinds: ["image", "video"] },
      { key: "bold-color", label: "Ярко", copy: "Запоминающиеся акценты и чистый контраст.", hint: "bold color accents, clean contrast, memorable palette", kinds: ["image", "video"] },
      { key: "monochrome", label: "Монохром", copy: "Сдержанная палитра и тональная гармония.", hint: "monochrome palette, tonal harmony, refined minimal color", kinds: ["image", "video"] },
      { key: "warm", label: "Тёплый", copy: "Уютная температура цвета и золотые акценты.", hint: "warm color temperature, cozy mood, golden highlights", kinds: ["image", "video"] },
      { key: "cool", label: "Холодный", copy: "Современная прохлада и чистые синие тона.", hint: "cool color temperature, modern atmosphere, crisp blue tones", kinds: ["image", "video"] },
    ],
  },
  {
    title: "Качество и детали",
    items: [
      { key: "high-detail", label: "Детали", copy: "Чистые фактуры и резкость в важных местах.", hint: "high detail, clean texture, sharp important elements", kinds: ["image", "video"] },
      { key: "realistic", label: "Реализм", copy: "Естественная анатомия и правдоподобные материалы.", hint: "photorealistic, natural anatomy, believable materials", kinds: ["image", "video"] },
      { key: "clean-bg", label: "Чистый фон", copy: "Меньше визуального шума, больше внимания герою.", hint: "clean background, no clutter, subject clearly separated", kinds: ["image", "video"] },
      { key: "no-artifacts", label: "Без ошибок", copy: "Снижает риск лишних деталей, текста и искажений.", hint: "no extra limbs, no distorted hands, no text artifacts", kinds: ["image", "video"] },
      { key: "skin-natural", label: "Живая кожа", copy: "Натуральная фактура без пластикового ретуша.", hint: "natural skin texture, accurate facial features, no plastic retouch", kinds: ["image", "video"] },
    ],
  },
  {
    title: "Видео",
    items: [
      { key: "slow-motion", label: "Плавно", copy: "Медленное движение без резких скачков.", hint: "smooth slow motion, graceful movement, stable temporal consistency", kinds: ["video"] },
      { key: "camera-push", label: "Наезд", copy: "Мягкое приближение камеры к главному объекту.", hint: "slow camera push-in, cinematic parallax, stable subject", kinds: ["video"] },
      { key: "handheld", label: "Живая камера", copy: "Лёгкая ручная динамика и документальное ощущение.", hint: "subtle handheld camera, documentary realism, natural motion", kinds: ["video"] },
      { key: "loopable", label: "Петля", copy: "Движение, которое аккуратно повторяется по кругу.", hint: "seamless loopable motion, clean start and end, no abrupt cut", kinds: ["video"] },
    ],
  },
  {
    title: "Музыка",
    items: [
      { key: "music-cinematic", label: "Кино", copy: "Эмоциональное развитие и объёмный микс.", hint: "cinematic arrangement, emotional build, polished mix", kinds: ["music"] },
      { key: "music-pop", label: "Поп", copy: "Яркий хук, понятная структура и лёгкая энергия.", hint: "catchy pop structure, clean hook, radio-ready energy", kinds: ["music"] },
      { key: "music-lofi", label: "Lo-fi", copy: "Тёплый звук, мягкий ритм и ностальгия.", hint: "lo-fi texture, warm drums, soft nostalgic atmosphere", kinds: ["music"] },
      { key: "music-dance", label: "Dance", copy: "Ровный пульс и клубная динамика.", hint: "dance groove, steady pulse, bright club energy", kinds: ["music"] },
      { key: "music-ambient", label: "Ambient", copy: "Пространство, спокойствие и плавная атмосфера.", hint: "ambient soundscape, spacious pads, calm evolving texture", kinds: ["music"] },
    ],
  },
];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function unwrap(json) {
  return Object.prototype.hasOwnProperty.call(json || {}, "data") ? json.data : json;
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers["X-Web-Auth-Token"] = state.token;
  if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const url = path.startsWith("/api/") ? path : `${API_BASE}${path}`;
  const response = await fetch(url, { credentials: "same-origin", ...options, headers });
  const json = await response.json().catch(() => ({}));
  if (!response.ok || json.ok === false) {
    throw new Error(json.error || json.detail || `HTTP ${response.status}`);
  }
  return unwrap(json);
}

async function optionalRequest(path, fallback = null) {
  try {
    return await request(path);
  } catch {
    return fallback;
  }
}

function cleanModelName(value) {
  return String(value || "")
    .replace(/[^\p{L}\p{N}\s./_-]/gu, "")
    .replace(/__.+$/, "")
    .replaceAll("/", " / ")
    .replace(/\s+/g, " ")
    .trim();
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function formatCurrency(value) {
  return `${formatNumber(value)}₽`;
}

function paymentMethodKey(method) {
  if (typeof method === "string") return method;
  return String(method?.key || method?.provider || "");
}

function paymentMethodLabel(method) {
  const key = paymentMethodKey(method);
  const labels = { tbank: "Карта", stars: "Telegram", crypto: "Крипто", lava: "Lava" };
  return method?.label || labels[key] || key;
}

function enabledPaymentMethods() {
  return (state.billing?.methods || state.paymentMethods || [])
    .map((method) => typeof method === "string" ? { key: method, label: paymentMethodLabel(method), status: "enabled" } : method)
    .filter((method) => method && method.status !== "disabled" && paymentMethodKey(method));
}

function percentLabel(value, fallback) {
  const numeric = Number(value ?? fallback ?? 0);
  return `${formatNumber(numeric <= 1 ? numeric * 100 : numeric)}%`;
}

function modeCountLabel(count) {
  if (count === 1) return "режим";
  if (count >= 2 && count <= 4) return "режима";
  return "режимов";
}

function typeLabel(type) {
  if (type === "video") return "Видео";
  if (type === "music") return "Музыка";
  return "Картинки";
}

function shortTypeLabel(type) {
  if (type === "video") return "Видео";
  if (type === "music") return "Музыка";
  return "Картинки";
}

function unitLabel(type) {
  if (type === "video") return "за видео";
  if (type === "music") return "за трек";
  return "за работу";
}

function omniResolutionKey(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw || raw === "auto") return "720p";
  if (raw === "2160p") return "4k";
  return raw;
}

function modelPriceRange(model) {
  if (!model) return { min: 0, max: 0 };
  if (model.type === "music") {
    const amount = Number(model.credits || 0);
    return { min: amount, max: amount };
  }
  if (model.type === "video") {
    const values = [];
    if (model.key === "gemini-omni-video") {
      Object.values(model.priceTable || {}).forEach((prices) => {
        Object.values(prices || {}).forEach((value) => {
          const numeric = Number(value || 0);
          if (Number.isFinite(numeric) && numeric > 0) values.push(numeric);
        });
      });
      Object.values(model.videoInputPrices || {}).forEach((value) => {
        const numeric = Number(value || 0);
        if (Number.isFinite(numeric) && numeric > 0) values.push(numeric);
      });
    } else if (model.creditsPerSec) {
      const durations = (model.durations || []).map((value) => Number(value || 0)).filter((value) => Number.isFinite(value) && value > 0);
      if (durations.length) durations.forEach((duration) => values.push(Number(model.creditsPerSec || 0) * duration));
      else values.push(Number(model.creditsPerSec || 0));
    } else {
      values.push(Number(model.credits || 0));
    }
    const sane = values.filter((value) => Number.isFinite(value) && value > 0);
    if (!sane.length) {
      const amount = Number(model.credits || 0);
      return { min: amount, max: amount };
    }
    return { min: Math.min(...sane), max: Math.max(...sane) };
  }
  const amount = Number(model.credits || 0);
  return { min: amount, max: amount };
}

function creditLabel(model) {
  const range = modelPriceRange(model);
  const value = range.min === range.max
    ? formatNumber(range.min)
    : `${formatNumber(range.min)}-${formatNumber(range.max)}`;
  if (model?.type === "music") return `${value} за трек`;
  if (model?.type === "video") return `${value} за видео`;
  return `${value} за работу`;
}

function modelApiType(model) {
  return model?.type || model?.gen_type || "image";
}

function normalizeModel(model, fallbackType = "image") {
  const type = model.gen_type || model.type || fallbackType;
  return {
    key: model.key || model.model_key || model.technical_key || "",
    name: cleanModelName(model.display_name || model.name || model.model_key || model.key || ""),
    type,
    credits: Number(model.credits || 0),
    capabilities: model.capabilities || model.modes || [type],
    active: model.is_active ?? model.active ?? true,
    aspectRatios: model.aspect_ratios || [],
    qualities: model.quality_options || [],
    qualityPrices: model.quality_prices || {},
    aspectRatioModes: model.aspect_ratio_modes || [],
    aspectRatioMinRefs: Number(model.aspect_ratio_min_refs || 0),
    maxRefs: Number(model.max_refs || 0),
    counts: model.counts || [],
    durations: model.durations || [],
    resolutions: model.resolutions || [],
    motionControls: model.motion_controls || [],
    modeOptions: model.mode_options || [],
    supportsVideoInput: Boolean(model.supports_video_input),
    maxAudioIds: Number(model.max_audio_ids || 0),
    maxCharacterIds: Number(model.max_character_ids || 0),
    hasSeed: Boolean(model.has_seed),
    priceTable: model.price_table || {},
    videoInputPrices: model.video_input_prices || {},
    creditsPerSec: Number(model.credits_per_sec || 0) || null,
    modes: model.modes || [],
  };
}

function modelFamilyKey(model) {
  let key = String(model.key || model.name || "").toLowerCase();
  key = key.replace(/__.+$/, "");
  key = key
    .replace(/(?:\/|-)(text-to-image|image-to-image|image-edit|text-to-video|image-to-video|video-to-video)$/, "")
    .replace(/(?:\/|-)(image-edit-pro|image-edit|edit-pro|edit)$/, "");
  return `${model.type}:${key || cleanModelName(model.name).toLowerCase()}`;
}

function modelModeLabels(model) {
  const source = `${model.key || ""} ${model.name || ""}`.toLowerCase();
  const labels = [];
  const referenceMode = /(image-to-image|image-edit|\/edit|-edit|\bedit\b)/.test(source);
  if (/text-to-(image|video)|\/text-to|-text-to/.test(source) || !referenceMode) labels.push("по описанию");
  if (referenceMode) labels.push("по примеру");
  const quality = source.match(/__quality=([a-z0-9]+)/)?.[1];
  if (quality) labels.push(quality.toUpperCase());
  return labels;
}

function capabilityLabel(value) {
  const source = String(value || "").toLowerCase();
  if (!source) return "Готово к созданию";
  if (source.includes("image-to") || source.includes("reference") || source.includes("edit")) return "по примеру";
  if (source.includes("text-to") || source === "text") return "по описанию";
  if (source.includes("video")) return "видео";
  if (source.includes("music") || source.includes("audio")) return "музыка";
  if (source.includes("image")) return "картинки";
  if (source === "active") return "доступно";
  return String(value).replace(/[-_]/g, " ");
}

function statusLabel(value) {
  const source = String(value || "").toLowerCase();
  if (source === "processing") return "готовится";
  if (source === "queued") return "в очереди";
  if (source === "pending") return "ожидает";
  if (source === "done" || source === "completed") return "готово";
  if (source === "failed" || source === "error") return "нужен повтор";
  if (source === "draft") return "черновик";
  return String(value || "в работе").replace(/[-_]/g, " ");
}

function preferredVariant(variants) {
  return [...variants].sort((left, right) => {
    const score = (model) => {
      const source = `${model.key || ""} ${model.name || ""}`.toLowerCase();
      let value = 0;
      if (/(image-to-image|image-edit|\/edit|-edit|\bedit\b)/.test(source)) value += 20;
      if (/__quality=/.test(source)) value += 8;
      if (!model.active) value += 4;
      return value;
    };
    return score(left) - score(right);
  })[0] || variants[0];
}

function cleanFamilyName(name) {
  return cleanModelName(name)
    .replace(/\s+Edit\s+Pro$/i, "")
    .replace(/\s+Edit$/i, "")
    .replace(/\s+·\s+.+$/i, "")
    .trim();
}

function groupModels(models) {
  const groups = new Map();
  models.forEach((model) => {
    const key = modelFamilyKey(model);
    const group = groups.get(key) || {
      key,
      type: model.type,
      variants: [],
      modes: new Set(),
      qualities: new Set(),
      active: false,
    };
    group.variants.push(model);
    group.active = group.active || Boolean(model.active);
    modelModeLabels(model).forEach((label) => {
      if (["BASIC", "HIGH", "1K", "2K", "4K"].includes(label)) group.qualities.add(label === "HIGH" ? "4K" : label);
      else group.modes.add(label);
    });
    groups.set(key, group);
  });

  return Array.from(groups.values()).map((group) => {
    const preferred = preferredVariant(group.variants);
    const credits = group.variants.flatMap((model) => {
      const range = modelPriceRange(model);
      return [range.min, range.max];
    }).filter((value) => Number.isFinite(value) && value > 0);
    const minCredits = credits.length ? Math.min(...credits) : 0;
    const maxCredits = credits.length ? Math.max(...credits) : 0;
    const modes = Array.from(group.modes);
    const qualities = Array.from(group.qualities);
    const firstList = (field) => group.variants.find((model) => model[field]?.length)?.[field] || preferred[field] || [];
    const qualityPrices = Object.assign({}, ...group.variants.map((model) => model.qualityPrices || {}));
    const mergedPriceTable = Object.assign({}, ...group.variants.map((model) => model.priceTable || {}));
    const mergedVideoInputPrices = Object.assign({}, ...group.variants.map((model) => model.videoInputPrices || {}));
    const displayName = cleanFamilyName(preferred.name || preferred.key);
    return {
      ...group,
      preferred: {
        ...preferred,
        name: displayName,
        credits: minCredits || preferred.credits,
        qualityPrices: Object.keys(qualityPrices).length ? qualityPrices : preferred.qualityPrices,
        priceTable: Object.keys(mergedPriceTable).length ? mergedPriceTable : preferred.priceTable,
        videoInputPrices: Object.keys(mergedVideoInputPrices).length ? mergedVideoInputPrices : preferred.videoInputPrices,
        qualities: firstList("qualities").length ? firstList("qualities") : qualities,
        aspectRatios: firstList("aspectRatios"),
        counts: firstList("counts"),
        durations: firstList("durations"),
        resolutions: firstList("resolutions"),
        variants: group.variants,
      },
      name: displayName,
      creditsLabel: minCredits === maxCredits ? formatNumber(minCredits) : `${formatNumber(minCredits)}-${formatNumber(maxCredits)}`,
      chips: [...modes, ...qualities].length ? [...modes, ...qualities] : preferred.capabilities || [group.type],
      subtitle: `${modes.length ? modes.join(" + ") : shortTypeLabel(group.type)} · ${group.variants.length} ${modeCountLabel(group.variants.length)}`,
    };
  });
}

const MODEL_GUIDE_VISUALS = {
  "gpt-image": "images/avatar-neon-orbit-01.png",
  "nano-banana": "images/avatar-neon-orbit-02.png",
  seedream: "images/concepts/aurora-atelier.png",
  grok: "images/hero-cinematic-gallery.png",
  qwen: "images/concepts/model-intelligence-lab.png",
  wan: "images/concepts/pink-blue-runway.png",
  kling: "images/apix-motion-preview.svg",
  veo: "images/hero-cinematic-gallery.png",
  suno: "images/apix-production-flow.svg",
  midjourney: "images/concepts/model-intelligence-lab.png",
  seedance: "images/hero-cinematic-gallery.png",
  "gemini-omni": "images/apix-premium-studio-hero.png",
  happyhorse: "images/hero-cinematic-gallery.png",
  default: "images/concepts/model-intelligence-lab.png",
};

const MODEL_FAMILY_PREVIEWS = {
  "gpt-image": "images/home/home-gpt-image-create.webp",
  "nano-banana": "images/home/home-nano-reference.webp",
  seedream: "images/home/home-seedream-edit.webp",
  grok: "images/home/home-gpt-image-create.webp",
  qwen: "images/home/home-seedream-edit.webp",
  wan: "images/home/home-seedream-edit.webp",
  kling: "images/home/home-kling-video.webp",
  veo: "images/home/home-kling-video.webp",
  suno: "images/home/home-suno-music.webp",
  midjourney: "images/home/home-gpt-image-create.webp",
  seedance: "images/home/home-kling-video.webp",
  "gemini-omni": "images/home/home-gpt-image-create.webp",
  happyhorse: "images/home/home-gpt-image-create.webp",
  default: "images/home/home-gpt-image-create.webp",
};

const MODEL_GUIDES = {
  "gpt-image": {
    title: "Точный визуал по подробному описанию",
    short: "Хороший выбор для рекламных кадров, обложек, предметки и аккуратных правок, когда важны смысл, детали и текст в кадре.",
    bestFor: ["обложки и креативы", "предметная съемка", "баннеры с надписями", "точные правки фото"],
    strengths: ["сильное следование описанию", "уверенная работа с деталями", "хорошо понимает композицию", "подходит для итераций"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Берите эту модель, если результат должен выглядеть собранно: понятный объект, чистый фон, аккуратный свет и минимум случайностей.", points: ["Для текста в кадре пишите короткую фразу отдельно.", "Для рекламы задавайте формат площадки: сторис, карточка товара, баннер.", "Для портретов фиксируйте возраст, одежду, свет и фон."] },
      { key: "prompt", title: "Как писать", body: "Лучше всего работает структура: объект -> действие -> среда -> свет -> стиль -> ограничения.", points: ["Один главный объект на один запрос.", "Добавляйте, что сохранить, а не только что изменить.", "Финально укажите настроение: премиально, спокойно, дерзко, минималистично."] },
      { key: "reference", title: "Фото-пример", body: "Если есть исходное фото, используйте его для сохранения лица, предмета или композиции, а текстом объясните только нужное изменение.", points: ["Не просите сразу 10 правок.", "Сначала фон и свет, потом мелкие элементы.", "Для товара добавляйте материал и масштаб."] },
      { key: "check", title: "Проверка", body: "Перед запуском проверьте, что в описании нет двух конфликтующих стилей и что важный текст написан без ошибок.", points: ["Формат кадра совпадает с площадкой.", "Нужный объект назван первым.", "Нежелательные детали вынесены в конец описания."] },
    ],
    tips: ["Для clean-рекламы добавляйте: soft studio light, clean background, premium product photography.", "Для людей не перегружайте позу и эмоцию: одна эмоция, одно действие.", "Для текста в кадре используйте короткие слова и просите ровную типографику."],
    examples: [
      { title: "Премиальная карточка товара", flow: "text", prompt: "Флакон нишевого парфюма на темном стекле, лилово-розовый контровой свет, капли воды, чистый фон, дорогая предметная съемка, место под короткий заголовок" },
      { title: "Обложка для эксперта", flow: "text", prompt: "Портрет женщины-предпринимателя в темном жакете, мягкий сине-розовый свет, уверенный взгляд, минимальный фон, премиальная обложка для соцсетей" },
      { title: "Правка фото", flow: "edit", prompt: "Сохранить лицо и позу, заменить фон на аккуратную студию, улучшить свет, убрать визуальный шум, оставить естественную кожу" },
    ],
    faq: [
      { q: "Когда брать GPT Image вместо других моделей?", a: "Когда важны точность описания, чистая композиция, понятная реклама или аккуратное редактирование без лишнего хаоса." },
      { q: "Подходит ли для надписей?", a: "Да, но лучше использовать короткий текст, отдельно указать точную фразу и не совмещать ее с десятком других требований." },
      { q: "Как получить более дорогой вид?", a: "Опишите материал, свет, фон и камеру. Например: стекло, сатин, мягкий контровой свет, чистая студия, премиальная предметная съемка." },
      { q: "Что делать, если результат слишком буквальный?", a: "Добавьте настроение и визуальный референс словами: editorial, cinematic, luxury, minimal, social cover." },
    ],
    sources: [{ label: "OpenAI: image generation", url: "https://developers.openai.com/api/docs/guides/image-generation" }],
  },
  "nano-banana": {
    title: "Стабильные персонажи и быстрые вариации",
    short: "Подходит для серий изображений с одним человеком, товаром или стилем: сменить фон, одежду, ракурс и сохранить узнаваемость.",
    bestFor: ["серии с одним героем", "фото по референсу", "быстрые соцсети", "продуктовые вариации"],
    strengths: ["сохраняет важные детали", "хорошо меняет окружение", "понятен новичкам", "быстро дает несколько направлений"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Выбирайте Nano Banana, если есть исходный герой или товар и нужно быстро получить новые сцены без потери узнаваемости.", points: ["Один референс лучше, чем коллаж из случайных фото.", "Для серии фиксируйте одинаковый стиль света.", "Для Pro-режима просите больше контроля и чистоты."] },
      { key: "prompt", title: "Как писать", body: "Формулируйте правку как задачу фотографу: что оставить, что поменять, где будет сцена и какой должен быть свет.", points: ["Начинайте с 'сохранить лицо/товар/форму'.", "Задавайте новую среду коротко.", "Не смешивайте реализм, 3D и иллюстрацию в одном запуске."] },
      { key: "reference", title: "Фото-пример", body: "Для сохранения персонажа используйте фото с чистым лицом и хорошим светом. Для товара — кадр без сильных бликов и перекрытий.", points: ["Фон можно менять смело.", "Поза меняется лучше, если исходник не слишком сложный.", "Для серии используйте одинаковые слова про стиль."] },
      { key: "check", title: "Проверка", body: "Проверьте, что запрос просит сохранить только важное. Чем больше 'сохранить все', тем меньше свободы у модели.", points: ["Лицо или товар назван первым.", "Новая сцена понятна.", "Стиль не конфликтует с референсом."] },
    ],
    tips: ["Для персонажа добавляйте: same face, same identity, natural skin texture.", "Для fashion-съемки фиксируйте материал одежды и свет.", "Если нужна серия, копируйте одну и ту же финальную строку стиля."],
    examples: [
      { title: "Единый герой в новой локации", flow: "reference", prompt: "Сохранить лицо и прическу с фото, перенести героя в вечерний rooftop lounge, лилово-синий свет, fashion editorial, естественная кожа" },
      { title: "Товар в кампейне", flow: "reference", prompt: "Сохранить форму и логотип продукта, поставить на глянцевую поверхность, добавить мягкие розовые отражения, премиальная рекламная съемка" },
      { title: "Быстрая соцсеть", flow: "text", prompt: "Стильный lifestyle-портрет для Reels cover, мягкая улыбка, неоновый вечерний город, розово-синий свет, чистая композиция" },
    ],
    faq: [
      { q: "Зачем выбирать Nano Banana Pro?", a: "Когда нужен более чистый результат, лучшее сохранение объекта и меньше случайных изменений при работе по фото." },
      { q: "Можно ли делать серию с одним персонажем?", a: "Да. Используйте один качественный референс и повторяйте одинаковые слова про лицо, свет и стиль." },
      { q: "Что чаще портит результат?", a: "Слишком много референсов без ясной роли: лицо из одного, одежда из второго, фон из третьего. Лучше описать роли прямо." },
      { q: "Подходит ли для товаров?", a: "Да, особенно для смены окружения, фона и визуального настроения при сохранении формы товара." },
    ],
    sources: [{ label: "Google Gemini image generation", url: "https://gemini.google/mp/overview/image-generation/?hl=en-GB" }],
  },
  seedream: {
    title: "Реализм, детали и сильная универсальность",
    short: "Универсальный режим для реалистичных фото, предметки, интерьеров и редактирования, где нужно совместить качество, скорость и аккуратность.",
    bestFor: ["реалистичные фото", "интерьеры", "предметная съемка", "обучающие иллюстрации"],
    strengths: ["генерация и правки в одном стиле", "высокая детализация", "сильная консистентность", "хорошо держит визуальную чистоту"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Seedream стоит брать как первый надежный вариант для реалистичной картинки: люди, товары, интерьер, сложный свет.", points: ["Для 4K просите меньше объектов и больше качества.", "Для интерьера задавайте материалы.", "Для правки фото описывайте одну главную цель."] },
      { key: "prompt", title: "Как писать", body: "Пишите как арт-директор: сцена, камера, свет, материал, настроение, финальное применение.", points: ["Материалы: стекло, металл, кожа, ткань.", "Свет: мягкий, контровой, дневной, студийный.", "Применение: карточка, постер, обложка, презентация."] },
      { key: "reference", title: "Фото-пример", body: "В редактировании Seedream хорошо держит исходный объект, если запрос не ломает геометрию кадра.", points: ["Для мебели сохраняйте форму и пропорции.", "Для портрета просите естественную кожу.", "Для товара не меняйте логотип без необходимости."] },
      { key: "check", title: "Проверка", body: "Перед запуском уберите лишние стили и оставьте один визуальный язык.", points: ["Один источник света.", "Один главный объект.", "Четкий формат кадра."] },
    ],
    tips: ["Для реализма добавляйте: real photography, natural imperfections, believable materials.", "Для интерьера пишите 'не перегружать декором'.", "Для образовательных картинок просите чистые подписи и понятную композицию."],
    examples: [
      { title: "Интерьер премиум-студии", flow: "text", prompt: "Современная творческая студия с темными стенами, лилово-синие акценты, мягкий дневной свет, дорогие материалы, реалистичная интерьерная фотография" },
      { title: "Рекламный beauty-кадр", flow: "text", prompt: "Косметический продукт на зеркальной поверхности, розовый гель-свет, капли воды, чистый фон, премиальная beauty-съемка, ultra realistic" },
      { title: "Улучшение исходника", flow: "edit", prompt: "Сохранить объект и ракурс, улучшить освещение, сделать фон чище, добавить премиальный розово-синий цветовой акцент" },
    ],
    faq: [
      { q: "Seedream лучше для генерации или редактирования?", a: "Он хорош в обоих сценариях: можно начать с нуля или аккуратно улучшить уже готовое фото." },
      { q: "Когда включать высокое качество?", a: "Когда результат нужен для карточки товара, портфолио, печати или важного первого экрана." },
      { q: "Как избежать пластиковой картинки?", a: "Добавьте естественные детали: slight imperfections, natural skin texture, realistic reflections, believable shadows." },
      { q: "Можно ли делать сложные сцены?", a: "Да, но лучше идти по шагам: сначала главная сцена, потом отдельная правка деталей." },
    ],
    sources: [{ label: "ByteDance Seedream", url: "https://seed.bytedance.com/en/blog/seedream-4-0-officially-released-beyond-drawing-into-imagination" }],
  },
  grok: {
    title: "Быстрые идеи, яркий стиль и движение",
    short: "Хорош для быстрых визуальных гипотез, мемных и social-first сцен, а также для роликов из текста или фото.",
    bestFor: ["соцсети", "быстрые концепты", "яркие персонажи", "короткие видео"],
    strengths: ["быстро дает вариации", "поддерживает image и video сценарии", "может оживлять фото", "хорош для смелых идей"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Grok Imagine уместен, когда нужна энергия, скорость и несколько смелых направлений для контента.", points: ["Для бренда задавайте границы стиля.", "Для видео описывайте действие, а не только внешний вид.", "Для фото-примера укажите, что должно сохраниться."] },
      { key: "prompt", title: "Как писать", body: "Используйте короткую драматургию: кто в кадре, что делает, что меняется, какая эмоция.", points: ["Одна сцена за запуск.", "Для видео: действие + движение камеры.", "Для изображения: стиль + свет + формат публикации."] },
      { key: "reference", title: "Фото-пример", body: "При работе по фото просите одну понятную трансформацию: стиль, фон, настроение или движение.", points: ["Для анимации исходник должен быть читаемым.", "Лучше статичный объект на чистом фоне.", "Не просите сложную хореографию из одного фото."] },
      { key: "check", title: "Проверка", body: "Проверьте, что промпт не конфликтует с выбранным режимом: картинке нужен кадр, видео — действие.", points: ["Указан формат.", "Указана эмоция.", "Указано движение для видео."] },
    ],
    tips: ["Для видео используйте глаголы: поворачивается, приближается, вспыхивает, камера отъезжает.", "Для social-креатива добавляйте bold composition и clear focal point.", "Если стиль слишком шумный, просите clean premium editorial."],
    examples: [
      { title: "Динамичный постер", flow: "text", prompt: "Яркий fashion-постер: модель в глянцевом розовом плаще, ночной город, синий неон, сильная поза, clean premium editorial" },
      { title: "Оживить фото", flow: "reference", prompt: "Сохранить героя из фото, добавить легкое движение волос и мягкий поворот камеры, вечерний неоновый свет, короткий cinematic clip" },
      { title: "Быстрый мем-креатив", flow: "text", prompt: "Сюрреалистичный рекламный кадр для соцсетей: огромный смартфон как арт-объект в центре города, яркий свет, веселое настроение" },
    ],
    faq: [
      { q: "Для чего Grok лучше всего?", a: "Для быстрых визуальных идей, ярких social-креативов и коротких роликов, где важна энергия." },
      { q: "Как писать для видео?", a: "Опишите действие и движение камеры: кто движется, куда смотрит, как меняется сцена." },
      { q: "Можно ли использовать фото?", a: "Да. Фото помогает сохранить героя или объект, а промпт задает новую сцену или движение." },
      { q: "Как сделать результат менее хаотичным?", a: "Добавьте clear focal point, clean background и ограничьте сцену одним главным действием." },
    ],
    sources: [{ label: "xAI Imagine", url: "https://docs.x.ai/developers/model-capabilities/imagine" }],
  },
  qwen: {
    title: "Текст, вывески и точные правки",
    short: "Подходит для задач, где в изображении есть надписи, интерфейсы, упаковка, постеры или нужно аккуратно заменить текст.",
    bestFor: ["постеры с текстом", "упаковка", "вывески", "точечные правки"],
    strengths: ["сильнее держит текст", "подходит для semantic edits", "хорошо сохраняет стиль исходника", "работает с bilingual-задачами"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Qwen берите, когда текст в кадре важнее декоративности: этикетки, вывески, постеры, надписи на товаре.", points: ["Фразу пишите в кавычках.", "Сразу указывайте язык.", "Для правки текста просите сохранить шрифт и стиль."] },
      { key: "prompt", title: "Как писать", body: "Отделяйте визуальную сцену от точного текста: сначала кадр, потом 'надпись: ...'.", points: ["Короткий текст работает надежнее.", "Не просите много мелких надписей.", "Указывайте место текста: сверху, на упаковке, на вывеске."] },
      { key: "reference", title: "Фото-пример", body: "Для замены надписи используйте исходник, где текст не размыт и не перекрыт объектами.", points: ["Сохраняйте шрифт, размер, цвет.", "Меняйте одну надпись за запуск.", "После правки проверяйте каждую букву."] },
      { key: "check", title: "Проверка", body: "Главная проверка Qwen — буквальная: нет ли опечаток в промпте и не слишком ли длинная фраза.", points: ["Фраза написана точно.", "Язык указан.", "Одна надпись — одна задача."] },
    ],
    tips: ["Для этикеток добавляйте: preserve font, preserve label layout.", "Для постера просите large readable typography.", "Для русского текста держите фразу короткой и без сложной пунктуации."],
    examples: [
      { title: "Постер с надписью", flow: "text", prompt: "Минималистичный постер для AI-студии, темный фон, розово-синий свет, крупная читаемая надпись: \"Создайте идею\", премиальная типографика" },
      { title: "Замена текста на упаковке", flow: "edit", prompt: "Сохранить упаковку, материал и свет, заменить надпись на этикетке на \"APIX Studio\", сохранить стиль шрифта и расположение" },
      { title: "Вывеска", flow: "text", prompt: "Ночная улица с премиальной стеклянной вывеской, текст на вывеске: \"APIX\", синий неон, влажный асфальт, реалистичная фотография" },
    ],
    faq: [
      { q: "Почему Qwen выбирать для текста?", a: "Эта линейка сильнее заточена под точный рендеринг и редактирование текста в изображении." },
      { q: "Можно ли менять надписи на фото?", a: "Да. Лучше менять одну надпись за раз и просить сохранить исходный шрифт, цвет и размер." },
      { q: "Что делать с длинным текстом?", a: "Разбейте задачу: сначала ключевой заголовок, потом отдельный запуск для мелких подписей." },
      { q: "Подходит ли для обычных фото?", a: "Да, но максимальная выгода Qwen проявляется там, где есть типографика, вывески и элементы дизайна." },
    ],
    sources: [{ label: "Qwen Image Edit", url: "https://qwenlm.github.io/blog/qwen-image-edit/" }],
  },
  wan: {
    title: "Массовые варианты и движение",
    short: "Практичный выбор для серий изображений, персонажей, а также видео из текста или фото, когда нужны варианты и контролируемая сцена.",
    bestFor: ["несколько вариантов", "персонажи", "image-to-video", "быстрые тесты кампейна"],
    strengths: ["поддерживает текст и фото", "можно делать несколько вариантов", "хорош для motion-сцен", "гибкие форматы кадра"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "WAN удобен, когда нужно быстро сравнить несколько направлений или оживить визуал без сложного продакшена.", points: ["Для изображений используйте 2 или 4 варианта.", "Для видео держите одно действие.", "Для персонажа фиксируйте одежду и ракурс."] },
      { key: "prompt", title: "Как писать", body: "Для WAN хорошо работает простая режиссура: сцена, герой, действие, свет, камера.", points: ["Не перегружайте фон.", "Для движения используйте один глагол.", "Для вариантов оставляйте пространство для интерпретации."] },
      { key: "reference", title: "Фото-пример", body: "Фото задает основу, промпт добавляет движение или новый стиль. Чем чище исходник, тем лучше итог.", points: ["Первый кадр должен быть резким.", "Не просите радикально менять форму объекта.", "Для товара лучше статичная камера."] },
      { key: "check", title: "Проверка", body: "Сравнивайте варианты по цели: кликабельность, реализм, узнаваемость, чистота фона.", points: ["Выбран нужный формат.", "Понятно главное действие.", "Не слишком много объектов."] },
    ],
    tips: ["Для серии добавляйте count 2 или 4, если доступно.", "Для видео: slow camera push-in часто дает более чистый результат.", "Для персонажей просите consistent outfit and face."],
    examples: [
      { title: "Серия рекламных вариантов", flow: "text", prompt: "Четыре варианта fashion-кадра для кампейна: модель в черном костюме, розово-синий свет, чистый фон, premium editorial, разные ракурсы" },
      { title: "Оживить продукт", flow: "reference", prompt: "Сохранить продукт из фото, медленный наезд камеры, мягкие отражения, премиальный темный фон, cinematic product video" },
      { title: "Персонаж", flow: "text", prompt: "Фантазийный герой в лаконичном костюме, реалистичная кожа, синий контровой свет, выразительный портрет, clean composition" },
    ],
    faq: [
      { q: "WAN лучше для фото или видео?", a: "Он полезен в обоих случаях: для картинок хороши варианты, для видео — простые сцены из текста или фото." },
      { q: "Как получить меньше артефактов в видео?", a: "Описывайте одно действие и мягкое движение камеры. Чем сложнее сцена, тем выше риск лишних деталей." },
      { q: "Когда выбирать Pro?", a: "Когда нужна более выразительная картинка, выше качество или важный коммерческий результат." },
      { q: "Можно ли использовать несколько референсов?", a: "Если режим поддерживает несколько фото, задайте роль каждому: лицо, одежда, фон, стиль." },
    ],
    sources: [{ label: "Wan Video", url: "https://github.com/Wan-Video/Wan2.2" }],
  },
  kling: {
    title: "Кинематографичное видео и контроль движения",
    short: "Для роликов из текста или фото, где важны плавное движение, камера, кадрирование и профессиональный video-look.",
    bestFor: ["короткие ролики", "image-to-video", "движение камеры", "motion control"],
    strengths: ["сильная видеоподача", "много длительностей", "поддерживает разные размеры", "есть motion-сценарии"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Kling выбирайте для роликов, где кадр должен ощущаться как снятый камерой: движение, глубина, свет и драматургия.", points: ["Для фото оживления берите понятный первый кадр.", "Для motion control держите действие ясным.", "Для 4K избегайте перегруженных сцен."] },
      { key: "prompt", title: "Как писать", body: "Видео-промпт должен быть не описанием картинки, а мини-сценой: кто, что делает, как движется камера, как меняется свет.", points: ["Добавляйте camera push-in, pan, handheld или dolly.", "Указывайте длительность под действие.", "Не ставьте несколько независимых действий."] },
      { key: "reference", title: "Фото-пример", body: "Первый кадр определяет композицию. Если в фото много мелких объектов, модель может оживить лишнее.", points: ["Главный объект должен быть крупным.", "Фон лучше чистый.", "Для людей избегайте перекрытых рук и лица."] },
      { key: "check", title: "Проверка", body: "Проверьте, что в запросе есть движение. Без него видео может быть красивым, но слишком статичным.", points: ["Есть действие.", "Есть движение камеры.", "Есть настроение света."] },
    ],
    tips: ["Для premium-ролика используйте slow dolly-in, soft cinematic lighting.", "Для человека задавайте small natural movement вместо сложной хореографии.", "Для товара хорошо работает rotating product on glossy surface."],
    examples: [
      { title: "Кинематографичный продукт", flow: "text", prompt: "Премиальный ролик: флакон парфюма медленно вращается на черном стекле, розовые и синие отражения, slow dolly-in, мягкий дым, cinematic product film" },
      { title: "Оживление портрета", flow: "reference", prompt: "Сохранить портрет, легкое движение волос, медленный поворот головы, мягкий неоновый свет, camera push-in, fashion editorial video" },
      { title: "Motion-сцена", flow: "text", prompt: "Спортивный автомобиль проезжает по мокрой ночной улице, синий неон, отражения на асфальте, низкая камера, плавный tracking shot" },
    ],
    faq: [
      { q: "Что важнее всего в промпте для Kling?", a: "Действие и камера. Если описать только внешний вид, ролик может получиться статичным." },
      { q: "Когда брать Motion?", a: "Когда нужно управлять характером движения или перенести движение на объект/персонажа." },
      { q: "Какой формат выбрать?", a: "9:16 для Reels/TikTok, 16:9 для YouTube и презентаций, 1:1 для универсальных social-карточек." },
      { q: "Как уменьшить риск деформаций?", a: "Используйте чистый первый кадр, одно действие и не просите сложную смену позы." },
    ],
    sources: [{ label: "Kling video models", url: "https://kling.ai/document-api/apiReference%2Fmodel%2FvideoModels" }],
  },
  veo: {
    title: "Реалистичное видео с сильной сценой",
    short: "Для коротких роликов, где важны реализм, натуральное движение, кадр и аккуратный visual storytelling.",
    bestFor: ["реалистичные ролики", "брендовые сцены", "image-to-video", "атмосферные клипы"],
    strengths: ["видео из текста или фото", "поддержка референсов", "хороший реализм", "подходит для storytelling"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Veo берите, когда ролик должен выглядеть максимально естественно: lifestyle, брендовая сцена, объект в среде.", points: ["Для людей описывайте естественное действие.", "Для бренда задавайте цвет и тон.", "Для фото-примера не меняйте резко композицию."] },
      { key: "prompt", title: "Как писать", body: "Пишите как краткий режиссерский бриф: сцена, герой, действие, камера, свет, настроение.", points: ["Один эпизод на один ролик.", "Камера должна помогать действию.", "Добавляйте ambient light, natural motion, realistic details."] },
      { key: "reference", title: "Фото-пример", body: "Референсы помогают удержать объект, стиль или первый кадр. Лучше использовать до трех сильных, а не много похожих.", points: ["Один референс на героя.", "Один на стиль, если нужно.", "Не смешивайте противоречивые эпохи и локации."] },
      { key: "check", title: "Проверка", body: "Проверьте, что ролик можно представить за 5-15 секунд. Если сцена требует минуты, разбейте ее на эпизоды.", points: ["Понятен старт.", "Понятно движение.", "Понятен финальный кадр."] },
    ],
    tips: ["Для realism добавляйте natural camera movement, believable physics.", "Для рекламы указывайте hero product shot в конце.", "Для человека используйте subtle gesture, smile, glance вместо резких движений."],
    examples: [
      { title: "Lifestyle-реклама", flow: "text", prompt: "Короткий реалистичный ролик: девушка входит в светлую студию, берет чашку кофе, мягкий утренний свет, slow handheld camera, premium lifestyle ad" },
      { title: "Оживить фото товара", flow: "reference", prompt: "Сохранить товар как главный объект, мягкий наезд камеры, реалистичные отражения, финальный hero shot, атмосферный брендовый ролик" },
      { title: "Атмосферный клип", flow: "text", prompt: "Ночной город после дождя, человек идет под синим неоном, розовые отражения, плавная камера сзади, cinematic realistic video" },
    ],
    faq: [
      { q: "Чем Veo отличается от Kling?", a: "Veo чаще выбирают для естественного реализма и storytelling, Kling — когда нужен более выраженный контроль motion и cinematic-динамика." },
      { q: "Сколько референсов использовать?", a: "Лучше 1-3: герой, объект или стиль. Слишком много референсов делает задачу менее ясной." },
      { q: "Как получить реалистичное движение?", a: "Просите маленькое натуральное действие и понятную камеру, а не сложный монтаж внутри одного ролика." },
      { q: "Что делать, если ролик выглядит слишком постановочным?", a: "Добавьте natural imperfections, handheld camera, ambient light и меньше декоративных слов." },
    ],
    sources: [{ label: "Google Veo on Vertex AI", url: "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation?hl=en" }],
  },
  suno: {
    title: "Музыка под ролики, бренды и атмосферу",
    short: "Создает треки по описанию: жанр, настроение, темп, вокал или инструментальная версия для видео и презентаций.",
    bestFor: ["саундтрек для ролика", "джингл", "фон для презентации", "вокальные демо"],
    strengths: ["богаче вокалы", "точнее жанры", "динамичная аранжировка", "можно описывать эмоцию"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Suno нужен, когда визуалу не хватает звука: рекламный ролик, заставка, Reels, презентация, moodboard.", points: ["Для видео задавайте длительность ощущения: intro, loop, climax.", "Для бренда задавайте настроение, а не только жанр.", "Инструментал включайте для фоновой музыки."] },
      { key: "prompt", title: "Как писать", body: "Музыкальный промпт: жанр, темп, настроение, инструменты, голос, где будет использоваться трек.", points: ["Пример: synth-pop, 105 bpm, glossy, female vocal.", "Для фона пишите no lead vocal.", "Для рекламы добавьте memorable hook."] },
      { key: "reference", title: "Сценарий", body: "Для сайта важна не ссылка на фото, а смысл ролика: что зритель должен почувствовать за первые секунды.", points: ["Опишите аудиторию.", "Опишите энергию.", "Укажите, нужен ли вокал."] },
      { key: "check", title: "Проверка", body: "Проверьте, что жанр не конфликтует с настроением: например, dark ambient и веселый pop hook лучше разделить.", points: ["Есть темп.", "Есть настроение.", "Есть инструменты или вокал."] },
    ],
    tips: ["Для премиального фона: cinematic electronic, soft pulse, warm pads, no vocals.", "Для короткого ролика просите strong intro in first 5 seconds.", "Для бренда фиксируйте 2-3 прилагательных: sleek, confident, futuristic."],
    examples: [
      { title: "Фон для premium video", flow: "text", prompt: "Cinematic electronic instrumental, 96 bpm, soft pulsing bass, airy pads, glossy futuristic mood, premium tech brand, no vocals" },
      { title: "Reels-трек", flow: "text", prompt: "Energetic synth-pop track, 120 bpm, bright hook in first 5 seconds, stylish female vocal, night city mood, polished production" },
      { title: "Презентация", flow: "text", prompt: "Minimal ambient corporate music, calm confident mood, soft piano, warm synth texture, no drums, seamless background for product presentation" },
    ],
    faq: [
      { q: "Как получить инструментальный трек?", a: "Включите режим инструментальной музыки и в описании добавьте no vocals или instrumental background." },
      { q: "Что важнее: жанр или настроение?", a: "Оба. Жанр задает форму, настроение задает эмоцию. Лучший промпт содержит и то, и другое." },
      { q: "Можно ли сделать музыку под видео?", a: "Да. Опишите визуальную сцену, темп, энергию и момент, где должен быть акцент." },
      { q: "Как сделать трек более премиальным?", a: "Просите polished production, tasteful arrangement, warm low-end, spacious mix и избегайте перегруза инструментами." },
    ],
    sources: [{ label: "Suno v4.5", url: "https://suno.com/blog/introducing-v4-5" }],
  },
  midjourney: {
    title: "Визуальные концепты и арт-дирекшн",
    short: "Для сильной стилистики, moodboard, концептов и смешивания нескольких изображений в новый визуальный язык.",
    bestFor: ["moodboard", "арт-концепт", "style exploration", "blend из фото"],
    strengths: ["выразительная эстетика", "хорош для поиска стиля", "можно смешивать изображения", "подходит для кампейновых направлений"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Midjourney хорош, когда нужно найти визуальный язык: стиль кампейна, настроение, постерность, арт-направление.", points: ["Для точного бренда добавляйте ограничения.", "Для blend используйте схожие по формату фото.", "Для веба сразу задавайте нужное соотношение сторон."] },
      { key: "prompt", title: "Как писать", body: "Пишите коротко и визуально: объект, стиль, материал, камера, свет, настроение.", points: ["Меньше служебных слов.", "Больше визуальных признаков.", "Формат задавайте сразу."] },
      { key: "reference", title: "Blend и референсы", body: "Blend лучше работает, когда исходные изображения похожи по композиции или у каждого есть ясная роль.", points: ["2-5 изображений достаточно.", "Одинаковое соотношение сторон помогает.", "Если нужен текстовый контроль, используйте обычный prompt с image references."] },
      { key: "check", title: "Проверка", body: "Оценивайте не только красоту, а применимость: можно ли из этого сделать баннер, обложку или продуктовый визуал.", points: ["Есть место под текст.", "Стиль не спорит с брендом.", "Композиция читается на мобиле."] },
    ],
    tips: ["Для luxury mood добавляйте editorial lighting, cinematic color grading.", "Для blend берите исходники одного формата.", "Для product moodboard делайте сначала стиль, потом точную карточку в другой модели."],
    examples: [
      { title: "Moodboard кампейна", flow: "text", prompt: "Luxury AI studio campaign moodboard, glossy magenta and electric blue lighting, premium editorial photography, sleek futuristic interface, dark background" },
      { title: "Blend персонажа и стиля", flow: "reference", prompt: "Смешать характер портрета с неоновым fashion editorial стилем, сохранить премиальное настроение, чистая композиция" },
      { title: "Постер", flow: "text", prompt: "Cinematic poster for creative AI studio, dramatic silhouette, pink and blue neon, glass reflections, premium sci-fi editorial look" },
    ],
    faq: [
      { q: "Когда Midjourney лучше других?", a: "Когда нужно быстро найти красивое художественное направление, а не строго повторить техническую спецификацию." },
      { q: "Как работает blend?", a: "Смешивает несколько изображений без текстового промпта; если нужен текстовый контроль, лучше использовать image references в обычном сценарии." },
      { q: "Как выбрать формат?", a: "Под задачу: 9:16 для вертикального контента, 16:9 для обложек и презентаций, 1:1 для карточек." },
      { q: "Что делать после красивого концепта?", a: "Используйте его как референс для более точной генерации или редактирования в Studio." },
    ],
    sources: [
      { label: "Midjourney versions", url: "https://docs.midjourney.com/hc/en-us/articles/32199405667853-Version" },
      { label: "Midjourney blend", url: "https://docs.midjourney.com/hc/en-us/articles/32635189884557-Blend-Images-in-Discord" },
    ],
  },
  seedance: {
    title: "Быстрое видео для широких форматов",
    short: "Для коротких роликов из текста или фото с большим выбором длительности и форматов кадра.",
    bestFor: ["быстрые ролики", "адаптивные форматы", "соцсети", "варианты видео"],
    strengths: ["много форматов", "поддержка фото", "разные длительности", "есть быстрый режим"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Seedance удобен для контента, который нужно адаптировать под разные площадки.", points: ["Fast — для быстрых тестов.", "Обычный режим — для важного результата.", "Adaptive формат — когда не уверены в кадре."] },
      { key: "prompt", title: "Как писать", body: "Опишите первую секунду, основное движение и финальное ощущение.", points: ["Одна сцена.", "Плавная камера.", "Четкое настроение."] },
      { key: "reference", title: "Фото-пример", body: "Фото задает героя или объект, промпт задает движение и атмосферу.", points: ["Лучше резкий первый кадр.", "Не перегружайте фон.", "Сохраняйте один главный объект."] },
      { key: "check", title: "Проверка", body: "Перед запуском выберите площадку: вертикаль, горизонталь или квадрат.", points: ["Формат выбран.", "Длительность хватает действию.", "Нет лишних сцен."] },
    ],
    tips: ["Для Reels используйте 9:16 и короткое действие.", "Для презентации берите 16:9 и более спокойную камеру.", "Для теста идеи начните с fast-режима."],
    examples: [
      { title: "Вертикальный ролик", flow: "text", prompt: "Вертикальный fashion-ролик 9:16, модель идет через неоновый коридор, розово-синий свет, плавная камера, premium social ad" },
      { title: "Оживить фото", flow: "reference", prompt: "Сохранить объект из фото, добавить мягкий camera push-in, световые блики, короткий премиальный ролик для сторис" },
      { title: "Широкий баннер", flow: "text", prompt: "16:9 cinematic product reveal, темный фон, стеклянные отражения, медленное появление продукта, футуристичная музыка подразумевается" },
    ],
    faq: [
      { q: "Когда брать Fast?", a: "Когда нужно быстро проверить идею, формат или движение до финального запуска." },
      { q: "Какой формат выбрать для соцсетей?", a: "Обычно 9:16 для Reels/TikTok, 1:1 для универсальной ленты, 16:9 для презентаций и YouTube." },
      { q: "Нужен ли референс?", a: "Для сохранения конкретного героя или товара — да. Для свободной сцены достаточно текста." },
      { q: "Как описать движение?", a: "Одним глаголом и одной камерой: идет + camera follows, продукт вращается + slow push-in." },
    ],
    sources: [{ label: "ByteDance Seedream family", url: "https://seed.bytedance.com/en/blog/seedream-4-0-officially-released-beyond-drawing-into-imagination" }],
  },
  "gemini-omni": {
    title: "Мультимодальное видео с персонажами",
    short: "Для сложных роликов, где важны персонажи, референсы, видео-вход и больше контроля над материалами.",
    bestFor: ["персонажи", "референсные видео", "сложные сцены", "брендовые серии"],
    strengths: ["работает с несколькими типами входа", "поддерживает персонажей", "гибкие размеры", "хорош для серии роликов"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Gemini Omni стоит брать, если обычного text-to-video мало: нужен персонаж, видео-референс или более сложная сцена.", points: ["Сначала соберите референсы.", "Опишите роль каждого файла.", "Не смешивайте слишком много действий."] },
      { key: "prompt", title: "Как писать", body: "Структура: персонаж, действие, окружение, камера, что сохранить, что изменить.", points: ["Фиксируйте identity.", "Пишите короткий эпизод.", "Разделяйте визуал и движение."] },
      { key: "reference", title: "Референсы", body: "Референсы работают лучше, когда у каждого понятная функция: лицо, стиль, движение, объект.", points: ["Не дублируйте одинаковые фото.", "Выбирайте самый чистый референс.", "Сохраняйте роли в тексте."] },
      { key: "check", title: "Проверка", body: "Проверьте, что модель не должна одновременно менять лицо, одежду, фон, движение и стиль.", points: ["Приоритеты расставлены.", "Персонаж описан.", "Сцена помещается в выбранную длительность."] },
    ],
    tips: ["Для персонажа повторяйте same identity, same facial features.", "Для video input просите переносить движение, а не весь визуальный шум.", "Для серии роликов держите единый шаблон промпта."],
    examples: [
      { title: "Серия с персонажем", flow: "reference", prompt: "Сохранить персонажа из референса, новая сцена в футуристичной студии, спокойная уверенная мимика, мягкий розово-синий свет, плавный camera push-in" },
      { title: "Движение из видео", flow: "reference", prompt: "Перенести характер движения из видео-референса на героя, сохранить лицо и стиль одежды, чистый премиальный фон" },
      { title: "Брендовый эпизод", flow: "text", prompt: "Короткий ролик с постоянным AI-ассистентом бренда, темная студия, световые панели, уверенная подача, cinematic tech commercial" },
    ],
    faq: [
      { q: "Когда нужен Omni-сценарий?", a: "Когда задача сложнее обычного ролика: персонажи, несколько референсов, видео-вход или серия связанных сцен." },
      { q: "Как не перегрузить модель?", a: "Назначьте каждому референсу одну роль и оставьте одно главное действие в ролике." },
      { q: "Можно ли делать серию с одним героем?", a: "Да, но используйте стабильный референс и одинаковые слова про внешность в каждом запуске." },
      { q: "Что важнее: фото или текст?", a: "Фото держит визуальную основу, текст объясняет намерение. Хороший результат требует обоих." },
    ],
    sources: [{ label: "Google Veo reference workflow", url: "https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation?hl=en" }],
  },
  happyhorse: {
    title: "Практичные видео для быстрых кампейнов",
    short: "Для понятных коротких роликов из текста или фото: продукт, персонаж, движение, соцсети.",
    bestFor: ["быстрые видео", "товарные сцены", "соцсети", "тесты motion"],
    strengths: ["простая постановка", "текст и фото", "разные длительности", "подходит для черновиков"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "HappyHorse берите для быстрых тестов ролика, когда важна понятная сцена и не нужен сложный motion-control.", points: ["Один объект.", "Одна камера.", "Одна эмоция."] },
      { key: "prompt", title: "Как писать", body: "Коротко опишите кадр, действие и свет. Чем проще сцена, тем чище видео.", points: ["Добавьте площадку: Reels, ad, banner.", "Пишите slow movement.", "Убирайте лишний декор."] },
      { key: "reference", title: "Фото-пример", body: "Используйте фото как первый кадр или основу объекта.", points: ["Резкий объект.", "Чистый фон.", "Понятная поза."] },
      { key: "check", title: "Проверка", body: "Проверьте, что действие реально помещается в выбранную длительность.", points: ["Длительность выбрана.", "Движение описано.", "Формат подходит площадке."] },
    ],
    tips: ["Для товара используйте slow rotating product.", "Для героя — subtle head turn and natural smile.", "Для соцсетей — clear focal point and bold light."],
    examples: [
      { title: "Товарный тест", flow: "text", prompt: "Короткий ролик товара на темном стекле, продукт медленно вращается, розово-синие отражения, clean premium ad" },
      { title: "Фото в движение", flow: "reference", prompt: "Сохранить объект из фото, добавить медленный camera push-in и мягкий световой блик, короткий social video" },
      { title: "Герой бренда", flow: "text", prompt: "Персонаж смотрит в камеру, легкая улыбка, темная студия, синий контровой свет, плавное приближение камеры" },
    ],
    faq: [
      { q: "Для чего HappyHorse?", a: "Для быстрых и понятных видеосцен, когда нужно протестировать идею без долгой подготовки." },
      { q: "Какой промпт лучше?", a: "Одна сцена, один главный объект, одно движение камеры." },
      { q: "Нужен ли референс?", a: "Если важен конкретный объект или герой — да. Для свободного концепта достаточно текста." },
      { q: "Как сделать результат дороже?", a: "Добавьте clean background, premium lighting, glossy reflections и уберите лишние элементы." },
    ],
    sources: [],
  },
  default: {
    title: "Практичный режим для создания контента",
    short: "Используйте эту модель, когда ее формат совпадает с задачей: картинка, видео или музыка.",
    bestFor: ["быстрый старт", "проверка идеи", "варианты", "готовый контент"],
    strengths: ["доступна в Studio", "работает с пресетами", "подходит для теста", "цена считается перед запуском"],
    lessons: [
      { key: "choose", title: "Когда выбирать", body: "Выбирайте модель по конечному результату: фото, видео или музыка. Если сомневаетесь, начните с короткого теста.", points: ["Одна задача на запуск.", "Понятный формат.", "Короткий промпт без конфликтов."] },
      { key: "prompt", title: "Как писать", body: "Опишите цель, объект, настроение и применение результата.", points: ["Для фото — свет и композиция.", "Для видео — действие и камера.", "Для музыки — жанр и эмоция."] },
      { key: "reference", title: "Примеры", body: "Референс нужен, если важно сохранить лицо, товар, стиль или композицию.", points: ["Референс должен быть чистым.", "Роль референса пишите словами.", "Не смешивайте лишнее."] },
      { key: "check", title: "Проверка", body: "Перед запуском проверьте стоимость, формат и описание.", points: ["Цель понятна.", "Формат выбран.", "Баланс готов."] },
    ],
    tips: ["Начинайте с простого теста.", "Сохраняйте удачные промпты в идеях.", "Используйте ленту как источник референсов."],
    examples: [
      { title: "Быстрый старт", flow: "text", prompt: "Премиальный визуал для соцсетей, главный объект в центре, лилово-синий свет, чистый фон, выразительная композиция" },
      { title: "По референсу", flow: "reference", prompt: "Сохранить характер примера, улучшить свет, фон и премиальную подачу, сделать результат чище и современнее" },
      { title: "Видео", flow: "text", prompt: "Короткий ролик с одним главным объектом, плавное движение камеры, мягкий свет, премиальное настроение" },
    ],
    faq: [
      { q: "С чего начать?", a: "Выберите формат результата и откройте боевой тест. Studio подставит модель и пример промпта." },
      { q: "Как понять стоимость?", a: "Стоимость динамически считается в Studio после выбора модели, качества, длительности и количества." },
      { q: "Можно ли использовать референс?", a: "Да, если выбранный режим поддерживает фото или видео-пример." },
      { q: "Где смотреть результат?", a: "После подтверждения задача появится в очереди и затем в библиотеке кабинета." },
    ],
    sources: [],
  },
};

function normalizeExample(item, index = 0) {
  const resultUrls = [...new Set([
    ...(Array.isArray(item.result_urls) ? item.result_urls : []),
    item.result_url,
    item.image,
  ].filter(Boolean))];
  const previewUrls = [...new Set([
    ...(Array.isArray(item.preview_urls) ? item.preview_urls : []),
    item.preview_url,
    item.image_preview,
    ...resultUrls,
  ].filter(Boolean))];
  const image = resultUrls[0] || "";
  const preview = previewUrls[0] || image;
  const type = item.type || item.gen_type || "image";
  return {
    id: item.id || index,
    type,
    model: item.model || "api-model",
    author: item.author || "",
    likes: Number(item.likes ?? item.likes_count ?? 0),
    likesCount: Number(item.likes ?? item.likes_count ?? 0),
    shares: Number(item.shares ?? item.shares_count ?? 0),
    sharesCount: Number(item.shares ?? item.shares_count ?? 0),
    remixCount: Number(item.remix_count || item.remixes || 0),
    image,
    preview,
    resultUrls,
    previewUrls,
    title: item.title || cleanModelName(item.model || "Готовая работа") || `Работа ${index + 1}`,
    prompt: String(item.prompt || item.prompt_text || "").replace(/\s+/g, " ").trim().slice(0, 240),
    status: item.status || "done",
    credits: Number(item.credits_spent || 0),
    isPublicFeed: Boolean(item.is_public_feed),
    isPromptLibrary: Boolean(item.is_prompt_library),
    promptActionsAllowed: item.prompt_actions_allowed ?? true,
    imageSessionId: item.image_session_id || item.imageSessionId || null,
    parentGenerationId: item.parent_generation_id || item.parentGenerationId || null,
    sourceFeedGenId: item.source_feed_gen_id || item.sourceFeedGenId || null,
    actionType: item.action_type || item.actionType || "",
    referenceUrl: item.reference_url || item.referenceUrl || "",
    referenceUrls: [...new Set([
      ...(Array.isArray(item.reference_urls) ? item.reference_urls : []),
      ...(Array.isArray(item.referenceUrls) ? item.referenceUrls : []),
      item.reference_url,
      item.referenceUrl,
    ].filter(Boolean))],
    sessionLastPrompt: item.session_last_prompt || item.sessionLastPrompt || "",
    sessionLastResultUrl: item.session_last_result_url || item.sessionLastResultUrl || "",
  };
}

function safeUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    const url = new URL(raw, location.origin);
    if (["http:", "https:"].includes(url.protocol)) return raw;
  } catch {}
  return "";
}

function uniqueSafeUrls(values = []) {
  return [...new Set(values.map(safeUrl).filter(Boolean))];
}

function mediaOriginalUrls(item = {}, fallbackIndex = null) {
  const urls = uniqueSafeUrls([
    ...(Array.isArray(item.resultUrls) ? item.resultUrls : []),
    ...(Array.isArray(item.result_urls) ? item.result_urls : []),
    item.resultUrl,
    item.result_url,
    item.image,
  ]);
  if (!urls.length && Number.isInteger(fallbackIndex)) {
    const fallback = safeUrl(fallbackImage(fallbackIndex));
    if (fallback) urls.push(fallback);
  }
  return urls;
}

function mediaPreviewUrls(item = {}) {
  return uniqueSafeUrls([
    ...(Array.isArray(item.previewUrls) ? item.previewUrls : []),
    ...(Array.isArray(item.preview_urls) ? item.preview_urls : []),
    item.previewUrl,
    item.preview,
    item.preview_url,
    item.image_preview,
  ]);
}

function mediaOpenAttrs(urls = [], index = 0) {
  const items = uniqueSafeUrls(urls);
  const activeIndex = Math.min(Math.max(Number(index) || 0, 0), Math.max(items.length - 1, 0));
  const activeUrl = items[activeIndex] || "";
  if (!activeUrl) return "";
  return `data-open-media="${escapeHtml(activeUrl)}" data-open-media-list="${escapeHtml(JSON.stringify(items))}" data-open-media-index="${activeIndex}"`;
}

function recoverFallbackImage(img) {
  if (!(img instanceof HTMLImageElement)) return;
  const fallback = safeUrl(img.dataset.fallbackSrc);
  if (!fallback) return;
  const fallbackHref = new URL(fallback, window.location.href).href;
  if (img.src === fallbackHref) return;
  if (!img.complete || img.naturalWidth <= 1 || img.naturalHeight <= 1) {
    img.src = fallback;
  }
}

function feedCarouselUrls() {
  return uniqueSafeUrls((state.examples || []).flatMap((entry, index) => mediaOriginalUrls(entry, index)));
}

function feedCarouselIndex(item = {}, index = 0, mediaIndex = 0, urls = null) {
  const items = Array.isArray(urls) && urls.length ? urls : feedCarouselUrls();
  const itemUrls = mediaOriginalUrls(item, index);
  const activeUrl = safeUrl(itemUrls[mediaIndex] || itemUrls[0] || "");
  const activeIndex = activeUrl ? items.indexOf(activeUrl) : -1;
  return Math.max(activeIndex, 0);
}

function mediaHtml(item, index = 0, options = {}) {
  const mediaUrls = mediaOriginalUrls(item, index);
  const fullUrl = mediaUrls[0] || "";
  const previewUrls = mediaPreviewUrls(item);
  const previewUrl = previewUrls[0] || fullUrl;
  const url = previewUrl || fullUrl;
  const viewerUrls = Array.isArray(options.openUrls) && options.openUrls.length ? options.openUrls : mediaUrls;
  const viewerIndexFor = (mediaUrl, fallback = 0) => {
    const safeMediaUrl = safeUrl(mediaUrl);
    const mediaIndex = safeMediaUrl ? uniqueSafeUrls(viewerUrls).indexOf(safeMediaUrl) : -1;
    if (mediaIndex >= 0) return mediaIndex;
    return Number.isFinite(Number(options.openIndex)) ? Number(options.openIndex) : fallback;
  };
  if (!url) return "";
  if (item.type === "video" || /\.(mp4|mov|webm)(\?|$)/i.test(fullUrl || url)) {
    return `<video src="${escapeHtml(url)}" controls playsinline preload="metadata"></video>`;
  }
  if (item.type === "music" || /\.(mp3|wav|ogg|m4a)(\?|$)/i.test(fullUrl || url)) {
    return `<audio src="${escapeHtml(fullUrl || url)}" controls></audio>`;
  }
  if (mediaUrls.length > 1) {
    const visible = mediaUrls.slice(0, 4);
    return `
      <figure class="media-mosaic media-mosaic-${visible.length}">
        ${visible.map((mediaUrl, mediaIndex) => {
          const thumb = previewUrls[mediaIndex] || mediaUrl;
          return `<img class="zoomable-media" src="${escapeHtml(thumb)}" loading="lazy" decoding="async" alt="" ${mediaOpenAttrs(viewerUrls, viewerIndexFor(mediaUrl, mediaIndex))}>`;
        }).join("")}
        ${mediaUrls.length > visible.length ? `<span>+${mediaUrls.length - visible.length}</span>` : ""}
      </figure>
    `;
  }
  return `<img class="zoomable-media" src="${escapeHtml(url)}" loading="lazy" decoding="async" alt="" ${mediaOpenAttrs(viewerUrls, viewerIndexFor(fullUrl || url, 0))}>`;
}

function primaryMediaUrl(item = {}) {
  return mediaOriginalUrls(item)[0] || "";
}

function feedItemTitle(item, index = 0) {
  const modelName = cleanModelName(item?.model || "");
  const rawTitle = String(item?.title || "").trim();
  if (rawTitle && (!modelName || rawTitle !== modelName)) return rawTitle;
  return `Работа #${item?.id || index + 1}`;
}

function feedItemLabel(item) {
  const type = String(item?.type || item?.gen_type || "image").toLowerCase();
  if (type === "video") return "Видео";
  if (type === "music" || type === "audio") return "Музыка";
  return "Картинка";
}

function fallbackImage(index = 0) {
  return state.examples[index]?.image || "images/concepts/pink-blue-runway.png";
}

function fallbackPromptImage(prompt = {}, index = 0) {
  const guideKey = modelGuideKey({ key: prompt.model || "" });
  return MODEL_FAMILY_PREVIEWS[guideKey] || fallbackImage(index) || "images/concepts/pink-blue-runway.png";
}

function promptPreviewHtml(prompt = {}, index = 0) {
  const preview = safeUrl(prompt.preview_url);
  const fallback = safeUrl(fallbackPromptImage(prompt, index));
  const src = preview || fallback;
  if (!src) return "";
  return `<img class="prompt-card-image" src="${escapeHtml(src)}" data-fallback-src="${escapeHtml(fallback)}" loading="lazy" decoding="async" alt="" onload="recoverFallbackImage(this)" onerror="recoverFallbackImage(this)">`;
}

function feedCountsHtml(item = {}) {
  return `
    <span>♥ ${formatNumber(item.likesCount ?? item.likes ?? 0)}</span>
    <span>↻ ${formatNumber(item.remixCount || 0)}</span>
    <span>↗ ${formatNumber(item.sharesCount ?? item.shares ?? 0)}</span>
  `;
}

function modelGuideKey(groupOrModel) {
  const variants = groupOrModel?.variants || groupOrModel?.preferred?.variants || [groupOrModel?.preferred || groupOrModel].filter(Boolean);
  const source = [groupOrModel?.key, groupOrModel?.name, ...variants.flatMap((model) => [model?.key, model?.name])]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (source.includes("gpt-image")) return "gpt-image";
  if (source.includes("nano-banana") || source.includes("banana")) return "nano-banana";
  if (source.includes("seedance")) return "seedance";
  if (source.includes("seedream")) return "seedream";
  if (source.includes("grok")) return "grok";
  if (source.includes("qwen")) return "qwen";
  if (source.includes("wan/") || source.includes("wan ")) return "wan";
  if (source.includes("kling")) return "kling";
  if (source.includes("veo")) return "veo";
  if (source.includes("suno")) return "suno";
  if (source.includes("midjourney")) return "midjourney";
  if (source.includes("gemini") || source.includes("omni")) return "gemini-omni";
  if (source.includes("happyhorse")) return "happyhorse";
  return "default";
}

function guideForGroup(group) {
  return MODEL_GUIDES[modelGuideKey(group)] || MODEL_GUIDES.default;
}

function modelDetailHref(group) {
  const key = group?.preferred?.key || group?.variants?.[0]?.key || group?.key || "";
  return `model.html?model=${encodeURIComponent(key)}`;
}

function studioHref(group, prompt = "", flow = "") {
  const model = group?.preferred || group;
  const kind = group?.type || model?.type || "image";
  const params = new URLSearchParams({ type: kind, model: model?.key || "" });
  if (kind === "image") params.set("flow", flow || "text");
  if (prompt) params.set("prompt", prompt);
  return `studio.html?${params.toString()}`;
}

function normalizeToken(value) {
  return String(value || "").toLowerCase().replace(/[^a-zа-я0-9]+/gi, "");
}

function displayOptionLabel(option) {
  const raw = typeof option === "object" ? option.label || option.value : option;
  return cleanModelName(raw).replace(/\s+/g, " ").trim();
}

function uniqueModelValues(values) {
  const seen = new Set();
  return values.map(displayOptionLabel).filter((value) => {
    const key = normalizeToken(value);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function groupCapabilityCards(group) {
  const variants = group?.variants?.length ? group.variants : [group?.preferred].filter(Boolean);
  const modes = uniqueModelValues(group?.chips || variants.flatMap((model) => model.capabilities || model.modes || []))
    .map(capabilityLabel);
  const qualities = uniqueModelValues(variants.flatMap((model) => model.qualities || []));
  const ratios = uniqueModelValues(variants.flatMap((model) => model.aspectRatios || []));
  const durations = uniqueModelValues(variants.flatMap((model) => (model.durations || []).map((value) => `${value} сек`)));
  const resolutions = uniqueModelValues(variants.flatMap((model) => model.resolutions || []));
  const maxRefs = Math.max(0, ...variants.map((model) => Number(model.maxRefs || 0)));
  const cards = [
    ["Сценарии", modes.length ? modes.join(" / ") : shortTypeLabel(group?.type)],
    ["Качество", qualities.length ? qualities.join(" / ") : "Авто"],
    ["Форматы", ratios.length ? ratios.slice(0, 6).join(" / ") : group?.type === "music" ? "Трек" : "Авто"],
  ];
  if (group?.type !== "music") cards.push(["Референсы", maxRefs ? `до ${maxRefs} фото` : "по необходимости"]);
  if (group?.type === "video") cards.push(["Длительность", durations.length ? durations.slice(0, 7).join(" / ") : "Авто"]);
  if (group?.type === "video" && resolutions.length) cards.push(["Размер", resolutions.join(" / ")]);
  return cards;
}

function examplesForGroup(group) {
  const strict = strictExamplesForGroup(group);
  if (strict.length) return strict;
  const byType = state.examples.filter((item) => !item.type || item.type === group?.type);
  return (byType.length ? byType : state.examples).slice(0, 4);
}

function strictExamplesForGroup(group) {
  const variants = group?.variants?.length ? group.variants : [group?.preferred].filter(Boolean);
  const tokens = [group?.name, ...variants.flatMap((model) => [model?.key, model?.name])]
    .map(normalizeToken)
    .filter(Boolean);
  const guideToken = normalizeToken(modelGuideKey(group));
  if (guideToken) tokens.push(guideToken);
  const matched = state.examples.filter((item) => {
    if (item.type && group?.type && item.type !== group.type) return false;
    const value = normalizeToken(`${item.model} ${item.title}`);
    if (!value) return false;
    return tokens.some((token) => value.includes(token) || token.includes(value));
  });
  return matched.slice(0, 4);
}

function findModelGroupFromRoute(groups) {
  const params = new URLSearchParams(location.search);
  const raw = params.get("model") || params.get("key") || "";
  if (!raw) return groups[0] || null;
  const token = normalizeToken(raw);
  return groups.find((group) => {
    const variants = group.variants || [];
    const values = [group.key, group.name, group.preferred?.key, group.preferred?.name, ...variants.flatMap((model) => [model.key, model.name])];
    return values.some((value) => {
      const normalized = normalizeToken(value);
      return normalized === token || normalized.includes(token) || token.includes(normalized);
    });
  }) || groups[0] || null;
}

function renderSourceLinks(sources = []) {
  if (!sources.length) return "";
  return `
    <div class="guide-sources">
      <span>Основано на открытых описаниях модели</span>
      ${sources.map((source) => `<a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.label)}</a>`).join("")}
    </div>
  `;
}

function renderGuidePromptCard(group, item, index) {
  const href = studioHref(group, item.prompt, item.flow || "text");
  return `
    <article class="guide-prompt-card">
      <span>${String(index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.prompt)}</p>
      <div class="guide-card-actions">
        <button type="button" data-copy-guide-prompt="${escapeHtml(item.prompt)}">Скопировать</button>
        <a href="${escapeHtml(href)}">Открыть в Studio</a>
      </div>
    </article>
  `;
}

function renderModelDetail() {
  const root = $("[data-model-detail]");
  if (!root) return;
  const allModels = state.models.length ? state.models : Object.values(state.modelsByKind).flat();
  const groups = groupModels(allModels);
  if (!groups.length) {
    root.innerHTML = `<div class="guide-empty">Загружаем модели и примеры...</div>`;
    return;
  }
  const group = findModelGroupFromRoute(groups);
  const guide = guideForGroup(group);
  const guideKey = modelGuideKey(group);
  const visual = MODEL_GUIDE_VISUALS[guideKey] || MODEL_GUIDE_VISUALS.default;
  const sample = guide.examples?.[0] || MODEL_GUIDES.default.examples[0];
  const liveHref = studioHref(group, sample.prompt, sample.flow || "text");
  const relatedExamples = examplesForGroup(group);
  const quickFacts = groupCapabilityCards(group).slice(0, 4);
  const compactTips = (guide.tips || []).slice(0, 3);
  document.title = `${group.name} — обучение и примеры APIX Studio`;

  root.innerHTML = `
    <section class="model-detail-hero">
      <div class="model-detail-copy">
        <a class="back-link" href="models.html">Все модели</a>
        <p class="eyebrow">${escapeHtml(shortTypeLabel(group.type))}</p>
        <h1>${escapeHtml(group.name)}</h1>
        <p class="lead">${escapeHtml(guide.short)}</p>
        <div class="guide-pill-row">
          ${(guide.bestFor || []).slice(0, 4).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
        </div>
        <div class="model-quick-facts">
          ${quickFacts.map(([label, value]) => `
            <article>
              <span>${escapeHtml(label)}</span>
              <b>${escapeHtml(value)}</b>
            </article>
          `).join("")}
        </div>
        <div class="model-detail-actions">
          <a class="button primary" href="${escapeHtml(liveHref)}">Боевой тест</a>
          <a class="button ghost" href="${escapeHtml(studioHref(group))}">Создать с нуля</a>
        </div>
        <p class="guide-run-note">Studio откроется с выбранной моделью, готовым описанием и проверкой стоимости.</p>
      </div>
      <div class="model-detail-visual">
        <img src="${escapeHtml(relatedExamples[0]?.image || visual || fallbackImage(0))}" alt="${escapeHtml(group.name)} пример результата" />
        <div>
          <span>${escapeHtml(guide.title)}</span>
          <b>${escapeHtml(creditLabel(group.preferred))}</b>
        </div>
      </div>
    </section>

    <section class="model-guide-section model-playbook">
      <div class="section-head split">
        <div>
          <p class="eyebrow">Playbook</p>
          <h2>Первый удачный запуск</h2>
        </div>
        <div class="guide-strengths compact">
          ${(guide.strengths || []).slice(0, 4).map((item) => `<article><span></span><b>${escapeHtml(item)}</b></article>`).join("")}
        </div>
      </div>

      <div class="playbook-grid">
        <div class="lesson-shell" data-model-lessons>
          <div class="lesson-tabs" role="tablist">
            ${(guide.lessons || []).map((lesson, index) => `
              <button type="button" role="tab" data-model-lesson="${escapeHtml(lesson.key)}" aria-selected="${index === 0 ? "true" : "false"}" class="${index === 0 ? "active" : ""}">${escapeHtml(lesson.title)}</button>
            `).join("")}
          </div>
          <div class="lesson-panels">
            ${(guide.lessons || []).map((lesson, index) => `
              <article class="lesson-panel ${index === 0 ? "active" : ""}" data-lesson-panel="${escapeHtml(lesson.key)}">
                <h3>${escapeHtml(lesson.title)}</h3>
                <p>${escapeHtml(lesson.body)}</p>
                <ul>${(lesson.points || []).slice(0, 3).map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>
              </article>
            `).join("")}
          </div>
        </div>

        <aside class="playbook-side">
          <div>
            <h3>Примеры</h3>
            <div class="guide-prompt-grid compact">
              ${(guide.examples || []).slice(0, 3).map((item, index) => renderGuidePromptCard(group, item, index)).join("")}
            </div>
          </div>

          <div>
            <h3>Лайфхаки</h3>
            <div class="tips-list compact">
              ${compactTips.map((item) => `<article>${escapeHtml(item)}</article>`).join("")}
            </div>
          </div>
        </aside>
      </div>

      <div class="model-guide-bottom">
        <div>
          <h3>FAQ</h3>
          <div class="guide-faq">
            ${(guide.faq || []).map((item, index) => `
              <article class="faq-item ${index === 0 ? "open" : ""}">
                <button type="button" data-guide-faq aria-expanded="${index === 0 ? "true" : "false"}">
                  <span>${escapeHtml(item.q)}</span>
                </button>
                <p>${escapeHtml(item.a)}</p>
              </article>
            `).join("")}
          </div>
        </div>

        <div>
          <div class="model-example-strip compact">
            ${relatedExamples.slice(0, 3).map((item, index) => `
              <article>
                ${mediaHtml(item, index)}
                <div>
                  <span>${escapeHtml(cleanModelName(item.model || group.name))}</span>
                  <b>${escapeHtml(item.title || "Пример")}</b>
                </div>
              </article>
            `).join("")}
          </div>
          ${renderSourceLinks(guide.sources)}
        </div>
      </div>
    </section>
  `;
}

async function triggerMediaDownload(url, filename = "") {
  const targetUrl = safeUrl(url || "");
  if (!targetUrl) {
    toast("Файл для скачивания не найден.", "danger");
    return;
  }
  try {
    const response = await fetch(targetUrl, { credentials: "omit" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const cleanName = String(filename || "").trim().replace(/[\/:*?"<>|]+/g, "-").replace(/\s+/g, " ");
    const urlName = targetUrl.split("/").pop()?.split("?")[0] || "result";
    link.href = blobUrl;
    link.download = cleanName || urlName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  } catch (error) {
    toast(`Не удалось скачать файл: ${error.message}`, "danger");
  }
}

async function triggerGenerationDownload(id, filename = "") {
  if (!id) return;
  try {
    const headers = {};
    if (state.token) headers["X-Web-Auth-Token"] = state.token;
    const response = await fetch(`${API_BASE}/generations/${encodeURIComponent(id)}/download`, { credentials: "same-origin", headers });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const cleanName = String(filename || `generation-${id}`).trim().replace(/[\/:*?"<>|]+/g, "-").replace(/\s+/g, " ");
    link.href = blobUrl;
    link.download = cleanName || `generation-${id}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  } catch (error) {
    toast(`Не удалось скачать файл: ${error.message}`, "danger");
  }
}

function parseMediaList(value) {
  try {
    const parsed = JSON.parse(value || "[]");
    if (Array.isArray(parsed)) return uniqueSafeUrls(parsed);
  } catch {}
  return [];
}

function ensureMediaViewer() {
  let modal = $("[data-media-viewer]");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.className = "modal-backdrop";
  modal.dataset.mediaViewer = "";
  modal.hidden = true;
  modal.innerHTML = `
    <section class="login-modal media-viewer-modal" role="dialog" aria-modal="true" aria-labelledby="media-viewer-title">
      <button class="modal-x" type="button" data-close-media-viewer aria-label="Закрыть">×</button>
      <div class="media-viewer-head">
        <div>
          <small data-media-viewer-counter>1 / 1</small>
          <h2 id="media-viewer-title">Просмотр результата</h2>
        </div>
        <div class="media-viewer-actions">
          <button class="button ghost" type="button" data-media-prev aria-label="Предыдущий файл">Назад</button>
          <button class="button ghost" type="button" data-download-media="" data-download-name="apix-result">Скачать</button>
          <button class="button ghost" type="button" data-media-next aria-label="Следующий файл">Дальше</button>
        </div>
      </div>
      <div class="media-viewer-body" data-media-viewer-body></div>
    </section>
  `;
  document.body.appendChild(modal);
  return modal;
}

function renderMediaViewer() {
  const modal = ensureMediaViewer();
  const items = state.mediaViewerItems || [];
  const current = items[state.mediaViewerIndex] || "";
  const body = modal.querySelector("[data-media-viewer-body]");
  const counter = modal.querySelector("[data-media-viewer-counter]");
  const download = modal.querySelector("[data-download-media]");
  const prev = modal.querySelector("[data-media-prev]");
  const next = modal.querySelector("[data-media-next]");
  if (!current || !body) return;
  if (/\.(mp4|mov|webm)(\?|$)/i.test(current)) {
    body.innerHTML = `<video src="${escapeHtml(current)}" controls playsinline autoplay></video>`;
  } else {
    body.innerHTML = `<img src="${escapeHtml(current)}" alt="Полный размер результата">`;
  }
  if (counter) counter.textContent = `${state.mediaViewerIndex + 1} / ${items.length}`;
  if (download) download.dataset.downloadMedia = current;
  if (prev) prev.disabled = items.length < 2;
  if (next) next.disabled = items.length < 2;
}

function openMediaViewer(url, list = [], index = null) {
  const directUrl = safeUrl(url);
  const items = uniqueSafeUrls(list.length ? list : [directUrl]);
  if (!items.length) {
    toast("Файл для просмотра не найден.", "danger");
    return;
  }
  const requestedIndex = Number(index);
  const directIndex = directUrl ? items.indexOf(directUrl) : -1;
  state.mediaViewerItems = items;
  state.mediaViewerIndex = Number.isFinite(requestedIndex) && requestedIndex >= 0
    ? Math.min(requestedIndex, items.length - 1)
    : Math.max(directIndex, 0);
  renderMediaViewer();
  ensureMediaViewer().hidden = false;
}

function closeMediaViewer() {
  const modal = $("[data-media-viewer]");
  if (modal) {
    modal.hidden = true;
    const body = modal.querySelector("[data-media-viewer-body]");
    if (body) body.innerHTML = "";
  }
}

function stepMediaViewer(direction) {
  const modal = $("[data-media-viewer]");
  const items = state.mediaViewerItems || [];
  if (!modal || modal.hidden || items.length < 2) return;
  const step = Number(direction) || 0;
  state.mediaViewerIndex = (state.mediaViewerIndex + step + items.length) % items.length;
  renderMediaViewer();
}

function toast(message, tone = "info") {
  const node = $("[data-toast]");
  if (!node) return;
  node.textContent = message;
  node.dataset.tone = tone;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    node.hidden = true;
  }, 3600);
}

function notifyGenerationCompletion(gen, previousStatus = "") {
  const normalized = String(gen?.status || "").toLowerCase();
  if (!["done", "failed"].includes(normalized)) return;
  if (!generationIsActive(previousStatus)) return;
  const id = Number(gen?.id) || String(gen?.id || "");
  if (!id) return;
  const noticeKey = `${id}:${normalized}`;
  if (state.completedGenerationNotices[noticeKey]) return;
  state.completedGenerationNotices[noticeKey] = Date.now();
  const title = gen?.title || `Работа #${id}`;
  const success = normalized === "done";
  const message = success
    ? "Готово — результат уже на сайте."
    : `Генерация не удалась: ${gen?.error || 'провайдер вернул ошибку'}`;
  toast(message, success ? "success" : "danger");
  const pageHidden = document.visibilityState !== "visible" || !document.hasFocus();
  if (!("Notification" in window) || Notification.permission !== "granted" || !pageHidden) return;
  try {
    const notification = new Notification(
      success ? "APIX: результат готов" : "APIX: ошибка генерации",
      {
        body: success ? `${title} готова. Открой сайт, чтобы посмотреть.` : `${title}: ${gen?.error || 'провайдер вернул ошибку'}`,
        icon: "/images/apix-premium-mark.svg",
      },
    );
    notification.onclick = () => {
      try { window.focus(); } catch {}
      location.href = "/studio.html";
      notification.close();
    };
  } catch {
    // Ignore browser notification errors.
  }
}

function setHero(index) {
  if (!state.examples.length) return;
  state.activeExample = index;
  const item = state.examples[index] || state.examples[0];
  const image = $("[data-hero-image]");
  const model = $("[data-hero-model]");
  const title = $("[data-hero-title]");
  if (image) image.src = item.image;
  if (model) model.textContent = cleanModelName(item.model);
  if (title) title.textContent = item.title;
  $$("[data-hero-index]").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.heroIndex) === index);
  });
}

function modelPreviewTitle(group, guide) {
  if (group?.type === "video") return "Пример ролика для выбранной модели";
  if (group?.type === "music") return "Пример трека для выбранной модели";
  return guide?.bestFor?.[0] || "Пример результата для выбранной модели";
}

function setModelPreview(group = currentModelGroup()) {
  if (!group) return;
  const guideKey = modelGuideKey(group);
  const guide = guideForGroup(group);
  const item = strictExamplesForGroup(group)[0];
  const image = $("[data-account-preview]");
  const model = $("[data-account-preview-model]");
  const title = $("[data-account-preview-title]");
  const preview = item?.image || MODEL_FAMILY_PREVIEWS[guideKey] || MODEL_GUIDE_VISUALS[guideKey] || MODEL_FAMILY_PREVIEWS.default || fallbackImage(0);
  if (image && preview) {
    image.src = preview;
    image.alt = `${cleanModelName(group.name)}: пример результата`;
  }
  if (model) model.textContent = cleanModelName(group.name);
  if (title) title.textContent = modelPreviewTitle(group, guide);
}

function setAccountPreview(index = state.activeExample) {
  if (state.generationStatus) {
    syncStudioResultStage();
    return;
  }
  const group = currentModelGroup();
  if (group) {
    setModelPreview(group);
    return;
  }
  if (!state.examples.length) return;
  const item = state.examples[index] || state.examples[0];
  const image = $("[data-account-preview]");
  const model = $("[data-account-preview-model]");
  const title = $("[data-account-preview-title]");
  if (image) image.src = item.image;
  if (model) model.textContent = cleanModelName(item.model);
  if (title) title.textContent = item.title;
}

function syncStudioResultStage(status = state.generationStatus) {
  const stage = $(".result-stage-clean");
  const image = $("[data-account-preview]");
  const model = $("[data-account-preview-model]");
  const title = $("[data-account-preview-title]");
  const actions = $("[data-studio-result-actions]");
  if (!stage || !image || !model || !title) return;

  const resultUrl = safeUrl(status?.image || status?.result_url || status?.resultUrl || status?.result_urls?.[0]);
  const active = status && generationIsActive(status.status);
  const failed = status && String(status.status || "").toLowerCase() === "failed";
  const done = status && String(status.status || "").toLowerCase() === "done";
  stage.classList.toggle("has-live-result", Boolean(status));
  stage.classList.toggle("is-waiting", Boolean(active && !resultUrl));
  stage.classList.toggle("is-failed", Boolean(failed));

  if (resultUrl) {
    const openUrls = mediaOriginalUrls(status);
    image.src = resultUrl;
    image.alt = done ? "Готовый результат генерации" : "Результат генерации";
    model.textContent = cleanModelName(status.model || currentModel()?.name || currentModel()?.key || "APIX");
    title.textContent = done ? "Готовый результат" : generationStatusCopy(status.status);
    if (actions) {
      const open = actions.querySelector("[data-studio-result-open]");
      const download = actions.querySelector("[data-studio-result-download]");
      if (open) {
        open.hidden = false;
        open.dataset.openMedia = resultUrl;
        open.dataset.openMediaList = JSON.stringify(openUrls.length ? openUrls : [resultUrl]);
        open.dataset.openMediaIndex = "0";
      }
      if (download) {
        download.hidden = false;
        download.dataset.downloadMedia = resultUrl;
        download.dataset.downloadName = status.title || "apix-result";
      }
      actions.hidden = false;
    }
    return;
  }

  if (status) {
    model.textContent = cleanModelName(status.model || currentModel()?.name || currentModel()?.key || "APIX");
    title.textContent = failed ? "Не удалось создать" : generationStatusCopy(status.status);
    if (actions) {
      actions.hidden = false;
      const open = actions.querySelector("[data-studio-result-open]");
      const download = actions.querySelector("[data-studio-result-download]");
      if (open) open.hidden = true;
      if (download) download.hidden = true;
    }
  } else if (actions) {
    actions.hidden = true;
  }
}

function renderHeroStack() {
  const stack = $("[data-hero-stack]");
  if (!stack) return;
  stack.innerHTML = state.examples.slice(0, 8).map((item, index) => `
    <button type="button" data-hero-index="${index}" aria-label="Показать пример ${index + 1}">
      <img src="${escapeHtml(item.image)}" loading="lazy" decoding="async" alt="">
    </button>
  `).join("");
  $$("[data-hero-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.heroIndex);
      setHero(index);
      setAccountPreview(index);
    });
  });
  setHero(0);
}

function modelsForCurrentKind() {
  return state.modelsByKind[state.generationKind]?.length
    ? state.modelsByKind[state.generationKind]
    : state.models.filter((model) => model.type === state.generationKind);
}

function groupedModelsForCurrentKind() {
  return groupModels(modelsForCurrentKind());
}

function currentModelGroup() {
  const select = $("[data-account-model-select]");
  const groups = groupedModelsForCurrentKind();
  return groups.find((group) => group.preferred.key === select?.value || group.variants.some((model) => model.key === select?.value)) || groups[0] || null;
}

function currentModel() {
  return currentModelGroup()?.preferred || modelsForCurrentKind()[0] || null;
}

function applyRouteParams() {
  const params = new URLSearchParams(location.search);
  const kind = params.get("type");
  if (["image", "video", "music"].includes(kind)) state.generationKind = kind;
  state.routeModelKey = params.get("model") || "";
  state.routePrompt = params.get("prompt") || "";
  state.routeReferenceUrl = params.get("ref") || "";
  state.routeReferenceUrls = uniqueSafeUrls([
    state.routeReferenceUrl,
    ...splitReferenceLinks(params.get("refs") || ""),
  ]);
  state.routeSourceReferenceUrl = params.get("source_ref") || "";
  state.routeFeedRemixId = params.get("feed_remix") || "";
  const flow = params.get("flow");
  const validFlow = ["text", "reference", "edit"].includes(flow);
  state.routeFlow = state.generationKind === "image" ? (validFlow ? flow : (state.routeFeedRemixId ? "reference" : "text")) : "";
}

function samePath(hrefPath, currentPath) {
  const clean = (value) => {
    const path = String(value || "/").replace(/^\//, "") || "index.html";
    return path === "index.html" ? "" : path;
  };
  return clean(hrefPath) === clean(currentPath);
}

function syncActiveNavigation() {
  const current = new URL(window.location.href);
  const rawCurrentFile = current.pathname.split("/").pop() || "index.html";
  const routeAliases = {
    "features.html": "models.html",
    "model.html": "models.html",
    "guide.html": "studio.html",
    "contact.html": "account.html",
  };
  const currentFile = routeAliases[rawCurrentFile] || rawCurrentFile;
  const currentType = current.searchParams.get("type") || (currentFile === "studio.html" ? state.generationKind || "image" : "");
  const currentFlow = current.searchParams.get("flow") || (currentFile === "studio.html" && currentType === "image" ? state.routeFlow || "text" : "");
  const currentHash = rawCurrentFile === "contact.html" ? "#assistant" : current.hash || "";

  $$(".topbar nav a").forEach((link) => {
    const url = new URL(link.getAttribute("href") || "/", window.location.href);
    const hrefFile = url.pathname.split("/").pop() || "index.html";
    const active = samePath(hrefFile, currentFile);
    link.toggleAttribute("aria-current", active);
    if (active) link.setAttribute("aria-current", "page");
  });

  $$(".product-menu a").forEach((link) => {
    const url = new URL(link.getAttribute("href") || "/", window.location.href);
    const hrefFile = url.pathname.split("/").pop() || "index.html";
    const hrefType = url.searchParams.get("type") || "";
    const hrefFlow = url.searchParams.get("flow") || "";
    const hrefHash = url.hash || "";
    let active = false;

    if (hrefFile === "studio.html" && currentFile === "studio.html") {
      active = hrefType === currentType && (!hrefFlow || hrefFlow === currentFlow);
      if (!currentFlow && hrefType === currentType && !hrefFlow) active = true;
    } else if (hrefFile === "account.html" && currentFile === "account.html") {
      active = hrefHash ? hrefHash === currentHash : !currentHash;
    } else {
      active = samePath(hrefFile, currentFile) && !hrefHash;
    }

    link.toggleAttribute("aria-current", active);
    if (active) link.setAttribute("aria-current", "page");
  });
}

function openAccountSection(tab = "billing") {
  if ($("[data-account-tabs]")) {
    activateAccountTab(tab, { updateHash: tab !== "billing" });
    return;
  }
  window.location.href = tab && tab !== "quick" ? `account.html#${tab}` : "account.html";
}

const FLOW_PRESETS = {
  text: {
    kind: "image",
    prompt: "Элегантный визуал для публикации: главный объект, настроение, свет, фон и желаемая подача",
    placeholder: "Опишите кадр: кто или что в центре, настроение, фон, свет, детали",
  },
  reference: {
    kind: "image",
    prompt: "Сохранить характер примера: стиль, композицию и настроение, улучшить свет и детали",
    placeholder: "Что сохранить из примера и что изменить?",
    referencePlaceholder: "Ссылка на референс",
  },
  edit: {
    kind: "image",
    prompt: "Улучшить исходное фото: сохранить внешность и композицию, аккуратно выровнять свет, стиль и детали",
    placeholder: "Что улучшить или изменить на фото?",
    referencePlaceholder: "Ссылка на исходное фото",
  },
};

const KIND_PRESETS = {
  video: {
    prompt: "Короткий ролик: главный объект, действие, движение камеры, свет и настроение сцены",
    placeholder: "Опишите сцену: герой, действие, движение камеры, свет и настроение",
  },
  music: {
    prompt: "Трек для короткого видео: жанр, настроение, темп, энергия и референсы звучания",
    placeholder: "Опишите музыку: жанр, настроение, темп, энергия и ощущение",
  },
};

function isDefaultPrompt(value) {
  const current = String(value || "").trim();
  if (!current || current.includes("Стильный портрет для обложки") || current.includes("Элегантный портрет для обложки")) return true;
  return [...Object.values(FLOW_PRESETS), ...Object.values(KIND_PRESETS)].some((preset) => current === preset.prompt);
}

function applyRoutePresetToComposer() {
  if (state.generationKind !== "image") return;
  const preset = FLOW_PRESETS[state.routeFlow];
  if (!preset) return;
  state.generationKind = preset.kind || state.generationKind;
  $$(".account-composer").forEach((form) => {
    const prompt = form.querySelector("textarea[name='prompt']");
    if (prompt) {
      const current = String(prompt.value || "").trim();
      prompt.placeholder = preset.placeholder || prompt.placeholder;
      if (isDefaultPrompt(current)) prompt.value = preset.prompt;
    }
    const referenceUrl = form.querySelector("[name='reference_url']");
    if (referenceUrl && preset.referencePlaceholder) {
      referenceUrl.placeholder = preset.referencePlaceholder;
    }
  });
}

function applyKindPresetToComposer() {
  const preset = KIND_PRESETS[state.generationKind];
  if (!preset) return;
  $$(".account-composer").forEach((form) => {
    const prompt = form.querySelector("textarea[name='prompt']");
    if (!prompt) return;
    const current = String(prompt.value || "").trim();
    prompt.placeholder = preset.placeholder || prompt.placeholder;
    if (isDefaultPrompt(current)) prompt.value = preset.prompt;
  });
}

function applyGenerationPresetToComposer() {
  const feedRemixMode = isFeedRemixMode();
  if (state.generationKind === "image") applyRoutePresetToComposer();
  else applyKindPresetToComposer();
  $$(".account-composer").forEach((form) => {
    const prompt = form.querySelector("textarea[name='prompt']");
    if (!prompt) return;
    prompt.toggleAttribute("required", !feedRemixMode);
    prompt.setAttribute("aria-required", feedRemixMode ? "false" : "true");
    if (feedRemixMode) {
      if (isDefaultPrompt(prompt.value) || !String(prompt.value || "").trim()) prompt.value = "";
      prompt.placeholder = "Промпт этой работы применится скрыто. Можно сразу запускать повтор.";
    }
  });
  if (state.routePrompt) {
    $$(".account-composer").forEach((form) => {
      const prompt = form.querySelector("textarea[name='prompt']");
      if (prompt) prompt.value = state.routePrompt;
    });
    state.routePrompt = "";
  }
  if (state.routeReferenceUrls.length) {
    $$(".account-composer").forEach((form) => {
      const reference = form.querySelector("input[name='reference_url']");
      const extra = form.querySelector("[name='reference_urls']");
      if (reference) reference.value = state.routeReferenceUrls[0] || "";
      if (extra) extra.value = state.routeReferenceUrls.slice(1).join("\n");
    });
  }
}

function isFeedRemixMode() {
  const params = new URLSearchParams(location.search);
  return Boolean(state.routeFeedRemixId || params.get("feed_remix"));
}

function updateStudioSearch(updates) {
  const currentFile = window.location.pathname.split("/").pop() || "index.html";
  if (currentFile !== "studio.html") return;
  const url = new URL(window.location.href);
  Object.entries(updates).forEach(([key, value]) => {
    if (value === "" || value == null) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
  });
  window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
}

function syncFlowControls() {
  const activeFlow = state.routeFlow || "text";
  const visible = state.generationKind === "image";
  $$("[data-flow-buttons]").forEach((group) => {
    group.hidden = !visible;
  });
  $$("[data-generation-flow]").forEach((button) => {
    const active = visible && button.dataset.generationFlow === activeFlow;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
}

function syncStudioSubpages() {
  const isImage = state.generationKind === "image";
  const flow = state.routeFlow || "text";
  const routeKey = isImage ? `image:${flow}` : `${state.generationKind}:default`;
  const map = {
    "image:text": {
      chip: "Картинка · с нуля",
      title: "Картинка по описанию",
      description: "Опишите идею, выберите формат и запустите генерацию без лишних шагов.",
      referenceTitle: "Референсы",
      referenceCopy: "Добавьте фото, если нужно сохранить стиль, лицо, позу или композицию.",
      showReference: true,
      openReference: false,
      showOptional: true,
      openOptional: false,
    },
    "image:reference": {
      chip: "Картинка · по референсу",
      title: "Картинка по референсу",
      description: "Сохраните стиль, композицию или внешность из примера и задайте нужные изменения.",
      referenceTitle: "Референс",
      referenceCopy: "Загрузите фото или вставьте ссылку на пример, от которого нужно оттолкнуться.",
      showReference: true,
      openReference: true,
      showOptional: true,
      openOptional: false,
    },
    "image:edit": {
      chip: "Фото · улучшение",
      title: "Улучшение фото",
      description: "Сохраните исходный кадр, но доведите свет, стиль и детали до аккуратного результата.",
      referenceTitle: "Исходное фото",
      referenceCopy: "Загрузите снимок или вставьте ссылку на фото, которое хотите улучшить.",
      showReference: true,
      openReference: true,
      showOptional: true,
      openOptional: false,
    },
    "video:default": {
      chip: "Видео",
      title: "Короткое видео",
      description: "Опишите сцену, движение камеры и настроение, затем выберите длительность.",
      referenceTitle: "Кадр или видео-референс",
      referenceCopy: "Можно добавить картинку или ссылку на видео, если ролик должен опираться на исходник.",
      showReference: true,
      openReference: false,
      showOptional: true,
      openOptional: true,
    },
    "music:default": {
      chip: "Музыка",
      title: "Музыкальный трек",
      description: "Опишите жанр, настроение, темп и энергию, Studio подготовит трек в отдельной очереди.",
      referenceTitle: "Без референсов",
      referenceCopy: "Для музыки достаточно текстового описания, поэтому блок с файлами скрыт.",
      showReference: false,
      openReference: false,
      showOptional: true,
      openOptional: false,
    },
  };
  const current = map[routeKey] || map["image:text"];

  const chip = document.querySelector("[data-studio-flow-chip]");
  const title = document.querySelector("[data-studio-flow-title]");
  const description = document.querySelector("[data-studio-flow-description]");
  const referenceTitle = document.querySelector("[data-reference-summary-title]");
  const referenceCopy = document.querySelector("[data-reference-summary-copy]");
  if (chip) chip.textContent = current.chip;
  if (title) title.textContent = current.title;
  if (description) description.textContent = current.description;
  if (referenceTitle) referenceTitle.textContent = current.referenceTitle;
  if (referenceCopy) referenceCopy.textContent = current.referenceCopy;

  $$("[data-studio-route-card]").forEach((card) => {
    const kindMatch = (card.dataset.routeKind || "image") === state.generationKind;
    const cardFlow = card.dataset.routeFlow || "default";
    const active = kindMatch && ((state.generationKind !== "image" && cardFlow === "default") || (state.generationKind === "image" && cardFlow === flow));
    card.classList.toggle("active", active);
    if (active) card.setAttribute("aria-current", "page");
    else card.removeAttribute("aria-current");
  });

  $$("[data-reference-section]").forEach((section) => {
    section.hidden = !current.showReference;
    if (current.showReference) section.open = Boolean(current.openReference);
  });

  $$("[data-optional-section]").forEach((section) => {
    section.hidden = !current.showOptional;
    if (current.showOptional && !section.dataset.userTouched) section.open = Boolean(current.openOptional);
  });
}

function setGenerationFlow(flow, { updateRoute = false } = {}) {
  state.routeFlow = ["text", "reference", "edit"].includes(flow) ? flow : "text";
  state.generationKind = "image";
  state.routeModelKey = "";
  state.routeFeedRemixId = "";
  state.routeSourceReferenceUrl = "";
  state.routeReferenceUrls = [];
  applyGenerationPresetToComposer();
  renderModels();
  syncFlowControls();
  syncStudioSubpages();
  syncActiveNavigation();
  if (updateRoute) updateStudioSearch({ type: "image", flow: state.routeFlow, model: "", feed_remix: "", source_ref: "", ref: "", refs: "" });
}

function setGenerationKind(kind, { updateRoute = false } = {}) {
  state.generationKind = ["image", "video", "music"].includes(kind) ? kind : "image";
  if (state.generationKind === "image" && !state.routeFlow) state.routeFlow = "text";
  state.routeModelKey = "";
  state.routeFeedRemixId = "";
  state.routeSourceReferenceUrl = "";
  state.routeReferenceUrls = [];
  applyGenerationPresetToComposer();
  renderModels();
  syncFlowControls();
  syncStudioSubpages();
  syncActiveNavigation();
  if (updateRoute) {
    updateStudioSearch({
      type: state.generationKind,
      flow: state.generationKind === "image" ? state.routeFlow || "text" : "",
      model: "",
      feed_remix: "",
      source_ref: "",
      ref: "",
      refs: "",
    });
  }
}

function optionTags(values, selected = "") {
  return (values || []).filter(Boolean).map((value) => {
    const option = typeof value === "object" ? value : { value, label: value };
    const rawValue = String(option.value ?? option.label ?? "");
    return `<option value="${escapeHtml(rawValue)}" ${rawValue === String(selected || "") ? "selected" : ""}>${escapeHtml(option.label || rawValue)}</option>`;
  }).join("");
}

function closeCustomSelects(except = null) {
  $$("[data-select-proxy]").forEach((proxy) => {
    if (proxy === except) return;
    proxy.classList.remove("open");
    proxy.closest("label")?.classList.remove("select-open");
    proxy.querySelector("[data-custom-options]")?.setAttribute("hidden", "");
    proxy.querySelector("[data-custom-select-toggle]")?.setAttribute("aria-expanded", "false");
  });
  state.openSelectProxy = except?.isConnected ? except : null;
}

function toggleCustomSelect(proxy, open) {
  if (!proxy) return;
  if (open) closeCustomSelects(proxy);
  proxy.classList.toggle("open", open);
  proxy.closest("label")?.classList.toggle("select-open", open);
  proxy.querySelector("[data-custom-options]")?.toggleAttribute("hidden", !open);
  proxy.querySelector("[data-custom-select-toggle]")?.setAttribute("aria-expanded", open ? "true" : "false");
  state.openSelectProxy = open ? proxy : null;
}

function syncCustomSelect(select) {
  if (!select || select.dataset.noCustomSelect === "true") return;
  const proxy = select.nextElementSibling?.matches?.("[data-select-proxy]")
    ? select.nextElementSibling
    : null;
  if (!proxy) return;

  const selected = select.selectedOptions?.[0] || select.options?.[0] || null;
  const label = selected?.textContent?.trim() || "Выберите";
  const hidden = Boolean(select.disabled || select.closest("label")?.hidden || select.closest("[hidden]"));
  const toggle = proxy.querySelector("[data-custom-select-toggle]");
  const valueLabel = proxy.querySelector("[data-custom-select-value]");
  const options = proxy.querySelector("[data-custom-options]");

  proxy.hidden = hidden;
  proxy.classList.toggle("disabled", Boolean(select.disabled));
  if (hidden || select.disabled) toggleCustomSelect(proxy, false);
  if (toggle) {
    toggle.disabled = Boolean(select.disabled);
    toggle.setAttribute("aria-expanded", proxy.classList.contains("open") ? "true" : "false");
  }
  if (valueLabel) valueLabel.textContent = label;
  if (options) {
    options.innerHTML = Array.from(select.options).map((option) => `
      <button
        type="button"
        role="option"
        data-custom-select-option
        data-value="${escapeHtml(option.value)}"
        aria-selected="${option.selected ? "true" : "false"}"
        ${option.disabled ? "disabled" : ""}
      >${escapeHtml(option.textContent || option.value)}</button>
    `).join("");
    options.hidden = !proxy.classList.contains("open");
  }
}

function enhanceSelect(select) {
  if (!select || select.dataset.enhancedSelect === "true" || select.dataset.noCustomSelect === "true") return;
  select.dataset.enhancedSelect = "true";
  select.classList.add("native-select-hidden");
  const proxy = document.createElement("div");
  proxy.className = "custom-select";
  proxy.dataset.selectProxy = "true";
  proxy.innerHTML = `
    <button type="button" class="custom-select-toggle" data-custom-select-toggle aria-haspopup="listbox" aria-expanded="false">
      <span data-custom-select-value></span>
    </button>
    <div class="custom-select-options" data-custom-options role="listbox" hidden></div>
  `;
  select.insertAdjacentElement("afterend", proxy);
  syncCustomSelect(select);
}

function refreshCustomSelects(root = document) {
  root.querySelectorAll("select").forEach(enhanceSelect);
  root.querySelectorAll("select").forEach(syncCustomSelect);
  closeCustomSelects();
}

function setComposerControl(name, visible) {
  $$(`.account-composer [name='${name}']`).forEach((node) => {
    const label = node.closest("label");
    const sourceOnly = Boolean(label?.dataset?.sourceOnly);
    const forceVisible = name === "quality";
    if (label) label.hidden = forceVisible ? !visible : (sourceOnly ? true : !visible);
    node.disabled = !visible;
  });
}

function setMirrorControl(selector, visible) {
  $$(selector).forEach((node) => {
    const label = node.closest("label");
    if (label) label.hidden = !visible;
    node.disabled = !visible;
  });
}

function syncComposerRows() {
  $$(".account-composer .composer-row").forEach((row) => {
    const controls = Array.from(row.querySelectorAll("label"));
    row.hidden = controls.length > 0 && controls.every((label) => label.hidden);
  });
}

function sectionHasVisibleControls(section) {
  if (!section) return false;
  const labels = Array.from(section.querySelectorAll("label"));
  const hasVisibleLabel = labels.some((label) => !label.hidden && !label.closest("[hidden]"));
  const hasPromptInjections = Boolean(section.querySelector("[data-prompt-injections]:not([hidden])"));
  return hasVisibleLabel || hasPromptInjections;
}

function syncDisclosureContentVisibility() {
  $$("[data-optional-section]").forEach((section) => {
    const hasVisible = sectionHasVisibleControls(section);
    section.hidden = section.hidden || !hasVisible;
    if (!hasVisible) section.open = false;
  });
  $$("[data-reference-section]").forEach((section) => {
    const card = section.querySelector("[data-photo-prompt-card]");
    if (card) card.hidden = card.hidden || !sectionHasVisibleControls(section);
  });
}

function syncControlVisibility(model) {
  const kind = state.generationKind;
  const source = `${model?.key || ""} ${model?.name || ""}`.toLowerCase();
  const hasResolutions = Boolean(model?.resolutions?.filter(Boolean).length);
  const hasCounts = Boolean(model?.counts?.length && model.counts.length > 1);
  const isGrok = source.includes("grok");

  setComposerControl("aspect_ratio", kind !== "music");
  setComposerControl("quality", kind !== "music");
  setComposerControl("count", hasCounts);
  setComposerControl("duration", kind === "video");
  setComposerControl("resolution", hasResolutions);
  setComposerControl("reference_url", kind !== "music");
  setComposerControl("reference_urls", kind !== "music");
  setComposerControl("reference_file", kind !== "music");
  setComposerControl("video_url", kind === "video");
  setComposerControl("seed", isGrok);
  setComposerControl("grok_mode", isGrok);
  setComposerControl("instrumental", kind === "music");
  $$("[data-photo-prompt-card]").forEach((card) => {
    card.hidden = kind === "music";
  });

  setMirrorControl("[data-quality-options]", kind !== "music");
  setMirrorControl("[data-count-options]", hasCounts);
  setMirrorControl("[data-duration-options]", kind === "video");
  renderPromptInjections();
  updatePromptInjectionStatus();
  syncComposerRows();
  syncDisclosureContentVisibility();
  refreshCustomSelects();
}

function variantMatches(model, patterns) {
  const source = `${model?.key || ""} ${model?.name || ""}`.toLowerCase();
  return patterns.some((pattern) => pattern.test(source));
}

function requestModelForCurrentSetup(model, { referenceUrl = "", videoUrl = "" } = {}) {
  const variants = model?.variants?.length ? model.variants : [model].filter(Boolean);
  if (!variants.length) return model;
  if (state.generationKind === "video") {
    if (videoUrl) return variants.find((item) => variantMatches(item, [/video-to-video/, /motion-control/])) || model;
    if (referenceUrl) return variants.find((item) => variantMatches(item, [/image-to-video/, /\/image/, /-image/])) || model;
    return variants.find((item) => variantMatches(item, [/text-to-video/, /\/text/, /-text/])) || model;
  }
  if (state.generationKind === "image") {
    if (referenceUrl) return variants.find((item) => variantMatches(item, [/image-to-image/, /image-edit/, /\/edit/, /-edit/, /\bedit\b/])) || model;
    return variants.find((item) => variantMatches(item, [/text-to-image/, /\/text/, /-text/])) || model;
  }
  return model;
}

function selectedComposerValue(name, form = document.querySelector(".account-composer")) {
  const node = form?.querySelector(`[name='${name}']`);
  if (!node || node.disabled) return "";
  return String(node.value || "");
}

function selectedComposerNumber(name, fallback = 0, form = document.querySelector(".account-composer")) {
  const value = Number(selectedComposerValue(name, form));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function estimateGenerationCost(model = currentModel(), form = document.querySelector(".account-composer")) {
  if (!model) return { amount: 0, unit: "за работу" };
  const kind = state.generationKind;
  if (kind === "music") return { amount: Number(model.credits || 0), unit: "за трек" };
  if (kind === "video") {
    const duration = selectedComposerNumber("duration", model.durations?.[0] || 5, form);
    if (model.key === "gemini-omni-video") {
      const resolution = omniResolutionKey(selectedComposerValue("resolution", form) || model.resolutions?.[0] || "720p");
      const mode = selectedComposerValue("mode", form) || (selectedComposerValue("video_url", form) ? "video" : "image");
      const table = model.priceTable?.[resolution] || model.priceTable?.["720p"] || {};
      const flat = mode === "video"
        ? Number(model.videoInputPrices?.[resolution] ?? model.videoInputPrices?.["720p"] ?? NaN)
        : Number(table?.[duration] ?? table?.[String(duration)] ?? NaN);
      if (Number.isFinite(flat) && flat > 0) return { amount: flat, unit: "за видео" };
    }
    const amount = model.creditsPerSec ? Number(model.creditsPerSec) * duration : Number(model.credits || 0);
    return { amount, unit: "за видео" };
  }
  const quality = selectedComposerValue("quality", form);
  const qualityPrice = quality && model.qualityPrices ? Number(model.qualityPrices[quality]) : NaN;
  const base = Number.isFinite(qualityPrice) && qualityPrice > 0 ? qualityPrice : Number(model.credits || 0);
  const count = selectedComposerNumber("count", 1, form);
  return { amount: base * count, unit: "за работу" };
}

function updateGenerationEstimate() {
  const note = $("[data-generation-note]");
  if (!note) return;
  const model = currentModel();
  const form = note.closest(".account-composer") || document.querySelector(".account-composer");
  const estimate = estimateGenerationCost(model, form);
  const name = cleanModelName(model?.name || model?.key || "Выбранный режим");
  note.innerHTML = `
    <span>Стоимость запуска</span>
    <b>${formatNumber(estimate.amount)} ${escapeHtml(estimate.unit)}</b>
    <small>${escapeHtml(name)}</small>
  `;
}

function generationKindLabel(kind = state.generationKind) {
  if (kind === "video") return "Видео";
  if (kind === "music") return "Музыка";
  return "Картинка";
}

function selectedOptionText(form, name) {
  const node = form?.querySelector(`[name='${name}']`);
  if (!node || node.disabled) return "";
  if (node instanceof HTMLSelectElement) {
    return node.selectedOptions?.[0]?.textContent?.trim() || node.value || "";
  }
  return String(node.value || "").trim();
}

function selectedOptionValue(form, name) {
  const node = form?.querySelector(`[name='${name}']`);
  if (!node || node.disabled) return "";
  return String(node.value || "").trim();
}

function referenceFiles(form) {
  const input = form?.querySelector("[name='reference_file']");
  if (!input || input.disabled || !input.files) return [];
  return Array.from(input.files).filter((file) => file && file.size > 0);
}

function splitReferenceLinks(value = "") {
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function referenceLinkValues(form) {
  const primary = selectedOptionValue(form, "reference_url");
  const extra = form?.querySelector("[name='reference_urls']");
  return uniqueSafeUrls([
    primary,
    ...splitReferenceLinks(extra && !extra.disabled ? extra.value : ""),
  ]);
}

function allPromptInjectionItems() {
  return PROMPT_INJECTION_CATEGORIES.flatMap((category) => category.items.map((item) => ({ ...item, category: category.title })));
}

function promptInjectionVisible(item, kind = state.generationKind) {
  const kinds = item.kinds || [];
  return !kinds.length || kinds.includes(kind);
}

function selectedPromptInjections(form = document.querySelector(".account-composer")) {
  const keys = new Set(
    Array.from(form?.querySelectorAll("[name='prompt_preset']:checked") || [])
      .map((input) => String(input.value || ""))
      .filter(Boolean)
  );
  return allPromptInjectionItems()
    .filter((item) => keys.has(item.key) && promptInjectionVisible(item));
}

function promptWithInjections(form, basePrompt = "") {
  const cleanPrompt = String(basePrompt || "").trim();
  const injections = selectedPromptInjections(form);
  if (!cleanPrompt || !injections.length) return { prompt: cleanPrompt, injections };
  const hints = injections.map((item) => item.hint).filter(Boolean);
  return {
    prompt: `${cleanPrompt}\n\nAdditional style constraints: ${hints.join("; ")}.`,
    injections,
  };
}

function renderPromptInjections(form = document.querySelector(".account-composer")) {
  const root = form?.querySelector("[data-prompt-injections]");
  if (!root) return;
  const selected = new Set(
    Array.from(root.querySelectorAll("[name='prompt_preset']:checked"))
      .map((input) => String(input.value || ""))
      .filter(Boolean)
  );
  const groups = PROMPT_INJECTION_CATEGORIES
    .map((category) => ({
      ...category,
      items: category.items.filter((item) => promptInjectionVisible(item)),
    }))
    .filter((category) => category.items.length);
  root.hidden = !groups.length;
  root.innerHTML = groups.length ? `
    <div class="prompt-injections-head">
      <div>
        <span>Скрытые акценты</span>
        <b>Нюансы стиля, света и качества</b>
      </div>
      <small data-preset-status>Выбрано: ${selected.size}</small>
    </div>
    <div class="prompt-injection-groups">
      ${groups.map((category) => `
        <section class="prompt-injection-group">
          <h4>${escapeHtml(category.title)}</h4>
          <div class="prompt-preset-list">
            ${category.items.map((item) => `
              <label class="prompt-preset">
                <input type="checkbox" name="prompt_preset" value="${escapeHtml(item.key)}" ${selected.has(item.key) ? "checked" : ""} />
                <span>
                  <b>${escapeHtml(item.label)}</b>
                  <small>${escapeHtml(item.copy || "Аккуратно усиливает результат без изменения текста в поле.")}</small>
                </span>
              </label>
            `).join("")}
          </div>
        </section>
      `).join("")}
    </div>
  ` : "";
}

function updatePromptInjectionStatus(form = document.querySelector(".account-composer")) {
  const status = form?.querySelector("[data-preset-status]");
  if (!status) return;
  const selected = selectedPromptInjections(form);
  status.textContent = selected.length
    ? `Выбрано: ${selected.length}`
    : "Акценты не выбраны";
}

function referenceSummary(form) {
  const files = referenceFiles(form);
  if (files.length === 1) return `фото: ${files[0].name}`;
  if (files.length > 1) return `${files.length} фото`;
  const links = referenceLinkValues(form);
  const videoUrl = selectedOptionText(form, "video_url");
  if (links.length === 1) return "ссылка на пример";
  if (links.length > 1) return `${links.length} ссылок`;
  if (videoUrl) return "ссылка на видео";
  return "без примера";
}

function composerFromTrigger(trigger) {
  return trigger?.closest?.(".account-composer") || document.querySelector(".account-composer");
}

function fileSizeLabel(size = 0) {
  const value = Number(size || 0);
  if (value >= 1024 * 1024) return `${formatNumber(value / 1024 / 1024)} МБ`;
  if (value >= 1024) return `${formatNumber(value / 1024)} КБ`;
  return value ? `${formatNumber(value)} Б` : "";
}

function syncReferencePreview(form = document.querySelector(".account-composer")) {
  const files = referenceFiles(form);
  const file = files[0];
  const preview = form?.querySelector("[data-reference-preview]");
  const image = form?.querySelector("[data-reference-preview-image]");
  if (!preview || !image) return;
  if (file) {
    const reader = new FileReader();
    reader.onload = () => {
      image.src = String(reader.result || "");
      image.alt = `Загруженный референс: ${file.name || 'reference'}`;
      preview.hidden = false;
    };
    reader.readAsDataURL(file);
    return;
  }
  image.src = "";
  image.alt = "Превью загруженного референса";
  preview.hidden = true;
}

function updatePhotoPromptStatus(form = document.querySelector(".account-composer"), message = "") {
  const files = referenceFiles(form);
  const file = files[0];
  const status = form?.querySelector("[data-photo-prompt-status]");
  const card = form?.querySelector("[data-photo-prompt-card]");
  if (!status) return;
  card?.classList.toggle("has-file", Boolean(files.length));
  status.textContent = message || (files.length > 1
    ? `${files.length} фото выбрано`
    : file ? `${file.name}${fileSizeLabel(file.size) ? ` · ${fileSizeLabel(file.size)}` : ""}` : "Сначала выберите фото");
  syncReferencePreview(form);
}

function ensureGenerationReviewModal() {
  let modal = $("[data-generation-review-modal]");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.className = "modal-backdrop";
  modal.dataset.generationReviewModal = "true";
  modal.hidden = true;
  modal.innerHTML = `
    <section class="login-modal review-modal" role="dialog" aria-modal="true" aria-labelledby="review-title">
      <button class="modal-x" type="button" data-close-review aria-label="Закрыть">×</button>
      <p class="eyebrow">Проверка запуска</p>
      <h2 id="review-title">Запускаем эту работу?</h2>
      <p>Проверьте сценарий, модель и стоимость. После запуска результат появится справа и в истории.</p>
      <div class="review-list" data-review-list></div>
      <div class="review-prompt" data-review-prompt></div>
      <div class="review-actions">
        <button class="button ghost" type="button" data-close-review>Проверить ещё раз</button>
        <button class="button primary" type="button" data-confirm-generation>Запустить</button>
      </div>
    </section>
  `;
  document.body.appendChild(modal);
  return modal;
}

function openGenerationReview(form) {
  if (!state.user) {
    openLogin();
    toast("Сначала войдите.", "info");
    return;
  }
  const prompt = String(new FormData(form).get("prompt") || "").trim();
  const feedRemixMode = isFeedRemixMode();
  const injections = feedRemixMode ? [] : selectedPromptInjections(form);
  if (!prompt && !feedRemixMode) {
    toast("Опишите, что нужно создать.", "danger");
    return;
  }
  state.pendingGenerationForm = form;
  const modal = ensureGenerationReviewModal();
  const model = currentModel();
  const estimate = estimateGenerationCost(model, form);
  const rows = [
    ["Формат", generationKindLabel()],
    ["Сценарий", state.generationKind === "image" ? ({ text: "С нуля", reference: "По референсу", edit: "Улучшить фото" }[state.routeFlow || "text"] || "С нуля") : "По описанию"],
    ["Модель", cleanModelName(model?.name || model?.key || "не выбрана")],
    ["Качество", selectedOptionText(form, "quality") || "Стандарт"],
    ["Формат кадра", selectedOptionText(form, "aspect_ratio") || "Авто"],
    ["Количество", selectedOptionValue(form, "count") || "1"],
    ...(state.generationKind === "video" ? [["Длительность", selectedOptionText(form, "duration") || "Авто"]] : []),
    ["Пример", referenceSummary(form)],
    ["Скрытые акценты", injections.length ? injections.map((item) => item.label).join(", ") : "не выбраны"],
    ["Стоимость", `${formatNumber(estimate.amount)} ${estimate.unit}`],
  ];
  modal.querySelector("[data-review-list]").innerHTML = rows.map(([label, value]) => `
    <article>
      <span>${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
    </article>
  `).join("");
  modal.querySelector("[data-review-prompt]").textContent = feedRemixMode ? "Промпт выбранной работы применится скрыто." : prompt;
  modal.hidden = false;
}

function closeGenerationReview({ keepPending = false } = {}) {
  const modal = $("[data-generation-review-modal]");
  if (modal) modal.hidden = true;
  if (!keepPending) state.pendingGenerationForm = null;
}

function syncGenerationControls() {
  const model = currentModel();
  const ratio = document.querySelector("[name='aspect_ratio']");
  const quality = document.querySelector("[name='quality']");
  const count = document.querySelector("[name='count']");
  const duration = document.querySelector("[name='duration']");
  const resolution = document.querySelector("[name='resolution']");
  const instrumental = document.querySelector("[name='instrumental']");

  if (ratio) {
    const ratios = model?.aspectRatios?.length ? model.aspectRatios : ["9:16", "1:1", "16:9"];
    ratio.innerHTML = optionTags(ratios, ratios[0]);
  }
  if (quality) {
    const qualities = model?.qualities?.length ? model.qualities : [{ value: "basic", label: "Стандарт" }, { value: "2K", label: "2K" }, { value: "4K", label: "4K" }];
    quality.innerHTML = optionTags(qualities, qualities[0]?.value || qualities[0]);
  }
  if (count) {
    const counts = model?.counts?.length ? model.counts : [1];
    count.innerHTML = optionTags(counts, counts[0]);
  }
  if (duration) {
    const durations = model?.durations?.length ? model.durations : [5, 10];
    duration.innerHTML = optionTags(durations.map((value) => ({ value, label: `${value} сек` })), durations[0]);
  }
  if (resolution) {
    const resolutions = model?.resolutions?.length ? model.resolutions : [""];
    resolution.innerHTML = optionTags([{ value: "", label: "Авто" }, ...resolutions.map((value) => ({ value, label: value }))], "");
  }
  if (instrumental) instrumental.disabled = state.generationKind !== "music";
  syncMirrorSelects("[data-quality-options]", quality, "<option value='basic'>Стандарт</option>");
  syncMirrorSelects("[data-count-options]", count, "<option>1</option>");
  syncMirrorSelects("[data-duration-options]", duration, "<option>5 сек</option>");
  syncControlVisibility(model);
  syncStudioSubpages();
  $$(".account-composer").forEach((form) => updatePhotoPromptStatus(form));
  updateGenerationEstimate();
  if (state.generationStatus) syncStudioResultStage();
  else setModelPreview(currentModelGroup());
  renderActiveImageSession();
  refreshCustomSelects();
}

function syncMirrorSelects(selector, sourceSelect, fallbackHtml) {
  $$(selector).forEach((mirror) => {
    mirror.innerHTML = sourceSelect?.innerHTML || fallbackHtml;
    mirror.value = sourceSelect?.value || mirror.options?.[0]?.value || "";
    mirror.disabled = Boolean(sourceSelect?.disabled);
  });
}

function updateComposerSelectFromMirror(sourceName, value) {
  const source = document.querySelector(`.account-composer [name='${sourceName}']`);
  if (!source || source.disabled) return;
  source.value = value;
  source.dispatchEvent(new Event("change", { bubbles: true }));
  syncMirrorSelectsFor(sourceName);
  updateGenerationEstimate();
  refreshCustomSelects();
}

function syncMirrorSelectsFor(sourceName) {
  const source = document.querySelector(`.account-composer [name='${sourceName}']`);
  const map = {
    quality: "[data-quality-options]",
    count: "[data-count-options]",
    duration: "[data-duration-options]",
  };
  if (!map[sourceName]) return;
  syncMirrorSelects(map[sourceName], source, source?.innerHTML || "");
}

function renderModels() {
  const grid = $("[data-model-grid]");
  const select = $("[data-model-select]");
  const accountSelect = $("[data-account-model-select]");
  const allModels = state.models.length ? state.models : Object.values(state.modelsByKind).flat();
  const groupedModels = groupModels(allModels);
  const visible = groupedModels.filter((model) => state.modelType === "all" || model.type === state.modelType);
  const counts = {
    image: groupedModels.filter((model) => model.type === "image").length,
    video: groupedModels.filter((model) => model.type === "video").length,
    music: groupedModels.filter((model) => model.type === "music").length,
  };

  if ($("[data-total-models]")) $("[data-total-models]").textContent = String(groupedModels.length || 0);
  if ($("[data-image-models]")) $("[data-image-models]").textContent = String(counts.image || 0);
  if ($("[data-video-models]")) $("[data-video-models]").textContent = String(counts.video || 0);
  if ($("[data-music-models]")) $("[data-music-models]").textContent = String(counts.music || 0);

  if (grid) {
    grid.innerHTML = visible.map((group, index) => {
      const model = group.preferred;
      const detailHref = modelDetailHref(group);
      return `
      <article class="model-card model-row" data-model-kind="${escapeHtml(group.type)}">
        <div class="model-id">${String(index + 1).padStart(2, "0")}</div>
        <div class="model-main">
          <span class="model-badge">${shortTypeLabel(group.type)}</span>
          <strong>${escapeHtml(group.name)}</strong>
          <small>${escapeHtml(group.subtitle)}</small>
        </div>
        <div class="model-chips">
          ${group.chips.slice(0, 5).map((item) => `<b>${escapeHtml(capabilityLabel(item))}</b>`).join("")}
          <b>${group.active ? "доступно" : "скоро"}</b>
        </div>
        <div class="model-price">
          <span>Стоимость</span>
          <strong>${escapeHtml(group.creditsLabel)}</strong>
          <small>${unitLabel(group.type)}</small>
        </div>
        <a class="model-action" href="${escapeHtml(detailHref)}">Открыть</a>
      </article>
    `;
    }).join("");
  }

  if (select) {
    select.innerHTML = groupedModels.map((group) => `
      <option value="${escapeHtml(group.preferred.key)}">${escapeHtml(group.name)}</option>
    `).join("");
  }

  if (accountSelect) {
    const groups = groupedModelsForCurrentKind();
    accountSelect.innerHTML = groups.map((group) => `
      <option value="${escapeHtml(group.preferred.key)}">${escapeHtml(group.name)}</option>
    `).join("");
    if (state.routeModelKey) {
      const group = groups.find((item) => item.preferred.key === state.routeModelKey || item.variants.some((model) => model.key === state.routeModelKey));
      if (group) accountSelect.value = group.preferred.key;
    }
  }

  $$("[data-generation-kind]").forEach((button) => {
    button.classList.toggle("active", button.dataset.generationKind === state.generationKind);
  });
  syncFlowControls();
  syncGenerationControls();
  renderModelDetail();
}

function renderGallery() {
  const grid = $("[data-gallery-grid]");
  if ($("[data-total-examples]")) $("[data-total-examples]").textContent = String(state.examples.length || 0);
  $$("[data-feed-source]").forEach((button) => {
    const active = (button.dataset.feedSource || "feed") === state.feedSource;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  if (!grid) return;
  grid.classList.add("feed-grid");
  grid.innerHTML = state.examples.map((item, index) => feedCard(item, index, "gallery")).join("");
}

function renderAuth() {
  const authed = Boolean(state.user);
  const name = state.user?.full_name || state.user?.username || "APIX creator";
  const credits = formatNumber(state.user?.credits || 0);
  $$("[data-account-status]").forEach((accountStatus) => {
    accountStatus.textContent = authed
      ? `${name} · баланс ${credits}`
      : state.fallbackMode ? "Backend недоступен" : "Гость · войдите или зарегистрируйтесь";
  });
    $$("[data-auth-only]").forEach((node) => {
    node.hidden = !authed;
  });
  $$("[data-guest-only]").forEach((node) => {
    node.hidden = authed;
  });
$$("[data-user-pill]").forEach((userPill) => {
    userPill.textContent = authed ? `Баланс ${credits}` : "Войти";
    if (authed) userPill.dataset.accountTarget = "billing";
    else delete userPill.dataset.accountTarget;
  });
  $$("[data-open-login]:not([data-user-pill])").forEach((button) => {
    const fixedTarget = button.dataset.accountTargetFixed === "true";
    if (authed) {
      button.textContent = button.matches(".concept-balance button") ? "Пополнить" : button.textContent;
      if (!fixedTarget) button.dataset.accountTarget = "billing";
    } else {
      if (button.matches(".concept-balance button")) button.textContent = "Войти";
      if (!fixedTarget) delete button.dataset.accountTarget;
    }
  });
  $$("[data-logout]").forEach((logout) => {
    logout.hidden = !authed;
  });
    $$(".topbar nav a[href='studio.html']").forEach((node) => {
    node.hidden = !authed;
  });
$$("[data-admin-only]").forEach((node) => {
    node.hidden = !state.user?.is_admin;
  });
  syncGenerationControls();
  renderBilling();
  renderReferrals();
  renderSettings();
  renderAdmin();
}

function renderAccountModelsMini() {
  const mini = $("[data-account-models-mini]");
  if (!mini) return;
  const groups = groupedModelsForCurrentKind();
  const active = currentModelGroup();
  const items = [
    active,
    ...groups.filter((group) => group.key !== active?.key),
  ].filter(Boolean).slice(0, 6);
  mini.innerHTML = items.map((group) => {
    const model = group.preferred;
    const isActive = active?.key === group.key;
    const capabilities = (group.chips || model.capabilities || []).slice(0, 2).map(capabilityLabel).join(" / ");
    return `
      <button class="model-mini${isActive ? " active" : ""}" type="button" data-mini-model="${escapeHtml(model.key)}" aria-pressed="${isActive ? "true" : "false"}">
        <span>${typeLabel(group.type)}</span>
        <b>${escapeHtml(group.name)}</b>
        <small>${escapeHtml(group.creditsLabel)} ${unitLabel(group.type)}${capabilities ? ` · ${escapeHtml(capabilities)}` : ""}</small>
      </button>
    `;
  }).join("");
}

function renderActiveImageSession() {
  const root = $("[data-active-image-session]");
  if (!root) return;
  const session = state.activeImageSession;
  if (!state.user || !session || state.generationKind !== "image") {
    root.hidden = true;
    root.innerHTML = "";
    return;
  }
  const refs = uniqueSafeUrls(session.reference_urls || session.referenceUrls || [session.reference_url, session.referenceUrl]);
  const promptMeta = session.prompt_hidden || session.promptHidden
    ? "Промпт защищён правилами ленты"
    : "Серия сохранена, текст не показываем на экране";
  root.hidden = false;
  root.innerHTML = `
    <div>
      <span>Активная серия</span>
      <b>${escapeHtml(cleanModelName(session.model || "модель"))} · ${escapeHtml(session.aspect_ratio || "auto")} · ${escapeHtml(session.quality || "basic")}</b>
      <small>${escapeHtml(promptMeta)}</small>
      <small>${refs.length ? `${refs.length} референс${refs.length > 1 ? "а" : ""}` : "без референса"}${session.last_generation_id ? ` · работа #${session.last_generation_id}` : ""}</small>
    </div>
    <div class="active-session-actions">
      <button class="button ghost" type="button" data-use-image-session>Продолжить</button>
      <button class="button ghost" type="button" data-archive-image-session="${escapeHtml(session.id)}">Новая серия</button>
    </div>
  `;
}

function applyActiveImageSession() {
  const session = state.activeImageSession;
  const form = document.querySelector(".account-composer");
  if (!session || !form) return;
  state.generationKind = "image";
  renderModels();
  const select = form.querySelector("[data-account-model-select]");
  if (select && session.model) {
    select.value = session.model;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    syncCustomSelect(select);
  }
  const prompt = form.querySelector("[name='prompt']");
  if (prompt && !(session.prompt_hidden || session.promptHidden)) {
    prompt.value = session.last_prompt || session.base_prompt || prompt.value || "";
  }
  const ratio = form.querySelector("[name='aspect_ratio']");
  if (ratio && session.aspect_ratio) ratio.value = session.aspect_ratio;
  const quality = form.querySelector("[name='quality']");
  if (quality && session.quality) quality.value = session.quality;
  const count = form.querySelector("[name='count']");
  if (count && session.count) count.value = String(session.count);
  const refs = uniqueSafeUrls(session.reference_urls || session.referenceUrls || [session.reference_url, session.referenceUrl]);
  const reference = form.querySelector("[name='reference_url']");
  const extra = form.querySelector("[name='reference_urls']");
  if (reference) reference.value = refs[0] || "";
  if (extra) extra.value = refs.slice(1).join("\n");
  setGenerationFlow(refs.length ? "reference" : "text", { updateRoute: true });
  updateGenerationEstimate();
  refreshCustomSelects();
  toast("Активная серия применена.", "success");
}

async function archiveActiveImageSession(sessionId) {
  if (!sessionId) return;
  try {
    await request(`/image-sessions/${sessionId}/archive`, { method: "POST" });
    state.activeImageSession = null;
    renderActiveImageSession();
    toast("Начинаем новую серию.", "success");
  } catch (error) {
    toast(`Не удалось закрыть серию: ${error.message}`, "danger");
  }
}

function renderSyncPanel() {
  const hasTelegram = Number(state.user?.tg_id || 0) > 0 || (state.user?.connected_surfaces || []).includes("telegram");
  const syncTitle = $("[data-telegram-sync-title]");
  const syncCopy = $("[data-telegram-sync-copy]");
  const syncMeta = $("[data-telegram-sync-meta]");
  const webTitle = $("[data-web-contact-title]");
  const webCopy = $("[data-web-contact-copy]");
  const syncButton = $("[data-sync-connect]");
  const openBot = $("[data-sync-open-bot]");
  const username = state.user?.username ? `@${state.user.username}` : "";
  const botLink = state.authConfig?.bot_link || (state.authConfig?.bot_username ? `https://t.me/${state.authConfig.bot_username}` : "");
  if (syncTitle) syncTitle.textContent = hasTelegram ? `Telegram привязан ${username || "к этому кабинету"}` : "Telegram пока не привязан";
  if (syncCopy) syncCopy.textContent = hasTelegram
    ? "Этот Telegram используется для входа по коду, синхронных уведомлений и быстрого возврата в бота без расхождения по балансу и истории."
    : "Привяжите Telegram, чтобы получать коды входа в бот, открывать оплаты и быстро возвращаться в аккаунт без ручного поиска.";
  if (syncMeta) syncMeta.textContent = hasTelegram
    ? `Статус: привязан${username ? ` • аккаунт ${username}` : ""}. Если захотите сменить Telegram, выйдите из кабинета и войдите через другой аккаунт.`
    : "Статус: не привязан. После привязки сайт покажет, в какой Telegram-аккаунт уходят коды входа.";
  if (webTitle) webTitle.textContent = state.user?.email || state.user?.phone || state.user?.full_name || "Web-аккаунт";
  if (webCopy) webCopy.textContent = hasTelegram
    ? "Сайт остаётся главным рабочим интерфейсом, а Telegram становится понятным связанным каналом: вход, коды, уведомления и быстрый возврат."
    : "Сейчас кабинет работает только в web. Telegram можно явно привязать как связанный канал для входа и уведомлений.";
  if (syncButton) {
    syncButton.hidden = false;
    if (hasTelegram) {
      syncButton.textContent = username ? `Привязан ${username}` : "Telegram привязан";
      syncButton.disabled = true;
    } else {
      syncButton.textContent = "Привязать Telegram";
      syncButton.disabled = false;
    }
  }
  if (openBot) {
    openBot.hidden = !botLink;
    if (botLink) openBot.href = botLink;
  }
}

function renderAccount() {
  if (state.generationStatus) syncStudioResultStage();
  else setAccountPreview(0);
  renderSyncPanel();
  renderQueue();
  renderLibrary();
  renderBilling();
  renderReferrals();
  renderPrompts();
  renderFeedPanel();
  renderAssistant();
  renderSettings();
  renderProfile();
  renderAdmin();
  renderActiveImageSession();
}

function queueItems() {
  return state.queue.slice(0, 8);
}

function renderQueue() {
  const queues = $$('[data-account-queue]');
  if (!queues.length) return;
  const items = queueItems();
  const html = items.length ? items.map((item, index) => {
    const active = generationIsActive(item.status);
    const progress = generationProgressValue(item);
    return `
      <article class="queue-card${active ? " is-working" : ""}">
        <img src="${escapeHtml(item.preview || item.preview_url || item.image || item.result_url || fallbackImage(index))}" loading="lazy" decoding="async" alt="">
        <div>
          <span>${escapeHtml(statusLabel(item.status || "queued"))} · ${escapeHtml(cleanModelName(item.model))}</span>
          <b>${escapeHtml(item.title || `Работа #${item.id || index + 1}`)}</b>
          <p>${escapeHtml(active ? `${generationStatusCopy(item.status)}. Можно продолжать работу, мы обновим результат автоматически.` : item.prompt || "Работа добавлена и скоро будет готова.")}</p>
        </div>
        <div class="progress" aria-label="Прогресс ${progress}%">
          <i style="width: ${Math.min(100, Math.max(8, Number(progress)))}%"></i>
        </div>
      </article>
    `;
  }).join("") : `<div class="empty-state">Активных задач пока нет. Запустите генерацию в Studio, и она появится здесь.</div>`;
  queues.forEach((queue) => { queue.innerHTML = html; });
}

function renderLibrary() {
  const libraries = $$('[data-account-library]');
  if (!libraries.length) return;
  libraries.forEach((library) => library.classList.add('library-board'));
  const items = state.history;
  const html = items.length ? items.map((item, index) => {
    const openUrl = safeUrl(item.result_url || item.image || (Array.isArray(item.result_urls) ? item.result_urls[0] : ""));
    const openAttrs = mediaOpenAttrs(mediaOriginalUrls(item, index), 0);
    const isImage = String(item.gen_type || item.type || "image").toLowerCase() === "image";
    const title = item.title || cleanModelName(item.model) || `Работа #${item.id || index + 1}`;
    return `
      <article class="library-card">
        ${openUrl ? mediaHtml(item, index) : `<figure class="library-placeholder"><span>${escapeHtml(statusLabel(item.status))}</span><b>Файл пока недоступен</b></figure>`}
        <div>
          <b>${escapeHtml(title)}</b>
          <span>${escapeHtml(cleanModelName(item.model))} · ${escapeHtml(item.status ? statusLabel(item.status) : `${formatNumber(item.likes)} лайков`)}</span>
          <div class="card-actions">
            ${openUrl ? `<button type="button" ${openAttrs}>Открыть</button>` : ""}
            ${openUrl && Number(item.id) ? `<button type="button" data-download-generation="${escapeHtml(item.id)}" data-download-name="${escapeHtml(title)}">Скачать</button>` : ""}
            ${Number(item.id) ? `<button type="button" data-generation-action="repeat" data-generation-id="${item.id}">Повторить</button>` : ""}
            ${Number(item.id) && openUrl && isImage ? `<button type="button" data-generation-action="variant" data-generation-id="${item.id}">Вариант</button>` : ""}
            ${Number(item.id) && openUrl && isImage ? `<button type="button" data-generation-action="animate" data-generation-id="${item.id}">Видео</button>` : ""}
            ${Number(item.id) ? `<button type="button" data-generation-action="share" data-generation-id="${item.id}">Ссылка</button>` : ""}
            ${Number(item.id) ? `<button type="button" data-generation-action="publish" data-generation-id="${item.id}">В ленту</button>` : ""}
            ${Number(item.id) && item.isPublicFeed ? `<button type="button" data-generation-action="remove-feed" data-generation-id="${item.id}">Снять</button>` : ""}
            ${Number(item.id) ? `<button type="button" data-generation-action="share-library" data-generation-id="${item.id}">В библиотеку</button>` : ""}
            ${Number(item.id) ? `<button type="button" data-generation-action="remove-library" data-generation-id="${item.id}">Убрать</button>` : ""}
          </div>
        </div>
      </article>
    `;
  }).join("") : `<div class="empty-state">История появится после первой генерации.</div>`;
  libraries.forEach((library) => { library.innerHTML = html; });
}

function generationIsActive(status) {
  return ["pending", "processing", "queued", "running", "created", "uploading"].includes(String(status || "").toLowerCase());
}

function generationStatusCopy(status) {
  const value = String(status || "queued").toLowerCase();
  if (value === "uploading") return "Загружаем референс";
  if (value === "created") return "Задача принята";
  if (value === "pending" || value === "queued") return "Ожидает свободный слот";
  if (value === "processing" || value === "running") return "Модель создает результат";
  if (value === "done") return "Готово";
  if (value === "failed") return "Не получилось";
  return "Готовим задачу";
}

function generationProgressValue(item = {}) {
  if (Number.isFinite(Number(item.progress))) return Number(item.progress);
  const status = String(item.status || "").toLowerCase();
  if (status === "uploading") return 14;
  if (status === "created") return 22;
  if (status === "pending" || status === "queued") return 34;
  if (status === "processing" || status === "running") return 72;
  if (status === "done") return 100;
  if (status === "failed") return 100;
  return 24;
}

function stopGenerationStatusPolling() {
  if (state.generationStatusPollTimer) {
    clearTimeout(state.generationStatusPollTimer);
    state.generationStatusPollTimer = null;
  }
}

async function pollGenerationStatusNow(id) {
  if (!id) return;
  try {
    const result = await request(`/generations/${id}`);
    mergeGeneration(result);
  } catch (_) {
    // keep silent; next retry may succeed
  }
}

function ensureGenerationStatusPolling(id) {
  stopGenerationStatusPolling();
  if (!id) return;
  const tick = async () => {
    const current = state.generationStatus;
    if (!current || Number(current.id) !== Number(id) || !generationIsActive(current.status)) {
      stopGenerationStatusPolling();
      return;
    }
    await pollGenerationStatusNow(id);
    const next = state.generationStatus;
    if (next && Number(next.id) === Number(id) && generationIsActive(next.status)) {
      const nextDelay = state.socket ? 10000 : 3500;
      state.generationStatusPollTimer = setTimeout(tick, nextDelay);
    } else {
      stopGenerationStatusPolling();
    }
  };
  state.generationStatusPollTimer = setTimeout(tick, 2500);
}

function setGenerationStatus(update = null) {
  state.generationStatus = update ? { ...(state.generationStatus || {}), ...update, updatedAt: Date.now() } : null;
  if (!state.generationStatus) {
    stopGenerationStatusPolling();
  } else if (generationIsActive(state.generationStatus.status) && Number(state.generationStatus.id)) {
    ensureGenerationStatusPolling(Number(state.generationStatus.id));
  } else {
    stopGenerationStatusPolling();
  }
  syncStudioResultStage();
  renderGenerationStatus();
}

function renderGenerationStatus() {
  const status = state.generationStatus;
  $$("[data-generation-status]").forEach((slot) => {
    if (!status) {
      slot.hidden = true;
      slot.innerHTML = "";
      return;
    }
    const active = generationIsActive(status.status);
    const failed = String(status.status || "").toLowerCase() === "failed";
    const done = String(status.status || "").toLowerCase() === "done";
    const progress = Math.min(100, Math.max(8, generationProgressValue(status)));
    const resultUrl = safeUrl(status.image || status.result_url || status.resultUrl || status.result_urls?.[0]);
    const resultOpenAttrs = mediaOpenAttrs(mediaOriginalUrls(status), 0);
    const usesSideResultStage = Boolean($(".result-stage-clean"));
    slot.hidden = false;
    slot.classList.toggle("is-active", active);
    slot.classList.toggle("is-done", done);
    slot.classList.toggle("is-failed", failed);
    const inlineMedia = done && resultUrl && !usesSideResultStage
      ? (/\.(mp4|mov|webm)(\?|$)/i.test(resultUrl)
          ? `<video class="generation-live-media" src="${escapeHtml(resultUrl)}" controls playsinline preload="metadata"></video>`
          : `<img class="generation-live-media" src="${escapeHtml(resultUrl)}" alt="Готовый результат" loading="eager" referrerpolicy="no-referrer">`)
      : "";
    slot.innerHTML = `
      <div class="generation-live-orb" aria-hidden="true"></div>
      <div class="generation-live-copy">
        <span>${escapeHtml(generationStatusCopy(status.status))}</span>
        <b>${escapeHtml(status.title || (status.id ? `Работа #${status.id}` : "Новая генерация"))}</b>
        <p>${escapeHtml(done ? (usesSideResultStage ? "Результат готов и показан справа." : "Результат готов и показан прямо здесь.") : failed ? (status.error || "Кредиты вернутся автоматически, если провайдер не принял задачу.") : "Можно оставаться на странице: статус обновится автоматически.")}</p>
        <div class="progress generation-live-progress"><i style="width:${progress}%"></i></div>
        ${inlineMedia}
      </div>
      ${resultUrl ? `<button class="button ghost" type="button" ${resultOpenAttrs}>Открыть</button>` : ""}
    `;
  });
}

function renderBilling() {
  const grid = $("[data-billing-grid]");
  if (!grid) return;
  const balance = formatNumber(state.user?.credits || 0);
  const methods = enabledPaymentMethods();
  const pending = state.billing?.pending || [];
  const plans = Array.isArray(state.plans) ? state.plans : [];
  const methodButtons = (plan, featured = false) => {
    if (!methods.length) {
      return `<button class="button ghost" type="button" disabled>Оплата скоро</button>`;
    }
    return methods.map((method, index) => `
      <button
        class="button ${featured && index === 0 ? "primary" : "ghost"}"
        type="button"
        data-topup-provider="${escapeHtml(paymentMethodKey(method))}"
        data-topup-plan="${escapeHtml(plan.key)}"
      >${escapeHtml(paymentMethodLabel(method))}</button>
    `).join("");
  };
  grid.innerHTML = `
    <article>
      <span>Баланс</span>
      <b>${balance}</b>
      <p>${state.user
        ? `${methods.length ? methods.map(paymentMethodLabel).join(" / ") : "Способы оплаты скоро появятся"} · ожидают оплаты: ${pending.length}`
        : "Войдите, чтобы увидеть баланс."}</p>
      <i><em style="width: ${state.user ? "42" : "18"}%"></em></i>
    </article>
    ${plans.length ? plans.map((plan, index) => `
      <article>
        <span>${index === 1 ? "Популярный пакет" : "Пополнить"}</span>
        <b>${escapeHtml(plan.label || plan.title || plan.key)}</b>
        <p>${formatNumber(plan.credits)} на баланс · ${escapeHtml(plan.price_rub_display || formatCurrency(plan.price_rub || 0))}</p>
        <div class="pay-actions">
          ${methodButtons(plan, index === 1)}
        </div>
      </article>
    `).join("") : `<article><span>Пополнение</span><b>Пакеты недоступны</b><p>Backend не вернул тарифы. Статические demo-пакеты отключены.</p><div class="pay-actions"><button class="button ghost" type="button" disabled>Ожидаем backend</button></div></article>`}
  `;
}

function renderReferrals() {
  const root = $("[data-referral-panel]");
  if (!root) return;
  const ref = state.referrals;
  const counts = ref?.counts || { l1: 0, l2: 0, l3: 0 };
  const balance = ref?.balance || { available_to_withdraw: 0, total_earned: 0 };
  const exchangeRate = Number(ref?.exchange_rate_rub_per_credit || 10);
  const exchangeMin = Number(ref?.exchange_min_rub || 100);
  const exchangeSampleRub = exchangeRate > 0 ? exchangeRate * 10 : 100;
  const exchangeSampleCredits = exchangeRate > 0 ? exchangeSampleRub / exchangeRate : 10;
  root.innerHTML = `
    <div>
      <span>Рефералы</span>
      <h3>${ref ? "Приглашайте друзей и получайте бонусы" : "Пригласите друзей и получайте бонусы"}</h3>
      <p>${ref ? `Ссылка: ${escapeHtml(ref.referral_link || "")}` : "После входа здесь появятся ссылка, уровни, начисления, доступно к выводу и история заявок."}</p>
      ${ref?.referral_link ? `<button class="button ghost" type="button" data-copy-referral="${escapeHtml(ref.referral_link)}">Скопировать ссылку</button>` : ""}
      <div class="ref-actions">
        <form class="withdrawal-form ref-action" data-withdrawal-form>
          <div class="ref-action-head">
            <b>Вывести деньги</b>
            <p>Минимум ${formatNumber(ref?.withdraw_min_rub || 0)}₽, заявка уйдет администратору.</p>
          </div>
          <label><span>Сумма вывода, ₽</span><input name="amount_rub" type="number" min="1" step="1" placeholder="${escapeHtml(ref?.withdraw_min_rub || 0)}"></label>
          <label><span>Реквизиты</span><textarea name="payout_details" rows="2" placeholder="Карта, USDT, банк или другой способ"></textarea></label>
          <button class="button ghost" type="submit">Вывести деньги</button>
        </form>
        <form class="withdrawal-form ref-action" data-referral-exchange-form>
          <div class="ref-action-head">
            <b>Купить поцелуи</b>
            <p>${formatNumber(exchangeSampleRub)}₽ = ${formatNumber(exchangeSampleCredits)} поцелуев по стандартному тарифу.</p>
          </div>
          <label><span>Сумма обмена, ₽</span><input name="amount_rub" type="number" min="1" step="1" placeholder="${escapeHtml(exchangeMin)}"></label>
          <button class="button primary" type="submit">Купить поцелуи</button>
        </form>
      </div>
    </div>
    <div class="ref-stats">
      <article><b>${percentLabel(ref?.commission_l1, 30)}</b><span>L1 комиссия · ${counts.l1 || 0}</span></article>
      <article><b>${percentLabel(ref?.commission_l2, 7)}</b><span>L2 комиссия · ${counts.l2 || 0}</span></article>
      <article><b>${percentLabel(ref?.commission_l3, 3)}</b><span>L3 комиссия · ${counts.l3 || 0}</span></article>
      <article><b>${formatNumber(balance.available_to_withdraw || 0)}₽</b><span>доступно к выводу</span></article>
      ${(ref?.withdrawals || []).slice(0, 4).map((item) => `<article><b>${formatNumber(item.amount_rub)}₽</b><span>${escapeHtml(item.status)} · заявка #${escapeHtml(item.id)}</span></article>`).join("")}
    </div>
  `;
}

function renderPrompts() {
  const board = $("[data-prompts-board]");
  if (!board) return;
  const controls = `
    <div class="prompt-library-head">
      <div>
        <span>Библиотека промптов</span>
        <h3>Готовые идеи с реальными примерами</h3>
        <p>Как в mini app: выбирайте карточку, запускайте идею, ставьте лайк или открывайте превью.</p>
      </div>
      <div class="feed-toolbar feed-toolbar-compact">
        <button type="button" data-prompt-source="catalog" aria-pressed="${state.promptSource === "catalog" ? "true" : "false"}">Каталог</button>
        <button type="button" data-prompt-source="my" aria-pressed="${state.promptSource === "my" ? "true" : "false"}">Мои</button>
        <button type="button" data-prompt-source="top" aria-pressed="${state.promptSource === "top" ? "true" : "false"}">Топ</button>
      </div>
    </div>
  `;
  board.innerHTML = controls + (state.prompts.length ? state.prompts.map((prompt, index) => `
    <article class="feature-card prompt-list-card">
      <button class="prompt-preview-open" type="button" ${safeUrl(prompt.preview_url) ? mediaOpenAttrs([prompt.preview_url], 0) : ""}>
        ${promptPreviewHtml(prompt, index)}
      </button>
      <span>${escapeHtml(prompt.category || "идея")} · ♥ ${formatNumber(prompt.likes || 0)} · ${formatNumber(prompt.uses_count || 0)} исп.</span>
      <h3>${escapeHtml(prompt.title || `Идея #${prompt.id}`)}</h3>
      <p>${escapeHtml(prompt.description || prompt.prompt_text || "")}</p>
      <div class="card-actions prompt-actions">
        <button type="button" class="feed-action-main" data-use-prompt="${escapeHtml(prompt.id)}">Создать</button>
        <button type="button" data-like-prompt="${escapeHtml(prompt.id)}">♥ Лайк</button>
        ${safeUrl(prompt.preview_url) ? `<button type="button" ${mediaOpenAttrs([prompt.preview_url], 0)}>Открыть</button>` : ""}
      </div>
    </article>
  `).join("") : `<div class="empty-state">Идеи появятся после входа или обновления каталога.</div>`);
}

function renderAdmin() {
  const board = $("[data-admin-board]");
  if (!board) return;
  if (!state.user?.is_admin) {
    board.innerHTML = `<div class="empty-state">Раздел доступен администраторам.</div>`;
    return;
  }
  board.innerHTML = state.adminPrompts.length ? state.adminPrompts.map((prompt, index) => `
    <article class="feature-card admin-card">
      ${promptPreviewHtml(prompt, index)}
      <span>${escapeHtml(prompt.category || "идея")} · ${escapeHtml(prompt.status || "pending")}</span>
      <h3>${escapeHtml(prompt.title || `Идея #${prompt.id}`)}</h3>
      <p>${escapeHtml(prompt.description || prompt.prompt_text || "")}</p>
      <div class="card-actions">
        <button type="button" data-admin-prompt-action="approve" data-prompt-id="${escapeHtml(prompt.id)}">Одобрить</button>
        <button type="button" data-admin-prompt-action="reject" data-prompt-id="${escapeHtml(prompt.id)}">Отклонить</button>
        <button type="button" data-admin-prompt-action="deactivate" data-prompt-id="${escapeHtml(prompt.id)}">Скрыть</button>
      </div>
    </article>
  `).join("") : `<div class="empty-state">Новых идей на модерации нет.</div>`;
}

function feedCard(item, index = 0, variant = "panel") {
  const id = Number(item.id || 0);
  const title = feedItemTitle(item, index);
  const label = feedItemLabel(item);
  const promptText = "Промпт скрыт. Повтор использует настройки выбранной работы.";
  const rawAuthor = String(item.author || "anon").replace(/^@+/, "");
  const author = `@${rawAuthor || "anon"}`;
  const model = cleanModelName(item.model || "model");
  const mediaUrl = primaryMediaUrl(item);
  const mediaUrls = mediaOriginalUrls(item, index);
  const carouselUrls = variant === "gallery" ? feedCarouselUrls() : mediaUrls;
  const openUrls = carouselUrls.length ? carouselUrls : mediaUrls;
  const carouselIndex = variant === "gallery" ? feedCarouselIndex(item, index, 0, openUrls) : 0;
  const openAttrs = mediaOpenAttrs(openUrls, carouselIndex);
  if (variant === "gallery") {
    return `
      <article class="gallery-card feed-card feed-card-clean feed-pin-card">
        ${mediaHtml(item, index, { openUrls, openIndex: carouselIndex })}
        <div class="feed-pin-info">
          <div class="feed-tile-head">
            <span class="feed-author">${escapeHtml(author)}</span>
            <b class="model-badge">${escapeHtml(model)}</b>
          </div>
          <div class="feed-tile-stats">${feedCountsHtml(item)}</div>
          <div class="feed-clean-actions feed-tile-actions">
            ${mediaUrl ? `<button type="button" class="feed-action-ghost" ${openAttrs}>Открыть</button>` : ""}
            ${id ? `<button type="button" data-like-feed="${escapeHtml(id)}">♥ Лайк</button>` : ""}
            ${id ? `<button type="button" class="feed-action-main" data-remix-feed="${escapeHtml(id)}">Повторить</button>` : `<a class="feed-action-main" href="studio.html">Создать</a>`}
          </div>
        </div>
      </article>
    `;
  }
  const className = "feature-card feed-card";
  return `
    <article class="${className} feed-pin-card">
      ${mediaHtml(item, index, { openUrls, openIndex: 0 })}
      <div class="feed-pin-info">
        <div class="feed-tile-head">
          <span class="feed-author">${escapeHtml(author)}</span>
          <b class="model-badge">${escapeHtml(model)}</b>
        </div>
        <div class="feed-tile-stats">${feedCountsHtml(item)}</div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(promptText)}</p>
        <div class="card-actions feed-actions">
          ${mediaUrl ? `<button class="feed-action" type="button" ${openAttrs}>Открыть</button>` : ""}
          ${id ? `<button class="feed-action" type="button" data-like-feed="${escapeHtml(id)}">Лайк</button>` : ""}
          ${id ? `<button class="feed-action" type="button" data-share-feed="${escapeHtml(id)}">Поделиться</button>` : ""}
          ${id ? `<button class="feed-action-main" type="button" data-remix-feed="${escapeHtml(id)}">Повторить</button>` : `<a class="feed-action-main" href="studio.html">Создать</a>`}
        </div>
      </div>
    </article>
  `;
}

function renderFeedPanel() {
  const board = $("[data-feed-board]");
  if (!board) return;
  const controls = `
    <div class="feed-panel-intro">
      <span>Лента</span>
      <h3>Работы, которые можно повторить или развить</h3>
      <p>Лайкайте удачные кадры, делитесь ими и запускайте похожий результат в свою очередь.</p>
      <div class="feed-toolbar feed-toolbar-compact">
        <button type="button" data-feed-source="feed" aria-pressed="${state.feedSource === "feed" ? "true" : "false"}">Все</button>
        <button type="button" data-feed-source="top_day" aria-pressed="${state.feedSource === "top_day" ? "true" : "false"}">Топ дня</button>
      </div>
    </div>
  `;
  board.innerHTML = state.examples.length ? `
    ${controls}
    <div class="feed-masonry account-feed-masonry">
      ${state.examples.map((item, index) => feedCard(item, index, "panel")).join("")}
    </div>
  ` : `${controls}<div class="empty-state">Лента пока пустая.</div>`;
  renderGallery();
}

function renderAssistant() {
  const log = $("[data-assistant-log]");
  if (!log) return;
  log.innerHTML = state.assistantHistory.length
    ? state.assistantHistory.map((item) => `<div class="assistant-msg ${item.role === "user" ? "user" : ""}">${escapeHtml(item.content)}</div>`).join("")
    : `<div class="assistant-msg">Я помогу превратить идею в понятное описание, выбрать формат результата и подготовить запуск.</div>`;
}

function renderSettings() {
  const panel = $("[data-help-panel]");
  syncLanguageUi();
  if (!panel) return;
  const activeTopic = state.help?.topic || "main";
  panel.innerHTML = state.help
    ? `
      <div class="settings-actions help-topic-actions">
        <button class="button ghost${activeTopic === "main" ? " active" : ""}" type="button" data-help-topic="main" aria-pressed="${activeTopic === "main" ? "true" : "false"}">Кабинет</button>
        <button class="button ghost${activeTopic === "stars" ? " active" : ""}" type="button" data-help-topic="stars" aria-pressed="${activeTopic === "stars" ? "true" : "false"}">Stars</button>
      </div>
      <article class="help-card"><span>${escapeHtml(state.help.topic)} · ${escapeHtml(state.help.language)}</span><p>${escapeHtml(state.help.text)}</p></article>
    `
    : `
      <div class="settings-actions help-topic-actions">
        <button class="button ghost active" type="button" data-help-topic="main" aria-pressed="true">Кабинет</button>
        <button class="button ghost" type="button" data-help-topic="stars" aria-pressed="false">Stars</button>
      </div>
      <article class="help-card"><span>Помощь</span><p>Войдите и выберите тему. Здесь появятся короткие подсказки по кабинету, балансу и созданию работ.</p></article>
    `;
}

function renderProfile() {
  const form = $("[data-profile-form]");
  if (form && state.user) {
    const fields = ["full_name", "username", "email", "phone", "photo_url"];
    fields.forEach((name) => {
      const input = form.querySelector(`[name='${name}']`);
      if (input) input.value = state.user[name] || "";
    });
  }
  const passwordForm = $("[data-password-form]");
  if (passwordForm) {
    const hasPassword = Boolean(state.user?.has_password);
    const currentRow = passwordForm.querySelector("[data-current-password-row]");
    const current = passwordForm.querySelector("[name='current_password']");
    const status = passwordForm.querySelector("[data-password-status]");
    if (currentRow) currentRow.hidden = !hasPassword;
    if (current) current.required = hasPassword;
    if (status) status.textContent = hasPassword
      ? "Пароль включён. Для смены укажите текущий пароль."
      : "Пароль ещё не задан. Создайте его для входа без Telegram.";
  }
}

async function submitProfile(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const data = new FormData(form);
  const body = {
    full_name: String(data.get("full_name") || "").trim() || null,
    username: String(data.get("username") || "").trim() || null,
    email: String(data.get("email") || "").trim() || null,
    phone: String(data.get("phone") || "").trim() || null,
    photo_url: String(data.get("photo_url") || "").trim() || null,
  };
  try {
    state.user = await request("/me/profile", { method: "PUT", body: JSON.stringify(body) });
    renderAuth();
    renderAccount();
    toast("Профиль обновлён.", "success");
  } catch (error) {
    toast(`Не удалось сохранить профиль: ${error.message}`, "danger");
  }
}

async function submitPassword(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const data = new FormData(form);
  const newPassword = String(data.get("new_password") || "");
  const confirm = String(data.get("new_password_confirm") || "");
  if (newPassword !== confirm) {
    toast("Пароли не совпадают.", "danger");
    return;
  }
  try {
    state.user = await request("/me/password", {
      method: "PUT",
      body: JSON.stringify({
        current_password: String(data.get("current_password") || "") || null,
        new_password: newPassword,
      }),
    });
    form.reset();
    renderProfile();
    renderAuth();
    toast("Пароль обновлён.", "success");
  } catch (error) {
    toast(`Не удалось обновить пароль: ${error.message}`, "danger");
  }
}

function ensurePasswordAuthForms() {
  $$("[data-login-modal] .auth-methods").forEach((root) => {
    root.querySelectorAll("[data-contact-login-form]").forEach((form) => {
      form.hidden = true;
      form.setAttribute("aria-hidden", "true");
    });
    if (root.querySelector("[data-password-auth-panel]")) return;
    const panel = document.createElement("div");
    panel.className = "password-auth-panel";
    panel.dataset.passwordAuthPanel = "true";
    panel.innerHTML = `
      <form class="contact-auth-form password-auth-form" data-password-login-form>
        <span>Почта и пароль</span>
        <label><input name="login" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com" required /></label>
        <label><input name="password" type="password" autocomplete="current-password" placeholder="Пароль" minlength="8" required /></label>
        <button class="button primary" type="submit">Войти</button>
        <small data-password-login-status>Для сайта используйте email и пароль от кабинета.</small>
      </form>
      <details class="auth-register-panel">
        <summary>
          <span>Нет аккаунта?</span>
          <b>Создать по email</b>
        </summary>
        <form class="contact-auth-form password-auth-form" data-password-register-form>
          <span>Новый аккаунт</span>
          <label><input name="full_name" type="text" autocomplete="name" placeholder="Ваше имя" /></label>
          <label><input name="email" type="email" autocomplete="email" placeholder="you@example.com" required /></label>
          <label><input name="password" type="password" autocomplete="new-password" placeholder="Пароль от 8 символов" minlength="8" required /></label>
          <button class="button ghost" type="submit">Создать аккаунт</button>
          <small data-password-register-status>После регистрации откроется профиль сайта.</small>
        </form>
      </details>
    `;
    const telegramPanel = root.querySelector(".telegram-auth-panel");
    root.insertBefore(panel, telegramPanel || null);
  });
}

async function passwordLogin(form) {
  const status = form.querySelector("[data-password-login-status]");
  const data = new FormData(form);
  try {
    const result = await request("/auth/password-login", {
      method: "POST",
      body: JSON.stringify({
        login: String(data.get("login") || "").trim(),
        password: String(data.get("password") || ""),
      }),
    });
    state.token = "";
    state.user = result.user;
    localStorage.removeItem(TOKEN_KEY);
    toast("Вход выполнен.", "success");
    await loadPrivate();
    finalizeAuth("queue");
  } catch (error) {
    if (status) status.textContent = `Не удалось войти: ${error.message}`;
  }
}

async function passwordRegister(form) {
  const status = form.querySelector("[data-password-register-status]");
  const data = new FormData(form);
  try {
    const result = await request("/auth/password-register", {
      method: "POST",
      body: JSON.stringify({
        full_name: String(data.get("full_name") || "").trim() || null,
        email: String(data.get("email") || "").trim(),
        password: String(data.get("password") || ""),
      }),
    });
    state.token = "";
    state.user = result.user;
    localStorage.removeItem(TOKEN_KEY);
    toast("Аккаунт создан.", "success");
    await loadPrivate();
    finalizeAuth("profile");
  } catch (error) {
    if (status) status.textContent = `Не удалось создать аккаунт: ${error.message}`;
  }
}

function syncContactAuthUi() {
  ensurePasswordAuthForms();
  $$('[data-contact-login-form]').forEach((form) => {
    form.hidden = true;
    form.setAttribute("aria-hidden", "true");
    const name = form.querySelector('input[name="full_name"]');
    if (name) {
      name.hidden = true;
      name.disabled = true;
    }
  });
  $$('[data-auth-fallback]').forEach((node) => {
    if (node.textContent) return;
    node.hidden = true;
  });
}

function resetLoginForms() {
  $$('[data-contact-login-form]').forEach((form) => {
    delete form.dataset.contact;
    const contact = form.querySelector('[name="contact"]');
    const code = form.querySelector('[name="code"]');
    const name = form.querySelector('[name="full_name"]');
    const submit = form.querySelector('[data-contact-submit]');
    const requestButton = form.querySelector('[data-contact-request]');
    const status = form.querySelector('[data-contact-login-status]');
    if (contact) contact.value = '';
    if (code) {
      code.value = '';
      code.disabled = true;
    }
    if (name && !name.disabled) name.value = '';
    if (submit) submit.disabled = true;
    if (requestButton && !requestButton._contactCooldownTimer) requestButton.disabled = false;
    if (status) status.textContent = state.authConfig?.contact_login_hint || 'Введите email или @username для входа по коду.';
  });
  $$("[data-password-login-form], [data-password-register-form]").forEach((form) => {
    form.reset();
  });
  $$("[data-password-login-status]").forEach((node) => {
    node.textContent = "Для сайта используйте email и пароль от кабинета.";
  });
  $$("[data-password-register-status]").forEach((node) => {
    node.textContent = "После регистрации откроется профиль сайта.";
  });
}

function finalizeAuth(entry = 'queue') {
  closeLogin();
  if (location.pathname === '/login') {
    history.replaceState(null, '', `/account#${entry}`);
  }
  if ($('[data-account-tabs]')) activateAccountTab(entry, { updateHash: true });
}

function openLogin() {
  const modal = $("[data-login-modal]");
  if (!modal) return;
  ensurePasswordAuthForms();
  resetLoginForms();
  modal.hidden = false;
  injectTelegramWidget();
}

function closeLogin() {
  const modal = $("[data-login-modal]");
  if (modal) modal.hidden = true;
}

function openHistoryModal() {
  if (!state.user) {
    openLogin();
    toast("Сначала войдите.", "info");
    return;
  }
  renderQueue();
  renderLibrary();
  const modal = $("[data-history-modal]");
  if (modal) modal.hidden = false;
}

function closeHistoryModal() {
  const modal = $("[data-history-modal]");
  if (modal) modal.hidden = true;
}

async function injectTelegramWidget() {
  const slot = $("[data-telegram-slot]");
  const fallback = $("[data-auth-fallback]");
  if (!slot) return;
  if (!state.authConfig) {
    state.authConfig = await optionalRequest("/auth/config", null);
  syncContactAuthUi();
  }
  syncContactAuthUi();
  const bot = state.authConfig?.bot_username;
  if (!bot) {
    if (fallback) {
      fallback.hidden = false;
      fallback.innerHTML = state.fallbackMode
        ? "Вход доступен на рабочем домене сайта."
        : "Telegram не отдал кнопку входа. Используйте вход по email и паролю слева.";
    }
    return;
  }
  if (slot.dataset.loaded === bot) return;
  slot.dataset.loaded = bot;
  slot.innerHTML = "";
  if (fallback) {
    fallback.hidden = true;
    fallback.textContent = "";
  }
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://telegram.org/js/telegram-widget.js?22";
  script.setAttribute("data-telegram-login", bot);
  script.setAttribute("data-size", "large");
  script.setAttribute("data-radius", "8");
  script.setAttribute("data-onauth", "onTelegramAuth(user)");
  script.setAttribute("data-request-access", "write");
  script.addEventListener("error", () => {
    slot.dataset.loaded = "";
    if (fallback) {
      const botLink = state.authConfig?.bot_link;
      fallback.hidden = false;
      fallback.innerHTML = botLink
        ? `Telegram сейчас недоступен. <a class="button ghost" href="${botLink}" target="_blank" rel="noopener">Открыть бота</a>`
        : "Telegram сейчас недоступен. Используйте вход по email и паролю слева.";
    }
  });
  slot.appendChild(script);
  window.setTimeout(() => {
    if (slot.dataset.loaded === bot && !slot.querySelector("iframe") && fallback) {
      const botLink = state.authConfig?.bot_link;
      fallback.hidden = false;
      fallback.innerHTML = botLink
        ? `Если кнопка Telegram не появилась, <a class="button ghost" href="${botLink}" target="_blank" rel="noopener">откройте бота напрямую</a> или войдите по email и паролю.`
        : "Если кнопка Telegram не появилась, используйте вход по email и паролю слева.";
    }
  }, 3500);
}

window.onTelegramAuth = async (user) => {
  try {
    const result = await request("/auth/telegram-login", { method: "POST", body: JSON.stringify(user) });
    state.token = "";
    state.user = result.user;
    localStorage.removeItem(TOKEN_KEY);
    toast("Вход выполнен. Ваш кабинет открыт.", "success");
    await loadPrivate();
    finalizeAuth("queue");
  } catch (error) {
    toast(`Ошибка входа: ${error.message}`, "danger");
  }
};

function startContactCooldown(form, seconds) {
  const button = form?.querySelector("[data-contact-request]");
  if (!button) return;
  const original = button.dataset.originalLabel || button.textContent || "Получить код";
  button.dataset.originalLabel = original;
  const finishAt = Date.now() + (Math.max(0, Number(seconds) || 0) * 1000);
  if (button._contactCooldownTimer) clearInterval(button._contactCooldownTimer);
  const tick = () => {
    const left = Math.max(0, Math.ceil((finishAt - Date.now()) / 1000));
    if (left <= 0) {
      button.disabled = false;
      button.textContent = original;
      if (button._contactCooldownTimer) clearInterval(button._contactCooldownTimer);
      button._contactCooldownTimer = null;
      return;
    }
    button.disabled = true;
    button.textContent = `Повтор через ${left}с`;
  };
  tick();
  button._contactCooldownTimer = setInterval(tick, 1000);
}

async function requestContactCode(form) {
  if (!state.authConfig?.contact_login) {
    const status = form.querySelector("[data-contact-login-status]");
    if (status) status.textContent = state.authConfig?.contact_login_hint || "Сейчас доступен вход по коду через email или Telegram.";
    return;
  }
  const status = form.querySelector("[data-contact-login-status]");
  const button = form.querySelector("[data-contact-request]");
  const contact = String(new FormData(form).get("contact") || "").trim();
  if (!contact) {
    if (status) status.textContent = state.authConfig?.contact_login_hint || "Укажите email или @username Telegram.";
    return;
  }
  if (button) button.disabled = true;
  if (status) status.textContent = "Отправляем код...";
  try {
    const result = await request("/auth/contact/request", {
      method: "POST",
      body: JSON.stringify({ contact }),
    });
    form.dataset.contact = result.contact || contact;
    const codeInput = form.querySelector("[name='code']");
    if (codeInput) {
      codeInput.disabled = false;
      codeInput.focus();
      if (result.debug_code) codeInput.value = result.debug_code;
    }
    const submit = form.querySelector("[data-contact-submit]");
    if (submit) submit.disabled = false;
    if (status) {
      status.textContent = result.debug_code
        ? `Код для входа: ${result.debug_code}`
        : (result.message || "Код отправлен. Введите его ниже.");
    }
    if (result.retry_after) startContactCooldown(form, result.retry_after);
  } catch (error) {
    if (status) status.textContent = `Не удалось отправить код: ${error.message}`;
  } finally {
    if (button && !button._contactCooldownTimer) button.disabled = false;
  }
}

async function verifyContactCode(form) {
  if (!state.authConfig?.contact_login) {
    const status = form.querySelector("[data-contact-login-status]");
    if (status) status.textContent = state.authConfig?.contact_login_hint || "Сейчас доступен вход по коду через email или Telegram.";
    return;
  }
  const status = form.querySelector("[data-contact-login-status]");
  const data = new FormData(form);
  const contact = form.dataset.contact || String(data.get("contact") || "").trim();
  const code = String(data.get("code") || "").trim();
  const fullName = String(data.get("full_name") || "").trim();
  if (!contact) {
    if (status) status.textContent = "Сначала укажи email или @username и запроси код.";
    return;
  }
  if (!code) {
    if (status) status.textContent = "Введите код из письма или сообщения бота.";
    return;
  }
  if (status) status.textContent = "Проверяем код...";
  try {
    const result = await request("/auth/contact/verify", {
      method: "POST",
      body: JSON.stringify({ contact, code, full_name: fullName || null }),
    });
    state.token = "";
    state.user = result.user;
    localStorage.removeItem(TOKEN_KEY);
    toast("Вход выполнен. Кабинет открыт.", "success");
    await loadPrivate();
    finalizeAuth("queue");
  } catch (error) {
    if (status) status.textContent = `Не удалось войти: ${error.message}`;
  }
}

function logout() {
  request("/auth/logout", { method: "POST" }).catch(() => {});
  localStorage.removeItem(TOKEN_KEY);
  state.token = "";
  state.user = null;
  state.queue = [];
  state.history = [];
  state.billing = null;
  state.referrals = null;
  state.help = null;
  state.adminPrompts = [];
  closeRealtime();
  closeLogin();
  resetLoginForms();
  if (location.pathname === '/login') {
    history.replaceState(null, '', '/account');
  }
  renderAuth();
  renderAccount();
  toast("Вы вышли из кабинета.", "info");
}

function mergeGeneration(item) {
  const gen = normalizeExample(item);
  gen.status = item.status || gen.status;
  gen.title = gen.title || `Работа #${gen.id}`;
  const id = Number(gen.id);
  const queueIndex = state.queue.findIndex((entry) => Number(entry.id) === id);
  const historyIndex = state.history.findIndex((entry) => Number(entry.id) === id);
  const previousEntry = queueIndex >= 0 ? state.queue[queueIndex] : (historyIndex >= 0 ? state.history[historyIndex] : null);
  const previousStatus = String(
    (previousEntry?.status)
    || ((state.generationStatus && Number(state.generationStatus.id) === id) ? state.generationStatus.status : "")
    || ""
  ).toLowerCase();
  const watchingSame = !state.generationStatus || Number(state.generationStatus.id) === id;
  if (generationIsActive(gen.status)) {
    if (queueIndex >= 0) state.queue[queueIndex] = { ...state.queue[queueIndex], ...gen };
    else state.queue.unshift(gen);
  } else {
    state.queue = state.queue.filter((entry) => Number(entry.id) !== id);
    if (historyIndex >= 0) state.history[historyIndex] = { ...state.history[historyIndex], ...gen };
    else state.history.unshift(gen);
  }
  state.queue = state.queue.slice(0, 16);
  state.history = state.history.slice(0, 48);
  if (watchingSame) {
    setGenerationStatus({ ...gen, resultUrl: gen.image || gen.result_url });
  }
  notifyGenerationCompletion(gen, previousStatus);
}

function connectRealtime() {
  if (!state.user || state.socket) return;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/web/ws/generations`);
  state.socket = socket;
  socket.addEventListener("open", () => {
    if (state.token) socket.send(JSON.stringify({ type: "auth", token: state.token }));
  });
  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "generation.snapshot") (payload.items || []).forEach(mergeGeneration);
      if (payload.type === "generation.updated") mergeGeneration(payload);
      renderQueue();
      renderLibrary();
      renderGenerationStatus();
    } catch {
      // Ignore malformed realtime messages.
    }
  });
  socket.addEventListener("close", () => {
    if (state.socket === socket) state.socket = null;
    if (state.user) setTimeout(connectRealtime, 5000);
  });
}

function closeRealtime() {
  if (!state.socket) return;
  const socket = state.socket;
  state.socket = null;
  socket.close();
}

async function uploadReference(file) {
  const form = new FormData();
  form.append("file", file);
  const result = await request("/uploads/reference", { method: "POST", body: form });
  return result.url;
}

async function uploadReferences(files = []) {
  const cleanFiles = files.filter((file) => file && file.size > 0);
  if (!cleanFiles.length) return [];
  const urls = [];
  for (const file of cleanFiles) {
    urls.push(await uploadReference(file));
  }
  return urls;
}

async function submitGeneration(form) {
  if (!state.user) {
    openLogin();
    toast("Сначала войдите.", "info");
    return;
  }
  const data = new FormData(form);
  const model = currentModel();
  const basePrompt = String(data.get("prompt") || "").trim();
  const params = new URLSearchParams(location.search);
  const feedRemixId = state.routeFeedRemixId || params.get("feed_remix") || "";
  const feedSourceRef = state.routeSourceReferenceUrl || params.get("source_ref") || "";
  const feedRemixMode = isFeedRemixMode();
  const injectedPrompt = promptWithInjections(form, basePrompt);
  const prompt = feedRemixMode ? basePrompt : injectedPrompt.prompt;
  if (!basePrompt && !feedRemixMode) {
    toast("Опишите, что нужно создать.", "danger");
    return;
  }
  const button = form.querySelector("[data-generate-button]") || $("[data-generate-button]");
  if (button) button.disabled = true;
  setGenerationStatus({
    id: "",
    status: "created",
    title: feedRemixMode ? "Повтор из ленты" : "Новая генерация",
    prompt: feedRemixMode ? "" : basePrompt,
    model: model?.key || model?.name || "",
    progress: 12,
  });
  try {
    const files = referenceFiles(form);
    let uploadedReferenceUrls = [];
    if (files.length) {
      setGenerationStatus({ status: "uploading", progress: 14 });
      uploadedReferenceUrls = await uploadReferences(files);
    }
    const allReferenceUrls = uniqueSafeUrls([
      ...uploadedReferenceUrls,
      ...referenceLinkValues(form),
    ]);
    const referenceUrl = allReferenceUrls[0] || "";
    const extraReferenceUrls = allReferenceUrls.slice(1);
    const videoUrl = String(data.get("video_url") || "").trim();
    const requestModel = requestModelForCurrentSetup(model, { referenceUrl, videoUrl });

    let body;
    let path;
    if (feedRemixMode && state.generationKind === "music") throw new Error("Повтор из ленты сейчас доступен только для изображений и видео");
    if (state.generationKind === "music") {
      path = "/generate/music";
      body = { prompt, instrumental: Boolean(data.get("instrumental")) };
    } else if (state.generationKind === "video") {
      path = feedRemixMode ? `/feed/${feedRemixId}/remix` : "/generate/video";
      body = {
        model: requestModel?.key,
        ...(feedRemixMode ? {} : { prompt }),
        mode: videoUrl ? "video" : "image",
        duration: Number(data.get("duration") || model?.durations?.[0] || 5),
        aspect_ratio: String(data.get("aspect_ratio") || "") || null,
        resolution: String(data.get("resolution") || "") || null,
        image_url: referenceUrl || null,
        source_image_url: feedRemixMode ? (feedSourceRef || null) : null,
        reference_urls: extraReferenceUrls,
        video_url: videoUrl || null,
        seed: data.get("seed") ? Number(data.get("seed")) : null,
        grok_mode: String(data.get("grok_mode") || "normal"),
      };
    } else {
      path = feedRemixMode ? `/feed/${feedRemixId}/remix` : "/generate/image";
      body = feedRemixMode
        ? {
            model: requestModel?.key,
            mode: "image",
            aspect_ratio: String(data.get("aspect_ratio") || "") || null,
            quality: String(data.get("quality") || "basic"),
            count: Number(data.get("count") || 1),
            image_url: referenceUrl || null,
            source_image_url: feedSourceRef || null,
            reference_urls: extraReferenceUrls,
          }
        : {
            model: requestModel?.key,
            prompt,
            aspect_ratio: String(data.get("aspect_ratio") || "") || null,
            quality: String(data.get("quality") || "basic"),
            count: Number(data.get("count") || 1),
            reference_url: referenceUrl || null,
            reference_urls: extraReferenceUrls,
          };
    }
    if (!body.model && state.generationKind !== "music") throw new Error("Модель недоступна");
    setGenerationStatus({
      status: "pending",
      title: feedRemixMode ? "Запускаем повтор из ленты" : "Отправляем задачу",
      model: body.model || "suno/v4.5",
      progress: 24,
    });
    const result = await request(path, { method: "POST", body: JSON.stringify(body) });
    mergeGeneration({ ...result, prompt: feedRemixMode ? "" : basePrompt, model: body.model || "suno/v4.5", image: fallbackImage(0), title: `Работа #${result.id || result.generation_id || ""}` });
    renderQueue();
    renderLibrary();
    renderGenerationStatus();
    document.querySelector("[data-account-tabs] [data-tab='queue']")?.click();
    toast("Задача запущена. Статус будет обновляться здесь.", "success");
    await loadPrivate({ quiet: true });
    pollQueue();
  } catch (error) {
    setGenerationStatus({ status: "failed", error: error.message, progress: 100 });
    toast(`Ошибка генерации: ${error.message}`, "danger");
  } finally {
    if (button && !button._contactCooldownTimer) button.disabled = false;
  }
}

async function improvePrompt(trigger = null) {
  if (!state.user) {
    openLogin();
    return;
  }
  const form = composerFromTrigger(trigger);
  const textarea = form?.querySelector("textarea[name='prompt']");
  const prompt = textarea?.value.trim();
  if (!prompt) return;
  try {
    const result = await request("/prompt/improve", {
      method: "POST",
      body: JSON.stringify({ prompt, kind: state.generationKind }),
    });
    textarea.value = result.prompt || prompt;
    toast("Описание улучшено.", "success");
  } catch (error) {
    toast(`Не удалось улучшить описание: ${error.message}`, "danger");
  }
}

async function pollQueue() {
  if (!state.user || !state.queue.length) return;
  await Promise.allSettled(state.queue.map(async (item) => {
    if (!Number(item.id)) return;
    const result = await request(`/generations/${item.id}`);
    mergeGeneration(result);
  }));
  renderQueue();
  renderLibrary();
  renderGenerationStatus();
  if (state.queue.length) setTimeout(pollQueue, 5500);
}

async function topup(provider, planKey) {
  if (!state.user) {
    openLogin();
    return;
  }
  if (!planKey || planKey.startsWith("demo_")) {
    toast("Войдите, чтобы увидеть доступные пакеты.", "info");
    return;
  }
  const activeMethods = enabledPaymentMethods();
  if (activeMethods.length && !activeMethods.some((method) => method.key === provider)) {
    toast("Этот способ оплаты сейчас недоступен.", "info");
    return;
  }
  try {
    const fallbackMethod = paymentMethodKey(enabledPaymentMethods()[0]) || "tbank";
    const method = ["tbank", "stars", "crypto", "lava"].includes(provider) ? provider : fallbackMethod;
    const result = await request(`/billing/topup/${method}`, { method: "POST", body: JSON.stringify({ plan_key: planKey }) });
    const url = result.pay_url || result.invoice_link;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
    else toast("Счёт создан.", "success");
  } catch (error) {
    toast(`Ошибка оплаты: ${error.message}`, "danger");
  }
}

async function generatePromptFromPhoto(trigger = null) {
  if (!state.user) {
    openLogin();
    return;
  }
  const formRoot = composerFromTrigger(trigger);
  const file = referenceFiles(formRoot)[0];
  const textarea = formRoot?.querySelector("textarea[name='prompt']");
  const button = trigger?.closest?.("[data-photo-prompt]") || formRoot?.querySelector("[data-photo-prompt]");
  if (!file) {
    toast("Выберите референс-файл в форме.", "info");
    updatePhotoPromptStatus(formRoot, "Сначала выберите фото");
    return;
  }
  try {
    if (button) button.disabled = true;
    updatePhotoPromptStatus(formRoot, "Считываем фото и готовим описание...");
    const form = new FormData();
    form.append("file", file);
    const result = await request("/photo-prompt", { method: "POST", body: form });
    const generatedPrompt = String(result?.prompt || "").trim();
    if (generatedPrompt) state.routePrompt = generatedPrompt;
    if (state.generationKind === "image") setGenerationFlow("reference", { updateRoute: true });
    const activeForm = document.querySelector(".account-composer");
    const activeTextarea = activeForm?.querySelector("textarea[name='prompt']");
    if (generatedPrompt && activeTextarea) {
      activeTextarea.value = generatedPrompt;
      activeTextarea.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (generatedPrompt && textarea) {
      textarea.value = generatedPrompt;
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }
    updatePhotoPromptStatus(document.querySelector(".account-composer") || formRoot, "Описание добавлено в поле выше");
    toast("Описание по фото готово.", "success");
  } catch (error) {
    updatePhotoPromptStatus(formRoot, "Не удалось получить описание");
    toast(`Не удалось разобрать фото: ${error.message}`, "danger");
  } finally {
    if (button && !button._contactCooldownTimer) button.disabled = false;
  }
}

async function handleGenerationAction(action, generationId) {
  if (!state.user) {
    openLogin();
    return;
  }
  if (["repeat", "variant", "animate"].includes(action)) {
    const item = (state.history || []).find((entry) => String(entry.id) === String(generationId));
    if (!item) return;
    const url = new URL('studio.html', window.location.href);
    const genType = String(item.gen_type || item.type || "image").toLowerCase();
    url.searchParams.set('type', action === "animate" ? "video" : (genType === 'video' ? 'video' : 'image'));
    if (item.model) url.searchParams.set('model', String(item.model));
    const prompt = item.sessionLastPrompt || item.prompt || "";
    if (prompt) url.searchParams.set('prompt', String(prompt));
    const originalRefs = uniqueSafeUrls(item.referenceUrls || []);
    const resultRefs = mediaOriginalUrls(item);
    const refs = action === "animate"
      ? resultRefs.slice(0, 1)
      : (originalRefs.length ? originalRefs : (action === "variant" ? resultRefs : []));
    if (item.sourceFeedGenId && action !== "animate") {
      url.searchParams.set('feed_remix', String(item.sourceFeedGenId));
      url.searchParams.set('flow', 'reference');
    }
    if (refs.length && (genType !== 'music' || action === "animate")) {
      url.searchParams.set('ref', refs[0]);
      if (refs.length > 1) url.searchParams.set('refs', refs.slice(1).join("\n"));
      if (action !== "animate" && genType === 'image') url.searchParams.set('flow', 'reference');
    }
    if (action === "animate") url.searchParams.delete('flow');
    if (action === "variant") url.searchParams.set('flow', 'reference');
    window.location.href = `${url.pathname}${url.search}`;
    return;
  }
  const allowed = {
    publish: "publish",
    share: "share",
    "share-library": "share-library",
    "remove-library": "remove-library",
  };
  const path = allowed[action];
  if (action === "remove-feed" && generationId) {
    try {
      await request(`/feed/${generationId}/remove`, { method: "POST" });
      toast("Работа снята с ленты.", "success");
      await loadPrivate({ quiet: true });
    } catch (error) {
      toast(`Не удалось снять с ленты: ${error.message}`, "danger");
    }
    return;
  }
  if (!path || !generationId) return;
  try {
    const result = await request(`/generations/${generationId}/${path}`, { method: "POST" });
    if (result?.link) navigator.clipboard?.writeText(result.link).catch(() => {});
    toast(result?.link ? "Готово. Ссылка скопирована." : "Действие выполнено.", "success");
    await loadPrivate({ quiet: true });
  } catch (error) {
    toast(`Ошибка действия: ${error.message}`, "danger");
  }
}

async function usePrompt(promptId) {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    const result = await request(`/prompts/${promptId}/use`, { method: "POST" });
    const prompt = result.prompt;
    const promptText = String(prompt?.prompt_text || "").trim();
    if (!promptText) throw new Error("Промпт пустой");
    const url = new URL("studio.html", window.location.href);
    url.searchParams.set("type", "image");
    url.searchParams.set("flow", "text");
    url.searchParams.set("prompt", promptText);
    if (prompt?.model) url.searchParams.set("model", String(prompt.model));
    window.location.href = `${url.pathname}${url.search}`;
  } catch (error) {
    toast(`Идея недоступна: ${error.message}`, "danger");
  }
}

async function likePrompt(promptId) {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    const result = await request(`/prompts/${promptId}/like`, { method: "POST" });
    if (result?.prompt) {
      state.prompts = state.prompts.map((item) => String(item.id) === String(promptId) ? result.prompt : item);
    } else {
      state.prompts = state.prompts.map((item) => String(item.id) === String(promptId) ? { ...item, likes: Number(item.likes || 0) + 1 } : item);
    }
    const promptPayload = await request(`/prompts?source=${encodeURIComponent(state.promptSource || "catalog")}&limit=${PROMPT_LIBRARY_LIMIT}`);
    state.prompts = promptPayload?.items || state.prompts;
    renderPrompts();
  } catch (error) {
    toast(`Не удалось поставить лайк: ${error.message}`, "danger");
  }
}

async function loadPrompts(source = "catalog") {
  if (source === "my" && !state.user) {
    openLogin();
    return;
  }
  try {
    const payload = await request(`/prompts?source=${encodeURIComponent(source)}&limit=${PROMPT_LIBRARY_LIMIT}`);
    state.promptSource = source;
    state.prompts = payload?.items || [];
    renderPrompts();
  } catch (error) {
    toast(`Не удалось загрузить промпты: ${error.message}`, "danger");
  }
}

async function likeFeed(feedId) {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    const result = await request(`/feed/${feedId}/like`, { method: "POST" });
    const likes = Number(result?.likes ?? result?.likes_count ?? 0);
    state.examples = state.examples.map((item) => {
      if (String(item.id) !== String(feedId)) return item;
      const nextLikes = likes || Number(item.likesCount || item.likes || 0) + 1;
      return { ...item, likes: nextLikes, likesCount: nextLikes };
    });
    renderGallery();
    renderFeedPanel();
    toast("Лайк поставлен.", "success");
  } catch (error) {
    toast(`Не удалось поставить лайк: ${error.message}`, "danger");
  }
}

async function shareFeed(feedId) {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    await request(`/feed/${feedId}/share`, { method: "POST" });
    const result = await request(`/feed/${feedId}/link`).catch(() => null);
    if (result?.link) {
      navigator.clipboard?.writeText(result.link).catch(() => {});
      toast("Ссылка на работу скопирована.", "success");
    } else {
      toast("Публикация отмечена как отправленная.", "success");
    }
    await loadPublic();
    renderGallery();
    renderFeedPanel();
  } catch (error) {
    toast(`Не удалось поделиться: ${error.message}`, "danger");
  }
}

async function remixFeed(feedId) {
  const item = state.examples.find((entry) => String(entry.id) === String(feedId));
  const ref = primaryMediaUrl(item || {});
  const url = new URL('studio.html', window.location.href);
  url.searchParams.set('type', 'image');
  url.searchParams.set('flow', 'reference');
  url.searchParams.set('feed_remix', String(feedId));
  if (ref) url.searchParams.set('source_ref', ref);
  url.searchParams.delete('ref');
  url.searchParams.delete('prompt');
  window.location.href = `${url.pathname}${url.search}`;
}

async function submitPrompt(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const data = Object.fromEntries(new FormData(form).entries());
  if (typeof data.tags === "string") {
    data.tags = data.tags.split(",").map((tag) => tag.trim()).filter(Boolean);
  }
  try {
    await request("/prompts", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    const promptPayload = await request("/prompts?limit=24");
    state.prompts = promptPayload?.items || state.prompts;
    renderPrompts();
    toast("Идея отправлена на модерацию.", "success");
  } catch (error) {
    toast(`Не удалось отправить идею: ${error.message}`, "danger");
  }
}

async function handleAdminPromptAction(action, promptId) {
  if (!state.user?.is_admin) return;
  try {
    const path = action === "reject" ? "reject" : action === "deactivate" ? "deactivate" : "approve";
    const options = path === "reject"
      ? { method: "POST", body: JSON.stringify({ reason: "Не подходит для публикации" }) }
      : { method: "POST" };
    await request(`/admin/prompts/${promptId}/${path}`, options);
    const payload = await request("/admin/prompts?status=pending");
    state.adminPrompts = payload?.items || [];
    renderAdmin();
    toast("Модерация обновлена.", "success");
  } catch (error) {
    toast(`Не удалось обновить идею: ${error.message}`, "danger");
  }
}

async function submitWithdrawal(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const data = new FormData(form);
  try {
    await request("/referrals/withdrawals", {
      method: "POST",
      body: JSON.stringify({
        amount_rub: Number(data.get("amount_rub") || 0),
        payout_details: String(data.get("payout_details") || "").trim(),
      }),
    });
    form.reset();
    const referrals = await request("/referrals");
    state.referrals = referrals;
    renderReferrals();
    toast("Заявка на вывод создана.", "success");
  } catch (error) {
    toast(`Не удалось создать заявку: ${error.message}`, "danger");
  }
}

async function submitReferralExchange(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const data = new FormData(form);
  try {
    const result = await request("/referrals/exchange", {
      method: "POST",
      body: JSON.stringify({
        amount_rub: Number(data.get("amount_rub") || 0),
      }),
    });
    form.reset();
    const referrals = await request("/referrals");
    state.referrals = referrals;
    renderReferrals();
    const credits = Number(result?.amount_credits || 0);
    toast(credits ? `Куплено ${formatNumber(credits)} поцелуев.` : "Баланс обменян в поцелуи.", "success");
  } catch (error) {
    toast(`Не удалось купить поцелуи: ${error.message}`, "danger");
  }
}

async function sendAssistant(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const textarea = form.querySelector("textarea[name='message']");
  const message = textarea?.value.trim();
  if (!message) return;
  state.assistantHistory.push({ role: "user", content: message });
  renderAssistant();
  form.reset();
  try {
    const result = await request("/assistant", {
      method: "POST",
      body: JSON.stringify({ message, history: state.assistantHistory.slice(-10) }),
    });
    state.assistantHistory.push({ role: "assistant", content: result.reply || "" });
    renderAssistant();
  } catch (error) {
    toast(`Ассистент недоступен: ${error.message}`, "danger");
  }
}

async function setLanguage(language) {
  if (!state.user) {
    openLogin();
    return;
  }
  const normalized = language === "en" ? "en" : "ru";
  try {
    await request("/settings/language", { method: "POST", body: JSON.stringify({ language: normalized }) });
    state.user.language = normalized;
    localStorage.setItem(LANG_KEY, normalized);
    syncLanguageUi();
    renderAuth();
    if (state.help) await loadHelp(state.help.topic || "main");
    toast(normalized === "en" ? "Account language updated." : "Язык аккаунта обновлён.", "success");
  } catch (error) {
    toast(`Не удалось сменить язык: ${error.message}`, "danger");
  }
}

async function loadHelp(topic = "main") {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    state.help = await request(`/help?topic=${encodeURIComponent(topic)}`);
    renderSettings();
  } catch (error) {
    toast(`Справка недоступна: ${error.message}`, "danger");
  }
}

function clearPublicData() {
  state.examples = [];
  state.prompts = [];
  state.plans = [];
  state.paymentMethods = [];
  state.models = [];
  state.modelsByKind = { image: [], video: [], music: [] };
}

async function loadFallbackData() {
  state.fallbackMode = true;
  clearPublicData();
}

async function ensureFallbackVisuals() {
  return;
}

function applyModelPayload(grouped = {}) {
  state.modelsByKind = {
    image: (grouped.image || []).map((model) => normalizeModel(model, "image")),
    video: (grouped.video || []).map((model) => normalizeModel(model, "video")),
    music: (grouped.music || []).map((model) => normalizeModel(model, "music")),
  };
  state.models = [
    ...state.modelsByKind.image,
    ...state.modelsByKind.video,
    ...state.modelsByKind.music,
  ];
}

function applyLandingPayload(payload = {}) {
  const promptPayload = payload.prompts || {};
  state.examples = (payload.examples || []).map(normalizeExample).filter((item) => item.image);
  state.prompts = (Array.isArray(promptPayload) ? promptPayload : promptPayload.items || []).slice(0, PROMPT_LIBRARY_LIMIT);
  state.plans = Array.isArray(payload.plans) ? payload.plans : state.plans;
  state.paymentMethods = Array.isArray(payload.payment_methods) ? payload.payment_methods : state.paymentMethods;
  applyModelPayload(payload.models || {});
}

async function loadPublic() {
  state.authConfig = await optionalRequest("/auth/config", null);
  try {
    applyLandingPayload(await request("/landing"));
  } catch {
    try {
      const [feed, modelPayload, promptPayload] = await Promise.all([
        request(`/feed?limit=${FULL_FEED_LIMIT}`),
        request("/models"),
        optionalRequest(`/prompts?limit=${PROMPT_LIBRARY_LIMIT}`, { items: [] }),
      ]);
      state.examples = (Array.isArray(feed) ? feed : feed.items || []).map(normalizeExample).filter((item) => item.image);
      state.prompts = (promptPayload?.items || []).slice(0, PROMPT_LIBRARY_LIMIT);
      state.plans = [];
      applyModelPayload(modelPayload || {});
    } catch {
      state.fallbackMode = true;
      clearPublicData();
    }
  }
  await ensureFallbackVisuals();
}

async function loadFeedSource(source = "feed") {
  const normalized = ["feed", "recent", "top", "top_day"].includes(source) ? source : "feed";
  try {
    const payload = await request(`/feed?source=${encodeURIComponent(normalized)}&limit=${FULL_FEED_LIMIT}`);
    state.feedSource = normalized;
    state.examples = (Array.isArray(payload) ? payload : payload.items || []).map(normalizeExample).filter((item) => item.image);
    renderGallery();
    renderFeedPanel();
  } catch (error) {
    toast(`Не удалось обновить ленту: ${error.message}`, "danger");
  }
}

async function loadPrivate({ quiet = false } = {}) {
  const me = await optionalRequest("/me", null);
  if (!me) {
    localStorage.removeItem(TOKEN_KEY);
    state.token = "";
    state.user = null;
    closeRealtime();
    renderAuth();
    renderAccount();
    if (!quiet) toast("Сессия истекла. Войдите снова.", "info");
    return;
  }
  state.user = me;
  const coreResults = await Promise.allSettled([
    request("/models/image"),
    request("/models/video"),
    request("/models/music"),
    request("/history?limit=48"),
    request("/generations/active"),
    request("/image-sessions/active"),
    request("/billing/plans"),
    request("/billing/transactions?limit=20"),
    optionalRequest("/billing/payment-methods", []),
    optionalRequest("/billing/payment-options", []),
  ]);
  const [imageModels, videoModels, musicModels, history, active, imageSession, plans, billing, methods, paymentOptions] = coreResults.map((result) => result.status === "fulfilled" ? result.value : null);
  state.modelsByKind = {
    image: (imageModels || []).map((model) => normalizeModel(model, "image")),
    video: (videoModels || []).map((model) => normalizeModel(model, "video")),
    music: (musicModels || []).map((model) => normalizeModel(model, "music")),
  };
  state.models = Object.values(state.modelsByKind).flat();
  state.history = (history || []).map(normalizeExample);
  state.queue = (active || []).map(normalizeExample);
  state.activeImageSession = imageSession || null;
  state.plans = Array.isArray(plans) ? plans : state.plans;
  state.billing = billing;
  state.paymentMethods = Array.isArray(methods) && methods.length ? methods : (billing?.methods || state.paymentMethods);
  state.paymentOptions = Array.isArray(paymentOptions) ? paymentOptions : state.paymentOptions;
  renderModels();
  applyGenerationPresetToComposer();
  renderAuth();
  renderAccount();
  syncAccountTabFromHash();
  syncActiveNavigation();
  refreshCustomSelects();
  connectRealtime();
  pollQueue();
  if (!quiet) toast("Кабинет обновлен.", "success");

  const extraResults = await Promise.allSettled([
    request("/referrals"),
    request("/prompts?limit=24"),
    request("/help?topic=main"),
    me.is_admin ? request("/admin/prompts?status=pending") : Promise.resolve({ items: [] }),
  ]);
  const [referrals, prompts, help, adminPrompts] = extraResults.map((result) => result.status === "fulfilled" ? result.value : null);
  state.referrals = referrals;
  state.prompts = prompts?.items || state.prompts;
  state.help = help || state.help;
  state.adminPrompts = adminPrompts?.items || [];
  renderAccount();
  syncAccountTabFromHash();
  refreshCustomSelects();
}

function bindFilters() {
  $$("[data-model-filter] button").forEach((button) => {
    button.addEventListener("click", () => {
      state.modelType = button.dataset.type || "all";
      $$("[data-model-filter] button").forEach((item) => item.classList.toggle("active", item === button));
      renderModels();
    });
  });
}

function bindAccountTabs() {
  $$("[data-account-tabs] button[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      activateAccountTab(button.dataset.tab || "billing", { updateHash: true });
    });
  });
  $$("[data-group-target]").forEach((button) => {
    button.addEventListener("click", () => {
      activateAccountTab(button.dataset.groupTarget || "billing", { updateHash: true });
    });
  });
  window.addEventListener("hashchange", syncAccountTabFromHash);
  syncAccountTabFromHash();
}

function activateAccountTab(tab, { updateHash = false } = {}) {
  const normalizedTab = tab === "workspace" ? "queue" : tab;
  const button = $(`[data-account-tabs] button[data-tab='${normalizedTab}']`);
  if (!button) return false;
  const titles = {
    queue: "Очередь и активные задачи",
    library: "История и файлы",
    feed: "Лента сообщества",
    prompts: "Промпты и идеи",
    profile: "Профиль и безопасность",
    assistant: "Ассистент",
    pro: "Telegram и синхрон",
    billing: "Баланс и пополнение",
    referrals: "Партнёрка и статистика",
    settings: "Настройки и помощь",
  };
  $$("[data-account-tabs] button").forEach((item) => item.classList.toggle("active", item === button));
  $$("[data-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === normalizedTab));
  const title = $("[data-account-title]");
  if (title) title.textContent = titles[normalizedTab] || normalizedTab;
  if (updateHash && location.hash !== `#${normalizedTab}`) {
    history.pushState(null, "", `#${normalizedTab}`);
  }
  syncActiveNavigation();
  refreshCustomSelects();
  return true;
}

function syncAccountTabFromHash() {
  const firstTab = document.querySelector("[data-account-tabs] button[data-tab]")?.dataset.tab || "billing";
  const tab = decodeURIComponent(location.hash.replace(/^#/, "")) || firstTab;
  if (!activateAccountTab(tab)) activateAccountTab(firstTab);
}

function bindMirrorControls() {
  const mirrorMap = {
    "[data-quality-options]": "quality",
    "[data-count-options]": "count",
    "[data-duration-options]": "duration",
  };
  Object.entries(mirrorMap).forEach(([selector, sourceName]) => {
    $$(selector).forEach((mirror) => {
      mirror.addEventListener("change", () => updateComposerSelectFromMirror(sourceName, mirror.value));
    });
  });
}

function bindUi() {
  bindFilters();
  bindAccountTabs();
  bindMirrorControls();
  $$("[data-open-login]").forEach((node) => node.addEventListener("click", () => {
    if (state.user && node.dataset.accountTarget) {
      openAccountSection(node.dataset.accountTarget);
      return;
    }
    openLogin();
  }));
  $$("[data-close-login]").forEach((node) => node.addEventListener("click", closeLogin));
  $$("[data-open-history-modal]").forEach((node) => node.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openHistoryModal();
  }));
  $$("[data-close-history-modal]").forEach((node) => node.addEventListener("click", closeHistoryModal));
  $$("[data-contact-request]").forEach((node) => node.addEventListener("click", () => {
    const form = node.closest("[data-contact-login-form]");
    if (form) requestContactCode(form);
  }));
  $$("[data-logout]").forEach((node) => node.addEventListener("click", logout));
  $$("[data-billing-tab]").forEach((node) => node.addEventListener("click", () => {
    document.querySelector("[data-account-tabs] [data-tab='billing']")?.click();
  }));
  $$("[data-generation-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      setGenerationKind(button.dataset.generationKind || "image", { updateRoute: true });
    });
  });
  $$("[data-generation-flow]").forEach((button) => {
    button.addEventListener("click", () => {
      setGenerationFlow(button.dataset.generationFlow || "text", { updateRoute: true });
    });
  });
  $("[data-account-model-select]")?.addEventListener("change", syncGenerationControls);
  $$(".account-composer").forEach((form) => {
    form.querySelectorAll("details").forEach((details) => {
      details.addEventListener("toggle", () => {
        if (details.open) details.dataset.userTouched = "true";
      });
    });
    form.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.matches("[data-account-model-select]")) return;
      if (target.matches("[name='reference_file']")) updatePhotoPromptStatus(form);
      if (target.matches("[name='prompt_preset']")) updatePromptInjectionStatus(form);
      if (["quality", "count", "duration"].includes(target.getAttribute("name") || "")) {
        syncMirrorSelectsFor(target.getAttribute("name") || "");
      }
      updateGenerationEstimate();
      refreshCustomSelects();
    });
    form.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (target.matches("[name='prompt'], [name='reference_url'], [name='reference_urls'], [name='video_url']")) return;
      updateGenerationEstimate();
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      openGenerationReview(form);
    });
  });
  $$("[data-improve-prompt]").forEach((node) => node.addEventListener("click", (event) => improvePrompt(event.currentTarget)));
  $$("[data-photo-prompt]").forEach((node) => node.addEventListener("click", (event) => generatePromptFromPhoto(event.currentTarget)));
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const customToggle = target.closest("[data-custom-select-toggle]");
    if (customToggle) {
      event.preventDefault();
      event.stopPropagation();
      const proxy = customToggle.closest("[data-select-proxy]");
      if (!proxy || proxy.classList.contains("disabled")) return;
      toggleCustomSelect(proxy, !proxy.classList.contains("open"));
      return;
    }
    const customOption = target.closest("[data-custom-select-option]");
    if (customOption) {
      event.preventDefault();
      event.stopPropagation();
      const proxy = customOption.closest("[data-select-proxy]");
      const select = proxy?.previousElementSibling;
      if (select?.matches?.("select")) {
        select.value = customOption.dataset.value || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncCustomSelect(select);
      }
      closeCustomSelects();
      return;
    }
    if (!target.closest("[data-select-proxy]")) closeCustomSelects();
    if (target.matches("[data-generation-review-modal]")) {
      closeGenerationReview();
      return;
    }
    if (target.matches("[data-history-modal]")) {
      closeHistoryModal();
      return;
    }
    if (target.matches("[data-media-viewer]")) {
      closeMediaViewer();
      return;
    }
    const miniModelButton = target.closest("[data-mini-model]");
    if (miniModelButton) {
      const select = $("[data-account-model-select]");
      if (select) {
        select.value = miniModelButton.dataset.miniModel || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncCustomSelect(select);
      }
      return;
    }
    const useImageSessionButton = target.closest("[data-use-image-session]");
    if (useImageSessionButton) {
      applyActiveImageSession();
      return;
    }
    const archiveImageSessionButton = target.closest("[data-archive-image-session]");
    if (archiveImageSessionButton) {
      archiveActiveImageSession(archiveImageSessionButton.dataset.archiveImageSession || "");
      return;
    }
    const closeReviewButton = target.closest("[data-close-review]");
    if (closeReviewButton) {
      closeGenerationReview();
      return;
    }
    const closeHistoryButton = target.closest("[data-close-history-modal]");
    if (closeHistoryButton) {
      closeHistoryModal();
      return;
    }
    const openHistoryButton = target.closest("[data-open-history-modal]");
    if (openHistoryButton) {
      event.preventDefault();
      openHistoryModal();
      return;
    }
    const closeMediaButton = target.closest("[data-close-media-viewer]");
    if (closeMediaButton) {
      closeMediaViewer();
      return;
    }
    const prevMediaButton = target.closest("[data-media-prev]");
    if (prevMediaButton) {
      stepMediaViewer(-1);
      return;
    }
    const nextMediaButton = target.closest("[data-media-next]");
    if (nextMediaButton) {
      stepMediaViewer(1);
      return;
    }
    const openMediaButton = target.closest("[data-open-media]");
    if (openMediaButton) {
      event.preventDefault();
      const list = parseMediaList(openMediaButton.dataset.openMediaList);
      const index = Number(openMediaButton.dataset.openMediaIndex);
      openMediaViewer(openMediaButton.dataset.openMedia || openMediaButton.getAttribute("src") || "", list, index);
      return;
    }
    const downloadMediaButton = target.closest("[data-download-media]");
    if (downloadMediaButton) {
      event.preventDefault();
      triggerMediaDownload(downloadMediaButton.dataset.downloadMedia || "", downloadMediaButton.dataset.downloadName || "");
      return;
    }
    const downloadGenerationButton = target.closest("[data-download-generation]");
    if (downloadGenerationButton) {
      event.preventDefault();
      triggerGenerationDownload(downloadGenerationButton.dataset.downloadGeneration || "", downloadGenerationButton.dataset.downloadName || "");
      return;
    }
    const confirmGenerationButton = target.closest("[data-confirm-generation]");
    if (confirmGenerationButton) {
      const form = state.pendingGenerationForm;
      closeGenerationReview({ keepPending: true });
      state.pendingGenerationForm = null;
      if (form) submitGeneration(form);
      return;
    }
    const lessonButton = target.closest("[data-model-lesson]");
    if (lessonButton) {
      const shell = lessonButton.closest("[data-model-lessons]");
      const key = lessonButton.dataset.modelLesson || "";
      shell?.querySelectorAll("[data-model-lesson]").forEach((button) => {
        const active = button === lessonButton;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      shell?.querySelectorAll("[data-lesson-panel]").forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.lessonPanel === key);
      });
      return;
    }
    const faqButton = target.closest("[data-guide-faq]");
    if (faqButton) {
      const item = faqButton.closest(".faq-item");
      const open = !item?.classList.contains("open");
      item?.classList.toggle("open", open);
      faqButton.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    const copyGuidePromptButton = target.closest("[data-copy-guide-prompt]");
    if (copyGuidePromptButton) {
      navigator.clipboard?.writeText(copyGuidePromptButton.dataset.copyGuidePrompt || "");
      toast("Промпт скопирован.", "success");
      return;
    }
    const topupButton = target.closest("[data-topup-plan]");
    if (topupButton) topup(topupButton.dataset.topupProvider, topupButton.dataset.topupPlan);
    const referralButton = target.closest("[data-copy-referral]");
    if (referralButton) {
      navigator.clipboard?.writeText(referralButton.dataset.copyReferral || "");
      toast("Реферальная ссылка скопирована.", "success");
    }
    const actionButton = target.closest("[data-generation-action]");
    if (actionButton) handleGenerationAction(actionButton.dataset.generationAction, actionButton.dataset.generationId);
    const usePromptButton = target.closest("[data-use-prompt]");
    if (usePromptButton) usePrompt(usePromptButton.dataset.usePrompt);
    const likePromptButton = target.closest("[data-like-prompt]");
    if (likePromptButton) likePrompt(likePromptButton.dataset.likePrompt);
    const promptSourceButton = target.closest("[data-prompt-source]");
    if (promptSourceButton) {
      loadPrompts(promptSourceButton.dataset.promptSource || "catalog");
      return;
    }
    const likeFeedButton = target.closest("[data-like-feed]");
    if (likeFeedButton) likeFeed(likeFeedButton.dataset.likeFeed);
    const shareFeedButton = target.closest("[data-share-feed]");
    if (shareFeedButton) shareFeed(shareFeedButton.dataset.shareFeed);
    const remixFeedButton = target.closest("[data-remix-feed]");
    if (remixFeedButton) remixFeed(remixFeedButton.dataset.remixFeed);
    const feedSourceButton = target.closest("[data-feed-source]");
    if (feedSourceButton) {
      loadFeedSource(feedSourceButton.dataset.feedSource || "feed");
      return;
    }
    const languageButton = target.closest("[data-language]");
    if (languageButton) setLanguage(languageButton.dataset.language);
    const helpButton = target.closest("[data-help-topic]");
    if (helpButton) loadHelp(helpButton.dataset.helpTopic);
    const adminPromptButton = target.closest("[data-admin-prompt-action]");
    if (adminPromptButton) {
      handleAdminPromptAction(adminPromptButton.dataset.adminPromptAction, adminPromptButton.dataset.promptId);
    }
  });
  document.addEventListener("submit", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const promptForm = target.closest("[data-prompt-form]");
    if (promptForm) {
      event.preventDefault();
      submitPrompt(promptForm);
    }
    const profileForm = target.closest("[data-profile-form]");
    if (profileForm) {
      event.preventDefault();
      submitProfile(profileForm);
      return;
    }
    const passwordForm = target.closest("[data-password-form]");
    if (passwordForm) {
      event.preventDefault();
      submitPassword(passwordForm);
      return;
    }
    const passwordLoginForm = target.closest("[data-password-login-form]");
    if (passwordLoginForm) {
      event.preventDefault();
      passwordLogin(passwordLoginForm);
      return;
    }
    const passwordRegisterForm = target.closest("[data-password-register-form]");
    if (passwordRegisterForm) {
      event.preventDefault();
      passwordRegister(passwordRegisterForm);
      return;
    }
    const withdrawalForm = target.closest("[data-withdrawal-form]");
    if (withdrawalForm) {
      event.preventDefault();
      submitWithdrawal(withdrawalForm);
      return;
    }
    const exchangeForm = target.closest("[data-referral-exchange-form]");
    if (exchangeForm) {
      event.preventDefault();
      submitReferralExchange(exchangeForm);
      return;
    }
    const assistantForm = target.closest("[data-assistant-form]");
    if (assistantForm) {
      event.preventDefault();
      sendAssistant(assistantForm);
    }
    const contactLoginForm = target.closest("[data-contact-login-form]");
    if (contactLoginForm) {
      event.preventDefault();
      verifyContactCode(contactLoginForm);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeLogin();
      closeGenerationReview();
      closeHistoryModal();
      closeMediaViewer();
      closeCustomSelects();
    }
    if (event.key === "ArrowLeft") stepMediaViewer(-1);
    if (event.key === "ArrowRight") stepMediaViewer(1);
  });
  document.addEventListener("pointerdown", (event) => {
    const target = event.target;
    if (target instanceof Element && !target.closest("[data-select-proxy]")) {
      closeCustomSelects();
    }
  }, true);
  document.addEventListener("focusin", (event) => {
    const target = event.target;
    if (target instanceof Element && !target.closest("[data-select-proxy]")) {
      closeCustomSelects();
    }
  });
  document.addEventListener("scroll", (event) => {
    const target = event.target;
    if (target instanceof Element && target.closest("[data-custom-options]")) return;
    closeCustomSelects();
  }, true);
}

async function boot() {
  localStorage.removeItem(TOKEN_KEY);
  bindUi();
  applyRouteParams();
  syncActiveNavigation();
  await loadPublic();
  await loadPrivate({ quiet: true });
  renderHeroStack();
  renderModels();
  applyGenerationPresetToComposer();
  renderGallery();
  renderAccount();
  renderAuth();
  if (location.pathname === '/login') openLogin();
  syncAccountTabFromHash();
  syncActiveNavigation();
  refreshCustomSelects();
}

boot().catch((error) => {
  console.error(error);
  toast(`Ошибка загрузки: ${error.message}`, "danger");
});
