import { Copy, ExternalLink, Library, RefreshCw, Share2, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { GenerationTask } from "@/lib/types";
import {
  firstMedia,
  formatCredits,
  formatRelativeDate,
  generationStatusLabel,
  isPendingTask,
  safeExternalUrl,
} from "@/lib/utils";
import { openExternalUrl } from "@/lib/telegram";

interface TaskDetailSheetProps {
  task: GenerationTask | null;
  open: boolean;
  busy?: boolean;
  onOpenChange: (open: boolean) => void;
  onRefresh: (task: GenerationTask) => void;
  onShare: (task: GenerationTask) => void;
  onToggleLibrary: (task: GenerationTask) => void;
}

function statusVariant(task: GenerationTask): "success" | "warning" | "destructive" | "secondary" {
  if (task.status === "done" || task.status === "completed") return "success";
  if (task.status === "failed") return "destructive";
  if (isPendingTask(task)) return "warning";
  return "secondary";
}

function TaskDetailSheet({
  task,
  open,
  busy,
  onOpenChange,
  onRefresh,
  onShare,
  onToggleLibrary,
}: TaskDetailSheetProps) {
  if (!task) return null;
  const media = safeExternalUrl(firstMedia(task));
  const isVideo = task.gen_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(media);
  const promptVisible = Boolean(task.prompt && !task.prompt_hidden && task.prompt_actions_allowed !== false);

  const copy = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} скопирован`);
    } catch {
      toast.error("Не удалось скопировать");
    }
  };

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title={`Задача #${task.id}`}
      description={`${task.model} · ${formatRelativeDate(task.created_at)}`}
      footer={
        <div className="grid grid-cols-3 gap-1.5">
          {media ? <Button size="sm" onClick={() => openExternalUrl(media)}><ExternalLink /> Открыть</Button> : <span />}
          <Button size="sm" variant="outline" disabled={busy} onClick={() => onShare(task)}><Share2 /> {task.is_public_feed ? "В ленте" : "Публикация"}</Button>
          <Button size="sm" variant="outline" disabled={busy || !promptVisible} onClick={() => onToggleLibrary(task)}>
            {task.is_prompt_library ? <Trash2 /> : <Library />}
            {task.is_prompt_library ? "Убрать" : "Сохранить"}
          </Button>
        </div>
      }
    >
      <div className="grid gap-2.5">
        {media ? (
          <div className="overflow-hidden rounded-xl border border-border bg-muted">
            {isVideo ? (
              <video src={media} controls playsInline className="max-h-[64dvh] w-full object-contain" />
            ) : (
              <img src={media} alt="Результат генерации" className="max-h-[64dvh] w-full object-contain" />
            )}
          </div>
        ) : (
          <div className="grid min-h-32 place-items-center rounded-xl border border-dashed border-border bg-muted/40 text-center text-xs text-muted-foreground">
            {task.status === "failed" ? "Результат не создан" : "Генерация ещё выполняется"}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1">
          <Badge variant={statusVariant(task)}>{generationStatusLabel(task.status)}</Badge>
          <Badge variant="outline">{task.gen_type}</Badge>
          {task.aspect_ratio ? <Badge variant="outline">{task.aspect_ratio}</Badge> : null}
          {task.duration ? <Badge variant="outline">{task.duration} сек</Badge> : null}
          <Badge variant="outline">{formatCredits(task.credits_spent)} кр.</Badge>
          {isPendingTask(task) ? (
            <Button variant="ghost" size="sm" className="ml-auto" disabled={busy} onClick={() => onRefresh(task)}>
              <RefreshCw className={busy ? "animate-spin" : ""} /> Обновить
            </Button>
          ) : null}
        </div>

        {task.error ? <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-2.5 text-xs text-destructive">{task.error}</div> : null}

        <details className="apix-help rounded-lg border border-border px-2.5">
          <summary>Технические данные</summary>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 pb-2 text-xs">
            <dt className="text-muted-foreground">Task ID</dt>
            <dd className="flex min-w-0 items-center justify-end gap-1.5 text-right font-mono text-[10px]">
              <span className="truncate">{task.task_id || task.id}</span>
              <button type="button" aria-label="Скопировать Task ID" onClick={() => copy(String(task.task_id || task.id), "Task ID")}><Copy className="size-3.5" /></button>
            </dd>
            <dt className="text-muted-foreground">Модель</dt><dd className="truncate text-right">{task.model}</dd>
            <dt className="text-muted-foreground">Стоимость</dt><dd className="text-right">{formatCredits(task.credits_spent)} кредитов</dd>
          </dl>
        </details>

        {promptVisible ? (
          <details className="apix-help rounded-lg border border-border px-2.5">
            <summary>Промпт</summary>
            <div className="pb-2">
              <div className="mb-1 flex justify-end"><Button variant="ghost" size="sm" onClick={() => copy(task.prompt || "", "Промпт")}><Copy /> Копировать</Button></div>
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">{task.prompt}</p>
            </div>
          </details>
        ) : task.prompt_hidden ? (
          <details className="apix-help rounded-lg border border-border px-2.5">
            <summary>Почему промпт скрыт</summary>
            <p className="pb-2">Автор скрыл промпт. Повтор выполняется на backend без раскрытия текста.</p>
          </details>
        ) : null}
      </div>
    </Sheet>
  );
}

export { TaskDetailSheet };
