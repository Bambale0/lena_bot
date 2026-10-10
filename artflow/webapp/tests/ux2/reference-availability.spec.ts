import { expect, test, type Page } from "@playwright/test";
const urls = ["https://media.example.test/static/upload/miniapp/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png", "https://media.example.test/static/upload/miniapp/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"];
const model = { key: "availability-photo", display_name: "Photo", modes: ["text", "image"], credits: 2,
  max_refs: 2, aspect_ratios: ["1:1"], counts: [1], quality_options: [{ value: "basic", label: "Обычное" }] };
async function prepare(page: Page, states: Record<string,string> = {}, light = false) {
  const posts: any[] = []; const checks: string[] = [];
  await page.addInitScript(({ light }) => { window.Telegram = { WebApp: { initData: "availability-fixture", colorScheme: light ? "light" : "dark", ready() {}, expand() {}, initDataUnsafe: { user: { id: 123 } }, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } as any; }, { light });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ contentType: "application/javascript", body: "" }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/web/upload-media/check") { const url = route.request().postDataJSON().url; checks.push(url); return route.fulfill({ json: { ok: true, data: { status: states[url] || "available" } } }); }
    if (path === "/api/v1/me") return route.fulfill({ json: { id: 7, tg_id: 123, full_name: "Tester", credits: 100, language: "ru", miniapp_ux2_available: true } });
    if (path === "/api/v1/models/image") return route.fulfill({ json: [model] });
    if (path === "/api/v1/models/video") return route.fulfill({ json: [] });
    if (path.endsWith("/generate/image")) { posts.push(route.request().postDataJSON()); return route.fulfill({ status: 202, json: { id: 900, gen_type: "image", status: "pending", model: model.key } }); }
    if (path.endsWith("/auth/config")) return route.fulfill({ json: { bot_username: "test_bot" } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/?ux=2");
  return { posts, checks };
}
async function editor(page: Page, photos = urls) {
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: "Фото Создать или изменить изображение" }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Сохранить описание");
  const field = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
  await field.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
  await field.fill(photos.join("\n"));
}
const launch = (page: Page) => page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true });

test("missing active photo stops before generation while retaining both inputs", async ({ page }) => {
  const { posts, checks } = await prepare(page, { [urls[1]]: "missing" });
  await editor(page);
  await launch(page).click();
  await expect.poll(() => checks.includes(urls[1])).toBe(true);
  await expect(page.getByRole("region", { name: "Notifications alt+T" })).toContainText("Файл больше недоступен");
  await expect(launch(page)).toBeEnabled();
  expect(posts).toHaveLength(0);
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Сохранить описание");
  await expect(page.locator(".ux2-reference-row")).toHaveCount(2);
  await expect(page.locator(".ux2-reference-row").nth(1).getByText("Файл больше недоступен. Выберите фото снова.", { exact: true })).toBeVisible();
});


test("a file disappearing after initial preview is shown as missing at submit", async ({ page }) => {
  const states: Record<string, string> = {};
  const { posts } = await prepare(page, states);
  await editor(page);
  const row = page.locator(".ux2-reference-row").nth(1);
  await expect(row.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "available");
  states[urls[1]] = "missing";
  await launch(page).click();
  await expect(row.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "missing");
  await expect(launch(page)).toBeEnabled();
  expect(posts).toHaveLength(0);
});


test("only verified active photos are submitted; a missing parked one stays", async ({ page }) => {
  const { posts } = await prepare(page, { [urls[1]]: "missing" });
  await editor(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await launch(page).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([urls[0]]);
  expect(JSON.stringify(posts[0])).not.toContain(urls[1]);
});

for (const state of ["unknown", "forbidden", "temporary_error"]) {
  test(`an active ${state} file cannot trigger a paid request`, async ({ page }) => {
    const { posts } = await prepare(page, { [urls[0]]: state });
    await editor(page, [urls[0]]);
    await launch(page).click();
    await expect(page.getByRole("region", { name: "Notifications alt+T" }).locator("[data-sonner-toast]")).toBeVisible();
    await expect(page.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", state);
    await expect(launch(page)).toBeEnabled();
    expect(posts).toHaveLength(0);
  });
}

test("checking again is read-only; subsequent launch is a separate action", async ({ page }) => {
  const states = { [urls[0]]: "missing" };
  const { posts } = await prepare(page, states);
  await editor(page, [urls[0]]);
  const row = page.locator(".ux2-reference-row");
  await expect(row.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "missing");
  states[urls[0]] = "available";
  await row.getByRole("button", { name: "Проверить снова", exact: true }).click();
  await expect(row.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "available");
  expect(posts).toHaveLength(0);
  await launch(page).click();
  await expect.poll(() => posts.length).toBe(1);
});

test("reload rechecks references instead of trusting previous availability", async ({ page }) => {
  const states: Record<string,string> = {};
  const { posts } = await prepare(page, states);
  await editor(page, [urls[0]]);
  await expect(page.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "available");
  states[urls[0]] = "missing";
  await page.reload();
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: "Фото Создать или изменить изображение" }).click();
  await expect(page.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "missing");
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Сохранить описание");
  expect(posts).toHaveLength(0);
});

test("a late response cannot mark a replacement URL missing", async ({ page }) => {
  const { posts } = await prepare(page);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let received = false;
  await page.route("**/api/web/upload-media/check", async route => {
    if (route.request().postDataJSON().url === urls[0]) { received = true; await held; return route.fulfill({ json: { data: { status: "missing" } } }); }
    return route.fulfill({ json: { data: { status: "available" } } });
  });
  await editor(page, [urls[0]]);
  await expect.poll(() => received).toBe(true);
  const field = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
  await field.fill(urls[1]);
  await expect(page.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "available");
  release();
  await expect(page.locator(".ux2-reference-row")).toHaveCount(1);
  await expect(page.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "available");
  expect(posts).toHaveLength(0);
});

test("transport error keeps the draft and never starts generation", async ({ page }) => {
  const { posts } = await prepare(page);
  await page.route("**/api/web/upload-media/check", route => route.fulfill({ status: 503, json: { detail: "temporary failure" } }));
  await editor(page, [urls[0]]);
  await launch(page).click();
  await expect(page.getByRole("region", { name: "Notifications alt+T" })).toContainText("Запуск не отправлен");
  await expect(launch(page)).toBeEnabled();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Сохранить описание");
  expect(posts).toHaveLength(0);
});

for (const light of [false, true]) {
  test(`missing photo warning and recovery fit 320px (${light ? "light" : "dark"})`, async ({ page }, info) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await prepare(page, { [urls[0]]: "missing" }, light);
    await editor(page, [urls[0]]);
    const row = page.locator(".ux2-reference-row");
    await row.scrollIntoViewIfNeeded();
    await expect(row.getByRole("button", { name: "Проверить снова", exact: true })).toBeVisible();
    const bounds = await row.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(320);
    await page.screenshot({ path: info.outputPath(`availability-${light ? "light" : "dark"}-320.png`), animations: "disabled" });
  });
}


test("a late passive check cannot resurrect a deleted reference", async ({ page }) => {
  const { posts } = await prepare(page);
  let release!: () => void; let received = false;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/web/upload-media/check", async route => {
    received = true; await held;
    return route.fulfill({ json: { data: { status: "available" } } });
  });
  await editor(page, [urls[0]]);
  await expect.poll(() => received).toBe(true);
  await page.getByRole("button", { name: "Убрать референс", exact: true }).click();
  release();
  await expect(page.locator(".ux2-reference-row")).toHaveCount(0);
  expect(posts).toHaveLength(0);
});

test("owner change during submit preflight prevents the old draft being sent", async ({ page }) => {
  const { posts } = await prepare(page);
  await editor(page, [urls[0]]);
  await expect(page.locator("[data-reference-availability]")).toHaveAttribute("data-reference-availability", "available");
  let release!: () => void; let received = false;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/web/upload-media/check", async route => {
    received = true; await held;
    return route.fulfill({ json: { data: { status: "available" } } });
  });
  await launch(page).click();
  await expect.poll(() => received).toBe(true);
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: 8, tg_id: 124, full_name: "Second tester", credits: 100, language: "ru", miniapp_ux2_available: true } }));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await expect(page.getByText("Second tester", { exact: true })).toBeVisible();
  release();
  await expect(page.getByRole("region", { name: "Notifications alt+T" })).toContainText("Подготовка изменилась");
  expect(posts).toHaveLength(0);
});
