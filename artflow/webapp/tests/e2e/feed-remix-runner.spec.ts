import { expect, test, type Page } from "@playwright/test";

const user = {
  id: 1,
  tg_id: 123,
  username: "tester",
  full_name: "Test User",
  credits: 100,
  referral_balance: 0,
  language: "ru",
};

const imageModels = [
  {
    key: "nano-banana-2",
    display_name: "🍌 Nano Banana 2",
    credits: 1.5,
    modes: ["text", "image"],
    aspect_ratios: ["1:1", "4:5", "9:16"],
    quality_options: [{ value: "2K", label: "2K" }],
    counts: [1, 2],
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
    max_refs: 1,
    supports_video_input: true,
  },
];

const feedItems = [
  {
    id: 201,
    model: "nano-banana-2",
    gen_type: "image",
    prompt: "",
    prompt_hidden: true,
    result_url: "https://example.test/source.png",
    result_urls: ["https://example.test/source.png"],
    preview_url: "https://example.test/source.png",
    preview_urls: ["https://example.test/source.png"],
    likes_count: 3,
    shares_count: 1,
    remixes: 2,
    aspect_ratio: "1:1",
    author: "Artist QA",
    is_mine: false,
  },
];

async function mockMiniAppApi(page: Page) {
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

  await page.route("https://example.test/source.png", (route) => route.fulfill({
    contentType: "image/png",
    body: Buffer.from([0x89, 0x50, 0x4e, 0x47]),
  }));
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: imageModels }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: videoModels }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: feedItems }));
  await page.route("**/api/v1/trends?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/plans", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/web/upload-media", (route) => route.fulfill({
    json: { data: { url: "https://example.test/uploaded-ref.png", kind: "image", content_type: "image/jpeg", size: 4 } },
  }));
}

test("feed work repeat asks for settings and preserves source media payload", async ({ page }) => {
  await mockMiniAppApi(page);
  let remixPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/feed/201/remix", async (route) => {
    remixPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 202,
      json: {
        id: 9201,
        task_id: "web:feed-remix-test",
        model: "nano-banana-2",
        gen_type: "image",
        prompt: "",
        prompt_hidden: true,
        status: "pending",
        result_url: null,
        result_urls: [],
        credits_spent: 1.5,
        created_at: new Date().toISOString(),
      },
    });
  });

  await page.goto("/?tgWebAppData=test");
  await expect(page.getByText("Artist QA")).toBeVisible();
  await page.getByRole("button", { name: "Повторить" }).first().click();

  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Исходная работа будет использована как основной референс.")).toBeVisible();
  await expect(dialog.getByLabel("Модель")).toBeVisible();

  await dialog.locator("input[type=file]").setInputFiles({
    name: "ref.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  await dialog.getByRole("button", { name: "Запустить повтор" }).click();

  await expect(page.getByRole("dialog", { name: /Задача #9201/ })).toBeVisible();
  expect(remixPayload).toMatchObject({
    model: "nano-banana-2",
    mode: "image",
    source_image_url: "https://example.test/source.png",
    image_url: "https://example.test/uploaded-ref.png",
    reference_urls: ["https://example.test/uploaded-ref.png"],
  });
});
