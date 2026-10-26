import { expect, test, type Page } from "@playwright/test";

const categories = {
  items: [
    { key: "portrait", title: "Портреты и образы", sort_order: 0, trend_count: 7, preview_items: [
      { id: 11, kind: "image", title: "Неоновый портрет", description: "Мягкий свет", preview_url: "https://media.example.test/11.png", category: "portrait", category_title: "Портреты и образы" },
      { id: 12, kind: "video", title: "Оживший портрет", description: "Плавное движение", preview_url: "https://media.example.test/12.mp4", category: "portrait", category_title: "Портреты и образы" },
      { id: 13, kind: "image", title: "Обложка журнала", preview_url: "https://media.example.test/broken.png", category: "portrait", category_title: "Портреты и образы" },
    ] },
    { key: "animals", title: "С животными 🐾", sort_order: 1, trend_count: 1, preview_items: [
      { id: 21, kind: "image", title: "С медведем", preview_url: "https://media.example.test/21.png", category: "animals", category_title: "С животными 🐾" },
    ] },
  ],
  has_more: false,
  next_cursor: null,
};

async function prepare(page: Page, admin = true) {
  const writes: Array<{ path: string; body: any }> = [];
  let folderPage = 0;
  let revision = 3;
  let adminItems = categories.items.map(({ preview_items: _preview, ...item }) => ({ ...item, is_visible: true, published_count: item.trend_count }));
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: "category-fixture", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, requestFullscreen() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("https://media.example.test/**", route => {
    if (route.request().url().includes("broken")) return route.abort("failed");
    return route.fulfill({ contentType: route.request().url().endsWith(".mp4") ? "video/mp4" : "image/png", body: Buffer.from("fixture") });
  });
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const body = method === "GET" ? null : route.request().postDataJSON();
    if (method !== "GET") writes.push({ path, body });
    const json = (value: unknown, status = 200) => route.fulfill({ status, json: value });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Администратор", credits: 120, language: "ru", miniapp_ux2_available: admin });
    if (path.endsWith("/me/permissions")) return json({ is_admin: admin });
    if (path.endsWith("/studio/preview")) return admin ? json({ allowed: true, ui_version: 3 }) : json({ detail: "Admin access required" }, 403);
    if (path.endsWith("/models/image") || path.endsWith("/models/video") || path.endsWith("/models/music") || path.endsWith("/history") || path.endsWith("/plans") || path.endsWith("/payment-methods") || path.endsWith("/prompts") || path.endsWith("/prompts/my")) return json([]);
    if (path.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    if (path === "/api/v1/trends") return json([]);
    if (path === "/api/v1/trend-categories") return json(categories);
    if (path === "/api/v1/trend-categories/portrait/trends") {
      folderPage += 1;
      return folderPage === 1
        ? json({ category: { key: "portrait", title: "Портреты и образы", sort_order: 0 }, items: categories.items[0].preview_items, has_more: true, next_cursor: "next" })
        : json({ category: { key: "portrait", title: "Портреты и образы", sort_order: 0 }, items: [{ id: 14, kind: "image", title: "Новый портрет", preview_url: "https://media.example.test/14.png" }], has_more: false, next_cursor: null });
    }
    if (path === "/api/v1/trends/11/link") return json({ link: "https://t.me/fixture_bot?start=trend_11" });
    if (path === "/api/v1/admin/trends/11/update") return json(categories.items[0].preview_items[0]);
    if (path === "/api/v1/admin/trend-categories" && method === "GET") return json({ revision, items: adminItems });
    if (path === "/api/v1/admin/trend-categories" && method === "POST") {
      revision += 1;
      const created = { key: "cat_newfixture", title: body.title, sort_order: adminItems.length, is_visible: true, trend_count: 0, published_count: 0 };
      adminItems = [...adminItems, created];
      return json({ revision, category: created }, 201);
    }
    if (/\/api\/v1\/admin\/trend-categories\/[^/]+\/update$/.test(path)) {
      revision += 1;
      const key = path.split("/").at(-2)!;
      adminItems = adminItems.map(item => item.key === key ? { ...item, ...body } : item);
      return json({ revision, category: adminItems.find(item => item.key === key) });
    }
    return json([]);
  });
  return writes;
}

test("black lilac trends are live category shelves with a full folder", async ({ page }, info) => {
  await prepare(page);
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "По шаблону", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Тренды по категориям" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Портреты и образы" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Смотреть все: Портреты и образы" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Повторить: Неоновый портрет/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Скопировать ссылку: Неоновый портрет" })).toBeVisible();
  await expect(page.getByText("Все категории", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Видео", exact: true }).click();
  await expect(page.getByRole("heading", { name: "С животными 🐾" })).toBeVisible();
  await expect(page.getByRole("button", { name: "В первых примерах нет этого формата — открыть всю папку" })).toBeVisible();
  await page.getByRole("button", { name: "Все", exact: true }).click();
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`trend-shelves-${width}.png`), fullPage: true });
  }
  await page.getByRole("button", { name: "Смотреть все: Портреты и образы" }).click();
  await expect(page.getByRole("heading", { name: "Портреты и образы" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Назад к категориям" })).toBeVisible();
  await page.getByRole("button", { name: "Показать ещё" }).click();
  await expect(page.getByText("Новый портрет", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Показать ещё" })).toHaveCount(0);
});

test("admin manages categories while ordinary users never see controls", async ({ page, browser }) => {
  const writes = await prepare(page, true);
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "По шаблону", exact: true }).click();
  await page.getByRole("button", { name: "Управление категориями" }).click();
  await expect(page.getByRole("heading", { name: "Категории трендов" })).toBeVisible();
  await page.getByLabel("Название новой категории").fill("Кинообразы");
  await page.getByRole("button", { name: "Создать категорию" }).click();
  await expect(page.getByLabel("Название Кинообразы")).toHaveValue("Кинообразы");
  await expect(page.getByRole("option", { name: "Кинообразы", exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: "Добавить тренд" }).click();
  await expect(page.getByRole("option", { name: "Кинообразы", exact: true })).toHaveCount(2);
  await page.getByRole("button", { name: "Закрыть форму" }).click();
  await page.getByRole("button", { name: "Поля", exact: true }).first().click();
  await expect(page.getByRole("button", { name: "Сохранить поля" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Скрыть Портреты и образы" }).click();
  await page.getByRole("button", { name: "Подтвердить скрытие" }).click();
  expect(writes.some(row => row.path === "/api/v1/admin/trend-categories" && row.body.expected_revision === 3)).toBe(true);
  expect(writes.some(row => row.path.endsWith("/portrait/update") && row.body.confirm_populated === true)).toBe(true);

  const ordinaryContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const ordinary = await ordinaryContext.newPage();
  await prepare(ordinary, false);
  await ordinary.goto("/");
  await ordinary.getByRole("button", { name: "Тренды", exact: true }).click();
  await expect(ordinary.getByRole("button", { name: "Управление категориями" })).toHaveCount(0);
  await ordinaryContext.close();
});
