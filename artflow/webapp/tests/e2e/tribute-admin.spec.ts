import { expect, test } from "@playwright/test";
import path from "node:path";

const landing = path.resolve(process.cwd(), "../landing");
const offer = {product_id: 1001, plan_key: "pack", payment_url: "https://web.tribute.tg/p/Test", currency: "usd", amount_minor: 200, credits: 15, amount_rub: 150, enabled: true, revision: 1};

test.beforeEach(async ({ page }) => {
  await page.route("**/tribute-admin.html", route => route.fulfill({path: path.join(landing, "tribute-admin.html"), contentType: "text/html"}));
  await page.route("**/js/tribute-admin.js", route => route.fulfill({path: path.join(landing, "js/tribute-admin.js"), contentType: "text/javascript"}));
  await page.route("**/css/prototype-premium.css", route => route.fulfill({path: path.join(landing, "css/prototype-premium.css"), contentType: "text/css"}));
  await page.route("https://telegram.org/**", route => route.fulfill({body: ""}));
});

test("catalog admin hides controls for unauthenticated users", async ({ page }) => {
  await page.route("**/api/web/admin/payments/tribute-products", route => route.fulfill({status: 401, json: {ok: false, error: "Authentication required"}}));
  await page.goto("/tribute-admin.html");
  await expect(page.locator("#catalog-status")).toContainText("Войдите");
  await expect(page.locator("#catalog-form")).toBeHidden();
});

test("catalog editor loads retained offer and submits optimistic revision once", async ({ page }) => {
  let current = {...offer};
  const writes: Array<Record<string, unknown>> = [];
  await page.route("**/api/web/admin/payments/tribute-products", route => route.fulfill({json: {ok: true, data: {items: [current]}}}));
  await page.route("**/api/web/admin/payments/tribute-products/1001", async route => {
    const body = route.request().postDataJSON();
    writes.push(body);
    current = {...current, enabled: body.enabled, revision: 2};
    await route.fulfill({json: {ok: true, data: current}});
  });
  await page.goto("/tribute-admin.html");
  await page.locator("#catalog-select").selectOption("1001");
  await expect(page.locator('[name="product_id"]')).toHaveAttribute("readonly", "");
  await expect(page.locator("#catalog-status")).toContainText("15 кредитов");
  await page.locator('[name="enabled"]').uncheck();
  await page.getByRole("button", {name: "Проверить и сохранить"}).click();
  await expect(page.locator("#catalog-status")).toContainText("Сохранено");
  expect(writes).toEqual([{plan_key: "pack", payment_url: offer.payment_url, currency: "usd", amount_minor: 200, enabled: false, expected_revision: 1}]);
  await expect(page.locator('[name="expected_revision"]')).toHaveValue("2");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
});

test("catalog conflict preserves draft and never automatically retries", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/web/admin/payments/tribute-products", route => route.fulfill({json: {ok: true, data: {items: [offer]}}}));
  await page.route("**/api/web/admin/payments/tribute-products/1001", route => {
    writes += 1;
    return route.fulfill({status: 409, json: {ok: false, error: "Stale revision"}});
  });
  await page.goto("/tribute-admin.html");
  await page.locator("#catalog-select").selectOption("1001");
  await page.getByRole("button", {name: "Проверить и сохранить"}).click();
  await expect(page.locator("#catalog-status")).toContainText("Обновите каталог");
  await expect(page.locator('[name="expected_revision"]')).toHaveValue("1");
  expect(writes).toBe(1);
});
