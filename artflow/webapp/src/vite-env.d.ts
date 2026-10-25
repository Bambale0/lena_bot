/// <reference types="vite/client" />

declare global {
  type TelegramWebAppEvent = "safeAreaChanged" | "contentSafeAreaChanged" | "viewportChanged" | "fullscreenChanged" | "fullscreenFailed";
  type TelegramSafeArea = { top: number; right: number; bottom: number; left: number };
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
    version?: string;
    isVersionAtLeast?: (version: string) => boolean;
    isFullscreen?: boolean;
    requestFullscreen?: () => void;
    safeAreaInset?: TelegramSafeArea;
    contentSafeAreaInset?: TelegramSafeArea;
    onEvent?: (event: TelegramWebAppEvent, callback: () => void) => void;
    offEvent?: (event: TelegramWebAppEvent, callback: () => void) => void;
    headerColor?: string;
    backgroundColor?: string;
    bottomBarColor?: string;
    setHeaderColor?: (color: string) => void;
    setBackgroundColor?: (color: string) => void;
    setBottomBarColor?: (color: string) => void;
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
