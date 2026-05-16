const root = document.getElementById("app");
const routes = ["home", "auth", "studio", "prompts", "prompt-detail", "add-prompt", "feed", "works", "billing", "profile", "admin"];

const state = {
  me: null,
  models: [],
  plans: [],
  feed: [],
  prompts: [],
  history: [],
  session: null,
  errors: {},
};

function routeName() {
  const raw = location.hash.replace(/^#\/?/, "").split("?")[0] || "home";
  return routes.includes(raw) ? raw : "home";
}

function setActiveNav() {
  const name = routeName();
  document.querySelectorAll(".nav a").forEach((link) => {
    link.classList.toggle("is-active", link.getAttribute("href") === `#/${name}`);
  });
}

async function api(path) {
  const headers = {};
  const devTgId = localStorage.getItem("apix_dev_tg_id");
  if (devTgId) headers["X-Dev-Tg-Id"] = devTgId;
  const res = await fetch(`/api/web${path}`, { headers });
  const json = await res.json().catch(() => ({ ok: false, error: "Bad API response" }));
  if (!res.ok || json.ok === false) throw new Error(json.error || `HTTP ${res.status}`);
  return Object.prototype.hasOwnProperty.call(json, "data") ? json.data : json;
}

async function loadData() {
  const jobs = [
    ["me", () => api("/me")],
    ["models", () => api("/models")],
    ["plans", () => api("/price-plans")],
    ["feed", () => api("/feed?limit=9")],
    ["prompts", () => api("/prompts?limit=9")],
    ["history", () => api("/history?limit=9")],
    ["session", () => api("/image-sessions/active")],
  ];

  await Promise.all(jobs.map(async ([key, fn]) => {
    try {
      state[key] = await fn();
      delete state.errors[key];
    } catch (err) {
      state.errors[key] = err.message;
    }
  }));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function empty(label, err) {
  return `<div class="empty">${escapeHtml(label)}${err ? `<br><span class="mono">${escapeHtml(err)}</span>` : ""}</div>`;
}

function imageBlock(url, alt) {
  if (!url) return `<div class="media" role="img" aria-label="${escapeHtml(alt)}"></div>`;
  return `<img class="media" src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" loading="lazy">`;
}

function promptCard(item) {
  return `
    <article class="paper-card">
      <p class="sticker pink">${escapeHtml(item.status || "prompt")}</p>
      ${imageBlock(item.preview_url, item.title || "Prompt preview")}
      <h3>${escapeHtml(item.title || "Untitled prompt")}</h3>
      <p class="card-text">${escapeHtml(item.description || item.prompt_text || "")}</p>
      <div class="metric-row">
        <span class="metric">${Number(item.likes || 0)} likes</span>
        <span class="metric">${Number(item.uses_count || 0)} uses</span>
      </div>
      <a class="action" href="#/prompt-detail?id=${encodeURIComponent(item.id)}">Open</a>
    </article>
  `;
}

function feedCard(item) {
  return `
    <article class="dark-card feed-card">
      <p class="sticker cyan">${escapeHtml(item.author || "anon")}</p>
      ${imageBlock(item.result_url, "Feed generation")}
      <h3>${escapeHtml(item.model || "Model")}</h3>
      <p class="card-text">${escapeHtml(item.prompt || "")}</p>
      <div class="metric-row">
        <span class="metric">${Number(item.likes || 0)} likes</span>
        <span class="metric">${Number(item.shares || 0)} shares</span>
        <span class="metric">${Number(item.remix_count || 0)} remixes</span>
      </div>
    </article>
  `;
}

function generationCard(item) {
  return `
    <article class="dark-card">
      <p class="sticker ${item.status === "done" ? "cyan" : "pink"}">${escapeHtml(item.status || "status")}</p>
      ${imageBlock(item.result_url, "Generation result")}
      <h3>${escapeHtml(item.model || "Model")}</h3>
      <p class="card-text">${escapeHtml(item.prompt || "")}</p>
      <div class="metric-row">
        <span class="metric">${escapeHtml(item.gen_type || "generation")}</span>
        <span class="metric">${Number(item.credits_spent || 0)} credits</span>
      </div>
    </article>
  `;
}

function screenHeader(sticker, title, text) {
  return `
    <section class="screen">
      <article class="paper-card pink">
        <p class="sticker cyan">${escapeHtml(sticker)}</p>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(text)}</p>
      </article>
    </section>
  `;
}

function renderHome() {
  const feed = Array.isArray(state.feed) ? state.feed.slice(0, 3) : [];
  const prompts = state.prompts?.items ? state.prompts.items.slice(0, 3) : [];
  return `
    <section class="hero">
      <div>
        <p class="sticker pink">WEB LAYER LIVE</p>
        <h1>Artflow<br><span class="riot-word">Prompt Riot</span></h1>
        <p class="lede">A raw studio shell for active series, public remix feed, prompt marketplace, billing, and Telegram identity sync.</p>
        <div class="hero-actions">
          <a class="action primary" href="#/studio">Open Studio</a>
          <a class="action" href="#/prompts">Browse Prompts</a>
          <a class="action" href="#/auth">Connect Telegram</a>
        </div>
      </div>
      <div class="poster-stack" aria-hidden="true">
        <div class="poster one"><span>series</span><b>keep the thread</b></div>
        <div class="poster two"><span>remix</span><b>feed back into art</b></div>
        <div class="poster three"><span>market</span><b>prompts with teeth</b></div>
      </div>
    </section>
    <section class="grid">${feed.length ? feed.map(feedCard).join("") : empty("Feed is empty or not reachable.", state.errors.feed)}</section>
    <section class="grid">${prompts.length ? prompts.map(promptCard).join("") : empty("Prompt marketplace is empty or not reachable.", state.errors.prompts)}</section>
  `;
}

function renderAuth() {
  const user = state.me;
  return `
    ${screenHeader("TELEGRAM SYNC", user ? "Connected" : "Connect Your Telegram Identity", user ? `Balance: ${user.credits} credits` : "Dev auth is available only when APIX_WEB_DEV_AUTH=1.")}
    <section class="panel-grid">
      <article class="paper-card">
        <h3>Dev Header</h3>
        <p class="muted">For local review, save a Telegram id and refresh API calls.</p>
        <form class="form" id="dev-auth-form">
          <label class="field"><span>X-Dev-Tg-Id</span><input name="tg_id" value="${escapeHtml(localStorage.getItem("apix_dev_tg_id") || "")}" inputmode="numeric"></label>
          <button class="action primary" type="submit">Save</button>
        </form>
      </article>
      <article class="dark-card">
        <h3>Current User</h3>
        ${user ? `<p class="mono">@${escapeHtml(user.username || "user")} / tg ${escapeHtml(user.tg_id)}</p><p>${escapeHtml(user.full_name || "")}</p>` : empty("No authenticated web user.", state.errors.me)}
      </article>
    </section>
  `;
}

function renderStudio() {
  const session = state.session;
  const models = Array.isArray(state.models) ? state.models.slice(0, 8) : [];
  return `
    ${screenHeader("ACTIVE SERIES", "Studio", "A calm workbench inside the zine wall. Generation launch endpoints are intentionally not faked yet.")}
    <section class="panel-grid">
      <article class="paper-card yellow">
        <h3>Session</h3>
        ${session ? `<p class="mono">#${session.id} ${escapeHtml(session.model)}</p><p>${escapeHtml(session.aspect_ratio || "auto")} / ${escapeHtml(session.quality || "basic")}</p>` : empty("No active image session.", state.errors.session)}
      </article>
      <article class="dark-card">
        <form class="form">
          <label class="field"><span>Model</span><select>${models.map((m) => `<option>${escapeHtml(m.display_name || m.model_key)}</option>`).join("")}</select></label>
          <label class="field"><span>Prompt</span><textarea placeholder="Paste a prompt, remix idea, or visual direction"></textarea></label>
          <div class="toolbar"><button class="action primary" type="button">Generate later</button><a class="action" href="#/feed">Remix Feed</a></div>
        </form>
      </article>
    </section>
  `;
}

function renderPrompts() {
  const items = state.prompts?.items || [];
  return `
    ${screenHeader("PROMPT LIBRARY", "Marketplace", "Browse approved prompts from the existing Artflow prompt repository.")}
    <div class="toolbar">
      ${["trending", "best", "characters", "realism", "cinematic", "nsfw", "music"].map((x) => `<span class="pill">${x}</span>`).join("")}
    </div>
    <section class="grid">${items.length ? items.map(promptCard).join("") : empty("No prompts returned.", state.errors.prompts)}</section>
  `;
}

function selectedPrompt() {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const id = params.get("id");
  const items = state.prompts?.items || [];
  return items.find((item) => String(item.id) === String(id)) || items[0];
}

function renderPromptDetail() {
  const item = selectedPrompt();
  if (!item) return `${screenHeader("PROMPT DETAIL", "No Prompt Loaded", "Open a prompt from the marketplace first.")}`;
  return `
    ${screenHeader("REMIX CARD", item.title || "Prompt Detail", item.description || "Full prompt text below.")}
    <section class="grid two">
      <article class="paper-card">${imageBlock(item.preview_url, item.title)}<div class="metric-row"><span class="metric">${Number(item.likes || 0)} likes</span><span class="metric">${Number(item.uses_count || 0)} uses</span></div></article>
      <article class="dark-card"><p class="mono">${escapeHtml(item.prompt_text || "")}</p><div class="toolbar"><a class="action primary" href="#/studio">Use In Studio</a><a class="action" href="#/add-prompt">Submit Variant</a></div></article>
    </section>
  `;
}

function renderAddPrompt() {
  return `
    ${screenHeader("ADD PROMPT", "Submit To Moderation", "Submission API lands in a later phase, so this form is a readable prototype for now.")}
    <article class="paper-card">
      <form class="form">
        <label class="field"><span>Preview URL</span><input placeholder="https://..."></label>
        <label class="field"><span>Title</span><input placeholder="Optional title"></label>
        <label class="field"><span>Prompt Text</span><textarea placeholder="Required prompt text"></textarea></label>
        <button class="action primary" type="button">Submit later</button>
      </form>
    </article>
  `;
}

function renderFeed() {
  const items = Array.isArray(state.feed) ? state.feed : [];
  return `
    ${screenHeader("REMIX FEED", "Public Works", "Cards are serialized from repo.get_feed_generations and top-day feed logic.")}
    <section class="grid">${items.length ? items.map(feedCard).join("") : empty("Feed returned no public cards.", state.errors.feed)}</section>
  `;
}

function renderWorks() {
  const items = Array.isArray(state.history) ? state.history : [];
  return `
    ${screenHeader("MY WORKS", "History", "Authenticated history uses the same Generation records as the bot.")}
    <section class="grid">${items.length ? items.map(generationCard).join("") : empty("No authenticated history yet.", state.errors.history)}</section>
  `;
}

function renderBilling() {
  const plans = Array.isArray(state.plans) ? state.plans : [];
  return `
    ${screenHeader("BALANCE", "Billing", "Price plans are read from active PricePlan rows. Payment creation is later-phase work.")}
    <section class="grid">${plans.length ? plans.map((p) => `
      <article class="paper-card cyan">
        <p class="sticker pink">${escapeHtml(p.key)}</p>
        <h3>${escapeHtml(p.label)}</h3>
        <p><b>${Number(p.credits || 0)}</b> credits</p>
        <p class="mono">${Number(p.price_rub || 0)} RUB${p.price_stars ? ` / ${p.price_stars} Stars` : ""}</p>
      </article>`).join("") : empty("No active price plans returned.", state.errors.plans)}</section>
  `;
}

function renderProfile() {
  const user = state.me;
  return `
    ${screenHeader("PROFILE", "Referrals", "Referral API is later-phase work; identity and balance are live now when dev auth is enabled.")}
    <section class="grid two">
      <article class="paper-card">${user ? `<h3>${escapeHtml(user.full_name || user.username || "User")}</h3><p class="mono">tg ${escapeHtml(user.tg_id)}</p><p>${Number(user.credits || 0)} credits</p>` : empty("Not connected.", state.errors.me)}</article>
      <article class="dark-card"><h3>Referral Code</h3><p class="mono">${escapeHtml(user?.referral_code || "connect first")}</p></article>
    </section>
  `;
}

function renderAdmin() {
  return `
    ${screenHeader("ADMIN", "Moderation Board", "Admin moderation API is not part of this frontend phase.")}
    <section class="columns">
      <div class="column"><p class="sticker pink">pending</p>${empty("Prompt queue endpoint not wired yet.")}</div>
      <div class="column"><p class="sticker cyan">approved</p>${empty("Approved prompts are visible in Marketplace.")}</div>
      <div class="column"><p class="sticker">rejected</p>${empty("Rejected queue endpoint not wired yet.")}</div>
    </section>
  `;
}

const renderers = {
  home: renderHome,
  auth: renderAuth,
  studio: renderStudio,
  prompts: renderPrompts,
  "prompt-detail": renderPromptDetail,
  "add-prompt": renderAddPrompt,
  feed: renderFeed,
  works: renderWorks,
  billing: renderBilling,
  profile: renderProfile,
  admin: renderAdmin,
};

function bindForms() {
  const form = document.getElementById("dev-auth-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const value = new FormData(form).get("tg_id");
      if (value) localStorage.setItem("apix_dev_tg_id", String(value).trim());
      else localStorage.removeItem("apix_dev_tg_id");
      await boot();
    });
  }
}

async function boot() {
  root.innerHTML = document.getElementById("loading-template").innerHTML;
  await loadData();
  const name = routeName();
  root.innerHTML = renderers[name]();
  setActiveNav();
  bindForms();
  root.focus({ preventScroll: true });
}

window.addEventListener("hashchange", boot);
boot();
