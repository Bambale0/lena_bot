import { toast } from "sonner";
import { isInsufficientCreditError } from "@/lib/credit-recovery";

export function creditErrorToast(error: unknown, fallback: string, onTopup?: () => void) {
  const shortage = isInsufficientCreditError(error);
  toast.error(shortage ? "Недостаточно кредитов. Пополни баланс и подтверди запуск ещё раз." : error instanceof Error ? error.message : fallback,
    shortage && onTopup ? { action: { label: "Пополнить", onClick: onTopup } } : undefined);
}
