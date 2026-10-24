import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Film, ImageIcon, Music2, Search } from "lucide-react";
import { MiniAppApi } from "@/lib/api";
import { formatCredits } from "@/lib/utils";
import type { ModelInfo } from "@/lib/types";

interface Props { api: MiniAppApi; imageModels: ModelInfo[]; videoModels: ModelInfo[]; onSelect: (model: ModelInfo, kind: "image" | "video" | "music") => void; }

export function LilacModels({ api, imageModels, videoModels, onSelect }: Props) {
  const [kind, setKind] = useState<"image" | "video" | "music">("image");
  const [query, setQuery] = useState("");
  const [music, setMusic] = useState<ModelInfo[]>([]);
  const [musicState, setMusicState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  useEffect(() => {
    if (kind !== "music") return;
    const controller = new AbortController(); setMusicState("loading");
    api.request<ModelInfo[]>("/models/music", {}, controller.signal).then(rows => { setMusic(rows); setMusicState("ready"); }).catch(() => { if (!controller.signal.aborted) setMusicState("error"); });
    return () => controller.abort();
  }, [api, kind]);
  const all = kind === "image" ? imageModels : kind === "video" ? videoModels : music;
  const rows = useMemo(() => all.filter(model => `${model.display_name} ${model.description || ""}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())), [all, query]);
  return <div className="lilac-page"><header className="lilac-title"><p>Каталог возможностей</p><h1>Нейросети</h1><span>Модели, параметры и цены из вашего каталога APIX.</span></header>
    <label className="lilac-search"><Search size={18} /><input aria-label="Найти нейросеть" placeholder="Поиск по моделям" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <div className="lilac-segments">{([{ key: "image", label: "Фото", Icon: ImageIcon }, { key: "video", label: "Видео", Icon: Film }, { key: "music", label: "Музыка", Icon: Music2 }] as const).map(({ key, label, Icon }) => <button key={key} aria-pressed={kind === key} onClick={() => setKind(key)}><Icon size={17} />{label}</button>)}</div>
    {kind === "music" && musicState === "loading" && <p role="status">Загружаем музыкальные модели…</p>}
    {kind === "music" && musicState === "error" && <p role="alert">Не удалось загрузить модели. Вернитесь в каталог и попробуйте ещё раз.</p>}
    {rows.map(model => <button key={model.key} className="lilac-model-card" onClick={() => onSelect(model, kind)}><div><h2>{model.display_name}</h2><p>{model.description || "Настройте модель под свою задачу"}</p></div>
      <div className="lilac-tags">{model.modes?.map(mode => <span key={mode}>{({ text: "По описанию", image: "По фото", video: "По видео", motion: "Движение" } as Record<string, string>)[mode] || mode}</span>)}{model.max_refs ? <span>До {model.max_refs} фото</span> : null}{model.aspect_ratios?.slice(0, 4).map(ratio => <span key={ratio}>{ratio}</span>)}</div>
      <div className="lilac-model-footer"><span>{model.is_per_second ? "От " : ""}{formatCredits(model.credits)} кр.{model.is_per_second ? "/сек" : ""}<small>Точная стоимость перед запуском</small></span><span>Выбрать <ArrowRight size={17} /></span></div>
    </button>)}
    {!rows.length && (kind !== "music" || musicState === "ready") && <div className="lilac-empty"><Search /><p>{query ? "По вашему запросу ничего не найдено. Измените поиск." : "В этой категории сейчас нет доступных моделей."}</p></div>}
  </div>;
}
