const FEED_VIDEO_SELECTOR = 'video[preload="metadata"]:not([controls])';
const PRIME_TIME_SECONDS = 0.08;

const registered = new WeakSet<HTMLVideoElement>();

function primeVideoFrame(video: HTMLVideoElement): void {
  if (video.dataset.apixFramePrimed === "1") return;
  if (!Number.isFinite(video.duration) || video.duration <= 0) return;

  const target = Math.min(PRIME_TIME_SECONDS, Math.max(0.01, video.duration / 100));
  try {
    video.currentTime = target;
    video.dataset.apixFramePrimed = "1";
    video.pause();
  } catch {
    // Some WebViews reject seeking until the first media data arrives.
  }
}

function activateVideo(video: HTMLVideoElement): void {
  if (video.dataset.apixPreviewActive === "1") return;
  video.dataset.apixPreviewActive = "1";
  video.preload = "auto";

  const prime = () => primeVideoFrame(video);
  video.addEventListener("loadedmetadata", prime, { passive: true });
  video.addEventListener("loadeddata", prime, { passive: true });
  video.addEventListener("canplay", prime, { passive: true });

  if (video.readyState >= HTMLMediaElement.HAVE_METADATA) prime();
  try {
    video.load();
  } catch {
    // The browser can still load the existing src normally.
  }
}

function registerVideo(video: HTMLVideoElement, observer: IntersectionObserver | null): void {
  if (registered.has(video)) return;
  registered.add(video);

  if (observer) observer.observe(video);
  else activateVideo(video);
}

export function installFeedVideoStabilizer(): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;

  let intersection: IntersectionObserver | null = null;
  if (typeof IntersectionObserver === "function") {
    intersection = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const video = entry.target as HTMLVideoElement;
          intersection?.unobserve(video);
          activateVideo(video);
        }
      },
      { root: null, rootMargin: "720px 0px", threshold: 0 },
    );
  }

  const scan = (root: ParentNode) => {
    if (root instanceof HTMLVideoElement && root.matches(FEED_VIDEO_SELECTOR)) {
      registerVideo(root, intersection);
    }
    root.querySelectorAll(FEED_VIDEO_SELECTOR).forEach((node) => {
      registerVideo(node as HTMLVideoElement, intersection);
    });
  };

  scan(document);

  const mutations = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node instanceof HTMLElement) scan(node);
      }
    }
  });
  mutations.observe(document.documentElement, { childList: true, subtree: true });
}
