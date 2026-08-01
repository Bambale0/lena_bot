import React, { useMemo, useState } from "react";
import Icon from "./icons.jsx";
import {
  api,
  copyText,
  feedPreviewCandidates,
  formatCompact,
  formatCredits,
  isVideoMedia,
  openExternal,
} from "./api.js";
import {
  Avatar,
  EmptyState,
  MediaViewer,
  ProgressiveMedia,
} from "./components.jsx";

function ProfileTile({ item, index, onOpen }) {
  const sources = feedPreviewCandidates(item, 0);
  const video = isVideoMedia(item, sources[0]);
  return (
    <button className={`cxProfileTile cxProfileTile--${index % 5}`} type="button" onClick={() => onOpen(item)}>
      <ProgressiveMedia item={item} sources={sources} compact/>
      <span className="cxProfileTile__shade"/>
      <b>{video ? "Видео" : "Фото"}</b>
      {video && <i><Icon name="play" size={18}/></i>}
      <footer>
        <span><Icon name="heart" size={14}/>{formatCompact(item.likes_count)}</span>
        <span><Icon name="eye" size={14}/>{formatCompact(item.views_count || item.remixes)}</span>
      </footer>
    </button>
  );
}

export default function ProfileScreen({ user, history, myFeed, referrals, onNavigate, onTopup, onNotice, onRemix }) {
  const [tab, setTab] = useState("posts");
  const [viewer, setViewer] = useState(null);

  const posts = useMemo(() => myFeed.filter((item) => item && item.id), [myFeed]);
  const saved = useMemo(() => history.filter((item) => item.is_prompt_library || item.is_public_feed), [history]);
  const visible = tab === "posts" ? posts : tab === "saved" ? saved : history;

  async function shareReferral() {
    const link = referrals?.referral_link || user?.referral_link;
    if (!link) {
      onNotice({ type: "warning", message: "Реферальная ссылка пока недоступна" });
      return;
    }
    if (await copyText(link)) onNotice({ type: "success", message: "Реферальная ссылка скопирована" });
  }

  async function like(item) {
    if (!item?.id || !item.is_public_feed) return;
    try {
      await api(`/feed/${item.id}/like`, { method: "POST" });
      onNotice({ type: "success", message: "Добавлено в понравившиеся" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поставить лайк" });
    }
  }

  async function share(item) {
    try {
      let link = item.share_link || "";
      if (item?.id && item.is_public_feed) {
        const result = await api(`/feed/${item.id}/link`);
        link = result.link || link;
      }
      link = link || item.result_url || item.preview_url;
      if (!link || !await copyText(link)) throw new Error("Ссылка недоступна");
      onNotice({ type: "success", message: "Ссылка скопирована" });
    } catch (error) {
      onNotice({ type: "error", message: error.message || "Не удалось поделиться" });
    }
  }

  return (
    <section className="cxScreen cxProfileScreen">
      <article className="cxProfileHero">
        <span className="cxProfileHero__mesh"/>
        <button className="cxProfileHero__settings" type="button" aria-label="Настройки"><Icon name="settings" size={22}/></button>
        <div className="cxProfileHero__identity">
          <Avatar user={user} size="xl"/>
          <div>
            <h2>{user.full_name || user.username || "APIX Creator"}</h2>
            <p>@{user.username || "apix_creator"}</p>
            <span><Icon name="crown" size={13}/>PRO</span>
          </div>
        </div>
        <div className="cxProfileStats">
          <div><b>{posts.length}</b><span>Создано</span></div>
          <div><b>{formatCompact(referrals?.counts?.l1 || 0)}</b><span>Партнёры</span></div>
          <div><b>{formatCredits(user.credits)}</b><span>Токены</span></div>
        </div>
      </article>

      <div className="cxProfileTabs">
        <button type="button" className={tab === "posts" ? "active" : ""} onClick={() => setTab("posts")}>Мои работы</button>
        <button type="button" className={tab === "saved" ? "active" : ""} onClick={() => setTab("saved")}>Сохранённые</button>
        <button type="button" className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>История</button>
      </div>

      {visible.length ? (
        <div className="cxProfileGrid">
          {visible.map((item, index) => <ProfileTile key={item.id || index} item={item} index={index} onOpen={(selected) => setViewer({ item: selected, index: 0 })}/>) }
        </div>
      ) : (
        <EmptyState
          icon="grid"
          title="Пока пусто"
          text="Созданные работы появятся здесь."
          action={<button className="cxPrimaryButton" type="button" onClick={() => onNavigate("create")}><Icon name="sparkle" size={17}/>Создать</button>}
        />
      )}

      <article className="cxReferralCard">
        <span className="cxReferralCard__gift"><Icon name="crown" size={27}/></span>
        <div><h3>Приглашай и получай</h3><p>Делись ссылкой с друзьями и получай бонус с их пополнений.</p></div>
        <button type="button" onClick={shareReferral}>Пригласить</button>
      </article>

      <button className="cxBalanceCard" type="button" onClick={onTopup}>
        <span><Icon name="sparkle" size={20}/>Баланс токенов</span>
        <b>{formatCredits(user.credits)}</b>
        <i><Icon name="plus" size={16}/></i>
      </button>

      <div className="cxProfileSupport">
        <button type="button" onClick={() => openExternal(user.support_url || "https://t.me/apix_ai_bot")}><Icon name="prompt" size={18}/>Поддержка</button>
        <button type="button" onClick={() => onNavigate("create")}><Icon name="sparkle" size={18}/>Новая работа</button>
      </div>

      {viewer && (
        <MediaViewer
          entry={viewer}
          onClose={() => setViewer(null)}
          onLike={like}
          onRemix={(item) => { setViewer(null); onRemix(item); }}
          onShare={share}
        />
      )}
    </section>
  );
}
