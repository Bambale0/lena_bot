import type { StartTarget } from "@/lib/types";

const INIT_DATA_STORAGE_KEY = "apix:telegram-init-data:v2";
const START_PARAM_STORAGE_KEY = "apix:start-param:v2";

function webApp(): TelegramWebApp | null {
  return typeof window === "undefined" ? null : window.Telegram?.WebApp ?? null;
}

function paramFromUrl(urlValue: string, key: string): string {
  if (!urlValue) return "";
  try {
    const url = new URL(urlValue, window.location.origin);
    const hash = url.hash.startsWith("#") ? url.hash.slice(1) : url.hash;
    const hashValue = new URLSearchParams(hash).get(key);
    return hashValue || url.searchParams.get(key) || "";
  } catch {
    return "";
  }
}

function storedValue(key: string): string {
  try {
    return window.sessionStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function storeValue(key: string, value: string): void {
  if (!value) return;
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Some Telegram WebViews can disable sessionStorage. Auth still works in-memory.
  }
}

export function readTelegramInitData(): string {
  if (typeof window === "undefined") return "";
  const current = window.location.href;
  const early = window.__APIX_EARLY_URL__ || "";
  const candidates = [
    paramFromUrl(current, "tgWebAppData"),
    new URL(current).searchParams.get("tgWebAppData") || "",
    webApp()?.initData || "",
    paramFromUrl(early, "tgWebAppData"),
    storedValue(INIT_DATA_STORAGE_KEY),
  ];
  const result = candidates.find((value) => value.trim())?.trim() || "";
  storeValue(INIT_DATA_STORAGE_KEY, result);
  return result;
}

export async function waitForTelegramInitData(timeoutMs = 8_000): Promise<string> {
  const startedAt = Date.now();
  while (Date.now() - startedAt <= timeoutMs) {
    const value = readTelegramInitData();
    if (value) return value;
    await new Promise((resolve) => window.setTimeout(resolve, 100));
  }
  return "";
}

export function readStartParam(): string {
  if (typeof window === "undefined") return "";
  const current = window.location.href;
  const early = window.__APIX_EARLY_URL__ || "";
  const candidates = [
    paramFromUrl(current, "tgWebAppStartParam"),
    new URL(current).searchParams.get("startapp") || "",
    webApp()?.initDataUnsafe?.start_param || "",
    paramFromUrl(early, "tgWebAppStartParam"),
    storedValue(START_PARAM_STORAGE_KEY),
  ];
  const result = candidates.find((value) => value.trim())?.trim() || "";
  storeValue(START_PARAM_STORAGE_KEY, result);
  return result;
}

export function parseStartTarget(rawValue: string): StartTarget | null {
  const value = String(rawValue || "").trim();
  if (!value) return null;
  const separator = value.indexOf("_");
  if (separator < 1) return null;
  const kind = value.slice(0, separator) as StartTarget["kind"];
  const targetValue = value.slice(separator + 1).trim();
  // trend_* deep links are handled by TrendRunnerPortal so the legacy App flow
  // cannot route users into the full generation form with leaked settings.
  if (!targetValue || !["ref", "profile", "feed", "remix", "prompt", "task"].includes(kind)) {
    return null;
  }
  return { kind, value: targetValue };
}

export function configureTelegramWebApp(): void {
  const app = webApp();
  app?.ready?.();
  app?.expand?.();
  const scheme = app?.colorScheme || "dark";
  document.documentElement.classList.toggle("dark", scheme !== "light");
}

export function telegramUserName(): string {
  const user = webApp()?.initDataUnsafe?.user;
  return [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim();
}

export function haptic(type: "light" | "medium" | "heavy" = "light"): void {
  webApp()?.HapticFeedback?.impactOccurred?.(type);
}

export function notifyHaptic(type: "error" | "success" | "warning"): void {
  webApp()?.HapticFeedback?.notificationOccurred?.(type);
}

export function openExternalUrl(value: string): void {
  if (!value) return;
  const app = webApp();
  if (value.startsWith("https://t.me/") && app?.openTelegramLink) {
    app.openTelegramLink(value);
    return;
  }
  if (app?.openLink) {
    app.openLink(value);
    return;
  }
  window.open(value, "_blank", "noopener,noreferrer");
}

export function openTelegramInvoice(url: string, callback?: (status: string) => void): void {
  const app = webApp();
  if (app?.openInvoice) {
    app.openInvoice(url, callback);
    return;
  }
  openExternalUrl(url);
}
