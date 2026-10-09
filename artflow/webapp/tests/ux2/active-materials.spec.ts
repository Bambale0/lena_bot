import { expect, test, type Page } from "@playwright/test";

const refs = ["https://media.example.test/first.png", "https://media.example.test/second.png"];
const baseModel = { key: "selection-a", display_name: "Selection A", modes: ["text", "image"], credits: 2,
  max_refs: 2, aspect_ratios: ["1:1", "9:16"], counts: [1], quality_options: [{ value: "basic", label: "Обычное" }] };
const models = [baseModel, { ...baseModel, key: "selection-b", display_name: "One reference", max_refs: 1 }];

async function prepare(page: Page, options: { light?: boolean; owner?: number } = {}) {
  const posts: Record<string, unknown>[] = [];
  await page.addInitScript(({ light }) => {
    window.Telegram = { WebApp: { initData: "selection-fixture", colorScheme: light ? "light" : "dark",
      initDataUnsafe: { user: { id: 123, first_name: "Tester" } }, ready() {}, expand() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
    }} as any;
  }, { light: options.light || false });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ contentType: "application/javascript", body: "" }));
  await page.route("https://media.example.test/**", route => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/web/upload-media/policy") return route.fulfill({ json: { data: { image_max_bytes: 20 * 1024 * 1024, image_formats: ["jpeg", "png", "webp"] } } });
    if (path === "/api/v1/me") return route.fulfill({ json: { id: options.owner || 7, tg_id: 123, full_name: "Tester", credits: 100, language: "ru", miniapp_ux2_available: true } });
    if (path === "/api/v1/models/image") return route.fulfill({ json: models });
    if (path === "/api/v1/models/video") return route.fulfill({ json: [{ ...baseModel, key: "selection-video", display_name: "Video", modes: ["image", "text"], durations: [5], resolutions: ["720p"] }] });
    if (path.startsWith("/api/v1/generate/")) {
      posts.push(route.request().postDataJSON());
      return route.fulfill({ status: 202, json: { id: 900, task_id: "selection-900", model: posts.at(-1)?.model, gen_type: "image", status: "pending" } });
    }
    if (route.request().method() !== "GET") throw new Error(`Unexpected write to ${path}`);
    if (path.endsWith("/auth/config")) return route.fulfill({ json: { bot_username: "test_bot" } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/?ux=2");
  return posts;
}
async function openPhoto(page: Page) {
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: "Фото Создать или изменить изображение" }).click();
}
async function addPhotos(page: Page) {
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("My original idea");
  const urls = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
  await urls.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
  await urls.fill(refs.join("\n"));
}
const submit = (page: Page) => page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true });
const canonical = (page: Page) => page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:ux2:drafts:v2:7") || "{}").drafts?.image);

test("excluding the second photo keeps both but submits only the first", async ({ page }, testInfo) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("selection-b");
  await expect(submit(page)).toBeDisabled();
  const second = page.getByRole("checkbox", { name: "Использовать фото 2", exact: true });
  await expect(second).toBeVisible();
  await second.uncheck();
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(page.getByText("Не используется", { exact: true })).toBeVisible();
  await expect(submit(page)).toBeEnabled();
  await expect.poll(async () => (await canonical(page))?.referenceMaterials?.map((x: any) => x.included)).toEqual([true, false]);
  expect(posts).toHaveLength(0);
  await page.screenshot({ path: testInfo.outputPath("active-and-parked.png"), animations: "disabled" });
  await submit(page).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[0]]);
  expect(posts[0].reference_url).toBe(refs[0]);
  expect(JSON.stringify(posts[0])).not.toContain(refs[1]);
});


test("reload and returning to a larger model never auto-include a parked photo", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  const before = (await canonical(page)).referenceMaterials;
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("selection-b");
  await page.reload(); await openPhoto(page);
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).not.toBeChecked();
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("selection-a");
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).not.toBeChecked();
  expect((await canonical(page)).referenceMaterials.map((x: any) => x.id)).toEqual(before.map((x: any) => x.id));
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).check();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual(refs);
});

test("a parked photo cannot exceed the limit but may replace the active choice", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("selection-b");
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).toBeDisabled();
  await expect(page.locator(".ux2-reference-reason")).toContainText("Сейчас включить нельзя");
  await page.getByRole("checkbox", { name: "Использовать фото 1", exact: true }).uncheck();
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).check();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[1]]);
  expect(posts[0].reference_url).toBe(refs[1]);
});

test("delete removes a parked photo while exclusion alone keeps it", async ({ page }) => {
  await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await expect(page.locator(".ux2-reference-row")).toHaveCount(2);
  await page.getByRole("button", { name: "Убрать референс", exact: true }).nth(1).click();
  await expect(page.locator(".ux2-reference-row")).toHaveCount(1);
  await expect.poll(async () => (await canonical(page))?.referenceMaterials?.length).toBe(1);
  await page.reload(); await openPhoto(page);
  await expect(page.getByText("second.png", { exact: true })).toHaveCount(0);
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
});

test("manual reordering retains inclusion identity rather than array positions", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке").fill([...refs].reverse().join("\n"));
  await expect(page.getByRole("checkbox", { name: "Использовать фото 1", exact: true })).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).toBeChecked();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[0]]);
});

test("a changed price stops submission until the user confirms again", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: models.map(model => ({ ...model, credits: 7 })) }));
  await submit(page).click();
  await expect(page.getByText("Условия модели обновились.", { exact: false })).toBeVisible();
  expect(posts).toHaveLength(0);
  await expect(page.getByRole("complementary")).toContainText("7 кр.");
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[0]]);
});

test("a new zero limit blocks the preserved active input before any generation POST", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: models.map(model => ({ ...model, max_refs: 0 })) }));
  await submit(page).click();
  await expect(page.getByText("Условия модели обновились.", { exact: false })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  await expect(page.locator(".ux2-reference-row")).toHaveCount(2);
  expect(posts).toHaveLength(0);
});

test("unavailable metadata preserves the selection and never sends an unchecked request", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.route("**/api/v1/models/image", route => route.fulfill({ status: 503, json: { detail: "Metadata unavailable" } }));
  await submit(page).click();
  await expect(page.getByText("Не удалось проверить актуальные условия.", { exact: false })).toBeVisible();
  await expect(submit(page)).toBeEnabled();
  expect(posts).toHaveLength(0);
  expect((await canonical(page)).referenceMaterials.map((x: any) => x.included)).toEqual([true, false]);
  await page.unroute("**/api/v1/models/image");
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
});


test("preflight locks edits and two same-frame clicks create only one request", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let metadataRequests = 0;
  await page.route("**/api/v1/models/image", async route => { metadataRequests += 1; await gate; await route.fulfill({ json: models }); });
  await submit(page).evaluate((button: HTMLButtonElement) => { button.click(); button.click(); });
  try {
    await expect.poll(() => metadataRequests).toBe(1);
    await expect(page.getByRole("checkbox", { name: "Использовать фото 1", exact: true })).toBeDisabled();
    await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Убрать референс", exact: true }).first()).toBeDisabled();
    expect(posts).toHaveLength(0);
  } finally { release(); }
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[0]]);
});

test("upload in progress locks the selection and preserves the parked item", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let uploads = 0;
  await page.route("**/api/web/upload-media", async route => { uploads += 1; await gate; await route.fulfill({ json: { data: { url: "https://media.example.test/third.png", kind: "image", content_type: "image/png", size: 68 } } }); });
  await page.locator('input[type="file"][accept="image/*"]').setInputFiles({ name: "third.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64") });
  try {
    await expect.poll(() => uploads).toBe(1);
    await expect(page.getByRole("checkbox", { name: "Использовать фото 1", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Убрать референс", exact: true }).first()).toBeDisabled();
  } finally { release(); }
  await expect.poll(async () => (await canonical(page))?.referenceMaterials?.map((x: any) => x.included)).toEqual([true, false, true]);
  expect(posts).toHaveLength(0);
});

test("legacy interface can send only active materials and preserves parked ones on return", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Настройки", exact: true }).click();
  await page.getByRole("button", { name: "Вернуть обычный интерфейс" }).click();
  await page.getByRole("tab", { name: "Фото", exact: true }).click();
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
  await expect(page.getByText("second.png", { exact: true })).toHaveCount(0);
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[0]]);
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("tab", { name: "Настройки", exact: true }).click();
  await page.getByRole("button", { name: "Открыть предпросмотр" }).click();
  await openPhoto(page);
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).not.toBeChecked();
});

test("selected photos are owner-scoped after changing accounts", async ({ page }) => {
  await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await expect.poll(async () => (await canonical(page))?.referenceMaterials?.length).toBe(2);
  await prepare(page, { owner: 8 }); await openPhoto(page);
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("");
  await expect(page.locator(".ux2-reference-row")).toHaveCount(0);
});

test("video reference mode requires an active photo and excludes parked ones from POST", async ({ page }) => {
  const posts = await prepare(page);
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: "Видео Из описания или ваших материалов" }).click();
  await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 1", exact: true }).uncheck();
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await expect(submit(page)).toBeDisabled();
  await expect(page.getByTestId("draft-media-conflicts")).toContainText("нужно включить хотя бы одно фото");
  expect(posts).toHaveLength(0);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).check();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[1]]);
  expect(posts[0].image_url).toBe(refs[1]);
});

for (const light of [false, true]) {
  test(`selection remains readable and operable at 320px (${light ? "light" : "dark"})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 568 });
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    await prepare(page, { light }); await openPhoto(page); await addPhotos(page);
    await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
    const panel = page.locator(".ux2-reference-selection");
    await expect(panel).toBeVisible();
    const width = await panel.evaluate(node => ({ client: node.clientWidth, scroll: node.scrollWidth }));
    expect(width.scroll).toBeLessThanOrEqual(width.client);
    const target = await page.locator(".ux2-reference-toggle").first().boundingBox();
    expect(target!.height).toBeGreaterThanOrEqual(44);
    const remove = await page.locator(".ux2-reference-delete").first().boundingBox();
    expect(remove!.height).toBeGreaterThanOrEqual(44);
    await panel.screenshot({ path: testInfo.outputPath(`selection-320-${light ? "light" : "dark"}.png`), animations: "disabled" });
    expect(errors).toEqual([]);
  });
}


test("opening and resetting a template restores the ordinary selected draft", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await expect.poll(async () => (await canonical(page))?.referenceMaterials?.length).toBe(2);
  await page.goto("/?ux=2&prompt=44");
  await page.getByRole("button", { name: "Сбросить", exact: true }).click();
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Использовать фото 2", exact: true })).not.toBeChecked();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("My original idea");
  expect(posts).toHaveLength(0);
  const serialized = await page.evaluate(() => sessionStorage.getItem("apix:ux2:drafts:v2:7"));
  expect(serialized).not.toContain("Использовать промпт из библиотеки");
});


test("malformed model metadata never admits a generation and leaves the draft editable", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [null] }));
  await submit(page).click();
  await expect(page.getByText("Не удалось проверить актуальные условия.", { exact: false })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Использовать фото 1", exact: true })).toBeEnabled();
  expect(posts).toHaveLength(0);
});

test("metadata transport timeout stops before a paid request and unlocks editing", async ({ page }) => {
  const posts = await prepare(page); await openPhoto(page); await addPhotos(page);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await page.clock.install();
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let reached = false;
  await page.route("**/api/v1/models/image", async route => { reached = true; await gate; await route.abort("timedout"); });
  await submit(page).click();
  try {
    await expect.poll(() => reached).toBe(true);
    await page.clock.runFor(15_100);
    await expect(page.getByText("Не удалось проверить актуальные условия.", { exact: false })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: "Использовать фото 1", exact: true })).toBeEnabled();
    expect(posts).toHaveLength(0);
  } finally { release(); }
});
