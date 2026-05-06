import type { Page } from "../App";

type Props = {
  page: Page;
  onNavigate: (page: Page) => void;
  onQuick: () => void;
};

const items: Array<{ page: Page; label: string; icon: string }> = [
  { page: "home", label: "Меню", icon: "⌂" },
  { page: "feed", label: "Лента", icon: "🔥" },
  { page: "library", label: "Библиотека", icon: "▦" },
  { page: "history", label: "История", icon: "▣" },
  { page: "profile", label: "Профиль", icon: "♙" },
];

export function BottomNav({ page, onNavigate, onQuick }: Props) {
  return (
    <nav className="bottomNav">
      {items.slice(0, 2).map((item) => (
        <button key={item.page} className={page === item.page ? "active" : ""} onClick={() => onNavigate(item.page)}>
          <span>{item.icon}</span>{item.label}
        </button>
      ))}
      <button className="quickFab" onClick={onQuick} aria-label="Быстрый старт">+</button>
      {items.slice(2).map((item) => (
        <button key={item.page} className={page === item.page ? "active" : ""} onClick={() => onNavigate(item.page)}>
          <span>{item.icon}</span>{item.label}
        </button>
      ))}
    </nav>
  );
}
