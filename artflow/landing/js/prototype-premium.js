const API_BASE = "/api/web";
const TOKEN_KEY = "apix-premium-web-token";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
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
  assistantHistory: [],
  help: null,
  billing: null,
  plans: [],
  referrals: null,
  socket: null,
  fallbackMode: false,
  routeModelKey: "",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

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
  const response = await fetch(url, { ...options, headers });
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
    state.fallbackMode = true;
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

function creditLabel(model) {
  const value = formatNumber(model?.credits || 0);
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
    counts: model.counts || [],
    durations: model.durations || [],
    resolutions: model.resolutions || [],
    modes: model.modes || [],
  };
}

function modelFamilyKey(model) {
  let key = String(model.key || model.name || "").toLowerCase();
  key = key.replace(/__.+$/, "");
  key = key
    .replace(/(?:\/|-)(text-to-image|image-to-image|image-edit|text-to-video|image-to-video|video-to-video)$/, "")
    .replace(/(?:\/|-)(edit)$/, "");
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
    const credits = group.variants.map((model) => Number(model.credits || 0)).filter((value) => Number.isFinite(value));
    const minCredits = credits.length ? Math.min(...credits) : 0;
    const maxCredits = credits.length ? Math.max(...credits) : 0;
    const modes = Array.from(group.modes);
    const qualities = Array.from(group.qualities);
    return {
      ...group,
      preferred,
      name: cleanFamilyName(preferred.name || preferred.key),
      creditsLabel: minCredits === maxCredits ? formatNumber(minCredits) : `${formatNumber(minCredits)}-${formatNumber(maxCredits)}`,
      chips: [...modes, ...qualities].length ? [...modes, ...qualities] : preferred.capabilities || [group.type],
      subtitle: `${modes.length ? modes.join(" + ") : shortTypeLabel(group.type)} · ${group.variants.length} ${modeCountLabel(group.variants.length)}`,
    };
  });
}

function normalizeExample(item, index = 0) {
  const image = item.result_url || item.image || item.result_urls?.[0] || "";
  const type = item.type || item.gen_type || "image";
  return {
    id: item.id || index,
    type,
    model: item.model || "api-model",
    author: item.author || "",
    likes: Number(item.likes || item.likes_count || 0),
    shares: Number(item.shares || item.shares_count || 0),
    remixCount: Number(item.remix_count || item.remixes || 0),
    image,
    title: item.title || cleanModelName(item.model || "Готовая работа") || `Работа ${index + 1}`,
    prompt: String(item.prompt || item.prompt_text || "").replace(/\s+/g, " ").trim().slice(0, 240),
    status: item.status || "done",
    credits: Number(item.credits_spent || 0),
    isPublicFeed: Boolean(item.is_public_feed),
    isPromptLibrary: Boolean(item.is_prompt_library),
    promptActionsAllowed: item.prompt_actions_allowed ?? true,
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

function mediaHtml(item, index = 0) {
  const url = safeUrl(item.image || item.result_url || fallbackImage(index));
  if (!url) return "";
  if (item.type === "video" || /\.(mp4|mov|webm)(\?|$)/i.test(url)) {
    return `<video src="${escapeHtml(url)}" controls playsinline></video>`;
  }
  if (item.type === "music" || /\.(mp3|wav|ogg|m4a)(\?|$)/i.test(url)) {
    return `<audio src="${escapeHtml(url)}" controls></audio>`;
  }
  return `<img src="${escapeHtml(url)}" alt="">`;
}

function fallbackImage(index = 0) {
  return state.examples[index]?.image || "images/concepts/pink-blue-runway.png";
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

function setAccountPreview(index = state.activeExample) {
  if (!state.examples.length) return;
  const item = state.examples[index] || state.examples[0];
  const image = $("[data-account-preview]");
  const model = $("[data-account-preview-model]");
  const title = $("[data-account-preview-title]");
  if (image) image.src = item.image;
  if (model) model.textContent = cleanModelName(item.model);
  if (title) title.textContent = item.title;
}

function renderHeroStack() {
  const stack = $("[data-hero-stack]");
  if (!stack) return;
  stack.innerHTML = state.examples.slice(0, 8).map((item, index) => `
    <button type="button" data-hero-index="${index}" aria-label="Показать пример ${index + 1}">
      <img src="${escapeHtml(item.image)}" alt="">
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

function currentModel() {
  const select = $("[data-account-model-select]");
  const models = modelsForCurrentKind();
  return models.find((model) => model.key === select?.value) || models[0] || null;
}

function applyRouteParams() {
  const params = new URLSearchParams(location.search);
  const kind = params.get("type");
  if (["image", "video", "music"].includes(kind)) state.generationKind = kind;
  state.routeModelKey = params.get("model") || "";
}

function optionTags(values, selected = "") {
  return (values || []).filter(Boolean).map((value) => {
    const option = typeof value === "object" ? value : { value, label: value };
    const rawValue = String(option.value ?? option.label ?? "");
    return `<option value="${escapeHtml(rawValue)}" ${rawValue === String(selected || "") ? "selected" : ""}>${escapeHtml(option.label || rawValue)}</option>`;
  }).join("");
}

function syncGenerationControls() {
  const model = currentModel();
  const ratio = document.querySelector("[name='aspect_ratio']");
  const quality = document.querySelector("[name='quality']");
  const count = document.querySelector("[name='count']");
  const duration = document.querySelector("[name='duration']");
  const resolution = document.querySelector("[name='resolution']");
  const instrumental = document.querySelector("[name='instrumental']");
  const qualityMirror = $("[data-quality-options]");
  const countMirror = $("[data-count-options]");
  const durationMirror = $("[data-duration-options]");
  const note = $("[data-generation-note]");

  if (ratio) {
    const ratios = model?.aspectRatios?.length ? model.aspectRatios : ["9:16", "1:1", "16:9"];
    ratio.innerHTML = optionTags(ratios, ratios[0]);
  }
  if (quality) {
    const qualities = model?.qualities?.length ? model.qualities : [{ value: "basic", label: "Basic" }, { value: "2K", label: "2K" }, { value: "4K", label: "4K" }];
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
  if (qualityMirror) qualityMirror.innerHTML = quality?.innerHTML || "<option>Basic</option>";
  if (countMirror) countMirror.innerHTML = count?.innerHTML || "<option>1</option>";
  if (durationMirror) {
    const durations = model?.durations?.length ? model.durations : [5, 10];
    durationMirror.innerHTML = optionTags(durations.map((value) => ({ value, label: `${value} сек` })), durations[0]);
  }
  if (note) {
    note.textContent = state.user
      ? `${cleanModelName(model?.name || model?.key || "Модель")} · ${creditLabel(model || {})}`
      : "Войдите через Telegram, чтобы сохранять работы и видеть готовность результата.";
  }
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
      const key = model.key || group.name;
      const href = `studio.html?type=${encodeURIComponent(group.type)}&model=${encodeURIComponent(key)}`;
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
        <a class="model-action" href="${escapeHtml(href)}">Создать</a>
      </article>
    `;
    }).join("");
  }

  if (select) {
    select.innerHTML = allModels.map((model) => `
      <option value="${escapeHtml(model.key)}">${escapeHtml(cleanModelName(model.name || model.key))} · ${escapeHtml(creditLabel(model))}</option>
    `).join("");
  }

  if (accountSelect) {
    const models = modelsForCurrentKind();
    accountSelect.innerHTML = models.map((model) => `
      <option value="${escapeHtml(model.key)}">${escapeHtml(cleanModelName(model.name || model.key))} · ${escapeHtml(creditLabel(model))}</option>
    `).join("");
    if (state.routeModelKey && models.some((model) => model.key === state.routeModelKey)) {
      accountSelect.value = state.routeModelKey;
    }
  }

  $$("[data-generation-kind]").forEach((button) => {
    button.classList.toggle("active", button.dataset.generationKind === state.generationKind);
  });
  syncGenerationControls();
}

function renderGallery() {
  const grid = $("[data-gallery-grid]");
  if ($("[data-total-examples]")) $("[data-total-examples]").textContent = String(state.examples.length || 0);
  if (!grid) return;
  grid.innerHTML = state.examples.map((item) => `
    <article class="gallery-card">
      <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title)}">
      <div>
        <span>${escapeHtml(cleanModelName(item.model))} · ${formatNumber(item.likes)} лайков</span>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.prompt)}</p>
      </div>
    </article>
  `).join("");
}

function renderAuth() {
  const authed = Boolean(state.user);
  const name = state.user?.full_name || state.user?.username || "APIX creator";
  const credits = formatNumber(state.user?.credits || 0);
  const accountStatus = $("[data-account-status]");
  const userPill = $("[data-user-pill]");
  const logout = $("[data-logout]");

  if (accountStatus) {
    accountStatus.textContent = authed
      ? `${name} · баланс ${credits}`
      : state.fallbackMode ? "Демо-режим" : "Гость · войдите через Telegram";
  }
  if (userPill) {
    userPill.textContent = authed ? `${name} · баланс ${credits}` : "Войти через Telegram";
  }
  if (logout) logout.hidden = !authed;
  syncGenerationControls();
  renderBilling();
  renderReferrals();
  renderSettings();
}

function renderAccount() {
  setAccountPreview(0);
  const mini = $("[data-account-models-mini]");
  if (mini) {
    const items = (state.models.length ? state.models : Object.values(state.modelsByKind).flat()).slice(0, 6);
    mini.innerHTML = items.map((model) => `
      <article class="model-mini">
        <span>${typeLabel(model.type)}</span>
        <b>${escapeHtml(cleanModelName(model.name || model.key))}</b>
        <small>${escapeHtml(creditLabel(model))} · ${escapeHtml((model.capabilities || []).slice(0, 2).map(capabilityLabel).join(" / "))}</small>
      </article>
    `).join("");
  }
  renderQueue();
  renderLibrary();
  renderBilling();
  renderReferrals();
  renderPrompts();
  renderFeedPanel();
  renderAssistant();
  renderSettings();
}

function queueItems() {
  const active = state.queue.length ? state.queue : state.examples.slice(0, 4).map((item, index) => ({
    ...item,
    status: ["processing", "queued", "pending", "draft"][index],
    progress: [76, 44, 28, 12][index],
  }));
  return active.slice(0, 8);
}

function renderQueue() {
  const queue = $("[data-account-queue]");
  if (!queue) return;
  queue.innerHTML = queueItems().map((item, index) => {
    const progress = item.progress || (["pending", "queued"].includes(item.status) ? 30 : item.status === "processing" ? 72 : item.status === "done" ? 100 : 14);
    return `
      <article class="queue-card">
        <img src="${escapeHtml(item.image || item.result_url || fallbackImage(index))}" alt="">
        <div>
          <span>${escapeHtml(statusLabel(item.status || "queued"))} · ${escapeHtml(cleanModelName(item.model))}</span>
          <b>${escapeHtml(item.title || `Работа #${item.id || index + 1}`)}</b>
          <p>${escapeHtml(item.prompt || "Работа добавлена и скоро будет готова.")}</p>
        </div>
        <div class="progress" aria-label="Прогресс ${progress}%">
          <i style="width: ${Math.min(100, Math.max(8, Number(progress)))}%"></i>
        </div>
      </article>
    `;
  }).join("");
}

function renderLibrary() {
  const library = $("[data-account-library]");
  if (!library) return;
  const items = (state.history.length ? state.history : state.examples).filter((item) => item.image || item.result_url).slice(0, 12);
  library.innerHTML = items.length ? items.map((item, index) => `
    <article class="library-card">
      ${mediaHtml(item, index)}
      <div>
        <b>${escapeHtml(item.title || cleanModelName(item.model) || "Готовая работа")}</b>
        <span>${escapeHtml(cleanModelName(item.model))} · ${escapeHtml(item.status ? statusLabel(item.status) : `${formatNumber(item.likes)} лайков`)}</span>
        <div class="card-actions">
          ${safeUrl(item.image) ? `<a href="${escapeHtml(safeUrl(item.image))}" target="_blank" rel="noopener noreferrer">Открыть</a>` : ""}
          ${Number(item.id) ? `<button type="button" data-generation-action="publish" data-generation-id="${item.id}">В ленту</button>` : ""}
          ${Number(item.id) ? `<button type="button" data-generation-action="share-library" data-generation-id="${item.id}">В библиотеку</button>` : ""}
          ${Number(item.id) ? `<button type="button" data-generation-action="remove-library" data-generation-id="${item.id}">Убрать</button>` : ""}
        </div>
      </div>
    </article>
  `).join("") : `<div class="empty-state">История появится после первой генерации.</div>`;
}

function renderBilling() {
  const grid = $("[data-billing-grid]");
  if (!grid) return;
  const balance = formatNumber(state.user?.credits || 0);
  const methods = state.billing?.methods || [];
  const pending = state.billing?.pending || [];
  const plans = state.plans.length ? state.plans : [
    { key: "demo_start", label: "Старт", credits: 300, price_rub_display: "390₽" },
    { key: "demo_studio", label: "Студия", credits: 1400, price_rub_display: "1 490₽" },
    { key: "demo_business", label: "Бизнес", credits: 5200, price_rub_display: "4 990₽" },
  ];
  grid.innerHTML = `
    <article>
      <span>Баланс</span>
      <b>${balance}</b>
      <p>${state.user
        ? `${methods.length ? methods.map((item) => item.label || item.key).join(" / ") : "Способы оплаты загружаются"} · ожидают оплаты: ${pending.length}`
        : "Войдите через Telegram, чтобы увидеть баланс."}</p>
      <i><em style="width: ${state.user ? "42" : "18"}%"></em></i>
    </article>
    ${plans.slice(0, 3).map((plan, index) => `
      <article>
        <span>${index === 1 ? "Популярный пакет" : "Пополнить"}</span>
        <b>${escapeHtml(plan.label || plan.title || plan.key)}</b>
        <p>${formatNumber(plan.credits)} на баланс · ${escapeHtml(plan.price_rub_display || formatCurrency(plan.price_rub || 0))}</p>
        <div class="pay-actions">
          <button class="button ${index === 1 ? "primary" : "ghost"}" type="button" data-topup-provider="tbank" data-topup-plan="${escapeHtml(plan.key)}">Карта</button>
          <button class="button ghost" type="button" data-topup-provider="stars" data-topup-plan="${escapeHtml(plan.key)}">Telegram</button>
          <button class="button ghost" type="button" data-topup-provider="crypto" data-topup-plan="${escapeHtml(plan.key)}">Крипто</button>
        </div>
      </article>
    `).join("")}
  `;
}

function renderReferrals() {
  const root = $("[data-referral-panel]");
  if (!root) return;
  const ref = state.referrals;
  const counts = ref?.counts || { l1: 0, l2: 0, l3: 0 };
  const balance = ref?.balance || { available_to_withdraw: 0, total_earned: 0 };
  root.innerHTML = `
    <div>
      <span>Рефералы</span>
      <h3>${ref ? "Приглашайте друзей и получайте бонусы" : "Пригласите друзей и получайте бонусы"}</h3>
      <p>${ref ? `Ссылка: ${escapeHtml(ref.referral_link || "")}` : "После входа здесь появятся ссылка, уровни, начисления, доступно к выводу и история заявок."}</p>
      ${ref?.referral_link ? `<button class="button ghost" type="button" data-copy-referral="${escapeHtml(ref.referral_link)}">Скопировать ссылку</button>` : ""}
      <form class="withdrawal-form" data-withdrawal-form>
        <label><span>Сумма вывода, ₽</span><input name="amount_rub" type="number" min="1" step="1" placeholder="${escapeHtml(ref?.withdraw_min_rub || 0)}"></label>
        <label><span>Реквизиты</span><textarea name="payout_details" rows="2" placeholder="Карта, USDT, банк или другой способ"></textarea></label>
        <button class="button primary" type="submit">Создать заявку</button>
      </form>
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
  board.innerHTML = state.prompts.length ? state.prompts.map((prompt) => `
    <article class="feature-card">
      ${safeUrl(prompt.preview_url) ? `<img src="${escapeHtml(safeUrl(prompt.preview_url))}" alt="">` : ""}
      <span>${escapeHtml(prompt.category || "идея")} · ${formatNumber(prompt.likes || 0)} лайков</span>
      <h3>${escapeHtml(prompt.title || `Идея #${prompt.id}`)}</h3>
      <p>${escapeHtml(prompt.description || prompt.prompt_text || "")}</p>
      <div class="card-actions">
        <button type="button" data-use-prompt="${escapeHtml(prompt.id)}">Создать</button>
        <button type="button" data-like-prompt="${escapeHtml(prompt.id)}">Лайк</button>
      </div>
    </article>
  `).join("") : `<div class="empty-state">Промпты загрузятся после входа или обновления каталога.</div>`;
}

function renderFeedPanel() {
  const board = $("[data-feed-board]");
  if (!board) return;
  board.innerHTML = state.examples.length ? state.examples.slice(0, 24).map((item, index) => `
    <article class="feature-card">
      ${mediaHtml(item, index)}
      <span>${escapeHtml(cleanModelName(item.model))} · ${formatNumber(item.likes)} лайков</span>
      <h3>${escapeHtml(item.title || `Работа #${item.id}`)}</h3>
      <p>${escapeHtml(item.prompt || "Описание скрыто автором.")}</p>
      <div class="card-actions">
        <button type="button" data-like-feed="${escapeHtml(item.id)}">Лайк</button>
        <button type="button" data-share-feed="${escapeHtml(item.id)}">Поделиться</button>
        <button type="button" data-remix-feed="${escapeHtml(item.id)}">Создать похожее</button>
      </div>
    </article>
  `).join("") : `<div class="empty-state">Лента пока пустая.</div>`;
}

function renderAssistant() {
  const log = $("[data-assistant-log]");
  if (!log) return;
  log.innerHTML = state.assistantHistory.length
    ? state.assistantHistory.map((item) => `<div class="assistant-msg ${item.role === "user" ? "user" : ""}">${escapeHtml(item.content)}</div>`).join("")
    : `<div class="assistant-msg">Я помогу собрать промпт, выбрать модель, подготовить сценарий или объяснить настройки генерации.</div>`;
}

function renderSettings() {
  const panel = $("[data-help-panel]");
  if (!panel) return;
  panel.innerHTML = state.help
    ? `<article class="help-card"><span>${escapeHtml(state.help.topic)} · ${escapeHtml(state.help.language)}</span><p>${escapeHtml(state.help.text)}</p></article>`
    : `<article class="help-card"><span>Help</span><p>Войдите через Telegram и выберите тему справки. Текст подтягивается из тех же help-функций, что использует бот.</p></article>`;
}

function openLogin() {
  const modal = $("[data-login-modal]");
  if (!modal) return;
  modal.hidden = false;
  injectTelegramWidget();
}

function closeLogin() {
  const modal = $("[data-login-modal]");
  if (modal) modal.hidden = true;
}

function injectTelegramWidget() {
  const slot = $("[data-telegram-slot]");
  const fallback = $("[data-auth-fallback]");
  if (!slot) return;
  const bot = state.authConfig?.bot_username;
  if (!bot) {
    if (fallback) {
      fallback.hidden = false;
      fallback.textContent = state.fallbackMode
        ? "Вход доступен на рабочем домене сайта."
        : "Вход через Telegram временно недоступен.";
    }
    return;
  }
  if (slot.dataset.loaded === bot) return;
  slot.dataset.loaded = bot;
  slot.innerHTML = "";
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://telegram.org/js/telegram-widget.js?22";
  script.setAttribute("data-telegram-login", bot);
  script.setAttribute("data-size", "large");
  script.setAttribute("data-radius", "8");
  script.setAttribute("data-onauth", "onTelegramAuth(user)");
  script.setAttribute("data-request-access", "write");
  slot.appendChild(script);
}

window.onTelegramAuth = async (user) => {
  try {
    const result = await request("/auth/telegram-login", { method: "POST", body: JSON.stringify(user) });
    state.token = result.token;
    state.user = result.user;
    localStorage.setItem(TOKEN_KEY, result.token);
    closeLogin();
    toast("Вход выполнен. Ваш кабинет открыт.", "success");
    await loadPrivate();
    location.hash = "#account";
  } catch (error) {
    toast(`Ошибка входа: ${error.message}`, "danger");
  }
};

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  state.token = "";
  state.user = null;
  state.queue = [];
  state.history = [];
  state.billing = null;
  state.referrals = null;
  closeRealtime();
  renderAuth();
  renderAccount();
  toast("Вы вышли из кабинета.", "info");
}

function mergeGeneration(item) {
  const gen = normalizeExample(item);
  gen.status = item.status || gen.status;
  gen.title = gen.title || `Работа #${gen.id}`;
  const id = Number(gen.id);
  if (["pending", "processing", "queued", "running"].includes(String(gen.status).toLowerCase())) {
    const index = state.queue.findIndex((entry) => Number(entry.id) === id);
    if (index >= 0) state.queue[index] = { ...state.queue[index], ...gen };
    else state.queue.unshift(gen);
  } else {
    state.queue = state.queue.filter((entry) => Number(entry.id) !== id);
    const index = state.history.findIndex((entry) => Number(entry.id) === id);
    if (index >= 0) state.history[index] = { ...state.history[index], ...gen };
    else state.history.unshift(gen);
  }
  state.queue = state.queue.slice(0, 16);
  state.history = state.history.slice(0, 48);
}

function connectRealtime() {
  if (!state.token || state.socket) return;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/v1/ws/generations?token=${encodeURIComponent(state.token)}`);
  state.socket = socket;
  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "generation.snapshot") (payload.items || []).forEach(mergeGeneration);
      if (payload.type === "generation.updated") mergeGeneration(payload);
      renderQueue();
      renderLibrary();
    } catch {
      // Ignore malformed realtime messages.
    }
  });
  socket.addEventListener("close", () => {
    if (state.socket === socket) state.socket = null;
    if (state.token && state.user) setTimeout(connectRealtime, 5000);
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

async function submitGeneration(form) {
  if (!state.user) {
    openLogin();
    toast("Сначала войдите через Telegram.", "info");
    return;
  }
  const data = new FormData(form);
  const model = currentModel();
  const prompt = String(data.get("prompt") || "").trim();
  if (!prompt) {
    toast("Добавьте промпт.", "danger");
    return;
  }
  const button = $("[data-generate-button]");
  if (button) button.disabled = true;
  try {
    let referenceUrl = String(data.get("reference_url") || "").trim();
    const file = data.get("reference_file");
    if (file instanceof File && file.size > 0) {
      referenceUrl = await uploadReference(file);
    }

    let body;
    let path;
    if (state.generationKind === "music") {
      path = "/generate/music";
      body = { prompt, instrumental: Boolean(data.get("instrumental")) };
    } else if (state.generationKind === "video") {
      path = "/generate/video";
      const videoUrl = String(data.get("video_url") || "").trim();
      body = {
        model: model?.key,
        prompt,
        mode: videoUrl ? "video" : referenceUrl ? "image" : "text",
        duration: Number(data.get("duration") || model?.durations?.[0] || 5),
        aspect_ratio: String(data.get("aspect_ratio") || "") || null,
        resolution: String(data.get("resolution") || "") || null,
        image_url: referenceUrl || null,
        reference_urls: [],
        video_url: videoUrl || null,
        seed: data.get("seed") ? Number(data.get("seed")) : null,
        grok_mode: String(data.get("grok_mode") || "normal"),
      };
    } else {
      path = "/generate/image";
      body = {
        model: model?.key,
        prompt,
        aspect_ratio: String(data.get("aspect_ratio") || "") || null,
        quality: String(data.get("quality") || "basic"),
        count: Number(data.get("count") || 1),
        reference_url: referenceUrl || null,
        reference_urls: [],
      };
    }
    if (!body.model && state.generationKind !== "music") throw new Error("Модель недоступна");
    const result = await request(path, { method: "POST", body: JSON.stringify(body) });
    mergeGeneration({ ...result, prompt, model: body.model || "suno/v4.5", image: fallbackImage(0), title: `Работа #${result.id || result.generation_id || ""}` });
    renderQueue();
    renderLibrary();
    document.querySelector("[data-account-tabs] [data-tab='queue']")?.click();
    toast("Задача отправлена в боевую очередь APIX.", "success");
    await loadPrivate({ quiet: true });
    pollQueue();
  } catch (error) {
    toast(`Ошибка генерации: ${error.message}`, "danger");
  } finally {
    if (button) button.disabled = false;
  }
}

async function improvePrompt() {
  if (!state.user) {
    openLogin();
    return;
  }
  const textarea = document.querySelector(".account-composer textarea[name='prompt']");
  const prompt = textarea?.value.trim();
  if (!prompt) return;
  try {
    const result = await request("/prompt/improve", {
      method: "POST",
      body: JSON.stringify({ prompt, kind: state.generationKind }),
    });
    textarea.value = result.prompt || prompt;
    toast("Промпт улучшен.", "success");
  } catch (error) {
    toast(`Не удалось улучшить промпт: ${error.message}`, "danger");
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
  try {
    const method = ["tbank", "stars", "crypto"].includes(provider) ? provider : "tbank";
    const result = await request(`/billing/topup/${method}`, { method: "POST", body: JSON.stringify({ plan_key: planKey }) });
    const url = result.pay_url || result.invoice_link;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
    else toast("Счёт создан.", "success");
  } catch (error) {
    toast(`Ошибка оплаты: ${error.message}`, "danger");
  }
}

async function generatePromptFromPhoto() {
  if (!state.user) {
    openLogin();
    return;
  }
  const file = document.querySelector(".account-composer input[name='reference_file']")?.files?.[0];
  const textarea = document.querySelector(".account-composer textarea[name='prompt']");
  if (!file) {
    toast("Выберите референс-файл в форме.", "info");
    return;
  }
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await request("/photo-prompt", { method: "POST", body: form });
    if (textarea && result.prompt) textarea.value = result.prompt;
    toast("Промпт по фото готов.", "success");
  } catch (error) {
    toast(`Не удалось разобрать фото: ${error.message}`, "danger");
  }
}

async function handleGenerationAction(action, generationId) {
  if (!state.user) {
    openLogin();
    return;
  }
  const allowed = {
    publish: "publish",
    "share-library": "share-library",
    "remove-library": "remove-library",
  };
  const path = allowed[action];
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
    const textarea = document.querySelector(".account-composer textarea[name='prompt']");
    if (textarea && prompt?.prompt_text) textarea.value = prompt.prompt_text;
    state.generationKind = "image";
    renderModels();
    document.querySelector("[data-account-tabs] [data-tab='quick']")?.click();
    toast("Промпт загружен в Studio.", "success");
  } catch (error) {
    toast(`Промпт недоступен: ${error.message}`, "danger");
  }
}

async function likePrompt(promptId) {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    await request(`/prompts/${promptId}/like`, { method: "POST" });
    const promptPayload = await request("/prompts?limit=24");
    state.prompts = promptPayload?.items || state.prompts;
    renderPrompts();
  } catch (error) {
    toast(`Не удалось поставить лайк: ${error.message}`, "danger");
  }
}

async function likeFeed(feedId) {
  if (!state.user) {
    openLogin();
    return;
  }
  try {
    await request(`/feed/${feedId}/like`, { method: "POST" });
    await loadPublic();
    renderGallery();
    renderFeedPanel();
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
    toast("Ссылка готова.", "success");
  } catch (error) {
    toast(`Не удалось поделиться: ${error.message}`, "danger");
  }
}

async function remixFeed(feedId) {
  if (!state.user) {
    openLogin();
    return;
  }
  const model = state.modelsByKind.image?.[0] || state.models.find((item) => item.type === "image");
  if (!model) {
    toast("Не удалось подобрать режим для похожей работы.", "danger");
    return;
  }
  try {
    const result = await request(`/feed/${feedId}/remix`, {
      method: "POST",
      body: JSON.stringify({
        model: model.key,
        mode: "image",
        quality: "basic",
        count: 1,
      }),
    });
    mergeGeneration({ ...result, image: fallbackImage(0), title: `Похожая работа #${result.id || ""}` });
    renderQueue();
    document.querySelector("[data-account-tabs] [data-tab='queue']")?.click();
    toast("Ремикс отправлен в очередь.", "success");
    await loadPrivate({ quiet: true });
  } catch (error) {
    toast(`Не удалось запустить remix: ${error.message}`, "danger");
  }
}

async function submitPrompt(form) {
  if (!state.user) {
    openLogin();
    return;
  }
  const data = Object.fromEntries(new FormData(form).entries());
  try {
    await request("/prompts", { method: "POST", body: JSON.stringify(data) });
    form.reset();
    const promptPayload = await request("/prompts?limit=24");
    state.prompts = promptPayload?.items || state.prompts;
    renderPrompts();
    toast("Промпт отправлен на модерацию.", "success");
  } catch (error) {
    toast(`Не удалось отправить промпт: ${error.message}`, "danger");
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
    const result = await request("/api/v1/assistant", {
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
  try {
    await request("/api/v1/settings/language", { method: "POST", body: JSON.stringify({ language }) });
    state.user.language = language;
    renderAuth();
    toast("Язык аккаунта обновлён.", "success");
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
    state.help = await request(`/api/v1/help?topic=${encodeURIComponent(topic)}`);
    renderSettings();
  } catch (error) {
    toast(`Справка недоступна: ${error.message}`, "danger");
  }
}

async function loadFallbackData() {
  const [feedResponse, modelResponse] = await Promise.all([
    fetch("data/prototype-feed.json"),
    fetch("data/prototype-models.json"),
  ]);
  const feed = await feedResponse.json();
  const modelData = await modelResponse.json();
  state.examples = (feed.examples || []).map(normalizeExample);
  state.models = (modelData.models || []).map((model) => normalizeModel(model));
  state.modelsByKind = {
    image: state.models.filter((model) => model.type === "image"),
    video: state.models.filter((model) => model.type === "video"),
    music: state.models.filter((model) => model.type === "music"),
  };
}

async function loadPublic() {
  state.authConfig = await optionalRequest("/auth/config", null);
  try {
    const [feed, modelPayload, promptPayload] = await Promise.all([
      request("/feed?limit=24"),
      request("/models"),
      optionalRequest("/prompts?limit=24", { items: [] }),
    ]);
    state.examples = (Array.isArray(feed) ? feed : feed.items || []).map(normalizeExample).filter((item) => item.image);
    state.prompts = (promptPayload?.items || []).slice(0, 24);
    const grouped = modelPayload || {};
    state.models = (grouped.all || []).map((model) => normalizeModel(model));
    state.modelsByKind = {
      image: (grouped.image || []).map((model) => normalizeModel(model, "image")),
      video: (grouped.video || []).map((model) => normalizeModel(model, "video")),
      music: (grouped.music || []).map((model) => normalizeModel(model, "music")),
    };
  } catch {
    state.fallbackMode = true;
    await loadFallbackData();
  }
}

async function loadPrivate({ quiet = false } = {}) {
  if (!state.token) return;
  const me = await optionalRequest("/me", null);
  if (!me) {
    localStorage.removeItem(TOKEN_KEY);
    state.token = "";
    state.user = null;
    renderAuth();
    return;
  }
  state.user = me;
  const results = await Promise.allSettled([
    request("/models/image"),
    request("/models/video"),
    request("/models/music"),
    request("/history?limit=48"),
    request("/generations/active"),
    request("/billing/plans"),
    request("/billing/transactions?limit=20"),
    request("/referrals"),
    request("/prompts?limit=24"),
    request("/api/v1/help?topic=main"),
  ]);
  const [imageModels, videoModels, musicModels, history, active, plans, billing, referrals, prompts, help] = results.map((result) => result.status === "fulfilled" ? result.value : null);
  state.modelsByKind = {
    image: (imageModels || []).map((model) => normalizeModel(model, "image")),
    video: (videoModels || []).map((model) => normalizeModel(model, "video")),
    music: (musicModels || []).map((model) => normalizeModel(model, "music")),
  };
  state.models = Object.values(state.modelsByKind).flat();
  state.history = (history || []).map(normalizeExample).filter((item) => item.image || item.status !== "done");
  state.queue = (active || []).map(normalizeExample);
  state.plans = Array.isArray(plans) ? plans : [];
  state.billing = billing;
  state.referrals = referrals;
  state.prompts = prompts?.items || state.prompts;
  state.help = help || state.help;
  renderModels();
  renderAuth();
  renderAccount();
  connectRealtime();
  pollQueue();
    if (!quiet) toast("Кабинет обновлен.", "success");
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
  const titles = {
    quick: "Создать",
    pro: "Точные настройки",
    queue: "Готовность работ",
    library: "Библиотека работ",
    billing: "Баланс и пополнение",
    referrals: "Рефералы",
    prompts: "Идеи",
    feed: "Галерея",
    assistant: "Помощник",
    settings: "Помощь и настройки",
  };
  $$("[data-account-tabs] button").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.tab || "quick";
      $$("[data-account-tabs] button").forEach((item) => item.classList.toggle("active", item === button));
      $$("[data-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === tab));
      const title = $("[data-account-title]");
      if (title) title.textContent = titles[tab] || tab;
    });
  });
}

function bindUi() {
  bindFilters();
  bindAccountTabs();
  $$("[data-open-login]").forEach((node) => node.addEventListener("click", openLogin));
  $$("[data-close-login]").forEach((node) => node.addEventListener("click", closeLogin));
  $$("[data-logout]").forEach((node) => node.addEventListener("click", logout));
  $$("[data-billing-tab]").forEach((node) => node.addEventListener("click", () => {
    document.querySelector("[data-account-tabs] [data-tab='billing']")?.click();
  }));
  $$("[data-generation-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      state.generationKind = button.dataset.generationKind || "image";
      $$("[data-generation-kind]").forEach((item) => item.classList.toggle("active", item === button));
      renderModels();
    });
  });
  $("[data-account-model-select]")?.addEventListener("change", syncGenerationControls);
  $(".account-composer")?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitGeneration(event.currentTarget);
  });
  $("[data-improve-prompt]")?.addEventListener("click", improvePrompt);
  $$("[data-photo-prompt]").forEach((node) => node.addEventListener("click", generatePromptFromPhoto));
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
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
    const likeFeedButton = target.closest("[data-like-feed]");
    if (likeFeedButton) likeFeed(likeFeedButton.dataset.likeFeed);
    const shareFeedButton = target.closest("[data-share-feed]");
    if (shareFeedButton) shareFeed(shareFeedButton.dataset.shareFeed);
    const remixFeedButton = target.closest("[data-remix-feed]");
    if (remixFeedButton) remixFeed(remixFeedButton.dataset.remixFeed);
    const languageButton = target.closest("[data-language]");
    if (languageButton) setLanguage(languageButton.dataset.language);
    const helpButton = target.closest("[data-help-topic]");
    if (helpButton) loadHelp(helpButton.dataset.helpTopic);
  });
  document.addEventListener("submit", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const promptForm = target.closest("[data-prompt-form]");
    if (promptForm) {
      event.preventDefault();
      submitPrompt(promptForm);
    }
    const withdrawalForm = target.closest("[data-withdrawal-form]");
    if (withdrawalForm) {
      event.preventDefault();
      submitWithdrawal(withdrawalForm);
    }
    const assistantForm = target.closest("[data-assistant-form]");
    if (assistantForm) {
      event.preventDefault();
      sendAssistant(assistantForm);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeLogin();
  });
}

async function boot() {
  bindUi();
  applyRouteParams();
  await loadPublic();
  renderHeroStack();
  renderModels();
  renderGallery();
  renderAccount();
  renderAuth();
  if (state.token) await loadPrivate({ quiet: true });
}

boot().catch((error) => {
  console.error(error);
  toast(`Ошибка загрузки: ${error.message}`, "danger");
});
