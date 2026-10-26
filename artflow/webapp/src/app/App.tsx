import { isKling4, kling4Body, kling4Intent } from "@/lib/kling4";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { BookOpenText, CircleHelp, CreditCard, LoaderCircle, Settings, ShieldCheck, UserRoundCog } from "lucide-react";
import { Toaster, toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { BalanceSheet } from "@/components/balance-sheet";
import { LockedScreen } from "@/components/locked-screen";
import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { FeedScreen } from "@/features/feed-screen";
import { CreateScreen } from "@/features/create-screen";
import { WorksScreen } from "@/features/works-screen";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { hasDraftInput, readUserDrafts, saveUserDrafts, tabStorage } from "@/lib/draft-storage";
import { previewEnabled, previewKey } from "@/lib/ux2";
import { inspectDraftMedia, switchDraftModel } from "@/lib/draft-media";
import { parseReferenceAvailability, referenceAvailabilityMessage, REFERENCE_CHECK_TIMEOUT_MS } from "@/lib/reference-availability";
import { usePhotoUploads } from "@/lib/use-photo-uploads";
import { photoUploading } from "@/lib/photo-upload";
import { appendReferenceUrls, applyDraftPatch, modelSnapshotKey, selectGenerationInputs, referenceMaterials } from "@/lib/reference-selection";
import { GenerationScreen } from "@/features/generation-screen";
import { ProfileScreen } from "@/features/profile-screen";
import { ServicesScreen } from "@/features/services-screen";
import { MusicSunoPanel } from "@/features/services-screen";
import { LilacHome, LilacCreate, LilacIdeas } from "@/features/lilac/home-screen";
import { LilacModels } from "@/features/lilac/models-screen";
import { LilacLibrary, type LibraryPrompt } from "@/features/lilac/library-screen";
import { LilacAssistant } from "@/features/lilac/assistant-screen";
import { LilacHelp, LilacBilling } from "@/features/lilac/account-screens";
import { LilacOwner } from "@/features/lilac/owner-screen";
import { LilacAdminSystemPanel } from "@/features/lilac/admin/system-panel";
import { LilacAccountEditor } from "@/features/lilac/account-editor";
import { LilacImageSeries } from "@/features/lilac/image-series";
import { lilacRequested } from "@/lib/lilac";
import { publishStudioBalance } from "@/lib/studio-balance";
import { clearPendingTopup, readPendingTopup, savePendingTopup, sameTopupAttempt, revokePaymentAccess, subscribePaymentAccessRevoked } from "@/lib/topup-recovery";
import { isInsufficientCreditError } from "@/lib/credit-recovery";
import { creditErrorToast } from "@/lib/credit-error-toast";
import { canReopenPayment, paymentFromResponse, paymentResolution, type RepeatPayment } from "@/features/feed-repeat-payment";
import { SettingsScreen } from "@/features/settings-screen";
import { TrendsScreen } from "@/features/trends-screen";
import { openTrendRunner } from "@/features/trend-runner";
import { supportsPlan, checkoutPrice } from "@/lib/billing-methods";
import { ApiError, FEED_PAGE_SIZE, MAX_HISTORY_ITEMS, MiniAppApi } from "@/lib/api";
import {
  configureTelegramWebApp,
  configureStudioChrome,
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
import { firstMedia, isPendingTask, safeExternalUrl } from "@/lib/utils";
import { saveDownload } from "@/lib/download";

window.__APIX_MINIAPP_BUILD_ID__ = "20261026-profile-folders-black-lilac-r2";

type FeedSource = "recent" | "top_day" | "top";
type VideoQuote = Awaited<ReturnType<MiniAppApi["quoteVideo"]>>;
type VideoConfirmation = { kind: "video" | "motion"; bodyKey: string; owner: number; quote: VideoQuote; count: number };

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
    wanAudio: true,
    wanNsfwChecker: true,
    wanReferenceAudioUrls: [],
    wanReferenceVideoUrls: [],
    wanReferenceFileUrls: [],
    wanReferenceLinkUrls: [],
    wanFirstFrameUrl: "",
    wanLastFrameUrl: "",
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
  const quoteWan = useCallback((payload: Record<string, unknown>) => {
    if (!api) return Promise.reject(new Error("Сервис временно недоступен"));
    return api.quoteVideo(payload).then(value => ({
      credits: value.cost_credits,
      rate: value.rate_credits_per_second ?? 0,
      billable_seconds: value.billable_seconds,
      input_video_seconds: value.reference_seconds,
      max_output_seconds: Math.max(0, 30 - value.reference_seconds),
    }));
  }, [api]);
  const [data, setData] = useState<BootstrapData | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>("feed");
  const [ux2, setUx2] = useState(false);
  const [lilac, setLilac] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  useEffect(() => {
    if (lilac) document.documentElement.dataset.apixStudio = "lilac";
    else delete document.documentElement.dataset.apixStudio;
    return () => { delete document.documentElement.dataset.apixStudio; };
  }, [lilac]);
  useEffect(() => lilac ? configureStudioChrome() : undefined, [lilac]);
  useEffect(() => configureTelegramWebApp(), []);
  const [worksRefreshing, setWorksRefreshing] = useState(false);
  const [draftStorageUnavailable, setDraftStorageUnavailable] = useState(false);
  const draftOwner = useRef<number | null>(null);
  const submissionLock = useRef(false);
  const latestActor = useRef<number | null>(null);
  latestActor.current = mode === "live" ? data?.user.id ?? null : null;

  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const [balanceOpen, setBalanceOpen] = useState(false);
  useLayoutEffect(() => {
    if (mode !== "live" || !lilac || !data?.user.miniapp_ux2_available) {
      publishStudioBalance(null);
      return;
    }
    const actorId = data.user.id;
    publishStudioBalance({ actorId, credits: data.user.credits, language: data.user.language || "ru", open: balanceOpen,
      onOpen: () => { if (latestActor.current === actorId) setBalanceOpen(true); } });
    return () => publishStudioBalance(null);
  }, [mode, lilac, data?.user.id, data?.user.credits, data?.user.language, data?.user.miniapp_ux2_available, balanceOpen]);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const paymentRequest = useRef(false);
  const [paymentError, setPaymentError] = useState("");
  const [pendingTopup, setPendingTopup] = useState<RepeatPayment | null>(null);
  const pendingTopupRef = useRef<RepeatPayment | null>(null);
  const [topupChecking, setTopupChecking] = useState(false);
  const [topupChecked, setTopupChecked] = useState<RepeatPayment | null>(null);
  const topupAbort = useRef<AbortController | null>(null);
  const topupCheckAbort = useRef<AbortController | null>(null);
  const topupStorage = () => { try { return window.sessionStorage; } catch { return null; } };
  useLayoutEffect(() => {
    const saved = data?.user.id ? readPendingTopup(topupStorage(), data.user.id) : null;
    pendingTopupRef.current = saved; setPendingTopup(saved); setTopupChecked(null); setTopupChecking(false); setPaymentError("");
    return () => { topupAbort.current?.abort(); topupCheckAbort.current?.abort(); };
  }, [data?.user.id]);
  useLayoutEffect(() => {
    if (mode !== "live") {
      topupAbort.current?.abort(); topupCheckAbort.current?.abort();
      setTopupChecked(null);
    }
  }, [mode]);
  useLayoutEffect(() => {
    if (balanceOpen && data?.user.id) {
      const saved = readPendingTopup(topupStorage(), data.user.id);
      const previous = pendingTopupRef.current;
      const current = saved && previous && sameTopupAttempt(saved, previous) ? previous : saved;
      pendingTopupRef.current = current; setPendingTopup(current); setTopupChecked(null);
    }
  }, [balanceOpen, data?.user.id]);
  const [submitting, setSubmitting] = useState(false);
  const [videoConfirmation, setVideoConfirmation] = useState<VideoConfirmation | null>(null);
  const [videoQuoteRefreshing, setVideoQuoteRefreshing] = useState(false);
  const previousBalanceOpen = useRef(false);
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
  const [musicModel, setMusicModel] = useState("");
  const [musicPrompt, setMusicPrompt] = useState("");
  const consumeMusicPrompt = useCallback(() => setMusicPrompt(""), []);
  const [imageDraft, setImageDraft] = useState<GenerationDraft>(() => emptyDraft("image"));
  const [videoDraft, setVideoDraft] = useState<GenerationDraft>(() => emptyDraft("video"));
  const [motionDraft, setMotionDraft] = useState<GenerationDraft>(() => emptyDraft("motion"));
  const latestOperations = useRef(false);
  latestOperations.current = submitting || Boolean(referenceUploadingKind || videoUploadingKind);
  const processedStartParam = useRef("");
  const refreshAbortRef = useRef<AbortController | null>(null);
  useLayoutEffect(() => subscribePaymentAccessRevoked(actorId => {
    if (latestActor.current !== actorId) return;
    latestActor.current = null;
    topupAbort.current?.abort(); topupCheckAbort.current?.abort(); refreshAbortRef.current?.abort();
    pendingTopupRef.current = null; setPendingTopup(null); setTopupChecked(null);
    setLilac(false); setUx2(false); setTaskOpen(false); setSelectedTask(null); setBalanceOpen(false);
    setData(null); setApi(null);
    publishStudioBalance(null);
    setErrorMessage("Сессия недоступна. Откройте приложение заново из бота."); setMode("locked");
  }), []);

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
    if (ux2 && data?.user.miniapp_ux2_available !== true) { setUx2(false); setLilac(false); setActiveTab("feed"); }
  }, [data?.user.miniapp_ux2_available, ux2]);

  const changePreview = (enabled: boolean) => {
    if (!data || data.user.miniapp_ux2_available !== true) return;
    if (photoQueue.hasPending()) { toast.info("Дождитесь завершения загрузки фото или отмените её в редакторе."); return; }
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
    setLilac(false);
    setActiveTab("feed");
  };

  const patchDraft = useCallback((kind: GenerationDraft["kind"], patcher: (current: GenerationDraft) => GenerationDraft) => {
    if (kind === "image") setImageDraft(patcher);
    else if (kind === "video") setVideoDraft(patcher);
    else setMotionDraft(patcher);
  }, []);

  const photoQueue = usePhotoUploads({
    owner: data?.user.id ?? null, enabled: ux2 && mode === "live", locked: submitting || Boolean(referenceUploadingKind || videoUploadingKind),
    drafts: { image: imageDraft, video: videoDraft, motion: motionDraft },
    models: { image: data?.imageModels || [], video: data?.videoModels || [] },
    update: patchDraft,
    policy: signal => api ? api.getPhotoUploadPolicy(signal) : Promise.reject(new Error("Unavailable")),
    upload: (file, signal) => api ? api.uploadMedia(file, signal) : Promise.reject(new Error("Unavailable")),
    notice: message => toast.info(message),
    emit: detail => window.dispatchEvent(new CustomEvent("apix:photo-upload", { detail })),
  });

  const resetPreset = useCallback((kind: GenerationDraft["kind"]) => {
    const saved = data ? readUserDrafts(tabStorage(), data.user.id)[kind] : undefined;
    patchDraft(kind, current => saved?.referenceMaterials !== undefined ? saved
      : { ...current, promptId: null, sourceTitle: "", prompt: "" });
  }, [data?.user.id, patchDraft]);

  const uploadReferenceFiles = useCallback(async (kind: GenerationDraft["kind"], files: File[]) => {
    const current = kind === "image" ? imageDraft : kind === "video" ? videoDraft : motionDraft;
    if (ux2 && current.promptId === null) { photoQueue.add(kind, files); return; }
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
  }, [api, patchDraft, referenceUploadingKind, ux2, photoQueue, imageDraft, videoDraft, motionDraft]);

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
      let admitted = false;
      if (lilacRequested(bootstrap.user, window.location.search)) {
        try { const admission = await client.request<{ allowed: boolean; ui_version: number }>("/studio/preview", { cache: "no-store" }); admitted = admission.allowed === true && admission.ui_version === 3; }
        catch { toast.error("Новая студия пока недоступна для этого аккаунта"); }
      }
      const preview = admitted || previewEnabled(bootstrap.user, window.location.search, savedPreview);
      setLilac(admitted);
      setUx2(preview);
      if (admitted) setActiveTab("home");
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

  const openLilac = async () => {
    if (!api || !data || data.user.miniapp_ux2_available !== true || previewBusy) return;
    if (photoQueue.hasPending()) { toast.info("Дождитесь завершения загрузки фото."); return; }
    const owner = data.user.id;
    setPreviewBusy(true);
    try {
      const admission = await api.request<{ allowed: boolean; ui_version: number }>("/studio/preview", { cache: "no-store" });
      if (latestActor.current !== owner || !admission.allowed || admission.ui_version !== 3) return;
      if (photoQueue.hasPending() || latestOperations.current) { toast.info("Дождитесь завершения текущей операции и откройте студию снова."); return; }
      const url = new URL(window.location.href); url.searchParams.set("ux", "3"); window.history.replaceState(window.history.state, "", url);
      const stored = readUserDrafts(tabStorage(), owner);
      setImageDraft(current => current.promptId === null && !hasDraftInput(current) && stored.image ? stored.image : current);
      setVideoDraft(current => current.promptId === null && !hasDraftInput(current) && stored.video ? stored.video : current);
      setMotionDraft(current => current.promptId === null && !hasDraftInput(current) && stored.motion ? stored.motion : current);
      setUx2(true); setLilac(true); setActiveTab("home");
    } catch (error) { toast.error(error instanceof Error ? error.message : "Не удалось открыть студию"); }
    finally { setPreviewBusy(false); }
  };

  const exitLilac = () => {
    if (photoQueue.hasPending()) { toast.info("Дождитесь завершения загрузки фото."); return; }
    const url = new URL(window.location.href); url.searchParams.set("ux", "1"); window.history.replaceState(window.history.state, "", url);
    setLilac(false); setUx2(false); setActiveTab("feed");
  };

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
      // Identity must take effect even if task history is temporarily unavailable.
      const user = await api.request<BootstrapData["user"]>("/me", { cache: "no-store" }, controller.signal);
      if (controller.signal.aborted) return;
      const ownerChanged = latestActor.current !== user.id;
      setData(current => current ? { ...current, user, ...(ownerChanged ? { recentTasks: [] } : {}) } : current);
      if (ownerChanged) { setTaskOpen(false); setSelectedTask(null); setBalanceOpen(false); }
      if (ownerChanged && lilac) { setLilac(false); setUx2(false); setMode("locked"); return; }
      if (user.miniapp_ux2_available !== true) {
        setLilac(false);
        setUx2(false);
        if (lilac || ux2) setActiveTab("feed");
      }
      const core = { user, recentTasks: await api.getRecentHistory(controller.signal) };
      if (controller.signal.aborted) return;
      setData((current) => {
        if (!current || current.user.id !== core.user.id) return current;
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
      if (error instanceof ApiError && [401, 403].includes(error.status)) {
        setLilac(false); setUx2(false); setTaskOpen(false); setBalanceOpen(false);
        setErrorMessage("Сессия недоступна. Откройте приложение заново из бота."); setMode("locked");
        return;
      }
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        console.warn("Mini App core refresh failed", error);
      }
    }
  }, [api, lilac, ux2]);

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

  const [referenceCheckVersion, setReferenceCheckVersion] = useState(0);
  const latestGenerationContext = useRef({ drafts: currentDraft, owner: data?.user.id, ux2 });
  latestGenerationContext.current = { drafts: currentDraft, owner: data?.user.id, ux2 };
  const checkReference = useCallback(async (url: string, signal: AbortSignal) => {
    if (!api) throw new Error("API unavailable");
    return parseReferenceAvailability(await api.checkReferenceAvailability(url, signal));
  }, [api, data?.user.id, referenceCheckVersion]);

  const submitGeneration = useCallback(async (kind: "image" | "video" | "motion", confirmed?: VideoConfirmation) => {
    if (!api || !data || submitting || submissionLock.current) return;
    const sourceDraft = currentDraft[kind];
    if (!isKling4(sourceDraft.model) && photoQueue.hasPending(kind)) return;
    const draft = selectGenerationInputs(sourceDraft);
    const hasSelection = !isKling4(sourceDraft.model) && sourceDraft.promptId === null && sourceDraft.referenceMaterials !== undefined;
    if ((ux2 || hasSelection) && draft.promptId === null) {
      if (!isKling4(draft.model) && (referenceUploadingKind === kind || videoUploadingKind === kind)) return;
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
    let checkingReferences = false;
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
      if (ux2 && sourceDraft.promptId === null && draft.referenceUrls.length) {
        checkingReferences = true;
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), REFERENCE_CHECK_TIMEOUT_MS);
        try {
          for (const item of referenceMaterials(sourceDraft).filter(item => item.included && item.url && !item.upload)) {
            const state = await checkReference(item.url, controller.signal);
            if (state !== "available") {
              // Invalidate transient row checks: the file may have disappeared
              // since the editor opened. A cached positive is not permission.
              setReferenceCheckVersion(value => value + 1);
              toast.error(referenceAvailabilityMessage(state, data.user.language === "en"));
              return;
            }
          }
        } finally { window.clearTimeout(timer); }
        const latest = latestGenerationContext.current;
        if (latest.owner !== data.user.id || !latest.ux2 || JSON.stringify(latest.drafts[kind]) !== JSON.stringify(sourceDraft)) {
          toast.info("Подготовка изменилась. Проверьте материалы и подтвердите запуск снова.");
          return;
        }
      }
      checkingReferences = false;
      checkingSelection = false;
      const prompt = draft.prompt.trim() || (draft.model.startsWith("higgsfield/genjutsu/") ? "" : "Использовать выбранный сценарий");
      const videoBody = {
        model: draft.model, prompt, prompt_id: draft.promptId, mode: draft.mode,
        duration: draft.duration, aspect_ratio: draft.aspectRatio, resolution: draft.resolution,
        image_url: draft.referenceUrls[0] || null, reference_urls: draft.referenceUrls,
        video_url: draft.videoUrl || null, video_start: draft.videoStart, video_end: draft.videoEnd,
        audio_ids: draft.audioIds, character_ids: draft.characterIds, seed: draft.seed,
        grok_mode: draft.grokMode || "normal",
        wan_audio: draft.wanAudio !== false,
        wan_nsfw_checker: draft.wanNsfwChecker !== false,
        wan_reference_video_urls: draft.wanReferenceVideoUrls || [],
        wan_reference_audio_urls: draft.wanReferenceAudioUrls || [],
        wan_reference_file_urls: draft.wanReferenceFileUrls || [],
        wan_reference_link_urls: draft.wanReferenceLinkUrls || [],
        wan_first_frame_url: draft.wanFirstFrameUrl || null,
        wan_last_frame_url: draft.wanLastFrameUrl || null,
        ...kling4Body(draft),
      };
      // Model-specific upload panels hold files outside GenerationDraft. Quote
      // every video launch so their enhancers can attach those files first.
      const needsVideoQuote = kind !== "image";
      let quotedCredits: number | undefined;
      if (needsVideoQuote) {
        const quote = await api.quoteVideo(videoBody);
        const bodyKey = JSON.stringify(videoBody);
        const latest = latestGenerationContext.current;
        if (latestActor.current !== data.user.id || latest.owner !== data.user.id || JSON.stringify(latest.drafts[kind]) !== JSON.stringify(sourceDraft)) return;
        if (!Number.isFinite(quote.cost_credits) || quote.cost_credits < 0 || !Number.isFinite(quote.balance_credits) || typeof quote.can_run !== "boolean") throw new Error("Стоимость видео недоступна. Повторите попытку.");
        if (!quote.can_run || quote.balance_credits < quote.cost_credits * taskCount || !confirmed || confirmed.owner !== data.user.id || confirmed.kind !== kind
            || confirmed.bodyKey !== bodyKey || confirmed.quote.cost_credits !== quote.cost_credits
            || confirmed.count !== taskCount) {
          setVideoConfirmation({ kind, bodyKey, owner: data.user.id, quote, count: taskCount });
          if (confirmed) toast.info("Цена или параметры изменились. Проверьте расчёт ещё раз.");
          return;
        }
        quotedCredits = quote.cost_credits;
        setVideoConfirmation(null);
      }
      for (let index = 0; index < taskCount; index += 1) {
        const intent = isKling4(draft.model) ? await kling4Intent(videoBody, data.user.id, index) : null;
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
          : await api.createVideo({ ...videoBody, quoted_credits: quotedCredits, ...(intent ? { intent_id: intent.id } : {}) });
        intent?.clear();
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
      if (latestActor.current === data.user.id && isInsufficientCreditError(error)) {
        toast.error("Недостаточно кредитов. Пополни баланс, затем вернись и подтверди запуск.", { action: { label: "Пополнить", onClick: () => { if (latestActor.current === data.user.id) setBalanceOpen(true); } } });
        return;
      }
      const prefix = createdTasks.length ? `Создано ${createdTasks.length}, дальше ошибка: ` : "";
      if (checkingReferences) setReferenceCheckVersion(value => value + 1);
      toast.error(checkingReferences ? "Не удалось проверить файлы. Запуск не отправлен, материалы сохранены."
        : checkingSelection
        ? "Не удалось проверить актуальные условия. Запуск не отправлен, материалы сохранены. Повторите проверку."
        : `${prefix}${error instanceof Error ? error.message : "Не удалось создать задачу"}`);
    } finally {
      submissionLock.current = false;
      setSubmitting(false);
    }
  }, [api, currentDraft, data, refreshCore, submitting, ux2, referenceUploadingKind, videoUploadingKind, photoQueue, checkReference]);

  useEffect(() => {
    const wasOpen = previousBalanceOpen.current;
    previousBalanceOpen.current = balanceOpen;
    if (!videoConfirmation) return;
    if (balanceOpen) { setVideoQuoteRefreshing(true); return; }
    if (wasOpen && videoConfirmation.owner === latestActor.current) {
      // Resume only recalculates. Passing no confirmation cannot create a video.
      setVideoQuoteRefreshing(true);
      setVideoConfirmation(null);
      void submitGeneration(videoConfirmation.kind).finally(() => setVideoQuoteRefreshing(false));
    }
  }, [balanceOpen, videoConfirmation, submitGeneration]);

  useEffect(() => {
    if (videoConfirmation && (mode !== "live" || videoConfirmation.owner !== data?.user.id)) setVideoConfirmation(null);
  }, [data?.user.id, mode, videoConfirmation]);

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

  const remixFeed = useCallback(async (item: FeedItem, sourceMediaUrl?: string) => {
    if (!api || remixingId) return;
    setRemixingId(item.id);
    try {
      const task = await api.remixFeedItem(item, sourceMediaUrl);
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
    const owner = latestActor.current;
    const nextHistory = [...assistantMessages, { role: "user" as const, text: message }];
    setAssistantMessages(nextHistory);
    setAssistantBusy(true);
    try {
      const reply = await api.sendAssistant(message, assistantMessages);
      setAssistantMessages((current) => [...current, { role: "assistant", text: reply }]);
    } catch (error) {
      if (owner === latestActor.current) creditErrorToast(error, "Помощник временно недоступен", () => { if (owner === latestActor.current) setBalanceOpen(true); });
    } finally {
      setAssistantBusy(false);
    }
  }, [api, assistantBusy, assistantMessages]);

  const createPhotoPrompt = useCallback(async (file: File) => {
    if (!api || photoPromptBusy) return;
    const owner = latestActor.current;
    setPhotoPromptBusy(true);
    setPhotoPromptResult(null);
    try {
      const result = await api.photoPrompt(file);
      setPhotoPromptResult(result);
      toast.success("Промпт готов");
    } catch (error) {
      if (owner === latestActor.current) creditErrorToast(error, "Не удалось проанализировать фото", () => { if (owner === latestActor.current) setBalanceOpen(true); });
    } finally {
      setPhotoPromptBusy(false);
    }
  }, [api, photoPromptBusy]);

  const createVideoPrompt = useCallback(async (file: File) => {
    if (!api || videoPromptBusy) return;
    const owner = latestActor.current;
    setVideoPromptBusy(true);
    setVideoPromptResult(null);
    try {
      const result = await api.videoPrompt(file);
      setVideoPromptResult(result);
      toast.success("Видео-промпт готов");
    } catch (error) {
      if (owner === latestActor.current) creditErrorToast(error, "Не удалось проанализировать видео", () => { if (owner === latestActor.current) setBalanceOpen(true); });
    } finally {
      setVideoPromptBusy(false);
    }
  }, [api, videoPromptBusy]);

  const pay = useCallback(async (provider: "tbank" | "crypto" | "tribute" | "lava", plan: PaymentPlan) => {
    if (!api || !data || latestActor.current !== data.user.id || paymentRequest.current) return;
    const owner = data.user.id;
    if (pendingTopupRef.current || readPendingTopup(topupStorage(), owner)) return;
    paymentRequest.current = true; setPaymentBusy(true); setPaymentError("");
    const controller = new AbortController(); topupAbort.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const [plans, providers, options] = await Promise.all([api.request<PaymentPlan[]>("/plans", {}, controller.signal), api.request<string[]>("/payment-methods", {}, controller.signal), api.request<{ lava_plan_keys?: string[] }>("/payment-options", {}, controller.signal)]);
      if (latestActor.current !== owner || controller.signal.aborted) return;
      if (!Array.isArray(plans) || !Array.isArray(providers)) throw new Error("Не удалось проверить условия оплаты. Обновите баланс.");
      const keys = Array.isArray(options.lava_plan_keys) ? options.lava_plan_keys : [];
      const fresh = plans.find(row => row.key === plan.key);
      setData(current => current?.user.id === owner ? { ...current, paymentPlans: plans, paymentMethods: providers, lavaPlanKeys: keys } : current);
      if (!fresh || !providers.includes(provider) || !supportsPlan(provider, fresh, keys)) throw new Error("Этот способ оплаты больше не доступен для пакета. Выберите другой.");
      if (fresh.credits !== plan.credits || checkoutPrice(provider, fresh) !== checkoutPrice(provider, plan)) throw new Error("Условия пакета изменились. Проверьте новую цену и количество кредитов перед оплатой.");
      // Another entry can create an invoice while this cabinet awaits preflight.
      // Adopt it; checking and claiming below must have no asynchronous gap.
      const existing = readPendingTopup(topupStorage(), owner);
      if (existing) {
        pendingTopupRef.current = existing; setPendingTopup(existing); setTopupChecked(null);
        return;
      }
      const pending: RepeatPayment = { startedAt: Date.now(), provider, planKey: plan.key, transactionId: null, checkoutUrl: null };
      if (!savePendingTopup(topupStorage(), owner, pending)) throw new Error("Не удалось сохранить защиту оплаты. Разрешите хранилище браузера и повторите попытку.");
      pendingTopupRef.current = pending; setPendingTopup(pending); setTopupChecked(null);
      let result: Record<string, unknown>;
      try { result = await api.createPayment(provider, plan.key, controller.signal); }
      catch (error) {
        if (error instanceof ApiError && [401, 403].includes(error.status)) throw error;
        if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408) {
          if (clearPendingTopup(topupStorage(), owner, pending) && latestActor.current === owner) { pendingTopupRef.current = null; setPendingTopup(null); }
        }
        throw error;
      }
      if (latestActor.current !== owner || controller.signal.aborted) return;
      const identified = paymentFromResponse(pending, result);
      if (!savePendingTopup(topupStorage(), owner, identified)) throw new Error("Не удалось сохранить номер оплаты. Проверьте её статус перед новой попыткой.");
      pendingTopupRef.current = identified; setPendingTopup(identified);
      const url = identified.checkoutUrl;
      if (!url) throw new Error("Платёжная ссылка не получена");
      openExternalUrl(url);
    } catch (error) {
      if (latestActor.current === owner && error instanceof ApiError && [401, 403].includes(error.status)) {
        revokePaymentAccess(owner); return;
      }
      if (latestActor.current === owner) setPaymentError(controller.signal.aborted ? "Время ожидания истекло. Если счёт уже отправлен, проверьте оплату перед новой попыткой." : error instanceof Error ? error.message : "Не удалось создать платёж. Проверьте историю платежей перед повтором.");
    } finally {
      window.clearTimeout(timeout);
      if (topupAbort.current === controller) topupAbort.current = null;
      paymentRequest.current = false; setPaymentBusy(false);
    }
  }, [api, data]);

  const checkTopup = async () => {
    const pending = pendingTopupRef.current, owner = latestActor.current;
    if (!api || !pending || !owner || topupChecking) return;
    setTopupChecking(true); setTopupChecked(null);
    const controller = new AbortController(); topupCheckAbort.current = controller;
    const timeout = window.setTimeout(() => controller.abort(), 15_000);
    try {
      const history = await api.requestWeb<{ transactions: unknown[] }>("/billing/transactions?limit=100", {}, controller.signal);
      if (latestActor.current !== owner || pendingTopupRef.current !== pending || controller.signal.aborted) return;
      if (!Array.isArray(history.transactions)) throw new Error("История оплаты недоступна. Повторите проверку позже.");
      const resolution = paymentResolution(pending, history.transactions);
      if (resolution === "pending") {
        setTopupChecked(pending);
        setPaymentError("Платёж пока не подтверждён. Отсутствие записи в последних операциях не означает отмену платежа.");
      } else {
        if (!clearPendingTopup(topupStorage(), owner, pending)) throw new Error("Текущая оплата изменилась. Закройте и откройте кабинет для новой проверки.");
        pendingTopupRef.current = null; setPendingTopup(null);
        setPaymentError(resolution === "paid" ? "Оплата подтверждена. Закройте окно, проверьте новую стоимость и подтвердите запуск."
          : resolution === "failed" ? "Платёж завершился ошибкой. Можно выбрать новое пополнение." : "Платёж возвращён. Можно выбрать новое пополнение.");
        void refreshCore();
      }
    } catch (error) {
      if (latestActor.current === owner && error instanceof ApiError && [401, 403].includes(error.status)) {
        revokePaymentAccess(owner); return;
      }
      if (latestActor.current === owner && pendingTopupRef.current === pending) setPaymentError(error instanceof Error ? error.message : "Не удалось проверить оплату");
    } finally { window.clearTimeout(timeout); if (topupCheckAbort.current === controller) topupCheckAbort.current = null; if (latestActor.current === owner) setTopupChecking(false); }
  };

  const acknowledgeTopup = () => {
    const pending = pendingTopupRef.current, owner = latestActor.current;
    if (!owner || !pending || pending !== topupChecked || pending.transactionId || topupChecking) return;
    if (!clearPendingTopup(topupStorage(), owner, pending)) { setPaymentError("Текущая оплата изменилась. Откройте кабинет ещё раз."); return; }
    pendingTopupRef.current = null; setPendingTopup(null); setTopupChecked(null);
    setPaymentError("Статус прошлой оплаты остаётся неизвестным. Новый счёт создаётся только по вашему нажатию.");
  };

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

  const navigateStudio = (tab: AppTab) => {
    // The quick action promises photo-to-video, not a generic text-only form.
    if (tab === "video" && videoDraft.promptId === null && !hasDraftInput(videoDraft) && !photoQueue.hasPending()) {
      const model = data.videoModels.find(row => row.key === videoDraft.model && row.modes?.includes("image")) || data.videoModels.find(row => row.modes?.includes("image"));
      if (model) setVideoDraft(current => ({ ...switchDraftModel(current, model), mode: "image" }));
    }
    setActiveTab(tab);
  };
  const studioWorks = <>{lilac && api && <LilacImageSeries key={data.user.id} api={api} models={data.imageModels} onContinue={series => {
        if (photoQueue.hasPending()) { toast.info("Дождитесь завершения загрузки фото."); return; }
        const model = data.imageModels.find(row => row.key === series.model);
        if (!model) { toast.error("Модель серии недоступна. Исходный черновик сохранён."); return; }
        const draft = { ...emptyDraft("image"), model: model.key, mode: series.mode, aspectRatio: series.aspect_ratio || imageDraft.aspectRatio, quality: series.quality, count: series.count, prompt: series.prompt_hidden || series.prompt_actions_allowed === false ? (imageDraft.promptId === null ? imageDraft.prompt : "") : series.last_prompt || series.base_prompt || "" };
        setImageDraft(appendReferenceUrls(draft, Array.from(new Set([series.reference_url, ...(series.reference_urls || [])].filter((url): url is string => Boolean(url))))));
        setActiveTab("photo");
      }} />}<WorksScreen tasks={data.recentTasks} models={[...data.imageModels, ...data.videoModels]} language={data.user.language} unavailable={data.historyUnavailable} refreshing={worksRefreshing} onOpenTask={openTask} onCreate={() => setActiveTab("create")} onRefresh={() => void refreshWorks()} /></>;
  const screen = (() => {
    if (lilac && api) {
      if (activeTab === "home") return <LilacHome data={data} drafts={[imageDraft, videoDraft, motionDraft]} onNavigate={navigateStudio} onTask={openTask} />;
      if (activeTab === "create") return <LilacCreate onNavigate={navigateStudio} />;
      if (activeTab === "ideas") return <LilacIdeas onNavigate={setActiveTab} />;
      if (activeTab === "assistant") return <LilacAssistant messages={assistantMessages} busy={assistantBusy} onSend={message => void sendAssistant(message)} />;
      if (activeTab === "music") return <div className="lilac-page"><header className="lilac-title"><p>Музыка и собственные голоса</p><h1>Создать музыку</h1><span>Выберите модель, опишите звучание и проверьте стоимость.</span></header><MusicSunoPanel key={data.user.id} audioToolsApi={api} initialModel={musicModel} initialPrompt={musicPrompt} onInitialPromptConsumed={consumeMusicPrompt} onBalanceOpen={() => { if (latestActor.current === data.user.id) setBalanceOpen(true); }} onCreated={task => { if (latestActor.current !== data.user.id) return; setData(current => current ? { ...current, recentTasks: [task, ...current.recentTasks.filter(row => row.id !== task.id)] } : current); openTask(task); void refreshCore(); }} /></div>;
      if (activeTab === "models") return <LilacModels api={api} imageModels={data.imageModels} videoModels={data.videoModels} onSelect={(model, kind) => {
        if (photoQueue.hasPending() || referenceUploadingKind || videoUploadingKind || submitting) { toast.info("Дождитесь завершения текущей операции."); return; }
        if (kind === "music") { setMusicModel(model.key); setActiveTab("music"); return; }
        const target = kind === "image" ? "image" : model.modes?.includes("motion") ? "motion" : "video";
        const draft = target === "image" ? imageDraft : target === "video" ? videoDraft : motionDraft;
        if (draft.promptId !== null) toast.info("Параметры шаблона закреплены. Сначала сбросьте шаблон в редакторе, чтобы сменить модель.");
        else patchDraft(target, current => switchDraftModel(current, model));
        setActiveTab(target === "image" ? "photo" : target);
      }} />;
      if (activeTab === "library") return <LilacLibrary key={data.user.id} api={api} onUse={async (prompt: LibraryPrompt, signal) => {
        if (photoQueue.hasPending() || referenceUploadingKind || videoUploadingKind || submitting) throw new Error("Дождитесь завершения текущей операции. Черновики сохранены.");
        const alive = () => !signal.aborted && latestActor.current === data.user.id;
        if (prompt.tags?.some(tag => tag.trim().toLowerCase() === "trend")) {
          const trend = await api.request<TrendItem>(`/trends/${prompt.id}`, {}, signal);
          if (!trend || trend.id !== prompt.id || !["image", "video"].includes(trend.kind)) throw new Error("Этот тренд сейчас недоступен.");
          if (alive()) openTrendRunner(trend); return;
        }
        const image = prompt.model ? data.imageModels.find(row => row.key === prompt.model) : data.imageModels.find(row => row.key === imageDraft.model) || data.imageModels[0];
        const video = prompt.model ? data.videoModels.find(row => row.key === prompt.model) : undefined;
        if (image || video) {
          const model = (image || video)!; const target = image ? "image" : model.modes?.includes("motion") ? "motion" : "video";
          if (alive()) { patchDraft(target, current => ({ ...selectGenerationInputs(switchDraftModel({ ...current, promptId: null }, model)), promptId: prompt.id, prompt: prompt.prompt_text || "Использовать задание из библиотеки", sourceTitle: prompt.title })); setActiveTab(target === "image" ? "photo" : target); }
          return;
        }
        const music = await api.request<ModelInfo[]>("/models/music", {}, signal);
        if (!Array.isArray(music) || !music.some(row => row.key === prompt.model)) throw new Error("Модель этого задания сейчас недоступна. Выберите другую идею; черновики сохранены.");
        if (!prompt.prompt_text?.trim()) throw new Error("Закрытый музыкальный шаблон нельзя перенести в свободный редактор. Выберите задание с открытым текстом.");
        if (alive()) { setMusicModel(prompt.model!); setMusicPrompt(prompt.prompt_text); setActiveTab("music"); }
      }} />;
      if (activeTab === "help") return <LilacHelp api={api} onNavigate={setActiveTab} />;
      if (activeTab === "billing") return <LilacBilling api={api} user={data.user} onTopup={() => setBalanceOpen(true)} />;
      if (activeTab === "owner" && data.user.miniapp_ux2_available === true) return <LilacOwner key={data.user.id} api={api} ownerId={data.user.id} systemPanel={<LilacAdminSystemPanel api={api} ownerId={data.user.id} />} />;
      if (activeTab === "account") return <LilacAccountEditor key={data.user.id} api={api} ownerId={data.user.id} onSaved={() => void refreshCore()} />;
    }
    if (ux2 && activeTab === "create") {
      return <CreateScreen imageModels={data.imageModels} videoModels={data.videoModels} drafts={[imageDraft, videoDraft, motionDraft]} language={data.user.language} onNavigate={setActiveTab} />;
    }
    if (ux2 && activeTab === "works") return studioWorks;
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
          onRemix={(item, sourceMediaUrl) => void remixFeed(item, sourceMediaUrl)}
        />
      );
    }
    if (activeTab === "photo") {
      return <GenerationScreen checkReference={ux2 ? checkReference : undefined} ux2={ux2} kind="image" user={data.user} models={data.imageModels} draft={imageDraft} submitting={submitting} referenceUploading={referenceUploadingKind === "image" || photoUploading(imageDraft)} photoUploads={ux2 && imageDraft.promptId === null ? photoQueue.controls("image") : undefined} videoUploading={videoUploadingKind === "image"} onChange={(patch) => setImageDraft((current) => applyDraftPatch(current, patch))} onUploadReferenceFiles={(files) => void uploadReferenceFiles("image", files)} onUploadVideoFile={(file) => void uploadVideoFile("image", file)} onSubmit={() => void submitGeneration("image")} onResetPreset={() => resetPreset("image")} />;
    }
    if (activeTab === "video") {
      return <GenerationScreen checkReference={ux2 ? checkReference : undefined} ux2={ux2} kind="video" user={data.user} models={data.videoModels} draft={videoDraft} submitting={submitting} referenceUploading={referenceUploadingKind === "video" || photoUploading(videoDraft)} photoUploads={ux2 && videoDraft.promptId === null ? photoQueue.controls("video") : undefined} videoUploading={videoUploadingKind === "video"} onChange={(patch) => setVideoDraft((current) => applyDraftPatch(current, patch))} onUploadReferenceFiles={(files) => void uploadReferenceFiles("video", files)} onUploadVideoFile={(file) => void uploadVideoFile("video", file)} onUploadKling4={file => api!.uploadKling4Asset(file, data.user.id)} onQuoteWan={quoteWan} onSubmit={() => void submitGeneration("video")} onResetPreset={() => resetPreset("video")} />;
    }
    if (activeTab === "motion") {
      return <GenerationScreen checkReference={ux2 ? checkReference : undefined} ux2={ux2} kind="motion" user={data.user} models={data.videoModels} draft={motionDraft} submitting={submitting} referenceUploading={referenceUploadingKind === "motion" || photoUploading(motionDraft)} photoUploads={ux2 && motionDraft.promptId === null ? photoQueue.controls("motion") : undefined} videoUploading={videoUploadingKind === "motion"} onChange={(patch) => setMotionDraft((current) => applyDraftPatch(current, patch))} onUploadReferenceFiles={(files) => void uploadReferenceFiles("motion", files)} onUploadVideoFile={(file) => void uploadVideoFile("motion", file)} onSubmit={() => void submitGeneration("motion")} onResetPreset={() => resetPreset("motion")} />;
    }
    if (activeTab === "trends") {
      return <TrendsScreen items={data.trends} filter={trendsFilter} loading={trendsLoading} preparingId={preparingTrendId} onFilterChange={setTrendsFilter} onRefresh={() => void loadTrends()} onPrepare={(trend) => void prepareTrend(trend)} />;
    }
    if (activeTab === "services") {
      return <ServicesScreen lilac={lilac} onBalanceOpen={() => { if (latestActor.current === data.user.id) setBalanceOpen(true); }} messages={assistantMessages} assistantBusy={assistantBusy} photoPromptBusy={photoPromptBusy} photoPromptResult={photoPromptResult} videoPromptBusy={videoPromptBusy} videoPromptResult={videoPromptResult} onAssistantSend={(message) => void sendAssistant(message)} onPhotoPrompt={(file) => void createPhotoPrompt(file)} onVideoPrompt={(file) => void createVideoPrompt(file)} onUsePrompt={(prompt) => { setImageDraft((current) => ({ ...current, prompt, promptId: null, sourceTitle: "" })); setActiveTab("photo"); }} onUseVideoPrompt={(prompt) => { setVideoDraft((current) => ({ ...current, prompt, promptId: null, sourceTitle: "" })); setActiveTab("video"); }} onNavigate={setActiveTab} />;
    }
    if (activeTab === "settings") {
      return <SettingsScreen previewEnabled={ux2} onPreviewChange={changePreview} user={data.user} busy={languageBusy} onLanguageChange={(language) => void changeLanguage(language)} onResetApp={() => void initialize()} />;
    }
    return (
      <ProfileScreen
        worksSection={lilac ? studioWorks : undefined}
        quickActions={ux2 ? <>
          {lilac && <Button variant="outline" onClick={() => setActiveTab("billing")}><CreditCard aria-hidden="true" />Баланс и платежи</Button>}
          {lilac && <Button variant="outline" onClick={() => setActiveTab("library")}><BookOpenText aria-hidden="true" />Мои промпты</Button>}
          {lilac && <Button variant="outline" onClick={() => setActiveTab("help")}><CircleHelp aria-hidden="true" />Помощь</Button>}
          {lilac && <Button variant="outline" onClick={() => setActiveTab("account")}><UserRoundCog aria-hidden="true" />Редактировать профиль</Button>}
          <Button variant="outline" onClick={() => setActiveTab("settings")}><Settings aria-hidden="true" />{data.user.language === "en" ? "Settings" : "Настройки"}</Button>
          {lilac && data.user.miniapp_ux2_available === true && <Button variant="outline" onClick={() => setActiveTab("owner")}><ShieldCheck aria-hidden="true" />Управление APIX</Button>}
        </> : undefined}
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
      <AppShell ux2={ux2} lilac={lilac} previewBusy={previewBusy} onNewStudio={() => void openLilac()} onExitStudio={exitLilac} activeTab={showFeed ? "feed" : activeTab} user={data.user} onTabChange={setActiveTab} onBalanceOpen={() => setBalanceOpen(true)}>
        {ux2 && draftStorageUnavailable && <div className="ux2-inline-notice" role="status">{data.user.language === "en" ? "Browser storage is unavailable. Keep this tab open to retain your draft." : "Хранилище браузера недоступно. Не закрывайте вкладку, чтобы не потерять черновик."}</div>}
        {screen}
      </AppShell>
      <TaskDetailSheet confirmPublicActions={lilac} task={selectedTask} open={taskOpen} busy={taskBusy} onOpenChange={setTaskOpen} onRefresh={(task) => void refreshTask(task)} onShare={(task) => void toggleTaskShare(task)} onToggleLibrary={(task) => void toggleTaskLibrary(task)}
      onDownload={lilac && api ? async (task, signal) => { const file = await api.downloadGeneration(task.id, signal); if (!signal.aborted && latestActor.current === data.user.id) saveDownload(file); } : undefined}
      onCopyLink={lilac && api ? async (task, signal) => { if (!task.is_public_feed) throw new Error("Сначала опубликуйте работу явно."); const result = await api.request<{ link: string }>(`/feed/${task.id}/link`, {}, signal); const link = safeExternalUrl(result.link); if (!link) throw new Error("Сервер не вернул ссылку на работу."); if (!signal.aborted && latestActor.current === data.user.id) await navigator.clipboard.writeText(link); } : undefined}
      onAnimate={lilac ? url => {
        if (photoQueue.hasPending() || videoUploadingKind || referenceUploadingKind || submitting) { toast.info("Дождитесь завершения текущей операции."); return; }
        if (videoDraft.promptId !== null) { toast.info("Сначала сбросьте шаблон в видеоредакторе. Ваш черновик сохранён."); return; }
        const model = data.videoModels.find(row => row.key === videoDraft.model && row.modes?.includes("image")) || data.videoModels.find(row => row.modes?.includes("image"));
        if (!model) { toast.info("Сейчас нет доступной модели видео по фото."); return; }
        setVideoDraft(current => appendReferenceUrls({ ...switchDraftModel(current, model), mode: "image" }, [url]));
        setTaskOpen(false); setActiveTab("video"); toast.info("Фото добавлено. Опишите движение и проверьте материалы перед запуском.");
      } : undefined} onReuse={lilac ? task => {
        if (photoQueue.hasPending()) { toast.info("Дождитесь завершения загрузки фото."); return; }
        if (!task.prompt || task.prompt_hidden || task.prompt_actions_allowed === false) return;
        const kind = task.gen_type === "video" ? "video" : "image";
        patchDraft(kind, current => ({ ...current, prompt: task.prompt!, promptId: null, sourceTitle: "" }));
        setTaskOpen(false); setActiveTab(kind === "image" ? "photo" : "video"); toast.info("Задание скопировано. Проверьте модель и исходные материалы перед запуском.");
      } : undefined} />
      <BalanceSheet open={balanceOpen} user={data.user} plans={data.paymentPlans} availableProviders={data.paymentMethods} lavaPlanKeys={data.lavaPlanKeys} busy={paymentBusy} error={paymentError} onOpenChange={setBalanceOpen} onPay={(provider, plan) => void pay(provider, plan)}
        pending={Boolean(pendingTopup)} checking={topupChecking} onCheck={() => void checkTopup()}
        onReopen={pendingTopup && canReopenPayment(pendingTopup) ? () => { if (pendingTopupRef.current === pendingTopup) openExternalUrl(pendingTopup.checkoutUrl!); } : undefined}
        onAcknowledge={pendingTopup && !pendingTopup.transactionId && topupChecked === pendingTopup ? acknowledgeTopup : undefined} />
      <Sheet balanceUnavailableReason={submitting ? "Дождитесь проверки стоимости." : undefined} open={Boolean(videoConfirmation)} title="Стоимость видео" description="Проверьте стоимость перед запуском" onOpenChange={(open) => { if (!open) setVideoConfirmation(null); }} footer={
        <Button className="w-full" disabled={submitting || videoQuoteRefreshing || !videoConfirmation?.quote.can_run || videoConfirmation.quote.balance_credits < videoConfirmation.quote.cost_credits * videoConfirmation.count} onClick={() => { if (videoConfirmation) void submitGeneration(videoConfirmation.kind, videoConfirmation); }}>
          {submitting ? "Проверяем цену…" : `Запустить за ${(videoConfirmation?.quote.cost_credits || 0) * (videoConfirmation?.count || 1)} 💋`}
        </Button>
      }>
        {videoConfirmation && <div className="grid gap-2 text-sm">
          <p>Видеореференсы: {videoConfirmation.quote.reference_seconds} сек</p>
          <p>Результат: {videoConfirmation.quote.output_seconds} сек</p>
          <p>К оплате: <strong>{videoConfirmation.quote.cost_credits} 💋 за задачу</strong></p>
          <p>Баланс: {videoConfirmation.quote.balance_credits} 💋</p>
          {videoConfirmation.quote.balance_credits < videoConfirmation.quote.cost_credits * videoConfirmation.count && <p>Не хватает: {Math.max(0, videoConfirmation.quote.cost_credits * videoConfirmation.count - videoConfirmation.quote.balance_credits)} 💋</p>}
          {videoQuoteRefreshing && <p role="status">Обновляем стоимость. Запуск нужно подтвердить отдельно.</p>}
          {!lilac && <Button variant="outline" disabled={submitting} onClick={() => setBalanceOpen(true)}>Пополнить</Button>}
          {videoConfirmation.count > 1 && <p>Всего задач: {videoConfirmation.count}</p>}
        </div>}
      </Sheet>
      <Toaster className="apix-toaster" richColors position="top-center" closeButton />
    </>
  );
}

export { App };
