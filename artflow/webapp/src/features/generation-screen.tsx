import type { ReactNode } from "react";
import { AlertCircle, Film, ImageIcon, LoaderCircle, Orbit, Sparkles, Upload, WandSparkles, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { GenerationDraft, ModelInfo, UserProfile } from "@/lib/types";
import {
  cn,
  estimateImageCost,
  estimateVideoCost,
  formatCredits,
  modelSupports,
  splitUrls,
} from "@/lib/utils";

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
      ? models.filter((model) => /motion/i.test(`${model.key} ${model.display_name}`))
      : models.filter((model) => !/motion-control/i.test(model.key) || kind === "video");
  const selectedModel = availableModels.find((model) => model.key === draft.model) || availableModels[0];
  const modes = kind === "motion" ? ["video"] : selectedModel?.modes?.length ? selectedModel.modes : ["text"];
  const ratios = selectedModel?.aspect_ratios?.length ? selectedModel.aspect_ratios : ["1:1", "9:16", "16:9"];
  const qualities = selectedModel?.quality_options?.length
    ? selectedModel.quality_options
    : [{ value: "basic", label: "Стандарт" }];
  const counts = selectedModel?.counts?.length ? selectedModel.counts : [1, 2, 4, 6];
  const durations = selectedModel?.duration_options?.length ? selectedModel.duration_options : [5, 10];
  const resolutions = selectedModel?.resolution_options?.length ? selectedModel.resolution_options : ["720p", "1080p"];
  const estimate = kind === "image" ? estimateImageCost(selectedModel, draft.quality, draft.count) : estimateVideoCost(selectedModel);
  const refsRequired = Boolean(selectedModel && !modelSupports(selectedModel, "text") && modelSupports(selectedModel, "image"));
  const maxRefs = Math.max(1, Number(selectedModel?.max_refs || 1));
  const tooManyRefs = draft.referenceUrls.length > maxRefs;
  const missingReference = refsRequired && draft.referenceUrls.length === 0;
  const missingMotionVideo = kind === "motion" && !draft.videoUrl;
  const missingPrompt = !draft.prompt.trim() && !draft.promptId;
  const insufficientCredits = estimate > Number(user.credits || 0);
  const mediaUploading = referenceUploading || videoUploading;
  const disabled = submitting || mediaUploading || !selectedModel || missingPrompt || missingReference || missingMotionVideo || tooManyRefs || insufficientCredits;
  const showReferenceUploader = kind === "image" || draft.mode === "image" || kind === "motion";
  const showVideoUploader = draft.mode === "video" || kind === "motion";
  const remainingRefs = Math.max(0, maxRefs - draft.referenceUrls.length);

  const syncSelectedModel = (modelKey: string) => {
    const model = availableModels.find((item) => item.key === modelKey);
    onChange({
      model: modelKey,
      mode: kind === "motion" ? "video" : model?.modes?.[0] || "text",
      aspectRatio: model?.aspect_ratios?.[0] || draft.aspectRatio || "1:1",
      quality: model?.quality_options?.[0]?.value || "basic",
      duration: model?.duration_options?.[0] || draft.duration || 5,
      resolution: model?.resolution_options?.[0] || draft.resolution || "720p",
      count: model?.counts?.[0] || 1,
    });
  };

  const removeReference = (url: string) => {
    onChange({ referenceUrls: draft.referenceUrls.filter((item) => item !== url) });
  };

  return (
    <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_270px]">
      <section className="grid min-w-0 gap-2.5">
        <div className="flex min-w-0 items-center justify-between gap-2 px-0.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary"><Icon className="size-4" /></span>
            <div className="min-w-0">
              <h1 className="text-lg font-bold tracking-tight sm:text-xl">{copy.title}</h1>
              <p className="truncate text-[11px] text-muted-foreground">{selectedModel?.display_name || copy.description}</p>
            </div>
          </div>
          <Badge variant="outline" className="shrink-0">{formatCredits(user.credits)} кр.</Badge>
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

        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle>Модель и идея</CardTitle>
          </CardHeader>
          <CardContent className="grid min-w-0 gap-2.5">
            <label className="grid min-w-0 gap-1 text-xs font-medium">
              Модель
              <Select value={selectedModel?.key || ""} onChange={(event) => syncSelectedModel(event.target.value)}>
                {availableModels.map((model) => (
                  <option key={model.key} value={model.key}>{model.display_name} · {formatCredits(model.credits)} кр.</option>
                ))}
              </Select>
            </label>

            {kind !== "image" || modes.length > 1 ? (
              <div className="flex min-w-0 items-center gap-2 overflow-x-auto pb-0.5">
                <span className="shrink-0 text-xs font-medium">Режим</span>
                {modes.map((mode) => (
                  <button key={mode} type="button" className={cn(chipClass(draft.mode === mode), "shrink-0")} onClick={() => onChange({ mode })}>
                    {modeLabel(mode)}
                  </button>
                ))}
              </div>
            ) : null}

            <label className="grid min-w-0 gap-1 text-xs font-medium">
              Промпт
              <Textarea
                className="min-h-24"
                value={draft.prompt}
                disabled={Boolean(draft.promptId)}
                placeholder={draft.promptId ? "Скрытый промпт тренда" : "Сцена, стиль, свет, движение, детали"}
                onChange={(event) => onChange({ prompt: event.target.value })}
              />
            </label>

            {showReferenceUploader ? (
              <div className="grid min-w-0 gap-2 rounded-xl border border-border/75 bg-card/40 p-2">
                <div className="flex min-w-0 items-center justify-between gap-2">
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
              <div className="grid min-w-0 gap-2 rounded-xl border border-border/75 bg-card/40 p-2">
                <div className="flex min-w-0 items-center justify-between gap-2">
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
                  <div className="flex min-w-0 items-center gap-1 rounded-lg bg-background/70 px-2 py-1 text-[10px]">
                    <Film className="size-3.5 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1 truncate">{shortUrlLabel(draft.videoUrl)}</span>
                    <button type="button" className="apix-focus-ring grid size-6 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive" onClick={() => onChange({ videoUrl: "" })} aria-label="Убрать видео">
                      <X className="size-3.5" />
                    </button>
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

            <details className="apix-help">
              <summary>Требования к файлам</summary>
              <p className="pb-2">Обычный путь — загрузка с устройства. Mini App отправляет файл на backend, получает публичную HTTPS-ссылку и только её передаёт в генерацию. Blob URL не отправляются.</p>
            </details>
          </CardContent>
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <CardHeader className="pb-2"><CardTitle>Параметры</CardTitle></CardHeader>
          <CardContent className="grid min-w-0 gap-2.5">
            {ratios.length ? (
              <div className="flex min-w-0 items-center gap-2 overflow-x-auto pb-0.5">
                <span className="shrink-0 text-xs font-medium">Формат</span>
                {ratios.map((ratio) => (
                  <button key={ratio} type="button" className={cn(chipClass(draft.aspectRatio === ratio), "shrink-0")} onClick={() => onChange({ aspectRatio: ratio })}>{ratio}</button>
                ))}
              </div>
            ) : null}

            {kind === "image" ? (
              <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                <div className="min-w-0">
                  <p className="mb-1 text-xs font-medium">Качество</p>
                  <div className="flex min-w-0 gap-1 overflow-x-auto">
                    {qualities.map((quality) => (
                      <button key={quality.value} type="button" className={cn(chipClass(draft.quality === quality.value), "shrink-0")} onClick={() => onChange({ quality: quality.value })}>
                        {quality.label || quality.value}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="min-w-0">
                  <p className="mb-1 text-xs font-medium">Количество</p>
                  <div className="flex min-w-0 gap-1 overflow-x-auto">
                    {counts.map((count) => (
                      <button key={count} type="button" className={cn(chipClass(draft.count === count), "min-w-8 shrink-0 px-2")} onClick={() => onChange({ count })}>{count}</button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid min-w-0 gap-2 sm:grid-cols-2">
                <label className="grid min-w-0 gap-1 text-xs font-medium">
                  Длительность
                  <Select value={String(draft.duration)} onChange={(event) => onChange({ duration: Number(event.target.value) })}>
                    {durations.map((duration) => <option key={duration} value={duration}>{duration} сек</option>)}
                  </Select>
                </label>
                <label className="grid min-w-0 gap-1 text-xs font-medium">
                  Разрешение
                  <Select value={draft.resolution} onChange={(event) => onChange({ resolution: event.target.value })}>
                    {resolutions.map((resolution) => <option key={resolution} value={resolution}>{resolution}</option>)}
                  </Select>
                </label>
              </div>
            )}

            <details className="apix-help">
              <summary>Расширенные параметры</summary>
              <p className="pb-2">Seed, negative prompt, CFG и watermark появятся только у моделей, которые объявляют эти capabilities.</p>
            </details>
          </CardContent>
        </Card>
      </section>

      <aside className="apix-launch-bar lg:sticky lg:top-16 lg:self-start">
        <Card className="border-primary/25 bg-popover/95 shadow-xl">
          <CardContent className="grid gap-2 p-2.5 sm:p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-[10px] text-muted-foreground">Стоимость</p>
                <p className="text-lg font-bold leading-none">{formatCredits(estimate)} кр.</p>
              </div>
              <Button className="min-w-[56%]" disabled={disabled} onClick={onSubmit}>
                {submitting ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <WandSparkles />}
                {submitting ? "Запуск…" : "Создать"}
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

            <details className="apix-help hidden lg:block">
              <summary>Что будет после запуска</summary>
              <p className="flex items-start gap-1.5 pb-2"><Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" />Задача сразу появится в истории, откроется результат и начнётся polling.</p>
            </details>
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
