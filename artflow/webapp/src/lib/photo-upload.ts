import type { GenerationDraft, PhotoUploadError, PhotoUploadState, ReferenceMaterial } from "./types";
import { referenceMaterials } from "./reference-selection.ts";

export interface PhotoPolicy { image_max_bytes: number; image_formats: string[] }
export interface UploadedPhoto { url: string; kind?: string; content_type?: string; size?: number }
export type PhotoUploadEvent =
  | { type: "start"; id: string; operationId: string }
  | { type: "failure"; id: string; operationId: string; error: PhotoUploadError }
  | { type: "success"; id: string; operationId: string; result: UploadedPhoto };
export class PhotoUploadFailure extends Error {
  readonly code: PhotoUploadError;
  constructor(code: PhotoUploadError) { super(code); this.code = code; }
}
export function parsePhotoPolicy(raw: unknown): PhotoPolicy {
  const p = raw as Partial<PhotoPolicy> | null;
  if (!p || !Number.isSafeInteger(p.image_max_bytes) || Number(p.image_max_bytes) <= 0 || !Array.isArray(p.image_formats)
    || !p.image_formats.length || p.image_formats.some(value => typeof value !== "string")) throw new PhotoUploadFailure("policy_unavailable");
  return { image_max_bytes: p.image_max_bytes!, image_formats: [...p.image_formats] };
}

/** Only public http(s) shapes (or same-origin absolute paths) may be previewed. No auth is added. */
export function safePhotoUrl(raw: unknown): raw is string {
  if (typeof raw !== "string" || !raw || raw.trim() !== raw || raw.includes("\\")) return false;
  if (raw.startsWith("/") && !raw.startsWith("//")) return true;
  try {
    const u = new URL(raw); const h = u.hostname.toLowerCase().replace(/^\[|\]$/g, "");
    if (!["http:", "https:"].includes(u.protocol) || !h || u.username || u.password) return false;
    if (h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal")) return false;
    if (h.includes(":")) return false; // no unverified IPv6 literal previews
    if (/^\d+\.\d+\.\d+\.\d+$/.test(h)) {
      const [a, b] = h.split(".").map(Number);
      if (a === 0 || a === 10 || a === 127 || a >= 224 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
        || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127)) return false;
    }
    return h.includes(".");
  } catch { return false; }
}

/** Signatures are file-format facts, not a provider/model allowlist. The server also validates. */
export async function validatePhotoFile(file: File, policy: PhotoPolicy): Promise<string> {
  if (!file.size) throw new PhotoUploadFailure("empty_file");
  if (file.size > policy.image_max_bytes) throw new PhotoUploadFailure("too_large");
  const b = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  let format = "";
  if (b[0] === 255 && b[1] === 216 && b[2] === 255) format = "jpeg";
  else if ([137, 80, 78, 71, 13, 10, 26, 10].every((v, i) => b[i] === v)) format = "png";
  else if (String.fromCharCode(...b.slice(0, 4)) === "RIFF" && String.fromCharCode(...b.slice(8, 12)) === "WEBP") format = "webp";
  if (!format || !policy.image_formats.includes(format)) throw new PhotoUploadFailure("invalid_file");
  return `image/${format}`;
}
export function validateUploadedPhoto(result: UploadedPhoto, file: File, contentType: string, policy: PhotoPolicy): UploadedPhoto {
  if (!safePhotoUrl(result.url) || (result.kind !== undefined && result.kind !== "image")
    || (result.content_type !== undefined && !["image/jpeg", "image/png", "image/webp"].includes(result.content_type))
    || (result.size !== undefined && (!Number.isSafeInteger(result.size) || result.size <= 0 || result.size > policy.image_max_bytes))) throw new PhotoUploadFailure("invalid_response");
  return { url: result.url, kind: "image", size: result.size ?? file.size, content_type: result.content_type || contentType };
}
export function queuePhoto(draft: GenerationDraft, id: string, upload: PhotoUploadState, replace = false): GenerationDraft {
  if (draft.promptId !== null) return draft;
  const items = referenceMaterials(draft);
  if (replace) {
    const found = items.find(item => item.id === id);
    if (!found) return draft;
    found.upload = { ...upload };
  } else {
    if (items.some(item => item.id === id)) return draft;
    items.push({ id, url: "", included: true, upload: { ...upload } });
  }
  return { ...draft, referenceUrls: [], referenceMaterials: items };
}
export function applyPhotoUploadEvent(draft: GenerationDraft, event: PhotoUploadEvent): GenerationDraft {
  if (draft.promptId !== null) return draft;
  const items = referenceMaterials(draft);
  const index = items.findIndex(item => item.id === event.id && item.upload?.operationId === event.operationId);
  if (index < 0) return draft;
  const item = items[index]; const upload = item.upload!;
  if (event.type === "success") {
    const { upload: _previous, ...original } = item;
    items[index] = { ...original, url: event.result.url, name: upload.name, size: event.result.size ?? upload.size,
      contentType: event.result.content_type || upload.contentType };
  } else items[index] = { ...item, upload: { ...upload, status: event.type === "start" ? "uploading" : "error",
    ...(event.type === "failure" ? { error: event.error } : { error: undefined }) } };
  return { ...draft, referenceUrls: [], referenceMaterials: items };
}
export function cancelPhotoReplacement(draft: GenerationDraft, id: string): GenerationDraft {
  if (draft.promptId !== null) return draft;
  return { ...draft, referenceUrls: [], referenceMaterials: referenceMaterials(draft).flatMap(item => {
    if (item.id !== id) return [item];
    if (!item.url) return [];
    const { upload: _pending, ...original } = item;
    return [original];
  }) };
}
export function photoUploading(draft: GenerationDraft): boolean {
  return draft.promptId === null && referenceMaterials(draft).some(item => item.upload && item.upload.status !== "error");
}
export function readyPhoto(item: ReferenceMaterial): boolean { return Boolean(item.url) && !item.upload; }
export function photoUploadMessage(error: PhotoUploadError | undefined, en = false): string {
  const messages: Record<PhotoUploadError, [string, string]> = {
    network: ["Не удалось загрузить фото. Повторите загрузку этого файла.", "Upload failed. Retry this photo."],
    timeout: ["Загрузка не завершилась вовремя. Повторите этот файл.", "Upload timed out. Retry this file."],
    empty_file: ["Файл пустой. Выберите другое фото.", "This file is empty. Choose another photo."],
    too_large: ["Фото превышает допустимый размер. Выберите файл поменьше.", "This photo exceeds the upload limit. Choose a smaller file."],
    invalid_file: ["Нужен файл JPEG, PNG или WebP.", "Choose a JPEG, PNG or WebP file."],
    invalid_response: ["Сервис не подтвердил загрузку фото. Повторите этот файл.", "The service did not confirm this photo. Retry the file."],
    policy_unavailable: ["Не удалось проверить ограничения загрузки. Повторите проверку.", "Upload limits could not be checked. Retry."],
    source_required: ["Загрузка прервалась. Выберите этот файл снова.", "Upload was interrupted. Select this file again."],
    rejected: ["Сервис отклонил файл. Выберите другое фото или повторите позже.", "The service rejected this file. Choose another photo or retry later."],
  };
  return messages[error || "network"][en ? 1 : 0];
}
