import { expect, test, type Page } from "@playwright/test";

const defaultVideoModels = [{ key: "fixture-video", display_name: "Видео модель", modes: ["text", "image"], credits: 10, max_refs: 1, aspect_ratios: ["16:9", "9:16"], durations: [5], resolutions: ["720p"] }];

async function prepare(page: Page, admin = true, videoModels = defaultVideoModels) {
  const writes: Array<{ path: string; body: any }> = [];
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: "lilac-fixture", initDataUnsafe: { user: { id: 123 } },
      colorScheme: "dark", ready() {}, expand() {}, openLink() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    } } as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (method !== "GET") writes.push({ path, body: route.request().headers()["content-type"]?.includes("application/json") ? route.request().postDataJSON() : null });
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Тестовый администратор", credits: 120, language: "ru", miniapp_ux2_available: admin });
    if (path.endsWith("/me/permissions")) return json({ is_admin: admin });
    if (path.endsWith("/studio/preview")) return admin ? json({ allowed: true, ui_version: 3 }) : route.fulfill({ status: 403, json: { detail: "Admin access required" } });
    if (path.endsWith("/models/image")) return json([{ key: "fixture-image", display_name: "Портретная модель", description: "Фото и иллюстрации", modes: ["text", "image"], credits: 5, max_refs: 2, aspect_ratios: ["1:1", "9:16"], counts: [1], quality_options: [{ value: "basic", label: "Обычное" }] }]);
    if (path.endsWith("/models/video")) return json(videoModels);
    if (path.endsWith("/models/music")) return json([{ key: "fixture-music", display_name: "Музыкальная модель", credits: 20 }]);
    if (path.endsWith("/music/voices")) return json([]);
    if (path.endsWith("/plans")) return json([{ key:"fixture-plan", title:"Серверный пакет", credits:50, price_rub:99 }]);
    if (path.endsWith("/payment-methods")) return json(["tbank"]);
    if (path.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    if (path.endsWith("/services/pinterest")) return json({ title: "Pinterest AI", price_credits: 5, description: "Ваша версия кадра" });
    if (path.endsWith("/help")) return json({ title: "Помощь APIX", text: "Выберите задачу, добавьте фото и проверьте стоимость." });
    if (path.endsWith("/assistant")) return json({ reply: "Помогу с вашей идеей" });
    if (path.endsWith("/prompts") || path.endsWith("/prompts/my")) return json({ total: 1, items: [{ id: 10, title: "Мой портрет", prompt_text: "Портрет в мягком свете", model: "fixture-image", category: "other", status: "approved", likes: 0 }] });
    if (path.endsWith("/billing/transactions")) return json({ ok: true, data: { transactions: [], pending: [] } });
    if (path.endsWith("/history")) return json([]);
    return json([]);
  });
  return writes;
}

test("new studio is an explicit admin entry while regular UI remains the default", async ({ page }) => {
  await prepare(page);
  await page.goto("/");
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Открыть новую студию APIX" }).click();
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  await expect(page.getByRole("heading", { name: "Что создадим сегодня?" })).toBeVisible();
});

test("black lilac foundation: palette, five destinations and full profile works", async ({ page }, info) => {
  await prepare(page);
  await page.goto("/?ux=3");
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(0, 0, 0)");
  await expect(page.locator("body")).not.toHaveCSS("background-image", "none");
  const nav = page.getByRole("navigation", { name: "Основная навигация" });
  await expect(nav.getByRole("tab", { name: "Проекты", exact: true })).toHaveCount(0);
  await expect(nav.getByRole("button", { name: "Пополнить", exact: true })).toBeVisible();
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    const create = await nav.locator('[data-destination="create"]').boundingBox();
    expect(create!.width).toBeGreaterThanOrEqual(44); expect(create!.height).toBeGreaterThanOrEqual(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.locator(".apix-app-header").getByRole("button", { name: "Пополнить", exact: true })).toBeVisible();
    await expect(page.locator(".apix-balance-button")).toContainText("120");
    await page.screenshot({ path: info.outputPath(`black-lilac-home-${width}.png`), fullPage: true });
  }
  await nav.getByRole("tab", { name: "Профиль", exact: true }).click();
  await expect(page.locator(".studio-profile-hero")).toHaveCSS("border-top-left-radius", "26px");
  await expect(page.locator(".studio-profile-hero")).toHaveCSS("border-top-right-radius", "10px");
  await expect(page.getByRole("region", { name: "Баланс профиля" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Пополнить баланс", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Быстрые действия", exact: true })).toBeVisible();
  for (const action of ["Баланс и платежи", "Мои промпты", "Помощь", "Редактировать профиль", "Настройки", "Управление APIX"]) {
    await expect(page.getByRole("button", { name: action, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("heading", { name: "Мои работы", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Обновить работы", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "В работе", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Все работы", exact: true })).toHaveCount(0);
  for (const width of [320, 390, 768, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    const touchTargets = await page.locator(".studio-profile-topup, .studio-profile-quick-actions button, .studio-profile-sections button").evaluateAll(nodes => nodes.map(node => {
      const box = node.getBoundingClientRect(); return { width: box.width, height: box.height };
    }));
    for (const target of touchTargets) { expect(target.width).toBeGreaterThanOrEqual(44); expect(target.height).toBeGreaterThanOrEqual(44); }
    await page.screenshot({ path: info.outputPath(`black-lilac-profile-${width}.png`), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole("button", { name: "Пополнить баланс", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Быстрые действия", exact: true })).toBeVisible();
  await nav.getByRole("tab", { name: "Главная", exact: true }).click();
  await page.getByRole("button", { name: "Все проекты", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Мои работы", exact: true })).toBeVisible();
  await expect(nav.getByRole("tab", { name: "Профиль", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.locator("[data-apix-editor-back]").click();
  await expect(page.locator(".studio-profile-works")).toBeVisible();
  await expect(page.locator("[data-apix-editor-back]")).toHaveCount(0);
});

test("luxury home keeps the APIX palette while matching the reference composition", async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?ux=3");

  await expect(page.getByRole("button", { name: "Язык: Русский", exact: true })).toBeVisible();
  const showcase = page.getByRole("region", { name: "Витрина APIX", exact: true });
  await expect(showcase).toBeVisible();
  const hero = showcase.getByRole("button", { name: "Создать фото — главный сценарий", exact: true });
  await expect(hero).toBeVisible();
  const heroBox = await hero.boundingBox();
  expect(heroBox!.width / heroBox!.height).toBeGreaterThan(1.45);
  await expect(showcase.getByRole("button", { name: "По шаблону", exact: true })).toBeVisible();
  await expect(showcase.getByRole("button", { name: "Открыть помощь", exact: true })).toBeVisible();

  const services = page.getByRole("navigation", { name: "Быстрый запуск", exact: true });
  const labels = ["Создать фото", "Оживить фото", "Создать музыку", "AI-помощник", "Все нейросети", "Инструменты"];
  for (const label of labels) await expect(services.getByRole("button", { name: label, exact: true })).toBeVisible();
  await expect(services.getByRole("button")).toHaveCount(6);
  const tiles = await services.getByRole("button").evaluateAll(nodes => nodes.map(node => {
    const box = node.getBoundingClientRect();
    return { x: box.x, y: box.y, width: box.width, height: box.height };
  }));
  expect(new Set(tiles.slice(0, 3).map(tile => Math.round(tile.y))).size).toBe(1);
  expect(tiles.every(tile => tile.width >= 44 && tile.height >= 44)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("bottom navigation uses four aligned outline glyphs and the branded APIX create medallion", async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?ux=3");
  const nav = page.getByRole("navigation", { name: "Основная навигация" });
  await expect(nav.locator(".lilac-nav-glyph")).toHaveCount(4);
  await expect(nav.locator(".lilac-nav-glyph svg")).toHaveCount(4);
  const medallion = nav.locator(".lilac-create-action");
  await expect(medallion.locator(".lilac-create-mark")).toHaveCount(1);
  const box = await medallion.boundingBox();
  expect(Math.abs(box!.width - box!.height)).toBeLessThanOrEqual(1);
  expect(await medallion.evaluate(node => getComputedStyle(node).borderRadius)).toBe("50%");
  expect(await medallion.evaluate(node => getComputedStyle(node).boxShadow)).toContain("inset");
  expect(await nav.getByRole("tab", { name: "Создать", exact: true }).getAttribute("aria-label")).toBe("Создать");
});

test("every luxury home launcher opens its real APIX workflow", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=3");
  const routes = [
    ["Создать фото", "Фото"],
    ["Оживить фото", "Видео"],
    ["Создать музыку", "Создать музыку"],
    ["AI-помощник", "AI-помощник"],
    ["Все нейросети", "Нейросети"],
    ["Инструменты", "Сервисы"],
  ] as const;
  for (const [launcher, heading] of routes) {
    await page.getByRole("navigation", { name: "Быстрый запуск", exact: true }).getByRole("button", { name: launcher, exact: true }).click();
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
    await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("tab", { name: "Главная", exact: true }).click();
  }
});

test("animate-photo launcher preserves the prompt and replaces a saved text-only Grok model", async ({ page }) => {
  const grokText = { key: "grok-imagine/text-to-video", display_name: "Grok Imagine Video", modes: ["text"], credits: 0.6, max_refs: 1, aspect_ratios: ["9:16"], durations: [10], resolutions: ["720p"] };
  const grokPhoto = { key: "grok-imagine/image-to-video", display_name: "Grok Imagine Video", modes: ["image"], credits: 0.7, max_refs: 7, aspect_ratios: ["9:16"], durations: [10], resolutions: ["720p"] };
  await prepare(page, true, [grokText, grokPhoto]);
  await page.goto("/?ux=3");

  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();
  const model = page.getByRole("combobox", { name: "Модель", exact: true });
  await model.selectOption(grokText.key);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Оживи красиво без речи");
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("tab", { name: "Главная", exact: true }).click();
  await page.locator("section").filter({ hasText: "Продолжить черновик" }).getByRole("button", { name: /Видео/ }).click();
  await expect(model).toHaveValue(grokText.key);
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Оживи красиво без речи");
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("tab", { name: "Главная", exact: true }).click();
  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();

  await expect(model).toHaveValue(grokPhoto.key);
  await expect(page.getByRole("button", { name: "По фото", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Оживи красиво без речи");
  await expect(page.getByText("Фото · до 7", { exact: true })).toBeVisible();
});

test("Grok exposes one plain text-or-photo choice and switches the underlying priced model", async ({ page }) => {
  const grokText = { key: "grok-imagine/text-to-video", display_name: "Grok Imagine Video", modes: ["text"], credits: 0.6, max_refs: 1, aspect_ratios: ["9:16"], durations: [10], resolutions: ["720p"] };
  const grokPhoto = { key: "grok-imagine/image-to-video", display_name: "Grok Imagine Video", modes: ["image"], credits: 0.7, max_refs: 7, aspect_ratios: ["9:16"], durations: [10], resolutions: ["720p"] };
  await prepare(page, true, [grokText, grokPhoto]);
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();
  const model = page.getByRole("combobox", { name: "Модель", exact: true });
  await model.selectOption(grokText.key);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Плавное движение камеры");

  await expect(page.getByRole("button", { name: "По тексту", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "По фото", exact: true }).click();

  await expect(model).toHaveValue(grokPhoto.key);
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Плавное движение камеры");
  await expect(page.getByText("0,7 кр.", { exact: true }).first()).toBeVisible();
});

test("Seedance presents three guided material tiles and keeps technical options collapsed", async ({ page }, info) => {
  const fallback = { key: "fixture-video", display_name: "Видео модель", modes: ["text", "image"], credits: 10, max_refs: 1, aspect_ratios: ["9:16"], durations: [5], resolutions: ["720p"] };
  const seedance = { key: "bytedance/seedance-2-5", display_name: "Seedance 2.5", modes: ["text", "multimodal"], auto_route_by_inputs: true, credits: 4, max_refs: 30, aspect_ratios: ["adaptive", "9:16"], durations: [4, 5, 10, 15, 30], resolutions: ["480p", "720p", "1080p"], supports_video_input: true };
  await prepare(page, true, [fallback, seedance]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption(seedance.key);

  const materials = page.getByRole("group", { name: "Материалы Seedance 2.5" });
  await expect(materials.locator("[data-seedance25-material]"), "photo, video and audio stay visible as task choices").toHaveCount(3, { timeout: 4000 });
  expect(await materials.locator("[data-seedance25-material]").evaluateAll(nodes => nodes.map(node => node.tagName))).toEqual(["BUTTON", "BUTTON", "BUTTON"]);
  for (const name of ["Фото", "Видео", "Аудио"]) await expect(materials.getByText(name, { exact: true })).toBeVisible();
  const advanced = materials.locator("details");
  await expect(advanced.getByText("Дополнительные настройки", { exact: true })).toBeVisible();
  await expect(advanced).not.toHaveAttribute("open", "");
  const chooser = page.waitForEvent("filechooser");
  await materials.getByText("Фото", { exact: true }).click();
  await chooser;
  await expect(page.getByText("Замена персонажа", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Generate audio", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Web search grounding", { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("tab", { name: "Главная", exact: true }).click();
  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toHaveValue(seedance.key);
  await expect(page.getByText("Возможности модели изменились", { exact: false })).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("seedance-guided-composer-390.png"), fullPage: true });
});

test("luxury home stays usable in compact portrait and phone landscape", async ({ page }) => {
  await prepare(page);
  for (const viewport of [{ width: 375, height: 812 }, { width: 844, height: 390 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/?ux=3");
    const header = page.locator(".apix-app-header");
    await expect(header.getByRole("button", { name: "Пополнить", exact: true })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Быстрый запуск", exact: true }).getByRole("button")).toHaveCount(6);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const nav = await page.getByRole("navigation", { name: "Основная навигация" }).boundingBox();
    expect(nav!.x).toBeGreaterThanOrEqual(0);
    expect(nav!.x + nav!.width).toBeLessThanOrEqual(viewport.width);
  }
});

test("black lilac foundation: phone profile header stays reachable after works scroll and topup cancel", async ({ page }, info) => {
  await prepare(page); await page.setViewportSize({width:390,height:844}); await page.goto("/?ux=3");
  await page.getByRole("navigation").getByRole("tab", {name:"Профиль",exact:true}).click();
  const balance = page.locator(".apix-balance-button");
  const measurements: unknown[] = [];
  const checkHeader = async () => {
    await expect(balance).toBeInViewport({ratio:1});
    await expect(page.locator(".ux2-wordmark")).toBeInViewport({ratio:1});
    const position = await balance.evaluate(node => {
      const rect = node.getBoundingClientRect();
      return { x:rect.x,y:rect.y,width:rect.width,height:rect.height,scrollY:window.scrollY,reachable:node.contains(document.elementFromPoint(rect.x+rect.width/2,rect.y+rect.height/2)) };
    });
    expect(position.reachable).toBe(true); expect(position.y).toBeGreaterThanOrEqual(0);
    measurements.push(position);
  };
  await checkHeader();
  await page.locator(".apix-shell > main").evaluate(node => {node.scrollTop=node.scrollHeight;});
  await checkHeader(); await balance.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button",{name:"Закрыть",exact:true}).click();
  await checkHeader(); await expect(page.locator(".studio-profile-works")).toBeVisible();
  await page.screenshot({path:info.outputPath("black-lilac-profile-persistent-header-390.png"),fullPage:true});
  await info.attach("profile-header-bounds",{body:JSON.stringify(measurements,null,2),contentType:"application/json"});
});

test("black lilac foundation: explicit topup cancels with the same editor and task", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 77, model: "fixture-image", gen_type: "image", prompt: "Моя работа", status: "done" }] }));
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Черновик до пополнения");
  await page.getByRole("navigation").getByRole("button", { name: "Пополнить", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(page.getByRole("dialog")).toContainText("Серверный пакет");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Черновик до пополнения");
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Моя работа — Готово", exact: true }).click();
  const task = page.getByRole("dialog", { name: "Задача #77" });
  await task.getByRole("button", { name: "Пополнить", exact: true }).click();
  await expect(task).not.toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(task).toBeVisible();
  await expect(task.getByRole("button", { name: "Пополнить", exact: true })).toBeFocused();
  expect(writes.filter(write => /\/topup\/|\/generate\//.test(write.path))).toHaveLength(0);
});

for (const entry of ["studio", "ordinary", "legacy"] as const) for (const supported of [true, false]) {
  test(`black lilac foundation: ${entry} Telegram ${supported ? "modern" : "unsupported"} fullscreen and safe chrome`, async ({ page }) => {
    await prepare(page);
    await page.addInitScript(({ supported }) => {
      const calls: string[] = [], events: Record<string, () => void> = {};
      (window as any).__telegramCalls = calls; (window as any).__telegramEvents = events;
      Object.assign(window.Telegram!.WebApp!, {
        version: supported ? "8.0" : "7.10", headerColor: "#123456", backgroundColor: "#234567", bottomBarColor: "#345678",
        safeAreaInset: { top: 24, bottom: 12, left: 0, right: 0 }, contentSafeAreaInset: { top: 32, bottom: 0, left: 0, right: 0 },
        ready() { calls.push("ready"); }, expand() { calls.push("expand"); },
        requestFullscreen() { calls.push("fullscreen"); },
        onEvent(name: string, callback: () => void) { events[name] = callback; }, offEvent(name: string) { delete events[name]; },
        setHeaderColor(color: string) { calls.push(`header:${color}`); }, setBackgroundColor(color: string) { calls.push(`background:${color}`); }, setBottomBarColor(color: string) { calls.push(`bottom:${color}`); },
      });
      document.documentElement.requestFullscreen = () => { throw new Error("Browser fullscreen must not be requested"); };
    }, { supported });
    await page.goto(entry === "studio" ? "/?ux=3" : entry === "legacy" ? "/?legacy=1" : "/");
    await expect.poll(() => page.evaluate(() => (window as any).__telegramCalls.includes("expand"))).toBe(true);
    expect(await page.evaluate(() => (window as any).__telegramCalls.filter((x: string) => x === "fullscreen").length)).toBe(supported ? 1 : 0);
    await page.evaluate(() => { (window as any).__telegramEvents.fullscreenChanged?.(); (window as any).__telegramEvents.fullscreenFailed?.(); });
    expect(await page.evaluate(() => (window as any).__telegramCalls.filter((x: string) => x === "fullscreen").length)).toBe(supported ? 1 : 0);
    if (entry === "studio") {
      await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
      expect((await page.locator(".apix-app-header").boundingBox())!.y).toBeGreaterThanOrEqual(56);
      await page.getByRole("button", { name: "Обычный интерфейс", exact: true }).click();
      await expect.poll(() => page.evaluate(() => (window as any).__telegramCalls.includes("header:#123456"))).toBe(true);
      expect(await page.evaluate(() => (window as any).__telegramCalls.includes("header:#000000"))).toBe(true);
    }
  });
}

test("black lilac foundation: actual contrast, lilac text, focus and short viewport", async ({ page }, info) => {
  await prepare(page); await page.emulateMedia({ reducedMotion: "reduce" }); await page.goto("/?ux=3");
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  const contrast = await page.evaluate(() => {
    const pixel = (color: string) => { const c = document.createElement("canvas"); c.width = c.height = 1; const ctx = c.getContext("2d")!; ctx.fillStyle = color; ctx.fillRect(0,0,1,1); return [...ctx.getImageData(0,0,1,1).data].slice(0,3); };
    const lum = (rgb: number[]) => rgb.map(x => x/255).map(x => x <= .04045 ? x/12.92 : ((x+.055)/1.055)**2.4).reduce((sum,x,i) => sum+x*[.2126,.7152,.0722][i],0);
    const root = getComputedStyle(document.documentElement);
    return [["--foreground", "--background"], ["--foreground", "--card"], ["--muted-foreground", "--card"], ["--primary", "--card"], ["--primary-foreground", "--primary"]].map(([fg,bg]) => {
      const f = pixel(root.getPropertyValue(fg)), b = pixel(root.getPropertyValue(bg));
      return { fg, bg, ratio:(Math.max(lum(f),lum(b))+.05)/(Math.min(lum(f),lum(b))+.05), lilac: f[2] >= f[0] };
    });
  });
  for (const pair of contrast) { expect(pair.ratio, `${pair.fg} on ${pair.bg}`).toBeGreaterThanOrEqual(4.5); expect(pair.lilac).toBe(true); }
  await info.attach("computed-contrast", { body: JSON.stringify(contrast, null, 2), contentType:"application/json" });
  await expect(page.locator(".ux2-wordmark strong")).toHaveCSS("color", "rgb(196, 161, 255)");
  await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  const prompt = page.getByRole("textbox", { name: /^Промпт/ }); await prompt.focus();
  await expect(prompt).toHaveCSS("outline-style", "solid");
  await expect(prompt).toHaveCSS("outline-width", "2px");
  await page.setViewportSize({ width:320,height:420 }); await prompt.fill("Короткий экран с клавиатурой");
  await page.locator(".apix-shell > main").evaluate(node => { node.scrollTop = node.scrollHeight; });
  const balance = page.locator(".apix-balance-button");
  await expect(balance).toBeInViewport(); await balance.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("button", { name:"Закрыть", exact:true })).toBeInViewport();
  for (let i=0;i<8;i++) await page.keyboard.press("Tab");
  expect(await page.getByRole("dialog").evaluate(node => node.contains(document.activeElement))).toBe(true);
  await page.screenshot({ path:info.outputPath("black-lilac-short-topup.png"), fullPage:true });
  await page.keyboard.press("Escape"); await expect(prompt).toHaveValue("Короткий экран с клавиатурой");
});

async function prepareRepeat(page: Page, pending = false) {
  const writes = await prepare(page);
  const source = { id:201, model:"fixture-image", gen_type:"image", result_url:"https://media.example.test/source.png", is_mine:true, aspect_ratio:"1:1" };
  await page.route("**/api/v1/feed/201", route => route.fulfill({json:source}));
  await page.route("**/api/v1/feed/201/remix/quote", route => route.fulfill({json:{ cost_credits:5, balance_credits:120, can_run:true, deficit_credits:0, recommended_plan:null }}));
  await page.route("https://media.example.test/**", route => route.fulfill({ contentType:"image/png", body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=","base64") }));
  await page.addInitScript(({pending}) => {
    const handlers = new Set<() => void>();
    window.Telegram!.WebApp!.BackButton = { show(){}, hide(){}, onClick(callback){handlers.add(callback);}, offClick(callback){handlers.delete(callback);} };
    window.addEventListener("test:telegram-back", () => handlers.forEach(callback => callback()));
    if (pending) sessionStorage.setItem("apix:feed-repeat-draft:v2:7:201", JSON.stringify({ savedAt:Date.now(), sourceMediaUrl:"https://media.example.test/source.png", references:[], changeRequest:"Ожидающий черновик", modelKey:"fixture-image", mode:"image", aspectRatio:"1:1", quality:"basic", count:1, duration:5, resolution:"720p", grokMode:"normal", payment:{ startedAt:Date.now(), provider:"tbank", planKey:"fixture-plan", transactionId:41, checkoutUrl:"https://pay.example.test/41" } }));
  }, {pending});
  await page.goto("/?ux=3&feed=201");
  return writes;
}

test("black lilac foundation: independent repeat portal preserves draft through topup and native Back", async ({ page }, info) => {
  const writes = await prepareRepeat(page);
  const repeat = page.getByRole("dialog", {name:"Повторить работу"});
  const draft = repeat.getByLabel("Что изменить в образе");
  await repeat.getByText("Что изменить (необязательно)", { exact: true }).click();
  await draft.fill("Новый красный фон");
  await repeat.getByRole("button", {name:"Пополнить", exact:true}).click();
  await expect(repeat).not.toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await page.evaluate(() => window.dispatchEvent(new Event("test:telegram-back")));
  await expect(repeat).toBeVisible(); await expect(draft).toHaveValue("Новый красный фон");
  await expect(repeat.getByRole("button", {name:"Пополнить", exact:true})).toBeFocused();
  await page.screenshot({ path:info.outputPath("black-lilac-repeat.png"), fullPage:true });
  expect(writes.filter(write => /\/topup\/|\/generate\/|\/remix$/.test(write.path))).toHaveLength(0);
});

test("black lilac foundation: pending inline checkout blocks generic topup without losing payment marker", async ({ page }) => {
  const writes = await prepareRepeat(page,true);
  const repeat = page.getByRole("dialog", {name:"Повторить работу"});
  await expect(repeat.getByRole("button", {name:"Пополнить", exact:true})).toBeDisabled();
  await expect(repeat.getByText("Завершите текущую операцию или проверьте уже открытую оплату ниже.", {exact:true})).toBeVisible();
  await expect(repeat.getByRole("button", {name:"Проверить оплату", exact:true})).toBeVisible();
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:feed-repeat-draft:v2:7:201")!).payment.transactionId)).toBe(41);
  expect(writes.filter(write => /\/topup\//.test(write.path))).toHaveLength(0);
});

for (const revoked of ["admission", "actor"] as const) test(`black lilac foundation: revoking ${revoked} removes the portal balance bridge`, async ({ page }) => {
  await prepareRepeat(page);
  const repeat = page.getByRole("dialog", {name:"Повторить работу"});
  await expect(repeat.getByRole("button", {name:"Пополнить", exact:true})).toBeEnabled();
  await page.route("**/api/v1/me", route => route.fulfill({json:{id:revoked === "actor" ? 8 : 7,tg_id:123,credits:120,language:"ru",miniapp_ux2_available:revoked === "actor"}}));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  await expect(page.locator(".studio-overlay-balance")).toHaveCount(0);
});

test("ordinary user cannot enable new studio by direct query", async ({ page }) => {
  await prepare(page, false);
  await page.goto("/?ux=3");
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Открыть новую студию APIX" })).toHaveCount(0);
});

test("admin studio exposes models library music and help through real destinations", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=3");
  await expect(page.getByRole("heading", { name: "Что создадим сегодня?" })).toBeVisible();
  await page.getByRole("button", { name: "Все нейросети" }).click();
  await expect(page.getByRole("heading", { name: "Нейросети" })).toBeVisible();
  await expect(page.getByText("Портретная модель", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Главная", exact: true }).click();
  await page.getByRole("button", { name: "Создать музыку" }).click();
  await expect(page.getByLabel("Модель", { exact: true })).toHaveValue("fixture-music");
  await page.getByRole("tab", { name: "Идеи", exact: true }).click();
  await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  await expect(page.getByText("Мой портрет", { exact: true })).toBeVisible();
});

test("assistant preserves earlier conversation content on the second request", async ({ page }) => {
  const writes = await prepare(page);
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "AI-помощник", exact: true }).click();
  const input = page.getByPlaceholder("Спросите о чём угодно");
  await input.fill("Создай идею");
  await page.getByRole("button", { name: "Отправить", exact: true }).click();
  await expect(page.getByText("Помогу с вашей идеей", { exact: true })).toBeVisible();
  await input.fill("Теперь короче");
  await page.getByRole("button", { name: "Отправить", exact: true }).click();
  await expect.poll(() => writes.filter(item => item.path.endsWith("/assistant")).length).toBe(2);
  const history = writes.filter(item => item.path.endsWith("/assistant"))[1].body.history;
  expect(history).toEqual([{ role: "user", content: "Создай идею" }, { role: "assistant", content: "Помогу с вашей идеей" }]);
});

for (const width of [320, 390, 768, 1280]) {
  test(`five studio destinations fit and home does not overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await prepare(page);
    await page.goto("/?ux=3");
    const rail = page.getByRole("tablist", { name: "Разделы Mini App" });
    const tabs = rail.locator("button");
    await expect(tabs).toHaveCount(5);
    await expect(rail.getByRole("tab")).toHaveCount(4);
    await expect(rail.getByRole("button", {name:"Пополнить",exact:true})).not.toHaveAttribute("aria-selected");
    await expect(tabs.nth(2)).toHaveAccessibleName("Создать");
    const createBox = await tabs.nth(2).boundingBox();
    expect(Math.abs(createBox!.x + createBox!.width / 2 - width / 2)).toBeLessThanOrEqual(2);
    for (const tab of await tabs.all()) {
      const box = await tab.boundingBox();
      expect(box && box.x >= 0 && box.x + box.width <= width + 1).toBeTruthy();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("preview closes when the authenticated server capability is revoked", async ({ page }) => {
  await prepare(page);
  await page.goto("/?ux=3");
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: 7, tg_id: 123, credits: 120, language: "ru", miniapp_ux2_available: false } }));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Открыть новую студию APIX" })).toHaveCount(0);
});

test("public prompt publication requires a separate explicit confirmation", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 77, model: "fixture-image", gen_type: "image", prompt: "Мой приватный портрет", status: "done", result_url: "https://media.example.test/result.png", created_at: "2026-10-24T12:00:00Z" }] }));
  await page.goto("/?ux=3");
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Мой приватный портрет — Готово" }).click();
  await page.getByRole("button", { name: "Опубликовать промпт", exact: true }).click();
  await expect(page.getByText("Задание станет доступно другим пользователям.", { exact: true })).toBeVisible();
  expect(writes.filter(item => item.path.endsWith("/share-library"))).toHaveLength(0);
  await page.getByRole("button", { name: "Подтвердить публикацию", exact: true }).click();
  await expect.poll(() => writes.filter(item => item.path.endsWith("/share-library")).length).toBe(1);
});

for (const failure of ["history", "auth"] as const) {
  test(`preview fails closed on permission revocation with ${failure} failure`, async ({ page }) => {
    await prepare(page); await page.goto("/?ux=3");
    await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
    await page.route("**/api/v1/history?**", route => route.fulfill({ status: 500, json: { detail: "Unavailable" } }));
    await page.route("**/api/v1/me", route => failure === "auth"
      ? route.fulfill({ status: 403, json: { detail: "Banned" } })
      : route.fulfill({ json: { id: 7, tg_id: 123, credits: 120, miniapp_ux2_available: false } }));
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  });
}

test("opening from ordinary UI and choosing a model preserves stored draft and references", async ({ page }) => {
  await prepare(page);
  await page.addInitScript(() => sessionStorage.setItem("apix:ux2:drafts:v1:7", JSON.stringify({ version: 1, owner: 7, drafts: { image: {
    kind: "image", model: "fixture-image", prompt: "Моя сохранённая идея", promptId: null, sourceTitle: "", aspectRatio: "9:16", quality: "basic", count: 1, taskCount: 1, mode: "image", duration: 5, resolution: "720p", referenceUrls: ["https://media.example.test/input.png"], videoUrl: "", videoStart: 0, videoEnd: null, audioIds: [], characterIds: [], seed: null, grokMode: "normal",
  } } })));
  await page.goto("/");
  await page.getByRole("button", { name: "Открыть новую студию APIX" }).click();
  await expect(page.getByText("Моя сохранённая идея", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Все нейросети" }).click();
  await page.getByRole("button", { name: /Портретная модель/ }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Моя сохранённая идея");
  await expect(page.getByText("input.png", { exact: true })).toBeVisible();
  const stored = await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:ux2:drafts:v1:7")!).drafts.image);
  expect(stored.referenceUrls).toEqual(["https://media.example.test/input.png"]);
  expect(stored.aspectRatio).toBe("9:16");
});

test("unapproved own library submission cannot start generation", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/prompts/my", route => route.fulfill({ json: { total: 1, items: [{ id: 11, title: "На модерации", status: "pending" }] } }));
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  await page.getByRole("button", { name: "Мои публикации", exact: true }).click();
  await page.getByRole("button", { name: /На модерации/ }).click();
  await expect(page.getByRole("button", { name: "Использовать задание", exact: true })).toBeDisabled();
});

test("source audio uses multipart upload then the installed generation contract", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/music/source-audio", route => route.fulfill({ status: 201, json: { url: "https://media.example.test/source.mp3", duration_seconds: 45, filename: "my-song.mp3" } }));
  await page.route("**/api/v1/music/from-audio", async route => {
    writes.push({ path: "/api/v1/music/from-audio", body: route.request().postDataJSON() });
    return route.fulfill({ status: 202, json: { id: 91, model: "fixture-music", status: "pending", gen_type: "music" } });
  });
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Создать музыку", exact: true }).click();
  await page.getByLabel("Исходное аудио", { exact: true }).setInputFiles({ name: "my-song.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("fixture") });
  await page.getByLabel("Задание для обработки", { exact: true }).fill("Добавь мягкий вокал");
  await page.getByLabel("Обработка аудио").selectOption("add_vocals");
  await expect(page.getByRole("button", { name: "Создать из аудио", exact: true })).toBeDisabled();
  await page.getByLabel("Название обработки", { exact: true }).fill("Мой трек");
  await page.getByLabel("Стиль обработки", { exact: true }).fill("Soft pop");
  await page.getByRole("button", { name: "Создать из аудио", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Задача #91" })).toBeVisible();
  expect(writes.find(item => item.path.endsWith("/from-audio"))?.body).toMatchObject({ operation: "add_vocals", model: "fixture-music", upload_url: "https://media.example.test/source.mp3", source_duration: 45 });
});

test("voice verification uploads the spoken phrase instead of a JSON stub", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/music/voices", route => route.fulfill({ json: [{ id: 5, name: "Мой голос", status: "awaiting_verification", validate_phrase: "Мой собственный голос" }] }));
  let uploaded = false;
  await page.route("**/api/v1/music/voices/5/verify", route => { uploaded = route.request().headers()["content-type"].includes("multipart/form-data"); return route.fulfill({ status: 202, json: { id: 5, status: "processing" } }); });
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Создать музыку", exact: true }).click();
  await page.getByLabel("Запись подтверждения: Мой голос").setInputFiles({ name: "voice.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("fixture") });
  await expect.poll(() => uploaded).toBe(true);
});

test("owner balance adjustment requires review and confirmation", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/admin/overview", route => route.fulfill({ json: { summary: { users_total: 1 } } }));
  await page.route("**/api/v1/admin/users?**", route => route.fulfill({ json: { items: [{ id: 9, full_name: "Тестовый клиент", credits: 30 }] } }));
  await page.route("**/api/v1/admin/withdrawals?**", route => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/admin/users/9", route => route.fulfill({ json: { user: { id: 9, full_name: "Тестовый клиент", tg_id: 789, credits: 30, is_banned: false }, stats: {}, ledger: [] } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Управление APIX", exact: true }).click();
  await page.getByRole("button", { name: /Тестовый клиент/ }).click();
  await page.getByLabel("Корректировка кредитов", { exact: true }).fill("10");
  await page.getByLabel("Комментарий", { exact: true }).fill("Тестовая корректировка");
  await page.getByRole("button", { name: "Проверить изменение баланса", exact: true }).click();
  expect(writes.filter(item => item.path.endsWith("/credits"))).toHaveLength(0);
  await page.getByRole("button", { name: "Подтвердить действие", exact: true }).click();
  await expect.poll(() => writes.filter(item => item.path.endsWith("/credits")).length).toBe(1);
});

test("visual smoke uses real rendered studio at mobile size", async ({ page }, info) => {
  await prepare(page); await page.setViewportSize({ width: 390, height: 844 }); await page.goto("/?ux=3");
  await expect(page.getByRole("heading", { name: "Что создадим сегодня?" })).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.body).fontFamily)).not.toContain("Times New Roman");
  await page.screenshot({ path: info.outputPath("lilac-home-mobile.png"), fullPage: true });
});

test("photo creation uses the existing full form and opens the real pending task", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/generate/image", route => { writes.push({ path: "/api/v1/generate/image", body: route.request().postDataJSON() }); return route.fulfill({ status: 202, json: { id: 101, gen_type: "image", model: "fixture-image", status: "pending", prompt: "Лиловый рассвет" } }); });
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Лиловый рассвет");
  await page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Задача #101" })).toBeVisible();
  expect(writes.find(item => item.path.endsWith("/generate/image"))?.body).toMatchObject({ model: "fixture-image", prompt: "Лиловый рассвет" });
});

test("failed generation leaves the user's idea editable without a fake result", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/generate/image", route => route.fulfill({ status: 402, json: { detail: "Недостаточно кредитов" } }));
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Моя идея сохранится");
  await page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true }).click();
  await expect(page.getByRole("region", { name: "Notifications alt+T" })).toContainText("Недостаточно кредитов");
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Моя идея сохранится");
  await expect(page.getByRole("dialog", { name: /Задача/ })).toHaveCount(0);
});

test("protected series restore keeps prompt hidden and requires replacement consent", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/web/image-sessions/active", route => route.fulfill({ json: { ok: true, data: { id: 4, model: "fixture-image", mode: "image", quality: "basic", count: 1, prompt_hidden: true, prompt_actions_allowed: false, reference_urls: ["https://media.example.test/series.png"] } } }));
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  await page.getByRole("button", { name: /Мой портрет/ }).click();
  await page.getByRole("button", { name: "Использовать задание", exact: true }).click();
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Продолжить серию", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Восстановить серию?" })).toBeVisible();
  await page.getByRole("button", { name: "Заменить черновик фото", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("");
  await expect(page.getByText("series.png", { exact: true })).toBeVisible();
});

test("multi-output results retain original URLs and animate without submitting", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 81, model: "fixture-image", gen_type: "image", prompt: "Два результата", status: "done", result_url: "https://media.example.test/original.png", result_urls: ["https://media.example.test/original.png", "https://media.example.test/second.png"], preview_url: "https://media.example.test/thumb.png" }] }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Два результата — Готово", exact: true }).click();
  await expect(page.getByRole("button", { name: "Оригинал 2", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Создать видео из результата", exact: true }).click();
  await expect(page.getByText("original.png", { exact: true })).toBeVisible();
  expect(writes.filter(item => item.path.includes("/generate/"))).toHaveLength(0);
});

test("delayed admission cannot replace edits made while access is being checked", async ({ page }) => {
  await prepare(page);
  await page.addInitScript(() => sessionStorage.setItem("apix:ux2:drafts:v1:7", JSON.stringify({ version: 1, owner: 7, drafts: { image: { kind: "image", model: "fixture-image", prompt: "Старый черновик", promptId: null, sourceTitle: "", aspectRatio: "1:1", quality: "basic", count: 1, taskCount: 1, mode: "text", duration: 5, resolution: "720p", referenceUrls: [], videoUrl: "", videoStart: 0, videoEnd: null, audioIds: [], characterIds: [], seed: null, grokMode: "normal" } } })));
  let release!: () => void; const held = new Promise<void>(resolve => { release = resolve; }); let received = false;
  await page.route("**/api/v1/studio/preview", async route => { received = true; await held; return route.fulfill({ json: { allowed: true, ui_version: 3 } }); });
  await page.goto("/"); await page.getByRole("tab", { name: "Фото", exact: true }).click();
  await page.getByRole("button", { name: "Открыть новую студию APIX" }).click();
  await expect.poll(() => received).toBe(true);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Самый свежий ввод"); release();
  await expect(page.getByText("Самый свежий ввод", { exact: true })).toBeVisible();
  await expect(page.getByText("Старый черновик", { exact: true })).toHaveCount(0);
});

test("lost owner mutation response blocks retry across reopening and reload", async ({ page }) => {
  await prepare(page);
  let credits = 30, posts = 0;
  await page.route("**/api/v1/admin/overview", route => route.fulfill({ json: { summary: { users_total: 1 } } }));
  await page.route("**/api/v1/admin/users?**", route => route.fulfill({ json: { items: [{ id: 9, full_name: "Тестовый клиент", credits }] } }));
  await page.route("**/api/v1/admin/withdrawals?**", route => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/admin/users/9", route => route.fulfill({ json: { user: { id: 9, full_name: "Тестовый клиент", tg_id: 789, credits }, stats: {}, ledger: credits === 40 ? [{ id: 1, delta: 10, note: "Проверка потери ответа" }] : [] } }));
  await page.route("**/api/v1/admin/users/9/credits", route => { posts++; credits += 10; return route.abort("failed"); });
  const enter = async () => { await page.getByRole("tab", { name: "Профиль", exact: true }).click(); await page.getByRole("button", { name: "Управление APIX", exact: true }).click(); };
  await page.goto("/?ux=3"); await enter();
  await page.getByRole("button", { name: /Тестовый клиент/ }).click();
  await page.getByLabel("Корректировка кредитов", { exact: true }).fill("10"); await page.getByLabel("Комментарий", { exact: true }).fill("Проверка потери ответа");
  await page.getByRole("button", { name: "Проверить изменение баланса", exact: true }).click();
  await page.getByRole("button", { name: "Подтвердить действие", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Результат корректировки не подтверждён", exact: true })).toBeVisible();
  expect(posts).toBe(1);
  await page.reload(); await enter();
  await expect(page.getByRole("heading", { name: "Результат корректировки не подтверждён", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Проверить историю корректировки", exact: true }).click();
  await expect(page.getByText("Баланс: 40 кр.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Проверить изменение баланса", exact: true })).toBeDisabled();
  expect(posts).toBe(1);
});
