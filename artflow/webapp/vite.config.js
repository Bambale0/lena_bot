import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function replaceRequired(code, from, to, label) {
  if (!code.includes(from)) {
    throw new Error(`Feed-first transform could not find: ${label}`);
  }
  return code.replace(from, to);
}

function feedFirstMiniApp() {
  return {
    name: "apix-feed-first-miniapp",
    enforce: "pre",
    transform(source, id) {
      if (!id.endsWith("/src/main.jsx")) return null;

      let code = source;
      code = replaceRequired(
        code,
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-trend-category-home-v4";',
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-feed-first-relevance-v1";',
        "Mini App build id",
      );
      code = replaceRequired(
        code,
        `  const onBack = () => {\n    if (screen === "home") tg()?.close?.();\n    else setScreen("home");\n  };`,
        `  const onBack = () => {\n    if (screen === "feed") tg()?.close?.();\n    else setScreen("feed");\n  };`,
        "header root navigation",
      );
      code = replaceRequired(
        code,
        '{screen === "home" ? "✕ Закрыть" : "‹ Назад"}',
        '{screen === "feed" ? "✕ Закрыть" : "‹ Назад"}',
        "header close label",
      );
      code = replaceRequired(
        code,
        `  const tabs = [\n    ["home", "⌂", "Главная", ""],\n    ["feed", "▤", "Лента", ""],`,
        `  const tabs = [\n    ["feed", "▤", "Лента", ""],\n    ["home", "🔥", "Тренды", ""],`,
        "bottom navigation order",
      );
      code = replaceRequired(
        code,
        '<p>{filtered.length} {filtered.length === 1 ? "работа" : "работ"}</p>',
        '<p>{filtered.length} {filtered.length === 1 ? "работа" : "работ"} · свежесть, популярность, повторы</p>',
        "feed relevance caption",
      );
      code = replaceRequired(
        code,
        '  const [screen, setScreen] = useState("home");',
        '  const [screen, setScreen] = useState("feed");',
        "initial screen",
      );
      code = replaceRequired(
        code,
        '  const feed = useApi(() => api("/feed?source=recent&limit=10000").then(items), fallbackFeed);',
        '  const feed = useApi(() => api("/feed?source=recent&limit=200").then(items), fallbackFeed);',
        "feed request limit",
      );
      code = replaceRequired(
        code,
        '        {screens[screen] || screens.home}',
        '        {screens[screen] || screens.feed}',
        "fallback screen",
      );

      return { code, map: null };
    },
  };
}

export default defineConfig({
  plugins: [feedFirstMiniApp(), react()],
  base: "/app/",
});
