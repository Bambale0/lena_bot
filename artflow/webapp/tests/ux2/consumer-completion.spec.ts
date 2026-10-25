import { expect, test, type Page } from "@playwright/test";

const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jH1sAAAAASUVORK5CYII=", "base64");
const mp4 = Buffer.from([
  "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAAIZnJlZQAABGhtZGF0AAACrgYF//+q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NCBy",
  "MzEwOCAzMWUxOWY5IC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyMyAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQu",
  "aHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9",
  "MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0",
  "X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTYgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9",
  "MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9",
  "MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTI1IHNjZW5lY3V0PTQwIGludHJhX3JlZnJl",
  "c2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRp",
  "bz0xLjQwIGFxPTE6MS4wMACAAAAAOWWIhAA7//7jq/gU2W9cdBenIlU7RjT88Ul2zyEzccsFUPz6rlbvBltktL8gDIAAXkH+1zT0gGlqgQAAAAxBmiRsQ7/+",
  "qZYAFNAAAAAJQZ5CeIX/ABixAAAACQGeYXRCvwAg4AAAAAkBnmNqQr8AIOEAAAASQZpoSahBaJlMCHf//qmWABTRAAAAC0GehkURLC//ABixAAAACQGepXRC",
  "vwAg4QAAAAkBnqdqQr8AIOAAAAASQZqsSahBbJlMCHf//qmWABTQAAAAC0GeykUVLC//ABixAAAACQGe6XRCvwAg4AAAAAkBnutqQr8AIOAAAAASQZrwSahB",
  "bJlMCG///qeEACkhAAAAC0GfDkUVLC//ABixAAAACQGfLXRCvwAg4QAAAAkBny9qQr8AIOAAAAASQZs0SahBbJlMCGf//p4QAKCAAAAAC0GfUkUVLC//ABix",
  "AAAACQGfcXRCvwAg4AAAAAkBn3NqQr8AIOAAAAARQZt4SahBbJlMCFf//jhAAm8AAAALQZ+WRRUsL/8AGLAAAAAJAZ+1dEK/ACDhAAAACQGft2pCvwAg4QAA",
  "BGZtb292AAAAbG12aGQAAAAAAAAAAAAAAAAAAAPoAAAD6AABAAABAAAAAAAAAAAAAAAAAQAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAAAAA",
  "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACAAADkHRyYWsAAABcdGtoZAAAAAMAAAAAAAAAAAAAAAEAAAAAAAAD6AAAAAAAAAAAAAAAAAAAAAAAAQAAAAAAAAAA",
  "AAAAAAAAAAEAAAAAAAAAAAAAAAAAAEAAAAAAoAAAAPAAAAAAACRlZHRzAAAAHGVsc3QAAAAAAAAAAQAAA+gAAAQAAAEAAAAAAwhtZGlhAAAAIG1kaGQAAAAA",
  "AAAAAAAAAAAAADIAAAAyAFXEAAAAAAAtaGRscgAAAAAAAAAAdmlkZQAAAAAAAAAAAAAAAFZpZGVvSGFuZGxlcgAAAAKzbWluZgAAABR2bWhkAAAAAQAAAAAA",
  "AAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAACc3N0YmwAAAC/c3RzZAAAAAAAAAABAAAAr2F2YzEAAAAAAAAAAQAAAAAAAAAAAAAA",
  "AAAAAAAAoADwAEgAAABIAAAAAAAAAAEVTGF2YzYwLjMxLjEwMiBsaWJ4MjY0AAAAAAAAAAAAAAAY//8AAAA1YXZjQwFkAAz/4QAYZ2QADKzZQofsBEAAAAMA",
  "QAAADIPFCmWAAQAGaOvjyyLA/fj4AAAAABBwYXNwAAAAAQAAAAEAAAAUYnRydAAAAAAAACMAAAAjAAAAABhzdHRzAAAAAAAAAAEAAAAZAAACAAAAABRzdHNz",
  "AAAAAAAAAAEAAAABAAAA2GN0dHMAAAAAAAAAGQAAAAEAAAQAAAAAAQAACgAAAAABAAAEAAAAAAEAAAAAAAAAAQAAAgAAAAABAAAKAAAAAAEAAAQAAAAAAQAA",
  "AAAAAAABAAACAAAAAAEAAAoAAAAAAQAABAAAAAABAAAAAAAAAAEAAAIAAAAAAQAACgAAAAABAAAEAAAAAAEAAAAAAAAAAQAAAgAAAAABAAAKAAAAAAEAAAQA",
  "AAAAAQAAAAAAAAABAAACAAAAAAEAAAoAAAAAAQAABAAAAAABAAAAAAAAAAEAAAIAAAAAHHN0c2MAAAAAAAAAAQAAAAEAAAAZAAAAAQAAAHhzdHN6AAAAAAAA",
  "AAAAAAAZAAAC7wAAABAAAAANAAAADQAAAA0AAAAWAAAADwAAAA0AAAANAAAAFgAAAA8AAAANAAAADQAAABYAAAAPAAAADQAAAA0AAAAWAAAADwAAAA0AAAAN",
  "AAAAFQAAAA8AAAANAAAADQAAABRzdGNvAAAAAAAAAAEAAAAwAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAA",
  "AAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExhdmY2MC4xNi4xMDA=",
].join(""), "base64");
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
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
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
  await expect(page.getByRole("tab", { name: "Профиль", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: /Создать фото/ }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Мой существующий черновик");
});

test("replacing previous active series is explicit and never copies protected recipe", async ({ page }) => {
  const state = await prepare(page, active);
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
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
  await page.locator(".lilac-preview-rail > button").first().scrollIntoViewIfNeeded();
  await expect(page.locator(".lilac-home :is(img, video)")).toHaveCount(0);
  expect(requests).toBeGreaterThan(0); expect(requests).toBeLessThanOrEqual(4);
  await expect(page.getByRole("button", { name: "Создать фото", exact: true }).locator("svg")).not.toHaveCount(0);
  await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Фото", exact: true })).toBeVisible();
});

test("home renders live MP4 previews without starting generation", async ({ page }) => {
  const state = await prepare(page);
  await page.route("**/api/v1/trends?**", route => route.fulfill({ json: [{
    id: 202,
    kind: "video",
    title: "Живой сценарий",
    description: "Видео-пример",
    preview_url: "https://media.example.test/live.mp4",
    model: "fixture-video",
    settings: {},
  }] }));
  await page.route("https://media.example.test/live.mp4", route => route.fulfill({ contentType: "video/mp4", body: mp4 }));
  await page.goto("/?ux=3");

  const tileFrame = page.getByRole("button", { name: "Оживить фото", exact: true }).locator("[data-apix-home-preview-frame]");
  const trendCard = page.locator(".lilac-preview-rail > button").filter({ hasText: "Живой сценарий" });
  const railFrame = trendCard.locator("[data-apix-home-preview-frame]");
  for (const frame of [tileFrame, railFrame]) {
    await frame.scrollIntoViewIfNeeded();
    const video = frame.locator("video");
    await expect(video).toBeVisible();
    await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState)).toBeGreaterThanOrEqual(1);
    expect(await video.evaluate((element: HTMLVideoElement) => ({
      autoPlay: element.autoplay,
      controls: element.controls,
      loop: element.loop,
      muted: element.muted,
      playsInline: element.playsInline,
      preload: element.getAttribute("preload"),
      videoWidth: element.videoWidth,
    }))).toEqual({ autoPlay: true, controls: false, loop: true, muted: true, playsInline: true, preload: "metadata", videoWidth: 160 });
    await expect.poll(() => video.evaluate((element: HTMLVideoElement) => ({
      currentTime: element.currentTime,
      ended: element.ended,
      paused: element.paused,
      stabilizerActive: element.dataset.apixPreviewActive || null,
    }))).toMatchObject({ ended: false, paused: false, stabilizerActive: null });
  }

  await trendCard.click();
  await expect(page.getByRole("dialog", { name: "Живой сценарий" })).toBeVisible();
  expect(state.writes.filter(row => /generate|\/run$/.test(row.path))).toHaveLength(0);
});

test("home video previews honor reduced motion and react to preference changes", async ({ page }) => {
  await prepare(page);
  await page.addInitScript(() => {
    const originalPlay = HTMLMediaElement.prototype.play;
    let playCalls = 0;
    Object.defineProperty(window, "__homePreviewPlayCalls", { get: () => playCalls });
    HTMLMediaElement.prototype.play = function play() {
      playCalls++;
      return originalPlay.call(this);
    };
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/v1/trends?**", route => route.fulfill({ json: [{
    id: 203, kind: "video", title: "Спокойный сценарий", preview_url: "https://media.example.test/reduced.mp4",
  }] }));
  await page.route("https://media.example.test/reduced.mp4", route => route.fulfill({ contentType: "video/mp4", body: mp4 }));
  await page.goto("/?ux=3");

  const tileFrame = page.getByRole("button", { name: "Оживить фото", exact: true }).locator("[data-apix-home-preview-frame]");
  const railFrame = page.locator(".lilac-preview-rail [data-apix-home-preview-frame]").first();
  await tileFrame.scrollIntoViewIfNeeded();
  await expect(tileFrame.locator("video")).toHaveCount(1);
  expect(await tileFrame.locator("video").evaluate((video: HTMLVideoElement) => ({ paused: video.paused, autoPlay: video.autoplay }))).toEqual({ paused: true, autoPlay: false });
  await railFrame.scrollIntoViewIfNeeded();
  await expect(railFrame.locator("video")).toHaveCount(1);
  expect(await railFrame.locator("video").evaluate((video: HTMLVideoElement) => ({ paused: video.paused, autoPlay: video.autoplay }))).toEqual({ paused: true, autoPlay: false });
  expect(await page.evaluate(() => (window as unknown as { __homePreviewPlayCalls: number }).__homePreviewPlayCalls)).toBe(0);
  expect(await railFrame.locator("video").evaluate((video: HTMLVideoElement) => !video.dataset.apixPreviewActive)).toBe(true);

  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect.poll(() => railFrame.locator("video").evaluate((video: HTMLVideoElement) => !video.paused)).toBe(true);
  await expect.poll(() => page.evaluate(() => (window as unknown as { __homePreviewPlayCalls: number }).__homePreviewPlayCalls)).toBeGreaterThan(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect.poll(() => railFrame.locator("video").evaluate((video: HTMLVideoElement) => video.paused)).toBe(true);
});

test("home keeps the entire video rail dormant while it is vertically outside the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 260 });
  await prepare(page);
  await page.addInitScript(() => {
    const originalPlay = HTMLMediaElement.prototype.play;
    let railPlayCalls = 0;
    Object.defineProperty(window, "__homeRailPlayCalls", { get: () => railPlayCalls });
    HTMLMediaElement.prototype.play = function play() {
      if (this.closest(".lilac-preview-rail")) railPlayCalls++;
      return originalPlay.call(this);
    };
  });
  const trends = Array.from({ length: 4 }, (_, index) => ({
    id: 250 + index,
    kind: "video",
    title: `Вертикальный сценарий ${index + 1}`,
    preview_url: `https://media.example.test/vertical-${index + 1}.mp4`,
  }));
  const requested: string[] = [];
  await page.route("**/api/v1/trends?**", route => route.fulfill({ json: trends }));
  await page.route("https://media.example.test/vertical-*.mp4", route => {
    requested.push(route.request().url());
    return route.fulfill({ contentType: "video/mp4", body: mp4 });
  });
  await page.goto("/?ux=3");

  const rail = page.locator(".lilac-preview-rail");
  const firstFrame = rail.locator("[data-apix-home-preview-frame]").first();
  expect(await firstFrame.evaluate(element => new Promise<boolean>(resolve => {
    const observer = new IntersectionObserver(([entry]) => { observer.disconnect(); resolve(Boolean(entry?.isIntersecting)); });
    observer.observe(element);
  }))).toBe(false);
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(rail.locator("video")).toHaveCount(0);
  expect(requested.some(url => url.endsWith("/vertical-2.mp4"))).toBe(false);
  expect(await page.evaluate(() => (window as unknown as { __homeRailPlayCalls: number }).__homeRailPlayCalls)).toBe(0);

  await firstFrame.scrollIntoViewIfNeeded();
  await expect.poll(() => firstFrame.locator("video").evaluate((video: HTMLVideoElement) => video.currentSrc)).toContain("vertical-1.mp4");
  await expect.poll(() => firstFrame.locator("video").evaluate((video: HTMLVideoElement) => !video.paused)).toBe(true);
  await expect.poll(() => page.evaluate(() => (window as unknown as { __homeRailPlayCalls: number }).__homeRailPlayCalls)).toBeGreaterThan(0);
});

test("home loads and plays only viewport-visible video previews", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await prepare(page);
  const trends = Array.from({ length: 8 }, (_, index) => ({
    id: 300 + index,
    kind: "video",
    title: `Живой сценарий ${index + 1}`,
    preview_url: `https://media.example.test/live-${index + 1}.mp4`,
  }));
  const requested: string[] = [];
  await page.route("**/api/v1/trends?**", route => route.fulfill({ json: trends }));
  await page.route("https://media.example.test/live-*.mp4", route => {
    requested.push(route.request().url());
    return route.fulfill({ contentType: "video/mp4", body: mp4 });
  });
  await page.goto("/?ux=3");

  const railCards = page.locator(".lilac-preview-rail > button");
  await expect(railCards).toHaveCount(8);
  const first = railCards.first().locator("[data-apix-home-preview-frame]");
  const last = railCards.last().locator("[data-apix-home-preview-frame]");
  await first.scrollIntoViewIfNeeded();
  await expect.poll(() => first.locator("video").evaluate((video: HTMLVideoElement) => video.currentSrc)).toContain("live-1.mp4");
  await expect(railCards.last().locator("video")).toHaveCount(0);
  expect(requested.some(url => url.endsWith("/live-8.mp4"))).toBe(false);

  await last.scrollIntoViewIfNeeded();
  await expect.poll(() => last.locator("video").evaluate((video: HTMLVideoElement) => video.currentSrc)).toContain("live-8.mp4");
  await expect.poll(() => last.locator("video").evaluate((video: HTMLVideoElement) => !video.paused)).toBe(true);
  await expect(railCards.first().locator("video")).toHaveCount(0);

  await first.scrollIntoViewIfNeeded();
  await expect.poll(() => first.locator("video").evaluate((video: HTMLVideoElement) => video.currentSrc)).toContain("live-1.mp4");
  await expect.poll(() => first.locator("video").evaluate((video: HTMLVideoElement) => !video.paused)).toBe(true);
  await expect(railCards.last().locator("video")).toHaveCount(0);
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
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  await page.getByRole("button", { name: "Сохранить серию", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Заменить активную серию?", exact: true })).toBeVisible();
  latest = { ...active, count: 2 };
  await page.getByRole("button", { name: "Заменить серию", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Активная серия изменилась");
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions")).toHaveLength(0);
});

for (const close of ["button", "Escape"] as const) {
test(`closing replacement confirmation via ${close} aborts its pending check before any create write`, async ({ page }) => {
  const state = await prepare(page, active); let reads = 0;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/web/image-sessions/active", async route => { reads++; if (reads === 3) await pending; await route.fulfill({ json: { data: active } }).catch(() => {}); });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
  await page.getByRole("button", { name: "Сохранить серию", exact: true }).click();
  await page.getByRole("button", { name: "Заменить серию", exact: true }).click();
  await expect.poll(() => reads).toBe(3);
  if (close === "Escape") await page.keyboard.press("Escape");
  else await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  release();
  await expect(page.getByRole("dialog", { name: "Создать серию фото", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Сохранить серию", exact: true })).toBeEnabled();
  expect(state.writes.filter(row => row.path === "/api/web/image-sessions")).toHaveLength(0);
});
}

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
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
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

for (const form of ["publication", "series"] as const) {
  test(`${form} retains textarea focus and complete sequential typing across controlled rerenders`, async ({ page }) => {
    await prepare(page);
    if (form === "publication") {
      await publication(page);
      await expect(page.getByLabel("Модель публикации", { exact: true })).toBeEnabled();
    } else {
      await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
      await page.getByRole("button", { name: "Создать серию фото", exact: true }).click();
      await expect(page.getByLabel("Модель серии", { exact: true })).toBeEnabled();
    }
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const description = page.getByRole("textbox", { name: form === "publication" ? "Краткое описание" : "Описание серии (необязательно)", exact: true });
    await description.click();
    await description.pressSequentially("AcompleteTypedDescription", { delay: 40 });
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(description).toBeFocused();
    await expect(description).toHaveValue("AcompleteTypedDescription");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: form === "publication" ? "Добавить промпт" : "Создать серию фото", exact: true })).toBeFocused();
  });
}

test("existing library Sheet traps Tab in both directions and restores its opener after Escape", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/prompts?**", route => route.fulfill({ json: { total: 1, items: [{ id: 64, title: "Идея для проверки фокуса", description: "Описание", model: "fixture-photo", prompt_text: "Мой текст для кадра", status: "approved" }] } }));
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  const opener = page.getByRole("button", { name: /Идея для проверки фокуса/ });
  await opener.click();
  const dialog = page.getByRole("dialog");
  const close = dialog.getByRole("button", { name: "Закрыть", exact: true });
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Использовать задание", exact: true })).toBeFocused();
  await page.keyboard.press("Tab"); await expect(close).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0); await expect(opener).toBeFocused();
});

test("existing owner Sheet Escape uses latest busy close guard while its mutation is pending", async ({ page }) => {
  await prepare(page); let posts = 0;
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/admin/overview", route => route.fulfill({ json: { summary: { users_total: 1 } } }));
  await page.route("**/api/v1/admin/users?**", route => route.fulfill({ json: { items: [{ id: 9, full_name: "Тестовый клиент", credits: 30 }] } }));
  await page.route("**/api/v1/admin/withdrawals?**", route => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/admin/users/9", route => route.fulfill({ json: { user: { id: 9, full_name: "Тестовый клиент", tg_id: 789, credits: 30, is_banned: false }, stats: {}, ledger: [] } }));
  await page.route("**/api/v1/admin/users/9/credits", async route => { posts++; await pending; await route.fulfill({ json: { ok: true } }); });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Управление APIX", exact: true }).click();
  await page.getByRole("button", { name: /Тестовый клиент/ }).click();
  await page.getByLabel("Корректировка кредитов", { exact: true }).fill("10");
  await page.getByLabel("Комментарий", { exact: true }).fill("Тестовая корректировка");
  await page.getByRole("button", { name: "Проверить изменение баланса", exact: true }).click();
  await page.getByRole("button", { name: "Подтвердить действие", exact: true }).click();
  await expect.poll(() => posts).toBe(1);
  const confirmation = page.getByRole("dialog", { name: "Подтверждение действия", exact: true });
  await expect(confirmation.getByRole("button", { name: "Сохраняем…", exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(confirmation).toBeVisible();
  release(); await expect(confirmation).toHaveCount(0);
  expect(posts).toBe(1);
});
