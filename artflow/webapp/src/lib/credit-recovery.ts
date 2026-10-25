/** Recognize only the application's explicit pre-spend shortage responses. */
export function isInsufficientCreditError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const value = error as { status?: unknown; message?: unknown };
  if (value.status !== 402 || typeof value.message !== "string") return false;
  return /^Insufficient credits: need \d+(?:\.\d+)?(?:, have \d+(?:\.\d+)?)?$/.test(value.message)
    || /^Недостаточно кредитов\. Нужно \d+(?:\.\d+)? 💋$/.test(value.message);
}
