import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Film, ImageIcon, ImagePlus, LoaderCircle, Plus, Ruler, Weight, X } from "lucide-react";
import { toast } from "sonner";

import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { readStudioBalance, subscribeStudioBalance } from "@/lib/studio-balance";
import { clearPendingTopup, readPendingTopup, savePendingTopup, sameTopupAttempt, revokePaymentAccess, subscribePaymentAccessRevoked } from "@/lib/topup-recovery";
import { canReopenPayment, paymentFromResponse, paymentResolution, type RepeatPayment, type PaymentProvider } from "@/features/feed-repeat-payment";
import { isPinterestServiceTrend } from "@/features/pinterest-service";
import type { GenerationTask, TrendItem, TrendUserField } from "@/lib/types";
import { notifyHaptic, openExternalUrl, readStartParam } from "@/lib/telegram";
import { safeExternalUrl } from "@/lib/utils";

const TREND_RUNNER_EVENT = "apix:open-trend-runner";
const API_BASE = "/api/v1";
const RUNNER_ROOT_ID = "apix-trend-runner-root";
const ACCEPTED_TREND_PHOTOS = "image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif,.jpg,.jpeg,.png,.webp,.heic,.heif,.avif";
const MAX_PINTEREST_EXTRA_IDENTITY_PHOTOS = 5;
const TREND_USER_NUMBER_RE = /^-?\d+(?:[.,]\d+)?$/;

function trendUserFieldValid(field: TrendUserField, value: string): boolean {
  const clean = value.trim();
  if (!clean) return field.required === false;
  if (field.type === "number") return TREND_USER_NUMBER_RE.test(clean);
  return clean.length <= Math.max(1, Math.min(160, field.max_length || 160));
}

function initialTrendUserValues(trend: TrendPublic): Record<string, string> {
  return Object.fromEntries((trend.user_fields || []).slice(0, 6).map((field) => [field.key, ""]));
}

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

type TrendCheckoutQuote = {
  duration_options?: number[];
  default_duration?: number;
  effective_duration?: number;
  duration_lock_reason?: string | null;
  cost_credits: number;
  balance_credits: number;
  can_run: boolean;
  deficit_credits: number;
  recommended_plan?: {
    key: string;
    label: string;
    credits: number;
    price_rub: number;
  } | null;
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

class TrendApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
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
    let message = response.status >= 500
      ? "Не удалось запустить тренд. Попробуйте ещё раз."
      : `Ошибка API ${response.status}`;
    let code: string | undefined;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      code = typeof detail?.code === "string" ? detail.code : undefined;
      message = String(payload?.error?.message || detail?.message || detail || payload?.message || message);
    } catch {
      // Keep fallback message.
    }
    throw new TrendApiError(message, response.status, code);
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
      if (!uploaded.asset_id) throw new Error("Не удалось подтвердить загрузку фото");
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
        if (!result.asset_id) throw new Error("Не удалось подтвердить загрузку фото");
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
      if (!result.task?.id) throw new Error("Не удалось подтвердить создание задачи");
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
  const balance = useSyncExternalStore(subscribeStudioBalance, readStudioBalance, () => null);
  const previousBalance = useRef(balance);
  const [trend, setTrend] = useState<TrendPublic | null>(null);
  const [phase, setPhase] = useState<RunnerPhase>("idle");
  const [error, setError] = useState("");
  const [localPreview, setLocalPreview] = useState("");
  const [uploadedAsset, setUploadedAsset] = useState<TrendUploadResponse | null>(null);
  const [userValues, setUserValues] = useState<Record<string, string>>({});
  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const [pinterestBusy, setPinterestBusy] = useState(false);
  const [checkout, setCheckout] = useState<TrendCheckoutQuote | null>(null);
  // Retain only safe capabilities for correction, never a payable price or balance.
  const [durationOffer, setDurationOffer] = useState<Pick<TrendCheckoutQuote,
    "duration_options" | "default_duration" | "effective_duration" | "duration_lock_reason"
  > | null>(null);
  const [checkoutError, setCheckoutError] = useState("");
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);
  const checkoutSequence = useRef(0);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [paymentWaiting, setPaymentWaiting] = useState(false);
  const paymentRef = useRef<RepeatPayment | null>(null);
  const [paymentChecking, setPaymentChecking] = useState(false);
  const [paymentChecked, setPaymentChecked] = useState<RepeatPayment | null>(null);
  const paymentOwner = useRef<number | null>(null);
  const paymentAbort = useRef<AbortController | null>(null);
  const heldTrend = useRef<TrendPublic | null>(null);
  if (trend) heldTrend.current = trend;
  const paymentStorage = () => { try { return window.sessionStorage; } catch { return null; } };
  const paymentCheckInFlight = useRef(false);
  const operationSequence = useRef(0);
  const [paymentMethods, setPaymentMethods] = useState<string[]>([]);
  const processedStart = useRef<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const runKeyRef = useRef<{ fingerprint: string; key: string } | null>(null);

  const genericBusy = phase === "uploading" || phase === "generating";
  const busy = genericBusy || pinterestBusy;
  const preview = safeExternalUrl(trend?.preview_url || "");
  const isVideoPreview = trend?.kind === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(preview);
  const isPinterest = Boolean(trend && isPinterestServiceTrend(trend));
  const hint = trend?.user_photo_hint || "Загрузите одно чёткое фото. Остальные параметры тренда уже настроены администратором.";
  const userFields = (trend?.user_fields || []).slice(0, 6);
  const userFieldsReady = userFields.every((field) => trendUserFieldValid(field, userValues[field.key] || ""));
  const personalized = userFields.length > 0;

  const resetRunner = useCallback(() => {
    paymentAbort.current?.abort();
    heldTrend.current = null;
    paymentOwner.current = null;
    setPaymentChecked(null);
    operationSequence.current++;
    checkoutSequence.current++;
    setDuration(null);
    runKeyRef.current = null;
    setPhase("idle");
    setError("");
    setPinterestBusy(false);
    setCheckout(null);
    setDurationOffer(null);
    setCheckoutError("");
    setCheckoutBusy(false);
    setPaymentBusy(false);
    setPaymentWaiting(false);
    paymentRef.current = null;
    setPaymentMethods([]);
    setUploadedAsset(null);
    setUserValues({});
    setLocalPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
  }, []);

  const closeRunner = useCallback(() => {
    if (busy || paymentBusy) return;
    if (paymentWaiting) { setTrend(null); return; }
    resetRunner();
    setTrend(null);
  }, [busy, paymentWaiting, paymentBusy, resetRunner]);

  useLayoutEffect(() => subscribePaymentAccessRevoked(actorId => {
    if (paymentOwner.current !== actorId && previousBalance.current?.actorId !== actorId) return;
    resetRunner(); setTrend(null); setTaskOpen(false); setSelectedTask(null);
  }), [resetRunner]);

  const showTrend = useCallback((next: TrendPublic) => {
    if (heldTrend.current && (paymentRef.current || heldTrend.current.id === next.id)) {
      setTrend(heldTrend.current);
      if (heldTrend.current.id !== next.id) setError("Сначала проверь оплату предыдущего повтора. Фото и настройки сохранены.");
      return;
    }
    resetRunner(); setUserValues(initialTrendUserValues(next)); setTrend(next);
  }, [resetRunner]);

  const loadTrend = useCallback(async (trendId: number) => {
    try {
      const payload = await apiJson<TrendPublic>(`/trends/${trendId}`);
      showTrend(payload);
    } catch (loadError) {
      toast.error(loadError instanceof Error ? loadError.message : "Не удалось открыть тренд");
    }
  }, [showTrend]);

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<TrendRunnerEventDetail>).detail || {};
      if (detail.trend) {
        showTrend(detail.trend);
      } else if (detail.trendId) {
        void loadTrend(detail.trendId);
      }
    };
    window.addEventListener(TREND_RUNNER_EVENT, onOpen);
    return () => window.removeEventListener(TREND_RUNNER_EVENT, onOpen);
  }, [loadTrend, showTrend]);

  const refreshCheckout = useCallback(async (trendId: number, quiet = false, signal?: AbortSignal) => {
    const sequence = ++checkoutSequence.current;
    setCheckout(null);
    setCheckoutError("");
    if (!quiet) setCheckoutBusy(true);
    try {
      const query = duration == null ? "" : `?duration=${duration}`;
      const quote = await apiJson<TrendCheckoutQuote>(`/trends/${trendId}/checkout${query}`, { signal });
      if (
        typeof quote?.can_run !== "boolean"
        || typeof quote.cost_credits !== "number" || !Number.isFinite(quote.cost_credits) || quote.cost_credits < 0
        || typeof quote.balance_credits !== "number" || !Number.isFinite(quote.balance_credits)
        || typeof quote.deficit_credits !== "number" || !Number.isFinite(quote.deficit_credits) || quote.deficit_credits < 0
      ) {
        throw new Error("Стоимость временно недоступна");
      }
      if (sequence !== checkoutSequence.current) return null;
      setCheckout(quote);
      setDurationOffer({ duration_options: quote.duration_options, default_duration: quote.default_duration,
        effective_duration: quote.effective_duration, duration_lock_reason: quote.duration_lock_reason });
      return quote;
    } catch (checkoutError) {
      if (sequence !== checkoutSequence.current) return null;
      if (checkoutError instanceof TrendApiError && [401, 403].includes(checkoutError.status)) {
        const owner = paymentOwner.current ?? readStudioBalance()?.actorId;
        if (owner) revokePaymentAccess(owner);
        else { resetRunner(); setTrend(null); }
        return null;
      }
      setCheckout(null);
      setCheckoutError(checkoutError instanceof Error ? checkoutError.message : "Не удалось получить стоимость");
      if (!quiet) {
        toast.error(checkoutError instanceof Error ? checkoutError.message : "Не удалось получить стоимость");
      }
      return null;
    } finally {
      if (!quiet && sequence === checkoutSequence.current) setCheckoutBusy(false);
    }
  }, [duration, resetRunner]);

  useLayoutEffect(() => {
    const previous = previousBalance.current;
    previousBalance.current = balance;
    if (previous && (!balance || previous.actorId !== balance.actorId)) {
      resetRunner(); setTrend(null); return;
    }
    if (!trend) return;
    if (balance?.open) {
      checkoutSequence.current++;
      setCheckout(null);
    } else if (previous?.open && balance) {
      void refreshCheckout(trend.id);
    }
  }, [balance, trend?.id, refreshCheckout, resetRunner]);

  useEffect(() => {
    if (!trend?.id) return;
    void refreshCheckout(trend.id);
  }, [refreshCheckout, trend?.id]);

  useEffect(() => {
    if (!trend?.id) return;
    const sequence = operationSequence.current;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    void apiJson<{ id: number }>("/me", { signal: controller.signal }).then(viewer => {
      if (sequence !== operationSequence.current || controller.signal.aborted || !Number.isSafeInteger(viewer.id)) return;
      paymentOwner.current = viewer.id;
      const saved = readPendingTopup(paymentStorage(), viewer.id);
      // Preserve the current in-memory URL, but follow an acknowledged/settled shared guard.
      if (!saved || !paymentRef.current || !sameTopupAttempt(saved, paymentRef.current)) { paymentRef.current = saved; setPaymentWaiting(Boolean(saved)); }
    }).catch(() => { if (!controller.signal.aborted) setError("Не удалось подтвердить аккаунт для оплаты. Открой повтор ещё раз."); })
      .finally(() => window.clearTimeout(timeout));
    return () => { controller.abort(); window.clearTimeout(timeout); };
  }, [trend?.id]);

  useEffect(() => {
    if (!trend?.id) return;
    const sequence = operationSequence.current;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    void apiJson<string[]>("/payment-methods", { signal: controller.signal })
      .then((methods) => {
        if (sequence === operationSequence.current && !controller.signal.aborted) setPaymentMethods(Array.isArray(methods) ? methods : []);
      }).catch(error => {
        if (sequence !== operationSequence.current || controller.signal.aborted) return;
        if (error instanceof TrendApiError && [401, 403].includes(error.status)) {
          const owner = paymentOwner.current ?? readStudioBalance()?.actorId;
          if (owner) revokePaymentAccess(owner);
          else { resetRunner(); setTrend(null); }
          return;
        }
        setPaymentMethods([]);
      }).finally(() => window.clearTimeout(timeout));
    return () => { controller.abort(); window.clearTimeout(timeout); };
  }, [trend?.id, resetRunner]);

  const checkPayment = useCallback(async (quiet = false) => {
    const payment = paymentRef.current;
    const owner = paymentOwner.current;
    const sequence = operationSequence.current;
    if (!payment || !owner || !trend || paymentCheckInFlight.current) return;
    paymentCheckInFlight.current = true; setPaymentChecking(true); setPaymentChecked(null);
    const controller = new AbortController(); paymentAbort.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const history = await apiJson<{ transactions: unknown[] }>("/api/web/billing/transactions?limit=100", { signal: controller.signal });
      if (sequence !== operationSequence.current || payment !== paymentRef.current || controller.signal.aborted) return;
      if (!Array.isArray(history.transactions)) throw new Error("История недоступна");
      const resolution = paymentResolution(payment, history.transactions);
      setCheckout(null);
      await refreshCheckout(trend.id, quiet, controller.signal);
      if (sequence !== operationSequence.current || payment !== paymentRef.current || controller.signal.aborted) return;
      if (resolution !== "pending") {
        if (!clearPendingTopup(paymentStorage(), owner, payment)) throw new Error("Текущая оплата изменилась");
        paymentRef.current = null; setPaymentWaiting(false);
        setError(resolution === "paid" ? "Оплата подтверждена. Проверь стоимость и нажми «Создать»."
          : resolution === "failed" ? "Платёж завершился ошибкой. Можно выбрать новое пополнение."
          : "Платёж возвращён. Можно выбрать новое пополнение.");
      } else if (!quiet) {
        setPaymentChecked(payment);
        setError("Платёж пока не подтверждён. Проверь его позже или обратись в поддержку. Достаточный баланс не подтверждает оплату этого счёта.");
      }
    } catch (error) {
      if (sequence === operationSequence.current && error instanceof TrendApiError && [401, 403].includes(error.status)) {
        revokePaymentAccess(owner); return;
      }
      if (sequence === operationSequence.current && !quiet) setError("Не удалось проверить оплату. Повтори проверку позже; новая оплата не создаётся.");
    } finally {
      window.clearTimeout(timeout);
      if (paymentAbort.current === controller) paymentAbort.current = null;
      paymentCheckInFlight.current = false;
      if (sequence === operationSequence.current) setPaymentChecking(false);
    }
  }, [trend, refreshCheckout]);

  useEffect(() => {
    if (!paymentWaiting || paymentBusy || !trend?.id) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      if (++attempts > 48) { window.clearInterval(timer); return; }
      void checkPayment(true);
    }, 2500);
    const onReturn = () => { if (document.visibilityState === "visible") void checkPayment(true); };
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", onReturn); document.removeEventListener("visibilitychange", onReturn); };
  }, [paymentWaiting, paymentBusy, checkPayment, trend?.id]);

  const payInline = useCallback(async () => {
    const plan = checkout?.recommended_plan;
    if (!plan || paymentBusy || paymentRef.current) return;
    const owner = paymentOwner.current;
    if (!owner) { setError("Дождись подтверждения аккаунта перед оплатой."); return; }
    const saved = readPendingTopup(paymentStorage(), owner);
    if (saved) { paymentRef.current = saved; setPaymentWaiting(true); return; }
    const provider = paymentMethods.find((method) => ["tbank", "crypto", "tribute", "lava"].includes(method));
    if (!provider) {
      toast.error("Сейчас нет доступного способа оплаты");
      return;
    }
    setPaymentBusy(true);
    const sequence = operationSequence.current;
    const pending: RepeatPayment = { startedAt: Date.now(), provider: provider as PaymentProvider, planKey: plan.key, transactionId: null, checkoutUrl: null };
    if (!savePendingTopup(paymentStorage(), owner, pending)) { setPaymentBusy(false); setError("Не удалось сохранить защиту оплаты. Разреши хранилище браузера."); return; }
    paymentRef.current = pending;
    setPaymentWaiting(true);
    const controller = new AbortController(); paymentAbort.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const payment = await apiJson<Record<string, unknown>>(`/topup/${provider}`, {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ plan_key: plan.key }),
      });
      if (sequence !== operationSequence.current || !paymentRef.current || controller.signal.aborted) return;
      paymentRef.current = paymentFromResponse(paymentRef.current, payment);
      if (!savePendingTopup(paymentStorage(), owner, paymentRef.current)) throw new Error("Не удалось сохранить номер оплаты");
      const url = paymentRef.current.checkoutUrl;
      if (!url) throw new Error("Платёжная ссылка не получена");
      setPaymentWaiting(true);
      openExternalUrl(url);
      toast.info("Оплата открыта. После возвращения проверь её статус.");
    } catch (paymentError) {
      if (sequence !== operationSequence.current) return;
      if (paymentError instanceof TrendApiError && [401, 403].includes(paymentError.status)) {
        revokePaymentAccess(owner); return;
      }
      if (paymentError instanceof TrendApiError && paymentError.status >= 400 && paymentError.status < 500 && paymentError.status !== 408) {
        if (clearPendingTopup(paymentStorage(), owner, pending)) { paymentRef.current = null; setPaymentWaiting(false); }
      }
      setError("Результат создания оплаты не подтверждён. Проверь уже открытую оплату перед новой попыткой.");
    } finally {
      window.clearTimeout(timeout);
      if (paymentAbort.current === controller) paymentAbort.current = null;
      if (sequence === operationSequence.current) setPaymentBusy(false);
    }
  }, [checkout?.recommended_plan, paymentBusy, paymentMethods]);

  useEffect(() => {
    const trendId = parseTrendStartParam();
    if (!trendId || processedStart.current === trendId) return;
    processedStart.current = trendId;
    void loadTrend(trendId);
  }, [loadTrend]);

  useEffect(() => () => {
    paymentAbort.current?.abort();
    setLocalPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return "";
    });
  }, []);

  const startTrend = useCallback(async (assetId: string, values: Record<string, string>) => {
    if (!trend || genericBusy || paymentBusy || balance?.open) return;
    if (!checkout || checkoutBusy || !checkout.can_run) {
      toast.error("Сначала дождись расчёта стоимости тренда");
      return;
    }
    setError("");
    const sequence = operationSequence.current;
    try {
      setPhase("generating");
      const fingerprint = JSON.stringify([trend.id, assetId, values, duration]);
      const requestKey = runKeyRef.current?.fingerprint === fingerprint
        ? runKeyRef.current.key
        : buildIdempotencyKey(trend.id);
      runKeyRef.current = { fingerprint, key: requestKey };
      const result = await apiJson<TrendRunResponse>(`/trends/${trend.id}/run`, {
        method: "POST",
        body: JSON.stringify({
          asset_id: assetId,
          idempotency_key: requestKey,
          user_values: values,
          quoted_credits: checkout.cost_credits,
          ...(duration == null ? {} : { duration }),
        }),
      });
      if (sequence !== operationSequence.current) return;
      if (!result.task?.id) throw new Error("Не удалось подтвердить создание задачи");
      setSelectedTask(result.task);
      setTaskOpen(true);
      notifyHaptic("success");
      toast.success("Тренд запущен");
      setTrend(null);
      resetRunner();
    } catch (runError) {
      if (sequence !== operationSequence.current) return;
      notifyHaptic("error");
      const message = runError instanceof Error ? runError.message : "Не удалось запустить тренд";
      setError(message);
      setPhase("error");
      if (runError instanceof TrendApiError && runError.code === "trend_quote_stale") {
        await refreshCheckout(trend.id);
        setPhase("idle");
        return;
      }
      toast.error(message);
    }
  }, [checkout, checkoutBusy, duration, genericBusy, paymentBusy, balance?.open, refreshCheckout, resetRunner, trend]);

  const runPhoto = useCallback(async (file: File | undefined | null) => {
    if (!trend || !file || genericBusy) return;
    setError("");
    const sequence = operationSequence.current;
    setUploadedAsset(null);
    setLocalPreview((current) => {
      if (current) URL.revokeObjectURL(current);
      return URL.createObjectURL(file);
    });
    try {
      setPhase("uploading");
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiJson<TrendUploadResponse>("/trends/upload", { method: "POST", body: form });
      if (sequence !== operationSequence.current) return;
      if (!uploaded.asset_id) throw new Error("Не удалось подтвердить загрузку фото");
      setUploadedAsset(uploaded);
      setPhase("idle");
      toast.success("Фото готово. Проверь стоимость и нажми «Создать».");
    } catch (runError) {
      if (sequence !== operationSequence.current) return;
      notifyHaptic("error");
      const message = runError instanceof Error ? runError.message : "Не удалось загрузить фото";
      setError(message);
      setPhase("error");
      toast.error(message);
    }
  }, [genericBusy, trend]);

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
    return uploadedAsset ? "Заменить фото" : "Загрузить фото";
  }, [personalized, phase, trend?.kind, uploadedAsset]);

  return (
    <>
      <Sheet
        balanceUnavailableReason={paymentWaiting || paymentBusy || busy ? "Завершите текущую операцию или проверьте уже открытую оплату ниже." : undefined}
        open={Boolean(trend)}
        title={isPinterest ? "Повтори фото с Pinterest" : trend?.title || "Повторить тренд"}
        description={isPinterest ? undefined : "Загрузи фото и подтверди стоимость. Сценарий тренда уже настроен."}
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

              {trend.kind === "video" && durationOffer?.effective_duration != null ? (
                <div className="grid gap-2 text-sm">
                  <label className="grid gap-2">
                    Длительность видео
                    <select aria-label="Длительность видео" className="min-h-11 rounded-lg border border-border bg-background px-3"
                      value={duration ?? checkout?.effective_duration ?? durationOffer.default_duration ?? durationOffer.effective_duration}
                      disabled={genericBusy || paymentBusy || Boolean(balance?.open) || Boolean(durationOffer.duration_lock_reason) || (durationOffer.duration_options?.length ?? 0) <= 1}
                      onChange={event => {
                        checkoutSequence.current++;
                        setCheckout(null);
                        setDuration(Number(event.target.value));
                        runKeyRef.current = null;
                        setError("");
                      }}>
                      {(durationOffer.duration_options?.length ? durationOffer.duration_options : [durationOffer.effective_duration]).map(seconds => <option key={seconds} value={seconds}>{seconds} сек</option>)}
                    </select>
                  </label>
                  {durationOffer.duration_lock_reason ? <span className="text-xs text-muted-foreground">{durationOffer.duration_lock_reason}</span> : null}
                  {duration != null ? <Button type="button" variant="outline" className="min-h-11 whitespace-normal"
                    disabled={genericBusy || paymentBusy || checkoutBusy || Boolean(balance?.open)}
                    onClick={() => {
                      checkoutSequence.current++;
                      setCheckout(null);
                      setDuration(null);
                      runKeyRef.current = null;
                      setError("");
                    }}>Вернуть длительность автора</Button> : null}
                </div>
              ) : null}
              <div className="rounded-xl border border-primary/20 bg-primary/5 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs text-muted-foreground">Стоимость повтора</p>
                    <p className="text-lg font-semibold text-foreground">
                      {checkoutBusy && !checkout ? "Считаем…" : `${checkout?.cost_credits ?? "—"} 💋`}
                    </p>
                  </div>
                  {checkout ? (
                    <div className="text-right text-[11px] text-muted-foreground">
                      <p>Баланс: {checkout.balance_credits} 💋</p>
                      {!checkout.can_run ? <p>Не хватает: {checkout.deficit_credits} 💋</p> : <p className="text-emerald-500">Можно запускать</p>}
                    </div>
                  ) : null}
                </div>
                {checkoutError && !checkout && !checkoutBusy ? <div className="mt-3 grid gap-2">
                  <p role="alert" className="text-sm text-destructive">{checkoutError}. Стоимость не подтверждена.</p>
                  <Button type="button" variant="outline" className="min-h-11"
                    disabled={genericBusy || paymentBusy || Boolean(balance?.open)}
                    onClick={() => void refreshCheckout(trend.id)}>Повторить расчёт</Button>
                </div> : null}
                {paymentWaiting ? <div className="mt-3 grid gap-2">
                  <p className="text-xs">Статус оплаты ещё не подтверждён. Фото и настройки сохранены.</p>
                  <Button variant="outline" disabled={paymentBusy || paymentChecking} onClick={() => void checkPayment()}>Проверить оплату</Button>
                  {paymentRef.current && canReopenPayment(paymentRef.current) ? <Button variant="outline" onClick={() => openExternalUrl(paymentRef.current!.checkoutUrl!)}>Открыть эту оплату</Button> : null}
                  {paymentChecked === paymentRef.current && paymentChecked && !paymentChecked.transactionId ? <>
                    <p className="text-xs">Статус этой попытки неизвестен. Проверь историю и платёжный сервис: новый счёт может привести к повторной оплате.</p>
                    <Button variant="outline" className="whitespace-normal" disabled={paymentChecking} onClick={() => {
                      if (paymentOwner.current && paymentChecked === paymentRef.current && clearPendingTopup(paymentStorage(), paymentOwner.current, paymentChecked)) {
                        paymentRef.current = null; setPaymentWaiting(false); setPaymentChecked(null);
                        setError("Статус прошлой оплаты остаётся неизвестным. Новая оплата — только по твоему нажатию.");
                      }
                    }}>Историю проверил — разрешить новое пополнение</Button>
                  </> : null}
                </div> : null}
                {checkout && !checkout.can_run && checkout.recommended_plan ? (
                  <div className="mt-3 grid gap-1.5">
                    <Button
                      type="button"
                      disabled={paymentBusy || paymentWaiting || paymentMethods.length === 0}
                      className="min-h-11 w-full"
                      onClick={() => void payInline()}
                    >
                      {paymentBusy ? <LoaderCircle className="size-4 animate-spin" /> : null}
                      {paymentWaiting
                        ? "Ждём подтверждение оплаты…"
                        : `Пополнить здесь · ${checkout.recommended_plan.price_rub} ₽`}
                    </Button>
                    <p className="text-center text-[10px] text-muted-foreground">
                      +{checkout.recommended_plan.credits} 💋. Возвращаться в раздел «Баланс» не нужно.
                    </p>
                  </div>
                ) : null}
              </div>

              {userFields.length ? (
                <div className="grid gap-2 rounded-xl border border-primary/20 bg-primary/5 p-3">
                  <div>
                    <p className="text-xs font-semibold text-foreground">Параметры тренда</p>
                    <p className="text-[10px] text-muted-foreground">Можно изменить только эти поля. Скрытый промпт останется скрытым.</p>
                  </div>
                  {userFields.map((field) => {
                    const value = userValues[field.key] || "";
                    const valid = trendUserFieldValid(field, value);
                    return (
                      <label key={field.key} className="grid gap-1 text-[11px] font-medium">
                        <span>{field.label}{field.required === false ? "" : " *"}</span>
                        <div className="flex items-center gap-2">
                          <input
                            type={field.type === "date" ? "date" : "text"}
                            inputMode={field.type === "number" ? "decimal" : "text"}
                            value={value}
                            maxLength={field.type === "date" ? undefined : Math.max(1, Math.min(160, field.max_length || 160))}
                            placeholder={field.placeholder || ""}
                            aria-invalid={Boolean(value) && !valid}
                            disabled={genericBusy}
                            className="min-h-10 min-w-0 flex-1 rounded-lg border border-border bg-background px-3 text-sm outline-none focus:border-primary/60"
                            onChange={(event) => {
                              let nextValue = event.target.value;
                              if (field.type === "number") nextValue = nextValue.replace(/[^0-9.,-]/g, "").slice(0, 160);
                              setUserValues((current) => ({ ...current, [field.key]: nextValue }));
                            }}
                          />
                          {field.suffix ? <span className="text-xs text-muted-foreground">{field.suffix}</span> : null}
                        </div>
                        {value && !valid ? <small className="text-destructive">Проверь значение поля «{field.label}»</small> : null}
                      </label>
                    );
                  })}
                </div>
              ) : null}

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
                {phase === "uploading" ? <LoaderCircle className="animate-spin" /> : <ImagePlus />}
                {phaseLabel}
              </Button>

              {uploadedAsset ? (
                <Button
                  disabled={genericBusy || paymentBusy || checkoutBusy || Boolean(balance?.open) || !userFieldsReady || !checkout || !checkout.can_run}
                  className="min-h-12 w-full"
                  onClick={() => {
                    if (uploadedAsset) void startTrend(uploadedAsset.asset_id, userValues);
                  }}
                >
                  {phase === "generating" ? <LoaderCircle className="animate-spin" /> : null}
                  {phase === "generating" ? "Генерирую…" : `Создать · ${checkout?.cost_credits ?? "—"} 💋`}
                </Button>
              ) : null}

              {personalized && !userFieldsReady ? (
                <p className="text-center text-[10px] text-muted-foreground">Заполни отмеченные поля, затем загрузи фото и нажми «Создать».</p>
              ) : null}

              {error ? <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">{error}</div> : null}

              <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-2 text-[11px] text-muted-foreground">
                <X className="mt-0.5 size-3.5 shrink-0" />
                <p>Модель, скрытый промпт, формат и качество сохраняются из рецепта автора. Для видео можно выбрать доступную длительность.</p>
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
