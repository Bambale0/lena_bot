import { ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { openExternalUrl } from "@/lib/telegram";

interface LockedScreenProps {
  message?: string;
  botUsername?: string;
  retrying?: boolean;
  onRetry: () => void;
}

function LockedScreen({ message, botUsername, retrying, onRetry }: LockedScreenProps) {
  const botLink = botUsername ? `https://t.me/${botUsername.replace(/^@/, "")}` : "";
  return (
    <main className="grid min-h-[100dvh] place-items-center px-4 py-8">
      <Card className="w-full max-w-md overflow-hidden">
        <CardHeader className="items-center text-center">
          <span className="mb-2 grid size-16 place-items-center rounded-2xl bg-primary/15 text-primary shadow-inner">
            <ShieldCheck className="size-8" />
          </span>
          <CardTitle className="text-xl">Откройте приложение через Telegram</CardTitle>
          <CardDescription>
            {message || "Telegram не передал подписанные данные входа. Баланс и задачи не подменяются демо-данными."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {botLink ? (
            <Button size="lg" onClick={() => openExternalUrl(botLink)}>
              Открыть Telegram-бота
              <ExternalLink />
            </Button>
          ) : null}
          <Button variant="outline" size="lg" disabled={retrying} onClick={onRetry}>
            <RefreshCw className={retrying ? "animate-spin" : ""} />
            Проверить снова
          </Button>
          <p className="text-center text-xs leading-relaxed text-muted-foreground">
            В обычном браузере доступен только интерфейс. Авторизация, баланс и генерации работают после запуска Mini App из бота.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

export { LockedScreen };
