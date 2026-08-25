import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ImagePlus, LoaderCircle, Plus, Ruler, Weight, X } from "lucide-react";
import { toast } from "sonner";

import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { GenerationTask } from "@/lib/types";
import { notifyHaptic } from "@/lib/telegram";

const API_BASE = "/api/v1";
const PINTEREST_SERVICE_EVENT = "apix:open-pinterest-service";
const PINTEREST_SERVICE_ROOT_ID = "apix-pinterest-service-root";
const ACCEPTED_PINTEREST_PHOTOS = "image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif,.jpg,.jpeg,.png,.webp,.heic,.heif,.avif";
const FALLBACK_MAX_EXTRA_IDENTITY_PHOTOS = 5;

type ServicePhase = "idle" | "uploading" | "generating" | "error";

type PinterestUploadResponse = {
  asset_id: string;
  url: string;
  kind: "image";
  filename?: string;
  content_type?: string;
  size?: number;
};

type PinterestReference = PinterestUploadResponse & {
  preview: string;
};

type PinterestRunResponse = {
  ok?: boolean;
  task: GenerationTask;
  credits?: number;
};

export type PinterestServiceInfo = {
  id: "pinterest" | string;
  title: string;
  description: string;
  badge?: string;
  price_credits: number;
  quality?: string;
  max_identity_angles?: number;
  height_min_cm?: number;
  height_max_cm?: number;
  weight_min_kg?: number;
  weight_max_kg?: number;
  available?: boolean;
};

type PinterestServiceEventDetail = {
  info?: PinterestServiceInfo;
};

let serviceRoot: Root | null = null;
let serviceMounted = false;

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

function formatCredits(value: number | null | undefined): string {
  const parsed = Number(value || 0);
  if (!Number.isFinite(parsed)) return "—";
  return Number.isInteger(parsed) ? String(parsed) : parsed.toFixed(1).replace(/\.0$/, "");
}

function buildServiceIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `pinterest-service-${crypto.randomUUID()}`;
  }
  return `pinterest-service-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function fetchPinterestServiceInfo(): Promise<PinterestServiceInfo> {
  return apiJson<PinterestServiceInfo>("/services/pinterest");
}

function ensurePinterestServicePortal(): void {
  if (typeof document === "undefined" || serviceMounted) return;
  let host = document.getElementById(PINTEREST_SERVICE_ROOT_ID);
  if (!host) {
    host = document.createElement("div");
    host.id = PINTEREST_SERVICE_ROOT_ID;
    document.body.appendChild(host);
  }
  serviceRoot = serviceRoot || createRoot(host);
  serviceRoot.render(<PinterestServicePortal />);
  serviceMounted = true;
}

export function openPinterestService(info?: PinterestServiceInfo): void {
  ensurePinterestServicePortal();
  window.dispatchEvent(new CustomEvent<PinterestServiceEventDetail>(PINTEREST_SERVICE_EVENT, { detail: { info } }));
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
            accept={ACCEPTED_PINTEREST_PHOTOS}
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

function PinterestServiceFlow({
  info,
  onTask,
  onBusyChange,
}: {
  info: PinterestServiceInfo;
  onTask: (task: GenerationTask) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [scene, setScene] = useState<PinterestReference | null>(null);
  const [identity, setIdentity] = useState<PinterestReference | null>(null);
  const [identityExtras, setIdentityExtras] = useState<PinterestReference[]>([]);
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [phase, setPhase] = useState<ServicePhase>("idle");
  const [error, setError] = useState("");
  const sceneInputRef = useRef<HTMLInputElement | null>(null);
  const identityInputRef = useRef<HTMLInputElement | null>(null);
  const extraInputRef = useRef<HTMLInputElement | null>(null);
  const previewUrls = useRef<Set<string>>(new Set());

  const maxExtraPhotos = Number(info.max_identity_angles || FALLBACK_MAX_EXTRA_IDENTITY_PHOTOS);
  const minHeight = Number(info.height_min_cm || 120);
  const maxHeight = Number(info.height_max_cm || 230);
  const minWeight = Number(info.weight_min_kg || 30);
  const maxWeight = Number(info.weight_max_kg || 250);
  const busy = phase === "uploading" || phase === "generating";
  const parsedHeight = Number(heightCm);
  const parsedWeight = Number(weightKg);
  const validHeight = Number.isInteger(parsedHeight) && parsedHeight >= minHeight && parsedHeight <= maxHeight;
  const validWeight = Number.isInteger(parsedWeight) && parsedWeight >= minWeight && parsedWeight <= maxWeight;
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
      const uploaded = await apiJson<PinterestUploadResponse>("/services/pinterest/upload", { method: "POST", body: form });
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
    const available = maxExtraPhotos - identityExtras.length;
    if (files.length > available) {
      const message = `Можно добавить максимум ${maxExtraPhotos} дополнительных ракурсов`;
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
        const result = await apiJson<PinterestUploadResponse>("/services/pinterest/upload", { method: "POST", body: form });
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
      const result = await apiJson<PinterestRunResponse>("/services/pinterest/run", {
        method: "POST",
        body: JSON.stringify({
          reference_asset_ids: referenceAssetIds,
          height_cm: parsedHeight,
          weight_kg: parsedWeight,
          confirmed: true,
          idempotency_key: buildServiceIdempotencyKey(),
        }),
      });
      if (!result.task?.id) throw new Error("Backend не вернул задачу");
      notifyHaptic("success");
      toast.success("Pinterest-сервис запущен");
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
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-primary/25 bg-primary/8 px-3 py-2.5">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-primary">Pinterest AI · сервис</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">Стоимость списывается только после запуска генерации.</p>
        </div>
        <span className="shrink-0 rounded-full border border-primary/25 bg-primary/15 px-2.5 py-1 text-xs font-bold text-primary">
          {formatCredits(info.price_credits)} 💋
        </span>
      </div>

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
              <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground">1–{maxExtraPhotos} ракурсов одного человека</p>
              <span className="text-[10px] text-muted-foreground">{identityExtras.length}/{maxExtraPhotos}</span>
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
              {identityExtras.length < maxExtraPhotos ? (
                <label className="relative flex size-14 cursor-pointer items-center justify-center rounded-xl border border-dashed border-border/70 bg-secondary/25 text-muted-foreground hover:border-primary/50 hover:text-foreground">
                  <input
                    ref={extraInputRef}
                    type="file"
                    multiple
                    accept={ACCEPTED_PINTEREST_PHOTOS}
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
              min={minHeight}
              max={maxHeight}
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
              min={minWeight}
              max={maxWeight}
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
      {heightCm && !validHeight ? <p className="text-[10px] text-destructive">Рост должен быть от {minHeight} до {maxHeight} см.</p> : null}
      {weightKg && !validWeight ? <p className="text-[10px] text-destructive">Вес должен быть от {minWeight} до {maxWeight} кг.</p> : null}

      {error ? <p className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}

      <Button type="button" disabled={!ready} className="h-12 text-base font-semibold" onClick={() => void generate()}>
        {phase === "generating" ? <LoaderCircle className="size-4 animate-spin" /> : null}
        {phase === "generating" ? "Генерирую…" : `Создать · ${formatCredits(info.price_credits)} 💋 →`}
      </Button>

      {!ready ? (
        <p className="text-center text-[10px] text-muted-foreground">
          Для запуска нужны референс, ваше фото, рост и вес. Загрузка фото сама генерацию не запускает.
        </p>
      ) : null}
    </div>
  );
}

function PinterestServicePortal() {
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState<PinterestServiceInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);

  const loadInfo = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchPinterestServiceInfo();
      setInfo(payload);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Pinterest AI временно недоступен";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<PinterestServiceEventDetail>).detail || {};
      if (detail.info) setInfo(detail.info);
      setError("");
      setOpen(true);
      if (!detail.info) void loadInfo();
    };
    window.addEventListener(PINTEREST_SERVICE_EVENT, onOpen);
    return () => window.removeEventListener(PINTEREST_SERVICE_EVENT, onOpen);
  }, [loadInfo]);

  const refreshTask = useCallback(async (task: GenerationTask) => {
    if (taskBusy) return;
    setTaskBusy(true);
    try {
      setSelectedTask(await apiJson<GenerationTask>(`/generations/${task.id}`));
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

  return (
    <>
      <Sheet
        open={open}
        title="Повтори фото с Pinterest"
        description={info ? `${info.description} · запуск ${formatCredits(info.price_credits)} 💋` : "Отдельный сервис Pinterest AI"}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && busy) return;
          setOpen(nextOpen);
        }}
      >
        {loading && !info ? (
          <div className="grid min-h-48 place-items-center text-sm text-muted-foreground">
            <div className="flex items-center gap-2"><LoaderCircle className="size-4 animate-spin" /> Загружаю Pinterest AI…</div>
          </div>
        ) : error && !info ? (
          <div className="grid gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            <p>{error}</p>
            <Button type="button" variant="outline" onClick={() => void loadInfo()}>Повторить</Button>
          </div>
        ) : info ? (
          <PinterestServiceFlow
            info={info}
            onBusyChange={setBusy}
            onTask={(task) => {
              setSelectedTask(task);
              setTaskOpen(true);
              setOpen(false);
              setBusy(false);
            }}
          />
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

if (typeof window !== "undefined") {
  window.setTimeout(() => ensurePinterestServicePortal(), 0);
}

export { PinterestServicePortal };
