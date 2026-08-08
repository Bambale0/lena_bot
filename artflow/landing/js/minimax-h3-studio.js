(() => {
  "use strict";

  const H3_MODEL = "minimax-h3/text-to-video";
  const GENERATE_PATH = "/api/web/generate/video";
  const UPLOAD_PATH = "/api/web/h3/upload-reference";
  const MAX_IMAGES = 9;
  const MAX_VIDEOS = 3;
  const MAX_AUDIOS = 3;
  const MAX_FILES = 12;
  const MIN_SECONDS = 2;
  const MAX_SECONDS = 15;
  const MAX_TOTAL_SECONDS = 15;
  const originalFetch = window.fetch.bind(window);

  let selectedVideos = [];
  let selectedAudios = [];

  function modelSelect() {
    return document.querySelector("[data-account-model-select]");
  }

  function isH3() {
    return modelSelect()?.value === H3_MODEL;
  }

  function parseLines(value) {
    return String(value || "")
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setOptions(select, values, current) {
    if (!select) return;
    const next = current && values.includes(current) ? current : values[0];
    select.innerHTML = values.map((value) => `<option value="${value}">${value}</option>`).join("");
    select.value = next;
  }

  function configureH3Controls() {
    if (!isH3()) return;
    const form = document.querySelector(".account-composer");
    if (!form) return;

    const duration = form.querySelector('select[name="duration"]');
    if (duration) setOptions(duration, Array.from({ length: 12 }, (_, index) => String(index + 4)), duration.value);

    const resolution = form.querySelector('select[name="resolution"]');
    if (resolution) {
      setOptions(resolution, ["2K", "768P"], resolution.value);
      const label = resolution.closest("label")?.querySelector("span");
      if (label) label.textContent = "Качество";
    }

    const ratio = form.querySelector('select[name="aspect_ratio"]');
    if (ratio) {
      setOptions(ratio, ["adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"], ratio.value);
      if (!ratio.dataset.h3Defaulted) {
        ratio.value = "adaptive";
        ratio.dataset.h3Defaulted = "1";
      }
    }

    const referenceInput = form.querySelector('input[name="reference_file"]');
    if (referenceInput) {
      referenceInput.multiple = true;
      referenceInput.accept = "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp,.heic,.heif";
    }
  }

  function mediaDuration(file, kind) {
    return new Promise((resolve, reject) => {
      const media = document.createElement(kind);
      const url = URL.createObjectURL(file);
      media.preload = "metadata";
      media.onloadedmetadata = () => {
        const value = Number(media.duration || 0);
        URL.revokeObjectURL(url);
        resolve(value);
      };
      media.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error(`Не удалось прочитать длительность ${file.name}`));
      };
      media.src = url;
    });
  }

  async function validateFiles(files, kind) {
    const maxCount = kind === "video" ? MAX_VIDEOS : MAX_AUDIOS;
    const maxBytes = (kind === "video" ? 50 : 15) * 1024 * 1024;
    const extension = kind === "video" ? /\.(mp4|mov)$/i : /\.(mp3|wav)$/i;
    const picked = Array.from(files || []).slice(0, maxCount);
    let totalSeconds = 0;
    for (const file of picked) {
      if (!extension.test(file.name)) {
        throw new Error(kind === "video" ? "Видео H3: только MP4/MOV" : "Аудио H3: только MP3/WAV");
      }
      if (file.size > maxBytes) {
        throw new Error(`${file.name}: максимум ${kind === "video" ? 50 : 15} МБ`);
      }
      const seconds = await mediaDuration(file, kind);
      if (seconds < MIN_SECONDS || seconds > MAX_SECONDS) {
        throw new Error(`${file.name}: длительность ${MIN_SECONDS}–${MAX_SECONDS} сек`);
      }
      totalSeconds += seconds;
    }
    if (totalSeconds > MAX_TOTAL_SECONDS + 0.05) {
      throw new Error(`Суммарная длительность ${kind === "video" ? "видео" : "аудио"} — максимум ${MAX_TOTAL_SECONDS} сек`);
    }
    return picked;
  }

  function ensurePanel() {
    const old = document.querySelector("[data-h3-web-reference-panel]");
    if (!isH3()) {
      if (old) old.hidden = true;
      return;
    }

    configureH3Controls();
    if (old) {
      old.hidden = false;
      return;
    }

    const body = document.querySelector("[data-optional-section] .composer-disclosure-body");
    if (!body) return;

    const panel = document.createElement("div");
    panel.dataset.h3WebReferencePanel = "1";
    panel.className = "composer-section";
    panel.innerHTML = `
      <div class="composer-main-settings-head">
        <div>
          <span>MiniMax H3</span>
          <b>Одна модель — маршрут определяется автоматически</b>
          <p>Без референсов — Text-to-Video; 1 фото — первый кадр; 2 фото — первый+последний; 3+ фото или видео/аудио — Reference-to-Video.</p>
        </div>
      </div>
      <div class="composer-row">
        <label>
          <span>Видео · до ${MAX_VIDEOS}, всего до ${MAX_TOTAL_SECONDS} сек</span>
          <input data-h3-web-video-files type="file" accept="video/mp4,video/quicktime,.mp4,.mov" multiple />
        </label>
        <label>
          <span>Аудио · до ${MAX_AUDIOS}, всего до ${MAX_TOTAL_SECONDS} сек</span>
          <input data-h3-web-audio-files type="file" accept="audio/mpeg,audio/wav,.mp3,.wav" multiple />
        </label>
      </div>
      <div class="composer-row">
        <label>
          <span>Видео по URL</span>
          <textarea data-h3-web-video-urls rows="2" placeholder="До ${MAX_VIDEOS} HTTPS-ссылок, по одной в строке"></textarea>
        </label>
        <label>
          <span>Аудио по URL</span>
          <textarea data-h3-web-audio-urls rows="2" placeholder="До ${MAX_AUDIOS} HTTPS-ссылок, по одной в строке"></textarea>
        </label>
      </div>
      <small>Фото: до ${MAX_IMAGES}; все референсы вместе: до ${MAX_FILES}. Видео/аудио: каждый файл ${MIN_SECONDS}–${MAX_SECONDS} сек. Аудио нельзя использовать без фото или видео.</small>
      <small data-h3-web-reference-status></small>
    `;
    body.appendChild(panel);

    panel.querySelector("[data-h3-web-video-files]")?.addEventListener("change", async (event) => {
      try {
        selectedVideos = await validateFiles(event.currentTarget.files, "video");
        updateStatus("");
      } catch (error) {
        selectedVideos = [];
        event.currentTarget.value = "";
        updateStatus(error instanceof Error ? error.message : "Некорректные видео");
      }
    });
    panel.querySelector("[data-h3-web-audio-files]")?.addEventListener("change", async (event) => {
      try {
        selectedAudios = await validateFiles(event.currentTarget.files, "audio");
        updateStatus("");
      } catch (error) {
        selectedAudios = [];
        event.currentTarget.value = "";
        updateStatus(error instanceof Error ? error.message : "Некорректное аудио");
      }
    });
    updateStatus("");
  }

  function updateStatus(error) {
    const status = document.querySelector("[data-h3-web-reference-status]");
    if (!status) return;
    status.textContent = error || `Файлы: видео ${selectedVideos.length}/${MAX_VIDEOS} · аудио ${selectedAudios.length}/${MAX_AUDIOS}`;
    status.style.color = error ? "#ef4444" : "";
  }

  function generationUrl(input) {
    if (typeof input === "string") return input;
    if (input instanceof URL) return input.toString();
    return input?.url || "";
  }

  function authHeaders(init) {
    const source = new Headers(init?.headers || {});
    const headers = {};
    const token = source.get("X-Web-Auth-Token");
    if (token) headers["X-Web-Auth-Token"] = token;
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
    if (!url) throw new Error("Сервер не вернул URL референса");
    return url;
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
    if (String(body.model || "") !== H3_MODEL) return originalFetch(input, init);

    const panel = document.querySelector("[data-h3-web-reference-panel]");
    const extraVideoUrls = parseLines(panel?.querySelector("[data-h3-web-video-urls]")?.value).slice(0, MAX_VIDEOS);
    const audioUrls = parseLines(panel?.querySelector("[data-h3-web-audio-urls]")?.value).slice(0, MAX_AUDIOS);

    const uploadedVideos = [];
    for (const file of selectedVideos.slice(0, MAX_VIDEOS)) uploadedVideos.push(await upload(file, init));
    const uploadedAudios = [];
    for (const file of selectedAudios.slice(0, MAX_AUDIOS)) uploadedAudios.push(await upload(file, init));

    const existingPrimary = String(body.video_url || "").trim();
    const existingExtra = Array.isArray(body.character_ids) ? body.character_ids.map(String).filter(Boolean) : [];
    const videos = [existingPrimary, ...existingExtra, ...extraVideoUrls, ...uploadedVideos]
      .filter(Boolean)
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, MAX_VIDEOS);
    body.video_url = videos[0] || null;
    body.character_ids = videos.slice(1);

    const existingAudio = Array.isArray(body.audio_ids) ? body.audio_ids.map(String).filter(Boolean) : [];
    body.audio_ids = [...existingAudio, ...audioUrls, ...uploadedAudios]
      .filter(Boolean)
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, MAX_AUDIOS);

    const images = [String(body.image_url || "").trim(), ...(Array.isArray(body.reference_urls) ? body.reference_urls.map(String) : [])]
      .filter(Boolean)
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, MAX_IMAGES);
    body.image_url = images[0] || null;
    body.reference_urls = images.slice(1);

    const refCount = images.length + videos.length + body.audio_ids.length;
    if (refCount > MAX_FILES) throw new Error(`MiniMax H3: максимум ${MAX_FILES} референсных файлов`);
    if (body.audio_ids.length && !images.length && !videos.length) {
      throw new Error("MiniMax H3: аудио-референс требует фото или видео");
    }

    body.duration = Math.max(4, Math.min(15, Number(body.duration) || 6));
    body.resolution = body.resolution === "768P" ? "768P" : "2K";

    if (!images.length && !videos.length && !body.audio_ids.length) {
      if (!body.aspect_ratio || body.aspect_ratio === "adaptive") body.aspect_ratio = "16:9";
      body.mode = "text";
    } else if (images.length <= 2 && !videos.length && !body.audio_ids.length) {
      body.aspect_ratio = "adaptive";
      body.mode = "image";
    } else {
      body.aspect_ratio = body.aspect_ratio || "adaptive";
      body.mode = "video";
    }

    return originalFetch(input, { ...init, body: JSON.stringify(body) });
  };

  document.addEventListener("change", (event) => {
    if (event.target === modelSelect()) ensurePanel();
  }, true);

  new MutationObserver(ensurePanel).observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensurePanel);
  else ensurePanel();
})();
