import assert from "node:assert/strict";
import { test } from "node:test";
import * as telegram from "../../src/lib/telegram.ts";
const { configureTelegramWebApp } = telegram;

function environment(overrides: Record<string, unknown> = {}) {
  const values = new Map<string, string>();
  const events = new Map<string, () => void>();
  const calls: string[] = [];
  const app = { version: "8.0", initData: "test", isFullscreen: false, colorScheme: "dark", headerColor: "#123456", backgroundColor: "#234567", bottomBarColor: "#345678",
    ready: () => calls.push("ready"), expand: () => calls.push("expand"), requestFullscreen: () => calls.push("fullscreen"),
    onEvent: (name: string, callback: () => void) => events.set(name, callback), offEvent: (name: string) => events.delete(name),
    setHeaderColor: (value: string) => calls.push(`header:${value}`), setBackgroundColor: (value: string) => calls.push(`background:${value}`), setBottomBarColor: (value: string) => calls.push(`bottom:${value}`),
    safeAreaInset: { top: 24, bottom: 12, left: 0, right: 0 }, contentSafeAreaInset: { top: 32, bottom: 0, left: 0, right: 0 }, ...overrides };
  Object.assign(globalThis, { window: { Telegram: { WebApp: app } }, document: { documentElement: { classList: { toggle() {} }, style: { setProperty: (key: string, value: string) => values.set(key, value), getPropertyValue: (key: string) => values.get(key) || "", removeProperty: (key: string) => values.delete(key) } } } });
  return { app, calls, events, values };
}

test("modern Telegram requests fullscreen once, tracks insets and cleans listeners", () => {
  const { app, calls, events, values } = environment();
  const cleanup = configureTelegramWebApp();
  assert.deepEqual(calls, ["ready", "expand", "fullscreen"]);
  assert.equal(values.get("--tg-safe-area-inset-top"), "24px");
  assert.equal(values.get("--tg-content-safe-area-inset-top"), "32px");
  app.contentSafeAreaInset.top = 48; events.get("contentSafeAreaChanged")?.();
  assert.equal(values.get("--tg-content-safe-area-inset-top"), "48px");
  events.get("fullscreenChanged")?.(); events.get("fullscreenFailed")?.(); events.get("viewportChanged")?.();
  assert.equal(calls.filter(value => value === "fullscreen").length, 1);
  cleanup(); assert.equal(events.size, 0); assert.equal(values.size, 0);
});

test("old, missing and already fullscreen clients use honest fallback", () => {
  for (const overrides of [{ version: "7.10" }, { requestFullscreen: undefined }, { isFullscreen: true }, { isVersionAtLeast: () => false }]) {
    const { calls } = environment(overrides); const cleanup = configureTelegramWebApp();
    assert.deepEqual(calls, ["ready", "expand"]); cleanup();
  }
  environment(); (globalThis as any).window.Telegram = undefined;
  assert.doesNotThrow(() => configureTelegramWebApp()());
});

test("throwing Telegram APIs cannot break initialization or cleanup", () => {
  const fail = () => { throw new Error("UNSUPPORTED"); };
  environment({ ready: fail, expand: fail, requestFullscreen: fail, onEvent: fail, offEvent: fail });
  assert.doesNotThrow(() => configureTelegramWebApp()());
});

test("Studio chrome becomes black lilac and restores the previous colors", () => {
  const { calls } = environment(); const cleanup = telegram.configureStudioChrome();
  assert.deepEqual(calls, ["header:#000000", "background:#000000", "bottom:#000000"]);
  cleanup();
  assert.deepEqual(calls.slice(3), ["header:#123456", "background:#234567", "bottom:#345678"]);
});

test("reconfiguration after user exit never forces fullscreen again", () => {
  const { calls } = environment();
  configureTelegramWebApp()(); configureTelegramWebApp()();
  assert.equal(calls.filter(call => call === "fullscreen").length, 1);
});
