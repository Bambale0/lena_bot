const H3_MODEL = "minimax-h3/text-to-video";
const SEEDANCE25_MODEL = "bytedance/seedance-2-5";

type AppTabEvent = CustomEvent<{ tab?: string }>;

const installed = new Set<string>();
let scheduled = false;

async function installModelEnhancer(modelKey: string): Promise<void> {
  if (!modelKey || installed.has(modelKey)) return;
  installed.add(modelKey);
  try {
    if (modelKey === H3_MODEL) {
      const module = await import("@/lib/minimax-h3-miniapp-enhancer");
      module.installMiniMaxH3MiniappEnhancer();
      return;
    }
    if (modelKey === SEEDANCE25_MODEL) {
      const module = await import("@/lib/seedance25-miniapp-enhancer");
      module.installSeedance25MiniappEnhancer();
    }
  } catch (error) {
    installed.delete(modelKey);
    console.error("[APIX] Failed to load model enhancer", modelKey, error);
  }
}

async function installServicesEnhancer(): Promise<void> {
  const key = "services:suno-source-audio";
  if (installed.has(key)) return;
  installed.add(key);
  try {
    const module = await import("@/lib/suno-source-audio-enhancer");
    module.installSunoSourceAudioEnhancer();
  } catch (error) {
    installed.delete(key);
    console.error("[APIX] Failed to load services enhancer", error);
  }
}

function selectedAdvancedModel(): string {
  const selects = document.querySelectorAll<HTMLSelectElement>("select");
  for (const select of selects) {
    if (select.value === H3_MODEL || select.value === SEEDANCE25_MODEL) return select.value;
  }
  return "";
}

function scan(): void {
  scheduled = false;
  const modelKey = selectedAdvancedModel();
  if (modelKey) void installModelEnhancer(modelKey);
}

function scheduleScan(): void {
  if (scheduled) return;
  scheduled = true;
  window.requestAnimationFrame(scan);
}

/**
 * Advanced provider adapters are intentionally absent from the initial bundle.
 * They are loaded only when the user enters the relevant model/surface.
 * This keeps their legacy DOM observers/polling off the main thread for the
 * common Feed/Profile/basic-generation interaction path.
 */
function installModelEnhancerLoader(): () => void {
  if (typeof document === "undefined") return () => undefined;

  const onChange = (event: Event) => {
    const target = event.target;
    if (target instanceof HTMLSelectElement && (target.value === H3_MODEL || target.value === SEEDANCE25_MODEL)) {
      void installModelEnhancer(target.value);
    }
  };

  const onTabChange = (event: Event) => {
    const tab = String((event as AppTabEvent).detail?.tab || "");
    if (tab === "services") void installServicesEnhancer();
    if (tab === "video" || tab === "motion") scheduleScan();
  };

  document.addEventListener("change", onChange, true);
  window.addEventListener("apix:tab-change", onTabChange);
  // One bounded post-mount scan supports deep-linked generation screens without
  // installing any permanent DOM observer or timer.
  window.requestAnimationFrame(() => window.requestAnimationFrame(scheduleScan));

  return () => {
    document.removeEventListener("change", onChange, true);
    window.removeEventListener("apix:tab-change", onTabChange);
  };
}

export { installModelEnhancerLoader };
