import {
  Bot,
  CircleDollarSign,
  Film,
  Flame,
  ImageIcon,
  Orbit,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { AppTab, GenerationTask, ModelInfo, UserProfile } from "@/lib/types";
import {
  firstMedia,
  formatCredits,
  formatRelativeDate,
  generationStatusLabel,
  isPendingTask,
} from "@/lib/utils";

interface StudioScreenProps {
  user: UserProfile;
  imageModels: ModelInfo[];
  videoModels: ModelInfo[];
  tasks: GenerationTask[];
  onNavigate: (tab: AppTab) => void;
  onOpenTask: (task: GenerationTask) => void;
  onBalanceOpen: () => void;
}

const actions: Array<{ tab: AppTab; title: string; description: string; icon: typeof Sparkles }> = [
  { tab: "photo", title: "Фото", description: "Текст, референсы и edit-модели", icon: ImageIcon },
  { tab: "video", title: "Видео", description: "Text-to-video и image-to-video", icon: Film },
  { tab: "motion", title: "Motion", description: "Перенести движение на персонажа", icon: Orbit },
  { tab: "services", title: "AI", description: "Помощник и промпт по фото", icon: Bot },
  { tab: "trends", title: "Тренды", description: "Готовые сценарии без раскрытия промпта", icon: Flame },
];

function taskBadge(task: GenerationTask) {
  if (task.status === "done" || task.status === "completed") return "success" as const;
  if (task.status === "failed") return "destructive" as const;
  return "warning" as const;
}

function StudioScreen({
  user,
  imageModels,
  videoModels,
  tasks,
  onNavigate,
  onOpenTask,
  onBalanceOpen,
}: StudioScreenProps) {
  return (
    <div className="grid gap-3">
      <section className="flex items-center justify-between gap-3 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/16 via-card/75 to-cyan-400/8 px-3 py-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Sparkles className="size-4 shrink-0 text-primary" />
            <h1 className="truncate text-lg font-bold tracking-tight sm:text-xl">Студия</h1>
            <Badge variant="outline" className="hidden sm:inline-flex">{imageModels.length + videoModels.length} моделей</Badge>
          </div>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {imageModels.length} фото · {videoModels.length} видео · {formatCredits(user.credits)} кр.
          </p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Button size="sm" onClick={() => onNavigate("photo")}><ImageIcon /> Создать</Button>
          <Button size="icon" variant="soft" className="size-8 min-h-8" onClick={onBalanceOpen} aria-label="Баланс"><CircleDollarSign /></Button>
        </div>
      </section>

      <section>
        <div className="mb-1.5 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Быстрые действия</h2>
          <span className="text-[10px] text-muted-foreground">Все функции в 1 касание</span>
        </div>
        <div className="grid grid-cols-5 gap-1.5">
          {actions.map(({ tab, title, description, icon: Icon }) => (
            <button
              key={tab}
              type="button"
              title={description}
              className="apix-focus-ring flex min-h-[66px] flex-col items-center justify-center gap-1 rounded-xl border border-border bg-card/70 px-1.5 text-center transition active:scale-[0.97]"
              onClick={() => onNavigate(tab)}
            >
              <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
                <Icon className="size-4" />
              </span>
              <span className="text-[10px] font-semibold leading-none">{title}</span>
            </button>
          ))}
        </div>
        <details className="apix-help mt-1.5">
          <summary>Что умеют разделы</summary>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 pb-2">
            {actions.map((action) => <span key={action.tab}><b>{action.title}:</b> {action.description}</span>)}
          </div>
        </details>
      </section>

      <section>
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Последние задачи</h2>
          <Button variant="ghost" size="sm" onClick={() => onNavigate("profile")}>История</Button>
        </div>

        {tasks.length ? (
          <div className="grid grid-cols-2 gap-1.5 min-[430px]:grid-cols-3 sm:grid-cols-4 lg:grid-cols-6">
            {tasks.slice(0, 12).map((task) => {
              const media = firstMedia(task);
              const isVideo = task.gen_type === "video";
              return (
                <Card
                  key={task.id}
                  className="cursor-pointer overflow-hidden shadow-none transition active:scale-[0.98]"
                  onClick={() => onOpenTask(task)}
                >
                  <div className="relative aspect-square overflow-hidden bg-muted">
                    {media ? (
                      isVideo ? (
                        <video src={media} muted playsInline preload="metadata" className="size-full object-cover" />
                      ) : (
                        <img src={media} alt="" loading="lazy" className="size-full object-cover" />
                      )
                    ) : (
                      <div className="grid size-full place-items-center text-muted-foreground">
                        {isPendingTask(task) ? <span className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" /> : <Sparkles className="size-4" />}
                      </div>
                    )}
                    <Badge variant={taskBadge(task)} className="absolute left-1 top-1 px-1.5 py-0 text-[9px]">
                      {generationStatusLabel(task.status)}
                    </Badge>
                  </div>
                  <div className="px-2 py-1.5">
                    <p className="truncate text-[10px] font-semibold">{task.model}</p>
                    <p className="mt-0.5 flex justify-between gap-1 text-[9px] text-muted-foreground">
                      <span>{formatRelativeDate(task.created_at)}</span>
                      <span>{formatCredits(task.credits_spent)}</span>
                    </p>
                  </div>
                </Card>
              );
            })}
          </div>
        ) : (
          <button type="button" className="grid min-h-24 w-full place-items-center rounded-xl border border-dashed border-border text-center" onClick={() => onNavigate("photo")}>
            <span><Sparkles className="mx-auto mb-1 size-5 text-primary" /><span className="text-xs font-medium">Создать первую работу</span></span>
          </button>
        )}
      </section>
    </div>
  );
}

export { StudioScreen };
