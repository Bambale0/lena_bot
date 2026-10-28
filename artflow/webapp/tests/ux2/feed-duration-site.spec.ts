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
    if (url.pathname.endsWith("/seedance25/upload-reference")) return json({ url: "https://example.test/guided-reader.jpg" });
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

test("standalone Seedance 2.5 keeps guided materials and working advanced controls", async ({ page }) => {
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
  if (await optional.getAttribute("open") !== null) await optional.locator(":scope > summary").click();
  await expect(optional).not.toHaveAttribute("open", "");
  await expect(page.locator("[data-seedance25-studio]")).toBeVisible();
  await expect(page.locator("[data-reference-section]")).toBeHidden();
  await expect(page.locator("[data-s25-material]")).toHaveCount(3);
  await page.locator("[data-s25-image-files]").setInputFiles({ name: "guided.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  const advanced = page.locator("[data-seedance25-studio] > details");
  await expect(advanced).not.toHaveAttribute("open", "");
  await advanced.locator(":scope > summary").click();
  await page.locator("textarea[name=prompt]").fill("Cinematic portrait with gentle camera motion");
  await page.locator("[data-s25-image-urls]").fill("https://example.test/ordinary-reader.jpg");
  await page.locator("[data-s25-generate-audio]").uncheck();
  await page.locator("[data-generate-button]").click();
  const review = page.locator("[data-generation-review-modal]");
  await expect(review.getByText("По материалам", { exact: true })).toBeVisible();
  await expect(review.getByText("Фото: 2", { exact: true })).toBeVisible();
  await review.locator("[data-confirm-generation]").click();
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0].image_url).toBe("https://example.test/ordinary-reader.jpg");
  expect(launches[0].reference_urls).toContain("https://example.test/guided-reader.jpg");
  expect(launches[0].audio_ids).toContain("__apix_seedance25:output_format=mp4");
  expect(launches[0].audio_ids).toContain("__apix_seedance25:generate_audio=false");
});

for (const capped of [false, true]) {
  test(`standalone Seedance review matches deduplicated ${capped ? "capped" : "mixed"} materials in quote and launch`, async ({ page }) => {
    await fixture(page);
    const requests: Record<string, any>[] = [];
    await page.route("**/api/web/generate/video{,/quote}", r => {
      requests.push(r.request().postDataJSON());
      return r.fulfill({ json: { ok: true, data: r.request().url().endsWith("/quote")
        ? { cost_credits: 20, can_run: true } : { id: 95, status: "pending" } } });
    });
    const photo = "https://example.test/material.jpg";
    const video = "https://example.test/material.mp4";
    const audio = "https://example.test/material.mp3";
    await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}&ref=${encodeURIComponent(photo)}`);
    const panel = page.locator("[data-seedance25-studio]");
    await expect(panel).toBeVisible();
    await panel.locator(":scope > details > summary").click();
    for (const [selector, url, limit] of [
      ["[data-s25-image-urls]", photo, 30],
      ["[data-s25-video-urls]", video, 10],
      ["[data-s25-audio-urls]", audio, 10],
    ] as const) {
      await panel.locator(selector).fill(capped
        ? [...Array(limit).fill(url), "https://example.test/outside-cap"].join("\n")
        : [url, url].join("\n"));
    }
    const optional = page.locator("[data-optional-section]");
    if (await optional.getAttribute("open") === null) await optional.locator(":scope > summary").click();
    await optional.locator("[name=video_url]").fill(video);
    if (!capped) await panel.locator("[data-s25-image-files]").setInputFiles({ name: "guided.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
    await page.locator("[data-generate-button]").click();
    const review = page.locator("[data-generation-review-modal]");
    await expect(review.getByText(`Фото: ${capped ? 1 : 2} · Видео: 1 · Аудио: 1`, { exact: true })).toBeVisible();
    await review.locator("[data-confirm-generation]").click();
    await expect.poll(() => requests.length).toBe(2);
    for (const body of requests) {
      expect([body.image_url, ...body.reference_urls]).toEqual(capped ? [photo] : [photo, "https://example.test/guided-reader.jpg"]);
      expect(body.video_url).toBe(video);
      expect(body.audio_ids.filter((value: string) => !value.startsWith("__apix_seedance25:"))).toEqual([audio]);
      expect(body.audio_ids.filter((value: string) => value.startsWith("__apix_seedance25:video_ref="))).toEqual([]);
    }
  });
}

test("standalone Seedance review deduplicates uploaded content and reuses prepared URLs", async ({ page }) => {
  await fixture(page);
  let uploads = 0;
  const requests: Record<string, any>[] = [];
  await page.route("**/api/web/seedance25/upload-reference", r => {
    uploads += 1;
    return r.fulfill({ json: { ok: true, data: { url: "https://example.test/same-content.jpg" } } });
  });
  await page.route("**/api/web/generate/video{,/quote}", r => {
    requests.push(r.request().postDataJSON());
    return r.fulfill({ json: { ok: true, data: r.request().url().endsWith("/quote")
      ? { cost_credits: 20, can_run: true } : { id: 97, status: "pending" } } });
  });
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}&ref=${encodeURIComponent("https://example.test/same-content.jpg")}`);
  await page.locator("[data-s25-image-files]").setInputFiles(["original.jpg", "copy.jpg"].map(name => ({ name, mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) })));
  await page.locator("[data-generate-button]").click();
  const review = page.locator("[data-generation-review-modal]");
  await expect(review.getByText("Фото: 1", { exact: true })).toBeVisible();
  expect(uploads).toBe(2);
  expect(requests).toHaveLength(0);
  await review.locator("[data-confirm-generation]").click();
  await expect.poll(() => requests.length).toBe(2);
  expect(uploads).toBe(2);
  for (const body of requests) expect([body.image_url, ...body.reference_urls]).toEqual(["https://example.test/same-content.jpg"]);
});

test("standalone Seedance failed upload prevents review and can be retried", async ({ page }) => {
  await fixture(page);
  let uploads = 0, generations = 0;
  await page.route("**/api/web/seedance25/upload-reference", r => {
    uploads += 1;
    return uploads === 1
      ? r.fulfill({ status: 503, json: { error: "Не удалось загрузить материал" } })
      : r.fulfill({ json: { ok: true, data: { url: "https://example.test/retried.jpg" } } });
  });
  await page.route("**/api/web/generate/video{,/quote}", r => { generations += 1; return r.fulfill({ json: {} }); });
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}`);
  await page.locator("[data-s25-image-files]").setInputFiles({ name: "retry.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  const button = page.locator("[data-generate-button]");
  await button.click();
  await expect(page.locator("[data-toast]")).toContainText("Не удалось загрузить материал");
  await expect(page.locator("[data-generation-review-modal]")).toBeHidden();
  await expect(button).toBeEnabled();
  expect(generations).toBe(0);
  await button.click();
  await expect(page.locator("[data-generation-review-modal]").getByText("Фото: 1", { exact: true })).toBeVisible();
  expect(uploads).toBe(2);
  expect(generations).toBe(0);
});

for (const change of ["selection", "logout"] as const) {
  test(`standalone Seedance does not open a stale review after ${change} during upload`, async ({ page }) => {
    await fixture(page);
    let uploadStarted = false, finishUpload: () => void = () => {};
    const uploadReady = new Promise<void>(resolve => { finishUpload = resolve; });
    await page.route("**/api/web/seedance25/upload-reference", async r => {
      uploadStarted = true;
      await uploadReady;
      await r.fulfill({ json: { ok: true, data: { url: "https://example.test/stale.jpg" } } });
    });
    await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}`);
    await page.locator("[data-s25-image-files]").setInputFiles({ name: "stale.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
    const button = page.locator("[data-generate-button]");
    await button.click();
    await expect.poll(() => uploadStarted).toBe(true);
    await expect(button).toBeDisabled();
    if (change === "logout") await page.locator("[data-logout]").click();
    else await page.locator("textarea[name=prompt]").fill("Changed while the selected file uploads");
    finishUpload();
    await expect(page.locator("[data-toast]")).toContainText("изменились");
    await expect(page.locator("[data-generation-review-modal]")).toBeHidden();
    await expect(button).toBeEnabled();
  });
}

test("standalone Seedance preparation has a bounded timeout and restores the form", async ({ page }) => {
  await fixture(page);
  let started = false, finishUpload: () => void = () => {};
  const uploadReady = new Promise<void>(resolve => { finishUpload = resolve; });
  await page.route("**/api/web/seedance25/upload-reference", async r => {
    started = true;
    await uploadReady;
    await r.fulfill({ json: { ok: true, data: { url: "https://example.test/late.jpg" } } }).catch(() => {});
  });
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}`);
  await page.locator("[data-s25-image-files]").setInputFiles({ name: "late.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await page.clock.install();
  const button = page.locator("[data-generate-button]");
  await button.click();
  await expect.poll(() => started).toBe(true);
  await page.clock.fastForward(120_000);
  await expect(page.locator("[data-toast]")).toContainText("Слишком долгая загрузка");
  await expect(button).toBeEnabled();
  await expect(page.locator("[data-generation-review-modal]")).toBeHidden();
  finishUpload();
});

test("standalone Seedance confirmation rejects a changed prepared selection", async ({ page }) => {
  await fixture(page);
  let generations = 0;
  await page.route("**/api/web/generate/video{,/quote}", r => { generations += 1; return r.fulfill({ json: { ok: true, data: { cost_credits: 20, can_run: true, id: 98, status: "pending" } } }); });
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}`);
  await page.locator("[data-s25-image-files]").setInputFiles({ name: "prepared.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await page.locator("[data-generate-button]").click();
  const review = page.locator("[data-generation-review-modal]");
  await expect(review).toBeVisible();
  await page.locator("textarea[name=prompt]").fill("A changed draft behind the open confirmation", { force: true });
  await review.locator("[data-confirm-generation]").click();
  await expect(page.locator("[data-toast]")).toContainText("изменились");
  await expect(review).toBeHidden();
  expect(generations).toBe(0);
});

test("standalone Grok exposes text and photo modes with the real variant and confirmation", async ({ page }) => {
  const textModel = "grok-imagine/text-to-video";
  const photoModel = "grok-imagine/image-to-video";
  const quotes: Record<string, unknown>[] = [];
  const launches: Record<string, unknown>[] = [];
  await page.route("**/studio.html?*", r => r.fulfill({ path: path.join(landing, "studio.html"), contentType: "text/html" }));
  await page.route("**/js/*.js?*", r => r.fulfill({ path: path.join(landing, "js", new URL(r.request().url()).pathname.split("/").pop()!), contentType: "text/javascript" }));
  await page.route("**/css/prototype-premium.css?*", r => r.fulfill({ path: path.join(landing, "css/prototype-premium.css"), contentType: "text/css" }));
  await page.route("**/api/web/**", r => {
    const url = new URL(r.request().url());
    const json = (data: unknown) => r.fulfill({ json: { ok: true, data } });
    if (url.pathname.endsWith("/me")) return json({ id: 7, credits: 100, full_name: "Reader" });
    if (url.pathname.endsWith("/uploads/reference")) return json({ url: "https://example.test/grok-reader.jpg" });
    if (url.pathname.endsWith("/models/video")) return json([
      { key: textModel, name: "Grok Imagine Video", type: "video", modes: ["text"], durations: [10], resolutions: ["720p"], aspect_ratios: ["9:16"], credits: 0.6, active: true },
      { key: photoModel, name: "Grok Imagine Video", type: "video", modes: ["image"], durations: [10], resolutions: ["720p"], aspect_ratios: ["9:16"], max_refs: 7, credits: 0.7, active: true },
    ]);
    if (url.pathname.endsWith("/generate/video/quote")) {
      const body = r.request().postDataJSON();
      quotes.push(body);
      return json({ cost_credits: body.model === photoModel ? 7 : 6, can_run: true, reference_seconds: 0, output_seconds: 10 });
    }
    if (url.pathname.endsWith("/generate/video")) {
      launches.push(r.request().postDataJSON());
      return json({ id: 93, status: "pending" });
    }
    if (url.pathname.includes("/prompts")) return json({ items: [] });
    if (url.pathname.includes("/transactions")) return json({ transactions: [], pending: [] });
    if (url.pathname.includes("/auth/config")) return json({});
    return json([]);
  });
  page.on("dialog", d => d.accept());
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(textModel)}`);

  const chooser = page.locator("[data-video-mode-switch]");
  const references = page.locator("[data-reference-section]");
  await expect(chooser).toBeVisible();
  await expect(chooser.getByRole("button", { name: "По тексту" })).toHaveAttribute("aria-pressed", "true");
  await expect(references).toBeHidden();
  await expect(page.locator("[data-generation-note]")).toContainText("0,6");
  await page.locator("[data-generate-button]").click();
  let review = page.locator("[data-generation-review-modal]");
  await expect(review.getByText("По тексту", { exact: true })).toBeVisible();
  await review.locator("[data-confirm-generation]").click();
  await expect.poll(() => launches.length).toBe(1);
  expect(quotes[0]).toMatchObject({ model: textModel, mode: "text", image_url: null });
  expect(launches[0]).toMatchObject({ model: textModel, mode: "text", image_url: null, quoted_credits: 6 });

  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(textModel)}`);
  await chooser.getByRole("button", { name: "По фото" }).click();
  await expect(chooser.getByRole("button", { name: "По фото" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("[data-generation-note]")).toContainText("0,7");
  await expect(references).toBeVisible();
  await page.locator("[data-generate-button]").click();
  await expect(page.locator("[data-generation-review-modal]")).toBeHidden();
  await expect(page.locator("[data-toast]")).toContainText("сначала добавьте исходное фото");

  if (await references.getAttribute("open") === null) await references.locator(":scope > summary").click();
  const fileInput = references.locator("input[name=reference_file]");
  await fileInput.setInputFiles({ name: "reader.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await references.locator("input[name=reference_url]").fill("https://example.test/route-reader.jpg");
  await chooser.getByRole("button", { name: "По тексту" }).click();
  await expect(references).toBeHidden();
  await expect.poll(() => fileInput.evaluate((input: HTMLInputElement) => input.files?.length || 0)).toBe(0);
  await expect(references.locator("input[name=reference_url]")).toHaveValue("");
  await expect(page.locator("[data-toast]")).toContainText("Фото убрано");
  await chooser.getByRole("button", { name: "По фото" }).click();
  await expect(references).toBeVisible();
  await fileInput.setInputFiles({ name: "reader.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await page.locator("[data-generate-button]").click();
  review = page.locator("[data-generation-review-modal]");
  await expect(review.getByText("По фото", { exact: true })).toBeVisible();
  await review.locator("[data-confirm-generation]").click();
  await expect.poll(() => launches.length).toBe(2);
  expect(quotes[1]).toMatchObject({ model: photoModel, mode: "image", image_url: "https://example.test/grok-reader.jpg" });
  expect(launches[1]).toMatchObject({ model: photoModel, mode: "image", image_url: "https://example.test/grok-reader.jpg", quoted_credits: 7 });
});

test("standalone Grok photo repeat keeps replacement photo while the mode chooser is hidden", async ({ page }) => {
  const textModel = "grok-imagine/text-to-video";
  const photoModel = "grok-imagine/image-to-video";
  const quotes: Record<string, unknown>[] = [];
  const launches: Record<string, unknown>[] = [];
  await page.route("**/studio.html?*", r => r.fulfill({ path: path.join(landing, "studio.html"), contentType: "text/html" }));
  await page.route("**/js/*.js?*", r => r.fulfill({ path: path.join(landing, "js", new URL(r.request().url()).pathname.split("/").pop()!), contentType: "text/javascript" }));
  await page.route("**/css/prototype-premium.css?*", r => r.fulfill({ path: path.join(landing, "css/prototype-premium.css"), contentType: "text/css" }));
  await page.route("**/api/web/**", r => {
    const url = new URL(r.request().url());
    const json = (data: unknown) => r.fulfill({ json: { ok: true, data } });
    if (url.pathname.endsWith("/me")) return json({ id: 7, credits: 100, full_name: "Reader" });
    if (url.pathname.endsWith("/models/video")) return json([
      { key: textModel, name: "Grok Imagine Video", type: "video", modes: ["text"], durations: [10], resolutions: ["720p"], aspect_ratios: ["9:16"], credits: 0.6, active: true },
      { key: photoModel, name: "Grok Imagine Video", type: "video", modes: ["image"], durations: [10], resolutions: ["720p"], aspect_ratios: ["9:16"], max_refs: 7, credits: 0.7, active: true },
    ]);
    if (url.pathname.endsWith("/uploads/reference")) return json({ url: "https://example.test/repeat-reader.jpg" });
    if (url.pathname.endsWith("/feed/77")) return json({
      id: 77, type: "video", model: photoModel, original_duration: 10,
      original_resolution: "720p", original_aspect_ratio: "9:16",
      source_has_video_reference: false, result_url: "https://example.test/source.mp4",
    });
    if (url.pathname.endsWith("/feed/77/remix/quote")) {
      quotes.push(r.request().postDataJSON());
      return json({ cost_credits: 7, can_run: true, duration_options: [10], default_duration: 10, effective_duration: 10 });
    }
    if (url.pathname.endsWith("/feed/77/remix")) {
      launches.push(r.request().postDataJSON());
      return json({ id: 94, status: "pending" });
    }
    if (url.pathname.includes("/prompts")) return json({ items: [] });
    if (url.pathname.includes("/transactions")) return json({ transactions: [], pending: [] });
    if (url.pathname.includes("/auth/config")) return json({});
    return json([]);
  });
  page.on("dialog", d => d.accept());
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(photoModel)}&feed_remix=77`);

  await expect(page.locator("[data-video-mode-switch]")).toBeHidden();
  const references = page.locator("[data-reference-section]");
  await expect(references).toBeVisible();
  if (await references.getAttribute("open") === null) await references.locator(":scope > summary").click();
  await references.locator("input[name=reference_file]").setInputFiles({ name: "repeat.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  await expect.poll(() => quotes.length).toBe(1);
  expect(quotes[0]).toMatchObject({ model: photoModel, mode: "image", image_url: "https://example.test/repeat-reader.jpg" });
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).toMatchObject({ model: photoModel, mode: "image", image_url: "https://example.test/repeat-reader.jpg", quoted_credits: 7 });
});

test("standalone Grok ratio follows distinct references without resetting other choices", async ({ page }) => {
  await fixture(page);
  const textModel = "grok-imagine/text-to-video", photoModel = "grok-imagine/image-to-video";
  const requests: Record<string, any>[] = [];
  await page.route("**/api/web/models/video", r => r.fulfill({ json: { ok: true, data: [
    { key: textModel, name: "Grok Imagine Video", type: "video", modes: ["text"], durations: [10], resolutions: ["720p"], aspect_ratios: ["9:16", "16:9"], credits: 0.6, active: true },
    { key: photoModel, name: "Grok Imagine Video", type: "video", modes: ["image"], durations: [10], resolutions: ["720p"], aspect_ratios: ["9:16", "16:9"], aspect_ratio_min_refs: 2, max_refs: 7, credits: 0.7, active: true },
  ] } }));
  await page.route("**/api/web/generate/video{,/quote}", r => {
    requests.push(r.request().postDataJSON());
    return r.fulfill({ json: { ok: true, data: r.request().url().endsWith("/quote")
      ? { cost_credits: 7, can_run: true } : { id: 96, status: "pending" } } });
  });
  const first = "https://example.test/first.jpg", second = "https://example.test/second.jpg";
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(photoModel)}&ref=${encodeURIComponent(first)}`);
  const ratio = page.locator(".account-composer [name=aspect_ratio]");
  const ratioLabel = ratio.locator("..");
  const references = page.locator("[data-reference-section]");
  await expect(ratio).toBeDisabled();
  await expect(ratioLabel).toBeHidden();
  if (await references.getAttribute("open") === null) await references.locator(":scope > summary").click();
  const extras = references.locator("[name=reference_urls]");
  await extras.fill(first);
  await expect(ratio).toBeDisabled();
  await extras.fill(`${first}\n${second}`);
  await expect(ratio).toBeEnabled();
  await expect(ratioLabel).toBeVisible();
  await ratio.selectOption("16:9");
  const optional = page.locator("[data-optional-section]");
  if (await optional.getAttribute("open") === null) await optional.locator(":scope > summary").click();
  await page.locator(".account-composer [name=resolution]").selectOption("720p");
  await extras.fill("");
  await expect(ratio).toBeDisabled();
  await expect(ratioLabel).toBeHidden();
  const files = references.locator("[name=reference_file]");
  await files.setInputFiles({ name: "second.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await expect(ratio).toBeEnabled();
  await expect(ratio).toHaveValue("16:9");
  await files.setInputFiles([]);
  await expect(ratio).toBeDisabled();
  await expect(page.locator(".account-composer [name=resolution]")).toHaveValue("720p");
  await page.locator("[data-generate-button]").click();
  const review = page.locator("[data-generation-review-modal]");
  await expect(review.locator("[data-review-list] article").filter({ hasText: "Формат кадра" }).locator("b")).toHaveText("Авто");
  await review.locator("[data-confirm-generation]").click();
  await expect.poll(() => requests.length).toBe(2);
  for (const body of requests) expect(body).toMatchObject({ model: photoModel, aspect_ratio: null, image_url: first, reference_urls: [], resolution: "720p" });

  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(photoModel)}&ref=${encodeURIComponent(first)}&refs=${encodeURIComponent(second)}`);
  await expect(ratio).toBeEnabled();
  await ratio.selectOption("16:9");
  await launch(page);
  await expect.poll(() => requests.length).toBe(4);
  for (const body of requests.slice(2)) expect(body).toMatchObject({ model: photoModel, aspect_ratio: "16:9", image_url: first, reference_urls: [second] });

  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(textModel)}`);
  await expect(ratio).toBeEnabled();
  await ratio.selectOption("16:9");
  await launch(page);
  await expect.poll(() => requests.length).toBe(6);
  for (const body of requests.slice(4)) expect(body).toMatchObject({ model: textModel, aspect_ratio: "16:9", image_url: null, reference_urls: [] });
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
