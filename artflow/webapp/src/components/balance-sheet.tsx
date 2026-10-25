import { useEffect, useMemo, useState } from "react";
import { Banknote, Bitcoin, CheckCircle2, CreditCard, Info, Send, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { t } from "@/lib/i18n";
import type { PaymentPlan, UserProfile } from "@/lib/types";
import { formatCredits, formatKisses } from "@/lib/utils";
import { supportsPlan, checkoutPrice } from "@/lib/billing-methods";

type PaymentProvider = "tbank" | "crypto" | "tribute" | "lava";

interface PaymentMethod {
  id: PaymentProvider;
  title: string;
  subtitle: string;
  icon: typeof CreditCard;
  badge?: string;
}

const methods: PaymentMethod[] = [
  { id: "tbank", title: "Карта | СБП", subtitle: "Оплата в рублях", icon: Banknote },
  { id: "crypto", title: "CryptoBot", subtitle: "USDT и крипто-оплата", icon: Bitcoin },
  { id: "tribute", title: "USD", subtitle: "Оплата в долларах", icon: CreditCard },
  { id: "lava", title: "СБП / Lava", subtitle: "Российская оплата по ссылке", icon: Send },
];

interface BalanceSheetProps {
  open: boolean;
  user: UserProfile;
  plans: PaymentPlan[];
  availableProviders: string[];
  lavaPlanKeys?: string[];
  busy?: boolean;
  error?: string;
  onOpenChange: (open: boolean) => void;
  onPay: (provider: PaymentProvider, plan: PaymentPlan) => void;
  pending?: boolean;
  checking?: boolean;
  onCheck?: () => void;
  onReopen?: () => void;
  onAcknowledge?: () => void;
}

function planPrice(plan: PaymentPlan, method: PaymentProvider): string {
  return checkoutPrice(method, plan);
}

function compactPrice(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "");
}

function planListPrice(plan: PaymentPlan): string {
  const rubValue = Number(plan.price_rub || 0);
  const usdValue = Number(plan.price_tribute_usd || 0);
  const rub = rubValue > 0 ? `${compactPrice(rubValue)}₽` : "";
  const usd = usdValue > 0 ? `$${compactPrice(usdValue)}` : "";
  return [rub, usd].filter(Boolean).join(" | ");
}

function BalanceSheet({ open, user, plans, availableProviders, lavaPlanKeys = [], busy, error, onOpenChange, onPay, pending, checking, onCheck, onReopen, onAcknowledge }: BalanceSheetProps) {
  const copy = t(user.language);
  const [selectedPlanKey, setSelectedPlanKey] = useState("");
  const [method, setMethod] = useState<PaymentProvider>("tbank");

  const selectedPlan = useMemo(() => {
    if (!plans.length) return null;
    return plans.find((plan) => plan.key === selectedPlanKey) || plans[0];
  }, [plans, selectedPlanKey]);

  const availableMethods = useMemo(() => selectedPlan ? methods.filter(item => availableProviders.includes(item.id) && supportsPlan(item.id, selectedPlan, lavaPlanKeys)) : [], [availableProviders, selectedPlan, lavaPlanKeys]);
  useEffect(() => {
    if (!availableMethods.some(item => item.id === method)) setMethod(availableMethods[0]?.id || "tbank");
  }, [availableMethods, method]);

  const selectedMethod = availableMethods.find((item) => item.id === method) || availableMethods[0];
  const MethodIcon = selectedMethod?.icon || CreditCard;
  const selectedPrice = selectedPlan && selectedMethod ? planPrice(selectedPlan, selectedMethod.id) : "";
  const payDisabled = busy || pending || !selectedPlan || !selectedMethod || !selectedPrice;

  return (
    <Sheet
      balanceSheet
      open={open}
      onOpenChange={onOpenChange}
      title={copy.balance.title}
      description={`${copy.settings.balance}: ${formatKisses(user.credits)}`}
    >
      <div className="grid gap-3">
        <section className="rounded-2xl border border-primary/25 bg-primary/8 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[10px] text-muted-foreground">{copy.balance.current}</p>
              <p className="text-2xl font-bold leading-none">{formatKisses(user.credits)}</p>
            </div>
            <Badge variant="outline" className="bg-background/60">{copy.currency.unit}</Badge>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{copy.balance.description}</p>
        </section>

        <section className="grid gap-2">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{copy.balance.packageStep}</h3>
            <Badge variant="outline">{plans.length}</Badge>
          </div>
          {plans.length ? (
            <div className="grid gap-2 min-[430px]:grid-cols-2">
              {plans.map((plan) => {
                const active = selectedPlan?.key === plan.key;
                const price = planListPrice(plan) || copy.balance.priceBeforePayment;
                return (
                  <button
                    key={plan.key}
                    type="button"
                    className={`apix-focus-ring rounded-xl border p-3 text-left transition active:scale-[0.99] ${active ? "border-primary/55 bg-primary/12 shadow-inner" : "border-border bg-card/55 hover:bg-accent/45"}`}
                    onClick={() => setSelectedPlanKey(plan.key)}
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <p className="min-w-0 truncate text-sm font-semibold">{plan.title || formatKisses(plan.credits, { emoji: false })}</p>
                      {active ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
                    </div>
                    <p className="text-lg font-bold">{formatKisses(plan.credits)}</p>
                    <p className="text-[10px] text-muted-foreground">{price}</p>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
              {copy.balance.noPlans}
            </div>
          )}
        </section>

        <section className="grid gap-2">
          <h3 className="text-sm font-semibold">{copy.balance.methodStep}</h3>
          <div className="grid gap-2">
            {!availableMethods.length ? (
              <div className="rounded-xl border border-dashed border-border p-3 text-center text-xs text-muted-foreground">
                {copy.balance.unavailableMethod}
              </div>
            ) : availableMethods.map((item) => {
              const Icon = item.icon;
              const active = method === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`apix-focus-ring flex items-center gap-2 rounded-xl border p-2.5 text-left transition active:scale-[0.99] ${active ? "border-primary/55 bg-primary/12" : "border-border bg-card/55 hover:bg-accent/45"}`}
                  onClick={() => setMethod(item.id)}
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-background/75 text-primary"><Icon className="size-4" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold">{item.title}</span>
                    <span className="block truncate text-[10px] text-muted-foreground">{item.subtitle}</span>
                  </span>
                  {item.badge ? <Badge variant="outline" className="shrink-0">{item.badge}</Badge> : null}
                  {active ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
                </button>
              );
            })}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-card/65 p-3">
          <div className="mb-2 flex items-start gap-2">
            <CreditCard className="mt-0.5 size-4 shrink-0 text-primary" />
            <div>
              <h3 className="text-sm font-semibold">{copy.balance.checkoutStep}</h3>
              <p className="text-[10px] text-muted-foreground">{selectedPlan ? `${selectedPlan.title || selectedPlan.key} · ${selectedPrice || copy.balance.unavailableMethod}` : copy.balance.selectPlan}</p>
            </div>
          </div>
          <Button className="w-full" disabled={payDisabled} onClick={() => selectedPlan && selectedMethod && selectedPrice && onPay(selectedMethod.id, selectedPlan)}>
            <MethodIcon className="size-4" />
            {busy ? copy.balance.creating : selectedMethod ? `${copy.balance.payVia} ${selectedMethod.title}` : copy.balance.unavailableMethod}
          </Button>
          {error && <p className="mt-2 text-sm" role="alert">{error}</p>}
          {pending && <div className="mt-3 grid gap-2" role="status">
            <p className="text-sm">Статус предыдущего пополнения не подтверждён. Достаточный баланс не подтверждает оплату этого счёта.</p>
            <Button variant="outline" disabled={busy || checking} onClick={onCheck}>{checking ? "Проверяем…" : "Проверить оплату"}</Button>
            {onReopen && <Button variant="outline" disabled={busy || checking} onClick={onReopen}>Открыть эту оплату</Button>}
            {onAcknowledge && <><p className="text-xs">Не удалось связать попытку с конкретным счётом. Проверьте историю и платёжный сервис: новое пополнение может привести к повторной оплате.</p><Button variant="outline" className="whitespace-normal" disabled={busy || checking} onClick={onAcknowledge}>Историю проверил — разрешить новое пополнение</Button></>}
          </div>}
          <div className="mt-2 grid gap-1.5 text-[10px] text-muted-foreground">
            <p className="flex items-start gap-1.5"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" />{copy.balance.safety}</p>
            <p className="flex items-start gap-1.5"><Info className="mt-0.5 size-3.5 shrink-0" />{copy.balance.webhook}</p>
          </div>
        </section>
      </div>
    </Sheet>
  );
}

export { BalanceSheet };
