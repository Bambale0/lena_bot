/** In-memory bridge for independently mounted runner roots. App owns identity and balance. */
export interface StudioBalance {
  readonly actorId: number;
  readonly credits: number;
  readonly language: string;
  readonly open: boolean;
  readonly onOpen: () => void;
}

let snapshot: StudioBalance | null = null;
const listeners = new Set<() => void>();
export const readStudioBalance = () => snapshot;
export function subscribeStudioBalance(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function publishStudioBalance(value: StudioBalance | null) {
  const published: StudioBalance | null = value ? Object.freeze({ ...value,
    onOpen: () => { if (snapshot === published) value.onOpen(); },
  }) : null;
  snapshot = published;
  listeners.forEach(listener => listener());
}
