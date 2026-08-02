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
      <header className="sticky top-0 z-40 -mx-1 mb-5 flex items-center justify-between gap-3 rounded-2xl border border-border/70 bg-background/76 px-3 py-2.5 shadow-sm backdrop-blur-2xl">
        <button
          type="button"
          className="apix-focus-ring flex min-w-0 items-center gap-3 rounded-xl text-left"
          onClick={() => onTabChange("profile")}
        >
          <span className="grid size-10 shrink-0 place-items-center overflow-hidden rounded-full border border-primary/30 bg-gradient-to-br from-primary via-fuchsia-500 to-cyan-400 font-bold text-white shadow-lg shadow-primary/15">
            {user.photo_url ? <img src={user.photo_url} alt="" className="size-full object-cover" /> : initial}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{name}</span>
            <span className="block truncate text-xs text-muted-foreground">APIX Studio</span>
          </span>
        </button>

        <Button variant="soft" size="sm" onClick={onBalanceOpen} aria-label="Открыть баланс">
          <CircleDollarSign />
          {formatCredits(user.credits)}
        </Button>
      </header>

      <main>{children}</main>

      <nav className="apix-bottom-nav apix-glass rounded-2xl p-1.5" aria-label="Основная навигация">
        <div className="apix-nav-scroll flex gap-1 overflow-x-auto overscroll-x-contain">
          {tabs.map(({ id, label, icon: Icon }) => {
            const active = id === activeTab;
            return (
              <button
                key={id}
                type="button"
                aria-current={active ? "page" : undefined}
                className={cn(
                  "apix-focus-ring flex min-h-14 min-w-[68px] flex-1 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[10px] font-medium transition",
                  active
                    ? "bg-primary/15 text-primary shadow-inner"
                    : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                )}
                onClick={() => {
                  haptic("light");
                  onTabChange(id);
                }}
              >
                <Icon className={cn("size-5", active && "drop-shadow-[0_0_10px_currentColor]")} />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export { AppShell };
