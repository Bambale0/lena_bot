export type AppMode = "booting" | "live" | "locked" | "error";

export type AppTab =
  | "studio"
  | "photo"
  | "video"
  | "motion"
  | "feed"
  | "trends"
  | "services"
  | "profile";

export type GenerationStatus = "pending" | "processing" | "done" | "failed" | string;

export interface UserProfile {
  id: number;
  tg_id?: number;
  telegram_id?: number;
  username?: string | null;
  full_name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  photo_url?: string | null;
  credits: number;
  referral_balance?: number;
  referral_code?: string;
  referral_link?: string;
  channel_url?: string | null;
  is_admin?: boolean;
}

export interface ModelOption {
  value: string;
  label?: string;
  credits?: number;
}

export interface ModelInfo {
  key: string;
  display_name: string;
  description?: string;
  credits: number;
  modes: string[];
  aspect_ratios?: string[];
  quality_options?: ModelOption[];
  duration_options?: number[];
  resolution_options?: string[];
  mode_options?: string[];
  counts?: number[];
  max_refs?: number;
  has_quality?: boolean;
  available_in_studio?: boolean;
}

export interface GenerationTask {
  id: number;
  task_id?: string | null;
  model: string;
  gen_type: "image" | "video" | "music" | "audio" | string;
  prompt?: string;
  prompt_hidden?: boolean;
  prompt_actions_allowed?: boolean;
  status: GenerationStatus;
  result_url?: string | null;
  result_urls?: string[];
  preview_url?: string | null;
  preview_urls?: string[];
  error?: string | null;
  credits_spent?: number;
  aspect_ratio?: string | null;
  duration?: number | null;
  quality?: string | null;
  created_at?: string;
  completed_at?: string | null;
  is_public_feed?: boolean;
  is_prompt_library?: boolean;
}

export interface FeedItem {
  id: number;
  model: string;
  gen_type?: string;
  prompt?: string;
  prompt_hidden?: boolean;
  result_url?: string;
  result_urls?: string[];
  preview_url?: string;
  preview_urls?: string[];
  likes_count?: number;
  shares_count?: number;
  remixes?: number;
  aspect_ratio?: string | null;
  author?: string;
  author_photo_url?: string | null;
  is_mine?: boolean;
}

export interface TrendItem {
  id: number;
  kind: "image" | "video";
  title: string;
  description?: string;
  preview_url?: string | null;
  model?: string | null;
  category?: string;
  category_title?: string;
  category_emoji?: string;
  uses_count?: number;
  settings?: Record<string, unknown>;
}

export interface PreparedTrend extends TrendItem {
  prompt_id: number;
  model: string;
  settings: Record<string, unknown>;
  prompt_hidden: true;
}

export interface PaymentPlan {
  key: string;
  title: string;
  credits: number;
  price_rub?: number;
  price_usdt?: number;
  price_stars?: number;
}

export interface ReferralStats {
  referral_code?: string;
  referral_link?: string;
  counts?: { l1?: number; l2?: number; l3?: number };
  balance?: {
    total_earned?: number;
    pending_withdrawals?: number;
    available_to_withdraw?: number;
  };
  feed_remix_reward_rub?: number;
}

export interface BootstrapData {
  user: UserProfile;
  imageModels: ModelInfo[];
  videoModels: ModelInfo[];
  recentTasks: GenerationTask[];
  feed: FeedItem[];
  trends: TrendItem[];
  paymentPlans: PaymentPlan[];
}

export interface GenerationDraft {
  kind: "image" | "video" | "motion";
  model: string;
  prompt: string;
  promptId: number | null;
  sourceTitle?: string;
  aspectRatio: string;
  quality: string;
  count: number;
  mode: string;
  duration: number;
  resolution: string;
  referenceUrls: string[];
  videoUrl: string;
}

export interface StartTarget {
  kind: "ref" | "profile" | "feed" | "remix" | "prompt" | "task" | "trend";
  value: string;
}

export interface AssistantMessage {
  role: "user" | "assistant";
  text: string;
}

export interface PhotoPromptResult {
  prompt: string;
  prompt_en?: string;
  prompt_ru?: string;
  negative_prompt?: string;
  model_hint?: string;
}
