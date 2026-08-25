import type { TrendItem } from "@/lib/types";

const PINTEREST_MARKERS = ["pinterest", "пинтерест"];
export const PINTEREST_SERVICE_ALIAS_ID = 0;

const PINTEREST_SERVICE_FALLBACK: TrendItem = {
  id: PINTEREST_SERVICE_ALIAS_ID,
  kind: "image",
  title: "Pinterest",
  description: "Pinterest Flow со своей внешностью",
  category: "pinterest",
  category_title: "Сервисы",
  category_emoji: "✨",
  preview_url: null,
};

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

export function findPinterestServiceTrend(items: TrendItem[]): TrendItem {
  return items.find(isPinterestServiceTrend) || PINTEREST_SERVICE_FALLBACK;
}
