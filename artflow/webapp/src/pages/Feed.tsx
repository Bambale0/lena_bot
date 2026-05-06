import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FeedItem } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { FeedCard } from "../components/FeedCard";
import { Header } from "../components/Header";
import { Loading } from "../components/Loading";

type Props = {
  onRemix: (id: number) => void;
  onLike: (id: number) => void;
  onProfile: () => void;
};

export function Feed({ onRemix, onLike, onProfile }: Props) {
  const [sort, setSort] = useState("trending");
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getFeed(sort).then((data) => {
      setItems(data.items);
      setLoading(false);
    });
  }, [sort]);

  return (
    <div className="page">
      <Header title="Лента ремиксов" onProfile={onProfile} />
      <div className="chips">
        {[
          ["trending", "Популярные"],
          ["top_day", "Топ дня"],
          ["new", "Новые"],
        ].map(([id, label]) => (
          <button key={id} className={sort === id ? "active" : ""} onClick={() => setSort(id)}>
            {label}
          </button>
        ))}
      </div>
      {loading ? <Loading /> : null}
      {!loading && !items.length ? <EmptyState title="Лента пока пустая" text="Публичные работы появятся здесь после генераций." /> : null}
      <div className="feedList">
        {items.map((item) => (
          <FeedCard key={item.id} item={item} onRemix={onRemix} onLike={onLike} />
        ))}
      </div>
    </div>
  );
}
