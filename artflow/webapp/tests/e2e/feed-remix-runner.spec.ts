import { expect, test, type Page } from "@playwright/test";

const user = {
  id: 1,
  tg_id: 123,
  username: "tester",
  full_name: "Test User",
  credits: 100,
  referral_balance: 0,
  language: "ru",
};

const imageModels = [
  {
    key: "nano-banana-2",
    display_name: "🍌 Nano Banana 2",
    credits: 1.5,
    modes: ["text", "image"],
    aspect_ratios: ["1:1", "4:5", "9:16"],
    quality_options: [{ value: "2K", label: "2K" }],
    counts: [1, 2],
    max_refs: 4,
    has_quality: true,
  },
];

const videoModels = [
  {
    key: "veo-3.1-fast",
    display_name: "Veo 3.1 Fast",
    credits: 20,
    modes: ["text", "image", "video"],
    aspect_ratios: ["16:9", "9:16"],
    durations: [5, 10],
    resolutions: ["720p", "1080p"],
    max_refs: 1,
    supports_video_input: true,
  },
];

const feedItems = [
  {
    id: 201,
    model: "nano-banana-2",
    gen_type: "image",
    prompt: "",
    prompt_hidden: true,
    result_url: "https://example.test/source.png",
    result_urls: ["https://example.test/source.png"],
    preview_url: "https://example.test/source.png",
    preview_urls: ["https://example.test/source.png"],
    likes_count: 3,
    shares_count: 1,
    remixes: 2,
    aspect_ratio: "1:1",
    author: "Artist QA",
    is_mine: false,
  },
];

async function mockMiniAppApi(page: Page) {
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "test",
        initDataUnsafe: { user: { id: 123, first_name: "Test" } },
        colorScheme: "dark",
        ready: () => undefined,
        expand: () => undefined,
        HapticFeedback: { impactOccurred: () => undefined, notificationOccurred: () => undefined },
        openLink: () => undefined,
        openInvoice: () => undefined,
      },
    } as typeof window.Telegram;
  });

  await page.route("https://example.test/source.png", (route) => route.fulfill({
    contentType: "image/png",
    body: Buffer.from([0x89, 0x50, 0x4e, 0x47]),
  }));
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: imageModels }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: videoModels }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: feedItems }));
  await page.route("**/api/v1/trends?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/plans", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/payment-methods", (route) => route.fulfill({ json: ["tbank"] }));
  await page.route("**/api/v1/feed/201/remix/quote", (route) => route.fulfill({ json: {
    cost_credits: 1.5, balance_credits: 100, can_run: true, deficit_credits: 0, recommended_plan: null,
  } }));
  await page.route("**/api/web/upload-media", (route) => route.fulfill({
    json: { data: { url: "https://example.test/uploaded-ref.png", kind: "image", content_type: "image/jpeg", size: 4 } },
  }));
}

test("feed work repeat asks for settings and preserves source media payload", async ({ page }) => {
  await mockMiniAppApi(page);
  let remixPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/feed/201/remix", async (route) => {
    remixPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 202,
      json: {
        id: 9201,
        task_id: "web:feed-remix-test",
        model: "nano-banana-2",
        gen_type: "image",
        prompt: "",
        prompt_hidden: true,
        status: "pending",
        result_url: null,
        result_urls: [],
        credits_spent: 1.5,
        created_at: new Date().toISOString(),
      },
    });
  });

  await page.goto("/?tgWebAppData=test");
  await expect(page.getByText("Artist QA")).toBeVisible();
  await page.getByRole("button", { name: "Повторить" }).first().click();

  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Исходная работа будет использована как основной референс.")).toBeVisible();
  await expect(dialog.getByLabel("Модель")).toBeVisible();

  await dialog.locator("input[type=file]").setInputFiles({
    name: "ref.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  await dialog.getByLabel("Что изменить в образе").fill("Замени одежду на красное платье до генерации");
  await expect(dialog.getByText("Стоимость: 1.5 💋").first()).toBeVisible();
  await dialog.getByRole("button", { name: /Запустить повтор/ }).click();

  await expect(page.getByRole("dialog", { name: /Задача #9201/ })).toBeVisible();
  expect(remixPayload).toMatchObject({
    model: "nano-banana-2",
    mode: "image",
    source_image_url: "https://example.test/source.png",
    image_url: "https://example.test/uploaded-ref.png",
    reference_urls: ["https://example.test/uploaded-ref.png"],
    change_request: "Замени одежду на красное платье до генерации",
  });
});

test("shared link opens exact repeat settings before any paid generation", async ({ page }) => {
  await mockMiniAppApi(page);
  let paidRequests = 0;
  await page.route("**/api/v1/feed/201/remix", async (route) => {
    paidRequests++;
    await route.fulfill({ status: 502, json: { detail: "Must not run before confirmation" } });
  });
  await page.goto("/?tgWebAppData=test&feed=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Artist QA")).toBeVisible();
  await expect(dialog.getByLabel("Что изменить в образе")).toBeVisible();
  expect(paidRequests).toBe(0);
});

test("insufficient balance can top up inline while preserving photo and settings", async ({ page }) => {
  await mockMiniAppApi(page);
  let paidRequests = 0;
  let topups = 0;
  let funded = false;
  await page.route("**/api/v1/feed/201/remix/quote", (route) => route.fulfill({ json: {
    cost_credits: 5, balance_credits: funded ? 12 : 0,
    can_run: funded, deficit_credits: funded ? 0 : 5,
    recommended_plan: funded ? null : { key: "starter", label: "Старт", credits: 10, price_rub: 100,
      payment_options: [{ provider: "tbank", amount: 100, currency: "RUB" }],
    },
  } }));
  await page.route("**/api/v1/topup/tbank", (route) => {
    topups++;
    // The webhook is deliberately delayed until after WebView reload.
    return route.fulfill({ json: { pay_url: "https://pay.example.test/checkout" } });
  });
  await page.route("**/api/v1/feed/201/remix", (route) => {
    paidRequests++;
    return route.fulfill({ status: 202, json: {
      id: 9202, model: "nano-banana-2", gen_type: "image",
      prompt: "", prompt_hidden: true, status: "pending", result_url: null, result_urls: [],
      credits_spent: 5, created_at: new Date().toISOString(),
    } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await dialog.getByLabel("Что изменить в образе").fill("Сделать белый костюм");
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
  expect(paidRequests).toBe(0);
  await dialog.getByRole("button", { name: "Пополнить здесь · 100 ₽" }).click();
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  await expect(dialog.getByLabel("Что изменить в образе")).toHaveValue("Сделать белый костюм");
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(topups).toBe(1);
  expect(paidRequests).toBe(0);

  // External bank checkout may reload Telegram's WebView while its webhook is
  // delayed. Never show a second payment button or lose uploaded media.
  await page.reload();
  const restored = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(restored).toBeVisible();
  await expect(restored.getByText("Реф #1")).toBeVisible();
  await expect(restored.getByLabel("Что изменить в образе")).toHaveValue("Сделать белый костюм");
  await expect(restored.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  funded = true; // provider webhook has now reconciled the balance
  await expect(restored.getByText("Можно запускать")).toBeVisible({ timeout: 12000 });
  expect(topups).toBe(1);
  expect(paidRequests).toBe(0);
  await restored.getByRole("button", { name: /Запустить повтор/ }).click();
  expect(paidRequests).toBe(1);
});

async function pendingCheckout(page: Page, paymentOptions = [{ provider: "tbank", amount: 100 as number | null, currency: "RUB" }]) {
  await mockMiniAppApi(page);
  const state = { topups: 0, funded: false };
  await page.route("**/api/v1/feed/201/remix/quote", route => route.fulfill({ json: {
    cost_credits: 5, balance_credits: state.funded ? 10 : 0, can_run: state.funded,
    deficit_credits: state.funded ? 0 : 5,
    recommended_plan: state.funded ? null : { key: "starter", label: "Старт", credits: 10, price_rub: 100,
      payment_options: paymentOptions,
    },
  } }));
  await page.route("**/api/v1/topup/tbank", route => {
    state.topups++;
    return route.fulfill({ json: { pay_url: "https://pay.example.test/original", transaction_id: 701, credits: 10 } });
  });
  await page.route("**/api/web/billing/transactions?**", route => route.fulfill({ json: { data: {
    transactions: [{ id: 701, provider: "tbank", status: state.funded ? "paid" : "pending", credits: 10 }],
  } } }));
  return state;
}

test("pending invoice is durable at the exact external handoff before any React effect", async ({ page }) => {
  const state = await pendingCheckout(page);
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByLabel("Что изменить в образе").fill("Сохранить мой образ");
  await page.evaluate(() => {
    window.Telegram!.WebApp!.openLink = () => {
      const snapshot = Object.fromEntries(Object.keys(sessionStorage).map(key => [key, sessionStorage.getItem(key)]));
      sessionStorage.setItem("test:external-handoff", JSON.stringify(snapshot));
      window.location.reload();
    };
  });
  const reloadedDocument = page.waitForEvent("domcontentloaded");
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  // The snapshot is captured synchronously inside openLink; read it only after
  // the intentionally replaced document has a usable JavaScript context.
  await reloadedDocument;
  const snapshot = await page.evaluate(() => JSON.parse(sessionStorage.getItem("test:external-handoff") || "{}"));
  const saved = JSON.parse(String(snapshot["apix:feed-repeat-draft:v2:1:201"]));
  expect(saved.payment).toMatchObject({ transactionId: 701, checkoutUrl: "https://pay.example.test/original" });
  expect(saved.changeRequest).toBe("Сохранить мой образ");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Что изменить в образе")).toHaveValue("Сохранить мой образ");
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(state.topups).toBe(1);
});

test("delayed webhook never unlocks a second invoice after poll timeout and reload", async ({ page }) => {
  const state = await pendingCheckout(page);
  await page.clock.install();
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toBeVisible();
  await page.clock.runFor(130_000);
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(state.topups).toBe(1);
  await page.reload();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(state.topups).toBe(1);
});

test("close and reopen preserves the same invoice while unrelated balance does not settle it", async ({ page }) => {
  const state = await pendingCheckout(page);
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.getByRole("button", { name: "Повторить", exact: true }).first().click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  const opened: string[] = [];
  await page.exposeFunction("recordCheckoutURL", (url: string) => { opened.push(url); });
  await page.evaluate(() => { window.Telegram!.WebApp!.openLink = (url: string) => { void (window as unknown as { recordCheckoutURL: (url: string) => Promise<void> }).recordCheckoutURL(url); }; });
  await dialog.getByRole("button", { name: "Открыть эту оплату", exact: true }).click();
  await expect.poll(() => opened.length).toBe(1);
  expect(opened[0]).toBe("https://pay.example.test/original");
  expect(state.topups).toBe(1);
  // Another balance update is deliberately not the pending invoice's receipt.
  await page.route("**/api/v1/feed/201/remix/quote", route => route.fulfill({ json: {
    cost_credits: 5, balance_credits: 20, can_run: true, deficit_credits: 0, recommended_plan: null,
  } }));
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toBeVisible();
  expect(state.topups).toBe(1);
});

test("lost invoice creation response remains guarded across reload", async ({ page }) => {
  const state = await pendingCheckout(page);
  await page.route("**/api/v1/topup/tbank", route => { state.topups++; return route.abort("failed"); });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  await page.reload();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(state.topups).toBe(1);
});

test("exact paid transaction unlocks checkout state but never launches generation automatically", async ({ page }) => {
  const state = await pendingCheckout(page);
  let generations = 0;
  await page.route("**/api/v1/feed/201/remix", route => { generations++; return route.fulfill({ status: 502, json: { detail: "Not expected" } }); });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  state.funded = true;
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  expect(generations).toBe(0);
  expect(state.topups).toBe(1);
});

test("delayed invoice response persists the latest edits before external navigation", async ({ page }) => {
  const state = await pendingCheckout(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/topup/tbank", async route => {
    state.topups++;
    await gate;
    await route.fulfill({ json: { pay_url: "https://pay.example.test/original", transaction_id: 701 } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await page.evaluate(() => {
    window.Telegram!.WebApp!.openLink = () => {
      sessionStorage.setItem("test:latest-handoff", sessionStorage.getItem("apix:feed-repeat-draft:v2:1:201") || "null");
    };
  });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await dialog.getByLabel("Что изменить в образе").fill("Последнее изменение");
  release();
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem("test:latest-handoff") || "null")?.changeRequest)).toBe("Последнее изменение");
  expect(state.topups).toBe(1);
});

test("reopening the same source during invoice creation adopts its late checkout identity", async ({ page }) => {
  const state = await pendingCheckout(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/topup/tbank", async route => {
    state.topups++;
    await gate;
    await route.fulfill({ json: { pay_url: "https://pay.example.test/original", transaction_id: 701 } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await page.evaluate(item => window.dispatchEvent(new CustomEvent("apix:open-feed-remix-runner", { detail: { item } })), feedItems[0]);
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  release();
  await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toBeVisible();
  await page.reload();
  await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toBeVisible();
  expect(state.topups).toBe(1);
});

test("unresolved Tribute product checkout is not offered as the same invoice", async ({ page }) => {
  await pendingCheckout(page, [{ provider: "tribute", amount: 2, currency: "USD" }]);
  let topups = 0;
  await page.route("**/api/v1/payment-methods", route => route.fulfill({ json: ["tribute"] }));
  await page.route("**/api/v1/topup/tribute", route => {
    topups++;
    return route.fulfill({ json: { pay_url: "https://pay.example.test/reusable-product", provider: "tribute", amount_usd: 2 } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toHaveCount(0);
  await page.reload();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toHaveCount(0);
  expect(topups).toBe(1);
});

test("repeat checkout ignores global providers that cannot sell the recommended plan", async ({ page }) => {
  const state = await pendingCheckout(page, [{ provider: "tribute", amount: 2, currency: "USD" }]);
  await page.route("**/api/v1/payment-methods", route => route.fulfill({ json: ["lava", "tribute"] }));
  let tributeTopups = 0;
  let lavaTopups = 0;
  await page.route("**/api/v1/topup/lava", route => {
    lavaTopups++;
    return route.fulfill({ status: 404, json: { detail: "Plan has no Lava offer" } });
  });
  await page.route("**/api/v1/topup/tribute", route => {
    tributeTopups++;
    expect(route.request().postDataJSON()).toEqual({ plan_key: "starter" });
    return route.fulfill({ json: { pay_url: "https://pay.example.test/product", amount_usd: 2 } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Пополнить здесь · 2 USD", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(tributeTopups).toBe(1);
  expect(lavaTopups).toBe(0);
  expect(state.topups).toBe(0);
});

test("repeat checkout displays CryptoBot charge in USDT", async ({ page }) => {
  await pendingCheckout(page, [{ provider: "crypto", amount: 1.11, currency: "USDT" }]);
  await page.route("**/api/v1/payment-methods", route => route.fulfill({ json: ["crypto"] }));
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Пополнить здесь · 1.11 USDT", exact: true })).toBeVisible();
  await expect(dialog.getByText("CryptoBot", { exact: true })).toBeVisible();
});

test("repeat checkout provider choice changes both charge disclosure and checkout destination", async ({ page }) => {
  const state = await pendingCheckout(page, [
    { provider: "tbank", amount: 100, currency: "RUB" },
    { provider: "crypto", amount: 1.11, currency: "USDT" },
  ]);
  let cryptoTopups = 0;
  await page.route("**/api/v1/topup/crypto", route => {
    cryptoTopups++;
    return route.fulfill({ json: { pay_url: "https://pay.example.test/crypto", transaction_id: 702, amount_usdt: 1.11 } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Пополнить здесь · 100 ₽", exact: true })).toBeVisible();
  await dialog.getByLabel("Способ оплаты").selectOption("crypto");
  await dialog.getByRole("button", { name: "Пополнить здесь · 1.11 USDT", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(cryptoTopups).toBe(1);
  expect(state.topups).toBe(0);
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:feed-repeat-draft:v2:1:201")!).payment.provider)).toBe("crypto");
});

test("repeat checkout never invents the amount of a mapped Lava offer", async ({ page }) => {
  await pendingCheckout(page, [{ provider: "lava", amount: null, currency: "RUB" }]);
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Пополнить здесь · сумма в ₽ на странице оплаты", exact: true })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Пополнить здесь · 100 ₽", exact: true })).toHaveCount(0);
});

test("repeat checkout fails closed when a plan has no eligible payment options", async ({ page }) => {
  const state = await pendingCheckout(page, []);
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByText("Для этого пакета пока нет доступного способа оплаты.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Пополнить здесь/ })).toHaveCount(0);
  expect(state.topups).toBe(0);
});

test("paid receipt cannot expose a stale insufficient-balance top-up while quote refresh is delayed", async ({ page }) => {
  const state = await pendingCheckout(page);
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/feed/201/remix/quote", async route => {
    await gate;
    await route.fulfill({ json: { cost_credits: 5, balance_credits: 10, can_run: true, deficit_credits: 0, recommended_plan: null } });
  });
  state.funded = true;
  await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Пополнить здесь/ })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
  release();
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  expect(state.topups).toBe(1);
});

test("Seedance source-video edit discloses measured billing without starting generation", async ({ page }) => {
  await mockMiniAppApi(page);
  let paidRequests = 0;
  await page.route("https://example.test/source.mp4", (route) => route.fulfill({ contentType: "video/mp4", body: Buffer.alloc(32) }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: [{
    key: "bytedance/seedance-2-5", display_name: "Seedance 2.5", credits: 4,
    modes: ["text", "multimodal"], supports_video_input: true, max_refs: 30,
    aspect_ratios: ["adaptive", "16:9", "9:16"], durations: [5, 10, 30], resolutions: ["720p"],
  }] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [{
    ...feedItems[0], model: "bytedance/seedance-2-5", gen_type: "video",
    result_url: "https://example.test/source.mp4", result_urls: ["https://example.test/source.mp4"],
  }] }));
  await page.route("**/api/v1/feed/201/remix/quote", (route) => route.fulfill({ json: {
    cost_credits: 28, balance_credits: 100, can_run: true, deficit_credits: 0,
    source_video_edit: true, effective_duration_seconds: 7,
  } }));
  await page.route("**/api/v1/feed/201/remix", (route) => {
    paidRequests++;
    return route.fulfill({ status: 502, json: { detail: "Must not run before confirmation" } });
  });
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("button", { name: "Повторить" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByLabel("Что изменить в образе").fill("Сделай одежду синей");
  await expect(dialog.getByText("Редактирование исходного ролика: длительность и кадр берутся из источника. Для оплаты: 7 сек.")).toBeVisible();
  await expect(dialog.getByText("Стоимость: 28 💋")).toBeVisible();
  expect(paidRequests).toBe(0);
});
