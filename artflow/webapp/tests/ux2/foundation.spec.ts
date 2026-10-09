import { expect, test, type Page } from "@playwright/test";

async function prepare(page: Page, allowed = true, light = false, extra: { ownerId?: number; historyFails?: () => boolean } = {}) {
  await page.addInitScript(({ light }) => {
    (window as any).__back = null;
    window.Telegram = { WebApp: {
      initData: "ux2-fixture", initDataUnsafe: { user: { id: 123, first_name: "Tester" } },
      colorScheme: light ? "light" : "dark", ready() {}, expand() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
      BackButton: { show() {}, hide() {}, onClick(fn: () => void) { (window as any).__back = fn; }, offClick() {} },
      openLink() {}, openInvoice() {},
    }} as any;
  }, { light });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ contentType: "application/javascript", body: "" }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") throw new Error(`Unexpected write: ${path}`);
    if (path.endsWith("/auth/config")) return route.fulfill({ json: { bot_username: "test_bot" } });
    if (path === "/api/v1/me") return route.fulfill({ json: {
      id: extra.ownerId || 7, tg_id: 123, full_name: "Тестовый пользователь", credits: 120, language: "ru",
      miniapp_ux2_available: allowed,
    }});
    if (path === "/api/v1/models/image") return route.fulfill({ json: [{ key: "fixture-image", display_name: "Тестовая модель", modes: ["text", "image"], credits: 2, max_refs: 2, aspect_ratios: ["1:1", "9:16"], counts: [1], quality_options: [{ value: "basic", label: "Обычное" }] }] });
    if (path === "/api/v1/models/video") return route.fulfill({ json: [
      { key: "fixture-video", display_name: "Тестовое видео", modes: ["text", "image"], credits: 4, max_refs: 1, aspect_ratios: ["16:9", "9:16"], durations: [5], resolutions: ["720p"] },
      { key: "fixture-motion", display_name: "Тестовое движение", modes: ["motion"], credits: 4, max_refs: 1, supports_video_input: true, durations: [5], resolutions: ["720p"] },
    ] });
    if (path === "/api/v1/history" && extra.historyFails?.()) return route.fulfill({ status: 503, json: { detail: "History unavailable" } });
    if (path === "/api/v1/history") return route.fulfill({ json: [
      { id: 101, task_id: "fixture-101", model: "fixture-image", gen_type: "image", prompt: "Портрет", status: "done", created_at: "2026-10-09T10:00:00Z", result_urls: [] },
      { id: 102, task_id: "fixture-102", model: "fixture-video", gen_type: "video", status: "reconciliation_required", created_at: "2026-10-09T11:00:00Z" },
      { id: 103, task_id: "fixture-103", model: "fixture-image", gen_type: "image", status: "failed", created_at: "2026-10-09T09:00:00Z" },
    ] });
    if (path === "/api/v1/referrals") return route.fulfill({ json: {} });
    return route.fulfill({ json: [] });
  });
}

const labels = ["Лента", "Тренды", "Создать", "Работы", "Профиль"];

for (const width of [320, 360, 390, 430, 768]) {
  test(`admin preview has five visible destinations at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 320 ? 568 : 844 });
    await prepare(page);
    await page.goto("/?ux=2");
    const tabs = page.getByRole("tablist", { name: "Разделы Mini App" }).getByRole("tab");
    await expect(tabs).toHaveCount(5);
    for (const name of labels) {
      const tab = tabs.filter({ hasText: name });
      await expect(tab).toBeVisible();
      const box = await tab.boundingBox();
      expect(box && box.x >= 0 && box.x + box.width <= width).toBeTruthy();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    await expect(page.getByRole("tab", { name: "Лента", exact: true })).toHaveAttribute("aria-selected", "true");
  });
}

test("query cannot enable preview for an ordinary user", async ({ page }) => {
  await prepare(page, false);
  await page.goto("/?ux=2");
  await expect(page.getByRole("tablist").getByRole("tab")).toHaveCount(8);
});

test("existing UI remains default", async ({ page }) => {
  await prepare(page);
  await page.goto("/");
  await expect(page.getByRole("tablist").getByRole("tab")).toHaveCount(8);
});

async function openPhoto(page: Page) {
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: "Фото Создать или изменить изображение" }).click();
  await expect(page.getByRole("heading", { name: "Фото", exact: true })).toBeVisible();
}

for (const light of [false, true]) {
  test(`preview destinations and editor Back work in ${light ? "light" : "dark"} theme`, async ({ page }, testInfo) => {
    await prepare(page, true, light);
    await page.goto("/?ux=2");
    await page.getByRole("tab", { name: "Создать", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Что создадим?" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Создать", exact: true })).toHaveAttribute("aria-selected", "true");
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`create-${light ? "light" : "dark"}.png`) });
    await openPhoto(page);
    await page.evaluate(() => (window as any).__back?.());
    await expect(page.getByRole("heading", { name: "Что создадим?" })).toBeVisible();
    for (const [button, heading] of [["Видео Из описания или ваших материалов", "Видео"], ["Перенести движение Фото персонажа и видео движения", "Motion"], ["Инструменты Помощник, промпты и музыка", null]]) {
      await page.getByRole("button", { name: button! }).click();
      if (heading) await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
      await page.locator("[data-apix-editor-back]").click();
    }
    await page.getByRole("tab", { name: "Тренды", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Тренды", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Работы", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Мои работы" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Работы", exact: true })).toHaveAttribute("aria-selected", "true");
    await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`works-${light ? "light" : "dark"}.png`) });
    await page.getByRole("tab", { name: "Профиль", exact: true }).click();
    await page.getByRole("button", { name: "Настройки", exact: true }).click();
    await expect(page.getByRole("button", { name: "Вернуть обычный интерфейс" })).toBeVisible();
    await page.getByRole("button", { name: "Вернуть обычный интерфейс" }).click();
    await expect(page.getByRole("tablist").getByRole("tab")).toHaveCount(8);
  });
}

test("ordinary prompt and format survive navigation and reload", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=2");
  await openPhoto(page);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Сохранить мой портрет и параметры");
  await page.getByRole("button", { name: "9:16", exact: true }).click();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("apix:ux2:drafts:v1:7"))).toContain("Сохранить мой портрет");
  await page.getByRole("tab", { name: "Работы", exact: true }).click();
  await page.reload();
  await openPhoto(page);
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Сохранить мой портрет и параметры");
  const state = await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:ux2:drafts:v1:7")!));
  expect(state.drafts.image.aspectRatio).toBe("9:16");
});

test("works distinguish provider review from failure without percentages", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=2");
  await page.getByRole("tab", { name: "Работы", exact: true }).click();
  await expect(page.locator(".ux2-work-tile")).toHaveCount(3);
  await page.getByRole("button", { name: "В работе", exact: true }).click();
  await expect(page.locator(".ux2-work-tile")).toHaveCount(1);
  await expect(page.locator(".ux2-work-tile")).toContainText("Уточняем статус у поставщика");
  await expect(page.locator(".ux2-work-tile")).not.toContainText("%");
  await page.getByRole("button", { name: "Ошибки", exact: true }).click();
  await expect(page.locator(".ux2-work-tile")).toHaveCount(1);
  await expect(page.locator(".ux2-work-tile")).toContainText("Ошибка");
});


test("history failure is not an empty library and refreshing recovers", async ({ page }) => {
  let fails = true;
  await prepare(page, true, false, { historyFails: () => fails });
  await page.goto("/?ux=2");
  await page.getByRole("tab", { name: "Работы", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Не удалось загрузить историю");
  fails = false;
  await page.getByRole("button", { name: "Обновить работы" }).click();
  await expect(page.locator(".ux2-work-tile")).toHaveCount(3);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("signing into another account cannot restore the previous draft", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=2");
  await openPhoto(page);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Draft for account seven");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("apix:ux2:drafts:v1:7"))).toContain("Draft for account seven");
  await page.unroute("**/api/**");
  await prepare(page, true, false, { ownerId: 8 });
  await page.reload();
  await openPhoto(page);
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("");
});

test("preview can be enabled from settings without a special URL", async ({ page }) => {
  await prepare(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "Настройки", exact: true }).click();
  await page.getByRole("button", { name: "Открыть предпросмотр" }).click();
  await expect(page.getByRole("tablist").getByRole("tab")).toHaveCount(5);
  await page.reload();
  await expect(page.getByRole("tablist").getByRole("tab")).toHaveCount(5);
});


test("uploaded reference survives reload without uploading twice", async ({ page }) => {
  await prepare(page);
  let uploads = 0;
  await page.route("**/api/web/upload-media", route => {
    uploads += 1;
    return route.fulfill({ json: { data: { url: "https://media.example.test/reference.png", kind: "image", content_type: "image/png", size: 68 } } });
  });
  await page.goto("/?ux=2");
  await openPhoto(page);
  await page.locator('input[type="file"][accept="image/*"]').setInputFiles({
    name: "reference.png", mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64"),
  });
  await expect(page.getByText("reference.png", { exact: true })).toBeVisible();
  await page.reload();
  await openPhoto(page);
  await expect(page.getByText("reference.png", { exact: true })).toBeVisible();
  expect(uploads).toBe(1);
});

test("opening and closing balance preserves the ordinary draft", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=2");
  await openPhoto(page);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Keep this description after balance");
  await page.getByRole("button", { name: "Открыть баланс" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Keep this description after balance");
});

for (const width of [320, 430]) {
  test(`create and works do not overflow horizontally at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 568 });
    await prepare(page);
    await page.goto("/?ux=2");
    for (const name of ["Создать", "Работы"]) {
      await page.getByRole("tab", { name, exact: true }).click();
      await expect(page.locator(".ux2-page")).toBeVisible();
      await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute("aria-selected", "true");
      const sizes = await page.locator(".apix-shell > main").evaluate(node => ({ viewport: node.clientWidth, content: node.scrollWidth }));
      expect(sizes.content).toBeLessThanOrEqual(sizes.viewport);
      await page.screenshot({ animations: "disabled", path: testInfo.outputPath(`${width}-${name === "Создать" ? "create" : "works"}.png`) });
    }
  });
}


test("a saved draft does not silently use changed model capabilities", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=2");
  await openPhoto(page);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Keep my idea when options change");
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem("apix:ux2:drafts:v1:7"))).toContain("Keep my idea");
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [{
    key: "fixture-image", display_name: "Тестовая модель", modes: ["text"], credits: 3,
    max_refs: 2, aspect_ratios: ["1:1"], counts: [1], quality_options: [{ value: "new-quality", label: "Новое качество" }],
  }] }));
  await page.reload();
  await openPhoto(page);
  await expect(page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Обновить параметры" })).toBeVisible();
  await page.getByRole("button", { name: "Обновить параметры" }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Keep my idea when options change");
  await expect(page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true })).toBeEnabled();
});


for (const [kind, extension, tag] of [["video", "mp4", "video"], ["music", "mp3", "audio"]]) {
  test(`works open original ${kind} media rather than its thumbnail`, async ({ page }) => {
    await prepare(page);
    const original = `https://media.example.test/result.${extension}`;
    await page.route("**/api/v1/history**", route => route.fulfill({ json: [{
      id: 201, task_id: "fixture-result", model: "fixture-video", gen_type: kind, status: "done",
      created_at: "2026-10-09T10:00:00Z", result_url: original, preview_url: "https://media.example.test/cover.jpg",
    }] }));
    await page.goto("/?ux=2");
    await page.getByRole("tab", { name: "Работы", exact: true }).click();
    await page.locator(".ux2-work-tile").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.locator(tag)).toHaveAttribute("src", original);
    await expect(dialog.locator(tag)).toHaveAttribute("controls", "");
  });
}


test("short screen keeps balance visible and the active destination unambiguous", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await prepare(page);
  await page.goto("/?ux=2");
  for (const name of ["Создать", "Работы", "Профиль"]) {
    await page.getByRole("tab", { name, exact: true }).click();
    await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('[role="tab"][aria-selected="true"]')).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Открыть баланс" })).toBeVisible();
  }
});
