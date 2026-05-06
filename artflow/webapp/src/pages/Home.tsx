import { BalanceCard } from "../components/BalanceCard";
import { FeedCard } from "../components/FeedCard";
import { Header } from "../components/Header";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import type { FeedItem, MeResponse } from "../api/types";
import type { Page } from "../App";
import type { ThemeId } from "../theme/themes";

type Props = {
  me?: MeResponse;
  top?: FeedItem;
  theme: ThemeId;
  onTheme: (theme: ThemeId) => void;
  onNavigate: (page: Page) => void;
  onRemix: (id: number) => void;
  onLike: (id: number) => void;
};

export function Home({ me, top, theme, onTheme, onNavigate, onRemix, onLike }: Props) {
  return (
    <div className="page">
      <Header user={me?.user} onProfile={() => onNavigate("profile")} />
      <BalanceCard user={me?.user} session={me?.active_image_session} />
      <ThemeSwitcher active={theme} onChange={onTheme} compact />

      <section>
        <h2>Быстрый старт</h2>
        <div className="quickGrid">
          <button onClick={() => onNavigate("library")}>🎨<span>Изображение</span></button>
          <button onClick={() => onNavigate("history")}>🎬<span>Видео</span></button>
          <button onClick={() => onNavigate("history")}>🎵<span>Песня</span></button>
          <button onClick={() => onNavigate("library")}>✨<span>Улучшить фото</span></button>
        </div>
      </section>

      <section>
        <div className="sectionTitle">
          <h2>Топ дня</h2>
          <button onClick={() => onNavigate("feed")}>Смотреть все</button>
        </div>
        {top ? <FeedCard item={top} onRemix={onRemix} onLike={onLike} /> : null}
      </section>
    </div>
  );
}
