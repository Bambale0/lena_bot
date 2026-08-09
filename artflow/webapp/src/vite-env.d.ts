/// <reference types="vite/client" />

declare global {
  type TelegramWebApp = {
    initData: string;
    initDataUnsafe?: {
      start_param?: string;
      user?: {
        id: number;
        first_name?: string;
        last_name?: string;
        username?: string;
        photo_url?: string;
      };
    };
    colorScheme?: "light" | "dark";
    ready?: () => void;
    expand?: () => void;
    openLink?: (url: string) => void;
    openTelegramLink?: (url: string) => void;
    openInvoice?: (url: string, callback?: (status: string) => void) => void;
    BackButton?: {
      isVisible?: boolean;
      show?: () => void;
      hide?: () => void;
      onClick?: (callback: () => void) => void;
      offClick?: (callback: () => void) => void;
    };
    HapticFeedback?: {
      impactOccurred?: (style: "light" | "medium" | "heavy") => void;
      notificationOccurred?: (type: "error" | "success" | "warning") => void;
    };
  };

  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
    __APIX_EARLY_URL__?: string;
    __APIX_MINIAPP_BUILD_ID__?: string;
  }
}

export {};
