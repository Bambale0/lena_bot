import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const photo = { name: "face.png", mimeType: "image/png", buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1e8AAAAASUVORK5CYII=", "base64") };

async function prepare(page: Page) {
  const state = { price: 10, failure: 0, actor: 7, admitted: true,
    quotes: [] as Record<string, string>[], runs: [] as Record<string, unknown>[], payments: 0 };
  const trend = { id: 101, title: "Кинопортрет", kind: "video", preview_url: "",
    user_fields: [{ key: "name", type: "text", label: "Имя героя", required: true }] };
  await page.addInitScript(() => {
    window.Telegram = { WebApp: { initData: "test", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {},
      openLink() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } as any;
  });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("**/api/**", route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/me")) return json({ id: state.actor, tg_id: 123, full_name: "Тест", credits: 100, language: "ru", miniapp_ux2_available: state.admitted });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/trends")) return json([trend]);
    if (path.endsWith("/trends/101")) return json(trend);
    if (path.endsWith("/checkout")) {
      state.quotes.push(Object.fromEntries(url.searchParams));
      if (state.failure) return route.fulfill({ status: state.failure, json: { detail: state.failure === 422 ? "Model not available" : "Расчёт временно недоступен" } });
      return json({ cost_credits: state.price, balance_credits: 100, can_run: true, deficit_credits: 0,
        default_duration: 5, effective_duration: Number(url.searchParams.get("duration") || 5), duration_options: [5, 10], recommended_plan: null });
    }
    if (path.endsWith("/trends/upload")) return json({ asset_id: "signed-photo", url: "https://example.test/face.png", kind: "image" });
    if (path.endsWith("/run")) { state.runs.push(route.request().postDataJSON()); return json({ task: { id: 900, status: "pending", gen_type: "video" } }); }
    if (path.includes("/topup/")) { state.payments++; return json({ transaction_id: 55, pay_url: "https://example.test/pay" }); }
    if (path.endsWith("/payment-methods")) return json(["tbank"]);
    return json([]);
  });
  return state;
}

test("curated rejected duration resets only duration and requires a fresh priced click", async ({ page }, testInfo) => {
  const state = await prepare(page);
  await page.goto("/?ux=3&startapp=trend_101");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  const duration = dialog.getByLabel("Длительность видео", { exact: true });
  await expect(duration).toHaveValue("5");
  await dialog.getByLabel("Имя героя").fill("Анна");
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toBeEnabled();
  state.failure = 422;
  await duration.selectOption("10");
  await expect.poll(() => state.quotes.at(-1)).toEqual({ duration: "10" });
  await expect(dialog.getByRole("button", { name: /Создать ·/ })).toBeDisabled();
  await expect(duration).toBeVisible();
  await expect(duration).toHaveValue("10");
  await expect(dialog).toContainText("Model not available");
  await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toHaveCount(0);
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  const reset = dialog.getByRole("button", { name: "Вернуть длительность автора", exact: true });
  await expect(reset).toBeEnabled();
  expect((await reset.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  const output = "D:/code/2026-10-24/promptx-ux-ui/outputs/final-fix";
  if (testInfo.project.name === "iPhone SE") {
    await mkdir(output, { recursive: true });
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 10_000 });
    await dialog.getByRole("button", { name: "Повторить расчёт", exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${output}/curated-error-320.png`, animations: "disabled" });
  }
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  state.failure = 0; state.price = 15;
  await reset.click();
  await expect(dialog.getByRole("button", { name: "Создать · 15 💋" })).toBeEnabled();
  await expect(duration).toHaveValue("5");
  expect(state.quotes.at(-1)).toEqual({});
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  await expect(dialog).not.toContainText("Model not available");
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  if (testInfo.project.name === "iPhone SE") {
    await dialog.getByRole("button", { name: "Создать · 15 💋" }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${output}/curated-recovered-320.png`, animations: "disabled" });
  }
  await dialog.getByRole("button", { name: "Создать · 15 💋" }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0]).toMatchObject({ asset_id: "signed-photo", user_values: { name: "Анна" }, quoted_credits: 15 });
  expect(state.runs[0]).not.toHaveProperty("duration");
  expect(state.runs[0]).not.toHaveProperty("model");
  expect(state.runs[0]).not.toHaveProperty("prompt");
  expect(state.payments).toBe(0);
});

for (const revoke of ["actor", "admission", "auth"] as const) test(`curated late recovery quote cannot restore the form after ${revoke} loss`, async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/?ux=3&startapp=trend_101");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await expect(dialog.getByLabel("Длительность видео", { exact: true })).toHaveValue("5");
  await dialog.getByLabel("Имя героя").fill("Анна");
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toBeEnabled();
  state.failure = 503;
  await dialog.getByLabel("Длительность видео", { exact: true }).selectOption("10");
  const retry = dialog.getByRole("button", { name: "Повторить расчёт", exact: true });
  await expect(retry).toBeEnabled();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let received = false; let completed = false;
  await page.route("**/api/v1/trends/101/checkout*", async route => {
    received = true;
    await held;
    await route.fallback();
    completed = true;
  });
  state.failure = 0;
  await retry.click();
  await expect.poll(() => received).toBe(true);
  if (revoke === "actor") state.actor = 8;
  if (revoke === "admission") state.admitted = false;
  if (revoke === "auth") await page.route("**/api/v1/me", route => route.fulfill({ status: 401, json: { detail: "Unauthorized" } }));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  release();
  await expect.poll(() => completed).toBe(true);
  await expect(dialog).not.toBeVisible();
  await expect(page.getByLabel("Имя героя")).toHaveCount(0);
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
});

for (const initial of [false, true]) test(`curated ${initial ? "initial" : "selected duration"} transient quote retries without losing the draft or reusing a price`, async ({ page }) => {
  const state = await prepare(page);
  if (initial) state.failure = 503;
  await page.goto("/?ux=3&startapp=trend_101");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  const duration = dialog.getByLabel("Длительность видео", { exact: true });
  if (!initial) await expect(duration).toHaveValue("5");
  await dialog.getByLabel("Имя героя").fill("Анна");
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  if (!initial) {
    await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toBeEnabled();
    state.failure = 503;
    await duration.selectOption("10");
  }
  await expect(dialog).toContainText("Расчёт временно недоступен");
  await expect(dialog.getByRole("button", { name: /Создать ·/ })).toBeDisabled();
  if (initial) {
    await expect(duration).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "Вернуть длительность автора", exact: true })).toHaveCount(0);
  } else await expect(duration).toHaveValue("10");
  const retry = dialog.getByRole("button", { name: "Повторить расчёт", exact: true });
  await expect(retry).toBeEnabled();
  expect((await retry.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let received = false;
  await page.route("**/api/v1/trends/101/checkout*", async route => {
    received = true;
    await held;
    await route.fallback();
  });
  state.failure = 0; state.price = 25;
  await retry.click();
  await expect.poll(() => received).toBe(true);
  await expect(dialog.getByRole("button", { name: /Создать ·/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toHaveCount(0);
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  release();
  await expect(dialog.getByRole("button", { name: "Создать · 25 💋" })).toBeEnabled();
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(duration).toHaveValue(initial ? "5" : "10");
  expect(state.quotes.at(-1)).toEqual(initial ? {} : { duration: "10" });
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  await dialog.getByRole("button", { name: "Создать · 25 💋" }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0]).toMatchObject({ asset_id: "signed-photo", user_values: { name: "Анна" }, quoted_credits: 25 });
  if (initial) expect(state.runs[0]).not.toHaveProperty("duration");
  else expect(state.runs[0]).toHaveProperty("duration", 10);
  expect(state.runs[0]).not.toHaveProperty("model");
  expect(state.runs[0]).not.toHaveProperty("prompt");
  expect(state.payments).toBe(0);
});

test("curated failed author-duration reset still shows the default and retries without an override", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/?ux=3&startapp=trend_101");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  const duration = dialog.getByLabel("Длительность видео", { exact: true });
  await expect(duration).toHaveValue("5");
  await dialog.getByLabel("Имя героя").fill("Анна");
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toBeEnabled();
  await duration.selectOption("10");
  await expect(dialog.getByRole("button", { name: "Создать · 10 💋" })).toBeEnabled();
  state.failure = 503;
  await dialog.getByRole("button", { name: "Вернуть длительность автора", exact: true }).click();
  await expect(dialog).toContainText("Расчёт временно недоступен");
  await expect(duration).toHaveValue("5");
  await expect(dialog.getByRole("button", { name: /Создать ·/ })).toBeDisabled();
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  state.failure = 0; state.price = 15;
  await dialog.getByRole("button", { name: "Повторить расчёт", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Создать · 15 💋" })).toBeEnabled();
  expect(state.quotes.at(-1)).toEqual({});
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  await dialog.getByRole("button", { name: "Создать · 15 💋" }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0]).toMatchObject({ asset_id: "signed-photo", user_values: { name: "Анна" }, quoted_credits: 15 });
  expect(state.runs[0]).not.toHaveProperty("duration");
});
