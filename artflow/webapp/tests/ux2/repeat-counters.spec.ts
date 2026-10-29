import { expect, test, type Page } from "@playwright/test";

const tasks = [
  { id: 701, model: "model-701", gen_type: "video", prompt: "Видео с повторами", remixes: 7, is_public_feed: true },
  { id: 702, model: "model-702", gen_type: "video", prompt: "Видео без повторов", remixes: 0, is_public_feed: true },
  { id: 703, model: "model-703", gen_type: "image", prompt: "Фото с повторами", remixes: 3, is_public_feed: true },
  { id: 704, model: "model-704", gen_type: "video", prompt: "Приватное видео", remixes: null, is_public_feed: false },
  { id: 705, model: "model-705", gen_type: "video", prompt: "Старый ответ сервера", is_public_feed: true },
  { id: 706, model: "model-706", gen_type: "video", prompt: "Счётчик недоступен", remixes: null, is_public_feed: true },
].map(task => ({ ...task, status: "done", created_at: "2026-10-29T10:00:00Z", result_url: `https://media.example.test/${task.id}.${task.gen_type === "video" ? "mp4" : "png"}` }));

async function prepare(page: Page, admin = true) {
  let repeats = 7;
  const writes: string[] = [];
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: "repeat-count-fixture", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {},
      HapticFeedback: { impactOccurred() {}, notificationOccurred() {} }, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    } } as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("https://media.example.test/**", route => route.abort("failed"));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") writes.push(path);
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture_bot" });
    if (path === "/api/v1/me") return json({ id: 7, tg_id: 123, full_name: "Тест", credits: 120, language: "ru", miniapp_ux2_available: admin });
    if (path.endsWith("/me/permissions")) return json({ is_admin: admin });
    if (path.endsWith("/studio/preview")) return admin ? json({ allowed: true, ui_version: 3 }) : route.fulfill({ status: 403, json: { detail: "Admin access required" } });
    if (path.endsWith("/history")) return json(tasks.map(task => task.id === 701 ? { ...task, remixes: repeats } : task));
    if (/\/generations\/\d+$/.test(path)) {
      const task = tasks.find(row => row.id === Number(path.split("/").at(-1)));
      return json(task?.id === 701 ? { ...task, remixes: repeats } : task);
    }
    if (path.endsWith("/feed") || path.endsWith("/feed/701")) {
      const item = { ...tasks[0], remixes: repeats, author: "Автор видео", likes_count: 2, shares_count: 1 };
      return json(path.endsWith("/feed/701") ? item : [item]);
    }
    if (path.endsWith("/referrals")) return json({ counts: {}, balance: {}, children: {}, withdrawals: [] });
    if (path.endsWith("/image-sessions/active")) return json({ data: null });
    return json([]);
  });
  return { writes, setRepeats(value: number) { repeats = value; } };
}

test("published video and photo repeat counts remain visible in profile and task details", async ({ page }, info) => {
  const state = await prepare(page);
  await page.goto("/?ux=3");
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  const tile = (title: string) => page.getByRole("button", { name: `${title} — Готово`, exact: true });
  await expect(tile("Видео с повторами")).toBeVisible();
  await tile("Видео с повторами").locator("video").evaluateAll(videos => videos.forEach(video => video.dispatchEvent(new Event("error"))));
  await expect(tile("Видео с повторами").locator("video")).toHaveCount(0);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(tile("Видео с повторами").getByText("Повторов: 7", { exact: true })).toBeVisible();
    await expect(tile("Видео без повторов").getByText("Повторов: 0", { exact: true })).toBeVisible();
    await expect(tile("Фото с повторами").getByText("Повторов: 3", { exact: true })).toBeVisible();
    for (const title of ["Приватное видео", "Старый ответ сервера", "Счётчик недоступен"]) {
      await expect(tile(title)).toBeVisible();
      await expect(tile(title).getByText(/Повторов:/)).toHaveCount(0);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await tile("Видео с повторами").scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath("profile-video-repeat-counts.png") });
  await tile("Видео с повторами").click();
  await expect(page.getByRole("dialog").getByText("Повторов: 7", { exact: true })).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Закрыть", exact: true }).click();
  state.setRepeats(8);
  await page.getByRole("button", { name: "Обновить работы", exact: true }).click();
  await expect(tile("Видео с повторами").getByText("Повторов: 8", { exact: true })).toBeVisible();
  await tile("Видео с повторами").click();
  await expect(page.getByRole("dialog").getByText("Повторов: 8", { exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("video repeat count is available inside the feed media viewer", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first().click();
  await expect(page.getByRole("dialog").getByText("Повторов: 7", { exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("ordinary profile tiles show the published video repeat count", async ({ page }) => {
  await prepare(page, false);
  await page.goto("/");
  await page.getByRole("navigation").getByText("Профиль", { exact: true }).click();
  await expect(page.getByRole("button", { name: /model-701/ }).first().getByText("Повторов: 7", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /model-702/ }).first().getByText("Повторов: 0", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /model-705/ }).first().getByText(/Повторов:/)).toHaveCount(0);
});
