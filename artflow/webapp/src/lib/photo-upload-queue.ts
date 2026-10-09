import type { GenerationDraft, ModelInfo, PhotoUploadError, PhotoUploadState } from "./types";
import { referenceMaterials, deleteReferenceMaterial } from "./reference-selection.ts";
import { inspectDraftMedia } from "./draft-media.ts";
import { applyPhotoUploadEvent, cancelPhotoReplacement, parsePhotoPolicy, PhotoUploadFailure, queuePhoto,
  validatePhotoFile, validateUploadedPhoto, type PhotoPolicy, type PhotoUploadEvent, type UploadedPhoto } from "./photo-upload.ts";

type Kind = GenerationDraft["kind"];
export interface PhotoUploadContext {
  owner: number | null;
  enabled: boolean;
  locked: boolean;
  drafts: Record<Kind, GenerationDraft>;
  models: { image: ModelInfo[]; video: ModelInfo[] };
  update: (kind: Kind, apply: (draft: GenerationDraft) => GenerationDraft) => void;
  policy: (signal: AbortSignal) => Promise<unknown>;
  upload: (file: File, signal: AbortSignal) => Promise<UploadedPhoto>;
  notice: (message: string) => void;
  emit?: (detail: Record<string, string | number>) => void;
}
interface Job {
  owner: number; kind: Kind; id: string; operationId: string; file: File; preview: string;
  cancelled: boolean; running: boolean; finished: boolean; controller?: AbortController;
}
export interface PhotoUploadControls {
  retry: (id: string) => void;
  replace: (id: string, file: File) => void;
  remove: (id: string) => void;
  cancel: (id: string) => void;
  hasSource: (id: string) => boolean;
  preview: (id: string) => string;
}
// A finite browser transport guard. No provider/billing retry or business SLA is changed.
const UPLOAD_TRANSPORT_TIMEOUT_MS = 60_000;

/** Files/controllers/object URLs are deliberately outside serializable draft state. */
export class PhotoUploadQueue {
  private sources = new Map<string, Job>();
  private pending: Job[] = [];
  private draining = false;
  private readonly context: () => PhotoUploadContext;
  constructor(context: () => PhotoUploadContext) { this.context = context; }
  private key(kind: Kind, id: string): string { return `${kind}:${id}`; }
  hasPending(kind?: Kind): boolean {
    return [...this.sources.values()].some(job => !job.cancelled && !job.finished && (!kind || job.kind === kind));
  }
  private release(job: Job): void {
    job.cancelled = true; job.controller?.abort();
    if (job.preview) URL.revokeObjectURL(job.preview);
    const key = this.key(job.kind, job.id);
    if (this.sources.get(key) === job) this.sources.delete(key);
  }
  private current(job: Job): boolean {
    const ctx = this.context();
    return !job.cancelled && ctx.enabled && ctx.owner === job.owner;
  }
  private publish(job: Job, event: PhotoUploadEvent): void {
    if (!this.current(job)) return;
    this.context().update(job.kind, current => this.current(job) ? applyPhotoUploadEvent(current, event) : current);
  }
  private emit(job: Job, stage: string, reason = ""): void {
    this.context().emit?.({ material_id: job.id, operation_id: job.operationId, kind: job.kind, stage, bytes: job.file.size, reason });
  }
  add(kind: Kind, files: File[], replaceId?: string): void {
    const ctx = this.context(); const draft = ctx.drafts[kind];
    if (!ctx.enabled || !ctx.owner || ctx.locked || this.hasPending(kind) || draft.promptId !== null || !files.length) return;
    const items = referenceMaterials(draft);
    if (replaceId) {
      if (files.length !== 1 || !items.some(item => item.id === replaceId)) return;
    } else {
      const model = (kind === "image" ? ctx.models.image : ctx.models.video).find(item => item.key === draft.model);
      const info = inspectDraftMedia(draft, model);
      const remaining = Math.max(0, (info.maxReferences ?? 0) - items.filter(item => item.included).length);
      if (!info.referenceInputsSupported || files.length > remaining) {
        ctx.notice(`Можно добавить фото: ${remaining}. Выберите нужные файлы — остальные не будут отброшены автоматически.`);
        return;
      }
    }
    for (const file of files) {
      const id = replaceId || crypto.randomUUID();
      const old = this.sources.get(this.key(kind, id)); if (old) this.release(old);
      let preview = "";
      try { preview = URL.createObjectURL(file); } catch { /* Preview is optional. */ }
      const job: Job = { owner: ctx.owner, kind, id, operationId: crypto.randomUUID(), file, preview, cancelled: false, running: false, finished: false };
      this.sources.set(this.key(kind, id), job);
      const upload: PhotoUploadState = { operationId: job.operationId, status: "queued", name: file.name.slice(0, 256), size: file.size, contentType: file.type };
      ctx.update(kind, current => this.current(job) ? queuePhoto(current, id, upload, Boolean(replaceId)) : current);
      this.pending.push(job); this.emit(job, "queued");
    }
    void this.drain();
  }
  controls(kind: Kind): PhotoUploadControls {
    return {
      retry: id => { const job = this.sources.get(this.key(kind, id)); if (job?.finished) this.add(kind, [job.file], id); },
      replace: (id, file) => this.add(kind, [file], id),
      remove: id => {
        const ctx = this.context(); if (ctx.locked) return;
        const job = this.sources.get(this.key(kind, id)); if (job) this.release(job);
        ctx.update(kind, current => deleteReferenceMaterial(current, id));
      },
      cancel: id => {
        const ctx = this.context(); if (ctx.locked) return;
        const job = this.sources.get(this.key(kind, id)); if (job) { this.emit(job, "cancelled"); this.release(job); }
        ctx.update(kind, current => cancelPhotoReplacement(current, id));
      },
      hasSource: id => { const job = this.sources.get(this.key(kind, id)); return Boolean(job && !job.cancelled && job.owner === this.context().owner); },
      preview: id => { const job = this.sources.get(this.key(kind, id)); return job && !job.cancelled && job.owner === this.context().owner ? job.preview : ""; },
    };
  }
  /** Cancel stale work after an owner/template/draft change; never reinsert removed entries. */
  reconcile(): void {
    const ctx = this.context();
    for (const job of this.sources.values()) {
      const draft = ctx.drafts[job.kind];
      const matches = draft.promptId === null && referenceMaterials(draft).some(item => item.id === job.id && item.upload?.operationId === job.operationId);
      if (ctx.owner !== job.owner || !ctx.enabled || !matches) this.release(job);
    }
  }
  dispose(): void { for (const job of this.sources.values()) this.release(job); this.pending = []; }
  private async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    let policy: PhotoPolicy | undefined; let policyOwner: number | null = null;
    try {
      while (this.pending.length) {
        const job = this.pending.shift()!;
        if (!this.current(job)) { this.release(job); continue; }
        const ctx = this.context(); const controller = new AbortController(); job.controller = controller; job.running = true;
        let timedOut = false;
        const timer = setTimeout(() => { timedOut = true; controller.abort(); }, UPLOAD_TRANSPORT_TIMEOUT_MS);
        this.publish(job, { type: "start", id: job.id, operationId: job.operationId }); this.emit(job, "uploading");
        try {
          if (!policy || policyOwner !== job.owner) {
            try { policy = parsePhotoPolicy(await ctx.policy(controller.signal)); policyOwner = job.owner; }
            catch (error) { if (timedOut) throw error; throw new PhotoUploadFailure("policy_unavailable"); }
          }
          if (!this.current(job)) continue;
          const contentType = await validatePhotoFile(job.file, policy);
          if (!this.current(job)) continue;
          // Some pickers omit or mislabel MIME. The verified byte signature determines it.
          const file = job.file.type === contentType ? job.file : new File([job.file], job.file.name, { type: contentType });
          const response = validateUploadedPhoto(await ctx.upload(file, controller.signal), file, contentType, policy);
          if (!this.current(job)) continue;
          this.publish(job, { type: "success", id: job.id, operationId: job.operationId, result: response }); this.emit(job, "ready");
          job.finished = true;
          // Let React apply the guarded completion before discarding the source record.
          if (job.preview) { URL.revokeObjectURL(job.preview); job.preview = ""; }
          this.sources.delete(this.key(job.kind, job.id));
        } catch (error) {
          if (!this.current(job)) continue;
          const status = (error as { status?: number })?.status;
          const code: PhotoUploadError = timedOut ? "timeout" : error instanceof PhotoUploadFailure ? error.code
            : status === 413 ? "too_large" : status === 422 ? "invalid_file" : status === 401 || status === 403 ? "rejected" : "network";
          job.finished = true;
          this.publish(job, { type: "failure", id: job.id, operationId: job.operationId, error: code }); this.emit(job, "error", code);
          if (code === "policy_unavailable") policy = undefined;
        } finally { clearTimeout(timer); job.running = false; job.controller = undefined; }
      }
    } finally { this.draining = false; }
  }
}
