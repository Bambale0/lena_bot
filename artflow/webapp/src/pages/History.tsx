import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HistoryItem } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Header } from "../components/Header";
import { Loading } from "../components/Loading";

type Props = {
  onRemix: (id: number) => void;
  onProfile: () => void;
};

const tabs = [
  ["all", "Все"],
  ["images", "Изображения"],
  ["video", "Видео"],
  ["music", "Музыка"],
];

export function History({ onRemix, onProfile }: Props) {
  const [kind, setKind] = useState("all");
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getHistory(kind).then((data) => {
      setItems(data.items);
      setLoading(false);
    });
  }, [kind]);

  return (
    <div className="page">
      <Header title="История" onProfile={onProfile} />
      <div className="chips">
        {tabs.map(([id, label]) => (
          <button key={id} className={kind === id ? "active" : ""} onClick={() => setKind(id)}>
            {label}
          </button>
        ))}
      </div>
      {loading ? <Loading /> : null}
      {!loading && !items.length ? <EmptyState title="История пока пустая" text="Готовые генерации появятся в этом разделе." /> : null}
      <div className="historyGrid">
        {items.map((item) => (
          <article className="historyCard" key={item.id}>
            <div className="preview historyPreview">
              {item.preview_url ? <img src={item.preview_url} alt="" /> : <div className="gradientPreview" />}
            </div>
            <b>{item.model}</b>
            <p>{item.prompt_preview}</p>
            <div className="cardActions">
              <button onClick={() => onRemix(item.id)}>Remix</button>
              <button>Save as prompt</button>
              {item.type === "image" ? <button>Animate video</button> : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
