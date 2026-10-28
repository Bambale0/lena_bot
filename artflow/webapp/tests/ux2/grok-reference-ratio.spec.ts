import { expect, test, type Page } from "@playwright/test";

const refs = ["https://media.example.test/first.png", "https://media.example.test/second.png"];
const textModel = "grok-imagine/text-to-video";
const photoModel = "grok-imagine/image-to-video";
const videoModels = [
  { key: textModel, display_name: "Grok Imagine Video", credits: 0.6, modes: ["text"],
    aspect_ratios: ["16:9", "9:16"], durations: [10], resolutions: ["720p"], max_refs: 0 },
  { key: photoModel, display_name: "Grok Imagine Video", credits: 0.7, modes: ["image"],
    aspect_ratios: ["16:9", "9:16"], aspect_ratio_min_refs: 2, durations: [10], resolutions: ["720p"], max_refs: 7 },
];

async function prepare(page: Page) {
  const quotes: Record<string, unknown>[] = [];
  const launches: Record<string, unknown>[] = [];
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: "grok-ratio-fixture", colorScheme: "dark",
      initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
    } } as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("https://media.example.test/**", route => route.fulfill({ contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Tester", credits: 100, language: "ru", miniapp_ux2_available: true });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/models/video")) return json(videoModels);
    if (path === "/api/web/upload-media/check") return json({ ok: true, data: { status: "available" } });
    if (path === "/api/web/upload-media/policy") return json({ data: { image_max_bytes: 20 * 1024 * 1024, image_formats: ["jpeg", "png", "webp"] } });
    if (path === "/api/v1/generate/video/quote") {
      quotes.push(route.request().postDataJSON());
      return json({ cost_credits: 7, balance_credits: 100, can_run: true, output_seconds: 10, reference_seconds: 0, billable_seconds: 10 });
    }
    if (path === "/api/v1/generate/video") {
      launches.push(route.request().postDataJSON());
      return json({ id: 900, model: launches.at(-1)?.model, gen_type: "video", status: "pending" });
    }
    return json([]);
  });
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Плавное движение камеры");
  return { quotes, launches };
}

const submit = (page: Page) => page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true });
const ratio = (page: Page) => page.getByRole("button", { name: "9:16", exact: true });
const confirmation = (page: Page) => page.getByRole("dialog", { name: "Стоимость видео", exact: true });

test("Grok photo format follows active photos 1 to 2 to 1 through quote and launch", async ({ page }) => {
  const { quotes, launches } = await prepare(page);
  const links = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
  await links.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
  await links.fill(refs[0]);

  await expect(ratio(page)).toHaveCount(0);
  await submit(page).click();
  await expect(confirmation(page)).toBeVisible();
  expect(quotes.at(-1)).toMatchObject({ model: photoModel, mode: "image", aspect_ratio: null, image_url: refs[0], reference_urls: [] });
  expect(launches).toHaveLength(0);
  await confirmation(page).getByRole("button", { name: "Закрыть", exact: true }).click();

  await links.fill(refs.join("\n"));
  await expect(ratio(page)).toBeVisible();
  await ratio(page).click();
  await submit(page).click();
  await expect(confirmation(page)).toBeVisible();
  expect(quotes.at(-1)).toMatchObject({ model: photoModel, mode: "image", aspect_ratio: "9:16", image_url: refs[0], reference_urls: [refs[1]] });
  expect(launches).toHaveLength(0);
  await confirmation(page).getByRole("button", { name: "Закрыть", exact: true }).click();

  await page.getByRole("checkbox", { name: "Использовать фото 2", exact: true }).uncheck();
  await expect(page.getByText("second.png", { exact: true })).toBeVisible();
  await expect(ratio(page)).toHaveCount(0);
  await submit(page).click();
  await expect(confirmation(page)).toBeVisible();
  expect(quotes.at(-1)).toMatchObject({ model: photoModel, mode: "image", aspect_ratio: null, image_url: refs[0], reference_urls: [] });
  await confirmation(page).getByRole("button", { name: "Запустить за 7 💋", exact: true }).click();
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).toEqual({ ...quotes.at(-1), quoted_credits: 7 });
  expect(launches[0].aspect_ratio).toBeNull();
});

test("Grok text sibling retains the chosen format without photo references", async ({ page }) => {
  const { quotes, launches } = await prepare(page);
  await page.getByRole("button", { name: "По тексту", exact: true }).click();
  await expect(ratio(page)).toBeVisible();
  await ratio(page).click();
  await submit(page).click();
  await expect(confirmation(page)).toBeVisible();
  expect(quotes.at(-1)).toMatchObject({ model: textModel, mode: "text", aspect_ratio: "9:16", image_url: null, reference_urls: [] });
  await confirmation(page).getByRole("button", { name: "Запустить за 7 💋", exact: true }).click();
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).toEqual({ ...quotes.at(-1), quoted_credits: 7 });
});

for (const { name, existingUrl, distinct } of [
  { name: "a URL and its uploaded file", existingUrl: true, distinct: false },
  { name: "two uploads of the same content", existingUrl: false, distinct: false },
  { name: "two uploads of distinct content", existingUrl: false, distinct: true },
]) {
  test(`Grok counts ${distinct ? "two effective photos" : "one effective photo"} for ${name}`, async ({ page }) => {
    const { quotes, launches } = await prepare(page);
    const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64");
    let uploads = 0;
    await page.route("**/api/web/upload-media", route => {
      uploads++;
      return route.fulfill({ json: { data: { url: refs[distinct ? uploads - 1 : 0], kind: "image", content_type: "image/png", size: png.length } } });
    });
    if (existingUrl) {
      const links = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
      await links.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
      await links.fill(refs[0]);
    }
    const files = (existingUrl ? ["duplicate.png"] : ["first-copy.png", "second-copy.png"])
      .map((name, index) => ({ name, mimeType: "image/png", buffer: distinct && index ? Buffer.concat([png, Buffer.from("\n")]) : png }));
    await page.locator('input[type="file"][accept="image/*"]').setInputFiles(files);
    await expect.poll(() => uploads).toBe(files.length);
    await expect(page.locator(".ux2-reference-row")).toHaveCount(2);
    await expect(submit(page)).toBeEnabled();
    if (distinct) {
      await expect(ratio(page)).toBeVisible();
      await ratio(page).click();
    } else await expect(ratio(page)).toHaveCount(0);

    await submit(page).click();
    await expect(confirmation(page)).toBeVisible();
    expect(quotes.at(-1)).toMatchObject({ model: photoModel, mode: "image", aspect_ratio: distinct ? "9:16" : null,
      image_url: refs[0], reference_urls: distinct ? [refs[1]] : [] });
    expect(launches).toHaveLength(0);
    await confirmation(page).getByRole("button", { name: "Запустить за 7 💋", exact: true }).click();
    await expect.poll(() => launches.length).toBe(1);
    expect(launches[0]).toEqual({ ...quotes.at(-1), quoted_credits: 7 });
  });
}
