import type { ReactNode } from "react";
import {
  Bot,
  CircleDollarSign,
  Film,
  Flame,
  GalleryVerticalEnd,
  ImageIcon,
  Orbit,
  Sparkles,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AppTab, UserProfile } from "@/lib/types";
import { cn, formatCredits } from "@/lib/utils";
import { haptic } from "@/lib/telegram";

const tabs: Array<{ id: AppTab; label: string; icon: typeof Sparkles }> = [
  { id: "studio", label: "Студия", icon: Sparkles },
  { id: "photo", label: "Фото", icon: ImageIcon },
  { id: "video", label: "Видео", icon: Film },
  { id: "motion", label: "Motion", icon: Orbit },
  { id: "feed", label: "Лента", icon: GalleryVerticalEnd },
  { id: "trends", label: "Тренды", icon: Flame },
  { id: "services", label: "Сервисы", icon: Bot },
  { id: "profile", label: "Профиль", icon: UserRound },
];

interface AppShellProps {
  activeTab: AppTab;
  user: UserProfile;
  children: ReactNode;
  onTabChange: (tab: AppTab) => void;
  onBalanceOpen: () => void;
}

function AppShell({ activeTab, user, children, onTabChange, onBalanceOpen }: AppShellProps) {
  const name = user.full_name || user.first_name || user.username || "Пользователь";
  const initial = name.trim().slice(0, 1).toUpperCase() || "A";

  return (
    <div className="apix-shell">
      <header className="sticky top-0 z-40 mb-2 flex min-h-11 items-center justify-between gap-2 rounded-xl border border-border/70 bg-background/88 px-2 py-1.5 shadow-sm backdrop-blur-2xl">
        <button
          type="button"
          className="apix-focus-ring flex min-w-0 items-center gap-2 rounded-lg text-left"
          onClick={() => onTabChange("profile")}
        >
          <span className="grid size-8 shrink-0 place-items-center overflow-hidden rounded-full border border-primary/30 bg-gradient-to-br from-primary via-fuchsia-500 to-cyan-400 text-xs font-bold text-white shadow-md shadow-primary/15">
            {user.photo_url ? <img src={user.photo_url} alt="" className="size-full object-cover" /> : initial}
          </span>
          <span className="min-w-0">
            <span className="block max-w-36 truncate text-xs font-semibold sm:max-w-none sm:text-sm">{name}</span>
            <span className="hidden truncate text-[10px] text-muted-foreground sm:block">APIX Studio</span>
          </span>
        </button>

        <Button variant="soft" size="sm" className="min-w-0 px-2.5" onClick={onBalanceOpen} aria-label="Открыть баланс">
          <CircleDollarSign className="size-3.5" />
          <span>{formatCredits(user.credits)}</span>
        </Button>
      </header>

      <main>{children}</main>

      <nav className="apix-bottom-nav apix-glass rounded-xl p-1" aria-label="Основная навигация">
        <div className="apix-nav-scroll flex gap-0.5 overflow-x-auto overscroll-x-contain">
          {tabs.map(({ id, label, icon: Icon }) => {
            const active = id === activeTab;
            return (
              <button
                key={id}
                type="button"
                aria-current={active ? "page" : undefined}
                aria-label={label}
                className={cn(
                  "apix-focus-ring flex min-h-12 min-w-[54px] flex-1 flex-col items-center justify-center gap-0.5 rounded-lg px-1 text-[9px] font-medium transition",
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
                <span className="leading-none">{label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export { AppShell };
