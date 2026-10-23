export const KLING4_REFERENCE = 'kling-4.0/reference-to-video';
export const KLING4_KEYFRAME = 'kling-4.0/keyframe-to-video';
export const isKling4 = (model: string) => model === KLING4_REFERENCE || model === KLING4_KEYFRAME;

export interface Kling4Element {
  name: string;
  image_urls?: string[];
  video_url?: string;
  tag?: 'character' | 'animal' | 'prop' | 'costume' | 'scene' | 'effect' | 'others';
  description?: string;
  voice_url?: string;
}
export interface Kling4Voice { name: string; audio_url: string; }
export interface Kling4Options {
  image_urls?: string[];
  video_urls?: string[];
  keep_original_sound?: boolean;
  elements?: Kling4Element[];
  voices?: Kling4Voice[];
  first_frame_url?: string | null;
  keyframe_urls?: string[];
  last_frame_url?: string | null;
}

export function kling4Body(draft: { model: string; kling4?: Kling4Options }): Record<string, unknown> {
  return isKling4(draft.model) ? { kling4: draft.kling4 || {}, image_url: null, reference_urls: [], video_url: null, video_start: 0, video_end: null, audio_ids: [], character_ids: [], seed: null } : {};
}

export async function kling4Intent(body: unknown, owner: number, index: number): Promise<{ id: string; clear: () => void }> {
  const bytes = new TextEncoder().encode(JSON.stringify({ body, owner, index }));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hash = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
  const key = `apix:kling4:intent:${owner}:${hash}`;
  let id = sessionStorage.getItem(key);
  if (!id) { id = crypto.randomUUID(); sessionStorage.setItem(key, id); }
  return { id, clear: () => sessionStorage.removeItem(key) };
}

export function renameKling4Mentions(previous: Kling4Options, next: Kling4Options, prompt: string): string {
  let updated = prompt;
  for (const key of ['elements', 'voices'] as const) {
    const before = previous[key] || []; const after = next[key] || [];
    if (before.length !== after.length) continue;
    before.forEach((item, index) => {
      const name = after[index]?.name;
      if (name && item.name !== name && /^[\u4E00-\u9FA5A-Za-z0-9_]{1,20}$/.test(name)) {
        const escaped = item.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        updated = updated.replace(new RegExp(`@${escaped}(?![\\p{L}\\p{N}_])`, 'gu'), `@${name}`);
      }
    });
  }
  return updated;
}


export function nextKling4Name(options: Kling4Options, prefix: string): string {
  const used = new Set([...(options.elements || []), ...(options.voices || [])].map(item => item.name.toLowerCase()));
  for (let index = 1; ; index += 1) if (!used.has(`${prefix}_${index}`.toLowerCase())) return `${prefix}_${index}`;
}

// Provider contract caps, also enforced by Kling4Input on the server.
const referenceCollections = { image: ['image_urls', 10], video: ['video_urls', 5], audio: ['voices', 3] } as const;
export type Kling4ReferenceKind = keyof typeof referenceCollections;

export function kling4FileKind(file: { name: string }): Kling4ReferenceKind {
  const extension = file.name.split('.').pop()?.toLowerCase();
  if (['png', 'jpg', 'jpeg', 'webp'].includes(extension || '')) return 'image';
  if (['mp4', 'mov', 'webm'].includes(extension || '')) return 'video';
  if (['wav', 'mp3', 'm4a', 'aac', 'flac', 'ogg', 'oga', 'opus'].includes(extension || '')) return 'audio';
  throw new Error('Поддерживаются фото, видео и аудио');
}

export function checkKling4ReferenceCapacity(value: Kling4Options, kind: Kling4ReferenceKind): void {
  const [collection, limit] = referenceCollections[kind];
  if ((value[collection]?.length || 0) >= limit) throw new Error(`Не больше ${limit} материалов этого типа`);
  const total = (value.image_urls?.length || 0) + (value.video_urls?.length || 0)
    + (value.elements?.length || 0) + (value.voices?.length || 0);
  if (total >= 15) throw new Error('Не больше 15 материалов');
}

export function appendKling4Reference(value: Kling4Options, asset: { url: string; kind?: string }): Kling4Options {
  if (!asset.url || !['image', 'video', 'audio'].includes(asset.kind || '')) throw new Error('Сервер не подтвердил тип материала. Повторите загрузку.');
  const kind = asset.kind as Kling4ReferenceKind;
  checkKling4ReferenceCapacity(value, kind);
  if (kind === 'audio') return { ...value, voices: [...(value.voices || []), { name: nextKling4Name(value, 'Voice'), audio_url: asset.url }] };
  const field = kind === 'image' ? 'image_urls' : 'video_urls';
  return { ...value, [field]: [...(value[field] || []), asset.url] };
}
