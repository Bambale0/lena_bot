import { BalanceCard } from "../components/BalanceCard";
import { Header } from "../components/Header";
import { ThemeSwitcher } from "../components/ThemeSwitcher";
import type { MeResponse } from "../api/types";
import type { Page } from "../App";
import type { ThemeId } from "../theme/themes";

type Props = {
  me?: MeResponse;
  theme: ThemeId;
  onTheme: (theme: ThemeId) => void;
  onNavigate: (page: Page) => void;
};

const menu: Array<{ label: string; page?: Page }> = [
  { label: "Мои промпты", page: "library" },
  { label: "Сохранённые", page: "library" },
  { label: "История генераций", page: "history" },
  { label: "Рефералы", page: "referrals" },
  { label: "Помощь" },
  { label: "Настройки" },
];

export function Profile({ me, theme, onTheme, onNavigate }: Props) {
  return (
    <div className="page">
      <Header title="Профиль" user={me?.user} onProfile={() => undefined} />
      <BalanceCard user={me?.user} session={null} />
      <section className="plainPanel">
        <h2>Дизайн приложения</h2>
        <ThemeSwitcher active={theme} onChange={onTheme} />
      </section>
      <section className="profileMenu">
        {menu.map((item) => (
          <button key={item.label} onClick={() => item.page && onNavigate(item.page)}>
            <span>{item.label}</span>
            <b>›</b>
          </button>
        ))}
      </section>
    </div>
  );
}
