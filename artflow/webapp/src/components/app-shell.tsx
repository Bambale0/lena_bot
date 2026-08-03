import { useEffect, useState, type ReactNode } from "react";
import {
  Bot,
  Film,
  Flame,
  GalleryVerticalEnd,
  ImageIcon,
  Orbit,
  Settings,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n";
import type { AppTab, UserProfile } from "@/lib/types";
import { cn, formatKisses } from "@/lib/utils";
import { haptic } from "@/lib/telegram";

const tabs: Array<{ id: AppTab; labelKey: keyof ReturnType<typeof t>["nav"]; icon: typeof GalleryVerticalEnd }> = [
  { id: "feed", labelKey: "feed", icon: GalleryVerticalEnd },
  { id: "photo", labelKey: "photo", icon: ImageIcon },
  { id: "video", labelKey: "video", icon: Film },
  { id: "motion", labelKey: "motion", icon: Orbit },
  { id: "trends", labelKey: "trends", icon: Flame },
  { id: "services", labelKey: "services", icon: Bot },
  { id: "profile", labelKey: "profile", icon: UserRound },
  { id: "settings", labelKey: "settings", icon: Settings },
];

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
  const copy = t(user.language);
  const name = user.full_name || user.first_name || user.username || "Пользователь";
  const initial = name.trim().slice(0, 1).toUpperCase() || "A";
  const viewport = useViewportMode();

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

        <Button variant="soft" size="sm" className="apix-balance-button min-w-fit shrink-0 justify-self-end px-2.5" onClick={onBalanceOpen} aria-label="Открыть баланс">
          <span>{formatKisses(user.credits, { compact: true })}</span>
        </Button>
      </header>

      <main>{children}</main>

      <nav className="apix-bottom-nav apix-glass rounded-2xl p-1" aria-label="Основная навигация">
        <div className="apix-nav-scroll flex min-w-0 gap-1 overflow-x-auto overscroll-x-contain" role="tablist" aria-label="Разделы Mini App">
          {tabs.map(({ id, labelKey, icon: Icon }) => {
            const active = id === activeTab;
            const label = copy.nav[labelKey];
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
