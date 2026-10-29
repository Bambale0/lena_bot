import assert from "node:assert/strict";
import test from "node:test";

import { installFeedVideoStabilizer } from "../../src/lib/feed-video-stabilizer.ts";

test("a metadata-ready preview is primed only after the post-load seek produces a frame", (t) => {
  class ElementStub extends EventTarget {
    querySelectorAll() { return []; }
  }

  class VideoStub extends ElementStub {
    static HAVE_NOTHING = 0;
    static HAVE_METADATA = 1;
    static HAVE_CURRENT_DATA = 2;

    dataset: Record<string, string> = {};
    preload = "metadata";
    controls = false;
    autoplay = false;
    readyState = VideoStub.HAVE_METADATA;
    duration = 8;
    paused = true;
    seeking = false;
    videoWidth = 320;
    videoHeight = 180;
    decodedFrameTime: number | null = null;
    position = 0;

    get currentTime() { return this.position; }
    set currentTime(value: number) {
      this.position = value;
      this.seeking = true;
      this.decodedFrameTime = null;
    }

    matches() {
      return this.preload === "metadata" && !this.controls && !this.autoplay;
    }

    pause() { this.paused = true; }

    load() {
      // A reload discards an earlier seek, even if assigning currentTime succeeded.
      // The DOM dataset survives; decoded media state and position do not.
      this.readyState = VideoStub.HAVE_NOTHING;
      this.duration = Number.NaN;
      this.position = 0;
      this.seeking = false;
      this.videoWidth = this.videoHeight = 0;
      this.decodedFrameTime = null;
      this.dispatchEvent(new Event("emptied"));
      this.dispatchEvent(new Event("loadstart"));
    }

    receiveMetadata() {
      this.duration = 8;
      this.videoWidth = 320;
      this.videoHeight = 180;
      this.readyState = VideoStub.HAVE_METADATA;
      this.dispatchEvent(new Event("loadedmetadata"));
    }

    receiveCurrentFrame() {
      this.decodedFrameTime = this.position;
      this.seeking = false;
      this.readyState = VideoStub.HAVE_CURRENT_DATA;
      this.dispatchEvent(new Event("loadeddata"));
      this.dispatchEvent(new Event("seeked"));
    }
  }

  const video = new VideoStub();
  const observers: IntersectionObserverStub[] = [];
  class IntersectionObserverStub {
    observed = new Set<VideoStub>();
    callback: (entries: { target: VideoStub; isIntersecting: boolean }[]) => void;

    constructor(callback: IntersectionObserverStub["callback"]) {
      this.callback = callback;
      observers.push(this);
    }

    observe(target: VideoStub) { this.observed.add(target); }
    unobserve(target: VideoStub) { this.observed.delete(target); }
    disconnect() { this.observed.clear(); }
    enterViewport(target: VideoStub) {
      assert.ok(this.observed.has(target), "The preview must be registered for viewport activation");
      this.callback([{ target, isIntersecting: true }]);
    }
  }

  class MutationObserverStub {
    observe() {}
    disconnect() {}
  }

  const documentStub = {
    documentElement: new ElementStub(),
    querySelectorAll: () => [video],
  };
  const globals: Record<string, unknown> = {
    window: {},
    document: documentStub,
    HTMLElement: ElementStub,
    HTMLMediaElement: VideoStub,
    HTMLVideoElement: VideoStub,
    IntersectionObserver: IntersectionObserverStub,
    MutationObserver: MutationObserverStub,
  };
  const previous = new Map(Object.keys(globals).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  t.after(() => {
    for (const [key, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else Reflect.deleteProperty(globalThis, key);
    }
  });
  for (const [key, value] of Object.entries(globals)) {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  }

  installFeedVideoStabilizer();
  const observer = observers[0];
  assert.ok(observer, "Preview loading must remain gated by viewport visibility");
  assert.equal(video.currentTime, 0, "Registration alone must not seek an offscreen preview");
  observer.enterViewport(video);

  assert.notEqual(video.dataset.apixFramePrimed, "1", "Metadata or a seek discarded by load() is not a decoded preview frame");
  if (video.readyState === VideoStub.HAVE_NOTHING) video.receiveMetadata();
  assert.ok(video.currentTime > 0 && video.currentTime < video.duration, "The active resource must seek to a frame after any load reset");
  assert.equal(video.seeking, true);
  assert.equal(video.decodedFrameTime, null);
  assert.notEqual(video.dataset.apixFramePrimed, "1", "Accepting currentTime must not report a frame before decoding completes");

  video.receiveCurrentFrame();
  assert.ok(video.decodedFrameTime !== null && video.decodedFrameTime > 0);
  assert.equal(video.dataset.apixFramePrimed, "1", "A confirmed current frame completes preview priming");
});
