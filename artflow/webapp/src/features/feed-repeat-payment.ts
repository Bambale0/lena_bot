export type PaymentProvider = "tbank" | "crypto" | "tribute" | "lava";
export type CheckoutPaymentOption = {
  provider: PaymentProvider;
  amount: number | null;
  currency: "RUB" | "USDT" | "USD";
};
export type FeedCheckoutPlan = {
  key: string;
  label: string;
  credits: number;
  price_rub: number;
  payment_options?: CheckoutPaymentOption[];
};

/** Missing or mismatched metadata must never fall back to a global provider. */
export function checkoutOptions(plan: { payment_options?: unknown } | null | undefined): CheckoutPaymentOption[] {
  if (!Array.isArray(plan?.payment_options)) return [];
  const currencies = { tbank: "RUB", crypto: "USDT", tribute: "USD", lava: "RUB" };
  return plan.payment_options.filter((value): value is CheckoutPaymentOption => {
    if (!value || typeof value !== "object") return false;
    const option = value as CheckoutPaymentOption;
    if (typeof option.provider !== "string" || !Object.prototype.hasOwnProperty.call(currencies, option.provider)
      || currencies[option.provider] !== option.currency) return false;
    return (option.provider === "lava" && option.amount === null)
      || (typeof option.amount === "number" && Number.isFinite(option.amount) && option.amount > 0);
  });
}

export function checkoutAmountLabel(option: CheckoutPaymentOption): string {
  const currency = option.currency === "RUB" ? "₽" : option.currency;
  return option.amount === null ? `сумма в ${currency} на странице оплаты` : `${option.amount} ${currency}`;
}

export function checkoutProviderLabel(provider: PaymentProvider): string {
  return { tbank: "Карта | СБП", crypto: "CryptoBot", tribute: "Tribute", lava: "Lava" }[provider];
}

export type RepeatPayment = {
  startedAt: number;
  provider: PaymentProvider | null;
  planKey: string | null;
  transactionId: number | null;
  checkoutUrl: string | null;
};
export type RepeatDraft = {
  savedAt: number;
  references: string[];
  changeRequest: string;
  modelKey: string;
  mode: string;
  aspectRatio: string;
  quality: string;
  count: number;
  duration: number;
  resolution: string;
  grokMode: string;
  payment: RepeatPayment | null;
};
type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export const repeatDraftKey = (actorId: number, sourceId: number) => `apix:feed-repeat-draft:v2:${actorId}:${sourceId}`;
const REPEAT_DRAFT_TTL_MS = 60 * 60 * 1000;
const PROVIDERS: PaymentProvider[] = ["tbank", "crypto", "tribute", "lava"];
const validId = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0;

function checkoutUrl(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}

function cleanDraft(value: unknown): RepeatDraft | null {
  if (!value || typeof value !== "object") return null;
  const saved = value as Record<string, unknown>;
  if (typeof saved.savedAt !== "number" || !Number.isFinite(saved.savedAt)) return null;
  const raw = saved.payment && typeof saved.payment === "object"
    ? saved.payment as Record<string, unknown> : null;
  // Old booleans and incomplete invoice responses must fail closed, never expire into a new invoice.
  const payment: RepeatPayment | null = raw || saved.paymentWaiting === true ? {
    startedAt: typeof raw?.startedAt === "number" && Number.isFinite(raw.startedAt) ? raw.startedAt : saved.savedAt,
    provider: PROVIDERS.includes(raw?.provider as PaymentProvider) ? raw!.provider as PaymentProvider : null,
    planKey: typeof raw?.planKey === "string" ? raw.planKey : null,
    transactionId: validId(raw?.transactionId) ? raw.transactionId : null,
    checkoutUrl: checkoutUrl(raw?.checkoutUrl),
  } : null;
  return {
    savedAt: saved.savedAt,
    references: Array.isArray(saved.references)
      ? saved.references.filter((value): value is string => typeof value === "string" && value.startsWith("https://")) : [],
    changeRequest: typeof saved.changeRequest === "string" ? saved.changeRequest.slice(0, 800) : "",
    modelKey: String(saved.modelKey || ""), mode: String(saved.mode || "image"),
    aspectRatio: String(saved.aspectRatio || "1:1"), quality: String(saved.quality || "basic"),
    count: Number(saved.count) || 1, duration: Number(saved.duration) || 5,
    resolution: String(saved.resolution || "720p"), grokMode: String(saved.grokMode || "normal"), payment,
  };
}

export function readRepeatDraft(
  storage: DraftStorage | null, actorId: number, sourceId: number,
  now = Date.now(), legacyTelegramId?: number,
): RepeatDraft | null {
  if (!storage || !validId(actorId) || !validId(sourceId)) return null;
  try {
    const key = repeatDraftKey(actorId, sourceId);
    let saved = cleanDraft(JSON.parse(storage.getItem(key) || "null"));
    if (!saved && validId(legacyTelegramId)) {
      const legacyKey = `apix:feed-repeat-draft:${legacyTelegramId}:${sourceId}`;
      saved = cleanDraft(JSON.parse(storage.getItem(legacyKey) || "null"));
      if (saved && saveRepeatDraft(storage, actorId, sourceId, saved)) storage.removeItem(legacyKey);
    }
    if (!saved) {
      const legacy = cleanDraft(JSON.parse(storage.getItem(`apix:feed-repeat-draft:session:${sourceId}`) || "null"));
      // Unknown actor: preserve only the safety guard, never someone else's photo or edits.
      if (legacy?.payment) saved = cleanDraft({ savedAt: legacy.savedAt, paymentWaiting: true });
    }
    if (!saved || (!saved.payment && (now < saved.savedAt || now - saved.savedAt > REPEAT_DRAFT_TTL_MS))) return null;
    return saved;
  } catch {
    return null;
  }
}

/** A true result proves the recovery snapshot was synchronously stored before a payment side effect. */
export function saveRepeatDraft(storage: DraftStorage | null, actorId: number, sourceId: number, draft: RepeatDraft): boolean {
  if (!storage || !validId(actorId) || !validId(sourceId)) return false;
  const clean = cleanDraft(draft);
  if (!clean) return false;
  try {
    const key = repeatDraftKey(actorId, sourceId);
    const serialized = JSON.stringify(clean);
    storage.setItem(key, serialized);
    return storage.getItem(key) === serialized;
  } catch {
    return false;
  }
}

export function clearRepeatDraft(storage: DraftStorage | null, actorId: number, sourceId: number): void {
  if (readRepeatDraft(storage, actorId, sourceId)?.payment) return;
  try { storage?.removeItem(repeatDraftKey(actorId, sourceId)); } catch { /* Optional storage. */ }
}

export function paymentFromResponse(payment: RepeatPayment, response: Record<string, unknown>): RepeatPayment {
  return {
    ...payment,
    transactionId: validId(response.transaction_id) ? response.transaction_id : null,
    checkoutUrl: checkoutUrl(response.pay_url || response.invoice_link || response.invoice_url || response.url),
  };
}

export function paymentResolution(payment: RepeatPayment, transactions: unknown): "pending" | "paid" | "failed" | "refunded" {
  if (!payment.transactionId || !payment.provider || !Array.isArray(transactions)) return "pending";
  const provider = payment.provider === "crypto" ? "cryptobot" : payment.provider;
  const matching = transactions.find((value: unknown) => {
    if (!value || typeof value !== "object") return false;
    const tx = value as Record<string, unknown>;
    return tx.id === payment.transactionId && tx.provider === provider;
  });
  return matching && ["paid", "failed", "refunded"].includes(matching.status) ? matching.status : "pending";
}

export function canReopenPayment(payment: RepeatPayment): boolean {
  // Tribute returns a fixed product page, so reopening it can start another purchase.
  return Boolean(payment.checkoutUrl && payment.provider && ["tbank", "crypto", "lava"].includes(payment.provider));
}
