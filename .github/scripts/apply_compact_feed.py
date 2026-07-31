from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "artflow/webapp/src/main.jsx"
STYLE = ROOT / "artflow/webapp/src/style.css"

feed_card = r'''function FeedCard({ item, idx, onRemix, onNotice, onRemoved }) {
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
  const mediaType = String(item.gen_type || item.type || item.generation_type || "").toLowerCase().includes("video") ? "video" : "image";

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
      const copied = await copyText(res.link || "");
      if (!copied) throw new Error("Не удалось скопировать ссылку");
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
    <article className="feedCompactCard">
      <div className={`feedCompactMedia ${visibleUrls.length > 1 ? "multi" : ""}`}>
        {visibleUrls.length ? visibleUrls.map((url, mediaIdx) => (
          <MediaThumb
            key={`${url}-${mediaIdx}`}
            url={url}
            openUrl={resultUrls[mediaIdx] || url}
            type={mediaType}
            idx={idx + mediaIdx}
            className="feedCompactImg"
            onOpen={openExternalUrl}
          />
        )) : <Art type="a" />}
        <div className="feedCompactTop">
          <span className="feedCompactAuthor">@{item.author || "anon"}</span>
          {item.is_mine && <span className="feedMineBadge">твой</span>}
        </div>
        <div className="feedCompactStats" aria-label="Статистика публикации">
          <span>♥ {likes}</span>
          <span>↻ {remixes}</span>
          {shares > 0 && <span>↗ {shares}</span>}
        </div>
        {resultUrls.length > 4 && <span className="feedMoreBadge">+{resultUrls.length - 4}</span>}
      </div>

      <div className="feedCompactActions">
        <button
          className={`feedIconAction ${liked ? "liked" : ""}`}
          onClick={handleLike}
          disabled={busy}
          aria-label="Поставить лайк"
          title="Лайк"
        >
          ♥
        </button>
        <button className="feedRepeatAction" onClick={() => onRemix?.(item)}>
          ↻ <span>Повторить</span>
        </button>
        {item.is_mine && (
          <>
            <button
              className={`feedIconAction ${linkCopied ? "successAction" : ""}`}
              onClick={handleCopyLink}
              aria-label="Скопировать ссылку"
              title="Поделиться"
            >
              {linkCopied ? "✓" : "↗"}
            </button>
            <button
              className="feedIconAction dangerAction"
              onClick={handleRemove}
              disabled={removing}
              aria-label="Удалить из ленты"
              title="Удалить"
            >
              {removing ? "…" : "×"}
            </button>
          </>
        )}
      </div>
    </article>
  );
}'''

feed_screen = r'''function Feed({ feed, feedLoading, prompts, setScreen, onRemix, onNotice, onRemoved, scope = "all", onPromptUse, onOpenPrompts }) {
  const [mode, setMode] = useState("all");
  const scopedFeed = scope === "midjourney" ? (feed || []).filter((item) => isMidjourneyModel(item.model)) : (feed || []);
  const myCount = scopedFeed.filter((item) => item.is_mine).length;
  const filtered = mode === "mine" ? scopedFeed.filter((item) => item.is_mine) : scopedFeed;
  const isMjScope = scope === "midjourney";

  return (
    <>
      <div className="feedPageHeader">
        <div>
          <h1>{isMjScope ? "Midjourney лента" : "Лента"}</h1>
          <p>{filtered.length} {filtered.length === 1 ? "работа" : "работ"}</p>
        </div>
        <button className="feedCreateButton" onClick={() => setScreen(isMjScope ? "midjourney" : "studio")}>
          ＋ Создать
        </button>
      </div>

      <div className="feedFilterBar" role="tablist" aria-label="Фильтр ленты">
        <button className={mode === "all" ? "active" : ""} onClick={() => setMode("all")} role="tab" aria-selected={mode === "all"}>
          Все <span>{scopedFeed.length}</span>
        </button>
        <button className={mode === "mine" ? "active mine" : ""} onClick={() => setMode("mine")} role="tab" aria-selected={mode === "mine"}>
          Мои <span>{myCount}</span>
        </button>
      </div>

      {feedLoading ? <Spinner /> : (
        <div className="feedList">
          {filtered.map((item, index) => (
            <FeedCard
              key={item.id || index}
              item={item}
              idx={index}
              onRemix={onRemix}
              onNotice={onNotice}
              onRemoved={onRemoved}
            />
          ))}
          {filtered.length === 0 && (
            <div className="feedEmptyState">
              <b>{mode === "mine" ? "Здесь появятся твои публикации" : "Лента пока пустая"}</b>
              <span>{mode === "mine" ? "Опубликуй готовую работу — она появится в этой вкладке." : "Создай первую работу и опубликуй её."}</span>
            </div>
          )}
        </div>
      )}
    </>
  );
}'''

feed_css = r'''/* compact feed gallery */
.feedPageHeader{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin:0 0 10px}
.feedPageHeader h1{font-size:24px;line-height:1.1}
.feedPageHeader p{margin:4px 0 0;color:var(--text-ghost);font-size:12px}
.feedCreateButton{flex:0 0 auto;border:1px solid var(--accent-border);background:var(--accent-soft);color:var(--accent-text);border-radius:12px;padding:8px 11px;font-size:12px;font-weight:750}
.feedFilterBar{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin-bottom:10px;padding:4px;border:1px solid var(--border-soft);border-radius:13px;background:var(--surface)}
.feedFilterBar button{display:flex;align-items:center;justify-content:center;gap:6px;min-height:34px;border-radius:9px;background:transparent;color:var(--text-soft);font-size:12px;font-weight:700}
.feedFilterBar button span{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 5px;border-radius:999px;background:var(--surface-2);font-size:10px;color:var(--text-ghost)}
.feedFilterBar button.active{background:var(--surface-3);color:var(--text);box-shadow:inset 0 0 0 1px var(--border)}
.feedFilterBar button.active span{background:var(--accent-soft);color:var(--accent-text)}
.feedFilterBar button.active.mine span{background:var(--success-soft);color:var(--success)}
.feedList{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;align-items:start}
.feedCompactCard{min-width:0;border:1px solid var(--border-soft);border-radius:14px;background:var(--surface);overflow:hidden;box-shadow:0 6px 18px rgba(0,0,0,.12);content-visibility:auto;contain-intrinsic-size:190px 240px}
.feedCompactMedia{position:relative;display:grid;width:100%;aspect-ratio:1/1;background:var(--bg-strong);overflow:hidden}
.feedCompactMedia.multi{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:2px}
.feedCompactMedia .art,.feedCompactMedia .mediaOpenable,.feedCompactImg{width:100%;height:100%;min-width:0;min-height:0;object-fit:cover}
.feedCompactMedia video{pointer-events:none}
.feedCompactTop{position:absolute;top:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;gap:6px;padding:7px;background:linear-gradient(180deg,rgba(0,0,0,.62),transparent);pointer-events:none}
.feedCompactAuthor{max-width:78%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff;font-size:10px;font-weight:750;text-shadow:0 1px 3px rgba(0,0,0,.8)}
.feedMineBadge{border:1px solid rgba(255,255,255,.28);background:rgba(28,140,83,.78);color:#fff;border-radius:999px;padding:2px 6px;font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.03em}
.feedCompactStats{position:absolute;left:6px;bottom:6px;display:flex;align-items:center;gap:4px;pointer-events:none}
.feedCompactStats span{border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.58);backdrop-filter:blur(8px);color:#fff;border-radius:999px;padding:3px 6px;font-size:9px;font-weight:750;line-height:1}
.feedMoreBadge{position:absolute;right:6px;bottom:6px;border:1px solid rgba(255,255,255,.18);border-radius:999px;background:rgba(0,0,0,.62);color:#fff;font-size:10px;font-weight:800;padding:3px 7px}
.feedCompactActions{display:flex;align-items:center;gap:5px;padding:6px}
.feedCompactActions button{height:32px;border:1px solid var(--border-strong);border-radius:9px;background:var(--surface-2);color:var(--text-soft);font-size:11px;font-weight:800;transition:transform .12s ease,background .12s ease,border-color .12s ease}
.feedCompactActions button:active{transform:scale(.96)}
.feedIconAction{flex:0 0 32px;padding:0;display:grid;place-items:center}
.feedIconAction.liked{border-color:rgba(236,72,153,.35);background:rgba(236,72,153,.15);color:#f472b6}
.feedRepeatAction{flex:1;min-width:0;padding:0 8px;border-color:var(--accent-border)!important;background:var(--accent-soft)!important;color:var(--accent-text)!important;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.feedCompactActions .successAction{border-color:var(--success-border);background:var(--success-soft);color:var(--success)}
.feedCompactActions .dangerAction{border-color:var(--danger-border);background:var(--danger-soft);color:var(--danger)}
.feedEmptyState{grid-column:1/-1;display:grid;gap:4px;margin-top:12px;padding:22px 16px;border:1px dashed var(--border-strong);border-radius:14px;text-align:center}
.feedEmptyState b{font-size:14px}
.feedEmptyState span{font-size:12px;color:var(--text-ghost)}
@media (max-width:360px){
  .feedList{gap:6px}
  .feedCompactCard{border-radius:12px}
  .feedCompactActions{gap:4px;padding:5px}
  .feedCompactActions button{height:30px;border-radius:8px}
  .feedIconAction{flex-basis:30px}
  .feedRepeatAction span{display:none}
}
'''

main = MAIN.read_text(encoding="utf-8")
card_start = main.index("function FeedCard({ item, idx, onRemix, onNotice, onRemoved }) {")
feed_start = main.index("function Feed({", card_start)
main = main[:card_start] + feed_card + "\n\n" + main[feed_start:]
feed_start = main.index("function Feed({", card_start)
trends_start = main.index("\n\n// ── Admin-curated trends", feed_start)
main = main[:feed_start] + feed_screen + main[trends_start:]
main = re.sub(
    r'window\.__APIX_MINIAPP_BUILD_ID__\s*=\s*"[^"]+";',
    'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-compact-feed-v3";',
    main,
    count=1,
)
MAIN.write_text(main, encoding="utf-8")

style = STYLE.read_text(encoding="utf-8")
css_start = style.index("/* feed gallery */")
result_start = style.index("\n.resultCard{", css_start)
style = style[:css_start] + feed_css + style[result_start:]
STYLE.write_text(style, encoding="utf-8")

print("compact feed tiles applied")
