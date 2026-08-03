import { CheckCircle2, Languages, Palette, RefreshCw, Smartphone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { colorSchemes, useColorScheme, type ColorScheme } from "@/lib/color-schemes";
import type { AppLanguage, UserProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SettingsScreenProps {
  user: UserProfile;
  busy?: boolean;
  onLanguageChange: (language: AppLanguage) => void;
  onResetApp: () => void;
}

const languages: Array<{ value: AppLanguage; title: string; subtitle: string; emoji: string }> = [
  { value: "ru", title: "Русский", subtitle: "Интерфейс и ответы бота на русском", emoji: "🇷🇺" },
  { value: "en", title: "English", subtitle: "Bot language and service messages in English", emoji: "🇬🇧" },
];

function SettingsScreen({ user, busy, onLanguageChange, onResetApp }: SettingsScreenProps) {
  const color = useColorScheme();
  const currentLanguage = user.language || "ru";

  return (
    <div className="grid gap-3">
      <div className="rounded-2xl border border-border bg-card/70 p-3">
        <div className="flex items-center gap-2">
          <span className="grid size-10 place-items-center rounded-xl bg-primary/15 text-primary"><Palette className="size-5" /></span>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold">Настройки</h1>
            <p className="truncate text-xs text-muted-foreground">Внешний вид, язык и поведение Mini App</p>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2"><Palette className="size-4" /> Цветовая схема</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2">
          <div className="grid grid-cols-2 gap-2 min-[520px]:grid-cols-4">
            {colorSchemes.map((scheme) => (
              <SchemeButton
                key={scheme.id}
                scheme={scheme}
                active={color.scheme === scheme.id}
                onClick={() => color.setScheme(scheme.id)}
              />
            ))}
          </div>
          <p className="text-xs text-muted-foreground">Схема сохраняется на устройстве и применяется через CSS-переменные. Telegram light/dark не ломается.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2"><Languages className="size-4" /> Язык</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2">
          {languages.map((language) => {
            const active = currentLanguage === language.value;
            return (
              <button
                key={language.value}
                type="button"
                className={cn(
                  "apix-focus-ring flex items-center gap-2 rounded-xl border p-3 text-left transition active:scale-[0.99]",
                  active ? "border-primary/55 bg-primary/12" : "border-border bg-card/55 hover:bg-accent/45",
                )}
                disabled={busy || active}
                onClick={() => onLanguageChange(language.value)}
              >
                <span className="text-lg" aria-hidden="true">{language.emoji}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{language.title}</span>
                  <span className="block text-[10px] text-muted-foreground">{language.subtitle}</span>
                </span>
                {active ? <Badge variant="outline">активен</Badge> : null}
              </button>
            );
          })}
          <p className="text-xs text-muted-foreground">Переключатель вызывает backend `/settings/language`, поэтому язык сохраняется в профиле пользователя.</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2"><Smartphone className="size-4" /> Диагностика Mini App</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-xs text-muted-foreground">
          <div className="grid grid-cols-2 gap-1.5">
            <InfoPill label="Пользователь" value={user.username ? `@${user.username}` : String(user.tg_id || user.id)} />
            <InfoPill label="Язык" value={currentLanguage.toUpperCase()} />
            <InfoPill label="Схема" value={color.current.label} />
            <InfoPill label="Баланс" value={`${user.credits} кр.`} />
          </div>
          <Button variant="outline" size="sm" onClick={onResetApp}><RefreshCw className="size-4" /> Перезагрузить данные</Button>
        </CardContent>
      </Card>
    </div>
  );
}

function SchemeButton({
  scheme,
  active,
  onClick,
}: {
  scheme: (typeof colorSchemes)[number];
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "apix-focus-ring grid min-h-24 gap-1 rounded-2xl border p-3 text-left transition active:scale-[0.99]",
        active ? "border-primary/60 bg-primary/12 shadow-inner" : "border-border bg-card/55 hover:bg-accent/45",
      )}
      data-apix-preview-scheme={scheme.id as ColorScheme}
      onClick={onClick}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="text-2xl" aria-hidden="true">{scheme.emoji}</span>
        {active ? <CheckCircle2 className="size-4 text-primary" /> : null}
      </span>
      <span className="block text-sm font-semibold">{scheme.label}</span>
      <span className="block text-[10px] text-muted-foreground">{scheme.description}</span>
      <span className="apix-scheme-preview mt-1 block h-2 rounded-full" />
    </button>
  );
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-background/55 px-2 py-1.5">
      <p className="text-[9px] text-muted-foreground">{label}</p>
      <p className="truncate text-xs font-semibold text-foreground">{value}</p>
    </div>
  );
}

export { SettingsScreen };
