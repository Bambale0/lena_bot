import { readFileSync } from "node:fs";

const FEED_START = "// ── Feed screen ───────────────────────────────────────────────────────────────";
const FEED_END = "// ── Admin-curated trends ─────────────────────────────────────────────────────";
const FEED_BLOCK = `${readFileSync(new URL("./feed-pinterest.block.jsx", import.meta.url), "utf8").trim()}\n\n`;

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
      code = code.replace(
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-feed-first-relevance-v1";',
        'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-feed-pinterest-filters-v2";',
      );

      return { code, map: null };
    },
  };
}
