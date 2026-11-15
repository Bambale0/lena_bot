import assert from "node:assert/strict";
import { test } from "node:test";
import { readTelegramInitData, telegramInitDataIsFresh, waitForTelegramInitData } from "../../src/lib/telegram.ts";

const KEY = "apix:telegram-init-data:v2";
const now = () => Math.floor(Date.now() / 1000);
const payload = (authDate: number, userId = 1) =>
  new URLSearchParams({ auth_date: String(authDate), user: JSON.stringify({ id: userId }), hash: "placeholder" }).toString();

function browser(options: { live?: string; cached?: string; url?: string; early?: string } = {}) {
  const stored = new Map<string, string>();
  if (options.cached !== undefined) stored.set(KEY, options.cached);
  const storage = {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => { stored.set(key, value); },
    removeItem: (key: string) => { stored.delete(key); },
  };
  Object.assign(globalThis, {
    window: {
      location: { href: options.url || "https://example.invalid/app", origin: "https://example.invalid" },
      Telegram: { WebApp: { initData: options.live || "" } },
      sessionStorage: storage,
      __APIX_EARLY_URL__: options.early || "",
    },
  });
  return stored;
}

test("rejects malformed, expired and far-future Telegram initData without treating it as verified", () => {
  const ts = now();
  assert.equal(telegramInitDataIsFresh("", ts), false);
  assert.equal(telegramInitDataIsFresh("hash=placeholder", ts), false);
  assert.equal(telegramInitDataIsFresh("auth_date=garbage", ts), false);
  assert.equal(telegramInitDataIsFresh(payload(ts - 8 * 86_400), ts), false);
  assert.equal(telegramInitDataIsFresh(payload(ts + 600), ts), false);
  assert.equal(telegramInitDataIsFresh(payload(ts - 3_600), ts), true);
});

test("live Telegram SDK credentials take priority over a stale or different cached identity", () => {
  const live = payload(now() - 10, 123);
  const cached = payload(now() - 8 * 86_400, 999);
  const url = "https://example.invalid/app#tgWebAppData=" + encodeURIComponent(payload(now() - 30, 777));
  const stored = browser({ live, cached, url });
  assert.equal(readTelegramInitData(), live);
  assert.equal(stored.get(KEY), live);
});

test("expired sessionStorage cannot short-circuit Telegram SDK initialization", async () => {
  const stored = browser({ cached: payload(now() - 9 * 86_400) });
  assert.equal(readTelegramInitData(), "");
  assert.equal(stored.has(KEY), false);
  assert.equal(await waitForTelegramInitData(0), "");
  const current = payload(now() - 5, 42);
  (globalThis as any).window.Telegram.WebApp.initData = current;
  assert.equal(await waitForTelegramInitData(0), current);
});

test("fresh early Telegram URL can recover delayed WebApp SDK", () => {
  const source = payload(now() - 15, 55);
  const stored = browser({ early: "https://example.invalid/app#tgWebAppData=" + encodeURIComponent(source) });
  assert.equal(readTelegramInitData(), source);
  assert.equal(stored.get(KEY), source);
});
