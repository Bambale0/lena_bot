import type { GenerationDraft, ModelInfo, ReferenceMaterial } from "./types";

/** v1 drafts are all-active. Ids remain local and are never sent to the provider. */
export function referenceMaterials(draft: GenerationDraft): ReferenceMaterial[] {
  if (draft.promptId === null && draft.referenceMaterials !== undefined) {
    return draft.referenceMaterials.map(item => ({ ...item }));
  }
  return draft.referenceUrls.map((url, index) => ({ id: `legacy-${index}`, url, included: true }));
}

/** A detached request view; it contains no parked urls or selection metadata. */
export function selectGenerationInputs(draft: GenerationDraft): GenerationDraft {
  const { referenceMaterials: _selection, ...base } = draft;
  return { ...base, referenceUrls: referenceMaterials(draft).filter(item => item.included).map(item => item.url),
    audioIds: [...draft.audioIds], characterIds: [...draft.characterIds] };
}

function withMaterials(draft: GenerationDraft, items: ReferenceMaterial[]): GenerationDraft {
  if (draft.promptId !== null) return draft;
  return { ...draft, referenceUrls: [], referenceMaterials: items.map(item => ({ ...item })) };
}

export function setReferenceIncluded(draft: GenerationDraft, id: string, included: boolean): GenerationDraft {
  return withMaterials(draft, referenceMaterials(draft).map(item => item.id === id ? { ...item, included } : item));
}

export function deleteReferenceMaterial(draft: GenerationDraft, id: string): GenerationDraft {
  return withMaterials(draft, referenceMaterials(draft).filter(item => item.id !== id));
}

/** Match by URL + occurrence, not display name or array index after reordering. */
function reconcile(items: ReferenceMaterial[], urls: string[], newId: () => string): ReferenceMaterial[] {
  const remaining = [...items];
  return urls.map(url => {
    const index = remaining.findIndex(item => item.url === url);
    return index < 0 ? { id: newId(), url, included: true } : { ...remaining.splice(index, 1)[0] };
  });
}

export function replaceReferenceMaterials(draft: GenerationDraft, urls: string[], newId = () => crypto.randomUUID()): GenerationDraft {
  return withMaterials(draft, reconcile(referenceMaterials(draft), urls, newId));
}

export function appendReferenceUrls(draft: GenerationDraft, urls: string[], newId = () => crypto.randomUUID()): GenerationDraft {
  if (draft.referenceMaterials === undefined || draft.promptId !== null) {
    return { ...draft, referenceUrls: [...new Set([...draft.referenceUrls, ...urls])] };
  }
  const items = referenceMaterials(draft);
  for (const url of urls) if (!items.some(item => item.url === url)) items.push({ id: newId(), url, included: true });
  return withMaterials(draft, items);
}

/** Legacy consumers edit the active projection, never the parked items. */
export function applyDraftPatch(draft: GenerationDraft, patch: Partial<GenerationDraft>): GenerationDraft {
  if (patch.promptId != null) return { ...selectGenerationInputs(draft), ...patch, referenceMaterials: undefined };
  const merged = { ...draft, ...patch };
  if (patch.referenceMaterials !== undefined) return withMaterials(merged, patch.referenceMaterials);
  if (draft.referenceMaterials === undefined || patch.referenceUrls === undefined) return merged;
  const items = referenceMaterials(draft);
  const parkedUrls = new Set(items.filter(item => !item.included).map(item => item.url));
  const active = reconcile(items.filter(item => item.included), patch.referenceUrls.filter(url => !parkedUrls.has(url)), () => crypto.randomUUID());
  const retained: ReferenceMaterial[] = [];
  for (const item of items) {
    if (!item.included) retained.push(item);
    else if (active.length) retained.push(active.shift()!);
  }
  return withMaterials(merged, [...retained, ...active]);
}

/** Stable value comparison, insensitive to JSON property ordering. */
export function modelSnapshotKey(model: ModelInfo | undefined): string {
  const ordered = (value: unknown): unknown => Array.isArray(value) ? value.map(ordered)
    : value && typeof value === "object" ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => [key, ordered(child)])) : value;
  return JSON.stringify(ordered(model ?? null));
}
