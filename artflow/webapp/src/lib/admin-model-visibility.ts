const STYLE_ID = "apix-admin-model-visibility";

type TelegramWindow = typeof window & {
  Telegram?: { WebApp?: { initData?: string } };
};

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
html:not([data-apix-admin="true"]) .apix-generation-card-content label:has(select) {
  display: none !important;
}
`;
  document.head.appendChild(style);
}

async function resolveAdminMode(): Promise<void> {
  const initData = ((window as TelegramWindow).Telegram?.WebApp?.initData || "").trim();
  if (!initData) {
    document.documentElement.dataset.apixAdmin = "false";
    return;
  }
  try {
    const response = await fetch("/api/v1/me/permissions", {
      headers: { "X-Telegram-Init-Data": initData },
    });
    if (!response.ok) throw new Error(`permissions ${response.status}`);
    const payload = (await response.json()) as { is_admin?: boolean };
    document.documentElement.dataset.apixAdmin = payload.is_admin ? "true" : "false";
  } catch {
    document.documentElement.dataset.apixAdmin = "false";
  }
}

export function installAdminModelVisibility(): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  installStyle();
  document.documentElement.dataset.apixAdmin = "false";
  window.setTimeout(() => void resolveAdminMode(), 0);
  window.setTimeout(() => void resolveAdminMode(), 1500);
}
