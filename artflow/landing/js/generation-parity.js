/* APIX standalone Studio generation parity layer.
 *
 * This file intentionally extends the production `prototype-premium.js` Studio
 * instead of creating another standalone Studio implementation. It consumes
 * the same normalized ModelInfo metadata already loaded by that runtime and
 * enriches request payloads only when a capability is present.
 */
(() => {
  "use strict";

  const GEMINI_OMNI = "gemini-omni-video";
  const MAX_GEMINI_MEDIA_SLOTS = 7;
  const MAX_TRIM_SECONDS = 10;
  const MAX_SEED = 2147483647;
  let voices = [];
  let voicesLoading = false;

  const form = () => document.querySelector(".account-composer");
  const field = (name) => form()?.querySelector(`[name='${name}']`) || null;
  const value = (name) => String(field(name)?.value || "").trim();
  const numberOrNull = (name) => {
    const raw = value(name);
    if (!raw) return null;
    const number = Number(raw);
    return Number.isFinite(number) ? number : null;
  };
  const ids = (name, max = 0) => {
    const unique = [];
    const seen = new Set();
    String(field(name)?.value || "").split(/[\n,]+/).forEach((raw) => {
      const item = raw.trim();
      if (!item || seen.has(item)) return;
      seen.add(item);
      unique.push(item);
    });
    return max > 0 ? unique.slice(0, max) : unique;
  };
  const current = () => (typeof currentModel === "function" ? currentModel() : null);
  const capabilityModes = (model) => Array.isArray(model?.modes) && model.modes.length ? model.modes : (model?.capabilities || []);
  const hasMode = (model, mode) => capabilityModes(model).includes(mode);

  function ensureParityControls() {
    const studioForm = form();
    const body = studioForm?.querySelector("[data-optional-section] .composer-disclosure-body");
    if (!body || body.querySelector("[data-generation-parity-controls]")) return;
    const block = document.createElement("div");
    block.dataset.generationParityControls = "";
    block.innerHTML = `
      <div class="composer-row" data-video-trim-row hidden>
        <label><span>Старт видео, сек</span><input name="video_start" type="number" min="0" step="0.1" value="0" /></label>
        <label><span>Конец видео, сек</span><input name="video_end" type="number" min="0" step="0.1" placeholder="до 10 сек" /></label>
      </div>
      <div class="composer-row" data-video-identity-row hidden>
        <label data-audio-ids-label hidden><span>Audio ID</span><textarea name="audio_ids" rows="2" placeholder="Один ID на строку"></textarea></label>
        <label data-character-ids-label hidden><span>Character IDs</span><textarea name="character_ids" rows="2" placeholder="Один ID на строку"></textarea></label>
      </div>
      <div class="composer-row" data-music-detail-row hidden>
        <label><span>Название трека</span><input name="title" maxlength="100" placeholder="Название" /></label>
        <label><span>Стиль трека</span><input name="style" maxlength="1000" placeholder="pop, cinematic, female vocal…" /></label>
      </div>
      <div data-voice-panel hidden>
        <div class="composer-row">
          <label><span>Голос</span><select name="voice_record_id" data-no-custom-select="true"><option value="">Suno вокал</option></select></label>
          <button class="button ghost" type="button" data-voice-refresh-list>Обновить голоса</button>
        </div>
        <details class="composer-disclosure" data-create-voice>
          <summary><span><b>Свой голос</b><small>Создать и подтвердить голосовую модель Suno.</small></span></summary>
          <div class="composer-disclosure-body">
            <div class="composer-row">
              <label><span>Название голоса</span><input name="voice_name" maxlength="128" /></label>
              <label><span>Стиль голоса</span><input name="voice_style" maxlength="256" /></label>
            </div>
            <label><span>Описание</span><textarea name="voice_description" rows="2" maxlength="1000"></textarea></label>
            <label class="reference-upload"><span>Исходное аудио</span><input name="voice_source_file" type="file" accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/aac,audio/flac,audio/ogg" /></label>
            <button class="button ghost" type="button" data-create-voice-button>Создать голос</button>
            <div data-voice-list></div>
          </div>
        </details>
      </div>
    `;
    body.insertBefore(block, body.querySelector("[data-prompt-injections]") || null);

    block.querySelector("[data-voice-refresh-list]")?.addEventListener("click", () => void loadVoices(true));
    block.querySelector("[data-create-voice-button]")?.addEventListener("click", () => void createVoice());
    block.querySelector("[data-voice-list]")?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-voice-action]");
      if (!button) return;
      const voiceId = Number(button.dataset.voiceId || 0);
      if (!voiceId) return;
      const action = button.dataset.voiceAction;
      if (action === "refresh") void refreshVoice(voiceId);
      if (action === "verify") {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/aac,audio/flac,audio/ogg";
        input.addEventListener("change", () => void verifyVoice(voiceId, input.files?.[0]));
        input.click();
      }
    });
  }

  function setVisible(selector, visible) {
    const node = form()?.querySelector(selector);
    if (!node) return;
    node.hidden = !visible;
    node.querySelectorAll("input,select,textarea,button").forEach((control) => {
      if (control.matches("[data-voice-refresh-list],[data-create-voice-button]") || !visible) control.disabled = !visible;
      else control.disabled = false;
    });
  }

  function syncParityControls(model = current()) {
    ensureParityControls();
    if (!model) return;
    const kind = typeof state !== "undefined" ? state.generationKind : "image";
    const video = kind === "video";
    const music = kind === "music";
    const supportsVideo = Boolean(model.supportsVideoInput || hasMode(model, "video") || hasMode(model, "motion"));
    const maxAudio = Number(model.maxAudioIds || 0);
    const maxCharacters = Number(model.maxCharacterIds || 0);

    setVisible("[data-video-trim-row]", video && Boolean(model.supportsVideoInput));
    setVisible("[data-video-identity-row]", video && (maxAudio > 0 || maxCharacters > 0));
    setVisible("[data-audio-ids-label]", video && maxAudio > 0);
    setVisible("[data-character-ids-label]", video && maxCharacters > 0);
    setVisible("[data-music-detail-row]", music);
    setVisible("[data-voice-panel]", music);

    const videoInput = field("video_url");
    if (videoInput) {
      const label = videoInput.closest("label");
      if (label) label.hidden = !video || !supportsVideo;
      videoInput.disabled = !video || !supportsVideo;
    }

    const seed = field("seed");
    if (seed) {
      seed.min = "0";
      seed.max = String(MAX_SEED);
      const label = seed.closest("label");
      if (label) label.hidden = !(video && model.hasSeed);
      seed.disabled = !(video && model.hasSeed);
    }

    const modeSelect = field("grok_mode");
    if (modeSelect) {
      const options = Array.isArray(model.modeOptions) ? model.modeOptions : [];
      if (options.length) {
        modeSelect.innerHTML = options.map((item) => `<option value="${String(item).replace(/"/g, "&quot;")}">${item}</option>`).join("");
      }
      const label = modeSelect.closest("label");
      if (label) label.hidden = !(video && options.length > 0);
      modeSelect.disabled = !(video && options.length > 0);
    }

    if (music && !voicesLoading && !voices.length) void loadVoices(false);
  }

  function validateAdvancedVideo(model, body) {
    if (!model || !body) return;
    if (body.mode === "video" && !body.video_url) throw new Error("Добавьте исходное видео");
    if (body.mode === "motion") {
      if (!body.image_url && !(body.reference_urls || []).length) throw new Error("Для Motion Control нужно фото персонажа");
      if (!body.video_url) throw new Error("Для Motion Control нужно видео движения");
    }
    if (body.video_url && body.video_end != null) {
      if (!(body.video_end > body.video_start)) throw new Error("Конец видео должен быть позже начала");
      if (body.video_end - body.video_start > MAX_TRIM_SECONDS) throw new Error("Фрагмент видео должен быть не длиннее 10 секунд");
    }
    if (body.seed != null && (!Number.isInteger(body.seed) || body.seed < 0 || body.seed > MAX_SEED)) {
      throw new Error(`Seed должен быть целым числом 0–${MAX_SEED}`);
    }
    if (model.key === GEMINI_OMNI) {
      const imageCount = body.mode === "image" ? [body.image_url, ...(body.reference_urls || [])].filter(Boolean).length : 0;
      const slots = imageCount + (body.video_url ? 2 : 0) + (body.character_ids || []).length;
      if (slots > MAX_GEMINI_MEDIA_SLOTS) throw new Error(`Gemini Omni: media slots ${slots}/${MAX_GEMINI_MEDIA_SLOTS}`);
    }
  }

  const baseRequest = typeof request === "function" ? request : null;
  if (baseRequest) {
    request = async function parityRequest(path, options = {}) {
      if (!options?.body || options.body instanceof FormData) return baseRequest(path, options);
      const isGeneration = /\/generate\/(image|video|music)$/.test(path) || /\/feed\/[^/]+\/remix$/.test(path);
      if (!isGeneration) return baseRequest(path, options);
      let body;
      try { body = JSON.parse(options.body); } catch { return baseRequest(path, options); }
      const model = current();
      const kind = typeof state !== "undefined" ? state.generationKind : "image";

      if (kind === "music" && /\/generate\/music$/.test(path)) {
        const selectedVoice = numberOrNull("voice_record_id");
        body.model = model?.key || body.model || undefined;
        body.voice_record_id = selectedVoice || undefined;
        body.title = value("title") || undefined;
        body.style = value("style") || undefined;
        if (selectedVoice) body.instrumental = false;
      }

      if (kind === "video" || /\/generate\/video$/.test(path)) {
        const modes = capabilityModes(model);
        if (modes.includes("motion")) body.mode = "motion";
        else if (body.video_url && modes.includes("video")) body.mode = "video";
        else if ((body.image_url || (body.reference_urls || []).length) && modes.includes("image")) body.mode = "image";
        else if (modes.includes("text")) body.mode = "text";

        body.video_start = numberOrNull("video_start") ?? 0;
        body.video_end = numberOrNull("video_end");
        body.audio_ids = ids("audio_ids", Number(model?.maxAudioIds || 0));
        body.character_ids = ids("character_ids", Number(model?.maxCharacterIds || 0));
        body.seed = model?.hasSeed ? numberOrNull("seed") : null;
        body.grok_mode = value("grok_mode") || body.grok_mode || "normal";
        validateAdvancedVideo(model, body);
      }
      return baseRequest(path, { ...options, body: JSON.stringify(body) });
    };
  }

  const baseSync = typeof syncControlVisibility === "function" ? syncControlVisibility : null;
  if (baseSync) {
    syncControlVisibility = function paritySyncControlVisibility(model) {
      baseSync(model);
      syncParityControls(model);
    };
  }

  function renderVoices() {
    const select = field("voice_record_id");
    const list = form()?.querySelector("[data-voice-list]");
    if (select) {
      const selected = select.value;
      const ready = voices.filter((voice) => voice.status === "ready" && voice.provider_voice_id);
      select.innerHTML = `<option value="">Suno вокал</option>${ready.map((voice) => `<option value="${voice.id}">${String(voice.name || `Voice #${voice.id}`)}</option>`).join("")}`;
      if (ready.some((voice) => String(voice.id) === selected)) select.value = selected;
    }
    if (list) {
      list.innerHTML = voices.length ? voices.map((voice) => {
        const status = String(voice.status || "");
        const action = status === "awaiting_verification" ? "verify" : (status === "ready" ? "" : "refresh");
        return `<div class="generation-live-status" style="margin-top:8px"><b>${String(voice.name || `Voice #${voice.id}`)}</b><span>${status}</span>${voice.validate_phrase ? `<code>${voice.validate_phrase}</code>` : ""}${voice.error ? `<small>${voice.error}</small>` : ""}${action ? `<button class="button ghost" type="button" data-voice-action="${action}" data-voice-id="${voice.id}">${action === "verify" ? "Загрузить проверку" : "Обновить статус"}</button>` : ""}</div>`;
      }).join("") : `<small>Своих голосов пока нет.</small>`;
    }
    if (typeof refreshCustomSelects === "function") refreshCustomSelects(form() || document);
  }

  async function loadVoices(showErrors = false) {
    if (voicesLoading || typeof request !== "function") return;
    voicesLoading = true;
    try {
      const payload = await request("/music/voices");
      voices = Array.isArray(payload) ? payload : [];
      renderVoices();
    } catch (error) {
      if (showErrors && typeof toast === "function") toast(`Не удалось загрузить голоса: ${error.message}`, "danger");
    } finally {
      voicesLoading = false;
    }
  }

  async function createVoice() {
    const source = field("voice_source_file")?.files?.[0];
    const name = value("voice_name");
    if (!name || !source) {
      if (typeof toast === "function") toast("Укажите название голоса и загрузите аудио", "info");
      return;
    }
    const payload = new FormData();
    payload.append("file", source);
    payload.append("name", name);
    payload.append("style", value("voice_style"));
    payload.append("description", value("voice_description"));
    try {
      const created = await request("/music/voices", { method: "POST", body: payload });
      voices = [created, ...voices.filter((voice) => voice.id !== created.id)];
      renderVoices();
      if (typeof toast === "function") toast("Голос отправлен на подготовку", "success");
    } catch (error) {
      if (typeof toast === "function") toast(`Не удалось создать голос: ${error.message}`, "danger");
    }
  }

  async function refreshVoice(voiceId) {
    try {
      const updated = await request(`/music/voices/${voiceId}/refresh`, { method: "POST", body: JSON.stringify({}) });
      voices = voices.map((voice) => voice.id === updated.id ? updated : voice);
      renderVoices();
    } catch (error) {
      if (typeof toast === "function") toast(`Не удалось обновить голос: ${error.message}`, "danger");
    }
  }

  async function verifyVoice(voiceId, audioFile) {
    if (!audioFile) return;
    const payload = new FormData();
    payload.append("file", audioFile);
    try {
      const updated = await request(`/music/voices/${voiceId}/verify`, { method: "POST", body: payload });
      voices = voices.map((voice) => voice.id === updated.id ? updated : voice);
      renderVoices();
      if (typeof toast === "function") toast("Проверочная запись отправлена", "success");
    } catch (error) {
      if (typeof toast === "function") toast(`Не удалось проверить голос: ${error.message}`, "danger");
    }
  }

  window.addEventListener("DOMContentLoaded", () => {
    ensureParityControls();
    syncParityControls(current());
    form()?.querySelector("[name='model']")?.addEventListener("change", () => setTimeout(() => syncParityControls(current()), 0));
  });
})();
