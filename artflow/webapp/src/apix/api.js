const API_BASE = "/api/v1";
const DEFAULT_TIMEOUT_MS = 30000;
const PHOTO_PROMPT_TIMEOUT_MS = 120000;

export function tg() {
  return window.Telegram?.WebApp || null;
}

export function initData() {
  return tg()?.initData || "";
}

export function tgUser() {
  return tg()?.initDataUnsafe?.user || null;
}

export function isTelegramRuntime() {
  return Boolean(initData());
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  const data = initData();
  if (data) headers["X-Telegram-Init-Data"] = data;
  const webToken = window.localStorage?.getItem("apix_web_auth_token");
  if (webToken) headers["X-Web-Auth-Token"] = webToken;
  return headers;
}

async function readErrorDetail(response, fallback) {
  let detail = fallback;
  try {
    const payload = await response.json();
    detail = payload.detail || payload.message || detail;
  } catch {
    const text = await response.text().catch(() => "");
    if (text) detail = text;
  }
  return detail;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(new Error("timeout")), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error("Запрос занял слишком много времени. Попробуй еще раз.");
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function api(path, options = {}) {
  const body = options.body;
  const hasBody = body !== undefined && body !== null;
  const response = await fetchWithTimeout(`${API_BASE}${path}`, {
    ...options,
    headers: authHeaders({
      ...(hasBody && !(body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    }),
  }, options.timeoutMs || DEFAULT_TIMEOUT_MS);

  if (!response.ok) {
    const detail = await readErrorDetail(response, `API ${response.status}`);
    throw Object.assign(new Error(detail), { status: response.status });
  }

  if (response.status === 204) return null;
  return response.json();
}

export async function uploadReference(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetchWithTimeout("/upload", {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });

  if (!response.ok) {
    const detail = await readErrorDetail(response, `Upload ${response.status}`);
    throw new Error(detail);
  }
  return response.json();
}

export async function photoPrompt(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetchWithTimeout(`${API_BASE}/photo-prompt`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  }, PHOTO_PROMPT_TIMEOUT_MS);

  if (!response.ok) {
    const detail = await readErrorDetail(response, `Photo prompt ${response.status}`);
    throw new Error(detail);
  }
  return response.json();
}

export function listItems(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

export function setupTelegramChrome() {
  const webapp = tg();
  if (!webapp) return;
  webapp.ready?.();
  webapp.expand?.();
  webapp.setHeaderColor?.("#07050c");
  webapp.setBackgroundColor?.("#07050c");
  webapp.disableVerticalSwipes?.();
}

export function haptic(kind = "light") {
  tg()?.HapticFeedback?.impactOccurred?.(kind);
}

export function notify(type = "success") {
  tg()?.HapticFeedback?.notificationOccurred?.(type);
}

export function openTelegramLink(url) {
  if (!url) return;
  const webapp = tg();
  if (webapp?.openTelegramLink && url.includes("t.me")) {
    webapp.openTelegramLink(url);
    return;
  }
  webapp?.openLink ? webapp.openLink(url) : window.open(url, "_blank", "noopener,noreferrer");
}
