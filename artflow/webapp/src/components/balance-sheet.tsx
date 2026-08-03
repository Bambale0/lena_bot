import { useMemo, useState } from "react";
import { Banknote, Bitcoin, CheckCircle2, CreditCard, Info, Send, ShieldCheck, Star } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { PaymentPlan, UserProfile } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

type PaymentProvider = "stars" | "tbank" | "crypto" | "lava";

interface PaymentMethod {
  id: PaymentProvider;
  title: string;
  subtitle: string;
  icon: typeof Star;
  badge?: string;
}

const methods: PaymentMethod[] = [
  { id: "stars", title: "Telegram Stars", subtitle: "Оплата внутри Telegram", icon: Star, badge: "быстро" },
  { id: "tbank", title: "Карта", subtitle: "T-Bank / банковская карта", icon: Banknote },
  { id: "crypto", title: "CryptoBot", subtitle: "USDT и крипто-оплата", icon: Bitcoin },
  { id: "lava", title: "СБП / Lava", subtitle: "Российская оплата по ссылке", icon: Send },
];

interface BalanceSheetProps {
  open: boolean;
  user: UserProfile;
  plans: PaymentPlan[];
  busy?: boolean;
  onOpenChange: (open: boolean) => void;
  onPay: (provider: PaymentProvider, plan: PaymentPlan) => void;
}

function planPrice(plan: PaymentPlan, method: PaymentProvider): string {
  if (method === "stars" && plan.price_stars) return `${plan.price_stars} ⭐`;
  if (method === "crypto" && plan.price_usdt) return `${plan.price_usdt} USDT`;
  if (plan.price_rub) return `${plan.price_rub} ₽`;
  return "Цена перед оплатой";
}

function BalanceSheet({ open, user, plans, busy, onOpenChange, onPay }: BalanceSheetProps) {
  const [selectedPlanKey, setSelectedPlanKey] = useState("");
  const [method, setMethod] = useState<PaymentProvider>("stars");

  const selectedPlan = useMemo(() => {
    if (!plans.length) return null;
    return plans.find((plan) => plan.key === selectedPlanKey) || plans[0];
  }, [plans, selectedPlanKey]);

  const selectedMethod = methods.find((item) => item.id === method) || methods[0];
  const MethodIcon = selectedMethod.icon;

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Кабинет оплаты"
      description={`Баланс: ${formatCredits(user.credits)} кредитов`}
    >
      <div className="grid gap-3">
        <section className="rounded-2xl border border-primary/25 bg-primary/8 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[10px] text-muted-foreground">Текущий баланс</p>
              <p className="text-2xl font-bold leading-none"><span aria-hidden="true">💋</span> {formatCredits(user.credits)}</p>
            </div>
            <Badge variant="outline" className="bg-background/60">кредиты</Badge>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Выбери пакет, способ оплаты и создай счёт. После успешной оплаты backend пополнит баланс через свой webhook.</p>
        </section>

        <section className="grid gap-2">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">1. Пакет кредитов</h3>
            <Badge variant="outline">{plans.length}</Badge>
          </div>
          {plans.length ? (
            <div className="grid gap-2 min-[430px]:grid-cols-2">
              {plans.map((plan) => {
                const active = selectedPlan?.key === plan.key;
                return (
                  <button
                    key={plan.key}
                    type="button"
                    className={`apix-focus-ring rounded-xl border p-3 text-left transition active:scale-[0.99] ${active ? "border-primary/55 bg-primary/12 shadow-inner" : "border-border bg-card/55 hover:bg-accent/45"}`}
                    onClick={() => setSelectedPlanKey(plan.key)}
                  >
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <p className="min-w-0 truncate text-sm font-semibold">{plan.title || `${formatCredits(plan.credits)} кредитов`}</p>
                      {active ? <CheckCircle2 className="size-4 shrink-0 text-primary" /> : null}
                    </div>
                    <p className="text-lg font-bold">{formatCredits(plan.credits)} кр.</p>
                    <p className="text-[10px] text-muted-foreground">от {planPrice(plan, method)}</p>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
              Пакеты оплаты временно недоступны. Backend `/plans` не вернул активные тарифы.
            </div>
          )}
        </section>

        <section className="grid gap-2">
          <h3 className="text-sm font-semibold">2. Способ оплаты</h3>
          <div className="grid gap-2">
            {methods.map((item) => {
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
              <h3 className="text-sm font-semibold">3. Создать счёт</h3>
              <p className="text-[10px] text-muted-foreground">{selectedPlan ? `${selectedPlan.title || selectedPlan.key} · ${planPrice(selectedPlan, method)}` : "Выбери пакет, чтобы продолжить"}</p>
            </div>
          </div>
          <Button className="w-full" disabled={busy || !selectedPlan} onClick={() => selectedPlan && onPay(method, selectedPlan)}>
            <MethodIcon className="size-4" />
            {busy ? "Создаём счёт…" : `Оплатить через ${selectedMethod.title}`}
          </Button>
          <div className="mt-2 grid gap-1.5 text-[10px] text-muted-foreground">
            <p className="flex items-start gap-1.5"><ShieldCheck className="mt-0.5 size-3.5 shrink-0" />Счёт создаётся на backend, секреты платёжных провайдеров не попадают во фронт.</p>
            <p className="flex items-start gap-1.5"><Info className="mt-0.5 size-3.5 shrink-0" />После оплаты вернись в Mini App: баланс обновится через webhook и авто-refresh.</p>
          </div>
        </section>
      </div>
    </Sheet>
  );
}

export { BalanceSheet };
