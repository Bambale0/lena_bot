import { useCallback, useEffect, useState } from "react";

export const API_BASE = "/api/v1";

export function telegram() {
  return window.Telegram?.WebApp || null;
}

export function telegramUser() {
  return telegram()?.initDataUnsafe?.user || null;
}

export function telegramInitData() {
  return telegram()?.initData || "";
}

export function prepareTelegram() {
  const app = telegram();
  if (!app) return;
  app.ready?.();
  app.expand?.();
  app.enableClosingConfirmation?.();
  app.setHeaderColor?.("#08080d");
  app.setBackgroundColor?.("#08080d");
  app.setBottomBarColor?.("#08080d");
}

export async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": telegramInitData(),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let detail = `API ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch {}
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;
  return response.json();
}

export async function apiForm(path, formData, options = {}) {
  const response = await fetch(path.startsWith("/api/") ? path : `${API_BASE}${path}`, {
    ...options,
    method: options.method || "POST",
    headers: {
      "X-Telegram-Init-Data": telegramInitData(),
      ...(options.headers || {}),
    },
    body: formData,
  });

  if (!response.ok) {
    let detail = `API ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch {}
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

export function asItems(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  return [];
}

export function useResource(loader, fallback, deps = []) {
  const [data, setData] = useState(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);

  const reload = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    Promise.resolve()
      .then(loader)
      .then((result) => {
        if (!alive) return;
        setData(result ?? fallback);
        setLoading(false);
      })
      .catch((reason) => {
        if (!alive) return;
        setError(reason?.message || "Не удалось загрузить данные");
        setData(fallback);
        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [...deps, version]);

  return { data, setData, loading, error, reload };
}

export function formatCredits(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(2)));
}

export function formatCompact(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  return new Intl.NumberFormat("ru-RU", {
    notation: number >= 1000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(number);
}

export function formatDate(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function generationResultUrls(generation) {
  const urls = Array.isArray(generation?.result_urls)
    ? generation.result_urls.filter(Boolean)
    : [];
  if (!urls.length && generation?.result_url) urls.push(generation.result_url);
  return urls;
}

export function generationPreviewUrls(generation) {
  const urls = Array.isArray(generation?.preview_urls)
    ? generation.preview_urls.filter(Boolean)
    : [];
  if (!urls.length && generation?.preview_url) urls.push(generation.preview_url);
  return urls.length ? urls : generationResultUrls(generation);
}

export function isVideoMedia(item, url = "") {
  return item?.gen_type === "video" || /\.(mp4|webm|mov)(?:$|\?)/i.test(url);
}

export function isImageMedia(item, url = "") {
  return !isVideoMedia(item, url) && item?.gen_type !== "music";
}

export function publicPrompt(item) {
  if (item?.prompt_hidden || item?.prompt_actions_allowed === false) return "";
  return String(item?.prompt || item?.prompt_text || item?.description || "").trim();
}

export function absoluteUrl(value) {
  if (!value) return "";
  try {
    return new URL(value, window.location.origin).toString();
  } catch {
    return String(value);
  }
}

export async function copyText(value) {
  if (!value) return false;
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  }
}

export function openTelegramLink(url) {
  if (!url) return;
  const target = absoluteUrl(url);
  const app = telegram();
  if (/^https:\/\/t\.me\//i.test(target)) app?.openTelegramLink?.(target);
  else if (app) app.openLink?.(target);
  else window.open(target, "_blank", "noopener,noreferrer");
}

export async function uploadReference(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/upload", {
    method: "POST",
    headers: { "X-Telegram-Init-Data": telegramInitData() },
    body: form,
  });

  if (!response.ok) {
    let detail = response.status === 413
      ? "Файл слишком большой. Максимум 20 МБ."
      : "Не удалось загрузить файл";
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch {}
    throw new Error(detail);
  }

  const payload = await response.json();
  if (!payload.url) throw new Error("Сервер не вернул ссылку на файл");
  return payload.url;
}

export function generationFromRealtime(payload) {
  if (!payload || payload.type !== "generation.updated") return null;
  const promptHidden = Boolean(payload.prompt_hidden) || payload.prompt_actions_allowed === false;
  return {
    id: payload.id || payload.generation_id,
    model: payload.model || "",
    gen_type: payload.gen_type || "image",
    prompt: promptHidden ? "" : payload.prompt || "",
    prompt_hidden: promptHidden,
    prompt_actions_allowed: !promptHidden && payload.prompt_actions_allowed !== false,
    status: payload.status || "pending",
    result_url: payload.result_url || null,
    preview_url: payload.preview_url || payload.result_url || null,
    result_urls: Array.isArray(payload.result_urls) ? payload.result_urls.filter(Boolean) : [],
    preview_urls: Array.isArray(payload.preview_urls) ? payload.preview_urls.filter(Boolean) : [],
    error: payload.error || null,
    credits_spent: Number(payload.credits_spent || 0),
    created_at: payload.created_at || "",
    is_public_feed: Boolean(payload.is_public_feed),
    is_prompt_library: Boolean(payload.is_prompt_library),
  };
}
