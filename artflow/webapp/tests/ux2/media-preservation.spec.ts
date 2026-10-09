import { expect, test, type Page } from "@playwright/test";

const photo = { key: "fixture-photo-a", display_name: "Photo A", modes: ["text", "image"], credits: 2,
  max_refs: 3, aspect_ratios: ["1:1", "9:16"], aspect_ratio_modes: ["text", "image"],
  counts: [1], quality_options: [{ value: "basic", label: "Обычное" }] };
const images = [photo, { ...photo, key: "fixture-photo-b", display_name: "Photo B" },
  { ...photo, key: "fixture-one", display_name: "One photo", max_refs: 1 },
  { ...photo, key: "fixture-text", display_name: "Text only", modes: ["text"], max_refs: 0 }];
const videos = [
  { ...photo, key: "fixture-video-a", display_name: "Video A", modes: ["video", "image", "text"], supports_video_input: true, durations: [5, 10], resolutions: ["720p"], max_refs_with_video: 2, max_audio_ids: 2, max_character_ids: 2 },
  { ...photo, key: "fixture-video-b", display_name: "Video B", modes: ["text"], supports_video_input: false, durations: [5, 10], resolutions: ["720p"], max_refs: 0 },
];
const refs = ["https://media.example.test/first.png", "https://media.example.test/second.png"];

async function prepare(page: Page, enabled = true) {
  const posts: Record<string, unknown>[] = [];
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: "ux2-test", initDataUnsafe: { user: { id: 123, first_name: "Test" } }, colorScheme: "dark",
      ready() {}, expand() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
    }} as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ contentType: "application/javascript", body: "" }));
  await page.route("https://media.example.test/**", route => route.fulfill({ contentType: "image/png", body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/me") return route.fulfill({ json: { id: 7, tg_id: 123, credits: 100, language: "ru", full_name: "Test", miniapp_ux2_available: enabled } });
    if (path === "/api/v1/models/image") return route.fulfill({ json: images });
    if (path === "/api/v1/models/video") return route.fulfill({ json: videos });
    if (path.startsWith("/api/v1/generate/")) {
      posts.push(route.request().postDataJSON());
      return route.fulfill({ status: 202, json: { id: 900, task_id: "test-900", status: "pending", gen_type: path.endsWith("image") ? "image" : "video", model: posts.at(-1)?.model } });
    }
    if (path.endsWith("/auth/config")) return route.fulfill({ json: { bot_username: "test_bot" } });
    return route.fulfill({ json: [] });
  });
  await page.goto(enabled ? "/?ux=2" : "/");
  return posts;
}
async function openEditor(page: Page, kind: "photo" | "video" = "photo") {
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: kind === "photo" ? "Фото Создать или изменить изображение" : "Видео Из описания или ваших материалов" }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Сохранить мою идею");
}
async function addReferences(page: Page) {
  const field = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
  await field.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
  await field.fill(refs.join("\n"));
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
}
const modelSelect = (page: Page) => page.getByRole("combobox", { name: "Модель", exact: true });
const submit = (page: Page) => page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true });
const stored = (page: Page) => page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:ux2:drafts:v1:7") || "{}").drafts);

test("compatible model switch keeps all references, text and compatible format", async ({ page }) => {
  const posts = await prepare(page); await openEditor(page); await addReferences(page);
  await page.getByRole("button", { name: "9:16", exact: true }).click();
  await modelSelect(page).selectOption("fixture-photo-b");
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect.poll(async () => (await stored(page))?.image?.referenceUrls).toEqual(refs);
  expect((await stored(page)).image.aspectRatio).toBe("9:16");
  await submit(page).click();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toMatchObject({ model: "fixture-photo-b", reference_urls: refs, reference_url: refs[0], aspect_ratio: "9:16", prompt: "Сохранить мою идею" });
});

test("smaller capacity does not truncate inputs and blocks launch", async ({ page }, testInfo) => {
  const posts = await prepare(page); await openEditor(page); await addReferences(page);
  await modelSelect(page).selectOption("fixture-one");
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  await expect(page.getByTestId("draft-media-conflicts")).toContainText("Материалы сохранены");
  await expect(page.getByTestId("draft-media-conflicts").locator("p")).toHaveCount(1);
  expect(posts).toHaveLength(0);
  await page.screenshot({ path: testInfo.outputPath("preserved-conflict.png"), animations: "disabled" });
  await page.reload(); await openEditor(page);
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  await page.getByRole("button", { name: "Убрать референс", exact: true }).nth(1).click();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual([refs[0]]);
});

test("text-only round trip retains photos without sending incompatible input", async ({ page }) => {
  const posts = await prepare(page); await openEditor(page); await addReferences(page);
  await modelSelect(page).selectOption("fixture-text");
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  await expect(page.locator('input[type="file"][accept="image/*"]')).toBeDisabled();
  await modelSelect(page).selectOption("fixture-photo-a");
  await expect(submit(page)).toBeEnabled();
  expect((await stored(page)).image.referenceUrls).toEqual(refs);
  expect(posts).toHaveLength(0);
});


async function addVideo(page: Page) {
  const field = page.getByPlaceholder("Опционально: https://…/motion.mp4");
  await field.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
  await field.fill("https://media.example.test/source.mp4");
  await page.getByLabel("Старт, сек").fill("2");
  await page.getByLabel("Конец, сек").fill("7");
}

test("video and trim survive an unsupported model and mode round trip", async ({ page }) => {
  const posts = await prepare(page); await openEditor(page, "video"); await addVideo(page);
  await modelSelect(page).selectOption("fixture-video-b");
  await expect(page.getByText("source.mp4", { exact: true })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  await expect(page.getByTestId("draft-media-conflicts")).toContainText("не принимает исходное видео");
  expect((await stored(page)).video).toMatchObject({ videoUrl: "https://media.example.test/source.mp4", videoStart: 2, videoEnd: 7 });
  await modelSelect(page).selectOption("fixture-video-a");
  await page.locator("button").filter({ hasText: /^Видео$/ }).click();
  await expect(page.getByLabel("Старт, сек")).toHaveValue("2");
  await expect(page.getByLabel("Конец, сек")).toHaveValue("7");
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0]).toMatchObject({ video_url: "https://media.example.test/source.mp4", video_start: 2, video_end: 7, mode: "video" });
});

test("changing ordinary photo mode never erases its reference list", async ({ page }) => {
  await prepare(page); await openEditor(page); await addReferences(page);
  await page.getByRole("button", { name: "Фото", exact: true }).click();
  await page.getByRole("button", { name: "Текст", exact: true }).click();
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect.poll(async () => (await stored(page)).image.referenceUrls).toEqual(refs);
});

test("audio and character identifiers remain visible when the new model cannot use them", async ({ page }) => {
  const posts = await prepare(page); await openEditor(page, "video");
  await page.getByRole("textbox", { name: /^Audio ID/ }).fill("audio-one");
  await page.getByRole("textbox", { name: /^Character IDs/ }).fill("character-one");
  await modelSelect(page).selectOption("fixture-video-b");
  await expect(page.getByRole("textbox", { name: /^Audio ID/ })).toHaveValue("audio-one");
  await expect(page.getByRole("textbox", { name: /^Character IDs/ })).toHaveValue("character-one");
  await expect(submit(page)).toBeDisabled(); expect(posts).toHaveLength(0);
  await page.getByRole("textbox", { name: /^Audio ID/ }).fill("");
  await page.getByRole("textbox", { name: /^Character IDs/ }).fill("");
  await expect(submit(page)).toBeEnabled();
});

test("model and mode changes wait for the current upload to finish", async ({ page }) => {
  await prepare(page); await openEditor(page);
  let release: () => void = () => undefined;
  const uploaded = new Promise<void>(resolve => { release = resolve; });
  let requested = false;
  await page.route("**/api/web/upload-media", async route => {
    requested = true; await uploaded;
    await route.fulfill({ json: { data: { url: refs[0], kind: "image", content_type: "image/png", size: 68 } } });
  });
  await page.locator('input[type="file"][accept="image/*"]').setInputFiles({ name: "first.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64") });
  await expect.poll(() => requested).toBe(true);
  await expect(modelSelect(page)).toBeDisabled();
  await expect(page.getByRole("button", { name: "Фото", exact: true })).toBeDisabled();
  await expect(submit(page)).toBeDisabled();
  release();
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
  await expect(modelSelect(page)).toBeEnabled();
  await modelSelect(page).selectOption("fixture-photo-b");
  await expect(page.getByText("first.png", { exact: true })).toBeVisible();
});

test("zero combined capacity retains photos and blocks video submission", async ({ page }) => {
  const posts = await prepare(page);
  await page.route("**/api/v1/models/video", route => route.fulfill({ json: [{ ...videos[0], max_refs_with_video: 0 }] }));
  await page.reload(); await openEditor(page, "video");
  await page.getByRole("button", { name: "Фото", exact: true }).click();
  await addReferences(page); await addVideo(page);
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(submit(page)).toBeDisabled();
  expect((await stored(page)).video.referenceUrls).toEqual(refs);
  expect(posts).toHaveLength(0);
});

test("ordinary legacy UI remains outside the preservation preview", async ({ page }) => {
  await prepare(page, false);
  await expect(page.getByRole("tablist").getByRole("tab")).toHaveCount(8);
  await page.getByRole("tab", { name: "Фото", exact: true }).click();
  await addReferences(page);
  await modelSelect(page).selectOption("fixture-photo-b");
  await expect(page.getByText("first.png", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("draft-media-conflicts")).toHaveCount(0);
});


test("narrow screen preserves the complete reference list and a readable conflict", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await prepare(page); await openEditor(page); await addReferences(page);
  await modelSelect(page).selectOption("fixture-one");
  const conflict = page.getByTestId("draft-media-conflicts");
  await expect(conflict).toBeVisible();
  await conflict.scrollIntoViewIfNeeded();
  const dimensions = await conflict.evaluate(node => ({ content: node.scrollWidth, visible: node.clientWidth }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.visible);
  await expect.poll(async () => (await stored(page)).image.referenceUrls).toEqual(refs);
  await page.screenshot({ path: testInfo.outputPath("media-conflict-320.png"), animations: "disabled" });
});


test("explicit video text mode does not silently ignore the retained photos", async ({ page }) => {
 const posts = await prepare(page); await openEditor(page, "video");
 await page.getByRole("button", { name: "Фото", exact: true }).click(); await addReferences(page);
 await page.getByRole("button", { name: "Текст", exact: true }).click();
 await expect(page.getByText("second.png", { exact: true })).toBeVisible();
 await expect(submit(page)).toBeDisabled();
 await expect(page.getByTestId("draft-media-conflicts")).toContainText("не использует фото");
 expect(posts).toHaveLength(0);
 await page.getByRole("button", { name: "Фото", exact: true }).click();
 await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
 expect(posts[0]).toMatchObject({ mode: "image", reference_urls: refs });
});

for (const auto of [false, true]) {
 test(`multimodal and automatic contracts keep supported photos (auto=${auto})`, async ({ page }) => {
  const posts = await prepare(page);
  await page.route("**/api/v1/models/video", route => route.fulfill({ json: [{ ...videos[0], modes: auto ? ["text", "image", "video"] : ["text", "multimodal"], auto_route_by_inputs: auto }] }));
  await page.reload(); await openEditor(page, "video"); await addReferences(page);
  await expect(submit(page)).toBeEnabled();
  await submit(page).click(); await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].reference_urls).toEqual(refs);
 });
}
