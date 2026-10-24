import { expect, test, type Page } from "@playwright/test";

async function prepare(page: Page) {
  const writes: Array<{ path: string; body: any }> = [];
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: "studio-capability-fixture", initDataUnsafe: { user: { id: 123 } }, colorScheme: "dark", ready() {}, expand() {}, openLink() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } as any; });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") writes.push({ path, body: route.request().headers()["content-type"]?.includes("application/json") ? route.request().postDataJSON() : route.request().postData() });
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Администратор", credits: 500, language: "ru", miniapp_ux2_available: true });
    if (path === "/api/web/me") return json({ data: { id: 7, full_name: "Администратор", username: "tester", email: "fixture@example.test", phone: "", language: "ru", has_password: true } });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/models/image")) return json([{ key: "image-fixture", display_name: "Фото модель", credits: 5, modes: ["text", "image"], max_refs: 2, aspect_ratios: ["1:1"], counts: [1] }]);
    if (path.endsWith("/models/video")) return json([{ key: "video-fixture", display_name: "Видео модель", credits: 10, modes: ["text", "image"], max_refs: 1, durations: [5], resolutions: ["720p"], aspect_ratios: ["16:9"] }]);
    if (path.endsWith("/models/music")) return json([{ key: "music-fixture", display_name: "Музыкальная модель", credits: 20, modes: ["text"] }]);
    if (path.endsWith("/payment-methods")) return json(["tbank", "tribute", "lava"]);
    if (path.endsWith("/payment-options")) return json({ methods: ["tbank", "lava"], lava_plan_keys: ["covered"] });
    if (path.endsWith("/plans")) return json([{ key: "covered", title: "Пакет с USD и Lava", credits: 100, price_rub: 200, price_tribute_usd: 3 }, { key: "card-only", title: "Только карта", credits: 50, price_rub: 100 }]);
    if (path.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    if (path.endsWith("/prompts")) return json({ total: 1, items: [{ id: 51, title: "Видео из библиотеки", prompt_text: "Медленное движение камеры", model: "video-fixture", status: "approved", tags: [] }] });
    if (path.endsWith("/admin/overview")) return json({ summary: {} });
    if (path.endsWith("/admin/users")) return json({ items: [{ id: 9, full_name: "Тестовый клиент", credits: 30 }] });
    if (path.endsWith("/admin/withdrawals")) return json({ items: [] });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    return json([]);
  });
  return writes;
}

test("checkout never offers an unsupported provider for the selected plan", async ({ page }) => {
  await prepare(page); await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Открыть баланс", exact: true }).click();
  await page.getByRole("button", { name: /Только карта/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: /Оплата в долларах/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Российская оплата по ссылке/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Карта \| СБП Оплата в рублях/ })).toBeVisible();
});

test("profile editor saves real web DTO without losing preview authority", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/web/me/profile", route => { writes.push({ path: "/api/web/me/profile", body: route.request().postDataJSON() }); return route.fulfill({ json: { data: { id: 7, full_name: "Новое имя", username: "tester", email: "new@example.test", phone: "", language: "ru", has_password: true } } }); });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Редактировать профиль", exact: true }).click();
  await page.getByLabel("Имя в профиле", { exact: true }).fill("Новое имя");
  await page.getByLabel("Email", { exact: true }).fill("new@example.test");
  await page.getByRole("button", { name: "Сохранить профиль", exact: true }).click();
  await expect(page.getByText("Профиль сохранён", { exact: true })).toBeVisible();
  expect(writes.find(row => row.path.endsWith("/me/profile"))?.body).toMatchObject({ full_name: "Новое имя", email: "new@example.test" });
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
});

test("password rejection stays inline and never claims the password changed", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/web/me/password", route => route.fulfill({ status: 401, json: { error: { message: "Текущий пароль неверный" } } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Редактировать профиль", exact: true }).click();
  await page.getByLabel("Текущий пароль", { exact: true }).fill("fixture-old-password");
  await page.getByLabel("Новый пароль", { exact: true }).fill("fixture-new-password");
  await page.getByLabel("Повторите новый пароль", { exact: true }).fill("fixture-new-password");
  await page.getByRole("button", { name: "Сохранить пароль", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Текущий пароль неверный");
  await expect(page.getByText("Пароль сохранён", { exact: true })).toHaveCount(0);
});

test("voice creation transmits language full chosen segment and voice metadata", async ({ page }) => {
  const writes = await prepare(page); await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Создать музыку", exact: true }).click();
  await page.getByPlaceholder("Название голоса", { exact: true }).fill("Мой вокал");
  await page.getByLabel("Исходная запись голоса", { exact: true }).setInputFiles({ name: "voice.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("fixture") });
  await page.getByLabel("Язык голоса", { exact: true }).selectOption("en");
  await page.getByLabel("Начало фрагмента, сек", { exact: true }).fill("12");
  await page.getByLabel("Конец фрагмента, сек", { exact: true }).fill("42");
  await page.locator("summary").filter({ hasText: "Дополнительные параметры голоса" }).click();
  await page.getByLabel("Описание голоса", { exact: true }).fill("Мягкий вокал");
  await page.getByLabel("Стиль голоса", { exact: true }).fill("soul");
  await page.getByLabel("Уровень исполнителя", { exact: true }).fill("professional");
  await page.getByRole("button", { name: "Создать голос", exact: true }).click();
  await expect.poll(() => writes.filter(row => row.path === "/api/v1/music/voices").length).toBe(1);
  const body = String(writes.find(row => row.path === "/api/v1/music/voices")?.body);
  expect(body).toContain('name="language"\r\n\r\nen'); expect(body).toContain('name="vocal_start_s"\r\n\r\n12'); expect(body).toContain('name="vocal_end_s"\r\n\r\n42');
  expect(body).toContain('name="description"\r\n\r\nМягкий вокал'); expect(body).toContain('name="style"\r\n\r\nsoul'); expect(body).toContain('name="singer_skill_level"\r\n\r\nprofessional');
});

test("owned result downloads through signed backend attachment not the thumbnail", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 81, model: "image-fixture", gen_type: "image", prompt: "Мой результат", status: "done", result_url: "https://media.example.test/original.png" }] }));
  let signed = false;
  await page.route("**/api/web/generations/81/download", route => { signed = route.request().headers()["x-telegram-init-data"] === "studio-capability-fixture"; return route.fulfill({ contentType: "image/png", headers: { "Content-Disposition": 'attachment; filename="result-81.png"' }, body: Buffer.from("fixture-image") }); });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Мой результат — Готово", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать файл", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("result-81.png"); expect(signed).toBe(true);
});

test("published result copies its real link without publishing again", async ({ page, context }) => {
  const writes = await prepare(page); await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 82, model: "image-fixture", gen_type: "image", prompt: "Общая работа", status: "done", is_public_feed: true, result_url: "https://media.example.test/original.png" }] }));
  await page.route("**/api/v1/feed/82/link", route => route.fulfill({ json: { link: "https://t.me/fixture_bot?start=feed_82" } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click();
  await page.getByRole("button", { name: "Общая работа — Готово", exact: true }).click();
  await page.getByRole("button", { name: "Скопировать ссылку на работу", exact: true }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe("https://t.me/fixture_bot?start=feed_82");
  expect(writes.filter(row => row.path.endsWith("/share"))).toHaveLength(0);
});

test("video library prompt opens video editor with its own model", async ({ page }) => {
  await prepare(page); await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  await page.getByRole("button", { name: /Видео из библиотеки/ }).click();
  await page.getByRole("button", { name: "Использовать задание", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Видео", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Медленное движение камеры");
});

test("owner can inspect payments already returned in user detail", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/admin/users/9", route => route.fulfill({ json: { user: { id: 9, full_name: "Тестовый клиент", credits: 30 }, stats: { generations_count: 4, payments_count: 1, paid_rub: 250, referrals: { l1: 2, l2: 0, l3: 0 } }, ledger: [], generations: [], transactions: [{ id: 42, amount_rub: 250, credits: 100, provider: "tbank", status: "paid", created_at: "2026-10-24T12:00:00Z" }], withdrawals: [] } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click(); await page.getByRole("button", { name: "Управление APIX", exact: true }).click();
  await page.getByRole("button", { name: /Тестовый клиент/ }).click();
  await page.getByRole("dialog").locator("summary").filter({ hasText: "Платежи" }).click();
  await expect(page.getByRole("dialog").getByText(/Платёж #42/)).toBeVisible();
});

test("library collections are folders and select the real tag source", async ({ page }) => {
  await prepare(page); const queries: string[] = [];
  await page.route("**/api/v1/prompts?**", route => { const query = new URL(route.request().url()).searchParams; queries.push(query.toString()); return route.fulfill({ json: query.get("source") === "collections" ? { items: [{ key: "portraits", title: "Портреты", source: "tag", tag: "portrait" }], total: 1 } : { items: [{ id: 52, title: "Идея портрета", status: "approved", tags: [] }], total: 1 } }); });
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click();
  await page.getByRole("combobox", { name: "Раздел библиотеки", exact: true }).selectOption("collections");
  await page.getByRole("button", { name: "Портреты", exact: true }).click();
  await expect(page.getByRole("button", { name: /Идея портрета/ })).toBeVisible();
  expect(queries.some(row => new URLSearchParams(row).get("tag") === "portrait")).toBe(true);
});

test("owner moderation requires explicit confirmation and reason", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/web/admin/prompts?status=pending", route => route.fulfill({ json: { data: { items: [{ id: 91, title: "Задание на проверке", prompt_text: "Текст проверяемого задания", status: "pending" }] } } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click(); await page.getByRole("button", { name: "Управление APIX", exact: true }).click();
  await page.getByRole("button", { name: "Проверить публикации", exact: true }).click();
  await page.getByRole("button", { name: "Отклонить публикацию", exact: true }).click();
  expect(writes.filter(row => row.path.endsWith("/reject"))).toHaveLength(0);
  await page.getByLabel("Причина отклонения", { exact: true }).fill("Уточните описание");
  await page.getByRole("button", { name: "Подтвердить отклонение", exact: true }).click();
  await expect.poll(() => writes.filter(row => row.path.endsWith("/91/reject")).length).toBe(1);
  expect(writes.find(row => row.path.endsWith("/91/reject"))?.body).toEqual({ reason: "Уточните описание" });
});

test("checkout refreshes terms and never creates invoice after price change", async ({ page }) => {
  const writes = await prepare(page); let requests = 0;
  await page.route("**/api/v1/plans", route => route.fulfill({ json: [{ key: "covered", title: "Пакет", credits: 100, price_rub: ++requests === 1 ? 200 : 250 }] }));
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Открыть баланс", exact: true }).click();
  await page.getByRole("button", { name: "Оплатить через Карта | СБП", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Условия пакета изменились");
  expect(writes.filter(row => row.path.includes("/topup/"))).toHaveLength(0);
});

test("unknown template model fails inline without changing draft or creating a task", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/prompts?**", route => route.fulfill({ json: { items: [{ id: 61, title: "Недоступная модель", model: "offline-model", status: "approved" }], total: 1 } }));
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click(); await page.getByRole("button", { name: /Недоступная модель/ }).click();
  await page.getByRole("button", { name: "Использовать задание", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Модель этого задания сейчас недоступна");
  expect(writes.filter(row => row.path.includes("/generate/"))).toHaveLength(0);
});

test("failed attachment stays inline and cannot download a login page", async ({ page }) => {
  await prepare(page);
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [{ id: 81, model: "image-fixture", gen_type: "image", prompt: "Мой результат", status: "done", result_url: "https://media.example.test/original.png" }] }));
  await page.route("**/api/web/generations/81/download", route => route.fulfill({ contentType: "text/html", body: "<html>Login</html>" }));
  let downloaded = false; page.on("download", () => { downloaded = true; });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Проекты", exact: true }).click(); await page.getByRole("button", { name: "Мой результат — Готово", exact: true }).click();
  await page.getByRole("button", { name: "Скачать файл", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible(); expect(downloaded).toBe(false);
});

test("voice segment outside server limits cannot be sent", async ({ page }) => {
  const writes = await prepare(page); await page.goto("/?ux=3"); await page.getByRole("button", { name: "Создать музыку", exact: true }).click();
  await page.getByPlaceholder("Название голоса", { exact: true }).fill("Мой вокал"); await page.getByLabel("Исходная запись голоса", { exact: true }).setInputFiles({ name: "voice.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("fixture") });
  await page.getByLabel("Конец фрагмента, сек", { exact: true }).fill("90"); await expect(page.getByRole("button", { name: "Создать голос", exact: true })).toBeDisabled();
  expect(writes.filter(row => row.path.endsWith("/music/voices"))).toHaveLength(0);
});

test("library template keeps active photo projection and reset restores parked photos", async ({ page }) => {
  const writes = await prepare(page); const first = "https://media.example.test/first.png", second = "https://media.example.test/second.png";
  await page.route("**/api/v1/prompts?**", route => route.fulfill({ json: { items: [{ id: 62, title: "Шаблон фото", model: "image-fixture", prompt_text: "Создай портрет", status: "approved" }], total: 1 } }));
  await page.route("**/api/v1/generate/image", route => { writes.push({ path: "/api/v1/generate/image", body: route.request().postDataJSON() }); return route.fulfill({ status: 202, json: { id: 99, model: "image-fixture", gen_type: "image", status: "pending" } }); });
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Создать фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Моя исходная идея");
  const urls = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке"); await urls.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click(); await urls.fill(`${first}\n${second}`);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.getByRole("tab", { name: "Идеи", exact: true }).click(); await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click(); await page.getByRole("button", { name: /Шаблон фото/ }).click(); await page.getByRole("button", { name: "Использовать задание", exact: true }).click();
  await expect(page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true })).toBeEnabled();
  await page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true }).click();
  await expect.poll(() => writes.filter(row => row.path.endsWith("/generate/image")).length).toBe(1);
  expect(writes.find(row => row.path.endsWith("/generate/image"))?.body).toMatchObject({ prompt_id: 62, reference_urls: [first] });
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Сбросить", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).not.toBeChecked();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Моя исходная идея");
});

test("avatar upload remains a draft until profile save and can be removed", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/web/upload-media", route => route.fulfill({ json: { data: { url: "https://media.example.test/avatar.png", kind: "image" } } }));
  await page.route("**/api/web/me/profile", route => { writes.push({ path: "/api/web/me/profile", body: route.request().postDataJSON() }); return route.fulfill({ json: { data: { id: 7, has_password: true, ...route.request().postDataJSON() } } }); });
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click(); await page.getByRole("button", { name: "Редактировать профиль", exact: true }).click();
  await page.getByLabel("Новое фото профиля", { exact: true }).setInputFiles({ name: "avatar.png", mimeType: "image/png", buffer: Buffer.from("fixture") });
  await expect(page.getByText("Фото загружено. Сохраните профиль, чтобы применить его.", { exact: true })).toBeVisible();
  expect(writes.filter(row => row.path.endsWith("/me/profile"))).toHaveLength(0);
  await page.getByRole("button", { name: "Сохранить профиль", exact: true }).click(); await expect(page.getByText("Профиль сохранён", { exact: true })).toBeVisible();
  expect(writes.find(row => row.path.endsWith("/me/profile"))?.body.photo_url).toBe("https://media.example.test/avatar.png");
  await page.getByRole("button", { name: "Убрать фото профиля", exact: true }).click(); await page.getByRole("button", { name: "Сохранить профиль", exact: true }).click();
  await expect.poll(() => writes.filter(row => row.path.endsWith("/me/profile")).length).toBe(2);
  expect(writes.filter(row => row.path.endsWith("/me/profile"))[1].body.photo_url).toBe("");
});

test("profile conflict preserves the entered data and shows server rejection", async ({ page }) => {
  await prepare(page); await page.route("**/api/web/me/profile", route => route.fulfill({ status: 409, json: { error: { message: "Email уже занят" } } }));
  await page.goto("/?ux=3"); await page.getByRole("tab", { name: "Профиль", exact: true }).click(); await page.getByRole("button", { name: "Редактировать профиль", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill("other@example.test"); await page.getByRole("button", { name: "Сохранить профиль", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("Email уже занят"); await expect(page.getByLabel("Email", { exact: true })).toHaveValue("other@example.test");
  await expect(page.getByText("Профиль сохранён", { exact: true })).toHaveCount(0);
});

test("library trend uses the existing trend runner without a generic paid launch", async ({ page }) => {
  const writes = await prepare(page);
  await page.route("**/api/v1/prompts?**", route => route.fulfill({ json: { items: [{ id: 63, title: "Тренд библиотеки", model: "video-fixture", status: "approved", tags: [" Trend "] }], total: 1 } }));
  await page.route("**/api/v1/trends/63", route => route.fulfill({ json: { id: 63, title: "Тренд библиотеки", kind: "video", model: "video-fixture", description: "Добавьте фото в мастер тренда" } }));
  await page.goto("/?ux=3"); await page.getByRole("button", { name: "Библиотека промптов", exact: true }).click(); await page.getByRole("button", { name: /Тренд библиотеки/ }).click(); await page.getByRole("button", { name: "Использовать задание", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(page.getByRole("dialog")).toContainText("Добавьте фото в мастер тренда");
  expect(writes.filter(row => row.path.includes("/generate/") || row.path.endsWith("/run"))).toHaveLength(0);
});
