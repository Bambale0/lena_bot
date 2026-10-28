import { ArrowRight, Bot, Film, ImageIcon, Library, LifeBuoy, Music2, Orbit, Shapes, Sparkles, WandSparkles } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { CreationArt } from "@/components/creation-art";
import { openTrendRunner } from "@/features/trend-runner";
import { hasDraftInput } from "@/lib/draft-storage";
import { readStudioBalance } from "@/lib/studio-balance";
import { firstMedia, formatRelativeDate, generationStatusLabel, safeExternalUrl } from "@/lib/utils";
import type { AppTab, BootstrapData, GenerationDraft, GenerationTask } from "@/lib/types";

interface HomeProps {
  data: BootstrapData;
  drafts: GenerationDraft[];
  onNavigate: (tab: AppTab) => void;
  onResume: (tab: AppTab) => void;
  onTask: (task: GenerationTask) => void;
}

const tasks = [
  { tab: "photo", title: "Создать фото", text: "Из описания или вашего снимка", Icon: ImageIcon },
  { tab: "video", title: "Оживить фото", text: "Создать видео и добавить движение", Icon: Film },
  { tab: "music", title: "Создать музыку", text: "Песня, инструментал и свой голос", Icon: Music2 },
  { tab: "assistant", title: "AI-помощник", text: "Идеи, тексты и помощь с заданием", Icon: Bot },
] as const;

const homeLaunchers = [
  { tab: "photo", title: "Создать фото", Icon: ImageIcon },
  { tab: "video", title: "Оживить фото", Icon: Film },
  { tab: "music", title: "Создать музыку", Icon: Music2 },
  { tab: "assistant", title: "AI-помощник", Icon: Bot },
  { tab: "models", title: "Все нейросети", Icon: Shapes },
  { tab: "services", title: "Инструменты", Icon: WandSparkles },
] as const;

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    if (typeof query.addEventListener === "function") query.addEventListener("change", sync);
    else query.addListener(sync);
    return () => {
      if (typeof query.removeEventListener === "function") query.removeEventListener("change", sync);
      else query.removeListener(sync);
    };
  }, []);
  return reduced;
}

function useViewportVisibility(enabled: boolean) {
  const ref = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!enabled || !element) { setVisible(false); return; }
    if (typeof IntersectionObserver === "function") {
      const observer = new IntersectionObserver(([entry]) => setVisible(Boolean(entry?.isIntersecting && entry.intersectionRatio > 0)), { root: null, threshold: 0.01 });
      observer.observe(element);
      return () => observer.disconnect();
    }
    const update = () => {
      const rect = element.getBoundingClientRect();
      setVisible(rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth);
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, { capture: true, passive: true });
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [enabled]);
  return { ref, visible };
}

function HomeThumbnail({ url, kind, reducedMotion, fallback = null }: { url?: string | null; kind: "image" | "video"; reducedMotion: boolean; fallback?: ReactNode }) {
  const src = safeExternalUrl(url);
  const [failed, setFailed] = useState("");
  const active = kind === "video" && Boolean(src) && failed !== src;
  const { ref: frameRef, visible } = useViewportVisibility(active);
  const videoRef = useRef<HTMLVideoElement>(null);
  const shouldPlay = active && visible && !reducedMotion;
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (!shouldPlay) { video.pause(); return; }
    let current = true;
    const play = () => {
      if (!current || !video.isConnected) return;
      void video.play().catch(() => undefined);
    };
    video.addEventListener("canplay", play);
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) play();
    return () => {
      current = false;
      video.removeEventListener("canplay", play);
      video.pause();
    };
  }, [shouldPlay, visible]);
  if (!src || failed === src) return <>{fallback}</>;
  return kind === "video"
    ? <span ref={frameRef} className="lilac-video-frame" aria-hidden="true" data-apix-home-preview-frame="">
        {visible && <video ref={videoRef} src={src} muted loop playsInline autoPlay={shouldPlay}
          preload="metadata" data-apix-home-preview=""
          onError={event => { if (event.currentTarget.isConnected && event.currentTarget.error) setFailed(src); }} />}
      </span>
    : <img src={src} alt="" loading="lazy" onError={() => setFailed(src)} />;
}

export function LilacHome({ data, drafts, onNavigate, onResume, onTask }: HomeProps) {
  const photoPreview = safeExternalUrl(data.feed.find(item => item.gen_type === "image")?.preview_url);
  const trendPreview = safeExternalUrl(data.trends.find(item => item.kind === "video")?.preview_url);
  const saved = drafts.filter(hasDraftInput);
  const reducedMotion = useReducedMotion();
  return <div className="lilac-page lilac-home">
    {data.user.credits === 0 && <div className="lilac-row"><span><strong>Баланс пока 0</strong><small>Можно выбрать пример и добавить фото. Перед платным запуском пополните баланс.</small></span><button className="lilac-primary" onClick={() => readStudioBalance()?.onOpen()}>Пополнить</button></div>}
    <section className="lilac-showcase" aria-label="Витрина APIX">
      <article className="lilac-showcase-hero" role="group" aria-label="Главный сценарий">
        <HomeThumbnail url={photoPreview} kind="image" reducedMotion={reducedMotion}
          fallback={<span className="lilac-hero-fallback" aria-hidden="true"><Sparkles /><i /><i /></span>} />
        <span className="lilac-showcase-shade" aria-hidden="true" />
        <header className="lilac-showcase-copy">
          <span>Ваша творческая студия</span>
          <h1>Что создадим сегодня?</h1>
          <p>Добавьте идею или фото — с настройками поможем.</p>
        </header>
        <button type="button" className="lilac-showcase-cta" aria-label="Создать фото — главный сценарий" onClick={() => onNavigate("photo")}>
          Создать <ArrowRight aria-hidden="true" />
        </button>
      </article>
      <div className="lilac-promo-grid">
        <button type="button" className="lilac-promo lilac-promo-trends" aria-label="По шаблону" onClick={() => onNavigate("trends")}>
          <HomeThumbnail url={trendPreview} kind="video" reducedMotion={reducedMotion}
            fallback={<span className="lilac-promo-fallback" aria-hidden="true"><Sparkles /><Orbit /><i /></span>} />
          <span className="lilac-promo-shade" aria-hidden="true" />
          <span className="lilac-promo-copy"><small>Готовые сценарии</small><strong>Тренды</strong><span>Повторить образ</span></span>
        </button>
        <button type="button" className="lilac-promo lilac-promo-help" aria-label="Открыть помощь" onClick={() => onNavigate("help")}>
          <span className="lilac-help-orbit" aria-hidden="true"><LifeBuoy /><i /></span>
          <span className="lilac-promo-copy"><small>APIX Studio</small><strong>Мы рядом</strong><span>Центр помощи</span></span>
        </button>
      </div>
      <span className="lilac-showcase-dots" aria-hidden="true"><i /><i /><i /><i /></span>
    </section>
    <nav className="lilac-service-grid" aria-label="Быстрый запуск">
      {homeLaunchers.map(({ tab, title, Icon }) => <button type="button" key={tab} aria-label={title} onClick={() => onNavigate(tab)}>
        <span className="lilac-service-icon">{tab === "video"
          ? <HomeThumbnail url={trendPreview} kind="video" reducedMotion={reducedMotion} fallback={<Icon aria-hidden="true" />} />
          : <Icon aria-hidden="true" />}</span>
        <span>{title}</span>
      </button>)}
    </nav>
    {saved.length > 0 && <section><div className="lilac-section-title"><h2>Продолжить черновик</h2></div>
      {saved.map(draft => <button className="lilac-row" key={draft.kind} onClick={() => onResume(draft.kind === "image" ? "photo" : draft.kind)}>
        <span className="lilac-mini-icon"><Orbit /></span><span><strong>{draft.kind === "image" ? "Фото" : draft.kind === "video" ? "Видео" : "Движение"}</strong><small>{draft.prompt.trim() || "Материалы уже добавлены"}</small></span><ArrowRight size={18} />
      </button>)}<p className="lilac-note">Черновики сохраняются в этой вкладке браузера.</p></section>}
    <section><div className="lilac-section-title"><h2>Повторить готовый пример</h2><button onClick={() => onNavigate("trends")}>Все шаблоны <ArrowRight size={15} /></button></div><p className="lilac-note">Выберите пример, добавьте свои материалы и подтвердите стоимость.</p>
      {data.trends.length ? <div className="lilac-preview-rail">{data.trends.slice(0, 8).map(trend => <button key={trend.id} onClick={() => openTrendRunner(trend)}>
        <HomeThumbnail url={trend.preview_url} kind={trend.kind} reducedMotion={reducedMotion} fallback={<Sparkles size={32} />} />
        <strong>{trend.title}</strong><small>{trend.kind === "video" ? "Видео" : "Фото"}</small>
      </button>)}</div> : <div className="lilac-empty"><Sparkles /><p>Готовых сценариев пока нет. Можно начать со своей идеи.</p><button className="lilac-primary" onClick={() => onNavigate("photo")}>Создать первое фото</button></div>}
    </section>
    <section><div className="lilac-section-title"><h2>Последние работы</h2><button onClick={() => onNavigate("works")}>Все проекты <ArrowRight size={15} /></button></div>
      {data.recentTasks.length ? data.recentTasks.slice(0, 3).map(task => <button key={task.id} className="lilac-row" onClick={() => onTask(task)}>
        <span className="lilac-mini-preview"><HomeThumbnail url={task.gen_type === "image" ? firstMedia(task) : undefined} kind={task.gen_type === "image" ? "image" : "video"} reducedMotion={reducedMotion} fallback={task.gen_type === "image" ? <ImageIcon /> : <Film />} /></span>
        <span><strong>{task.prompt_hidden || task.prompt_actions_allowed === false ? "Работа по шаблону" : task.prompt || task.model}</strong><small>{generationStatusLabel(task.status)} · {formatRelativeDate(task.created_at)}</small></span><ArrowRight size={18} />
      </button>) : <p className="lilac-note">Здесь появятся ваши фото, видео и песни после первого запуска.</p>}
    </section>
    <div className="lilac-two-links"><button onClick={() => onNavigate("library")}><Library /> Библиотека промптов</button><button onClick={() => onNavigate("help")}><LifeBuoy /> Как начать</button></div>
  </div>;
}

export function LilacCreate({ onNavigate }: { onNavigate: (tab: AppTab) => void }) {
  const featured = tasks.filter(task => task.tab === "photo" || task.tab === "video");
  const tools = [...tasks.filter(task => task.tab !== "photo" && task.tab !== "video"), { tab: "motion", title: "Перенести движение", text: "Фото персонажа и видео движения", Icon: Orbit }, { tab: "services", title: "Инструменты", text: "Промпт по фото и видео, Pinterest", Icon: WandSparkles }];
  return <div className="lilac-page creation-menu">
    <header className="creation-menu-header"><h1>Какой результат нужен?</h1><p>Выберите задачу. Идею и материалы добавите в редакторе.</p></header>
    <div className="creation-featured">{featured.map(({ tab, title, text }) => <button type="button" key={tab} className="creation-choice apix-focus-ring" onClick={() => onNavigate(tab)}>
      <span className="creation-choice-visual"><CreationArt kind={tab} /></span>
      <span className="creation-choice-copy"><strong>{title}</strong><span>{text}</span></span>
    </button>)}</div>
    <div className="creation-tools">{tools.map(({ tab, title, text, Icon }) => <button type="button" key={tab} className="creation-tool apix-focus-ring" onClick={() => onNavigate(tab as AppTab)}>
      <span className="creation-tool-icon"><Icon aria-hidden="true" /></span>
      <span className="creation-tool-copy"><strong>{title}</strong><span>{text}</span></span>
    </button>)}</div>
    <div className="creation-shortcuts">
      <button type="button" className="creation-shortcut apix-focus-ring" onClick={() => onNavigate("trends")}><Sparkles aria-hidden="true" /><span><strong>Повторить готовый пример</strong><small>Выберите образец и добавьте свои материалы</small></span></button>
      <button type="button" className="creation-shortcut apix-focus-ring" onClick={() => onNavigate("models")}><Shapes aria-hidden="true" /><span><strong>Выбрать нейросеть</strong><small>Возможности, параметры и текущая стоимость</small></span></button>
    </div>
  </div>;
}

export function LilacIdeas({ onNavigate }: { onNavigate: (tab: AppTab) => void }) {
  return <div className="lilac-page"><header className="lilac-title"><p>Вдохновение</p><h1>Найдите свою идею</h1><span>Повторяйте готовые сценарии и создавайте свои версии.</span></header>
    {[
      { tab: "trends", Icon: Sparkles, title: "Шаблоны и тренды", text: "Выберите образец и добавьте свои материалы" },
      { tab: "feed", Icon: ImageIcon, title: "Лента работ", text: "Фото, видео и повтор со своими исходниками" },
      { tab: "library", Icon: Library, title: "Библиотека промптов", text: "Готовые задания и ваши публикации" },
    ].map(({ tab, Icon, title, text }) => <button aria-label={title} className="lilac-row lilac-idea-row" key={tab} onClick={() => onNavigate(tab as AppTab)}><span className="lilac-mini-icon"><Icon /></span><span><strong>{title}</strong><small>{text}</small></span><ArrowRight /></button>)}
  </div>;
}
