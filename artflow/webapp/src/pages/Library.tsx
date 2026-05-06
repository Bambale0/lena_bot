import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { PromptItem } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Header } from "../components/Header";
import { Loading } from "../components/Loading";
import { PromptCard } from "../components/PromptCard";

type Props = {
  onOpenPrompt: (id: number) => void;
  onProfile: () => void;
};

const chips = ["🔥 Топ дня", "🚀 Популярное", "🆕 Новые", "💎 Платные", "⭐ Сохранённые", "👤 Characters", "🎬 Cinematic", "🎵 Music"];

export function Library({ onOpenPrompt, onProfile }: Props) {
  const [items, setItems] = useState<PromptItem[]>([]);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(chips[0]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getPrompts(active.includes("Новые") ? "?sort=new" : "?sort=trending").then((data) => {
      setItems(data.items);
      setLoading(false);
    });
  }, [active]);

  const filtered = useMemo(
    () => items.filter((item) => `${item.title} ${item.description}`.toLowerCase().includes(query.toLowerCase())),
    [items, query],
  );

  return (
    <div className="page">
      <Header title="Библиотека идей" onProfile={onProfile} />
      <input className="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по промптам" />
      <div className="chips scroll">
        {chips.map((chip) => (
          <button key={chip} className={active === chip ? "active" : ""} onClick={() => setActive(chip)}>
            {chip}
          </button>
        ))}
      </div>
      {loading ? <Loading /> : null}
      {!loading && !filtered.length ? <EmptyState title="Ничего не найдено" text="Попробуй другой запрос или подборку." /> : null}
      <div className="promptGrid">
        {filtered.map((prompt) => (
          <PromptCard key={prompt.id} prompt={prompt} onOpen={onOpenPrompt} />
        ))}
      </div>
    </div>
  );
}
