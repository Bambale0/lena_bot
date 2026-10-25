/** Typed boundary for owner tools. No retries; no credentials or request bodies in storage. */
export interface AdminTransport {
  request<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T>;
  requestWeb<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T>;
}
export interface GenerationRow {
  id: number; user_id: number; model: string; gen_type: string; status: string;
  prompt: string; prompt_hidden?: boolean; task_id?: string; credits_spent: number;
  error?: string; created_at?: string; finished_at?: string;
}
export interface GenerationPage { items: GenerationRow[]; total: number; limit: number; offset: number; }
export interface FailureResult { id: number; status: string; changed: boolean; refunded: boolean; refunded_credits: number; }
export interface LedgerRow { id: number; user_id: number; delta: number; balance_after: number; entry_type: string; source_type?: string; source_id?: string; note?: string; created_at?: string; }
export interface ModelCost { id: number; model_key: string; gen_type: string; display_name: string; credits: number; is_active: boolean; }
export interface PricePlan { id: number; key: string; label: string; credits: number; price_rub: number; price_stars: number | null; sort_order: number; is_active: boolean; }
export interface Pricing { models: ModelCost[]; price_plans: PricePlan[]; }
export interface AdminPrompt { id: number; title: string; prompt_text?: string; description?: string; model?: string; status: string; is_mine?: boolean; }
export interface WanRoute { model_key: string; policy: "neironych_kie" | "neironych_only" | "kie_only"; neironych_model_id: string; revision: number; source: string; updated_by_admin_tg_id: number | null; credential_configured?: boolean; }
export interface QwenRoute { mode: string; primary_provider: "neironych" | "kie"; backup_provider: "neironych" | "kie" | null; source: string; updated_by_admin_tg_id: number | null; }
export interface NanoRoute { model_key: string; primary_provider: "neironych" | "nexus"; source: string; updated_by_admin_tg_id: number | null; }
export interface RecoveryPolicy { provider: string; auto_refund_seconds: number; source: string; updated_by_admin_tg_id: number | null; }
export interface SupplierReview { generation_id: number; user_id: number; model: string; provider?: string; state: string; original_task_id: string | null; provider_task_id: string | null; refunded_at: string | null; last_provider_status: string | null; next_check_at?: string | null; checks?: number | null; }
export interface SupplierSettlement { generation_id: number; review_state: string; customer_balance_unchanged: boolean; }
export interface TributeProduct { product_id: number; plan_key: string; payment_url: string; currency: "usd"; amount_minor: number; credits: number; amount_rub: number; enabled: boolean; revision: number; }

export class AdminSession {
  readonly ownerId: number;
  private controller = new AbortController();
  private revoked = false;
  private transport: AdminTransport;
  private onUnauthorized: () => void;
  private timeoutMs: number;
  constructor(transport: AdminTransport, ownerId: number, onUnauthorized: () => void, timeoutMs = 15_000) {
    this.transport = transport; this.ownerId = ownerId; this.onUnauthorized = onUnauthorized; this.timeoutMs = timeoutMs;
  }
  get signal() { return this.controller.signal; }
  active = () => !this.revoked && !this.signal.aborted;
  dispose = () => { this.controller.abort(); };
  request = <T>(path: string, init: RequestInit = {}, signal?: AbortSignal) => this.send<T>("request", path, init, signal);
  requestWeb = <T>(path: string, init: RequestInit = {}, signal?: AbortSignal) => this.send<T>("requestWeb", path, init, signal);
  private async send<T>(kind: "request" | "requestWeb", path: string, init: RequestInit, external?: AbortSignal): Promise<T> {
    if (!this.active()) throw new Error("Доступ администратора утрачен");
    const controller = new AbortController();
    const parent = external ?? init.signal;
    const abort = () => controller.abort();
    this.signal.addEventListener("abort", abort, { once: true });
    parent?.addEventListener("abort", abort, { once: true });
    if (parent?.aborted) controller.abort();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, this.timeoutMs);
    let rejectAbort: (() => void) | undefined;
    try {
      if (controller.signal.aborted) throw new Error("Запрос отменён");
      const cancelled = new Promise<never>((_, reject) => {
        rejectAbort = () => reject(new Error(timedOut ? "Истекло время ожидания. Результат запроса не подтверждён." : "Запрос отменён"));
        controller.signal.addEventListener("abort", rejectAbort, { once: true });
        if (controller.signal.aborted) rejectAbort();
      });
      const result = await Promise.race([this.transport[kind]<T>(path, { cache: "no-store", ...init }, controller.signal), cancelled]);
      if (!this.active() || controller.signal.aborted) throw new Error("Запрос отменён");
      return result;
    } catch (error) {
      const status = error && typeof error === "object" && "status" in error ? error.status : undefined;
      if ((status === 401 || status === 403) && !this.revoked) {
        this.revoked = true; this.controller.abort(); this.onUnauthorized();
      }
      throw error;
    } finally {
      clearTimeout(timer);
      this.signal.removeEventListener("abort", abort); parent?.removeEventListener("abort", abort);
      if (rejectAbort) controller.signal.removeEventListener("abort", rejectAbort);
    }
  }
}

export interface UncertainOperation { ownerId: number; targetId: number; action: string; }
type GuardStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export class FinancialGuard {
  private key: string;
  private ownerId: number;
  private storage: GuardStorage | null;
  constructor(ownerId: number, scope: string, storage: GuardStorage | null) {
    this.ownerId = ownerId; this.key = `apix:lilac:admin:${ownerId}:${scope}`; this.storage = storage;
  }
  pending(): UncertainOperation | null {
    try {
      if (!this.storage) throw new Error();
      const raw = this.storage.getItem(this.key); if (!raw) return null;
      const row = JSON.parse(raw) as UncertainOperation;
      if (row.ownerId !== this.ownerId || !Number.isSafeInteger(row.targetId) || row.targetId <= 0 || typeof row.action !== "string") throw new Error();
      return { ownerId: row.ownerId, targetId: row.targetId, action: row.action };
    } catch { return { ownerId: this.ownerId, targetId: 0, action: "storage-unavailable" }; }
  }
  begin(action: string, targetId: number) {
    if (!this.storage || this.pending()) throw new Error("Операция заблокирована: сначала сверьте предыдущий результат и доступность хранилища.");
    const marker = { ownerId: this.ownerId, action, targetId };
    this.storage.setItem(this.key, JSON.stringify(marker));
    if (this.storage.getItem(this.key) !== JSON.stringify(marker)) throw new Error("Не удалось сохранить состояние операции");
  }
  clear() {
    if (!this.storage) throw new Error("Хранилище недоступно");
    this.storage.removeItem(this.key);
    if (this.storage.getItem(this.key)) throw new Error("Не удалось снять блокировку");
  }
}

export function changedFields<T extends object>(original: T, next: T): Partial<T> {
  return Object.fromEntries(Object.entries(next).filter(([key, value]) => !Object.is(original[key as keyof T], value))) as Partial<T>;
}
export function sameFields<T extends object>(original: T, fresh: object): boolean {
  return Object.entries(original).every(([key, value]) => Object.is(value, (fresh as Record<string, unknown>)[key]));
}
export const adminError = (error: unknown) => error instanceof Error ? error.message : "Не удалось выполнить запрос";

export async function readGeneration(session: AdminSession, id: number): Promise<GenerationRow> {
  const page = await session.requestWeb<GenerationPage>(`/admin/generations?status=all&gen_type=all&q=${id}&limit=100&offset=0`);
  const row = page.items.find(item => item.id === id);
  if (!row) throw new Error("Задача не найдена среди свежих результатов. Уточните поиск перед действием.");
  return row;
}
