from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("artflow")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if content.count(old) != 1:
        raise RuntimeError(f"Expected one occurrence in {path}: {old[:100]!r}, found {content.count(old)}")
    write(path, content.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    content = read(path)
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Pattern not found exactly once in {path}: {pattern[:120]!r}; count={count}")
    write(path, updated)


# ---------------------------------------------------------------------------
# Backend: trend category contract stored in the existing tag array.
# ---------------------------------------------------------------------------
write(
    "core/trends.py",
    '''from __future__ import annotations

from datetime import datetime
from typing import Any

from db.models import PromptStatus, UserPrompt

TREND_TAG = "trend"
TREND_VIDEO_TAG = "trend-video"
TREND_PREFIX = "trend-"
TREND_CATEGORY_PREFIX = "trend-category:"
DEFAULT_TREND_CATEGORY = "featured"
TREND_CATEGORIES: dict[str, dict[str, str]] = {
    "featured": {"title": "Тренды", "emoji": "🔥"},
    "photo-video": {"title": "Фото → видео", "emoji": "🎬"},
    "portrait": {"title": "Портреты", "emoji": "✨"},
    "cartoon": {"title": "Мультфильм", "emoji": "🎨"},
    "animals": {"title": "С животными", "emoji": "🦁"},
    "holidays": {"title": "Праздники", "emoji": "🎉"},
    "style": {"title": "Образы", "emoji": "💫"},
}


def normalized_tags(prompt_or_tags: UserPrompt | list[str] | tuple[str, ...] | None) -> set[str]:
    raw = getattr(prompt_or_tags, "tags", prompt_or_tags) or []
    return {str(item).strip().lower() for item in raw if str(item or "").strip()}


def is_trend_prompt(prompt: UserPrompt | None) -> bool:
    return bool(prompt and TREND_TAG in normalized_tags(prompt))


def trend_kind(prompt: UserPrompt) -> str:
    tags = normalized_tags(prompt)
    return "video" if TREND_VIDEO_TAG in tags else "image"


def _tag_value(tags: set[str], prefix: str) -> str | None:
    for tag in tags:
        if tag.startswith(prefix):
            value = tag[len(prefix):].strip()
            if value:
                return value
    return None


def normalize_trend_category(value: Any) -> str:
    category = str(value or "").strip().lower()
    return category if category in TREND_CATEGORIES else DEFAULT_TREND_CATEGORY


def trend_category(prompt: UserPrompt) -> str:
    return normalize_trend_category(_tag_value(normalized_tags(prompt), TREND_CATEGORY_PREFIX))


def trend_category_payload(category: str) -> dict[str, str]:
    key = normalize_trend_category(category)
    meta = TREND_CATEGORIES[key]
    return {"key": key, "title": meta["title"], "emoji": meta["emoji"]}


def trend_settings(prompt: UserPrompt) -> dict[str, Any]:
    tags = normalized_tags(prompt)
    kind = trend_kind(prompt)
    duration_raw = _tag_value(tags, "trend-duration:")
    try:
        duration = int(duration_raw) if duration_raw else None
    except (TypeError, ValueError):
        duration = None

    requires_reference = "trend-requires-reference" in tags
    scenario = _tag_value(tags, "trend-scenario:")
    if scenario in {"image", "imgtxt", "i2v"}:
        requires_reference = True

    return {
        "scenario": scenario or ("image" if requires_reference else "text"),
        "duration": duration,
        "ratio": _tag_value(tags, "trend-ratio:"),
        "quality": _tag_value(tags, "trend-quality:"),
        "resolution": _tag_value(tags, "trend-resolution:"),
        "requires_reference": requires_reference,
        "kind": kind,
        "category": trend_category(prompt),
    }


def build_trend_tags(kind: str, settings: dict[str, Any] | None = None) -> list[str]:
    kind = "video" if str(kind).lower() == "video" else "image"
    settings = dict(settings or {})
    tags = [TREND_TAG, f"{TREND_CATEGORY_PREFIX}{normalize_trend_category(settings.get('category'))}"]
    if kind == "video":
        tags.append(TREND_VIDEO_TAG)

    scenario = str(settings.get("scenario") or "").strip().lower()
    if scenario:
        tags.append(f"trend-scenario:{scenario}")
    duration = settings.get("duration")
    if duration not in (None, ""):
        tags.append(f"trend-duration:{int(duration)}")
    ratio = str(settings.get("ratio") or "").strip()
    if ratio:
        tags.append(f"trend-ratio:{ratio}")
    quality = str(settings.get("quality") or "").strip()
    if quality:
        tags.append(f"trend-quality:{quality}")
    resolution = str(settings.get("resolution") or "").strip()
    if resolution:
        tags.append(f"trend-resolution:{resolution}")
    if bool(settings.get("requires_reference")):
        tags.append("trend-requires-reference")
    return list(dict.fromkeys(tags))


def trend_is_public(prompt: UserPrompt | None) -> bool:
    return bool(
        is_trend_prompt(prompt)
        and prompt.status == PromptStatus.approved
        and prompt.is_public
    )


def trend_public_payload(prompt: UserPrompt) -> dict[str, Any]:
    created_at: datetime | None = getattr(prompt, "created_at", None)
    category = trend_category_payload(trend_category(prompt))
    return {
        "id": int(prompt.id),
        "kind": trend_kind(prompt),
        "category": category["key"],
        "category_title": category["title"],
        "category_emoji": category["emoji"],
        "title": prompt.title,
        "description": prompt.description,
        "preview_url": prompt.preview_url,
        "model": prompt.model,
        "settings": trend_settings(prompt),
        "uses_count": int(prompt.uses_count or 0),
        "likes": int(prompt.likes or 0),
        "created_at": created_at.isoformat() if created_at else "",
    }


def trend_admin_payload(prompt: UserPrompt) -> dict[str, Any]:
    payload = trend_public_payload(prompt)
    payload.update({
        "prompt_template": prompt.prompt_text,
        "status": getattr(prompt.status, "value", str(prompt.status)),
        "is_public": bool(prompt.is_public),
        "author_id": int(prompt.author_id),
    })
    return payload
''',
)

# ---------------------------------------------------------------------------
# Telegram admin flow: category is selected by admin before the model.
# ---------------------------------------------------------------------------
replace_once(
    "bot/handlers/trends.py",
    "from core.trends import (\n    TREND_TAG,",
    "from core.trends import (\n    TREND_CATEGORIES,\n    TREND_TAG,",
)
replace_once(
    "bot/handlers/trends.py",
    "    description = State()\n    model = State()",
    "    description = State()\n    category = State()\n    model = State()",
)
regex_once(
    "bot/handlers/trends.py",
    r'''@router\.message\(TrendAdminFSM\.description, IsAdmin\(\)\)\nasync def trend_description\(.*?\n\n@router\.callback_query\(TrendAdminFSM\.model,''',
    '''@router.message(TrendAdminFSM.description, IsAdmin())
async def trend_description(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if len(value) > 200:
        await message.answer("Описание длиннее 200 символов.")
        return
    await state.update_data(description=value)
    await state.set_state(TrendAdminFSM.category)
    builder = InlineKeyboardBuilder()
    for key, meta in TREND_CATEGORIES.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{meta['emoji']} {meta['title']}",
                callback_data=f"trends:category:{key}",
            )
        )
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await message.answer("Выбери категорию витрины:", reply_markup=builder.as_markup())


@router.callback_query(TrendAdminFSM.category, F.data.startswith("trends:category:"), IsAdmin())
async def trend_category_pick(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    if category not in TREND_CATEGORIES:
        await call.answer("Категория не найдена", show_alert=True)
        return
    data = await state.get_data()
    kind = data.get("kind", "image")
    models = [
        item for item in await repo.get_all_model_costs(session)
        if getattr(getattr(item, "gen_type", None), "value", None) == kind and getattr(item, "is_active", True)
    ]
    if not models:
        await call.message.answer("Нет активных моделей этого типа.", reply_markup=back_to_menu_kb())
        await state.clear()
        return
    await state.update_data(category=category)
    await state.set_state(TrendAdminFSM.model)
    builder = InlineKeyboardBuilder()
    for item in models:
        builder.row(InlineKeyboardButton(text=item.display_name[:50], callback_data=f"trends:model:{item.model_key}"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await call.message.answer("Выбери модель:", reply_markup=builder.as_markup())
    await safe_answer_callback(call)


@router.callback_query(TrendAdminFSM.model,''',
)
replace_once(
    "bot/handlers/trends.py",
    '''    settings_payload = {
        "scenario": data.get("scenario"),''',
    '''    settings_payload = {
        "category": data.get("category", "featured"),
        "scenario": data.get("scenario"),''',
)

# ---------------------------------------------------------------------------
# Mini App: category-first home, compact discovery cards, 5-tab navigation.
# ---------------------------------------------------------------------------
replace_once(
    "webapp/src/main.jsx",
    'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-compact-feed-v3";',
    'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-trend-category-home-v4";',
)

regex_once(
    "webapp/src/main.jsx",
    r'''function Nav\(\{ screen, setScreen \}\) \{.*?\n\}\n\n// ── TopUp modal''',
    '''function Nav({ screen, setScreen }) {
  const tabs = [
    ["home", "⌂", "Главная", ""],
    ["feed", "▤", "Лента", ""],
    ["studio", "+", "Создать", "navCreate"],
    ["assistant", "◯", "AI", ""],
    ["profile", "♙", "Профиль", ""],
  ];
  return (
    <div className="nav">
      {tabs.map(([id, ic, label, extraClass]) => (
        <button
          key={id}
          onClick={() => setScreen(id)}
          className={`${screen === id ? "on" : ""} ${extraClass}`.trim()}
        >
          <b>{ic}</b><small>{label}</small>
        </button>
      ))}
    </div>
  );
}

// ── TopUp modal''',
)

regex_once(
    "webapp/src/main.jsx",
    r'''function Home\(.*?\n\}\n\n// ── Feed screen''',
    '''const TREND_CATEGORY_META = [
  { key: "featured", title: "Тренды", emoji: "🔥" },
  { key: "photo-video", title: "Фото → видео", emoji: "🎬" },
  { key: "portrait", title: "Портреты", emoji: "✨" },
  { key: "cartoon", title: "Мультфильм", emoji: "🎨" },
  { key: "animals", title: "С животными", emoji: "🦁" },
  { key: "holidays", title: "Праздники", emoji: "🎉" },
  { key: "style", title: "Образы", emoji: "💫" },
];

function trendCategoryMeta(itemOrKey) {
  const key = typeof itemOrKey === "string" ? itemOrKey : itemOrKey?.category || itemOrKey?.settings?.category || "featured";
  const known = TREND_CATEGORY_META.find((item) => item.key === key) || TREND_CATEGORY_META[0];
  if (typeof itemOrKey === "object" && itemOrKey) {
    return {
      ...known,
      title: itemOrKey.category_title || known.title,
      emoji: itemOrKey.category_emoji || known.emoji,
    };
  }
  return known;
}

function TrendDiscoveryCard({ item, onApply, onShare, onArchive, manage = false }) {
  const category = trendCategoryMeta(item);
  const settings = item.settings || {};
  const isVideo = item.kind === "video";
  return (
    <article className={`trendDiscoveryCard ${manage ? "manage" : ""}`}>
      <button className="trendDiscoveryMedia" onClick={() => onApply?.(item)} aria-label={`Открыть тренд ${item.title}`}>
        {item.preview_url ? (
          isVideo
            ? <video src={item.preview_url} muted loop autoPlay playsInline preload="metadata" />
            : <img src={item.preview_url} alt={item.title || "Тренд"} loading="lazy" />
        ) : <Art type="a" />}
        <span className="trendKindBadge">{isVideo ? "▻ Видео" : "▧ Фото"}</span>
        {(settings.requires_reference || settings.scenario === "image") && <span className="trendReferenceBadge">＋ фото</span>}
        <div className="trendDiscoveryCaption">
          <small>{category.emoji} {category.title}</small>
          <b>{item.title}</b>
          {item.description && <span>{item.description}</span>}
        </div>
      </button>
      {manage && (
        <div className="trendManageActions">
          <button className="primary" onClick={() => onApply?.(item)}>Повторить</button>
          <button onClick={() => onShare?.(item)}>↗</button>
          <button className="dangerAction" onClick={() => onArchive?.(item)}>×</button>
        </div>
      )}
    </article>
  );
}

function Home({ user, trends, loading, setScreen, onApply, openStudioKind }) {
  const [activeCategory, setActiveCategory] = useState("all");
  const availableCategories = TREND_CATEGORY_META.filter((meta) => (trends || []).some((item) => trendCategoryMeta(item).key === meta.key));
  const sections = (activeCategory === "all" ? availableCategories : availableCategories.filter((meta) => meta.key === activeCategory))
    .map((meta) => ({ ...meta, items: (trends || []).filter((item) => trendCategoryMeta(item).key === meta.key) }))
    .filter((section) => section.items.length);

  const shortcuts = [
    ["▧", "Картинка", () => openStudioKind?.("image")],
    ["▻", "Видео", () => openStudioKind?.("video")],
    ["✦", "Промпт по фото", () => setScreen("prompts")],
    ["♫", "Звук", () => setScreen("music")],
    ["MJ", "Midjourney", () => setScreen("midjourney")],
  ];

  return (
    <div className="trendHome">
      <div className="trendQuickRail" aria-label="Быстрые инструменты">
        {shortcuts.map(([icon, label, action]) => (
          <button key={label} className="trendQuickTool" onClick={action}>
            <b>{icon}</b><span>{label}</span>
          </button>
        ))}
      </div>

      <section className="trendHomeHero">
        <div>
          <span className="trendEyebrow">Готовые сценарии</span>
          <h1>Тренды</h1>
          <p>Выбери эффект, добавь своё фото и получи результат без ручной настройки модели.</p>
        </div>
        {user.is_admin && <button onClick={() => setScreen("trends")}>Управление</button>}
      </section>

      <div className="trendCategoryTabs" role="tablist" aria-label="Категории трендов">
        <button className={activeCategory === "all" ? "active" : ""} onClick={() => setActiveCategory("all")}>Все</button>
        {availableCategories.map((meta) => (
          <button key={meta.key} className={activeCategory === meta.key ? "active" : ""} onClick={() => setActiveCategory(meta.key)}>
            {meta.emoji} {meta.title}
          </button>
        ))}
      </div>

      {loading ? <Spinner /> : sections.length ? sections.map((section) => (
        <section className="trendDiscoverySection" key={section.key}>
          <div className="trendSectionHead">
            <div><h2>{section.emoji} {section.title}</h2><p>{section.items.length} шаблонов</p></div>
            {activeCategory === "all" && <button onClick={() => setActiveCategory(section.key)}>Все</button>}
          </div>
          <div className="trendDiscoveryRail">
            {section.items.map((item) => <TrendDiscoveryCard key={item.id} item={item} onApply={onApply} />)}
          </div>
        </section>
      )) : (
        <div className="trendHomeEmpty">
          <b>Тренды пока не опубликованы</b>
          <span>После добавления администратором они появятся здесь по категориям.</span>
          {user.is_admin && <button className="primary" onClick={() => setScreen("trends")}>Добавить первый тренд</button>}
        </div>
      )}
    </div>
  );
}

// ── Feed screen''',
)

# Add category state and selector to the Mini App admin form.
replace_once(
    "webapp/src/main.jsx",
    '  const [description, setDescription] = useState("");\n  const [model, setModel] = useState("");',
    '  const [description, setDescription] = useState("");\n  const [category, setCategory] = useState("featured");\n  const [model, setModel] = useState("");',
)
replace_once(
    "webapp/src/main.jsx",
    '''          settings: {
            scenario: kind === "video" ? scenario : undefined,''',
    '''          settings: {
            category,
            scenario: kind === "video" ? scenario : undefined,''',
)
replace_once(
    "webapp/src/main.jsx",
    '''      <textarea className="field" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Публичное описание — до 200 символов" maxLength={200} />
      <select value={model} onChange={(e) => setModel(e.target.value)}>''',
    '''      <textarea className="field" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Публичное описание — до 200 символов" maxLength={200} />
      <select value={category} onChange={(e) => setCategory(e.target.value)}>
        {TREND_CATEGORY_META.map((item) => <option key={item.key} value={item.key}>{item.emoji} {item.title}</option>)}
      </select>
      <select value={model} onChange={(e) => setModel(e.target.value)}>''',
)

regex_once(
    "webapp/src/main.jsx",
    r'''function Trends\(\{ trends, loading, user, imageModels, videoModels, reload, onApply, onNotice \}\) \{.*?\n\}\n\n// ── Post-generation share buttons''',
    '''function Trends({ trends, loading, user, imageModels, videoModels, reload, onApply, onNotice }) {
  const [adminOpen, setAdminOpen] = useState(false);

  async function share(item) {
    try {
      const result = await api(`/trends/${item.id}/link`);
      const ok = result.link ? await copyText(result.link) : false;
      onNotice?.({ type: ok ? "success" : "error", message: ok ? "Ссылка на тренд скопирована" : "Не удалось получить ссылку" });
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось получить ссылку" });
    }
  }

  async function archive(item) {
    if (!window.confirm(`Убрать тренд «${item.title}»?`)) return;
    try {
      await api(`/admin/trends/${item.id}/archive`, { method: "POST" });
      onNotice?.({ type: "success", message: "Тренд скрыт" });
      reload?.();
    } catch (e) {
      onNotice?.({ type: "error", message: e.message || "Не удалось скрыть тренд" });
    }
  }

  const sections = TREND_CATEGORY_META
    .map((meta) => ({ ...meta, items: (trends || []).filter((item) => trendCategoryMeta(item).key === meta.key) }))
    .filter((section) => section.items.length);

  if (loading) return <><h1>Тренды</h1><Spinner /></>;
  return (
    <>
      <div className="trendManagerHead">
        <div><h1>Тренды</h1><p>Категории и шаблоны задаёт администратор.</p></div>
        {user.is_admin && <button className="primary" onClick={() => setAdminOpen((value) => !value)}>{adminOpen ? "Закрыть" : "+ Добавить"}</button>}
      </div>
      {user.is_admin && adminOpen && <TrendAdminForm imageModels={imageModels} videoModels={videoModels} onCreated={() => { reload?.(); setAdminOpen(false); }} onNotice={onNotice} />}
      {sections.map((section) => (
        <section className="trendDiscoverySection" key={section.key}>
          <div className="trendSectionHead"><div><h2>{section.emoji} {section.title}</h2><p>{section.items.length} шаблонов</p></div></div>
          <div className="trendManageGrid">
            {section.items.map((item) => (
              <TrendDiscoveryCard key={item.id} item={item} onApply={onApply} onShare={share} onArchive={archive} manage={user.is_admin} />
            ))}
          </div>
        </section>
      ))}
      {!sections.length && <div className="trendHomeEmpty"><b>Нет опубликованных трендов</b><span>Добавь первый шаблон и выбери для него категорию.</span></div>}
    </>
  );
}

// ── Post-generation share buttons''',
)

replace_once(
    "webapp/src/main.jsx",
    '''  function openStudioPreset(item) {
    setRemixSource(null);''',
    '''  function openStudioKind(kind = "image") {
    setRemixSource(null);
    setGeneration(null);
    setStudioPreset({ kind });
    setScreen("studio");
  }

  function openStudioPreset(item) {
    setRemixSource(null);''',
)

regex_once(
    "webapp/src/main.jsx",
    r'''    home: <Home .*? />,\n    capabilities:''',
    '''    home: <Home user={user} trends={curatedTrends.data} loading={curatedTrends.loading} setScreen={navigate} onApply={openTrendPreset} openStudioKind={openStudioKind} />,
    capabilities:''',
)

# ---------------------------------------------------------------------------
# Visual system for the trend-first home and centered create button.
# ---------------------------------------------------------------------------
style_path = ROOT / "webapp/src/style.css"
style = style_path.read_text(encoding="utf-8")
style += r'''

/* category-first trend home */
.trendHome{display:grid;gap:18px}
.trendQuickRail{display:flex;gap:12px;overflow-x:auto;margin:2px -16px 0;padding:4px 16px 8px;scroll-snap-type:x proximity;scrollbar-width:none}
.trendQuickRail::-webkit-scrollbar{display:none}
.trendQuickTool{flex:0 0 84px;display:grid;gap:7px;justify-items:center;background:transparent;color:var(--text-soft);scroll-snap-align:start}
.trendQuickTool b{display:grid;place-items:center;width:64px;height:64px;border:1px solid var(--border-strong);border-radius:20px;background:linear-gradient(145deg,var(--surface-3),var(--surface));color:var(--text);font-size:24px;font-weight:700;box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.trendQuickTool span{font-size:11px;line-height:1.2;text-align:center}
.trendHomeHero{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;padding:18px;border:1px solid var(--border-soft);border-radius:24px;background:radial-gradient(circle at 88% 15%,var(--accent-soft),transparent 44%),linear-gradient(145deg,var(--surface-2),var(--surface));overflow:hidden}
.trendHomeHero h1{margin:3px 0 5px;font-size:30px;line-height:1;font-weight:800}
.trendHomeHero p{max-width:310px;margin:0;color:var(--text-soft);font-size:13px;line-height:1.45}
.trendHomeHero>button{flex:0 0 auto;padding:8px 11px;border:1px solid var(--accent-border);border-radius:12px;background:var(--accent-soft);color:var(--accent-text);font-size:11px;font-weight:750}
.trendEyebrow{color:var(--accent-text);font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}
.trendCategoryTabs{display:flex;gap:7px;overflow-x:auto;margin:0 -16px;padding:0 16px 3px;scrollbar-width:none}
.trendCategoryTabs::-webkit-scrollbar{display:none}
.trendCategoryTabs button{flex:0 0 auto;padding:8px 12px;border:1px solid var(--border);border-radius:999px;background:var(--surface);color:var(--text-soft);font-size:11px;font-weight:700;white-space:nowrap}
.trendCategoryTabs button.active{border-color:var(--accent-border);background:var(--accent-soft);color:var(--accent-text)}
.trendDiscoverySection{display:grid;gap:10px;margin-top:3px}
.trendSectionHead{display:flex;align-items:center;justify-content:space-between;gap:10px}
.trendSectionHead h2{margin:0;font-size:19px;font-weight:780}
.trendSectionHead p{margin:2px 0 0;color:var(--text-ghost);font-size:10px}
.trendSectionHead>button{padding:7px 11px;border:1px solid var(--border);border-radius:11px;background:var(--surface-2);color:var(--text-soft);font-size:11px;font-weight:700}
.trendDiscoveryRail{display:flex;gap:10px;overflow-x:auto;margin:0 -16px;padding:0 16px 5px;scroll-snap-type:x mandatory;scrollbar-width:none}
.trendDiscoveryRail::-webkit-scrollbar{display:none}
.trendDiscoveryRail .trendDiscoveryCard{flex:0 0 min(72vw,230px);scroll-snap-align:start}
.trendDiscoveryCard{min-width:0;border:1px solid var(--border-soft);border-radius:18px;background:var(--surface);overflow:hidden;box-shadow:0 10px 28px rgba(0,0,0,.14)}
.trendDiscoveryMedia{position:relative;display:block;width:100%;padding:0;aspect-ratio:4/5;background:var(--bg-strong);overflow:hidden;text-align:left}
.trendDiscoveryMedia img,.trendDiscoveryMedia video,.trendDiscoveryMedia .art{width:100%;height:100%;object-fit:cover}
.trendKindBadge,.trendReferenceBadge{position:absolute;top:9px;z-index:2;padding:4px 7px;border:1px solid rgba(255,255,255,.18);border-radius:9px;background:rgba(5,7,16,.64);backdrop-filter:blur(10px);color:#fff;font-size:9px;font-weight:800}
.trendKindBadge{right:9px}
.trendReferenceBadge{left:9px}
.trendDiscoveryCaption{position:absolute;left:0;right:0;bottom:0;display:grid;gap:3px;padding:42px 12px 12px;background:linear-gradient(180deg,transparent,rgba(2,4,12,.92));color:#fff}
.trendDiscoveryCaption small{font-size:9px;font-weight:750;color:rgba(255,255,255,.74)}
.trendDiscoveryCaption b{font-size:16px;line-height:1.15;text-shadow:0 2px 8px rgba(0,0,0,.55)}
.trendDiscoveryCaption span{display:-webkit-box;overflow:hidden;-webkit-box-orient:vertical;-webkit-line-clamp:2;color:rgba(255,255,255,.72);font-size:10px;line-height:1.35}
.trendManageGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.trendManageGrid .trendDiscoveryMedia{aspect-ratio:3/4}
.trendManageActions{display:grid;grid-template-columns:1fr 34px 34px;gap:5px;padding:6px}
.trendManageActions button{min-width:0;height:32px;border:1px solid var(--border-strong);border-radius:9px;background:var(--surface-2);font-size:10px;font-weight:800}
.trendManageActions .primary{border-color:var(--accent-border)}
.trendManagerHead{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px}
.trendManagerHead h1{font-size:26px}
.trendManagerHead p{margin:4px 0 0;color:var(--text-soft);font-size:12px}
.trendManagerHead>button{padding:9px 12px;border-radius:12px;font-size:12px}
.trendHomeEmpty{display:grid;justify-items:center;gap:7px;padding:30px 18px;border:1px dashed var(--border-strong);border-radius:20px;text-align:center}
.trendHomeEmpty b{font-size:15px}
.trendHomeEmpty span{max-width:290px;color:var(--text-ghost);font-size:12px}
.trendHomeEmpty button{margin-top:5px;padding:10px 14px;border-radius:12px}

/* reference-style five-tab navigation with central create action */
.nav{grid-template-columns:repeat(5,1fr);align-items:end;padding:7px 10px}
.nav button{min-width:0}
.nav .navCreate{position:relative;transform:translateY(-12px);color:#fff}
.nav .navCreate b{display:grid;place-items:center;width:54px;height:54px;margin:0 auto -2px;border-radius:999px;background:linear-gradient(145deg,var(--accent),#4f7cff);box-shadow:0 10px 28px rgba(59,150,255,.34);font-size:32px;font-weight:300;line-height:1}
.nav .navCreate small{color:var(--text-soft)}
.nav .navCreate.on{background:transparent}

@media (max-width:360px){
  .trendQuickTool{flex-basis:74px}
  .trendQuickTool b{width:58px;height:58px;border-radius:18px}
  .trendHomeHero{padding:15px}
  .trendHomeHero h1{font-size:27px}
  .trendDiscoveryRail .trendDiscoveryCard{flex-basis:72vw}
  .trendManageGrid{gap:7px}
}
'''
style_path.write_text(style, encoding="utf-8")

# ---------------------------------------------------------------------------
# Docs and tests.
# ---------------------------------------------------------------------------
docs = read("docs/trends.md")
docs += '''\n\n## Категории и стартовый экран Mini App\n\nГлавный экран Mini App является витриной админских трендов. Администратор выбирает категорию при публикации; категория хранится в системном теге `trend-category:<slug>`. Старые записи без тега относятся к `featured`. Публичный API возвращает `category`, `category_title` и `category_emoji`, но по-прежнему не возвращает канонический prompt.\n'''
write("docs/trends.md", docs)

write(
    "tests/test_trend_category_home.py",
    '''from __future__ import annotations

from types import SimpleNamespace

from core.trends import (
    DEFAULT_TREND_CATEGORY,
    TREND_CATEGORIES,
    build_trend_tags,
    trend_category,
    trend_public_payload,
    trend_settings,
)
from db.models import PromptStatus


def _prompt(tags: list[str]):
    return SimpleNamespace(
        id=1,
        author_id=1,
        title="Lion portrait",
        description="Reference-driven portrait",
        prompt_text="SECRET",
        preview_url="https://cdn.example/trend.jpg",
        model="nano-banana-pro",
        tags=tags,
        likes=0,
        uses_count=3,
        status=PromptStatus.approved,
        is_public=True,
        created_at=None,
    )


def test_category_roundtrip_in_existing_tags_storage():
    item = _prompt(build_trend_tags("image", {"category": "animals", "ratio": "4:5"}))
    assert trend_category(item) == "animals"
    assert trend_settings(item)["category"] == "animals"
    payload = trend_public_payload(item)
    assert payload["category"] == "animals"
    assert payload["category_title"] == TREND_CATEGORIES["animals"]["title"]
    assert payload["category_emoji"] == TREND_CATEGORIES["animals"]["emoji"]
    assert "prompt_text" not in payload


def test_legacy_trend_without_category_uses_featured():
    item = _prompt(["trend"])
    assert trend_category(item) == DEFAULT_TREND_CATEGORY


def test_frontend_is_category_first_and_keeps_studio_as_action():
    source = open("webapp/src/main.jsx", encoding="utf-8").read()
    css = open("webapp/src/style.css", encoding="utf-8").read()
    bot = open("bot/handlers/trends.py", encoding="utf-8").read()

    assert "function TrendDiscoveryCard" in source
    assert "trendCategoryTabs" in source
    assert "trendDiscoveryRail" in source
    assert 'openStudioKind?.("image")' in source
    assert '["studio", "+", "Создать", "navCreate"]' in source
    assert "trend-category-home-v4" in source
    assert ".trendDiscoveryCard" in css
    assert ".nav .navCreate" in css
    assert "TrendAdminFSM.category" in bot
    assert 'settings_payload = {\n        "category"' in bot
''',
)

print("trend category home integration applied")
