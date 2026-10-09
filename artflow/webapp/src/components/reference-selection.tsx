import { useCallback, useEffect, useState } from "react";
import { ImageIcon, LoaderCircle, RotateCcw, X } from "lucide-react";
import type { GenerationDraft, ModelInfo, ReferenceMaterial } from "@/lib/types";
import type { PhotoUploadControls } from "@/lib/photo-upload-queue";
import { inspectDraftMedia } from "@/lib/draft-media";
import { photoUploadMessage, safePhotoUrl } from "@/lib/photo-upload";
import { deleteReferenceMaterial, referenceMaterials, setReferenceIncluded } from "@/lib/reference-selection";
import { Sheet } from "@/components/ui/sheet";

interface ReferenceSelectionProps {
  draft: GenerationDraft; model?: ModelInfo; busy: boolean; submitting?: boolean;
  language?: string; labelFor: (url: string) => string; onChange: (patch: Partial<GenerationDraft>) => void;
  uploads?: PhotoUploadControls;
}
function fileSize(size?: number): string {
  if (size === undefined) return "";
  return size >= 1024 * 1024 ? `${(size / (1024 * 1024)).toFixed(1)} MiB` : `${Math.max(1, Math.round(size / 1024))} KiB`;
}
function photoSource(item: ReferenceMaterial, uploads?: PhotoUploadControls): string {
  if (item.url && safePhotoUrl(item.url)) return item.url;
  return uploads?.preview(item.id) || "";
}
function Thumbnail({ source, index, onOpen, disabled }: { source: string; index: number; onOpen: () => void; disabled: boolean }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [source]);
  return <button type="button" className="ux2-reference-preview apix-focus-ring" aria-label={`Открыть фото ${index + 1}`}
    disabled={disabled || !source} onClick={onOpen}>
    {source && !broken ? <img src={source} alt={`Фото ${index + 1}`} referrerPolicy="no-referrer" onError={() => setBroken(true)} /> : <ImageIcon size={26} aria-hidden="true" />}
    {broken && <span>Нет превью</span>}
  </button>;
}

function PhotoViewer({ source, name, en }: { source: string; name: string; en: boolean }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [source]);
  return source && !broken
    ? <img className="ux2-photo-original" src={source} alt={name} referrerPolicy="no-referrer" onError={() => setBroken(true)} />
    : <p className="ux2-inline-notice" role="status">{en ? "Preview could not be opened. The file is kept in your draft." : "Не удалось открыть превью. Файл сохранён в черновике."}</p>;
}

export function ReferenceSelection({ draft, model, busy, submitting = false, language, labelFor, onChange, uploads }: ReferenceSelectionProps) {
  const en = language === "en";
  const items = referenceMaterials(draft);
  const [viewId, setViewId] = useState<string | null>(null);
  const closeView = useCallback((open: boolean) => { if (!open) setViewId(null); }, []);
  const viewed = items.find(item => item.id === viewId);
  const active = items.filter(item => item.included && item.url && !item.upload).length;
  if (!items.length) return null;
  return <div className="ux2-reference-selection">
    <p className="ux2-reference-summary" aria-live="polite">{en ? `In this run: ${active} of ${items.length}` : `В запуске: ${active} из ${items.length}`}</p>
    <p className="ux2-reference-help">{en ? "Uncheck a photo to keep it for later. Delete removes it from the draft." : "Снимите отметку, чтобы оставить фото на потом. «Удалить» уберёт его из черновика."}</p>
    {items.map((item, index) => {
      const candidate = setReferenceIncluded(draft, item.id, true);
      const conflict = !item.included ? inspectDraftMedia(candidate, model).issues.find(issue => issue.code.startsWith("reference_") || issue.code === "model_unavailable" || issue.code === "mode_unsupported") : undefined;
      const name = item.name || (item.url ? labelFor(item.url) : item.upload?.name) || (en ? "Photo" : "Фото");
      const reasonId = `reference-reason-${item.id}`;
      const stage = item.upload?.status || "ready";
      const replacement = Boolean(item.url && item.upload);
      const hasSource = Boolean(uploads?.hasSource(item.id));
      const canRetry = hasSource && !["invalid_file", "empty_file", "too_large", "source_required"].includes(item.upload?.error || "");
      const source = photoSource(item, uploads);
      const status = stage === "queued" ? (en ? "Queued" : "Ожидает загрузки") : stage === "uploading" ? (en ? "Uploading" : "Загружается")
        : stage === "error" ? (en ? "Upload error" : "Ошибка загрузки") : item.name ? (en ? "Uploaded" : "Загружено") : (en ? "Added by link" : "Добавлено по ссылке");
      return <div key={item.id} className="ux2-reference-row ux2-photo-row" data-reference-id={item.id} data-included={item.included} data-upload-state={stage}
        role="group" aria-label={`${en ? "Photo" : "Фото"} ${index + 1}: ${name}`}>
        <Thumbnail source={source} index={index} disabled={submitting} onOpen={() => setViewId(item.id)} />
        <div className="ux2-photo-description">
          <div className="ux2-reference-name"><span title={name}>{name}</span></div>
          <p className="ux2-photo-metadata">{fileSize(item.size ?? item.upload?.size)}{(item.contentType || item.upload?.contentType) ? ` · ${(item.contentType || item.upload?.contentType)?.replace("image/", "").toUpperCase()}` : ""}</p>
          <p className="ux2-photo-status" role="status">{stage === "uploading" && <LoaderCircle size={14} className="animate-spin" aria-hidden="true" />}{replacement ? (en ? "Replacement: " : "Замена: ") : ""}{status}</p>
        </div>
        <label className="ux2-reference-toggle">
          <input type="checkbox" checked={item.included} disabled={busy || Boolean(conflict)}
            aria-label={en ? `Use photo ${index + 1}` : `Использовать фото ${index + 1}`}
            aria-describedby={conflict ? reasonId : undefined}
            onChange={event => {
              if (busy || (event.currentTarget.checked && conflict)) return;
              onChange(setReferenceIncluded(draft, item.id, event.currentTarget.checked));
              window.dispatchEvent(new CustomEvent("apix:reference-selection", { detail: { action: event.currentTarget.checked ? "include" : "exclude", total: items.length } }));
            }} />
          <span>{item.included ? (en ? "In this run" : "В запуске") : (en ? "Not used" : "Не используется")}</span>
        </label>
        <div className="ux2-photo-actions">
          {uploads && item.upload && stage !== "error" ? <button type="button" disabled={submitting} className="apix-focus-ring"
            aria-label={`Отменить загрузку фото ${index + 1}`} onClick={() => uploads.cancel(item.id)}>{en ? "Cancel upload" : "Отменить загрузку"}</button> : <>
            {uploads && stage === "error" && canRetry && <button type="button" className="apix-focus-ring" disabled={busy}
              aria-label={`Повторить загрузку фото ${index + 1}`} onClick={() => uploads.retry(item.id)}><RotateCcw size={16} aria-hidden="true" />{en ? "Retry" : "Повторить"}</button>}
            {uploads && <label className="ux2-photo-replace apix-focus-ring">{item.upload ? (en ? "Choose again" : "Выбрать снова") : (en ? "Replace" : "Заменить")}
              <input type="file" accept="image/jpeg,image/png,image/webp" aria-label={`${item.upload ? "Выбрать снова фото" : "Заменить фото"} ${index + 1}`} disabled={busy}
                onChange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ""; if (file && !busy) uploads.replace(item.id, file); }} />
            </label>}
            {uploads && replacement && <button type="button" className="apix-focus-ring" disabled={busy} onClick={() => uploads.cancel(item.id)}>{en ? "Keep original" : "Оставить прежнее"}</button>}
            <button type="button" disabled={busy} className="ux2-reference-delete apix-focus-ring" aria-label={en ? "Remove reference" : "Убрать референс"}
              onClick={() => { if (!busy) uploads ? uploads.remove(item.id) : onChange(deleteReferenceMaterial(draft, item.id)); }}><X size={16} aria-hidden="true" />{en ? "Delete" : "Удалить"}</button>
          </>}
        </div>
        {stage === "error" && <p className="ux2-photo-error" role="status">{photoUploadMessage(!hasSource ? "source_required" : item.upload?.error, en)}{replacement ? (en ? " The original is kept until you confirm the replacement." : " Предыдущее фото сохранено.") : ""}</p>}
        {conflict && <p id={reasonId} className="ux2-reference-reason">{en ? "This photo cannot be included with the current model, mode or limit. Check upload and settings." : "Сейчас включить нельзя: проверьте загрузку, модель, режим и лимит фото."}</p>}
      </div>;
    })}
    <Sheet open={Boolean(viewed)} title={en ? "Photo preview" : "Просмотр фото"} onOpenChange={closeView}>
      {viewed && <PhotoViewer source={photoSource(viewed, uploads)} name={viewed.name || viewed.upload?.name || (en ? "Photo" : "Фото")} en={en} />}
    </Sheet>
  </div>;
}
