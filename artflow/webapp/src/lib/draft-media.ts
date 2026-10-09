import { selectGenerationInputs } from "./reference-selection.ts";
import type { GenerationDraft, ModelInfo } from "./types";

export interface MediaConflict { code: string; message: string }
export interface DraftMediaInspection {
  maxReferences: number | null;
  referenceInputsSupported: boolean;
  videoInputSupported: boolean;
  issues: MediaConflict[];
}

function capacity(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}
function keepOrFirst<T>(current: T, allowed?: T[]): T {
  return allowed?.length && !allowed.includes(current) ? allowed[0] : current;
}

/** Change only supported ordinary settings; canonical input media are never trimmed. */
export function switchDraftModel(draft: GenerationDraft, model: ModelInfo): GenerationDraft {
  if (draft.promptId !== null) return draft;
  return {
    ...draft,
    model: model.key,
    mode: keepOrFirst(draft.mode, model.modes),
    aspectRatio: keepOrFirst(draft.aspectRatio, model.aspect_ratios),
    quality: keepOrFirst(draft.quality, model.quality_options?.map(option => option.value)),
    count: keepOrFirst(draft.count, model.counts),
    duration: model.duration_from_source ? draft.duration : keepOrFirst(draft.duration, model.duration_options?.length ? model.duration_options : model.durations),
    resolution: keepOrFirst(draft.resolution, model.resolution_options?.length ? model.resolution_options : model.resolutions),
    grokMode: keepOrFirst(draft.grokMode, model.mode_options),
    seed: model.has_seed ? draft.seed : null,
    referenceUrls: [...draft.referenceUrls],
    audioIds: [...draft.audioIds],
    characterIds: [...draft.characterIds],
  };
}

/** Shared by the form and command boundary. Does not change the draft or payload. */
export function inspectDraftMedia(source: GenerationDraft, model: ModelInfo | undefined): DraftMediaInspection {
  const draft = selectGenerationInputs(source);
  const issues: MediaConflict[] = [];
  if (!model) return { maxReferences: null, referenceInputsSupported: false, videoInputSupported: false,
    issues: [{ code: "model_unavailable", message: "Модель недоступна. Выберите доступную модель; материалы сохранены." }] };
  const modes = Array.isArray(model.modes) ? model.modes : [];
  if (!modes.includes(draft.mode)) issues.push({ code: "mode_unsupported", message: "Этот режим недоступен у выбранной модели." });
  const supportsPhotos = modes.includes("image") || modes.includes("motion") || modes.includes("multimodal") || model.requires_reference_images === true;
  const videoInputSupported = model.supports_video_input === true || model.requires_video_input === true || modes.includes("video") || modes.includes("motion");
  let maxReferences = capacity(model.max_refs);
  if (!supportsPhotos) maxReferences = 0;
  if (draft.videoUrl && model.max_refs_with_video != null) {
    const combined = capacity(model.max_refs_with_video);
    maxReferences = combined === null || maxReferences === null ? null : Math.min(maxReferences, combined);
  }
  if (source.referenceMaterials !== undefined && draft.referenceUrls.length === 0 && (
    draft.kind === "motion" || model.requires_reference_images === true || (!modes.includes("text") && supportsPhotos)
    || (draft.kind === "video" && draft.mode === "image" && model.auto_route_by_inputs !== true && !modes.includes("multimodal"))
  )) issues.push({ code: "reference_required", message: "Для этого режима нужно включить хотя бы одно фото в запуск." });
  if (draft.referenceUrls.length) {
    // The ordinary video normalizer consumes image references only in image mode.
    // Input-routed/multimodal adapters explicitly advertise their different contract.
    const acceptsPhotosInMode = draft.kind === "image" || draft.kind === "motion" || draft.mode === "image"
      || model.auto_route_by_inputs === true || modes.includes("multimodal") || model.requires_reference_images === true;
    if (supportsPhotos && !acceptsPhotosInMode) issues.push({ code: "reference_mode_unsupported", message: "Этот видеорежим не использует фото. Материалы сохранены: выберите режим «Фото» или совместимую модель." });
    if (maxReferences === null) issues.push({ code: "reference_capacity_unknown", message: "Лимит фото неизвестен. Выберите другую модель или обновите каталог." });
    else if (draft.referenceUrls.length > maxReferences) issues.push({ code: "reference_limit", message: maxReferences === 0
      ? "Выбранная модель или сочетание входов не поддерживает эти фото. Смените модель или исключите фото из запуска."
      : `Сохранено фото: ${draft.referenceUrls.length}; можно использовать: ${maxReferences}. Смените модель или исключите лишние фото из запуска.` });
  }
  if (draft.videoUrl && !videoInputSupported) issues.push({ code: "video_unsupported", message: "Модель не принимает исходное видео. Оно сохранено: вернитесь к совместимой модели или явно уберите видео." });
  for (const [values, rawLimit, code, label] of [
    [draft.audioIds, model.max_audio_ids, "audio_ids_limit", "Audio ID"],
    [draft.characterIds, model.max_character_ids, "character_ids_limit", "Character ID"],
  ] as const) {
    const limit = capacity(rawLimit);
    if (values.length && (limit === null || values.length > limit)) issues.push({ code, message: `${label}: сохранено ${values.length}, доступно ${limit === null ? "неизвестно" : limit}. Измените модель или список идентификаторов.` });
  }
  return { maxReferences, referenceInputsSupported: supportsPhotos && maxReferences !== null && maxReferences > 0, videoInputSupported, issues };
}
