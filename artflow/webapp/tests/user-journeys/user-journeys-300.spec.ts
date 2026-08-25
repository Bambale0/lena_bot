import { expect, test, type Page, type Route } from "@playwright/test";

const SCENARIOS_PER_DOMAIN = 25;
const DOMAIN_COUNT = 12;
const EXPECTED_TEST_COUNT = SCENARIOS_PER_DOMAIN * DOMAIN_COUNT;

if (EXPECTED_TEST_COUNT !== 300) {
  throw new Error(`Expected 300 user-journey tests, got ${EXPECTED_TEST_COUNT}`);
}

const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=",
  "base64",
);

const NAV_TABS = ["Лента", "Фото", "Видео", "Motion", "Тренды", "Сервисы", "Профиль", "Настройки"] as const;

type Json = Record<string, unknown>;

type Captures = {
  feedSources?: string[];
  remix?: Json;
  image?: Json;
  video?: Json;
  trendRun?: Json;
  language?: Json;
};

type MockOptions = {
  user?: Json;
  feed?: Json[];
  feedBySource?: Record<string, Json[]>;
  publicFeed?: Record<number, Json>;
  trends?: Json[];
  plans?: Json[];
  history?: Json[];
  imageModels?: Json[];
  videoModels?: Json[];
  musicModels?: Json[];
  colorScheme?: "dark" | "light";
  startParam?: string;
  uploadUrl?: string;
  captures?: Captures;
  failures?: Record<string, number>;
};

const baseUser: Json = {
  id: 1,
  tg_id: 123,
  username: "journey_user",
  full_name: "Journey User",
  credits: 100,
  referral_code: "JOURNEY",
  referral_link: "https://t.me/apix_ai_bot?start=JOURNEY",
  referral_balance: 0,
  referral_withdraw_min_rub: 500,
  language: "ru",
};

const imageModels: Json[] = [
  {
    key: "nano-banana-2",
    display_name: "🍌 Nano Banana 2",
    credits: 1.5,
    modes: ["text", "image"],
    aspect_ratio_modes: ["text", "image"],
    aspect_ratios: ["1:1", "4:5", "9:16"],
    quality_options: [
      { value: "2K", label: "2K", credits: 1.5 },
      { value: "4K", label: "4K", credits: 2.5 },
    ],
    quality_prices: { "2K": 1.5, "4K": 2.5 },
    counts: [1, 2, 4],
    max_refs: 4,
    has_quality: true,
  },
];

const videoModels: Json[] = [
  {
    key: "veo-3.1-fast",
    display_name: "Veo 3.1 Fast",
    credits: 20,
    modes: ["text", "image", "video"],
    aspect_ratio_modes: ["text", "image", "video"],
    aspect_ratios: ["16:9", "9:16"],
    durations: [5, 10],
    duration_options: [5, 10],
    resolutions: ["720p", "1080p"],
    resolution_options: ["720p", "1080p"],
    max_refs: 1,
    has_quality: true,
    supports_video_input: true,
  },
  {
    key: "kling-motion-control",
    display_name: "Kling Motion Control",
    credits: 30,
    modes: ["motion"],
    aspect_ratio_modes: ["motion"],
    aspect_ratios: ["16:9", "9:16"],
    durations: [5],
    resolutions: ["720p"],
    max_refs: 1,
    supports_video_input: true,
  },
];

const defaultPlans: Json[] = [
  { key: "mini", title: "Мини", credits: 15, price_rub: 150, price_stars: 150 },
  { key: "start", title: "Старт", credits: 25, price_rub: 250, price_stars: 250 },
];

const defaultReferrals: Json = {
  referral_code: "JOURNEY",
  referral_link: "https://t.me/apix_ai_bot?start=JOURNEY",
  bonus_l1_credits: 5,
  commission_l1: 10,
  commission_l2: 5,
  commission_l3: 2,
  withdraw_min_rub: 500,
  exchange_min_rub: 100,
  exchange_rate_rub_per_credit: 10,
  counts: { l1: 0, l2: 0, l3: 0 },
  balance: { total_earned: 0, pending_withdrawals: 0, available_to_withdraw: 0 },
  feed_remix_reward_rub: 0,
  children: { l1: [], l2: [], l3: [] },
  withdrawals: [],
};

function makeFeedItem(seed: number, overrides: Json = {}): Json {
  const isVideo = Boolean(overrides.gen_type === "video");
  const extension = isVideo ? "mp4" : "png";
  const media = `https://example.test/media-${seed}.${extension}`;
  return {
    id: 1000 + seed,
    model: isVideo ? "veo-3.1-fast" : "nano-banana-2",
    gen_type: isVideo ? "video" : "image",
    prompt: `Пользовательский сценарий ${seed}`,
    prompt_hidden: false,
    result_url: media,
    result_urls: [media],
    preview_url: media,
    preview_urls: [media],
    likes_count: seed % 7,
    shares_count: seed % 5,
    remixes: seed % 3,
    aspect_ratio: isVideo ? "16:9" : "1:1",
    author: `Автор ${seed}`,
    is_mine: false,
    ...overrides,
  };
}

function makeTrend(seed: number, kind: "image" | "video" = "image"): Json {
  return {
    id: 2000 + seed,
    kind,
    title: `Тренд ${seed}`,
    description: `Описание тренда ${seed}`,
    user_photo_hint: "Загрузите подходящий референс",
    preview_url: `https://example.test/trend-${seed}.${kind === "video" ? "mp4" : "png"}`,
    category: kind === "video" ? `video-${seed % 4}` : `image-${seed % 4}`,
    category_title: kind === "video" ? `Видео ${seed % 4}` : `Фото ${seed % 4}`,
    category_emoji: kind === "video" ? "🎬" : "✨",
    uses_count: seed,
  };
}

function makeTask(seed: number, kind: "image" | "video" = "image"): Json {
  return {
    id: 9000 + seed,
    task_id: `web:journey-${kind}-${seed}`,
    model: kind === "video" ? "veo-3.1-fast" : "nano-banana-2",
    gen_type: kind,
    prompt: `Journey task ${seed}`,
    prompt_hidden: false,
    status: "pending",
    result_url: null,
    result_urls: [],
    credits_spent: kind === "video" ? 20 : 1.5,
    created_at: new Date(2026, 7, 25, 3, seed % 60).toISOString(),
  };
}

function requestJson(route: Route): Json {
  try {
    return (route.request().postDataJSON() || {}) as Json;
  } catch {
    return {};
  }
}

async function mockMiniApp(page: Page, options: MockOptions = {}) {
  const user = { ...baseUser, ...(options.user || {}) };
  const captures = options.captures || {};
  const feed = options.feed || [];
  const feedBySource = options.feedBySource || {};
  const publicFeed = options.publicFeed || {};
  const trends = options.trends || [];
  const plans = options.plans || defaultPlans;
  const history = options.history || [];
  const images = options.imageModels || imageModels;
  const videos = options.videoModels || videoModels;
  const music = options.musicModels || [{ key: "suno-v5", display_name: "Suno 5", credits: 10, modes: ["text"] }];
  const uploadUrl = options.uploadUrl || "https://example.test/uploaded-ref.png";
  const failures = options.failures || {};

  await page.addInitScript(
    ({ colorScheme, startParam }) => {
      window.Telegram = {
        WebApp: {
          initData: "journey-test",
          initDataUnsafe: {
            user: { id: 123, first_name: "Journey" },
            start_param: startParam || undefined,
          },
          colorScheme,
          ready: () => undefined,
          expand: () => undefined,
          HapticFeedback: {
            impactOccurred: () => undefined,
            notificationOccurred: () => undefined,
          },
          openLink: () => undefined,
          openInvoice: () => undefined,
        },
      } as typeof window.Telegram;
    },
    { colorScheme: options.colorScheme || "dark", startParam: options.startParam || "" },
  );

  await page.route("https://example.test/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (/\.(mp4|webm|mov)$/i.test(pathname)) {
      await route.fulfill({ status: 200, contentType: "video/mp4", body: Buffer.alloc(0) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "image/png", body: TINY_PNG });
  });

  await page.route("**/api/web/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const failure = failures[path];
    if (failure) {
      await route.fulfill({ status: failure, json: { detail: `Injected failure ${failure}` } });
      return;
    }
    if (path === "/api/web/upload-media") {
      await route.fulfill({ json: { data: { url: uploadUrl, kind: "image", content_type: "image/jpeg", size: 4 } } });
      return;
    }
    const feedMatch = path.match(/^\/api\/web\/feed\/(\d+)$/);
    if (feedMatch) {
      const id = Number(feedMatch[1]);
      const item = publicFeed[id];
      await route.fulfill(item ? { json: { data: item } } : { status: 404, json: { detail: "Not found" } });
      return;
    }
    const publishMatch = path.match(/^\/api\/web\/feed\/generations\/(\d+)\/publish$/);
    if (publishMatch) {
      await route.fulfill({ json: { data: { is_public_feed: true, link: `https://t.me/apix_ai_bot?start=feed_${publishMatch[1]}` } } });
      return;
    }
    await route.fulfill({ json: {} });
  });

  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const failure = failures[path];
    if (failure) {
      await route.fulfill({ status: failure, json: { detail: `Injected failure ${failure}` } });
      return;
    }

    if (path === "/api/v1/me") return route.fulfill({ json: user });
    if (path === "/api/v1/models/image") return route.fulfill({ json: images });
    if (path === "/api/v1/models/video") return route.fulfill({ json: videos });
    if (path === "/api/v1/models/music") return route.fulfill({ json: music });
    if (path === "/api/v1/history") return route.fulfill({ json: history });
    if (path === "/api/v1/plans") return route.fulfill({ json: plans });
    if (path === "/api/v1/referrals") return route.fulfill({ json: defaultReferrals });
    if (path === "/api/v1/music/voices") return route.fulfill({ json: [] });

    if (path === "/api/v1/feed" && method === "GET") {
      const source = url.searchParams.get("source") || "recent";
      captures.feedSources?.push(source);
      return route.fulfill({ json: feedBySource[source] || feed });
    }

    const likeMatch = path.match(/^\/api\/v1\/feed\/(\d+)\/like$/);
    if (likeMatch && method === "POST") return route.fulfill({ json: { likes_count: 99 } });

    const remixMatch = path.match(/^\/api\/v1\/feed\/(\d+)\/remix$/);
    if (remixMatch && method === "POST") {
      captures.remix = requestJson(route);
      return route.fulfill({ status: 202, json: makeTask(Number(remixMatch[1]), "image") });
    }

    if (path === "/api/v1/generate/image" && method === "POST") {
      captures.image = requestJson(route);
      return route.fulfill({ status: 202, json: makeTask(1, "image") });
    }
    if (path === "/api/v1/generate/video" && method === "POST") {
      captures.video = requestJson(route);
      return route.fulfill({ status: 202, json: makeTask(2, "video") });
    }

    if (path === "/api/v1/trends" && method === "GET") return route.fulfill({ json: trends });
    const trendDetailMatch = path.match(/^\/api\/v1\/trends\/(\d+)$/);
    if (trendDetailMatch && method === "GET") {
      const id = Number(trendDetailMatch[1]);
      const trend = trends.find((item) => Number(item.id) === id);
      return route.fulfill(trend ? { json: trend } : { status: 404, json: { detail: "Trend not found" } });
    }
    if (path === "/api/v1/trends/upload" && method === "POST") {
      return route.fulfill({ json: { asset_id: "apixasset.journey.signature", url: uploadUrl, kind: "image", filename: "journey.jpg" } });
    }
    const trendRunMatch = path.match(/^\/api\/v1\/trends\/(\d+)\/run$/);
    if (trendRunMatch && method === "POST") {
      captures.trendRun = requestJson(route);
      return route.fulfill({ json: { ok: true, credits: Number(user.credits || 100) - 1.5, task: makeTask(Number(trendRunMatch[1]), "image") } });
    }
    const trendPrepareMatch = path.match(/^\/api\/v1\/trends\/(\d+)\/prepare$/);
    if (trendPrepareMatch && method === "POST") {
      const id = Number(trendPrepareMatch[1]);
      const trend = trends.find((item) => Number(item.id) === id) || makeTrend(id);
      return route.fulfill({ json: { kind: trend.kind || "image", prompt_id: id, title: trend.title || `Тренд ${id}`, model: "nano-banana-2", settings: { ratio: "1:1", quality: "2K" } } });
    }
    const trendLinkMatch = path.match(/^\/api\/v1\/trends\/(\d+)\/link$/);
    if (trendLinkMatch) return route.fulfill({ json: { link: `https://t.me/apix_ai_bot?startapp=trend_${trendLinkMatch[1]}` } });

    if (path === "/api/v1/settings/language" && method === "POST") {
      captures.language = requestJson(route);
      return route.fulfill({ json: captures.language });
    }
    if (path.startsWith("/api/v1/topup/")) return route.fulfill({ json: { url: "https://example.test/pay" } });
    if (path === "/api/v1/assistant") return route.fulfill({ json: { reply: "Тестовый ответ ассистента" } });
    if (path === "/api/v1/photo-prompt") return route.fulfill({ json: { prompt: "cinematic portrait" } });

    const generationMatch = path.match(/^\/api\/v1\/generations\/(\d+)$/);
    if (generationMatch) return route.fulfill({ json: makeTask(Number(generationMatch[1]), "image") });

    await route.fulfill({ json: {} });
  });
}

async function openApp(page: Page, query = "") {
  await page.goto(`/?tgWebAppData=journey-test${query}`);
  await expect(page.getByRole("tab", { name: "Лента", exact: true })).toBeVisible();
}

function viewportMode(width: number): string {
  if (width <= 360) return "nano";
  if (width <= 430) return "phone";
  if (width <= 560) return "phablet";
  if (width <= 900) return "tablet";
  return "wide";
}

function registerDomain(name: string, runner: (page: Page, seed: number) => Promise<void>) {
  test.describe(name, () => {
    for (let seed = 1; seed <= SCENARIOS_PER_DOMAIN; seed += 1) {
      test(`${name} · пользовательский сценарий ${seed}`, async ({ page }) => {
        await runner(page, seed);
      });
    }
  });
}

registerDomain("01 · Навигация между основными разделами", async (page, seed) => {
  await mockMiniApp(page);
  await openApp(page);
  const sequence = [
    NAV_TABS[seed % NAV_TABS.length],
    NAV_TABS[(seed * 3 + 1) % NAV_TABS.length],
    NAV_TABS[(seed * 5 + 2) % NAV_TABS.length],
  ];
  for (const label of sequence) {
    const tab = page.getByRole("tab", { name: label, exact: true });
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
  }
  await expect(page.getByRole("tab", { selected: true })).toHaveCount(1);
});

registerDomain("02 · Адаптивность Telegram WebView", async (page, seed) => {
  const widths = [320, 340, 360, 361, 375, 390, 414, 430, 431, 480, 520, 560, 561, 640, 720, 768, 820, 900, 901, 1024, 1100, 1180, 1280, 1366, 1440];
  const width = widths[seed - 1];
  const height = seed % 3 === 0 ? 600 : seed % 3 === 1 ? 844 : 720;
  await page.setViewportSize({ width, height });
  await mockMiniApp(page, { colorScheme: seed % 2 ? "dark" : "light" });
  await openApp(page);
  const shell = page.locator(".apix-shell");
  await expect(shell).toHaveAttribute("data-viewport", viewportMode(width));
  await expect(shell).toHaveAttribute("data-short", height <= 660 ? "true" : "false");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(2);
});

registerDomain("03 · Профиль в шапке и кабинет баланса", async (page, seed) => {
  const name = `Пользователь ${seed}`;
  const plan = { key: `plan-${seed}`, title: `Пакет ${seed}`, credits: 10 + seed, price_rub: 100 + seed * 10, price_stars: 100 + seed * 10 };
  await mockMiniApp(page, {
    user: { full_name: name, username: `user_${seed}`, credits: 20 + seed },
    plans: [plan],
  });
  await openApp(page);
  await expect(page.locator(".apix-profile-name")).toHaveText(name);
  await page.getByRole("button", { name: "Открыть баланс" }).click();
  await expect(page.getByText(plan.title, { exact: true })).toBeVisible();
  await expect(page.getByText(new RegExp(`${plan.credits}\\s*поцелу`))).toBeVisible();
});

registerDomain("04 · Фильтры и источники ленты", async (page, seed) => {
  const source = ["recent", "top_day", "top"][seed % 3];
  const sourceLabel = source === "recent" ? "Новые" : source === "top_day" ? "Топ дня" : "Лучшие";
  const filter = ["Все", "Фото", "Видео", "Мои"][seed % 4];
  const base = seed * 10;
  const sourceItems = [
    makeFeedItem(base + 1, { author: `Фото ${seed}`, is_mine: false }),
    makeFeedItem(base + 2, { author: `Моё фото ${seed}`, is_mine: true }),
    makeFeedItem(base + 3, { author: `Видео ${seed}`, gen_type: "video", result_url: `https://example.test/video-${seed}.mp4`, result_urls: [`https://example.test/video-${seed}.mp4`], preview_url: `https://example.test/video-${seed}.mp4`, preview_urls: [`https://example.test/video-${seed}.mp4`] }),
    makeFeedItem(base + 4, { author: `Моё видео ${seed}`, gen_type: "video", is_mine: true, result_url: `https://example.test/mine-video-${seed}.mp4`, result_urls: [`https://example.test/mine-video-${seed}.mp4`], preview_url: `https://example.test/mine-video-${seed}.mp4`, preview_urls: [`https://example.test/mine-video-${seed}.mp4`] }),
  ];
  const captures: Captures = { feedSources: [] };
  await mockMiniApp(page, {
    feed: sourceItems,
    feedBySource: { recent: sourceItems, top_day: sourceItems, top: sourceItems },
    captures,
  });
  await openApp(page);
  const toolbar = page.locator(".apix-feed-toolbar");
  await toolbar.getByRole("button", { name: sourceLabel, exact: true }).click();
  await toolbar.getByRole("button", { name: filter, exact: true }).click();
  expect(captures.feedSources?.includes(source)).toBeTruthy();
  if (filter === "Фото") {
    await expect(page.getByText(`Фото ${seed}`, { exact: true })).toBeVisible();
    await expect(page.getByText(`Видео ${seed}`, { exact: true })).toHaveCount(0);
  } else if (filter === "Видео") {
    await expect(page.getByText(`Видео ${seed}`, { exact: true })).toBeVisible();
    await expect(page.getByText(`Фото ${seed}`, { exact: true })).toHaveCount(0);
  } else if (filter === "Мои") {
    await expect(page.getByText(`Моё фото ${seed}`, { exact: true })).toBeVisible();
    await expect(page.getByText(`Фото ${seed}`, { exact: true })).toHaveCount(0);
  } else {
    await expect(page.locator(".apix-feed-card")).toHaveCount(4);
  }
});

registerDomain("05 · Shared feed link открывает именно выбранную работу", async (page, seed) => {
  const targetId = 5000 + seed;
  const canonical = `https://example.test/canonical-${seed}.png`;
  const stale = `https://example.test/stale-${seed}.png`;
  const target = makeFeedItem(seed, {
    id: targetId,
    author: `Target ${seed}`,
    result_url: stale,
    result_urls: [canonical, stale],
    preview_url: stale,
    preview_urls: [stale],
  });
  const decoy = makeFeedItem(8000 + seed, { author: `Decoy ${seed}` });
  const useTelegramStart = seed % 2 === 0;
  await mockMiniApp(page, {
    feed: [decoy],
    publicFeed: { [targetId]: target },
    startParam: useTelegramStart ? `feed_${targetId}` : "",
  });
  await openApp(page, useTelegramStart ? "" : `&feed=${targetId}`);
  const firstCard = page.locator(".apix-feed-card").first();
  await expect(firstCard.getByText(`Target ${seed}`, { exact: true })).toBeVisible();
  await expect(firstCard.locator("img")).toHaveAttribute("src", canonical);
});

registerDomain("06 · Повтор работы из ленты сохраняет исходник и новые refs", async (page, seed) => {
  const source = `https://example.test/repeat-source-${seed}.png`;
  const uploaded = `https://example.test/repeat-ref-${seed}.png`;
  const item = makeFeedItem(seed, {
    id: 6000 + seed,
    author: `Repeat ${seed}`,
    result_url: source,
    result_urls: [source],
    preview_url: source,
    preview_urls: [source],
  });
  const captures: Captures = {};
  await mockMiniApp(page, { feed: [item], uploadUrl: uploaded, captures });
  await openApp(page);
  await page.locator(".apix-feed-card").first().getByRole("button", { name: "Повторить" }).click();
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await dialog.locator("input[type=file]").setInputFiles({
    name: `ref-${seed}.jpg`,
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  await dialog.getByRole("button", { name: "Запустить повтор" }).click();
  await expect(page.getByRole("dialog", { name: /Задача #/ })).toBeVisible();
  expect(captures.remix).toMatchObject({
    source_image_url: source,
    image_url: uploaded,
    reference_urls: [uploaded],
  });
});

registerDomain("07 · Фото-генерация с пользовательскими параметрами", async (page, seed) => {
  const prompt = `Фотореалистичный портрет сценарий ${seed}`;
  const ratio = ["1:1", "4:5", "9:16"][seed % 3];
  const quality = seed % 2 ? "2K" : "4K";
  const captures: Captures = {};
  await mockMiniApp(page, { captures });
  await openApp(page);
  await page.getByRole("tab", { name: "Фото", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Фото", exact: true })).toBeVisible();
  await page.getByLabel("Промпт").fill(prompt);
  await page.getByRole("button", { name: ratio, exact: true }).click();
  await page.getByRole("button", { name: quality, exact: true }).click();
  await page.locator(".apix-submit-button").click();
  await expect(page.getByRole("dialog", { name: /Задача #9001/ })).toBeVisible();
  expect(captures.image).toMatchObject({
    model: "nano-banana-2",
    prompt,
    aspect_ratio: ratio,
    quality,
    reference_urls: [],
  });
});

registerDomain("08 · Видео-генерация с режимом, длительностью и разрешением", async (page, seed) => {
  const prompt = `Видео пользовательский сценарий ${seed}`;
  const ratio = seed % 2 ? "16:9" : "9:16";
  const duration = seed % 2 ? 5 : 10;
  const resolution = seed % 3 ? "720p" : "1080p";
  const captures: Captures = {};
  await mockMiniApp(page, { captures });
  await openApp(page);
  await page.getByRole("tab", { name: "Видео", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Видео", exact: true })).toBeVisible();
  await page.getByLabel("Промпт").fill(prompt);
  await page.getByRole("button", { name: ratio, exact: true }).click();
  await page.getByRole("button", { name: `${duration} сек`, exact: true }).click();
  await page.getByRole("button", { name: resolution, exact: true }).click();
  await page.locator(".apix-submit-button").click();
  await expect(page.getByRole("dialog", { name: /Задача #9002/ })).toBeVisible();
  expect(captures.video).toMatchObject({
    model: "veo-3.1-fast",
    prompt,
    mode: "text",
    duration,
    aspect_ratio: ratio,
    resolution,
  });
});

registerDomain("09 · Каталог трендов и пользовательские фильтры", async (page, seed) => {
  const imageTrend = makeTrend(seed, "image");
  const videoTrend = makeTrend(100 + seed, "video");
  await mockMiniApp(page, { trends: [imageTrend, videoTrend] });
  await openApp(page);
  await page.getByRole("tab", { name: "Тренды", exact: true }).click();
  await expect(page.getByText(String(imageTrend.title), { exact: true }).first()).toBeVisible();
  await expect(page.getByText(String(videoTrend.title), { exact: true }).first()).toBeVisible();
  const kind = seed % 2 ? "Фото" : "Видео";
  await page.getByRole("button", { name: kind, exact: true }).first().click();
  if (kind === "Фото") {
    await expect(page.getByText(String(imageTrend.title), { exact: true }).first()).toBeVisible();
  } else {
    await expect(page.getByText(String(videoTrend.title), { exact: true }).first()).toBeVisible();
  }
});

registerDomain("10 · Запуск тренда через upload-first runner", async (page, seed) => {
  const trend = makeTrend(seed, "image");
  const captures: Captures = {};
  await mockMiniApp(page, { trends: [trend], captures });
  await openApp(page);
  await page.getByRole("tab", { name: "Тренды", exact: true }).click();
  await page.getByRole("button", { name: /Повторить/ }).first().click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: new RegExp(String(trend.title)) });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("select")).toHaveCount(0);
  await expect(dialog.locator("textarea")).toHaveCount(0);
  await dialog.locator("input[type=file]").setInputFiles({
    name: `identity-${seed}.jpg`,
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect(page.getByRole("dialog", { name: /Задача #/ })).toBeVisible();
  expect(captures.trendRun).toMatchObject({ asset_id: "apixasset.journey.signature" });
  expect(typeof captures.trendRun?.idempotency_key).toBe("string");
  expect(captures.trendRun).not.toHaveProperty("model");
  expect(captures.trendRun).not.toHaveProperty("prompt");
});

registerDomain("11 · Настройки, сервисы и профиль пользователя", async (page, seed) => {
  const captures: Captures = {};
  const history = [makeTask(seed, seed % 2 ? "image" : "video")];
  await mockMiniApp(page, {
    user: { full_name: `Кабинет ${seed}`, username: `cabinet_${seed}` },
    history,
    captures,
  });
  await openApp(page);
  const branch = seed % 3;
  if (branch === 0) {
    await page.getByRole("tab", { name: "Настройки", exact: true }).click();
    await expect(page.getByText("Цветовая схема")).toBeVisible();
    const schemeButtons = page.locator("[data-apix-preview-scheme]");
    await expect(schemeButtons).toHaveCount(4);
    await schemeButtons.nth(seed % 4).click();
    await page.getByRole("button", { name: /English/ }).click();
    expect(captures.language).toMatchObject({ language: "en" });
  } else if (branch === 1) {
    await page.getByRole("tab", { name: "Сервисы", exact: true }).click();
    await expect(page.getByText("Музыка / Suno")).toBeVisible();
    await expect(page.getByPlaceholder("Текст песни или идея трека")).toBeVisible();
  } else {
    await page.getByRole("tab", { name: "Профиль", exact: true }).click();
    await expect(page.getByRole("heading", { name: `Кабинет ${seed}` })).toBeVisible();
    await expect(page.getByText("История").first()).toBeVisible();
    await page.getByRole("button", { name: "История задач", exact: true }).click();
    await expect(page.getByText("Всего")).toBeVisible();
  }
});

registerDomain("12 · Ошибки, пустые данные и валидация без краша приложения", async (page, seed) => {
  const mode = seed % 5;
  const failures: Record<string, number> = {};
  let feed: Json[] = [];
  let trends: Json[] = [];
  let plans: Json[] = [];
  let images: Json[] = imageModels;
  let videos: Json[] = videoModels;

  if (mode === 0) failures["/api/v1/feed"] = 503;
  if (mode === 1) failures["/api/v1/trends"] = 502;
  if (mode === 2) plans = [];
  if (mode === 3) images = [];
  if (mode === 4) videos = [];

  await mockMiniApp(page, { feed, trends, plans, imageModels: images, videoModels: videos, failures });
  await openApp(page);
  await expect(page.locator(".apix-shell")).toBeVisible();

  if (mode === 0) {
    await expect(page.getByText("По этому фильтру работ пока нет")).toBeVisible();
  } else if (mode === 1) {
    await page.getByRole("tab", { name: "Тренды", exact: true }).click();
    await expect(page.getByRole("tab", { name: "Тренды", exact: true })).toHaveAttribute("aria-selected", "true");
  } else if (mode === 2) {
    await page.getByRole("button", { name: "Открыть баланс" }).click();
    await expect(page.getByText(/пакет/i).first()).toBeVisible();
  } else if (mode === 3) {
    await page.getByRole("tab", { name: "Фото", exact: true }).click();
    await expect(page.getByText("Нет моделей")).toBeVisible();
  } else {
    await page.getByRole("tab", { name: "Видео", exact: true }).click();
    await expect(page.getByText("Нет моделей")).toBeVisible();
  }
});
