import React, { useMemo, useRef, useState } from "react";
import Icon from "./icons.jsx";
import {
  copyText,
  formatCompact,
  generationPreviewUrls,
  telegramInitData,
} from "./api.js";
import { EmptyState, Loading, ProgressiveMedia } from "./components.jsx";

const CATEGORIES = [
  ["all", "Все", "sparkle"],
  ["cinematic", "Кинематик", "video"],
  ["realism", "Реализм", "user"],
  ["neon", "Неон", "sparkle"],
  ["portrait", "Портрет", "camera"],
  ["photo", "Фото", "image"],
  ["video", "Видео", "play"],
];

function promptText(item) {
  return String(item.prompt_text || item.prompt || item.description || "").trim();
}

function PromptCard({ item, index, onUse, onCopy }) {
  const text = promptText(item);
  const preview = item.preview_url || item.image_url || generationPreviewUrls(item)[0];
  const category = item.category || item.model || (index % 2 ? "Реализм" : "Кинематик");

  return (
    <article className="cxPromptCard">
      <div className="cxPromptCard__media">
        <ProgressiveMedia item={item} sources={[preview]} compact/>
        <span>{category}</span>
      </div>
      <div className="cxPromptCard__body">
        <header>
          <div><h3>{item.title || "Кинематографичный промпт"}</h3><span><Icon name="sparkle" size={13}/>{formatCompact(item.uses_count || item.likes_count || 0)}</span></div>
          <button type="button" onClick={() => onCopy(text)} aria-label="Копировать"><Icon name="copy" size={19}/></button>
        </header>
        <p>{text.length > 145 ? `${text.slice(0, 142)}…` : text || "Готовый промпт для создания выразительного визуального образа."}</p>
        <footer>
          <div><span>{category}</span>{item.gen_type && <span>{item.gen_type === "video" ? "Видео" : "Фото"}</span>}</div>
          <button type="button" onClick={() => onUse(item)}>Использовать<Icon name="chevron" size={14}/></button>
        </footer>
      </div>
    </article>
  );
}

export default function PromptsScreen({ prompts, loading, onUse, onNotice, onNavigate }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [tab, setTab] = useState("popular");
  const [photoPrompt, setPhotoPrompt] = useState("");
  const [photoBusy, setPhotoBusy] = useState(false);
  const fileRef = useRef(null);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    let result = prompts.filter((item) => {
      const text = `${item.title || ""} ${promptText(item)} ${item.category || ""} ${item.model || ""}`.toLowerCase();
      if (needle && !text.includes(needle)) return false;
      if (category === "all") return true;
      if (category === "photo") return item.gen_type !== "video";
      if (category === "video") return item.gen_type === "video";
      return text.includes(category);
    });

    if (tab === "saved") result = result.filter((item) => item.is_mine || item.owner_is_me || item.saved_by_me);
    if (tab === "new") result = [...result].sort((a, b) => Date.parse(b.created_at || 0) - Date.parse(a.created_at || 0));
    if (tab === "popular") result = [...result].sort((a, b) => Number(b.uses_count || b.likes_count || 0) - Number(a.uses_count || a.likes_count || 0));
    return result;
  }, [prompts, query, category, tab]);

  async function copy(value) {
    if (!value) return;
    if (await copyText(value)) onNotice({ type: "success", message: "Промпт скопирован" });
  }

  async function analyzePhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setPhotoBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/v1/photo-prompt", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": telegramInitData() },
        body: form,
      });
      if (!response.ok) throw new Error("Не удалось разобрать фото");
      const result = await response.json();
      setPhotoPrompt(result.prompt || "");
      onNotice({ type: "success", message: "Промпт готов" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось создать промпт" });
    } finally {
      setPhotoBusy(false);
    }
  }

  return (
    <section className="cxScreen cxPromptsScreen">
      <div className="cxPromptLead">
        <label className="cxSearchField cxSearchField--wide">
          <Icon name="search" size={20}/>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск промптов..."/>
          {query && <button type="button" onClick={() => setQuery("")}><Icon name="close" size={16}/></button>}
        </label>
        <button className="cxCreateQuick cxCreateQuick--wide" type="button" onClick={() => onNavigate("create")}><Icon name="plus" size={18}/>Создать</button>
      </div>

      <div className="cxCategoryRail">
        {CATEGORIES.map(([key, label, icon]) => (
          <button key={key} type="button" className={category === key ? "active" : ""} onClick={() => setCategory(key)}>
            <Icon name={icon} size={16}/><span>{label}</span>
          </button>
        ))}
      </div>

      <div className="cxPromptTabs">
        <button type="button" className={tab === "popular" ? "active" : ""} onClick={() => setTab("popular")}>Популярные</button>
        <button type="button" className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>Новые</button>
        <button type="button" className={tab === "saved" ? "active" : ""} onClick={() => setTab("saved")}>Сохранённые</button>
      </div>

      <section className="cxPhotoPromptTool">
        <div className="cxPhotoPromptTool__icon"><Icon name="camera" size={23}/><i/></div>
        <div><h2>Промпт по фото</h2><p>Загрузи референс — AI восстановит описание и стиль.</p></div>
        <button type="button" onClick={() => fileRef.current?.click()} disabled={photoBusy}>{photoBusy ? "Анализ..." : "Загрузить"}</button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={analyzePhoto}/>
        {photoPrompt && (
          <article className="cxPhotoPromptResult">
            <p>{photoPrompt}</p>
            <div>
              <button type="button" onClick={() => copy(photoPrompt)}><Icon name="copy" size={17}/>Копировать</button>
              <button className="cxPrimaryButton" type="button" onClick={() => onUse({ title: "Промпт по фото", prompt_text: photoPrompt })}><Icon name="sparkle" size={17}/>Создать</button>
            </div>
          </article>
        )}
      </section>

      {loading ? <Loading label="Загружаем идеи"/> : filtered.length ? (
        <div className="cxPromptList">
          {filtered.map((item, index) => <PromptCard key={item.id || index} item={item} index={index} onUse={onUse} onCopy={copy}/>) }
        </div>
      ) : (
        <EmptyState icon="prompt" title="Ничего не найдено" text="Измени запрос или выбери другую категорию."/>
      )}
    </section>
  );
}
