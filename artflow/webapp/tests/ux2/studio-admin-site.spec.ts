import { expect, test } from "@playwright/test";
import path from "node:path";

const landing = path.resolve(process.cwd(), "../landing");
for (const refunded of [0, 40]) {
  test(`site manual failure reports actual refund ${refunded} and refreshes user cache`, async ({ page }) => {
    let usersReads = 0, writes = 0;
    await page.route("**/account.html", r => r.fulfill({ path: path.join(landing, "account.html"), contentType: "text/html" }));
    await page.route("**/js/prototype-premium.js?*", r => r.fulfill({ path: path.join(landing, "js/prototype-premium.js"), contentType: "text/javascript" }));
    await page.route("**/css/prototype-premium.css?*", r => r.fulfill({ path: path.join(landing, "css/prototype-premium.css"), contentType: "text/css" }));
    await page.route("**/api/web/**", r => {
      const url = new URL(r.request().url());
      const json = (data: unknown) => r.fulfill({ json: { ok: true, data } });
      if (url.pathname.endsWith("/me")) return json({ id: 7, tg_id: 123, full_name: "Администратор", credits: 100, is_admin: true });
      if (url.pathname.endsWith("/admin/users")) { usersReads++; return json({ items: [], total: 0 }); }
      if (url.pathname.endsWith("/admin/generations/73/fail")) { writes++; return json({ id: 73, status: "failed", changed: true, refunded: refunded > 0, refunded_credits: refunded }); }
      if (url.pathname.endsWith("/admin/generations")) return json({ total: 1, items: [{ id: 73, user_id: 9, user: { id: 9, full_name: "Клиент" }, model: "fixture", gen_type: "image", status: writes ? "failed" : "processing", credits_spent: 40, prompt: "Fixture", created_at: "2026-10-25T00:00:00Z" }] });
      if (url.pathname.includes("/admin/")) return json({ items: [], totals: {}, periods: {}, series: {} });
      if (url.pathname.includes("/prompts")) return json({ items: [] });
      if (url.pathname.includes("/transactions")) return json({ transactions: [], pending: [] });
      if (url.pathname.includes("/auth/config")) return json({});
      return json([]);
    });
    page.on("dialog", d => d.accept());
    await page.goto("/account.html#admin");
    await page.locator('[data-admin-section="users"]').click();
    await expect.poll(() => usersReads).toBe(1);
    await page.locator('[data-admin-section="generations"]').click();
    await page.locator('[data-admin-generation-fail="73"]').click();
    await expect.poll(() => writes).toBe(1);
    await expect(page.getByText(refunded ? "Задача отмечена ошибочной. Возвращено: 40 кр." : "Задача отмечена ошибочной. Возврат не выполнялся.", { exact: true })).toBeVisible();
    await page.locator('[data-admin-section="users"]').click();
    await expect.poll(() => usersReads).toBe(2);
  });
}
