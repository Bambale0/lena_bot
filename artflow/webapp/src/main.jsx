import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_BASE = "/api/v1";

// ── fallbacks ────────────────────────────────────────────────────────────────

const fallbackUser = {
  username: null,
  full_name: null,
  credits: 0,
  referral_balance: 0,
  referral_code: "",
  referral_link: "",
};

const fallbackImageModels = [];

const fallbackVideoModels = [];

const fallbackFeed = [];

const fallbackPlans = [];
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

async function publishGeneration(id) {
  return api(`/generations/${id}/publish`, { method: "POST" });
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

function items(x) { return Array.isArray(x) ? x : Array.isArray(x?.items) ? x.items : []; }

function isMiniappVideoModelSupported(model) {
  const modes = model?.modes || [];
  return modes.includes("text") || modes.includes("image");
}

function modelModesLabel(model) {
  const modes = model?.modes || ["text"];
  if (modes.includes("text") && modes.includes("image")) return "текст + фото";
  if (modes.includes("image")) return "по фото";
  return "текст";
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

function Avatar({ name = "?" }) {
  return <div className="avatar">{String(name || "?").slice(0, 1).toUpperCase()}</div>;
}

function Spinner() {
  return <div className="spinner" />;
}

function NoticeBar({ notice, onClose }) {
  if (!notice?.message) return null;
  return (
    <div className={`noticeBar ${notice.type || "info"}`}>
      <span>{notice.message}</span>
      <button onClick={onClose}>×</button>
    </div>
  );
}

function MediaThumb({ url, type, idx = 0, className = "" }) {
  if (url) {
    if (type === "video" || /\.(mp4|webm|mov)/i.test(url))
      return <video src={url} className={className || undefined} muted playsInline loop />;
    if (type === "music" || /\.(mp3|ogg|wav)/i.test(url))
      return <div className={`musicThumb ${className}`}>🎵</div>;
    return <img src={url} className={className || undefined} />;
  }
  return <Art type={["a","b","c","d"][idx % 4]} />;
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
    ["feed", "◷", "Лента"],
    ["studio", "⌘", "Студия"],
    ["music", "♫", "Музыка"],
    ["history", "☰", "История"],
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
  const [selected, setSelected] = useState(null);
  const [method, setMethod] = useState("stars");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

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
      const endpoint = method === "crypto" ? "/topup/crypto" : method === "stars" ? "/topup/stars" : "/topup/tbank";
      const res = await api(endpoint, { method: "POST", body: JSON.stringify({ plan_key: selected }) });
      const url = res.invoice_link || res.pay_url;
      if (!url) throw new Error("Платёжная ссылка не получена");
      if (method === "stars" && tg()?.openInvoice) tg().openInvoice(url, () => {});
      else if (tg()) tg().openLink(url);
      else window.open(url, "_blank");
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
                <em>{formatRub(p)}</em>
              </button>
            ))}
          </div>
        )}

        <div className="tabs" style={{ marginTop: 16 }}>
          <button className={method === "stars" ? "active" : ""} onClick={() => setMethod("stars")}>⭐ Stars</button>
          <button className={method === "tbank" ? "active" : ""} onClick={() => setMethod("tbank")}>💳 Т-Банк</button>
          <button className={method === "crypto" ? "active" : ""} onClick={() => setMethod("crypto")}>₮ Крипто</button>
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

function ProfileStrip({ user, historyCount, setScreen, setTopup }) {
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
        <div><b>{user.referral_balance || 0}</b><span>реф ₽</span></div>
        <div onClick={() => setTopup(true)} style={{ cursor: "pointer" }}>
          <b>+</b><span>пополнить</span>
        </div>
      </div>
    </section>
  );
}

function PromptFeed({ prompts, setScreen }) {
  return (
    <section className="block">
      <div className="title">
        <div><h2>Библиотека промптов</h2><p>Готовые идеи для старта</p></div>
        <button onClick={() => setScreen("prompts")}>Все</button>
      </div>
      <div className="hscroll">
        {prompts.map((p, i) => (
          <button key={p.id || i} className="promptCard" onClick={() => setScreen("studio")}>
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

function Home({ user, feed, prompts, historyCount, setScreen, setTopup }) {
  return (
    <>
      <ProfileStrip user={user} historyCount={historyCount} setScreen={setScreen} setTopup={setTopup} />
      <PromptFeed prompts={prompts} setScreen={setScreen} />
      <section className="block">
        <div className="title">
          <h2>Публичные работы</h2>
          <button onClick={() => setScreen("feed")}>Все</button>
        </div>
        <div className="grid">
          {feed.slice(0, 4).map((f, i) => (
            <button key={f.id || i} className="feedCard" onClick={() => setScreen("feed")}>
              <MediaThumb url={f.result_url} type="image" idx={i} />
              <div>
                <span>{f.model}</span>
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

function FeedCard({ item, idx, onRemix, onNotice }) {
  const [liked, setLiked] = useState(false);
  const [likes, setLikes] = useState(item.likes_count || 0);
  const [busy, setBusy] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);

  async function handleLike() {
    if (liked || busy) return;
    setBusy(true);
    try {
      const res = await api(`/feed/${item.id}/like`, { method: "POST" });
      setLikes(res.likes_count ?? likes + 1);
      setLiked(true);
    } catch {
      setLikes(l => l + 1);
      setLiked(true);
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
      setTimeout(() => setLinkCopied(false), 2000);
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось получить ссылку" });
    }
  }

  return (
    <div className="feedFullCard">
      <div className="feedFullMedia">
        <MediaThumb url={item.result_url} type="image" idx={idx} className="feedFullImg" />
      </div>
      <div className="feedFullInfo">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <span className="modelBadge">{item.model}</span>
          <span className="feedAuthor">@{item.author || "anon"}</span>
        </div>
        <div className="feedActions" style={{ marginTop: 10, display: "flex", gap: 8 }}>
          <button className={`likeBtn ${liked ? "liked" : ""}`} onClick={handleLike} disabled={busy}>
            ♥ {likes}
          </button>
          <button
            className="remixBtn"
            onClick={() => onRemix && onRemix(item)}
            style={{ flex: 1, padding: "8px 12px", borderRadius: 10, background: "var(--accent-soft)", border: "1px solid var(--accent-border)", color: "var(--accent-text)", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
          >
            🔁 Повторить
          </button>
          {item.is_mine && (
            <button
              onClick={handleCopyLink}
              style={{ padding: "8px 10px", borderRadius: 10, background: linkCopied ? "var(--success-soft)" : "var(--surface-2)", border: `1px solid ${linkCopied ? "var(--success-border)" : "var(--border-strong)"}`, color: linkCopied ? "var(--success)" : "var(--text-soft)", fontSize: 13, cursor: "pointer" }}
            >
              {linkCopied ? "✅" : "🔗"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Feed({ feed, feedLoading, prompts, setScreen, onRemix, onNotice }) {
  const filtered = feed;

  return (
    <>
      <h1>Лента</h1>
      <PromptFeed prompts={prompts} setScreen={setScreen} />
      {feedLoading ? <Spinner /> : (
        <div className="feedList">
          {filtered.map((f, i) => <FeedCard key={f.id || i} item={f} idx={i} onRemix={onRemix} onNotice={onNotice} />)}
          {filtered.length === 0 && <p style={{ color: "var(--text-ghost)", textAlign: "center", marginTop: 32 }}>Пусто</p>}
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
      await api(`/generations/${genId}/share`, { method: "POST" });
      setInFeed(true);
      tg()?.HapticFeedback?.notificationOccurred("success");
    } catch (e) { onNotice?.({ type: "error", message: e.message || "Не удалось опубликовать" }); }
    finally { setBusyFeed(false); }
  }

  async function handleLib() {
    if (inLib || busyLib) return;
    setBusyLib(true);
    try {
      await api(`/generations/${genId}/share-library`, { method: "POST" });
      setInLib(true);
      tg()?.HapticFeedback?.notificationOccurred("success");
    } catch (e) { onNotice?.({ type: "error", message: e.message || "Не удалось опубликовать" }); }
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
        onClick={handleLib} disabled={busyLib || inLib}
        style={{ ...btnBase, background: inLib ? "var(--accent-soft)" : "var(--surface-2)", border: `1px solid ${inLib ? "var(--accent-border)" : "var(--border-strong)"}`, color: inLib ? "var(--accent-text)" : "var(--text-muted)" }}
      >
        {inLib ? "✅ В библиотеке" : busyLib ? "..." : "📚 В библиотеку"}
      </button>
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

  if (modes.includes("image")) return "edit";
  if (key.includes("seedream")) return "fast";
  if (key.includes("wan")) return "fast";
  if (key.includes("nano") || key.includes("banana")) return "fast";
  return "fast";
}

function getVideoScenario(model) {
  const key = String(model?.key || "").toLowerCase();
  const modes = model?.modes || ["text"];
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

function modeOptionLabel(x) {
  return {
    fun: "Fun",
    normal: "Normal",
    spicy: "Spicy",
  }[x] || x;
}

function Studio({ imageModels, videoModels, user, onGenerate, onRemixGenerate, generation, setTopup, remixSource, clearRemix, onNotice }) {
  const isRemix = !!remixSource;
  const supportedVideoModels = useMemo(
    () => (videoModels || []).filter(isMiniappVideoModelSupported),
    [videoModels],
  );

  const [kind, setKind] = useState(remixSource?.gen_type === "video" ? "video" : "image");
  const [scenario, setScenario] = useState("fast");

  const sourceModels = useMemo(
    () => (kind === "image" ? imageModels : supportedVideoModels),
    [kind, imageModels, supportedVideoModels],
  );
  const scenarioModels = useMemo(
    () => getScenarioModels(kind, scenario, imageModels, supportedVideoModels),
    [kind, scenario, imageModels, supportedVideoModels],
  );
  const visibleModels = scenarioModels.length ? scenarioModels : sourceModels;

  const [model, setModel] = useState(visibleModels[0]?.key || "");
  const current = visibleModels.find((m) => m.key === model) || visibleModels[0] || sourceModels[0];

  const [mode, setMode] = useState("text");
  const [prompt, setPrompt] = useState("");
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
    setScenario("fast");
  }, [kind, isRemix, remixSource?.gen_type]);

  useEffect(() => {
    if (!remixSource) {
      setRefUrls([]);
      setRefError("");
      return;
    }
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

  async function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setRefError("");
    try {
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
      setRefUrls((prev) => {
        const cleaned = prev.filter((url) => normalizeAbsoluteUrl(url) !== uploadedUrl);
        if ((Number(current?.max_refs || 1) || 1) <= 1) return [uploadedUrl];
        return [...cleaned, uploadedUrl].slice(0, Number(current?.max_refs || 1) || 1);
      });
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
  const maxRefs = Math.max(1, Number(current?.max_refs || 1) || 1);
  const hasValidRefUrl = normalizedRefUrls.every((value) => isAbsoluteHttpUrl(value));
  const isPerSecond = Boolean(current?.is_per_second);
  const perSec = Number(current?.credits_per_sec || current?.credits || 0);
  const baseCost = Number(current?.credits || 0);
  const estimatedCost = kind === "video" && isPerSecond ? duration * perSec : baseCost;

  const modes = current?.modes || ["text"];
  const qualityOptions = normalizeQualityOptions(current);
  const modeOptions = normalizeModeOptions(current);
  const durations = current?.durations || current?.duration_options || [];
  const resolutions = current?.resolutions || [];
  const counts = current?.counts || [1];

  const canUseReference = modes.includes("image");
  const requiresReference = mode === "image" && canUseReference;
  const showMode = modes.length > 1;
  const showRatio = (current?.aspect_ratios || []).length > 1;
  const showQuality = kind === "image" && qualityOptions.length > 1;
  const showCount = kind === "image" && counts.length > 1;
  const showDuration = kind === "video" && durations.length > 0;
  const showResolution = kind === "video" && resolutions.length > 1;
  const showModeOption = kind === "video" && modeOptions.length > 1;

  async function handleImprovePrompt() {
    if (!prompt.trim() || improvingPrompt) return;
    setImprovingPrompt(true);
    try {
      const result = await api("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt, kind: "music" }) });
      setPrompt(result.prompt || prompt);
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Идея для трека усилена" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось улучшить описание трека" });
    } finally {
      setImprovingPrompt(false);
    }
  }

  function handleGenerate() {
    if (!current) return;

    if (requiresReference && !normalizedRefUrls.length && !(isRemix && remixSource?.gen_type === "image" && remixSource?.result_url)) {
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

    const remixRefUrl = isRemix && remixSource?.gen_type === "image" ? normalizeAbsoluteUrl(remixSource?.result_url || "") : "";
    const effectiveRefUrls = mode === "image"
      ? (normalizedRefUrls.length ? normalizedRefUrls.slice(0, maxRefs) : remixRefUrl ? [remixRefUrl] : [])
      : [];
    const effectiveRefUrl = effectiveRefUrls[0] || null;

    const payload = {
      model,
      prompt,
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
          <h1>{isRemix ? "🔁 Повтор из ленты" : "Студия"}</h1>
          <p>{kind === "image" ? "Создай изображение или ремикс по фото" : "Создай видео или оживи фото"}</p>
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
          <button className={kind === "image" ? "active" : ""} onClick={() => setKind("image")}>🖼 Фото</button>
          <button className={kind === "video" ? "active" : ""} onClick={() => setKind("video")}>🎬 Видео</button>
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
        <div className="modelList">
          {visibleModels.map((m) => (
            <button key={m.key} className={model === m.key ? "active" : ""} onClick={() => setModel(m.key)}>
              <i>{kind === "video" ? "🎬" : m.key?.includes("seedream") ? "☁️" : m.key?.includes("wan") ? "🌊" : m.key?.includes("grok") ? "⚡" : "🍌"}</i>
              <span>
                <b>{m.display_name}</b>
                <small>
                  {modelModesLabel(m)}
                  {" · "}
                  {m.is_per_second ? `${m.credits_per_sec || m.credits} 💋/сек` : `${m.credits} 💋`}
                </small>
              </span>
            </button>
          ))}
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
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleFileUpload} />
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

      {!isRemix && (
        <SettingsRow label="Промпт">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={kind === "video" ? "Опиши сцену, движение и настроение..." : "Опиши идею изображения..."}
          />
        </SettingsRow>
      )}

      <div className="studioActions">
        <button className="secondaryBtn" disabled={!prompt.trim() || improvingPrompt || isRemix} onClick={handleImprovePrompt}>
          {improvingPrompt ? "⏳ Улучшаю..." : "✨ Улучшить промпт"}
        </button>
      </div>

      <button
        className="primary studioGenerate"
        disabled={!current || (!isRemix && !prompt.trim()) || (requiresReference && !normalizedRefUrl) || !hasValidRefUrl}
        onClick={handleGenerate}
      >
        {kind === "video" ? "Создать видео" : "Сгенерировать"}
        <span>{estimatedCost || current?.credits || 0} 💋</span>
      </button>

      {generation && (
        <div className="status">
          <b>Генерация #{generation.id}</b>
          <span>{generation.status}</span>
          {generation.error && <p>{generation.error}</p>}
        </div>
      )}
    </section>
  );
}

// ── Music screen ──────────────────────────────────────────────────────────────

function Music({ user, musicGen, onGenerateMusic, setTopup, onNotice }) {
  const [prompt, setPrompt] = useState("");
  const [instrumental, setInstrumental] = useState(false);
  const [improvingPrompt, setImprovingPrompt] = useState(false);

  const MUSIC_CREDITS = 20;
  const genStatus = musicGen?.status;
  const statusColor = genStatus === "done" ? "#4ade80" : genStatus === "failed" ? "#f87171" : "#facc15";

  async function handleImprovePrompt() {
    if (!prompt.trim() || improvingPrompt) return;
    setImprovingPrompt(true);
    try {
      const result = await api("/prompt/improve", { method: "POST", body: JSON.stringify({ prompt, kind }) });
      setPrompt(result.prompt || prompt);
      tg()?.HapticFeedback?.notificationOccurred("success");
      onNotice?.({ type: "success", message: "Промпт улучшен" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось улучшить промпт" });
    } finally {
      setImprovingPrompt(false);
    }
  }

  function handleGenerate() {
    if (!prompt.trim()) return;
    if (user.credits < MUSIC_CREDITS) { setTopup(true); return; }
    onGenerateMusic({ prompt, instrumental });
  }

  return (
    <section>
      <div className="studioHead">
        <h1>🎵 Музыка</h1>
        <button className="balanceBtn" onClick={() => setTopup(true)}>{user.credits} 💋</button>
      </div>

      <div style={{ marginBottom: 16, padding: "12px 14px", borderRadius: 14, background: "var(--accent-soft)", border: "1px solid var(--accent-border)", fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
        Генерация песни с помощью Suno AI. Описывай жанр, настроение, инструменты и тематику.
        <div style={{ marginTop: 8, fontWeight: 700, color: "var(--text)" }}>Стоимость: {MUSIC_CREDITS} 💋 за трек.</div>
      </div>

      <SettingsRow label="Режим">
        <div className="tabs soft">
          <button className={!instrumental ? "active" : ""} onClick={() => setInstrumental(false)}>🎤 С текстом</button>
          <button className={instrumental ? "active" : ""} onClick={() => setInstrumental(true)}>🎸 Инструментал</button>
        </div>
      </SettingsRow>

      <SettingsRow label="Описание трека">
        <textarea
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder={instrumental
            ? "Например: epic orchestral, cinematic, dramatic, Hans Zimmer style..."
            : "Например: upbeat pop song about summer, female vocal, dance vibes..."}
          maxLength={4000}
          style={{ minHeight: 100 }}
        />
      </SettingsRow>

      <div style={{ display: "grid", gap: 10, marginBottom: 10 }}>
        <button className="ghost" onClick={handleImprovePrompt} disabled={!prompt.trim() || improvingPrompt}>
          {improvingPrompt ? "⏳ Улучшаю описание..." : "✨ Улучшить описание трека"}
        </button>
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
        {genStatus === "pending" ? "⏳ Генерирую..." : `🎵 Создать трек · ${MUSIC_CREDITS} 💋`}
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

function History({ history, loading, onNotice }) {
  if (loading) return <Spinner />;
  return (
    <>
      <h1>История</h1>
      {history.length === 0
        ? <p style={{ color: "var(--text-ghost)", textAlign: "center", marginTop: 40 }}>Генераций пока нет. Создайте первую в Студии!</p>
        : <div className="historyList">
            {history.map((g, i) => (
              <div key={g.id} className="historyCard">
                <div className="historyMedia">
                  <MediaThumb url={g.result_url} type={g.gen_type} idx={i} className="historyImg" />
                </div>
                <div className="historyInfo">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <span className="modelBadge">{g.model}</span>
                    <span style={{ fontSize: 11, color: getStatusColor(g.status) }}>{g.status}</span>
                  </div>
                  <p className="feedPrompt">{g.prompt}</p>
                  {g.gen_type === "music" && g.result_url && (
                    <audio controls src={g.result_url} style={{ width: "100%", borderRadius: 8, marginTop: 6 }} />
                  )}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
                    <small style={{ color: "var(--text-ghost)", fontSize: 11 }}>{formatDate(g.created_at)}</small>
                    <small style={{ color: "var(--accent-text)", fontSize: 11 }}>−{g.credits_spent} 💋</small>
                  </div>
                  {g.status === "done" && g.gen_type !== "music" && (
                    <GenShareButtons genId={g.id} initialFeed={g.is_public_feed} initialLib={g.is_prompt_library} onNotice={onNotice} />
                  )}
                </div>
              </div>
            ))}
          </div>
      }
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

function Profile({ user, history, setScreen, setTopup, theme, setTheme, resolvedTheme }) {
  const referralLink = user.referral_link || `https://t.me/apix_ai_bot?start=${user.referral_code || ""}`;
  const menuItems = [
    ["studio", "⌘", "Студия генераций"],
    ["music", "♫", "Музыка (Suno)"],
    ["history", "☰", "Мои генерации"],
    ["feed", "◷", "Публичная лента"],
    ["prompts", "📚", "Библиотека промптов"],
  ];

  return (
    <>
      <section className="profileMini">
        <Avatar photoUrl={user.photo_url} name={user.full_name || user.username} />
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
        <div><b>{user.referral_balance || 0}</b><span>реф ₽</span></div>
      </div>

      <button
        className="primary"
        onClick={() => setTopup(true)}
        style={{ width: "100%", padding: "14px", borderRadius: 16, marginTop: 16, fontSize: 15 }}
      >
        💳 Пополнить баланс
      </button>

      <ThemePicker value={theme} onChange={setTheme} resolvedTheme={resolvedTheme} />

      <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 14, background: "var(--surface)", border: "1px solid var(--border)", fontSize: 13 }}>
        <span style={{ color: "var(--text-soft)" }}>Реферальная ссылка: </span>
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

function Prompts({ prompts, loading, setScreen }) {
  const [photoPromptLoading, setPhotoPromptLoading] = useState(false);
  const [photoPromptResult, setPhotoPromptResult] = useState("");
  const photoPromptInputRef = useRef(null);
  const filtered = prompts || [];

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

  if (loading) return <><h1>Библиотека</h1><Spinner /></>;

  return (
    <>
      <h1>Библиотека промптов</h1>
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
              <button onClick={() => setScreen("studio")}>✨ В студию</button>
            </div>
          </div>
        )}
      </section>

      <div style={{ display: "grid", gap: 12 }}>
        {filtered.map((p, i) => (
          <button key={p.id} className="promptListCard" onClick={() => setScreen("studio")}>
            {p.preview_url
              ? <img src={p.preview_url} alt={p.title} className="promptListImg" />
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
            </div>
          </button>
        ))}
        {filtered.length === 0 && (
          <p style={{ color: "var(--text-ghost)", textAlign: "center", marginTop: 32 }}>Промпты не найдены</p>
        )}
      </div>
    </>
  );
}

// ── App root ─────────────────────────────────────────────────────────────────

function FullViewer({ item, onClose }) {
  if (!item) return null;
  return <div className="viewer" onClick={onClose}>
    <div className="viewerPanel" onClick={(e) => e.stopPropagation()}>
      <button className="viewerClose" onClick={onClose}>×</button>
      {item.result_url ? <img src={item.result_url} alt="" /> : <Art type="a" />}
      <div className="viewerMeta">
        <b>{item.model || "Generation"}</b>
        <p>{item.prompt || "Промпт скрыт"}</p>
        <div className="viewerActions">
          <button onClick={() => item.id && publishGeneration(item.id)}>📚 В библиотеку</button>
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
  const poll = useRef(null);
  const musicPoll = useRef(null);

  const me = useApi(() => api("/me"), fallbackUser);
  const imageModels = useApi(() => api("/models/image").then(x => items(x).length ? items(x) : x), fallbackImageModels);
  const videoModels = useApi(() => api("/models/video").then(x => items(x).length ? items(x) : x), fallbackVideoModels);
  const feed = useApi(() => api("/feed?limit=30").then(items), fallbackFeed);
  const history = useApi(() => api("/history?limit=50").then(items), []);
  const prompts = useApi(() => api("/prompts?limit=30").then(items), []);

  const user = me.data;
  const isDemo = me.error || imageModels.error || videoModels.error;
  const resolvedTheme = resolveTheme(theme);

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

  // Poll image/video generation
  useEffect(() => {
    if (!pollId) return;
    clearInterval(poll.current);
    poll.current = setInterval(async () => {
      try {
        const g = await api(`/generations/${pollId}`);
        setGeneration(g);
        if (["done", "failed"].includes(g.status)) {
          clearInterval(poll.current);
          setPollId(null);
          if (g.status === "done") { me.reload(); history.reload(); }
        }
      } catch {
        clearInterval(poll.current);
        setPollId(null);
      }
    }, 3500);
    return () => clearInterval(poll.current);
  }, [pollId]);

  // Poll music generation
  useEffect(() => {
    if (!musicPollId) return;
    clearInterval(musicPoll.current);
    musicPoll.current = setInterval(async () => {
      try {
        const g = await api(`/generations/${musicPollId}`);
        setMusicGen(g);
        if (["done", "failed"].includes(g.status)) {
          clearInterval(musicPoll.current);
          setMusicPollId(null);
          if (g.status === "done") { me.reload(); history.reload(); }
        }
      } catch {
        clearInterval(musicPoll.current);
        setMusicPollId(null);
      }
    }, 5000);
    return () => clearInterval(musicPoll.current);
  }, [musicPollId]);

  async function generate(kind, payload) {
    setGeneration({ id: 0, status: "pending" });
    try {
      const endpoint = kind === "video" ? "/generate/video" : "/generate/image";
      const body = kind === "video"
        ? { model: payload.model, prompt: payload.prompt, mode: payload.mode, duration: payload.duration, aspect_ratio: payload.aspect_ratio, resolution: payload.resolution, image_url: payload.image_url, grok_mode: payload.grok_mode }
        : { model: payload.model, prompt: payload.prompt, aspect_ratio: payload.aspect_ratio, quality: payload.quality, count: payload.count, reference_url: payload.reference_url };
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
    setGeneration({ id: 0, status: "pending" });
    try {
      const body = { model: payload.model, prompt: "", mode: payload.mode || "text", duration: payload.duration, aspect_ratio: payload.aspect_ratio, resolution: payload.resolution, image_url: payload.image_url, grok_mode: payload.grok_mode, quality: payload.quality, count: payload.count };
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

  function handleRemix(feedItem) {
    setRemixSource({
      gen_id: feedItem.id,
      model: feedItem.model,
      gen_type: feedItem.gen_type || "image",
      result_url: feedItem.result_url || null,
    });
    setGeneration(null);
    setScreen("studio");
  }

  const screens = {
    home: <Home user={user} feed={feed.data} prompts={prompts.data} historyCount={history.data.length} setScreen={setScreen} setTopup={setTopupOpen} />,
    feed: <Feed feed={feed.data} feedLoading={feed.loading} prompts={prompts.data} setScreen={setScreen} onRemix={handleRemix} onNotice={setNotice} />,
    studio: <Studio imageModels={imageModels.data} videoModels={videoModels.data} user={user} onGenerate={generate} onRemixGenerate={remixGenerate} generation={generation} setTopup={setTopupOpen} remixSource={remixSource} clearRemix={() => setRemixSource(null)} onNotice={setNotice} />,
    music: <Music user={user} musicGen={musicGen} onGenerateMusic={generateMusic} setTopup={setTopupOpen} onNotice={setNotice} />,
    history: <History history={history.data} loading={history.loading} onNotice={setNotice} />,
    profile: <Profile user={user} history={history.data} setScreen={setScreen} setTopup={setTopupOpen} theme={theme} setTheme={setTheme} resolvedTheme={resolvedTheme} />,
    prompts:<Prompts prompts={prompts.data} loading={prompts.loading} setScreen={setScreen}/>,
  };

  return (
    <main>
      <div className="bg" />
      <div className="wrap">
        <Header screen={screen} setScreen={setScreen} user={user} setTopup={setTopupOpen} />
        <NoticeBar notice={notice} onClose={() => setNotice(null)} />
        {isDemo && (
          <div className="warn">
            Demo-режим: API недоступен или нет Telegram initData. Данные — заглушки.
          </div>
        )}
        {screens[screen] || screens.home}
      </div>
      <Nav screen={screen} setScreen={setScreen} />
      {topupOpen && <TopupModal onClose={() => setTopupOpen(false)} />}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
