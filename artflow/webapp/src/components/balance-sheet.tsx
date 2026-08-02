import { Banknote, Bitcoin, Send, Star } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      <div className="grid gap-3 sm:grid-cols-2">
        {plans.length ? (
          plans.map((plan) => (
            <Card key={plan.key} className="shadow-none">
              <CardHeader>
                <CardTitle>{plan.title || `${formatCredits(plan.credits)} кредитов`}</CardTitle>
                <p className="text-2xl font-bold">{formatCredits(plan.credits)} кр.</p>
              </CardHeader>
              <CardContent className="grid grid-cols-2 gap-2">
                <Button disabled={busy} onClick={() => onPay("stars", plan)}>
                  <Star /> Stars
                </Button>
                <Button variant="outline" disabled={busy} onClick={() => onPay("tbank", plan)}>
                  <Banknote /> Карта
                </Button>
                <Button variant="outline" disabled={busy} onClick={() => onPay("crypto", plan)}>
                  <Bitcoin /> Crypto
                </Button>
                <Button variant="outline" disabled={busy} onClick={() => onPay("lava", plan)}>
                  <Send /> СБП
                </Button>
                <p className="col-span-2 text-center text-xs text-muted-foreground">
                  {plan.price_rub ? `${plan.price_rub} ₽` : "Цена будет показана перед оплатой"}
                </p>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="col-span-full rounded-2xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            Пакеты оплаты временно недоступны. Баланс не изменён.
          </div>
        )}
      </div>
    </Sheet>
  );
}

export { BalanceSheet };
