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

const pinterestService = {
  id: "pinterest",
  title: "Pinterest AI",
  description: "Повторяй Pinterest-сцены со своей внешностью",
  badge: "Новинка",
  price_credits: 2,
  quality: "2K",
  max_identity_angles: 5,
  height_min_cm: 120,
  height_max_cm: 230,
  weight_min_kg: 30,
  weight_max_kg: 250,
  available: true,
};

test("service=pinterest opens Pinterest Flow directly from the bot button", async ({ page }) => {
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/models/music", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/trends?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/services/pinterest", (route) => route.fulfill({ json: pinterestService }));
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

  await page.goto("/?service=pinterest&tgWebAppData=test");

  const dialog = page.locator("#apix-pinterest-service-root").getByRole("dialog", { name: "Повтори фото с Pinterest" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Pinterest AI · сервис", { exact: true })).toBeVisible();
  await expect(dialog.getByText("2 💋", { exact: true })).toBeVisible();
});
