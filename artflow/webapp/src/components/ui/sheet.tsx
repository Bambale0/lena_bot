import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface SheetProps {
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
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function Sheet({ open, title, description, children, footer, className, onOpenChange }: SheetProps) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const instanceId = useId();
  const titleId = `${instanceId}-title`;
  const descriptionId = `${instanceId}-description`;

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const focusFirst = () => {
      const target = closeRef.current || dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE) || dialogRef.current;
      target?.focus?.();
    };
    window.requestAnimationFrame(focusFirst);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onOpenChange(false);
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((node) => {
        const style = window.getComputedStyle(node);
        return style.display !== "none" && style.visibility !== "hidden";
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
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus?.();
    };
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[1200] flex items-end justify-center sm:items-center" role="presentation">
      <button
        type="button"
        aria-label="Закрыть"
        className="absolute inset-0 bg-black/65 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      <section
        ref={dialogRef}
        role="dialog"
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
