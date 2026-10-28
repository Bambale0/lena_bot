import { expect, test, type Locator, type Page } from "@playwright/test";

const imageModel = {
  key: "creation-image", display_name: "Nano Banana Pro", modes: ["text", "image"],
  credits: 1.5, max_refs: 4, counts: [1],
  aspect_ratios: ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
  quality_options: [{ value: "2K", label: "2K", credits: 1.5 }, { value: "4K", label: "4K", credits: 3 }],
};
const videoModel = {
  key: "creation-video", display_name: "Видео модель", modes: ["text", "image"],
  credits: 5, max_refs: 1, aspect_ratios: ["16:9", "9:16"], durations: [5, 10], resolutions: ["720p", "1080p"],
};
const h3Model = { ...videoModel, key: "minimax-h3/text-to-video", display_name: "MiniMax H3", max_refs: 9, auto_route_by_inputs: true,
  durations: Array.from({ length: 12 }, (_, index) => index + 4), resolutions: ["768P", "2K"] };

async function prepare(page: Page, videoModels = [videoModel]) {
  const quotes: Record<string, unknown>[] = [];
  const launches: Array<{ kind: string; body: Record<string, unknown> }> = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: "creation-studio-fixture", initDataUnsafe: { user: { id: 123 } }, colorScheme: "dark",
      ready() {}, expand() {}, openLink() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} },
      BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    } } as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Тестовый автор", credits: 120, language: "ru", miniapp_ux2_available: true });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/models/image")) return json([imageModel]);
    if (path.endsWith("/models/video")) return json(videoModels);
    if (path.endsWith("/models/music")) return json([]);
    if (path.endsWith("/prompts") || path.endsWith("/prompts/my")) return json({ items: [] });
    if (path.endsWith("/billing/transactions")) return json({ ok: true, data: { transactions: [], pending: [] } });
    if (path === "/api/v1/generate/video/quote") {
      quotes.push(route.request().postDataJSON());
      return json({ cost_credits: 5, balance_credits: 120, can_run: true, output_seconds: 5, reference_seconds: 0, billable_seconds: 5 });
    }
    if (path === "/api/v1/generate/image" || path === "/api/v1/generate/video") {
      const kind = path.endsWith("/image") ? "image" : "video";
      const body = route.request().postDataJSON();
      launches.push({ kind, body });
      return route.fulfill({ status: 202, json: { id: 902, gen_type: kind, model: body.model, status: "pending", prompt: body.prompt } });
    }
    return json([]);
  });
  await page.goto("/?ux=3");
  await expect(page.locator('[data-ui-version="3"]')).toBeVisible();
  return { quotes, launches, errors };
}

async function openMenu(page: Page) {
  await page.locator('.apix-bottom-nav [data-destination="create"]').click();
  await expect(page.getByRole("heading", { name: "Какой результат нужен?", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Создать фото/ })).toBeVisible();
}

async function openPhoto(page: Page) {
  await openMenu(page);
  await page.getByRole("button", { name: /^Создать фото/ }).click();
  await expect(page.getByRole("textbox", { name: /^Промпт/ })).toBeVisible();
}

const submit = (page: Page) => page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true });

async function expectUncoveredCenter(control: Locator, description: string) {
  await control.scrollIntoViewIfNeeded();
  const observation = await control.evaluate(element => {
    const box = element.getBoundingClientRect();
    const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
    return { uncovered: element.contains(hit), rect: box.toJSON(), hit: hit?.className || hit?.tagName };
  });
  expect(observation.uncovered, `${description}: ${JSON.stringify(observation)}`).toBe(true);
}

test("visual output controls expose their selection and preserve the draft through menu navigation", async ({ page }) => {
  const { launches, errors } = await prepare(page);
  await openPhoto(page);
  const prompt = page.getByRole("textbox", { name: /^Промпт/ });
  await prompt.fill("Портрет в мягком лиловом свете");
  const portrait = page.getByRole("button", { name: "9:16", exact: true });
  await portrait.focus();
  await page.keyboard.press("Space");
  await expect(portrait).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "1:1", exact: true })).toHaveAttribute("aria-pressed", "false");
  await expect(portrait).toBeFocused();
  expect(await portrait.evaluate(element => getComputedStyle(element).outlineStyle)).not.toBe("none");
  await page.getByRole("button", { name: "4K", exact: true }).click();
  await expect(page.getByRole("button", { name: "4K", exact: true })).toHaveAttribute("aria-pressed", "true");

  await openPhoto(page);
  await expect(prompt).toHaveValue("Портрет в мягком лиловом свете");
  await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toHaveValue(imageModel.key);
  await expect(portrait).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "4K", exact: true })).toHaveAttribute("aria-pressed", "true");
  await submit(page).click();
  await expect(page.getByRole("dialog", { name: "Задача #902", exact: true })).toBeVisible();
  expect(launches).toHaveLength(1);
  expect(launches[0]).toMatchObject({ kind: "image", body: { model: imageModel.key, prompt: "Портрет в мягком лиловом свете", aspect_ratio: "9:16", quality: "4K" } });
  expect(errors).toEqual([]);
});

test("the redesigned video editor still quotes the selected format before confirmed launch", async ({ page }) => {
  const { quotes, launches, errors } = await prepare(page);
  await openMenu(page);
  await page.getByRole("button", { name: /^Оживить фото/ }).click();
  await page.getByRole("button", { name: /^(Текст|По тексту)$/ }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Камера плавно отдаляется от героя");
  await page.getByRole("button", { name: "16:9", exact: true }).click();
  await submit(page).click();
  const confirmation = page.getByRole("dialog", { name: "Стоимость видео", exact: true });
  await expect(confirmation).toBeVisible();
  expect(quotes.at(-1)).toMatchObject({ model: videoModel.key, mode: "text", aspect_ratio: "16:9" });
  expect(launches).toHaveLength(0);
  await confirmation.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "9:16", exact: true }).click();
  await submit(page).click();
  await expect(confirmation).toBeVisible();
  expect(quotes.at(-1)).toMatchObject({ aspect_ratio: "9:16" });
  expect(launches).toHaveLength(0);
  await confirmation.getByRole("button", { name: "Запустить за 5 💋", exact: true }).click();
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0].body).toEqual({ ...quotes.at(-1), quoted_credits: 5 });
  expect(errors).toEqual([]);
});

test("creation choices and editor remain usable across mobile and desktop viewports", async ({ page }, info) => {
  const { errors } = await prepare(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: width >= 1000 ? 960 : 844 });
    await openMenu(page);
    const header = page.locator(".apix-app-header");
    const topup = await header.getByRole("button", { name: "Пополнить", exact: true }).boundingBox();
    const balance = await header.locator(".apix-balance-button").boundingBox();
    expect(topup!.x + topup!.width, `top-up and balance do not overlap at ${width}px`).toBeLessThanOrEqual(balance!.x);
    await page.screenshot({ path: info.outputPath(`creation-menu-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: /^Создать фото/ }).click();
    await page.getByRole("textbox", { name: /^Промпт/ }).fill("Портрет для обложки с мягким светом");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const controls = page.getByRole("button", { name: /^(auto|1:1|2:3|3:2|3:4|4:3|4:5|5:4|9:16|16:9|21:9|2K|4K)$/ });
    for (const control of await controls.all()) {
      const box = await control.boundingBox();
      const label = await control.getAttribute("aria-label") || await control.textContent();
      expect(box?.width, `${label} touch width at ${width}px`).toBeGreaterThanOrEqual(44);
      expect(box?.height, `${label} touch height at ${width}px`).toBeGreaterThanOrEqual(44);
    }
    await page.screenshot({ path: info.outputPath(`creation-editor-${width}.png`), fullPage: true });
    const sixTasks = page.getByRole("button", { name: "6", exact: true });
    await expectUncoveredCenter(sixTasks, `task quantity is not covered by the launch bar at ${width}px`);
    await sixTasks.click();
    await expect(sixTasks).toHaveAttribute("aria-pressed", "true");
    const oneTask = page.getByRole("button", { name: "1", exact: true });
    await expectUncoveredCenter(oneTask, `single-task choice is not covered at ${width}px`);
    await oneTask.click();
    await expect(oneTask).toHaveAttribute("aria-pressed", "true");
    const addPhoto = page.locator(".apix-uploader-head").getByText("Добавить", { exact: true });
    await expectUncoveredCenter(addPhoto, `photo upload is not covered by the launch bar at ${width}px`);
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), addPhoto.click()]);
    await chooser.setFiles([]);
    await submit(page).scrollIntoViewIfNeeded();
    const button = await submit(page).boundingBox();
    const nav = await page.locator(".apix-bottom-nav").boundingBox();
    const launchBar = await page.locator(".apix-launch-bar").boundingBox();
    expect(button!.y + button!.height).toBeLessThanOrEqual(nav!.y);
    expect(nav!.y - launchBar!.y - launchBar!.height, "launch bar stays near navigation without floating over the middle of the editor").toBeLessThanOrEqual(48);
    expect(button!.height).toBeGreaterThanOrEqual(44);
    await expectUncoveredCenter(submit(page), `launch remains clickable at ${width}px`);
  }
  expect(errors).toEqual([]);
});

test("MiniMax H3 materials stay reachable together with the editor and launch action", async ({ page }, info) => {
  const { errors, launches } = await prepare(page, [videoModel, h3Model]);
  await page.setViewportSize({ width: 390, height: 667 });
  await openMenu(page);
  await page.getByRole("button", { name: /^Оживить фото/ }).click();
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption(h3Model.key);
  const panel = page.locator("[data-h3-reference-files]");
  await expect(panel).toBeVisible();
  const prompt = page.getByRole("textbox", { name: /^Промпт/ });
  await expectUncoveredCenter(prompt, "H3 materials must not collapse or cover the prompt");
  await prompt.fill("Камера следует за героем вдоль набережной");
  for (const label of ["Видео · до 3, суммарно до 15 сек", "Аудио · до 3, суммарно до 15 сек"]) {
    const input = panel.getByLabel(label, { exact: true });
    await expectUncoveredCenter(input, `${label} is reachable within the editor`);
    expect((await input.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), input.click()]);
    await chooser.setFiles([]);
  }
  const duration = page.getByRole("button", { name: "15 сек", exact: true });
  await expectUncoveredCenter(duration, "the last H3 duration is reachable without horizontal clipping");
  await duration.click();
  await expect(duration).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expectUncoveredCenter(submit(page), "H3 launch remains reachable after inspecting materials");
  await expect(prompt).toHaveValue("Камера следует за героем вдоль набережной");
  await page.screenshot({ path: info.outputPath("creation-h3-materials-mobile.png"), fullPage: true });
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption(videoModel.key);
  await expect(panel).toBeHidden();
  await expect(page.getByRole("group", { name: "Режим", exact: true })).toBeVisible();
  await expect(prompt).toHaveValue("Камера следует за героем вдоль набережной");
  expect(launches).toHaveLength(0);
  expect(errors).toEqual([]);
});

test("the creation tile opens the default H3 materials without requiring a model change", async ({ page }) => {
  const { errors, launches } = await prepare(page, [h3Model]);
  await openMenu(page);
  await page.getByRole("button", { name: /^Оживить фото/ }).click();
  await expect(page.getByRole("combobox", { name: "Модель", exact: true })).toHaveValue(h3Model.key);
  const panel = page.locator("[data-h3-reference-files]");
  await expect(panel).toBeVisible();
  const input = panel.getByLabel("Видео · до 3, суммарно до 15 сек", { exact: true });
  await expectUncoveredCenter(input, "the default H3 material chooser is reachable on first entry");
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), input.click()]);
  await chooser.setFiles([]);
  expect(launches).toHaveLength(0);
  expect(errors).toEqual([]);
});

test("switching to H3 keeps saved draft photos visible and lets the author exclude them", async ({ page }) => {
  const { errors, launches, quotes } = await prepare(page, [videoModel, h3Model]);
  const photoUrl = "https://media.example.test/retained-draft.png";
  await page.route("https://media.example.test/**", route => route.fulfill({ contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlZ5xkAAAAASUVORK5CYII=", "base64") }));
  await page.route("**/api/web/upload-media/check", route => route.fulfill({ json: { ok: true, data: { status: "available" } } }));
  await openMenu(page);
  await page.getByRole("button", { name: /^Оживить фото/ }).click();
  const prompt = page.getByRole("textbox", { name: /^Промпт/ });
  await prompt.fill("Сохранить лицо и добавить плавное движение камеры");
  const links = page.getByPlaceholder("Опционально: HTTPS-ссылки, по одной в строке");
  await links.locator("..").getByText("Вставить ссылку вручную", { exact: true }).click();
  await links.fill(photoUrl);
  const savedPhoto = page.getByRole("group", { name: "Фото 1: retained-draft.png", exact: true });
  await expect(savedPhoto).toBeVisible();
  const included = savedPhoto.getByRole("checkbox", { name: "Использовать фото 1", exact: true });
  await expect(included).toBeChecked();

  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption(h3Model.key);
  await expect(page.locator("[data-h3-reference-files]")).toBeVisible();
  await expect(savedPhoto).toBeVisible();
  await expect(included).toBeChecked();
  await expectUncoveredCenter(included, "the author can inspect and exclude a retained H3 draft photo");
  await included.uncheck();
  await expect(included).not.toBeChecked();
  await expect(savedPhoto).toBeVisible();
  await expect(savedPhoto.getByText("retained-draft.png", { exact: true })).toBeVisible();
  await expect(prompt).toHaveValue("Сохранить лицо и добавить плавное движение камеры");
  expect(launches).toHaveLength(0);
  expect(quotes).toHaveLength(0);
  expect(errors).toEqual([]);
});
