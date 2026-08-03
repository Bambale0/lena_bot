import { Banknote, Bitcoin, Send, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { PaymentPlan, UserProfile } from "@/lib/types";
import { formatCredits } from "@/lib/utils";

interface BalanceSheetProps {
  open: boolean;
  user: UserProfile;
  plans: PaymentPlan[];
  busy?: boolean;
  onOpenChange: (open: boolean) => void;
  onPay: (provider: "stars" | "tbank" | "crypto" | "lava", plan: PaymentPlan) => void;
}

function BalanceSheet({ open, user, plans, busy, onOpenChange, onPay }: BalanceSheetProps) {
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Баланс"
      description={`Доступно ${formatCredits(user.credits)} кредитов`}
    >
      <div className="grid gap-2">
        {plans.length ? (
          plans.map((plan) => (
            <section key={plan.key} className="rounded-xl border border-border bg-card/65 p-2.5">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="truncate text-sm font-semibold">{plan.title || `${formatCredits(plan.credits)} кредитов`}</h3>
                  <p className="text-[10px] text-muted-foreground">{plan.price_rub ? `${plan.price_rub} ₽` : "Цена перед оплатой"}</p>
                </div>
                <p className="shrink-0 text-lg font-bold">{formatCredits(plan.credits)} кр.</p>
              </div>
              <div className="grid grid-cols-4 gap-1">
                <Button size="sm" className="px-1 text-[10px]" disabled={busy} onClick={() => onPay("stars", plan)}><Star className="size-3.5" /> Stars</Button>
                <Button size="sm" className="px-1 text-[10px]" variant="outline" disabled={busy} onClick={() => onPay("tbank", plan)}><Banknote className="size-3.5" /> Карта</Button>
                <Button size="sm" className="px-1 text-[10px]" variant="outline" disabled={busy} onClick={() => onPay("crypto", plan)}><Bitcoin className="size-3.5" /> Crypto</Button>
                <Button size="sm" className="px-1 text-[10px]" variant="outline" disabled={busy} onClick={() => onPay("lava", plan)}><Send className="size-3.5" /> СБП</Button>
              </div>
            </section>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
            Пакеты оплаты временно недоступны. Баланс не изменён.
          </div>
        )}
      </div>
    </Sheet>
  );
}

export { BalanceSheet };
