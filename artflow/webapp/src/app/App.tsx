import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Toaster, toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { BalanceSheet } from "@/components/balance-sheet";
import { LockedScreen } from "@/components/locked-screen";
import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { FeedScreen } from "@/features/feed-screen";
import { CreateScreen } from "@/features/create-screen";
import { WorksScreen } from "@/features/works-screen";
import { Button } from "@/components/ui/button";
import { hasDraftInput, readUserDrafts, saveUserDrafts, tabStorage } from "@/lib/draft-storage";
import { previewEnabled, previewKey } from "@/lib/ux2";
import { inspectDraftMedia } from "@/lib/draft-media";
import { appendReferenceUrls, applyDraftPatch, modelSnapshotKey, selectGenerationInputs } from "@/lib/reference-selection";
import { GenerationScreen } from "@/features/generation-screen";
import { ProfileScreen } from "@/features/profile-screen";
import { ServicesScreen } from "@/features/services-screen";
import { SettingsScreen } from "@/features/settings-screen";
import { TrendsScreen } from "@/features/trends-screen";
import { ApiError, FEED_PAGE_SIZE, MAX_HISTORY_ITEMS, MiniAppApi } from "@/lib/api";
import {
  configureTelegramWebApp,
  haptic,
  notifyHaptic,
  openExternalUrl,
  parseStartTarget,
  readStartParam,
  waitForTelegramInitData,
} from "@/lib/telegram";
import type {
  AppLanguage,
  AppMode,
  AppTab,
  AssistantMessage,
  BootstrapData,
  FeedItem,
  GenerationDraft,
  GenerationTask,
  ModelInfo,
  PaymentPlan,
  PhotoPromptResult,
  PreparedTrend,
  ReferralStats,
  TrendItem,
  VideoPromptResult,
} from "@/lib/types";
import { firstMedia, isPendingTask } from "@/lib/utils";

window.__APIX_MINIAPP_BUILD_ID__ = "20260803-settings-cabinets-v1";

type FeedSource = "recent" | "top_day" | "top";

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

function clampTaskCount(value: number | undefined): number {
  const normalized = Number(value || 1);
  return [1, 2, 3, 4, 6].includes(normalized) ? normalized : 1;
}

function emptyDraft(kind: GenerationDraft["kind"]): GenerationDraft {
  return {
    kind,
    model: "",
    prompt: "",
    promptId: null,
    sourceTitle: "",
    aspectRatio: kind === "video" || kind === "motion" ? "16:9" : "1:1",
    quality: "basic",
    count: 1,
    taskCount: 1,
    mode: kind === "motion" ? "motion" : "text",
    duration: 5,
    resolution: "720p",
    referenceUrls: [],
    videoUrl: "",
    videoStart: 0,
    videoEnd: null,
    audioIds: [],
    characterIds: [],
    seed: null,
    grokMode: "normal",
  };
}

function numberSetting(settings: Record<string, unknown>, key: string, fallback: number): number {
  const value = Number(settings[key]);
  return Number.isFinite(value) ? value : fallback;
}

function stringSetting(settings: Record<string, unknown>, key: string, fallback: string): string {
  const value = settings[key];
  return typeof value === "string" && value ? value : fallback;
}

function mediaLooksVideo(item: FeedItem): boolean {
  const media = firstMedia(item);
  return item.gen_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(media);
}

function uniqueStrings(items: string[]): string[] {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

async function readVideoDurationSeconds(file: File): Promise<number | null> {
  if (!file.type.startsWith("video/")) return null;
  const objectUrl = URL.createObjectURL(file);
  try {
    return await new Promise<number | null>((resolve) => {
      const video = document.createElement("video");
      let settled = false;
      const finish = (value: number | null) => {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      const timer = window.setTimeout(() => finish(null), 5000);
      video.preload = "metadata";
      video.onloadedmetadata = () => {
        window.clearTimeout(timer);
        const seconds = Number(video.duration);
        finish(Number.isFinite(seconds) && seconds > 0 ? seconds : null);
      };
      video.onerror = () => {
        window.clearTimeout(timer);
        finish(null);
      };
      video.src = objectUrl;
    });
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function mergeFeedPage(current: FeedItem[], incoming: FeedItem[]): FeedItem[] {
  const incomingById = new Map(incoming.map((item) => [item.id, item]));
  const currentIds = new Set(current.map((item) => item.id));
  return [
    ...current.map((item) => incomingById.get(item.id) || item),
    ...incoming.filter((item) => !currentIds.has(item.id)),
  ];
}

function App() {
  const [mode, setMode] = useState<AppMode>("booting");
  const [errorMessage, setErrorMessage] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [botUsername, setBotUsername] = useState("");
  const [api, setApi] = useState<MiniAppApi | null>(null);
  const [data, setData] = useState<BootstrapData | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>("feed");
  const [ux2, setUx2] = useState(false);
  const [worksRefreshing, setWorksRefreshing] = useState(false);
  const [draftStorageUnavailable, setDraftStorageUnavailable] = useState(false);
  const draftOwner = useRef<number | null>(null);
  const submissionLock = useRef(false);
  const latestActor = useRef<number | null>(null);
  latestActor.current = data?.user.id ?? null;

  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const [balanceOpen, setBalanceOpen] = useState(false);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [remixingId, setRemixingId] = useState<number | null>(null);
  const [feedSource, setFeedSource] = useState<FeedSource>("recent");
  const [feedLimit, setFeedLimit] = useState(FEED_PAGE_SIZE);
  const [feedHasMore, setFeedHasMore] = useState(true);
  const [feedLoading, setFeedLoading] = useState(false);
  const [feedLoadingMore, setFeedLoadingMore] = useState(false);
  const [trendsFilter, setTrendsFilter] = useState<"all" | "image" | "video">("all");
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [preparingTrendId, setPreparingTrendId] = useState<number | null>(null);
  const [referrals, setReferrals] = useState<ReferralStats | null>(null);
  const [referralsLoading, setReferralsLoading] = useState(false);
  const [referralActionBusy, setReferralActionBusy] = useState(false);
  const [languageBusy, setLanguageBusy] = useState(false);
  const [assistantMessages, setAssistantMessages] = useState<AssistantMessage[]>([]);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [photoPromptBusy, setPhotoPromptBusy] = useState(false);
  const [photoPromptResult, setPhotoPromptResult] = useState<PhotoPromptResult | null>(null);
  const [videoPromptBusy, setVideoPromptBusy] = useState(false);
  const [videoPromptResult, setVideoPromptResult] = useState<VideoPromptResult | null>(null);
  const [referenceUploadingKind, setReferenceUploadingKind] = useState<GenerationDraft["kind"] | null>(null);
  const [videoUploadingKind, setVideoUploadingKind] = useState<GenerationDraft["kind"] | null>(null);
  const [imageDraft, setImageDraft] = useState<GenerationDraft>(() => emptyDraft("image"));
  const [videoDraft, setVideoDraft] = useState<GenerationDraft>(() => emptyDraft("video"));
  const [motionDraft, setMotionDraft] = useState<GenerationDraft>(() => emptyDraft("motion"));
  const processedStartParam = useRef("");
  const refreshAbortRef = useRef<AbortController | null>(null);

  const hydrateDraftDefaults = useCallback((bootstrap: BootstrapData, preview: boolean) => {
    if (draftOwner.current === bootstrap.user.id) return;
    draftOwner.current = bootstrap.user.id;
    const stored = preview ? readUserDrafts(tabStorage(), bootstrap.user.id) : {};
    const firstImage = bootstrap.imageModels[0];
    const firstVideo = bootstrap.videoModels.find(model => !/motion-control/i.test(model.key)) || bootstrap.videoModels[0];
    const firstMotion = bootstrap.videoModels.find(model => /motion/i.test(`${model.key} ${model.display_name}`) || model.modes?.includes("motion"));
    const make = (kind: GenerationDraft["kind"], model?: ModelInfo): GenerationDraft => ({
      ...emptyDraft(kind), model: model?.key || "", mode: model?.modes?.[0] || (kind === "motion" ? "motion" : "text"),
      aspectRatio: model?.aspect_ratios?.[0] || emptyDraft(kind).aspectRatio,
      quality: model?.quality_options?.[0]?.value || "basic", count: model?.counts?.[0] || 1,
      duration: modelDurations(model)[0] || 5, resolution: modelResolutions(model)[0] || "720p",
      grokMode: model?.mode_options?.[0] || "normal",
    });
    setImageDraft(stored.image || make("image", firstImage));
    setVideoDraft(stored.video || make("video", firstVideo));
    setMotionDraft(stored.motion || make("motion", firstMotion));
  }, []);

  useEffect(() => {
    if (mode !== "live" || !ux2 || !data || draftOwner.current !== data.user.id) return;
    const saved = saveUserDrafts(tabStorage(), data.user.id, { image: imageDraft, video: videoDraft, motion: motionDraft });
    setDraftStorageUnavailable(!saved);
  }, [mode, ux2, data?.user.id, imageDraft, videoDraft, motionDraft]);

  useEffect(() => {
    if (ux2 && data?.user.miniapp_ux2_available !== true) { setUx2(false); setActiveTab("feed"); }
  }, [data?.user.miniapp_ux2_available, ux2]);

  const changePreview = (enabled: boolean) => {
    if (!data || data.user.miniapp_ux2_available !== true) return;
    const storage = tabStorage();
    try { storage?.setItem(previewKey(data.user.id), enabled ? "2" : "1"); } catch { /* In-memory preview still works. */ }
    if (enabled) {
      const stored = readUserDrafts(storage, data.user.id);
      if (imageDraft.promptId === null && !hasDraftInput(imageDraft) && stored.image) setImageDraft(stored.image);
      if (videoDraft.promptId === null && !hasDraftInput(videoDraft) && stored.video) setVideoDraft(stored.video);
      if (motionDraft.promptId === null && !hasDraftInput(motionDraft) && stored.motion) setMotionDraft(stored.motion);
    }
    const url = new URL(window.location.href);
    url.searchParams.set("ux", enabled ? "2" : "1");
    window.history.replaceState(window.history.state, "", url);
    setUx2(enabled);
    setActiveTab("feed");
  };

  const patchDraft = useCallback((kind: GenerationDraft["kind"], patcher: (current: GenerationDraft) => GenerationDraft) => {
    if (kind === "image") setImageDraft(patcher);
    else if (kind === "video") setVideoDraft(patcher);
    else setMotionDraft(patcher);
  }, []);

  const resetPreset = useCallback((kind: GenerationDraft["kind"]) => {
    const saved = data ? readUserDrafts(tabStorage(), data.user.id)[kind] : undefined;
    patchDraft(kind, current => saved?.referenceMaterials !== undefined ? saved
      : { ...current, promptId: null, sourceTitle: "", prompt: "" });
  }, [data?.user.id, patchDraft]);

  const uploadReferenceFiles = useCallback(async (kind: GenerationDraft["kind"], files: File[]) => {
    if (!api || referenceUploadingKind || !files.length) return;
    setReferenceUploadingKind(kind);
    try {
      const uploaded: string[] = [];
      for (const file of files) {
        const result = await api.uploadMedia(file);
        if (result.url) uploaded.push(result.url);
      }
      if (!uploaded.length) throw new Error("Backend не вернул ссылки на файлы");
      patchDraft(kind, (current) => appendReferenceUrls(current, uploaded));
      notifyHaptic("success");
      toast.success(uploaded.length === 1 ? "Фото загружено" : `Загружено файлов: ${uploaded.length}`);
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить файл");
    } finally {
      setReferenceUploadingKind(null);
    }
  }, [api, patchDraft, referenceUploadingKind]);

  const uploadVideoFile = useCallback(async (kind: GenerationDraft["kind"], file: File) => {
    if (!api || videoUploadingKind) return;
    setVideoUploadingKind(kind);
    try {
      const detectedDuration = await readVideoDurationSeconds(file);
      const selectedDraft = kind === "image" ? imageDraft : kind === "video" ? videoDraft : motionDraft;
      const modelList = kind === "image" ? data?.imageModels : data?.videoModels;
      const selected = modelList?.find((model) => model.key === selectedDraft.model);
      if (selected?.duration_from_source && detectedDuration != null && (detectedDuration < 4 || detectedDuration > 30)) {
        throw new Error("Для Genjutsu загрузи видео длительностью от 4 до 30 секунд");
      }
      const result = await api.uploadMedia(file);
      if (!result.url) throw new Error("Backend не вернул ссылку на видео");
      patchDraft(kind, (current) => {
        const sourceDuration = selected?.duration_from_source && detectedDuration != null
          ? Math.ceil(detectedDuration)
          : current.duration;
        return { ...current, videoUrl: result.url, duration: sourceDuration };
      });
      notifyHaptic("success");
      toast.success(
        detectedDuration != null ? `Видео загружено · ${Math.ceil(detectedDuration)} сек` : "Видео загружено",
      );
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить видео");
    } finally {
      setVideoUploadingKind(null);
    }
  }, [api, data?.imageModels, data?.videoModels, imageDraft, videoDraft, motionDraft, patchDraft, videoUploadingKind]);

  const applyPreparedTrend = useCallback((prepared: PreparedTrend) => {
    const settings = prepared.settings || {};
    if (prepared.kind === "video") {
      setVideoDraft((current) => ({
        ...selectGenerationInputs(current),
        model: prepared.model,
        prompt: "Использовать скрытый трендовый промпт",
        promptId: prepared.prompt_id,
        sourceTitle: prepared.title,
        mode: stringSetting(settings, "scenario", current.mode),
        aspectRatio: stringSetting(settings, "ratio", current.aspectRatio),
        duration: numberSetting(settings, "duration", current.duration),
        resolution: stringSetting(settings, "resolution", current.resolution),
        grokMode: stringSetting(settings, "grok_mode", current.grokMode),
      }));
      setActiveTab("video");
    } else {
      setImageDraft((current) => ({
        ...selectGenerationInputs(current),
        model: prepared.model,
        prompt: "Использовать скрытый трендовый промпт",
        promptId: prepared.prompt_id,
        sourceTitle: prepared.title,
        aspectRatio: stringSetting(settings, "ratio", current.aspectRatio),
        quality: stringSetting(settings, "quality", current.quality),
      }));
      setActiveTab("photo");
    }
    haptic("medium");
  }, []);

  const processStartParam = useCallback(
    async (client: MiniAppApi, bootstrap: BootstrapData) => {
      const raw = readStartParam();
      if (!raw || processedStartParam.current === raw) return;
      processedStartParam.current = raw;
      const target = parseStartTarget(raw);
      if (!target) return;

      if (target.kind === "profile") {
        setActiveTab("profile");
        return;
      }
      if (target.kind === "feed" || target.kind === "remix") {
        setActiveTab("feed");
        const feedId = Number(target.value);
        if (!Number.isSafeInteger(feedId) || feedId <= 0) return;
        // Opening a link must prepare a repeat, never start paid work.
        // Bootstrap already hydrates this exact public source (not a nearby card).
        const source = bootstrap.feed.find((entry) => entry.id === feedId);
        if (!source) {
          toast.error("Работа из ссылки не найдена или больше не опубликована");
          return;
        }
        void client.remixFeedItem(source).then((task) => {
          setData((current) => current ? {
            ...current, recentTasks: [task, ...current.recentTasks.filter((entry) => entry.id !== task.id)],
          } : current);
          setSelectedTask(task);
          setTaskOpen(true);
        }).catch((cause: Error) => {
          if (cause.message !== "Повтор отменён" && cause.message !== "Открыт новый повтор") {
            toast.error(cause.message || "Не удалось настроить повтор");
          }
        });
        return;
      }
      if (target.kind === "trend") {
        const id = Number(target.value);
        if (Number.isInteger(id)) applyPreparedTrend(await client.prepareTrend(id));
        return;
      }
      if (target.kind === "task") {
        const id = Number(target.value);
        if (Number.isInteger(id)) {
          const task = await client.getGeneration(id);
          setSelectedTask(task);
          setTaskOpen(true);
        }
        return;
      }
      if (target.kind === "prompt") {
        const promptId = Number(target.value);
        const model = bootstrap.imageModels[0];
        if (Number.isInteger(promptId)) {
          setImageDraft((current) => ({
            ...selectGenerationInputs(current),
            model: current.model || model?.key || "",
            prompt: "Использовать промпт из библиотеки",
            promptId,
            sourceTitle: `Промпт #${promptId}`,
          }));
          setActiveTab("photo");
        }
      }
    },
    [applyPreparedTrend],
  );

  const initialize = useCallback(async () => {
    setRetrying(true);
    setMode("booting");
    setErrorMessage("");
    configureTelegramWebApp();

    const authProbe = new MiniAppApi("");
    authProbe.getAuthConfig().then((config) => setBotUsername(config.bot_username || "")).catch(() => undefined);

    try {
      const initData = await waitForTelegramInitData(8_000);
      if (!initData) {
        setMode("locked");
        return;
      }
      const client = new MiniAppApi(initData);
      const bootstrap = await client.bootstrap();
      setApi(client);
      setData(bootstrap);
      setFeedLimit(FEED_PAGE_SIZE);
      setFeedHasMore(bootstrap.feed.length >= FEED_PAGE_SIZE);
      let savedPreview: string | null = null;
      try { savedPreview = tabStorage()?.getItem(previewKey(bootstrap.user.id)) || null; } catch { /* Storage is optional. */ }
      const preview = previewEnabled(bootstrap.user, window.location.search, savedPreview);
      setUx2(preview);
      hydrateDraftDefaults(bootstrap, preview);
      setMode("live");
      await processStartParam(client, bootstrap);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Не удалось загрузить Mini App";
      setErrorMessage(message);
      setMode(error instanceof ApiError && error.status === 401 ? "locked" : "error");
    } finally {
      setRetrying(false);
    }
  }, [hydrateDraftDefaults, processStartParam]);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  const refreshCore = useCallback(async () => {
    if (!api || document.visibilityState !== "visible") return;
    // Abort the previous poll before starting a new one: the old code
    // returned a cleanup function that no caller ever ran.
    refreshAbortRef.current?.abort();
    const controller = new AbortController();
    refreshAbortRef.current = controller;
    try {
      const core = await api.refreshCore(controller.signal);
      setData((current) => {
        if (!current) return current;
        const freshTaskIds = new Set(core.recentTasks.map((task) => task.id));
        // Fresh page (newest 100) wins on overlapping ids, so status updates
        // propagate; the tail is preserved but bounded. Items that fall out
        // of the newest page keep their last-seen status until reload — the
        // open task sheet has its own 4s poll for live status (see below).
        // Server-side deletions are likewise visible only after reload.
        const recentTasks = [
          ...core.recentTasks,
          ...current.recentTasks.filter((task) => !freshTaskIds.has(task.id)),
        ].slice(0, MAX_HISTORY_ITEMS);
        return {
          ...current,
          user: core.user,
          historyUnavailable: false,
          recentTasks,
        };
      });
      setSelectedTask((current) => {
        if (!current) return current;
        return core.recentTasks.find((task) => task.id === current.id) || current;
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        console.warn("Mini App core refresh failed", error);
      }
    }
  }, [api]);

  const refreshReferrals = useCallback(async () => {
    if (!api || referralsLoading) return;
    setReferralsLoading(true);
    try {
      setReferrals(await api.getReferrals());
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось загрузить партнёрскую статистику");
    } finally {
      setReferralsLoading(false);
    }
  }, [api, referralsLoading]);

  useEffect(() => {
    if (mode !== "live" || !api) return undefined;
    const timer = window.setInterval(() => void refreshCore(), 5_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refreshCore();
    };
    window.addEventListener("focus", onVisible);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onVisible);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [api, mode, refreshCore]);

  useEffect(() => {
    if (!api || !taskOpen || !selectedTask || !isPendingTask(selectedTask) || document.visibilityState !== "visible") return undefined;
    const timer = window.setInterval(async () => {
      try {
        const task = await api.getGeneration(selectedTask.id);
        setSelectedTask(task);
        setData((current) => current ? {
          ...current,
          recentTasks: [task, ...current.recentTasks.filter((item) => item.id !== task.id)],
        } : current);
        if (!isPendingTask(task)) {
          notifyHaptic(task.status === "failed" ? "error" : "success");
          toast[task.status === "failed" ? "error" : "success"](
            task.status === "failed" ? "Генерация завершилась ошибкой" : "Результат готов",
          );
        }
      } catch (error) {
        console.warn("Task polling failed", error);
      }
    }, 4_000);
    return () => window.clearInterval(timer);
  }, [api, selectedTask, taskOpen]);

  useEffect(() => {
    if (activeTab !== "profile" || referrals || referralsLoading) return;
    void refreshReferrals();
  }, [activeTab, referrals, referralsLoading, refreshReferrals]);

  const openTask = useCallback((task: GenerationTask) => {
    setSelectedTask(task);
    setTaskOpen(true);
  }, []);

  const currentDraft = useMemo(() => ({ image: imageDraft, video: videoDraft, motion: motionDraft }), [imageDraft, motionDraft, videoDraft]);

  const submitGeneration = useCallback(async (kind: "image" | "video" | "motion") => {
    if (!api || !data || submitting || submissionLock.current) return;
    const sourceDraft = currentDraft[kind];
    const draft = selectGenerationInputs(sourceDraft);
    const hasSelection = sourceDraft.promptId === null && sourceDraft.referenceMaterials !== undefined;
    if ((ux2 || hasSelection) && draft.promptId === null) {
      if (referenceUploadingKind === kind || videoUploadingKind === kind) return;
      const model = (kind === "image" ? data.imageModels : data.videoModels).find(item => item.key === draft.model);
      const { issues } = inspectDraftMedia(sourceDraft, model);
      if (issues.length) {
        toast.error(issues[0].message);
        return;
      }
    }
    const taskCount = clampTaskCount(draft.taskCount);
    submissionLock.current = true;
    setSubmitting(true);
    const createdTasks: GenerationTask[] = [];
    let checkingSelection = hasSelection;
    try {
      if (hasSelection) {
        const previousModel = (kind === "image" ? data.imageModels : data.videoModels).find(item => item.key === draft.model);
        const controller = new AbortController();
        // Finite UI transport guard, independent of provider retry/billing policy.
        const timer = window.setTimeout(() => controller.abort(), 15_000);
        let freshModels: ModelInfo[];
        try {
          const response = await api.request<unknown>(kind === "image" ? "/models/image" : "/models/video", {}, controller.signal);
          if (!Array.isArray(response) || response.some(item => !item || typeof item.key !== "string"
            || typeof item.display_name !== "string" || !Array.isArray(item.modes)
            || typeof item.credits !== "number" || !Number.isFinite(item.credits) || item.credits < 0)) {
            throw new Error("Не удалось проверить возможности модели. Материалы сохранены.");
          }
          freshModels = response as ModelInfo[];
        } finally { window.clearTimeout(timer); }
        if (latestActor.current !== data.user.id || draftOwner.current !== data.user.id) throw new Error("Аккаунт изменился. Откройте редактор заново.");
        const currentModel = freshModels.find(item => item.key === draft.model);
        setData(current => current && current.user.id === data.user.id
          ? { ...current, ...(kind === "image" ? { imageModels: freshModels } : { videoModels: freshModels }) } : current);
        if (modelSnapshotKey(previousModel) !== modelSnapshotKey(currentModel)) {
          toast.info("Условия модели обновились. Проверьте материалы и стоимость, затем подтвердите запуск ещё раз.");
          return;
        }
        const freshIssues = inspectDraftMedia(sourceDraft, currentModel).issues;
        if (freshIssues.length) { toast.error(freshIssues[0].message); return; }
      }
      checkingSelection = false;
      const prompt = draft.prompt.trim() || (draft.model.startsWith("higgsfield/genjutsu/") ? "" : "Использовать выбранный сценарий");
      for (let index = 0; index < taskCount; index += 1) {
        const task = kind === "image"
          ? await api.createImage({
              model: draft.model,
              prompt,
              prompt_id: draft.promptId,
              aspect_ratio: draft.aspectRatio,
              quality: draft.quality,
              count: draft.count,
              reference_url: draft.referenceUrls[0] || null,
              reference_urls: draft.referenceUrls,
            })
          : await api.createVideo({
              model: draft.model,
              prompt,
              prompt_id: draft.promptId,
              mode: draft.mode,
              duration: draft.duration,
              aspect_ratio: draft.aspectRatio,
              resolution: draft.resolution,
              image_url: draft.referenceUrls[0] || null,
              reference_urls: draft.referenceUrls,
              video_url: draft.videoUrl || null,
              video_start: draft.videoStart,
              video_end: draft.videoEnd,
              audio_ids: draft.audioIds,
              character_ids: draft.characterIds,
              seed: draft.seed,
              grok_mode: draft.grokMode || "normal",
            });
        createdTasks.push(task);
      }
      const orderedTasks = [...createdTasks].reverse();
      setData((current) => current ? {
        ...current,
        recentTasks: [...orderedTasks, ...current.recentTasks.filter((item) => !createdTasks.some((task) => task.id === item.id))],
      } : current);
      const primaryTask = createdTasks[createdTasks.length - 1];
      setSelectedTask(primaryTask);
      setTaskOpen(true);
      notifyHaptic("success");
      toast.success(taskCount > 1 ? `Создано задач: ${taskCount}` : "Задача создана");
      void refreshCore();
    } catch (error) {
      if (createdTasks.length) {
        const orderedTasks = [...createdTasks].reverse();
        setData((current) => current ? {
          ...current,
          recentTasks: [...orderedTasks, ...current.recentTasks.filter((item) => !createdTasks.some((task) => task.id === item.id))],
        } : current);
      }
      notifyHaptic("error");
      const prefix = createdTasks.length ? `Создано ${createdTasks.length}, дальше ошибка: ` : "";
      toast.error(checkingSelection
        ? "Не удалось проверить актуальные условия. Запуск не отправлен, материалы сохранены. Повторите проверку."
        : `${prefix}${error instanceof Error ? error.message : "Не удалось создать задачу"}`);
    } finally {
      submissionLock.current = false;
      setSubmitting(false);
    }
  }, [api, currentDraft, data, refreshCore, submitting, ux2, referenceUploadingKind, videoUploadingKind]);

  const refreshTask = useCallback(async (task: GenerationTask) => {
    if (!api || taskBusy) return;
    setTaskBusy(true);
    try {
      const updated = await api.getGeneration(task.id);
      setSelectedTask(updated);
      setData((current) => current ? { ...current, recentTasks: [updated, ...current.recentTasks.filter((item) => item.id !== updated.id)] } : current);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить задачу");
    } finally {
      setTaskBusy(false);
    }
  }, [api, taskBusy]);

  const toggleTaskShare = useCallback(async (task: GenerationTask) => {
    if (!api || taskBusy) return;
    setTaskBusy(true);
    try {
      if (task.is_public_feed) {
        await api.removeFeedPost(task.id);
        setSelectedTask({ ...task, is_public_feed: false });
        toast.success("Публикация убрана из ленты");
      } else {
        const result = await api.shareGeneration(task.id);
        setSelectedTask({ ...task, is_public_feed: true });
        if (result.link) {
          try { await navigator.clipboard.writeText(result.link); } catch { /* Link remains published even if clipboard is unavailable. */ }
        }
        toast.success("Работа опубликована");
      }
      void refreshCore();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось изменить публикацию");
    } finally {
      setTaskBusy(false);
    }
  }, [api, refreshCore, taskBusy]);

  const toggleTaskLibrary = useCallback(async (task: GenerationTask) => {
    if (!api || taskBusy) return;
    setTaskBusy(true);
    try {
      if (task.is_prompt_library) await api.removePrompt(task.id);
      else await api.savePrompt(task.id);
      setSelectedTask({ ...task, is_prompt_library: !task.is_prompt_library });
      toast.success(task.is_prompt_library ? "Промпт убран из библиотеки" : "Промпт добавлен в библиотеку");
      void refreshCore();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось изменить библиотеку");
    } finally {
      setTaskBusy(false);
    }
  }, [api, refreshCore, taskBusy]);

  const loadFeed = useCallback(async (source = feedSource, limit = FEED_PAGE_SIZE) => {
    if (!api || feedLoading) return;
    setFeedLoading(true);
    try {
      const feed = await api.getFeed(source, limit);
      setData((current) => current ? { ...current, feed } : current);
      setFeedLimit(limit);
      setFeedHasMore(feed.length >= limit);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить ленту");
    } finally {
      setFeedLoading(false);
    }
  }, [api, feedLoading, feedSource]);

  const loadMoreFeed = useCallback(async () => {
    if (!api || feedLoading || feedLoadingMore || !feedHasMore) return;
    const nextLimit = feedLimit + FEED_PAGE_SIZE;
    setFeedLoadingMore(true);
    try {
      const feed = await api.getFeed(feedSource, nextLimit);
      setData((current) => current ? { ...current, feed: mergeFeedPage(current.feed, feed) } : current);
      setFeedLimit(nextLimit);
      setFeedHasMore(feed.length >= nextLimit);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось подгрузить ленту");
    } finally {
      setFeedLoadingMore(false);
    }
  }, [api, feedHasMore, feedLimit, feedLoading, feedLoadingMore, feedSource]);

  const likeFeed = useCallback(async (item: FeedItem) => {
    if (!api) return;
    try {
      const result = await api.likeFeed(item.id);
      setData((current) => current ? {
        ...current,
        feed: current.feed.map((entry) => entry.id === item.id ? { ...entry, likes_count: result.likes_count ?? (entry.likes_count || 0) + 1 } : entry),
      } : current);
      haptic("light");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось поставить лайк");
    }
  }, [api]);

  const remixFeed = useCallback(async (item: FeedItem) => {
    if (!api || remixingId) return;
    setRemixingId(item.id);
    try {
      const task = await api.remixFeedItem(item);
      setData((current) => current ? { ...current, recentTasks: [task, ...current.recentTasks.filter((entry) => entry.id !== task.id)] } : current);
      openTask(task);
      notifyHaptic("success");
      toast.success("Повтор запущен");
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось повторить работу");
    } finally {
      setRemixingId(null);
    }
  }, [api, openTask, remixingId]);

  const loadTrends = useCallback(async () => {
    if (!api || trendsLoading) return;
    setTrendsLoading(true);
    try {
      const trends = await api.getTrends();
      setData((current) => current ? { ...current, trends } : current);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить тренды");
    } finally {
      setTrendsLoading(false);
    }
  }, [api, trendsLoading]);

  const prepareTrend = useCallback(async (trend: TrendItem) => {
    if (!api || preparingTrendId) return;
    setPreparingTrendId(trend.id);
    try {
      applyPreparedTrend(await api.prepareTrend(trend.id));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось подготовить тренд");
    } finally {
      setPreparingTrendId(null);
    }
  }, [api, applyPreparedTrend, preparingTrendId]);

  const sendAssistant = useCallback(async (message: string) => {
    if (!api || assistantBusy) return;
    const nextHistory = [...assistantMessages, { role: "user" as const, text: message }];
    setAssistantMessages(nextHistory);
    setAssistantBusy(true);
    try {
      const reply = await api.sendAssistant(message, assistantMessages);
      setAssistantMessages((current) => [...current, { role: "assistant", text: reply }]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Помощник временно недоступен");
    } finally {
      setAssistantBusy(false);
    }
  }, [api, assistantBusy, assistantMessages]);

  const createPhotoPrompt = useCallback(async (file: File) => {
    if (!api || photoPromptBusy) return;
    setPhotoPromptBusy(true);
    setPhotoPromptResult(null);
    try {
      const result = await api.photoPrompt(file);
      setPhotoPromptResult(result);
      toast.success("Промпт готов");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось проанализировать фото");
    } finally {
      setPhotoPromptBusy(false);
    }
  }, [api, photoPromptBusy]);

  const createVideoPrompt = useCallback(async (file: File) => {
    if (!api || videoPromptBusy) return;
    setVideoPromptBusy(true);
    setVideoPromptResult(null);
    try {
      const result = await api.videoPrompt(file);
      setVideoPromptResult(result);
      toast.success("Видео-промпт готов");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось проанализировать видео");
    } finally {
      setVideoPromptBusy(false);
    }
  }, [api, videoPromptBusy]);

  const pay = useCallback(async (provider: "tbank" | "crypto" | "tribute" | "lava", plan: PaymentPlan) => {
    if (!api || paymentBusy) return;
    setPaymentBusy(true);
    try {
      const result = await api.createPayment(provider, plan.key);
      const url = String(result.invoice_link || result.invoice_url || result.pay_url || result.url || "");
      if (!url) throw new Error("Платёжная ссылка не получена");
      openExternalUrl(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось создать платёж");
    } finally {
      setPaymentBusy(false);
    }
  }, [api, paymentBusy, refreshCore]);

  const changeLanguage = useCallback(async (language: AppLanguage) => {
    if (!api || !data || languageBusy) return;
    setLanguageBusy(true);
    try {
      const result = await api.setLanguage(language);
      setData((current) => current ? { ...current, user: { ...current.user, language: result.language } } : current);
      notifyHaptic("success");
      toast.success(result.language === "en" ? "Language switched to English" : "Язык переключён на русский");
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось сменить язык");
    } finally {
      setLanguageBusy(false);
    }
  }, [api, data, languageBusy]);

  const createReferralWithdrawal = useCallback(async (amountRub: number, payoutDetails: string) => {
    if (!api || referralActionBusy) return;
    setReferralActionBusy(true);
    try {
      await api.createReferralWithdrawal(amountRub, payoutDetails);
      notifyHaptic("success");
      toast.success("Заявка на вывод создана");
      await refreshReferrals();
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось создать заявку");
    } finally {
      setReferralActionBusy(false);
    }
  }, [api, referralActionBusy, refreshReferrals]);

  const exchangeReferralBalance = useCallback(async (amountRub: number) => {
    if (!api || referralActionBusy) return;
    setReferralActionBusy(true);
    try {
      await api.exchangeReferralBalance(amountRub);
      notifyHaptic("success");
      toast.success("Партнёрский баланс обменян на кредиты");
      await refreshReferrals();
      void refreshCore();
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось обменять баланс");
    } finally {
      setReferralActionBusy(false);
    }
  }, [api, referralActionBusy, refreshCore, refreshReferrals]);

  const refreshWorks = async () => {
    if (!api || worksRefreshing) return;
    setWorksRefreshing(true);
    try {
      const history = await api.getHistory();
      setData(current => {
        if (!current) return current;
        const currentById = new Map(current.recentTasks.map(task => [task.id, task]));
        const incomingIds = new Set(history.map(task => task.id));
        const refreshed = history.map(task => {
          const known = currentById.get(task.id);
          // A delayed history response must not downgrade a completed local task.
          return known && !isPendingTask(known) && isPendingTask(task) ? known : task;
        });
        return { ...current, historyUnavailable: false, recentTasks: [...refreshed, ...current.recentTasks.filter(task => !incomingIds.has(task.id))].slice(0, MAX_HISTORY_ITEMS) };
      });
    } catch {
      setData(current => current ? { ...current, historyUnavailable: true } : current);
    } finally { setWorksRefreshing(false); }
  };

  const showFeed = activeTab === "feed" || activeTab === "studio";

  if (mode === "booting") {
    return (
      <main className="grid min-h-[100dvh] place-items-center px-4 text-center">
        <div>
          <span className="mx-auto grid size-16 place-items-center rounded-2xl bg-primary/15 text-primary"><LoaderCircle className="size-8 animate-spin" /></span>
          <h1 className="mt-4 text-xl font-semibold">Синхронизируем APIX</h1>
          <p className="mt-1 text-sm text-muted-foreground">Проверяем Telegram-сессию, баланс, модели и задачи</p>
        </div>
      </main>
    );
  }

  if (mode === "locked" || mode === "error" || !data) {
    return <LockedScreen message={errorMessage} botUsername={botUsername} retrying={retrying} onRetry={() => void initialize()} />;
  }

  const screen = (() => {
    if (ux2 && activeTab === "create") {
      return <CreateScreen imageModels={data.imageModels} videoModels={data.videoModels} drafts={[imageDraft, videoDraft, motionDraft]} language={data.user.language} onNavigate={setActiveTab} />;
    }
    if (ux2 && activeTab === "works") {
      return <WorksScreen tasks={data.recentTasks} models={[...data.imageModels, ...data.videoModels]} language={data.user.language} unavailable={data.historyUnavailable} refreshing={worksRefreshing} onOpenTask={openTask} onCreate={() => setActiveTab("create")} onRefresh={() => void refreshWorks()} />;
    }
    if (showFeed) {
      return (
        <FeedScreen
          items={data.feed}
          source={feedSource}
          loading={feedLoading}
          loadingMore={feedLoadingMore}
          hasMore={feedHasMore}
          remixingId={remixingId}
          onSourceChange={(source) => {
            setFeedSource(source);
            setFeedHasMore(true);
            void loadFeed(source, FEED_PAGE_SIZE);
          }}
          onRefresh={() => void loadFeed(feedSource, Math.max(feedLimit, FEED_PAGE_SIZE))}
          onLoadMore={() => void loadMoreFeed()}
          onLike={(item) => void likeFeed(item)}
          onRemix={(item) => void remixFeed(item)}
        />
      );
    }
    if (activeTab === "photo") {
      return <GenerationScreen ux2={ux2} kind="image" user={data.user} models={data.imageModels} draft={imageDraft} submitting={submitting} referenceUploading={referenceUploadingKind === "image"} videoUploading={videoUploadingKind === "image"} onChange={(patch) => setImageDraft((current) => applyDraftPatch(current, patch))} onUploadReferenceFiles={(files) => void uploadReferenceFiles("image", files)} onUploadVideoFile={(file) => void uploadVideoFile("image", file)} onSubmit={() => void submitGeneration("image")} onResetPreset={() => resetPreset("image")} />;
    }
    if (activeTab === "video") {
      return <GenerationScreen ux2={ux2} kind="video" user={data.user} models={data.videoModels} draft={videoDraft} submitting={submitting} referenceUploading={referenceUploadingKind === "video"} videoUploading={videoUploadingKind === "video"} onChange={(patch) => setVideoDraft((current) => applyDraftPatch(current, patch))} onUploadReferenceFiles={(files) => void uploadReferenceFiles("video", files)} onUploadVideoFile={(file) => void uploadVideoFile("video", file)} onSubmit={() => void submitGeneration("video")} onResetPreset={() => resetPreset("video")} />;
    }
    if (activeTab === "motion") {
      return <GenerationScreen ux2={ux2} kind="motion" user={data.user} models={data.videoModels} draft={motionDraft} submitting={submitting} referenceUploading={referenceUploadingKind === "motion"} videoUploading={videoUploadingKind === "motion"} onChange={(patch) => setMotionDraft((current) => applyDraftPatch(current, patch))} onUploadReferenceFiles={(files) => void uploadReferenceFiles("motion", files)} onUploadVideoFile={(file) => void uploadVideoFile("motion", file)} onSubmit={() => void submitGeneration("motion")} onResetPreset={() => resetPreset("motion")} />;
    }
    if (activeTab === "trends") {
      return <TrendsScreen items={data.trends} filter={trendsFilter} loading={trendsLoading} preparingId={preparingTrendId} onFilterChange={setTrendsFilter} onRefresh={() => void loadTrends()} onPrepare={(trend) => void prepareTrend(trend)} />;
    }
    if (activeTab === "services") {
      return <ServicesScreen messages={assistantMessages} assistantBusy={assistantBusy} photoPromptBusy={photoPromptBusy} photoPromptResult={photoPromptResult} videoPromptBusy={videoPromptBusy} videoPromptResult={videoPromptResult} onAssistantSend={(message) => void sendAssistant(message)} onPhotoPrompt={(file) => void createPhotoPrompt(file)} onVideoPrompt={(file) => void createVideoPrompt(file)} onUsePrompt={(prompt) => { setImageDraft((current) => ({ ...current, prompt, promptId: null, sourceTitle: "" })); setActiveTab("photo"); }} onUseVideoPrompt={(prompt) => { setVideoDraft((current) => ({ ...current, prompt, promptId: null, sourceTitle: "" })); setActiveTab("video"); }} onNavigate={setActiveTab} />;
    }
    if (activeTab === "settings") {
      return <SettingsScreen previewEnabled={ux2} onPreviewChange={changePreview} user={data.user} busy={languageBusy} onLanguageChange={(language) => void changeLanguage(language)} onResetApp={() => void initialize()} />;
    }
    return (
      <ProfileScreen
        user={data.user}
        tasks={data.recentTasks}
        referrals={referrals}
        referralsLoading={referralsLoading}
        referralBusy={referralActionBusy}
        onOpenTask={openTask}
        onBalanceOpen={() => setBalanceOpen(true)}
        onRefreshReferrals={() => void refreshReferrals()}
        onReferralWithdraw={(amountRub, payoutDetails) => void createReferralWithdrawal(amountRub, payoutDetails)}
        onReferralExchange={(amountRub) => void exchangeReferralBalance(amountRub)}
      />
    );
  })();

  return (
    <>
      <AppShell ux2={ux2} activeTab={showFeed ? "feed" : activeTab} user={data.user} onTabChange={setActiveTab} onBalanceOpen={() => setBalanceOpen(true)}>
        {ux2 && activeTab === "profile" && <div className="ux2-profile-actions"><Button variant="outline" onClick={() => setActiveTab("settings")}>{data.user.language === "en" ? "Settings" : "Настройки"}</Button></div>}
        {ux2 && draftStorageUnavailable && <div className="ux2-inline-notice" role="status">{data.user.language === "en" ? "Browser storage is unavailable. Keep this tab open to retain your draft." : "Хранилище браузера недоступно. Не закрывайте вкладку, чтобы не потерять черновик."}</div>}
        {screen}
      </AppShell>
      <TaskDetailSheet task={selectedTask} open={taskOpen} busy={taskBusy} onOpenChange={setTaskOpen} onRefresh={(task) => void refreshTask(task)} onShare={(task) => void toggleTaskShare(task)} onToggleLibrary={(task) => void toggleTaskLibrary(task)} />
      <BalanceSheet open={balanceOpen} user={data.user} plans={data.paymentPlans} availableProviders={data.paymentMethods} busy={paymentBusy} onOpenChange={setBalanceOpen} onPay={(provider, plan) => void pay(provider, plan)} />
      <Toaster className="apix-toaster" richColors position="top-center" closeButton />
    </>
  );
}

export { App };
