import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ActionResult, PromptItem } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { Loading } from "../components/Loading";
import { shareUrl } from "../telegram";

type Props = {
  promptId: number;
  onBack: () => void;
};

export function PromptDetails({ promptId, onBack }: Props) {
  const [prompt, setPrompt] = useState<PromptItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState<ActionResult | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getPrompt(promptId).then((data) => {
      setPrompt(data);
      setLoading(false);
    });
  }, [promptId]);

  if (loading) return <div className="page"><Loading /></div>;
  if (!prompt) return <div className="page"><EmptyState title="Промпт не найден" action="Назад" onAction={onBack} /></div>;
  if (result?.ok) {
    return (
      <div className="page successPage">
        <button className="backButton" onClick={onBack}>← Библиотека</button>
        <div className="successMark">✓</div>
        <h1>{result.message || "Пресет применён. Вернись в бот, отправь фото или уточнение."}</h1>
      </div>
    );
  }

  return (
    <div className="page">
      <button className="backButton" onClick={onBack}>← Библиотека идей</button>
      <article className="detailCard">
        <div className="preview detailPreview">
          {prompt.preview_url ? <img src={prompt.preview_url} alt="" /> : <div className="gradientPreview" />}
          <span className="badge">{prompt.reference_count || 0}/5</span>
        </div>
        <h1>{prompt.title}</h1>
        <p>{prompt.description}</p>
        <div className="detailList">
          <span>Модель: <b>{prompt.model}</b></span>
          <span>Формат: <b>{prompt.aspect_ratio || "9:16"}</b></span>
          <span>Качество: <b>{prompt.quality || "2K"}</b></span>
          <span>Стоимость: <b>{prompt.price_bananas} 🍌</b></span>
          <span>Использований: <b>{prompt.uses_count}</b></span>
        </div>
        <div className="stackActions">
          <button className="primary" onClick={() => api.usePrompt(prompt.id).then(setResult)}>🔥 Использовать этот промпт</button>
          <button onClick={() => api.savePrompt(prompt.id).then(setResult)}>🔖 Сохранить</button>
          <button onClick={() => shareUrl(window.location.href)}>📤 Поделиться</button>
        </div>
      </article>
    </div>
  );
}
