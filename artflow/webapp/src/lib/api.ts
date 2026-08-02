import type {
  AssistantMessage,
  BootstrapData,
  FeedItem,
  GenerationTask,
  ModelInfo,
  PaymentPlan,
  PhotoPromptResult,
  PreparedTrend,
  ReferralStats,
  TrendItem,
  UserProfile,
} from "@/lib/types";
import { asArray, asRecord } from "@/lib/utils";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(message: string, status: number, code = "API_ERROR", details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function readApiError(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  const record = asRecord(payload);
  const nestedError = asRecord(record.error);
  const detail = record.detail;
  const message =
    (typeof nestedError.message === "string" && nestedError.message) ||
    (typeof detail === "string" && detail) ||
    (typeof record.message === "string" && record.message) ||
    `Ошибка API ${response.status}`;
  const code =
    (typeof nestedError.code === "string" && nestedError.code) ||
    (typeof record.code === "string" && record.code) ||
    "API_ERROR";
  return new ApiError(message, response.status, code, asRecord(nestedError.details));
}

function settledValue<T>(result: PromiseSettledResult<T>, fallback: T): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

export class MiniAppApi {
  constructor(private readonly initData: string) {}

  async request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
    const isForm = init.body instanceof FormData;
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: signal ?? init.signal,
      headers: {
        ...(isForm ? {} : { "Content-Type": "application/json" }),
        "X-Telegram-Init-Data": this.initData,
        ...(init.headers || {}),
      },
    });
    if (!response.ok) throw await readApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async bootstrap(signal?: AbortSignal): Promise<BootstrapData> {
    const [userResult, imageResult, videoResult, historyResult, feedResult, trendsResult, plansResult] =
      await Promise.allSettled([
        this.request<UserProfile>("/me", {}, signal),
        this.request<unknown>("/models/image", {}, signal),
        this.request<unknown>("/models/video", {}, signal),
        this.request<unknown>("/history?limit=16", {}, signal),
        this.request<unknown>("/feed?source=recent&limit=16", {}, signal),
        this.request<unknown>("/trends?limit=32", {}, signal),
        this.request<unknown>("/plans", {}, signal),
      ]);

    if (userResult.status === "rejected") throw userResult.reason;

    return {
      user: userResult.value,
      imageModels: asArray<ModelInfo>(settledValue(imageResult, [])),
      videoModels: asArray<ModelInfo>(settledValue(videoResult, [])),
      recentTasks: asArray<GenerationTask>(settledValue(historyResult, [])),
      feed: asArray<FeedItem>(settledValue(feedResult, [])),
      trends: asArray<TrendItem>(settledValue(trendsResult, [])),
      paymentPlans: asArray<PaymentPlan>(settledValue(plansResult, [])),
    };
  }

  async refreshCore(signal?: AbortSignal): Promise<{ user: UserProfile; recentTasks: GenerationTask[] }> {
    const [user, history] = await Promise.all([
      this.request<UserProfile>("/me", {}, signal),
      this.request<unknown>("/history?limit=16", {}, signal),
    ]);
    return { user, recentTasks: asArray<GenerationTask>(history) };
  }

  getGeneration(id: number, signal?: AbortSignal): Promise<GenerationTask> {
    return this.request<GenerationTask>(`/generations/${id}`, {}, signal);
  }

  createImage(body: Record<string, unknown>): Promise<GenerationTask> {
    return this.request<GenerationTask>("/generate/image", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  createVideo(body: Record<string, unknown>): Promise<GenerationTask> {
    return this.request<GenerationTask>("/generate/video", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  getFeed(source: "recent" | "top_day" | "top", signal?: AbortSignal): Promise<FeedItem[]> {
    return this.request<unknown>(`/feed?source=${source}&limit=24`, {}, signal).then((value) => asArray<FeedItem>(value));
  }

  likeFeed(id: number): Promise<{ likes_count?: number }> {
    return this.request<{ likes_count?: number }>(`/feed/${id}/like`, { method: "POST", body: "{}" });
  }

  remixFeed(id: number, body: Record<string, unknown>): Promise<GenerationTask> {
    return this.request<GenerationTask>(`/feed/${id}/remix`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  shareGeneration(id: number): Promise<{ link?: string; is_public_feed?: boolean }> {
    return this.request<{ link?: string; is_public_feed?: boolean }>(`/generations/${id}/share`, { method: "POST", body: "{}" });
  }

  removeFeedPost(id: number): Promise<{ is_public_feed?: boolean }> {
    return this.request<{ is_public_feed?: boolean }>(`/feed/${id}/remove`, { method: "POST", body: "{}" });
  }

  savePrompt(id: number): Promise<{ is_prompt_library?: boolean }> {
    return this.request<{ is_prompt_library?: boolean }>(`/generations/${id}/share-library`, { method: "POST", body: "{}" });
  }

  removePrompt(id: number): Promise<{ is_prompt_library?: boolean }> {
    return this.request<{ is_prompt_library?: boolean }>(`/generations/${id}/remove-library`, { method: "POST", body: "{}" });
  }

  getTrends(kind?: "image" | "video", signal?: AbortSignal): Promise<TrendItem[]> {
    const query = kind ? `?kind=${kind}&limit=64` : "?limit=64";
    return this.request<unknown>(`/trends${query}`, {}, signal).then((value) => asArray<TrendItem>(value));
  }

  prepareTrend(id: number): Promise<PreparedTrend> {
    return this.request<PreparedTrend>(`/trends/${id}/prepare`, { method: "POST", body: "{}" });
  }

  getReferrals(signal?: AbortSignal): Promise<ReferralStats> {
    return this.request<ReferralStats>("/referrals", {}, signal);
  }

  sendAssistant(message: string, history: AssistantMessage[]): Promise<string> {
    return this.request<unknown>("/assistant", {
      method: "POST",
      body: JSON.stringify({ message, history: history.slice(-10) }),
    }).then((payload) => {
      const record = asRecord(payload);
      return String(record.reply || record.message || record.text || "Готово. Чем ещё помочь?");
    });
  }

  async photoPrompt(file: File): Promise<PhotoPromptResult> {
    const form = new FormData();
    form.append("file", file);
    const payload = await this.request<unknown>("/photo-prompt", { method: "POST", body: form });
    const record = asRecord(payload);
    return {
      prompt: String(record.prompt || record.prompt_en || record.prompt_ru || ""),
      prompt_en: typeof record.prompt_en === "string" ? record.prompt_en : undefined,
      prompt_ru: typeof record.prompt_ru === "string" ? record.prompt_ru : undefined,
      negative_prompt: typeof record.negative_prompt === "string" ? record.negative_prompt : undefined,
      model_hint: typeof record.model_hint === "string" ? record.model_hint : undefined,
    };
  }

  createPayment(provider: "stars" | "tbank" | "crypto" | "lava", planKey: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/topup/${provider}`, {
      method: "POST",
      body: JSON.stringify({ plan_key: planKey }),
    });
  }

  getAuthConfig(): Promise<{ bot_username?: string }> {
    return fetch(`${API_BASE}/auth/config`).then(async (response) => {
      if (!response.ok) throw await readApiError(response);
      return (await response.json()) as { bot_username?: string };
    });
  }
}
