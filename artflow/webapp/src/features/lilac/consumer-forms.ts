import type { ModelInfo } from "@/lib/types";

/** Media is rendered by the browser, never fetched by a new server proxy. */
export function consumerMediaUrl(value: string): string {
  if (!value.trim() || value.length > 2048) return "";
  const raw = value.trim();
  if ((!/^https?:\/\//i.test(raw) && !/^\/(?!\/)/.test(raw)) || /[\\\u0000-\u001f\u007f]/.test(raw)) return "";
  try {
    const origin = globalThis.location?.origin;
    const url = new URL(raw, origin);
    return !url.username && !url.password && (url.protocol === "https:" || (url.protocol === "http:" && url.origin === origin)) ? url.href : "";
  } catch { return ""; }
}

export function publicationTags(value: string): string[] {
  return [...new Set(value.split(",").map(tag => tag.trim()).filter(Boolean))];
}

export function uploadedImage(result: { url: string; kind?: string; content_type?: string }): string {
  const url = consumerMediaUrl(result.url);
  if (!url || (result.kind !== "image" && !result.content_type?.startsWith("image/")) || (result.kind && result.kind !== "image") || (result.content_type && !result.content_type.startsWith("image/"))) {
    throw new Error("Сервер не вернул безопасное изображение. Выберите другой файл или уберите его.");
  }
  return url;
}

export interface SeriesSettings { model: string; mode: string; aspect_ratio: string | null; quality: string; count: number; }
export function seriesOptions(model: ModelInfo) {
  return {
    modes: model.modes || [], ratios: model.aspect_ratios || [],
    qualities: model.quality_options?.length ? model.quality_options : [{ value: "basic", label: "По умолчанию" }],
    counts: model.counts?.length ? model.counts.filter(count => Number.isSafeInteger(count) && count >= 1 && count <= 6) : [1],
    maxRefs: model.modes?.includes("image") && Number.isSafeInteger(model.max_refs) && model.max_refs! > 0 ? model.max_refs! : 0,
  };
}
export function initialSeriesSettings(model: ModelInfo): SeriesSettings {
  const options = seriesOptions(model);
  return { model: model.key, mode: options.modes[0] || "", aspect_ratio: options.ratios[0] || null, quality: options.qualities[0]?.value || "basic", count: options.counts[0] || 1 };
}
export function seriesValidation(settings: SeriesSettings, model: ModelInfo | undefined, references: string[]): string {
  if (!model || model.key !== settings.model) return "Модель недоступна. Обновите каталог или выберите другую.";
  const options = seriesOptions(model);
  if (!options.modes.includes(settings.mode) || !options.qualities.some(option => option.value === settings.quality) || !options.counts.includes(settings.count)) return "Выберите доступные режим, качество и количество из каталога.";
  const ratioSupported = (model.aspect_ratio_modes || options.modes).includes(settings.mode) && references.length >= (model.aspect_ratio_min_refs || 0);
  if (settings.aspect_ratio && (!ratioSupported || !options.ratios.includes(settings.aspect_ratio))) return "Формат недоступен для этого режима или количества исходных фото. Выберите автоматический формат.";
  if (references.length > options.maxRefs) return `Можно использовать исходных фото: ${options.maxRefs}. Уберите лишние фото или смените модель.`;
  if (references.some(url => !consumerMediaUrl(url))) return "Исходное фото имеет небезопасный адрес. Уберите его и загрузите снова.";
  return "";
}
