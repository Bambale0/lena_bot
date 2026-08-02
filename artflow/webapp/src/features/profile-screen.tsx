import { Copy, Gift, Globe2, History, Play, Share2, Sparkles, Users, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GenerationTask, ReferralStats, UserProfile } from "@/lib/types";
import { firstMedia, formatCredits, formatRelativeDate, generationStatusLabel } from "@/lib/utils";

interface ProfileScreenProps {
  user: UserProfile;
  tasks: GenerationTask[];
  referrals: ReferralStats | null;
  referralsLoading: boolean;
  onOpenTask: (task: GenerationTask) => void;
  onBalanceOpen: () => void;
}

function ProfileScreen({ user, tasks, referrals, referralsLoading, onOpenTask, onBalanceOpen }: ProfileScreenProps) {
  const name = user.full_name || user.first_name || user.username || "Пользователь";
  const referralLink = referrals?.referral_link || user.referral_link || "";
  const invited = Number(referrals?.counts?.l1 || 0) + Number(referrals?.counts?.l2 || 0) + Number(referrals?.counts?.l3 || 0);
  const publishedTasks = tasks.filter((task) => Boolean(task.is_public_feed));

  const copy = async (value: string, label: string) => {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} скопирована`);
    } catch {
      toast.error("Не удалось скопировать");
    }
  };

  return (
    <div className="grid gap-3">
      <Card className="overflow-hidden">
        <div className="h-12 bg-gradient-to-r from-primary/45 via-fuchsia-500/25 to-cyan-400/25" />
        <CardContent className="relative grid gap-2.5 pb-3">
          <div className="-mt-7 flex items-end justify-between gap-2">
            <div className="flex min-w-0 items-end gap-2">
              <span className="grid size-14 shrink-0 place-items-center overflow-hidden rounded-2xl border-3 border-background bg-gradient-to-br from-primary to-cyan-400 text-xl font-bold text-white shadow-lg">
                {user.photo_url ? <img src={user.photo_url} alt="" className="size-full object-cover" /> : name.slice(0, 1).toUpperCase()}
              </span>
              <div className="min-w-0 pb-0.5">
                <h1 className="truncate text-lg font-bold tracking-tight">{name}</h1>
                <p className="truncate text-[10px] text-muted-foreground">{user.username ? `@${user.username}` : "Telegram-профиль"}</p>
              </div>
            </div>
            <Button variant="soft" size="sm" onClick={onBalanceOpen}><Wallet /> {formatCredits(user.credits)}</Button>
          </div>

          <div className="grid grid-cols-4 gap-1.5">
            <Stat label="История" value={tasks.length} icon={History} />
            <Stat label="Выложено" value={publishedTasks.length} icon={Globe2} />
            <Stat label="Приглашено" value={invited} icon={Users} />
            <Stat label="Баланс" value={formatCredits(referrals?.balance?.available_to_withdraw || user.referral_balance)} icon={Gift} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="grid gap-3">
          <WorkGrid
            title="Выложенные работы"
            empty="Ты ещё ничего не выложил в профиль"
            tasks={publishedTasks}
            onOpenTask={onOpenTask}
          />

          <WorkGrid
            title="Все работы"
            empty="История пока пустая"
            tasks={tasks}
            onOpenTask={onOpenTask}
          />
        </section>

        <aside>
          <Card>
            <CardHeader className="pb-2"><CardTitle>Партнёрская программа</CardTitle></CardHeader>
            <CardContent className="grid gap-2">
              {referralsLoading ? (
                <div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" /> Загружаем…</div>
              ) : (
                <>
                  <div className="flex items-center justify-between gap-2 rounded-lg border border-border bg-muted/35 px-3 py-2">
                    <div className="min-w-0"><p className="text-[9px] text-muted-foreground">Реферальный код</p><p className="truncate font-mono text-sm font-semibold">{referrals?.referral_code || user.referral_code || "—"}</p></div>
                    <Button variant="ghost" size="icon" className="size-8 min-h-8" disabled={!referralLink} onClick={() => copy(referralLink, "Ссылка")} aria-label="Копировать"><Copy /></Button>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    <Button variant="outline" size="sm" disabled={!referralLink} onClick={() => copy(referralLink, "Ссылка")}><Copy /> Копировать</Button>
                    <Button size="sm" disabled={!referralLink} onClick={() => copy(referralLink, "Ссылка для публикации")}><Share2 /> Поделиться</Button>
                  </div>
                  <details className="apix-help">
                    <summary>Правила начислений</summary>
                    <p className="pb-2">Привязка реферала не перезаписывается, начисления проходят через серверный ledger.</p>
                  </details>
                </>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function WorkGrid({
  title,
  empty,
  tasks,
  onOpenTask,
}: {
  title: string;
  empty: string;
  tasks: GenerationTask[];
  onOpenTask: (task: GenerationTask) => void;
}) {
  return (
    <section>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        <Badge variant="outline">{tasks.length}</Badge>
      </div>
      {tasks.length ? (
        <div className="grid grid-cols-2 gap-1.5 min-[390px]:grid-cols-3 sm:grid-cols-4 xl:grid-cols-5">
          {tasks.map((task) => <TaskTile key={task.id} task={task} onOpenTask={onOpenTask} />)}
        </div>
      ) : (
        <div className="grid min-h-24 place-items-center rounded-xl border border-dashed border-border text-xs text-muted-foreground">{empty}</div>
      )}
    </section>
  );
}

function TaskTile({ task, onOpenTask }: { task: GenerationTask; onOpenTask: (task: GenerationTask) => void }) {
  const media = firstMedia(task);
  const video = task.gen_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(media);
  return (
    <button
      type="button"
      className="apix-focus-ring apix-glass overflow-hidden rounded-xl text-left transition active:scale-[0.98]"
      onClick={() => onOpenTask(task)}
    >
      <div className="relative aspect-square bg-muted">
        {media ? (
          video ? <video src={media} muted playsInline preload="metadata" className="size-full object-cover" /> : <img src={media} alt="" loading="lazy" className="size-full object-cover" />
        ) : <div className="grid size-full place-items-center text-muted-foreground"><Sparkles className="size-4" /></div>}
        {video ? <span className="absolute inset-0 grid place-items-center"><span className="grid size-8 place-items-center rounded-full bg-black/55 text-white"><Play className="ml-0.5 size-3.5" /></span></span> : null}
        <Badge variant={task.status === "failed" ? "destructive" : task.status === "done" ? "success" : "warning"} className="absolute left-1 top-1 px-1.5 py-0 text-[8px]">{generationStatusLabel(task.status)}</Badge>
        {task.is_public_feed ? <Badge variant="outline" className="absolute bottom-1 left-1 bg-background/80 px-1.5 py-0 text-[8px]">в профиле</Badge> : null}
      </div>
      <div className="px-2 py-1.5">
        <p className="truncate text-[10px] font-semibold">{task.model}</p>
        <p className="mt-0.5 flex justify-between gap-1 text-[9px] text-muted-foreground"><span>{formatRelativeDate(task.created_at)}</span><span>{formatCredits(task.credits_spent)}</span></p>
      </div>
    </button>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof History }) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-card/55 px-1.5 py-2 text-center">
      <Icon className="mx-auto mb-0.5 size-3.5 text-primary" />
      <p className="truncate text-xs font-bold">{value}</p>
      <p className="truncate text-[8px] text-muted-foreground">{label}</p>
    </div>
  );
}

export { ProfileScreen };
