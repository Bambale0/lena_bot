import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Film, ImageIcon, LoaderCircle, Repeat2, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { FeedItem, GenerationTask, ModelInfo } from "@/lib/types";
import { notifyHaptic } from "@/lib/telegram";
import { cn, firstMedia, safeExternalUrl } from "@/lib/utils";

const FEED_REMIX_EVENT = "apix:open-feed-remix-runner";
const RUNNER_ROOT_ID = "apix-feed-remix-runner-root";
const API_BASE = "/api/v1";
const ACCEPTED_REFERENCE_IMAGES = "image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif";
const ACCEPTED_REFERENCE_EXTENSIONS = ".jpg,.jpeg,.png,.webp,.heic,.heif,.avif";

type ModelBucket = "image" | "video";
type RunnerPhase = "idle" | "uploading" | "generating" | "error";
type FeedRemixEventDetail = { item: FeedItem };
type PendingRemix = { resolve: (task: GenerationTask) => void; reject: (error: Error) => void };

type UploadResponse = { url?: string; content_type?: string; size?: number };

let runnerRoot: Root | null = null;
let runnerMounted = false;
let pendingRemix: PendingRemix | null = null;

function ensureFeedRemixRunnerPortal(): void {
  if (typeof document === "undefined" || runnerMounted) return;
  let host = document.getElementById(RUNNER_ROOT_ID);
  if (!host) {
    host = document.createElement("div");
    host.id = RUNNER_ROOT_ID;
    document.body.appendChild(host);
  }
  runnerRoot = runnerRoot || createRoot(host);
  runnerRoot.render(<FeedRemixRunnerPortal />);
  runnerMounted = true;
}

function initDataHeader(): string {
  try {
    return window.Telegram?.WebApp?.initData || window.sessionStorage.getItem("apix:telegram-init-data:v2") || "";
  } catch {
    return window.Telegram?.WebApp?.initData || "";
  }
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const initData = initDataHeader();
  return { ...(initData ? { "X-Telegram-Init-Data": initData } : {}), ...extra };
}

async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const body = init.body;
  const isForm = body instanceof FormData;
  const response = await fetch(path.startsWith("/api/") ? path : `${API_BASE}${path}`, {
    ...init,
    headers: authHeaders({
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...((init.headers || {}) as Record<string, string>),
    }),
  });
  if (!response.ok) {
    let message = `Ошибка API ${response.status}`;
    try {
      const payload = await response.json();
      message = String(payload?.error?.message || payload?.detail || payload?.message || message);
    } catch {
      // Keep fallback message.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json();
  return (payload?.data || payload) as T;
}

async function uploadReferenceImage(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/web/upload-media", {
    method: "POST",
    body: form,
    headers: authHeaders(),
  });
  if (!response.ok) {
    let message = `Ошибка API ${response.status}`;
    try {
      const payload = await response.json();
      message = String(payload?.error?.message || payload?.detail || payload?.message || message);
    } catch {
      // Keep fallback message.
    }
    throw new Error(message);
  }
  const payload = await response.json();
  return (payload?.data || payload) as UploadResponse;
}

function openFeedRemixRunner(item: FeedItem): Promise<GenerationTask> {
  ensureFeedRemixRunnerPortal();
  if (pendingRemix) pendingRemix.reject(new Error("Открыт новый повтор"));
  return new Promise<GenerationTask>((resolve, reject) => {
    pendingRemix = { resolve, reject };
    window.dispatchEvent(new CustomEvent<FeedRemixEventDetail>(FEED_REMIX_EVENT, { detail: { item } }));
  });
}

function modelDurations(model?: ModelInfo): number[] {
  if (model?.duration_options?.length) return model.duration_options;
  if (model?.durations?.length) return model.durations;
  return [5, 10];
}

function modelResolutions(model?: ModelInfo): string[] {
  if (model?.resolution_options?.length) return model.resolution_options;
  if (model?.resolutions?.length) return model.resolutions;
  return ["720p", "1080p"];
}

function modelAspectRatios(model?: ModelInfo): string[] {
  return model?.aspect_ratios?.length ? model.aspect_ratios : ["1:1", "4:5", "9:16", "16:9"];
}

function selectedModelBucket(modelKey: string, videoModels: ModelInfo[]): ModelBucket {
  return videoModels.some((model) => model.key === modelKey) ? "video" : "image";
}

function mediaLooksVideo(url: string | null | undefined): boolean {
  return /\.(mp4|webm|mov|m4v)(\?|$)/i.test(String(url || ""));
}

function itemLooksVideo(item: FeedItem): boolean {
  return item.gen_type === "video" || mediaLooksVideo(firstMedia(item));
}

function FeedRemixRunnerPortal() {
  const [item, setItem] = useState<FeedItem | null>(null);
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [videoModels, setVideoModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [phase, setPhase] = useState<RunnerPhase>("idle");
  const [error, setError] = useState("");
  const [modelKey, setModelKey] = useState("");
  const [mode, setMode] = useState("image");
  const [aspectRatio, setAspectRatio] = useState("1:1");
  const [quality, setQuality] = useState("basic");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(5);
  const [resolution, setResolution] = useState("720p");
  const [grokMode, setGrokMode] = useState("normal");
  const [references, setReferences] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const allModels = useMemo(() => [...imageModels, ...videoModels], [imageModels, videoModels]);
  const selectedModel = useMemo(() => allModels.find((model) => model.key === modelKey), [allModels, modelKey]);
  const bucket = selectedModelBucket(modelKey, videoModels);
  const busy = phase === "uploading" || phase === "generating" || modelsLoading;
  const sourcePreview = safeExternalUrl(firstMedia(item || {}));
  const sourceIsVideo = item ? itemLooksVideo(item) : false;
  const aspectRatios = modelAspectRatios(selectedModel);
  const durations = modelDurations(selectedModel);
  const resolutions = modelResolutions(selectedModel);
  const modeOptions = selectedModel?.modes?.length ? selectedModel.modes : [bucket === "video" ? "image" : "image"];
  const qualityOptions = selectedModel?.quality_options?.length ? selectedModel.quality_options : [{ value: "basic", label: "Базовое" }];
  const countOptions = selectedModel?.counts?.length ? selectedModel.counts : [1];

  const resetForm = useCallback((nextItem: FeedItem | null = null) => {
    setItem(nextItem);
    setPhase("idle");
    setError("");
    setReferences([]);
    setModelKey(nextItem?.model || "");
    setMode(nextItem && itemLooksVideo(nextItem) ? "text" : "image");
    setAspectRatio(nextItem?.aspect_ratio || "1:1");
    setQuality("basic");
    setCount(1);
    setDuration(5);
    setResolution("720p");
    setGrokMode("normal");
  }, []);

  const cancelPending = useCallback((message = "Повтор отменён") => {
    if (pendingRemix) pendingRemix.reject(new Error(message));
    pendingRemix = null;
  }, []);

  const loadModels = useCallback(async () => {
    if (modelsLoading || (imageModels.length && videoModels.length)) return;
    setModelsLoading(true);
    try {
      const [images, videos] = await Promise.all([apiJson<ModelInfo[]>("/models/image"), apiJson<ModelInfo[]>("/models/video")]);
      setImageModels(Array.isArray(images) ? images : []);
      setVideoModels(Array.isArray(videos) ? videos : []);
    } catch (loadError) {
      toast.error(loadError instanceof Error ? loadError.message : "Не удалось загрузить модели");
    } finally {
      setModelsLoading(false);
    }
  }, [imageModels.length, modelsLoading, videoModels.length]);

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<FeedRemixEventDetail>).detail;
      if (!detail?.item) return;
      resetForm(detail.item);
      void loadModels();
    };
    window.addEventListener(FEED_REMIX_EVENT, onOpen);
    return () => window.removeEventListener(FEED_REMIX_EVENT, onOpen);
  }, [loadModels, resetForm]);

  useEffect(() => {
    if (!item || !allModels.length) return;
    if (modelKey && allModels.some((model) => model.key === modelKey)) return;
    const fallback = allModels.find((model) => model.key === item.model) || imageModels[0] || videoModels[0];
    if (fallback) setModelKey(fallback.key);
  }, [allModels, imageModels, item, modelKey, videoModels]);

  useEffect(() => {
    if (!selectedModel) return;
    const nextRatios = modelAspectRatios(selectedModel);
    if (!nextRatios.includes(aspectRatio)) setAspectRatio(nextRatios[0] || "1:1");
    const nextDurations = modelDurations(selectedModel);
    if (!nextDurations.includes(duration)) setDuration(nextDurations[0] || 5);
    const nextResolutions = modelResolutions(selectedModel);
    if (!nextResolutions.includes(resolution)) setResolution(nextResolutions[0] || "720p");
    const nextQuality = selectedModel.quality_options?.map((option) => option.value) || ["basic"];
    if (!nextQuality.includes(quality)) setQuality(nextQuality[0] || "basic");
    const nextCounts = selectedModel.counts || [1];
    if (!nextCounts.includes(count)) setCount(nextCounts[0] || 1);
    if (!modeOptions.includes(mode)) setMode(modeOptions[0] || "image");
  }, [aspectRatio, count, duration, mode, modeOptions, quality, resolution, selectedModel]);

  const close = useCallback(() => {
    if (busy) return;
    cancelPending();
    resetForm(null);
  }, [busy, cancelPending, resetForm]);

  const addReferenceFiles = useCallback(async (files: File[]) => {
    if (!files.length || busy) return;
    setPhase("uploading");
    setError("");
    try {
      const uploaded: string[] = [];
      for (const file of files) {
        const result = await uploadReferenceImage(file);
        if (result.url) uploaded.push(result.url);
      }
      if (!uploaded.length) throw new Error("Backend не вернул ссылки на референсы");
      setReferences((current) => Array.from(new Set([...current, ...uploaded])));
      notifyHaptic("success");
      toast.success(uploaded.length === 1 ? "Референс добавлен" : `Добавлено референсов: ${uploaded.length}`);
      setPhase("idle");
    } catch (uploadError) {
      notifyHaptic("error");
      const message = uploadError instanceof Error ? uploadError.message : "Не удалось загрузить референс";
      setError(message);
      setPhase("error");
      toast.error(message);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [busy]);

  const submit = useCallback(async () => {
    if (!item || !selectedModel || busy) return;
    setPhase("generating");
    setError("");
    try {
      const isVideoModel = bucket === "video";
      const sourceMedia = sourcePreview || "";
      const primaryUserReference = references[0] || "";
      const task = await apiJson<GenerationTask>(`/feed/${item.id}/remix`, {
        method: "POST",
        body: JSON.stringify({
          model: selectedModel.key,
          mode: isVideoModel ? mode : "image",
          duration,
          aspect_ratio: aspectRatio,
          resolution,
          image_url: primaryUserReference || (!sourceIsVideo ? sourceMedia || null : null),
          source_image_url: !sourceIsVideo ? sourceMedia || null : null,
          reference_urls: references,
          video_url: sourceIsVideo ? sourceMedia || null : null,
          video_start: 0,
          video_end: null,
          audio_ids: [],
          character_ids: [],
          seed: null,
          grok_mode: grokMode,
          quality,
          count,
        }),
      });
      pendingRemix?.resolve(task);
      pendingRemix = null;
      notifyHaptic("success");
      toast.success("Повтор запущен");
      resetForm(null);
    } catch (runError) {
      notifyHaptic("error");
      const message = runError instanceof Error ? runError.message : "Не удалось запустить повтор";
      setError(message);
      setPhase("error");
      toast.error(message);
    }
  }, [aspectRatio, bucket, busy, count, duration, grokMode, item, mode, quality, references, resetForm, resolution, selectedModel, sourceIsVideo, sourcePreview]);

  const phaseLabel = useMemo(() => {
    if (phase === "uploading") return "Загружаем референсы…";
    if (phase === "generating") return "Запускаем повтор…";
    if (phase === "error") return "Проверь настройки и попробуй ещё раз";
    return "Настройте повтор и нажмите «Запустить»";
  }, [phase]);

  return (
    <Sheet
      open={Boolean(item)}
      title="Повторить работу"
      description="Скрытый промпт останется на backend. Вы выбираете референсы, модель и параметры."
      onOpenChange={(open) => {
        if (!open) close();
      }}
      footer={
        <div className="grid gap-2">
          {error ? <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p> : null}
          <Button className="min-h-11 rounded-xl" disabled={busy || !selectedModel} onClick={() => void submit()}>
            {phase === "generating" ? <LoaderCircle className="size-4 animate-spin" /> : <Repeat2 className="size-4" />}
            {phase === "generating" ? "Запуск…" : "Запустить повтор"}
          </Button>
        </div>
      }
    >
      {item ? (
        <div className="grid gap-3 text-sm">
          <div className="grid grid-cols-[88px_1fr] gap-3 rounded-xl border border-border bg-card/65 p-2">
            <div className="overflow-hidden rounded-lg bg-muted">
              {sourcePreview ? (
                sourceIsVideo ? (
                  <video src={sourcePreview} muted playsInline preload="metadata" className="aspect-square size-full object-cover" />
                ) : (
                  <img src={sourcePreview} alt="" className="aspect-square size-full object-cover" />
                )
              ) : (
                <div className="grid aspect-square place-items-center text-muted-foreground">{sourceIsVideo ? <Film /> : <ImageIcon />}</div>
              )}
            </div>
            <div className="min-w-0 self-center">
              <p className="truncate font-semibold">{item.author || "Автор"}</p>
              <p className="truncate text-xs text-muted-foreground">{item.model}</p>
              <p className="mt-1 text-xs text-muted-foreground">Исходная работа будет использована как основной референс.</p>
            </div>
          </div>

          <div className="grid gap-2 rounded-xl border border-border bg-card/60 p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="font-semibold">Референсы</p>
                <p className="text-xs text-muted-foreground">Можно добавить свои фото поверх исходной работы.</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={`${ACCEPTED_REFERENCE_IMAGES},${ACCEPTED_REFERENCE_EXTENSIONS}`}
                multiple
                onChange={(event) => void addReferenceFiles(Array.from(event.target.files || []))}
              />
              <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => fileInputRef.current?.click()}>
                {phase === "uploading" ? <LoaderCircle className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
                Добавить
              </Button>
            </div>
            {references.length ? (
              <div className="flex flex-wrap gap-1.5">
                {references.map((url, index) => (
                  <span key={url} className="inline-flex max-w-full items-center gap-1 rounded-full bg-muted px-2 py-1 text-xs">
                    <span className="truncate">Реф #{index + 1}</span>
                    <button type="button" className="text-muted-foreground" onClick={() => setReferences((current) => current.filter((itemUrl) => itemUrl !== url))} aria-label="Удалить референс">
                      <X className="size-3" />
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          <label className="grid gap-1 text-xs font-semibold">
            Модель
            <select className="min-h-11 rounded-xl border border-input bg-background px-3 text-sm" value={modelKey} onChange={(event) => setModelKey(event.target.value)} disabled={busy || modelsLoading}>
              {modelsLoading ? <option>Загружаем модели…</option> : null}
              {imageModels.length ? <optgroup label="Фото">{imageModels.map((model) => <option key={model.key} value={model.key}>{model.display_name}</option>)}</optgroup> : null}
              {videoModels.length ? <optgroup label="Видео">{videoModels.map((model) => <option key={model.key} value={model.key}>{model.display_name}</option>)}</optgroup> : null}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="grid gap-1 text-xs font-semibold">
              Формат
              <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value)} disabled={busy}>
                {aspectRatios.map((ratio) => <option key={ratio} value={ratio}>{ratio}</option>)}
              </select>
            </label>

            {bucket === "image" ? (
              <label className="grid gap-1 text-xs font-semibold">
                Качество
                <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={quality} onChange={(event) => setQuality(event.target.value)} disabled={busy}>
                  {qualityOptions.map((option) => <option key={option.value} value={option.value}>{option.label || option.value}</option>)}
                </select>
              </label>
            ) : (
              <label className="grid gap-1 text-xs font-semibold">
                Режим
                <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={mode} onChange={(event) => setMode(event.target.value)} disabled={busy}>
                  {modeOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
            )}
          </div>

          {bucket === "image" ? (
            <label className="grid gap-1 text-xs font-semibold">
              Количество вариантов
              <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={count} onChange={(event) => setCount(Number(event.target.value) || 1)} disabled={busy}>
                {countOptions.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1 text-xs font-semibold">
                Длительность
                <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={duration} onChange={(event) => setDuration(Number(event.target.value) || 5)} disabled={busy}>
                  {durations.map((value) => <option key={value} value={value}>{value} сек</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs font-semibold">
                Разрешение
                <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={resolution} onChange={(event) => setResolution(event.target.value)} disabled={busy}>
                  {resolutions.map((value) => <option key={value} value={value}>{value}</option>)}
                </select>
              </label>
            </div>
          )}

          {selectedModel?.mode_options?.length ? (
            <label className="grid gap-1 text-xs font-semibold">
              Motion / вариант
              <select className="min-h-10 rounded-xl border border-input bg-background px-3 text-sm" value={grokMode} onChange={(event) => setGrokMode(event.target.value)} disabled={busy}>
                {selectedModel.mode_options.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
            </label>
          ) : null}

          <p className={cn("rounded-xl border border-border bg-muted/45 px-3 py-2 text-xs text-muted-foreground", phase !== "idle" && "text-foreground")}>{phaseLabel}</p>
        </div>
      ) : null}
    </Sheet>
  );
}

ensureFeedRemixRunnerPortal();

export { openFeedRemixRunner };
