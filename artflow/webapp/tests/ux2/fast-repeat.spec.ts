import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const photo = { name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) };
async function prepare(page: Page, initialBalance = 100) {
  const state = { balance: initialBalance, price: 10, actor: 7, admitted: true, quoteCount: 0,
    quotes: [] as any[], runs: [] as any[], payments: 0, receipt: "pending", failQuote: false };
  const trend = { id: 101, title: "Кинопортрет", kind: "video", preview_url: "", category: "portrait", category_title: "Портреты", user_fields: [{ key: "name", type: "text", label: "Имя героя", required: true }] };
  const item = { id: 201, model: "video-fixture", gen_type: "video", prompt_hidden: true, prompt: "", author: "Автор", result_url: "https://example.test/clip.mp4", source_has_video_reference: false, original_duration: 5, original_aspect_ratio: "16:9", original_resolution: "720p" };
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: "test", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, openLink() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } as any; });
  await page.route("**/telegram-web-app.js", route => route.fulfill({ body: "" }));
  await page.route("https://example.test/**", route => route.fulfill({ body: "" }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    const json = (value: unknown) => route.fulfill({ json: value });
    if (path.endsWith("/me")) return json({ id: state.actor, tg_id: 123, full_name: "Администратор", credits: state.balance, language: "ru", miniapp_ux2_available: state.admitted });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/models/image")) return json([{ key: "image-fixture", display_name: "Фото", credits: 5, modes: ["text", "image"], max_refs: 2, aspect_ratios: ["1:1"], counts: [1] }]);
    if (path.endsWith("/models/video")) return json([{ key: "video-fixture", display_name: "Видео", credits: 10, modes: ["text", "image"], max_refs: 1, durations: [5, 10], resolutions: ["720p"], aspect_ratios: ["16:9"] }]);
    if (path.endsWith("/models/music")) return json([{ key: "music-fixture", display_name: "Музыка", credits: 20, modes: ["text"] }]);
    if (path.endsWith("/trend-categories")) return json({ items: [{ key: "portrait", title: "Портреты", sort_order: 0, trend_count: 1, preview_items: [trend] }], has_more: false, next_cursor: null });
    if (path.endsWith("/trend-categories/portrait/trends")) return json({ category: { key: "portrait", title: "Портреты", sort_order: 0 }, items: [trend], has_more: false, next_cursor: null });
    if (path.endsWith("/trends")) return json([trend]);
    if (path.endsWith("/trends/101")) return json(trend);
    if (path.endsWith("/feed")) return json([item]);
    if (path.endsWith("/feed/201")) return json(item);
    if (path.endsWith("/checkout") || path.endsWith("/remix/quote")) {
      state.quoteCount++;
      const body = route.request().method() === "POST" ? route.request().postDataJSON() : Object.fromEntries(new URL(route.request().url()).searchParams);
      state.quotes.push(body);
      if (state.failQuote) return route.fulfill({ status: 503, json: { detail: "Расчёт временно недоступен" } });
      return json({ cost_credits: state.price, balance_credits: state.balance, can_run: state.balance >= state.price, deficit_credits: Math.max(0, state.price - state.balance), effective_duration: Number(body.duration || 5), default_duration: 5, duration_options: [5, 10], recommended_plan: { key: "small", label: "Пакет", credits: 100, price_rub: 200, payment_options: [{ provider: "tbank", amount: 200, currency: "RUB" }] } });
    }
    if (path.endsWith("/trends/upload")) return json({ asset_id: "signed-photo", url: "https://example.test/face.jpg", kind: "image" });
    if (path.endsWith("/upload-media")) return json({ data: { url: "https://example.test/face.jpg", kind: "image" } });
    if (path.endsWith("/run") || path.endsWith("/remix")) { state.runs.push(route.request().postDataJSON()); return json({ task: { id: 900, status: "pending", gen_type: "video" }, id: 900, status: "pending", gen_type: "video" }); }
    if (path.endsWith("/plans")) return json([{ key: "small", title: "Пакет", credits: 100, price_rub: 200 }]);
    if (path.endsWith("/payment-methods")) return json(["tbank"]);
    if (path.endsWith("/payment-options")) return json({ methods: ["tbank"], lava_plan_keys: [] });
    if (path.endsWith("/topup/tbank")) { state.payments++; return json({ transaction_id: 55, pay_url: "https://example.test/pay" }); }
    if (path === "/api/web/billing/transactions") return json({ transactions: [{ id: 55, provider: "tbank", status: state.receipt }] });
    return json([]);
  });
  return state;
}

test("fast repeat keeps settings optional and refreshes exact quote on topup cancel", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("combobox", { name: "Модель", exact: true })).not.toBeVisible();
  await dialog.getByText("Настройки повтора", { exact: true }).click();
  await expect(dialog.getByRole("combobox", { name: "Модель", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "10 сек", exact: true }).click();
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 10/ })).toBeEnabled();
  const before = state.quoteCount;
  await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
  state.price = 20;
  await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect.poll(() => state.quoteCount).toBeGreaterThan(before);
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 20/ })).toBeEnabled();
  expect(state.quotes[state.quotes.length - 1]).toMatchObject({ duration_override: 10, reference_urls: ["https://example.test/face.jpg"] });
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  await dialog.getByRole("button", { name: /Запустить повтор · 20/ }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0]).toMatchObject({ duration_override: 10, quoted_credits: 20, reference_urls: ["https://example.test/face.jpg"] });
  expect(state.runs[0]).not.toHaveProperty("prompt");
});

test("curated topup return keeps photo fields and duration but requires a new quote and click", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3&startapp=trend_101");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await dialog.getByLabel("Длительность видео").selectOption("10");
  await dialog.getByLabel("Имя героя").fill("Анна");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: /Создать · 10/ })).toBeDisabled();
  const before = state.quoteCount;
  await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
  state.balance = 100; state.price = 20;
  await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect.poll(() => state.quoteCount).toBeGreaterThan(before);
  await expect(dialog.getByRole("button", { name: /Создать · 20/ })).toBeEnabled();
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(dialog.getByLabel("Длительность видео")).toHaveValue("10");
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
  await dialog.getByRole("button", { name: /Создать · 20/ }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0]).toMatchObject({ duration: 10, asset_id: "signed-photo", user_values: { name: "Анна" }, quoted_credits: 20 });
});

test("curated sufficient balance never confirms an unrelated pending invoice", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3&startapp=trend_101");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  expect(state.payments).toBe(1);
  state.balance = 100;
  await expect(dialog.getByText("Баланс: 100 💋", { exact: true })).toBeVisible({ timeout: 8000 });
  await expect(page.getByText("Оплата зачислена — можно запускать", { exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Пополнить", exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog).toContainText("Платёж пока не подтверждён");
  state.receipt = "failed";
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog).toContainText("Платёж завершился ошибкой");
  await expect(dialog.getByRole("button", { name: "Пополнить", exact: true })).toBeEnabled();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(1);
});

test("global held preflight adopts the inline invoice created while its cabinet was closed", async ({ page }) => {
  const state = await prepare(page, 0);
  let releaseInvoice!: () => void;
  const invoiceResponse = new Promise<void>(resolve => { releaseInvoice = resolve; });
  await page.route("**/api/v1/topup/tbank", async route => {
    state.payments++;
    await invoiceResponse;
    await route.fulfill({ json: { transaction_id: 55, pay_url: "https://example.test/pay" } });
  });
  await page.goto("/?ux=3&startapp=trend_101");
  const runner = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await expect(runner.getByRole("button", { name: /Пополнить здесь/ })).toBeEnabled();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let preflight = false;
  await page.route("**/api/v1/plans", async route => {
    preflight = true;
    await held;
    await route.fulfill({ json: [{ key: "small", title: "Пакет", credits: 100, price_rub: 200 }] });
  });
  await runner.getByRole("button", { name: "Пополнить", exact: true }).click();
  const cabinet = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await cabinet.getByRole("button", { name: /Оплатить через/ }).click();
  await expect.poll(() => preflight).toBe(true);
  await cabinet.getByRole("button", { name: "Закрыть", exact: true }).click();
  await runner.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect.poll(() => state.payments).toBe(1);
  // Receipt of the POST is not completion of its response-derived identity.
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:pending-topup:v1:7")!).transactionId)).toBeNull();
  releaseInvoice();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:pending-topup:v1:7")!).transactionId)).toBe(55);
  const marker = await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:7"));
  expect(JSON.parse(marker!)).toMatchObject({ transactionId: 55 });
  release();
  await runner.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  await expect(cabinet.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  await expect(cabinet.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  expect(state.payments).toBe(1);
  expect(await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:7"))).toBe(marker);
  expect(state.runs).toHaveLength(0);
});

for (const entry of ["global", "curated", "feed"] as const) {
  for (const boundary of ["invoice", "history", "preflight"] as const) {
    for (const status of [401, 403]) test(`${entry} direct ${boundary} ${status} revokes payment access and preserves submitted attempts`, async ({ page }) => {
      const state = await prepare(page, 0);
      await page.goto(entry === "curated" ? "/?ux=3&startapp=trend_101" : entry === "feed" ? "/?ux=3&feed=201" : "/?ux=3");
      if (entry === "global") await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
      const dialog = entry === "global" ? page.getByRole("dialog", { name: "Кабинет оплаты" })
        : page.locator(entry === "curated" ? "#apix-trend-runner-root" : "#apix-feed-remix-runner-root").getByRole("dialog");
      if (entry === "feed") {
        await expect(dialog.locator("input[type=file]")).toBeEnabled();
        await dialog.locator("input[type=file]").setInputFiles(photo);
      }
      const pay = dialog.getByRole("button", { name: entry === "global" ? /Оплатить через/ : /Пополнить здесь/ });
      await expect(pay).toBeEnabled();
      const endpoint = boundary === "history" ? "**/api/web/billing/transactions?limit=100"
        : boundary === "invoice" ? "**/api/v1/topup/tbank"
        : entry === "global" ? "**/api/v1/plans"
        : entry === "curated" ? "**/api/v1/trends/101/checkout**" : "**/api/v1/feed/201/remix/quote";
      let rejected = 0;
      await page.route(endpoint, route => {
        rejected++;
        if (boundary === "invoice") state.payments++;
        return route.fulfill({ status, json: { detail: "Session access revoked" } });
      });
      if (boundary === "preflight" && entry !== "global") {
        await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
        await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
      } else {
        await pay.click();
        if (boundary === "history") await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
      }
      await expect.poll(() => rejected).toBeGreaterThan(0);
      await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
      await expect(dialog).not.toBeVisible();
      await expect(page.getByText("Сессия недоступна. Откройте приложение заново из бота.", { exact: true })).toBeVisible();
      // A fresh successful /me poll cannot resurrect the revoked payment lifetime.
      await page.evaluate(() => window.dispatchEvent(new Event("focus")));
      await expect(page.getByRole("button", { name: "Баланс — Пополнить" })).toHaveCount(0);
      const marker = await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:7"));
      if (boundary === "preflight") { expect(marker).toBeNull(); expect(state.payments).toBe(0); }
      else { expect(marker).not.toBeNull(); expect(state.payments).toBe(1); }
      expect(state.runs).toHaveLength(0);
    });
  }
}

test("curated direct payment-methods 403 revokes before invoice creation", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3");
  await expect(page.getByRole("button", { name: /Кинопортрет/ })).toBeVisible();
  await page.route("**/api/v1/payment-methods", route => route.fulfill({ status: 403, json: { detail: "Forbidden" } }));
  await page.getByRole("button", { name: /Кинопортрет/ }).click();
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  await expect(page.locator("#apix-trend-runner-root").getByRole("dialog")).not.toBeVisible();
  expect(state.payments).toBe(0);
  expect(await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:7"))).toBeNull();
});

test("inline auth revocation cancels held global preflight and fresh login retains the unresolved invoice", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3&startapp=trend_101");
  const runner = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await expect(runner.getByRole("button", { name: /Пополнить здесь/ })).toBeEnabled();
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let preflight = false;
  await page.route("**/api/v1/plans", async route => {
    preflight = true; await held;
    await route.fulfill({ json: [{ key: "small", title: "Пакет", credits: 100, price_rub: 200 }] }).catch(() => {});
  });
  await page.route("**/api/v1/topup/tbank", route => { state.payments++; return route.fulfill({ status: 403, json: { detail: "Forbidden" } }); });
  await runner.getByRole("button", { name: "Пополнить", exact: true }).click();
  const cabinet = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await cabinet.getByRole("button", { name: /Оплатить через/ }).click();
  await expect.poll(() => preflight).toBe(true);
  await cabinet.getByRole("button", { name: "Закрыть", exact: true }).click();
  await runner.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(page.getByRole("button", { name: "Проверить снова", exact: true })).toBeVisible();
  const marker = await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:7"));
  expect(marker).not.toBeNull();
  release();
  await page.unroute("**/api/v1/plans");
  await page.unroute("**/api/v1/topup/tbank");
  await page.getByRole("button", { name: "Проверить снова", exact: true }).click();
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  await expect(cabinet.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  await expect(cabinet.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  expect(state.payments).toBe(1);
  expect(await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:7"))).toBe(marker);
  expect(state.runs).toHaveLength(0);
});

test("global lost invoice response stays guarded across cancel and reload", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.route("**/api/v1/topup/tbank", route => { state.payments++; return route.abort("failed"); });
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  const dialog = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await dialog.getByRole("button", { name: /Оплатить через/ }).click();
  await expect(dialog.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.reload();
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  await expect(dialog.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: /Историю проверил/ })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog).toContainText("не подтверждён");
  await expect(dialog.getByRole("button", { name: /Историю проверил/ })).toBeVisible();
  expect(await dialog.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  await dialog.getByRole("button", { name: /Историю проверил/ }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "D:/code/2026-10-24/promptx-ux-ui/outputs/task-6/topup-uncertain-320.png", animations: "disabled" });
  await dialog.getByRole("button", { name: /Историю проверил/ }).click();
  await expect(dialog).toContainText("остаётся неизвестным");
  await expect(dialog.getByRole("button", { name: /Оплатить через/ })).toBeEnabled();
  expect(state.payments).toBe(1);
  expect(state.runs).toHaveLength(0);
});

test("curated pending invoice survives closing and blocks global topup while preserving its photo", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: /Кинопортрет/ }).click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await dialog.getByLabel("Имя героя").fill("Анна");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  const global = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await expect(global.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  await global.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: /Кинопортрет/ }).click();
  await expect(dialog.getByLabel("Имя героя")).toHaveValue("Анна");
  await expect(dialog.getByAltText("Ваше фото")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Пополнить", exact: true })).toBeDisabled();
  expect(state.payments).toBe(1); expect(state.runs).toHaveLength(0);
});

test("feed inline invoice blocks global topup after closing and reconciles on return", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  const global = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await expect(global.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  state.receipt = "paid"; state.balance = 100;
  await global.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(global).toContainText("Оплата подтверждена");
  await global.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 10/ })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "Проверить оплату", exact: true })).toHaveCount(0);
  expect(state.payments).toBe(1); expect(state.runs).toHaveLength(0);
});

test("an old feed receipt cannot clear a newer global invoice after reopening the draft", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.route("**/api/v1/topup/tbank", route => { state.payments++; return route.fulfill({ json: { transaction_id: 54 + state.payments, pay_url: "https://example.test/pay" } }); });
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  const global = page.getByRole("dialog", { name: "Кабинет оплаты" });
  state.receipt = "paid"; state.balance = 100;
  await global.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(global).toContainText("Оплата подтверждена");
  await global.getByRole("button", { name: /Оплатить через/ }).click();
  await expect.poll(() => state.payments).toBe(2);
  await expect(global.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  await global.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Повторить", exact: true }).click();
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog).toContainText("Платёж пока не подтверждён");
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:pending-topup:v1:7")!).transactionId)).toBe(56);
  expect(state.runs).toHaveLength(0);
});

test("main video shortage shows quoted amounts and refreshes before an explicit launch", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.route("**/api/v1/generate/video/quote", route => { state.quoteCount++; return route.fulfill({ json: { cost_credits: state.price, balance_credits: state.balance, can_run: state.balance >= state.price, output_seconds: 5, reference_seconds: 0, billable_seconds: 5 } }); });
  await page.route("**/api/v1/generate/video", route => { state.runs.push(route.request().postDataJSON()); return route.fulfill({ json: { id: 900, status: "pending", gen_type: "video" } }); });
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Оживить фото", exact: true }).click();
  await page.getByRole("textbox", { name: /^Промпт/ }).fill("Медленно движущаяся камера");
  await page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Стоимость видео" });
  await expect(dialog).toContainText("Не хватает: 10 💋");
  await expect(dialog).toContainText("Баланс: 0 💋");
  await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
  state.balance = 100; state.price = 20;
  await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Запустить за 20 💋" })).toBeEnabled();
  expect(state.runs).toHaveLength(0);
  await dialog.getByRole("button", { name: "Запустить за 20 💋" }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.runs[0]).toMatchObject({ quoted_credits: 20, prompt: "Медленно движущаяся камера" });
});

test("home offers real ready examples and a nonblocking known-zero invitation", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3");
  await expect(page.getByText("Баланс пока 0", { exact: false })).toBeVisible();
  await page.getByRole("tab", { name: "Создать", exact: true }).click();
  await page.getByRole("button", { name: /Повторить готовый пример/ }).click();
  await expect(page.getByText("Кинопортрет", { exact: true }).first()).toBeVisible();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
});

for (const [kind, message, recovery] of [["image", "Insufficient credits: need 5, have 0", true], ["image", "Failed to spend credits", false], ["music", "Insufficient credits: need 20, have 0", true]] as const) {
  test(`${kind} recognized shortage recovery=${recovery} preserves input and never retries`, async ({ page }) => {
    const state = await prepare(page, 0);
    await page.route(`**/api/v1/generate/${kind}`, route => { state.runs.push(route.request().postDataJSON()); return route.fulfill({ status: 402, json: { detail: message } }); });
    await page.goto("/?ux=3");
    await page.getByRole("button", { name: kind === "image" ? "Создать фото" : "Создать музыку", exact: true }).click();
    const prompt = kind === "image" ? page.getByRole("textbox", { name: /^Промпт/ }) : page.getByPlaceholder("Текст песни или идея трека");
    await prompt.fill("Моя сохранённая идея");
    if (kind === "image") await page.getByRole("complementary").getByRole("button", { name: "Создать", exact: true }).click();
    else await page.getByRole("button", { name: "Создать музыку", exact: true }).click();
    await expect.poll(() => state.runs.length).toBe(1);
    const action = page.locator("[data-sonner-toast]").getByRole("button", { name: "Пополнить", exact: true });
    if (recovery) {
      await action.click();
      await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
    } else await expect(action).toHaveCount(0);
    await expect(prompt).toHaveValue("Моя сохранённая идея");
    expect(state.runs).toHaveLength(1); expect(state.payments).toBe(0);
  });
}

test("failed resume quote cannot reuse the previous payable offer", async ({ page }) => {
  const state = await prepare(page);
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 10/ })).toBeEnabled();
  await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
  state.failQuote = true;
  await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(dialog).toContainText("Расчёт временно недоступен");
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
  expect(state.runs).toHaveLength(0);
});

test("server-approved free repeat stays possible with zero balance", async ({ page }) => {
  const state = await prepare(page, 0); state.price = 0;
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 0/ })).toBeEnabled();
  expect(state.runs).toHaveLength(0);
  await dialog.getByRole("button", { name: /Запустить повтор · 0/ }).click();
  await expect.poll(() => state.runs.length).toBe(1);
  expect(state.payments).toBe(0);
});

for (const revoke of ["actor", "admission", "auth"] as const) test(`repeat discards late quote after ${revoke} loss`, async ({ page }) => {
  const state = await prepare(page);
  let release!: () => void; const held = new Promise<void>(resolve => { release = resolve; }); let received = false;
  await page.route("**/api/v1/feed/201/remix/quote", async route => { received = true; await held; await route.fulfill({ json: { cost_credits: 10, balance_credits: 100, can_run: true, deficit_credits: 0 } }).catch(() => {}); });
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect.poll(() => received).toBe(true);
  if (revoke === "actor") state.actor = 8;
  if (revoke === "admission") state.admitted = false;
  if (revoke === "auth") await page.route("**/api/v1/me", route => route.fulfill({ status: 401, json: { detail: "Unauthorized" } }));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  release();
  await expect(dialog).not.toBeVisible();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(0);
});

test("global exact paid receipt refreshes repeat but never creates work", async ({ page }) => {
  const state = await prepare(page, 0);
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
  const payment = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await payment.getByRole("button", { name: /Оплатить через/ }).click();
  await expect.poll(() => state.payments).toBe(1);
  state.balance = 100;
  await payment.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(payment.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  state.receipt = "paid";
  await payment.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(payment).toContainText("Оплата подтверждена");
  await expect(payment.getByRole("button", { name: /Оплатить через/ })).toBeEnabled();
  await payment.getByRole("button", { name: "Закрыть", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 10/ })).toBeEnabled();
  expect(state.runs).toHaveLength(0); expect(state.payments).toBe(1);
});

test("stalled global invoice times out without permitting a second invoice", async ({ page }) => {
  const state = await prepare(page);
  await page.clock.install();
  let release!: () => void; const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/topup/tbank", async route => { state.payments++; await held; await route.fulfill({ json: { transaction_id: 55, pay_url: "https://example.test/pay" } }).catch(() => {}); });
  await page.goto("/?ux=3");
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  const dialog = page.getByRole("dialog", { name: "Кабинет оплаты" });
  await dialog.getByRole("button", { name: /Оплатить через/ }).click();
  await expect.poll(() => state.payments).toBe(1);
  await page.clock.fastForward(21_000);
  await expect(dialog.getByRole("button", { name: "Проверить оплату", exact: true })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: /Оплатить через/ })).toBeDisabled();
  release();
  expect(state.payments).toBe(1);
});

test("global late invoice after actor loss cannot open a payment or affect the next actor", async ({ page }) => {
  const state = await prepare(page);
  await page.addInitScript(() => { (window as any).__links = []; });
  let release!: () => void; const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/topup/tbank", async route => { state.payments++; await held; await route.fulfill({ json: { transaction_id: 55, pay_url: "https://example.test/pay" } }).catch(() => {}); });
  await page.goto("/?ux=3");
  await page.evaluate(() => { window.Telegram!.WebApp.openLink = (url: string) => { (window as any).__links.push(url); }; });
  await page.getByRole("button", { name: "Баланс — Пополнить" }).click();
  await page.getByRole("dialog", { name: "Кабинет оплаты" }).getByRole("button", { name: /Оплатить через/ }).click();
  await expect.poll(() => state.payments).toBe(1);
  state.actor = 8;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator('[data-ui-version="3"]')).toHaveCount(0);
  release();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:pending-topup:v1:7")!).transactionId)).toBeNull();
  expect(await page.evaluate(() => sessionStorage.getItem("apix:pending-topup:v1:8"))).toBeNull();
  expect(await page.evaluate(() => (window as any).__links)).toEqual([]);
  expect(state.payments).toBe(1);
});

for (const width of [320, 390, 1280]) test(`fast repeat and topup screenshots ${width}`, async ({ page }) => {
  const state = await prepare(page, 0);
  await page.setViewportSize({ width, height: 844 });
  await page.goto("/?ux=3&feed=201");
  const dialog = page.locator("#apix-feed-remix-runner-root").getByRole("dialog");
  await expect(dialog.locator("input[type=file]")).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles(photo);
  await expect(dialog.getByRole("button", { name: /Пополнить здесь/ })).toBeVisible();
  const output = "D:/code/2026-10-24/promptx-ux-ui/outputs/task-6";
  await mkdir(output, { recursive: true });
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 10_000 });
  await page.screenshot({ path: `${output}/fast-repeat-${width}.png`, fullPage: true, animations: "disabled" });
  await dialog.getByRole("button", { name: "Пополнить", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Кабинет оплаты" })).toBeVisible();
  await page.screenshot({ path: `${output}/topup-${width}.png`, fullPage: true, animations: "disabled" });
  expect(state.payments).toBe(0); expect(state.runs).toHaveLength(0);
});
