import { useEffect, useMemo, useRef, useState } from "react";
import { Bot, Camera, Film, Headphones, ImageIcon, LifeBuoy, Music2, RefreshCw, Send, Sparkles, Upload, Users } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { findPinterestServiceTrend } from "@/features/pinterest-service";
import { openTrendRunner } from "@/features/trend-runner";
import { t } from "@/lib/i18n";
import { readTelegramInitData } from "@/lib/telegram";
import type { AppTab, AssistantMessage, PhotoPromptResult, TrendItem } from "@/lib/types";
import { formatKisses } from "@/lib/utils";

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

type MusicModel = { key: string; display_name: string; credits: number };
type SunoVoice = {
  id: number;
  name: string;
  status: string;
  style?: string | null;
  language?: string;
  validate_phrase?: string | null;
  provider_voice_id?: string | null;
  error?: string | null;
};

function miniappHeaders(json = true): HeadersInit {
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    "X-Telegram-Init-Data": readTelegramInitData(),
  };
}

async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      ...miniappHeaders(!(init.body instanceof FormData)),
      ...(init.headers || {}),
    },
  });
  if (!response.ok) {
    let message = `API ${response.status}`;
    try {
      const payload = await response.json();
      message = String(payload.detail || payload.message || payload.error?.message || message);
    } catch {
      // keep generic message
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
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
  const copy = t("ru").services;
  const [message, setMessage] = useState("");
  const [selectedFileName, setSelectedFileName] = useState("");
  const [pinterestTrend, setPinterestTrend] = useState<TrendItem>(() => findPinterestServiceTrend([]));
  const [pinterestLoading, setPinterestLoading] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    apiJson<TrendItem[]>("/trends?limit=32")
      .then((items) => {
        if (active) setPinterestTrend(findPinterestServiceTrend(Array.isArray(items) ? items : []));
      })
      .catch(() => {
        if (active) setPinterestTrend(findPinterestServiceTrend([]));
      })
      .finally(() => {
        if (active) setPinterestLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const send = () => {
    const value = message.trim();
    if (!value || assistantBusy) return;
    onAssistantSend(value);
    setMessage("");
  };

  const services = [
    { title: "Оживить", description: "Image-to-video", icon: Film, tab: "video" as AppTab },
    { title: "Изменить", description: "Edit-модели", icon: ImageIcon, tab: "photo" as AppTab },
    { title: "Музыка", description: "Suno генерация", icon: Music2, tab: "services" as AppTab },
    { title: "Avatar", description: "Фото и аудио", icon: Headphones, tab: "video" as AppTab },
    { title: "Партнёры", description: "Рефералы", icon: Users, tab: "profile" as AppTab },
    { title: "Помощь", description: "Task ID и ошибки", icon: LifeBuoy, tab: "profile" as AppTab },
    { title: "Pinterest", description: "Pinterest Flow со своей внешностью", icon: Sparkles, pinterest: true, badge: "Новинка" },
  ];

  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-between gap-2 px-0.5">
        <div>
          <div className="flex items-center gap-2"><h1 className="text-lg font-bold tracking-tight sm:text-xl">{copy.title}</h1><Badge variant="outline">AI</Badge></div>
          <details className="apix-help"><summary>{copy.whatHere}</summary><p className="pb-2">{copy.whatHereText}</p></details>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-7">
        {services.map(({ title, description, icon: Icon, tab, pinterest, badge }) => {
          const serviceTitle = pinterest
            ? (pinterestLoading ? "Pinterest Flow загружается — можно открыть уже сейчас" : description)
            : description;
          return (
            <button
              key={title}
              type="button"
              title={serviceTitle}
              className={`apix-focus-ring relative flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-xl border px-1 text-center active:scale-[0.97] ${pinterest ? "border-primary/40 bg-primary/10" : "border-border bg-card/70"}`}
              onClick={() => {
                if (pinterest) {
                  openTrendRunner(pinterestTrend);
                  return;
                }
                if (tab) onNavigate(tab);
              }}
            >
              {badge ? <span className="absolute right-1 top-1 rounded-full border border-primary/25 bg-primary/15 px-1.5 py-0.5 text-[6px] font-black uppercase tracking-wide text-primary">{badge}</span> : null}
              <span className={`grid size-8 place-items-center rounded-lg ${pinterest ? "bg-primary/20 text-primary" : "bg-primary/12 text-primary"}`}><Icon className="size-4" /></span>
              <span className="max-w-full truncate text-[9px] font-semibold leading-none">{title}</span>
            </button>
          );
        })}
      </div>

      <div className="grid gap-2.5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
        <section className="grid gap-2.5 lg:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-primary"><Bot className="size-4" /><CardTitle>{copy.assistant}</CardTitle></div>
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
                    {copy.assistantEmpty}
                  </div>
                )}
              </div>
              <div className="flex gap-1.5">
                <Input
                  value={message}
                  placeholder={copy.assistantPlaceholder}
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
              <div className="flex items-center gap-2 text-primary"><Camera className="size-4" /><CardTitle>{copy.photoPrompt}</CardTitle></div>
            </CardHeader>
            <CardContent className="grid gap-2">
              <input
                ref={inputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
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
                  <span className="block truncate text-sm font-semibold">{selectedFileName || copy.chooseImage}</span>
                  <span className="mt-0.5 block text-[10px] text-muted-foreground">JPEG, PNG, WEBP, GIF</span>
                </span>
              </button>
              {photoPromptBusy ? (
                <div className="flex items-center justify-center gap-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
                  <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" /> {copy.analyze}
                </div>
              ) : null}
              {photoPromptResult?.prompt ? (
                <div className="grid gap-2 rounded-xl border border-border bg-background/35 p-2.5">
                  <Textarea value={photoPromptResult.prompt} readOnly className="min-h-28" />
                  <div className="flex items-center justify-between gap-2">
                    {photoPromptResult.model_hint ? <p className="truncate text-[10px] text-muted-foreground">{photoPromptResult.model_hint}</p> : <span />}
                    <Button size="sm" onClick={() => onUsePrompt(photoPromptResult.prompt)}><Sparkles /> {copy.use}</Button>
                  </div>
                </div>
              ) : null}
              <details className="apix-help">
                <summary>Об обработке файла</summary>
                <p className="pb-2">Изображение отправляется multipart на backend; HEIC/AVIF убраны из выбора, потому что backend их не принимает.</p>
              </details>
            </CardContent>
          </Card>
        </section>

        <MusicSunoPanel />
      </div>
    </div>
  );
}

function MusicSunoPanel() {
  const copy = t("ru").services;
  const [models, setModels] = useState<MusicModel[]>([]);
  const [voices, setVoices] = useState<SunoVoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [modelKey, setModelKey] = useState("");
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [style, setStyle] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const [voiceId, setVoiceId] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [voiceFile, setVoiceFile] = useState<File | null>(null);
  const voiceInputRef = useRef<HTMLInputElement>(null);

  const selectedModel = useMemo(() => models.find((model) => model.key === modelKey) || models[0], [modelKey, models]);
  const readyVoices = voices.filter((voice) => String(voice.status).toLowerCase() === "ready");

  const refresh = async () => {
    setLoading(true);
    try {
      const [modelRows, voiceRows] = await Promise.all([
        apiJson<MusicModel[]>("/models/music"),
        apiJson<SunoVoice[]>("/music/voices"),
      ]);
      setModels(Array.isArray(modelRows) ? modelRows : []);
      setVoices(Array.isArray(voiceRows) ? voiceRows : []);
      if (!modelKey && modelRows[0]?.key) setModelKey(modelRows[0].key);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить музыку/Suno");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const createMusic = async () => {
    const text = prompt.trim();
    if (!text || busy) return toast.error("Нужен промпт для музыки");
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        prompt: text,
        instrumental,
        model: selectedModel?.key,
        title: title.trim() || undefined,
        style: style.trim() || undefined,
        voice_record_id: voiceId ? Number(voiceId) : undefined,
      };
      await apiJson("/generate/music", { method: "POST", body: JSON.stringify(payload) });
      toast.success("Музыкальная задача создана");
      setPrompt("");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось создать музыку");
    } finally {
      setBusy(false);
    }
  };

  const createVoice = async () => {
    if (!voiceFile) return toast.error("Выбери аудио для голоса");
    if (!voiceName.trim()) return toast.error("Укажи название голоса");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", voiceFile);
      form.append("name", voiceName.trim());
      if (style.trim()) form.append("style", style.trim());
      form.append("language", "ru");
      await apiJson("/music/voices", { method: "POST", body: form });
      toast.success("Голос отправлен на подготовку");
      setVoiceFile(null);
      setVoiceName("");
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось создать голос");
    } finally {
      setBusy(false);
    }
  };

  const refreshVoice = async (id: number) => {
    setBusy(true);
    try {
      await apiJson(`/music/voices/${id}/refresh`, { method: "POST", body: "{}" });
      await refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить голос");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="min-w-0">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-primary"><Music2 className="size-4" /><CardTitle>{copy.musicTitle}</CardTitle></div>
          <Button variant="ghost" size="sm" disabled={loading} onClick={() => void refresh()}><RefreshCw className="size-4" /> {copy.refreshVoices}</Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <section className="grid gap-2 rounded-xl border border-border bg-card/45 p-2.5">
          <div className="grid gap-2 min-[520px]:grid-cols-2">
            <label className="grid gap-1 text-xs font-medium">
              Модель
              <Select value={selectedModel?.key || ""} onChange={(event) => setModelKey(event.target.value)}>
                {models.map((model) => <option key={model.key} value={model.key}>{model.display_name} · {formatKisses(model.credits)}</option>)}
              </Select>
            </label>
            <label className="grid gap-1 text-xs font-medium">
              Голос
              <Select value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>
                <option value="">Без кастомного голоса</option>
                {readyVoices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}
              </Select>
            </label>
          </div>
          <Textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={copy.musicPrompt} className="min-h-24" />
          <div className="grid gap-2 min-[520px]:grid-cols-2">
            <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={copy.trackTitle} />
            <Input value={style} onChange={(event) => setStyle(event.target.value)} placeholder={copy.style} />
          </div>
          <label className="flex items-center gap-2 rounded-xl border border-border bg-background/45 px-3 py-2 text-xs">
            <input type="checkbox" checked={instrumental} onChange={(event) => setInstrumental(event.target.checked)} />
            {copy.instrumental}
          </label>
          <Button disabled={busy || !prompt.trim()} onClick={() => void createMusic()}><Music2 className="size-4" /> {busy ? "Создаём…" : copy.createMusic}</Button>
        </section>

        <section className="grid gap-2 rounded-xl border border-border bg-card/45 p-2.5">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">{copy.voices}</h3>
            <Badge variant="outline">{voices.length}</Badge>
          </div>
          <input
            ref={voiceInputRef}
            type="file"
            accept="audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/aac,audio/flac,audio/ogg"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              setVoiceFile(file);
              event.target.value = "";
            }}
          />
          <div className="grid gap-2 min-[520px]:grid-cols-[minmax(0,1fr)_auto]">
            <Input value={voiceName} onChange={(event) => setVoiceName(event.target.value)} placeholder={copy.voiceName} />
            <Button variant="outline" onClick={() => voiceInputRef.current?.click()}><Upload className="size-4" /> {voiceFile?.name || copy.chooseAudio}</Button>
          </div>
          <Button variant="secondary" disabled={busy || !voiceFile || !voiceName.trim()} onClick={() => void createVoice()}>{copy.createVoice}</Button>
          <div className="grid gap-1.5">
            {voices.map((voice) => (
              <div key={voice.id} className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-border bg-background/45 px-2 py-1.5 text-xs">
                <div className="min-w-0">
                  <p className="truncate font-semibold">{voice.name}</p>
                  <p className="truncate text-[10px] text-muted-foreground">{voice.status}{voice.validate_phrase ? ` · ${voice.validate_phrase}` : ""}{voice.error ? ` · ${voice.error}` : ""}</p>
                </div>
                <Button variant="ghost" size="sm" disabled={busy} onClick={() => void refreshVoice(voice.id)}>Refresh</Button>
              </div>
            ))}
            {!voices.length ? <p className="text-xs text-muted-foreground">Голоса пока не созданы.</p> : null}
          </div>
        </section>
      </CardContent>
    </Card>
  );
}

export { ServicesScreen };
