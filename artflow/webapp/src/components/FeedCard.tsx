import type { FeedItem } from "../api/types";

type Props = {
  item: FeedItem;
  onRemix: (id: number) => void;
  onLike: (id: number) => void;
  onSave?: (id: number) => void;
  onShare?: (id: number) => void;
};

export function FeedCard({ item, onRemix, onLike, onSave, onShare }: Props) {
  return (
    <article className="feedCard">
      <div className="preview mediaTall">
        {item.preview_url ? <img src={item.preview_url} alt="" /> : <div className="gradientPreview" />}
        <div className="mediaMeta">
          <b>{item.author}</b>
          <span>{item.model}</span>
        </div>
      </div>
      <p>{item.prompt_preview}</p>
      <div className="metrics">
        <span>♥ {item.likes}</span>
        <span>↻ {item.remixes}</span>
        <span>↗ {item.shares}</span>
      </div>
      <div className="cardActions">
        <button onClick={() => onRemix(item.id)}>✨ Ремикс</button>
        <button onClick={() => onLike(item.id)}>❤️</button>
        <button onClick={() => onSave?.(item.id)}>🔖</button>
        <button onClick={() => onShare?.(item.id)}>📤</button>
      </div>
    </article>
  );
}
