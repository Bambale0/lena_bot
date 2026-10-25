import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const landing = path.resolve(process.cwd(), "../landing");
const model = "bytedance/seedance-2-5";
async function fixture(page: Page, launchStatus = 202, locked = false) {
  const quotes: Record<string, unknown>[] = [], launches: Record<string, unknown>[] = [];
  await page.route("**/studio.html?*", r => r.fulfill({ path: path.join(landing, "studio.html"), contentType: "text/html" }));
  await page.route("**/js/*.js?*", r => r.fulfill({ path: path.join(landing, "js", new URL(r.request().url()).pathname.split("/").pop()!), contentType: "text/javascript" }));
  await page.route("**/css/prototype-premium.css?*", r => r.fulfill({ path: path.join(landing, "css/prototype-premium.css"), contentType: "text/css" }));
  await page.route("**/api/web/**", r => {
    const url = new URL(r.request().url());
    const json = (data: unknown) => r.fulfill({ json: { ok: true, data } });
    if (url.pathname.endsWith("/me")) return json({ id: 7, credits: 100, full_name: "Reader" });
    if (url.pathname.endsWith("/uploads/reference")) return json({ url: "https://example.test/uploaded-reader.jpg" });
    if (url.pathname.endsWith("/models/video")) return json([{ key: model, name: "Seedance 2.5", type: "video", durations: [5, 10, 15], resolutions: ["480p", "720p"], aspect_ratios: ["9:16", "16:9"], credits: 2, active: true }]);
    if (url.pathname.endsWith("/feed/42")) return json({ id: 42, type: "video", model, original_duration: 10, original_resolution: "720p", original_aspect_ratio: "16:9", source_has_video_reference: locked, result_url: "https://example.test/public.mp4" });
    if (url.pathname.endsWith("/remix/quote")) {
      const body = r.request().postDataJSON(); quotes.push(body);
      // Exact-recipe admission forbids consumer controls/references besides photos.
      if (body.audio_ids?.length || body.character_ids?.length || body.seed != null || body.video_url || !body.image_url) {
        return r.fulfill({ status: 422, json: { detail: "Exact recipe accepts only reader photos and duration override" } });
      }
      const seconds = locked ? 7 : (body.duration_override || 10);
      return json({ cost_credits: seconds * 2 + (launchStatus === 409 && launches.length ? 5 : 0), can_run: true, output_seconds: seconds, duration_options: locked ? [] : [5, 10, 15], default_duration: 10, effective_duration: seconds, duration_lock_reason: locked ? "Длительность определяется исходным видео." : null });
    }
    if (url.pathname.endsWith("/remix")) {
      const body = r.request().postDataJSON(); launches.push(body);
      if (body.audio_ids?.length || body.character_ids?.length || body.seed != null || body.video_url || !body.image_url) {
        return r.fulfill({ status: 422, json: { detail: "Exact recipe accepts only reader photos and duration override" } });
      }
      if (launchStatus !== 202 && (launchStatus !== 409 || launches.length === 1)) return r.fulfill({ status: launchStatus, json: { ok: false, error: "Response unavailable" } });
      return json({ id: 91, status: "pending" });
    }
    if (url.pathname.includes("/prompts")) return json({ items: [] });
    if (url.pathname.includes("/transactions")) return json({ transactions: [], pending: [] });
    if (url.pathname.includes("/auth/config")) return json({});
    return json([]);
  });
  page.on("dialog", d => d.accept());
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}&feed_remix=42&ref=${encodeURIComponent("https://example.test/reader.jpg")}`);
  return { quotes, launches };
}

async function launch(page: Page) {
  await page.locator("[data-generate-button]").click();
  await page.locator("[data-confirm-generation]").click();
}

test("standalone site preserves recipe default and sends only explicit duration override", async ({ page }) => {
  const { quotes, launches } = await fixture(page);
  const duration = page.locator(".account-composer [name=duration]");
  await expect(duration).toHaveValue("10");
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  await expect.poll(() => quotes.length).toBe(1);
  expect(quotes[0].audio_ids || []).toEqual([]);
  await expect(duration).toBeEnabled();
  expect(quotes[0]).not.toHaveProperty("duration_override");
  await duration.selectOption("15");
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).toMatchObject({ model, duration: 10, duration_override: 15, quoted_credits: 30 });
  expect(launches[0]).not.toHaveProperty("prompt");
  expect(launches[0].audio_ids || []).toEqual([]);
});

test("standalone Seedance 2.5 exact repeat keeps reader photo upload without general controls", async ({ page }) => {
  const { quotes, launches } = await fixture(page);
  const references = page.locator("[data-reference-section]");
  await expect(references).toBeVisible();
  await references.locator("summary").click();
  const photo = references.locator("input[name=reference_file]");
  await expect(photo).toBeVisible();
  await photo.setInputFiles({ name: "reader.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await expect(page.locator("[data-seedance25-studio]")).toBeHidden();
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  const duration = page.locator(".account-composer [name=duration]");
  await expect(duration).toBeEnabled();
  await duration.selectOption("15");
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  for (const body of [...quotes, ...launches]) {
    expect(body.image_url).toBe("https://example.test/uploaded-reader.jpg");
    expect(body.audio_ids || []).toEqual([]);
    expect(body.character_ids || []).toEqual([]);
    expect(body.seed).toBeNull();
    expect(body).not.toHaveProperty("prompt");
  }
  expect(launches[0]).toMatchObject({ duration: 10, duration_override: 15, quoted_credits: 30 });
});

test("standalone Seedance 2.5 ordinary generation retains its multimodal controls", async ({ page }) => {
  await fixture(page);
  const launches: Record<string, unknown>[] = [];
  await page.route("**/api/web/generate/video/quote", r => r.fulfill({ json: { ok: true, data: { cost_credits: 20, can_run: true } } }));
  await page.route("**/api/web/generate/video", r => {
    launches.push(r.request().postDataJSON());
    return r.fulfill({ json: { ok: true, data: { id: 92, status: "pending" } } });
  });
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}`);
  await expect(page.locator("[data-account-model-select]")).toHaveValue(model);
  const optional = page.locator("[data-optional-section]");
  if (await optional.getAttribute("open") === null) await optional.locator(":scope > summary").click();
  await expect(page.locator("[data-seedance25-studio]")).toBeVisible();
  await expect(page.locator("[data-reference-section]")).toBeHidden();
  await page.locator("textarea[name=prompt]").fill("Cinematic portrait with gentle camera motion");
  await page.locator("[data-s25-image-urls]").fill("https://example.test/ordinary-reader.jpg");
  await page.locator("[data-s25-generate-audio]").uncheck();
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0].image_url).toBe("https://example.test/ordinary-reader.jpg");
  expect(launches[0].audio_ids).toContain("__apix_seedance25:output_format=mp4");
  expect(launches[0].audio_ids).toContain("__apix_seedance25:generate_audio=false");
});

test("standalone site blocks ambiguous repeat across reload until history acknowledgement", async ({ page }) => {
  const { launches } = await fixture(page, 503);
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  await page.reload();
  await expect(page.locator("[data-generate-button]")).toBeDisabled();
  await expect(page.getByText(/Результат запуска неизвестен/)).toBeVisible();
  expect(launches).toHaveLength(1);
  const stored = await page.evaluate(() => Object.entries(sessionStorage));
  expect(stored).toContainEqual(["apix:feed-launch:v1:7:42:remix", "pending"]);
  await page.getByRole("button", { name: "Проверить историю" }).click();
  await page.getByRole("button", { name: "Историю проверил — разрешить новый запуск" }).click();
  await expect(page.locator("[data-generate-button]")).toBeEnabled();
  expect(launches).toHaveLength(1);
});

test("standalone site locks measured source edit duration after quote", async ({ page }) => {
  const { launches } = await fixture(page, 202, true);
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  const duration = page.locator(".account-composer [name=duration]");
  await expect(duration).toHaveValue("7");
  await expect(duration).toBeDisabled();
  await expect(page.getByText("Длительность определяется исходным видео.", { exact: true })).toBeVisible();
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).not.toHaveProperty("duration_override");
  expect(launches[0].quoted_credits).toBe(14);
});

test("standalone site keeps legacy duration absent and stale price needs another explicit launch", async ({ page }) => {
  const { launches } = await fixture(page, 409);
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  await expect(page.getByText(/Цена изменилась/).first()).toBeVisible();
  expect(launches[0]).toMatchObject({ duration: 10, quoted_credits: 20 });
  expect(launches[0]).not.toHaveProperty("duration_override");
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  await expect(page.getByText(/К оплате: 25/)).toBeVisible();
  expect(launches).toHaveLength(1);
  await launch(page);
  await expect.poll(() => launches.length).toBe(2);
  expect(launches[1]).toMatchObject({ duration: 10, quoted_credits: 25 });
  expect(launches[1]).not.toHaveProperty("duration_override");
});
