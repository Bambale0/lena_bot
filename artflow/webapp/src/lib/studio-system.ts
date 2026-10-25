/** Form validation only. Mounted admin routes remain the authority. */
export function positiveSafeInteger(value: string): number | null {
  if (!/^[0-9]+$/.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}
export function decimalMinorUnits(value: string): number | null {
  const match = /^([0-9]+)(?:\.([0-9]{1,2}))?$/.exec(value.trim());
  if (!match) return null;
  const cents = BigInt(match[1]) * 100n + BigInt((match[2] ?? "").padEnd(2, "0"));
  return cents > 0n && cents <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(cents) : null;
}
export function minorUnitsDecimal(value: number): string {
  return Number.isSafeInteger(value) && value > 0 ? `${Math.floor(value / 100)}.${String(value % 100).padStart(2, "0")}` : "";
}
export function recoverySeconds(value: string): number | null {
  const seconds = positiveSafeInteger(value);
  return seconds !== null && seconds >= 600 && seconds <= 86400 ? seconds : null;
}
export function humanDeadline(seconds: number): string {
  const hours = Math.floor(seconds / 3600), minutes = Math.floor(seconds % 3600 / 60), rest = seconds % 60;
  return [hours && `${hours} ч`, minutes && `${minutes} мин`, rest && `${rest} с`].filter(Boolean).join(" ");
}
export function validNativeWanId(value: string, variant: "standard" | "prime"): boolean {
  return /^[A-Za-z0-9_./-]{1,80}$/.test(value) && /^wan-3(?:[._/-][A-Za-z0-9_./-]+)?$/.test(value) && value.includes("prime") === (variant === "prime");
}
export function validTributeUrl(value: string): boolean {
  return /^https:\/\/web\.tribute\.tg\/p\/[A-Za-z0-9]+$/.test(value) && value.length <= 2048;
}
export function validReviewNote(value: string): boolean {
  const length = Array.from(value.trim()).length;
  return length >= 12 && length <= 500;
}
