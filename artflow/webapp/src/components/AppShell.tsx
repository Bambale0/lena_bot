import type { CSSProperties, ReactNode } from "react";
import type { Page } from "../App";
import type { Theme, ThemeId } from "../theme/themes";
import { BottomNav } from "./BottomNav";

type Props = {
  children: ReactNode;
  page: Page;
  themeId: ThemeId;
  theme: Theme;
  onNavigate: (page: Page) => void;
  onQuick: () => void;
};

export function AppShell({ children, page, themeId, theme, onNavigate, onQuick }: Props) {
  const style = {
    "--bg": theme.background,
    "--card": theme.card,
    "--card-alt": theme.cardAlt,
    "--text": theme.text,
    "--muted": theme.muted,
    "--accent": theme.accent,
    "--accent2": theme.accent2,
    "--border": theme.border,
    "--button-gradient": theme.buttonGradient,
    "--glow": theme.glow,
    "--nav": theme.nav,
  } as CSSProperties;

  return (
    <div className={`appRoot theme-${themeId}`} style={style}>
      <main className="appFrame">{children}</main>
      <BottomNav page={page} onNavigate={onNavigate} onQuick={onQuick} />
    </div>
  );
}
