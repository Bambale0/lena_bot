import { readFileSync } from "node:fs";

const FEED_START = "// ── Feed screen ───────────────────────────────────────────────────────────────";
const FEED_END = "// ── Admin-curated trends ─────────────────────────────────────────────────────";
const FEED_BLOCK = `${readFileSync(new URL("./feed-pinterest.block.jsx", import.meta.url), "utf8").trim()}\n\n`;

function replaceRequired(code, from, to, label) {
  if (!code.includes(from)) {
    throw new Error(`Feed persistence transform could not find: ${label}`);
  }
  return code.replace(from, to);
}

export function feedPinterestMiniApp() {
  return {
    name: "apix-feed-pinterest-miniapp",
    enforce: "pre",
    transform(source, id) {
      if (!id.endsWith("/src/main.jsx")) return null;

      let code = source;
      const start = code.indexOf(FEED_START);
      const end = code.indexOf(FEED_END);
      if (start < 0 || end < 0 || end <= start) {
        throw new Error("Pinterest feed transform could not locate feed component boundaries");
      }

      code = `${code.slice(0, start)}${FEED_BLOCK}${code.slice(end)}`;
      if (!code.includes('import "./feed-pinterest.css";')) {
        code = code.replace(
          'import "./style.css";',
          'import "./style.css";\nimport "./feed-pinterest.css";',
        );
      }

      // A preview failure is a media-delivery problem, not a reason to remove
      // the publication. Keep the card and its actions mounted permanently.
      code = replaceRequired(
        code,
        "  const visibleUrls = previewUrls.filter((url) => !failedUrls.has(url)).slice(0, 4);",
        "  const visibleUrls = previewUrls.slice(0, 4);",
        "stable visible URLs",
      );
      code = replaceRequired(
        code,
        "  if (!previewUrls.length || (!visibleUrls.length && failedUrls.size)) return null;",
        "  if (!previewUrls.length) return null;",
        "card removal guard",
      );
      code = replaceRequired(
        code,
        "            onOpen={onOpen}\n            onError={() => hideBrokenMedia(url)}",
        "            onOpen={failedUrls.has(url) ? undefined : onOpen}\n            onError={(event) => { event.currentTarget.style.opacity = \"0\"; hideBrokenMedia(url); }}",
        "broken preview handler",
      );
      code = replaceRequired(
        code,
        "        ))}\n\n        <div className=\"feedCompactTop\">",
        `        ))}\n\n        {visibleUrls.length > 0 && visibleUrls.every((url) => failedUrls.has(url)) && (\n          <div\n            className="feedMediaFallback"\n            style={{\n              position: "absolute",\n              inset: 0,\n              display: "grid",\n              placeItems: "center",\n              padding: "28px 14px",\n              textAlign: "center",\n              color: "rgba(255,255,255,.72)",\n              background: "linear-gradient(145deg, #181b25, #0f1118)",\n              fontSize: 12,\n              lineHeight: 1.35,\n            }}\n          >\n            <span>Превью временно недоступно.<br />Публикация сохранена.</span>\n          </div>\n        )}\n\n        <div className="feedCompactTop">`,
        "preview fallback",
      );
      code = replaceRequired(
        code,
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-feed-first-relevance-v1";',
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260801-feed-card-persistence-v6";',
        "Mini App build id",
      );

      return { code, map: null };
    },
  };
}
