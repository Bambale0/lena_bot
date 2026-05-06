import { getInitData } from "../telegram";
import type { ActionResult, FeedItem, HistoryItem, MeResponse, PromptItem, Referrals } from "./types";

const demoMe: MeResponse = {
  user: {
    id: 1,
    tg_id: 123456789,
    username: "LeLu88",
    full_name: "Lena Creator",
    credits: 1003,
    referral_code: "APIXDEMO",
  },
  active_image_session: {
    id: 1,
    model: "nano-banana-pro",
    aspect_ratio: "9:16",
    quality: "2K",
    count: 3,
    reference_count: 1,
    last_result_url: null,
  },
};

const demoFeed: FeedItem[] = [
  {
    id: 1,
    author: "@LeLu88",
    model: "Nano Banana Pro",
    preview_url: null,
    prompt_preview: "WB карточка, премиальная глянцевая предметная съемка, мягкий розовый свет, дорогая витрина.",
    likes: 2100,
    remixes: 36,
    shares: 14,
    created_at: new Date().toISOString(),
  },
  {
    id: 2,
    author: "@CyberArt",
    model: "Seedream 4.5",
    preview_url: null,
    prompt_preview: "Cyber neon portrait in a rainy city, glossy cinematic reflections, creator-ready composition.",
    likes: 842,
    remixes: 7,
    shares: 8,
    created_at: new Date().toISOString(),
  },
];

const demoPrompts: PromptItem[] = [
  {
    id: 1,
    title: "WB карточка - глянец",
    description: "Идеальный стиль для товарных карточек: чистый свет, дорогой материал, аккуратный фон.",
    preview_url: null,
    category: "photo",
    uses_count: 2100,
    price_bananas: 4,
    model: "nano-banana-pro",
    likes: 980,
    aspect_ratio: "9:16",
    reference_count: 3,
    quality: "2K",
  },
  {
    id: 2,
    title: "Аватар - реализм",
    description: "Портретный пресет для выразительного личного бренда и соцсетей.",
    preview_url: null,
    category: "photo",
    uses_count: 980,
    price_bananas: 3,
    model: "seedream/4.5-text-to-image",
    likes: 615,
    aspect_ratio: "4:5",
    reference_count: 1,
    quality: "1K",
  },
  {
    id: 3,
    title: "Неон - киберпанк",
    description: "Городская ночная сцена с яркой вывеской, мокрым асфальтом и кинематографичным контрастом.",
    preview_url: null,
    category: "art",
    uses_count: 842,
    price_bananas: 5,
    model: "nano-banana-2",
    likes: 512,
    aspect_ratio: "16:9",
    reference_count: 0,
    quality: "2K",
  },
];

const demoHistory: HistoryItem[] = demoFeed.map((item) => ({
  id: item.id,
  type: "image",
  model: item.model,
  preview_url: item.preview_url,
  prompt_preview: item.prompt_preview,
  created_at: item.created_at,
  likes: item.likes,
  shares: item.shares,
}));

const demoReferrals: Referrals = {
  referral_link: "https://t.me/APIXBot?start=APIXDEMO",
  referral_code: "APIXDEMO",
  level1_count: 23,
  level2_count: 12,
  level3_count: 4,
  earned_bananas: 342,
  rates: { level1: 30, level2: 7, level3: 3 },
};

async function request<T>(path: string, options: RequestInit = {}, fallback: T): Promise<T> {
  const initData = getInitData();
  if (!initData) return fallback;

  try {
    const response = await fetch(`/api/webapp${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
        ...(options.headers || {}),
      },
    });
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as T;
  } catch (error) {
    console.warn("WebApp API fallback:", error);
    return fallback;
  }
}

export const api = {
  getMe: () => request<MeResponse>("/me", {}, demoMe),
  getFeed: (sort = "trending") => request<{ items: FeedItem[] }>(`/feed?sort=${sort}`, {}, { items: demoFeed }),
  getPrompts: (params = "") => request<{ items: PromptItem[] }>(`/prompts${params}`, {}, { items: demoPrompts }),
  getPrompt: (id: number) => request<PromptItem>(`/prompts/${id}`, {}, demoPrompts.find((item) => item.id === id) || demoPrompts[0]),
  usePrompt: (id: number) =>
    request<ActionResult>(`/prompts/${id}/use`, { method: "POST" }, { ok: true, open_bot_required: true, message: "Пресет применён. Вернись в бот, отправь фото или уточнение." }),
  remixGeneration: (id: number) =>
    request<ActionResult>(`/feed/${id}/remix`, { method: "POST" }, { ok: true, open_bot_required: true, message: "Ремикс подготовлен. Вернись в бот и отправь уточнение." }),
  likeFeed: (id: number) => request<ActionResult>(`/feed/${id}/like`, { method: "POST" }, { ok: true, likes: 0, persisted: false }),
  savePrompt: (id: number) => request<ActionResult>(`/prompts/${id}/save`, { method: "POST" }, { ok: true, persisted: false }),
  getHistory: (kind = "all") => request<{ items: HistoryItem[] }>(`/history?kind=${kind}`, {}, { items: demoHistory }),
  getReferrals: () => request<Referrals>("/referrals", {}, demoReferrals),
};
