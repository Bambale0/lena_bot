import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const landing = path.resolve(process.cwd(), "../landing");
const model = "bytedance/seedance-2-fast";
async function fixture(page: Page, launchStatus = 202, locked = false) {
  const quotes: Record<string, unknown>[] = [], launches: Record<string, unknown>[] = [];
  await page.route("**/studio.html?*", r => r.fulfill({ path: path.join(landing, "studio.html"), contentType: "text/html" }));
  await page.route("**/js/*.js?*", r => r.fulfill({ path: path.join(landing, "js", new URL(r.request().url()).pathname.split("/").pop()!), contentType: "text/javascript" }));
  await page.route("**/css/prototype-premium.css?*", r => r.fulfill({ path: path.join(landing, "css/prototype-premium.css"), contentType: "text/css" }));
  await page.route("**/api/web/**", r => {
    const url = new URL(r.request().url());
    const json = (data: unknown) => r.fulfill({ json: { ok: true, data } });
    if (url.pathname.endsWith("/me")) return json({ id: 7, credits: 100, full_name: "Reader" });
    if (url.pathname.endsWith("/models/video")) return json([{ key: model, name: "Seedance 2 Fast", type: "video", durations: [5, 10, 15], resolutions: ["480p", "720p"], aspect_ratios: ["9:16", "16:9"], credits: 2, active: true }]);
    if (url.pathname.endsWith("/feed/42")) return json({ id: 42, type: "video", model, original_duration: 10, original_resolution: "720p", original_aspect_ratio: "16:9", source_has_video_reference: locked, result_url: "https://example.test/public.mp4" });
    if (url.pathname.endsWith("/remix/quote")) {
      const body = r.request().postDataJSON(); quotes.push(body);
      const seconds = locked ? 7 : (body.duration_override || 10);
      return json({ cost_credits: seconds * 2 + (launchStatus === 409 && launches.length ? 5 : 0), can_run: true, output_seconds: seconds, duration_options: locked ? [] : [5, 10, 15], default_duration: 10, effective_duration: seconds, duration_lock_reason: locked ? "Длительность определяется исходным видео." : null });
    }
    if (url.pathname.endsWith("/remix")) {
      launches.push(r.request().postDataJSON());
      if (launchStatus !== 202 && (launchStatus !== 409 || launches.length === 1)) return r.fulfill({ status: launchStatus, json: { ok: false, error: "Response unavailable" } });
      return json({ id: 91, status: "pending" });
    }
    if (url.pathname.includes("/prompts")) return json({ items: [] });
    if (url.pathname.includes("/transactions")) return json({ transactions: [], pending: [] });
    if (url.pathname.includes("/auth/config")) return json({});
    return json([]);
  });
  page.on("dialog", d => d.accept());
  await page.goto(`/studio.html?type=video&model=${encodeURIComponent(model)}&feed_remix=42`);
  return { quotes, launches };
}

async function launch(page: Page) {
  await page.locator("[data-generate-button]").click();
  await page.locator("[data-confirm-generation]").click();
}

test("standalone site preserves recipe default and sends only explicit duration override", async ({ page }) => {
  const { quotes, launches } = await fixture(page);
  const duration = page.locator(".account-composer [name=duration]");
  await expect(duration).toHaveValue("10");
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  await expect(duration).toBeEnabled();
  expect(quotes[0]).not.toHaveProperty("duration_override");
  await duration.selectOption("15");
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).toMatchObject({ model, duration: 10, duration_override: 15, quoted_credits: 30 });
  expect(launches[0]).not.toHaveProperty("prompt");
});

test("standalone site blocks ambiguous repeat across reload until history acknowledgement", async ({ page }) => {
  const { launches } = await fixture(page, 503);
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  await page.reload();
  await expect(page.locator("[data-generate-button]")).toBeDisabled();
  await expect(page.getByText(/Результат запуска неизвестен/)).toBeVisible();
  expect(launches).toHaveLength(1);
  const stored = await page.evaluate(() => Object.entries(sessionStorage));
  expect(stored).toContainEqual(["apix:feed-launch:v1:7:42:remix", "pending"]);
  await page.getByRole("button", { name: "Проверить историю" }).click();
  await page.getByRole("button", { name: "Историю проверил — разрешить новый запуск" }).click();
  await expect(page.locator("[data-generate-button]")).toBeEnabled();
  expect(launches).toHaveLength(1);
});

test("standalone site locks measured source edit duration after quote", async ({ page }) => {
  const { launches } = await fixture(page, 202, true);
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  const duration = page.locator(".account-composer [name=duration]");
  await expect(duration).toHaveValue("7");
  await expect(duration).toBeDisabled();
  await expect(page.getByText("Длительность определяется исходным видео.", { exact: true })).toBeVisible();
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  expect(launches[0]).not.toHaveProperty("duration_override");
  expect(launches[0].quoted_credits).toBe(14);
});

test("standalone site keeps legacy duration absent and stale price needs another explicit launch", async ({ page }) => {
  const { launches } = await fixture(page, 409);
  await launch(page);
  await expect.poll(() => launches.length).toBe(1);
  await expect(page.getByText(/Цена изменилась/).first()).toBeVisible();
  expect(launches[0]).toMatchObject({ duration: 10, quoted_credits: 20 });
  expect(launches[0]).not.toHaveProperty("duration_override");
  await page.getByRole("button", { name: "Проверить цену и длительность" }).click();
  await expect(page.getByText(/К оплате: 25/)).toBeVisible();
  expect(launches).toHaveLength(1);
  await launch(page);
  await expect.poll(() => launches.length).toBe(2);
  expect(launches[1]).toMatchObject({ duration: 10, quoted_credits: 25 });
  expect(launches[1]).not.toHaveProperty("duration_override");
});
