import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { FeedItem, MeResponse } from "./api/types";
import { AppShell } from "./components/AppShell";
import { Feed } from "./pages/Feed";
import { History } from "./pages/History";
import { Home } from "./pages/Home";
import { Library } from "./pages/Library";
import { Profile } from "./pages/Profile";
import { PromptDetails } from "./pages/PromptDetails";
import { Referrals } from "./pages/Referrals";
import { initTelegram, openTelegramLink, haptic } from "./telegram";
import { themes, type ThemeId } from "./theme/themes";

export type Page = "home" | "feed" | "library" | "prompt" | "history" | "referrals" | "profile";

const THEME_KEY = "apix_theme";

function getStoredTheme(): ThemeId {
  const value = localStorage.getItem(THEME_KEY);
  return value && value in themes ? (value as ThemeId) : "neonPink";
}

export function App() {
  const [page, setPage] = useState<Page>("home");
  const [theme, setTheme] = useState<ThemeId>(getStoredTheme);
  const [me, setMe] = useState<MeResponse>();
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [promptId, setPromptId] = useState<number | null>(null);
  const [quickOpen, setQuickOpen] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    initTelegram();
    api.getMe().then(setMe);
    api.getFeed("top_day").then((data) => setFeed(data.items));
  }, []);

  const themeDef = useMemo(() => themes[theme], [theme]);

  const changeTheme = (next: ThemeId) => {
    setTheme(next);
    localStorage.setItem(THEME_KEY, next);
    haptic();
  };

  const navigate = (next: Page) => {
    setPage(next);
    setQuickOpen(false);
    haptic();
  };

  const openPrompt = (id: number) => {
    setPromptId(id);
    navigate("prompt");
  };

  const showResult = (message?: string) => {
    setToast(message || "Готово");
    setTimeout(() => setToast(""), 2800);
  };

  const remix = (id: number) => api.remixGeneration(id).then((result) => showResult(result.message));
  const like = (id: number) => api.likeFeed(id).then(() => showResult("Лайк засчитан"));

  return (
    <AppShell page={page} themeId={theme} theme={themeDef} onNavigate={navigate} onQuick={() => setQuickOpen(true)}>
      {page === "home" ? (
        <Home me={me} top={feed[0]} theme={theme} onTheme={changeTheme} onNavigate={navigate} onRemix={remix} onLike={like} />
      ) : null}
      {page === "feed" ? <Feed onRemix={remix} onLike={like} onProfile={() => navigate("profile")} /> : null}
      {page === "library" ? <Library onOpenPrompt={openPrompt} onProfile={() => navigate("profile")} /> : null}
      {page === "prompt" && promptId ? <PromptDetails promptId={promptId} onBack={() => navigate("library")} /> : null}
      {page === "history" ? <History onRemix={remix} onProfile={() => navigate("profile")} /> : null}
      {page === "referrals" ? <Referrals onProfile={() => navigate("profile")} /> : null}
      {page === "profile" ? <Profile me={me} theme={theme} onTheme={changeTheme} onNavigate={navigate} /> : null}

      {quickOpen ? (
        <div className="quickOverlay" onClick={() => setQuickOpen(false)}>
          <div className="quickSheet" onClick={(event) => event.stopPropagation()}>
            <button onClick={() => navigate("library")}>🎨 Изображение</button>
            <button onClick={() => navigate("history")}>🎬 Видео</button>
            <button onClick={() => navigate("history")}>🎵 Песня</button>
            <button onClick={() => openTelegramLink("https://t.me/APIXBot")}>✨ Продолжить в боте</button>
          </div>
        </div>
      ) : null}
      {toast ? <div className="toast">{toast}</div> : null}
    </AppShell>
  );
}
