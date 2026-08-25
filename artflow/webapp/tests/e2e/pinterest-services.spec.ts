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

const trends = [
  {
    id: 101,
    kind: "image",
    title: "Кинопортрет",
    description: "Загрузите портретное фото",
    category: "portrait",
    category_title: "Портреты",
    category_emoji: "✨",
    uses_count: 3,
  },
  {
    id: 103,
    kind: "image",
    title: "Pinterest AI",
    description: "Pinterest Flow со своей внешностью",
    category: "featured",
    category_title: "Тренды",
    category_emoji: "🔥",
    uses_count: 12,
  },
];

async function mockApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/models/music", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/trends?**", (route) => route.fulfill({ json: trends }));
  await page.route("**/api/v1/plans", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/music/voices", (route) => route.fulfill({ json: [] }));
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

test("Pinterest lives in Services with a new badge and is absent from Trends", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");

  await page.getByRole("tab", { name: "Сервисы" }).click();
  const pinterest = page.getByRole("button", { name: /Pinterest/ }).first();
  await expect(pinterest).toBeVisible();
  await expect(pinterest.getByText("Новинка", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Тренды" }).click();
  await expect(page.getByText("Кинопортрет", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Pinterest AI", { exact: true })).toHaveCount(0);
});

test("Pinterest Services tile opens the existing trend runner", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Сервисы" }).click();

  await page.getByRole("button", { name: /Pinterest/ }).first().click();

  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: /Pinterest AI/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("input[type=file]")).toHaveCount(1);
  await expect(dialog.locator("select")).toHaveCount(0);
  await expect(dialog.locator("textarea")).toHaveCount(0);
});
