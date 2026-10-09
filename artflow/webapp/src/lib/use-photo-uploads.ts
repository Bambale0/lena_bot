import { useEffect, useRef } from "react";
import { PhotoUploadQueue, type PhotoUploadContext } from "./photo-upload-queue";

export function usePhotoUploads(context: PhotoUploadContext): PhotoUploadQueue {
  const latest = useRef(context);
  latest.current = context;
  const instance = useRef<PhotoUploadQueue | null>(null);
  if (!instance.current) instance.current = new PhotoUploadQueue(() => latest.current);
  const queue = instance.current;
  useEffect(() => { queue.reconcile(); });
  useEffect(() => () => queue.dispose(), [queue]);
  return queue;
}
