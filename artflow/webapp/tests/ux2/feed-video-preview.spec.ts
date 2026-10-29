import { expect, test, type Locator, type Page, type Route } from "@playwright/test";

import { feedVideoMp4 } from "../fixtures/feed-video-first-frame";

const mediaOrigin = "https://video-preview.example.test";
const videos = Array.from({ length: 4 }, (_, index) => ({
  id: 801 + index, author: "Видео для проверки кадра " + (index + 1),
  model: "fixture-video", gen_type: "video", prompt_hidden: true,
  result_url: mediaOrigin + "/render-" + (index + 1) + "?asset=video",
  result_urls: [mediaOrigin + "/render-" + (index + 1) + "?asset=video"],
  preview_url: "", preview_urls: [], remixes: 0, likes_count: 0, shares_count: 0,
}));

async function serveVideo(route: Route) {
  const total = feedVideoMp4.length;
  const headers = { "Content-Type": "video/mp4", "Accept-Ranges": "bytes", "Cache-Control": "no-store" };
  const range = route.request().headers().range?.match(/^bytes=(\d*)-(\d*)$/);
  // A server may ignore unsupported/malformed ranges and send the full resource.
  if (!range || (!range[1] && !range[2])) {
    return route.fulfill({ status: 200, headers: { ...headers, "Content-Length": String(total) }, body: feedVideoMp4 });
  }
  const suffix = !range[1];
  const suffixLength = suffix ? Number(range[2]) : 0;
  const start = suffix ? Math.max(0, total - suffixLength) : Number(range[1]);
  const end = suffix || !range[2] ? total - 1 : Math.min(Number(range[2]), total - 1);
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start >= total || end < start ||
      (suffix && (!Number.isSafeInteger(suffixLength) || suffixLength <= 0))) {
    return route.fulfill({ status: 416, headers: { ...headers, "Content-Range": "bytes */" + total, "Content-Length": "0" }, body: "" });
  }
  const body = feedVideoMp4.subarray(start, end + 1);
  return route.fulfill({ status: 206, headers: {
    ...headers, "Content-Range": "bytes " + start + "-" + end + "/" + total, "Content-Length": String(body.length),
  }, body });
}

async function prepare(page: Page, precedingPhotos = 0) {
  const writes: string[] = [];
  const photos = Array.from({ length: precedingPhotos }, (_, index) => ({
    id: 901 + index, author: "Фотография для прокрутки " + (index + 1),
    model: "fixture-image", gen_type: "image", prompt_hidden: true,
    result_url: mediaOrigin + "/photo-" + (index + 1) + ".svg",
    result_urls: [mediaOrigin + "/photo-" + (index + 1) + ".svg"],
    remixes: 0, likes_count: 0, shares_count: 0,
  }));
  const items = [...photos, ...videos];
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: "video-first-frame-fixture", initDataUnsafe: { user: { id: 123 } }, colorScheme: "dark",
      ready() {}, expand() {}, openLink() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    } } as typeof window.Telegram;
  });
  await page.route("**/*", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET") {
      writes.push(url.pathname);
      return route.fulfill({ status: 403, json: { detail: "This preview test permits no writes" } });
    }
    if (url.origin === mediaOrigin) {
      if (/^\/render-\d+$/.test(url.pathname)) return serveVideo(route);
      return route.fulfill({ contentType: "image/svg+xml", body:
        '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200"><rect width="160" height="200" fill="#b0a2bf"/></svg>' });
    }
    if (url.pathname.endsWith("telegram-web-app.js")) return route.fulfill({ contentType: "application/javascript", body: "" });
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const endpoint = url.pathname;
    const json = (value: unknown) => route.fulfill({ json: value });
    if (endpoint.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (endpoint === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Проверка видео", credits: 120, language: "ru", miniapp_ux2_available: true });
    if (endpoint.endsWith("/me/permissions")) return json({ is_admin: true });
    if (endpoint.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (endpoint.endsWith("/models/image")) return json([{ key: "fixture-image", display_name: "Фото", credits: 5, modes: ["text"], aspect_ratios: ["4:5"], counts: [1] }]);
    if (endpoint.endsWith("/models/video")) return json([{ key: "fixture-video", display_name: "Видео", credits: 10, modes: ["text"], aspect_ratios: ["4:5"], durations: [5], resolutions: ["720p"] }]);
    if (endpoint.endsWith("/feed")) return json(items);
    if (/\/feed\/\d+$/.test(endpoint)) return json(items.find(item => item.id === Number(endpoint.split("/").at(-1))));
    if (endpoint.endsWith("/image-sessions/active")) return json({ data: null });
    if (endpoint.endsWith("/trend-categories")) return json({ items: [], has_more: false, next_cursor: null });
    if (endpoint.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    return json([]);
  });
  return { writes, count: items.length };
}

async function openGallery(page: Page, count: number) {
  await page.goto("/?ux=3");
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("tab", { name: "Идеи", exact: true }).click();
  await page.getByRole("button", { name: "Лента работ", exact: true }).click();
  await expect(page.locator(".apix-feed-card")).toHaveCount(count);
}

function videoCard(page: Page, index: number) {
  return page.getByRole("article", { name: "Работа автора " + videos[index].author, exact: true });
}

async function blueFrameFraction(page: Page, media: Locator) {
  const box = await media.boundingBox();
  if (!box) return 0;
  // A small interior patch avoids the video badge, Play button, rounded corners
  // and caption. Read rendered screenshot pixels, not only decoded canvas data.
  const clip = { x: box.x + box.width * 0.22, y: box.y + box.height * 0.28, width: 12, height: 12 };
  const viewport = page.viewportSize()!;
  if (clip.x < 0 || clip.y < 0 || clip.x + clip.width > viewport.width || clip.y + clip.height > viewport.height) return 0;
  const png = await page.screenshot({ clip, scale: "css" });
  return page.evaluate(async dataUrl => {
    const image = new Image();
    image.src = dataUrl;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let blue = 0;
    for (let offset = 0; offset < pixels.length; offset += 4) {
      if (pixels[offset] < 25 && pixels[offset + 1] < 25 && pixels[offset + 2] > 90 && pixels[offset + 3] > 240) blue++;
    }
    return blue / (pixels.length / 4);
  }, "data:image/png;base64," + png.toString("base64"));
}

async function expectPaintedFrames(page: Page) {
  for (let index = 0; index < videos.length; index++) {
    const card = videoCard(page, index);
    const video = card.locator(".apix-feed-media video");
    await expect(card).toBeInViewport();
    await expect(video).toBeVisible();
    await expect.poll(() => video.evaluate((element: HTMLVideoElement) => ({
      currentFrameAvailable: element.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA,
      width: element.videoWidth, height: element.videoHeight, error: element.error?.code ?? null,
    })), { timeout: 10_000 }).toEqual({ currentFrameAvailable: true, width: 160, height: 240, error: null });
    await expect.poll(() => blueFrameFraction(page, card.locator(".apix-feed-media")),
      { timeout: 10_000, message: "Video " + (index + 1) + " must paint its real blue frame, not a blank card" }).toBeGreaterThan(0.9);
    await expect(card.locator(".feed-media-fallback")).toHaveCount(0);
  }
}

test("feed video previews paint real first frames in the initial viewport", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const state = await prepare(page);
  await openGallery(page, state.count);
  await expectPaintedFrames(page);
  expect(state.writes).toEqual([]);
  await page.screenshot({ path: info.outputPath("feed-video-first-frames-initial.png") });
});

test("feed video previews paint when metadata is ready before scrolling into view", async ({ page }, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  // Twenty photos keep the video row well below the viewport and the feed's
  // preload margin, while all 24 cards fit the existing first render batch.
  const state = await prepare(page, 20);
  await openGallery(page, state.count);
  for (let index = 0; index < videos.length; index++) {
    const card = videoCard(page, index);
    await expect(card).not.toBeInViewport();
    const box = await card.boundingBox();
    expect(box!.y).toBeGreaterThan(page.viewportSize()!.height + 1000);
    await expect.poll(() => card.locator("video").evaluate((element: HTMLVideoElement) =>
      element.readyState >= HTMLMediaElement.HAVE_METADATA), { timeout: 10_000 }).toBe(true);
  }
  await videoCard(page, 0).scrollIntoViewIfNeeded();
  await expectPaintedFrames(page);
  expect(state.writes).toEqual([]);
  await page.screenshot({ path: info.outputPath("feed-video-first-frames-after-scroll.png") });
});
