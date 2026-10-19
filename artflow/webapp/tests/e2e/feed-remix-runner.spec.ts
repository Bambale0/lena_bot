import { expect, test, type Locator, type Page } from "@playwright/test";

// Server-issued opaque output bindings; API tests verify real digest membership.
const boundPreview = (index: number, output = index) =>
  `/api/v1/feed/201/preview.webp?index=${index}&output_id=${["a", "b", "c"][output].repeat(64)}`;

async function restoreLegacySceneOnNextDocument(page: Page, missing: boolean) {
  // Seed the old-client draft before the new document starts. Mutating storage
  // in the live runner races its invoice response and correct autosave behavior.
  await page.addInitScript((missing) => {
    const key = "apix:feed-repeat-draft:v2:1:201";
    const old = JSON.parse(window.sessionStorage.getItem(key)!);
    old.sourceMediaUrl = missing ? "" : old.sourceMediaUrl.split("&output_id=")[0];
    window.sessionStorage.setItem(key, JSON.stringify(old));
  }, missing);
}

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

async function mockMiniAppApi(page: Page, withTelegram = true, nativeBack = false, imageRecipe = false) {
  if (withTelegram) await page.addInitScript((nativeBack) => {
    const backHandlers = new Set<() => void>();
    if (nativeBack) window.addEventListener("apix:test-back", () => backHandlers.forEach(handler => handler()));
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
        BackButton: nativeBack ? {
          show: () => undefined, hide: () => undefined,
          onClick: (handler: () => void) => { backHandlers.add(handler); },
          offClick: (handler: () => void) => { backHandlers.delete(handler); },
        } : undefined,
      },
    } as typeof window.Telegram;
  }, nativeBack);

  await page.route("https://example.test/source.png", (route) => route.fulfill({
    contentType: "image/png",
    body: Buffer.from([0x89, 0x50, 0x4e, 0x47]),
  }));
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: imageModels }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: videoModels }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: feedItems.map((item) => ({
    ...item, is_mine: !imageRecipe, source_image_recipe_available: imageRecipe,
  })) }));
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
  await mockMiniAppApi(page, true, false, true);
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
  await expect(dialog.getByText("Применим промпт автора к твоим фото. Готовую работу автора модели не отправляем.")).toBeVisible();
  await expect(dialog.locator("select").first()).toBeVisible();

  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
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
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
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
  await expect(dialog.getByRole("contentinfo").getByText("Стоимость: 28 💋", { exact: true })).toBeVisible();
  expect(paidRequests).toBe(0);
});

test("image recipe uses all reference slots for reader photos", async ({ page }) => {
  await mockMiniAppApi(page, true, false, true);
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [
    ...imageModels, { ...imageModels[0], key: "qwen/image-edit", display_name: "Single reference", max_refs: 1 },
  ] }));
  let uploads = 0;
  let paidRequests = 0;
  let quotes = 0;
  await page.route("**/api/v1/feed/201/remix/quote", route => {
    quotes++;
    return route.fulfill({ json: { cost_credits: 2, balance_credits: 100, can_run: true } });
  });
  await page.route("**/api/web/upload-media", route => {
    uploads++;
    return route.fulfill({ json: { data: { url: `https://example.test/ref-${uploads}.png` } } });
  });
  await page.route("**/api/v1/feed/201/remix", route => {
    paidRequests++;
    return route.fulfill({ status: 500, json: { detail: "Unexpected launch" } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByText("Повтор по исходному рецепту автора: лицо возьмём с твоих фото (до 4). Готовое изображение автора не отправляется модели.")).toBeVisible();
  expect(quotes).toBe(0);
  const photo = (index: number) => ({ name: `ref-${index}.jpg`, mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, index]) });
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles([1, 2, 3, 4, 5].map(photo));
  await expect(dialog.getByRole("contentinfo").getByText("Повтор по исходному рецепту автора: лицо возьмём с твоих фото (до 4). Готовое изображение автора не отправляется модели.")).toBeVisible();
  expect(uploads).toBe(0);
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles([1, 2, 3, 4].map(photo));
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(4);
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeDisabled();
  await expect(dialog.locator("select").first().locator('option[value="qwen/image-edit"]')).toHaveJSProperty("disabled", true);
  expect(uploads).toBe(4);
  await expect.poll(() => quotes).toBeGreaterThan(0);
  expect(paidRequests).toBe(0);
});

test("foreign photo without a public recipe cannot reach quote or checkout", async ({ page }) => {
  await mockMiniAppApi(page);
  await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [{
    ...feedItems[0], is_mine: false, source_image_recipe_available: false,
  }] }));
  let quotes = 0;
  await page.route("**/api/v1/feed/201/remix/quote", route => {
    quotes++;
    return route.fulfill({ status: 422, json: { detail: "Recipe unavailable" } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByText("Для этой публикации повтор по промпту автора недоступен.")).toBeVisible();
  await dialog.locator("input[type=file]").setInputFiles({
    name: "ref.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  expect(quotes).toBe(0);
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
});

test("one-reference image models retain text edits without offering impossible photo uploads", async ({ page }) => {
  await mockMiniAppApi(page);
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [{ ...imageModels[0], max_refs: 1 }] }));
  let latestQuote: Record<string, unknown> | null = null;
  await page.route("**/api/v1/feed/201/remix/quote", route => {
    latestQuote = route.request().postDataJSON();
    return route.fulfill({ json: { cost_credits: 2, balance_credits: 100, can_run: true, deficit_credits: 0 } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeDisabled();
  await dialog.getByLabel("Что изменить в образе").fill("Сделай фон синим");
  await expect(dialog.getByRole("button", { name: /Запустить повтор · 2/ })).toBeEnabled();
  expect(latestQuote?.["reference_urls"]).toEqual([]);
  expect(latestQuote?.["source_image_url"]).toBe("https://example.test/source.png");
  expect(latestQuote?.["change_request"]).toBe("Сделай фон синим");
});

test("restored photos beyond current source-reserved capacity remain visible and cannot launch", async ({ page }) => {
  await mockMiniAppApi(page);
  let maxRefs = 3;
  let uploads = 0;
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [{ ...imageModels[0], max_refs: maxRefs }] }));
  await page.route("**/api/web/upload-media", route => {
    uploads++;
    return route.fulfill({ json: { data: { url: `https://example.test/ref-${uploads}.png` } } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles([1, 2].map(index => ({ name: `ref-${index}.jpg`, mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, index]) })));
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(2);
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  maxRefs = 2;
  await page.reload();
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(2);
  await expect(dialog.getByRole("alert")).toContainText("Сохранённые фото не удалены");
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
  await dialog.getByLabel("Удалить референс").last().click();
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(1);
});

test("a valid six-photo repeat draft restores every photo without silent truncation", async ({ page }) => {
  await mockMiniAppApi(page);
  let uploads = 0;
  await page.route("**/api/v1/models/image", route => route.fulfill({ json: [{ ...imageModels[0], max_refs: 7 }] }));
  await page.route("**/api/web/upload-media", route => {
    uploads++;
    return route.fulfill({ json: { data: { url: `https://example.test/ref-${uploads}.png` } } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles([1, 2, 3, 4, 5, 6].map(index => ({ name: `ref-${index}.jpg`, mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, index]) })));
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(6);
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  await page.reload();
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(6);
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  expect(uploads).toBe(6);
});

test("Gemini source-video quota reserves two shared slots before photo upload", async ({ page }) => {
  await mockMiniAppApi(page);
  await page.route("https://example.test/source.mp4", route => route.fulfill({ contentType: "video/mp4", body: Buffer.alloc(32) }));
  await page.route("**/api/v1/models/video", route => route.fulfill({ json: [{
    key: "gemini-omni-video", display_name: "Gemini Omni", credits: 38, modes: ["text", "image", "video"],
    max_refs: 7, max_refs_with_video: 5, supports_video_input: true,
    aspect_ratios: ["16:9"], durations: [4], resolutions: ["1080p"],
  }] }));
  await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [{
    ...feedItems[0], model: "gemini-omni-video", gen_type: "video",
    result_url: "https://example.test/source.mp4", result_urls: ["https://example.test/source.mp4"],
  }] }));
  let uploads = 0;
  await page.route("**/api/web/upload-media", route => {
    uploads++;
    return route.fulfill({ json: { data: { url: `https://example.test/ref-${uploads}.png` } } });
  });
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByText("Для этой модели можно добавить своих фото: 5. Нужна поддержка исходного видео.")).toBeVisible();
  const photo = (index: number) => ({ name: `ref-${index}.jpg`, mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, index]) });
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles([1, 2, 3, 4, 5, 6].map(photo));
  await expect(dialog.getByRole("contentinfo")).toContainText("можно добавить своих фото: 5");
  expect(uploads).toBe(0);
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
  await dialog.locator("input[type=file]").setInputFiles([1, 2, 3, 4, 5].map(photo));
  await expect(dialog.getByLabel("Удалить референс")).toHaveCount(5);
  await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeDisabled();
  expect(uploads).toBe(5);
});


test("payment notification leaves underlying controls clickable while visible", async ({ page }) => {
  const state = await pendingCheckout(page);
  await page.goto("/?tgWebAppData=test&remix=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  const notice = page.locator("[data-sonner-toast]").filter({ hasText: "Оплата открыта" });
  await expect(notice).toBeVisible();
  // Informational surfaces must not capture input. Dismiss/action controls remain interactive.
  await expect(notice).toHaveCSS("pointer-events", "none");
  await expect(notice.locator("button")).toHaveCSS("pointer-events", "auto");
  await dialog.getByRole("button", { name: "Закрыть", exact: true }).click({ timeout: 2000 });
  await expect(dialog).toHaveCount(0);
  expect(state.topups).toBe(1);
  await page.getByRole("button", { name: "Повторить", exact: true }).first().click();
  await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
  expect(state.topups).toBe(1);
});

test("creator photo-to-video replay never sends rendered MP4 and keeps creator recipe", async ({ page }) => {
  await mockMiniAppApi(page);
  const model = {
    key: "veo-3.1-fast", display_name: "Veo 3.1 Fast",
    credits: 20, modes: ["text", "image", "video"],
    aspect_ratios: ["16:9", "9:16"], durations: [5, 10],
    resolutions: ["720p", "1080p"],
    max_refs: 1, supports_video_input: true,
  };
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [{
    id: 57213, model: model.key, gen_type: "video",
    prompt: "", prompt_hidden: true,
    source_has_video_reference: false,
    original_duration: 10, original_aspect_ratio: "9:16", original_resolution: "720p",
    result_url: "https://example.test/rendered.mp4",
    result_urls: ["https://example.test/rendered.mp4"],
    preview_url: "https://example.test/rendered.mp4",
    author: "Artist Replay", is_mine: false,
    likes_count: 0, shares_count: 0, remixes: 0, aspect_ratio: "9:16",
  }] }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: [model] }));
  await page.route("**/api/v1/feed/57213/remix/quote", (route) => route.fulfill({ json: {
    cost_credits: 20, balance_credits: 100,
    can_run: true, deficit_credits: 0, recommended_plan: null,
  } }));
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/v1/feed/57213/remix", (route) => {
    sent = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({ status: 202, json: {
      id: 9205, model: model.key, gen_type: "video",
      prompt: "", prompt_hidden: true,
      status: "pending", result_url: null, result_urls: [],
      credits_spent: 20, created_at: new Date().toISOString(),
    } });
  });

  await page.goto("/?tgWebAppData=test&feed=57213");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Применим исходный промпт автора к твоему фото. Готовое видео автора не передаётся.")).toBeVisible();
  await expect(dialog.getByLabel("Что изменить в образе")).toHaveCount(0);
  await expect(dialog.getByLabel("Модель")).toBeDisabled();
  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg", mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect(dialog.getByText("Реф #1")).toBeVisible();
  await expect(dialog.getByText("Стоимость: 20 💋").first()).toBeVisible();
  await dialog.getByRole("button", { name: /Запустить повтор/ }).click();
  await expect(page.getByRole("dialog", { name: /Задача #9205/ })).toBeVisible();
  expect(sent).toMatchObject({
    model: model.key, change_request: "",
    image_url: "https://example.test/uploaded-ref.png",
    reference_urls: ["https://example.test/uploaded-ref.png"],
    video_url: null, duration: 10, aspect_ratio: "9:16", resolution: "720p",
  });
});

test("deep-linked older creator video retains photo-only recipe provenance", async ({ page }) => {
  await mockMiniAppApi(page);
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed/57213", (route) => route.fulfill({ json: {
    id: 57213, model: "veo-3.1-fast", gen_type: "video",
    prompt: "", prompt_hidden: true, source_has_video_reference: false,
    original_duration: 10, original_aspect_ratio: "9:16", original_resolution: "720p",
    result_url: "https://example.test/rendered.mp4", result_urls: ["https://example.test/rendered.mp4"],
    author: "Artist Old Link", likes_count: 0, shares_count: 0, remixes: 0,
  } }));
  await page.goto("/?tgWebAppData=test&feed=57213");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Применим исходный промпт автора к твоему фото. Готовое видео автора не передаётся.")).toBeVisible();
  await expect(dialog.getByLabel("Модель")).toBeDisabled();
});

test("text-only source video can replay author prompt without photos", async ({ page }) => {
  await mockMiniAppApi(page);
  const model = {
    key: "kling-2.6/text-to-video", display_name: "Kling 2.6 Text",
    modes: ["text"], credits: 12, durations: [5, 10],
    aspect_ratios: ["16:9", "9:16"], resolutions: ["720p", "1080p"],
  };
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [{
    id: 57218, model: model.key, gen_type: "video", prompt: "", prompt_hidden: true,
    source_has_video_reference: false, original_duration: 10,
    original_aspect_ratio: "9:16", original_resolution: "720p",
    result_url: "https://example.test/text-source.mp4",
    author: "Text Artist", likes_count: 0, shares_count: 0, remixes: 0,
  }] }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: [model] }));
  await page.route("**/api/v1/feed/57218/remix/quote", (route) => route.fulfill({ json: {
    cost_credits: 12, balance_credits: 100, can_run: true, deficit_credits: 0,
  } }));
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/v1/feed/57218/remix", (route) => {
    sent = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({ status: 202, json: {
      id: 9206, model: model.key, gen_type: "video", status: "pending", prompt: "",
      prompt_hidden: true, result_url: null, result_urls: [], credits_spent: 12,
      created_at: new Date().toISOString(),
    } });
  });
  await page.goto("/?tgWebAppData=test&feed=57218");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByText("Повторим исходный текстовый запрос автора. Эта модель не поддерживает фото-референсы.")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Добавить" })).toBeDisabled();
  await expect(dialog.getByText("Стоимость: 12 💋").first()).toBeVisible();
  await dialog.getByRole("button", { name: /Запустить повтор/ }).click();
  await expect(page.getByRole("dialog", { name: /Задача #9206/ })).toBeVisible();
  expect(sent).toMatchObject({
    model: model.key, mode: "text", change_request: "",
    image_url: null, reference_urls: [], video_url: null,
    duration: 10, aspect_ratio: "9:16", resolution: "720p",
  });
});


async function expectCenterIsReachable(target: Locator, message: string) {
  await expect(target).toBeVisible();
  await expect.poll(() => target.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const hit = element.ownerDocument.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return Boolean(hit && element.contains(hit));
  }), { message }).toBe(true);
}

async function expectViewerRepeatIsReachable(page: Page) {
  await expectCenterIsReachable(
    page.locator(".apix-media-viewer").getByRole("button", { name: "Повторить эту работу" }),
    "Gallery repeat must receive clicks above the bottom navigation",
  );
}

test("feed cover decoration leaves media reachable and its Repeat action stays clickable", async ({ page }) => {
  await mockMiniAppApi(page);
  let likes = 0;
  await page.route("**/api/v1/feed/201/like", route => {
    likes++;
    return route.fulfill({ json: { likes_count: 4 } });
  });
  await page.goto("/?tgWebAppData=test");
  const card = page.locator(".apix-feed-card").first();
  const cover = card.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first();
  await expectCenterIsReachable(cover, "Decorative author/model footer must not swallow the visible cover tap");
  await cover.click();
  await expect(page.locator(".apix-media-viewer")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".apix-media-viewer")).toHaveCount(0);
  const author = card.getByText("Artist QA", { exact: true });
  await expect(author).toBeVisible();
  const point = await author.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
    const opener = element.closest(".apix-feed-card")!.querySelector('button[aria-label="Открыть внутри приложения"]')!;
    return { x, y, opensMedia: opener.contains(element.ownerDocument.elementFromPoint(x, y)) };
  });
  expect(point.opensMedia, "Tapping decorative author text must target the media opener").toBe(true);
  if (test.info().project.use.hasTouch) await page.touchscreen.tap(point.x, point.y);
  else await page.mouse.click(point.x, point.y);
  await expect(page.locator(".apix-media-viewer")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".apix-media-viewer")).toHaveCount(0);
  const like = card.getByRole("button", { name: "Лайк", exact: true });
  await expectCenterIsReachable(like, "Like must remain independently reachable");
  await like.click();
  await expect.poll(() => likes).toBe(1);
  await expect(page.locator(".apix-media-viewer")).toHaveCount(0);
  const maximize = card.getByRole("button", { name: "Открыть внутри приложения", exact: true }).nth(1);
  await expectCenterIsReachable(maximize, "The explicit gallery control must remain reachable");
  await maximize.click();
  await expect(page.locator(".apix-media-viewer")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".apix-media-viewer")).toHaveCount(0);
  const repeat = card.getByRole("button", { name: "Повторить", exact: true });
  await expectCenterIsReachable(repeat, "Repeat must receive clicks inside the pointer-transparent footer");
  await repeat.click();
  await expect(page.getByRole("dialog", { name: "Повторить работу" })).toBeVisible();
  await expect(page.locator(".apix-media-viewer")).toHaveCount(0);
});

for (const surface of ["telegram", "browser"] as const) {
  test(`${surface} gallery repeat keeps selected second result through quote and submit`, async ({ page }) => {
    await mockMiniAppApi(page, surface === "telegram");
    const previews = [0, 1].map(index => boundPreview(index));
    await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [{
      ...feedItems[0], source_image_recipe_available: true,
      result_url: "", result_urls: [], preview_url: previews[0], preview_urls: previews,
    }] }));
    let latestQuote: Record<string, unknown> | null = null;
    let submitted: Record<string, unknown> | null = null;
    await page.route("**/api/v1/feed/201/remix/quote", route => {
      latestQuote = route.request().postDataJSON();
      return route.fulfill({ json: { cost_credits: 1.5, balance_credits: 100, can_run: true } });
    });
    await page.route("**/api/v1/feed/201/remix", route => {
      submitted = route.request().postDataJSON();
      return route.fulfill({ status: 202, json: {
        id: 9201, task_id: "web:selected-result", model: "nano-banana-2", gen_type: "image",
        status: "pending", result_urls: [], credits_spent: 1.5, created_at: new Date().toISOString(),
      } });
    });
    await page.goto("/?tgWebAppData=test");
    await expect(page.getByText("Artist QA")).toBeVisible();
    await page.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first().click();
    const viewer = page.locator(".apix-media-viewer");
    await expect(viewer).toBeVisible();
    await viewer.getByRole("button", { name: "Следующее фото" }).click();
    await expect(viewer.locator("img")).toHaveAttribute("src", new RegExp("index=1&output_id=b{64}$"));
    await expectViewerRepeatIsReachable(page);
    await viewer.getByRole("button", { name: "Повторить эту работу" }).click();
    const dialog = page.getByRole("dialog", { name: "Повторить работу" });
    await expect(dialog).toBeVisible();
    const selectedSource = new URL(previews[1], page.url()).href;
    await expect(dialog.locator("input[type=file]")).toBeEnabled();
    await dialog.locator("input[type=file]").setInputFiles({
      name: "ref.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect(dialog.getByText("Реф #1")).toBeVisible();
    await expect.poll(() => latestQuote?.source_image_url).toBe(selectedSource);
    await expect.poll(() => latestQuote?.image_url).toBe("https://example.test/uploaded-ref.png");
    await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
    await dialog.getByRole("button", { name: /Запустить повтор/ }).click();
    await expect.poll(() => submitted).not.toBeNull();
    expect(submitted).toEqual(latestQuote);
    expect(submitted).toMatchObject({ source_image_url: selectedSource,
      image_url: "https://example.test/uploaded-ref.png", reference_urls: ["https://example.test/uploaded-ref.png"] });
  });
}

test("older image deep link quotes the same owned preview route as list cards", async ({ page }) => {
  await mockMiniAppApi(page);
  await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [] }));
  await page.route("**/api/web/feed/201", route => route.fulfill({ json: { data: {
    ...feedItems[0], source_image_recipe_available: true,
    preview_url: "https://example.test/source_preview_384_deadbeef.webp",
    preview_urls: ["https://example.test/source_preview_384_deadbeef.webp"],
  } } }));
  await page.route("**/api/v1/feed/201", route => route.fulfill({ json: {
    ...feedItems[0], source_image_recipe_available: true, result_url: "", result_urls: [],
    preview_url: boundPreview(0),
    preview_urls: [boundPreview(0)],
  } }));
  let quote: Record<string, unknown> | null = null;
  await page.route("**/api/v1/feed/201/remix/quote", route => {
    quote = route.request().postDataJSON();
    return route.fulfill({ json: { cost_credits: 1.5, balance_credits: 100, can_run: true } });
  });
  await page.goto("/?tgWebAppData=test&feed=201");
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog).toBeVisible();
  await dialog.locator("input[type=file]").setInputFiles({
    name: "ref.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect.poll(() => quote?.source_image_url).toBe(new URL(boundPreview(0), page.url()).href);
});


for (const restored of ["available", "expired", "legacy", "missing", "default"] as const) {
  test(`checkout restoration ${restored} validates the exact saved output before paid launch`, async ({ page }) => {
    const state = await pendingCheckout(page);
    let previews = [0, 1, 2].map(index => boundPreview(index));
    let available = new Set(["a".repeat(64), "b".repeat(64), "c".repeat(64)]);
    await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [{
      ...feedItems[0], source_image_recipe_available: true,
      result_url: "", result_urls: [], preview_url: previews[0], preview_urls: previews,
    }] }));
    const quoteBodies: Record<string, unknown>[] = [];
    await page.route("**/api/v1/feed/201/remix/quote", route => {
      const body = route.request().postDataJSON();
      quoteBodies.push(body);
      const outputId = new URL(body.source_image_url).searchParams.get("output_id");
      if (!outputId || !available.has(outputId)) return route.fulfill({ status: 422, json: {
        detail: "Выбранное фото недоступно или выбор устарел. Выберите фото заново в ленте; поцелуи не списаны.",
      } });
      return route.fulfill({ json: {
        cost_credits: 5, balance_credits: state.funded ? 10 : 0, can_run: state.funded,
        deficit_credits: state.funded ? 0 : 5,
        recommended_plan: state.funded ? null : { key: "starter", label: "Старт", credits: 10, price_rub: 100,
          payment_options: [{ provider: "tbank", amount: 100, currency: "RUB" }],
        },
      } });
    });
    let submitted: Record<string, unknown> | null = null;
    await page.route("**/api/v1/feed/201/remix", route => {
      submitted = route.request().postDataJSON();
      return route.fulfill({ status: 202, json: {
        id: 9201, model: "nano-banana-2", gen_type: "image", status: "pending",
        result_urls: [], credits_spent: 5, created_at: new Date().toISOString(),
      } });
    });
    const viewer = page.locator(".apix-media-viewer");
    await page.goto(restored === "default" ? "/?tgWebAppData=test&remix=201" : "/?tgWebAppData=test");
    if (restored !== "default") {
      await page.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first().click();
      await viewer.getByRole("button", { name: "Следующее фото" }).click();
      await expectViewerRepeatIsReachable(page);
      await viewer.getByRole("button", { name: "Повторить эту работу" }).click();
    }
    const dialog = page.getByRole("dialog", { name: "Повторить работу" });
    await expect(dialog.getByRole("button", { name: "Добавить", exact: true })).toBeEnabled();
    await dialog.locator("input[type=file]").setInputFiles({
      name: "ref.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await dialog.getByLabel("Что изменить в образе").fill("Белый костюм");
    await dialog.getByRole("button", { name: /Пополнить здесь/ }).click();
    await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
    // Pending UI appears before the invoice response. The restoration fixture
    // requires the actual same-checkout receipt, not the pre-response marker.
    await expect.poll(() => page.evaluate(() =>
      JSON.parse(sessionStorage.getItem("apix:feed-repeat-draft:v2:1:201")!).payment,
    )).toMatchObject({ transactionId: 701, checkoutUrl: "https://pay.example.test/original" });
    await expect(dialog.getByRole("button", { name: "Открыть эту оплату", exact: true })).toBeEnabled();
    const selected = new URL(boundPreview(restored === "default" ? 0 : 1), page.url()).href;
    const saved = await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:feed-repeat-draft:v2:1:201")!));
    expect(saved.sourceMediaUrl).toBe(selected);
    expect(saved.references).toEqual(["https://example.test/uploaded-ref.png"]);
    // Remove A before returning: index 1 now displays C, never the selected B.
    previews = [boundPreview(0, 1), boundPreview(1, 2)];
    available = new Set(["b".repeat(64), "c".repeat(64)]);
    if (restored === "expired") {
      previews = [boundPreview(0, 2)];
      available.delete("b".repeat(64));
    }
    if (restored === "legacy" || restored === "missing") {
      await restoreLegacySceneOnNextDocument(page, restored === "missing");
    }
    quoteBodies.length = 0;
    await page.goto("/?tgWebAppData=test&remix=201");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Что изменить в образе")).toHaveValue("Белый костюм");
    await expect(dialog.getByText("Реф #1")).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
    const restoredSource = restored === "legacy" ? selected.split("&output_id=")[0] : selected;
    const restoredDraft = await page.evaluate(() => JSON.parse(sessionStorage.getItem("apix:feed-repeat-draft:v2:1:201")!));
    expect(restoredDraft.sourceMediaUrl).toBe(restored === "missing" ? "" : restoredSource);
    expect(restoredDraft.references).toEqual(saved.references);
    expect(restoredDraft.payment).toEqual(saved.payment);
    if (restored !== "missing") await expect.poll(() => quoteBodies.some(body => body.source_image_url === restoredSource)).toBe(true);
    else expect(quoteBodies).toEqual([]);
    if (restored !== "available") {
      await expect(dialog.getByText(/Выберите фото заново в ленте/)).toBeVisible();
      await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeDisabled();
    }
    expect(submitted).toBeNull();
    expect(state.topups).toBe(1);
    // An explicit fresh gallery selection overrides the saved binding and keeps edits/receipt.
    await dialog.getByRole("button", { name: "Закрыть", exact: true }).click();
    await page.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first().click();
    if (previews.length > 1) await viewer.getByRole("button", { name: "Следующее фото" }).click();
    await expectViewerRepeatIsReachable(page);
    await viewer.getByRole("button", { name: "Повторить эту работу" }).click();
    const fresh = new URL(previews.at(-1)!, page.url()).href;
    await expect.poll(() => quoteBodies.at(-1)?.source_image_url).toBe(fresh);
    await expect(dialog.getByText("Реф #1")).toBeVisible();
    await expect(dialog.getByRole("button", { name: /Ждём подтверждение оплаты/ })).toBeDisabled();
    state.funded = true;
    await dialog.getByRole("button", { name: "Проверить оплату", exact: true }).click();
    await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
    await dialog.getByRole("button", { name: /Запустить повтор/ }).click();
    await expect.poll(() => submitted).not.toBeNull();
    expect(submitted).toMatchObject({ source_image_url: fresh,
      image_url: "https://example.test/uploaded-ref.png", reference_urls: ["https://example.test/uploaded-ref.png"],
      change_request: "Белый костюм",
    });
    expect(state.topups).toBe(1);
  });
}


test("gallery portal closes with Escape and native Back dismisses the repeat sheet first", async ({ page }) => {
  await mockMiniAppApi(page, true, true);
  // Keep this deterministic native BackButton fixture from being replaced by
  // the live SDK; no external Telegram session is part of this test.
  await page.route("https://telegram.org/js/telegram-web-app.js", route => route.fulfill({ contentType: "application/javascript", body: "" }));
  let submissions = 0;
  await page.route("**/api/v1/feed/201/remix", route => { submissions++; return route.abort(); });
  await page.goto("/?tgWebAppData=test");
  const open = page.getByRole("button", { name: "Открыть внутри приложения", exact: true }).first();
  const viewer = page.locator(".apix-media-viewer");
  await open.click();
  await expectViewerRepeatIsReachable(page);
  await page.keyboard.press("Escape");
  await expect(viewer).toHaveCount(0);
  await open.click();
  await expectViewerRepeatIsReachable(page);
  await viewer.getByRole("button", { name: "Повторить эту работу" }).click();
  const dialog = page.getByRole("dialog", { name: "Повторить работу" });
  await expect(dialog.getByRole("button", { name: /Запустить повтор/ })).toBeEnabled();
  await page.evaluate(() => window.dispatchEvent(new Event("apix:test-back")));
  await expect(dialog).toHaveCount(0);
  await expect(viewer).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("apix:test-back")));
  await expect(viewer).toHaveCount(0);
  expect(submissions).toBe(0);
});

for (const modelKey of ["wan/3-0-video", "wan/3-0-video-prime"]) {
  test(`Wan public repeat confirms server quote before launch: ${modelKey}`, async ({ page }) => {
    await mockMiniAppApi(page);
    const model = {
      key: modelKey, display_name: modelKey.endsWith("prime") ? "Wan 3.0 Prime" : "Wan 3.0",
      credits: 4, modes: ["text", "image", "video"],
      aspect_ratios: ["adaptive", "16:9", "9:16"], durations: [5, 10, 15, 30],
      resolutions: ["480p", "720p", "1080p"], max_refs: 10, supports_video_input: true,
    };
    const source = {
      id: 201, model: modelKey, gen_type: "video", prompt: "", prompt_hidden: true,
      source_has_video_reference: true, original_duration: 15,
      original_aspect_ratio: "9:16", original_resolution: "480p",
      result_url: "https://example.test/rendered.mp4", result_urls: ["https://example.test/rendered.mp4"],
      author: "Wan Creator", likes_count: 0, shares_count: 0, remixes: 0, is_mine: false,
    };
    await page.route("**/api/v1/feed?**", route => route.fulfill({ json: [source] }));
    await page.route("**/api/v1/feed/201", route => route.fulfill({ json: source }));
    await page.route("**/api/v1/models/video", route => route.fulfill({ json: [model] }));
    const quotes: Record<string, unknown>[] = [];
    await page.route("**/api/v1/feed/201/remix/quote", route => {
      quotes.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({ json: {
        cost_credits: 84, balance_credits: 100, can_run: true, deficit_credits: 0,
        output_seconds: 15, reference_seconds: 6, billable_seconds: 21,
      } });
    });
    const launches: Record<string, unknown>[] = [];
    await page.route("**/api/v1/feed/201/remix", route => {
      launches.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({ status: 202, json: {
        id: 9207, model: modelKey, gen_type: "video", status: "pending", prompt: "", prompt_hidden: true,
        result_url: null, result_urls: [], credits_spent: 84, created_at: new Date().toISOString(),
      } });
    });
    await page.goto("/?tgWebAppData=test&feed=201");
    const dialog = page.getByRole("dialog", { name: "Повторить работу" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Модель")).toBeDisabled();
    expect(launches).toHaveLength(0);
    await dialog.locator("input[type=file]").setInputFiles({
      name: "reader.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect(dialog.getByText("Стоимость: 84 💋").first()).toBeVisible();
    await expect.poll(() => quotes.length).toBeGreaterThan(0);
    expect(launches).toHaveLength(0);
    await dialog.getByRole("button", { name: /Запустить повтор/ }).click();
    await expect(page.getByRole("dialog", { name: /Задача #9207/ })).toBeVisible();
    expect(launches).toHaveLength(1);
    expect(launches[0]).toMatchObject({
      model: modelKey, image_url: "https://example.test/uploaded-ref.png",
      duration: 15, resolution: "480p", aspect_ratio: "9:16", quoted_credits: 84, change_request: "",
    });
    expect(launches[0]).not.toHaveProperty("wan30_request");
    expect(launches[0]).not.toHaveProperty("prompt");
  });
}
