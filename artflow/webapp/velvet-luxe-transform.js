import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const BLOCK_PATH = path.join(ROOT, "velvet-luxe.block.jsx");

function readSection(source, name) {
  const startMarker = `// @section ${name}`;
  const endMarker = "// @endsection";
  const start = source.indexOf(startMarker);
  if (start < 0) throw new Error(`Missing Velvet Luxe section: ${name}`);
  const bodyStart = source.indexOf("\n", start) + 1;
  const end = source.indexOf(endMarker, bodyStart);
  if (end < 0) throw new Error(`Missing end marker for Velvet Luxe section: ${name}`);
  return source.slice(bodyStart, end).trim();
}

function findFunctionEnd(source, start) {
  const open = source.indexOf("{", start);
  if (open < 0) throw new Error("Function opening brace not found");

  let depth = 0;
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = open; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1];

    if (lineComment) {
      if (char === "\n") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (char === "\\") {
        escaped = true;
        continue;
      }
      if (char === quote) quote = "";
      continue;
    }

    if (char === "/" && next === "/") {
      lineComment = true;
      index += 1;
      continue;
    }
    if (char === "/" && next === "*") {
      blockComment = true;
      index += 1;
      continue;
    }
    if (char === '"' || char === "'" || char === "`") {
      quote = char;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return index + 1;
    }
  }

  throw new Error("Function closing brace not found");
}

function replaceFunction(source, name, replacement) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`Velvet Luxe target not found: ${name}`);
  const end = findFunctionEnd(source, start);
  return `${source.slice(0, start)}${replacement}${source.slice(end)}`;
}

function replaceFeedConstants(source, replacement) {
  const start = source.indexOf("const FEED_FILTERS = [");
  const endMarker = "\n\nfunction Icon(";
  const end = source.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error("Velvet Luxe feed constants target not found");
  return `${source.slice(0, start)}${replacement}${source.slice(end)}`;
}

export default function velvetLuxeMiniApp() {
  const blocks = fs.readFileSync(BLOCK_PATH, "utf8");
  const sections = {
    constants: readSection(blocks, "FEED_CONSTANTS"),
    header: readSection(blocks, "APP_HEADER"),
    nav: readSection(blocks, "BOTTOM_NAVIGATION"),
    media: readSection(blocks, "FEED_MEDIA"),
    card: readSection(blocks, "FEED_CARD"),
    viewer: readSection(blocks, "FEED_VIEWER"),
    feed: readSection(blocks, "FEED_SCREEN"),
  };

  return {
    name: "apix-velvet-luxe-v3",
    enforce: "pre",
    transform(code, id) {
      const normalized = id.split("?")[0].replaceAll("\\", "/");
      if (!normalized.endsWith("/src/v2/VelvetApp.jsx")) return null;

      let next = replaceFeedConstants(code, sections.constants);
      next = replaceFunction(next, "AppHeader", sections.header);
      next = replaceFunction(next, "BottomNavigation", sections.nav);
      next = replaceFunction(next, "FeedMedia", sections.media);
      next = replaceFunction(next, "FeedCard", sections.card);
      next = replaceFunction(next, "FeedViewer", sections.viewer);
      next = replaceFunction(next, "FeedScreen", sections.feed);

      const oldCall = '<AppHeader screen={screen} user={user} onSearch={() => setScreen("feed")} onTopup={() => setTopupOpen(true)}/>';
      const newCall = '<AppHeader screen={screen} user={user} onSearch={() => setScreen("feed")} onTopup={() => setTopupOpen(true)} onCreate={() => setScreen("create")}/>';
      if (!next.includes(oldCall)) throw new Error("Velvet Luxe AppHeader call target not found");
      next = next.replace(oldCall, newCall);

      const oldSearch = 'onClick={onSearch} aria-label="Поиск"';
      const newSearch = 'onClick={() => { onSearch?.(); window.dispatchEvent(new Event("apix:feed-search")); }} aria-label="Поиск"';
      if (!next.includes(oldSearch)) throw new Error("Velvet Luxe search action target not found");
      next = next.replace(oldSearch, newSearch);

      const stateAnchor = '  const [items, setItems] = useState(feed);\n\n  useEffect(() => setItems(feed), [feed]);';
      const stateReplacement = '  const [items, setItems] = useState(feed);\n\n  useEffect(() => setItems(feed), [feed]);\n  useEffect(() => {\n    const openSearch = () => setSearchOpen(true);\n    window.addEventListener("apix:feed-search", openSearch);\n    return () => window.removeEventListener("apix:feed-search", openSearch);\n  }, []);';
      if (!next.includes(stateAnchor)) throw new Error("Velvet Luxe feed search state target not found");
      next = next.replace(stateAnchor, stateReplacement);

      return { code: next, map: null };
    },
  };
}
