import { expect, test, type Page } from "@playwright/test";

async function setup(page: Page) {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  const state = { forbid: "", conflict: false, lose: false, generic: false, seconds: 3600, audience: "admin", instruction: "Сохраняйте узнаваемые черты человека и исходную композицию. Не добавляйте лишние элементы и не изменяйте личность персонажа.", revision: 2, settled: false };
  let wan = { model_key: "wan/3-0-video", policy: "kie_only", neironych_model_id: "wan-3.0", revision: 2, source: "database", updated_by_admin_tg_id: 123, credential_configured: true };
  let qwen = { mode: "text", primary_provider: "neironych", backup_provider: "kie" as string | null, source: "database", updated_by_admin_tg_id: 123 };
  let nano = { model_key: "nano-banana-2.1", primary_provider: "neironych", source: "database", updated_by_admin_tg_id: 123 };
  let products = [{ product_id: 88, plan_key: "basic", payment_url: "https://web.tribute.tg/p/Ab88", currency: "usd", amount_minor: 1099, credits: 100, amount_rub: 200, enabled: true, revision: 2 }];
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: "test", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} } } } as any; });
  await page.route("**/telegram-web-app.js", r => r.fulfill({ body: "" }));
  await page.route("**/api/**", async r => {
    const path = new URL(r.request().url()).pathname, method = r.request().method();
    const json = (data: unknown) => r.fulfill({ json: path.startsWith("/api/web") ? { ok: true, data } : data });
    if (state.forbid && path.includes(state.forbid)) return r.fulfill({ status: 403, json: { detail: "Revoked" } });
    if (method !== "GET") {
      const body = r.request().postDataJSON(); writes.push({ path, body });
      if (state.conflict) return r.fulfill({ status: 409, json: { detail: "Настройки изменились. Обновите данные." } });
      if (path.includes("refund-supplier-review/")) { state.settled = true; if (state.lose) return r.abort("failed"); if (state.generic) return json({ generation_id: 73 }); return json({ generation_id: 73, review_state: "settled", customer_balance_unchanged: true }); }
      if (path.includes("/wan30/")) { state.revision++; wan = { ...wan, policy: body.policy, neironych_model_id: body.neironych_model_id, revision: state.revision }; const { credential_configured: _credential, ...saved } = wan; return json(saved); }
      if (path.includes("/qwen38/")) { qwen = { ...qwen, ...body, mode: path.split("/").at(-1)! }; return json(qwen); }
      if (path.endsWith("/nano-banana-2.1")) { nano = { ...nano, ...body }; return json(nano); }
      if (path.includes("/image-recovery/")) state.seconds = body.auto_refund_seconds;
      if (path.endsWith("/kling4/access")) state.audience = body.audience;
      if (path.endsWith("/feed-recipe-identity")) state.instruction = body.instruction;
      if (path.includes("/tribute-products/")) {
        const id = Number(path.split("/").at(-1)); const row = { product_id: id, ...body, credits: 100, amount_rub: 200, revision: body.expected_revision + 1 }; delete row.expected_revision;
        products = [...products.filter(p => p.product_id !== id), row]; return json(row);
      }
    }
    if (path.endsWith("/me")) return json({ id: 7, tg_id: 123, credits: 100, miniapp_ux2_available: true, is_admin: true });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture" });
    if (path.endsWith("/admin/overview")) return json({ summary: {} });
    if (path.endsWith("/admin/users") || path.endsWith("/admin/withdrawals")) return json({ items: [] });
    if (path.includes("/wan30/")) return json({ ...wan, neironych_model_id: path.endsWith("prime") ? "wan-3.0-prime" : wan.neironych_model_id, revision: state.revision });
    if (path.includes("/qwen38/")) return json({ ...qwen, mode: path.split("/").at(-1) });
    if (path.endsWith("/nano-banana-2.1")) return json(nano);
    if (path.includes("/image-recovery/")) return json({ provider: path.split("/").at(-1), auto_refund_seconds: state.seconds, source: "database", updated_by_admin_tg_id: 123 });
    if (path.endsWith("/refund-supplier-reviews")) return json({ items: state.settled ? [] : [{ generation_id: 73, user_id: 9, model: "fixture", provider: "nexus", state: "needs_admin_resolution", original_task_id: "local-73", provider_task_id: "remote-73", refunded_at: "2026-10-25T12:00:00Z", last_provider_status: "completed", next_check_at: null, checks: 2 }], count: state.settled ? 0 : 1 });
    if (path.endsWith("/tribute-products")) return json({ items: products });
    if (path.endsWith("/admin/pricing")) return json({ models: [], price_plans: [{ id: 3, key: "basic", label: "Пакет", credits: 100, price_rub: 200, price_stars: null, sort_order: 1, is_active: true }] });
    if (path.endsWith("/kling4/access")) return json({ audience: state.audience });
    if (path.endsWith("/feed-recipe-identity")) return json({ instruction: state.instruction });
    return json([]);
  });
  await open(page);
  return { writes, state };
}
async function open(page: Page) {
  await page.goto("/?ux=3");
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Управление APIX", exact: true }).click();
  await page.getByRole("button", { name: "Настройки системы", exact: true }).click();
}
async function confirm(page: Page) { await page.getByRole("button", { name: "Подтвердить изменение" }).click(); }

test("Wan exposes native mapping and sends revision only after confirmation", async ({ page }) => {
  const { writes } = await setup(page);
  await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click();
  await expect(page.getByLabel("Нативный ID Wan")).toHaveValue("wan-3.0");
  await page.getByLabel("Политика Wan").selectOption("kie_neironych");
  await page.getByRole("button", { name: "Проверить маршрут" }).click(); expect(writes).toHaveLength(0);
  await confirm(page); await expect(page.getByText("Настройка сохранена и проверена.", { exact: true })).toBeVisible();
  expect(writes[0].body).toEqual({ policy: "kie_neironych", neironych_model_id: "wan-3.0", expected_revision: 2 });
});
test("Qwen and Nano validate distinct providers and use real route payloads", async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click();
  await page.getByLabel("Семейство маршрута").selectOption("qwen-text");
  await page.getByLabel("Резервный провайдер").selectOption("neironych");
  await expect(page.getByRole("button", { name: "Проверить маршрут" })).toBeDisabled();
  await page.getByLabel("Резервный провайдер").selectOption("");
  await page.getByRole("button", { name: "Проверить маршрут" }).click(); await confirm(page);
  await expect.poll(() => writes.length).toBe(1); expect(writes[0].body).toEqual({ primary_provider: "neironych", backup_provider: null });
  await page.getByLabel("Семейство маршрута").selectOption("nano");
  await page.getByLabel("Основной провайдер").selectOption("nexus");
  await page.getByRole("button", { name: "Проверить маршрут" }).click(); await confirm(page);
  await expect.poll(() => writes.length).toBe(2); expect(writes[1].body).toEqual({ primary_provider: "nexus" });
});
test("Wan conflict closes confirmation and requires explicit reload and new confirmation", async ({ page }) => {
  const { writes, state } = await setup(page); await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click();
  await page.getByLabel("Политика Wan").selectOption("neironych_only"); await page.getByRole("button", { name: "Проверить маршрут" }).click(); state.conflict = true;
  await confirm(page); await expect(page.getByRole("alert")).toContainText("Обновите"); await expect(page.getByRole("alertdialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Проверить маршрут" })).toBeDisabled(); expect(writes).toHaveLength(1);
});
test("recovery validates integer deadline, compares fresh original and saves exact seconds", async ({ page }) => {
  const { writes, state } = await setup(page); await page.getByRole("button", { name: "Автовозврат изображений", exact: true }).click();
  await expect(page.getByLabel("Срок автовозврата, секунды")).toHaveValue("3600");
  for (const value of ["", "-1", "599", "600.5", "86401"]) { await page.getByLabel("Срок автовозврата, секунды").fill(value); await expect(page.getByRole("button", { name: "Проверить срок" })).toBeDisabled(); }
  await page.getByLabel("Срок автовозврата, секунды").fill("7200"); state.seconds = 4000;
  await page.getByRole("button", { name: "Проверить срок" }).click(); await expect(page.getByRole("alert")).toContainText("изменились"); expect(writes).toHaveLength(0);
  await page.getByRole("button", { name: "Обновить настройку" }).click(); await page.getByLabel("Срок автовозврата, секунды").fill("7200");
  await page.getByRole("button", { name: "Проверить срок" }).click(); await confirm(page);
  await expect(page.getByText("Настройка сохранена и проверена.", { exact: true })).toBeVisible(); expect(writes[0].body).toEqual({ auto_refund_seconds: 7200 });
});
for (const family of ["Изображения", "Seedance"]) test(`supplier ${family} validates note and settles without touching customer balance`, async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click(); await page.getByLabel("Очередь поставщиков").selectOption(family === "Seedance" ? "seedance" : "images");
  await page.getByRole("button", { name: /Сверка #73/ }).click(); await page.getByLabel("Комментарий сверки").fill("   ");
  await expect(page.getByRole("button", { name: "Проверить сверку" })).toBeDisabled();
  await page.getByLabel("Комментарий сверки").fill("  Стоимость проверена по отчёту  "); await page.getByRole("button", { name: "Проверить сверку" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Баланс клиента не изменяется"); await confirm(page);
  await expect(page.getByText("Сверка поставщика подтверждена. Баланс клиента не изменён.", { exact: true })).toBeVisible();
  expect(writes[0].body).toEqual({ resolution: "confirmed_not_accepted", note: "Стоимость проверена по отчёту" });
  expect(writes[0].path).toContain(family === "Seedance" ? "/seedance/" : "/images/");
});
test("supplier generic response keeps durable minimal marker and blocks replay after reload", async ({ page }) => {
  const { writes, state } = await setup(page); state.generic = true;
  await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click(); await page.getByRole("button", { name: /Сверка #73/ }).click();
  await page.getByLabel("Комментарий сверки").fill("Достаточно подробный комментарий"); await page.getByRole("button", { name: "Проверить сверку" }).click(); await confirm(page);
  await expect(page.getByText("Результат сверки не подтверждён", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("apix:lilac:admin:7:supplier-images"))).toBe('{"ownerId":7,"action":"confirmed_not_accepted","targetId":73}');
  await open(page); await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click();
  await expect(page.getByText("Результат сверки не подтверждён", { exact: true })).toBeVisible(); expect(writes).toHaveLength(1);
});
test("Tribute uses real plans, exact cents and expected zero revision for new product", async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Каталог Tribute", exact: true }).click();
  await page.getByRole("button", { name: "Новый продукт Tribute", exact: true }).click();
  await page.getByLabel("ID продукта Tribute").fill("89"); await page.getByLabel("Ссылка Tribute").fill("https://web.tribute.tg/p/Ab89");
  await page.getByLabel("Цена, USD").fill("-1"); await expect(page.getByRole("button", { name: "Проверить продукт" })).toBeDisabled();
  await page.getByLabel("Цена, USD").fill("10.99"); await page.getByRole("button", { name: "Проверить продукт" }).click(); expect(writes).toHaveLength(0); await confirm(page);
  await expect(page.getByText("Продукт Tribute сохранён и проверен.", { exact: true })).toBeVisible();
  expect(writes[0].body).toEqual({ plan_key: "basic", payment_url: "https://web.tribute.tg/p/Ab89", currency: "usd", amount_minor: 1099, enabled: true, expected_revision: 0 });
});
test("Kling public access requires exposure confirmation and feed instruction stays out of storage", async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Контент и доступ", exact: true }).click();
  await page.getByLabel("Аудитория Kling 4").selectOption("public"); await page.getByRole("button", { name: "Проверить доступ" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("всем пользователям"); await confirm(page);
  await expect.poll(() => writes.length).toBe(1); expect(writes[0].body).toEqual({ audience: "public" });
  await page.getByLabel("Инструкция идентичности").fill("коротко"); await expect(page.getByRole("button", { name: "Проверить инструкцию" })).toBeDisabled();
  const instruction = "Новая административная инструкция. ".repeat(5); await page.getByLabel("Инструкция идентичности").fill(instruction);
  await page.getByRole("button", { name: "Проверить инструкцию" }).click(); await confirm(page); await expect.poll(() => writes.length).toBe(2);
  expect(writes[1].body).toEqual({ instruction: instruction.trim() });
  expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain("Новая административная");
});
test("settings authorization loss removes all owner controls and mobile fits 320px", async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 844 }); const { state, writes } = await setup(page);
  await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click();
  await expect(page.getByLabel("Нативный ID Wan")).toHaveValue("wan-3.0"); await page.getByLabel("Нативный ID Wan").scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("system-settings-320.png"), fullPage: true });
  for (const button of await page.getByRole("navigation", { name: "Разделы настроек системы" }).getByRole("button").all()) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  for (const [section, label] of [["Автовозврат изображений", "Срок автовозврата, секунды"], ["Сверка поставщиков", "Очередь поставщиков"], ["Каталог Tribute", ""], ["Контент и доступ", "Инструкция идентичности"]]) {
    await page.getByRole("button", { name: section, exact: true }).click();
    if (label) await expect(page.getByLabel(label)).toBeVisible(); else { await page.getByRole("button", { name: /Tribute #88/ }).click(); await expect(page.getByLabel("Цена, USD")).toBeVisible(); }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  state.forbid = "/image-recovery/"; await page.getByRole("button", { name: "Автовозврат изображений", exact: true }).click();
  await expect(page.getByText("Доступ администратора утрачен", { exact: true })).toBeVisible(); await expect(page.getByRole("button", { name: "Настройки системы", exact: true })).toHaveCount(0); expect(writes).toHaveLength(0);
});

test("Wan rejects wrong family or variant and stale revision before sending", async ({ page }) => {
  const { state, writes } = await setup(page); await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click();
  await page.getByLabel("Политика Wan").selectOption("neironych_only");
  for (const value of ["", "wan-3.0-prime", "other-model", "wan-3 bad"]) { await page.getByLabel("Нативный ID Wan").fill(value); await expect(page.getByRole("button", { name: "Проверить маршрут" })).toBeDisabled(); }
  await page.getByLabel("Нативный ID Wan").fill("wan-3.0"); await page.getByRole("button", { name: "Проверить маршрут" }).click(); await expect(page.getByRole("alertdialog")).toBeVisible(); state.revision = 3; await confirm(page);
  await expect(page.getByRole("alert")).toContainText("изменились"); expect(writes).toHaveLength(0);
});
for (const route of ["wan-prime", "qwen-image", "qwen-video"]) test(`route selector reads real ${route} endpoint`, async ({ page }) => {
  const { writes } = await setup(page); const reads: string[] = []; page.on("request", r => { if (r.url().includes("provider-routing")) reads.push(r.url()); });
  await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click(); await page.getByLabel("Семейство маршрута").selectOption(route);
  const path = route === "wan-prime" ? "/wan30/prime" : `/qwen38/${route.slice(5)}`;
  await expect.poll(() => reads.some(url => url.includes(path))).toBe(true);
  if (route === "wan-prime") { await expect(page.getByLabel("Нативный ID Wan")).toHaveValue("wan-3.0-prime"); await page.getByLabel("Нативный ID Wan").fill("wan-3.0"); await expect(page.getByRole("button", { name: "Проверить маршрут" })).toBeDisabled(); }
  else { await page.getByLabel("Резервный провайдер").selectOption(""); await page.getByRole("button", { name: "Проверить маршрут" }).click(); await confirm(page); await expect.poll(() => writes.length).toBe(1); expect(writes[0].path).toContain(path); }
});
test("Nexus recovery catches changes after confirmation without a write", async ({ page }) => {
  const { writes, state } = await setup(page); await page.getByRole("button", { name: "Автовозврат изображений", exact: true }).click(); await page.getByLabel("Провайдер автовозврата").selectOption("nexus");
  await expect(page.getByLabel("Срок автовозврата, секунды")).toHaveValue("3600"); await page.getByLabel("Срок автовозврата, секунды").fill("600");
  await page.getByRole("button", { name: "Проверить срок" }).click(); await expect(page.getByRole("alertdialog")).toBeVisible(); state.seconds = 4200; await confirm(page);
  await expect(page.getByRole("alert")).toContainText("изменились"); expect(writes).toHaveLength(0);
});
test("supplier storage unavailable blocks dispatch and no note is persisted", async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click(); await page.getByRole("button", { name: /Сверка #73/ }).click();
  await page.getByLabel("Комментарий сверки").fill("Достаточно подробный комментарий"); await page.getByRole("button", { name: "Проверить сверку" }).click();
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error("storage denied"); }; }); await confirm(page);
  await expect(page.getByRole("alert").filter({ hasText: "storage denied" })).toBeVisible(); expect(writes).toHaveLength(0);
});
test("supplier lost response requires fresh bounded reconciliation and explicit outside confirmation", async ({ page }) => {
  const { writes, state } = await setup(page); state.lose = true;
  await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click(); await page.getByRole("button", { name: /Сверка #73/ }).click(); await page.getByLabel("Результат сверки").selectOption("cost_reconciled");
  await page.getByLabel("Комментарий сверки").fill("Стоимость согласована по отчёту"); await page.getByRole("button", { name: "Проверить сверку" }).click(); await confirm(page);
  await expect(page.getByText("Результат сверки не подтверждён", { exact: true })).toBeVisible(); await page.getByRole("button", { name: "Сверить очередь поставщика" }).click();
  await expect(page.getByText(/Это не подтверждение расчёта/)).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("apix:lilac:admin:7:supplier-images"))).not.toBeNull();
  await page.getByRole("button", { name: "Я сверил внешний отчёт" }).click(); await confirm(page); await expect(page.getByText(/Блокировка снята по вашему подтверждению/)).toBeVisible();
  expect(writes).toHaveLength(1); expect(writes[0].body.resolution).toBe("cost_reconciled");
});
test("supplier server 409 retains uncertainty, does not mark settled or resend", async ({ page }) => {
  const { writes, state } = await setup(page); state.conflict = true;
  await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click(); await page.getByRole("button", { name: /Сверка #73/ }).click(); await page.getByLabel("Комментарий сверки").fill("Сверено ответственным сотрудником");
  await page.getByRole("button", { name: "Проверить сверку" }).click(); await confirm(page); await expect(page.getByText("Результат сверки не подтверждён", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Сверить очередь поставщика" }).click(); await expect(page.getByText("Задача остаётся открытой. Блокировка сохранена.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Я сверил внешний отчёт" })).toHaveCount(0); expect(writes).toHaveLength(1);
});
test("Tribute immutable terms and server conflict require reload, never automatic overwrite", async ({ page }) => {
  const { writes, state } = await setup(page); await page.getByRole("button", { name: "Каталог Tribute", exact: true }).click(); await page.getByRole("button", { name: /Tribute #88/ }).click();
  await expect(page.getByLabel("ID продукта Tribute")).toHaveAttribute("readonly", ""); await expect(page.getByLabel("Цена, USD")).toHaveValue("10.99"); await expect(page.getByLabel("Цена, USD")).toHaveAttribute("readonly", "");
  await expect(page.getByLabel("Пакет Tribute")).toBeDisabled(); await page.getByLabel("Продукт включён").uncheck(); await page.getByRole("button", { name: "Проверить продукт" }).click(); state.conflict = true; await confirm(page);
  await expect(page.getByRole("alert")).toContainText("изменились"); await expect(page.getByRole("button", { name: "Проверить продукт" })).toBeDisabled(); expect(writes[0].body.expected_revision).toBe(2); expect(writes).toHaveLength(1);
});
test("Tribute rejects malformed canonical link and fractional cents and validates response revision", async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Каталог Tribute", exact: true }).click(); await page.getByRole("button", { name: "Новый продукт Tribute", exact: true }).click();
  await page.getByLabel("ID продукта Tribute").fill("89"); await page.getByLabel("Ссылка Tribute").fill("https://web.tribute.tg.evil/p/Ab89"); await page.getByLabel("Цена, USD").fill("10.99"); await expect(page.getByRole("button", { name: "Проверить продукт" })).toBeDisabled();
  await page.getByLabel("Ссылка Tribute").fill("https://web.tribute.tg/p/Ab89"); await page.getByLabel("Цена, USD").fill("0.001"); await expect(page.getByRole("button", { name: "Проверить продукт" })).toBeDisabled();
  await page.getByLabel("Цена, USD").fill("0.29"); await page.route("**/api/web/admin/payments/tribute-products/89", r => r.fulfill({ json: { ok: true, data: { product_id: 89, plan_key: "basic", payment_url: "https://web.tribute.tg/p/Ab89", currency: "usd", amount_minor: 29, credits: 100, amount_rub: 200, enabled: true, revision: 0 } } }));
  await page.getByRole("button", { name: "Проверить продукт" }).click(); await confirm(page); await expect(page.getByRole("alert")).toContainText("версию"); await expect(page.getByText("Продукт Tribute сохранён и проверен.", { exact: true })).toHaveCount(0); expect(writes).toHaveLength(0);
});
test("content conflicts after confirmation do not overwrite fresh policy", async ({ page }) => {
  const { writes, state } = await setup(page); await page.getByRole("button", { name: "Контент и доступ", exact: true }).click();
  await page.getByLabel("Аудитория Kling 4").selectOption("disabled"); await page.getByRole("button", { name: "Проверить доступ" }).click(); await expect(page.getByRole("alertdialog")).toBeVisible(); state.audience = "public"; await confirm(page); await expect(page.getByRole("alert")).toContainText("изменились");
  await page.getByLabel("Инструкция идентичности").fill("Инструкция для сохранения идентичности. ".repeat(5)); await page.getByRole("button", { name: "Проверить инструкцию" }).click(); await expect(page.getByRole("alertdialog")).toBeVisible(); state.instruction = "Другой сотрудник изменил административную политику. ".repeat(4); await confirm(page);
  await expect(page.getByRole("alert").filter({ hasText: "изменились" })).toHaveCount(2); expect(writes).toHaveLength(0);
});
for (const [section, path] of [["Маршруты провайдеров", "/provider-routing/"], ["Автовозврат изображений", "/image-recovery/"], ["Сверка поставщиков", "/refund-supplier-reviews"], ["Каталог Tribute", "/tribute-products"], ["Контент и доступ", "/kling4/access"]]) test(`authorization loss in ${section} revokes whole owner`, async ({ page }) => {
  const { state, writes } = await setup(page); state.forbid = path; await page.getByRole("button", { name: section, exact: true }).click();
  await expect(page.getByText("Доступ администратора утрачен", { exact: true })).toBeVisible(); await expect(page.getByRole("button", { name: "Проверить публикации" })).toHaveCount(0); expect(writes).toHaveLength(0);
});
test("system subtab navigation aborts late privileged read", async ({ page }) => {
  await setup(page); let release!: () => void;
  await page.route("**/api/web/admin/feed-recipe-identity", async r => { await new Promise<void>(resolve => { release = resolve; }); await r.fulfill({ json: { ok: true, data: { instruction: "late-private-instruction ".repeat(6) } } }); });
  await page.getByRole("button", { name: "Контент и доступ", exact: true }).click(); await expect.poll(() => Boolean(release)).toBe(true);
  await page.getByRole("button", { name: "Каталог Tribute", exact: true }).click(); release(); await expect(page.getByRole("button", { name: "Новый продукт Tribute" })).toBeVisible();
  await expect(page.getByLabel("Инструкция идентичности")).toHaveCount(0); await expect(page.getByText(/late-private-instruction/)).toHaveCount(0);
});
test("Tribute can disable a historical product after package economics changed", async ({ page }) => {
  const { writes } = await setup(page);
  await page.route("**/api/web/admin/pricing", r => r.fulfill({ json: { ok: true, data: { models: [], price_plans: [{ id: 3, key: "basic", label: "Пакет", credits: 100, price_rub: 300, price_stars: null, sort_order: 1, is_active: true }] } } }));
  await page.getByRole("button", { name: "Каталог Tribute", exact: true }).click(); await page.getByRole("button", { name: /Tribute #88/ }).click();
  await page.getByLabel("Продукт включён").uncheck(); await page.getByRole("button", { name: "Проверить продукт" }).click(); await confirm(page);
  await expect(page.getByText("Продукт Tribute сохранён и проверен.", { exact: true })).toBeVisible(); expect(writes[0].body.enabled).toBe(false);
});

for (const family of ["providers", "recovery", "suppliers", "tribute", "content"]) test(`failed ${family} command is never replayed on reload`, async ({ page }) => {
  await setup(page); let attempts = 0;
  await page.route("**/api/web/admin/**", r => {
    if (r.request().method() !== "PUT") return r.fallback();
    attempts++; return r.fulfill({ status: 503, json: { detail: "Проверка поставщика недоступна" } });
  });
  if (family === "providers") { await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click(); await page.getByLabel("Политика Wan").selectOption("neironych_only"); await page.getByRole("button", { name: "Проверить маршрут" }).click(); }
  if (family === "recovery") { await page.getByRole("button", { name: "Автовозврат изображений", exact: true }).click(); await page.getByLabel("Срок автовозврата, секунды").fill("7200"); await page.getByRole("button", { name: "Проверить срок" }).click(); }
  if (family === "suppliers") { await page.getByRole("button", { name: "Сверка поставщиков", exact: true }).click(); await page.getByRole("button", { name: /Сверка #73/ }).click(); await page.getByLabel("Комментарий сверки").fill("Сверено по отчёту поставщика"); await page.getByRole("button", { name: "Проверить сверку" }).click(); }
  if (family === "tribute") { await page.getByRole("button", { name: "Каталог Tribute", exact: true }).click(); await page.getByRole("button", { name: /Tribute #88/ }).click(); await page.getByLabel("Продукт включён").uncheck(); await page.getByRole("button", { name: "Проверить продукт" }).click(); }
  if (family === "content") { await page.getByRole("button", { name: "Контент и доступ", exact: true }).click(); await page.getByLabel("Аудитория Kling 4").selectOption("disabled"); await page.getByRole("button", { name: "Проверить доступ" }).click(); }
  await confirm(page); await expect(page.getByRole("alert").filter({ hasText: "недоступна" })).toBeVisible();
  await expect(page.getByRole("alertdialog")).toHaveCount(0); await open(page); expect(attempts).toBe(1);
});
test("401 during confirmed settings write revokes owner and prevents another send", async ({ page }) => {
  await setup(page); let attempts = 0;
  await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click(); await page.getByLabel("Политика Wan").selectOption("neironych_only"); await page.getByRole("button", { name: "Проверить маршрут" }).click();
  await page.route("**/api/web/admin/provider-routing/wan30/standard", r => r.request().method() === "PUT" ? (attempts++, r.fulfill({ status: 401, json: { detail: "Expired" } })) : r.fallback()); await confirm(page);
  await expect(page.getByText("Доступ администратора утрачен", { exact: true })).toBeVisible(); await expect(page.getByRole("alertdialog")).toHaveCount(0); expect(attempts).toBe(1);
});
test("confirmation offers touch-sized controls and cancellation never sends", async ({ page }) => {
  const { writes } = await setup(page); await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click(); await page.getByLabel("Политика Wan").selectOption("neironych_only"); await page.getByRole("button", { name: "Проверить маршрут" }).click();
  for (const button of await page.getByRole("alertdialog").getByRole("button").all()) expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await page.getByRole("button", { name: "Отмена", exact: true }).click(); await expect(page.getByRole("alertdialog")).toHaveCount(0); expect(writes).toHaveLength(0);
});
test("feed policy length follows server Unicode characters instead of UTF16 units", async ({ page }) => {
  await setup(page); await page.getByRole("button", { name: "Контент и доступ", exact: true }).click(); await page.getByLabel("Инструкция идентичности").fill("🙂".repeat(60));
  await expect(page.getByRole("button", { name: "Проверить инструкцию" })).toBeDisabled();
});
test("a later failed settings write cannot leave the previous success notice visible", async ({ page }) => {
  const { state } = await setup(page); await page.getByRole("button", { name: "Маршруты провайдеров", exact: true }).click(); await page.getByLabel("Политика Wan").selectOption("neironych_only"); await page.getByRole("button", { name: "Проверить маршрут" }).click(); await confirm(page);
  await expect(page.getByText("Настройка сохранена и проверена.", { exact: true })).toBeVisible(); await page.getByLabel("Политика Wan").selectOption("kie_only"); await page.getByRole("button", { name: "Проверить маршрут" }).click(); state.conflict = true; await confirm(page);
  await expect(page.getByRole("alert")).toBeVisible(); await expect(page.getByText("Настройка сохранена и проверена.", { exact: true })).toHaveCount(0);
});
