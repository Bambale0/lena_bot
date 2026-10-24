import { expect, test, type Page } from "@playwright/test";

async function prepare(page: Page, admin = true) {
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
    if (path.endsWith("/models/video")) return json([{ key: "fixture-video", display_name: "Видео модель", modes: ["text", "image"], credits: 10, max_refs: 1, aspect_ratios: ["16:9", "9:16"], durations: [5], resolutions: ["720p"] }]);
    if (path.endsWith("/models/music")) return json([{ key: "fixture-music", display_name: "Музыкальная модель", credits: 20 }]);
    if (path.endsWith("/music/voices")) return json([]);
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
  test(`five studio tabs fit and home does not overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await prepare(page);
    await page.goto("/?ux=3");
    const tabs = page.getByRole("tablist", { name: "Разделы Mini App" }).getByRole("tab");
    await expect(tabs).toHaveCount(5);
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
  await page.getByRole("tab", { name: "Проекты", exact: true }).click();
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
  await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Продолжить серию", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Восстановить серию?" })).toBeVisible();
  await page.getByRole("button", { name: "Заменить черновик фото", exact: true }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("");
  await expect(page.getByText("series.png", { exact: true })).toBeVisible();
});

test("multi-output results retain original URLs and animate without submitting", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 81, model: "fixture-image", gen_type: "image", prompt: "Два результата", status: "done", result_url: "https://media.example.test/original.png", result_urls: ["https://media.example.test/original.png", "https://media.example.test/second.png"], preview_url: "https://media.example.test/thumb.png" }] }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
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
