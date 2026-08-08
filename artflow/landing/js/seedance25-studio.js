(() => {
  "use strict";

  const MODEL = "bytedance/seedance-2-5";
  const GENERATE_PATH = "/api/web/generate/video";
  const UPLOAD_PATH = "/api/web/seedance25/upload-reference";
  const TOKEN_PREFIX = "__apix_seedance25:";
  const originalFetch = window.fetch.bind(window);

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

  function ensurePanel() {
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
          <b>Режим определяется автоматически</b>
          <p>Без референсов — text-to-video; ровно 1 фото — first frame; 2+ фото или любое видео/аудио — multimodal references.</p>
        </div>
      </div>
      <div class="composer-row">
        <label>
          <span>Доп. видео-файлы</span>
          <input data-s25-video-files type="file" accept="video/mp4,video/quicktime,video/x-matroska,.mp4,.mov,.mkv" multiple />
        </label>
        <label>
          <span>Аудио-файлы</span>
          <input data-s25-audio-files type="file" accept="audio/*,.mp3,.wav,.aac,.m4a,.ogg" multiple />
        </label>
      </div>
      <div class="composer-row">
        <label><span>Доп. video refs по URL</span><textarea data-s25-video-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label>
        <label><span>Audio refs по URL</span><textarea data-s25-audio-urls rows="2" placeholder="Одна HTTPS-ссылка на строку"></textarea></label>
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
    const uploadedVideos = [];
    for (const file of videoFiles) uploadedVideos.push(await upload(file, init));
    const uploadedAudios = [];
    for (const file of audioFiles) uploadedAudios.push(await upload(file, init));

    const videoUrls = lines(panel?.querySelector("[data-s25-video-urls]")?.value, 10);
    const audioUrls = lines(panel?.querySelector("[data-s25-audio-urls]")?.value, 10);
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
