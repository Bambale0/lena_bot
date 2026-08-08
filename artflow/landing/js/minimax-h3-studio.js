(() => {
  "use strict";

  const H3_REFERENCE_MODEL = "minimax-h3/reference-to-video";
  const GENERATE_PATH = "/api/web/generate/video";
  const UPLOAD_PATH = "/api/web/upload-media";
  const originalFetch = window.fetch.bind(window);

  let selectedVideos = [];
  let selectedAudio = null;

  function modelSelect() {
    return document.querySelector("[data-account-model-select]");
  }

  function parseLines(value) {
    return String(value || "")
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function ensurePanel() {
    const select = modelSelect();
    const old = document.querySelector("[data-h3-web-reference-panel]");
    if (!select || select.value !== H3_REFERENCE_MODEL) {
      if (old) old.hidden = true;
      return;
    }

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
          <span>MiniMax H3 Reference</span>
          <b>Фото + видео + аудио в одной генерации</b>
          <p>Фото добавляются в блоке «Референсы» выше. Здесь можно добавить до 3 коротких видео и 1 аудио.</p>
        </div>
      </div>
      <div class="composer-row">
        <label>
          <span>Видео-файлы · до 3</span>
          <input data-h3-web-video-files type="file" accept="video/*" multiple />
        </label>
        <label>
          <span>Аудио-файл · до 1</span>
          <input data-h3-web-audio-file type="file" accept="audio/*" />
        </label>
      </div>
      <div class="composer-row">
        <label>
          <span>Доп. видео по URL</span>
          <textarea data-h3-web-video-urls rows="2" placeholder="До 3 HTTPS-ссылок, по одной в строке"></textarea>
        </label>
        <label>
          <span>Аудио по URL</span>
          <textarea data-h3-web-audio-url rows="2" placeholder="Одна HTTPS-ссылка на аудиофайл"></textarea>
        </label>
      </div>
      <small data-h3-web-reference-status>Можно сочетать фото, видео и аудио одновременно.</small>
    `;
    body.appendChild(panel);

    panel.querySelector("[data-h3-web-video-files]")?.addEventListener("change", (event) => {
      selectedVideos = Array.from(event.currentTarget.files || []).slice(0, 3);
      updateStatus();
    });
    panel.querySelector("[data-h3-web-audio-file]")?.addEventListener("change", (event) => {
      selectedAudio = event.currentTarget.files?.[0] || null;
      updateStatus();
    });
  }

  function updateStatus() {
    const status = document.querySelector("[data-h3-web-reference-status]");
    if (!status) return;
    status.textContent = `Файлы: видео ${selectedVideos.length}/3 · аудио ${selectedAudio ? 1 : 0}/1`;
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
    if (String(body.model || "") !== H3_REFERENCE_MODEL) return originalFetch(input, init);

    const panel = document.querySelector("[data-h3-web-reference-panel]");
    const extraVideoUrls = parseLines(panel?.querySelector("[data-h3-web-video-urls]")?.value);
    const audioUrls = parseLines(panel?.querySelector("[data-h3-web-audio-url]")?.value);

    const uploadedVideos = [];
    for (const file of selectedVideos.slice(0, 3)) uploadedVideos.push(await upload(file, init));
    const uploadedAudio = selectedAudio ? await upload(selectedAudio, init) : "";

    const existingPrimary = String(body.video_url || "").trim();
    const existingExtra = Array.isArray(body.character_ids) ? body.character_ids.map(String).filter(Boolean) : [];
    const videos = [existingPrimary, ...existingExtra, ...extraVideoUrls, ...uploadedVideos]
      .filter(Boolean)
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, 3);
    body.video_url = videos[0] || null;
    body.character_ids = videos.slice(1);

    const existingAudio = Array.isArray(body.audio_ids) ? body.audio_ids.map(String).filter(Boolean) : [];
    body.audio_ids = [existingAudio[0], audioUrls[0], uploadedAudio].filter(Boolean).slice(0, 1);

    return originalFetch(input, { ...init, body: JSON.stringify(body) });
  };

  document.addEventListener("change", (event) => {
    if (event.target === modelSelect()) ensurePanel();
  }, true);

  new MutationObserver(ensurePanel).observe(document.documentElement, { childList: true, subtree: true });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensurePanel);
  else ensurePanel();
})();
