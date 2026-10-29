import { expect, test, type Page } from "@playwright/test";

async function setup(page: Page) {
  const writes: Array<{ path: string; body: Record<string, unknown> }> = [];
  const reads: string[] = [];
  const state = { status: "processing", refunded: false, lose: false, forbid: "", modelCredits: 5 };
  let plan = { id: 3, key: "basic", label: "Пакет", credits: 100, price_rub: 200, price_stars: null as number | null, sort_order: 1, is_active: true };
  await page.addInitScript(() => { window.Telegram = { WebApp: { initData: "test", initDataUnsafe: { user: { id: 123 } }, ready() {}, expand() {}, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} } } } as any; });
  await page.route("**/telegram-web-app.js", r => r.fulfill({ body: "" }));
  await page.route("**/api/**", async r => {
    const url = new URL(r.request().url()), path = url.pathname, method = r.request().method();
    const json = (data: unknown) => r.fulfill({ json: path.startsWith("/api/web") ? { ok: true, data } : data });
    if (method === "GET") reads.push(url.pathname + url.search);
    else writes.push({ path, body: r.request().postDataJSON() });
    if (state.forbid && path.includes(state.forbid)) return r.fulfill({ status: 403, json: { detail: "Revoked" } });
    if (path.endsWith("/me")) return json({ id: 7, tg_id: 123, credits: 100, miniapp_ux2_available: true, is_admin: true });
    if (path.endsWith("/me/permissions")) return json({ is_admin: true });
    if (path.endsWith("/studio/preview")) return json({ allowed: true, ui_version: 3 });
    if (path.endsWith("/auth/config")) return json({ bot_username: "fixture" });
    if (path.endsWith("/admin/overview")) return json({ summary: {} });
    if (path.endsWith("/admin/users")) return json({ items: [{ id: 9, full_name: "Клиент", credits: 30 }] });
    if (path.endsWith("/admin/users/9")) return json({ user: { id: 9, tg_id: 789, full_name: "Клиент", credits: 30 }, stats: {}, ledger: [] });
    if (path.endsWith("/admin/withdrawals")) return json({ items: [] });
    if (path.endsWith("/admin/generations/73/fail")) {
      state.status = "failed"; state.refunded = writes.at(-1)!.body.refund === true;
      if (state.lose) return r.abort("failed");
      return json({ id: 73, status: "failed", changed: true, refunded: state.refunded, refunded_credits: state.refunded ? 40 : 0 });
    }
    if (path.endsWith("/admin/generations")) return json({ total: 1, offset: 0, limit: 25, items: [{ id: 73, user_id: 9, model: "fixture", gen_type: "image", status: state.status, prompt: "Проверяемая задача", task_id: "supplier-73", credits_spent: 40, created_at: "2026-10-25T12:00:00Z" }] });
    if (path.endsWith("/admin/pricing")) return json({ models: [{ id: 2, model_key: "fixture", gen_type: "image", display_name: "Модель", credits: state.modelCredits, is_active: true }], price_plans: [plan] });
    if (path.endsWith("/admin/price-plans/3")) { plan = { ...plan, ...writes.at(-1)!.body }; return json(plan); }
    if (path.endsWith("/admin/model-costs/2")) { state.modelCredits = Number(writes.at(-1)!.body.credits); return json({ id: 2, credits: state.modelCredits }); }
    if (path.endsWith("/admin/ledger")) return json({ items: state.refunded ? [{ id: 1, user_id: 9, delta: 40, balance_after: 140, entry_type: "admin_generation_refund", source_type: "generation", source_id: "73", note: "Возврат администратора", created_at: "2026-10-25T12:00:00Z" }] : [] });
    if (path.endsWith("/prompts/10/deactivate")) return json({ id: 10, status: "deactivated", title: "Публичная идея" });
    if (path.endsWith("/prompts/10")) return json({ id: 10, title: "Публичная идея", description: "", prompt_text: "Описание идеи", status: "approved", model: "fixture", tags: [], likes: 0, uses_count: 0, is_mine: false });
    if (path.endsWith("/prompts")) return json({ items: [{ id: 10, title: "Публичная идея" }], total: 1 });
    return json([]);
  });
  await openOwner(page);
  return { state, writes, reads };
}
async function openOwner(page: Page) {
  await page.goto("/?ux=3");
  await page.getByRole("tab", { name: "Профиль", exact: true }).click();
  await page.getByRole("button", { name: "Управление APIX", exact: true }).click();
}
async function queue(page: Page) {
  await page.getByRole("button", { name: "Очередь генераций", exact: true }).click();
  await page.getByRole("button", { name: /Задача #73/ }).click();
}
async function reviewFailure(page: Page) {
  await page.getByLabel("Причина завершения").fill("Проверено администратором");
  await page.getByRole("button", { name: "Проверить завершение" }).click();
}

test("queue filters and refund require fresh inspection and explicit confirmation", async ({ page }) => {
  const { writes, reads } = await setup(page);
  await page.getByRole("button", { name: "Очередь генераций", exact: true }).click();
  await page.getByLabel("Статус генераций").selectOption("processing");
  await page.getByLabel("Тип генераций").selectOption("image");
  await page.getByLabel("Поиск генераций").fill("supplier-73");
  await page.getByRole("button", { name: "Найти задачи" }).click();
  await expect.poll(() => reads.some(x => x.includes("status=processing") && x.includes("gen_type=image") && x.includes("q=supplier-73") && x.includes("offset=0"))).toBe(true);
  await page.getByRole("button", { name: /Задача #73/ }).click();
  await reviewFailure(page);
  expect(writes).toHaveLength(0);
  await page.getByRole("button", { name: "Подтвердить изменение" }).dblclick();
  await expect(page.getByText("Возвращено: 40 кр.", { exact: true })).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toEqual({ error: "Проверено администратором", refund: true });
});

test("optional no-refund and stale final task never claim returned credits", async ({ page }) => {
  const { state, writes } = await setup(page); await queue(page);
  await page.getByLabel("Вернуть списанные кредиты").uncheck();
  await reviewFailure(page);
  state.status = "done";
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "завершена" })).toBeVisible();
  expect(writes).toHaveLength(0);
});

test("lost refund response survives reload and requires fresh status and ledger reconciliation", async ({ page }) => {
  const { state, writes } = await setup(page); state.lose = true;
  await queue(page); await reviewFailure(page);
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(page.getByText("Результат операции не подтверждён", { exact: true })).toBeVisible();
  await openOwner(page);
  await page.getByRole("button", { name: "Очередь генераций", exact: true }).click();
  await expect(page.getByText("Результат операции не подтверждён", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Сверить задачу и баланс" }).click();
  await expect(page.getByText("Возврат подтверждён журналом: 40 кр.", { exact: true })).toBeVisible();
  expect(writes).toHaveLength(1);
});

test("pricing sends changed fields only after fresh check and shows plan economics notice", async ({ page }) => {
  const { writes } = await setup(page);
  await page.getByRole("button", { name: "Цены и пакеты", exact: true }).click();
  await page.getByRole("button", { name: "Модель · fixture" }).click();
  await page.getByLabel("Стоимость, кредиты").fill("8");
  await page.getByRole("button", { name: "Проверить цены" }).click();
  await expect(page.getByText(/5 → 8/)).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].body).toEqual({ credits: 8 });
  await page.getByRole("button", { name: "Пакет · basic" }).click();
  await expect(page.getByText(/новый продукт Tribute/)).toBeVisible();
});

test("pricing detects stale original and blocks blank or negative fields", async ({ page }) => {
  const { state, writes } = await setup(page);
  await page.getByRole("button", { name: "Цены и пакеты", exact: true }).click();
  await page.getByRole("button", { name: "Модель · fixture" }).click();
  await page.getByLabel("Стоимость, кредиты").fill("-1");
  await expect(page.getByRole("button", { name: "Проверить цены" })).toBeDisabled();
  await page.getByLabel("Стоимость, кредиты").fill("8"); state.modelCredits = 7;
  await page.getByRole("button", { name: "Проверить цены" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "изменились" })).toBeVisible();
  expect(writes).toHaveLength(0);
});

test("ledger uses bounded real user filter and prompt deactivation inspects ID", async ({ page }) => {
  const { state, reads, writes } = await setup(page); state.refunded = true;
  await page.getByRole("button", { name: "Журнал баланса", exact: true }).click();
  await page.getByLabel("ID аккаунта для журнала").fill("9");
  await page.getByRole("button", { name: "Загрузить журнал" }).click();
  await expect(page.getByText("Возврат администратора", { exact: true })).toBeVisible();
  expect(reads.some(x => x.includes("/admin/ledger?user_id=9&limit=50"))).toBe(true);
  await page.getByRole("button", { name: "Опубликованные промпты", exact: true }).click();
  await page.getByLabel("ID промпта").fill("10");
  await page.getByRole("button", { name: "Открыть промпт" }).click();
  await expect(page.getByText("Описание идеи", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Снять с публикации" }).click();
  expect(writes).toHaveLength(0);
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].path).toBe("/api/web/admin/prompts/10/deactivate");
  await expect(page.getByText("Промпт снят с публикации.", { exact: true })).toBeVisible();
});

for (const source of ["/admin/generations", "/admin/users/9"]) {
  test(`authorization loss in ${source} removes all privileged owner state`, async ({ page }) => {
    const { state, writes } = await setup(page); state.forbid = source;
    await page.getByRole("button", { name: source.endsWith("9") ? /Клиент/ : "Очередь генераций", exact: !source.endsWith("9") }).click();
    await expect(page.getByText("Доступ администратора утрачен", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: /Клиент|Проверить публикации|Очередь генераций/ })).toHaveCount(0);
    expect(writes).toHaveLength(0);
  });
}

test("successful no-refund sends explicit false and never claims refund", async ({ page }) => {
  const { writes } = await setup(page); await queue(page);
  await page.getByLabel("Вернуть списанные кредиты").uncheck(); await reviewFailure(page);
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(page.getByText("Задача отмечена ошибочной. Возврат не выполнялся.", { exact: true })).toBeVisible();
  expect(writes[0].body.refund).toBe(false);
});

test("generic 200 does not clear financial uncertainty or claim refund", async ({ page }) => {
  await setup(page);
  let posts = 0;
  await page.route("**/api/web/admin/generations/73/fail", r => { posts++; return r.fulfill({ json: { ok: true, data: { id: 73 } } }); });
  await queue(page); await reviewFailure(page);
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(page.getByText("Результат операции не подтверждён", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Проверить завершение" })).toBeDisabled();
  expect(posts).toBe(1);
  expect(await page.evaluate(() => sessionStorage.getItem("apix:lilac:admin:7:generation"))).toBe('{"ownerId":7,"action":"fail-refund","targetId":73}');
});

test("unavailable session storage blocks financial request", async ({ page }) => {
  const { writes } = await setup(page);
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new Error("denied"); }; });
  await queue(page); await reviewFailure(page);
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "denied" })).toBeVisible();
  expect(writes).toHaveLength(0);
});

test("plan changes expose real fields and omit unchanged nullable legacy price", async ({ page }) => {
  const { writes } = await setup(page);
  await page.getByRole("button", { name: "Цены и пакеты", exact: true }).click();
  await page.getByRole("button", { name: "Пакет · basic" }).click();
  await page.getByLabel("Кредиты в пакете").fill("");
  await expect(page.getByRole("button", { name: "Проверить цены" })).toBeDisabled();
  await page.getByLabel("Кредиты в пакете").fill("120");
  await page.getByLabel("Цена, рубли", { exact: true }).fill("240");
  await page.getByLabel("Порядок пакета").fill("2");
  await page.getByRole("button", { name: "Проверить цены" }).click();
  await page.getByRole("button", { name: "Подтвердить изменение" }).click();
  await expect(page.getByText("Цены сохранены и проверены повторным чтением.", { exact: true })).toBeVisible();
  expect(writes[0].body).toEqual({ credits: 120, price_rub: 240, sort_order: 2 });
});

test("new queue response after leaving panel cannot reopen privileged task data", async ({ page }) => {
  await setup(page);
  let release!: () => void;
  await page.route("**/api/web/admin/generations?**", async r => {
    await new Promise<void>(resolve => { release = resolve; });
    await r.fulfill({ json: { ok: true, data: { total: 1, items: [{ id: 99, model: "late-private", status: "processing" }] } } });
  });
  await page.getByRole("button", { name: "Очередь генераций", exact: true }).click();
  await expect.poll(() => Boolean(release)).toBe(true);
  await page.getByRole("button", { name: "Журнал баланса", exact: true }).click(); release();
  await expect(page.getByRole("button", { name: "Загрузить журнал" })).toBeVisible();
  await expect(page.getByText(/late-private/)).toHaveCount(0);
});

test("admin queue fits 320px and exposes touch-sized navigation", async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 844 }); await setup(page); await queue(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  for (const button of await page.getByRole("navigation", { name: "Административные инструменты" }).getByRole("button").all()) {
    expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  }
  await page.screenshot({ path: info.outputPath("admin-queue-320.png"), fullPage: true });
});
