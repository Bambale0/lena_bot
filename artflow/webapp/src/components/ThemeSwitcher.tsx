import { themes, themeIds, type ThemeId } from "../theme/themes";

type Props = {
  active: ThemeId;
  onChange: (theme: ThemeId) => void;
  compact?: boolean;
};

export function ThemeSwitcher({ active, onChange, compact = false }: Props) {
  return (
    <div className={compact ? "themeSwitcher compact" : "themeSwitcher"}>
      {themeIds.map((id) => (
        <button key={id} className={id === active ? "active" : ""} onClick={() => onChange(id)}>
          <span className={`swatch ${id}`} />
          {!compact ? themes[id].name : ""}
        </button>
      ))}
    </div>
  );
}
