import type { ReactNode } from "react";
import { AlertCircle, Film, ImageIcon, Orbit, Sparkles, WandSparkles } from "lucide-react";

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
  onChange: (patch: Partial<GenerationDraft>) => void;
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

function GenerationScreen({
  kind,
  user,
  models,
  draft,
  submitting,
  onChange,
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
  const disabled = submitting || !selectedModel || missingPrompt || missingReference || missingMotionVideo || tooManyRefs || insufficientCredits;

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

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_270px]">
      <section className="grid gap-2.5">
        <div className="flex items-center justify-between gap-2 px-0.5">
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
          <div className="flex items-center justify-between gap-2 rounded-lg border border-primary/25 bg-primary/8 px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold">Тренд #{draft.promptId}: {draft.sourceTitle || "сценарий"}</p>
              <p className="text-[10px] text-muted-foreground">Скрытый промпт применит backend</p>
            </div>
            <Button variant="ghost" size="sm" onClick={onResetPreset}>Сбросить</Button>
          </div>
        ) : null}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Модель и идея</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2.5">
            <label className="grid gap-1 text-xs font-medium">
              Модель
              <Select value={selectedModel?.key || ""} onChange={(event) => syncSelectedModel(event.target.value)}>
                {availableModels.map((model) => (
                  <option key={model.key} value={model.key}>{model.display_name} · {formatCredits(model.credits)} кр.</option>
                ))}
              </Select>
            </label>

            {kind !== "image" || modes.length > 1 ? (
              <div className="flex items-center gap-2 overflow-x-auto pb-0.5">
                <span className="shrink-0 text-xs font-medium">Режим</span>
                {modes.map((mode) => (
                  <button key={mode} type="button" className={cn(chipClass(draft.mode === mode), "shrink-0")} onClick={() => onChange({ mode })}>
                    {modeLabel(mode)}
                  </button>
                ))}
              </div>
            ) : null}

            <label className="grid gap-1 text-xs font-medium">
              Промпт
              <Textarea
                className="min-h-24"
                value={draft.prompt}
                disabled={Boolean(draft.promptId)}
                placeholder={draft.promptId ? "Скрытый промпт тренда" : "Сцена, стиль, свет, движение, детали"}
                onChange={(event) => onChange({ prompt: event.target.value })}
              />
            </label>

            {(kind === "image" || draft.mode === "image" || kind === "motion") ? (
              <label className="grid gap-1 text-xs font-medium">
                Референсы · до {maxRefs}
                <Textarea
                  className="min-h-16 font-mono text-base sm:text-xs"
                  value={draft.referenceUrls.join("\n")}
                  placeholder="HTTPS-ссылки, по одной в строке"
                  onChange={(event) => onChange({ referenceUrls: splitUrls(event.target.value) })}
                />
              </label>
            ) : null}

            {(draft.mode === "video" || kind === "motion") ? (
              <label className="grid gap-1 text-xs font-medium">
                Видео движения
                <Input
                  value={draft.videoUrl}
                  placeholder="https://…/motion.mp4"
                  inputMode="url"
                  onChange={(event) => onChange({ videoUrl: event.target.value.trim() })}
                />
              </label>
            ) : null}

            <details className="apix-help">
              <summary>Требования к референсам</summary>
              <p className="pb-2">Backend принимает безопасные публичные HTTPS-ссылки. Blob URL не отправляются.</p>
            </details>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle>Параметры</CardTitle></CardHeader>
          <CardContent className="grid gap-2.5">
            {ratios.length ? (
              <div className="flex items-center gap-2 overflow-x-auto pb-0.5">
                <span className="shrink-0 text-xs font-medium">Формат</span>
                {ratios.map((ratio) => (
                  <button key={ratio} type="button" className={cn(chipClass(draft.aspectRatio === ratio), "shrink-0")} onClick={() => onChange({ aspectRatio: ratio })}>{ratio}</button>
                ))}
              </div>
            ) : null}

            {kind === "image" ? (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="mb-1 text-xs font-medium">Качество</p>
                  <div className="flex gap-1 overflow-x-auto">
                    {qualities.map((quality) => (
                      <button key={quality.value} type="button" className={cn(chipClass(draft.quality === quality.value), "shrink-0")} onClick={() => onChange({ quality: quality.value })}>
                        {quality.label || quality.value}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium">Количество</p>
                  <div className="flex gap-1 overflow-x-auto">
                    {counts.map((count) => (
                      <button key={count} type="button" className={cn(chipClass(draft.count === count), "min-w-8 shrink-0 px-2")} onClick={() => onChange({ count })}>{count}</button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1 text-xs font-medium">
                  Длительность
                  <Select value={String(draft.duration)} onChange={(event) => onChange({ duration: Number(event.target.value) })}>
                    {durations.map((duration) => <option key={duration} value={duration}>{duration} сек</option>)}
                  </Select>
                </label>
                <label className="grid gap-1 text-xs font-medium">
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
