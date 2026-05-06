export type WebUser = {
  id: number;
  tg_id: number;
  username?: string | null;
  full_name?: string | null;
  credits: number;
  referral_code: string;
};

export type ImageSession = {
  id: number;
  model: string;
  aspect_ratio?: string | null;
  quality: string;
  count: number;
  reference_count: number;
  last_result_url?: string | null;
};

export type MeResponse = {
  user: WebUser;
  active_image_session?: ImageSession | null;
};

export type FeedItem = {
  id: number;
  author: string;
  model: string;
  preview_url?: string | null;
  prompt_preview: string;
  likes: number;
  remixes: number;
  shares: number;
  created_at?: string | null;
};

export type PromptItem = {
  id: number;
  title: string;
  description: string;
  preview_url?: string | null;
  category: string;
  uses_count: number;
  price_bananas: number;
  model: string;
  likes?: number;
  aspect_ratio?: string;
  reference_count?: number;
  quality?: string;
};

export type HistoryItem = {
  id: number;
  type: "image" | "video" | "music";
  model: string;
  preview_url?: string | null;
  prompt_preview: string;
  created_at?: string | null;
  likes?: number;
  shares?: number;
};

export type Referrals = {
  referral_link: string;
  referral_code: string;
  level1_count: number;
  level2_count: number;
  level3_count: number;
  earned_bananas: number;
  rates: { level1: number; level2: number; level3: number };
};

export type ActionResult = {
  ok: boolean;
  open_bot_required?: boolean;
  message?: string;
  persisted?: boolean;
  likes?: number;
};
