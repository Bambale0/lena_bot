// Review and submission share the same ordering, deduplication and limits.
function seedance25MaterialSelection(existing, panel, files) {
  const merge = (kind, selector, limit) => {
    const links = String(panel?.querySelector(selector)?.value || "")
      .split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean).slice(0, limit);
    return [...new Set([
      ...(existing[kind] || []), ...links, ...(files[kind] || []).slice(0, limit),
    ].filter(Boolean))].slice(0, limit);
  };
  return {
    images: merge("images", "[data-s25-image-urls]", 30),
    videos: merge("videos", "[data-s25-video-urls]", 10),
    audios: merge("audios", "[data-s25-audio-urls]", 10),
  };
}

const composerMaterialReview = (() => {
  "use strict";

  const MODEL = "bytedance/seedance-2-5";
  const GENERATE_PATH = "/api/web/generate/video";
  const UPLOAD_PATH = "/api/web/seedance25/upload-reference";
  const TOKEN_PREFIX = "__apix_seedance25:";
  const originalFetch = window.fetch.bind(window);

  let preparation = null;

  function panelFiles(panel) {
    const files = (selector, limit) => Array.from(panel?.querySelector(selector)?.files || []).slice(0, limit);
    return {
      images: files("[data-s25-image-files]", 30),
      videos: files("[data-s25-video-files]", 10),
      audios: files("[data-s25-audio-files]", 10),
    };
  }

  function selectionSnapshot(form) {
    const panel = form?.querySelector("[data-seedance25-studio]");
    return [
      state.authEpoch, state.user?.id, state.token, state.generationKind,
      state.routeModelKey, state.routeFeedRemixId, state.routeSourceReferenceUrl,
      panel, panel?.hidden,
      ...Array.from(form.querySelectorAll("input, select, textarea")).flatMap((field) => [
        // Ratio availability is derived from the uploaded URLs, not user input.
        field, field.name === "aspect_ratio" ? null : field.disabled,
        field.value, field.checked, ...Array.from(field.files || []),
      ]),
    ];
  }

  function matchesSelection(candidate) {
    if (!candidate) return false;
    const current = selectionSnapshot(candidate.form);
    return current.length === candidate.snapshot.length
      && current.every((value, index) => value === candidate.snapshot[index]);
  }

  function referenceUrl(file, channel, init) {
    if (!matchesSelection(preparation)) return null;
    if (init && (authHeaders(init)["X-Web-Auth-Token"] || "") !== preparation.token) return null;
    return preparation[channel].get(file) || null;
  }

  async function prepareReview(form, { signal } = {}) {
    preparation = null;
    const candidate = {
      form, snapshot: selectionSnapshot(form), token: state.token || "",
      generic: new Map(), panel: new Map(),
    };
    const assertCurrent = () => {
      if (signal?.aborted) throw new DOMException("Upload timed out", "AbortError");
      if (!matchesSelection(candidate)) throw new Error("Материалы или параметры изменились. Проверьте их ещё раз.");
    };
    for (const file of referenceFiles(form)) {
      assertCurrent();
      candidate.generic.set(file, await uploadReference(file, { signal }));
    }
    const files = panelFiles(form.querySelector("[data-seedance25-studio]:not([hidden])"));
    const init = { headers: candidate.token ? { "X-Web-Auth-Token": candidate.token } : {}, signal };
    for (const file of [...files.images, ...files.videos, ...files.audios]) {
      assertCurrent();
      candidate.panel.set(file, await upload(file, init));
    }
    assertCurrent();
    preparation = candidate;
  }

  function preparedReferences(form) {
    if (preparation?.form !== form || !matchesSelection(preparation)) return null;
    return uniqueSafeUrls([
      ...referenceFiles(form).map((file) => preparation.generic.get(file)), ...referenceLinkValues(form),
    ]);
  }

  function preparedMaterials(form) {
    const references = preparedReferences(form);
    if (!references) return null;
    const panel = form.querySelector("[data-seedance25-studio]:not([hidden])");
    const files = panelFiles(panel);
    return seedance25MaterialSelection({
      images: references,
      videos: [selectedOptionValue(form, "video_url")],
    }, panel, Object.fromEntries(Object.entries(files).map(([kind, items]) => [kind, items.map((file) => preparation.panel.get(file))])));
  }

  function modelSelect() {
    return document.querySelector("[data-account-model-select]");
  }

  function selected() {
    return modelSelect()?.value === MODEL;
  }

  function exactFeedRepeat() {
    // The shared composer owns exact replay photos and the duration override.
    // General-generation controls must never be injected into its author recipe.
    return typeof state !== "undefined" && state.feedRepeat?.scope === feedRepeatScope()
      && state.feedRepeat?.authEpoch === state.authEpoch
      && typeof state.feedRepeat?.source?.source_has_video_reference === "boolean";
  }

  function token(key, value) {
    return `${TOKEN_PREFIX}${key}=${String(value)}`;
  }

  function genericSeedModeLabel() {
    const grok = document.querySelector('select[name="grok_mode"]');
    return grok?.closest("label") || null;
  }

  function applySurface() {
    const refs = document.querySelector("[data-reference-section]");
    const seedMode = genericSeedModeLabel();
    if (refs) refs.style.display = selected() && !exactFeedRepeat() ? "none" : "";
    if (seedMode) seedMode.style.display = selected() ? "none" : "";
  }

  function ensurePanel() {
    applySurface();
    const existing = document.querySelector("[data-seedance25-studio]");
    if (!selected() || exactFeedRepeat()) {
      if (existing) existing.hidden = true;
      return;
    }
    if (existing) {
      existing.hidden = false;
      return;
    }

    const composer = document.querySelector(".account-composer");
    const intro = composer?.querySelector(".composer-section-intro");
    const referenceSection = composer?.querySelector("[data-reference-section]");
    if (!composer || (!intro && !referenceSection)) return;

    const panel = document.createElement("div");
    panel.dataset.seedance25Studio = "1";
    panel.className = "composer-section";
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", "Материалы Seedance 2.5");
    panel.innerHTML = `
      <div class="composer-main-settings-head">
        <div>
          <span>Seedance 2.5</span><b>Добавьте материалы</b>
          <p>Можно выбрать фото, видео, аудио или сочетать их. Без файлов видео создаётся только по тексту.</p>
        </div>
      </div>
      <div class="composer-row">
        <label data-s25-material="photo">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 6-5 4 4 3-3 5 5"/></svg>
          <span>Фото · до 30</span>
          <input data-s25-image-files type="file" accept="image/*,.jpg,.jpeg,.png,.webp,.gif,.bmp" multiple />
        </label>
        <label data-s25-material="video">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4M10 9l4 3-4 3Z"/></svg>
          <span>Видео · до 10</span>
          <input data-s25-video-files type="file" accept="video/mp4,video/quicktime,video/x-matroska,.mp4,.mov,.mkv" multiple />
        </label>
        <label data-s25-material="audio">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/></svg>
          <span>Аудио · до 10</span>
          <input data-s25-audio-files type="file" accept="audio/*,.mp3,.wav,.aac,.m4a,.ogg" multiple />
        </label>
      </div>
      <details class="composer-disclosure"><summary>Дополнительные настройки</summary><div class="composer-disclosure-body">
        <p>Качество 480p / 720p / 1080p выбирается в общих параметрах.</p>
        <div class="composer-row"><label><span>Фото по ссылкам</span><textarea data-s25-image-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label></div>
        <div class="composer-row"><label><span>Видео по ссылкам</span><textarea data-s25-video-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label><label><span>Аудио по ссылкам</span><textarea data-s25-audio-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label></div>
        <div class="composer-row"><label><span>Точная длительность 4–30 сек</span><input data-s25-duration type="number" min="4" max="30" /></label><label><span>Формат файла</span><select data-s25-output><option value="mp4">MP4</option><option value="mov">MOV</option></select></label></div>
        <div class="composer-row"><label class="check-line"><input data-s25-auto-duration type="checkbox" /><span>Автоматическая длительность</span></label><label class="check-line"><input data-s25-generate-audio type="checkbox" checked /><span>Создавать звук</span></label></div>
        <div class="composer-row"><label class="check-line"><input data-s25-return-frame type="checkbox" /><span>Вернуть последний кадр</span></label><label class="check-line"><input data-s25-web-search type="checkbox" /><span>Использовать поиск в интернете</span></label></div>
      </div></details>
    `;
    if (intro) intro.insertAdjacentElement("afterend", panel);
    else referenceSection.insertAdjacentElement("beforebegin", panel);

  }

  function generationUrl(input) {
    if (typeof input === "string") return input;
    if (input instanceof URL) return input.toString();
    return input?.url || "";
  }

  function authHeaders(init) {
    const source = new Headers(init?.headers || {});
    const headers = {};
    const tokenValue = source.get("X-Web-Auth-Token");
    if (tokenValue) headers["X-Web-Auth-Token"] = tokenValue;
    return headers;
  }

  async function upload(file, init) {
    const prepared = referenceUrl(file, "panel", init);
    if (prepared) return prepared;
    const form = new FormData();
    form.append("file", file);
    const response = await originalFetch(UPLOAD_PATH, {
      method: "POST",
      body: form,
      credentials: "same-origin",
      headers: authHeaders(init),
      signal: init?.signal,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || payload.detail || `Upload HTTP ${response.status}`);
    const data = payload.data || payload;
    const url = String(data.url || "").trim();
    if (!url) throw new Error("Seedance 2.5 upload did not return URL");
    return url;
  }

  window.fetch = async (input, init = {}) => {
    const url = generationUrl(input);
    const isGeneration = (url.includes(GENERATE_PATH) || /\/api\/web\/feed\/\d+\/remix(?:\/quote)?$/.test(url))
      && String(init.method || "GET").toUpperCase() === "POST";
    if (!isGeneration || typeof init.body !== "string") return originalFetch(input, init);

    let body;
    try {
      body = JSON.parse(init.body);
    } catch {
      return originalFetch(input, init);
    }
    if (String(body.model || "") !== MODEL) return originalFetch(input, init);
    if (/\/api\/web\/feed\/\d+\/remix(?:\/quote)?$/.test(url) && exactFeedRepeat()) {
      return originalFetch(input, init);
    }

    const panel = document.querySelector("[data-seedance25-studio]");
    const files = panelFiles(panel);
    const uploadedImages = [];
    for (const file of files.images) uploadedImages.push(await upload(file, init));
    const uploadedVideos = [];
    for (const file of files.videos) uploadedVideos.push(await upload(file, init));
    const uploadedAudios = [];
    for (const file of files.audios) uploadedAudios.push(await upload(file, init));

    const materials = seedance25MaterialSelection({
      images: [String(body.image_url || "").trim(), ...(Array.isArray(body.reference_urls) ? body.reference_urls.map(String) : [])],
      videos: [String(body.video_url || "").trim()],
      audios: Array.isArray(body.audio_ids) ? body.audio_ids.map(String) : [],
    }, panel, { images: uploadedImages, videos: uploadedVideos, audios: uploadedAudios });
    const { images: allImages, videos: allVideos, audios: allAudios } = materials;
    body.image_url = allImages[0] || null;
    body.reference_urls = allImages.slice(1);
    body.video_url = allVideos[0] || null;

    const controls = [
      token("output_format", panel?.querySelector("[data-s25-output]")?.value === "mov" ? "mov" : "mp4"),
      token("generate_audio", Boolean(panel?.querySelector("[data-s25-generate-audio]")?.checked)),
      token("return_last_frame", Boolean(panel?.querySelector("[data-s25-return-frame]")?.checked)),
      token("web_search", Boolean(panel?.querySelector("[data-s25-web-search]")?.checked)),
      ...allVideos.slice(1).map((ref) => token("video_ref", ref)),
    ];
    const autoDuration = Boolean(panel?.querySelector("[data-s25-auto-duration]")?.checked);
    const exact = Number(panel?.querySelector("[data-s25-duration]")?.value || 0);
    if (autoDuration) controls.push(token("duration", -1));
    else if (exact) controls.push(token("duration", Math.max(4, Math.min(30, exact))));

    body.audio_ids = [...allAudios, ...controls];
    body.character_ids = [];
    body.mode = "text";
    body.grok_mode = null;

    return originalFetch(input, { ...init, body: JSON.stringify(body) });
  };

  document.addEventListener("change", (event) => {
    if (event.target === modelSelect()) ensurePanel();
  }, true);
  new MutationObserver(ensurePanel).observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensurePanel);
  else ensurePanel();
  return { prepare: prepareReview, references: preparedReferences, materials: preparedMaterials, referenceUrl };
})();

// Suno source-audio product surface. It lives in this already-loaded Studio
// enhancer bundle so the standalone website gets own-audio support without
// duplicating the core composer.
(() => {
  "use strict";

  const NORMAL_PATH = "/api/web/generate/music";
  const UPLOAD_PATH = "/api/web/music/source-audio";
  const SOURCE_PATH = "/api/web/music/from-audio";
  const originalFetch = window.fetch.bind(window);
  let file = null;
  let duration = 0;

  function modelSelect() {
    return document.querySelector("[data-account-model-select]");
  }

  function selected() {
    return String(modelSelect()?.value || "").startsWith("suno/");
  }

  function authHeaders(init) {
    const source = new Headers(init?.headers || {});
    const headers = {};
    const tokenValue = source.get("X-Web-Auth-Token");
    if (tokenValue) headers["X-Web-Auth-Token"] = tokenValue;
    return headers;
  }

  function mediaDuration(audioFile) {
    return new Promise((resolve, reject) => {
      const audio = document.createElement("audio");
      const url = URL.createObjectURL(audioFile);
      audio.preload = "metadata";
      audio.onloadedmetadata = () => {
        const value = Number(audio.duration || 0);
        URL.revokeObjectURL(url);
        resolve(value);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Не удалось прочитать аудиофайл"));
      };
      audio.src = url;
    });
  }

  function setStatus(panel, text, isError = false) {
    const node = panel?.querySelector("[data-suno-web-status]");
    if (!node) return;
    node.textContent = text || (file ? `${file.name} · ${Math.round(duration)} сек` : "Без файла — обычная генерация Suno по описанию");
    node.style.color = isError ? "#ef4444" : "";
  }

  function ensurePanel() {
    const existing = document.querySelector("[data-suno-web-source]");
    if (!selected()) {
      if (existing) existing.hidden = true;
      return;
    }
    if (existing) {
      existing.hidden = false;
      return;
    }
    const body = document.querySelector("[data-optional-section] .composer-disclosure-body");
    if (!body) return;

    const panel = document.createElement("div");
    panel.dataset.sunoWebSource = "1";
    panel.className = "composer-section";
    panel.innerHTML = `
      <div class="composer-main-settings-head">
        <div><span>Suno · свой аудиофайл</span><b>Загрузите трек до 8 минут</b><p>Cover, продолжение трека, добавление вокала или инструментала работают через официальный Suno upload flow.</p></div>
      </div>
      <div class="composer-row">
        <label><span>Исходное аудио</span><input data-suno-web-file type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus" /></label>
        <label><span>Что сделать</span><select data-suno-web-operation><option value="cover">Cover / изменить стиль</option><option value="extend">Продолжить трек</option><option value="add_vocals">Добавить вокал</option><option value="add_instrumental">Добавить инструментал</option></select></label>
      </div>
      <div class="composer-row">
        <label><span>Название · для вокала/инструментала</span><input data-suno-web-title type="text" maxlength="100" /></label>
        <label><span>Стиль / теги</span><input data-suno-web-style type="text" maxlength="1000" placeholder="Jazz, cinematic, pop..." /></label>
      </div>
      <small data-suno-web-status></small>
      <button class="button ghost" type="button" data-suno-web-clear hidden>Убрать аудиофайл</button>
    `;
    body.appendChild(panel);

    panel.querySelector("[data-suno-web-file]")?.addEventListener("change", async (event) => {
      const picked = event.currentTarget.files?.[0] || null;
      event.currentTarget.value = "";
      if (!picked) return;
      try {
        if (!/\.(mp3|wav|m4a|aac|flac|ogg|opus)$/i.test(picked.name)) throw new Error("Поддерживаются MP3, WAV, M4A, AAC, FLAC, OGG и OPUS");
        if (picked.size > 100 * 1024 * 1024) throw new Error("Файл больше 100 МБ");
        const seconds = await mediaDuration(picked);
        if (!seconds || seconds > 480.05) throw new Error("Suno принимает исходное аудио до 8 минут");
        file = picked;
        duration = seconds;
        panel.querySelector("[data-suno-web-clear]").hidden = false;
        setStatus(panel, "");
      } catch (error) {
        file = null;
        duration = 0;
        setStatus(panel, error instanceof Error ? error.message : "Некорректный аудиофайл", true);
      }
    });
    panel.querySelector("[data-suno-web-clear]")?.addEventListener("click", () => {
      file = null;
      duration = 0;
      panel.querySelector("[data-suno-web-clear]").hidden = true;
      setStatus(panel, "");
    });
    setStatus(panel, "");
  }

  async function upload(init) {
    const form = new FormData();
    form.append("file", file);
    const response = await originalFetch(UPLOAD_PATH, {
      method: "POST",
      body: form,
      credentials: "same-origin",
      headers: authHeaders(init),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) throw new Error(payload.error || payload.detail || `Upload HTTP ${response.status}`);
    const data = payload.data || payload;
    if (!data.url) throw new Error("Suno upload did not return URL");
    return data;
  }

  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : (input instanceof URL ? input.toString() : input?.url || "");
    const isMusic = url.includes(NORMAL_PATH) && String(init.method || "GET").toUpperCase() === "POST";
    if (!isMusic || !file || typeof init.body !== "string") return originalFetch(input, init);

    let body;
    try { body = JSON.parse(init.body); } catch { return originalFetch(input, init); }
    const uploaded = await upload(init);
    const panel = document.querySelector("[data-suno-web-source]");
    const operation = panel?.querySelector("[data-suno-web-operation]")?.value || "cover";
    const title = String(panel?.querySelector("[data-suno-web-title]")?.value || "").trim();
    const style = String(panel?.querySelector("[data-suno-web-style]")?.value || "").trim();
    const payload = {
      ...body,
      model: modelSelect()?.value || undefined,
      operation,
      upload_url: uploaded.url,
      source_duration: Number(uploaded.duration_seconds || duration || 0),
      continue_at: operation === "extend" ? Math.max(0.1, Number(uploaded.duration_seconds || duration || 0) - 0.5) : undefined,
      title: title || undefined,
      style: style || undefined,
    };
    return originalFetch(SOURCE_PATH, { ...init, body: JSON.stringify(payload) });
  };

  document.addEventListener("change", (event) => {
    if (event.target === modelSelect()) ensurePanel();
  }, true);
  new MutationObserver(ensurePanel).observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensurePanel);
  else ensurePanel();
})();
