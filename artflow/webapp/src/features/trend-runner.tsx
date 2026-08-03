import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Copy, Film, ImageIcon, LoaderCircle, UploadCloud, X } from "lucide-react";
import { toast } from "sonner";

import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { GenerationTask, TrendItem } from "@/lib/types";
import { notifyHaptic, readStartParam } from "@/lib/telegram";
import { safeExternalUrl } from "@/lib/utils";

const TREND_RUNNER_EVENT = "apix:open-trend-runner";
const API_BASE = "/api/v1";
const ACCEPTED_TREND_PHOTO_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/heic",
  "image/heif",
  "image/avif",
].join(",");
const ACCEPTED_TREND_PHOTO_EXTENSIONS = ".jpg,.jpeg,.png,.webp,.heic,.heif,.avif";

type RunnerPhase = "idle" | "uploading" | "generating" | "error";
type TrendPublic = TrendItem & {
  user_photo_hint?: string | null;
  model_label?: string | null;
  status?: string;
};

type TrendUploadResponse = {
  asset_id: string;
  url: string;
  kind: "image";
  filename?: string;
  content_type?: string;
  size?: number;
};

type TrendRunResponse = {
  ok?: boolean;
  task: GenerationTask;
  credits?: number;
};

type TrendRunnerEventDetail = {
  trend?: TrendPublic;
  trendId?: number;
};

function initDataHeader(): string {
  try {
    return window.Telegram?.WebApp?.initData || window.sessionStorage.getItem("apix:telegram-init-data:v2") || "";
  } catch {
    return window.Telegram?.WebApp?.initData || "";
  }
}

async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const body = init.body;
  const isForm = body instanceof FormData;
  const response = await fetch(path.startsWith("/api/") ? path : `${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      "X-Telegram-Init-Data": initDataHeader(),
      ...(init.headers || {}),
    },
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

function buildIdempotencyKey(trendId: number): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `trend-${trendId}-${crypto.randomUUID()}`;
  }
  return `trend-${trendId}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function parseTrendStartParam(): number | null {
  const raw = readStartParam();
  const match = /^trend_(\d+)$/i.exec(raw);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function openTrendRunner(trend: TrendPublic): void {
  window.dispatchEvent(new CustomEvent<TrendRunnerEventDetail>(TREND_RUNNER_EVENT, { detail: { trend } }));
}

function openTrendRunnerById(trendId: number): void {
  window.dispatchEvent(new CustomEvent<TrendRunnerEventDetail>(TREND_RUNNER_EVENT, { detail: { trendId } }));
}

function TrendRunnerPortal() {
  const [trend, setTrend] = useState<TrendPublic | null>(null);
  const [phase, setPhase] = useState<RunnerPhase>("idle");
  const [error, setError] = useState("");
  const [localPreview, setLocalPreview] = useState("");
  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const processedStart = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const busy = phase === "uploading" || phase === "generating";
  const preview = safeExternalUrl(trend?.preview_url || "");
  const isVideoPreview = trend?.kind === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(preview);
  const hint = trend?.user_photo_hint || "Загрузите одно чёткое фото. Остальные параметры тренда уже настроены администратором.";

  const resetRunner = useCallback(() => {
    setPhase("idle");
    setError("");
    setLocalPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
  }, []);

  const closeRunner = useCallback(() => {
    if (busy) return;
    resetRunner();
    setTrend(null);
  }, [busy, resetRunner]);

  const loadTrend = useCallback(async (trendId: number) => {
    try {
      const payload = await apiJson<TrendPublic>(`/trends/${trendId}`);
      resetRunner();
      setTrend(payload);
    } catch (loadError) {
      toast.error(loadError instanceof Error ? loadError.message : "Не удалось открыть тренд");
    }
  }, [resetRunner]);

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<TrendRunnerEventDetail>).detail || {};
      if (detail.trend) {
        resetRunner();
        setTrend(detail.trend);
      } else if (detail.trendId) {
        void loadTrend(detail.trendId);
      }
    };
    window.addEventListener(TREND_RUNNER_EVENT, onOpen);
    return () => window.removeEventListener(TREND_RUNNER_EVENT, onOpen);
  }, [loadTrend, resetRunner]);

  useEffect(() => {
    const trendId = parseTrendStartParam();
    if (!trendId || processedStart.current === trendId) return;
    processedStart.current = trendId;
    void loadTrend(trendId);
  }, [loadTrend]);

  useEffect(() => () => {
    setLocalPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
  }, []);

  const runPhoto = useCallback(async (file: File | undefined | null) => {
    if (!trend || !file || busy) return;
    setError("");
    setLocalPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(file);
    });
    try {
      setPhase("uploading");
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiJson<TrendUploadResponse>("/trends/upload", { method: "POST", body: form });
      if (!uploaded.asset_id) throw new Error("Backend не вернул asset_id");

      setPhase("generating");
      const result = await apiJson<TrendRunResponse>(`/trends/${trend.id}/run`, {
        method: "POST",
        body: JSON.stringify({ asset_id: uploaded.asset_id, idempotency_key: buildIdempotencyKey(trend.id) }),
      });
      if (!result.task?.id) throw new Error("Backend не вернул задачу");
      setSelectedTask(result.task);
      setTaskOpen(true);
      notifyHaptic("success");
      toast.success("Тренд запущен");
      setTrend(null);
      resetRunner();
    } catch (runError) {
      notifyHaptic("error");
      const message = runError instanceof Error ? runError.message : "Не удалось запустить тренд";
      setError(message);
      setPhase("error");
      toast.error(message);
    }
  }, [busy, resetRunner, trend]);

  const refreshTask = useCallback(async (task: GenerationTask) => {
    if (taskBusy) return;
    setTaskBusy(true);
    try {
      const updated = await apiJson<GenerationTask>(`/generations/${task.id}`);
      setSelectedTask(updated);
    } catch (refreshError) {
      toast.error(refreshError instanceof Error ? refreshError.message : "Не удалось обновить задачу");
    } finally {
      setTaskBusy(false);
    }
  }, [taskBusy]);

  const toggleTaskShare = useCallback(async (task: GenerationTask) => {
    if (taskBusy) return;
    setTaskBusy(true);
    try {
      if (task.is_public_feed) {
        await apiJson(`/feed/${task.id}/remove`, { method: "POST", body: "{}" });
        setSelectedTask({ ...task, is_public_feed: false });
        toast.success("Публикация убрана из ленты");
      } else {
        await apiJson(`/api/web/feed/generations/${task.id}/publish`, { method: "POST", body: "{}" });
        setSelectedTask({ ...task, is_public_feed: true });
        toast.success("Работа опубликована");
      }
    } catch (shareError) {
      toast.error(shareError instanceof Error ? shareError.message : "Не удалось изменить публикацию");
    } finally {
      setTaskBusy(false);
    }
  }, [taskBusy]);

  const toggleTaskLibrary = useCallback(async (task: GenerationTask) => {
    if (taskBusy) return;
    setTaskBusy(true);
    try {
      if (task.is_prompt_library) {
        await apiJson(`/generations/${task.id}/remove-library`, { method: "POST", body: "{}" });
      } else {
        await apiJson(`/generations/${task.id}/share-library`, { method: "POST", body: "{}" });
      }
      setSelectedTask({ ...task, is_prompt_library: !task.is_prompt_library });
    } catch (libraryError) {
      toast.error(libraryError instanceof Error ? libraryError.message : "Не удалось изменить библиотеку");
    } finally {
      setTaskBusy(false);
    }
  }, [taskBusy]);

  const phaseLabel = useMemo(() => {
    if (phase === "uploading") return "Загружаем фото…";
    if (phase === "generating") return "Запускаем генерацию…";
    if (phase === "error") return "Можно выбрать фото ещё раз";
    return "Выберите фото — запуск начнётся автоматически";
  }, [phase]);

  return (
    <>
      <Sheet
        open={Boolean(trend)}
        title={trend?.title || "Повторить тренд"}
        description="Один снимок. Без настроек. Всё остальное применит backend."
        onOpenChange={(open) => {
          if (!open) closeRunner();
        }}
      >
        {trend ? (
          <div className="grid gap-3">
            <div className="overflow-hidden rounded-xl border border-border bg-muted">
              {preview ? (
                isVideoPreview ? (
                  <video src={preview} muted playsInline preload="metadata" controls className="max-h-[42dvh] w-full object-cover" />
                ) : (
                  <img src={preview} alt="Превью тренда" className="max-h-[42dvh] w-full object-cover" />
                )
              ) : (
                <div className="grid min-h-40 place-items-center text-muted-foreground">
                  {trend.kind === "video" ? <Film /> : <ImageIcon />}
                </div>
              )}
            </div>

            <div className="rounded-xl border border-border bg-card/60 p-3 text-sm text-muted-foreground">
              {trend.description ? <p className="mb-2 text-foreground">{trend.description}</p> : null}
              <p>{hint}</p>
            </div>

            {localPreview ? (
              <div className="overflow-hidden rounded-xl border border-primary/30 bg-primary/10">
                <img src={localPreview} alt="Ваше фото" className="max-h-56 w-full object-contain" />
              </div>
            ) : null}

            <input
              ref={fileInputRef}
              type="file"
              accept={`${ACCEPTED_TREND_PHOTO_TYPES},${ACCEPTED_TREND_PHOTO_EXTENSIONS}`}
              className="sr-only"
              disabled={busy}
              onChange={(event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                void runPhoto(file);
              }}
            />

            <Button disabled={busy} className="min-h-12 w-full" onClick={() => fileInputRef.current?.click()}>
              {busy ? <LoaderCircle className="animate-spin" /> : <UploadCloud />}
              {phaseLabel}
            </Button>

            {error ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">{error}</div>
            ) : null}

            <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground">
              <X className="mt-0.5 size-3.5 shrink-0" />
              <p>В этом сценарии нельзя менять модель, промпт, формат, качество, duration, seed или provider-параметры. Они применяются только на backend.</p>
            </div>
          </div>
        ) : null}
      </Sheet>

      <TaskDetailSheet
        task={selectedTask}
        open={taskOpen}
        busy={taskBusy}
        onOpenChange={setTaskOpen}
        onRefresh={(task) => void refreshTask(task)}
        onShare={(task) => void toggleTaskShare(task)}
        onToggleLibrary={(task) => void toggleTaskLibrary(task)}
      />
    </>
  );
}

async function copyTrendLink(trend: TrendPublic): Promise<void> {
  const payload = await apiJson<{ link?: string }>(`/trends/${trend.id}/link`);
  const link = payload.link || "";
  if (!link) throw new Error("Ссылка недоступна");
  await navigator.clipboard.writeText(link);
}

export { TrendRunnerPortal, copyTrendLink, openTrendRunner, openTrendRunnerById };
