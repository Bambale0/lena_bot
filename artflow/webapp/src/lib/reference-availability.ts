export type ReferenceAvailability = "available" | "missing" | "unknown" | "forbidden" | "temporary_error";
export type ReferenceChecker = (url: string, signal: AbortSignal) => Promise<ReferenceAvailability>;
export const REFERENCE_CHECK_TIMEOUT_MS = 15_000;
const states: ReferenceAvailability[] = ["available", "missing", "unknown", "forbidden", "temporary_error"];

export function parseReferenceAvailability(raw: unknown): ReferenceAvailability {
  const value = raw && typeof raw === "object" ? (raw as { status?: unknown }).status : undefined;
  return typeof value === "string" && states.includes(value as ReferenceAvailability) ? value as ReferenceAvailability : "temporary_error";
}
export function referenceAvailabilityMessage(state: ReferenceAvailability | "checking", en = false): string {
  const messages: Record<ReferenceAvailability | "checking", [string, string]> = {
    checking: ["Проверяем файл…", "Checking the file…"],
    available: ["Файл найден в хранилище", "File found in storage"],
    missing: ["Файл больше недоступен. Выберите фото снова.", "This file is no longer available. Choose the photo again."],
    unknown: ["Эту ссылку нельзя подтвердить. Загрузите фото с устройства.", "This link cannot be verified. Upload the photo from your device."],
    forbidden: ["Ссылка не подходит для безопасной проверки. Загрузите фото снова.", "This link cannot be safely checked. Upload the photo again."],
    temporary_error: ["Не удалось проверить файл. Повторите проверку.", "Could not check the file. Try again."],
  };
  return messages[state][en ? 1 : 0];
}
