import { useEffect, useId, useLayoutEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn, formatKisses } from "@/lib/utils";
import { readStudioBalance, subscribeStudioBalance } from "@/lib/studio-balance";

interface SheetProps {
  balanceSheet?: boolean;
  balanceUnavailableReason?: string;
  role?: "dialog" | "alertdialog";
  open: boolean;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  onOpenChange: (open: boolean) => void;
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "summary",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

const activeSheets: HTMLElement[] = [];
let unlockedOverflow = "";

function Sheet({ open, title, description, children, footer, className, onOpenChange, role = "dialog", balanceSheet = false, balanceUnavailableReason }: SheetProps) {
  const balance = useSyncExternalStore(subscribeStudioBalance, readStudioBalance, () => null);
  const suspended = !balanceSheet && Boolean(balance?.open);
  const suspendedRef = useRef(suspended);
  useLayoutEffect(() => { suspendedRef.current = suspended; }, [suspended]);
  const resumeFocus = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const onOpenChangeRef = useRef(onOpenChange);
  useLayoutEffect(() => { onOpenChangeRef.current = onOpenChange; }, [onOpenChange]);
  const instanceId = useId();
  const titleId = `${instanceId}-title`;
  const descriptionId = `${instanceId}-description`;

  useEffect(() => {
    if (!open || suspended) return undefined;
    const dialog = dialogRef.current!;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!activeSheets.length) unlockedOverflow = document.body.style.overflow;
    activeSheets.push(dialog);
    document.body.style.overflow = "hidden";

    const focusFirst = () => {
      if (activeSheets[activeSheets.length - 1] !== dialog) return;
      const target = resumeFocus.current && dialog.contains(resumeFocus.current) ? resumeFocus.current : closeRef.current || dialog.querySelector<HTMLElement>(FOCUSABLE) || dialog;
      resumeFocus.current = null;
      target?.focus?.();
    };
    const focusFrame = window.requestAnimationFrame(focusFirst);

    const onKeyDown = (event: KeyboardEvent) => {
      if (activeSheets[activeSheets.length - 1] !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onOpenChangeRef.current(false);
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((node) => {
        const style = window.getComputedStyle(node);
        return style.display !== "none" && style.visibility !== "hidden" && node.getClientRects().length > 0;
      });
      if (!focusable.length) {
        event.preventDefault();
        dialogRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !dialogRef.current.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      if (suspendedRef.current && document.activeElement instanceof HTMLElement && dialog.contains(document.activeElement)) resumeFocus.current = document.activeElement;
      const index = activeSheets.indexOf(dialog);
      if (index !== -1) activeSheets.splice(index, 1);
      if (!activeSheets.length) document.body.style.overflow = unlockedOverflow;
      window.removeEventListener("keydown", onKeyDown);
      if (!suspendedRef.current && previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open, suspended]);

  if (!open) return null;

  return (
    <div hidden={suspended} inert={suspended} style={suspended ? { display: "none" } : undefined} className="fixed inset-0 z-[1200] flex items-end justify-center sm:items-center" role="presentation">
      <button
        type="button"
        aria-label="Закрыть"
        className="absolute inset-0 bg-black/65 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      <section
        ref={dialogRef}
        role={role}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          "apix-safe-sheet relative z-10 flex max-h-[calc(100dvh-env(safe-area-inset-top)-4px)] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl border border-border bg-popover shadow-2xl sm:max-h-[92dvh] sm:rounded-2xl",
          className,
        )}
      >
        <div className="mx-auto mt-1.5 h-1 w-9 shrink-0 rounded-full bg-muted-foreground/25 sm:hidden" />
        <header className="flex items-start justify-between gap-3 border-b border-border px-3 py-2.5 sm:px-4 sm:py-3">
          <div className="min-w-0">
            <h2 id={titleId} className="truncate text-base font-semibold sm:text-lg">
              {title}
            </h2>
            {description ? <p id={descriptionId} className="mt-0.5 truncate text-xs text-muted-foreground">{description}</p> : null}
          </div>
          <Button ref={closeRef} variant="ghost" size="icon" className="size-9 min-h-9" aria-label="Закрыть" onClick={() => onOpenChange(false)}>
            <X />
          </Button>
        </header>
        {balance && !balanceSheet && <div className="studio-overlay-balance">
          <span>{balance.language === "en" ? "Balance" : "Баланс"}: {formatKisses(balance.credits)}</span>
          <button type="button" className="apix-focus-ring" disabled={Boolean(balanceUnavailableReason)} onClick={balance.onOpen}>{balance.language === "en" ? "Top up" : "Пополнить"}</button>
          {balanceUnavailableReason && <p role="status">{balanceUnavailableReason}</p>}
        </div>}
        <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-4">{children}</div>
        {footer ? (
          <footer className="border-t border-border bg-popover/95 p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur-xl sm:p-4">
            {footer}
          </footer>
        ) : null}
      </section>
    </div>
  );
}

export { Sheet };
