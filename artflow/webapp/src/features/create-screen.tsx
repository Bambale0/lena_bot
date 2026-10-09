import { ArrowUpRight, Bot, Film, ImageIcon, Orbit, PencilLine } from "lucide-react";
import type { AppTab, GenerationDraft, ModelInfo } from "@/lib/types";
import { hasDraftInput } from "@/lib/draft-storage";

interface CreateScreenProps {
  imageModels: ModelInfo[];
  videoModels: ModelInfo[];
  drafts: GenerationDraft[];
  language?: string;
  onNavigate: (tab: AppTab) => void;
}

export function CreateScreen({ imageModels, videoModels, drafts, language, onNavigate }: CreateScreenProps) {
  const en = language === "en";
  const motion = videoModels.filter(model => model.modes?.includes("motion") || /motion/i.test(model.key));
  const videos = videoModels.filter(model => !motion.includes(model));
  const actions = [
    { tab: "photo" as const, icon: ImageIcon, title: en ? "Photo" : "Фото", detail: en ? "Create or edit an image" : "Создать или изменить изображение", available: imageModels.length > 0 },
    { tab: "video" as const, icon: Film, title: en ? "Video" : "Видео", detail: en ? "From an idea or your media" : "Из описания или ваших материалов", available: videos.length > 0 },
    { tab: "motion" as const, icon: Orbit, title: en ? "Transfer motion" : "Перенести движение", detail: en ? "Character photo and a motion video" : "Фото персонажа и видео движения", available: motion.length > 0 },
    { tab: "services" as const, icon: Bot, title: en ? "Tools" : "Инструменты", detail: en ? "Assistant, prompts and music" : "Помощник, промпты и музыка", available: true },
  ];
  const saved = drafts.filter(hasDraftInput);
  return <div className="ux2-page">
    <header className="ux2-page-title">
      <h1>{en ? "What will you create?" : "Что создадим?"}</h1>
      <p>{en ? "Choose a task. Your media and settings stay in your draft." : "Выберите задачу. Материалы и настройки останутся в черновике."}</p>
    </header>
    <div className="ux2-create-grid">
      {actions.map(({ tab, icon: Icon, title, detail, available }) => <button type="button" key={tab}
        className="ux2-create-card apix-focus-ring" disabled={!available} onClick={() => onNavigate(tab)}>
        <span className="ux2-create-icon"><Icon size={26} aria-hidden="true" /></span>
        <ArrowUpRight className="ux2-create-arrow" size={20} aria-hidden="true" />
        <strong>{title}</strong><span>{detail}</span>
        {!available && <small>{en ? "Temporarily unavailable" : "Временно недоступно"}</small>}
      </button>)}
    </div>
    <section className="ux2-drafts-section" aria-label={en ? "Drafts" : "Черновики"}>
      <h2>{en ? "Continue a draft" : "Продолжить черновик"}</h2>
      <p className="ux2-hint">{en ? "Saved in this browser tab. Check your media before submitting." : "Сохраняются в этой вкладке. Перед запуском проверьте материалы."}</p>
      {saved.length ? saved.map(draft => <button key={draft.kind} type="button" className="ux2-draft-row apix-focus-ring"
        onClick={() => onNavigate(draft.kind === "image" ? "photo" : draft.kind)}>
        <PencilLine size={20} aria-hidden="true" />
        <span><strong>{draft.kind === "image" ? (en ? "Photo" : "Фото") : draft.kind === "video" ? (en ? "Video" : "Видео") : (en ? "Motion" : "Движение")}</strong>
          <span>{draft.prompt.trim() || (en ? "Media added" : "Материалы добавлены")}</span></span>
        <ArrowUpRight size={18} aria-hidden="true" />
      </button>) : <div className="ux2-empty-draft">{en ? "Your draft will appear as you fill in the editor." : "Черновик появится, когда вы начнёте заполнять редактор."}</div>}
    </section>
  </div>;
}
