import type { TrendItem } from "@/lib/types";

const PINTEREST_MARKERS = ["pinterest", "пинтерест"];

function normalized(value: unknown): string {
  return String(value || "").trim().toLocaleLowerCase("ru-RU");
}

export function isPinterestServiceTrend(trend: TrendItem): boolean {
  const category = normalized(trend.category);
  if (category.includes("pinterest")) return true;

  const searchable = [trend.title, trend.description, trend.category_title]
    .map(normalized)
    .filter(Boolean)
    .join(" ");

  return PINTEREST_MARKERS.some((marker) => searchable.includes(marker));
}

export function findPinterestServiceTrend(items: TrendItem[]): TrendItem | null {
  return items.find(isPinterestServiceTrend) || null;
}
