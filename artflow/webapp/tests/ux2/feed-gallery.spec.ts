import { expect, test, type Locator, type Page } from "@playwright/test";

const mediaOrigin = "https://gallery.example.test";
const originalA = `${mediaOrigin}/original-a.png`;
const originalB = `${mediaOrigin}/original-b.png`;
const originalVideo = `${mediaOrigin}/opaque-render?asset=video`;
const staleVideo = `${mediaOrigin}/stale-video.mp4`;
const hiddenPrompt = "PRIVATE_RECIPE_MUST_NEVER_APPEAR_IN_THE_GALLERY";
const longAuthor = "Студия северного света и необычных визуальных историй";
const boundResults = [0, 1].map(index => `/api/v1/feed/201/preview.webp?index=${index}&output_id=${(index ? "b" : "a").repeat(64)}`);

const items = [
  { id: 201, author: longAuthor, model: "image-fixture", gen_type: "image", is_mine: true,
    result_url: originalA, result_urls: [originalA, originalB],
    preview_url: `${mediaOrigin}/preview-a.webp`, preview_urls: [`${mediaOrigin}/preview-a.webp`, `${mediaOrigin}/preview-b.webp`],
    remixes: 12345, likes_count: 38, shares_count: 2, aspect_ratio: "4:5" },
  { id: 202, author: "Видео с недоступным постером", model: "video-fixture", gen_type: "video",
    result_url: `${mediaOrigin}/unavailable.mp4`, result_urls: [`${mediaOrigin}/unavailable.mp4`],
    preview_url: `${mediaOrigin}/unavailable-poster.webp`, remixes: 0, likes_count: 0, shares_count: 0 },
  { id: 203, author: "Автор с неизвестным счётчиком", model: "image-fixture", gen_type: "image",
    result_url: `${mediaOrigin}/portrait.png`, result_urls: [`${mediaOrigin}/portrait.png`], remixes: null },
  { id: 204, author: "Автор старой публикации", model: "image-fixture", gen_type: "image",
    result_url: `${mediaOrigin}/landscape.png`, result_urls: [`${mediaOrigin}/landscape.png`] },
  { id: 205, author: "Архитектура и свет", model: "image-fixture", gen_type: "image",
    result_url: `${mediaOrigin}/architecture.png`, result_urls: [`${mediaOrigin}/architecture.png`], remixes: 7 },
  { id: 206, author: "Ещё один видеосюжет", model: "video-fixture", gen_type: "video",
    result_url: originalVideo, result_urls: [originalVideo],
    preview_url: originalVideo, preview_urls: [staleVideo], remixes: 3 },
].map(item => ({ ...item, prompt_hidden: true, prompt: hiddenPrompt }));

async function prepare(page: Page, protectedAlbum = false, trends: Record<string, unknown>[] = []) {
  const state = {
    writes: [] as string[], mediaRequests: [] as string[], videoRequestTypes: [] as string[],
    videoRequestDom: [] as { videoSources: string[]; imageSources: string[]; posters: string[] }[],
    quotes: [] as Record<string, unknown>[], likes: 0,
  };
  const feedItems = items.map(item => item.id === 201 && protectedAlbum ? {
    ...item, is_mine: false, source_image_recipe_available: true, result_url: "", result_urls: [],
    preview_url: boundResults[0], preview_urls: boundResults,
  } : item);
  await page.addInitScript(() => {
    const handlers = new Set<() => void>();
    window.addEventListener("apix:gallery-test-back", () => handlers.forEach(handler => handler()));
    window.Telegram = { WebApp: {
      initData: "gallery-fixture", initDataUnsafe: { user: { id: 123 } }, colorScheme: "dark",
      ready() {}, expand() {}, openLink() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
      BackButton: { show() {}, hide() {}, onClick(handler: () => void) { handlers.add(handler); },
        offClick(handler: () => void) { handlers.delete(handler); } },
    } } as typeof window.Telegram;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route(`${mediaOrigin}/**`, async route => {
    const request = route.request();
    state.mediaRequests.push(request.url());
    if (request.url() === originalVideo) {
      state.videoRequestTypes.push(request.resourceType());
      // Capture the element before abort triggers the media-error fallback.
      state.videoRequestDom.push(await page.evaluate(() => {
        const videos = Array.from(document.querySelectorAll<HTMLVideoElement>(".apix-feed-media video"));
        return {
          videoSources: videos.map(video => video.src),
          imageSources: Array.from(document.querySelectorAll<HTMLImageElement>(".apix-feed-media img"), image => image.src),
          posters: videos.map(video => video.poster),
        };
      }));
    }
    const path = new URL(request.url()).pathname;
    if (request.url() === originalVideo || path.includes("unavailable") || path.endsWith(".mp4")) return route.abort("failed");
    return route.fulfill({ contentType: "image/svg+xml", body:
      `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="${path.includes("preview") ? "#d19979" : path.includes("-b") ? "#3f6980" : "#706092"}"/><circle cx="200" cy="200" r="90" fill="#d9cbe9"/></svg>` });
  });
  await page.route("**/api/**", route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET") state.writes.push(path);
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Тестовый администратор", credits: 120, language: "ru", miniapp_ux2_available: true });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/models/image")) return json([{ key: "image-fixture", display_name: "Фотография", credits: 5, modes: ["text", "image"], max_refs: 2, aspect_ratios: ["4:5"], counts: [1] }]);
    if (path.endsWith("/models/video")) return json([{ key: "video-fixture", display_name: "Видео", credits: 10, modes: ["text", "image"], max_refs: 1, aspect_ratios: ["4:5"], durations: [5], resolutions: ["720p"] }]);
    if (path === "/api/v1/feed/201/preview.webp") return route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500"><rect width="400" height="500" fill="#706092"/></svg>' });
    if (path.endsWith("/upload-media")) return json({ data: { url: `${mediaOrigin}/reader.png`, kind: "image", content_type: "image/png", size: 68 } });
    if (path.endsWith("/feed/201/like")) { state.likes++; return json({ likes_count: 39 }); }
    if (path.endsWith("/remix/quote")) {
      state.quotes.push(request.postDataJSON());
      return json({ cost_credits: 5, balance_credits: 120, can_run: true, deficit_credits: 0 });
    }
    if (/\/feed\/\d+\/remix$|\/generate\//.test(path)) return route.fulfill({ status: 500, json: { detail: "No paid launch is part of this gallery test" } });
    if (path.endsWith("/feed")) return json(feedItems);
    if (/\/feed\/\d+$/.test(path)) return json(feedItems.find(item => item.id === Number(path.split("/").at(-1))));
    if (path.endsWith("/image-sessions/active")) return json({ data: null });
    if (path === "/api/v1/trends") return json(trends);
    if (path.endsWith("/trend-categories")) return json({ items: [], has_more: false, next_cursor: null });
    if (path.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    return json([]);
  });
  return state;
}

async function openGallery(page: Page) {
  await page.goto("/?ux=3");
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  await page.getByRole("navigation", { name: "Основная навигация" }).getByRole("tab", { name: "Идеи", exact: true }).click();
  await page.getByRole("button", { name: "Лента работ", exact: true }).click();
  await expect(page.locator(".apix-feed-card")).toHaveCount(items.length);
}

function cardByAuthor(page: Page, author: string) {
  return page.locator(".apix-feed-card").filter({ hasText: author });
}

async function expectReachable(control: Locator) {
  await control.scrollIntoViewIfNeeded();
  await expect(control).toBeVisible();
  const result = await control.evaluate(element => {
    const box = element.getBoundingClientRect();
    const hit = element.ownerDocument.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return { width: box.width, height: box.height, reachable: hit === element || element.contains(hit) };
  });
  expect(result.width).toBeGreaterThanOrEqual(44);
  expect(result.height).toBeGreaterThanOrEqual(44);
  expect(result.reachable, "The visible control must receive a tap above overlays and navigation").toBe(true);
}

function paidWrites(writes: string[]) {
  return writes.filter(path => /\/feed\/\d+\/remix$|\/generate\/|\/trends\/\d+\/run$/.test(path));
}

for (const [width, columns] of [[320, 1], [390, 2], [1440, 4]] as const) {
  test(`filled studio gallery stays legible and actionable at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    const state = await prepare(page);
    await openGallery(page);
    const cards = page.locator(".apix-feed-card");
    const rows = await cards.evaluateAll(nodes => nodes.map(node => {
      const box = node.getBoundingClientRect(); return { x: box.x, y: box.y, width: box.width };
    }));
    expect(rows.filter(row => Math.abs(row.y - rows[0].y) < 2)).toHaveLength(columns);
    const media = await cards.first().locator(".apix-feed-media").boundingBox();
    expect(media!.width / media!.height).toBeCloseTo(4 / 5, 2);
    await expect(cards.first().locator(".feed-card-author")).toBeVisible();
    await expect(cards.first().locator(".feed-card-model")).toBeVisible();
    const metadata = await cards.locator(".feed-card-author, .feed-card-model, .feed-card-stats").evaluateAll(nodes => nodes.map(node => Number.parseFloat(getComputedStyle(node).fontSize)));
    expect(metadata.every(size => size >= 13)).toBe(true);
    const album = cardByAuthor(page, longAuthor);
    await expect(album.getByText("Повторов: 12345", { exact: true })).toBeVisible();
    await expect(cardByAuthor(page, "Видео с недоступным постером").getByText("Повторов: 0", { exact: true })).toBeVisible();
    const failedVideo = cardByAuthor(page, "Видео с недоступным постером");
    await failedVideo.locator(".apix-feed-media img, .apix-feed-media video").evaluateAll(nodes => nodes.forEach(node => node.dispatchEvent(new Event("error"))));
    await expect(failedVideo.locator(".feed-media-fallback")).toContainText("Превью недоступно");
    await expect(failedVideo.locator(".feed-card-play")).toBeHidden();
    const videoAlias = cardByAuthor(page, "Ещё один видеосюжет");
    await expect(videoAlias.locator('img[src$=".mp4"], video[poster$=".mp4"]')).toHaveCount(0);
    for (const author of ["Автор с неизвестным счётчиком", "Автор старой публикации"]) {
      await expect(cardByAuthor(page, author).getByText(/Повторов:/)).toHaveCount(0);
    }
    const repeat = album.getByRole("button", { name: "Повторить", exact: true });
    const placement = await repeat.evaluate(button => {
      const media = button.closest(".apix-feed-card")!.querySelector(".apix-feed-media")!;
      return { actionTop: button.getBoundingClientRect().top, mediaBottom: media.getBoundingClientRect().bottom };
    });
    expect(placement.actionTop).toBeGreaterThanOrEqual(placement.mediaBottom - 1);
    for (const control of [repeat, album.getByRole("button", { name: "Лайк", exact: true }),
      failedVideo.getByRole("button", { name: "Повторить", exact: true }),
      cards.last().getByRole("button", { name: "Повторить", exact: true })]) await expectReachable(control);
    await expect.poll(() => state.mediaRequests.includes(originalVideo)).toBe(true);
    expect(state.mediaRequests).not.toContain(staleVideo);
    await expect.poll(() => state.videoRequestDom.length).toBeGreaterThan(0);
    for (const snapshot of state.videoRequestDom) {
      expect(snapshot.videoSources).toContain(originalVideo);
      expect(snapshot.imageSources).not.toContain(originalVideo);
      expect(snapshot.posters).not.toContain(originalVideo);
    }
    expect(state.videoRequestTypes).not.toContain("image");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await page.locator(".apix-shell > main").evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    await expect(page.getByText(hiddenPrompt, { exact: true })).toHaveCount(0);
    await expect(page.locator(".apix-feed-toolbar").getByText(/^\d+\/\d+$/)).toHaveCount(0);
    await expect(cards.getByText("выбор", { exact: true })).toHaveCount(0);
    for (const [name, selected] of [["Сортировка работ", "Новые"], ["Тип работ", "Все"]]) {
      const group = page.getByRole("group", { name, exact: true });
      await expect(group.getByRole("button", { name: selected, exact: true })).toHaveAttribute("aria-pressed", "true");
      await expect(group.locator('[aria-pressed="true"]')).toHaveCount(1);
    }
    expect(paidWrites(state.writes)).toEqual([]);
    await album.scrollIntoViewIfNeeded();
    await page.screenshot({ path: info.outputPath(`feed-gallery-${width}.png`) });
  });
}

test("trend usage counts show their own label and preserve zero without inventing unknown counts", async ({ page }) => {
  const trends = [
    { id: 301, title: "Популярный фототренд", uses_count: 7 },
    { id: 302, title: "Новый фототренд", uses_count: 0 },
    { id: 303, title: "Фототренд без данных", uses_count: null },
    { id: 304, title: "Фототренд прежней версии" },
  ].map(trend => ({ ...trend, kind: "image", category: "photo", category_title: "Фототренды",
    preview_url: `${mediaOrigin}/trend-${trend.id}.png` }));
  const state = await prepare(page, false, trends);
  await openGallery(page);
  const mode = page.getByRole("group", { name: "Содержимое ленты", exact: true }).getByRole("button", { name: "Тренды", exact: true });
  await mode.click();
  await expect(mode).toHaveAttribute("aria-pressed", "true");
  const cards = page.getByRole("article");
  await expect(cards).toHaveCount(trends.length);
  const trendCard = (title: string) => page.getByRole("article", { name: title, exact: true });
  for (const trend of trends) await expect(trendCard(trend.title).getByRole("heading", { name: trend.title, exact: true })).toBeVisible();
  await expect(trendCard("Популярный фототренд").getByText("Использований: 7", { exact: true })).toBeVisible();
  await expect(trendCard("Новый фототренд").getByText("Использований: 0", { exact: true })).toBeVisible();
  for (const title of ["Фототренд без данных", "Фототренд прежней версии"]) {
    await expect(trendCard(title).getByText(/Использований:/)).toHaveCount(0);
  }
  await expect(cards.getByText(/Повторов:/)).toHaveCount(0);
  expect(paidWrites(state.writes)).toEqual([]);
});

for (const protectedAlbum of [false, true]) {
  test(`${protectedAlbum ? "bound public" : "original owned"} album repeats exactly the second result without thumbnail slides or paid launch`, async ({ page }) => {
    const state = await prepare(page, protectedAlbum);
    await openGallery(page);
    const album = cardByAuthor(page, longAuthor);
    await expect(album.locator(".apix-feed-media img")).toHaveAttribute("src",
      new URL(protectedAlbum ? boundResults[0] : originalA, page.url()).href);
    const like = album.getByRole("button", { name: "Лайк", exact: true });
    await expectReachable(like);
    await like.click();
    await expect.poll(() => state.likes).toBe(1);
    await expect(album.locator(".feed-card-stats")).toContainText("39");
    await expect(page.locator(".apix-media-viewer")).toHaveCount(0);

    await album.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first().click();
    const viewer = page.locator(".apix-media-viewer");
    await expect(viewer).toBeVisible();
    await viewer.getByRole("button", { name: "Следующее фото", exact: true }).click();
    const selected = new URL(protectedAlbum ? boundResults[1] : originalB, page.url()).href;
    await expect.poll(() => viewer.locator("img").first().evaluate(image => (image as HTMLImageElement).src)).toBe(selected);
    // Reaching the last real result must not reveal its thumbnail as a third result.
    await page.keyboard.press("ArrowRight");
    await expect.poll(() => viewer.locator("img").first().evaluate(image => (image as HTMLImageElement).src)).toBe(selected);
    await expect(viewer.getByRole("button", { name: /^Открыть вариант / })).toHaveCount(2);
    await expect(viewer.getByText(hiddenPrompt, { exact: true })).toHaveCount(0);

    const repeat = viewer.getByRole("button", { name: "Повторить эту работу", exact: true });
    await expectReachable(repeat);
    await repeat.click();
    const sheet = page.getByRole("dialog", { name: "Повторить работу", exact: true });
    await expect(sheet).toBeVisible();
    if (protectedAlbum) {
      await sheet.locator("input[type=file]").setInputFiles({ name: "reader.png", mimeType: "image/png",
        buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=", "base64") });
      await expect(sheet.getByText("Реф #1", { exact: true })).toBeVisible();
    }
    await expect.poll(() => state.quotes.at(-1)?.source_image_url).toBe(selected);
    await expect(sheet.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
    expect(state.quotes.every(quote => quote.source_image_url === selected)).toBe(true);
    expect(JSON.stringify(state.quotes)).not.toContain(hiddenPrompt);
    if (!protectedAlbum) expect(JSON.stringify(state.quotes)).not.toContain("preview-");
    expect(paidWrites(state.writes)).toEqual([]);
    expect(state.likes).toBe(1);
  });
}

test("gallery traps keyboard focus and restores it through the repeat overlay and back to its opener", async ({ page }) => {
  const state = await prepare(page);
  await openGallery(page);
  const opener = cardByAuthor(page, longAuthor).getByRole("button", { name: "Открыть внутри приложения", exact: true }).first();
  await opener.focus();
  await page.keyboard.press("Enter");
  const viewer = page.locator(".apix-media-viewer");
  await expect(viewer).toBeVisible();
  const focusIsInside = (scope: Locator) => scope.evaluate(node => node.contains(document.activeElement));
  await expect.poll(() => focusIsInside(viewer)).toBe(true);
  const focusEdge = async (first: boolean) => viewer.evaluate((node, first) => {
    const controls = Array.from(node.querySelectorAll<HTMLElement>("button, a[href], input, select, textarea, [tabindex]"))
      .filter(control => control.tabIndex >= 0 && !control.hasAttribute("disabled") && control.getClientRects().length > 0);
    (first ? controls[0] : controls.at(-1))?.focus();
  }, first);
  await focusEdge(false);
  await page.keyboard.press("Tab");
  await expect.poll(() => focusIsInside(viewer)).toBe(true);
  await focusEdge(true);
  await page.keyboard.press("Shift+Tab");
  await expect.poll(() => focusIsInside(viewer)).toBe(true);

  const repeat = viewer.getByRole("button", { name: "Повторить эту работу", exact: true });
  await repeat.focus();
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog", { name: "Повторить работу", exact: true });
  await expect(sheet).toBeVisible();
  await expect.poll(() => focusIsInside(sheet)).toBe(true);
  await page.keyboard.press("Tab");
  await expect.poll(() => focusIsInside(sheet)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
  await expect(viewer).toBeVisible();
  await expect(repeat).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(viewer).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(paidWrites(state.writes)).toEqual([]);
});
