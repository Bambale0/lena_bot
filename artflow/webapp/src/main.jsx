import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_BASE = "/api/v1";
const REALTIME_MAX_FAILURES = 5;
window.__APIX_MINIAPP_BUILD_ID__ = "20260713-miniapp-asset-cache-bust";

// ── fallbacks ────────────────────────────────────────────────────────────────

const fallbackUser = {
  username: null,
  full_name: null,
  photo_url: null,
  credits: 0,
  referral_balance: 0,
  referral_code: "",
  referral_link: "",
  referral_withdraw_min_rub: 1000,
  referral_withdraw_min_credits: 1000,
  language: "ru",
};

const fallbackImageModels = [];

const fallbackVideoModels = [];

const fallbackFeed = [];

const fallbackPlans = [];
const fallbackReferralStats = {
  referral_code: "",
  referral_link: "",
  bonus_l1_credits: 0,
  commission_l1: 0,
  commission_l2: 0,
  commission_l3: 0,
  withdraw_min_rub: 1000,
  withdraw_min_credits: 1000,
  counts: { l1: 0, l2: 0, l3: 0 },
  balance: { total_earned: 0, pending_withdrawals: 0, available_to_withdraw: 0 },
  feed_remix_reward_rub: 0,
  children: { l1: [], l2: [], l3: [] },
  withdrawals: [],
};
const THEME_STORAGE_KEY = "apix-miniapp-theme";
const THEME_OPTIONS = [
  { value: "system", label: "Системная" },
  { value: "dark", label: "Темная" },
  { value: "light", label: "Светлая" },
  { value: "mintpink", label: "Салатово-розовая" },
];

// ── Telegram WebApp helpers ──────────────────────────────────────────────────

function tg() { return window.Telegram?.WebApp || null; }
function tgUser() { return tg()?.initDataUnsafe?.user || null; }
function initData() { return tg()?.initData || ""; }

function telegramFullName(user) {
  return [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim();
}

function readStoredTheme() {
  const value = window.localStorage.getItem(THEME_STORAGE_KEY);
  return THEME_OPTIONS.some((theme) => theme.value === value) ? value : "system";
}

function detectSystemTheme() {
  const telegramTheme = tg()?.colorScheme;
  if (telegramTheme === "light" || telegramTheme === "dark") return telegramTheme;
  return window.matchMedia?.("(prefers-color-scheme: light)")?.matches ? "light" : "dark";
}

function resolveTheme(theme) {
  return theme === "system" ? detectSystemTheme() : theme;
}

function themeLabel(theme) {
  return {
    dark: "темная",
    light: "светлая",
    mintpink: "салатово-розовая",
  }[theme] || "темная";
}

// ── API client ───────────────────────────────────────────────────────────────

async function saveGenerationPrompt(id) {
  return api(`/generations/${id}/share-library`, { method: "POST" });
}

async function photoPromptApi(file) {
  const fd = new FormData();
  fd.append("file", file);

  const res = await fetch(`${API_BASE}/photo-prompt`, {
    method: "POST",
    headers: { "X-Telegram-Init-Data": initData() },
    body: fd,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Photo prompt failed: ${res.status}`);
  }

  const data = await res.json();
  return data.prompt || "";
}

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData(),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = `API ${res.status}`;
    try { const j = await res.json(); detail = j.detail || detail; } catch {}
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return res.json();
}

async function apiForm(path, formData, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    method: options.method || "POST",
    headers: {
      "X-Telegram-Init-Data": initData(),
      ...(options.headers || {}),
    },
    body: formData,
  });
  if (!res.ok) {
    let detail = `API ${res.status}`;
    try { const j = await res.json(); detail = j.detail || detail; } catch {}
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return res.json();
}

function realtimeWsUrl() {
  const data = initData();
  if (!data) return "";
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${API_BASE}/ws/generations`;
}

function realtimeAuthMessage() {
  const data = initData();
  return data ? { type: "auth", init_data: data } : null;
}

function generationFromRealtimeEvent(payload) {
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

function items(x) { return Array.isArray(x) ? x : Array.isArray(x?.items) ? x.items : []; }

function extractPlainText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map(extractPlainText).filter(Boolean).join("\n").trim();
  }
  if (typeof value === "object") {
    if (typeof value.text === "string") return value.text;
    if (typeof value.reply === "string") return value.reply;
    if (typeof value.message === "string") return value.message;
    if (typeof value.content === "string") return value.content;
    if (Array.isArray(value.content)) return extractPlainText(value.content);
    return "";
  }
  return "";
}

function stripAssistantDebugContext(value) {
  let text = extractPlainText(value).trim();
  if (!text) return "";

  text = text
    .replace(/^\s*КОНТЕКСТ\s*/i, "")
    .replace(/^\s*CONTEXT\s*/i, "");

  const debugLine = /^\s*(role|content)\s*:/i;
  const hasDebugShape = text.split(/\n+/).some((line) => debugLine.test(line));
  if (hasDebugShape) {
    const lines = text.split(/\n+/)
      .filter((line) => !debugLine.test(line))
      .filter((line) => !/^\s*\[\s*\{\s*"type"\s*:\s*"input_text"/i.test(line))
      .map((line) => line.trim())
      .filter(Boolean);
    text = lines.join("\n").trim();
  }

  return text || "Готово. Чем ещё помочь?";
}

function formatCredits(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0";
  return String(Number.isInteger(num) ? num : Number(num.toFixed(2))).replace(/\.0+$/, "");
}

const STYLE_EDIT_OPTIONS = [
  {
    value: "clothes",
    label: "Одежду",
    hint: "Например: белый костюм, шелковое платье, oversize худи.",
  },
  {
    value: "haircut",
    label: "Прическу",
    hint: "Например: каре, высокий хвост, мягкие локоны.",
  },
  {
    value: "hair_color",
    label: "Цвет волос",
    hint: "Например: медный блонд, холодный брюнет, пастельно-розовый.",
  },
  {
    value: "nails",
    label: "Ногти",
    hint: "Например: нюдовый маникюр, красный френч, хром.",
  },
];

const STYLE_EDIT_PROMPT_RE = /^Edit the reference image\. Change ONLY .*? to: (.*?)\. Keep /s;

function publicPromptText(value) {
  const text = String(value || "").trim();
  const match = text.match(STYLE_EDIT_PROMPT_RE);
  return match?.[1]?.trim() || text;
}

function styleEditPrompt(editKind, detailValue) {
  const detail = String(detailValue || "").trim();
  if (!editKind || !detail) return detail;
  const templates = {
    clothes: `Edit the reference image. Change ONLY the main person's clothing to: ${detail}. Keep the face, hair, body, pose, background, vehicles, and all other objects unchanged. Do not recolor anything except the clothing.`,
    haircut: `Edit the reference image. Change ONLY the main person's hairstyle or haircut to: ${detail}. Keep the face, hair color, clothing, body, pose, background, vehicles, and all other objects unchanged.`,
    hair_color: `Edit the reference image. Change ONLY the main person's hair color to: ${detail}. Keep the hairstyle, face, skin, clothing, body, pose, background, cars, vehicles, and all other objects unchanged. Do not recolor anything except the hair.`,
    nails: `Edit the reference image. Change ONLY the main person's nails or manicure to: ${detail}. Keep the hands shape, face, hair, clothing, body, pose, background, vehicles, and all other objects unchanged.`,
  };
  return templates[editKind] || detail;
}

async function copyText(value) {
  if (!value) return false;
  try {
    await navigator.clipboard?.writeText(value);
    return true;
  } catch {
    return false;
  }
}

function openExternalUrl(url) {
  if (!url) return;
  let target = String(url).trim();
  try { target = new URL(target, window.location.origin).toString(); } catch {}
  if (tg()) tg().openLink(target);
  else window.open(target, "_blank", "noopener,noreferrer");
}

function isMiniappVideoModelSupported(model) {
  const modes = model?.modes || [];
  return modes.includes("text") || modes.includes("image");
}

function isMidjourneyModel(modelOrKey) {
  const key = String(typeof modelOrKey === "string" ? modelOrKey : modelOrKey?.key || "").toLowerCase();
  return key.startsWith("midjourney-");
}

function modelModesLabel(model) {
  const key = String(model?.key || "").toLowerCase();
  const modes = model?.modes || ["text"];
  if (key === "midjourney-blend") return "2–5 фото";
  if (key === "midjourney-video") return "анимация фото";
  if (modes.includes("text") && modes.includes("image")) return "текст + фото";
  if (modes.includes("image")) return "по фото";
  return "текст";
}

function formatGenerationStatus(status) {
  if (status === "done") return "Готово";
  if (status === "failed") return "Ошибка";
  if (status === "processing") return "В обработке";
  if (status === "pending") return "В очереди";
  return status || "В работе";
}

function generationStatusTone(status) {
  if (status === "done") return "success";
  if (status === "failed") return "danger";
  return "warning";
}

function useApi(loader, fallback, deps = []) {
  const [data, setData] = useState(fallback);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const run = useCallback(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    loader()
      .then(v => { if (alive) { setData(v ?? fallback); setLoading(false); } })
      .catch(e => { if (alive) { setError(e.message); setData(fallback); setLoading(false); } });
    return () => { alive = false; };
  }, deps);

  useEffect(() => run(), [run]);
  return { data, loading, error, reload: run };
}

// ── tiny UI atoms ────────────────────────────────────────────────────────────

function Art({ type = "a" }) {
  return <div className={`art art-${type}`}><span /></div>;
}

function Avatar({ name = "?", photoUrl = null }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [photoUrl]);
  const letter = String(name || "?").slice(0, 1).toUpperCase();
  const showPhoto = Boolean(photoUrl) && !failed;
  return (
    <div className={`avatar ${showPhoto ? "hasPhoto" : ""}`}>
      {showPhoto ? <img src={photoUrl} alt="" onError={() => setFailed(true)} /> : letter}
    </div>
  );
}

function Spinner() {
  return <div className="spinner" />;
}

function NoticeBar({ notice, onClose }) {
  if (!notice?.message) return null;
  return (
    <div className={`noticeBar ${notice.type || "info"}`} role={notice.type === "error" ? "alert" : "status"} aria-live={notice.type === "error" ? "assertive" : "polite"}>
      <span>{notice.message}</span>
      <button onClick={onClose}>×</button>
    </div>
  );
}

function MediaThumb({ url, openUrl = "", type, idx = 0, className = "", onOpen, onError }) {
  const targetUrl = openUrl || url;
  const openable = !!(targetUrl && onOpen && type !== "music");
  const mediaClass = `${className || ""}${openable ? " mediaOpenable" : ""}`.trim() || undefined;
  const openProps = openable ? {
    onClick: (event) => {
      event.stopPropagation();
      onOpen(targetUrl);
    },
    onKeyDown: (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        event.stopPropagation();
        onOpen(targetUrl);
      }
    },
    role: "button",
    tabIndex: 0,
  } : {};

  if (url) {
    if (type === "video" || /\.(mp4|webm|mov)/i.test(url))
      return <video src={url} className={mediaClass} controls playsInline preload="metadata" onError={onError} {...openProps} />;
    if (type === "music" || /\.(mp3|ogg|wav)/i.test(url))
      return <div className={`musicThumb ${className}`}>🎵</div>;
    return <img src={url} className={mediaClass} alt="result" loading="lazy" referrerPolicy="no-referrer" onError={onError} {...openProps} />;
  }
  return <Art type={["a","b","c","d"][idx % 4]} />;
}

function ProfileFeedTile({ item, idx, setScreen }) {
  const [hidden, setHidden] = useState(false);
  const urls = generationPreviewUrls(item);
  if (hidden || !urls.length) return null;
  return (
    <button className="profileFeedTile" onClick={() => setScreen("feed")}>
      <MediaThumb
        url={urls[0]}
        openUrl={item?.result_url || urls[0]}
        type="image"
        idx={idx}
        className="profileFeedMedia"
        onOpen={openExternalUrl}
        onError={() => setHidden(true)}
      />
    </button>
  );
}

function generationResultUrls(generation) {
  const urls = Array.isArray(generation?.result_urls) ? generation.result_urls.filter(Boolean) : [];
  if (!urls.length && generation?.result_url) urls.push(generation.result_url);
  return urls;
}

function generationPreviewUrls(generation) {
  const urls = Array.isArray(generation?.preview_urls) ? generation.preview_urls.filter(Boolean) : [];
  if (!urls.length && generation?.preview_url) urls.push(generation.preview_url);
  return urls.length ? urls : generationResultUrls(generation);
}

function generationPreviewUrl(generation) {
  return generationPreviewUrls(generation)[0] || generation?.preview_url || generation?.result_url || "";
}

function generationPromptHidden(generation) {
  return Boolean(generation?.prompt_hidden) || generation?.prompt_actions_allowed === false;
}

function generationPromptActionsAllowed(generation) {
  return !generationPromptHidden(generation);
}

function generationDisplayPrompt(generation, fallback = "") {
  if (generationPromptHidden(generation)) return "Промпт скрыт";
  return publicPromptText(generation?.prompt || fallback || "");
}

// ── Header ───────────────────────────────────────────────────────────────────

function Header({ screen, setScreen, user, setTopup }) {
  const onBack = () => {
    if (screen === "home") tg()?.close?.();
    else setScreen("home");
  };

  return (
    <div className="header">
      <button onClick={onBack} className="ghost">
        {screen === "home" ? "✕ Закрыть" : "‹ Назад"}
      </button>
      <span className="headerTitle">APIX</span>
      <div className="headerRight">
        <Avatar photoUrl={user.photo_url} name={user.full_name || user.username} />
        <button className="balanceBtn" onClick={() => setTopup(true)}>
          {user.credits} 💋
        </button>
      </div>
    </div>
  );
}

// ── Bottom Nav ───────────────────────────────────────────────────────────────

function Nav({ screen, setScreen }) {
  const tabs = [
    ["home", "⌂", "Главная"],
    ["studio", "⌘", "Студия"],
    ["midjourney", "MJ", "MJ"],
    ["assistant", "?", "AI"],
    ["feed", "◷", "Лента"],
    ["profile", "♙", "Профиль"],
  ];
  return (
    <div className="nav">
      {tabs.map(([id, ic, label]) => (
        <button key={id} onClick={() => setScreen(id)} className={screen === id ? "on" : ""}>
          <b>{ic}</b><small>{label}</small>
        </button>
      ))}
    </div>
  );
}

// ── TopUp modal ──────────────────────────────────────────────────────────────

function TopupModal({ onClose }) {
  const { data: plans, loading, reload: reloadPlans } = useApi(
    () => api(`/plans?_=${Date.now()}`, { cache: "no-store" }),
    fallbackPlans,
  );
  const { data: paymentMethods = [] } = useApi(
    () => api(`/payment-methods?_=${Date.now()}`, { cache: "no-store" }),
    [],
  );
  const [selected, setSelected] = useState(null);
  const [method, setMethod] = useState("tbank");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!paymentMethods.length) return;
    if (!paymentMethods.includes(method)) {
      setMethod(paymentMethods[0]);
    }
  }, [paymentMethods, method]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      reloadPlans();
    }, 15000);

    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        reloadPlans();
      }
    };

    window.addEventListener("focus", reloadPlans);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", reloadPlans);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [reloadPlans]);

  const formatRub = (plan) => {
    if (plan?.price_rub_display) return plan.price_rub_display;
    const value = Number(plan?.price_rub || 0);
    return `${String(value.toFixed(2)).replace(/\.?0+$/, "")}₽`;
  };

  async function handlePay() {
    if (!selected) return;
    setBusy(true); setErr(null);
    try {
      const endpoint = method === "crypto"
        ? "/topup/crypto"
        : method === "stars"
          ? "/topup/stars"
          : method === "lava"
            ? "/topup/lava"
            : "/topup/tbank";
      const res = await api(endpoint, { method: "POST", body: JSON.stringify({ plan_key: selected }) });
      const url = res.invoice_link || res.pay_url;
      if (!url) throw new Error("Платёжная ссылка не получена");
      openExternalUrl(url);
      onClose();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modalOverlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modalHead">
          <h2>Пополнить баланс</h2>
          <button onClick={onClose} className="ghost">✕</button>
        </div>

        {loading ? <Spinner /> : (
          <div className="plans">
            {plans.map(p => (
              <button
                key={p.key}
                className={`planCard ${selected === p.key ? "active" : ""}`}
                onClick={() => setSelected(p.key)}
              >
                <b>{p.title || p.label}</b>
                <span>{p.credits} 💋</span>
                <em>{method === "stars" ? `${p.price_stars} ⭐` : formatRub(p)}</em>
              </button>
            ))}
          </div>
        )}

        <div className="tabs" style={{ marginTop: 16 }}>
          {paymentMethods.includes("tbank") && <button className={method === "tbank" ? "active" : ""} onClick={() => setMethod("tbank")}>💳 Т-Банк</button>}
          {paymentMethods.includes("stars") && <button className={method === "stars" ? "active" : ""} onClick={() => setMethod("stars")}>⭐ Stars</button>}
          {paymentMethods.includes("crypto") && <button className={method === "crypto" ? "active" : ""} onClick={() => setMethod("crypto")}>₮ Крипто</button>}
          {paymentMethods.includes("lava") && <button className={method === "lava" ? "active" : ""} onClick={() => setMethod("lava")}>💸 Lava</button>}
        </div>

        {err && <div className="warn">{err}</div>}

        <button
          disabled={!selected || busy}
          onClick={handlePay}
          className="primary"
          style={{ width: "100%", padding: "14px", borderRadius: 16, marginTop: 12, fontSize: 15 }}
        >
          {busy ? "Загрузка..." : "Оплатить"}
        </button>
      </div>
    </div>
  );
}

// ── Home screen ───────────────────────────────────────────────────────────────

function ProfileStrip({ user, referrals, historyCount, setScreen, setTopup }) {
  return (
    <section className="profileStrip">
      <Avatar photoUrl={user.photo_url} name={user.full_name || user.username} />
      <div className="grow">
        <h2>{user.full_name || user.username || "APIX"}</h2>
        <p>@{user.username || "user"}</p>
      </div>
      <button onClick={() => setScreen("studio")} className="primary small">Создать</button>
      <div className="miniStats">
        <div onClick={() => setTopup(true)} style={{ cursor: "pointer" }}>
          <b>{user.credits}</b><span>💋 токены</span>
        </div>
        <div><b>{historyCount}</b><span>работ</span></div>
        <div><b>{formatRub(user.referral_balance || 0)}</b><span>партнёрский баланс</span></div>
        <div><b>{formatRub(referrals?.exchange_min_rub || 100)}</b><span>мин. обмен</span></div>
        <div onClick={() => setTopup(true)} style={{ cursor: "pointer" }}>
          <b>+</b><span>пополнить</span>
        </div>
      </div>
    </section>
  );
}

function PromptFeed({ prompts, setScreen, onPromptUse, onOpenAll }) {
  return (
    <section className="block">
      <div className="title">
        <div><h2>Библиотека промптов</h2><p>Готовые идеи для старта</p></div>
        <button onClick={() => onOpenAll ? onOpenAll() : setScreen("prompts")}>Все</button>
      </div>
      <div className="hscroll">
        {prompts.map((p, i) => (
          <button key={p.id || i} className="promptCard" onClick={() => onPromptUse ? onPromptUse(p) : setScreen("studio")}>
            {p.preview_url
              ? <img src={p.preview_url} alt={p.title} />
              : <Art type={["a","b","c","d"][i % 4]} />}
            <div>
              <h3>{p.title}</h3>
              <p>{p.description || p.prompt_text}</p>
              <footer>
                <span>{p.model || "Prompt"}</span>
                <b>{p.uses_count || 0} исп</b>
              </footer>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function Home({ user, referrals, feed, prompts, historyCount, setScreen, setTopup, midjourneyItems = [], openStudioPreset, onPromptUse }) {
  return (
    <>
      <ProfileStrip user={user} referrals={referrals} historyCount={historyCount} setScreen={setScreen} setTopup={setTopup} />
      <section className="block">
        <div className="title">
          <div><h2>Возможности APIX</h2><p>Фото, видео, музыка, промпты и партнёрка в одном Mini App</p></div>
          <button onClick={() => setScreen("capabilities")}>Все</button>
        </div>
        <div className="toolGrid compact">
          <button className="toolCard" onClick={() => setScreen("studio")}><b>⌘</b><span>Генерация изображений и видео</span></button>
          <button className="toolCard" onClick={() => setScreen("midjourney")}><b>MJ</b><span>Midjourney модуль</span></button>
          <button className="toolCard" onClick={() => setScreen("music")}><b>♪</b><span>Музыка AI</span></button>
          <button className="toolCard" onClick={() => setScreen("assistant")}><b>AI</b><span>Ассистент по промптам</span></button>
          <button className="toolCard" onClick={() => setScreen("referrals")}><b>₽</b><span>Партнёрский кабинет</span></button>
        </div>
      </section>
      {!!midjourneyItems.length && (
        <section className="block">
          <div className="title">
            <div><h2>Midjourney</h2><p>Цены из текущих моделей</p></div>
            <button onClick={() => setScreen("midjourney")}>Открыть</button>
          </div>
          <div className="grid">
            {midjourneyItems.map((item, i) => (
              <button
                key={item.key || i}
                className="feedCard"
                onClick={() => item.available_in_studio && openStudioPreset ? openStudioPreset(item) : undefined}
                style={{ textAlign: "left", cursor: item.available_in_studio ? "pointer" : "default" }}
              >
                <div>
                  <span>{item.display_name}</span>
                  <p>{item.credits} 💋 · {item.gen_type === "video" ? "video" : "image"}{item.available_in_studio ? " · открыть" : ""}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="block">
        <div className="title">
          <h2>Публичные работы</h2>
          <button onClick={() => setScreen("feed")}>Все</button>
        </div>
        <div className="grid">
          {feed.slice(0, 4).map((f, i) => (
            <button key={f.id || i} className="feedCard" onClick={() => setScreen("feed")}>
              <MediaThumb url={generationPreviewUrl(f)} openUrl={f.result_url || generationPreviewUrl(f)} type="image" idx={i} />
              <div>
                <p>@{f.author || "anon"} · ♥ {f.likes_count || 0} · 🔁 {f.remixes || 0}</p>
              </div>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

// ── Feed screen ───────────────────────────────────────────────────────────────

function FeedCard({ item, idx, onRemix, onNotice, onRemoved }) {
  const [liked, setLiked] = useState(false);
  const [likes, setLikes] = useState(item.likes_count || 0);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const shares = item.shares_count || 0;
  const remixes = item.remixes || 0;
  const resultUrls = generationResultUrls(item);
  const previewUrls = generationPreviewUrls(item);
  const visibleUrls = previewUrls.slice(0, 4);

  async function handleLike() {
    if (liked || busy) return;
    setBusy(true);
    try {
      const res = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLikes(res.likes_count ?? likes + 1);
      setLiked(true);
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось поставить лайк" });
    } finally {
      setBusy(false);
    }
  }

  async function handleCopyLink() {
    try {
      const res = await api(`/feed/${item.id}/link`);
      await navigator.clipboard?.writeText(res.link);
      tg()?.HapticFeedback?.notificationOccurred("success");
      setLinkCopied(true);
      onNotice?.({ type: "success", message: "Ссылка для репоста скопирована" });
      setTimeout(() => setLinkCopied(false), 2000);
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось получить ссылку" });
    }
  }

  async function handleRemove() {
    if (!item.is_mine || removing) return;
    const ok = window.confirm("Удалить этот пост из ленты? Он исчезнет из общей ленты.");
    if (!ok) return;
    setRemoving(true);
    try {
      await api(`/feed/${item.id}/remove`, { method: "POST" });
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Пост удалён из ленты" });
      onRemoved?.(item.id);
    } catch (e) {
      tg()?.HapticFeedback?.notificationOccurred("error");
      onNotice?.({ type: "error", message: e.message || "Не удалось удалить пост" });
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="feedFullCard feedTileCard">
      <div className={`feedTileMedia ${visibleUrls.length > 1 ? "multi" : ""}`}>
        {visibleUrls.length ? visibleUrls.map((url, mediaIdx) => (
          <MediaThumb
            key={`${url}-${mediaIdx}`}
            url={url}
            openUrl={resultUrls[mediaIdx] || url}
            type="image"
            idx={idx + mediaIdx}
            className="feedTileImg"
            onOpen={openExternalUrl}
          />
        )) : <Art type="a" />}
        {resultUrls.length > 4 && <span className="feedMoreBadge">+{resultUrls.length - 4}</span>}
      </div>
      <div className="feedTileInfo">
        <div className="feedTileHead">
          <span className="feedAuthor">@{item.author || "anon"}</span>
        </div>

        <div className="feedTileStats">
          <span>♥ {likes}</span>
          <span>🔁 {remixes}</span>
          <span>📤 {shares}</span>
          {item.is_mine && <span className="mineMark">твой</span>}
        </div>

        <div className="feedActions feedTileActions">
          <button className={`likeBtn ${liked ? "liked" : ""}`} onClick={handleLike} disabled={busy}>
            ♥
          </button>
          <button
            className="remixBtn"
            onClick={() => onRemix && onRemix(item)}
          >
            🔁 Повтор
          </button>
          {item.is_mine && (
            <>
              <button
                className={linkCopied ? "successAction" : ""}
                onClick={handleCopyLink}
              >
                {linkCopied ? "✓" : "🔗"}
              </button>
              <button
                className="dangerAction"
                onClick={handleRemove}
                disabled={removing}
              >
                {removing ? "…" : "🗑"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Feed({ feed, feedLoading, prompts, setScreen, onRemix, onNotice, onRemoved, scope = "all", onPromptUse, onOpenPrompts }) {
  const [mode, setMode] = useState("all");
  const scopedFeed = scope === "midjourney" ? (feed || []).filter((item) => isMidjourneyModel(item.model)) : (feed || []);
  const myCount = scopedFeed.filter(item => item.is_mine).length;
  const filtered = mode === "mine" ? scopedFeed.filter(item => item.is_mine) : scopedFeed;
  const totalLikes = filtered.reduce((sum, item) => sum + (item.likes_count || 0), 0);
  const isMjScope = scope === "midjourney";

  return (
    <>
      <h1>{isMjScope ? "Midjourney лента" : "Лента"}</h1>
      <div style={{ marginBottom: 14, padding: "12px 14px", borderRadius: 14, background: "var(--surface-2)", border: "1px solid var(--border-soft)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 10 }}>
          <div>
            <div style={{ fontWeight: 700 }}>{isMjScope ? "Публичные MJ-работы" : "Публичные работы"}</div>
            <div style={{ fontSize: 12, color: "var(--text-ghost)", marginTop: 4 }}>Смотри чужие работы, повторяй и забирай ссылку на репост для своих.</div>
          </div>
          <button onClick={() => setScreen(isMjScope ? "midjourney" : "studio")} style={{ padding: "8px 12px", borderRadius: 10, border: "1px solid var(--accent-border)", background: "var(--accent-soft)", color: "var(--accent-text)", fontSize: 13, fontWeight: 600 }}>{isMjScope ? "В MJ" : "В студию"}</button>
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <button onClick={() => setMode("all")} style={{ flex: 1, padding: "9px 12px", borderRadius: 12, border: `1px solid ${mode === "all" ? "var(--accent-border)" : "var(--border-strong)"}`, background: mode === "all" ? "var(--accent-soft)" : "var(--surface-1)", color: mode === "all" ? "var(--accent-text)" : "var(--text-muted)", fontWeight: 600 }}>Все ({scopedFeed.length})</button>
          <button onClick={() => setMode("mine")} style={{ flex: 1, padding: "9px 12px", borderRadius: 12, border: `1px solid ${mode === "mine" ? "var(--success-border)" : "var(--border-strong)"}`, background: mode === "mine" ? "var(--success-soft)" : "var(--surface-1)", color: mode === "mine" ? "var(--success)" : "var(--text-muted)", fontWeight: 600 }}>Мои ({myCount})</button>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", fontSize: 12, color: "var(--text-ghost)" }}>
          <span>Карточек: {filtered.length}</span>
          <span>Лайков: {totalLikes}</span>
        </div>
      </div>
      {feedLoading ? <Spinner /> : (
        <div className="feedList">
          {filtered.map((f, i) => <FeedCard key={f.id || i} item={f} idx={i} onRemix={onRemix} onNotice={onNotice} onRemoved={onRemoved} />)}
          {filtered.length === 0 && (
            <div style={{ color: "var(--text-ghost)", textAlign: "center", marginTop: 32, padding: "24px 16px", border: "1px dashed var(--border-strong)", borderRadius: 16 }}>
              {mode === "mine" ? "У тебя пока нет работ в ленте. Опубликуй готовую картинку и забери ссылку для репоста." : "Лента пока пустая."}
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ── Post-generation share buttons ────────────────────────────────────────────

function GenShareButtons({ genId, initialFeed = false, initialLib = false, onNotice }) {
  const [inFeed, setInFeed] = useState(initialFeed);
  const [inLib, setInLib] = useState(initialLib);
  const [busyFeed, setBusyFeed] = useState(false);
  const [busyLib, setBusyLib] = useState(false);

  async function handleFeed() {
    if (inFeed || busyFeed) return;
    setBusyFeed(true);
    try {
      const res = await api(`/generations/${genId}/share`, { method: "POST" });
      setInFeed(true);
      tg()?.HapticFeedback?.notificationOccurred("success");
      const link = res?.link || "";
      if (link) {
        try {
          await navigator.clipboard?.writeText(link);
          onNotice?.({ type: "success", message: `Добавлено в ленту. Ссылка скопирована: ${link}` });
        } catch {
          onNotice?.({ type: "success", message: `Добавлено в ленту. Ссылка: ${link}` });
        }
      } else {
        onNotice?.({ type: "success", message: "Добавлено в ленту" });
      }
    } catch (e) { onNotice?.({ type: "error", message: e.message || "Не удалось опубликовать" }); }
    finally { setBusyFeed(false); }
  }

  async function handleLib() {
    if (busyLib) return;
    setBusyLib(true);
    try {
      const endpoint = inLib ? "remove-library" : "share-library";
      await api(`/generations/${genId}/${endpoint}`, { method: "POST" });
      setInLib(!inLib);
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: inLib ? "Убрано из библиотеки" : "Добавлено в библиотеку" });
    } catch (e) { onNotice?.({ type: "error", message: e.message || "Не удалось изменить библиотеку" }); }
    finally { setBusyLib(false); }
  }

  const btnBase = { flex: 1, padding: "10px 8px", borderRadius: 12, fontSize: 13, fontWeight: 600, cursor: "pointer", transition: "all .2s" };

  return (
    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
      <button
        onClick={handleFeed} disabled={busyFeed || inFeed}
        style={{ ...btnBase, background: inFeed ? "var(--success-soft)" : "var(--surface-2)", border: `1px solid ${inFeed ? "var(--success-border)" : "var(--border-strong)"}`, color: inFeed ? "var(--success)" : "var(--text-muted)" }}
      >
        {inFeed ? "✅ В ленте" : busyFeed ? "..." : "📤 В ленту"}
      </button>
      <button
        onClick={handleLib} disabled={busyLib}
        style={{ ...btnBase, background: inLib ? "var(--accent-soft)" : "var(--surface-2)", border: `1px solid ${inLib ? "var(--accent-border)" : "var(--border-strong)"}`, color: inLib ? "var(--accent-text)" : "var(--text-muted)" }}
      >
        {busyLib ? "..." : inLib ? "Убрать из библиотеки" : "💾 Сохранить промпт"}
      </button>
    </div>
  );
}

function GenerationResultCard({
  generation,
  kind = "image",
  model,
  prompt,
  onNotice,
  onRepeat,
  onRemixImage,
  onStyleImage,
  onAnimateImage,
}) {
  if (!generation?.result_url) return null;
  const mediaType = generation.gen_type || kind;
  const resultUrls = generationResultUrls(generation);
  const isImage = mediaType === "image";
  const isMusic = mediaType === "music";
  const promptHidden = generationPromptHidden(generation);
  const promptActionsAllowed = generationPromptActionsAllowed(generation);
  const displayPrompt = generationDisplayPrompt(generation, prompt);

  return (
    <div className="resultCard">
      {isImage && resultUrls.length > 1 ? (
        <div className="resultGallery">
          {resultUrls.map((url, index) => (
            <MediaThumb key={`${url}-${index}`} url={url} type="image" className="resultGalleryImg" onOpen={openExternalUrl} />
          ))}
        </div>
      ) : isMusic ? (
        <div className="resultMedia audioResult">
          <audio controls src={generation.result_url} />
        </div>
      ) : (
        <div className="resultMedia">
          <MediaThumb url={generation.result_url} type={mediaType} className="resultImg" onOpen={openExternalUrl} />
        </div>
      )}
      <div className="resultInfo">
        <div className="resultMetaRow">
          <span className="modelBadge">{generation.model || model}</span>
          <span className="resultReady">готово</span>
        </div>
        <p className="resultPrompt">{displayPrompt}</p>
        <div className="resultActions">
          {isImage && onRemixImage && (
            <button type="button" className="ghost actionButton" onClick={() => onRemixImage(generation)}>
              ✨ Ремикс
            </button>
          )}
          {onRepeat && (
            <button type="button" className="ghost actionButton" onClick={onRepeat}>
              🔁 Ещё вариант
            </button>
          )}
          {isImage && onStyleImage && (
            <button type="button" className="ghost actionButton wideAction" onClick={() => onStyleImage(generation)}>
              💅 Изменить образ
            </button>
          )}
          {isImage && onAnimateImage && (
            <button type="button" className="ghost actionButton wideAction" onClick={() => onAnimateImage(generation)}>
              🎬 Оживить
            </button>
          )}
          {!promptHidden && displayPrompt && (
            <button type="button" className="ghost actionButton wideAction" onClick={async () => {
              const ok = await copyText(displayPrompt);
              if (ok) onNotice?.({ type: "success", message: "Промпт скопирован" });
            }}>
              📋 Скопировать промпт
            </button>
          )}
          <button type="button" className="ghost actionButton wideAction" onClick={() => openExternalUrl(generation.result_url)}>
            Открыть оригинал
          </button>
        </div>
        {isImage && promptActionsAllowed && (
          <GenShareButtons genId={generation.id} initialFeed={generation.is_public_feed} initialLib={generation.is_prompt_library} onNotice={onNotice} />
        )}
      </div>
    </div>
  );
}

// ── Studio screen ─────────────────────────────────────────────────────────────

function SettingsRow({ label, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".06em" }}>{label}</div>
      {children}
    </div>
  );
}

function ChipGroup({ options, value, onChange }) {
  return (
    <div className="chips">
      {options.map(o => {
        const v = typeof o === "object" ? o.value : o;
        const l = typeof o === "object" ? o.label : o;
        return (
          <button key={v} className={value === v ? "active" : ""} onClick={() => onChange(v)}>{l}</button>
        );
      })}
    </div>
  );
}


function ScenarioCard({ active, icon, title, hint, onClick }) {
  return (
    <button className={`scenarioCard ${active ? "active" : ""}`} onClick={onClick}>
      <b>{icon}</b>
      <span>{title}</span>
      <small>{hint}</small>
    </button>
  );
}

function getImageScenario(model) {
  const key = String(model?.key || "").toLowerCase();
  const modes = model?.modes || ["text"];

  if (key.includes("midjourney-imagine")) return "fast";
  if (key.includes("midjourney-blend")) return "edit";
  if (modes.includes("image")) return "edit";
  if (key.includes("seedream")) return "fast";
  if (key.includes("wan")) return "fast";
  if (key.includes("nano") || key.includes("banana")) return "fast";
  return "fast";
}

function getVideoScenario(model) {
  const key = String(model?.key || "").toLowerCase();
  const modes = model?.modes || ["text"];
  if (key.includes("midjourney-video")) return "i2v";
  if (modes.includes("image")) return "i2v";
  if (key.includes("fast") || key.includes("turbo")) return "fast";
  return "quality";
}

function getScenarioModels(kind, scenario, imageModels, videoModels) {
  const source = kind === "image" ? imageModels : videoModels;
  if (scenario === "all") return source;

  return source.filter((m) => {
    if (kind === "image") return getImageScenario(m) === scenario;
    return getVideoScenario(m) === scenario;
  });
}



function normalizeQualityOptions(model) {
  return (model?.quality_options || []).map((q) => {
    if (typeof q === "object") return q;
    return { value: q, label: q };
  });
}

function normalizeModeOptions(model) {
  const raw = model?.mode_options || [];
  return raw.map((value) => ({ value, label: modeOptionLabel(value) }));
}

function normalizeAbsoluteUrl(value) {
  return typeof value === "string" ? value.trim() : "";
}

function isAbsoluteHttpUrl(value) {
  try {
    const url = new URL(normalizeAbsoluteUrl(value));
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

function isTelegramDeepLink(value) {
  try {
    const url = new URL(normalizeAbsoluteUrl(value));
    return (url.protocol === "https:" || url.protocol === "http:") && url.hostname === "t.me" && url.pathname.length > 1;
  } catch {
    return false;
  }
}

function preferredReferralLink(...candidates) {
  for (const value of candidates) {
    if (isAbsoluteHttpUrl(value)) return normalizeAbsoluteUrl(value);
  }
  return "";
}

function siteReferralFallback(code) {
  const ref = String(code || "").trim();
  return ref ? `https://apixbotai.com/account.html?ref=${encodeURIComponent(ref)}` : "https://apixbotai.com/account.html";
}

function modeOptionLabel(x) {
  return {
    fun: "Fun",
    normal: "Normal",
    spicy: "Spicy",
    low: "🐢 Low",
    high: "🏎 High",
  }[x] || x;
}

function Studio({
  imageModels,
  videoModels,
  user,
  onGenerate,
  onRemixGenerate,
  generation,
  setTopup,
  remixSource,
  clearRemix,
  onNotice,
  preset,
  modelScope = "all",
  title = "Студия",
  subtitle,
}) {
  const isRemix = !!remixSource;
  const scopedImageModels = useMemo(
    () => modelScope === "midjourney" ? (imageModels || []).filter(isMidjourneyModel) : (imageModels || []),
    [imageModels, modelScope],
  );
  const supportedVideoModels = useMemo(
    () => (videoModels || [])
      .filter(isMiniappVideoModelSupported)
      .filter((model) => modelScope === "midjourney" ? isMidjourneyModel(model) : true),
    [videoModels, modelScope],
  );

  const [kind, setKind] = useState(remixSource?.gen_type === "video" ? "video" : "image");
  const [scenario, setScenario] = useState("fast");

  const sourceModels = useMemo(
    () => (kind === "image" ? scopedImageModels : supportedVideoModels),
    [kind, scopedImageModels, supportedVideoModels],
  );
  const scenarioModels = useMemo(
    () => getScenarioModels(kind, scenario, scopedImageModels, supportedVideoModels),
    [kind, scenario, scopedImageModels, supportedVideoModels],
  );
  const visibleModels = scenarioModels.length ? scenarioModels : sourceModels;

  const [model, setModel] = useState(visibleModels[0]?.key || "");
  const current = visibleModels.find((m) => m.key === model) || visibleModels[0] || sourceModels[0];
  const [showAllModels, setShowAllModels] = useState(false);

  const [mode, setMode] = useState("text");
  const [prompt, setPrompt] = useState("");
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [ratio, setRatio] = useState("9:16");
  const [quality, setQuality] = useState("basic");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(5);
  const [resolution, setResolution] = useState("720p");
  const [modeOption, setModeOption] = useState("normal");
  const [refUrls, setRefUrls] = useState([]);
  const [refError, setRefError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [improvingPrompt, setImprovingPrompt] = useState(false);
  const [styleEditOpen, setStyleEditOpen] = useState(false);
  const [styleEditKind, setStyleEditKind] = useState("");
  const fileRef = useRef(null);

  useEffect(() => {
    if (isRemix && remixSource?.gen_type === "image" && kind === "image") {
      setScenario("edit");
      return;
    }
    if (isRemix && remixSource?.gen_type === "video" && kind === "video") {
      setScenario("fast");
      return;
    }
    const allowed = kind === "image" ? ["fast", "edit", "all"] : ["fast", "quality", "i2v", "all"];
    setScenario((prev) => allowed.includes(prev) ? prev : "fast");
  }, [kind, isRemix, remixSource?.gen_type]);

  useEffect(() => {
    if (kind !== "image") {
      setStyleEditOpen(false);
      setStyleEditKind("");
    }
  }, [kind]);

  useEffect(() => {
    if (!remixSource) {
      setRefUrls([]);
      setRefError("");
      return;
    }
    setStyleEditOpen(false);
    setStyleEditKind("");
    setKind(remixSource.gen_type === "video" ? "video" : "image");
    if (remixSource.gen_type === "image") {
      setScenario("edit");
      const nextRefUrl = normalizeAbsoluteUrl(remixSource.result_url || "");
      setRefUrls(nextRefUrl ? [nextRefUrl] : []);
      setRefError(nextRefUrl && !isAbsoluteHttpUrl(nextRefUrl) ? "Для ремикса нужна полная ссылка вида https://..." : "");
      return;
    }
    setScenario("fast");
    setRefUrls([]);
    setRefError("");
  }, [remixSource?.gen_id, remixSource?.gen_type, remixSource?.result_url]);

  useEffect(() => {
    if (!visibleModels.length) {
      if (model) setModel("");
      return;
    }
    const stillVisible = visibleModels.some((item) => item.key === model);
    if (!stillVisible) {
      setModel(visibleModels[0]?.key || "");
    }
  }, [visibleModels, model]);

  useEffect(() => {
    setShowAllModels(false);
  }, [kind, scenario, preset?.modelKey, remixSource?.gen_id]);

  useEffect(() => {
    if (preset?.modelKey) {
      setKind(preset.kind === "video" ? "video" : "image");
      setScenario("all");
    }
  }, [preset?.modelKey, preset?.kind]);

  useEffect(() => {
    if (!preset?.prompt) return;
    setKind("image");
    setPrompt(preset.prompt);
    setSelectedPrompt(preset.promptId ? { id: preset.promptId, title: preset.title || "Промпт" } : null);
    if (preset.modelKey) setScenario("all");
  }, [preset?.prompt, preset?.promptId, preset?.title, preset?.modelKey]);

  useEffect(() => {
    if (preset?.modelKey && visibleModels.some((item) => item.key === preset.modelKey)) {
      setModel(preset.modelKey);
    }
  }, [preset?.modelKey, visibleModels]);

  useEffect(() => {
    if (!current) return;

    const modes = current.modes || ["text"];
    setMode(modes.includes("image") && (scenario === "edit" || scenario === "i2v") ? "image" : modes[0] || "text");

    setRatio((current.aspect_ratios || [])[0] || "9:16");

    const q = normalizeQualityOptions(current)[0];
    setQuality(q?.value || "basic");

    setCount((current.counts || [1])[0] || 1);
    setDuration((current.durations || current.duration_options || [5])[0] || 5);
    setResolution((current.resolutions || ["720p"])[0] || "720p");
    setModeOption((current.mode_options || [])[0] || "normal");
  }, [current?.key, scenario]);

  const remixSourceRefUrls = isRemix
    ? generationResultUrls(remixSource || {})
      .map((url) => normalizeAbsoluteUrl(url))
      .filter(Boolean)
      .slice(0, 4)
    : [];
  const remixSourceRefUrl = remixSourceRefUrls[0] || "";
  const isRemixSourceRef = (url) => remixSourceRefUrls.includes(normalizeAbsoluteUrl(url));

  async function handleFileUpload(e) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    setUploading(true);
    setRefError("");
    try {
      const limit = Math.max(1, Math.min(isRemix ? 4 : Infinity, Number(current?.max_refs || 1) || 1));
      const baseRefs = normalizedRefUrls.filter((url) => !isRemixSourceRef(url));
      const existing = baseRefs.length;
      const sourceSlots = isRemix ? remixSourceRefUrls.length : 0;
      const availableSlots = Math.max(0, limit - sourceSlots - existing);
      const queue = limit <= 1 ? files.slice(0, 1) : files.slice(0, availableSlots);

      if (!queue.length) {
        throw new Error(`У этой модели уже максимум ${limit} референс(ов)`);
      }

      const uploadedUrls = [];
      for (const file of queue) {
        const fd = new FormData();
        fd.append("file", file);

        const res = await fetch("/upload", {
          method: "POST",
          headers: { "X-Telegram-Init-Data": initData() },
          body: fd,
        });

        if (!res.ok) {
          let detail = "Не удалось загрузить файл";
          try {
            const raw = await res.text();
            if (raw) {
              try {
                const parsed = JSON.parse(raw);
                detail = parsed?.detail || parsed?.message || raw || detail;
              } catch {
                detail = raw;
              }
            }
          } catch {}
          if (res.status === 413) {
            detail = "Файл слишком большой. Максимум 20 МБ.";
          }
          throw new Error(detail);
        }
        const data = await res.json();
        const uploadedUrl = normalizeAbsoluteUrl(data.url);
        if (!isAbsoluteHttpUrl(uploadedUrl)) {
          throw new Error("Сервер вернул неполную ссылку на референс");
        }
        uploadedUrls.push(uploadedUrl);
      }

      setRefUrls((prev) => {
        const seen = new Set();
        const base = prev
          .map((url) => normalizeAbsoluteUrl(url))
          .filter((url) => url && !isRemixSourceRef(url));
        const merged = [...base, ...uploadedUrls].filter((url) => {
          const normalized = normalizeAbsoluteUrl(url);
          if (!normalized || seen.has(normalized)) return false;
          seen.add(normalized);
          return true;
        });
        return merged.slice(0, limit);
      });

      if (files.length > queue.length) {
        onNotice?.({ type: "warning", message: `Добавил ${queue.length}. Лимит модели — ${limit} референсов.` });
      }
    } catch (error) {
      setRefError(error?.message || "Не удалось получить полную ссылку на референс");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  const normalizedRefUrls = refUrls
    .map((value) => normalizeAbsoluteUrl(value))
    .filter(Boolean);
  const normalizedRefUrl = normalizedRefUrls[0] || "";
  const maxRefs = Math.max(1, Math.min(isRemix ? 4 : Infinity, Number(current?.max_refs || 1) || 1));
  const hasValidRefUrl = normalizedRefUrls.every((value) => isAbsoluteHttpUrl(value));
  const isPerSecond = Boolean(current?.is_per_second);
  const requiresPrompt = current?.key !== "midjourney-blend";
  const perSec = Number(current?.credits_per_sec || current?.credits || 0);
  const isGeminiOmniVideo = current?.key === "gemini-omni-video";
  const omniResolutionKey = isGeminiOmniVideo
    ? ((resolution === "2160p" || resolution === "2160P") ? "4k" : (resolution || "720p"))
    : resolution;
  const omniHasVideoInput = isGeminiOmniVideo && mode === "video";
  const omniBaseCost = isGeminiOmniVideo
    ? Number(
        omniHasVideoInput
          ? (current?.video_input_prices?.[omniResolutionKey] ?? current?.credits)
          : (current?.price_table?.[omniResolutionKey]?.[duration] ?? current?.credits)
      )
    : Number(current?.credits || 0);
  const baseCost = kind === "image"
    ? Number((current?.quality_prices?.[quality] ?? current?.credits) || 0)
    : omniBaseCost;
  const estimatedCost = kind === "video" && isPerSecond ? duration * perSec : baseCost;

  const modes = current?.modes || ["text"];
  const qualityOptions = normalizeQualityOptions(current).map((option) => {
    const price = Number(current?.quality_prices?.[option.value]);
    if (!Number.isFinite(price) || price <= 0) return option;
    return { ...option, label: `${option.label} · ${formatCredits(price)} 💋` };
  });
  const modeOptions = normalizeModeOptions(current);
  const durations = current?.durations || current?.duration_options || [];
  const resolutions = current?.resolutions || [];
  const counts = current?.counts || [1];
  const ratioModes = Array.isArray(current?.aspect_ratio_modes) && current.aspect_ratio_modes.length
    ? current.aspect_ratio_modes
    : modes;
  const recommendedModels = useMemo(() => {
    if (visibleModels.length <= 4 || scenario === "all") return visibleModels;
    const top = visibleModels.slice(0, 4);
    if (top.some((item) => item.key === model)) return top;
    const selected = visibleModels.find((item) => item.key === model);
    return selected ? [...top.slice(0, 3), selected] : top;
  }, [visibleModels, scenario, model]);
  const displayedModels = showAllModels || scenario === "all" ? visibleModels : recommendedModels;

  const canUseReference = modes.includes("image");
  const requiresReference = mode === "image" && canUseReference;
  const showMode = modes.length > 1;
  const showRatio = (current?.aspect_ratios || []).length > 1 && ratioModes.includes(mode);
  const showQuality = kind === "image" && qualityOptions.length > 1;
  const showCount = kind === "image" && counts.length > 1;
  const showDuration = kind === "video" && durations.length > 0;
  const showResolution = kind === "video" && resolutions.length > 1;
  const showModeOption = kind === "video" && modeOptions.length > 1;
  const styleEditChoice = STYLE_EDIT_OPTIONS.find((option) => option.value === styleEditKind) || null;
  const styleEditReady = !styleEditOpen || Boolean(styleEditKind);
  const stylePromptPlaceholder = styleEditChoice
    ? styleEditChoice.hint
    : styleEditOpen
      ? "Выбери, что меняем в образе, затем напиши детали..."
      : kind === "video"
        ? "Опиши сцену, движение и настроение..."
        : "Опиши идею изображения...";

  async function handleImprovePrompt() {
    if (!prompt.trim() || improvingPrompt) return;
    setImprovingPrompt(true);
    try {
      const result = await api("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt, kind }) });
      setPrompt(result.prompt || prompt);
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: kind === "video" ? "Промпт для видео улучшен" : "Промпт улучшен" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось улучшить промпт" });
    } finally {
      setImprovingPrompt(false);
    }
  }

  function handleGenerate(promptOverride = null) {
    if (!current) return;
    const userProvidedRefUrls = normalizedRefUrls.filter((url) => !isRemixSourceRef(url));

    if (styleEditOpen && !styleEditKind) {
      onNotice?.({ type: "warning", message: "Выбери, что поменять в образе." });
      return;
    }

    if (requiresReference && !userProvidedRefUrls.length && !remixSourceRefUrl) {
      setRefError("Укажи полную ссылку на референс вида https://...");
      return;
    }

    if (!hasValidRefUrl) {
      setRefError("Референс должен быть полной ссылкой и начинаться с http:// или https://");
      return;
    }

    if (user.credits < estimatedCost) {
      setTopup(true);
      return;
    }

    const effectiveRefUrls = mode === "image"
      ? (isRemix
        ? [...remixSourceRefUrls, ...userProvidedRefUrls].slice(0, maxRefs)
        : userProvidedRefUrls.slice(0, maxRefs))
      : [];
    const effectiveRefUrl = effectiveRefUrls[0] || null;

    const basePrompt = typeof promptOverride === "string" ? promptOverride : prompt;
    const promptForGeneration = styleEditKind ? styleEditPrompt(styleEditKind, basePrompt) : basePrompt;
    const payload = {
      model,
      prompt: promptForGeneration,
      prompt_id: kind === "image" && !styleEditKind && promptForGeneration === prompt ? selectedPrompt?.id : null,
      mode,
      aspect_ratio: ratio,
      quality,
      count,
      duration,
      resolution,
      grok_mode: modeOptions.length ? modeOption : undefined,
      image_url: effectiveRefUrl,
      reference_url: effectiveRefUrl,
      reference_urls: effectiveRefUrls.slice(1),
    };

    if (isRemix) onRemixGenerate(remixSource.gen_id, payload);
    else onGenerate(kind, payload);
  }

  function resultImageUrl(item) {
    return generationResultUrls(item)[0] || item?.result_url || "";
  }

  function handleResultRepeat() {
    const promptForRepeat = String(prompt || generation?.prompt || "").trim();
    if (!promptForRepeat || isRemix || generationPromptHidden(generation)) return;
    if (!prompt.trim()) setPrompt(promptForRepeat);
    handleGenerate(promptForRepeat);
  }

  function handleResultRemix(item) {
    const url = resultImageUrl(item);
    if (!url) return;
    clearRemix?.();
    setKind("image");
    setScenario("edit");
    setMode("image");
    setSelectedPrompt(null);
    setStyleEditOpen(false);
    setStyleEditKind("");
    setPrompt("");
    setRefUrls([url]);
    setRefError(isAbsoluteHttpUrl(url) ? "" : "Для ремикса нужна полная ссылка вида https://...");
    onNotice?.({ type: "success", message: "Референс добавлен. Напиши, что изменить." });
  }

  function handleResultStyle(item) {
    const url = resultImageUrl(item);
    if (!url) return;
    clearRemix?.();
    setKind("image");
    setScenario("edit");
    setMode("image");
    setSelectedPrompt(null);
    setStyleEditOpen(true);
    setStyleEditKind("");
    setPrompt("");
    setRefUrls([url]);
    setRefError(isAbsoluteHttpUrl(url) ? "" : "Для изменения образа нужна полная ссылка вида https://...");
    onNotice?.({ type: "success", message: "Выбери, что поменять в образе." });
  }

  function handleResultAnimate(item) {
    const url = resultImageUrl(item);
    if (!url) return;
    clearRemix?.();
    setKind("video");
    setScenario("i2v");
    setMode("image");
    setSelectedPrompt(null);
    setStyleEditOpen(false);
    setStyleEditKind("");
    setPrompt("");
    setRefUrls([url]);
    setRefError(isAbsoluteHttpUrl(url) ? "" : "Для оживления нужна полная ссылка вида https://...");
    onNotice?.({ type: "success", message: "Кадр добавлен для видео. Опиши движение." });
  }

  const scenarios = kind === "image"
    ? [
        ["fast", "⚡", "Быстро", "минимум настроек"],
        ["edit", "🖼", "По фото", "референс / img2img"],
        ["all", "☰", "Все", "ручной выбор"],
      ]
    : [
        ["fast", "⚡", "Быстро", "короткий ролик"],
        ["quality", "🎬", "Кино", "лучшее качество"],
        ["i2v", "🖼", "Фото → видео", "оживить кадр"],
        ["all", "☰", "Все", "ручной выбор"],
      ];

  return (
    <section className="studioClean">
      <div className="studioHead">
        <div>
          <h1>{isRemix ? "🔁 Повтор из ленты" : title}</h1>
          <p>{subtitle || (kind === "image" ? "Создай изображение или ремикс по фото" : "Создай видео или оживи фото")}</p>
        </div>
        <button className="balanceBtn" onClick={() => setTopup(true)}>{user.credits} 💋</button>
      </div>

      {isRemix && (
        <div className="remixNotice">
          <span>Промпт автора скрыт — выбери модель и параметры</span>
          <button onClick={clearRemix}>×</button>
        </div>
      )}

      <SettingsRow label="Что создаём">
        <div className="tabs">
          <button className={kind === "image" ? "active" : ""} onClick={() => setKind("image")} disabled={!scopedImageModels.length}>🖼 Фото</button>
          <button className={kind === "video" ? "active" : ""} onClick={() => setKind("video")} disabled={!supportedVideoModels.length}>🎬 Видео</button>
        </div>
      </SettingsRow>

      <SettingsRow label="Сценарий">
        <div className="scenarioGrid">
          {scenarios.map(([id, icon, title, hint]) => (
            <ScenarioCard
              key={id}
              active={scenario === id}
              icon={icon}
              title={title}
              hint={hint}
              onClick={() => setScenario(id)}
            />
          ))}
        </div>
      </SettingsRow>

      <SettingsRow label="Модель">
        {visibleModels.length > 4 && scenario !== "all" && (
          <div className="modelSectionHead">
            <span>{showAllModels ? `Все модели: ${visibleModels.length}` : `Рекомендуемые: ${displayedModels.length}`}</span>
            <button type="button" className="modelToggleBtn" onClick={() => setShowAllModels((prev) => !prev)}>
              {showAllModels ? "Скрыть лишнее" : "Все модели"}
            </button>
          </div>
        )}
        <div className="modelList">
          {visibleModels.length === 0 && (
            <div className="warn">Нет доступных моделей для этого раздела.</div>
          )}
          {displayedModels.map((m) => {
            const selected = model === m.key;
            const selectedFlatPrice = selected && kind === "video" && m.key === "gemini-omni-video"
              ? estimatedCost
              : (selected ? (m.quality_prices?.[quality] ?? m.credits) : m.credits);
            const modelPrice = m.is_per_second
              ? `${m.credits_per_sec || m.credits} 💋/сек`
              : `${formatCredits(selectedFlatPrice || 0)} 💋`;
            return (
              <button key={m.key} className={selected ? "active" : ""} onClick={() => setModel(m.key)}>
                <i>{kind === "video" ? "🎬" : m.key?.includes("seedream") ? "☁️" : m.key?.includes("wan") ? "🌊" : m.key?.includes("grok") ? "⚡" : "🍌"}</i>
                <span>
                  <b>{m.display_name}</b>
                  <small>{selected ? `${modelModesLabel(m)} · ${modelPrice}` : "Нажми, чтобы выбрать"}</small>
                </span>
              </button>
            );
          })}
        </div>
      </SettingsRow>

      {showMode && (
        <SettingsRow label="Режим">
          <div className="tabs soft">
            {modes.map((m) => (
              <button key={m} className={mode === m ? "active" : ""} onClick={() => setMode(m)}>
                {m === "text" ? "Текст" : m === "image" ? "По фото" : m}
              </button>
            ))}
          </div>
        </SettingsRow>
      )}

      {mode === "image" && canUseReference && (
        <SettingsRow label="Референс">
          <div className="refBlock">
            {normalizedRefUrls.length > 0 && (
              <div className="refGallery">
                {normalizedRefUrls.map((url, index) => (
                  <div key={`${url}-${index}`} className="refPreview">
                    <img src={url} alt={`reference-${index + 1}`} />
                    <button
                      className="refRemove"
                      onClick={() => {
                        setRefUrls((prev) => prev.filter((_, itemIndex) => itemIndex !== index));
                        setRefError("");
                      }}
                    >×</button>
                  </div>
                ))}
              </div>
            )}
            {normalizedRefUrls.length < maxRefs && (
              <button className="refUpload" onClick={() => fileRef.current?.click()} disabled={uploading}>
                {uploading ? "Загрузка..." : normalizedRefUrls.length ? `📎 Добавить ещё (${normalizedRefUrls.length}/${maxRefs})` : "📎 Загрузить фото"}
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/*" multiple={maxRefs > 1} hidden onChange={handleFileUpload} />
            <input
              type="url"
              value={refUrls[0] || ""}
              onChange={(e) => {
                const nextValue = e.target.value;
                setRefUrls((prev) => {
                  const rest = prev.slice(1, maxRefs);
                  return nextValue ? [nextValue, ...rest] : rest;
                });
                if (refError) setRefError("");
              }}
              placeholder="Полная публичная ссылка на изображение"
              spellCheck={false}
              autoCapitalize="none"
              autoCorrect="off"
            />
            <small style={{ color: "var(--text-faint)", lineHeight: 1.4 }}>
              Нужна полная публичная ссылка на изображение. После загрузки она подставится сюда автоматически.
              {maxRefs > 1 ? ` Эта модель принимает до ${maxRefs} референсов.` : ""}
            </small>
            {refError && <div className="warn">{refError}</div>}
          </div>
        </SettingsRow>
      )}

      <div className="settingsGrid">
        {showRatio && (
          <SettingsRow label="Формат">
            <ChipGroup options={current.aspect_ratios} value={ratio} onChange={setRatio} />
          </SettingsRow>
        )}

        {showQuality && (
          <SettingsRow label="Качество">
            <ChipGroup options={qualityOptions} value={quality} onChange={setQuality} />
          </SettingsRow>
        )}

        {showCount && (
          <SettingsRow label="Количество">
            <ChipGroup options={counts} value={count} onChange={setCount} />
          </SettingsRow>
        )}

        {showDuration && (
          <SettingsRow label="Длительность">
            <ChipGroup options={durations.map((d) => ({ value: d, label: `${d} сек` }))} value={duration} onChange={setDuration} />
          </SettingsRow>
        )}

        {showResolution && (
          <SettingsRow label="Разрешение">
            <ChipGroup options={resolutions} value={resolution} onChange={setResolution} />
          </SettingsRow>
        )}

        {showModeOption && (
          <SettingsRow label="Режим модели">
            <ChipGroup options={modeOptions} value={modeOption} onChange={setModeOption} />
          </SettingsRow>
        )}
      </div>

      {kind === "image" && styleEditOpen && (
        <SettingsRow label="Изменить образ">
          <div className="tabs soft">
            {STYLE_EDIT_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={styleEditKind === option.value ? "active" : ""}
                onClick={() => {
                  setStyleEditKind(option.value);
                  setPrompt("");
                  setSelectedPrompt(null);
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </SettingsRow>
      )}

      {!isRemix && (
        <SettingsRow label="Промпт">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={stylePromptPlaceholder}
          />
          {selectedPrompt && (
            <div className="selectedPrompt">
              <span>Из библиотеки: <b>{selectedPrompt.title}</b></span>
              <button type="button" onClick={() => setSelectedPrompt(null)}>×</button>
            </div>
          )}
        </SettingsRow>
      )}

      <button
        className="primary studioGenerate"
        disabled={!current || (!isRemix && requiresPrompt && !prompt.trim()) || (styleEditOpen && !styleEditReady) || (requiresReference && !normalizedRefUrl) || !hasValidRefUrl}
        onClick={handleGenerate}
      >
        {kind === "video" ? "Создать видео" : "Сгенерировать"}
        <span>{formatCredits(estimatedCost || current?.credits || 0)} 💋</span>
      </button>

      {generation && (
        <div className={`status status-${generationStatusTone(generation.status)}`}>
          <div className="statusHead">
            <b>Генерация #{generation.id}</b>
            <span className={`statusBadge ${generationStatusTone(generation.status)}`}>{formatGenerationStatus(generation.status)}</span>
          </div>
          {generation.error && <p>{generation.error}</p>}
          {generation.status === "pending" && (
            <p style={{ color: "var(--text-soft)", fontSize: 12, margin: "8px 0 0" }}>Результат появится здесь автоматически, без поиска в истории.</p>
          )}
        </div>
      )}

      <GenerationResultCard
        generation={generation}
        kind={kind}
        model={model}
        prompt={prompt}
        onNotice={onNotice}
        onRepeat={!isRemix && String(prompt || generation?.prompt || "").trim() && !generationPromptHidden(generation) ? handleResultRepeat : null}
        onRemixImage={handleResultRemix}
        onStyleImage={handleResultStyle}
        onAnimateImage={supportedVideoModels.length ? handleResultAnimate : null}
      />
    </section>
  );
}

// ── Music screen ──────────────────────────────────────────────────────────────

function Music({ user, musicGen, musicModels = [], onGenerateMusic, setTopup, onNotice }) {
  const [prompt, setPrompt] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const [improvingPrompt, setImprovingPrompt] = useState(false);
  const [selectedModelKey, setSelectedModelKey] = useState("");
  const [voices, setVoices] = useState([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [selectedVoiceId, setSelectedVoiceId] = useState("");
  const [trackTitle, setTrackTitle] = useState("");
  const [trackStyle, setTrackStyle] = useState("");
  const [voiceName, setVoiceName] = useState("");
  const [voiceStyle, setVoiceStyle] = useState("");
  const [voiceDescription, setVoiceDescription] = useState("");
  const [verifyTargetId, setVerifyTargetId] = useState(null);
  const sourceVoiceInputRef = useRef(null);
  const verifyVoiceInputRef = useRef(null);

  const availableModels = Array.isArray(musicModels) ? musicModels.filter(Boolean) : [];
  const selectedModel = availableModels.find((item) => item.key === selectedModelKey) || availableModels[0] || null;
  const musicCredits = Number(selectedModel?.credits || 0);
  const musicTitle = selectedModel?.display_name || "Suno";
  const readyVoices = voices.filter((voice) => voice.status === "ready" && voice.provider_voice_id);
  const selectedVoice = voices.find((voice) => String(voice.id) === selectedVoiceId) || null;
  const activeVoiceIds = voices
    .filter((voice) => voice.status === "validating" || voice.status === "generating")
    .map((voice) => voice.id)
    .join(",");

  const genStatus = musicGen?.status;
  const statusColor = genStatus === "done" ? "#4ade80" : genStatus === "failed" ? "#f87171" : "#facc15";
  const promptLimit = selectedVoice ? 5000 : 500;

  async function loadVoices({ quiet = false } = {}) {
    if (!quiet) setVoicesLoading(true);
    try {
      const data = await api("/music/voices");
      setVoices(Array.isArray(data) ? data : []);
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось загрузить голоса" });
    } finally {
      if (!quiet) setVoicesLoading(false);
    }
  }

  async function refreshVoice(id, { quiet = false } = {}) {
    try {
      const updated = await api(`/music/voices/${id}/refresh`, { method: "POST" });
      setVoices((items) => items.map((item) => item.id === updated.id ? updated : item));
      return updated;
    } catch (e) {
      if (!quiet) onNotice?.({ type: "error", message: e.message || "Не удалось обновить голос" });
      return null;
    }
  }

  async function handleImprovePrompt() {
    if (!prompt.trim() || improvingPrompt) return;
    setImprovingPrompt(true);
    try {
      const result = await api("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt, kind: "music" }) });
      setPrompt(result.prompt || prompt);
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Промпт улучшен" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось улучшить промпт" });
    } finally {
      setImprovingPrompt(false);
    }
  }

  useEffect(() => {
    if (!availableModels.length) return;
    if (!selectedModelKey || !availableModels.some((item) => item.key === selectedModelKey)) {
      setSelectedModelKey(availableModels[0].key);
    }
  }, [availableModels, selectedModelKey]);

  useEffect(() => {
    loadVoices({ quiet: true });
  }, []);

  useEffect(() => {
    if (!activeVoiceIds) return undefined;
    const timer = setInterval(() => {
      activeVoiceIds.split(",").filter(Boolean).forEach((id) => refreshVoice(Number(id), { quiet: true }));
    }, 6000);
    return () => clearInterval(timer);
  }, [activeVoiceIds]);

  useEffect(() => {
    if (!selectedVoice) return;
    setInstrumental(false);
    if (!trackStyle.trim() && selectedVoice.style) setTrackStyle(selectedVoice.style);
  }, [selectedVoiceId]);

  async function handleCreateVoiceFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || voiceBusy) return;
    if (!voiceName.trim()) {
      onNotice?.({ type: "error", message: "Назови голос" });
      return;
    }
    setVoiceBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", voiceName.trim());
      if (voiceStyle.trim()) form.append("style", voiceStyle.trim());
      if (voiceDescription.trim()) form.append("description", voiceDescription.trim());
      const created = await apiForm("/music/voices", form);
      setVoices((items) => [created, ...items.filter((item) => item.id !== created.id)]);
      setVoiceName("");
      setVoiceDescription("");
      onNotice?.({ type: "success", message: "Голос загружен" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось загрузить голос" });
    } finally {
      setVoiceBusy(false);
    }
  }

  function requestVoiceVerification(id) {
    setVerifyTargetId(id);
    verifyVoiceInputRef.current?.click();
  }

  async function handleVerifyVoiceFile(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !verifyTargetId || voiceBusy) return;
    setVoiceBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const updated = await apiForm(`/music/voices/${verifyTargetId}/verify`, form);
      setVoices((items) => items.map((item) => item.id === updated.id ? updated : item));
      onNotice?.({ type: "success", message: "Проверочная запись отправлена" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось отправить запись" });
    } finally {
      setVoiceBusy(false);
      setVerifyTargetId(null);
    }
  }

  function handleGenerate() {
    if (!prompt.trim()) return;
    if (musicCredits > 0 && user.credits < musicCredits) { setTopup(true); return; }
    if (selectedVoice) {
      if (!trackTitle.trim()) {
        onNotice?.({ type: "error", message: "Укажи название трека" });
        return;
      }
      if (!trackStyle.trim()) {
        onNotice?.({ type: "error", message: "Укажи стиль трека" });
        return;
      }
    }
    onGenerateMusic({
      prompt,
      instrumental: selectedVoice ? false : instrumental,
      model: selectedModel?.key || undefined,
      voice_record_id: selectedVoice ? selectedVoice.id : undefined,
      title: selectedVoice ? trackTitle.trim() : undefined,
      style: selectedVoice ? trackStyle.trim() : undefined,
    });
  }

  function voiceStatusLabel(status) {
    return {
      validating: "готовится фраза",
      awaiting_verification: "нужна проверка",
      generating: "создаётся",
      ready: "готов",
      failed: "ошибка",
    }[status] || status || "ожидает";
  }

  return (
    <section>
      <div className="studioHead">
        <h1>🎵 Музыка</h1>
        <button className="balanceBtn" onClick={() => setTopup(true)}>{user.credits} 💋</button>
      </div>

      <div style={{ marginBottom: 16, padding: "12px 14px", borderRadius: 14, background: "var(--accent-soft)", border: "1px solid var(--accent-border)", fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
        Генерация песни через {musicTitle}. Описывай жанр, настроение, инструменты и тематику.
        <div style={{ marginTop: 8, fontWeight: 700, color: "var(--text)" }}>Стоимость: {musicCredits || "—"} 💋 за трек.</div>
      </div>

      <input
        ref={sourceVoiceInputRef}
        type="file"
        accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/aac,audio/flac,audio/ogg"
        onChange={handleCreateVoiceFile}
        hidden
      />
      <input
        ref={verifyVoiceInputRef}
        type="file"
        accept="audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/aac,audio/flac,audio/ogg"
        onChange={handleVerifyVoiceFile}
        hidden
      />

      {availableModels.length > 0 && (
        <SettingsRow label="Модель">
          <select value={selectedModelKey} onChange={e => setSelectedModelKey(e.target.value)}>
            {availableModels.map((model) => <option key={model.key} value={model.key}>{model.display_name} · {formatCredits(model.credits)} 💋</option>)}
          </select>
        </SettingsRow>
      )}

      <SettingsRow label="Режим">
        <div className="tabs soft">
          <button className={!instrumental ? "active" : ""} onClick={() => setInstrumental(false)}>🎤 С текстом</button>
          <button className={instrumental ? "active" : ""} onClick={() => setInstrumental(true)} disabled={Boolean(selectedVoice)}>🎸 Инструментал</button>
        </div>
      </SettingsRow>

      <SettingsRow label="Голос">
        <select value={selectedVoiceId} onChange={e => setSelectedVoiceId(e.target.value)}>
          <option value="">Suno вокал</option>
          {readyVoices.map((voice) => <option key={voice.id} value={voice.id}>{voice.name}</option>)}
        </select>
      </SettingsRow>

      {selectedVoice && (
        <div className="voiceGenerationFields">
          <input className="field" value={trackTitle} onChange={e => setTrackTitle(e.target.value)} placeholder="Название трека" maxLength={100} />
          <input className="field" value={trackStyle} onChange={e => setTrackStyle(e.target.value)} placeholder="Стиль: pop, cinematic, female vocal..." maxLength={1000} />
        </div>
      )}

      <div className="voicePanel">
        <div className="voicePanelHead">
          <b>Свой голос</b>
          <button className="ghost" onClick={() => loadVoices()} disabled={voicesLoading || voiceBusy}>{voicesLoading ? "Обновляю..." : "Обновить"}</button>
        </div>
        <div className="voiceCreateGrid">
          <input className="field" value={voiceName} onChange={e => setVoiceName(e.target.value)} placeholder="Название голоса" maxLength={128} />
          <input className="field" value={voiceStyle} onChange={e => setVoiceStyle(e.target.value)} placeholder="Стиль по умолчанию" maxLength={256} />
          <textarea className="field" value={voiceDescription} onChange={e => setVoiceDescription(e.target.value)} placeholder="Описание голоса" maxLength={1000} />
          <button className="refUpload" onClick={() => sourceVoiceInputRef.current?.click()} disabled={voiceBusy || !voiceName.trim()}>
            {voiceBusy ? "Идёт обработка..." : "Загрузить аудио"}
          </button>
        </div>
        <div className="voiceList">
          {voices.length ? voices.map((voice) => (
            <div className={`voiceItem ${voice.status}`} key={voice.id}>
              <div className="voiceItemTop">
                <b>{voice.name}</b>
                <span>{voiceStatusLabel(voice.status)}</span>
              </div>
              {voice.style && <small>{voice.style}</small>}
              {voice.error && <p>{voice.error}</p>}
              {voice.validate_phrase && voice.status === "awaiting_verification" && (
                <code>{voice.validate_phrase}</code>
              )}
              <div className="voiceActions">
                {voice.status === "ready" && (
                  <button className={selectedVoiceId === String(voice.id) ? "active" : ""} onClick={() => setSelectedVoiceId(String(voice.id))}>Выбрать</button>
                )}
                {voice.status === "awaiting_verification" && (
                  <button onClick={() => requestVoiceVerification(voice.id)} disabled={voiceBusy}>Загрузить проверку</button>
                )}
                {(voice.status === "validating" || voice.status === "generating" || voice.status === "failed") && (
                  <button onClick={() => refreshVoice(voice.id)} disabled={voiceBusy}>Обновить статус</button>
                )}
              </div>
            </div>
          )) : (
            <div className="voiceEmpty">Голосов пока нет</div>
          )}
        </div>
      </div>

      <SettingsRow label="Описание трека">
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder={instrumental
            ? "Например: epic orchestral, cinematic, dramatic, Hans Zimmer style..."
            : "Например: upbeat pop song about summer, female vocal, dance vibes..."}
          maxLength={promptLimit}
          style={{ minHeight: 100 }}
        />
      </SettingsRow>

      <div style={{ display: "grid", gap: 10, marginBottom: 10 }}>
        <div style={{ fontSize: 12, color: "var(--text-ghost)" }}>
          💡 Промпт лучше писать на английском. Генерация занимает ~1–2 мин.
        </div>
      </div>

      <button
        disabled={!prompt.trim() || genStatus === "pending"}
        onClick={handleGenerate}
        className="primary"
        style={{ width: "100%", padding: 14, borderRadius: 16, fontSize: 15 }}
      >
        {genStatus === "pending" ? "⏳ Генерирую..." : `🎵 Создать трек · ${musicCredits || 0} 💋`}
      </button>

      {musicGen && (
        <div className="status" style={{ borderColor: `${statusColor}44`, background: `${statusColor}11`, marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <b>Трек #{musicGen.id}</b>
            <span style={{ color: statusColor, fontSize: 13 }}>{musicGen.status}</span>
          </div>
          {musicGen.status === "pending" && (
            <p style={{ color: "var(--text-soft)", fontSize: 12, margin: "8px 0 0" }}>
              Ожидай ~1–2 минуты. Результат придёт в Telegram и появится здесь автоматически.
            </p>
          )}
          {musicGen.result_url && (
            <div style={{ marginTop: 12 }}>
              <audio controls src={musicGen.result_url} style={{ width: "100%", borderRadius: 10 }} />
            </div>
          )}
          {musicGen.error && <p style={{ color: "var(--danger)", margin: "8px 0 0", fontSize: 12 }}>{musicGen.error}</p>}
        </div>
      )}
    </section>
  );
}

// ── History screen ────────────────────────────────────────────────────────────

function History({ history, loading, onNotice, scope = "all", onPromptUse = null }) {
  if (loading) return <Spinner />;
  const visibleHistory = scope === "midjourney" ? (history || []).filter((item) => isMidjourneyModel(item.model)) : (history || []);
  const isMjScope = scope === "midjourney";
  return (
    <>
      <h1>{isMjScope ? "История Midjourney" : "История"}</h1>
      {visibleHistory.length === 0
        ? <p style={{ color: "var(--text-ghost)", textAlign: "center", marginTop: 40 }}>{isMjScope ? "Midjourney-генераций пока нет." : "Генераций пока нет. Создайте первую в Студии!"}</p>
        : <div className="historyList">
            {visibleHistory.map((g, i) => {
              const resultUrls = generationResultUrls(g);
              const promptHidden = generationPromptHidden(g);
              const promptActionsAllowed = generationPromptActionsAllowed(g);
              const displayPrompt = generationDisplayPrompt(g);
              return (
              <div key={g.id} className="historyCard">
                <div className="historyMediaWrap">
                  {g.gen_type === "image" && resultUrls.length > 1 ? (
                    <div className="historyResultGallery">
                      {generationPreviewUrls(g).map((url, index) => (
                        <MediaThumb key={`${url}-${index}`} url={url} openUrl={resultUrls[index] || url} type="image" idx={index} className="historyGalleryImg" onOpen={openExternalUrl} />
                      ))}
                    </div>
                  ) : (
                    <button type="button" className="historyMedia historyMediaBtn" onClick={() => g.result_url && openExternalUrl(g.result_url)} disabled={!g.result_url}>
                      <MediaThumb url={generationPreviewUrl(g)} openUrl={g.result_url || generationPreviewUrl(g)} type={g.gen_type} idx={i} className="historyImg" />
                    </button>
                  )}
                </div>
                <div className="historyInfo">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                    <span className="modelBadge">{g.model}</span>
                    <span style={{ fontSize: 11, color: getStatusColor(g.status) }}>{formatGenerationStatus(g.status)}</span>
                  </div>
                  <p className="feedPrompt">{displayPrompt}</p>
                  {g.gen_type === "music" && g.result_url && (
                    <audio controls src={g.result_url} style={{ width: "100%", borderRadius: 8, marginTop: 6 }} />
                  )}
                  <div className="historyActionRow">
                    {!promptHidden && g.prompt && onPromptUse && (
                      <button type="button" className="ghost" onClick={() => onPromptUse({
                        title: "Повтор из истории",
                        prompt: g.prompt || "",
                        prompt_text: g.prompt || "",
                        model: g.model || undefined,
                      })}>🔁 Повторить</button>
                    )}
                    <button type="button" className="ghost" onClick={() => g.result_url && openExternalUrl(g.result_url)} disabled={!g.result_url}>👁 Открыть</button>
                    {!promptHidden && g.prompt && (
                      <button type="button" className="ghost" onClick={async () => {
                        const ok = await copyText(g.prompt || "");
                        if (ok) onNotice?.({ type: "success", message: "Промпт скопирован" });
                      }}>📋 Промпт</button>
                    )}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
                    <small style={{ color: "var(--text-ghost)", fontSize: 11 }}>{formatDate(g.created_at)}</small>
                    <small style={{ color: "var(--accent-text)", fontSize: 11 }}>−{formatCredits(g.credits_spent)} 💋</small>
                  </div>
                  {g.status === "done" && g.gen_type === "image" && promptActionsAllowed && (
                    <GenShareButtons genId={g.id} initialFeed={g.is_public_feed} initialLib={g.is_prompt_library} onNotice={onNotice} />
                  )}
                </div>
              </div>
              );
            })}
          </div>
      }
    </>
  );
}

function MidjourneyModule({
  imageModels,
  videoModels,
  user,
  generation,
  prompts,
  feed,
  history,
  setScreen,
  setTopup,
  onGenerate,
  onRemixGenerate,
  remixSource,
  clearRemix,
  onNotice,
  preset,
  onPromptUse,
  onOpenPrompts,
  onOpenFeed,
  onOpenHistory,
}) {
  const mjHistory = (history || []).filter((item) => isMidjourneyModel(item.model));
  const mjFeed = (feed || []).filter((item) => isMidjourneyModel(item.model)).slice(0, 3);
  const mjPrompts = (prompts || []).slice(0, 4);

  return (
    <>
      <section className="mjModuleHero">
        <div>
          <h1>Midjourney</h1>
          <p>Отдельный модуль с тем же балансом, историей, лентой, библиотекой промптов и референсами.</p>
        </div>
        <button className="balanceBtn" onClick={() => setTopup(true)}>{user.credits} 💋</button>
      </section>

      <section className="block">
        <div className="mjQuickGrid">
          <button onClick={onOpenPrompts}><b>📚</b><span>Библиотека промптов</span></button>
          <button onClick={onOpenFeed}><b>◷</b><span>Лента и ремиксы</span></button>
          <button onClick={onOpenHistory}><b>☰</b><span>История MJ: {mjHistory.length}</span></button>
          <button onClick={() => setTopup(true)}><b>💋</b><span>Баланс и оплата</span></button>
        </div>
      </section>

      <Studio
        imageModels={imageModels}
        videoModels={videoModels}
        user={user}
        onGenerate={onGenerate}
        onRemixGenerate={onRemixGenerate}
        generation={generation}
        setTopup={setTopup}
        remixSource={remixSource}
        clearRemix={clearRemix}
        onNotice={onNotice}
        preset={preset}
        modelScope="midjourney"
        title="Midjourney Studio"
        subtitle="Imagine, Blend, референсы, форматы, видео по фото и промпты из общей библиотеки."
      />

      {!!mjFeed.length && (
        <section className="block">
          <div className="title">
            <div><h2>MJ в ленте</h2><p>Публичные работы можно ремиксовать и шарить</p></div>
            <button onClick={onOpenFeed}>Все</button>
          </div>
          <div className="grid">
            {mjFeed.map((item, index) => (
              <button key={item.id || index} className="feedCard" onClick={onOpenFeed}>
                <MediaThumb url={item.result_url} type={item.gen_type || "image"} idx={index} className="feedImg" />
                <div>
                  <span>{item.model}</span>
                  <p>{item.likes_count || 0} лайков · {item.shares_count || 0} шеров</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function getStatusColor(s) {
  if (s === "done") return "#4ade80";
  if (s === "failed") return "#f87171";
  return "#facc15";
}

function formatDate(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

// ── All capabilities ─────────────────────────────────────────────────────────

function Capabilities({ setScreen, setTopup }) {
  const tools = [
    ["studio", "⌘", "Студия генераций", "Изображения, редактирование по референсам, blend, text-to-video и image-to-video."],
    ["midjourney", "MJ", "Midjourney", "Отдельный MJ-модуль с общей историей, лентой, библиотекой промптов, оплатой и референсами."],
    ["music", "♪", "Музыка AI", "Песни с вокалом или инструментальные треки по описанию настроения и жанра."],
    ["assistant", "AI", "AI-ассистент", "Помогает улучшить промпт, выбрать модель, разобраться с референсами и оплатой."],
    ["prompts", "📚", "Библиотека промптов", "Готовые идеи и формулы, которые можно быстро адаптировать под свою задачу."],
    ["feed", "◷", "Публичная лента", "Публикуй удачные работы, собирай лайки, делись ссылками и запускай ремиксы."],
    ["history", "☰", "История", "Все твои генерации, статусы, результаты, промпты и быстрые действия в одном месте."],
    ["referrals", "₽", "Партнёрка", "Реферальная ссылка, уровни, баланс, заявки на вывод и доход от ремиксов."],
    ["help", "?", "Помощь", "Инструкции из Telegram-бота, подсказки по Stars, оплате, рефералам и промптам."],
    ["profile", "♙", "Профиль и настройки", "Баланс, темы интерфейса, язык и основные пользовательские параметры."],
    ...(window.__APIX_IS_ADMIN__ ? [["admin", "🛡", "Owner cockpit", "Обзор метрик, юзеры, выводы и быстрые owner-операции."]] : []),
  ];

  return (
    <section>
      <div className="studioHead">
        <h1>Все возможности</h1>
        <button className="balanceBtn" onClick={() => setTopup(true)}>Пополнить</button>
      </div>
      <div className="capabilityHero">
        <b>APIX Web работает с той же базой, что и Telegram-бот.</b>
        <p>Запускай генерации из Mini App, возвращайся к ним в боте и наоборот: баланс, история, лента, промпты и партнёрка общие.</p>
      </div>
      <div className="toolGrid">
        {tools.map(([id, icon, title, text]) => (
          <button key={id} className="toolCard big" onClick={() => setScreen(id)}>
            <b>{icon}</b>
            <strong>{title}</strong>
            <span>{text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

// ── Assistant screen ─────────────────────────────────────────────────────────

function Assistant({ onNotice }) {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Привет! Я помогу собрать промпт, выбрать модель или объяснить, как лучше сделать изображение, видео или трек в APIX." },
  ]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    const message = text.trim();
    if (!message || busy) return;
    const nextMessages = [...messages, { role: "user", content: message }];
    setMessages(nextMessages);
    setText("");
    setBusy(true);
    try {
      const history = messages.slice(-10).map(({ role, content }) => ({ role, content: stripAssistantDebugContext(content) }));
      const res = await api("/assistant", { method: "POST", body: JSON.stringify({ message, history }) });
      setMessages((prev) => [...prev, { role: "assistant", content: stripAssistantDebugContext(res.reply || res) }]);
      tg()?.HapticFeedback?.notificationOccurred("success");
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Ассистент сейчас недоступен" });
      setMessages((prev) => [...prev, { role: "assistant", content: "Не смог получить ответ. Попробуй ещё раз через минуту или сформулируй короче." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="studioHead">
        <h1>AI-ассистент</h1>
        <span className="statusBadge success">web + bot</span>
      </div>
      <div className="assistantPanel">
        <div className="assistantMessages">
          {messages.map((m, i) => (
            <div key={`${m.role}-${i}`} className={`assistantBubble ${m.role}`}>
              {stripAssistantDebugContext(m.content)}
            </div>
          ))}
          {busy && <div className="assistantBubble assistant">Думаю над ответом...</div>}
        </div>
        <div className="assistantQuick">
          {["Улучши промпт для фэшн-съёмки", "Какая модель подойдёт для анимации фото?", "Как заработать на рефералах?"].map((q) => (
            <button key={q} onClick={() => setText(q)}>{q}</button>
          ))}
        </div>
        <div className="assistantInput">
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Спроси про промпт, модель, оплату, историю или ленту..." maxLength={4000} />
          <button className="primary" onClick={send} disabled={!text.trim() || busy}>{busy ? "..." : "Отправить"}</button>
        </div>
      </div>
    </section>
  );
}

// ── Referrals screen ─────────────────────────────────────────────────────────

function formatRub(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return "0₽";
  return `${num.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}₽`;
}

function pct(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function Referrals({ user, stats, loading, reload, onNotice }) {
  const referralCode = user.referral_code || stats.referral_code || "";
  const referralLink = preferredReferralLink(
    stats.referral_link,
    user.referral_link,
    siteReferralFallback(referralCode),
  );
  const available = Number(stats.balance?.available_to_withdraw || 0);
  const withdrawMinAmount = Number(stats.withdraw_min_rub || user.referral_withdraw_min_rub || 1000);
  const exchangeMinAmount = Number(stats.exchange_min_rub || 100);
  const rubPerCredit = Number(stats.exchange_rate_rub_per_credit || 10);
  const [exchangeAmount, setExchangeAmount] = useState("");
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawDetails, setWithdrawDetails] = useState("");
  const [busyAction, setBusyAction] = useState("");

  async function copyReferral() {
    const ok = await copyText(referralLink);
    onNotice?.({ type: ok ? "success" : "error", message: ok ? "Партнёрская ссылка скопирована" : "Не удалось скопировать ссылку" });
  }

  async function exchange() {
    if (busyAction) return;
    setBusyAction("exchange");
    try {
      await api("/referrals/exchange", {
        method: "POST",
        body: JSON.stringify({ amount_rub: Number(exchangeAmount) }),
      });
      setExchangeAmount("");
      reload?.();
      onNotice?.({ type: "success", message: "Готово: 💋 начислены на баланс" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось обменять баланс" });
    } finally {
      setBusyAction("");
    }
  }

  async function requestWithdrawal() {
    if (busyAction) return;
    setBusyAction("withdraw");
    try {
      await api("/referrals/withdrawals", {
        method: "POST",
        body: JSON.stringify({ amount_rub: Number(withdrawAmount), payout_details: withdrawDetails }),
      });
      setWithdrawAmount("");
      setWithdrawDetails("");
      reload?.();
      onNotice?.({ type: "success", message: "Заявка на вывод создана" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось создать заявку" });
    } finally {
      setBusyAction("");
    }
  }

  if (loading) return <Spinner />;

  return (
    <section>
      <div className="studioHead">
        <h1>Партнёрка</h1>
        <button className="balanceBtn" onClick={copyReferral}>Скопировать</button>
      </div>
      <div className="referralLinkBox" onClick={copyReferral}>
        <span>Твоя ссылка</span>
        <b>{referralLink}</b>
      </div>
      <div className="profileStats referralStats">
        <div><b>{stats.counts?.l1 || 0}</b><span>1 уровень · +{formatCredits(stats.bonus_l1_credits)} 💋</span></div>
        <div><b>{stats.counts?.l2 || 0}</b><span>2 уровень · {pct(stats.commission_l2)}</span></div>
        <div><b>{stats.counts?.l3 || 0}</b><span>3 уровень · {pct(stats.commission_l3)}</span></div>
      </div>
      <div className="moneyGrid">
        <div><span>Всего заработано</span><b>{formatRub(stats.balance?.total_earned)}</b></div>
        <div><span>Доступно</span><b>{formatRub(available)}</b></div>
        <div><span>В ожидании</span><b>{formatRub(stats.balance?.pending_withdrawals)}</b></div>
        <div><span>Ремиксы ленты</span><b>{formatRub(stats.feed_remix_reward_rub)}</b></div>
      </div>

      <section className="block referralPanel">
        <div className="title"><div><h2>Партнёрский баланс</h2><p>Курс покупки: 100₽ = {formatCredits(100 / rubPerCredit)} 💋.</p></div></div>
        <div className="referralActions">
          <article className="referralActionBox">
            <h3>Купить 💋</h3>
            <p>Списать рубли с партнёрского баланса и сразу начислить поцелуи.</p>
            <input className="field" inputMode="decimal" value={exchangeAmount} onChange={(e) => setExchangeAmount(e.target.value)} placeholder={`Сумма, например ${exchangeMinAmount}`} />
            <button className="primary referralActionButton" onClick={exchange} disabled={Boolean(busyAction) || Number(exchangeAmount) < exchangeMinAmount || available < Number(exchangeAmount)}>
              {busyAction === "exchange" ? "Обмен..." : "Купить поцелуи"}
            </button>
          </article>
          <article className="referralActionBox">
            <h3>Вывести деньги</h3>
            <p>Создать заявку на выплату администратору.</p>
            <input className="field" inputMode="decimal" value={withdrawAmount} onChange={(e) => setWithdrawAmount(e.target.value)} placeholder={`Сумма от ${withdrawMinAmount}`} />
            <input className="field" value={withdrawDetails} onChange={(e) => setWithdrawDetails(e.target.value)} placeholder="Реквизиты: банк, телефон, карта" />
            <button className="secondaryBtn referralActionButton" onClick={requestWithdrawal} disabled={Boolean(busyAction) || Number(withdrawAmount) < withdrawMinAmount || available < Number(withdrawAmount) || withdrawDetails.trim().length < 5}>
              {busyAction === "withdraw" ? "Отправляем..." : "Вывести деньги"}
            </button>
          </article>
        </div>
      </section>

      <section className="block">
        <div className="title"><div><h2>Последние операции</h2><p>История синхронизируется с ботом</p></div></div>
        <div className="miniList">
          {(stats.withdrawals || []).length
            ? stats.withdrawals.map((item) => {
              const isExchange = item.payout_details === "AUTO_CREDITS";
              const label = isExchange
                ? `${formatRub(item.amount_rub)} → ${formatCredits(item.amount_credits || (Number(item.amount_rub || 0) / rubPerCredit))} 💋`
                : formatRub(item.amount_rub);
              return <div key={item.id}><b>{label}</b><span>{item.status} · {formatDate(item.created_at)}</span></div>;
            })
            : <div><b>Операций пока нет</b><span>Баланс можно вывести деньгами или обменять на 💋.</span></div>}
        </div>
      </section>
    </section>
  );
}

function adminDate(value) {
  return formatDate(value);
}

function AdminMetric({ label, value, hint }) {
  return (
    <div className="toolCard">
      <strong>{value}</strong>
      <span>{label}</span>
      {hint ? <small style={{ opacity: 0.7 }}>{hint}</small> : null}
    </div>
  );
}

function AdminBars({ title, items, kind = "count" }) {
  const max = Math.max(1, ...((items || []).map((item) => Number(item.value || 0))));
  return (
    <section>
      <div className="studioHead">
        <h1 style={{ fontSize: 18 }}>{title}</h1>
      </div>
      <div className="assistantPanel" style={{ gap: 10 }}>
        {(items || []).map((item) => {
          const value = Number(item.value || 0);
          const width = `${Math.max(6, Math.round((value / max) * 100))}%`;
          return (
            <div key={`${title}-${item.date}`} style={{ display: "grid", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 12, opacity: 0.82 }}>
                <span>{item.date}</span>
                <b>{kind === "money" ? formatRub(value) : Math.round(value * 10) / 10}</b>
              </div>
              <div style={{ height: 8, borderRadius: 999, background: "rgba(255,255,255,.08)", overflow: "hidden" }}>
                <div style={{ width, height: "100%", borderRadius: 999, background: "linear-gradient(90deg,#ff4d6d,#7c3aed)" }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AdminDashboard({ user, onNotice }) {
  const [tab, setTab] = useState("overview");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [withdrawalStatus, setWithdrawalStatus] = useState("pending");

  const overview = useApi(
    () => user.is_admin ? api("/admin/overview") : Promise.resolve({ summary: {}, charts: {}, top_models: [], providers: [] }),
    { summary: {}, charts: {}, top_models: [], providers: [] },
    [user.is_admin],
  );
  const users = useApi(
    () => user.is_admin ? api(`/admin/users?query=${encodeURIComponent(search)}`) : Promise.resolve({ items: [] }),
    { items: [] },
    [user.is_admin, search],
  );
  const selectedUser = useApi(
    () => user.is_admin && selectedUserId ? api(`/admin/users/${selectedUserId}`) : Promise.resolve(null),
    null,
    [user.is_admin, selectedUserId],
  );
  const withdrawals = useApi(
    () => user.is_admin ? api(`/admin/withdrawals?status=${encodeURIComponent(withdrawalStatus)}`) : Promise.resolve({ items: [] }),
    { items: [] },
    [user.is_admin, withdrawalStatus],
  );

  useEffect(() => {
    if (!selectedUserId && users.data?.items?.length) setSelectedUserId(users.data.items[0].id);
  }, [users.data, selectedUserId]);

  if (!user.is_admin) {
    return (
      <section>
        <div className="warn">Админ-раздел доступен только owner/admin аккаунтам.</div>
      </section>
    );
  }

  async function applyCredits(sign = 1) {
    if (!selectedUserId) return;
    const raw = window.prompt(sign > 0 ? "Сколько кредитов добавить?" : "Сколько кредитов списать?");
    if (!raw) return;
    const amount = Number(raw);
    if (!Number.isFinite(amount) || amount <= 0) {
      onNotice?.({ type: "error", message: "Нужна корректная сумма" });
      return;
    }
    const note = window.prompt("Комментарий для истории", sign > 0 ? "Owner topup" : "Owner deduction") || undefined;
    try {
      await api(`/admin/users/${selectedUserId}/credits`, {
        method: "POST",
        body: JSON.stringify({ amount: amount * sign, note }),
      });
      onNotice?.({ type: "success", message: sign > 0 ? "Кредиты начислены" : "Кредиты списаны" });
      users.reload();
      selectedUser.reload();
      overview.reload();
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось обновить баланс" });
    }
  }

  async function toggleBan() {
    if (!selectedUserId || !selectedUser.data?.user) return;
    const next = !selectedUser.data.user.is_banned;
    try {
      await api(`/admin/users/${selectedUserId}/ban`, { method: "POST", body: JSON.stringify({ banned: next }) });
      onNotice?.({ type: "success", message: next ? "Пользователь заблокирован" : "Пользователь разблокирован" });
      users.reload();
      selectedUser.reload();
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось изменить бан" });
    }
  }

  async function reviewWithdrawal(item, action) {
    const note = window.prompt(action === "approve" ? "Комментарий к выплате" : "Причина отклонения", item.admin_note || "") || undefined;
    try {
      await api(`/admin/withdrawals/${item.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, note }),
      });
      onNotice?.({ type: "success", message: action === "approve" ? "Заявка подтверждена" : "Заявка отклонена" });
      withdrawals.reload();
      overview.reload();
      if (selectedUserId === item.user?.id) selectedUser.reload();
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось обработать заявку" });
    }
  }

  const summary = overview.data?.summary || {};
  const currentUser = selectedUser.data?.user;
  const currentStats = selectedUser.data?.stats || {};

  return (
    <section>
      <div className="studioHead">
        <h1>Owner cockpit</h1>
        <span className="statusBadge success">MVP</span>
      </div>
      <div className="tabs soft">
        {[
          ["overview", "Обзор"],
          ["users", "Пользователи"],
          ["withdrawals", "Выводы"],
        ].map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          {overview.loading ? <Spinner /> : (
            <>
              <div className="toolGrid">
                <AdminMetric label="Юзеры всего" value={summary.users_total || 0} hint={`+${summary.users_new_7d || 0} за 7д`} />
                <AdminMetric label="Платящие" value={summary.paid_users || 0} hint={`${summary.success_rate_7d || 0}% success`} />
                <AdminMetric label="Выручка" value={formatRub(summary.revenue_total || 0)} hint={`${formatRub(summary.revenue_7d || 0)} за 7д`} />
                <AdminMetric label="Генерации" value={summary.generations_total || 0} hint={`${summary.generations_7d || 0} за 7д`} />
                <AdminMetric label="Выводы ждут" value={summary.pending_withdrawals_count || 0} hint={formatRub(summary.pending_withdrawals_amount || 0)} />
                <AdminMetric label="Промпты на модерации" value={summary.pending_prompts || 0} hint={`img ${summary.image_7d || 0} · vid ${summary.video_7d || 0} · music ${summary.music_7d || 0}`} />
              </div>
              <AdminBars title="Новые пользователи" items={overview.data?.charts?.users || []} />
              <AdminBars title="Выручка" items={overview.data?.charts?.revenue || []} kind="money" />
              <AdminBars title="Генерации" items={overview.data?.charts?.generations || []} />
              <section>
                <div className="studioHead"><h1 style={{ fontSize: 18 }}>Топ моделей за 7 дней</h1></div>
                <div className="assistantPanel">
                  {(overview.data?.top_models || []).length ? overview.data.top_models.map((item) => (
                    <div key={item.model} className="feedCard" style={{ cursor: "default" }}>
                      <div>
                        <b>{item.model}</b>
                        <p>{item.count} запусков</p>
                      </div>
                    </div>
                  )) : <div className="warn">Пока нет данных.</div>}
                </div>
              </section>
              <section>
                <div className="studioHead"><h1 style={{ fontSize: 18 }}>Платёжные провайдеры за 30 дней</h1></div>
                <div className="assistantPanel">
                  {(overview.data?.providers || []).length ? overview.data.providers.map((item) => (
                    <div key={item.provider} className="feedCard" style={{ cursor: "default" }}>
                      <div>
                        <b>{item.provider}</b>
                        <p>{item.count} платежей · {formatRub(item.revenue || 0)}</p>
                      </div>
                    </div>
                  )) : <div className="warn">Пока нет платежей.</div>}
                </div>
              </section>
            </>
          )}
        </>
      )}

      {tab === "users" && (
        <div className="toolGrid" style={{ alignItems: "start" }}>
          <section className="assistantPanel" style={{ gridColumn: "span 1" }}>
            <div className="assistantInput">
              <input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder="Поиск: id, tg_id, @username, имя" />
              <button className="primary" onClick={() => setSearch(searchInput.trim())}>Найти</button>
            </div>
            {users.loading ? <Spinner /> : (users.data?.items || []).map((item) => (
              <button key={item.id} className={`feedCard ${selectedUserId === item.id ? "active" : ""}`} onClick={() => setSelectedUserId(item.id)} style={{ textAlign: "left" }}>
                <div>
                  <b>{item.full_name || item.username || `User #${item.id}`}</b>
                  <p>ID {item.id} · tg {item.tg_id}</p>
                  <p>{formatCredits(item.credits)} кр · {formatRub(item.paid_rub || 0)} · {item.generations_count || 0} ген.</p>
                </div>
                {item.is_banned ? <span className="statusBadge danger">ban</span> : null}
              </button>
            ))}
          </section>

          <section className="assistantPanel" style={{ gridColumn: "span 1" }}>
            {selectedUser.loading ? <Spinner /> : !currentUser ? <div className="warn">Выбери пользователя слева.</div> : (
              <>
                <div className="studioHead">
                  <h1 style={{ fontSize: 18 }}>{currentUser.full_name || currentUser.username || `User #${currentUser.id}`}</h1>
                  {currentUser.is_banned ? <span className="statusBadge danger">banned</span> : <span className="statusBadge success">active</span>}
                </div>
                <div className="toolGrid">
                  <AdminMetric label="Кредиты" value={formatCredits(currentUser.credits)} />
                  <AdminMetric label="Реф. баланс" value={formatRub(currentUser.referral_balance || 0)} />
                  <AdminMetric label="Платежи" value={currentStats.payments_count || 0} hint={formatRub(currentStats.paid_rub || 0)} />
                  <AdminMetric label="Рефералы" value={(currentStats.referrals?.l1 || 0) + (currentStats.referrals?.l2 || 0) + (currentStats.referrals?.l3 || 0)} hint={`L1 ${currentStats.referrals?.l1 || 0} · L2 ${currentStats.referrals?.l2 || 0} · L3 ${currentStats.referrals?.l3 || 0}`} />
                </div>
                <div className="assistantQuick">
                  <button onClick={() => applyCredits(1)}>+ кредиты</button>
                  <button onClick={() => applyCredits(-1)}>- кредиты</button>
                  <button onClick={toggleBan}>{currentUser.is_banned ? "Разбанить" : "Забанить"}</button>
                </div>
                <div className="assistantPanel" style={{ gap: 8 }}>
                  <b>Последние платежи</b>
                  {(selectedUser.data?.transactions || []).slice(0, 6).map((item) => (
                    <div key={`tx-${item.id}`} className="feedCard" style={{ cursor: "default" }}>
                      <div>
                        <b>{item.provider} · {item.status}</b>
                        <p>{formatRub(item.amount_rub || 0)} · {formatCredits(item.credits || 0)} кр · {adminDate(item.created_at)}</p>
                      </div>
                    </div>
                  ))}
                  {!selectedUser.data?.transactions?.length ? <div className="warn">Платежей пока нет.</div> : null}
                </div>
                <div className="assistantPanel" style={{ gap: 8 }}>
                  <b>Кредитный ledger</b>
                  {(selectedUser.data?.ledger || []).slice(0, 8).map((item) => (
                    <div key={`ledger-${item.id}`} className="feedCard" style={{ cursor: "default" }}>
                      <div>
                        <b>{item.entry_type}</b>
                        <p>{item.delta > 0 ? "+" : ""}{formatCredits(item.delta)} → {formatCredits(item.balance_after)} · {adminDate(item.created_at)}</p>
                        {item.note ? <p>{item.note}</p> : null}
                      </div>
                    </div>
                  ))}
                  {!selectedUser.data?.ledger?.length ? <div className="warn">Записей пока нет.</div> : null}
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {tab === "withdrawals" && (
        <>
          <div className="tabs soft">
            {["pending", "approved", "rejected", "all"].map((status) => (
              <button key={status} className={withdrawalStatus === status ? "active" : ""} onClick={() => setWithdrawalStatus(status)}>{status}</button>
            ))}
          </div>
          {withdrawals.loading ? <Spinner /> : (
            <div className="assistantPanel">
              {(withdrawals.data?.items || []).map((item) => (
                <div key={item.id} className="feedCard" style={{ cursor: "default", display: "grid", gap: 10 }}>
                  <div>
                    <b>{item.user?.full_name || item.user?.username || `User #${item.user?.id}`}</b>
                    <p>{formatCredits(item.amount_rub || 0)} 💋 · {item.status} · {adminDate(item.created_at)}</p>
                    <p>{item.payout_details}</p>
                    {item.admin_note ? <p>Note: {item.admin_note}</p> : null}
                  </div>
                  {item.status === "pending" ? (
                    <div className="assistantQuick">
                      <button onClick={() => reviewWithdrawal(item, "approve")}>Подтвердить</button>
                      <button onClick={() => reviewWithdrawal(item, "reject")}>Отклонить</button>
                      <button onClick={() => { setTab("users"); setSelectedUserId(item.user?.id || null); }}>Открыть юзера</button>
                    </div>
                  ) : null}
                </div>
              ))}
              {!withdrawals.data?.items?.length ? <div className="warn">Заявок нет.</div> : null}
            </div>
          )}
        </>
      )}
    </section>
  );
}

function Help({ onNotice }) {
  const [topic, setTopic] = useState("main");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api(`/help?topic=${topic}`)
      .then((data) => { if (alive) setText(data.text || ""); })
      .catch((e) => onNotice?.({ type: "error", message: e.message || "Не удалось загрузить помощь" }))
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [topic]);

  return (
    <section>
      <div className="studioHead">
        <h1>Помощь</h1>
        <span className="statusBadge success">из бота</span>
      </div>
      <div className="tabs soft">
        <button className={topic === "main" ? "active" : ""} onClick={() => setTopic("main")}>Как пользоваться</button>
        <button className={topic === "stars" ? "active" : ""} onClick={() => setTopic("stars")}>Telegram Stars</button>
      </div>
      {loading ? <Spinner /> : <div className="helpText">{text.replace(/<[^>]+>/g, "")}</div>}
    </section>
  );
}

// ── Profile screen ────────────────────────────────────────────────────────────

function ThemePicker({ value, onChange, resolvedTheme }) {
  return (
    <div className="themeCard">
      <div className="themeCardHead">
        <div>
          <b>Тема интерфейса</b>
          <p>Сохраняется на этом устройстве. Сейчас активна: {themeLabel(resolvedTheme)}.</p>
        </div>
      </div>
      <div className="themeOptions">
        {THEME_OPTIONS.map((option) => (
          <button
            key={option.value}
            className={value === option.value ? "active" : ""}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Profile({ user, history, myFeed = [], setScreen, setTopup, theme, setTheme, resolvedTheme, onNotice, reloadUser }) {
  const referralLink = preferredReferralLink(
    user.referral_link,
    siteReferralFallback(user.referral_code),
  );
  const [language, setLanguage] = useState(user.language || "ru");
  const [avatarUploading, setAvatarUploading] = useState(false);
  const avatarInputRef = useRef(null);
  const profileFeed = useMemo(() => myFeed || [], [myFeed]);
  const menuItems = [
    ["capabilities", "✦", "Все возможности"],
    ["studio", "⌘", "Студия генераций"],
    ["midjourney", "MJ", "Midjourney"],
    ["assistant", "AI", "AI-ассистент"],
    ["music", "🎶", "Музыка"],
    ["history", "☰", "Мои генерации"],
    ["feed", "◷", "Публичная лента"],
    ["prompts", "📚", "Библиотека промптов"],
    ["referrals", "₽", "Партнёрский кабинет"],
    ["help", "?", "Помощь"],
    ...(user.is_admin ? [["admin", "🛡", "Owner cockpit"]] : []),
  ];

  useEffect(() => {
    setLanguage(user.language || "ru");
  }, [user.language]);

  async function changeLanguage(nextLanguage) {
    setLanguage(nextLanguage);
    try {
      await api("/settings/language", { method: "POST", body: JSON.stringify({ language: nextLanguage }) });
      reloadUser?.();
      onNotice?.({ type: "success", message: nextLanguage === "ru" ? "Язык: русский" : "Language: English" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось сохранить язык" });
    }
  }

  async function handleAvatarUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/upload", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": initData() },
        body: fd,
      });
      if (!res.ok) {
        const raw = await res.text().catch(() => "");
        let detail = raw || "Не удалось загрузить фото";
        try {
          const parsed = raw ? JSON.parse(raw) : null;
          detail = parsed?.detail || parsed?.message || detail;
        } catch {}
        throw new Error(detail);
      }
      const data = await res.json();
      const photoUrl = normalizeAbsoluteUrl(data.url);
      if (!isAbsoluteHttpUrl(photoUrl)) throw new Error("Сервер вернул неполную ссылку");
      await api("/me/photo", { method: "POST", body: JSON.stringify({ photo_url: photoUrl }) });
      await reloadUser?.();
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Фото профиля обновлено" });
    } catch (e) {
      tg()?.HapticFeedback?.notificationOccurred("error");
      onNotice?.({ type: "error", message: e.message || "Не удалось обновить фото" });
    } finally {
      setAvatarUploading(false);
      e.target.value = "";
    }
  }

  return (
    <>
      <section className="profileMini profileHero">
        <input ref={avatarInputRef} className="profilePhotoInput" type="file" accept="image/*" onChange={handleAvatarUpload} />
        <button className="profileAvatarAction" onClick={() => avatarInputRef.current?.click()} disabled={avatarUploading}>
          <Avatar photoUrl={user.photo_url} name={user.full_name || user.username} />
          <span>{avatarUploading ? "..." : "+"}</span>
        </button>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{user.full_name || user.username}</h2>
          <p style={{ margin: "2px 0 0", color: "var(--text-faint)", fontSize: 13 }}>@{user.username || "user"}</p>
        </div>
        <span style={{ fontSize: 11, background: "var(--accent-soft-2)", border: "1px solid var(--accent-border)", borderRadius: 999, padding: "4px 10px", color: "var(--accent-text)" }}>
          {user.credits} 💋
        </span>
      </section>

      <div className="profileStats">
        <div><b>{user.credits}</b><span>токены</span></div>
        <div><b>{history.length}</b><span>работ</span></div>
        <div><b>{formatRub(user.referral_balance || 0)}</b><span>партнёрский баланс</span></div>
      </div>

      <section className="profileFeedBlock">
        <div className="title">
          <div>
            <h2>Мои фото в ленте</h2>
            <p>{profileFeed.length} опубликовано</p>
          </div>
          <button onClick={() => setScreen("feed")}>Лента</button>
        </div>
        {profileFeed.length ? (
          <div className="profileFeedGrid">
            {profileFeed.slice(0, 12).map((item, idx) => (
              <ProfileFeedTile key={item.id || idx} item={item} idx={idx} setScreen={setScreen} />
            ))}
          </div>
        ) : (
          <div className="profileFeedEmpty">Пока здесь нет опубликованных фото.</div>
        )}
      </section>

      <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 14, background: "var(--surface)", border: "1px solid var(--border)", fontSize: 13, lineHeight: 1.45 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>👥 Партнёрка</div>
        <div style={{ color: "var(--text-soft)" }}>Минимальный вывод: <b style={{ color: "var(--text-main)" }}>{formatRub(user.referral_withdraw_min_rub || 1000)}</b></div>
      </div>

      <button
        className="primary"
        onClick={() => setTopup(true)}
        style={{ width: "100%", padding: "14px", borderRadius: 16, marginTop: 16, fontSize: 15 }}
      >
        💳 Пополнить баланс
      </button>

      <ThemePicker value={theme} onChange={setTheme} resolvedTheme={resolvedTheme} />

      <div className="themeCard">
        <div className="themeCardHead">
          <div>
            <b>Язык бота</b>
            <p>Настройка общая для Telegram-бота и Mini App.</p>
          </div>
        </div>
        <div className="themeOptions">
          <button className={language === "ru" ? "active" : ""} onClick={() => changeLanguage("ru")}>Русский</button>
          <button className={language === "en" ? "active" : ""} onClick={() => changeLanguage("en")}>English</button>
        </div>
      </div>

      <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 14, background: "var(--surface)", border: "1px solid var(--border)", fontSize: 13 }}>
        <span style={{ color: "var(--text-soft)" }}>Партнёрская ссылка: </span>
        <b
          style={{ color: "var(--accent-text)", cursor: "pointer", wordBreak: "break-all" }}
          onClick={() => {
            if (tg()) tg().HapticFeedback?.notificationOccurred("success");
            navigator.clipboard?.writeText(referralLink).catch(() => {});
          }}
        >
          {referralLink}
        </b>
        <span style={{ color: "var(--text-ghost)", marginLeft: 8 }}>— нажмите для копирования</span>
      </div>

      <div className="menu" style={{ marginTop: 16 }}>
        {menuItems.map(([id, ic, t]) => (
          <button key={id} onClick={() => setScreen(id)}>
            <span>{ic} {t}</span><span>›</span>
          </button>
        ))}
      </div>
    </>
  );
}

// ── Prompts screen ────────────────────────────────────────────────────────────


function PhotoPromptTool({ setScreen, generatedPhotoPrompt, setGeneratedPhotoPrompt }) {
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setLoading(true);
    try {
      const prompt = await photoPromptApi(file);
      setGeneratedPhotoPrompt({
        prompt,
        fileName: file.name,
        createdAt: new Date().toISOString(),
      });
    } catch (err) {
      setGeneratedPhotoPrompt({
        prompt: "Не удалось проанализировать изображение. Попробуй другое фото или повтори позже.",
        error: err.message,
        createdAt: new Date().toISOString(),
      });
    } finally {
      setLoading(false);
      e.target.value = "";
    }
  }

  async function copyPrompt() {
    if (!generatedPhotoPrompt?.prompt) return;
    try {
      await navigator.clipboard.writeText(generatedPhotoPrompt.prompt);
    } catch {}
  }

  return (
    <section className="photoPromptTool">
      <div>
        <h2>📸 Промпт по фото</h2>
        <p>Загрузи изображение — я разберу стиль, сцену, свет и превращу в готовый prompt.</p>
      </div>

      <button className="photoPromptUpload" onClick={() => inputRef.current?.click()} disabled={loading}>
        {loading ? "Анализирую изображение..." : "Загрузить фото для анализа"}
      </button>
      <input ref={inputRef} type="file" accept="image/*" hidden onChange={onFile} />

      {generatedPhotoPrompt?.prompt && (
        <div className="generatedPromptCard">
          <div className="generatedPromptTop">
            <b>Готовый prompt</b>
            {generatedPhotoPrompt.fileName && <span>{generatedPhotoPrompt.fileName}</span>}
          </div>
          <p>{generatedPhotoPrompt.prompt}</p>
          <div className="generatedPromptActions">
            <button onClick={copyPrompt}>📋 Скопировать</button>
            <button onClick={() => setScreen("studio")}>✨ В студию</button>
          </div>
        </div>
      )}
    </section>
  );
}

function Prompts({ prompts, loading, setScreen, onPromptUse, onNotice, target = "studio" }) {
  const [photoPromptLoading, setPhotoPromptLoading] = useState(false);
  const [photoPromptResult, setPhotoPromptResult] = useState("");
  const [source, setSource] = useState("catalog");
  const [sourceItems, setSourceItems] = useState([]);
  const [sourceLoading, setSourceLoading] = useState(false);
  const photoPromptInputRef = useRef(null);
  const filtered = source === "catalog" ? (prompts || []) : sourceItems;
  const targetLabel = target === "midjourney" ? "В MJ" : "В студию";

  useEffect(() => {
    if (source === "catalog") return;
    let alive = true;
    setSourceLoading(true);
    const path = source === "my"
      ? "/prompts/my"
      : source.startsWith("tag:")
        ? `/prompts?source=tag&tag=${encodeURIComponent(source.slice(4))}&limit=30`
        : `/prompts?source=${source}&limit=30`;
    api(path)
      .then((data) => { if (alive) setSourceItems(items(data)); })
      .catch((e) => onNotice?.({ type: "error", message: e.message || "Не удалось загрузить промпты" }))
      .finally(() => { if (alive) setSourceLoading(false); });
    return () => { alive = false; };
  }, [source]);

  async function handlePromptPhotoFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setPhotoPromptLoading(true);
    try {
      const prompt = await photoPromptApi(file);
      setPhotoPromptResult(prompt || "Не удалось получить prompt по фото.");
    } catch (err) {
      setPhotoPromptResult("Ошибка анализа фото: " + (err?.message || err));
    } finally {
      setPhotoPromptLoading(false);
      e.target.value = "";
    }
  }

  async function copyPhotoPrompt() {
    if (!photoPromptResult) return;
    try {
      await navigator.clipboard.writeText(photoPromptResult);
    } catch {}
  }

  async function likePrompt(promptItem) {
    try {
      const res = await api(`/prompts/${promptItem.id}/like`, { method: "POST" });
      onNotice?.({ type: "success", message: res.status === "duplicate" ? "Ты уже лайкал этот промпт" : "Лайк сохранён" });
      setSourceItems((prev) => prev.map((p) => p.id === promptItem.id ? { ...p, likes: res.likes } : p));
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось поставить лайк" });
    }
  }

  async function sharePrompt(promptItem) {
    try {
      const res = await api(`/prompts/${promptItem.id}/link`);
      const ok = await copyText(res.link);
      onNotice?.({ type: ok ? "success" : "error", message: ok ? "Ссылка на промпт скопирована" : "Не удалось скопировать ссылку" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось получить ссылку" });
    }
  }

  async function deactivatePrompt(promptItem) {
    if (!window.confirm("Деактивировать этот промпт? Он пропадёт из публичной библиотеки.")) return;
    try {
      await api(`/prompts/${promptItem.id}/deactivate`, { method: "POST" });
      setSourceItems((prev) => prev.filter((p) => p.id !== promptItem.id));
      onNotice?.({ type: "success", message: "Промпт деактивирован" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось деактивировать промпт" });
    }
  }

  if (loading) return <><h1>Библиотека</h1><Spinner /></>;

  return (
    <>
      <h1>Библиотека промптов</h1>
      <div className="sourceTabs">
        {[
          ["catalog", "Каталог"],
          ["top", "Топ"],
          ["popular", "Популярные"],
          ["tag:cinematic", "Cinematic"],
          ["tag:cyberpunk", "Cyberpunk"],
          ["my", "Мои"],
        ].map(([id, label]) => (
          <button key={id} className={source === id ? "active" : ""} onClick={() => setSource(id)}>{label}</button>
        ))}
      </div>
      <section className="photoPromptTool">
        <div>
          <h2>📸 Промпт по фото</h2>
          <p>Загрузи изображение — я проанализирую стиль, композицию, свет и сделаю готовый prompt.</p>
        </div>

        <button
          className="photoPromptUpload"
          onClick={() => photoPromptInputRef.current?.click()}
          disabled={photoPromptLoading}
        >
          {photoPromptLoading ? "Анализирую фото..." : "Загрузить фото для анализа"}
        </button>

        <input
          ref={photoPromptInputRef}
          type="file"
          accept="image/*"
          hidden
          onChange={handlePromptPhotoFile}
        />

        {photoPromptResult && (
          <div className="generatedPromptCard">
            <div className="generatedPromptTop">
              <b>Готовый prompt</b>
            </div>
            <p>{photoPromptResult}</p>
            <div className="generatedPromptActions">
              <button onClick={copyPhotoPrompt}>📋 Скопировать</button>
              <button onClick={() => onPromptUse ? onPromptUse({ title: "Промпт по фото", prompt_text: photoPromptResult }) : setScreen("studio")}>✨ {targetLabel}</button>
            </div>
          </div>
        )}
      </section>

      <div style={{ display: "grid", gap: 12 }}>
        {sourceLoading && <Spinner />}
        {filtered.map((p, i) => (
          <div key={p.id} className="promptListCard promptListCardAction">
            {p.preview_url
              ? (
                <button type="button" className="promptPreviewBtn" onClick={() => openExternalUrl(p.preview_url)}>
                  <img src={p.preview_url} alt={p.title} className="promptListImg" />
                </button>
              )
              : <Art type={["a","b","c","d"][i % 4]} />}
            <div className="promptListInfo">
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{p.title}</h3>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--text-soft)", overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                {p.description || p.prompt_text}
              </p>
              <footer style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, color: "var(--text-ghost)" }}>
                <span>{p.model || "Any"}</span>
                <span>♥ {p.likes || 0}  ·  {p.uses_count || 0} исп</span>
              </footer>
              <div className="promptActions">
                <button onClick={() => onPromptUse ? onPromptUse(p) : setScreen("studio")}>{targetLabel}</button>
                <button onClick={() => likePrompt(p)}>♥</button>
                <button onClick={() => sharePrompt(p)}>↗</button>
                {source === "my" && <button onClick={() => deactivatePrompt(p)}>Скрыть</button>}
              </div>
            </div>
          </div>
        ))}
        {!sourceLoading && filtered.length === 0 && (
          <p style={{ color: "var(--text-ghost)", textAlign: "center", marginTop: 32 }}>Промпты не найдены</p>
        )}
      </div>
    </>
  );
}

// ── App root ─────────────────────────────────────────────────────────────────

function FullViewer({ item, onClose }) {
  if (!item) return null;
  const promptActionsAllowed = generationPromptActionsAllowed(item);
  return <div className="viewer" onClick={onClose}>
    <div className="viewerPanel" onClick={(e) => e.stopPropagation()}>
      <button className="viewerClose" onClick={onClose}>×</button>
      {item.result_url ? <img src={item.result_url} alt="" /> : <Art type="a" />}
      <div className="viewerMeta">
        <b>{item.model || "Generation"}</b>
        <p>{generationDisplayPrompt(item)}</p>
        <div className="viewerActions">
          {promptActionsAllowed && item.id && (
            <button onClick={() => saveGenerationPrompt(item.id)}>💾 Сохранить промпт</button>
          )}
          <button onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  </div>
}

function App() {
  const [screen, setScreen] = useState("home");
  const [generation, setGeneration] = useState(null);
  const [musicGen, setMusicGen] = useState(null);
  const [pollId, setPollId] = useState(null);
  const [musicPollId, setMusicPollId] = useState(null);
  const [topupOpen, setTopupOpen] = useState(false);
  const [remixSource, setRemixSource] = useState(null);
  const [notice, setNotice] = useState(null);
  const [theme, setTheme] = useState(() => readStoredTheme());
  const [studioPreset, setStudioPreset] = useState(null);
  const [promptTarget, setPromptTarget] = useState("studio");
  const [feedScope, setFeedScope] = useState("all");
  const [historyScope, setHistoryScope] = useState("all");
  const poll = useRef(null);
  const musicPoll = useRef(null);
  const pollIdRef = useRef(null);
  const musicPollIdRef = useRef(null);
  const realtimeRef = useRef(null);
  const realtimeReconnectRef = useRef(null);
  const generationScreen = useRef("studio");

  useEffect(() => {
    const webApp = tg();
    try {
      webApp?.ready?.();
      webApp?.expand?.();
    } catch (_) {}
  }, []);

  useEffect(() => {
    const resetScroll = () => {
      try {
        window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      } catch (_) {
        window.scrollTo(0, 0);
      }
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    };

    resetScroll();
    const frame = window.requestAnimationFrame(resetScroll);
    return () => window.cancelAnimationFrame(frame);
  }, [screen]);

  const me = useApi(() => api("/me"), fallbackUser);
  const imageModels = useApi(() => api("/models/image").then(x => items(x).length ? items(x) : x), fallbackImageModels);
  const videoModels = useApi(() => api("/models/video").then(x => items(x).length ? items(x) : x), fallbackVideoModels);
  const musicModels = useApi(() => api("/models/music").then(x => items(x).length ? items(x) : x), []);
  const feed = useApi(() => api("/feed?limit=10000").then(items), fallbackFeed);
  const myFeed = useApi(() => api("/me/feed?limit=10000").then(items), []);
  const history = useApi(() => api("/history?limit=50").then(items), []);
  const prompts = useApi(() => api("/prompts?limit=30").then(items), []);
  const midjourneyItems = useApi(() => api("/public/midjourney").then(items), []);
  const referrals = useApi(() => api("/referrals"), fallbackReferralStats);

  const telegramUser = tgUser();
  const user = useMemo(() => {
    const tgName = telegramFullName(telegramUser);
    return {
      ...fallbackUser,
      ...(me.data || {}),
      username: me.data?.username || telegramUser?.username || null,
      full_name: me.data?.full_name || tgName || null,
      photo_url: me.data?.photo_url || telegramUser?.photo_url || null,
    };
  }, [me.data, telegramUser?.username, telegramUser?.first_name, telegramUser?.last_name, telegramUser?.photo_url]);
  const isDemo = me.error || imageModels.error || videoModels.error;
  const resolvedTheme = resolveTheme(theme);

  useEffect(() => {
    pollIdRef.current = pollId;
  }, [pollId]);

  useEffect(() => {
    musicPollIdRef.current = musicPollId;
  }, [musicPollId]);

  useEffect(() => {
    if (!notice?.message) return undefined;
    const timer = setTimeout(() => setNotice(null), 3200);
    return () => clearTimeout(timer);
  }, [notice?.message]);

  useEffect(() => { tg()?.ready?.(); tg()?.expand?.(); }, []);

  useEffect(() => {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const nextTheme = resolveTheme(theme);
      root.dataset.theme = nextTheme;

      const webApp = tg();
      if (webApp) {
        const bg = nextTheme === "light"
          ? "#f4f1fb"
          : nextTheme === "mintpink"
            ? "#f4ffe3"
            : "#050507";
        const head = nextTheme === "light"
          ? "#ffffff"
          : nextTheme === "mintpink"
            ? "#fff2f8"
            : "#050507";
        webApp.setBackgroundColor?.(bg);
        webApp.setHeaderColor?.(head);
        webApp.setBottomBarColor?.(bg);
      }
    };

    apply();

    const media = window.matchMedia?.("(prefers-color-scheme: light)");
    const handleChange = () => {
      if (theme === "system") apply();
    };

    media?.addEventListener?.("change", handleChange);
    tg()?.onEvent?.("themeChanged", handleChange);
    return () => {
      media?.removeEventListener?.("change", handleChange);
      tg()?.offEvent?.("themeChanged", handleChange);
    };
  }, [theme]);

  const applyRealtimeGeneration = useCallback((payload) => {
    const g = generationFromRealtimeEvent(payload);
    if (!g?.id) return;
    const isFinal = ["done", "failed"].includes(String(g.status || "").toLowerCase());
    const isMusic = g.gen_type === "music";

    if (isMusic) {
      setMusicGen((prev) => (!prev?.id || Number(prev.id) === Number(g.id) ? { ...(prev || {}), ...g } : prev));
      if (Number(musicPollIdRef.current) === Number(g.id) && isFinal) {
        clearInterval(musicPoll.current);
        setMusicPollId(null);
      }
    } else {
      setGeneration((prev) => (!prev?.id || Number(prev.id) === Number(g.id) ? { ...(prev || {}), ...g } : g));
      if (Number(pollIdRef.current) === Number(g.id) && isFinal) {
        clearInterval(poll.current);
        setPollId(null);
      }
    }

    if (isFinal) {
      me.reload();
      history.reload();
      if (!isMusic) feed.reload();
      tg()?.HapticFeedback?.notificationOccurred(g.status === "done" ? "success" : "error");
      setNotice({
        type: g.status === "done" ? "success" : "error",
        message: g.status === "done"
          ? `${isMusic ? "Музыка" : g.gen_type === "video" ? "Видео" : "Изображение"} готово — результат уже на экране.`
          : `Генерация #${g.id} завершилась ошибкой.`,
      });
    }
  }, [feed.reload, history.reload, me.reload]);

  useEffect(() => {
    const url = realtimeWsUrl();
    const authMessage = realtimeAuthMessage();
    if (!url || !authMessage) return undefined;

    let closed = false;
    let retryMs = 1000;
    let failures = 0;

    const connect = () => {
      if (closed) return;
      const socket = new WebSocket(url);
      realtimeRef.current = socket;

      socket.onopen = () => {
        retryMs = 1000;
        socket.send(JSON.stringify(authMessage));
      };
      socket.onmessage = (event) => {
        failures = 0;
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "generation.snapshot" && Array.isArray(payload.items)) {
            payload.items.forEach(applyRealtimeGeneration);
            return;
          }
          applyRealtimeGeneration(payload);
        } catch {}
      };
      socket.onclose = () => {
        if (closed) return;
        failures += 1;
        if (failures > REALTIME_MAX_FAILURES) return;
        realtimeReconnectRef.current = window.setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 1.8, 12000);
      };
      socket.onerror = () => {
        socket.close();
      };
    };

    connect();
    return () => {
      closed = true;
      if (realtimeReconnectRef.current) window.clearTimeout(realtimeReconnectRef.current);
      realtimeRef.current?.close?.();
    };
  }, [applyRealtimeGeneration]);

  // Poll image/video generation
  useEffect(() => {
    if (!pollId) return;
    let failures = 0;
    clearInterval(poll.current);
    poll.current = setInterval(async () => {
      try {
        const g = await api(`/generations/${pollId}`);
        failures = 0;
        setGeneration(g);
        if (["done", "failed"].includes(g.status)) {
          clearInterval(poll.current);
          setPollId(null);
          if (g.status === "done") {
            me.reload();
            history.reload();
            feed.reload();
            setScreen(generationScreen.current || "studio");
            tg()?.HapticFeedback?.notificationOccurred("success");
            setNotice({ type: "success", message: "Готово — показываю результат сразу." });
          } else {
            me.reload();
            history.reload();
            setNotice({ type: "error", message: "Генерация завершилась ошибкой. Если кредиты списались, они вернутся автоматически." });
          }
        }
      } catch (e) {
        failures += 1;
        if (e?.status === 404 || failures >= 12) {
          clearInterval(poll.current);
          setPollId(null);
          setNotice({ type: "error", message: "Не удалось получить статус генерации. Историю можно обновить позже." });
        }
      }
    }, 3500);
    return () => clearInterval(poll.current);
  }, [pollId]);

  // Poll music generation
  useEffect(() => {
    if (!musicPollId) return;
    let failures = 0;
    clearInterval(musicPoll.current);
    musicPoll.current = setInterval(async () => {
      try {
        const g = await api(`/generations/${musicPollId}`);
        failures = 0;
        setMusicGen(g);
        if (["done", "failed"].includes(g.status)) {
          clearInterval(musicPoll.current);
          setMusicPollId(null);
          me.reload();
          history.reload();
        }
      } catch (e) {
        failures += 1;
        if (e?.status === 404 || failures >= 12) {
          clearInterval(musicPoll.current);
          setMusicPollId(null);
        }
      }
    }, 5000);
    return () => clearInterval(musicPoll.current);
  }, [musicPollId]);

  async function generate(kind, payload) {
    generationScreen.current = screen === "midjourney" ? "midjourney" : "studio";
    setGeneration({ id: 0, status: "pending" });
    try {
      const endpoint = kind === "video" ? "/generate/video" : "/generate/image";
      const body = kind === "video"
        ? { model: payload.model, prompt: payload.prompt || (payload.model === "midjourney-video" ? "mj-video" : ""), mode: payload.mode, duration: payload.duration, aspect_ratio: payload.aspect_ratio, resolution: payload.resolution, image_url: payload.image_url, reference_urls: payload.reference_urls || [], grok_mode: payload.grok_mode }
        : { model: payload.model, prompt: payload.prompt || (payload.model === "midjourney-blend" ? "mj-blend" : ""), prompt_id: payload.prompt_id || null, aspect_ratio: payload.aspect_ratio, quality: payload.quality, count: payload.count, reference_url: payload.reference_url, reference_urls: payload.reference_urls || [] };
      const g = await api(endpoint, { method: "POST", body: JSON.stringify(body) });
      setGeneration(g);
      setPollId(g.id);
      me.reload();
    } catch (e) {
      setGeneration({ id: 0, status: "failed", error: e.message });
      if (e.status === 402) setTopupOpen(true);
    }
  }

  async function remixGenerate(genId, payload) {
    generationScreen.current = screen === "midjourney" ? "midjourney" : "studio";
    setGeneration({ id: 0, status: "pending" });
    try {
      const body = { model: payload.model, prompt: "", mode: payload.mode || "text", duration: payload.duration, aspect_ratio: payload.aspect_ratio, resolution: payload.resolution, image_url: payload.image_url, reference_urls: payload.reference_urls || [], grok_mode: payload.grok_mode, quality: payload.quality, count: payload.count };
      const g = await api(`/feed/${genId}/remix`, { method: "POST", body: JSON.stringify(body) });
      setGeneration(g);
      setPollId(g.id);
      setRemixSource(null);
      me.reload();
    } catch (e) {
      setGeneration({ id: 0, status: "failed", error: e.message });
      if (e.status === 402) setTopupOpen(true);
    }
  }

  async function generateMusic(payload) {
    setMusicGen({ id: 0, status: "pending" });
    try {
      const g = await api("/generate/music", { method: "POST", body: JSON.stringify(payload) });
      setMusicGen(g);
      setMusicPollId(g.id);
      me.reload();
    } catch (e) {
      setMusicGen({ id: 0, status: "failed", error: e.message });
      if (e.status === 402) setTopupOpen(true);
    }
  }

  function openStudioPreset(item) {
    setRemixSource(null);
    setStudioPreset({ modelKey: item.key, kind: item.gen_type });
    setScreen(isMidjourneyModel(item.key) ? "midjourney" : "studio");
  }

  function openPromptPreset(promptItem) {
    if (isMidjourneyModel(promptItem.model)) {
      openMidjourneyPromptPreset(promptItem);
      return;
    }
    setRemixSource(null);
    setStudioPreset({
      kind: "image",
      modelKey: promptItem.model || undefined,
      prompt: promptItem.prompt_text || promptItem.prompt || "",
      promptId: promptItem.id || null,
      title: promptItem.title || "Промпт",
    });
    setScreen("studio");
  }

  function openMidjourneyPromptPreset(promptItem) {
    setRemixSource(null);
    setStudioPreset({
      kind: "image",
      modelKey: "midjourney-imagine",
      prompt: promptItem.prompt_text || promptItem.prompt || "",
      promptId: promptItem.id || null,
      title: promptItem.title || "Промпт",
    });
    setScreen("midjourney");
  }

  function navigate(nextScreen) {
    if (nextScreen === "feed") setFeedScope("all");
    if (nextScreen === "history") setHistoryScope("all");
    if (nextScreen === "prompts") setPromptTarget("studio");
    setScreen(nextScreen);
  }

  function openPromptLibrary(target = "studio") {
    setPromptTarget(target === "midjourney" ? "midjourney" : "studio");
    setScreen("prompts");
  }

  function openFeed(scope = "all") {
    const normalizedScope = scope === "midjourney" ? "midjourney" : "all";
    setFeedScope(normalizedScope);
    setPromptTarget(normalizedScope === "midjourney" ? "midjourney" : "studio");
    setScreen("feed");
  }

  function openHistory(scope = "all") {
    setHistoryScope(scope === "midjourney" ? "midjourney" : "all");
    setScreen("history");
  }

  function handleRemix(feedItem) {
    const targetScreen = isMidjourneyModel(feedItem.model) ? "midjourney" : "studio";
    setRemixSource({
      gen_id: feedItem.id,
      model: feedItem.model,
      gen_type: feedItem.gen_type || "image",
      result_url: feedItem.result_url || null,
      result_urls: generationResultUrls(feedItem).slice(0, 4),
    });
    setGeneration(null);
    generationScreen.current = targetScreen;
    setScreen(targetScreen);
  }

  const activePromptUse = promptTarget === "midjourney" ? openMidjourneyPromptPreset : openPromptPreset;

  window.__APIX_IS_ADMIN__ = Boolean(user?.is_admin);

  const screens = {
    home: <Home user={user} referrals={referrals.data} feed={feed.data} prompts={prompts.data} historyCount={history.data.length} setScreen={navigate} setTopup={setTopupOpen} midjourneyItems={midjourneyItems.data} openStudioPreset={openStudioPreset} onPromptUse={openPromptPreset} />,
    capabilities: <Capabilities setScreen={navigate} setTopup={setTopupOpen} />,
    assistant: <Assistant onNotice={setNotice} />,
    feed: <Feed feed={feed.data} feedLoading={feed.loading} prompts={prompts.data} setScreen={navigate} onRemix={handleRemix} onNotice={setNotice} onRemoved={() => { feed.reload(); myFeed.reload(); }} scope={feedScope} onPromptUse={feedScope === "midjourney" ? openMidjourneyPromptPreset : openPromptPreset} onOpenPrompts={() => openPromptLibrary(feedScope === "midjourney" ? "midjourney" : "studio")} />,
    studio: <Studio imageModels={imageModels.data} videoModels={videoModels.data} user={user} onGenerate={generate} onRemixGenerate={remixGenerate} generation={generation} setTopup={setTopupOpen} remixSource={remixSource} clearRemix={() => setRemixSource(null)} onNotice={setNotice} preset={studioPreset} />,
    midjourney: <MidjourneyModule imageModels={imageModels.data} videoModels={videoModels.data} user={user} generation={generation} prompts={prompts.data} feed={feed.data} history={history.data} setScreen={navigate} setTopup={setTopupOpen} onGenerate={generate} onRemixGenerate={remixGenerate} remixSource={remixSource} clearRemix={() => setRemixSource(null)} onNotice={setNotice} preset={studioPreset} onPromptUse={openMidjourneyPromptPreset} onOpenPrompts={() => openPromptLibrary("midjourney")} onOpenFeed={() => openFeed("midjourney")} onOpenHistory={() => openHistory("midjourney")} />,
    music: <Music user={user} musicGen={musicGen} musicModels={musicModels.data} onGenerateMusic={generateMusic} setTopup={setTopupOpen} onNotice={setNotice} />,
    history: <History history={history.data} loading={history.loading} onNotice={setNotice} scope={historyScope} onPromptUse={openPromptPreset} />,
    profile: <Profile user={user} history={history.data} myFeed={myFeed.data} setScreen={navigate} setTopup={setTopupOpen} theme={theme} setTheme={setTheme} resolvedTheme={resolvedTheme} onNotice={setNotice} reloadUser={me.reload} />,
    referrals: <Referrals user={user} stats={referrals.data} loading={referrals.loading} reload={referrals.reload} onNotice={setNotice} />,
    help: <Help onNotice={setNotice} />,
    admin: <AdminDashboard user={user} onNotice={setNotice} />,
    prompts:<Prompts prompts={prompts.data} loading={prompts.loading} setScreen={navigate} onPromptUse={activePromptUse} onNotice={setNotice} target={promptTarget}/>,
  };

  return (
    <main>
      <div className="bg" />
      <div className="wrap">
        <Header screen={screen} setScreen={navigate} user={user} setTopup={setTopupOpen} />
        <NoticeBar notice={notice} onClose={() => setNotice(null)} />
        {isDemo && (
          <div className="warn">
            Demo-режим: API недоступен или нет Telegram initData. Данные — заглушки.
          </div>
        )}
        {screens[screen] || screens.home}
      </div>
      <Nav screen={screen} setScreen={navigate} />
      {topupOpen && <TopupModal onClose={() => setTopupOpen(false)} />}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
