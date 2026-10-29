import { Repeat2 } from "lucide-react";
import { cn } from "@/lib/utils";

export function RepeatCount({ count, language, className }: { count?: number | null; language?: string; className?: string }) {
  if (typeof count !== "number" || !Number.isInteger(count) || count < 0) return null;
  return <span className={cn("inline-flex items-center gap-1 whitespace-nowrap text-xs", className)}>
    <Repeat2 size={14} aria-hidden="true" />
    <span>{language === "en" ? "Repeats" : "Повторов"}: {count}</span>
  </span>;
}
