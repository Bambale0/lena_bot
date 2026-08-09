// Shared capability helpers for generation surfaces.
// Keep this module free of React so Mini App, Web and tests can consume the same contract.

export const VIDEO_SCENARIOS = Object.freeze({
  FAST: "fast",
  QUALITY: "quality",
  IMAGE_TO_VIDEO: "i2v",
  MOTION: "motion",
  ADVANCED: "advanced",
  ALL: "all",
});

export function modelModes(model) {
  return Array.isArray(model?.modes) && model.modes.length ? model.modes : ["text"];
}

export function supportsMode(model, mode) {
  return modelModes(model).includes(mode);
}

export function supportsMiniappVideoModel(model) {
  const modes = modelModes(model);
  return modes.some((mode) => ["text", "image", "video", "motion"].includes(mode));
}

export function isAdvancedVideoModel(model) {
  const modes = modelModes(model);
  return Boolean(
    modes.includes("video") ||
    modes.includes("motion") ||
    Number(model?.max_audio_ids || 0) > 0 ||
    Number(model?.max_character_ids || 0) > 0 ||
    model?.has_seed ||
    model?.supports_video_input
  );
}

export function videoScenario(model) {
  const key = String(model?.key || "").toLowerCase();
  const modes = modelModes(model);

  if (modes.includes("motion")) return VIDEO_SCENARIOS.MOTION;
  if (isAdvancedVideoModel(model)) return VIDEO_SCENARIOS.ADVANCED;
  if (key.includes("midjourney-video") || modes.includes("image")) return VIDEO_SCENARIOS.IMAGE_TO_VIDEO;
  if (key.includes("fast") || key.includes("turbo")) return VIDEO_SCENARIOS.FAST;
  return VIDEO_SCENARIOS.QUALITY;
}

export function videoModeLabel(mode) {
  return {
    text: "Текст → видео",
    image: "Фото → видео",
    video: "Видео → видео",
    motion: "Motion Control",
  }[mode] || mode;
}

export function capabilityFlags(model, mode) {
  const modes = modelModes(model);
  const selectedMode = modes.includes(mode) ? mode : modes[0];
  return {
    mode: selectedMode,
    canUseImages: modes.includes("image"),
    canUseVideo: Boolean(model?.supports_video_input || modes.includes("video")),
    canUseMotion: modes.includes("motion"),
    maxImageRefs: Math.max(0, Number(model?.max_refs || 0)),
    maxAudioIds: Math.max(0, Number(model?.max_audio_ids || 0)),
    maxCharacterIds: Math.max(0, Number(model?.max_character_ids || 0)),
    hasSeed: Boolean(model?.has_seed),
  };
}

export function normalizeIdList(value, maxItems) {
  const raw = Array.isArray(value)
    ? value
    : String(value || "").split(/[\n,]+/g);
  const unique = [];
  const seen = new Set();
  for (const item of raw) {
    const normalized = String(item || "").trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    unique.push(normalized);
    if (maxItems > 0 && unique.length >= maxItems) break;
  }
  return unique;
}

export function buildAdvancedVideoPayload({
  model,
  mode,
  prompt,
  promptId = null,
  duration,
  aspectRatio,
  resolution,
  grokMode,
  imageUrls = [],
  videoUrl = null,
  videoStart = 0,
  videoEnd = null,
  audioIds = [],
  characterIds = [],
  seed = null,
}) {
  const flags = capabilityFlags(model, mode);
  const refs = flags.mode === "image" ? imageUrls.filter(Boolean).slice(0, flags.maxImageRefs || 1) : [];
  const normalizedAudioIds = normalizeIdList(audioIds, flags.maxAudioIds);
  const normalizedCharacterIds = normalizeIdList(characterIds, flags.maxCharacterIds);

  return {
    model: model?.key || "",
    prompt,
    prompt_id: promptId,
    mode: flags.mode,
    duration,
    aspect_ratio: aspectRatio,
    resolution,
    grok_mode: grokMode || undefined,
    image_url: refs[0] || null,
    reference_url: refs[0] || null,
    reference_urls: refs.slice(1),
    video_url: flags.canUseVideo && flags.mode === "video" ? videoUrl || null : null,
    video_start: flags.canUseVideo && flags.mode === "video" ? Number(videoStart || 0) : 0,
    video_end: flags.canUseVideo && flags.mode === "video" && videoEnd !== "" && videoEnd != null ? Number(videoEnd) : null,
    audio_ids: normalizedAudioIds,
    character_ids: normalizedCharacterIds,
    seed: flags.hasSeed && seed !== "" && seed != null ? Number(seed) : null,
  };
}

export function validateAdvancedVideoInput({ model, mode, imageUrls = [], videoUrl = null, videoStart = 0, videoEnd = null, audioIds = [], characterIds = [] }) {
  const flags = capabilityFlags(model, mode);
  const errors = [];

  if (flags.mode === "image" && !imageUrls.filter(Boolean).length) errors.push("Добавь фото-референс.");
  if (flags.mode === "video" && !videoUrl) errors.push("Добавь исходное видео.");
  if (flags.mode === "video" && videoEnd != null && videoEnd !== "") {
    const start = Number(videoStart || 0);
    const end = Number(videoEnd);
    if (!Number.isFinite(end) || end <= start) errors.push("Конец фрагмента должен быть позже начала.");
    if (Number.isFinite(end) && end - start > 10) errors.push("Фрагмент видео должен быть не длиннее 10 секунд.");
  }
  if (normalizeIdList(audioIds, 0).length > flags.maxAudioIds) errors.push(`Можно указать не больше ${flags.maxAudioIds} Audio ID.`);
  if (normalizeIdList(characterIds, 0).length > flags.maxCharacterIds) errors.push(`Можно указать не больше ${flags.maxCharacterIds} Character ID.`);

  return errors;
}
