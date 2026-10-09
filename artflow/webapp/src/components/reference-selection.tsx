import { ImageIcon, X } from "lucide-react";
import type { GenerationDraft, ModelInfo } from "@/lib/types";
import { inspectDraftMedia } from "@/lib/draft-media";
import { deleteReferenceMaterial, referenceMaterials, setReferenceIncluded } from "@/lib/reference-selection";

interface ReferenceSelectionProps {
  draft: GenerationDraft;
  model?: ModelInfo;
  busy: boolean;
  language?: string;
  labelFor: (url: string) => string;
  onChange: (patch: Partial<GenerationDraft>) => void;
}

export function ReferenceSelection({ draft, model, busy, language, labelFor, onChange }: ReferenceSelectionProps) {
  const en = language === "en";
  const items = referenceMaterials(draft);
  const active = items.filter(item => item.included).length;
  if (!items.length) return null;
  return <div className="ux2-reference-selection">
    <p className="ux2-reference-summary" aria-live="polite">{en ? `In this run: ${active} of ${items.length}` : `В запуске: ${active} из ${items.length}`}</p>
    <p className="ux2-reference-help">{en ? "Uncheck a photo to keep it for later. Delete removes it from the draft." : "Снимите отметку, чтобы оставить фото на потом. «Удалить» уберёт его из черновика."}</p>
    {items.map((item, index) => {
      const candidate = setReferenceIncluded(draft, item.id, true);
      const conflict = !item.included ? inspectDraftMedia(candidate, model).issues.find(issue => issue.code.startsWith("reference_") || issue.code === "model_unavailable" || issue.code === "mode_unsupported") : undefined;
      const name = labelFor(item.url);
      const reasonId = `reference-reason-${item.id}`;
      return <div key={item.id} className="ux2-reference-row" data-reference-id={item.id} data-included={item.included}
        role="group" aria-label={`${en ? "Photo" : "Фото"} ${index + 1}: ${name}`}>
        <div className="ux2-reference-name"><ImageIcon size={18} aria-hidden="true" /><span>{name}</span></div>
        <button type="button" disabled={busy} className="ux2-reference-delete apix-focus-ring" aria-label={en ? "Remove reference" : "Убрать референс"}
          onClick={() => { if (!busy) onChange(deleteReferenceMaterial(draft, item.id)); }}><X size={16} aria-hidden="true" />{en ? "Delete" : "Удалить"}</button>
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
        {conflict && <p id={reasonId} className="ux2-reference-reason">{en ? "This photo cannot be included with the current model, mode or limit. Change settings or exclude another photo." : "Сейчас включить нельзя: проверьте модель, режим и лимит фото. Можно исключить другое фото или сменить настройки."}</p>}
      </div>;
    })}
  </div>;
}
