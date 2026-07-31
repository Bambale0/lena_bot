import { readFileSync } from "node:fs";

const FEED_START = "// ── Feed screen ───────────────────────────────────────────────────────────────";
const FEED_END = "// ── Admin-curated trends ─────────────────────────────────────────────────────";
const FEED_BLOCK = `${readFileSync(new URL("./feed-pinterest.block.jsx", import.meta.url), "utf8").trim()}\n\n`;

function replaceRequired(code, from, to, label) {
  if (!code.includes(from)) {
    throw new Error(`Feed stability transform could not find: ${label}`);
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

      // A failed image request must never make a publication disappear. The
      // backend now returns a valid retryable WebP placeholder, and this guard
      // keeps the card mounted even if a proxy/browser still emits onError.
      code = replaceRequired(
        code,
        "  const visibleUrls = previewUrls.filter((url) => !failedUrls.has(url)).slice(0, 4);",
        "  const visibleUrls = previewUrls.slice(0, 4);",
        "stable preview list",
      );
      code = replaceRequired(
        code,
        "  if (!previewUrls.length || (!visibleUrls.length && failedUrls.size)) return null;",
        "  if (!previewUrls.length) return null;",
        "card collapse guard",
      );
      code = replaceRequired(
        code,
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-feed-first-relevance-v1";',
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260801-feed-stability-v5";',
        "Mini App build id",
      );

      return { code, map: null };
    },
  };
}
