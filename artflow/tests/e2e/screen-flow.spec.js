const { test, expect } = require("@playwright/test");
const { installApiMocks } = require("./mock-api");

async function attachScreen(page, testInfo, name) {
  await testInfo.attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
}

async function expectNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    return Math.max(root.scrollWidth, body?.scrollWidth || 0) - window.innerWidth;
  });
  expect(overflow).toBeLessThanOrEqual(2);
}

test.describe("public discovery screens", () => {
  test("home explains the product and login modal is usable", async ({ page }, testInfo) => {
    await installApiMocks(page, { authenticated: false });
    await page.goto("/");

    await expect(page.locator("h1")).toContainText("Создайте картинку, видео или музыку");
    await expect(page.locator('a[href="studio.html?type=image&flow=text"]')).toBeVisible();
    await expect(page.locator('a[href="models.html"]')).toBeVisible();

    await page.locator("[data-open-login]").first().click();
    await expect(page.locator("[data-login-modal]")).toBeVisible();
    await expect(page.locator("#login-title")).toContainText("Откройте кабинет APIX");
    await page.locator("[data-close-login]").click();
    await expect(page.locator("[data-login-modal]")).toBeHidden();

    await attachScreen(page, testInfo, "home-guest");
  });

  test("models catalog loads data and filters by media type", async ({ page }, testInfo) => {
    await installApiMocks(page, { authenticated: false });
    await page.goto("/models.html");

    await expect(page.locator("h1")).toContainText("Выберите модель под задачу");
    await expect.poll(async () => Number(await page.locator("[data-total-models]").textContent())).toBeGreaterThan(0);
    await expect(page.locator("[data-model-grid]")).toContainText("GPT Image 2");

    const videoFilter = page.locator('[data-model-filter] button[data-type="video"]');
    await videoFilter.click();
    await expect(videoFilter).toHaveClass(/active/);
    await expect(page.locator("[data-model-grid]")).toContainText("Kling 3.0");

    await attachScreen(page, testInfo, "models-video-filter");
  });

  test("gallery renders real examples and switches source", async ({ page }, testInfo) => {
    await installApiMocks(page, { authenticated: false });
    await page.goto("/gallery.html");

    await expect(page.locator("h1")).toContainText("Живые примеры APIX");
    await expect(page.locator("[data-gallery-grid]")).toContainText(/Премиальный|creator/i);

    const topDay = page.locator('[data-feed-source="top_day"]');
    await topDay.click();
    await expect(topDay).toHaveAttribute("aria-pressed", "true");

    await attachScreen(page, testInfo, "gallery-top-day");
  });

  test("guest studio presents an explicit login gate instead of a blank screen", async ({ page }, testInfo) => {
    await installApiMocks(page, { authenticated: false });
    await page.goto("/studio.html?type=image&flow=text");

    await expect(page.locator("h1")).toContainText("Создайте кадр, ролик или трек");
    await expect(page.locator("[data-guest-only]")).toBeVisible();
    await expect(page.locator(".standalone-workflow")).toBeHidden();

    await page.locator("[data-guest-only] [data-open-login]").click();
    await expect(page.locator("[data-login-modal]")).toBeVisible();

    await attachScreen(page, testInfo, "studio-guest-gate");
  });
});

test.describe("authenticated product flows", () => {
  test("image creation reaches the generation API", async ({ page }, testInfo) => {
    const calls = await installApiMocks(page, { authenticated: true });
    await page.goto("/studio.html?type=image&flow=text");

    const form = page.locator(".account-composer");
    await expect(form).toBeVisible();
    await expect(page.locator("[data-account-model-select]")).toBeVisible();
    await expect.poll(async () => page.locator("[data-account-model-select] option").count()).toBeGreaterThan(0);

    await page.locator('textarea[name="prompt"]').fill(
      "Рекламный портрет продукта, мягкий студийный свет, чистый фон, высокая детализация",
    );
    await page.locator("[data-generate-button]").click();

    await expect.poll(() => calls.generate.length).toBe(1);
    expect(calls.generate[0].path).toContain("/generate/image");
    await expect(page.locator("[data-generation-status]")).toBeVisible();

    await attachScreen(page, testInfo, "studio-image-processing");
  });

  test("account hash routing opens billing and referrals without exposing admin", async ({ page }, testInfo) => {
    await installApiMocks(page, { authenticated: true, isAdmin: false });
    await page.goto("/account.html#billing");

    await expect(page.locator(".account-shell")).toBeVisible();
    const billingTab = page.locator('[data-tab="billing"]');
    await expect(billingTab).toHaveClass(/active/);
    await expect(page.locator('[data-panel="billing"]')).toHaveClass(/active/);

    const referralsTab = page.locator('[data-tab="referrals"]');
    await referralsTab.click();
    await expect(referralsTab).toHaveClass(/active/);
    await expect(page.locator('[data-panel="referrals"]')).toHaveClass(/active/);
    await expect(page.locator("[data-referral-panel]")).toContainText(/TESTREF|Партн|рефера/i);
    await expect(page.locator("[data-admin-only]")).toBeHidden();

    await attachScreen(page, testInfo, "account-referrals");
  });

  test("admin navigation is visible only for an admin user", async ({ page }) => {
    await installApiMocks(page, { authenticated: true, isAdmin: true });
    await page.goto("/account.html");

    await expect(page.locator(".account-shell")).toBeVisible();
    await expect(page.locator("[data-admin-only]")).toBeVisible();
  });
});

test.describe("resilience and responsive UX", () => {
  test("public screens do not overflow a 390px viewport", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installApiMocks(page, { authenticated: false });

    for (const [name, path] of [
      ["home", "/"],
      ["studio", "/studio.html"],
      ["models", "/models.html"],
      ["gallery", "/gallery.html"],
      ["account", "/account.html"],
    ]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      await expectNoHorizontalOverflow(page);
      await attachScreen(page, testInfo, `mobile-${name}`);
    }
  });

  test("an unavailable landing API does not erase the public page", async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await installApiMocks(page, { authenticated: false, failPaths: ["/landing"] });
    await page.goto("/");

    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("main")).toContainText("APIX");
    expect(pageErrors).toEqual([]);
  });
});
