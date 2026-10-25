import { expect, test, type Page } from "@playwright/test";

const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jH1sAAAAASUVORK5CYII=", "base64");
const photo = { key: "fixture-photo", display_name: "Фото из каталога", credits: 5, modes: ["text", "image"], max_refs: 2, aspect_ratios: ["1:1", "9:16"], counts: [1, 2], quality_options: [{ value: "basic", label: "Обычное" }, { value: "high", label: "Высокое" }] };
const active = { id: 21, model: "fixture-photo", mode: "image", quality: "basic", count: 1, prompt_hidden: true, base_prompt: "DO_NOT_COPY", reference_urls: ["https://media.example.test/private.png"] };

async function prepare(page: Page, previous: unknown = null) {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  let mineReads = 0;
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: "consumer-fixture", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } as any; });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (method !== "GET") writes.push({ path, body: route.request().headers()["content-type"]?.includes("application/json") ? route.request().postDataJSON() : {} });
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Тест", credits: 120, language: "ru", miniapp_ux2_available: true });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/models/image")) return json([photo, { ...photo, key: "text-only", display_name: "Только текст", modes: ["text"], max_refs: 0, counts: [1], quality_options: [], aspect_ratios: [] }]);
    if (path.endsWith("/models/video")) return json([{ ...photo, key: "fixture-video", display_name: "Видео из каталога" }]);
    if (path.endsWith("/models/music")) return json([{ key: "fixture-music", display_name: "Музыка из каталога", credits: 10, modes: ["text"] }]);
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path.endsWith("/image-sessions/active")) return json({ data: previous });
    if (path === "/api/web/image-sessions" && method === "POST") return json({ data: { id: 22, ...route.request().postDataJSON() } });
    if (path === "/api/web/upload-media") return json({ data: { url: "https://media.example.test/cover.png", kind: "image", content_type: "image/png" } });
    if (path.endsWith("/prompts/my")) { mineReads++; return json({ items: [{ id: 51, title: "Моя новая публикация", status: "pending" }], total: 1 }); }
    if (path === "/api/web/prompts" && method === "POST") return json({ data: { id: 51, status: "pending", ...route.request().postDataJSON() } });
    if (path.endsWith("/prompts")) return json({ items: [], total: 0 });
    if (path.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    return json([]);
  });
  return { writes, mineReads: () => mineReads };
}

async function publication(page: Page) {
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  await page.getByRole("button", { name: "Добавить промпт", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill("Моя новая публикация");
  await page.getByLabel("Задание", { exact: true }).fill("Портрет в мягком свете из моего описания");
}

test("advanced publication sends current model tags and uploaded cover via web DTO and refreshes own list", async ({ page }) => {
  const state = await prepare(page); await publication(page);
  await page.getByLabel("Модель публикации", { exact: true }).selectOption("fixture-video");
  await page.getByLabel("Теги через запятую", { exact: true }).fill(" портрет, свет, портрет ");
  await page.getByLabel("Обложка публикации", { exact: true }).setInputFiles({ name: "cover.png", mimeType: "image/png", buffer: png });
  await expect(page.getByText("Обложка загружена", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Отправить на проверку", exact: true })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Я понимаю/ }).check();
  await page.getByRole("button", { name: "Отправить на проверку", exact: true }).click();
  await expect(page.getByRole("button", { name: /Моя новая публикация/ })).toBeVisible();
  expect(state.writes.filter(row => row.path === "/api/web/prompts").map(row => row.body)).toEqual([{ title: "Моя новая публикация", description: "", prompt_text: "Портрет в мягком свете из моего описания", model: "fixture-video", tags: ["портрет", "свет"], preview_url: "https://media.example.test/cover.png" }]);
  expect(state.writes.some(row => row.path === "/api/v1/prompts")).toBe(false);
  expect(state.mineReads()).toBeGreaterThan(0);
});

for (const failure of ["invalid-file", "upload-error", "unsafe-url", "non-image"] as const) {
  test(`publication blocks ${failure} until cover is explicitly removed`, async ({ page }) => {
    const state = await prepare(page);
    if (failure !== "invalid-file") await page.route("**/api/web/upload-media", route => {
      state.writes.push({ path: "/api/web/upload-media", body: {} });
      return failure === "upload-error" ? route.fulfill({ status: 422, json: { error: { message: "Файл не принят" } } }) : route.fulfill({ json: { data: { url: failure === "unsafe-url" ? "javascript:alert(1)" : "https://media.example.test/audio.mp3", kind: failure === "non-image" ? "audio" : "image" } } });
    });
    await publication(page); await page.getByRole("checkbox", { name: /Я понимаю/ }).check();
    await page.getByLabel("Обложка публикации", { exact: true }).setInputFiles({ name: failure === "invalid-file" ? "bad.txt" : "cover.png", mimeType: failure === "invalid-file" ? "text/plain" : "image/png", buffer: png });
    await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: "Отправить на проверку", exact: true })).toBeDisabled();
    expect(state.writes.filter(row => row.path === "/api/web/prompts")).toHaveLength(0);
    if (failure === "invalid-file") expect(state.writes.filter(row => row.path === "/api/web/upload-media")).toHaveLength(0);
    await page.getByRole("button", { name: "Убрать обложку", exact: true }).click();
    await expect(page.getByRole("button", { name: "Отправить на проверку", exact: true })).toBeEnabled();
  });
}

test("Projects creates catalog-configured series with own references without generation or draft overwrite", async ({ page }, testInfo) => {
  const state = await prepare(page);
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Мой существующий черновик");
  await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  const form = page.getByRole("dialog");
  await expect(form).toContainText("Генерация не запускается");
  await form.getByLabel("Модель серии", { exact: true }).selectOption("fixture-photo");
  await form.getByLabel("Режим серии", { exact: true }).selectOption("image");
  await form.getByLabel("Формат серии", { exact: true }).selectOption("9:16");
  await form.getByLabel("Качество серии", { exact: true }).selectOption("high");
  await form.getByLabel("Количество фото в серии", { exact: true }).selectOption("2");
  await form.getByLabel("Описание серии (необязательно)", { exact: true }).fill("Моё собственное описание");
  await form.getByLabel("Исходные фото серии", { exact: true }).setInputFiles({ name: "reference.png", mimeType: "image/png", buffer: png });
  await expect(form.getByText("Загружено фото: 1")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("series-dialog.png"), fullPage: true });
  await form.getByRole("button", { name: "Сохранить серию", exact: true }).click();
  await expect(page.getByText("Серия создана", { exact: true })).toBeVisible();
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions").map(row => row.body)).toEqual([{ model: "fixture-photo", mode: "image", aspect_ratio: "9:16", quality: "high", count: 2, base_prompt: "Моё собственное описание", reference_urls: ["https://media.example.test/cover.png"] }]);
  expect(state.writes.some(row => /generate|generation|\/image$/.test(row.path))).toBe(false);
  await expect(page.getByRole("tab", { name: "Проекты", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: /Создать фото/ }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Мой существующий черновик");
});

test("replacing previous active series is explicit and never copies protected recipe", async ({ page }) => {
  const state = await prepare(page, active);
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  await expect(page.getByLabel("Описание серии (необязательно)", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "Сохранить серию", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Заменить активную серию?", exact: true })).toBeVisible();
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions")).toHaveLength(0);
  await page.getByRole("button", { name: "Заменить серию", exact: true }).click();
  await expect.poll(() => state.writes.filter(row => row.path === "/api/web/image-sessions").length).toBe(1);
  const payload = state.writes.find(row => row.path === "/api/web/image-sessions")!.body;
  expect(payload.base_prompt).toBeNull(); expect(payload.reference_urls).toEqual([]);
  expect(JSON.stringify(payload)).not.toContain("DO_NOT_COPY");
});

test("home thumbnails remove failed network and non-image media while preserving usable cards", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [{ id: 1, gen_type: "image", preview_url: "https://media.example.test/broken.png" }] }));
  await page.route("**/api/v1/trends?**", route => route.fulfill({ json: [{ id: 2, kind: "video", title: "Сценарий", preview_url: "https://media.example.test/not-image" }] }));
  let requests = 0;
  await page.route("https://media.example.test/**", route => { requests++; return route.request().url().includes("broken") ? route.abort() : route.fulfill({ contentType: "text/html", body: "not an image" }); });
  await page.goto("/?ux=3");
  await expect(page.getByRole("button", { name: "Создать фото", exact: true })).toBeVisible();
  await expect(page.locator(".lilac-home img")).toHaveCount(0);
  expect(requests).toBeGreaterThan(0); expect(requests).toBeLessThanOrEqual(3);
  await expect(page.getByRole("button", { name: "Создать фото", exact: true }).locator("svg")).not.toHaveCount(0);
  await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Фото", exact: true })).toBeVisible();
});

test("publication rejects an invalid manual cover address instead of resolving it as a local path", async ({ page }) => {
  const state = await prepare(page); await publication(page);
  await page.getByRole("checkbox", { name: /Я понимаю/ }).check();
  await page.getByLabel("Ссылка на обложку (необязательно)", { exact: true }).fill("not-a-url");
  await expect(page.getByRole("button", { name: "Отправить на проверку", exact: true })).toBeDisabled();
  expect(state.writes.filter(row => row.path === "/api/web/prompts")).toHaveLength(0);
});

test("closing an uploading publication discards its late response and keeps the next form empty", async ({ page }) => {
  await prepare(page); let uploads = 0, completed = false;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/web/upload-media", async route => { uploads++; await pending; await route.fulfill({ json: { data: { url: "https://media.example.test/old-cover.png", kind: "image" } } }).catch(() => {}); completed = true; });
  await publication(page);
  await page.getByLabel("Обложка публикации", { exact: true }).setInputFiles({ name: "cover.png", mimeType: "image/png", buffer: png });
  await expect.poll(() => uploads).toBe(1);
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Добавить промпт", exact: true }).click();
  release(); await expect.poll(() => completed).toBe(true);
  await expect(page.getByLabel("Ссылка на обложку (необязательно)", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Название", { exact: true })).toHaveValue("");
});

test("publication checks current catalog and never posts a removed model", async ({ page }) => {
  const state = await prepare(page); await publication(page);
  await expect(page.getByLabel("Модель публикации", { exact: true })).toHaveValue("fixture-photo");
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [] }));
  await page.getByRole("checkbox", { name: /Я понимаю/ }).check();
  await page.getByRole("button", { name: "Отправить на проверку", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Модель больше недоступна");
  expect(state.writes.filter(row => row.path === "/api/web/prompts")).toHaveLength(0);
});

test("publication duplicate DOM activation produces one write", async ({ page }) => {
  const state = await prepare(page); await publication(page);
  await page.getByRole("checkbox", { name: /Я понимаю/ }).check();
  await page.getByRole("button", { name: "Отправить на проверку", exact: true }).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  await expect(page.getByRole("button", { name: /Моя новая публикация/ })).toBeVisible();
  expect(state.writes.filter(row => row.path === "/api/web/prompts")).toHaveLength(1);
});

test("replacement detects a changed active series and never overwrites it", async ({ page }) => {
  const state = await prepare(page, active); let latest = active;
  await page.route("**/api/web/image-sessions/active", route => route.fulfill({ json: { data: latest } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  await page.getByRole("button", { name: "Сохранить серию", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Заменить активную серию?", exact: true })).toBeVisible();
  latest = { ...active, count: 2 };
  await page.getByRole("button", { name: "Заменить серию", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Активная серия изменилась");
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions")).toHaveLength(0);
});

test("closing replacement confirmation aborts its pending check before any create write", async ({ page }) => {
  const state = await prepare(page, active); let reads = 0;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/web/image-sessions/active", async route => { reads++; if (reads === 3) await pending; await route.fulfill({ json: { data: active } }).catch(() => {}); });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  await page.getByRole("button", { name: "Сохранить серию", exact: true }).click();
  await page.getByRole("button", { name: "Заменить серию", exact: true }).click();
  await expect.poll(() => reads).toBe(3);
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  release();
  await expect(page.getByRole("dialog", { name: "Создать серию фото", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Сохранить серию", exact: true })).toBeEnabled();
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions")).toHaveLength(0);
});

test("publication authorization loss blocks repeat sends and never claims success", async ({ page }) => {
  const state = await prepare(page);
  await page.route("**/api/web/prompts", route => { state.writes.push({ path: "/api/web/prompts", body: route.request().postDataJSON() }); return route.fulfill({ status: 403, json: { error: { message: "Доступ закрыт" } } }); });
  await publication(page); await page.getByRole("checkbox", { name: /Я понимаю/ }).check();
  await page.getByRole("button", { name: "Отправить на проверку", exact: true }).click();
  await expect(page.getByRole("dialog").getByText("Доступ закрыт", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Отправить на проверку", exact: true })).toBeDisabled();
  expect(state.writes.filter(row => row.path === "/api/web/prompts")).toHaveLength(1);
  await expect(page.getByText("Промпт отправлен на проверку", { exact: true })).toHaveCount(0);
});

test("series preserves uploaded inputs when switching to an incompatible model and blocks save", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  await page.getByLabel("Исходные фото серии", { exact: true }).setInputFiles({ name: "reference.png", mimeType: "image/png", buffer: png });
  await expect(page.getByText("Загружено фото: 1")).toBeVisible();
  await page.getByLabel("Модель серии", { exact: true }).selectOption("text-only");
  await expect(page.getByText("Загружено фото: 1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Сохранить серию", exact: true })).toBeDisabled();
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions")).toHaveLength(0);
  await page.getByRole("button", { name: "Убрать исходные фото", exact: true }).click();
  await expect(page.getByRole("button", { name: "Сохранить серию", exact: true })).toBeEnabled();
});

test("consumer forms fit 320px and keep controls at least 44px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 }); await prepare(page); await publication(page);
  await expect(page.getByLabel("Модель публикации", { exact: true })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  for (const control of await page.locator('.lilac-consumer-form button, .lilac-consumer-form select, .lilac-consumer-form input:not([type="checkbox"])').all()) {
    expect((await control.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }
});
