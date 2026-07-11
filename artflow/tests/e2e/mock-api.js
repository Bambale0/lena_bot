const USER = {
  id: 1,
  tg_id: 123456789,
  username: "creator",
  full_name: "Тестовый креатор",
  email: "creator@example.com",
  phone: null,
  photo_url: null,
  credits: 120,
  referral_code: "TESTREF",
  language: "ru",
  is_admin: false,
};

const IMAGE_MODEL = {
  model_key: "gpt-image-2-text-to-image",
  technical_key: "gpt-image-2-text-to-image",
  display_name: "GPT Image 2",
  gen_type: "image",
  credits: 5,
  capabilities: ["text-to-image", "image"],
  is_active: true,
  aspect_ratios: ["9:16", "1:1", "16:9"],
  quality_options: ["basic", "2K", "4K"],
  quality_prices: { basic: 5, "2K": 7, "4K": 10 },
  counts: [1, 2, 4],
  max_refs: 0,
};

const EDIT_MODEL = {
  model_key: "nano-banana-pro",
  technical_key: "nano-banana-pro",
  display_name: "Nano Banana Pro",
  gen_type: "image",
  credits: 4,
  capabilities: ["image-to-image", "reference", "edit"],
  is_active: true,
  aspect_ratios: ["9:16", "1:1", "16:9"],
  quality_options: ["basic", "2K"],
  quality_prices: { basic: 4, "2K": 6 },
  counts: [1, 2],
  max_refs: 4,
};

const VIDEO_MODEL = {
  model_key: "kling-3.0/video",
  technical_key: "kling-3.0/video",
  display_name: "Kling 3.0",
  gen_type: "video",
  credits: 35,
  capabilities: ["text-to-video", "image-to-video", "video"],
  is_active: true,
  aspect_ratios: ["9:16", "16:9", "1:1"],
  durations: [5, 10],
  resolutions: ["720p", "1080p"],
  price_table: {
    "720p": { "5": 35, "10": 60 },
    "1080p": { "5": 45, "10": 80 },
  },
};

const MUSIC_MODEL = {
  model_key: "suno/v4.5",
  technical_key: "suno/v4.5",
  display_name: "Suno 4.5",
  gen_type: "music",
  credits: 12,
  capabilities: ["music", "lyrics", "instrumental"],
  is_active: true,
};

const MODELS = {
  image: [IMAGE_MODEL, EDIT_MODEL],
  video: [VIDEO_MODEL],
  music: [MUSIC_MODEL],
};
MODELS.all = [...MODELS.image, ...MODELS.video, ...MODELS.music];

const FEED = [
  {
    id: 101,
    generation_id: 101,
    type: "image",
    gen_type: "image",
    result_url: "/images/home/home-gpt-image-create.webp",
    result_urls: ["/images/home/home-gpt-image-create.webp"],
    prompt: "Премиальный рекламный портрет в мягком студийном свете",
    prompt_visibility: "public",
    model: "gpt-image-2-text-to-image",
    author: "@creator",
    likes: 14,
    shares: 2,
    remix_count: 3,
    aspect_ratio: "9:16",
    quality: "2K",
    created_at: "2026-07-11T10:00:00Z",
    can_remix: true,
    can_use_reference: true,
  },
];

const PROMPTS = [
  {
    id: 201,
    title: "Премиальный портрет",
    description: "Студийный портрет для рекламы и обложек",
    prompt_text: "Премиальный портрет, мягкий контровой свет, чистый фон",
    preview_url: "/images/home/home-nano-reference.webp",
    model: "nano-banana-pro",
    tags: ["portrait", "premium"],
    likes: 22,
    uses_count: 41,
    status: "approved",
    is_mine: false,
  },
];

const PLANS = [
  {
    key: "start",
    name: "Старт",
    credits: 100,
    amount_rub: 499,
    price_rub: 499,
    is_active: true,
  },
];

function ok(data) {
  return { ok: true, data };
}

async function json(route, data, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify(data),
  });
}

function installWebSocketMock(page) {
  return page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.CONNECTING;
        this.listeners = new Map();
        setTimeout(() => {
          this.readyState = MockWebSocket.OPEN;
          this.emit("open", {});
        }, 0);
      }

      addEventListener(type, callback) {
        const items = this.listeners.get(type) || [];
        items.push(callback);
        this.listeners.set(type, items);
      }

      removeEventListener(type, callback) {
        const items = this.listeners.get(type) || [];
        this.listeners.set(type, items.filter((item) => item !== callback));
      }

      emit(type, event) {
        const handler = this[`on${type}`];
        if (typeof handler === "function") handler(event);
        for (const callback of this.listeners.get(type) || []) callback(event);
      }

      send(raw) {
        let payload = null;
        try {
          payload = JSON.parse(raw);
        } catch {
          payload = null;
        }
        if (payload?.type === "auth") {
          setTimeout(() => {
            this.emit("message", {
              data: JSON.stringify({ type: "snapshot", items: [] }),
            });
          }, 0);
        }
        if (payload?.type === "ping") {
          setTimeout(() => {
            this.emit("message", {
              data: JSON.stringify({ type: "pong", ts: payload.ts }),
            });
          }, 0);
        }
      }

      close() {
        this.readyState = MockWebSocket.CLOSED;
        this.emit("close", { code: 1000 });
      }
    }

    window.WebSocket = MockWebSocket;
  });
}

async function installApiMocks(page, options = {}) {
  const authenticated = options.authenticated ?? true;
  const isAdmin = options.isAdmin ?? false;
  const failPaths = options.failPaths || [];
  const calls = {
    generate: [],
    paths: [],
  };

  await installWebSocketMock(page);

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    calls.paths.push(`${request.method()} ${path}`);

    if (failPaths.some((fragment) => path.includes(fragment))) {
      await json(route, { ok: false, error: "Тестовая ошибка API" }, 500);
      return;
    }

    if (path.endsWith("/auth/config")) {
      await json(route, ok({
        telegram_login_enabled: false,
        telegram_bot_username: "APIXBot",
        contact_auth_enabled: true,
        password_auth_enabled: true,
        captcha: { enabled: false, provider: "turnstile", site_key: "" },
      }));
      return;
    }

    if (path.endsWith("/me")) {
      if (!authenticated) {
        await json(route, { ok: false, error: "Authentication required" }, 401);
        return;
      }
      await json(route, ok({ ...USER, is_admin: isAdmin }));
      return;
    }

    if (path.endsWith("/landing")) {
      await json(route, ok({
        models: MODELS,
        examples: FEED,
        prompts: { items: PROMPTS, total: PROMPTS.length },
        plans: PLANS,
        payment_methods: [
          { key: "tbank", label: "Карта", status: "enabled" },
          { key: "stars", label: "Telegram Stars", status: "enabled" },
        ],
      }));
      return;
    }

    if (path.endsWith("/models")) {
      await json(route, ok(MODELS));
      return;
    }
    if (path.endsWith("/models/image")) {
      await json(route, ok(MODELS.image));
      return;
    }
    if (path.endsWith("/models/video")) {
      await json(route, ok(MODELS.video));
      return;
    }
    if (path.endsWith("/models/music")) {
      await json(route, ok(MODELS.music));
      return;
    }

    if (path.endsWith("/price-plans") || path.endsWith("/plans")) {
      await json(route, ok(PLANS));
      return;
    }

    if (path.includes("/feed")) {
      if (request.method() === "GET") {
        await json(route, ok({ items: FEED, total: FEED.length }));
      } else {
        await json(route, ok({ success: true }));
      }
      return;
    }

    if (path.includes("/prompts")) {
      if (request.method() === "GET") {
        const promptId = Number(path.split("/").at(-1));
        if (Number.isFinite(promptId)) {
          await json(route, ok(PROMPTS.find((item) => item.id === promptId) || PROMPTS[0]));
        } else {
          await json(route, ok({ items: PROMPTS, total: PROMPTS.length }));
        }
      } else {
        await json(route, ok({ ...PROMPTS[0], id: 202, status: "pending" }));
      }
      return;
    }

    if (path.endsWith("/history")) {
      await json(route, ok([]));
      return;
    }

    if (path.endsWith("/generations/active")) {
      await json(route, ok([]));
      return;
    }

    if (/\/generations\/\d+$/.test(path)) {
      await json(route, ok({
        id: 501,
        generation_id: 501,
        gen_type: "image",
        type: "image",
        status: "processing",
        model: IMAGE_MODEL.model_key,
        prompt: "Тестовый промпт",
        credits_spent: IMAGE_MODEL.credits,
        result_url: null,
        result_urls: [],
      }));
      return;
    }

    if (path.endsWith("/image-sessions/active")) {
      await json(route, ok(null));
      return;
    }

    if (path.includes("/billing") || path.includes("/payment-methods") || path.includes("/payment-options")) {
      await json(route, ok({
        balance: USER.credits,
        credits: USER.credits,
        plans: PLANS,
        methods: [
          { key: "tbank", label: "Карта", status: "enabled" },
          { key: "stars", label: "Telegram Stars", status: "enabled" },
        ],
        transactions: [],
      }));
      return;
    }

    if (path.includes("/referrals")) {
      await json(route, ok({
        referral_code: USER.referral_code,
        referral_link: "https://apixbotai.com/account.html?ref=TESTREF",
        levels: { l1: 2, l2: 1, l3: 0 },
        available_rub: 120,
        pending_rub: 0,
        min_withdraw_rub: 1000,
        withdrawals: [],
      }));
      return;
    }

    if (path.endsWith("/help")) {
      await json(route, ok({
        title: "Помощь",
        items: [{ title: "Как начать", text: "Откройте Studio и выберите сценарий." }],
      }));
      return;
    }

    if (path.endsWith("/assistant")) {
      await json(route, ok({ message: "Тестовый ответ ассистента" }));
      return;
    }

    if (path.includes("/generate/")) {
      let body = null;
      try {
        body = request.postDataJSON();
      } catch {
        body = request.postData();
      }
      calls.generate.push({ path, body });
      await json(route, ok({
        id: 501,
        generation_id: 501,
        task_id: "web_test_task",
        status: "processing",
        model: body?.model || IMAGE_MODEL.model_key,
        credits_spent: IMAGE_MODEL.credits,
      }), 202);
      return;
    }

    if (path.includes("/admin/")) {
      if (!isAdmin) {
        await json(route, { ok: false, error: "Forbidden" }, 403);
        return;
      }
      await json(route, ok({ items: [], total: 0 }));
      return;
    }

    if (!authenticated && request.method() !== "GET") {
      await json(route, { ok: false, error: "Authentication required" }, 401);
      return;
    }

    await json(route, ok(request.method() === "GET" ? [] : {}));
  });

  return calls;
}

module.exports = {
  FEED,
  MODELS,
  PLANS,
  PROMPTS,
  USER,
  installApiMocks,
};
