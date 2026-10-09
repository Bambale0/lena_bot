import { expect, test, type Page } from "@playwright/test";

const draftKey = "apix:feed-repeat-draft:v2:1:201";
const source = {
  id: 201, model: "nano-banana-2", gen_type: "image", prompt: "", prompt_hidden: true,
  result_url: "https://example.test/source.png", result_urls: ["https://example.test/source.png"],
  preview_url: "https://example.test/source.png", preview_urls: ["https://example.test/source.png"],
  likes_count: 0, shares_count: 0, remixes: 0, aspect_ratio: "1:1", author: "Tribute QA", is_mine: false,
};

async function tributeCheckout(page: Page, lostResponse = false) {
  const state = { funded: false, topups: 0, generations: 0 };
  await page.addInitScript(() => {
    window.Telegram = { WebApp: {
      initData: "test", initDataUnsafe: { user: { id: 123, first_name: "Test" } }, colorScheme: "dark",
      ready: () => undefined, expand: () => undefined, openLink: () => undefined,
      HapticFeedback: { impactOccurred: () => undefined, notificationOccurred: () => undefined },
    } } as typeof window.Telegram;
  });
  await page.route("**/api/v1/me", route => route.fulfill({ json: {
    id: 1, tg_id: 123, username: "tester", full_name: "Test", credits: state.funded ? 15 : 0,
    referral_balance: 0, language: "ru",
  } }));
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [{
    key: "nano-banana-2", display_name: "Nano Banana 2", credits: 5, modes: ["text", "image"],
    aspect_ratios: ["1:1"], quality_options: [{ value: "2K", label: "2K" }], counts: [1], max_refs: 4,
  }] }));
  await page.route("**/api/v1/models/video", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [source] }));
  await page.route("**/api/v1/trends?**", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/plans", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/payment-methods", route => route.fulfill({ json: ["tribute"] }));
  await page.route("**/api/v1/feed/201/remix/quote", route => route.fulfill({ json: {
    cost_credits: 5, balance_credits: state.funded ? 15 : 0, can_run: state.funded,
    deficit_credits: state.funded ? 0 : 5,
    recommended_plan: state.funded ? null : {
      key: "credits_15", label: "мини", credits: 15, price_rub: 150,
      payment_options: [{ provider: "tribute", amount: 2, currency: "USD" }],
    },
  } }));
  await page.route("**/api/v1/topup/tribute", route => {
    state.topups++;
    expect(route.request().postDataJSON()).toEqual({ plan_key: "credits_15" });
    return lostResponse ? route.abort("failed") : route.fulfill({ json: {
      pay_url: "https://web.tribute.tg/p/DDs", credits: 15, amount_rub: 150, amount_usd: 2, provider: "tribute",
    } });
  });
  // Even an owned paid purchase is not proof that this static product checkout settled.
  await page.route("**/api/web/billing/transactions?**", route => route.fulfill({ json: { data: {
    transactions: [{ id: 701, provider: "tribute", external_id: "digital:78901", status: "paid", credits: 15 }],
  } } }));
  await page.route("**/api/web/upload-media", route => route.fulfill({ json: { data: {
    url: "https://example.test/face.jpg", kind: "image", content_type: "image/jpeg", size: 4,
  } } }));
  await page.route("**/api/v1/feed/201/remix", route => {
    state.generations++;
    expect(route.request().postDataJSON()).toMatchObject({
      model: "nano-banana-2", source_image_url: source.result_url,
      reference_urls: ["https://example.test/face.jpg"], change_request: "Белый костюм",
    });
    return route.fulfill({ status: 202, json: {
      id: 9201, model: "nano-banana-2", gen_type: "image", prompt: "", prompt_hidden: true,
      status: "pending", result_url: null, result_urls: [], credits_spent: 5, created_at: new Date().toISOString(),
    } });
  });
  return state;
}

for (const lostResponse of [false, true]) {
  test(`funded Tribute repeat survives ${lostResponse ? "lost checkout response" : "webhook delay"} without claiming receipt or starting another checkout`, async ({ page }) => {
    const state = await tributeCheckout(page, lostResponse);
    await page.goto("/?tgWebAppData=test&remix=201");
    const dialog = page.getByRole("dialog", { name: "Повторить работу" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles({
      name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect(dialog.getByText("Реф #1")).toBeVisible();
    await dialog.getByLabel("Что изменить в образе").fill("Белый костюм");
    await dialog.getByRole("button", { name: "Пополнить здесь · 2 USD", exact: true }).click();
    await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toHaveCount(0);
    await expect.poll(() => state.topups).toBe(1);

    // A later authoritative quote sees the webhook's balance credit. The product
    // checkout still has no transaction_id, so it must not be marked paid.
    state.funded = true;
    await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled({ timeout: 12_000 });
    await expect(dialog.getByText("Баланс достаточен для повтора", { exact: true })).toBeVisible();
    await page.reload();
    await expect(dialog.getByLabel("Что изменить в образе")).toHaveValue("Белый костюм");
    await expect(dialog.getByText("Реф #1")).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
    await expect(dialog.getByText("Баланс достаточен для повтора", { exact: true })).toBeVisible();
    await expect(dialog.getByText("Статус этой оплаты не подтверждён. Новое пополнение заблокировано, чтобы избежать повторной оплаты.", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Пополнить здесь|Открыть эту оплату/ })).toHaveCount(0);
    expect(state.generations).toBe(0);
    expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).payment, draftKey)).toMatchObject({
      provider: "tribute", planKey: "credits_15", transactionId: null,
    });

    await dialog.getByRole("button", { name: /Запустить повтор/ }).click();
    await expect(page.getByRole("dialog", { name: /Задача #9201/ })).toBeVisible();
    expect(state.generations).toBe(1);
    expect(await page.evaluate(key => JSON.parse(sessionStorage.getItem(key)!).payment, draftKey)).toMatchObject({
      provider: "tribute", transactionId: null,
    });

    // Reopening after spending the balance cannot convert this unresolved
    // checkout into another payment, even though generation succeeded.
    state.funded = false;
    await page.reload();
    await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: /Пополнить здесь|Открыть эту оплату/ })).toHaveCount(0);
    await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
    await expect(dialog.getByText(/Статус этой оплаты пока нельзя подтвердить/)).toBeVisible();
    expect(state.topups).toBe(1);
    expect(state.generations).toBe(1);
  });
}
