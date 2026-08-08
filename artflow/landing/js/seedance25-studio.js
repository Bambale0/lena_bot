(() => {
  "use strict";

  const MODEL = "bytedance/seedance-2-5";
  const GENERATE_PATH = "/api/web/generate/video";
  const UPLOAD_PATH = "/api/web/seedance25/upload-reference";
  const TOKEN_PREFIX = "__apix_seedance25:";
  const originalFetch = window.fetch.bind(window);

  let imageFiles = [];
  let videoFiles = [];
  let audioFiles = [];

  function modelSelect() {
    return document.querySelector("[data-account-model-select]");
  }

  function selected() {
    return modelSelect()?.value === MODEL;
  }

  function token(key, value) {
    return `${TOKEN_PREFIX}${key}=${String(value)}`;
  }

  function lines(value, limit) {
    return String(value || "")
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, limit);
  }

  function genericSeedModeLabel() {
    const grok = document.querySelector('select[name="grok_mode"]');
    return grok?.closest("label") || null;
  }

  function applySurface() {
    const refs = document.querySelector("[data-reference-section]");
    const seedMode = genericSeedModeLabel();
    if (refs) refs.style.display = selected() ? "none" : "";
    if (seedMode) seedMode.style.display = selected() ? "none" : "";
  }

  function ensurePanel() {
    applySurface();
    const existing = document.querySelector("[data-seedance25-studio]");
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
    panel.dataset.seedance25Studio = "1";
    panel.className = "composer-section";
    panel.innerHTML = `
      <div class="composer-main-settings-head">
        <div>
          <span>Seedance 2.5</span>
          <b>Один мультимодальный вход</b>
          <p>Без референсов — text-to-video; ровно 1 фото — first frame с adaptive ratio; 2+ фото или любое видео/аудио — multimodal references.</p>
        </div>
      </div>
      <div class="composer-row">
        <label>
          <span>Фото-файлы · до 30</span>
          <input data-s25-image-files type="file" accept="image/*,.jpg,.jpeg,.png,.webp,.gif,.bmp" multiple />
        </label>
        <label><span>Фото по URL</span><textarea data-s25-image-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label>
      </div>
      <div class="composer-row">
        <label>
          <span>Видео-файлы · до 10</span>
          <input data-s25-video-files type="file" accept="video/mp4,video/quicktime,video/x-matroska,.mp4,.mov,.mkv" multiple />
        </label>
        <label><span>Видео по URL</span><textarea data-s25-video-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label>
      </div>
      <div class="composer-row">
        <label>
          <span>Аудио-файлы · до 10</span>
          <input data-s25-audio-files type="file" accept="audio/*,.mp3,.wav,.aac,.m4a,.ogg" multiple />
        </label>
        <label><span>Аудио по URL</span><textarea data-s25-audio-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label>
      </div>
      <div class="composer-row">
        <label><span>Точная длительность 4–30 сек</span><input data-s25-duration type="number" min="4" max="30" /></label>
        <label><span>Output</span><select data-s25-output><option value="mp4">mp4</option><option value="mov">mov</option></select></label>
      </div>
      <div class="composer-row">
        <label class="check-line"><input data-s25-auto-duration type="checkbox" /><span>Auto duration</span></label>
        <label class="check-line"><input data-s25-generate-audio type="checkbox" checked /><span>Generate audio</span></label>
      </div>
      <div class="composer-row">
        <label class="check-line"><input data-s25-return-frame type="checkbox" /><span>Return last frame</span></label>
        <label class="check-line"><input data-s25-web-search type="checkbox" /><span>Web search grounding</span></label>
      </div>
    `;
    body.appendChild(panel);

    panel.querySelector("[data-s25-image-files]")?.addEventListener("change", (event) => {
      imageFiles = Array.from(event.currentTarget.files || []).slice(0, 30);
    });
    panel.querySelector("[data-s25-video-files]")?.addEventListener("change", (event) => {
      videoFiles = Array.from(event.currentTarget.files || []).slice(0, 10);
    });
    panel.querySelector("[data-s25-audio-files]")?.addEventListener("change", (event) => {
      audioFiles = Array.from(event.currentTarget.files || []).slice(0, 10);
    });
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
    const form = new FormData();
    form.append("file", file);
    const response = await originalFetch(UPLOAD_PATH, {
      method: "POST",
      body: form,
      credentials: "same-origin",
      headers: authHeaders(init),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || payload.detail || `Upload HTTP ${response.status}`);
    const data = payload.data || payload;
    const url = String(data.url || "").trim();
    if (!url) throw new Error("Seedance 2.5 upload did not return URL");
    return url;
  }

  function unique(values) {
    return values.filter(Boolean).filter((item, index, all) => all.indexOf(item) === index);
  }

  window.fetch = async (input, init = {}) => {
    const url = generationUrl(input);
    const isGeneration = url.includes(GENERATE_PATH) && String(init.method || "GET").toUpperCase() === "POST";
    if (!isGeneration || typeof init.body !== "string") return originalFetch(input, init);

    let body;
    try {
      body = JSON.parse(init.body);
    } catch {
      return originalFetch(input, init);
    }
    if (String(body.model || "") !== MODEL) return originalFetch(input, init);

    const panel = document.querySelector("[data-seedance25-studio]");
    const uploadedImages = [];
    for (const file of imageFiles) uploadedImages.push(await upload(file, init));
    const uploadedVideos = [];
    for (const file of videoFiles) uploadedVideos.push(await upload(file, init));
    const uploadedAudios = [];
    for (const file of audioFiles) uploadedAudios.push(await upload(file, init));

    const imageUrls = lines(panel?.querySelector("[data-s25-image-urls]")?.value, 30);
    const videoUrls = lines(panel?.querySelector("[data-s25-video-urls]")?.value, 10);
    const audioUrls = lines(panel?.querySelector("[data-s25-audio-urls]")?.value, 10);

    const existingImages = unique([
      String(body.image_url || "").trim(),
      ...(Array.isArray(body.reference_urls) ? body.reference_urls.map(String) : []),
    ]);
    const allImages = unique([...existingImages, ...imageUrls, ...uploadedImages]).slice(0, 30);
    body.image_url = allImages[0] || null;
    body.reference_urls = allImages.slice(1);

    const primaryVideo = String(body.video_url || "").trim();
    const allVideos = unique([primaryVideo, ...videoUrls, ...uploadedVideos]).slice(0, 10);
    body.video_url = allVideos[0] || null;

    const existingAudio = Array.isArray(body.audio_ids) ? body.audio_ids.map(String) : [];
    const allAudios = unique([...existingAudio, ...audioUrls, ...uploadedAudios]).slice(0, 10);

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
