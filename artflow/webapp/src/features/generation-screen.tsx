import type { ReactNode } from "react";
import { AlertCircle, Film, ImageIcon, Info, Orbit, Sparkles, WandSparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  image: {
    title: "Генерация фото",
    description: "Текст, edit-модели, несколько референсов и пакетный результат.",
    icon: ImageIcon,
  },
  video: {
    title: "Генерация видео",
    description: "Text-to-video, image-to-video и video-to-video в одной форме.",
    icon: Film,
  },
  motion: {
    title: "Motion Control",
    description: "Фото персонажа + видео движения. Стоимость подтверждается сервером.",
    icon: Orbit,
  },
};

function chipClass(active: boolean): string {
  return cn(
    "apix-focus-ring min-h-9 rounded-xl border px-3 text-xs font-semibold transition",
    active
      ? "border-primary/45 bg-primary/15 text-primary"
      : "border-border bg-card/45 text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

function modeLabel(mode: string): string {
  return {
    text: "По тексту",
    image: "По фото",
    video: "По видео",
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
  const estimate =
    kind === "image"
      ? estimateImageCost(selectedModel, draft.quality, draft.count)
      : estimateVideoCost(selectedModel);
  const refsRequired = Boolean(selectedModel && !modelSupports(selectedModel, "text") && modelSupports(selectedModel, "image"));
  const maxRefs = Math.max(1, Number(selectedModel?.max_refs || 1));
  const tooManyRefs = draft.referenceUrls.length > maxRefs;
  const missingReference = refsRequired && draft.referenceUrls.length === 0;
  const missingMotionVideo = kind === "motion" && !draft.videoUrl;
  const missingPrompt = !draft.prompt.trim() && !draft.promptId;
  const insufficientCredits = estimate > Number(user.credits || 0);
  const disabled =
    submitting ||
    !selectedModel ||
    missingPrompt ||
    missingReference ||
    missingMotionVideo ||
    tooManyRefs ||
    insufficientCredits;

  const syncSelectedModel = (modelKey: string) => {
    const model = availableModels.find((item) => item.key === modelKey);
    const firstMode = kind === "motion" ? "video" : model?.modes?.[0] || "text";
    onChange({
      model: modelKey,
      mode: firstMode,
      aspectRatio: model?.aspect_ratios?.[0] || draft.aspectRatio || "1:1",
      quality: model?.quality_options?.[0]?.value || "basic",
      duration: model?.duration_options?.[0] || draft.duration || 5,
      resolution: model?.resolution_options?.[0] || draft.resolution || "720p",
      count: model?.counts?.[0] || 1,
    });
  };

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className="grid gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-primary">
            <Icon className="size-5" />
            <span className="text-xs font-semibold uppercase tracking-[0.16em]">APIX Studio</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{copy.title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{copy.description}</p>
        </div>

        {draft.promptId ? (
          <Card className="border-primary/25 bg-primary/8 shadow-none">
            <CardContent className="flex items-start justify-between gap-3 p-4">
              <div>
                <Badge>Тренд #{draft.promptId}</Badge>
                <p className="mt-2 font-semibold">{draft.sourceTitle || "Готовый сценарий"}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Канонический промпт скрыт и будет подставлен backend. Его нельзя случайно раскрыть в интерфейсе.
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={onResetPreset}>Сбросить</Button>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>1. Модель и сценарий</CardTitle>
            <CardDescription>Показываются только модели, доступные через текущий backend registry.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Модель
              <Select value={selectedModel?.key || ""} onChange={(event) => syncSelectedModel(event.target.value)}>
                {availableModels.map((model) => (
                  <option key={model.key} value={model.key}>
                    {model.display_name} · {formatCredits(model.credits)} кр.
                  </option>
                ))}
              </Select>
            </label>

            {kind !== "image" || modes.length > 1 ? (
              <div>
                <p className="mb-2 text-sm font-medium">Сценарий</p>
                <div className="flex flex-wrap gap-2">
                  {modes.map((mode) => (
                    <button key={mode} type="button" className={chipClass(draft.mode === mode)} onClick={() => onChange({ mode })}>
                      {modeLabel(mode)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>2. Идея и референсы</CardTitle>
            <CardDescription>Основной целевой шаг. Дополнительные параметры находятся ниже.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <label className="grid gap-2 text-sm font-medium">
              Промпт
              <Textarea
                value={draft.prompt}
                disabled={Boolean(draft.promptId)}
                placeholder={draft.promptId ? "Скрытый промпт тренда применяется сервером" : "Опишите сцену, стиль, свет, движение и важные детали"}
                onChange={(event) => onChange({ prompt: event.target.value })}
              />
            </label>

            {(kind === "image" || draft.mode === "image" || kind === "motion") && (
              <label className="grid gap-2 text-sm font-medium">
                Референсы изображений
                <Textarea
                  className="min-h-24 font-mono text-xs"
                  value={draft.referenceUrls.join("\n")}
                  placeholder={`По одной публичной HTTPS-ссылке в строке. Максимум: ${maxRefs}`}
                  onChange={(event) => onChange({ referenceUrls: splitUrls(event.target.value) })}
                />
                <span className="text-xs font-normal text-muted-foreground">
                  Файлы не маскируются как blob URL: backend принимает только безопасные публичные HTTPS-ссылки.
                </span>
              </label>
            )}

            {(draft.mode === "video" || kind === "motion") && (
              <label className="grid gap-2 text-sm font-medium">
                Видео движения / video reference
                <Input
                  value={draft.videoUrl}
                  placeholder="https://cdn.example.com/motion.mp4"
                  inputMode="url"
                  onChange={(event) => onChange({ videoUrl: event.target.value.trim() })}
                />
              </label>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>3. Параметры</CardTitle>
            <CardDescription>Неподдерживаемые значения не отправляются.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5">
            {ratios.length ? (
              <div>
                <p className="mb-2 text-sm font-medium">Формат</p>
                <div className="flex flex-wrap gap-2">
                  {ratios.map((ratio) => (
                    <button key={ratio} type="button" className={chipClass(draft.aspectRatio === ratio)} onClick={() => onChange({ aspectRatio: ratio })}>
                      {ratio}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {kind === "image" ? (
              <>
                <div>
                  <p className="mb-2 text-sm font-medium">Качество</p>
                  <div className="flex flex-wrap gap-2">
                    {qualities.map((quality) => (
                      <button
                        key={quality.value}
                        type="button"
                        className={chipClass(draft.quality === quality.value)}
                        onClick={() => onChange({ quality: quality.value })}
                      >
                        {quality.label || quality.value}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">Количество</p>
                  <div className="flex flex-wrap gap-2">
                    {counts.map((count) => (
                      <button key={count} type="button" className={chipClass(draft.count === count)} onClick={() => onChange({ count })}>
                        {count}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-2 text-sm font-medium">
                  Длительность
                  <Select value={String(draft.duration)} onChange={(event) => onChange({ duration: Number(event.target.value) })}>
                    {durations.map((duration) => <option key={duration} value={duration}>{duration} сек</option>)}
                  </Select>
                </label>
                <label className="grid gap-2 text-sm font-medium">
                  Разрешение
                  <Select value={draft.resolution} onChange={(event) => onChange({ resolution: event.target.value })}>
                    {resolutions.map((resolution) => <option key={resolution} value={resolution}>{resolution}</option>)}
                  </Select>
                </label>
              </div>
            )}

            <details className="rounded-xl border border-border bg-muted/35 p-3">
              <summary className="cursor-pointer text-sm font-semibold">Расширенные параметры</summary>
              <div className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
                <Info className="mt-0.5 size-4 shrink-0" />
                Seed, negative prompt, CFG, watermark и provider-specific параметры появятся только для моделей, которые объявляют соответствующие capabilities. Сейчас форма не придумывает поля, отсутствующие в текущем контракте.
              </div>
            </details>
          </CardContent>
        </Card>
      </section>

      <aside className="lg:sticky lg:top-24 lg:self-start">
        <Card>
          <CardHeader>
            <CardTitle>Запуск</CardTitle>
            <CardDescription>Финальная стоимость будет повторно рассчитана backend.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="rounded-2xl border border-primary/20 bg-primary/8 p-4">
              <p className="text-xs text-muted-foreground">Предварительная стоимость</p>
              <p className="mt-1 text-3xl font-bold">{formatCredits(estimate)} кр.</p>
              <p className="mt-1 text-xs text-muted-foreground">Баланс: {formatCredits(user.credits)} кр.</p>
            </div>

            {missingPrompt ? <ValidationError>Добавьте промпт или выберите тренд.</ValidationError> : null}
            {missingReference ? <ValidationError>Эта модель требует хотя бы один референс.</ValidationError> : null}
            {tooManyRefs ? <ValidationError>Модель поддерживает не более {maxRefs} референсов.</ValidationError> : null}
            {missingMotionVideo ? <ValidationError>Для Motion Control нужно видео движения.</ValidationError> : null}
            {insufficientCredits ? <ValidationError>Недостаточно кредитов для запуска.</ValidationError> : null}
            {!availableModels.length ? <ValidationError>Подходящие модели сейчас недоступны.</ValidationError> : null}

            <Button size="lg" disabled={disabled} onClick={onSubmit}>
              {submitting ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" /> : <WandSparkles />}
              {submitting ? "Создаём задачу…" : "Запустить генерацию"}
            </Button>

            <p className="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
              После ответа 202 задача сразу появится в истории, откроется detail sheet и начнётся polling.
            </p>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function ValidationError({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-xl border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      {children}
    </p>
  );
}

export { GenerationScreen };
