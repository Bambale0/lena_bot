import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Film, ImageIcon, LoaderCircle, Music2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GenerationTask, ModelInfo } from "@/lib/types";
import { firstMedia, formatRelativeDate, generationStatusLabel, isPendingTask } from "@/lib/utils";

type WorkFilter = "all" | "active" | "done" | "failed";
interface WorksScreenProps {
  tasks: GenerationTask[];
  models: ModelInfo[];
  language?: string;
  unavailable?: boolean;
  refreshing?: boolean;
  onOpenTask: (task: GenerationTask) => void;
  onCreate: () => void;
  onRefresh: () => void;
}
const PAGE_SIZE = 36;
const done = (task: GenerationTask) => ["done", "completed"].includes(task.status);

export function WorksScreen({ tasks, models, language, unavailable, refreshing, onOpenTask, onCreate, onRefresh }: WorksScreenProps) {
  const en = language === "en";
  const [filter, setFilter] = useState<WorkFilter>("all");
  const [limit, setLimit] = useState(PAGE_SIZE);
  const filtered = useMemo(() => tasks.filter(task => filter === "all" || (filter === "active" ? isPendingTask(task) : filter === "done" ? done(task) : task.status === "failed"))
    .sort((a, b) => Number(isPendingTask(b)) - Number(isPendingTask(a)) || (Date.parse(b.created_at || "") || 0) - (Date.parse(a.created_at || "") || 0) || b.id - a.id), [tasks, filter]);
  const filters: Array<[WorkFilter, string]> = [["all", en ? "All" : "Все"], ["active", en ? "In progress" : "В работе"], ["done", en ? "Ready" : "Готовые"], ["failed", en ? "Errors" : "Ошибки"]];
  return <div className="ux2-page">
    <header className="ux2-page-title ux2-title-actions">
      <div><h1>{en ? "My works" : "Мои работы"}</h1><p>{en ? `${tasks.length} loaded. Private results stay here too.` : `Загружено: ${tasks.length}. Неопубликованные результаты тоже здесь.`}</p></div>
      <Button variant="ghost" size="icon" aria-label={en ? "Refresh works" : "Обновить работы"} disabled={refreshing} onClick={onRefresh}><RefreshCw className={refreshing ? "animate-spin" : ""} /></Button>
    </header>
    {unavailable && <div className="ux2-inline-notice" role="alert"><AlertCircle size={20} aria-hidden="true" /><span>{en ? "Could not load history. Try refreshing; your works have not been deleted." : "Не удалось загрузить историю. Обновите список — ваши работы не удалены."}</span></div>}
    <div className="ux2-work-filters" aria-label={en ? "Work status" : "Статус работ"}>
      {filters.map(([value, label]) => <button key={value} type="button" className="apix-focus-ring" aria-pressed={filter === value} onClick={() => { setFilter(value); setLimit(PAGE_SIZE); }}>{label}</button>)}
    </div>
    {filtered.length ? <>
      <div className="ux2-works-grid">{filtered.slice(0, limit).map(task => <WorkTile key={task.id} task={task} model={models.find(model => model.key === task.model)} en={en} onOpen={onOpenTask} />)}</div>
      {filtered.length > limit && <Button variant="outline" onClick={() => setLimit(value => value + PAGE_SIZE)}>{en ? "Show more" : "Показать ещё"}</Button>}
    </> : !unavailable && <div className="ux2-empty-state">
      <ImageIcon size={36} aria-hidden="true" />
      <h2>{filter === "all" ? (en ? "Your first work starts here" : "Здесь будет ваша первая работа") : (en ? "No works with this status" : "Работ с таким статусом пока нет")}</h2>
      <p>{en ? "Start creating or select another filter." : "Начните создание или выберите другой фильтр."}</p>
      <Button onClick={filter === "all" ? onCreate : () => setFilter("all")}>{filter === "all" ? (en ? "Create" : "Создать") : (en ? "Show all" : "Показать все")}</Button>
    </div>}
  </div>;
}

function WorkTile({ task, model, en, onOpen }: { task: GenerationTask; model?: ModelInfo; en: boolean; onOpen: (task: GenerationTask) => void }) {
  const [broken, setBroken] = useState(false);
  const media = firstMedia(task);
  useEffect(() => setBroken(false), [media]);
  const isVideo = task.gen_type === "video";
  const Icon = isVideo ? Film : ["music", "audio"].includes(task.gen_type) ? Music2 : ImageIcon;
  const running = isPendingTask(task);
  const status = en ? (done(task) ? "Ready" : running ? "In progress" : task.status === "failed" ? "Error" : "Checking status") : generationStatusLabel(task.status);
  const title = (!task.prompt_hidden && task.prompt_actions_allowed !== false && task.prompt?.trim()) || model?.display_name || (isVideo ? (en ? "Video" : "Видео") : (en ? "Work" : "Работа"));
  return <button type="button" className="ux2-work-tile apix-focus-ring" onClick={() => onOpen(task)} aria-label={`${title} — ${status}`}>
    <span className="ux2-work-preview">
      {media && !broken ? (/\.(mp4|webm|mov)(\?|$)/i.test(media)
        ? <video src={media} muted playsInline preload="none" onError={() => setBroken(true)} />
        : <img src={media} alt="" loading="lazy" onError={() => setBroken(true)} />)
        : <Icon size={32} aria-hidden="true" />}
      <span className="ux2-work-status" data-status={task.status === "failed" ? "failed" : done(task) ? "done" : "pending"}>
        {running && <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />}{status}
      </span>
    </span>
    <span className="ux2-work-caption"><strong>{title}</strong><span>{formatRelativeDate(task.created_at)}</span></span>
  </button>;
}
