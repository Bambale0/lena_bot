import { expect, test } from "@playwright/test";

const user = {
  id: 1,
  tg_id: 123,
  username: "tester",
  full_name: "Test User",
  credits: 100,
  referral_code: "REF123",
  referral_link: "https://t.me/apix_bot?start=REF123",
  referral_balance: 0,
  referral_withdraw_min_rub: 500,
  language: "ru",
};

const imageModels = [
  {
    key: "nano-banana-2",
    display_name: "🍌 Nano Banana 2",
    credits: 1.5,
    modes: ["text", "image"],
    aspect_ratios: ["1:1", "2:3", "3:2"],
    quality_options: [{ value: "2K", label: "2K" }],
    quality_prices: { "2K": 1.5 },
    counts: [1, 2, 4],
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
    counts: [],
    max_refs: 1,
    has_quality: true,
    supports_video_input: true,
  },
];

const plans = [
  { key: "mini", title: "мини", credits: 15, price_rub: 150, price_stars: 150 },
  { key: "start", title: "старт", credits: 25, price_rub: 250, price_stars: 250 },
];

const trends = [
  {
    id: 101,
    kind: "image",
    title: "Кинопортрет",
    description: "Загрузите портретное фото",
    user_photo_hint: "Лучше фото по пояс",
    preview_url: "https://example.test/trend.jpg",
    category: "portrait",
    category_title: "Портреты",
    category_emoji: "✨",
    uses_count: 3,
  },
  {
    id: 102,
    kind: "video",
    title: "Фото в видео",
    description: "Оживим ваш снимок",
    user_photo_hint: "Нужно одно селфи",
    preview_url: "https://example.test/trend.mp4",
    category: "photo-video",
    category_title: "Фото → видео",
    category_emoji: "🎬",
    uses_count: 5,
  },
];

async function mockApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/models/image", (route) => route.fulfill({ json: imageModels }));
  await page.route("**/api/v1/models/video", (route) => route.fulfill({ json: videoModels }));
  await page.route("**/api/v1/models/music", (route) => route.fulfill({ json: [{ key: "suno-v5", display_name: "Suno 5", credits: 10, modes: ["text"] }] }));
  await page.route("**/api/v1/history?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/feed?**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/trends?**", (route) => route.fulfill({ json: trends }));
  await page.route("**/api/v1/trends/101", (route) => route.fulfill({ json: trends[0] }));
  await page.route("**/api/v1/trends/101/checkout", (route) => route.fulfill({ json: {
    cost_credits: 1.5, balance_credits: 100, can_run: true,
    deficit_credits: 0, recommended_plan: null,
  } }));
  await page.route("**/api/v1/trends/101/link", (route) => route.fulfill({ json: { link: "https://t.me/apix_bot?start=ref_REF123__trend_101" } }));
  await page.route("**/api/v1/plans", (route) => route.fulfill({ json: plans }));
  await page.route("**/api/v1/referrals", (route) => route.fulfill({ json: {
    referral_code: "REF123",
    referral_link: "https://t.me/apix_bot?start=REF123",
    bonus_l1_credits: 5,
    commission_l1: 10,
    commission_l2: 5,
    commission_l3: 2,
    withdraw_min_rub: 500,
    exchange_min_rub: 100,
    exchange_rate_rub_per_credit: 10,
    counts: { l1: 0, l2: 0, l3: 0 },
    balance: { total_earned: 0, pending_withdrawals: 0, available_to_withdraw: 0 },
    feed_remix_reward_rub: 0,
    children: { l1: [], l2: [], l3: [] },
    withdrawals: [],
  } }));
  await page.route("**/api/v1/music/voices", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/settings/language", async (route) => {
    const body = route.request().postDataJSON() as { language?: string };
    await route.fulfill({ json: { language: body.language || "ru" } });
  });
  await page.route("**/api/v1/topup/**", (route) => route.fulfill({ json: { url: "https://example.test/pay" } }));
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
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("renders feed-first shell without horizontal overflow", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await expect(page.getByRole("tab", { name: "Лента" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Настройки" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(2);
});

test("background account refresh preserves the ordinary user's selected tab", async ({ page }) => {
  let historyResponses = 0;
  page.on("response", (response) => {
    if (new URL(response.url()).pathname === "/api/v1/history") historyResponses++;
  });
  await page.goto("/?tgWebAppData=test");
  await expect.poll(() => historyResponses).toBeGreaterThan(0);
  const photoTab = page.getByRole("tab", { name: "Фото" });
  await photoTab.click();
  await expect(photoTab).toHaveAttribute("aria-selected", "true");

  const beforeRefresh = historyResponses;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => historyResponses).toBeGreaterThan(beforeRefresh);

  await expect(photoTab).toHaveAttribute("aria-selected", "true");
});

test("payment cabinet uses kisses wording", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await expect(page.getByRole("tab", { name: "Лента" })).toBeVisible();
  await page.locator(".apix-balance-button").dispatchEvent("click");
  await expect(page.getByText("1. Пакет поцелуев")).toBeVisible();
  await expect(page.getByText(/15 поцелу/)).toBeVisible();
  await expect(page.getByText("кредиты")).toHaveCount(0);
});

test("settings expose color schemes and language switch", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Настройки" }).click();
  await expect(page.getByText("Цветовая схема")).toBeVisible();
  await expect(page.getByText("Поцелуй")).toBeVisible();
  await page.getByRole("button", { name: /English/ }).click();
  await expect(page.getByText("Language switched to English")).toBeVisible();
});

test("services expose mobile-friendly Suno music panel", async ({ page }) => {
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Сервисы" }).click();
  await expect(page.getByText("Музыка / Suno")).toBeVisible();
  await expect(page.getByPlaceholder("Текст песни или идея трека")).toBeVisible();
});

test("video trend selects quoted duration without automatic launch", async ({ page }) => {
  let sent: Record<string, unknown> | null = null;
  await page.route("**/api/v1/trends/102", route => route.fulfill({ json: trends[1] }));
  await page.route("**/api/v1/trends/102/checkout*", route => {
    const duration = Number(new URL(route.request().url()).searchParams.get("duration") || 10);
    return route.fulfill({ json: { cost_credits: duration * 4, balance_credits: 1000, can_run: true,
      deficit_credits: 0, default_duration: 10, effective_duration: duration, duration_options: [5, 10, 15, 30] } });
  });
  await page.route("**/api/v1/trends/upload", route => route.fulfill({ json: { asset_id: "apixasset.test.signature", url: "https://example.test/user.jpg", kind: "image" } }));
  await page.route("**/api/v1/trends/102/run", route => {
    sent = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { task: { id: 9020, gen_type: "video", status: "pending" } } });
  });
  await page.goto("/?tgWebAppData=test&startapp=trend_102");
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog");
  await expect(dialog.getByLabel("Длительность видео")).toHaveValue("10");
  await dialog.getByLabel("Длительность видео").selectOption("15");
  await dialog.locator("input[type=file]").setInputFiles({ name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]) });
  await expect(dialog.getByRole("button", { name: "Создать · 60 💋" })).toBeEnabled();
  expect(sent).toBeNull();
  await dialog.getByRole("button", { name: "Создать · 60 💋" }).click();
  await expect(page.getByRole("dialog", { name: /Задача #9020/ })).toBeVisible();
  expect(sent).toMatchObject({ duration: 15, quoted_credits: 60, asset_id: "apixasset.test.signature" });
  expect(sent).not.toHaveProperty("model");
});

test("one-photo trend runner uploads and runs without exposing generation controls", async ({ page }) => {
  let runPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/trends/upload", async (route) => {
    await route.fulfill({ json: { asset_id: "apixasset.test.signature", url: "https://example.test/user.jpg", kind: "image", filename: "face.jpg" } });
  });
  await page.route("**/api/v1/trends/101/run", async (route) => {
    runPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ json: {
      ok: true,
      credits: 98.5,
      task: {
        id: 9001,
        task_id: "web:trend-test",
        model: "Nano Banana 2",
        gen_type: "image",
        prompt: "",
        prompt_hidden: true,
        status: "pending",
        result_url: null,
        result_urls: [],
        credits_spent: 1.5,
        created_at: new Date().toISOString(),
      },
    } });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Тренды" }).click();
  await expect(page.getByText("Кинопортрет").first()).toBeVisible();
  const portraitFilter = page.getByRole("button", { name: "✨ Портреты", exact: true });
  await expect(portraitFilter).toBeVisible();
  await portraitFilter.click();
  await page.getByRole("button", { name: /Повторить/ }).first().click();

  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: /Кинопортрет/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("select")).toHaveCount(0);
  await expect(dialog.locator("textarea")).toHaveCount(0);
  await expect(dialog.getByRole("combobox")).toHaveCount(0);

  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });

  await expect(page.getByRole("dialog", { name: /Задача #9001/ })).toBeVisible();
  expect(runPayload).toMatchObject({ asset_id: "apixasset.test.signature" });
  expect(typeof runPayload?.idempotency_key).toBe("string");
  expect(runPayload?.quoted_credits).toBe(1.5);
  expect(runPayload).not.toHaveProperty("model");
  expect(runPayload).not.toHaveProperty("prompt");
  expect(runPayload).not.toHaveProperty("ratio");
  expect(runPayload).not.toHaveProperty("duration");
});

test("retrying a trend after a lost response keeps the same request key", async ({ page }) => {
  const keys: string[] = [];
  await page.route("**/api/v1/trends/upload", (route) => route.fulfill({ json: {
    asset_id: "apixasset.retry.signature", url: "https://example.test/user.jpg", kind: "image",
  } }));
  await page.route("**/api/v1/trends/101/run", (route) => {
    const body = route.request().postDataJSON() as { idempotency_key: string };
    keys.push(body.idempotency_key);
    return route.fulfill({ status: 503, json: { detail: "Temporary response failure" } });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Тренды" }).click();
  await page.getByRole("button", { name: "✨ Портреты", exact: true }).click();
  await page.getByRole("button", { name: /Повторить/ }).first().click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: /Кинопортрет/ });
  await expect(dialog.getByText("1.5 💋", { exact: true })).toBeVisible();
  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect.poll(() => keys.length).toBe(1);
  await dialog.getByRole("button", { name: /Создать/ }).click();
  await expect.poll(() => keys.length).toBe(2);
  expect(keys[1]).toBe(keys[0]);
});

test("trend runner shows a useful message for an empty server error", async ({ page }) => {
  await page.route("**/api/v1/trends/upload", (route) => route.fulfill({ json: {
    asset_id: "apixasset.server.signature", url: "https://example.test/user.jpg", kind: "image",
  } }));
  await page.route("**/api/v1/trends/101/run", (route) => route.fulfill({
    status: 500, body: "", contentType: "text/plain",
  }));

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Тренды" }).click();
  await page.getByRole("button", { name: "✨ Портреты", exact: true }).click();
  await page.getByRole("button", { name: /Повторить/ }).first().click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: /Кинопортрет/ });
  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });

  await expect(dialog.getByText("Не удалось запустить тренд. Попробуйте ещё раз.")).toBeVisible();
  await expect(dialog).not.toContainText("Ошибка API 500");
});

test("stale trend price refreshes checkout and reuses the uploaded photo", async ({ page }) => {
  let price = 1.5;
  let uploads = 0;
  const runs: Array<{ asset_id: string; idempotency_key: string; quoted_credits: number }> = [];
  await page.route("**/api/v1/trends/101/checkout", route => route.fulfill({ json: {
    cost_credits: price, balance_credits: 100, can_run: true,
    deficit_credits: 0, recommended_plan: null,
  } }));
  await page.route("**/api/v1/trends/upload", route => {
    uploads++;
    return route.fulfill({ json: {
      asset_id: "apixasset.price.signature", url: "https://example.test/user.jpg", kind: "image",
    } });
  });
  await page.route("**/api/v1/trends/101/run", route => {
    const body = route.request().postDataJSON() as typeof runs[number];
    runs.push(body);
    if (runs.length === 1) {
      price = 2;
      return route.fulfill({ status: 409, json: { detail: {
        code: "trend_quote_stale", message: "Цена тренда изменилась. Проверь стоимость и подтверди запуск.",
      } } });
    }
    return route.fulfill({ json: { ok: true, credits: 98, task: {
      id: 9002, task_id: "web:trend-price", model: "Nano Banana 2",
      gen_type: "image", prompt: "", prompt_hidden: true, status: "pending",
      result_url: null, result_urls: [], credits_spent: 2,
      created_at: new Date().toISOString(),
    } } });
  });

  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Тренды" }).click();
  await page.getByRole("button", { name: "✨ Портреты", exact: true }).click();
  await page.getByRole("button", { name: /Повторить/ }).first().click();
  const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: /Кинопортрет/ });
  await expect(dialog.getByText("1.5 💋", { exact: true })).toBeVisible();
  await dialog.locator("input[type=file]").setInputFiles({
    name: "face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
  });
  await expect.poll(() => runs.length).toBe(1);
  await expect(dialog.getByRole("button", { name: "Создать · 2 💋" })).toBeVisible();
  await dialog.getByRole("button", { name: /Создать/ }).click();
  await expect(page.getByRole("dialog", { name: /Задача #9002/ })).toBeVisible();
  expect(uploads).toBe(1);
  expect(runs.map(run => run.quoted_credits)).toEqual([1.5, 2]);
  expect(runs[1].asset_id).toBe(runs[0].asset_id);
  expect(runs[1].idempotency_key).toBe(runs[0].idempotency_key);
});


test("Seedance recovery stays neutral and reaches ready without a paid replay", async ({ page }) => {
  let status = "processing";
  let submits = 0;
  const task = () => ({
    id: 731, model: "bytedance/seedance-2-5", gen_type: "video", status,
    prompt: "test scene", credits_spent: 70, created_at: new Date().toISOString(),
    result_url: status === "done" ? "https://example.test/completed.mp4" : null,
  });
  await page.route("**/api/v1/generations/731", route => route.fulfill({ json: task() }));
  await page.route("**/api/v1/history?**", route => route.fulfill({ json: [task()] }));
  await page.route("**/api/v1/generate/video", route => {
    submits++;
    return route.fulfill({ status: 500, json: { detail: "No paid replay expected" } });
  });
  await page.goto("/?tgWebAppData=test&task=731");
  const dialog = page.getByRole("dialog", { name: /Задача #731/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Генерация ещё выполняется")).toBeVisible();
  status = "reconciliation_required";
  await dialog.getByRole("button", { name: /Обновить/ }).click();
  await expect(dialog.getByText("Создаётся", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Задача принята. Результат появится здесь автоматически.")).toBeVisible();
  await expect(dialog).not.toContainText(/поставщик|провайдер|удержан|уточняем|обратитесь в поддержку/i);
  await expect(page.getByText("Результат готов", { exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Опубликовать/ })).toBeDisabled();
  status = "done";
  await dialog.getByRole("button", { name: /Обновить/ }).click();
  await expect(dialog.getByText("Готово", { exact: true })).toBeVisible();
  expect(submits).toBe(0);
});

for (const trend of trends) {
  test(`bot trend=${trend.id} deep link uses shared upload/claim runner only`, async ({ page }) => {
    const genericRequests: string[] = [];
    const runs: Record<string, unknown>[] = [];
    let checkoutReads = 0;
    await page.route(`**/api/v1/trends/${trend.id}`, (route) => route.fulfill({ json: trend }));
    await page.route(`**/api/v1/trends/${trend.id}/checkout`, (route) => {
      checkoutReads += 1;
      return route.fulfill({ json: {
        cost_credits: 1.5, balance_credits: 100, can_run: true,
        deficit_credits: 0, recommended_plan: null,
      } });
    });
    await page.route("**/api/v1/trends/*/prepare", (route) => {
      genericRequests.push(route.request().url());
      return route.fulfill({ status: 409, json: { detail: "Generic preparation must not run for a bot trend link" } });
    });
    await page.route("**/api/v1/generate/**", (route) => {
      genericRequests.push(route.request().url());
      return route.fulfill({ status: 409, json: { detail: "Use shared trend runner" } });
    });
    await page.route("**/api/v1/trends/upload", (route) => route.fulfill({ json: {
      asset_id: "apixasset.bot-entry.signature", url: "https://example.test/own-face.jpg", kind: "image",
    } }));
    await page.route(`**/api/v1/trends/${trend.id}/run`, (route) => {
      runs.push(route.request().postDataJSON() as Record<string, unknown>);
      return route.fulfill({ json: {
        ok: true, credits: 98.5,
        task: { id: 9500 + trend.id, model: "test-model", gen_type: trend.kind,
          prompt: "", prompt_hidden: true, status: "pending", result_url: null,
          result_urls: [], credits_spent: 1.5, created_at: new Date().toISOString() },
      } });
    });
    await page.goto(`/?trend=${trend.id}&tgWebAppData=test`);
    const dialog = page.locator("#apix-trend-runner-root").getByRole("dialog", { name: trend.title });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("tab", { name: "Лента", exact: true })).toBeVisible();
    await expect.poll(() => checkoutReads).toBeGreaterThan(0);
    expect(runs).toHaveLength(0);
    expect(genericRequests).toEqual([]);
    await expect(dialog.locator("textarea, select")).toHaveCount(0);

    await dialog.locator("input[type=file]").setInputFiles({
      name: "own-face.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xd9]),
    });
    await expect(page.getByRole("dialog", { name: `Задача #${9500 + trend.id}` })).toBeVisible();
    expect(runs).toHaveLength(1);
    expect(runs[0]).toMatchObject({ asset_id: "apixasset.bot-entry.signature", quoted_credits: 1.5 });
    expect(typeof runs[0].idempotency_key).toBe("string");
    expect(runs[0]).not.toHaveProperty("prompt");
    expect(runs[0]).not.toHaveProperty("model");
    expect(genericRequests).toEqual([]);
  });
}


test("new Wan Prime draft quotes native-compatible defaults and retains explicit standby options", async ({ page }) => {
  const quotes: Record<string, unknown>[] = [];
  await page.route("**/api/v1/models/video", route => route.fulfill({ json: [...videoModels, {
    key: "wan/3-0-video-prime", display_name: "Wan 3.0 Prime", credits: 18,
    modes: ["text", "image", "video"], aspect_ratios: ["16:9", "9:16", "1:1", "adaptive", "4:3", "3:4"],
    aspect_ratio_modes: ["text", "image", "video"], duration_options: [2, 3, 5, 8],
    resolution_options: ["480p", "720p", "1080p"], max_refs: 10,
  }] }));
  await page.route("**/api/v1/generate/video/quote", route => {
    quotes.push(route.request().postDataJSON());
    return route.fulfill({ json: { credits: 90, rate: 18, billable_seconds: 5, input_video_seconds: 0 } });
  });
  await page.goto("/?tgWebAppData=test");
  await page.getByRole("tab", { name: "Видео", exact: true }).click();
  await page.getByRole("combobox", { name: "Модель", exact: true }).selectOption("wan/3-0-video-prime");
  await expect.poll(() => quotes.at(-1)?.aspect_ratio).toBe("16:9");
  expect(quotes.at(-1)?.duration).toBe(5);
  expect(quotes.at(-1)?.resolution).toBe("720p");
  await page.getByRole("button", { name: "adaptive", exact: true }).click();
  await expect.poll(() => quotes.at(-1)?.aspect_ratio).toBe("adaptive");
});
