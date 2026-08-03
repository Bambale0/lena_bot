import { useEffect, useState, type ReactNode } from "react";
import {
  Bot,
  Film,
  Flame,
  GalleryVerticalEnd,
  ImageIcon,
  Orbit,
  Palette,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AppTab, UserProfile } from "@/lib/types";
import { cn, formatCredits } from "@/lib/utils";
import { haptic } from "@/lib/telegram";

const tabs: Array<{ id: AppTab; label: string; icon: typeof GalleryVerticalEnd }> = [
  { id: "feed", label: "Лента", icon: GalleryVerticalEnd },
  { id: "photo", label: "Фото", icon: ImageIcon },
  { id: "video", label: "Видео", icon: Film },
  { id: "motion", label: "Motion", icon: Orbit },
  { id: "trends", label: "Тренды", icon: Flame },
  { id: "services", label: "Сервисы", icon: Bot },
  { id: "profile", label: "Профиль", icon: UserRound },
];

const colorSchemes = [
  { id: "violet", label: "Неон", emoji: "🟣" },
  { id: "kiss", label: "Поцелуй", emoji: "💋" },
  { id: "ocean", label: "Океан", emoji: "🌊" },
  { id: "banana", label: "Банан", emoji: "🍌" },
] as const;

type ColorScheme = (typeof colorSchemes)[number]["id"];

const COLOR_SCHEME_STORAGE_KEY = "apix-color-scheme";
const DEFAULT_COLOR_SCHEME: ColorScheme = "violet";

interface AppShellProps {
  activeTab: AppTab;
  user: UserProfile;
  children: ReactNode;
  onTabChange: (tab: AppTab) => void;
  onBalanceOpen: () => void;
}

type ViewportMode = "nano" | "phone" | "phablet" | "tablet" | "wide";

interface ViewportState {
  mode: ViewportMode;
  short: boolean;
  width: number;
  height: number;
}

function isColorScheme(value: string | null): value is ColorScheme {
  return Boolean(value && colorSchemes.some((scheme) => scheme.id === value));
}

function readColorScheme(): ColorScheme {
  if (typeof window === "undefined") return DEFAULT_COLOR_SCHEME;
  const stored = window.localStorage.getItem(COLOR_SCHEME_STORAGE_KEY);
  return isColorScheme(stored) ? stored : DEFAULT_COLOR_SCHEME;
}

function applyColorScheme(scheme: ColorScheme) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.apixScheme = scheme;
}

function useColorScheme() {
  const [scheme, setScheme] = useState<ColorScheme>(() => {
    const initial = readColorScheme();
    applyColorScheme(initial);
    return initial;
  });

  useEffect(() => {
    applyColorScheme(scheme);
    window.localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, scheme);
  }, [scheme]);

  const currentIndex = colorSchemes.findIndex((item) => item.id === scheme);
  const current = colorSchemes[currentIndex >= 0 ? currentIndex : 0];
  const cycle = () => {
    const next = colorSchemes[(currentIndex + 1) % colorSchemes.length] || colorSchemes[0];
    setScheme(next.id);
    haptic("light");
  };
  return { current, cycle };
}

function classifyViewport(width: number): ViewportMode {
  if (width <= 360) return "nano";
  if (width <= 430) return "phone";
  if (width <= 560) return "phablet";
  if (width <= 900) return "tablet";
  return "wide";
}

function readViewport(): ViewportState {
  if (typeof window === "undefined") return { mode: "wide", short: false, width: 1024, height: 768 };
  const viewport = window.visualViewport;
  const width = Math.max(320, Math.round(viewport?.width || window.innerWidth || document.documentElement.clientWidth || 1024));
  const height = Math.max(360, Math.round(viewport?.height || window.innerHeight || document.documentElement.clientHeight || 768));
  return { mode: classifyViewport(width), short: height <= 660, width, height };
}

function applyViewportCssVars(viewport: ViewportState) {
  if (typeof document === "undefined") return;
  document.documentElement.style.setProperty("--apix-visual-viewport-width", `${viewport.width}px`);
  document.documentElement.style.setProperty("--apix-visual-viewport-height", `${viewport.height}px`);
}

function useViewportMode() {
  const [viewport, setViewport] = useState(() => {
    const initial = readViewport();
    applyViewportCssVars(initial);
    return initial;
  });

  useEffect(() => {
    let frame = 0;
    const update = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        const next = readViewport();
        applyViewportCssVars(next);
        setViewport(next);
      });
    };
    update();
    window.addEventListener("resize", update, { passive: true });
    window.addEventListener("orientationchange", update, { passive: true });
    window.visualViewport?.addEventListener("resize", update, { passive: true });
    window.visualViewport?.addEventListener("scroll", update, { passive: true });
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, []);

  return viewport;
}

function AppShell({ activeTab, user, children, onTabChange, onBalanceOpen }: AppShellProps) {
  const name = user.full_name || user.first_name || user.username || "Пользователь";
  const initial = name.trim().slice(0, 1).toUpperCase() || "A";
  const viewport = useViewportMode();
  const scheme = useColorScheme();

  return (
    <div
      className="apix-shell"
      data-viewport={viewport.mode}
      data-short={viewport.short ? "true" : "false"}
      data-width={viewport.width}
      data-height={viewport.height}
    >
      <header className="apix-app-header grid min-h-11 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-xl border border-border/70 bg-background/88 px-2 py-1.5 shadow-sm backdrop-blur-2xl">
        <button
          type="button"
          className="apix-profile-button apix-focus-ring flex min-w-0 max-w-full items-center gap-2 rounded-lg text-left"
          onClick={() => onTabChange("profile")}
        >
          <span className="apix-profile-avatar grid size-8 shrink-0 place-items-center overflow-hidden rounded-full border border-primary/30 bg-gradient-to-br from-primary via-fuchsia-500 to-cyan-400 text-xs font-bold text-white shadow-md shadow-primary/15">
            {user.photo_url ? <img src={user.photo_url} alt="" className="size-full object-cover" /> : initial}
          </span>
          <span className="min-w-0">
            <span className="apix-profile-name block max-w-36 truncate text-xs font-semibold sm:max-w-none sm:text-sm">{name}</span>
            <span className="apix-profile-subtitle hidden truncate text-[10px] text-muted-foreground sm:block">APIX Mini App</span>
          </span>
        </button>

        <div className="apix-header-actions flex min-w-fit shrink-0 items-center gap-1 justify-self-end">
          <Button
            variant="ghost"
            size="sm"
            className="apix-theme-button shrink-0 px-2"
            onClick={scheme.cycle}
            aria-label={`Цветовая схема: ${scheme.current.label}. Переключить`}
            title={`Цветовая схема: ${scheme.current.label}`}
          >
            <Palette className="size-3.5" />
            <span className="apix-theme-emoji" aria-hidden="true">{scheme.current.emoji}</span>
            <span className="apix-theme-label hidden sm:inline">{scheme.current.label}</span>
          </Button>
          <Button variant="soft" size="sm" className="apix-balance-button min-w-fit shrink-0 px-2.5" onClick={onBalanceOpen} aria-label="Открыть баланс">
            <span className="text-sm leading-none" aria-hidden="true">💋</span>
            <span>{formatCredits(user.credits)}</span>
          </Button>
        </div>
      </header>

      <main>{children}</main>

      <nav className="apix-bottom-nav apix-glass rounded-2xl p-1" aria-label="Основная навигация">
        <div className="apix-nav-scroll flex min-w-0 gap-1 overflow-x-auto overscroll-x-contain" role="tablist" aria-label="Разделы Mini App">
          {tabs.map(({ id, label, icon: Icon }) => {
            const active = id === activeTab;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={active}
                aria-current={active ? "page" : undefined}
                aria-label={label}
                className={cn(
                  "apix-nav-item apix-focus-ring flex min-h-12 min-w-[74px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-xl px-2 text-[10px] font-semibold transition active:scale-[0.97]",
                  active
                    ? "bg-primary/15 text-primary shadow-inner"
                    : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                )}
                onClick={() => {
                  haptic("light");
                  onTabChange(id);
                }}
              >
                <Icon className={cn("size-[18px]", active && "drop-shadow-[0_0_8px_currentColor]")} />
                <span className="apix-nav-label leading-none">{label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export { AppShell };
