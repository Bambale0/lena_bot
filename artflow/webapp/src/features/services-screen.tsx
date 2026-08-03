import { useRef, useState } from "react";
import { Bot, Camera, Film, Headphones, ImageIcon, LifeBuoy, Send, Sparkles, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
    { title: "Оживить", description: "Image-to-video", icon: Film, tab: "video" as AppTab },
    { title: "Изменить", description: "Edit-модели", icon: ImageIcon, tab: "photo" as AppTab },
    { title: "Avatar", description: "Фото и аудио", icon: Headphones, tab: "video" as AppTab },
    { title: "Партнёры", description: "Рефералы", icon: Users, tab: "profile" as AppTab },
    { title: "Помощь", description: "Task ID и ошибки", icon: LifeBuoy, tab: "profile" as AppTab },
  ];

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-2 px-0.5">
        <div>
          <div className="flex items-center gap-2"><h1 className="text-lg font-bold tracking-tight sm:text-xl">Сервисы</h1><Badge variant="outline">AI</Badge></div>
          <details className="apix-help"><summary>Что здесь есть</summary><p className="pb-2">Помощник, анализ фото и быстрые переходы в готовые сценарии.</p></details>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-1.5">
        {services.map(({ title, description, icon: Icon, tab }) => (
          <button
            key={title}
            type="button"
            title={description}
            className="apix-focus-ring flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card/70 px-1 text-center active:scale-[0.97]"
            onClick={() => onNavigate(tab)}
          >
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary"><Icon className="size-4" /></span>
            <span className="text-[9px] font-semibold leading-none">{title}</span>
          </button>
        ))}
      </div>

      <div className="grid gap-2.5 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-primary"><Bot className="size-4" /><CardTitle>AI-помощник</CardTitle></div>
              <Badge variant="secondary">{messages.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="grid gap-2">
            <div className="max-h-[46dvh] min-h-28 space-y-1.5 overflow-y-auto rounded-lg border border-border bg-background/35 p-2">
              {messages.length ? messages.map((item, index) => (
                <div
                  key={`${item.role}-${index}`}
                  className={item.role === "user" ? "ml-7 rounded-xl rounded-br-sm bg-primary px-2.5 py-2 text-xs text-primary-foreground" : "mr-7 rounded-xl rounded-bl-sm bg-secondary px-2.5 py-2 text-xs text-secondary-foreground"}
                >
                  {item.text}
                </div>
              )) : (
                <div className="grid min-h-24 place-items-center px-3 text-center text-xs text-muted-foreground">
                  Спросите про модель, стоимость или промпт.
                </div>
              )}
            </div>
            <div className="flex gap-1.5">
              <Input
                value={message}
                placeholder="Что хотите создать?"
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
            <details className="apix-help">
              <summary>Как работает помощник</summary>
              <p className="pb-2">Он использует текущий registry моделей и последние сообщения диалога.</p>
            </details>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2 text-primary"><Camera className="size-4" /><CardTitle>Промпт по фото</CardTitle></div>
          </CardHeader>
          <CardContent className="grid gap-2">
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
              className="apix-focus-ring flex min-h-24 items-center justify-center gap-3 rounded-xl border border-dashed border-primary/35 bg-primary/6 px-3 py-3 text-left"
              onClick={() => inputRef.current?.click()}
            >
              <Camera className="size-6 shrink-0 text-primary" />
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{selectedFileName || "Выбрать изображение"}</span>
                <span className="mt-0.5 block text-[10px] text-muted-foreground">JPEG, PNG, WEBP, HEIC, HEIF, AVIF</span>
              </span>
            </button>
            {photoPromptBusy ? (
              <div className="flex items-center justify-center gap-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
                <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" /> Анализируем…
              </div>
            ) : null}
            {photoPromptResult?.prompt ? (
              <div className="grid gap-2 rounded-xl border border-border bg-background/35 p-2.5">
                <Textarea value={photoPromptResult.prompt} readOnly className="min-h-28" />
                <div className="flex items-center justify-between gap-2">
                  {photoPromptResult.model_hint ? <p className="truncate text-[10px] text-muted-foreground">{photoPromptResult.model_hint}</p> : <span />}
                  <Button size="sm" onClick={() => onUsePrompt(photoPromptResult.prompt)}><Sparkles /> Использовать</Button>
                </div>
              </div>
            ) : null}
            <details className="apix-help">
              <summary>Об обработке файла</summary>
              <p className="pb-2">Изображение отправляется multipart на backend; состояние загрузки снимается после ответа или ошибки.</p>
            </details>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export { ServicesScreen };
