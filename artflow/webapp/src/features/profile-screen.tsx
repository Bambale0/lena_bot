import { useMemo, useState } from "react";
import { Copy, Gift, Globe2, History, Play, RefreshCw, Share2, Sparkles, Users, Wallet } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { GenerationTask, ReferralStats, UserProfile } from "@/lib/types";
import { firstMedia, formatCredits, formatRelativeDate, generationStatusLabel } from "@/lib/utils";

interface ProfileScreenProps {
  user: UserProfile;
  tasks: GenerationTask[];
  referrals: ReferralStats | null;
  referralsLoading: boolean;
  referralBusy?: boolean;
  onOpenTask: (task: GenerationTask) => void;
  onBalanceOpen: () => void;
  onRefreshReferrals: () => void;
  onReferralWithdraw: (amountRub: number, payoutDetails: string) => void;
  onReferralExchange: (amountRub: number) => void;
}

type ProfileSection = "works" | "partner" | "history";

function ProfileScreen({
  user,
  tasks,
  referrals,
  referralsLoading,
  referralBusy,
  onOpenTask,
  onBalanceOpen,
  onRefreshReferrals,
  onReferralWithdraw,
  onReferralExchange,
}: ProfileScreenProps) {
  const [section, setSection] = useState<ProfileSection>("works");
  const name = user.full_name || user.first_name || user.username || "Пользователь";
  const referralLink = referrals?.referral_link || user.referral_link || "";
  const invited = Number(referrals?.counts?.l1 || 0) + Number(referrals?.counts?.l2 || 0) + Number(referrals?.counts?.l3 || 0);
  const publishedTasks = tasks.filter((task) => Boolean(task.is_public_feed));
  const completedTasks = tasks.filter((task) => task.status === "done" || task.status === "completed");
  const failedTasks = tasks.filter((task) => task.status === "failed");

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
            <Button variant="soft" size="sm" onClick={onBalanceOpen}><span aria-hidden="true">💋</span> {formatCredits(user.credits)}</Button>
          </div>

          <div className="grid grid-cols-4 gap-1.5">
            <Stat label="История" value={tasks.length} icon={History} />
            <Stat label="Выложено" value={publishedTasks.length} icon={Globe2} />
            <Stat label="Приглашено" value={invited} icon={Users} />
            <Stat label="К выводу" value={formatCredits(referrals?.balance?.available_to_withdraw || user.referral_balance)} icon={Gift} />
          </div>
        </CardContent>
      </Card>

      <div className="apix-chip-rail flex gap-1 overflow-x-auto pb-1">
        <SectionButton active={section === "works"} onClick={() => setSection("works")}>Работы</SectionButton>
        <SectionButton active={section === "partner"} onClick={() => setSection("partner")}>Партнёрский кабинет</SectionButton>
        <SectionButton active={section === "history"} onClick={() => setSection("history")}>История задач</SectionButton>
      </div>

      {section === "works" ? (
        <section className="grid gap-3">
          <WorkGrid title="Выложенные работы" empty="Ты ещё ничего не выложил в профиль" tasks={publishedTasks} onOpenTask={onOpenTask} />
          <WorkGrid title="Все работы" empty="История пока пустая" tasks={tasks} onOpenTask={onOpenTask} />
        </section>
      ) : null}

      {section === "partner" ? (
        <ReferralCabinet
          referrals={referrals}
          loading={referralsLoading}
          busy={referralBusy}
          referralLink={referralLink}
          referralCode={referrals?.referral_code || user.referral_code || ""}
          onCopy={copy}
          onRefresh={onRefreshReferrals}
          onWithdraw={onReferralWithdraw}
          onExchange={onReferralExchange}
        />
      ) : null}

      {section === "history" ? (
        <Card>
          <CardHeader className="pb-2"><CardTitle>История задач</CardTitle></CardHeader>
          <CardContent className="grid gap-2">
            <div className="grid grid-cols-3 gap-1.5">
              <MiniStat label="Готово" value={completedTasks.length} />
              <MiniStat label="Ошибки" value={failedTasks.length} />
              <MiniStat label="Всего" value={tasks.length} />
            </div>
            <div className="grid gap-1.5">
              {tasks.map((task) => <HistoryRow key={task.id} task={task} onOpenTask={onOpenTask} />)}
              {!tasks.length ? <div className="rounded-xl border border-dashed border-border p-4 text-center text-xs text-muted-foreground">История пока пустая</div> : null}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function ReferralCabinet({
  referrals,
  loading,
  busy,
  referralLink,
  referralCode,
  onCopy,
  onRefresh,
  onWithdraw,
  onExchange,
}: {
  referrals: ReferralStats | null;
  loading: boolean;
  busy?: boolean;
  referralLink: string;
  referralCode: string;
  onCopy: (value: string, label: string) => void;
  onRefresh: () => void;
  onWithdraw: (amountRub: number, payoutDetails: string) => void;
  onExchange: (amountRub: number) => void;
}) {
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [payoutDetails, setPayoutDetails] = useState("");
  const [exchangeAmount, setExchangeAmount] = useState("");
  const balance = referrals?.balance || {};
  const counts = referrals?.counts || {};
  const available = Number(balance.available_to_withdraw || 0);
  const minWithdraw = Number(referrals?.withdraw_min_rub || 0);
  const minExchange = Number(referrals?.exchange_min_rub || 0);
  const children = useMemo(() => Object.entries(referrals?.children || {}), [referrals?.children]);

  const requestWithdraw = () => {
    const amount = Number(withdrawAmount);
    if (!Number.isFinite(amount) || amount <= 0) return toast.error("Укажи сумму вывода");
    if (!payoutDetails.trim()) return toast.error("Укажи реквизиты вывода");
    onWithdraw(amount, payoutDetails.trim());
  };

  const requestExchange = () => {
    const amount = Number(exchangeAmount);
    if (!Number.isFinite(amount) || amount <= 0) return toast.error("Укажи сумму обмена");
    onExchange(amount);
  };

  if (loading) {
    return <div className="rounded-xl border border-border p-4 text-center text-xs text-muted-foreground">Загружаем партнёрский кабинет…</div>;
  }

  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section className="grid gap-3">
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle>Партнёрская программа</CardTitle>
              <Button variant="ghost" size="sm" onClick={onRefresh}><RefreshCw className="size-4" /> Обновить</Button>
            </div>
          </CardHeader>
          <CardContent className="grid gap-2">
            <div className="grid grid-cols-3 gap-1.5">
              <MiniStat label="L1" value={Number(counts.l1 || 0)} />
              <MiniStat label="L2" value={Number(counts.l2 || 0)} />
              <MiniStat label="L3" value={Number(counts.l3 || 0)} />
            </div>
            <div className="rounded-xl border border-border bg-muted/35 p-3">
              <p className="text-[10px] text-muted-foreground">Реферальный код</p>
              <div className="mt-1 flex items-center gap-2">
                <p className="min-w-0 flex-1 truncate font-mono text-sm font-semibold">{referralCode || "—"}</p>
                <Button variant="ghost" size="icon" className="size-8" disabled={!referralLink} onClick={() => onCopy(referralLink, "Ссылка")} aria-label="Копировать"><Copy /></Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              <Button variant="outline" size="sm" disabled={!referralLink} onClick={() => onCopy(referralLink, "Ссылка")}><Copy /> Копировать</Button>
              <Button size="sm" disabled={!referralLink} onClick={() => onCopy(`Моя ссылка APIX: ${referralLink}`, "Текст для публикации")}><Share2 /> Текст поста</Button>
            </div>
            <div className="rounded-xl border border-border bg-muted/35 p-3 text-xs text-muted-foreground">
              <p className="font-semibold text-foreground">Правила партнёрской программы</p>
              <p className="mt-1">Бонус L1: +{formatCredits(referrals?.bonus_l1_credits)} 💋 начисляется один раз после первого успешного платного пополнения приглашённого.</p>
              <p className="mt-1">Регистрация или переход по реферальной ссылке сами по себе бонус не начисляют.</p>
              <p className="mt-1">Комиссии: L1 {formatCredits(referrals?.commission_l1)}% · L2 {formatCredits(referrals?.commission_l2)}% · L3 {formatCredits(referrals?.commission_l3)}%</p>
              <p className="mt-1">Награда за ремиксы из ленты: {formatCredits(referrals?.feed_remix_reward_rub)} ₽</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle>Приглашённые</CardTitle></CardHeader>
          <CardContent className="grid gap-2">
            {children.length ? children.map(([level, rows]) => (
              <section key={level} className="grid gap-1.5">
                <div className="flex items-center justify-between gap-2"><h3 className="text-xs font-semibold uppercase">{level}</h3><Badge variant="outline">{rows.length}</Badge></div>
                {rows.length ? rows.map((child) => (
                  <div key={`${level}-${child.id}`} className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card/55 px-2 py-1.5 text-xs">
                    <span className="min-w-0 truncate">{child.username ? `@${child.username}` : child.full_name || `ID ${child.id}`}</span>
                    <span className="shrink-0 text-muted-foreground">{child.generations_count || 0} gen · {formatCredits(child.paid_rub)} ₽</span>
                  </div>
                )) : <p className="text-xs text-muted-foreground">Пока нет пользователей на этом уровне</p>}
              </section>
            )) : <p className="text-xs text-muted-foreground">Backend пока не вернул список приглашённых.</p>}
          </CardContent>
        </Card>
      </section>

      <aside className="grid gap-3 self-start">
        <Card>
          <CardHeader className="pb-2"><CardTitle>Баланс партнёрки</CardTitle></CardHeader>
          <CardContent className="grid gap-2">
            <MiniStat label="Всего начислено" value={`${formatCredits(balance.total_earned)} ₽`} />
            <MiniStat label="В ожидании" value={`${formatCredits(balance.pending_withdrawals)} ₽`} />
            <MiniStat label="Доступно" value={`${formatCredits(available)} ₽`} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle>Вывод средств</CardTitle></CardHeader>
          <CardContent className="grid gap-2">
            <Input value={withdrawAmount} inputMode="decimal" placeholder={`Сумма, мин. ${formatCredits(minWithdraw)} ₽`} onChange={(event) => setWithdrawAmount(event.target.value)} />
            <Input value={payoutDetails} placeholder="Реквизиты: карта / USDT / контакт" onChange={(event) => setPayoutDetails(event.target.value)} />
            <Button disabled={busy || available <= 0} onClick={requestWithdraw}>Запросить вывод</Button>
            <p className="text-[10px] text-muted-foreground">Заявка уйдёт администраторам через backend, статус появится в истории.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle>Обмен в кредиты</CardTitle></CardHeader>
          <CardContent className="grid gap-2">
            <Input value={exchangeAmount} inputMode="decimal" placeholder={`Сумма, мин. ${formatCredits(minExchange)} ₽`} onChange={(event) => setExchangeAmount(event.target.value)} />
            <Button variant="outline" disabled={busy || available <= 0} onClick={requestExchange}>Обменять на кредиты</Button>
            <p className="text-[10px] text-muted-foreground">Курс: {formatCredits(referrals?.exchange_rate_rub_per_credit || 0)} ₽ за 1 кредит.</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle>История заявок</CardTitle></CardHeader>
          <CardContent className="grid gap-1.5">
            {referrals?.withdrawals?.length ? referrals.withdrawals.map((item) => (
              <div key={item.id} className="rounded-xl border border-border bg-card/55 p-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <strong>{formatCredits(item.amount_rub)} ₽</strong>
                  <Badge variant="outline">{item.status}</Badge>
                </div>
                <p className="mt-1 truncate text-[10px] text-muted-foreground">{item.payout_details === "AUTO_CREDITS" ? `Обмен на ${formatCredits(item.amount_credits)} кр.` : item.payout_details}</p>
              </div>
            )) : <p className="text-xs text-muted-foreground">Заявок пока нет</p>}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function SectionButton({ active, children, onClick }: { active: boolean; children: string; onClick: () => void }) {
  return <button type="button" className={`apix-focus-ring shrink-0 rounded-xl border px-3 py-2 text-xs font-semibold ${active ? "border-primary/55 bg-primary/15 text-primary" : "border-border bg-card/55 text-muted-foreground"}`} onClick={onClick}>{children}</button>;
}

function WorkGrid({ title, empty, tasks, onOpenTask }: { title: string; empty: string; tasks: GenerationTask[]; onOpenTask: (task: GenerationTask) => void }) {
  return (
    <section>
      <div className="mb-1.5 flex items-center justify-between gap-2"><h2 className="text-sm font-semibold tracking-tight">{title}</h2><Badge variant="outline">{tasks.length}</Badge></div>
      {tasks.length ? (
        <div className="grid grid-cols-2 gap-1.5 min-[390px]:grid-cols-3 sm:grid-cols-4 xl:grid-cols-5">
          {tasks.map((task) => <TaskTile key={task.id} task={task} onOpenTask={onOpenTask} />)}
        </div>
      ) : <div className="grid min-h-24 place-items-center rounded-xl border border-dashed border-border text-xs text-muted-foreground">{empty}</div>}
    </section>
  );
}

function TaskTile({ task, onOpenTask }: { task: GenerationTask; onOpenTask: (task: GenerationTask) => void }) {
  const media = firstMedia(task);
  const video = task.gen_type === "video" || /\.(mp4|webm|mov)(\?|$)/i.test(media);
  return (
    <button type="button" className="apix-focus-ring apix-glass overflow-hidden rounded-xl text-left transition active:scale-[0.98]" onClick={() => onOpenTask(task)}>
      <div className="relative aspect-square bg-muted">
        {media ? video ? <video src={media} muted playsInline preload="metadata" className="size-full object-cover" /> : <img src={media} alt="" loading="lazy" className="size-full object-cover" /> : <div className="grid size-full place-items-center text-muted-foreground"><Sparkles className="size-4" /></div>}
        {video ? <span className="absolute inset-0 grid place-items-center"><span className="grid size-8 place-items-center rounded-full bg-black/55 text-white"><Play className="ml-0.5 size-3.5" /></span></span> : null}
        <Badge variant={task.status === "failed" ? "destructive" : task.status === "done" ? "success" : "warning"} className="absolute left-1 top-1 px-1.5 py-0 text-[8px]">{generationStatusLabel(task.status)}</Badge>
        {task.is_public_feed ? <Badge variant="outline" className="absolute bottom-1 left-1 bg-background/80 px-1.5 py-0 text-[8px]">в профиле</Badge> : null}
      </div>
      <div className="px-2 py-1.5"><p className="truncate text-[10px] font-semibold">{task.model}</p><p className="mt-0.5 flex justify-between gap-1 text-[9px] text-muted-foreground"><span>{formatRelativeDate(task.created_at)}</span><span>{formatCredits(task.credits_spent)}</span></p></div>
    </button>
  );
}

function HistoryRow({ task, onOpenTask }: { task: GenerationTask; onOpenTask: (task: GenerationTask) => void }) {
  return (
    <button type="button" className="apix-focus-ring flex items-center gap-2 rounded-xl border border-border bg-card/55 p-2 text-left" onClick={() => onOpenTask(task)}>
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Sparkles className="size-4" /></span>
      <span className="min-w-0 flex-1"><span className="block truncate text-xs font-semibold">{task.model}</span><span className="block truncate text-[10px] text-muted-foreground">{formatRelativeDate(task.created_at)} · {formatCredits(task.credits_spent)} кр.</span></span>
      <Badge variant={task.status === "failed" ? "destructive" : task.status === "done" ? "success" : "warning"}>{generationStatusLabel(task.status)}</Badge>
    </button>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return <div className="rounded-xl border border-border bg-card/55 px-2 py-2 text-center"><p className="truncate text-sm font-bold">{value}</p><p className="truncate text-[9px] text-muted-foreground">{label}</p></div>;
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
