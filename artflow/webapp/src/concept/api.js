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
  app.setHeaderColor?.("#08080f");
  app.setBackgroundColor?.("#08080f");
  app.setBottomBarColor?.("#08080f");
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
      const body = await response.json();
      detail = body.detail || body.message || detail;
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
      const body = await response.json();
      detail = body.detail || body.message || detail;
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
      .then((value) => {
        if (!alive) return;
        setData(value ?? fallback);
        setLoading(false);
      })
      .catch((reason) => {
        if (!alive) return;
        setData(fallback);
        setError(reason?.message || "Не удалось загрузить данные");
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
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number);
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
    return new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return "";
  }
}

export function publicPrompt(item) {
  if (item?.prompt_hidden || item?.prompt_actions_allowed === false) return "";
  return String(item?.prompt || item?.prompt_text || item?.description || "").trim();
}

export function generationResultUrls(item) {
  const urls = Array.isArray(item?.result_urls) ? item.result_urls.filter(Boolean) : [];
  if (!urls.length && item?.result_url) urls.push(item.result_url);
  return urls;
}

export function generationPreviewUrls(item) {
  const urls = Array.isArray(item?.preview_urls) ? item.preview_urls.filter(Boolean) : [];
  if (!urls.length && item?.preview_url) urls.push(item.preview_url);
  return urls.length ? urls : generationResultUrls(item);
}

export function feedPreviewCandidates(item, index = 0) {
  const payload = generationPreviewUrls(item);
  const originals = generationResultUrls(item);
  const candidates = [
    payload[index],
    item?.id ? `${API_BASE}/feed/${item.id}/preview.webp?index=${index}` : "",
    index === 0 ? item?.preview_url : "",
    originals[index],
    index === 0 ? item?.result_url : "",
  ];
  return [...new Set(candidates.filter(Boolean))];
}

export function feedDisplayCandidates(item, index = 0) {
  const previews = generationPreviewUrls(item);
  const originals = generationResultUrls(item);
  const candidates = [
    item?.id ? `${API_BASE}/feed/${item.id}/display.webp?index=${index}` : "",
    originals[index],
    previews[index],
    index === 0 ? item?.result_url : "",
    index === 0 ? item?.preview_url : "",
  ];
  return [...new Set(candidates.filter(Boolean))];
}

export function isVideoMedia(item, url = "") {
  return item?.gen_type === "video" || /\.(mp4|webm|mov)(?:$|\?)/i.test(url);
}

export async function uploadReference(file) {
  const form = new FormData();
  form.append("file", file);
  const result = await apiForm("/upload", form);
  if (!result?.url) throw new Error("Сервер не вернул ссылку на файл");
  return result.url;
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

export function openExternal(url) {
  if (!url) return;
  const target = new URL(url, window.location.origin).toString();
  const app = telegram();
  if (/^https:\/\/t\.me\//i.test(target)) app?.openTelegramLink?.(target);
  else if (app) app.openLink?.(target);
  else window.open(target, "_blank", "noopener,noreferrer");
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
