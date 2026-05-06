import type { WebUser } from "../api/types";
import { getUser } from "../telegram";

type Props = {
  user?: WebUser;
  title?: string;
  onProfile: () => void;
};

export function Header({ user, title = "APIX", onProfile }: Props) {
  const tgUser = getUser();
  const display = user?.username || tgUser.username || user?.full_name || tgUser.first_name || "creator";
  const avatarText = (tgUser.first_name || user?.full_name || "A").slice(0, 1).toUpperCase();

  return (
    <header className="header">
      <div>
        <div className="brand">💎 {title}</div>
        <div className="muted">@{display}</div>
      </div>
      <button className="avatarButton" onClick={onProfile} aria-label="Профиль">
        {tgUser.photo_url ? <img src={tgUser.photo_url} alt="" /> : avatarText}
      </button>
    </header>
  );
}
