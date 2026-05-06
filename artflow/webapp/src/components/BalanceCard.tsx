import type { ImageSession, WebUser } from "../api/types";
import { openTelegramLink } from "../telegram";

type Props = {
  user?: WebUser;
  session?: ImageSession | null;
};

export function BalanceCard({ user, session }: Props) {
  return (
    <section className="balancePanel">
      <div className="balanceTop">
        <div>
          <span>Баланс</span>
          <strong>{user?.credits ?? 1003} 🍌</strong>
        </div>
        <button className="roundCta" onClick={() => openTelegramLink("https://t.me/APIXBot")}>+</button>
      </div>
      {session ? (
        <button className="sessionCard" onClick={() => openTelegramLink("https://t.me/APIXBot")}>
          <span className="banana">🍌</span>
          <span>
            <b>Продолжить серию</b>
            <small>{session.model} · {session.aspect_ratio || "auto"} · {session.quality} · {session.count} фото</small>
            <small>{session.reference_count ? `${session.reference_count} референс` : "без референса"}</small>
          </span>
          <span className="arrow">→</span>
        </button>
      ) : null}
    </section>
  );
}
