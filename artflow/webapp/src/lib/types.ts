export type AppMode = "booting" | "live" | "locked" | "error";

export type AppTab =
  | "studio"
  | "photo"
  | "video"
  | "motion"
  | "feed"
  | "trends"
  | "services"
  | "profile"
  | "settings";

export type GenerationStatus = "pending" | "processing" | "done" | "failed" | string;
export type AppLanguage = "ru" | "en";

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
  referral_withdraw_min_rub?: number;
  language?: AppLanguage;
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
  aspect_ratio_modes?: string[];
  aspect_ratio_min_refs?: number;
  quality_options?: ModelOption[];
  quality_prices?: Record<string, number>;
  duration_options?: number[];
  durations?: number[];
  resolution_options?: string[];
  resolutions?: string[];
  motion_controls?: string[];
  mode_options?: string[];
  counts?: number[];
  max_refs?: number;
  has_quality?: boolean;
  is_per_second?: boolean;
  credits_per_sec?: number | null;
  supports_video_input?: boolean;
  max_audio_ids?: number;
  max_character_ids?: number;
  has_seed?: boolean;
  video_input_prices?: Record<string, number>;
  price_table?: Record<string, Record<string, number>>;
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

export interface ReferralChild {
  id: number;
  username?: string | null;
  full_name?: string | null;
  generations_count?: number;
  paid_rub?: number;
}

export interface ReferralWithdrawal {
  id: number;
  amount_rub: number;
  amount_credits?: number | null;
  payout_details: string;
  status: string;
  created_at: string;
}

export interface ReferralStats {
  referral_code?: string;
  referral_link?: string;
  bonus_l1_credits?: number;
  commission_l1?: number;
  commission_l2?: number;
  commission_l3?: number;
  withdraw_min_rub?: number;
  withdraw_min_credits?: number | null;
  exchange_min_rub?: number | null;
  exchange_rate_rub_per_credit?: number | null;
  counts?: { l1?: number; l2?: number; l3?: number };
  balance?: {
    total_earned?: number;
    pending_withdrawals?: number;
    available_to_withdraw?: number;
  };
  feed_remix_reward_rub?: number;
  children?: Record<string, ReferralChild[]>;
  withdrawals?: ReferralWithdrawal[];
}

export interface BootstrapData {
  user: UserProfile;
  imageModels: ModelInfo[];
  videoModels: ModelInfo[];
  recentTasks: GenerationTask[];
  feed: FeedItem[];
  trends: TrendItem[];
  paymentPlans: PaymentPlan[];
  paymentMethods: string[];
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
  taskCount: number;
  mode: string;
  duration: number;
  resolution: string;
  referenceUrls: string[];
  videoUrl: string;
  videoStart: number;
  videoEnd: number | null;
  audioIds: string[];
  characterIds: string[];
  seed: number | null;
  grokMode: string;
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
