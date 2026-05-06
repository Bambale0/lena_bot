import type { PromptItem } from "../api/types";

type Props = {
  prompt: PromptItem;
  onOpen: (id: number) => void;
};

export function PromptCard({ prompt, onOpen }: Props) {
  return (
    <button className="promptCard" onClick={() => onOpen(prompt.id)}>
      <div className="preview promptPreview">
        {prompt.preview_url ? <img src={prompt.preview_url} alt="" /> : <div className="gradientPreview" />}
        <span className="badge">{prompt.price_bananas} 🍌</span>
      </div>
      <b>{prompt.title}</b>
      <span>{prompt.model}</span>
      <small>★ {prompt.uses_count}</small>
    </button>
  );
}
