import { expect, test } from "@playwright/test";

const user = {
  id: 1,
  tg_id: 123,
  username: "tester",
  full_name: "Test User",
  credits: 100,
  referral_code: "REF123",
  referral_link: "https://t.me/apix_bot?start=REF123",
  referral_balance: 0,
  referral_withdraw_min_rub: 500,
  language: "ru",
};

const imageModels = [
  {
    key: "nano-banana-2",
    display_name: "🍌 Nano Banana 2",
    credits: 1.5,
    modes: ["text", "image"],
    aspect_ratios: ["1:1", "2:3", "3:2"],
    quality_options: [{ value: "2K", label: "2K" }],
    quality_prices: { "2K": 1.5 },
    counts: [1, 2, 4],
    max_refs: 4,
    has_quality: true,
  },
];

const videoModels = [
  {
    key: "veo-3.1-fast",
    display_name: "Veo 3.1 Fast",
    credits: 20,
    modes: ["text", "image", "video"],
    aspect_ratios: ["16:9", "9:16"],
    durations: [5, 10],
    resolutions: ["720p", "1080p"],
    counts: [],
    max_refs: 1,
    has_quality: true,
    supports_video_input: true,
  },
];

const plans = [
  { key: "mini", title: "мини", credits: 15, price_rub: 150, price_stars: 150 },
  { key: "start", title: "старт", credits: 25, price_rub: 250, price_stars: 250 },
];

const trends = [
  {
    id: 101,
    kind: "image",
    title: "Кинопортрет",
    description: "Загрузите портретное фото",
    user_photo_hint: "Лучше фото по пояс",
    preview_url: "https://example.test/trend.jpg",
    category_title: "Портреты",
    category_emoji: "✨",
    uses_count: 3,
  },
  {
    id: 102,
    kind: "video",
    title: "Фото в видео",
    description: "Оживим ваш снимок",
    user_photo_hint: "Нужно одно селфи",
    preview_url: "https://example.test/trend.mp4",
    category_title: "Фото → видео",
    category_emoji: "🎬",
    uses_count: 5,
  },
];

async function mockApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: imageModels }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: videoModels }));
  await page.route("**/api/v1/models/music", (route) => route.fulfill({ json: [{ key: "suno-v5", display_name: "Suno 5", credits: 10, modes: ["text"] }] }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/trends?**", (route) => route.fulfill({ json: trends }));
  await page.route("**/api/v1/trends/101", (route) => route.fulfill({ json: trends[0] }));
  await page.route("**/api/v1/trends/101/link", (route) => route.fulfill({ json: { link: "https://t.me/apix_bot?startapp=trend_101" } }));
  await page.route("**/api/v1/plans", (route) => route.fulfill({ json: plans }));
  await page.route("**/api/v1/referrals", (route) => route.fulfill({ json: {
    referral_code: "REF123",
    referral_link: "https://t.me/apix_bot?start=REF123",
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
  } }));
  await page.route("**/api/v1/music/voices", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/settings/language", async (route) => {
    const body = route.request().postDataJSON() as { language?: string };
    await route.fulfill({ json: { language: body.language || "ru" } });
  });
  await page.route("**/api/v1/topup/**", (route) => route.fulfill({ json: { url: "https://example.test/pay" } }));
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "test",
        initDataUnsafe: { user: { id: 123, first_name: "Test" } },
        colorScheme: "dark",
        ready: () => undefined,
        expand: () => undefined,
        HapticFeedback: { impactOccurred: () => undefined, notificationOccurred: () => undefined },
        openLink: () => undefined,
        openInvoice: () => undefined,
      },
    } as typeof window.Telegram;
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("renders feed-first shell without horizontal overflow", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await expect(page.getByRole("tab", { name: "Лента" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Настройки" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(2);
});

test("payment cabinet uses kisses wording", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("button", { name: /Открыть баланс/ }).click();
  await expect(page.getByText("1. Пакет поцелуев")).toBeVisible();
  await expect(page.getByText(/15 поцелу/)).toBeVisible();
  await expect(page.getByText("кредиты")).toHaveCount(0);
});

test("settings expose color schemes and language switch", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Настройки" }).click();
  await expect(page.getByText("Цветовая схема")).toBeVisible();
  await expect(page.getByText("Поцелуй")).toBeVisible();
  await page.getByText("English").click();
  await expect(page.getByText(/English|Язык/)).toBeVisible();
});

test("services expose mobile-friendly Suno music panel", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Сервисы" }).click();
  await expect(page.getByText("Музыка / Suno")).toBeVisible();
  await expect(page.getByPlaceholder("Текст песни или идея трека")).toBeVisible();
});

test("one-photo trend runner uploads and runs without exposing generation controls", async ({ page }) => {
  let runPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/trends/upload", async (route) => {
    await route.fulfill({ json: { asset_id: "apixasset.test.signature", url: "https://example.test/user.jpg", kind: "image", filename: "face.jpg" } });
  });
  await page.route("**/api/v1/trends/101/run", async (route) => {
    runPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ json: {
      ok: true,
      credits: 98.5,
      task: {
        id: 9001,
        task_id: "web:trend-test",
        model: "Nano Banana 2",
        gen_type: "image",
        prompt: "",
        prompt_hidden: true,
        status: "pending",
        result_url: null,
        result_urls: [],
        credits_spent: 1.5,
        created_at: new Date().toISOString(),
      },
    } });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Тренды" }).click();
  await expect(page.getByText("Фото-тренды")).toBeVisible();
  await page.getByRole("button", { name: /Повторить/ }).first().click();

  const dialog = page.getByRole("dialog", { name: /Кинопортрет/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("select")).toHaveCount(0);
  await expect(dialog.locator("textarea")).toHaveCount(0);
  await expect(dialog.getByText(/модель|формат|качество|duration|seed/i)).toHaveCount(0);

  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });

  await expect(page.getByRole("dialog", { name: /Задача #9001/ })).toBeVisible();
  expect(runPayload).toMatchObject({ asset_id: "apixasset.test.signature" });
  expect(typeof runPayload?.idempotency_key).toBe("string");
  expect(runPayload).not.toHaveProperty("model");
  expect(runPayload).not.toHaveProperty("prompt");
  expect(runPayload).not.toHaveProperty("ratio");
  expect(runPayload).not.toHaveProperty("duration");
});
