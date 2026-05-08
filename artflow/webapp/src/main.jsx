import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

const API_BASE = "/api/v1";

// ── fallbacks ────────────────────────────────────────────────────────────────

const fallbackUser = { username: "demo", full_name: "Demo User", credits: 100, referral_balance: 0, referral_code: "DEMO" };

const fallbackImageModels = [
  { key: "nano-banana-pro", display_name: "NanoBanana Pro", credits: 10, aspect_ratios: ["9:16","1:1","16:9"], quality_options: [{value:"2K",label:"2K"},{value:"4K",label:"4K"}], counts: [1,2,4,6], has_quality: true, modes: ["text","image"] },
  { key: "wan/2-7-image-pro", display_name: "WAN 2.7 Pro", credits: 8, aspect_ratios: ["1:1","16:9","9:16","4:3","3:4"], quality_options: [{value:"1K",label:"1K"},{value:"2K",label:"2K"},{value:"4K",label:"4K"}], counts: [1,2,4,6], has_quality: true, modes: ["text","image"] },
  { key: "seedream/4.5-text-to-image", display_name: "Seedream 4.5", credits: 2, aspect_ratios: ["9:16","1:1","16:9","4:3"], quality_options: [{value:"basic",label:"2K"},{value:"high",label:"4K"}], counts: [1], has_quality: true, modes: ["text"] },
];

const fallbackVideoModels = [
  { key: "kling-3.0/video", display_name: "Kling 3.0", credits: 8, aspect_ratios: ["9:16","16:9","1:1"], modes: ["text","image"], durations: [5,10], resolutions: ["2K","4K"], has_quality: true },
  { key: "bytedance/seedance-2-fast", display_name: "Seedance 2 Fast", credits: 15, aspect_ratios: ["16:9","9:16","1:1"], modes: ["text","image"], durations: [3,5,8], resolutions: ["480p","720p"], has_quality: true },
];

const fallbackFeed = [
  { id:500, model:"NanoBanana Pro", prompt:"white cat in blooming lilac flowers", likes_count:116, result_url:null },
  { id:501, model:"Seedream 4.5", prompt:"perfume bottle in pink flowers", likes_count:281, result_url:null },
];

const fallbackPlans = [
  { key:"starter", title:"Старт", credits:100, price_rub:199, price_usdt:2.21 },
  { key:"basic",   title:"Базовый", credits:300, price_rub:499, price_usdt:5.54 },
  { key:"pro",     title:"Про", credits:700, price_rub:999, price_usdt:11.10 },
  { key:"ultra",   title:"Ультра", credits:2000, price_rub:2490, price_usdt:27.67 },
];

// ── Telegram WebApp helpers ──────────────────────────────────────────────────

function tg() { return window.Telegram?.WebApp || null; }
function initData() { return tg()?.initData || ""; }

// ── API client ───────────────────────────────────────────────────────────────

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
        <Avatar name={user.full_name || user.username} />
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
  const { data: plans, loading } = useApi(() => api("/plans"), fallbackPlans);
  const [selected, setSelected] = useState(null);
  const [method, setMethod] = useState("tbank");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function handlePay() {
    if (!selected) return;
    setBusy(true); setErr(null);
    try {
      const endpoint = method === "crypto" ? "/topup/crypto" : "/topup/tbank";
      const res = await api(endpoint, { method: "POST", body: JSON.stringify({ plan_key: selected }) });
      const url = res.pay_url;
      if (tg()) tg().openLink(url);
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
                <b>{p.title}</b>
                <span>{p.credits} 💋</span>
                <em>{p.price_rub} ₽</em>
              </button>
            ))}
          </div>
        )}

        <div className="tabs" style={{ marginTop: 16 }}>
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
      <Avatar name={user.full_name || user.username} />
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
              <div><span>{f.model}</span><p>{f.prompt}</p></div>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}

// ── Feed screen ───────────────────────────────────────────────────────────────

function FeedCard({ item, idx, onRemix }) {
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
      alert(e.message || "Ошибка");
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
            style={{ flex: 1, padding: "8px 12px", borderRadius: 10, background: "rgba(124,58,237,.2)", border: "1px solid rgba(124,58,237,.4)", color: "#c4b5fd", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
          >
            🔁 Повторить
          </button>
          {item.is_mine && (
            <button
              onClick={handleCopyLink}
              style={{ padding: "8px 10px", borderRadius: 10, background: linkCopied ? "rgba(74,222,128,.15)" : "rgba(255,255,255,.07)", border: `1px solid ${linkCopied ? "rgba(74,222,128,.4)" : "rgba(255,255,255,.15)"}`, color: linkCopied ? "#4ade80" : "rgba(255,255,255,.7)", fontSize: 13, cursor: "pointer" }}
            >
              {linkCopied ? "✅" : "🔗"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Feed({ feed, feedLoading, prompts, setScreen, onRemix }) {
  const [filter, setFilter] = useState("all");
  const filters = [["all","Все"], ["image","Фото"], ["video","Видео"]];
  const filtered = filter === "all" ? feed : feed.filter(f => f.gen_type === filter || (filter === "image" && !f.gen_type));

  return (
    <>
      <h1>Лента</h1>
      <PromptFeed prompts={prompts} setScreen={setScreen} />
      <div className="chips top" style={{ marginBottom: 16 }}>
        {filters.map(([k, l]) => (
          <button key={k} className={filter === k ? "active" : ""} onClick={() => setFilter(k)}>{l}</button>
        ))}
      </div>
      {feedLoading ? <Spinner /> : (
        <div className="feedList">
          {filtered.map((f, i) => <FeedCard key={f.id || i} item={f} idx={i} onRemix={onRemix} />)}
          {filtered.length === 0 && <p style={{ color: "rgba(255,255,255,.4)", textAlign: "center", marginTop: 32 }}>Пусто</p>}
        </div>
      )}
    </>
  );
}

// ── Post-generation share buttons ────────────────────────────────────────────

function GenShareButtons({ genId, initialFeed = false, initialLib = false }) {
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
    } catch (e) { alert(e.message); }
    finally { setBusyFeed(false); }
  }

  async function handleLib() {
    if (inLib || busyLib) return;
    setBusyLib(true);
    try {
      await api(`/generations/${genId}/share-library`, { method: "POST" });
      setInLib(true);
      tg()?.HapticFeedback?.notificationOccurred("success");
    } catch (e) { alert(e.message); }
    finally { setBusyLib(false); }
  }

  const btnBase = { flex: 1, padding: "10px 8px", borderRadius: 12, fontSize: 13, fontWeight: 600, cursor: "pointer", transition: "all .2s" };

  return (
    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
      <button
        onClick={handleFeed} disabled={busyFeed || inFeed}
        style={{ ...btnBase, background: inFeed ? "rgba(74,222,128,.15)" : "rgba(255,255,255,.07)", border: `1px solid ${inFeed ? "rgba(74,222,128,.4)" : "rgba(255,255,255,.15)"}`, color: inFeed ? "#4ade80" : "rgba(255,255,255,.8)" }}
      >
        {inFeed ? "✅ В ленте" : busyFeed ? "..." : "📤 В ленту"}
      </button>
      <button
        onClick={handleLib} disabled={busyLib || inLib}
        style={{ ...btnBase, background: inLib ? "rgba(167,139,250,.15)" : "rgba(255,255,255,.07)", border: `1px solid ${inLib ? "rgba(167,139,250,.5)" : "rgba(255,255,255,.15)"}`, color: inLib ? "#c4b5fd" : "rgba(255,255,255,.8)" }}
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
      <div style={{ fontSize: 11, color: "rgba(255,255,255,.45)", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".06em" }}>{label}</div>
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

function Studio({ imageModels, videoModels, user, onGenerate, onRemixGenerate, generation, setTopup, remixSource, clearRemix }) {
  const isRemix = !!remixSource;
  const initialKind = remixSource?.gen_type === "video" ? "video" : "image";

  const [kind, setKind] = useState(initialKind);
  const models = kind === "image" ? imageModels : videoModels;
  const [model, setModel] = useState(remixSource?.model || models[0]?.key || "");
  const [mode, setMode] = useState("text");
  const [prompt, setPrompt] = useState("");
  const [ratio, setRatio] = useState("9:16");
  const [quality, setQuality] = useState("basic");
  const [count, setCount] = useState(1);
  const [duration, setDuration] = useState(5);
  const [resolution, setResolution] = useState("720p");
  const [grokMode, setGrokMode] = useState("normal");
  const [refUrl, setRefUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const current = models.find(m => m.key === model) || models[0];

  useEffect(() => {
    if (remixSource) {
      setKind(remixSource.gen_type === "video" ? "video" : "image");
      setModel(remixSource.model || models[0]?.key || "");
    }
  }, [remixSource]);

  useEffect(() => { if (!isRemix) { setModel(models[0]?.key || ""); setMode("text"); } }, [kind]);

  useEffect(() => {
    if (!current) return;
    const firstRatio = current.aspect_ratios?.[0];
    if (firstRatio) setRatio(firstRatio);
    const firstQ = current.quality_options?.[0]?.value || current.quality_options?.[0];
    if (firstQ) setQuality(typeof firstQ === "object" ? firstQ.value : firstQ);
    const firstDur = current.durations?.[0] || 5;
    setDuration(firstDur);
    const firstRes = current.resolutions?.[0] || "720p";
    setResolution(firstRes);
    setCount(1);
    setGrokMode("normal");
  }, [model, kind]);

  async function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/upload", {
        method: "POST",
        headers: { "X-Telegram-Init-Data": initData() },
        body: fd,
      });
      if (!res.ok) throw new Error("Upload failed");
      const { url } = await res.json();
      setRefUrl(url);
    } catch {
      setRefUrl(URL.createObjectURL(file));
    } finally {
      setUploading(false);
    }
  }

  const estimatedCost = current?.is_per_second
    ? duration * (current.credits_per_sec || current.credits || 0)
    : (current?.credits || 0);

  function handleGenerate() {
    if (user.credits < estimatedCost) { setTopup(true); return; }
    const payload = {
      model, mode, aspect_ratio: ratio, quality, count,
      duration, resolution, grok_mode: grokMode,
      image_url: mode === "image" ? refUrl || null : null,
      reference_url: mode === "image" ? refUrl || null : null,
    };
    if (isRemix) onRemixGenerate(remixSource.gen_id, payload);
    else onGenerate(kind, { ...payload, prompt });
  }

  const genStatus = generation?.status;
  const statusColor = genStatus === "done" ? "#4ade80" : genStatus === "failed" ? "#f87171" : "#facc15";

  // model capability flags
  const showQuality = kind === "image" && current?.has_quality && (current.quality_options || []).length > 1;
  const showCount = kind === "image" && (current?.counts || [1]).length > 1;
  const showRatio = (current?.aspect_ratios || []).length > 1;
  const showDuration = kind === "video" && (current?.durations || []).length > 0;
  const showResolution = kind === "video" && (current?.resolutions || []).length > 1;
  const showGrokMode = kind === "video" && current?.key?.includes("grok");

  return (
    <section>
      <div className="studioHead">
        <h1>{isRemix ? "🔁 Повтор из ленты" : "Студия"}</h1>
        <button className="balanceBtn" onClick={() => setTopup(true)}>{user.credits} 💋</button>
      </div>

      {isRemix && (
        <div style={{ marginBottom: 12, padding: "10px 14px", borderRadius: 12, background: "rgba(124,58,237,.12)", border: "1px solid rgba(124,58,237,.3)", fontSize: 13, color: "#c4b5fd", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Промпт автора скрыт — выбери модель и параметры</span>
          <button onClick={clearRemix} style={{ background: "none", border: "none", color: "rgba(255,255,255,.4)", fontSize: 16, cursor: "pointer", padding: "0 4px" }}>✕</button>
        </div>
      )}

      <SettingsRow label="Тип">
        <div className="tabs">
          <button className={kind === "image" ? "active" : ""} onClick={() => setKind("image")}>🖼 Фото</button>
          <button className={kind === "video" ? "active" : ""} onClick={() => setKind("video")}>🎬 Видео</button>
        </div>
      </SettingsRow>

      <SettingsRow label="Модель">
        <div className="models">
          {models.map(m => (
            <button key={m.key} onClick={() => setModel(m.key)} className={model === m.key ? "active" : ""}>
              <i>{kind === "video" ? "🎬" : m.key.includes("seedream") ? "☁️" : m.key.includes("wan") ? "🌊" : m.key.includes("grok") ? "⚡" : "🍌"}</i>
              <span>{m.display_name}</span>
              <small style={{ color: "rgba(255,255,255,.4)", fontSize: 10 }}>
                {m.is_per_second ? `от ${m.credits_per_sec || m.credits} 💋/сек` : `${m.credits} 💋`}
              </small>
            </button>
          ))}
        </div>
      </SettingsRow>

      {(current?.modes || ["text"]).length > 1 && (
        <SettingsRow label="Режим">
          <div className="tabs soft">
            {(current?.modes || ["text"]).map(m => (
              <button key={m} className={mode === m ? "active" : ""} onClick={() => setMode(m)}>
                {m === "text" ? `Text → ${kind === "video" ? "Video" : "Image"}` :
                 m === "image" ? `Image → ${kind === "video" ? "Video" : "Image"}` :
                 m === "motion" ? "🕺 Motion Control" : m}
              </button>
            ))}
          </div>
        </SettingsRow>
      )}

      {mode === "image" && (
        <SettingsRow label="Референс">
          <div className="refBlock">
            {refUrl
              ? <div className="refPreview">
                  <img src={refUrl} alt="reference" />
                  <button onClick={() => setRefUrl("")} className="refRemove">✕</button>
                </div>
              : <button className="refUpload" onClick={() => fileRef.current?.click()} disabled={uploading}>
                  {uploading ? "Загрузка..." : "📎 Загрузить референс"}
                </button>
            }
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={handleFileUpload} />
          </div>
        </SettingsRow>
      )}

      {showRatio && (
        <SettingsRow label="Соотношение сторон">
          <ChipGroup
            options={(current?.aspect_ratios || []).slice(0, 8)}
            value={ratio}
            onChange={setRatio}
          />
        </SettingsRow>
      )}

      {showQuality && (
        <SettingsRow label="Качество">
          <ChipGroup
            options={(current.quality_options || []).map(q =>
              typeof q === "object" ? q : { value: q, label: q }
            )}
            value={quality}
            onChange={setQuality}
          />
        </SettingsRow>
      )}

      {showCount && (
        <SettingsRow label="Количество изображений">
          <ChipGroup
            options={(current.counts || [1]).map(n => ({ value: n, label: `${n} шт` }))}
            value={count}
            onChange={setCount}
          />
        </SettingsRow>
      )}

      {showDuration && (
        <SettingsRow label="Длительность">
          <ChipGroup
            options={(current.durations || [5]).map(d => ({ value: d, label: `${d}с` }))}
            value={duration}
            onChange={setDuration}
          />
        </SettingsRow>
      )}

      {showResolution && (
        <SettingsRow label="Разрешение">
          <ChipGroup
            options={current.resolutions || []}
            value={resolution}
            onChange={setResolution}
          />
        </SettingsRow>
      )}

      {showGrokMode && (
        <SettingsRow label="Стиль Grok">
          <ChipGroup
            options={["normal","fun","spicy"].map(m => ({ value: m, label: m === "normal" ? "Норм" : m === "fun" ? "Весёлый" : "Горячий" }))}
            value={grokMode}
            onChange={setGrokMode}
          />
        </SettingsRow>
      )}

      {!isRemix && (
        <SettingsRow label="Промпт">
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder={kind === "video" ? "Опишите движение, сцену и камеру..." : "Опишите вашу идею..."}
            maxLength={4000}
          />
        </SettingsRow>
      )}

      <button
        disabled={(!isRemix && !prompt.trim()) || genStatus === "pending"}
        onClick={handleGenerate}
        className="primary"
        style={{ width: "100%", padding: 14, borderRadius: 16, marginTop: 4, fontSize: 15 }}
      >
        {genStatus === "pending"
          ? "⏳ Генерация..."
          : current?.is_per_second
            ? `${kind === "video" ? "Создать видео" : "Сгенерировать"} · ${duration}с × ${current.credits_per_sec || current.credits} = ${estimatedCost} 💋`
            : `${kind === "video" ? "Создать видео" : "Сгенерировать"} · ${count > 1 ? `${count} × ` : ""}${current?.credits || 0} = ${(current?.credits || 0) * count} 💋`}
      </button>

      {generation && (
        <div className="status" style={{ borderColor: `${statusColor}44`, background: `${statusColor}11`, marginTop: 16 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <b>Генерация #{generation.id}</b>
            <span style={{ color: statusColor, fontSize: 13 }}>{generation.status}</span>
          </div>
          {generation.result_url && (
            <div className="genResult">
              <MediaThumb url={generation.result_url} type={kind} idx={0} className="genResultMedia" />
            </div>
          )}
          {generation.status === "done" && generation.id > 0 && (
            <GenShareButtons genId={generation.id} />
          )}
          {generation.error && <p style={{ color: "#f87171", margin: "8px 0 0", fontSize: 12 }}>{generation.error}</p>}
        </div>
      )}
    </section>
  );
}

// ── Music screen ──────────────────────────────────────────────────────────────

function Music({ user, musicGen, onGenerateMusic, setTopup }) {
  const [prompt, setPrompt] = useState("");
  const [instrumental, setInstrumental] = useState(false);

  const MUSIC_CREDITS = 20;
  const genStatus = musicGen?.status;
  const statusColor = genStatus === "done" ? "#4ade80" : genStatus === "failed" ? "#f87171" : "#facc15";

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

      <div style={{ marginBottom: 16, padding: "12px 14px", borderRadius: 14, background: "rgba(124,58,237,.1)", border: "1px solid rgba(124,58,237,.2)", fontSize: 13, color: "rgba(255,255,255,.7)", lineHeight: 1.5 }}>
        Генерация песни с помощью Suno AI. Описывай жанр, настроение, инструменты и тематику.
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

      <div style={{ fontSize: 12, color: "rgba(255,255,255,.35)", marginBottom: 10 }}>
        💡 Промпт лучше писать на английском. Генерация занимает ~1–2 мин.
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
            <p style={{ color: "rgba(255,255,255,.5)", fontSize: 12, margin: "8px 0 0" }}>
              Ожидай ~1–2 минуты. Результат придёт в Telegram и появится здесь автоматически.
            </p>
          )}
          {musicGen.result_url && (
            <div style={{ marginTop: 12 }}>
              <audio controls src={musicGen.result_url} style={{ width: "100%", borderRadius: 10 }} />
            </div>
          )}
          {musicGen.error && <p style={{ color: "#f87171", margin: "8px 0 0", fontSize: 12 }}>{musicGen.error}</p>}
        </div>
      )}
    </section>
  );
}

// ── History screen ────────────────────────────────────────────────────────────

function History({ history, loading }) {
  if (loading) return <Spinner />;
  return (
    <>
      <h1>История</h1>
      {history.length === 0
        ? <p style={{ color: "rgba(255,255,255,.4)", textAlign: "center", marginTop: 40 }}>Генераций пока нет. Создайте первую в Студии!</p>
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
                    <small style={{ color: "rgba(255,255,255,.35)", fontSize: 11 }}>{formatDate(g.created_at)}</small>
                    <small style={{ color: "#a78bfa", fontSize: 11 }}>−{g.credits_spent} 💋</small>
                  </div>
                  {g.status === "done" && g.gen_type !== "music" && (
                    <GenShareButtons genId={g.id} initialFeed={g.is_public_feed} initialLib={g.is_prompt_library} />
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

function Profile({ user, history, setScreen, setTopup }) {
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
        <Avatar name={user.full_name || user.username} />
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{user.full_name || user.username}</h2>
          <p style={{ margin: "2px 0 0", color: "rgba(255,255,255,.42)", fontSize: 13 }}>@{user.username || "user"}</p>
        </div>
        <span style={{ fontSize: 11, background: "rgba(124,58,237,.3)", border: "1px solid rgba(124,58,237,.5)", borderRadius: 999, padding: "4px 10px", color: "#c4b5fd" }}>
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

      <div style={{ marginTop: 16, padding: "10px 14px", borderRadius: 14, background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.08)", fontSize: 13 }}>
        <span style={{ color: "rgba(255,255,255,.5)" }}>Реферальный код: </span>
        <b
          style={{ color: "#a78bfa", cursor: "pointer" }}
          onClick={() => {
            if (tg()) tg().HapticFeedback?.notificationOccurred("success");
            navigator.clipboard?.writeText(user.referral_code).catch(() => {});
          }}
        >
          {user.referral_code}
        </b>
        <span style={{ color: "rgba(255,255,255,.35)", marginLeft: 8 }}>— нажмите для копирования</span>
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

function Prompts({ prompts, loading, setScreen }) {
  const [category, setCategory] = useState("all");
  const cats = [["all","Все"], ["image","Фото"], ["video","Видео"], ["other","Другое"]];
  const filtered = category === "all" ? prompts : prompts.filter(p => p.category === category);

  if (loading) return <><h1>Библиотека</h1><Spinner /></>;

  return (
    <>
      <h1>Библиотека промптов</h1>
      <div className="chips top" style={{ marginBottom: 16 }}>
        {cats.map(([k, l]) => (
          <button key={k} className={category === k ? "active" : ""} onClick={() => setCategory(k)}>{l}</button>
        ))}
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {filtered.map((p, i) => (
          <button key={p.id} className="promptListCard" onClick={() => setScreen("studio")}>
            {p.preview_url
              ? <img src={p.preview_url} alt={p.title} className="promptListImg" />
              : <Art type={["a","b","c","d"][i % 4]} />}
            <div className="promptListInfo">
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{p.title}</h3>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "rgba(255,255,255,.5)", overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                {p.description || p.prompt_text}
              </p>
              <footer style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, color: "rgba(255,255,255,.4)" }}>
                <span>{p.model || "Any"}</span>
                <span>♥ {p.likes || 0}  ·  {p.uses_count || 0} исп</span>
              </footer>
            </div>
          </button>
        ))}
        {filtered.length === 0 && (
          <p style={{ color: "rgba(255,255,255,.4)", textAlign: "center", marginTop: 32 }}>Промпты не найдены</p>
        )}
      </div>
    </>
  );
}

// ── App root ─────────────────────────────────────────────────────────────────

function App() {
  const [screen, setScreen] = useState("home");
  const [generation, setGeneration] = useState(null);
  const [musicGen, setMusicGen] = useState(null);
  const [pollId, setPollId] = useState(null);
  const [musicPollId, setMusicPollId] = useState(null);
  const [topupOpen, setTopupOpen] = useState(false);
  const [remixSource, setRemixSource] = useState(null);
  const poll = useRef(null);
  const musicPoll = useRef(null);

  const me = useApi(() => api("/me"), fallbackUser);
  const imageModels = useApi(() => api("/models/image").then(x => items(x).length ? items(x) : x), fallbackImageModels);
  const videoModels = useApi(() => api("/models/video").then(x => items(x).length ? items(x) : x), fallbackVideoModels);
  const feed = useApi(() => api("/feed?limit=30").then(items), fallbackFeed);
  const history = useApi(() => api("/history?limit=50").then(items), []);
  const prompts = useApi(() => api("/prompts?limit=30").then(items), []);

  const user = me.data;
  const isDemo = me.error || imageModels.error;

  useEffect(() => { tg()?.ready?.(); tg()?.expand?.(); }, []);

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
      const body = { model: payload.model, prompt: "", mode: payload.mode || "text", duration: payload.duration, aspect_ratio: payload.aspect_ratio, resolution: payload.resolution, image_url: payload.image_url, grok_mode: payload.grok_mode, quality: payload.quality };
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
    setRemixSource({ gen_id: feedItem.id, model: feedItem.model, gen_type: feedItem.gen_type || "image" });
    setGeneration(null);
    setScreen("studio");
  }

  const screens = {
    home: <Home user={user} feed={feed.data} prompts={prompts.data} historyCount={history.data.length} setScreen={setScreen} setTopup={setTopupOpen} />,
    feed: <Feed feed={feed.data} feedLoading={feed.loading} prompts={prompts.data} setScreen={setScreen} onRemix={handleRemix} />,
    studio: <Studio imageModels={imageModels.data} videoModels={videoModels.data} user={user} onGenerate={generate} onRemixGenerate={remixGenerate} generation={generation} setTopup={setTopupOpen} remixSource={remixSource} clearRemix={() => setRemixSource(null)} />,
    music: <Music user={user} musicGen={musicGen} onGenerateMusic={generateMusic} setTopup={setTopupOpen} />,
    history: <History history={history.data} loading={history.loading} />,
    profile: <Profile user={user} history={history.data} setScreen={setScreen} setTopup={setTopupOpen} />,
    prompts: <Prompts prompts={prompts.data} loading={prompts.loading} setScreen={setScreen} />,
  };

  return (
    <main>
      <div className="bg" />
      <div className="wrap">
        <Header screen={screen} setScreen={setScreen} user={user} setTopup={setTopupOpen} />
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
