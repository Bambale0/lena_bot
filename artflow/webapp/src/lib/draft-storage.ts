import type { GenerationDraft } from "./types";

export type DraftKind = GenerationDraft["kind"];
export type DraftSet = Partial<Record<DraftKind, GenerationDraft>>;
export type DraftStorage = Pick<Storage, "getItem" | "setItem">;
const KINDS: DraftKind[] = ["image", "video", "motion"];
const MAX_STORED_CHARS = 128 * 1024;

export function draftStorageKey(owner: number): string {
  return `apix:ux2:drafts:v1:${owner}`;
}

export function hasDraftInput(draft: GenerationDraft): boolean {
  return draft.promptId === null && Boolean(draft.prompt.trim() || draft.referenceUrls.length || draft.videoUrl);
}

function safeMedia(value: unknown): value is string {
  if (typeof value !== "string") return false;
  if (value.startsWith("/") && !value.startsWith("//")) return true;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password;
  } catch { return false; }
}

function decodeDraft(raw: unknown, kind: DraftKind): GenerationDraft | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const d = raw as Record<string, unknown>;
  // Hidden trend/remix data is not a device draft. Only explicit user-authored drafts.
  if (d.kind !== kind || d.promptId !== null) return null;
  const strings = ["model", "prompt", "aspectRatio", "quality", "mode", "resolution", "videoUrl", "grokMode"] as const;
  if (strings.some(key => typeof d[key] !== "string")) return null;
  const numbers = ["count", "taskCount", "duration", "videoStart"] as const;
  if (numbers.some(key => typeof d[key] !== "number" || !Number.isFinite(d[key]) || Number(d[key]) < 0)) return null;
  if (![d.videoEnd, d.seed].every(value => value === null || (typeof value === "number" && Number.isFinite(value)))) return null;
  if (!Array.isArray(d.referenceUrls) || !d.referenceUrls.every(safeMedia)) return null;
  if (d.videoUrl !== "" && !safeMedia(d.videoUrl)) return null;
  if (![d.audioIds, d.characterIds].every(value => Array.isArray(value) && value.every(item => typeof item === "string"))) return null;
  // Explicit allowlist: never spread untrusted storage or accidentally persist auth/quotes.
  return {
    kind, model: d.model as string, prompt: d.prompt as string, promptId: null, sourceTitle: "",
    aspectRatio: d.aspectRatio as string, quality: d.quality as string,
    count: d.count as number, taskCount: d.taskCount as number, mode: d.mode as string,
    duration: d.duration as number, resolution: d.resolution as string,
    referenceUrls: [...d.referenceUrls] as string[], videoUrl: d.videoUrl as string,
    videoStart: d.videoStart as number, videoEnd: d.videoEnd as number | null,
    audioIds: [...d.audioIds as string[]], characterIds: [...d.characterIds as string[]],
    seed: d.seed as number | null, grokMode: d.grokMode as string,
  };
}

export function readUserDrafts(storage: DraftStorage | null, owner: number): DraftSet {
  if (!storage || !Number.isSafeInteger(owner) || owner <= 0) return {};
  try {
    const raw = storage.getItem(draftStorageKey(owner));
    if (!raw || raw.length > MAX_STORED_CHARS) return {};
    const envelope = JSON.parse(raw);
    if (envelope?.version !== 1 || envelope.owner !== owner || !envelope.drafts) return {};
    const result: DraftSet = {};
    for (const kind of KINDS) {
      const draft = decodeDraft(envelope.drafts[kind], kind);
      if (draft && hasDraftInput(draft)) result[kind] = draft;
    }
    return result;
  } catch { return {}; }
}

export function saveUserDrafts(storage: DraftStorage | null, owner: number, drafts: DraftSet): boolean {
  if (!storage || !Number.isSafeInteger(owner) || owner <= 0) return false;
  try {
    const next = readUserDrafts(storage, owner);
    for (const kind of KINDS) {
      const current = drafts[kind];
      // Visiting a template must not erase a previously saved ordinary draft.
      if (!current || current.promptId !== null) continue;
      const safe = decodeDraft(current, kind);
      if (safe && hasDraftInput(safe)) next[kind] = safe;
      else delete next[kind];
    }
    const value = JSON.stringify({ version: 1, owner, drafts: next });
    if (value.length > MAX_STORED_CHARS) return false;
    storage.setItem(draftStorageKey(owner), value);
    return true;
  } catch { return false; }
}

export function tabStorage(): Storage | null {
  try { return typeof window === "undefined" ? null : window.sessionStorage; }
  catch { return null; }
}
