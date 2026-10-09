import { referenceMaterials, selectGenerationInputs } from "./reference-selection.ts";
import type { GenerationDraft, ReferenceMaterial } from "./types";

export type DraftKind = GenerationDraft["kind"];
export type DraftSet = Partial<Record<DraftKind, GenerationDraft>>;
export type DraftStorage = Pick<Storage, "getItem" | "setItem">;
const KINDS: DraftKind[] = ["image", "video", "motion"];
const MAX_STORED_CHARS = 128 * 1024;

export function draftStorageKey(owner: number): string {
  return `apix:ux2:drafts:v1:${owner}`;
}

export function selectionStorageKey(owner: number): string {
  return `apix:ux2:drafts:v2:${owner}`;
}

export function hasDraftInput(draft: GenerationDraft): boolean {
  return draft.promptId === null && Boolean(draft.prompt.trim() || referenceMaterials(draft).length || draft.videoUrl || draft.audioIds.length || draft.characterIds.length);
}

function safeMedia(value: unknown): value is string {
  if (typeof value !== "string") return false;
  if (value.startsWith("/") && !value.startsWith("//")) return true;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password;
  } catch { return false; }
}

function decodeSelection(raw: unknown): ReferenceMaterial[] | null {
  if (!Array.isArray(raw)) return null;
  const ids = new Set<string>();
  const result: ReferenceMaterial[] = [];
  for (const value of raw) {
    if (!value || typeof value !== "object" || typeof value.id !== "string" || !value.id || value.id.length > 128
      || ids.has(value.id) || !safeMedia(value.url) || typeof value.included !== "boolean") return null;
    ids.add(value.id);
    result.push({ id: value.id, url: value.url, included: value.included });
  }
  return result;
}

function decodeDraft(raw: unknown, kind: DraftKind, modern = false): GenerationDraft | null {
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
  let selection: ReferenceMaterial[] | undefined;
  if (modern && d.referenceMaterials !== undefined) {
    const decoded = decodeSelection(d.referenceMaterials);
    if (!decoded || d.referenceUrls.length !== 0) return null;
    selection = decoded;
  }
  // Explicit allowlist: never spread untrusted storage or accidentally persist auth/quotes.
  return {
    kind, model: d.model as string, prompt: d.prompt as string, promptId: null, sourceTitle: "",
    aspectRatio: d.aspectRatio as string, quality: d.quality as string,
    count: d.count as number, taskCount: d.taskCount as number, mode: d.mode as string,
    duration: d.duration as number, resolution: d.resolution as string,
    referenceUrls: [...d.referenceUrls] as string[], videoUrl: d.videoUrl as string,
    ...(selection !== undefined ? { referenceMaterials: selection } : {}),
    videoStart: d.videoStart as number, videoEnd: d.videoEnd as number | null,
    audioIds: [...d.audioIds as string[]], characterIds: [...d.characterIds as string[]],
    seed: d.seed as number | null, grokMode: d.grokMode as string,
  };
}

function decodeEnvelope(raw: string | null, owner: number, version: number): DraftSet | null {
  if (!raw || raw.length > MAX_STORED_CHARS) return null;
  try {
    const envelope = JSON.parse(raw);
    if (envelope?.version !== version || envelope.owner !== owner || !envelope.drafts
      || typeof envelope.drafts !== "object" || Array.isArray(envelope.drafts)) return null;
    const result: DraftSet = {};
    for (const kind of KINDS) {
      if (envelope.drafts[kind] === undefined) continue;
      const draft = decodeDraft(envelope.drafts[kind], kind, version === 2);
      if (!draft) return null;
      if (hasDraftInput(draft)) result[kind] = draft;
    }
    return result;
  } catch { return null; }
}

export function readUserDrafts(storage: DraftStorage | null, owner: number): DraftSet {
  if (!storage || !Number.isSafeInteger(owner) || owner <= 0) return {};
  try {
    const modern = storage.getItem(selectionStorageKey(owner));
    // Never recover a stale all-active mirror if the canonical snapshot is invalid.
    return modern !== null ? decodeEnvelope(modern, owner, 2) || {}
      : decodeEnvelope(storage.getItem(draftStorageKey(owner)), owner, 1) || {};
  } catch { return {}; }
}

export function saveUserDrafts(storage: DraftStorage | null, owner: number, drafts: DraftSet): boolean {
  if (!storage || !Number.isSafeInteger(owner) || owner <= 0) return false;
  try {
    const existingModern = storage.getItem(selectionStorageKey(owner));
    if (existingModern !== null && !decodeEnvelope(existingModern, owner, 2)) return false;
    const next = readUserDrafts(storage, owner);
    for (const kind of KINDS) {
      const current = drafts[kind];
      // Visiting a template must not erase a previously saved ordinary draft.
      if (!current || current.promptId !== null) continue;
      const safe = decodeDraft(current, kind, true);
      if (!safe) return false;
      if (hasDraftInput(safe)) next[kind] = safe;
      else delete next[kind];
    }
    const modern = existingModern !== null || Object.values(next).some(draft => draft.referenceMaterials !== undefined);
    const compatibility: DraftSet = {};
    for (const kind of KINDS) if (next[kind]) compatibility[kind] = selectGenerationInputs(next[kind]!);
    const legacyValue = JSON.stringify({ version: 1, owner, drafts: compatibility });
    const modernValue = JSON.stringify({ version: 2, owner, drafts: next });
    if (legacyValue.length > MAX_STORED_CHARS || modernValue.length > MAX_STORED_CHARS) return false;
    // Commit the safe old-code view first. A failed write is reported, never claimed durable.
    storage.setItem(draftStorageKey(owner), legacyValue);
    if (modern) storage.setItem(selectionStorageKey(owner), modernValue);
    return true;
  } catch { return false; }
}

export function tabStorage(): Storage | null {
  try { return typeof window === "undefined" ? null : window.sessionStorage; }
  catch { return null; }
}
