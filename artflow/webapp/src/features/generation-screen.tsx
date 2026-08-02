import type { ReactNode } from "react";
import { AlertCircle, Film, ImageIcon, LoaderCircle, Orbit, Upload, WandSparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { GenerationDraft, ModelInfo, UserProfile } from "@/lib/types";
import { cn, formatCredits, modelSupports, splitUrls } from "@/lib/utils";

interface GenerationScreenProps {
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
}

const TASK_COUNT_OPTIONS = [1, 2, 3, 4, 6];

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
  kind,
  user,
  models,
  draft,
  submitting,
  referenceUploading,
  videoUploading,
  onChange,
  onUploadReferenceFiles,
  onUploadVideoFile,
  onSubmit,
  onResetPreset,
}: GenerationScreenProps) {
  const copy = titles[kind];
  const Icon = copy.icon;
  const availableModels =
    kind === "motion"
      ? models.filter((model) => /motion/i.test(`${model.key} ${model.display_name}`) || model.modes?.includes("motion"))
      : models.filter((model) => !/motion-control/i.test(model.key) || kind === "video");
  const selectedModel = availableModels.find((model) => model.key === draft.model) || availableModels[0];
  const modes = selectedModel?.modes?.length ? selectedModel.modes : [kind === "motion" ? "motion" : "text"];
  const ratios = selectedModel?.aspect_ratios?.length ? selectedModel.aspect_ratios : [kind === "image" ? "1:1" : "16:9"];
  const qualities = selectedModel?.quality_options?.length ? selectedModel.quality_options : [];
  const outputCounts = selectedModel?.counts?.length ? selectedModel.counts : [1];
  const durations = listOr(selectedModel?.duration_options, selectedModel?.durations, [5, 10]);
  const resolutions = listOr(selectedModel?.resolution_options, selectedModel?.resolutions, ["720p", "1080p"]);
  const modeOptions = selectedModel?.mode_options || [];
  const taskCount = clampTaskCount(draft.taskCount);
  const baseEstimate = kind === "image" ? imageBaseCost(selectedModel, draft.quality, draft.count) : videoBaseCost(selectedModel, draft);
  const estimate = baseEstimate * taskCount;
  const refsRequired = Boolean(selectedModel && !modelSupports(selectedModel, "text") && modelSupports(selectedModel, "image"));
  const maxRefs = Math.max(1, Number(selectedModel?.max_refs || 1));
  const tooManyRefs = draft.referenceUrls.length > maxRefs;
  const missingReference = refsRequired && draft.referenceUrls.length === 0;
  const videoModeNeedsUpload = draft.mode === "video" || (kind === "motion" && draft.mode !== "text");
  const missingMotionVideo = videoModeNeedsUpload && kind === "motion" && !draft.videoUrl;
  const missingPrompt = !draft.prompt.trim() && !draft.promptId;
  const insufficientCredits = estimate > Number(user.credits || 0);
  const mediaUploading = referenceUploading || videoUploading;
  const disabled = submitting || mediaUploading || !selectedModel || missingPrompt || missingReference || missingMotionVideo || tooManyRefs || insufficientCredits;
  const showReferenceUploader = kind === "image" || draft.mode === "image" || kind === "motion";
  const showVideoUploader = draft.mode === "video" || kind === "motion" || Boolean(selectedModel?.supports_video_input);
  const remainingRefs = Math.max(0, maxRefs - draft.referenceUrls.length);
  const maxAudioIds = Number(selectedModel?.max_audio_ids || 0);
  const maxCharacterIds = Number(selectedModel?.max_character_ids || 0);

  const syncSelectedModel = (modelKey: string) => {
    const model = availableModels.find((item) => item.key === modelKey);
    const nextDurations = listOr(model?.duration_options, model?.durations, [5]);
    const nextResolutions = listOr(model?.resolution_options, model?.resolutions, ["720p"]);
    onChange({
      model: modelKey,
      mode: model?.modes?.[0] || (kind === "motion" ? "motion" : "text"),
      aspectRatio: model?.aspect_ratios?.[0] || draft.aspectRatio || (kind === "image" ? "1:1" : "16:9"),
      quality: model?.quality_options?.[0]?.value || "basic",
      duration: nextDurations[0] || draft.duration || 5,
      resolution: nextResolutions[0] || draft.resolution || "720p",
      count: model?.counts?.[0] || 1,
      grokMode: model?.mode_options?.[0] || "normal",
      seed: null,
      audioIds: [],
      characterIds: [],
      videoStart: 0,
      videoEnd: null,
    });
  };

  const removeReference = (url: string) => {
    onChange({ referenceUrls: draft.referenceUrls.filter((item) => item !== url) });
  };

  return (
    <div className="apix-generation-layout grid min-w-0 gap-3 xl:grid-cols-[minmax(0,1fr)_280px]">
      <section className="apix-generation-main grid min-w-0 gap-2.5">
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

        <Card className="apix-generation-card min-w-0 overflow-hidden">
          <CardHeader className="apix-generation-card-header pb-2">
            <CardTitle>Модель и идея</CardTitle>
          </CardHeader>
          <CardContent className="apix-generation-card-content grid min-w-0 gap-2.5">
            <label className="grid min-w-0 gap-1 text-xs font-medium">
              Модель
              <Select value={selectedModel?.key || ""} onChange={(event) => syncSelectedModel(event.target.value)}>
                {availableModels.map((model) => (
                  <option key={model.key} value={model.key}>{model.display_name} · {formatCredits(model.credits)} кр.</option>
                ))}
              </Select>
            </label>

            {modes.length > 1 || kind !== "image" ? (
              <LabeledChips label="Режим">
                {modes.map((mode) => (
                  <button key={mode} type="button" className={cn(chipClass(draft.mode === mode), "shrink-0")} onClick={() => onChange({ mode })}>
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
                onChange={(event) => onChange({ prompt: event.target.value })}
              />
            </label>

            {showReferenceUploader ? (
              <div className="apix-uploader-card grid min-w-0 gap-2 rounded-xl border border-border/75 bg-card/40 p-2">
                <div className="apix-uploader-head flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold">Референсы · до {maxRefs}</p>
                    <p className="text-[10px] text-muted-foreground">Загрузи фото с устройства. Ссылки вставлять не нужно.</p>
                  </div>
                  <label className={cn(chipClass(Boolean(remainingRefs) && !referenceUploading), "inline-flex shrink-0 cursor-pointer items-center gap-1.5") }>
                    {referenceUploading ? <LoaderCircle className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
                    {referenceUploading ? "Загрузка" : "Добавить"}
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      className="sr-only"
                      disabled={!remainingRefs || referenceUploading}
                      onChange={(event) => {
                        const files = Array.from(event.currentTarget.files || []).slice(0, remainingRefs);
                        event.currentTarget.value = "";
                        if (files.length) onUploadReferenceFiles(files);
                      }}
                    />
                  </label>
                </div>

                {draft.referenceUrls.length ? (
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
                    value={draft.referenceUrls.join("\n")}
                    placeholder="Опционально: HTTPS-ссылки, по одной в строке"
                    onChange={(event) => onChange({ referenceUrls: splitUrls(event.target.value) })}
                  />
                </details>
              </div>
            ) : null}

            {showVideoUploader ? (
              <div className="apix-uploader-card grid min-w-0 gap-2 rounded-xl border border-border/75 bg-card/40 p-2">
                <div className="apix-uploader-head flex min-w-0 flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold">{kind === "motion" ? "Видео движения" : "Видео-референс"}</p>
                    <p className="text-[10px] text-muted-foreground">Загрузи ролик с устройства, если модель требует видео.</p>
                  </div>
                  <label className={cn(chipClass(!videoUploading), "inline-flex shrink-0 cursor-pointer items-center gap-1.5") }>
                    {videoUploading ? <LoaderCircle className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
                    {videoUploading ? "Загрузка" : "Видео"}
                    <input
                      type="file"
                      accept="video/mp4,video/webm,video/quicktime,video/*"
                      className="sr-only"
                      disabled={videoUploading}
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
                      <button type="button" className="apix-focus-ring grid size-6 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive" onClick={() => onChange({ videoUrl: "" })} aria-label="Убрать видео">
                        <X className="size-3.5" />
                      </button>
                    </div>
                    {selectedModel?.supports_video_input ? (
                      <div className="grid grid-cols-2 gap-2">
                        <label className="grid gap-1 text-[10px] text-muted-foreground">Старт, сек<Input type="number" min={0} value={draft.videoStart} onChange={(event) => onChange({ videoStart: Math.max(0, Number(event.target.value) || 0) })} /></label>
                        <label className="grid gap-1 text-[10px] text-muted-foreground">Конец, сек<Input type="number" min={0} value={draft.videoEnd ?? ""} placeholder="auto" onChange={(event) => onChange({ videoEnd: event.target.value ? Math.max(0, Number(event.target.value) || 0) : null })} /></label>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <details className="apix-help border-0">
                  <summary>Вставить ссылку вручную</summary>
                  <Input
                    value={draft.videoUrl}
                    placeholder="Опционально: https://…/motion.mp4"
                    inputMode="url"
                    onChange={(event) => onChange({ videoUrl: event.target.value.trim() })}
                  />
                </details>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="apix-generation-card min-w-0 overflow-hidden">
          <CardHeader className="apix-generation-card-header pb-2"><CardTitle>Параметры</CardTitle></CardHeader>
          <CardContent className="apix-generation-card-content grid min-w-0 gap-3">
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
                {durations.length ? (
                  <LabeledChips label="Длительность">
                    {durations.map((duration) => (
                      <button key={duration} type="button" className={cn(chipClass(draft.duration === duration), "shrink-0")} onClick={() => onChange({ duration })}>{duration} сек</button>
                    ))}
                  </LabeledChips>
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
                      <button key={mode} type="button" className={cn(chipClass(draft.grokMode === mode), "shrink-0")} onClick={() => onChange({ grokMode: mode })}>{mode}</button>
                    ))}
                  </LabeledChips>
                ) : null}

                {selectedModel?.has_seed ? (
                  <label className="grid min-w-0 gap-1 text-xs font-medium">
                    Seed
                    <Input type="number" value={draft.seed ?? ""} placeholder="auto" onChange={(event) => onChange({ seed: event.target.value ? Number(event.target.value) : null })} />
                  </label>
                ) : null}

                {maxAudioIds > 0 ? (
                  <label className="grid min-w-0 gap-1 text-xs font-medium">
                    Audio IDs · до {maxAudioIds}
                    <Textarea className="min-h-14 font-mono text-base sm:text-xs" value={draft.audioIds.join("\n")} placeholder="по одному ID в строке" onChange={(event) => onChange({ audioIds: splitUrls(event.target.value).slice(0, maxAudioIds) })} />
                  </label>
                ) : null}

                {maxCharacterIds > 0 ? (
                  <label className="grid min-w-0 gap-1 text-xs font-medium">
                    Character IDs · до {maxCharacterIds}
                    <Textarea className="min-h-14 font-mono text-base sm:text-xs" value={draft.characterIds.join("\n")} placeholder="по одному ID в строке" onChange={(event) => onChange({ characterIds: splitUrls(event.target.value).slice(0, maxCharacterIds) })} />
                  </label>
                ) : null}
              </>
            )}

            <LabeledChips label="Количество задач">
              {TASK_COUNT_OPTIONS.map((count) => (
                <button key={count} type="button" className={cn(chipClass(taskCount === count), "min-w-8 shrink-0 px-2")} onClick={() => onChange({ taskCount: count })}>{count}</button>
              ))}
            </LabeledChips>
          </CardContent>
        </Card>
      </section>

      <aside className="apix-launch-bar xl:sticky xl:top-16 xl:self-start">
        <Card className="apix-launch-card border-primary/25 bg-popover/95 shadow-xl">
          <CardContent className="grid gap-2 p-2.5 sm:p-3">
            <div className="apix-launch-row flex items-center justify-between gap-2">
              <div>
                <p className="text-[10px] text-muted-foreground">Стоимость</p>
                <p className="text-lg font-bold leading-none">{formatCredits(estimate)} кр.</p>
                {taskCount > 1 ? <p className="mt-1 text-[10px] text-muted-foreground">{taskCount} задачи подряд</p> : null}
              </div>
              <Button className="apix-submit-button w-full min-[430px]:w-auto min-[430px]:min-w-[56%]" disabled={disabled} onClick={onSubmit}>
                {submitting ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <WandSparkles />}
                {submitting ? "Запуск…" : taskCount > 1 ? `Создать ${taskCount}` : "Создать"}
              </Button>
            </div>

            <div className="flex flex-wrap gap-x-2 gap-y-0.5">
              {missingPrompt ? <ValidationError>Нужен промпт</ValidationError> : null}
              {missingReference ? <ValidationError>Нужен референс</ValidationError> : null}
              {tooManyRefs ? <ValidationError>Лишние референсы</ValidationError> : null}
              {missingMotionVideo ? <ValidationError>Нужно видео</ValidationError> : null}
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
