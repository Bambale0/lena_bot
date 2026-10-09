import { expect, test, type Page } from "@playwright/test";
// Valid synthetic image for decoder and visual QA, not a user photograph.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAGAAAACACAIAAAB7vvvtAAADF0lEQVR4nO2dPW4UQRSEe1dOyQlIkEXCJbgCCbcg8zmIcO4UiQQCDmBxBwvJsiXOwAUIGi3j3Zmpntev34+3vtCe6Z3+pqp3p9eSd78ffxWyzN77AqJDQQAKAlAQgIIAFASgIAAFASgIQEEACgJQEICCABQEuPC+AB3+3H46/eGLd1f9I++y7wfNqpnSqSl3xaCdxmNWyJogwbRlUcqdIANSCpK1RnZWPkE9a4rg3HyCjEkmqPMtSTBCMkH2UBCAggAUBKAgAAUBkgnq38HYOkIyQfbkE9QTIsG5+QQVqSNudwwh64ZZpfHBqqeVuRPUMvPON77cCTrAbzXcyF0xAygIQEEACgJQEICCABQEoCDAcEFX159Hv8RQxgqqdlI7YsUAAwVNg5M3RKME5TVyhF3FkiobImjJRUZHXKQB+oLWY5IuRMqC0s0f4lCxXBI1BbXPPJEjNUFB5nz97avugG7vYiOEVju6jnQEyWar60g9O5Xn+TlIUZaCoJ4gaIVoUHxKv6AIa/OsHS1l/hXrVDwuO5UuQVrxGRRDFXdyQWHLtekAiH/FKgLdo8tVEQpyj0+7nU6PURJUAkifRSJo3EwaR94aip4QbRbkfp9tlp4DgSpWWb8BYjviE7cJco+PPRsEmdlZeqHOcslOD1exyqkjlaVHMEirIN9yGS/MU4ImqIR5QGsSdLbxKS1/ae9r5/WrlyOG/fj+Q+ORcStWhtnZxO7m+5eVX/+4/Wl2KacMFfT28k3LYWsJesZ2Sil3D/cthwWtWIRyVRYFOcbHzE5LiMIlKE52KvOCfFcfS2CIZgSdQ7naCVQxLzvrIToW5BUf3+ysOHoi6HyWnnZCVCzC0rMUov+CzrNcEOcEhbIzG6J/grj6LLEvLNeE0xC5VSygnVn2LvGJbOcoRGDDzOYiAnLYTnOoWHw7U6wFZbFzuE5TQVnsTAnxqBGTejvtBGWMTzETlNTO3cO90b+uafwSKiBcgwAUBKAgAAUBKAhAQQAKAlAQgIIAFASgIAAFASgIQEEACgJQEICCABQEoCAABQEoCPAXcw8CIf4jKTgAAAAASUVORK5CYII=", "base64");
const model = { key: "upload-image", display_name: "Upload image", modes: ["text", "image"], credits: 2,
  max_refs: 4, aspect_ratios: ["1:1"], counts: [1], quality_options: [{ value: "basic", label: "Обычное" }] };
const file = (name: string) => ({ name, mimeType: "image/png", buffer: PNG });
const picker = (page: Page) => page.locator('input[type="file"][accept="image/*"]').first();
const submit = (page: Page) => page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true });
async function openPhoto(page: Page) {
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: "Фото Создать или изменить изображение" }).click();
}
async function prepare(page: Page, options: { light?: boolean } = {}) {
  const uploads: string[] = []; const posts: Record<string, unknown>[] = [];
  const state = { owner: 7, failSecond: false, brokenPreview: false, policyBytes: 20 * 1024 * 1024, malformed: false };
  await page.addInitScript(({ light }) => { window.Telegram = { WebApp: { initData: "uploads-fixture", colorScheme: light ? "light" : "dark",
    initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
  }} as any; }, { light: options.light || false });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "", contentType: "application/javascript" }));
  await page.route("https://media.example.test/**", route => route.fulfill(state.brokenPreview ? { status: 404, body: "missing" } : { contentType: "image/png", body: PNG }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/me") return route.fulfill({ json: { id: state.owner, tg_id: 123, credits: 100, language: "ru", miniapp_ux2_available: true } });
    if (path === "/api/v1/models/image") return route.fulfill({ json: [model] });
    if (path === "/api/v1/models/video") return route.fulfill({ json: [] });
    if (path === "/api/web/upload-media/policy") return route.fulfill({ json: { ok: true, data: { image_max_bytes: state.policyBytes, image_formats: ["jpeg", "png", "webp"] } } });
    if (path === "/api/web/upload-media") {
      const name = /filename="([^"]+)"/.exec(route.request().postDataBuffer()?.toString() || "")?.[1] || "unknown";
      uploads.push(name);
      if (state.failSecond && name === "second.png") return route.fulfill({ status: 503, json: { error: "Temporary upload failure" } });
      return route.fulfill({ json: { ok: true, data: state.malformed ? {} : { url: `https://media.example.test/${name}`, kind: "image", content_type: "image/png", size: PNG.length } } });
    }
    if (path.startsWith("/api/v1/generate/")) { posts.push(route.request().postDataJSON()); return route.fulfill({ status: 202, json: { id: 900, model: model.key, status: "pending", gen_type: "image" } }); }
    if (route.request().method() !== "GET") throw new Error(`Unexpected write ${path}`);
    if (path.endsWith("/auth/config")) return route.fulfill({ json: { bot_username: "test_bot" } });
    return route.fulfill({ json: [] });
  });
  await page.goto("/?ux=2"); await openPhoto(page);
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Мой черновик не должен потеряться");
  return { uploads, posts, state };
}

test("second file failure retains the first success and the third file", async ({ page }) => {
  const { uploads, posts, state } = await prepare(page); state.failSecond = true;
  await picker(page).setInputFiles([file("first.png"), file("second.png"), file("third.png")]);
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
  await expect(page.getByText("third.png", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Повторить загрузку фото 2", exact: true })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  expect(uploads).toEqual(["first.png", "second.png", "third.png"]);
  expect(posts).toHaveLength(0);
  state.failSecond = false;
  await page.getByRole("button", { name: "Повторить загрузку фото 2", exact: true }).click();
  await expect(submit(page)).toBeEnabled();
  expect(uploads).toEqual(["first.png", "second.png", "third.png", "second.png"]);
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual(["first.png", "second.png", "third.png"].map(name => `https://media.example.test/${name}`));
});

const canonical = (page: Page) => page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:ux2:drafts:v3:7") || "{}").drafts?.image);
const replacePicker = (page: Page, n = 1) => page.getByLabel(`Заменить фото ${n}`, { exact: true });

test("failed replacement retains original and parked state, retry changes only that file", async ({ page }) => {
  const { state, uploads, posts } = await prepare(page);
  await picker(page).setInputFiles(file("first.png"));
  await expect(submit(page)).toBeEnabled();
  await page.getByRole("checkbox", { name: "Использовать фото 1", exact: true }).uncheck();
  const id = (await canonical(page)).referenceMaterials[0].id;
  state.failSecond = true;
  await replacePicker(page).setInputFiles(file("second.png"));
  await expect(page.getByRole("button", { name: "Оставить прежнее", exact: true })).toBeVisible();
  expect((await canonical(page)).referenceMaterials[0]).toMatchObject({ id, url: "https://media.example.test/first.png", included: false });
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
  state.failSecond = false;
  await page.getByRole("button", { name: "Повторить загрузку фото 1", exact: true }).click();
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect.poll(async () => (await canonical(page))?.referenceMaterials[0]?.upload).toBeUndefined();
  await page.reload(); await openPhoto(page);
  expect((await canonical(page)).referenceMaterials[0]).toMatchObject({ id, url: "https://media.example.test/second.png", included: false });
  await expect(page.getByRole("checkbox", { name: "Использовать фото 1", exact: true })).not.toBeChecked();
  expect(uploads).toEqual(["first.png", "second.png", "second.png"]); expect(posts).toHaveLength(0);
});

test("keeping the original after a failed replacement needs no new upload", async ({ page }) => {
  const { state, posts, uploads } = await prepare(page);
  await picker(page).setInputFiles(file("first.png")); await expect(submit(page)).toBeEnabled();
  state.failSecond = true; await replacePicker(page).setInputFiles(file("second.png"));
  await page.getByRole("button", { name: "Оставить прежнее", exact: true }).click();
  await expect(submit(page)).toBeEnabled(); await submit(page).click();
  await expect.poll(() => posts.length).toBe(1); expect(posts[0].reference_urls).toEqual(["https://media.example.test/first.png"]);
  expect(uploads).toHaveLength(2);
});

test("reload keeps acknowledged files and requests the interrupted source again", async ({ page }) => {
  const { posts } = await prepare(page);
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  let waiting = false;
  await page.route("**/api/web/upload-media", async route => {
    if (!(route.request().postDataBuffer()?.toString().includes('filename="second.png"'))) return route.fallback();
    waiting = true; await gate; await route.fulfill({ json: { data: { url: "https://media.example.test/second.png", kind: "image", content_type: "image/png", size: PNG.length } } }).catch(() => undefined);
  });
  await picker(page).setInputFiles([file("first.png"), file("second.png"), file("third.png")]);
  await expect.poll(() => waiting).toBe(true);
  await expect.poll(async () => (await canonical(page))?.referenceMaterials[0]?.url).toBe("https://media.example.test/first.png");
  const stored = await page.evaluate(() => sessionStorage.getItem("apix:ux2:drafts:v3:7")); expect(stored).not.toContain("blob:");
  await page.reload(); release(); await openPhoto(page);
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
  await expect(page.getByText("Загрузка прервалась. Выберите этот файл снова.", { exact: true })).toHaveCount(2);
  await expect(submit(page)).toBeDisabled();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toHaveValue("Мой черновик не должен потеряться");
  await expect(page.getByLabel("Выбрать снова фото 2", { exact: true })).toBeVisible(); expect(posts).toHaveLength(0);
});

test("cancel remains reachable during upload and late response never resurrects the photo", async ({ page }) => {
  const { posts } = await prepare(page);
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; }); let requested = false; let settled = false;
  await page.route("**/api/web/upload-media", async route => {
    requested = true; await gate;
    await route.fulfill({ json: { data: { url: "https://media.example.test/late.png", kind: "image", content_type: "image/png", size: PNG.length } } }).catch(() => undefined);
    settled = true;
  });
  await picker(page).setInputFiles(file("first.png")); await expect.poll(() => requested).toBe(true);
  await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Отменить загрузку фото 1", exact: true }).click();
  release(); await expect.poll(() => settled).toBe(true);
  await expect(page.locator(".ux2-photo-row")).toHaveCount(0); await expect(submit(page)).toBeEnabled(); expect(posts).toHaveLength(0);
});

test("leaving the editor does not duplicate or discard an active upload", async ({ page }) => {
  const { posts } = await prepare(page);
  let release!: () => void; const gate = new Promise<void>(resolve => { release = resolve; }); let requested = 0;
  await page.route("**/api/web/upload-media", async route => { requested++; await gate; return route.fulfill({ json: { data: { url: "https://media.example.test/first.png", kind: "image", content_type: "image/png", size: PNG.length } } }); });
  await picker(page).setInputFiles(file("first.png")); await expect.poll(() => requested).toBe(1);
  await page.getByRole("tab", { name: "Работы", exact: true }).click(); release(); await openPhoto(page);
  await expect(page.getByText("first.png", { exact: true })).toBeVisible(); await expect(submit(page)).toBeEnabled();
  expect(requested).toBe(1); expect(posts).toHaveLength(0);
});

for (const failure of ["too_large", "invalid_file", "empty_file"]) {
  test(`file validation ${failure} stops before the upload POST`, async ({ page }) => {
    const { state, uploads, posts } = await prepare(page);
    if (failure === "too_large") state.policyBytes = PNG.length - 1;
    const chosen = failure === "invalid_file" ? { ...file("bad.png"), buffer: Buffer.from("not a picture") }
      : failure === "empty_file" ? { ...file("empty.png"), buffer: Buffer.alloc(0) } : file("first.png");
    await picker(page).setInputFiles(chosen);
    await expect(page.locator('.ux2-photo-row[data-upload-state="error"]')).toHaveCount(1);
    expect(uploads).toHaveLength(0); expect(posts).toHaveLength(0);
    await expect(submit(page)).toBeDisabled(); await expect(page.getByLabel("Выбрать снова фото 1", { exact: true })).toBeVisible();
  });
}

test("too many selected files are not silently sliced or uploaded", async ({ page }) => {
  const { uploads } = await prepare(page);
  await picker(page).setInputFiles([file("1.png"),file("2.png"),file("3.png"),file("4.png"),file("5.png")]);
  await expect(page.getByText(/Можно добавить фото: 4/)).toBeVisible();
  expect(uploads).toHaveLength(0); await expect(page.locator(".ux2-photo-row")).toHaveCount(0);
});

test("policy outage and malformed upload response preserve the draft without generation", async ({ page }) => {
  const { state, uploads, posts } = await prepare(page);
  await page.route("**/api/web/upload-media/policy", route => route.fulfill({ status: 503, json: { error: "Unavailable" } }));
  await picker(page).setInputFiles(file("first.png"));
  await expect(page.getByRole("button", { name: "Повторить загрузку фото 1", exact: true })).toBeVisible(); expect(uploads).toHaveLength(0);
  await page.unroute("**/api/web/upload-media/policy"); state.malformed = true;
  await page.getByRole("button", { name: "Повторить загрузку фото 1", exact: true }).click();
  await expect(page.getByText("Сервис не подтвердил загрузку фото. Повторите этот файл.", { exact: true })).toBeVisible();
  expect(uploads).toHaveLength(1); expect(posts).toHaveLength(0); await expect(submit(page)).toBeDisabled();
});

test("excluding a failed photo allows only the acknowledged photos to be sent", async ({ page }) => {
  const { state, posts } = await prepare(page); state.failSecond = true;
  await picker(page).setInputFiles([file("first.png"),file("second.png"),file("third.png")]);
  await expect(page.getByRole("button", { name: "Повторить загрузку фото 2", exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await expect(submit(page)).toBeEnabled(); await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual(["https://media.example.test/first.png","https://media.example.test/third.png"]);
  expect((await canonical(page)).referenceMaterials).toHaveLength(3);
});

test("identical names and URLs have independent identity and selection", async ({ page }) => {
  const { posts } = await prepare(page);
  await picker(page).setInputFiles([file("first.png"),file("first.png")]); await expect(submit(page)).toBeEnabled();
  const items=(await canonical(page)).referenceMaterials; expect(items).toHaveLength(2); expect(items[0].id).not.toBe(items[1].id);
  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1); expect(posts[0].reference_urls).toEqual(["https://media.example.test/first.png"]);
});

for (const light of [false,true]) {
  test(`photo preview and retry controls fit at 320px (${light ? "light" : "dark"})`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 568 });
    const { state }=await prepare(page,{light});state.failSecond=true;
    await picker(page).setInputFiles([file("first.png"),file("second.png")]);
    await expect(page.getByRole("button",{name:"Повторить загрузку фото 2",exact:true})).toBeVisible();
    await page.locator(".ux2-reference-selection").scrollIntoViewIfNeeded();
    const size=await page.locator(".apix-shell > main").evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth}));expect(size.scroll).toBeLessThanOrEqual(size.width);
    await page.screenshot({path:testInfo.outputPath(`uploads-${light ? "light" : "dark"}-320.png`),animations:"disabled"});
    await page.getByRole("button",{name:"Открыть фото 1",exact:true}).click();
    await expect(page.getByRole("dialog",{name:"Просмотр фото"})).toBeVisible();
    await expect(page.getByRole("dialog").locator("img")).toHaveAttribute("src","https://media.example.test/first.png");
    await page.getByRole("dialog").getByRole("button",{name:"Закрыть",exact:true}).click();
  });
}

test("broken thumbnail does not erase the uploaded original", async ({ page }) => {
  const { state }=await prepare(page);state.brokenPreview=true;
  await picker(page).setInputFiles(file("first.png"));await expect(submit(page)).toBeEnabled();
  await expect(page.getByText("Нет превью",{exact:true})).toBeVisible();
  expect((await canonical(page)).referenceMaterials[0].url).toBe("https://media.example.test/first.png");
  await page.getByRole("button",{name:"Открыть фото 1",exact:true}).click();
  await expect(page.getByText("Не удалось открыть превью. Файл сохранён в черновике.",{exact:true})).toBeVisible();
});


test("successful photo renders a decoded thumbnail and original", async ({ page }) => {
  await prepare(page);
  await picker(page).setInputFiles(file("first.png"));
  await expect(submit(page)).toBeEnabled();
  const image = page.getByRole("button", { name: "Открыть фото 1", exact: true }).locator("img");
  await expect(image).toBeVisible();
  expect(await image.evaluate(async (element: HTMLImageElement) => { try { await element.decode(); return element.naturalWidth > 0; } catch { return false; } })).toBe(true);
  await page.getByRole("button", { name: "Открыть фото 1", exact: true }).click();
  const original=page.getByRole("dialog").locator("img");
  expect(await original.evaluate(async (element: HTMLImageElement) => { try { await element.decode(); return element.naturalWidth > 0; } catch { return false; } })).toBe(true);
});
