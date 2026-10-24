import type { PaymentPlan } from "./types";

export type CheckoutProvider = "tbank" | "crypto" | "tribute" | "lava";
const positive = (value: unknown): boolean => typeof value === "number" && Number.isFinite(value) && value > 0;

export function supportsPlan(provider: CheckoutProvider, plan: PaymentPlan, lavaPlanKeys: readonly string[] = []): boolean {
  if (provider === "tribute") return positive(plan.price_tribute_usd);
  if (provider === "crypto") return positive(plan.price_usdt);
  return positive(plan.price_rub) && (provider !== "lava" || lavaPlanKeys.includes(plan.key));
}

export function checkoutPrice(provider: CheckoutProvider, plan: PaymentPlan): string {
  if (provider === "tribute") return positive(plan.price_tribute_usd) ? `$${plan.price_tribute_usd}` : "";
  if (provider === "crypto") return positive(plan.price_usdt) ? `${plan.price_usdt} USDT` : "";
  return positive(plan.price_rub) ? `${plan.price_rub} ₽` : "";
}
