import { Copy, Gift, History, Share2, Sparkles, Users, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
    <div className="grid gap-5">
      <Card className="overflow-hidden">
        <div className="h-28 bg-gradient-to-r from-primary/45 via-fuchsia-500/25 to-cyan-400/25" />
        <CardContent className="relative grid gap-4 pb-5">
          <div className="-mt-11 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="flex min-w-0 items-end gap-3">
              <span className="grid size-24 shrink-0 place-items-center overflow-hidden rounded-3xl border-4 border-background bg-gradient-to-br from-primary to-cyan-400 text-3xl font-bold text-white shadow-xl">
                {user.photo_url ? <img src={user.photo_url} alt="" className="size-full object-cover" /> : name.slice(0, 1).toUpperCase()}
              </span>
              <div className="min-w-0 pb-1">
                <h1 className="truncate text-2xl font-bold tracking-tight">{name}</h1>
                <p className="truncate text-sm text-muted-foreground">{user.username ? `@${user.username}` : "Telegram-профиль"}</p>
              </div>
            </div>
            <Button variant="soft" onClick={onBalanceOpen}><Wallet /> {formatCredits(user.credits)} кр.</Button>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Задач" value={tasks.length} icon={History} />
            <Stat label="Приглашено" value={invited} icon={Users} />
            <Stat label="Партнёрский баланс" value={formatCredits(referrals?.balance?.available_to_withdraw || user.referral_balance)} icon={Gift} />
            <Stat label="Всего заработано" value={formatCredits(referrals?.balance?.total_earned)} icon={Sparkles} />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section>
          <div className="mb-3">
            <h2 className="text-xl font-semibold tracking-tight">История</h2>
            <p className="text-sm text-muted-foreground">Приватные задачи видны только владельцу.</p>
          </div>
          {tasks.length ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {tasks.map((task) => {
                const media = firstMedia(task);
                const video = task.gen_type === "video";
                return (
                  <button
                    key={task.id}
                    type="button"
                    className="apix-focus-ring apix-glass overflow-hidden rounded-2xl text-left transition hover:-translate-y-0.5 hover:border-primary/30"
                    onClick={() => onOpenTask(task)}
                  >
                    <div className="aspect-video bg-muted">
                      {media ? (
                        video ? <video src={media} muted playsInline preload="metadata" className="size-full object-cover" /> : <img src={media} alt="" loading="lazy" className="size-full object-cover" />
                      ) : <div className="grid size-full place-items-center text-muted-foreground"><Sparkles /></div>}
                    </div>
                    <div className="grid gap-1 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-semibold">{task.model}</span>
                        <Badge variant={task.status === "failed" ? "destructive" : task.status === "done" ? "success" : "warning"}>{generationStatusLabel(task.status)}</Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">{formatRelativeDate(task.created_at)} · {formatCredits(task.credits_spent)} кр.</span>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="grid min-h-48 place-items-center rounded-2xl border border-dashed border-border text-sm text-muted-foreground">История пока пустая</div>
          )}
        </section>

        <aside>
          <Card>
            <CardHeader>
              <CardTitle>Партнёрская программа</CardTitle>
              <CardDescription>Существующая привязка реферала не перезаписывается новой ссылкой.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {referralsLoading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground"><span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" /> Загружаем статистику…</div>
              ) : (
                <>
                  <div className="rounded-2xl border border-border bg-muted/35 p-4">
                    <p className="text-xs text-muted-foreground">Реферальный код</p>
                    <p className="mt-1 font-mono text-lg font-semibold">{referrals?.referral_code || user.referral_code || "—"}</p>
                  </div>
                  <Button variant="outline" disabled={!referralLink} onClick={() => copy(referralLink, "Ссылка")}>
                    <Copy /> Копировать ссылку
                  </Button>
                  <Button disabled={!referralLink} onClick={() => copy(referralLink, "Ссылка для публикации")}>
                    <Share2 /> Поделиться
                  </Button>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Вознаграждения за повтор работ проходят через серверный ledger и не зависят от данных frontend.
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof History }) {
  return (
    <div className="rounded-2xl border border-border bg-card/55 p-3">
      <Icon className="mb-2 size-4 text-primary" />
      <p className="text-lg font-bold">{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  );
}

export { ProfileScreen };
