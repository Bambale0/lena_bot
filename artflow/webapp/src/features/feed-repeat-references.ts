type FeedReferenceModel = { max_refs?: number; max_refs_with_video?: number | null; supports_video_input?: boolean };

/** A rendered video is not a video input unless the creator submitted one. */
export function feedUserReferenceCapacity(
  model: FeedReferenceModel | undefined, sourceIsVideo: boolean, requiresVideoInput = sourceIsVideo,
): number {
  const maximum = model?.max_refs;
  if (!Number.isSafeInteger(maximum) || maximum === undefined || maximum < 1) return 0;
  if (sourceIsVideo) {
    if (!requiresVideoInput) return maximum;
    if (model?.supports_video_input !== true) return 0;
    const sharedLimit = model.max_refs_with_video;
    if (sharedLimit == null) return maximum;
    return Number.isSafeInteger(sharedLimit) && sharedLimit >= 0 ? Math.min(maximum, sharedLimit) : 0;
  }
  return maximum - 1;
}
