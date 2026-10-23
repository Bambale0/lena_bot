import { expect, test } from "@playwright/test";
import path from "node:path";
const landing = path.resolve(process.cwd(), "../landing");
test.beforeEach(async ({ page }) => {
  for (const file of ["wan-routing-admin.html", "js/wan-routing-admin.js", "css/prototype-premium.css"]) {
    await page.route("**/" + file, route => route.fulfill({ path: path.join(landing, file), contentType: file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html" }));
  }
  await page.route("https://telegram.org/**", route => route.fulfill({ body: "" }));
});
test("routing controls stay hidden without server admin authorization", async ({ page }) => {
  await page.route("**/api/web/admin/provider-routing/wan30/*", route => route.fulfill({ status: 403, json: { ok: false, error: "Forbidden" } }));
  await page.goto("/wan-routing-admin.html");
  await expect(page.getByRole("status")).toContainText("права администратора");
  await expect(page.locator("form")).toBeHidden();
});
test("admin changes both models without redeploy and conflict never replays a write", async ({ page }) => {
  const rows = {
    standard: { policy: "neironych_kie", neironych_model_id: "wan-3", revision: 1, credential_configured: true },
    prime: { policy: "neironych_kie", neironych_model_id: "wan-3-prime", revision: 1, credential_configured: true },
  };
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/web/admin/provider-routing/wan30/*", route => {
    const variant = route.request().url().endsWith("prime") ? "prime" : "standard";
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON(); writes.push({ variant, ...body });
      if (variant === "prime") return route.fulfill({ status: 409, json: { ok: false, error: "Настройки изменились" } });
      rows[variant] = { ...rows[variant], ...body, revision: 2 };
    }
    return route.fulfill({ json: { ok: true, data: rows[variant] } });
  });
  await page.goto("/wan-routing-admin.html");
  await expect(page.getByLabel("ID модели Нейроныча")).toHaveValue("wan-3");
  await page.getByRole("combobox", { name: "Маршрут", exact: true }).selectOption("kie_only");
  await page.getByRole("button", { name: "Проверить и сохранить" }).click();
  await expect(page.getByRole("status")).toContainText("Сохранено");
  expect(writes[0]).toEqual({ variant: "standard", policy: "kie_only", neironych_model_id: "wan-3", expected_revision: 1 });
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("prime");
  await expect(page.getByLabel("ID модели Нейроныча")).toHaveValue("wan-3-prime");
  await page.getByRole("button", { name: "Проверить и сохранить" }).click();
  await expect(page.getByRole("status")).toContainText("Настройки изменились");
  await page.getByRole("button", { name: "Проверить и сохранить" }).click();
  expect(writes).toHaveLength(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
});
