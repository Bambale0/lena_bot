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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  { tab: "photo", title: "Создать фото", description: "Текст, референсы и edit-модели", icon: ImageIcon },
  { tab: "video", title: "Создать видео", description: "Text-to-video и image-to-video", icon: Film },
  { tab: "motion", title: "Motion Control", description: "Перенести движение на персонажа", icon: Orbit },
  { tab: "services", title: "AI-помощник", description: "Выбрать модель и улучшить идею", icon: Bot },
  { tab: "trends", title: "Повторить тренд", description: "Готовые сценарии без раскрытия промпта", icon: Flame },
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
    <div className="grid gap-5">
      <section className="relative overflow-hidden rounded-3xl border border-primary/20 bg-gradient-to-br from-primary/22 via-card/80 to-cyan-400/10 p-5 shadow-2xl shadow-primary/10 sm:p-7">
        <div className="relative z-10 max-w-2xl">
          <Badge className="mb-3">Рабочая студия</Badge>
          <h1 className="text-3xl font-bold tracking-tight sm:text-5xl">Создавайте без лишних экранов</h1>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
            Модель → промпт или референс → параметры → запуск. Баланс и стоимость подтверждаются backend.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button size="lg" onClick={() => onNavigate("photo")}>
              <Sparkles /> Начать с фото
            </Button>
            <Button size="lg" variant="outline" onClick={onBalanceOpen}>
              <CircleDollarSign /> {formatCredits(user.credits)} кредитов
            </Button>
          </div>
        </div>
        <div className="pointer-events-none absolute -right-12 -top-16 size-64 rounded-full bg-primary/20 blur-3xl" />
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Быстрые действия</h2>
            <p className="text-sm text-muted-foreground">
              {imageModels.length} фото-моделей · {videoModels.length} видео-моделей
            </p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {actions.map(({ tab, title, description, icon: Icon }) => (
            <button
              key={tab}
              type="button"
              className="apix-focus-ring apix-glass group rounded-2xl p-4 text-left transition hover:-translate-y-1 hover:border-primary/35"
              onClick={() => onNavigate(tab)}
            >
              <span className="mb-4 grid size-11 place-items-center rounded-xl bg-primary/12 text-primary transition group-hover:scale-105">
                <Icon className="size-5" />
              </span>
              <span className="block font-semibold">{title}</span>
              <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{description}</span>
            </button>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">Последние задачи</h2>
            <p className="text-sm text-muted-foreground">Статус обновляется при активном окне</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => onNavigate("profile")}>Вся история</Button>
        </div>

        {tasks.length ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {tasks.slice(0, 8).map((task) => {
              const media = firstMedia(task);
              const isVideo = task.gen_type === "video";
              return (
                <Card
                  key={task.id}
                  className="cursor-pointer overflow-hidden transition hover:-translate-y-0.5 hover:border-primary/30"
                  onClick={() => onOpenTask(task)}
                >
                  <div className="relative aspect-[4/3] overflow-hidden bg-muted">
                    {media ? (
                      isVideo ? (
                        <video src={media} muted playsInline preload="metadata" className="size-full object-cover" />
                      ) : (
                        <img src={media} alt="" loading="lazy" className="size-full object-cover" />
                      )
                    ) : (
                      <div className="grid size-full place-items-center text-muted-foreground">
                        {isPendingTask(task) ? <span className="size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" /> : <Sparkles />}
                      </div>
                    )}
                    <Badge variant={taskBadge(task)} className="absolute left-2 top-2">
                      {generationStatusLabel(task.status)}
                    </Badge>
                  </div>
                  <CardHeader className="p-3">
                    <CardTitle className="truncate text-sm">{task.model}</CardTitle>
                    <CardDescription className="flex items-center justify-between text-xs">
                      <span>{formatRelativeDate(task.created_at)}</span>
                      <span>{formatCredits(task.credits_spent)} кр.</span>
                    </CardDescription>
                  </CardHeader>
                </Card>
              );
            })}
          </div>
        ) : (
          <Card>
            <CardContent className="grid min-h-40 place-items-center text-center">
              <div>
                <Sparkles className="mx-auto mb-3 size-7 text-primary" />
                <p className="font-medium">Задач пока нет</p>
                <p className="mt-1 text-sm text-muted-foreground">Создайте первую работу — она появится здесь сразу после запуска.</p>
              </div>
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
}

export { StudioScreen };
