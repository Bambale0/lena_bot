import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Toaster, toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { BalanceSheet } from "@/components/balance-sheet";
import { LockedScreen } from "@/components/locked-screen";
import { TaskDetailSheet } from "@/components/task-detail-sheet";
import { FeedScreen } from "@/features/feed-screen";
import { GenerationScreen } from "@/features/generation-screen";
import { ProfileScreen } from "@/features/profile-screen";
import { ServicesScreen } from "@/features/services-screen";
import { StudioScreen } from "@/features/studio-screen";
import { TrendsScreen } from "@/features/trends-screen";
import { ApiError, MiniAppApi } from "@/lib/api";
import {
  configureTelegramWebApp,
  haptic,
  notifyHaptic,
  openExternalUrl,
  openTelegramInvoice,
  parseStartTarget,
  readStartParam,
  waitForTelegramInitData,
} from "@/lib/telegram";
import type {
  AppMode,
  AppTab,
  AssistantMessage,
  BootstrapData,
  FeedItem,
  GenerationDraft,
  GenerationTask,
  PaymentPlan,
  PhotoPromptResult,
  PreparedTrend,
  ReferralStats,
  TrendItem,
} from "@/lib/types";
import { asRecord, firstMedia, isPendingTask } from "@/lib/utils";

window.__APIX_MINIAPP_BUILD_ID__ = "20260802-shadcn-shell-v1";

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
    mode: kind === "motion" ? "video" : "text",
    duration: 5,
    resolution: "720p",
    referenceUrls: [],
    videoUrl: "",
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

function App() {
  const [mode, setMode] = useState<AppMode>("booting");
  const [errorMessage, setErrorMessage] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [botUsername, setBotUsername] = useState("");
  const [api, setApi] = useState<MiniAppApi | null>(null);
  const [data, setData] = useState<BootstrapData | null>(null);
  const [activeTab, setActiveTab] = useState<AppTab>("studio");
  const [selectedTask, setSelectedTask] = useState<GenerationTask | null>(null);
  const [taskOpen, setTaskOpen] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const [balanceOpen, setBalanceOpen] = useState(false);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedSource, setFeedSource] = useState<"recent" | "top_day" | "top">("recent");
  const [feedLoading, setFeedLoading] = useState(false);
  const [trendsFilter, setTrendsFilter] = useState<"all" | "image" | "video">("all");
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [preparingTrendId, setPreparingTrendId] = useState<number | null>(null);
  const [referrals, setReferrals] = useState<ReferralStats | null>(null);
  const [referralsLoading, setReferralsLoading] = useState(false);
  const [assistantMessages, setAssistantMessages] = useState<AssistantMessage[]>([]);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [photoPromptBusy, setPhotoPromptBusy] = useState(false);
  const [photoPromptResult, setPhotoPromptResult] = useState<PhotoPromptResult | null>(null);
  const [imageDraft, setImageDraft] = useState<GenerationDraft>(() => emptyDraft("image"));
  const [videoDraft, setVideoDraft] = useState<GenerationDraft>(() => emptyDraft("video"));
  const [motionDraft, setMotionDraft] = useState<GenerationDraft>(() => emptyDraft("motion"));
  const processedStartParam = useRef("");

  const hydrateDraftDefaults = useCallback((bootstrap: BootstrapData) => {
    const firstImage = bootstrap.imageModels[0];
    const firstVideo = bootstrap.videoModels.find((model) => !/motion-control/i.test(model.key)) || bootstrap.videoModels[0];
    const firstMotion = bootstrap.videoModels.find((model) => /motion/i.test(`${model.key} ${model.display_name}`));
    setImageDraft((current) => ({
      ...current,
      model: current.model || firstImage?.key || "",
      mode: firstImage?.modes?.[0] || current.mode,
      aspectRatio: firstImage?.aspect_ratios?.[0] || current.aspectRatio,
      quality: firstImage?.quality_options?.[0]?.value || current.quality,
      count: firstImage?.counts?.[0] || current.count,
    }));
    setVideoDraft((current) => ({
      ...current,
      model: current.model || firstVideo?.key || "",
      mode: firstVideo?.modes?.[0] || current.mode,
      aspectRatio: firstVideo?.aspect_ratios?.[0] || current.aspectRatio,
      duration: firstVideo?.duration_options?.[0] || current.duration,
      resolution: firstVideo?.resolution_options?.[0] || current.resolution,
    }));
    setMotionDraft((current) => ({
      ...current,
      model: current.model || firstMotion?.key || "",
      mode: "video",
      aspectRatio: firstMotion?.aspect_ratios?.[0] || current.aspectRatio,
      duration: firstMotion?.duration_options?.[0] || current.duration,
      resolution: firstMotion?.resolution_options?.[0] || current.resolution,
    }));
  }, []);

  const applyPreparedTrend = useCallback((prepared: PreparedTrend) => {
    const settings = prepared.settings || {};
    if (prepared.kind === "video") {
      setVideoDraft((current) => ({
        ...current,
        model: prepared.model,
        prompt: "Использовать скрытый трендовый промпт",
        promptId: prepared.prompt_id,
        sourceTitle: prepared.title,
        mode: stringSetting(settings, "scenario", current.mode),
        aspectRatio: stringSetting(settings, "ratio", current.aspectRatio),
        duration: numberSetting(settings, "duration", current.duration),
        resolution: stringSetting(settings, "resolution", current.resolution),
      }));
      setActiveTab("video");
    } else {
      setImageDraft((current) => ({
        ...current,
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
            ...current,
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
      hydrateDraftDefaults(bootstrap);
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
    const controller = new AbortController();
    try {
      const core = await api.refreshCore(controller.signal);
      setData((current) => (current ? { ...current, ...core } : current));
      setSelectedTask((current) => {
        if (!current) return current;
        return core.recentTasks.find((task) => task.id === current.id) || current;
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        console.warn("Mini App core refresh failed", error);
      }
    }
    return () => controller.abort();
  }, [api]);

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
    if (activeTab !== "profile" || !api || referrals || referralsLoading) return;
    setReferralsLoading(true);
    api.getReferrals()
      .then(setReferrals)
      .catch((error) => toast.error(error instanceof Error ? error.message : "Не удалось загрузить партнёрскую статистику"))
      .finally(() => setReferralsLoading(false));
  }, [activeTab, api, referrals, referralsLoading]);

  const openTask = useCallback((task: GenerationTask) => {
    setSelectedTask(task);
    setTaskOpen(true);
  }, []);

  const currentDraft = useMemo(() => ({ image: imageDraft, video: videoDraft, motion: motionDraft }), [imageDraft, motionDraft, videoDraft]);

  const submitGeneration = useCallback(async (kind: "image" | "video" | "motion") => {
    if (!api || !data || submitting) return;
    const draft = currentDraft[kind];
    setSubmitting(true);
    try {
      const prompt = draft.prompt.trim() || "Использовать выбранный сценарий";
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
            mode: kind === "motion" ? "video" : draft.mode,
            duration: draft.duration,
            aspect_ratio: draft.aspectRatio,
            resolution: draft.resolution,
            image_url: draft.referenceUrls[0] || null,
            reference_urls: draft.referenceUrls,
            video_url: draft.videoUrl || null,
          });
      setData((current) => current ? {
        ...current,
        recentTasks: [task, ...current.recentTasks.filter((item) => item.id !== task.id)],
      } : current);
      setSelectedTask(task);
      setTaskOpen(true);
      notifyHaptic("success");
      toast.success("Задача создана");
      void refreshCore();
    } catch (error) {
      notifyHaptic("error");
      toast.error(error instanceof Error ? error.message : "Не удалось создать задачу");
    } finally {
      setSubmitting(false);
    }
  }, [api, currentDraft, data, refreshCore, submitting]);

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

  const loadFeed = useCallback(async (source = feedSource) => {
    if (!api || feedLoading) return;
    setFeedLoading(true);
    try {
      const feed = await api.getFeed(source);
      setData((current) => current ? { ...current, feed } : current);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось обновить ленту");
    } finally {
      setFeedLoading(false);
    }
  }, [api, feedLoading, feedSource]);

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
    if (!api || submitting) return;
    setSubmitting(true);
    try {
      const media = firstMedia(item);
      const video = item.gen_type === "video";
      const task = await api.remixFeed(item.id, {
        model: item.model,
        mode: video ? "video" : "image",
        duration: 5,
        aspect_ratio: item.aspect_ratio || (video ? "16:9" : "1:1"),
        resolution: "720p",
        source_image_url: video ? null : media,
        video_url: video ? media : null,
        reference_urls: [],
      });
      setData((current) => current ? { ...current, recentTasks: [task, ...current.recentTasks.filter((entry) => entry.id !== task.id)] } : current);
      openTask(task);
      toast.success("Повтор запущен");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось повторить работу");
    } finally {
      setSubmitting(false);
    }
  }, [api, openTask, submitting]);

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

  const pay = useCallback(async (provider: "stars" | "tbank" | "crypto" | "lava", plan: PaymentPlan) => {
    if (!api || paymentBusy) return;
    setPaymentBusy(true);
    try {
      const result = await api.createPayment(provider, plan.key);
      const url = String(result.invoice_link || result.invoice_url || result.pay_url || result.url || "");
      if (!url) throw new Error("Платёжная ссылка не получена");
      if (provider === "stars") {
        openTelegramInvoice(url, (status) => {
          if (status === "paid") {
            toast.success("Оплата прошла");
            setBalanceOpen(false);
            void refreshCore();
          } else if (status === "failed") toast.error("Оплата не прошла");
          else if (status === "cancelled") toast.info("Оплата отменена");
        });
      } else {
        openExternalUrl(url);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Не удалось создать платёж");
    } finally {
      setPaymentBusy(false);
    }
  }, [api, paymentBusy, refreshCore]);

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
    if (activeTab === "studio") {
      return <StudioScreen user={data.user} imageModels={data.imageModels} videoModels={data.videoModels} tasks={data.recentTasks} onNavigate={setActiveTab} onOpenTask={openTask} onBalanceOpen={() => setBalanceOpen(true)} />;
    }
    if (activeTab === "photo") {
      return <GenerationScreen kind="image" user={data.user} models={data.imageModels} draft={imageDraft} submitting={submitting} onChange={(patch) => setImageDraft((current) => ({ ...current, ...patch }))} onSubmit={() => void submitGeneration("image")} onResetPreset={() => setImageDraft((current) => ({ ...current, promptId: null, sourceTitle: "", prompt: "" }))} />;
    }
    if (activeTab === "video") {
      return <GenerationScreen kind="video" user={data.user} models={data.videoModels} draft={videoDraft} submitting={submitting} onChange={(patch) => setVideoDraft((current) => ({ ...current, ...patch }))} onSubmit={() => void submitGeneration("video")} onResetPreset={() => setVideoDraft((current) => ({ ...current, promptId: null, sourceTitle: "", prompt: "" }))} />;
    }
    if (activeTab === "motion") {
      return <GenerationScreen kind="motion" user={data.user} models={data.videoModels} draft={motionDraft} submitting={submitting} onChange={(patch) => setMotionDraft((current) => ({ ...current, ...patch }))} onSubmit={() => void submitGeneration("motion")} onResetPreset={() => setMotionDraft((current) => ({ ...current, promptId: null, sourceTitle: "", prompt: "" }))} />;
    }
    if (activeTab === "feed") {
      return <FeedScreen items={data.feed} source={feedSource} loading={feedLoading} onSourceChange={(source) => { setFeedSource(source); void loadFeed(source); }} onRefresh={() => void loadFeed()} onLike={(item) => void likeFeed(item)} onRemix={(item) => void remixFeed(item)} />;
    }
    if (activeTab === "trends") {
      return <TrendsScreen items={data.trends} filter={trendsFilter} loading={trendsLoading} preparingId={preparingTrendId} onFilterChange={setTrendsFilter} onRefresh={() => void loadTrends()} onPrepare={(trend) => void prepareTrend(trend)} />;
    }
    if (activeTab === "services") {
      return <ServicesScreen messages={assistantMessages} assistantBusy={assistantBusy} photoPromptBusy={photoPromptBusy} photoPromptResult={photoPromptResult} onAssistantSend={(message) => void sendAssistant(message)} onPhotoPrompt={(file) => void createPhotoPrompt(file)} onUsePrompt={(prompt) => { setImageDraft((current) => ({ ...current, prompt, promptId: null, sourceTitle: "" })); setActiveTab("photo"); }} onNavigate={setActiveTab} />;
    }
    return <ProfileScreen user={data.user} tasks={data.recentTasks} referrals={referrals} referralsLoading={referralsLoading} onOpenTask={openTask} onBalanceOpen={() => setBalanceOpen(true)} />;
  })();

  return (
    <>
      <AppShell activeTab={activeTab} user={data.user} onTabChange={setActiveTab} onBalanceOpen={() => setBalanceOpen(true)}>
        {screen}
      </AppShell>
      <TaskDetailSheet task={selectedTask} open={taskOpen} busy={taskBusy} onOpenChange={setTaskOpen} onRefresh={(task) => void refreshTask(task)} onShare={(task) => void toggleTaskShare(task)} onToggleLibrary={(task) => void toggleTaskLibrary(task)} />
      <BalanceSheet open={balanceOpen} user={data.user} plans={data.paymentPlans} busy={paymentBusy} onOpenChange={setBalanceOpen} onPay={(provider, plan) => void pay(provider, plan)} />
      <Toaster richColors position="top-center" closeButton />
    </>
  );
}

export { App };
