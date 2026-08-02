import { useRef, useState } from "react";
import { Bot, Camera, Film, Headphones, ImageIcon, LifeBuoy, Send, Sparkles, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { AppTab, AssistantMessage, PhotoPromptResult } from "@/lib/types";

interface ServicesScreenProps {
  messages: AssistantMessage[];
  assistantBusy: boolean;
  photoPromptBusy: boolean;
  photoPromptResult: PhotoPromptResult | null;
  onAssistantSend: (message: string) => void;
  onPhotoPrompt: (file: File) => void;
  onUsePrompt: (prompt: string) => void;
  onNavigate: (tab: AppTab) => void;
}

function ServicesScreen({
  messages,
  assistantBusy,
  photoPromptBusy,
  photoPromptResult,
  onAssistantSend,
  onPhotoPrompt,
  onUsePrompt,
  onNavigate,
}: ServicesScreenProps) {
  const [message, setMessage] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const send = () => {
    const value = message.trim();
    if (!value || assistantBusy) return;
    onAssistantSend(value);
    setMessage("");
  };

  const services = [
    { title: "Оживить фото", description: "Image-to-video с подходящей моделью", icon: Film, tab: "video" as AppTab },
    { title: "Изменить фото", description: "Edit-модели и несколько референсов", icon: ImageIcon, tab: "photo" as AppTab },
    { title: "Avatar", description: "Фото персонажа и аудио-сценарий", icon: Headphones, tab: "video" as AppTab },
    { title: "Партнёрам", description: "Реферальная статистика и начисления", icon: Users, tab: "profile" as AppTab },
    { title: "Поддержка", description: "Task ID и понятная диагностика ошибок", icon: LifeBuoy, tab: "profile" as AppTab },
  ];

  return (
    <div className="grid gap-5">
      <div>
        <Badge className="mb-2">AI-инструменты</Badge>
        <h1 className="text-3xl font-bold tracking-tight">Сервисы</h1>
        <p className="mt-1 text-sm text-muted-foreground">Помощник, анализ фото и быстрые переходы в готовые сценарии.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {services.map(({ title, description, icon: Icon, tab }) => (
          <button
            key={title}
            type="button"
            className="apix-focus-ring apix-glass rounded-2xl p-4 text-left transition hover:-translate-y-0.5 hover:border-primary/35"
            onClick={() => onNavigate(tab)}
          >
            <span className="mb-3 grid size-10 place-items-center rounded-xl bg-primary/12 text-primary"><Icon className="size-5" /></span>
            <span className="block text-sm font-semibold">{title}</span>
            <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{description}</span>
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="mb-1 flex items-center gap-2 text-primary"><Bot className="size-5" /><span className="text-xs font-semibold uppercase tracking-wider">Помощник</span></div>
            <CardTitle>Какую модель выбрать?</CardTitle>
            <CardDescription>Помощник получает актуальный registry моделей и последние сообщения, а не выдумывает возможности.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="max-h-80 space-y-2 overflow-y-auto rounded-2xl border border-border bg-background/35 p-3">
              {messages.length ? messages.map((item, index) => (
                <div
                  key={`${item.role}-${index}`}
                  className={item.role === "user" ? "ml-8 rounded-2xl rounded-br-md bg-primary p-3 text-sm text-primary-foreground" : "mr-8 rounded-2xl rounded-bl-md bg-secondary p-3 text-sm text-secondary-foreground"}
                >
                  {item.text}
                </div>
              )) : (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  Спросите, какую модель взять, сколько будет стоить задача или как построить промпт.
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Input
                value={message}
                placeholder="Например: хочу оживить портрет"
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    send();
                  }
                }}
              />
              <Button size="icon" disabled={!message.trim() || assistantBusy} onClick={send} aria-label="Отправить">
                {assistantBusy ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <Send />}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="mb-1 flex items-center gap-2 text-primary"><Camera className="size-5" /><span className="text-xs font-semibold uppercase tracking-wider">Vision</span></div>
            <CardTitle>Промпт по фото</CardTitle>
            <CardDescription>Файл отправляется multipart на backend. Spinner всегда снимается после успеха или ошибки.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                setSelectedFileName(file.name);
                onPhotoPrompt(file);
                event.target.value = "";
              }}
            />
            <button
              type="button"
              className="apix-focus-ring grid min-h-40 place-items-center rounded-2xl border border-dashed border-primary/35 bg-primary/6 p-5 text-center"
              onClick={() => inputRef.current?.click()}
            >
              <span>
                <Camera className="mx-auto mb-3 size-8 text-primary" />
                <span className="block font-semibold">{selectedFileName || "Выбрать изображение"}</span>
                <span className="mt-1 block text-xs text-muted-foreground">JPEG, PNG, WEBP, HEIC, HEIF или AVIF</span>
              </span>
            </button>
            {photoPromptBusy ? (
              <div className="flex items-center justify-center gap-2 rounded-xl bg-muted p-3 text-sm text-muted-foreground">
                <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" /> Анализируем изображение…
              </div>
            ) : null}
            {photoPromptResult?.prompt ? (
              <div className="grid gap-3 rounded-2xl border border-border bg-background/35 p-4">
                <Textarea value={photoPromptResult.prompt} readOnly className="min-h-36" />
                {photoPromptResult.model_hint ? <p className="text-xs text-muted-foreground">Рекомендация: {photoPromptResult.model_hint}</p> : null}
                <Button onClick={() => onUsePrompt(photoPromptResult.prompt)}>
                  <Sparkles /> Перейти к генерации фото
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export { ServicesScreen };
