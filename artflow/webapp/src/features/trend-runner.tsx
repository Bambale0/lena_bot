import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Film, ImageIcon, ImagePlus, LoaderCircle, Plus, Ruler, Weight, X } from "lucide-react";
import { toast } from "sonner";

import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { isPinterestServiceTrend } from "@/features/pinterest-service";
import type { GenerationTask, TrendItem } from "@/lib/types";
import { notifyHaptic, readStartParam } from "@/lib/telegram";
import { safeExternalUrl } from "@/lib/utils";

const TREND_RUNNER_EVENT = "apix:open-trend-runner";
const API_BASE = "/api/v1";
const RUNNER_ROOT_ID = "apix-trend-runner-root";
const ACCEPTED_TREND_PHOTOS = "image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif,.jpg,.jpeg,.png,.webp,.heic,.heif,.avif";
const MAX_PINTEREST_EXTRA_IDENTITY_PHOTOS = 5;

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

type PinterestReference = TrendUploadResponse & {
  preview: string;
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

let runnerRoot: Root | null = null;
let runnerMounted = false;

function ensureTrendRunnerPortal(): void {
  if (typeof document === "undefined" || runnerMounted) return;
  let host = document.getElementById(RUNNER_ROOT_ID);
  if (!host) {
    host = document.createElement("div");
    host.id = RUNNER_ROOT_ID;
    document.body.appendChild(host);
  }
  runnerRoot = runnerRoot || createRoot(host);
  runnerRoot.render(<TrendRunnerPortal />);
  runnerMounted = true;
}

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
  ensureTrendRunnerPortal();
  window.dispatchEvent(new CustomEvent<TrendRunnerEventDetail>(TREND_RUNNER_EVENT, { detail: { trend } }));
}

function openTrendRunnerById(trendId: number): void {
  ensureTrendRunnerPortal();
  window.dispatchEvent(new CustomEvent<TrendRunnerEventDetail>(TREND_RUNNER_EVENT, { detail: { trendId } }));
}

function PinterestPrimarySlot({
  label,
  badge,
  emptyLabel,
  item,
  busy,
  uploading,
  inputRef,
  inputLabel,
  onFile,
  onRemove,
}: {
  label: "РЕФЕРЕНС" | "ТЫ";
  badge: string;
  emptyLabel: string;
  item: PinterestReference | null;
  busy: boolean;
  uploading: boolean;
  inputRef: React.RefObject<HTMLInputElement | null>;
  inputLabel: string;
  onFile: (file: File) => void;
  onRemove: () => void;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5 px-1">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
        <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[9px] font-semibold text-primary">{badge}</span>
      </div>
      <div className="relative">
        <label className="relative flex min-h-44 cursor-pointer flex-col overflow-hidden rounded-2xl border border-dashed border-border/70 bg-secondary/35 text-sm transition hover:border-primary/50">
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_TREND_PHOTOS}
            className="absolute inset-0 z-20 cursor-pointer opacity-0"
            aria-label={inputLabel}
            disabled={busy}
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              event.currentTarget.value = "";
              if (file) onFile(file);
            }}
          />
          {item ? (
            <img src={item.preview} alt={label} className="h-36 w-full object-cover" />
          ) : (
            <div className="flex h-36 flex-col items-center justify-center gap-2 text-muted-foreground">
              {uploading ? <LoaderCircle className="size-7 animate-spin text-primary" /> : <ImagePlus className="size-7 text-primary" />}
              <span className="text-xs font-medium">Загрузить</span>
            </div>
          )}
          <div className="flex min-h-10 items-center justify-center px-2 py-2 text-center text-xs font-medium text-foreground">
            {item ? "Готово ✓" : emptyLabel}
          </div>
        </label>
        {item && !busy ? (
          <button
            type="button"
            aria-label={`Удалить ${label.toLowerCase()}`}
            onClick={onRemove}
            className="absolute right-2 top-2 z-30 flex size-8 items-center justify-center rounded-full bg-background/90 text-foreground shadow"
          >
            <X className="size-4" />
          </button>
        ) : null}
      </div>
    </div>
  );
}

function PinterestTrendFlow({
  trend,
  onTask,
  onBusyChange,
}: {
  trend: TrendPublic;
  onTask: (task: GenerationTask) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [scene, setScene] = useState<PinterestReference | null>(null);
  const [identity, setIdentity] = useState<PinterestReference | null>(null);
  const [identityExtras, setIdentityExtras] = useState<PinterestReference[]>([]);
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [phase, setPhase] = useState<RunnerPhase>("idle");
  const [error, setError] = useState("");
  const sceneInputRef = useRef<HTMLInputElement | null>(null);
  const identityInputRef = useRef<HTMLInputElement | null>(null);
  const extraInputRef = useRef<HTMLInputElement | null>(null);
  const previewUrls = useRef<Set<string>>(new Set());

  const busy = phase === "uploading" || phase === "generating";
  const parsedHeight = Number(heightCm);
  const parsedWeight = Number(weightKg);
  const validHeight = Number.isInteger(parsedHeight) && parsedHeight >= 120 && parsedHeight <= 230;
  const validWeight = Number.isInteger(parsedWeight) && parsedWeight >= 30 && parsedWeight <= 250;
  const primaryReady = Boolean(scene && identity);
  const ready = Boolean(primaryReady && validHeight && validWeight && !busy);

  useEffect(() => {
    onBusyChange(busy);
  }, [busy, onBusyChange]);

  useEffect(() => () => {
    previewUrls.current.forEach((url) => URL.revokeObjectURL(url));
    previewUrls.current.clear();
    onBusyChange(false);
  }, [onBusyChange]);

  const revokePreview = (item: PinterestReference | null | undefined) => {
    if (!item?.preview) return;
    URL.revokeObjectURL(item.preview);
    previewUrls.current.delete(item.preview);
  };

  const uploadOne = async (file: File, slot: "scene" | "identity") => {
    if (busy) return;
    const preview = URL.createObjectURL(file);
    previewUrls.current.add(preview);
    setError("");
    setPhase("uploading");
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiJson<TrendUploadResponse>("/trends/upload", { method: "POST", body: form });
      if (!uploaded.asset_id) throw new Error("Backend не вернул asset_id");
      const next: PinterestReference = { ...uploaded, preview };
      if (slot === "scene") {
        revokePreview(scene);
        setScene(next);
      } else {
        revokePreview(identity);
        setIdentity(next);
      }
      setPhase("idle");
    } catch (uploadError) {
      URL.revokeObjectURL(preview);
      previewUrls.current.delete(preview);
      const message = uploadError instanceof Error ? uploadError.message : "Не удалось загрузить фото";
      setError(message);
      setPhase("error");
      toast.error(message);
    }
  };

  const uploadExtras = async (files: File[]) => {
    if (busy || !files.length) return;
    const available = MAX_PINTEREST_EXTRA_IDENTITY_PHOTOS - identityExtras.length;
    if (files.length > available) {
      const message = `Можно добавить максимум ${MAX_PINTEREST_EXTRA_IDENTITY_PHOTOS} дополнительных ракурсов`;
      setError(message);
      setPhase("error");
      toast.error(message);
      return;
    }

    const previews = files.map((file) => URL.createObjectURL(file));
    previews.forEach((url) => previewUrls.current.add(url));
    setError("");
    setPhase("uploading");
    try {
      const uploaded = await Promise.all(files.map(async (file, index) => {
        const form = new FormData();
        form.append("file", file);
        const result = await apiJson<TrendUploadResponse>("/trends/upload", { method: "POST", body: form });
        if (!result.asset_id) throw new Error("Backend не вернул asset_id");
        return { ...result, preview: previews[index] } as PinterestReference;
      }));
      setIdentityExtras((current) => [...current, ...uploaded]);
      setPhase("idle");
    } catch (uploadError) {
      previews.forEach((url) => {
        URL.revokeObjectURL(url);
        previewUrls.current.delete(url);
      });
      const message = uploadError instanceof Error ? uploadError.message : "Не удалось загрузить дополнительные ракурсы";
      setError(message);
      setPhase("error");
      toast.error(message);
    }
  };

  const removeExtra = (index: number) => {
    if (busy) return;
    setIdentityExtras((current) => {
      const target = current[index];
      revokePreview(target);
      return current.filter((_, currentIndex) => currentIndex !== index);
    });
    setError("");
    setPhase("idle");
  };

  const generate = async () => {
    if (!ready || !scene || !identity) return;
    setError("");
    setPhase("generating");
    try {
      const referenceAssetIds = [scene.asset_id, identity.asset_id, ...identityExtras.map((item) => item.asset_id)];
      const result = await apiJson<TrendRunResponse>(`/trends/${trend.id}/pinterest-run`, {
        method: "POST",
        body: JSON.stringify({
          reference_asset_ids: referenceAssetIds,
          height_cm: parsedHeight,
          weight_kg: parsedWeight,
          confirmed: true,
          idempotency_key: buildIdempotencyKey(trend.id),
        }),
      });
      if (!result.task?.id) throw new Error("Backend не вернул задачу");
      notifyHaptic("success");
      toast.success("Изображение отправлено в генерацию");
      onTask(result.task);
    } catch (generateError) {
      notifyHaptic("error");
      const message = generateError instanceof Error ? generateError.message : "Не удалось создать изображение";
      setError(message);
      setPhase("error");
      toast.error(message);
    }
  };

  return (
    <div className="grid gap-3">
      <div className="rounded-2xl border border-amber-300/30 bg-amber-200/10 p-3">
        <p className="text-xs font-semibold text-foreground">Как получить результат 1 в 1</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          Слева — кадр, который повторяем. Справа — ваше основное фото. Генерация не запускается после загрузки: сначала добавьте все данные и нажмите «Создать».
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <PinterestPrimarySlot
          label="РЕФЕРЕНС"
          badge="откуда"
          emptyLabel="Фото, которое повторяем"
          item={scene}
          busy={busy}
          uploading={phase === "uploading"}
          inputRef={sceneInputRef}
          inputLabel="Загрузить референс Pinterest"
          onFile={(file) => void uploadOne(file, "scene")}
          onRemove={() => {
            revokePreview(scene);
            setScene(null);
            setError("");
            setPhase("idle");
          }}
        />
        <PinterestPrimarySlot
          label="ТЫ"
          badge="кого вставляем"
          emptyLabel="Ваше фото"
          item={identity}
          busy={busy}
          uploading={phase === "uploading"}
          inputRef={identityInputRef}
          inputLabel="Загрузить ваше фото"
          onFile={(file) => void uploadOne(file, "identity")}
          onRemove={() => {
            revokePreview(identity);
            setIdentity(null);
            setError("");
            setPhase("idle");
          }}
        />
      </div>

      {primaryReady ? (
        <>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">1–5 ракурсов одного человека</p>
              <span className="text-[10px] text-muted-foreground">{identityExtras.length}/{MAX_PINTEREST_EXTRA_IDENTITY_PHOTOS}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {identityExtras.map((item, index) => (
                <div key={`${item.asset_id}-${index}`} className="relative size-14 overflow-hidden rounded-xl border border-border/60">
                  <img src={item.preview} alt={`Дополнительный ракурс ${index + 1}`} className="size-full object-cover" />
                  {!busy ? (
                    <button
                      type="button"
                      aria-label={`Удалить ракурс ${index + 1}`}
                      onClick={() => removeExtra(index)}
                      className="absolute right-0.5 top-0.5 flex size-5 items-center justify-center rounded-full bg-background/90 text-foreground"
                    >
                      <X className="size-3" />
                    </button>
                  ) : null}
                </div>
              ))}
              {identityExtras.length < MAX_PINTEREST_EXTRA_IDENTITY_PHOTOS ? (
                <label className="relative flex size-14 cursor-pointer items-center justify-center rounded-xl border border-dashed border-border/70 bg-secondary/25 text-muted-foreground hover:border-primary/50 hover:text-foreground">
                  <input
                    ref={extraInputRef}
                    type="file"
                    multiple
                    accept={ACCEPTED_TREND_PHOTOS}
                    className="absolute inset-0 cursor-pointer opacity-0"
                    aria-label="Добавить дополнительные ракурсы"
                    disabled={busy}
                    onChange={(event) => {
                      const files = Array.from(event.currentTarget.files || []);
                      event.currentTarget.value = "";
                      void uploadExtras(files);
                    }}
                  />
                  {phase === "uploading" ? <LoaderCircle className="size-5 animate-spin" /> : <Plus className="size-5" />}
                </label>
              ) : null}
            </div>
            <p className="text-[10px] leading-relaxed text-muted-foreground">
              Дополнительные ракурсы необязательны, но помогают точнее сохранить лицо, волосы и пропорции.
            </p>
          </div>

          <div className="space-y-1 text-[11px] text-muted-foreground">
            <p><span className="text-emerald-500">●</span> сцена, свет и поза считаются с референса</p>
            <p><span className="text-emerald-500">●</span> лицо и внешность берутся только с твоего фото</p>
          </div>
        </>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        <label className="space-y-1.5">
          <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
            <Ruler className="size-3.5" /> Рост
          </span>
          <div className="relative">
            <input
              type="number"
              inputMode="numeric"
              min={120}
              max={230}
              step={1}
              value={heightCm}
              onChange={(event) => setHeightCm(event.target.value.replace(/[^0-9]/g, "").slice(0, 3))}
              placeholder="165"
              disabled={busy}
              aria-label="Рост"
              aria-invalid={Boolean(heightCm) && !validHeight}
              className="h-11 w-full rounded-xl border border-border/70 bg-secondary/25 px-3 pr-9 text-base outline-none transition focus:border-primary/60"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">см</span>
          </div>
        </label>
        <label className="space-y-1.5">
          <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">
            <Weight className="size-3.5" /> Вес
          </span>
          <div className="relative">
            <input
              type="number"
              inputMode="numeric"
              min={30}
              max={250}
              step={1}
              value={weightKg}
              onChange={(event) => setWeightKg(event.target.value.replace(/[^0-9]/g, "").slice(0, 3))}
              placeholder="55"
              disabled={busy}
              aria-label="Вес"
              aria-invalid={Boolean(weightKg) && !validWeight}
              className="h-11 w-full rounded-xl border border-border/70 bg-secondary/25 px-3 pr-9 text-base outline-none transition focus:border-primary/60"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">кг</span>
          </div>
        </label>
      </div>
      <p className="-mt-1 text-[10px] leading-relaxed text-muted-foreground">
        Рост и вес обязательны, чтобы руки, шея и пропорции тела совпали с вами.
      </p>
      {heightCm && !validHeight ? <p className="text-[10px] text-destructive">Рост должен быть от 120 до 230 см.</p> : null}
      {weightKg && !validWeight ? <p className="text-[10px] text-destructive">Вес должен быть от 30 до 250 кг.</p> : null}

      {error ? <p className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}

      <Button type="button" disabled={!ready} className="h-12 text-base font-semibold" onClick={() => void generate()}>
        {phase === "generating" ? <LoaderCircle className="size-4 animate-spin" /> : null}
        {phase === "generating" ? "Генерирую…" : "Создать →"}
      </Button>

      {!ready ? (
        <p className="text-center text-[10px] text-muted-foreground">
          Для запуска нужны референс, ваше фото, рост и вес. Загрузка фото сама генерацию не запускает.
        </p>
      ) : null}
    </div>
  );
}

function TrendRunnerPortal() {
  const [trend, setTrend] = useState<TrendPublic | null>(null);
  const [phase, setPhase] = useState<RunnerPhase>("idle");
  const [error, setError] = useState("");
  const [localPreview, setLocalPreview] = useState("");
  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const [pinterestBusy, setPinterestBusy] = useState(false);
  const processedStart = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const genericBusy = phase === "uploading" || phase === "generating";
  const busy = genericBusy || pinterestBusy;
  const preview = safeExternalUrl(trend?.preview_url || "");
  const isVideoPreview = trend?.kind === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(preview);
  const isPinterest = Boolean(trend && isPinterestServiceTrend(trend));
  const hint = trend?.user_photo_hint || "Загрузите одно чёткое фото. Остальные параметры тренда уже настроены администратором.";

  const resetRunner = useCallback(() => {
    setPhase("idle");
    setError("");
    setPinterestBusy(false);
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
    if (!trend || !file || genericBusy) return;
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
  }, [genericBusy, resetRunner, trend]);

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
        title={isPinterest ? "Повтори фото с Pinterest" : trend?.title || "Повторить тренд"}
        description={isPinterest ? undefined : "Один снимок. Без настроек. Всё остальное применит backend."}
        onOpenChange={(open) => {
          if (!open) closeRunner();
        }}
      >
        {trend ? (
          isPinterest ? (
            <PinterestTrendFlow
              trend={trend}
              onBusyChange={setPinterestBusy}
              onTask={(task) => {
                setSelectedTask(task);
                setTaskOpen(true);
                setTrend(null);
                setPinterestBusy(false);
              }}
            />
          ) : (
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
                accept={ACCEPTED_TREND_PHOTOS}
                className="sr-only"
                disabled={genericBusy}
                onChange={(event) => {
                  const file = event.currentTarget.files?.[0];
                  event.currentTarget.value = "";
                  void runPhoto(file);
                }}
              />

              <Button disabled={genericBusy} className="min-h-12 w-full" onClick={() => fileInputRef.current?.click()}>
                {genericBusy ? <LoaderCircle className="animate-spin" /> : <ImagePlus />}
                {phaseLabel}
              </Button>

              {error ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">{error}</div> : null}

              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground">
                <X className="mt-0.5 size-3.5 shrink-0" />
                <p>В этом сценарии нельзя менять модель, промпт, формат, качество, duration, seed или provider-параметры. Они применяются только на backend.</p>
              </div>
            </div>
          )
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

if (typeof window !== "undefined") {
  window.setTimeout(() => ensureTrendRunnerPortal(), 0);
}

export { TrendRunnerPortal, copyTrendLink, openTrendRunner, openTrendRunnerById };