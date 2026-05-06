export type TelegramUser = {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
};

type TelegramWebApp = {
  initData: string;
  initDataUnsafe?: { user?: TelegramUser };
  ready: () => void;
  expand: () => void;
  close: () => void;
  openTelegramLink: (url: string) => void;
  HapticFeedback?: { impactOccurred: (style: "light" | "medium" | "heavy") => void };
};

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

const demoUser: TelegramUser = {
  id: 123456789,
  first_name: "Lena",
  last_name: "Creator",
  username: "LeLu88",
};

const webApp = () => window.Telegram?.WebApp;

export function initTelegram() {
  const tg = webApp();
  tg?.ready();
  tg?.expand();
}

export function getInitData() {
  return webApp()?.initData || "";
}

export function getUser() {
  return webApp()?.initDataUnsafe?.user || demoUser;
}

export function haptic(style: "light" | "medium" | "heavy" = "light") {
  webApp()?.HapticFeedback?.impactOccurred(style);
}

export function openTelegramLink(url: string) {
  const tg = webApp();
  if (tg) tg.openTelegramLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

export function close() {
  webApp()?.close();
}

export function shareUrl(url: string) {
  openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}`);
}
