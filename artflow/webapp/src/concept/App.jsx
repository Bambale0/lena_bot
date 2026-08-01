import React, { useEffect, useMemo, useState } from "react";
import {
  api,
  asItems,
  generationFromRealtime,
  prepareTelegram,
  telegram,
  telegramInitData,
  telegramUser,
  useResource,
} from "./api.js";
import {
  AppHeader,
  BottomNavigation,
  DemoBanner,
  Notice,
} from "./components.jsx";
import FeedScreen from "./FeedScreen.jsx";
import CreateScreen from "./CreateScreen.jsx";
import PromptsScreen from "./PromptsScreen.jsx";
import ProfileScreen from "./ProfileScreen.jsx";
import TopupModal from "./TopupModal.jsx";

const FALLBACK_USER = {
  username: "",
  full_name: "",
  photo_url: "",
  credits: 0,
  referral_balance: 0,
  referral_link: "",
  support_url: "",
  is_admin: false,
};

export default function ConceptApp() {
  const [screen, setScreen] = useState("feed");
  const [notice, setNotice] = useState(null);
  const [topupOpen, setTopupOpen] = useState(false);
  const [preset, setPreset] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [pollId, setPollId] = useState(null);
  const [searchRequested, setSearchRequested] = useState(0);

  const me = useResource(() => api("/me"), FALLBACK_USER);
  const imageModels = useResource(() => api("/models/image").then((value) => asItems(value).length ? asItems(value) : value), []);
  const videoModels = useResource(() => api("/models/video").then((value) => asItems(value).length ? asItems(value) : value), []);
  const feed = useResource(() => api("/feed?source=recent&limit=60").then(asItems), []);
  const prompts = useResource(() => api("/prompts?limit=60").then(asItems), []);
  const history = useResource(() => api("/history?limit=60").then(asItems), []);
  const myFeed = useResource(() => api("/me/feed?limit=100").then(asItems), []);
  const referrals = useResource(() => api("/referrals"), {});

  const tgProfile = telegramUser();
  const user = useMemo(() => ({
    ...FALLBACK_USER,
    ...(me.data || {}),
    username: me.data?.username || tgProfile?.username || "",
    full_name: me.data?.full_name || [tgProfile?.first_name, tgProfile?.last_name].filter(Boolean).join(" ") || "",
    photo_url: me.data?.photo_url || tgProfile?.photo_url || "",
  }), [me.data, tgProfile]);

  useEffect(() => {
    prepareTelegram();
    document.documentElement.dataset.apixTheme = "velvet-concept";
  }, []);

  useEffect(() => {
    if (!pollId) return undefined;
    let failures = 0;
    const timer = window.setInterval(async () => {
      try {
        const result = await api(`/generations/${pollId}`);
        failures = 0;
        setGeneration(result);
        if (result.status === "done" || result.status === "failed") {
          window.clearInterval(timer);
          setPollId(null);
          me.reload();
          history.reload();
        }
      } catch {
        failures += 1;
        if (failures >= 5) {
          window.clearInterval(timer);
          setPollId(null);
          setNotice({ type: "error", message: "Статус временно недоступен. Проверь историю позже." });
        }
      }
    }, 3500);
    return () => window.clearInterval(timer);
  }, [pollId]);

  useEffect(() => {
    const initData = telegramInitData();
    if (!initData) return undefined;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws/generations`);
    socket.addEventListener("open", () => socket.send(JSON.stringify({ type: "auth", init_data: initData })));
    socket.addEventListener("message", (event) => {
      try {
        const next = generationFromRealtime(JSON.parse(event.data));
        if (!next) return;
        setGeneration((current) => !current?.id || Number(current.id) === Number(next.id)
          ? { ...(current || {}), ...next }
          : current);
        if (next.status === "done" || next.status === "failed") {
          setPollId((id) => Number(id) === Number(next.id) ? null : id);
          me.reload();
          history.reload();
        }
      } catch {}
    });
    return () => socket.close();
  }, []);

  async function generate({ kind, payload, remix }) {
    setGeneration({ id: 0, status: "pending", gen_type: kind });
    try {
      let result;
      if (remix) {
        result = await api(`/feed/${remix.id}/remix`, {
          method: "POST",
          body: JSON.stringify({
            model: payload.model,
            prompt: "",
            mode: payload.mode || "text",
            duration: payload.duration,
            aspect_ratio: payload.aspect_ratio,
            resolution: payload.resolution,
            image_url: payload.image_url,
            reference_urls: payload.reference_urls || [],
            grok_mode: payload.grok_mode,
            quality: payload.quality,
            count: payload.count,
          }),
        });
      } else {
        const endpoint = kind === "video" ? "/generate/video" : "/generate/image";
        const body = kind === "video"
          ? {
              model: payload.model,
              prompt: payload.prompt,
              prompt_id: payload.prompt_id || null,
              mode: payload.mode,
              duration: payload.duration,
              aspect_ratio: payload.aspect_ratio,
              resolution: payload.resolution,
              image_url: payload.image_url,
              reference_urls: payload.reference_urls || [],
              grok_mode: payload.grok_mode,
            }
          : {
              model: payload.model,
              prompt: payload.prompt,
              prompt_id: payload.prompt_id || null,
              aspect_ratio: payload.aspect_ratio,
              quality: payload.quality,
              count: payload.count,
              reference_url: payload.reference_url,
              reference_urls: payload.reference_urls || [],
            };
        result = await api(endpoint, { method: "POST", body: JSON.stringify(body) });
      }

      setGeneration(result);
      setPollId(result.id);
      setPreset(null);
      me.reload();
      telegram()?.HapticFeedback?.notificationOccurred?.("success");
    } catch (error) {
      setGeneration({ id: 0, status: "failed", gen_type: kind, error: error.message });
      if (error.status === 402) setTopupOpen(true);
      else setNotice({ type: "error", message: error.message || "Не удалось запустить генерацию" });
    }
  }

  function usePrompt(item) {
    setPreset({
      id: `prompt-${item.id || Date.now()}`,
      prompt: item.prompt_text || item.prompt || item.description || "",
      promptId: item.id || null,
      modelKey: item.model || item.model_key || "",
      kind: item.kind === "video" || item.gen_type === "video" ? "video" : "image",
    });
    setScreen("create");
  }

  function navigate(next) {
    setScreen(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="cxApp">
      <span className="cxAmbient cxAmbient--purple"/>
      <span className="cxAmbient cxAmbient--cyan"/>
      <span className="cxNoise"/>

      <AppHeader
        screen={screen}
        user={user}
        onSearch={() => { setScreen("feed"); setSearchRequested((value) => value + 1); }}
        onCreate={() => navigate("create")}
        onTopup={() => setTopupOpen(true)}
      />
      <DemoBanner/>

      <main>
        {screen === "feed" && (
          <FeedScreen
            feed={feed.data}
            loading={feed.loading}
            onReload={feed.reload}
            onNavigate={navigate}
            onPreset={setPreset}
            onNotice={setNotice}
            searchRequested={searchRequested}
          />
        )}
        {screen === "create" && (
          <CreateScreen
            user={user}
            imageModels={imageModels.data}
            videoModels={videoModels.data}
            preset={preset}
            generation={generation}
            onGenerate={generate}
            onClearPreset={() => setPreset(null)}
            onTopup={() => setTopupOpen(true)}
            onNotice={setNotice}
            onFeedReload={() => { feed.reload(); myFeed.reload(); }}
          />
        )}
        {screen === "prompts" && (
          <PromptsScreen
            prompts={prompts.data}
            loading={prompts.loading}
            onUse={usePrompt}
            onNotice={setNotice}
            onNavigate={navigate}
          />
        )}
        {screen === "profile" && (
          <ProfileScreen
            user={user}
            history={history.data}
            myFeed={myFeed.data}
            referrals={referrals.data}
            onNavigate={navigate}
            onTopup={() => setTopupOpen(true)}
            onNotice={setNotice}
          />
        )}
      </main>

      <BottomNavigation screen={screen} onNavigate={navigate}/>
      <Notice notice={notice} onClose={() => setNotice(null)}/>
      {topupOpen && (
        <TopupModal
          user={user}
          onClose={() => setTopupOpen(false)}
          onNotice={setNotice}
          onPaid={me.reload}
        />
      )}
    </div>
  );
}
