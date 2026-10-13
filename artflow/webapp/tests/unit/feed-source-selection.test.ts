import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import * as utils from "../../src/lib/utils.ts";

const require = createRequire(import.meta.url);
function loadProduction(path: string, dependencies: Record<string, unknown>, expose = "") {
  const compiled = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const module = { exports: {} as Record<string, any> };
  new Function("exports", "require", compiled + expose)(module.exports, (name: string) => {
    if (name in dependencies) return dependencies[name];
    if (name === "lucide-react") return new Proxy({}, { get: (_, name) => String(name) });
    if (name === "react" || name === "react/jsx-runtime" || name === "react-dom") return require(name);
    throw new Error(`Unexpected component dependency: ${name}`);
  });
  return module.exports;
}

// Execute the real stateless viewer and React event handlers; isolate unrelated
// portals and visual wrappers only, with no source-text assertions.
const { MediaViewer } = loadProduction("../../src/features/feed-screen.tsx", {
  "sonner": {}, "@/components/ui/badge": { Badge: "badge" },
  "@/components/ui/button": { Button: "button" }, "@/components/ui/card": { Card: "card" },
  "@/features/trend-runner": {}, "@/lib/telegram": {}, "@/lib/utils": utils,
}, "\nexports.MediaViewer = MediaViewer;");

type Element = { type?: unknown; props?: Record<string, any> };
function descendants(node: any): Element[] {
  if (!node || typeof node !== "object") return [];
  if (Array.isArray(node)) return node.flatMap(descendants);
  return [node, ...descendants(node.props?.children)];
}
function textOf(node: any): string {
  if (typeof node === "string") return node;
  if (Array.isArray(node)) return node.map(textOf).join("");
  return node?.props ? textOf(node.props.children) : "";
}

test("gallery next then repeat hands off the displayed result, not the item default", () => {
  const urls = ["https://apix.example/api/v1/feed/201/preview.webp?index=0&output_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "https://apix.example/api/v1/feed/201/preview.webp?index=1&output_id=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"];
  const item = { id: 201, gen_type: "image", preview_url: urls[0], preview_urls: urls };
  let viewer = { item, urls, index: 0 };
  let handedOff: unknown[] = [];
  const render = () => MediaViewer({ viewer, onClose() {}, remixingId: null,
    onChangeIndex(index: number) { viewer = { ...viewer, index }; },
    onRemix(...args: unknown[]) { handedOff = args; },
  });
  descendants(render()).find(node => node.props?.["aria-label"] === "Следующее фото")!.props!.onClick();
  const selected = render();
  assert.equal(descendants(selected).find(node => node.type === "img")?.props?.src, urls[1]);
  descendants(selected).find(node => node.type === "button" && textOf(node).includes("Повторить эту работу"))!.props!.onClick();
  assert.deepEqual(handedOff, [item, urls[1]]);
});

test("deep-link API uses the same authenticated feed representation as normal cards", async (t) => {
  const { MiniAppApi } = loadProduction("../../src/lib/api.ts", {
    "@/lib/utils": utils, "@/lib/telegram": {}, "@/features/feed-remix-runner": {},
  });
  t.mock.method(globalThis, "fetch", async (url, init) => {
    assert.equal(url, "/api/v1/feed/201");
    assert.equal(new Headers(init?.headers).get("X-Telegram-Init-Data"), "fixture");
    return new Response(JSON.stringify({ id: 201, preview_url: "/api/v1/feed/201/preview.webp?index=0&output_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }));
  });
  const item = await new MiniAppApi("fixture").getPublicFeedItem(201);
  assert.equal(item.preview_url, "/api/v1/feed/201/preview.webp?index=0&output_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
});

test("API forwards the gallery source to the shared runner unchanged", async () => {
  let handedOff: unknown[] = [];
  const { MiniAppApi } = loadProduction("../../src/lib/api.ts", {
    "@/lib/utils": utils, "@/lib/telegram": {},
    "@/features/feed-remix-runner": { openFeedRemixRunner(...args: unknown[]) { handedOff = args; } },
  });
  const item = { id: 201 };
  const selected = "https://apix.example/api/v1/feed/201/preview.webp?index=1&output_id=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  new MiniAppApi("fixture").remixFeedItem(item, selected);
  assert.deepEqual(handedOff, [item, selected]);
});

test("runner open event restores selected source and explicit selection wins before quote", async (t) => {
  const payment = await import("../../src/features/feed-repeat-payment.ts");
  const references = await import("../../src/features/feed-repeat-references.ts");
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); } };
  const host = Object.assign(new EventTarget(), { location: { origin: "https://apixbotai.com" },
    sessionStorage: storage, setTimeout, clearTimeout });
  const previousWindow = globalThis.window;
  let cleanups: (() => void)[] = [];
  Object.defineProperty(globalThis, "window", { configurable: true, writable: true, value: host });
  t.after(() => { for (const cleanup of cleanups) cleanup(); if (previousWindow) globalThis.window = previousWindow; else delete (globalThis as any).window; });
  t.mock.method(globalThis, "fetch", async (url) => {
    if (url === "/api/v1/me") return Response.json({ id: 1 });
    if (url === "/api/v1/models/image") return Response.json([{ key: "nano-banana-2", modes: ["image"], max_refs: 4 }]);
    if (url === "/api/v1/models/video") return Response.json([]);
    throw new Error(`Unexpected API call: ${url}`);
  });
  // A small stateful hook host exercises the production open-event subscription
  // and request-body memo without a DOM or an additional test-only dependency.
  // Hook positions are tracked generically, never hardcoded to component fields.
  const states: any[] = [], refs: any[] = [], effects: (() => unknown)[] = [];
  let stateIndex = 0, refIndex = 0;
  let memos: any[] = [];
  const react = {
    useState(initial: unknown) {
      const index = stateIndex++;
      if (!(index in states)) states[index] = initial;
      return [states[index], (value: any) => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
    },
    useRef(initial: unknown) { const index = refIndex++; return refs[index] ||= { current: initial }; },
    useMemo(fn: () => unknown) { const value = fn(); memos.push(value); return value; },
    useCallback(fn: unknown) { return fn; },
    useEffect(fn: () => unknown) { effects.push(fn); },
  };
  const { Portal } = loadProduction("../../src/features/feed-remix-runner.tsx", {
    react, "react-dom/client": {}, "sonner": { toast: {} },
    "@/components/ui/button": { Button: "button" }, "@/components/ui/sheet": { Sheet: "sheet" },
    "@/lib/telegram": {}, "@/lib/utils": utils,
    "@/features/feed-repeat-references": references, "@/features/feed-repeat-payment": payment,
  }, "\nexports.Portal = FeedRemixRunnerPortal;");
  let rendered: any;
  const render = () => { stateIndex = refIndex = 0; memos = []; effects.length = 0; rendered = Portal();
    return memos.find(value => value && typeof value === "object" && "source_image_url" in value); };
  render();
  cleanups = effects.map(effect => effect()).filter((value): value is () => void => typeof value === "function");
  const zero = "https://apixbotai.com/api/v1/feed/201/preview.webp?index=0&output_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
  const one = "https://apixbotai.com/api/v1/feed/201/preview.webp?index=1&output_id=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
  const item = { id: 201, model: "nano-banana-2", gen_type: "image", preview_url: zero, preview_urls: [zero, one] };
  const draft = { savedAt: Date.now(), sourceMediaUrl: one, references: [], changeRequest: "", modelKey: "nano-banana-2",
    mode: "image", aspectRatio: "1:1", quality: "2K", count: 1, duration: 5, resolution: "720p", grokMode: "normal", payment: null };
  const open = async (sourceMediaUrl?: string) => {
    host.dispatchEvent(new CustomEvent("apix:open-feed-remix-runner", { detail: { item, sourceMediaUrl } }));
    await new Promise(resolve => setImmediate(resolve));
    return render();
  };
  payment.saveRepeatDraft(storage, 1, 201, { ...draft, sourceMediaUrl: zero });
  let body = await open(one);
  assert.equal(body.source_image_url, one);
  assert.equal(body.image_url, one);
  payment.saveRepeatDraft(storage, 1, 201, draft);
  assert.equal((await open()).source_image_url, one);
  assert.equal((await open(zero)).source_image_url, zero);
  payment.saveRepeatDraft(storage, 1, 201, { ...draft, references: ["https://example.test/user.jpg"] });
  body = await open();
  assert.equal(body.source_image_url, one);
  assert.equal(body.image_url, "https://example.test/user.jpg");
  assert.deepEqual(body.reference_urls, ["https://example.test/user.jpg"]);
  // A genuinely fresh deep link captures the bound default before a checkout.
  storage.removeItem(payment.repeatDraftKey(1, 201));
  assert.equal((await open()).source_image_url, zero);
  cleanups.push(...effects.map(effect => effect()).filter((value): value is () => void => typeof value === "function"));
  assert.equal(payment.readRepeatDraft(storage, 1, 201)?.sourceMediaUrl, zero);
  // Restore that exact default, even if a new feed snapshot has another first image.
  item.preview_url = one;
  item.preview_urls = [one];
  assert.equal((await open()).source_image_url, zero);
  const pending = { startedAt: Date.now(), provider: "tbank" as const, planKey: "starter", transactionId: 701, checkoutUrl: "https://pay.example.test/original" };
  const { restoreLegacySceneOnNextDocument } = loadProduction("../e2e/feed-remix-runner.spec.ts", {
    "@playwright/test": { test() {}, expect: {} },
  }, "\nexports.restoreLegacySceneOnNextDocument = restoreLegacySceneOnNextDocument;");
  for (const missing of [false, true]) {
    let initializeDocument = () => {};
    const page = {
      evaluate: async (fn: (arg: boolean) => void, arg: boolean) => fn(arg),
      addInitScript: async (fn: (arg: boolean) => void, arg: boolean) => { initializeDocument = () => fn(arg); },
    };
    const liveDraft = { ...draft, references: ["https://example.test/user.jpg"], payment: pending };
    payment.saveRepeatDraft(storage, 1, 201, liveDraft);
    await restoreLegacySceneOnNextDocument(page, missing);
    // A pending response/autosave from the old document can still save its valid binding.
    payment.saveRepeatDraft(storage, 1, 201, liveDraft);
    initializeDocument();
    body = await open();
    const legacySource = missing ? "" : one.split("&output_id=")[0];
    assert.equal(body.source_image_url, legacySource || null, "The new document must actually restore the intended legacy fixture");
    if (missing) assert.match(textOf(rendered.props.footer), /Выберите фото заново в ленте/);
    assert.deepEqual(body.reference_urls, ["https://example.test/user.jpg"]);
    assert.deepEqual(payment.readRepeatDraft(storage, 1, 201)?.payment, pending);
    assert.equal(payment.readRepeatDraft(storage, 1, 201)?.sourceMediaUrl, legacySource);
    assert.equal((await open(one)).source_image_url, one, "A fresh gallery click repairs the legacy selection");
  }
});

test("all shared-link journey fixtures satisfy the production v1 hydration client", async (t) => {
  const playwrightTest = Object.assign(() => undefined, { describe: (_name: string, run: () => void) => run() });
  const { mockMiniApp } = loadProduction("../user-journeys/user-journeys-300.spec.ts", {
    "@playwright/test": { test: playwrightTest, expect: {} },
  }, "\nexports.mockMiniApp = mockMiniApp;");
  const routes = new Map<string, (route: any) => Promise<unknown>>();
  const publicFeed = Object.fromEntries(Array.from({ length: 25 }, (_, index) => {
    const id = 5001 + index;
    return [id, { id, author: `Target ${index + 1}`, result_urls: [`https://example.test/canonical-${index + 1}.png`] }];
  }));
  await mockMiniApp({ addInitScript: async () => {}, route: async (pattern: string, handler: any) => { routes.set(pattern, handler); } }, { publicFeed });
  const { MiniAppApi } = loadProduction("../../src/lib/api.ts", {
    "@/lib/utils": utils, "@/lib/telegram": {}, "@/features/feed-remix-runner": {},
  });
  t.mock.method(globalThis, "fetch", async (url, init) => {
    let response: Response | undefined;
    const path = String(url);
    assert.ok(path.startsWith("/api/v1/feed/"));
    await routes.get("**/api/v1/**")!({
      request: () => ({ url: () => `https://apix.example${path}`, method: () => init?.method || "GET" }),
      fulfill: async (result: any) => { response = Response.json(result.json, { status: result.status || 200 }); },
    });
    assert.ok(response);
    return response;
  });
  const client = new MiniAppApi("fixture");
  for (let seed = 1; seed <= 25; seed++) {
    const item = await client.getPublicFeedItem(5000 + seed);
    assert.equal(item.author, `Target ${seed}`);
    assert.deepEqual(item.result_urls, [`https://example.test/canonical-${seed}.png`]);
  }
  await assert.rejects(client.getPublicFeedItem(99999), (error: any) => error.status === 404);
});

test("card decoration passes pointer input to the gallery while actions stay independent", (t) => {
  const body = { nodeType: 1 };
  const previousWindow = globalThis.window, previousDocument = globalThis.document;
  Object.defineProperty(globalThis, "window", { configurable: true, writable: true, value: { location: { origin: "https://apix.example" } } });
  Object.defineProperty(globalThis, "document", { configurable: true, writable: true, value: { body } });
  t.after(() => {
    if (previousWindow) globalThis.window = previousWindow; else delete (globalThis as any).window;
    if (previousDocument) globalThis.document = previousDocument; else delete (globalThis as any).document;
  });
  const states: any[] = [];
  let stateIndex = 0;
  const react = {
    useState(initial: unknown) { const index = stateIndex++; if (!(index in states)) states[index] = initial;
      return [states[index], (value: any) => { states[index] = typeof value === "function" ? value(states[index]) : value; }]; },
    useMemo: (fn: () => unknown) => fn(), useCallback: (fn: unknown) => fn,
    useEffect() {}, useRef: (value: unknown) => ({ current: value }),
  };
  const { FeedScreen } = loadProduction("../../src/features/feed-screen.tsx", {
    react, "react-dom": require("react-dom"), "sonner": {}, "@/components/ui/badge": { Badge: "badge" },
    "@/components/ui/button": { Button: "button" }, "@/components/ui/card": { Card: "card" },
    "@/features/trend-runner": {}, "@/lib/telegram": {}, "@/lib/utils": utils,
  });
  const item = { id: 201, gen_type: "image", model: "nano-banana-2", author: "Artist QA", preview_url: "https://example.test/source.png" };
  let repeated: unknown[] = [], liked: unknown;
  const render = () => { stateIndex = 0; return FeedScreen({
    items: [item],
    source: "recent", loading: false, onSourceChange() {}, onRefresh() {},
    onLike(value: unknown) { liked = value; }, onRemix(...values: unknown[]) { repeated = values; },
  }); };
  const portal = (tree: any) => descendants(tree).find(node => (node as any).containerInfo === body) as any;
  const initial = render();
  assert.equal(portal(initial), undefined);
  const footer = descendants(initial).find(node => node.type === "div"
    && node.props?.className?.includes("bottom-0") && textOf(node).includes("Artist QA"))!;
  assert.ok(footer.props!.className.split(" ").includes("pointer-events-none"), "Decorative metadata must not intercept cover taps");
  const repeat = descendants(footer).find(node => node.type === "button")!;
  assert.ok(repeat.props!.className.split(" ").includes("pointer-events-auto"), "Repeat must remain clickable inside the transparent footer");
  const event = { stopPropagation() {} };
  repeat.props!.onClick(event);
  assert.deepEqual(repeated, [item, item.preview_url]);
  assert.equal(portal(render()), undefined, "Repeat must not open the gallery");
  descendants(initial).find(node => node.props?.["aria-label"] === "Лайк")!.props!.onClick(event);
  assert.equal(liked, item);
  assert.equal(portal(render()), undefined, "Like must not open the gallery");
  descendants(initial).find(node => node.props?.["aria-label"] === "Открыть внутри приложения")!.props!.onClick();
  const opened = portal(render());
  assert.ok(opened, "Gallery must escape feed/main containing and stacking contexts");
  assert.equal(opened.$$typeof, Symbol.for("react.portal"));
  opened.children.props.onClose();
  assert.equal(portal(render()), undefined);
});
