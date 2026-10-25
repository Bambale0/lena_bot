import { isKling4, KLING4_KEYFRAME, KLING4_REFERENCE, kling4Body, renameKling4Mentions } from "@/lib/kling4";
import { Kling4Materials } from "@/components/kling4-materials";
import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle, Film, ImageIcon, LoaderCircle, Orbit, Upload, WandSparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { GenerationDraft, ModelInfo, UserProfile } from "@/lib/types";
import { cn, formatCredits, modelSupports, splitUrls } from "@/lib/utils";
import { inspectDraftMedia, switchDraftModel } from "@/lib/draft-media";
import { referenceMaterials, replaceReferenceMaterials, selectGenerationInputs } from "@/lib/reference-selection";
import { ReferenceSelection } from "@/components/reference-selection";
import type { PhotoUploadControls } from "@/lib/photo-upload-queue";

import type { ReferenceChecker } from "@/lib/reference-availability";

interface GenerationScreenProps {
  checkReference?: ReferenceChecker;
  ux2?: boolean;
  photoUploads?: PhotoUploadControls;
  kind: "image" | "video" | "motion";
  user: UserProfile;
  models: ModelInfo[];
  draft: GenerationDraft;
  submitting: boolean;
  referenceUploading: boolean;
  videoUploading: boolean;
  onChange: (patch: Partial<GenerationDraft>) => void;
  onUploadReferenceFiles: (files: File[]) => void;
  onUploadVideoFile: (file: File) => void;
  onSubmit: () => void;
  onResetPreset: () => void;
  onUploadKling4?: (file: File) => Promise<{ url: string; kind?: string }>;
  onQuoteWan?: (payload: Record<string, unknown>) => Promise<{
    credits: number;
    rate: number;
    billable_seconds: number;
    input_video_seconds: number;
    max_output_seconds: number;
  }>;
}

const TASK_COUNT_OPTIONS = [1, 2, 3, 4, 6];
const GEMINI_OMNI_MODEL = "gemini-omni-video";
const GEMINI_MAX_MEDIA_SLOTS = 7;
const GEMINI_MAX_TRIM_SECONDS = 10;
const GEMINI_MAX_SEED = 2_147_483_647;
const SEEDANCE_20_MODELS = new Set(["bytedance/seedance-2", "bytedance/seedance-2-fast", "bytedance/seedance-2-mini"]);
const SEEDANCE_25_MODEL = "bytedance/seedance-2-5";
const WAN30_MODELS = new Set(["wan/3-0-video", "wan/3-0-video-prime"]);
const KLING_3_MODELS = new Set(["kling-3.0/video", "kling/v3-turbo-text-to-video", "kling/v3-turbo-image-to-video"]);

function promptMaxLength(kind: "image" | "video" | "motion", modelKey: string | undefined): number {
  if (kind !== "video") return 4000;
  if (isKling4(modelKey || "")) return 8000;
  if (WAN30_MODELS.has(modelKey || "")) return 4500;
  if (modelKey === SEEDANCE_25_MODEL) return 30000;
  if (modelKey && SEEDANCE_20_MODELS.has(modelKey)) return 20000;
  if (modelKey && KLING_3_MODELS.has(modelKey)) return 2500;
  return 4000;
}

const titles = {
  image: { title: "Фото", description: "Текст, edit-модели, референсы и пакетный результат.", icon: ImageIcon },
  video: { title: "Видео", description: "Text-to-video, image-to-video и video-to-video.", icon: Film },
  motion: { title: "Motion", description: "Фото персонажа и видео движения.", icon: Orbit },
};

function chipClass(active: boolean): string {
  return cn(
    "apix-focus-ring min-h-8 rounded-lg border px-2.5 text-xs font-semibold transition",
    active
      ? "border-primary/45 bg-primary/15 text-primary"
      : "border-border bg-card/45 text-muted-foreground active:bg-accent",
  );
}

function modeLabel(mode: string): string {
  return {
    text: "Текст",
    image: "Фото",
    video: "Видео",
    motion: "Motion",
    avatar: "Аватар",
    audio: "Голос",
    character: "Персонаж",
  }[mode] || mode;
}

function modeOptionLabel(mode: string): string {
  return {
    fun: "Fun · свободнее",
    normal: "Normal · универсально",
    spicy: "Spicy · смелее",
    low: "Low motion",
    high: "High motion",
  }[mode] || mode;
}

function shortUrlLabel(url: string): string {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    const name = parts[parts.length - 1] || parsed.hostname;
    return decodeURIComponent(name).slice(0, 42);
  } catch {
    return url.slice(0, 42);
  }
}

function listOr<T>(primary: T[] | undefined, secondary: T[] | undefined, fallback: T[]): T[] {
  if (primary?.length) return primary;
  if (secondary?.length) return secondary;
  return fallback;
}

function clampTaskCount(value: number | undefined): number {
  const normalized = Number(value || 1);
  return TASK_COUNT_OPTIONS.includes(normalized) ? normalized : 1;
}

function optionLabel(options: { value: string; label?: string }[] | undefined, value: string): string {
  return options?.find((item) => item.value === value)?.label || value;
}

function imageBaseCost(model: ModelInfo | undefined, quality: string, count: number): number {
  if (!model) return 0;
  const qualityPrice = model.quality_prices?.[quality];
  const optionPrice = model.quality_options?.find((item) => item.value === quality)?.credits;
  return Number(qualityPrice ?? optionPrice ?? model.credits ?? 0) * Math.max(1, count);
}

function videoBaseCost(model: ModelInfo | undefined, draft: GenerationDraft): number {
  if (!model) return 0;
  const tablePrice = model.price_table?.[draft.resolution]?.[String(draft.duration)];
  const videoInputPrice = draft.videoUrl ? model.video_input_prices?.[draft.resolution] : undefined;
  if (Number.isFinite(Number(videoInputPrice))) return Number(videoInputPrice);
  if (Number.isFinite(Number(tablePrice))) return Number(tablePrice);
  if (model.is_per_second) return Number(model.credits_per_sec ?? model.credits ?? 0) * Math.max(1, draft.duration || 1);
  return Number(model.credits ?? 0);
}

function LabeledChips({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="apix-parameter-group grid min-w-0 gap-1">
      <p className="text-xs font-medium">{label}</p>
      <div className="apix-parameter-chips flex min-w-0 flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function GenerationScreen({
  checkReference,
  ux2 = false,
  photoUploads,
  kind,
  user,
  models,
  draft: storedDraft,
  submitting,
  referenceUploading,
  videoUploading,
  onChange,
  onUploadReferenceFiles,
  onUploadVideoFile,
  onSubmit,
  onResetPreset,
  onQuoteWan,
  onUploadKling4,
}: GenerationScreenProps) {
  const draft = selectGenerationInputs(storedDraft);
  const preserveMedia = ux2 && draft.promptId === null;
  const selectionExists = storedDraft.promptId === null && storedDraft.referenceMaterials !== undefined;
  const allReferences = referenceMaterials(storedDraft);
  const [switchNotice, setSwitchNotice] = useState("");
  const [kling4Uploading, setKling4Uploading] = useState(false);
  const copy = titles[kind];
  const Icon = copy.icon;
  const availableModels =
    kind === "motion"
      ? models.filter((model) => /motion/i.test(`${model.key} ${model.display_name}`) || model.modes?.includes("motion"))
      : models.filter((model) => !model.modes?.includes("motion") && !/motion-control/i.test(model.key)
        && (model.key !== KLING4_KEYFRAME || draft.model === KLING4_KEYFRAME));
  const selectedModel = availableModels.find((model) => model.key === draft.model) || (ux2 && draft.model ? undefined : availableModels[0]);
  const kling4Selected = isKling4(selectedModel?.key || "");
  const isWan30 = kind === "video" && WAN30_MODELS.has(selectedModel?.key || "");
  const [wanQuote, setWanQuote] = useState<{
    key: string;
    credits?: number;
    rate?: number;
    billableSeconds?: number;
    inputSeconds?: number;
    error?: string;
  } | null>(null);
  const wanQuotePayload = {
    // Quote depends on media and settings, not prompt keystrokes.
    model: draft.model, prompt: "Проверка цены",
    ...kling4Body(draft),
    mode: draft.mode, duration: draft.duration,
    resolution: draft.resolution, aspect_ratio: draft.aspectRatio,
    image_url: draft.referenceUrls[0] || null, reference_urls: draft.referenceUrls,
    video_url: draft.videoUrl || null,
    seed: draft.seed,
    wan_audio: draft.wanAudio !== false,
    wan_nsfw_checker: draft.wanNsfwChecker !== false,
    wan_reference_video_urls: draft.wanReferenceVideoUrls || [],
    wan_reference_audio_urls: draft.wanReferenceAudioUrls || [],
    wan_reference_file_urls: draft.wanReferenceFileUrls || [],
    wan_reference_link_urls: draft.wanReferenceLinkUrls || [],
    wan_first_frame_url: draft.wanFirstFrameUrl || null,
    wan_last_frame_url: draft.wanLastFrameUrl || null,
  };
  const wanQuoteKey = JSON.stringify(wanQuotePayload);
  useEffect(() => {
    if (!isWan30 || !onQuoteWan || !draft.model || (draft.mode === "video" && !draft.videoUrl)
      || (draft.mode === "image" && !draft.referenceUrls.length)) {
      setWanQuote(null);
      return;
    }
    let disposed = false;
    setWanQuote(null);
    const timer = window.setTimeout(() => {
      void onQuoteWan(JSON.parse(wanQuoteKey) as Record<string, unknown>)
        .then((value) => {
          if (!disposed) setWanQuote({
            key: wanQuoteKey, credits: value.credits, rate: value.rate,
            billableSeconds: value.billable_seconds, inputSeconds: value.input_video_seconds,
          });
        })
        .catch((cause: Error) => {
          if (!disposed) setWanQuote({ key: wanQuoteKey, error: cause.message || "Не удалось рассчитать цену" });
        });
    }, 280);
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [isWan30, onQuoteWan, wanQuoteKey, draft.model, draft.mode, draft.videoUrl, draft.referenceUrls.length]);
  const mediaInspection = inspectDraftMedia(storedDraft, selectedModel);
  const modes = selectedModel?.modes?.length ? selectedModel.modes : [kind === "motion" ? "motion" : "text"];
  const ratioModes = selectedModel?.aspect_ratio_modes?.length ? selectedModel.aspect_ratio_modes : modes;
  const ratios = ratioModes.includes(draft.mode) && selectedModel?.aspect_ratios?.length ? selectedModel.aspect_ratios : [];
  const qualities = selectedModel?.quality_options?.length ? selectedModel.quality_options : [];
  const outputCounts = selectedModel?.counts?.length ? selectedModel.counts : [1];
  const durations = listOr(selectedModel?.duration_options, selectedModel?.durations, kind === "motion" ? [] : [5, 10]);
  const resolutions = listOr(selectedModel?.resolution_options, selectedModel?.resolutions, ["720p", "1080p"]);
  const modeOptions = selectedModel?.mode_options || [];
  const taskCount = clampTaskCount(draft.taskCount);
  const baseEstimate = kind === "image" ? imageBaseCost(selectedModel, draft.quality, draft.count) : videoBaseCost(selectedModel, draft);
  const quoteReady = !isWan30 || (wanQuote?.key === wanQuoteKey && wanQuote.credits !== undefined && !wanQuote.error);
  const estimate = (isWan30 ? (quoteReady ? Number(wanQuote?.credits) : 0) : baseEstimate) * taskCount;
  const referenceVideoPricePending = kling4Selected || !isWan30 && kind !== "image" && Boolean(
    draft.videoUrl || draft.audioIds.some(item => item.startsWith("__apix_seedance25:video_ref="))
    || (draft.model.startsWith("minimax-h3/") && draft.characterIds.length),
  );
  const maxRefs = preserveMedia ? mediaInspection.maxReferences ?? 0 : Math.max(1, Number(selectedModel?.max_refs || 1));
  const maxAudioIds = Math.max(0, Number(selectedModel?.max_audio_ids || 0));
  const maxCharacterIds = Math.max(0, Number(selectedModel?.max_character_ids || 0));
  const refsRequired = kind === "motion" || Boolean(selectedModel?.requires_reference_images) || Boolean(selectedModel && !modelSupports(selectedModel, "text") && modelSupports(selectedModel, "image"));
  const missingReference = !kling4Selected && (refsRequired && draft.referenceUrls.length === 0);
  const tooManyRefs = draft.referenceUrls.length > maxRefs;
  const missingVideo = !kling4Selected && ((Boolean(selectedModel?.requires_video_input) || draft.mode === "video" || kind === "motion") && !draft.videoUrl);
  const missingPrompt = !draft.prompt.trim() && !draft.promptId && !selectedModel?.key.startsWith("higgsfield/genjutsu/");
  const maxPromptLength = promptMaxLength(kind, selectedModel?.key);
  const insufficientCredits = !referenceVideoPricePending && estimate > Number(user.credits || 0);
  const mediaUploading = (!kling4Selected && (referenceUploading || videoUploading)) || kling4Uploading;
  const invalidSeed = Boolean(
    selectedModel?.has_seed &&
    draft.seed != null &&
    (!Number.isInteger(draft.seed) || draft.seed < 0 || draft.seed > GEMINI_MAX_SEED),
  );
  const invalidTrim = Boolean(
    draft.videoUrl &&
    draft.videoEnd != null &&
    (draft.videoEnd <= draft.videoStart || draft.videoEnd - draft.videoStart > GEMINI_MAX_TRIM_SECONDS),
  );
  const tooManyAudioIds = draft.audioIds.length > maxAudioIds;
  const tooManyCharacterIds = draft.characterIds.length > maxCharacterIds;
  const geminiMediaSlots = selectedModel?.key === GEMINI_OMNI_MODEL
    ? (draft.mode === "image" ? draft.referenceUrls.length : 0) + (draft.videoUrl ? 2 : 0) + draft.characterIds.length
    : 0;
  const mediaQuotaExceeded = selectedModel?.key === GEMINI_OMNI_MODEL && geminiMediaSlots > GEMINI_MAX_MEDIA_SLOTS;
  const invalidWanDuration = isWan30 && (!Number.isInteger(draft.duration) || draft.duration < 2 || draft.duration > 30);
  const advancedInvalid = invalidSeed || invalidTrim || tooManyAudioIds || tooManyCharacterIds || mediaQuotaExceeded || invalidWanDuration;
  const unsupportedSettings = ux2 && !draft.promptId && Boolean(selectedModel && (
    !modes.includes(draft.mode) ||
    (ratios.length > 0 && !ratios.includes(draft.aspectRatio)) ||
    (kind === "image" && ((qualities.length > 0 && !qualities.some(option => option.value === draft.quality)) || !outputCounts.includes(draft.count))) ||
    (kind !== "image" && (
      (!isWan30 && !selectedModel.duration_from_source && durations.length > 0 && !durations.includes(draft.duration)) ||
      !resolutions.includes(draft.resolution) ||
      (modeOptions.length > 0 && !modeOptions.includes(draft.grokMode))
    )) || !TASK_COUNT_OPTIONS.includes(draft.taskCount)
  ));
  const refreshDraftParameters = () => {
    const nextMode = modes.includes(draft.mode) ? draft.mode : modes[0];
    onChange({
      mode: nextMode,
      aspectRatio: selectedModel?.aspect_ratios?.includes(draft.aspectRatio) ? draft.aspectRatio : selectedModel?.aspect_ratios?.[0] || draft.aspectRatio,
      quality: qualities.some(option => option.value === draft.quality) ? draft.quality : qualities[0]?.value || draft.quality,
      count: outputCounts.includes(draft.count) ? draft.count : outputCounts[0],
      taskCount: clampTaskCount(draft.taskCount),
      duration: isWan30 ? draft.duration : durations.includes(draft.duration) ? draft.duration : durations[0] || draft.duration,
      resolution: resolutions.includes(draft.resolution) ? draft.resolution : resolutions[0],
      grokMode: modeOptions.includes(draft.grokMode) ? draft.grokMode : modeOptions[0] || draft.grokMode,
    });
  };

  const disabled = submitting || mediaUploading || !selectedModel || missingPrompt || missingReference || missingVideo || tooManyRefs || advancedInvalid || unsupportedSettings || !quoteReady || (preserveMedia && mediaInspection.issues.length > 0);
  const showReferenceUploader = !kling4Selected && (kind === "image" || draft.mode === "image" || kind === "motion" || (isWan30 && draft.mode === "video") || selectedModel?.key === SEEDANCE_25_MODEL || (preserveMedia && (allReferences.length > 0 || (mediaInspection.referenceInputsSupported && (selectedModel?.auto_route_by_inputs === true || modes.includes("multimodal"))))));
  const showVideoUploader = !kling4Selected && (draft.mode === "video" || kind === "motion" || Boolean(selectedModel?.supports_video_input && !isWan30) || (preserveMedia && Boolean(draft.videoUrl)));
  const remainingRefs = Math.max(0, maxRefs - draft.referenceUrls.length);

  const syncSelectedModel = (modelKey: string) => {
    const model = availableModels.find((item) => item.key === modelKey);
    if (preserveMedia) {
      if (!model || mediaUploading || submitting) return;
      const next = switchDraftModel(storedDraft, model);
      const labels = { mode: "режим", aspectRatio: "формат", quality: "качество", count: "число результатов", duration: "длительность", resolution: "разрешение", grokMode: "вариант модели", seed: "seed" } as const;
      const changed = (Object.keys(labels) as Array<keyof typeof labels>).filter(key => next[key] !== draft[key]).map(key => labels[key]);
      setSwitchNotice(`Модель изменена. Материалы сохранены. Проверьте стоимость.${changed.length ? ` Обновлены несовместимые параметры: ${changed.join(", ")}.` : ""}`);
      onChange(next);
      return;
    }
    const nextDurations = listOr(model?.duration_options, model?.durations, kind === "motion" ? [] : [5]);
    const nextResolutions = listOr(model?.resolution_options, model?.resolutions, ["720p"]);
    const nextMode = model?.modes?.[0] || (kind === "motion" ? "motion" : "text");
    const ratioAllowed = (model?.aspect_ratio_modes?.length ? model.aspect_ratio_modes : model?.modes || []).includes(nextMode);
    let nextAspectRatio = draft.aspectRatio;
    if (WAN30_MODELS.has(modelKey)) {
      nextAspectRatio = model?.aspect_ratios?.[0] || "adaptive";
    } else if (ratioAllowed) {
      nextAspectRatio = model?.aspect_ratios?.[0] || draft.aspectRatio;
    }
    onChange({
      model: modelKey,
      mode: nextMode,
      aspectRatio: nextAspectRatio,
      quality: model?.quality_options?.[0]?.value || "basic",
      duration: WAN30_MODELS.has(modelKey) ? 5 : nextDurations[0] || draft.duration || 5,
      resolution: WAN30_MODELS.has(modelKey) ? "720p" : nextResolutions[0] || draft.resolution || "720p",
      count: model?.counts?.[0] || 1,
      grokMode: model?.mode_options?.[0] || "normal",
      seed: null,
      kling4: {},
      wanAudio: true,
      wanNsfwChecker: true,
      wanReferenceAudioUrls: [],
      wanReferenceVideoUrls: [],
      wanReferenceFileUrls: [],
      wanReferenceLinkUrls: [],
      wanFirstFrameUrl: "",
      wanLastFrameUrl: "",
      audioIds: [],
      characterIds: [],
      referenceUrls: [],
      videoUrl: "",
      videoStart: 0,
      videoEnd: null,
    });
  };

  const removeReference = (url: string) => {
    onChange({ referenceUrls: draft.referenceUrls.filter((item) => item !== url) });
  };

  const changeMode = (mode: string) => {
    if (preserveMedia) {
      if (mediaUploading || submitting || !modes.includes(mode)) return;
      onChange({ mode });
      setSwitchNotice("Режим изменён. Материалы сохранены; проверьте настройки перед запуском.");
      return;
    }
    const patch: Partial<GenerationDraft> = { mode };
    if (mode !== "image" && kind !== "motion" && !isWan30) patch.referenceUrls = [];
    if (mode !== "video" && kind !== "motion") {
      patch.videoUrl = "";
      patch.videoStart = 0;
      patch.videoEnd = null;
    }
    onChange(patch);
  };

  return (
    <div className="apix-generation-layout grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_280px]">
      <fieldset disabled={kling4Uploading || (preserveMedia || selectionExists) && (submitting || (mediaUploading && !photoUploads))} className="apix-generation-main grid min-w-0 gap-2.5">
        <div className="apix-generation-titlebar flex min-w-0 items-center justify-between gap-2 px-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="apix-generation-icon grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary"><Icon className="size-4" /></span>
            <div className="min-w-0">
              <h1 className="apix-generation-title text-lg font-bold tracking-tight sm:text-xl">{copy.title}</h1>
              <p className="apix-generation-subtitle truncate text-[11px] text-muted-foreground">{selectedModel?.display_name || copy.description}</p>
            </div>
          </div>
          <Badge variant="outline" className="apix-generation-balance shrink-0">{formatCredits(user.credits)} кр.</Badge>
        </div>

        {draft.promptId ? (
          <div className="flex min-w-0 items-center justify-between gap-2 rounded-lg border border-primary/25 bg-primary/8 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold">Тренд #{draft.promptId}: {draft.sourceTitle || "сценарий"}</p>
              <p className="text-[10px] text-muted-foreground">Скрытый промпт применит backend</p>
            </div>
            <Button variant="ghost" size="sm" onClick={onResetPreset}>Сбросить</Button>
          </div>
        ) : null}

        {unsupportedSettings && <div className="ux2-inline-notice" role="alert">
          <div><p>Возможности модели изменились. Обновите недоступные параметры перед запуском. Текст и материалы сохранятся.</p>
            <Button variant="outline" className="mt-2" onClick={refreshDraftParameters}>Обновить параметры</Button>
          </div>
        </div>}

        <Card className="apix-generation-card min-w-0 overflow-hidden">
          <CardHeader className="apix-generation-card-header pb-2"><CardTitle>Модель и идея</CardTitle></CardHeader>
          <CardContent className="apix-generation-card-content grid min-w-0 gap-2.5">
            <fieldset className="grid min-w-0 gap-2.5" disabled={preserveMedia && mediaUploading}>
            <label className="grid min-w-0 gap-1 text-xs font-medium">
              Модель
              <Select value={selectedModel?.key || ""} disabled={preserveMedia && (mediaUploading || submitting)} onChange={(event) => syncSelectedModel(event.target.value)}>
                {ux2 && !selectedModel && draft.model && <option value="" disabled>Модель черновика недоступна — выберите другую</option>}
                {availableModels.map((model) => (
                  <option key={model.key} value={model.key}>{model.key === KLING4_REFERENCE ? 'Kling 4' : model.display_name} · {formatCredits(model.credits)} кр.</option>
                ))}
              </Select>
            </label>

            {preserveMedia && switchNotice && <p role="status" className="text-sm text-muted-foreground">{switchNotice}</p>}
            {preserveMedia && mediaInspection.issues.length > 0 && <div className="ux2-inline-notice" data-testid="draft-media-conflicts" role="alert">
              <div className="grid gap-2"><strong>Материалы сохранены</strong>
                {mediaInspection.issues.map(issue => <p key={issue.code}>{issue.message}</p>)}
              </div>
            </div>}

            {!kling4Selected && (modes.length > 1 || kind !== "image") ? (
              <LabeledChips label="Режим">
                {modes.map((mode) => (
                  <button key={mode} type="button" className={cn(chipClass(draft.mode === mode), "shrink-0")} disabled={preserveMedia && (mediaUploading || submitting)} onClick={() => changeMode(mode)}>
                    {modeLabel(mode)}
                  </button>
                ))}
              </LabeledChips>
            ) : null}

            <label className="grid min-w-0 gap-1 text-xs font-medium">
              Промпт
              <Textarea
                className="apix-prompt-input min-h-24"
                value={draft.prompt}
                disabled={Boolean(draft.promptId)}
                placeholder={draft.promptId ? "Скрытый промпт тренда" : "Сцена, стиль, свет, движение, детали"}
                maxLength={maxPromptLength}
                onChange={(event) => onChange({ prompt: event.target.value })}
              />
              {!draft.promptId ? <span className="text-[10px] text-muted-foreground">{draft.prompt.length.toLocaleString("ru-RU")} / {maxPromptLength.toLocaleString("ru-RU")}</span> : null}
            </label>

            </fieldset>

            {kling4Selected && onUploadKling4 ? <Kling4Materials key={`${user.id}:${draft.model}`} onBusyChange={setKling4Uploading} model={draft.model} value={draft.kling4 || {}} onChange={kling4 => onChange({ kling4, prompt: renameKling4Mentions(draft.kling4 || {}, kling4, draft.prompt) })} onUpload={onUploadKling4} /> : null}
            {showReferenceUploader ? (
              <div className="apix-uploader-card grid min-w-0 gap-2 rounded-xl border border-border/75 bg-card/40 p-2">
                <div className="apix-uploader-head flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold">{kind === "motion" ? "Фото персонажа" : `Референсы · до ${maxRefs}`}</p>
                    <p className="text-[10px] text-muted-foreground">Загрузи фото с устройства. Ссылки вставлять не нужно.</p>
                  </div>
                  <label className={cn(chipClass(Boolean(remainingRefs) && !referenceUploading), "inline-flex shrink-0 cursor-pointer items-center gap-1.5") }>
                    {referenceUploading ? <LoaderCircle className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
                    {referenceUploading ? "Загрузка" : "Добавить"}
                    <input
                      type="file"
                      accept="image/*"
                      multiple={maxRefs > 1}
                      className="sr-only"
                      disabled={!remainingRefs || referenceUploading || (preserveMedia && !mediaInspection.referenceInputsSupported)}
                      onChange={(event) => {
                        const selected = Array.from(event.currentTarget.files || []);
                        const files = preserveMedia ? selected : selected.slice(0, remainingRefs);
                        event.currentTarget.value = "";
                        if (files.length) onUploadReferenceFiles(files);
                      }}
                    />
                  </label>
                </div>

                {preserveMedia ? <ReferenceSelection draft={storedDraft} model={selectedModel} busy={submitting || mediaUploading}
                  checkReference={checkReference} language={user.language} labelFor={shortUrlLabel} onChange={onChange} uploads={photoUploads} submitting={submitting} /> : draft.referenceUrls.length ? (
                  <div className="grid min-w-0 gap-1">
                    {draft.referenceUrls.map((url, index) => (
                      <div key={`${url}-${index}`} className="flex min-w-0 items-center gap-1 rounded-lg bg-background/70 px-2 py-1 text-[10px]">
                        <ImageIcon className="size-3.5 shrink-0 text-primary" />
                        <span className="min-w-0 flex-1 truncate">{shortUrlLabel(url)}</span>
                        <button type="button" className="apix-focus-ring grid size-6 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive" onClick={() => removeReference(url)} aria-label="Убрать референс">
                          <X className="size-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null}

                <details className="apix-help border-0">
                  <summary>Вставить ссылку вручную</summary>
                  <Textarea
                    className="min-h-14 font-mono text-base sm:text-xs"
                    disabled={preserveMedia && mediaUploading}
                    value={(preserveMedia ? allReferences.map(item => item.url).filter(Boolean) : draft.referenceUrls).join("\n")}
                    placeholder="Опционально: HTTPS-ссылки, по одной в строке"
                    onChange={(event) => onChange(preserveMedia && selectionExists
                      ? replaceReferenceMaterials(storedDraft, splitUrls(event.target.value))
                      : { referenceUrls: preserveMedia ? splitUrls(event.target.value) : splitUrls(event.target.value).slice(0, maxRefs) })}
                  />
                </details>
              </div>
            ) : null}

            <fieldset disabled={preserveMedia && mediaUploading}>
            {showVideoUploader ? (
              <div className="apix-uploader-card grid min-w-0 gap-2 rounded-xl border border-border/75 bg-card/40 p-2">
                <div className="apix-uploader-head flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold">{kind === "motion" ? "Видео движения" : "Видео-референс"}</p>
                    <p className="text-[10px] text-muted-foreground">{kind === "motion" ? "Движение из ролика будет перенесено на персонажа." : "Загрузи ролик, когда выбран режим Видео."}</p>
                  </div>
                  <label className={cn(chipClass(!videoUploading), "inline-flex shrink-0 cursor-pointer items-center gap-1.5") }>
                    {videoUploading ? <LoaderCircle className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
                    {videoUploading ? "Загрузка" : "Видео"}
                    <input
                      type="file"
                      accept="video/mp4,video/webm,video/quicktime,video/*"
                      className="sr-only"
                      disabled={videoUploading || (preserveMedia && !mediaInspection.videoInputSupported)}
                      onChange={(event) => {
                        const file = event.currentTarget.files?.[0];
                        event.currentTarget.value = "";
                        if (file) onUploadVideoFile(file);
                      }}
                    />
                  </label>
                </div>

                {draft.videoUrl ? (
                  <div className="grid min-w-0 gap-2">
                    <div className="flex min-w-0 items-center gap-1 rounded-lg bg-background/70 px-2 py-1 text-[10px]">
                      <Film className="size-3.5 shrink-0 text-primary" />
                      <span className="min-w-0 flex-1 truncate">{shortUrlLabel(draft.videoUrl)}</span>
                      <button type="button" className="apix-focus-ring grid size-6 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive" onClick={() => onChange({ videoUrl: "", videoStart: 0, videoEnd: null })} aria-label="Убрать видео">
                        <X className="size-3.5" />
                      </button>
                    </div>
                    {selectedModel?.supports_video_input && !isWan30 ? (
                      <div className="grid grid-cols-2 gap-2">
                        <label className="grid gap-1 text-[10px] text-muted-foreground">Старт, сек<Input type="number" min={0} value={draft.videoStart} onChange={(event) => onChange({ videoStart: Math.max(0, Number(event.target.value) || 0) })} /></label>
                        <label className="grid gap-1 text-[10px] text-muted-foreground">Конец, сек<Input type="number" min={0} value={draft.videoEnd ?? ""} placeholder="auto" aria-invalid={invalidTrim} onChange={(event) => onChange({ videoEnd: event.target.value ? Math.max(0, Number(event.target.value) || 0) : null })} /></label>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <details className="apix-help border-0">
                  <summary>Вставить ссылку вручную</summary>
                  <Input value={draft.videoUrl} placeholder="Опционально: https://…/motion.mp4" inputMode="url" onChange={(event) => onChange({ videoUrl: event.target.value.trim() })} />
                </details>
              </div>
            ) : null}
            </fieldset>
          </CardContent>
        </Card>

        <Card className="apix-generation-card min-w-0 overflow-hidden">
          <CardHeader className="apix-generation-card-header pb-2"><CardTitle>Параметры</CardTitle></CardHeader>
          <CardContent className="apix-generation-card-content grid min-w-0 gap-3">
            <fieldset className="grid min-w-0 gap-3" disabled={preserveMedia && mediaUploading}>
            {ratios.length ? (
              <LabeledChips label="Формат">
                {ratios.map((ratio) => (
                  <button key={ratio} type="button" className={cn(chipClass(draft.aspectRatio === ratio), "shrink-0")} onClick={() => onChange({ aspectRatio: ratio })}>{ratio}</button>
                ))}
              </LabeledChips>
            ) : null}

            {kind === "image" ? (
              <>
                {qualities.length ? (
                  <LabeledChips label="Качество">
                    {qualities.map((quality) => (
                      <button key={quality.value} type="button" className={cn(chipClass(draft.quality === quality.value), "shrink-0")} onClick={() => onChange({ quality: quality.value })}>
                        {quality.label || quality.value}
                      </button>
                    ))}
                  </LabeledChips>
                ) : null}

                {outputCounts.length > 1 ? (
                  <LabeledChips label="Результатов в задаче">
                    {outputCounts.map((count) => (
                      <button key={count} type="button" className={cn(chipClass(draft.count === count), "min-w-8 shrink-0 px-2")} onClick={() => onChange({ count })}>{count}</button>
                    ))}
                  </LabeledChips>
                ) : null}
              </>
            ) : (
              <>
                {!selectedModel?.duration_from_source && durations.length ? (() => {
                  const durationIndex = Math.max(0, durations.indexOf(draft.duration));
                  const selectedDuration = isWan30 && !durations.includes(draft.duration) ? draft.duration : durations[durationIndex] ?? draft.duration;
                  return (
                    <div className="apix-parameter-group grid min-w-0 gap-1.5">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-medium">Длительность</p>
                        <Badge variant="outline" className="shrink-0">{selectedDuration} сек</Badge>
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={Math.max(0, durations.length - 1)}
                        step={1}
                        value={durationIndex}
                        disabled={durations.length <= 1}
                        aria-label="Длительность видео"
                        aria-valuetext={`${selectedDuration} секунд`}
                        className="apix-focus-ring h-8 w-full cursor-pointer accent-primary disabled:cursor-default disabled:opacity-60"
                        onChange={(event) => {
                          const nextDuration = durations[Number(event.target.value)];
                          if (nextDuration != null) onChange({ duration: nextDuration });
                        }}
                      />
                      <div className="flex items-center justify-between gap-1 text-[10px] text-muted-foreground">
                        {durations.map((duration) => (
                          <button
                            key={duration}
                            type="button"
                            className={cn(
                              "apix-focus-ring min-w-0 rounded px-1 py-0.5 text-[10px] transition",
                              duration === selectedDuration ? "font-semibold text-primary" : "text-muted-foreground hover:text-foreground",
                            )}
                            onClick={() => onChange({ duration })}
                          >
                            {duration} сек
                          </button>
                        ))}
                      </div>
                    </div>
                  );
                })() : null}

                {selectedModel?.duration_from_source ? (
                  <div className="rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                    Длительность и итоговая стоимость определятся по загруженному исходному видео (от 4 до 30 секунд).
                  </div>
                ) : null}

                {resolutions.length ? (
                  <LabeledChips label="Разрешение">
                    {resolutions.map((resolution) => (
                      <button key={resolution} type="button" className={cn(chipClass(draft.resolution === resolution), "shrink-0")} onClick={() => onChange({ resolution })}>{optionLabel(selectedModel?.quality_options, resolution)}</button>
                    ))}
                  </LabeledChips>
                ) : null}

                {modeOptions.length ? (
                  <LabeledChips label="Вариант модели">
                    {modeOptions.map((mode) => (
                      <button key={mode} type="button" className={cn(chipClass(draft.grokMode === mode), "shrink-0")} onClick={() => onChange({ grokMode: mode })}>{modeOptionLabel(mode)}</button>
                    ))}
                  </LabeledChips>
                ) : null}

                {selectedModel?.has_seed && !isWan30 ? (
                  <label className="grid min-w-0 gap-1 text-xs font-medium">
                    Seed
                    <Input type="number" min={0} max={GEMINI_MAX_SEED} step={1} value={draft.seed ?? ""} placeholder="auto" aria-invalid={invalidSeed} onChange={(event) => onChange({ seed: event.target.value ? Number(event.target.value) : null })} />
                  </label>
                ) : null}

                {isWan30 ? (
                  <details className="apix-help rounded-xl border border-border/70 bg-muted/20 px-3 py-2">
                    <summary className="cursor-pointer text-xs font-semibold">Ещё настройки (необязательно)</summary>
                    <div className="grid gap-3 pt-3">
                      <label className="grid gap-1 text-xs font-medium">
                        Своя длительность (2–30 сек)
                        <Input type="number" min={2} max={30} value={draft.duration} onChange={event => {
                          const value = Number(event.target.value);
                          if (Number.isInteger(value) && value >= 2 && value <= 30) onChange({ duration: value });
                        }} />
                      </label>
                      <label className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={draft.wanAudio !== false} onChange={event => onChange({ wanAudio: event.target.checked })} />
                        Видео со звуком
                      </label>
                      <label className="flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={draft.wanNsfwChecker !== false} onChange={event => onChange({ wanNsfwChecker: event.target.checked })} />
                        Проверка безопасности
                      </label>
                      <label className="grid gap-1 text-xs font-medium">
                        Seed (для повторяемого результата)
                        <Input type="number" min={0} max={GEMINI_MAX_SEED} value={draft.seed ?? ""} placeholder="Автоматически" aria-invalid={invalidSeed} onChange={event => onChange({ seed: event.target.value === "" ? null : Number(event.target.value) })} />
                      </label>
                      {draft.mode === "image" ? <label className="grid gap-1 text-xs font-medium">
                        Финальный кадр (если нужно)
                        <Input value={draft.wanLastFrameUrl || ""} placeholder="https://… (или добавь второе фото)" onChange={event => onChange({ wanLastFrameUrl: event.target.value.trim() })} />
                      </label> : null}
                      <label className="grid gap-1 text-xs font-medium">
                        Аудиореференсы (по одной ссылке)
                        <Textarea className="min-h-14 font-mono" value={(draft.wanReferenceAudioUrls || []).join("\n")} placeholder="https://…/audio.mp3" onChange={event => onChange({ wanReferenceAudioUrls: splitUrls(event.target.value).slice(0, 5) })} />
                      </label>
                      <label className="grid gap-1 text-xs font-medium">
                        Дополнительные видеореференсы
                        <Textarea className="min-h-14 font-mono" value={(draft.wanReferenceVideoUrls || []).join("\n")} placeholder="Сначала загрузи видео в APIX" onChange={event => onChange({ wanReferenceVideoUrls: splitUrls(event.target.value).slice(0, 5) })} />
                      </label>
                      <label className="grid gap-1 text-xs font-medium">
                        Документ для референса (HTTPS)
                        <Input value={(draft.wanReferenceFileUrls || [])[0] || ""} placeholder="https://…/brief.pdf" onChange={event => onChange({ wanReferenceFileUrls: event.target.value.trim() ? [event.target.value.trim()] : [] })} />
                      </label>
                      <label className="grid gap-1 text-xs font-medium">
                        Ссылка на веб-страницу
                        <Input value={(draft.wanReferenceLinkUrls || [])[0] || ""} placeholder="https://…/article" onChange={event => onChange({ wanReferenceLinkUrls: event.target.value.trim() ? [event.target.value.trim()] : [] })} />
                      </label>
                      <p className="text-[11px] text-muted-foreground">Если не знаешь, что выбрать, оставь как есть. Дополнительные видео учитываются в стоимости.</p>
                    </div>
                  </details>
                ) : null}

                {maxAudioIds > 0 || (preserveMedia && draft.audioIds.length > 0) ? (
                  <label className="grid min-w-0 gap-1 text-xs font-medium">
                    Audio ID · до {maxAudioIds}
                    <Textarea className="min-h-14 font-mono text-base sm:text-xs" value={draft.audioIds.join("\n")} placeholder="по одному ID в строке" onChange={(event) => onChange({ audioIds: preserveMedia ? splitUrls(event.target.value) : splitUrls(event.target.value).slice(0, maxAudioIds) })} />
                  </label>
                ) : null}

                {maxCharacterIds > 0 || (preserveMedia && draft.characterIds.length > 0) ? (
                  <label className="grid min-w-0 gap-1 text-xs font-medium">
                    Character IDs · до {maxCharacterIds}
                    <Textarea className="min-h-14 font-mono text-base sm:text-xs" value={draft.characterIds.join("\n")} placeholder="по одному ID в строке" onChange={(event) => onChange({ characterIds: preserveMedia ? splitUrls(event.target.value) : splitUrls(event.target.value).slice(0, maxCharacterIds) })} />
                    {selectedModel?.key === GEMINI_OMNI_MODEL ? <span className="text-[10px] text-muted-foreground">Media slots: {geminiMediaSlots}/{GEMINI_MAX_MEDIA_SLOTS}. Видео занимает 2, Character ID — 1.</span> : null}
                  </label>
                ) : null}
              </>
            )}

            <LabeledChips label="Количество задач">
              {TASK_COUNT_OPTIONS.map((count) => (
                <button key={count} type="button" className={cn(chipClass(taskCount === count), "min-w-8 shrink-0 px-2")} onClick={() => onChange({ taskCount: count })}>{count}</button>
              ))}
            </LabeledChips>
            </fieldset>
          </CardContent>
        </Card>
      </fieldset>

      <aside className="apix-launch-bar xl:sticky xl:top-16 xl:self-start">
        <Card className="apix-launch-card border-primary/25 bg-popover/95 shadow-xl">
          <CardContent className="grid gap-2 p-2.5 sm:p-3">
            <div className="apix-launch-row flex items-center justify-between gap-2">
              <div>
                <p className="text-[10px] text-muted-foreground">Стоимость</p>
                <p className="text-lg font-bold leading-none">
                  {isWan30 && !quoteReady ? "Проверяем цену…" :
                    referenceVideoPricePending ? "После проверки видео" : `${formatCredits(estimate)} кр.`}
                </p>
                {isWan30 && quoteReady ? <p className="mt-1 text-[10px] text-muted-foreground">
                  {wanQuote?.billableSeconds} сек к оплате
                  {wanQuote?.inputSeconds ? ` · включая ${wanQuote.inputSeconds} сек исходного видео` : ""}
                </p> : null}
                {selectedModel?.is_per_second ? <p className="mt-1 text-[10px] text-muted-foreground">{formatCredits(selectedModel.credits_per_sec ?? selectedModel.credits)} кр./сек</p> : null}
                {taskCount > 1 ? <p className="mt-1 text-[10px] text-muted-foreground">{taskCount} задачи подряд</p> : null}
              </div>
              <Button className="apix-submit-button w-full min-[430px]:w-auto min-[430px]:min-w-[56%]" disabled={disabled} onClick={onSubmit}>
                {submitting ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <WandSparkles />}
                {submitting ? "Запуск…" : taskCount > 1 ? `Создать ${taskCount}` : "Создать"}
              </Button>
            </div>

            <div className="flex flex-wrap gap-x-2 gap-y-0.5" aria-live="polite">
              {preserveMedia && mediaInspection.issues.length > 0 ? <ValidationError>Проверьте сохранённые материалы</ValidationError> : null}
              {missingPrompt ? <ValidationError>Нужен промпт</ValidationError> : null}
              {missingReference ? <ValidationError>{kind === "motion" ? "Нужно фото персонажа" : "Нужен референс"}</ValidationError> : null}
              {tooManyRefs ? <ValidationError>Лишние референсы</ValidationError> : null}
              {missingVideo ? <ValidationError>{kind === "motion" ? "Нужно видео движения" : "Нужно исходное видео"}</ValidationError> : null}
              {invalidTrim ? <ValidationError>Фрагмент видео: 0–10 сек, конец позже начала</ValidationError> : null}
              {invalidSeed ? <ValidationError>Seed: целое 0–2147483647</ValidationError> : null}
              {isWan30 && wanQuote?.key === wanQuoteKey && wanQuote.error ? <ValidationError>{wanQuote.error}</ValidationError> : null}
              {mediaQuotaExceeded ? <ValidationError>Превышена квота Gemini: {geminiMediaSlots}/{GEMINI_MAX_MEDIA_SLOTS}</ValidationError> : null}
              {tooManyAudioIds ? <ValidationError>Слишком много Audio ID</ValidationError> : null}
              {tooManyCharacterIds ? <ValidationError>Слишком много Character ID</ValidationError> : null}
              {mediaUploading ? <ValidationError>Дождись загрузки файла</ValidationError> : null}
              {insufficientCredits ? <ValidationError>Мало кредитов</ValidationError> : null}
              {!availableModels.length ? <ValidationError>Нет моделей</ValidationError> : null}
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function ValidationError({ children }: { children: ReactNode }) {
  return <span className="flex items-center gap-1 text-[10px] text-destructive"><AlertCircle className="size-3" />{children}</span>;
}

export { GenerationScreen };
