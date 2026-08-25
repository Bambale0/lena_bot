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

test("Pinterest stays active in Services even when it is outside the public trends slice", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");

  await page.getByRole("tab", { name: "Сервисы" }).click();
  const pinterest = page.getByRole("button", { name: /Pinterest/ }).first();
  await expect(pinterest).toBeVisible();
  await expect(pinterest).toBeEnabled();
  await expect(pinterest.getByText("Новинка", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "Тренды" }).click();
  await expect(page.getByText("Кинопортрет", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Pinterest", { exact: true })).toHaveCount(0);
});

test("Pinterest Services matches the approved manual reference UX", async ({ page }) => {
  let uploadIndex = 0;
  let runCalls = 0;
  let runPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/trends/upload", async (route) => {
    uploadIndex += 1;
    await route.fulfill({
      json: {
        asset_id: `asset-${uploadIndex}`,
        url: `/uploads/pinterest-${uploadIndex}.jpg`,
        kind: "image",
        filename: `pinterest-${uploadIndex}.jpg`,
        content_type: "image/jpeg",
      },
    });
  });
  await page.route("**/api/v1/trends/0/pinterest-run", async (route) => {
    runCalls += 1;
    runPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 202,
      json: {
        ok: true,
        task: { id: 777, model: "nano-banana-pro", gen_type: "image", status: "pending" },
        credits: 98,
      },
    });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Сервисы" }).click();
  await page.getByRole("button", { name: /Pinterest/ }).first().click();

  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: "Повтори фото с Pinterest" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Как получить результат 1 в 1", { exact: true })).toBeVisible();
  await expect(dialog.getByText(/Слева — кадр, который повторяем\. Справа — ваше основное фото/)).toBeVisible();
  await expect(dialog.getByText("РЕФЕРЕНС", { exact: true })).toBeVisible();
  await expect(dialog.getByText("откуда", { exact: true })).toBeVisible();
  await expect(dialog.getByText("ТЫ", { exact: true })).toBeVisible();
  await expect(dialog.getByText("кого вставляем", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Фото, которое повторяем", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Ваше фото", { exact: true })).toBeVisible();
  await expect(dialog.getByText(/Рост и вес обязательны, чтобы руки, шея и пропорции тела совпали с вами/)).toBeVisible();
  await expect(dialog.getByText(/Загрузка фото сама генерацию не запускает/)).toBeVisible();
  await expect(dialog.locator("input[type=file]")).toHaveCount(2);
  await expect(dialog.locator('input[type="number"]')).toHaveCount(2);
  await expect(dialog.locator("select")).toHaveCount(0);
  await expect(dialog.locator("textarea")).toHaveCount(0);

  const createButton = dialog.getByRole("button", { name: "Создать →" });
  await expect(createButton).toBeDisabled();

  await dialog.getByLabel("Загрузить референс Pinterest").setInputFiles({
    name: "scene.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from("scene"),
  });
  expect(runCalls).toBe(0);
  await expect(dialog.getByText("Готово ✓", { exact: true }).first()).toBeVisible();

  await dialog.getByLabel("Загрузить ваше фото").setInputFiles({
    name: "me.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from("identity"),
  });
  expect(runCalls).toBe(0);
  await expect(dialog.getByText("1–5 ракурсов одного человека", { exact: true })).toBeVisible();
  await expect(dialog.getByText(/Дополнительные ракурсы необязательны/)).toBeVisible();
  await expect(dialog.getByText(/сцена, свет и поза считаются с референса/)).toBeVisible();
  await expect(dialog.getByText(/лицо и внешность берутся только с твоего фото/)).toBeVisible();
  await expect(dialog.locator("input[type=file]")).toHaveCount(3);
  await expect(createButton).toBeDisabled();

  await dialog.getByLabel("Рост").fill("165");
  await dialog.getByLabel("Вес").fill("55");
  await expect(createButton).toBeEnabled();
  expect(runCalls).toBe(0);

  await createButton.click();
  await expect.poll(() => runCalls).toBe(1);
  expect(runPayload).toMatchObject({
    reference_asset_ids: ["asset-1", "asset-2"],
    height_cm: 165,
    weight_kg: 55,
    confirmed: true,
  });
});

test("Pinterest accepts multiple optional identity angles without auto-start", async ({ page }) => {
  let uploadIndex = 0;
  let runCalls = 0;
  let runPayload: Record<string, unknown> | null = null;

  await page.route("**/api/v1/trends/upload", async (route) => {
    uploadIndex += 1;
    await route.fulfill({
      json: {
        asset_id: `asset-${uploadIndex}`,
        url: `/uploads/${uploadIndex}.jpg`,
        kind: "image",
        filename: `${uploadIndex}.jpg`,
      },
    });
  });
  await page.route("**/api/v1/trends/0/pinterest-run", async (route) => {
    runCalls += 1;
    runPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 202,
      json: { ok: true, task: { id: 778, model: "nano-banana-pro", gen_type: "image", status: "pending" }, credits: 98 },
    });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Сервисы" }).click();
  await page.getByRole("button", { name: /Pinterest/ }).first().click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: "Повтори фото с Pinterest" });

  await dialog.getByLabel("Загрузить референс Pinterest").setInputFiles({ name: "scene.jpg", mimeType: "image/jpeg", buffer: Buffer.from("scene") });
  await dialog.getByLabel("Загрузить ваше фото").setInputFiles({ name: "me.jpg", mimeType: "image/jpeg", buffer: Buffer.from("me") });
  await dialog.getByLabel("Добавить дополнительные ракурсы").setInputFiles([
    { name: "me-side.jpg", mimeType: "image/jpeg", buffer: Buffer.from("side") },
    { name: "me-three-quarter.jpg", mimeType: "image/jpeg", buffer: Buffer.from("three-quarter") },
  ]);

  expect(runCalls).toBe(0);
  await expect(dialog.getByText("2/5", { exact: true })).toBeVisible();
  await expect(dialog.getByAltText("Дополнительный ракурс 1")).toBeVisible();
  await expect(dialog.getByAltText("Дополнительный ракурс 2")).toBeVisible();

  await dialog.getByLabel("Рост").fill("170");
  await dialog.getByLabel("Вес").fill("62");
  await dialog.getByRole("button", { name: "Создать →" }).click();
  await expect.poll(() => runCalls).toBe(1);
  expect(runPayload).toMatchObject({
    reference_asset_ids: ["asset-1", "asset-2", "asset-3", "asset-4"],
    height_cm: 170,
    weight_kg: 62,
    confirmed: true,
  });
});

test("Pinterest validates measurements before generation", async ({ page }) => {
  let uploadIndex = 0;
  let runCalls = 0;
  await page.route("**/api/v1/trends/upload", async (route) => {
    uploadIndex += 1;
    await route.fulfill({ json: { asset_id: `asset-${uploadIndex}`, url: `/uploads/${uploadIndex}.jpg`, kind: "image" } });
  });
  await page.route("**/api/v1/trends/0/pinterest-run", async (route) => {
    runCalls += 1;
    await route.fulfill({ status: 202, json: { ok: true, task: { id: 779, model: "nano-banana-pro", gen_type: "image", status: "pending" } } });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Сервисы" }).click();
  await page.getByRole("button", { name: /Pinterest/ }).first().click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: "Повтори фото с Pinterest" });

  await dialog.getByLabel("Загрузить референс Pinterest").setInputFiles({ name: "scene.jpg", mimeType: "image/jpeg", buffer: Buffer.from("scene") });
  await dialog.getByLabel("Загрузить ваше фото").setInputFiles({ name: "me.jpg", mimeType: "image/jpeg", buffer: Buffer.from("me") });
  await dialog.getByLabel("Рост").fill("119");
  await dialog.getByLabel("Вес").fill("251");

  await expect(dialog.getByText("Рост должен быть от 120 до 230 см.", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Вес должен быть от 30 до 250 кг.", { exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Создать →" })).toBeDisabled();
  expect(runCalls).toBe(0);
});
