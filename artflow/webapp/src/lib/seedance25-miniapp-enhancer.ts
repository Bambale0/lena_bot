import { MiniAppApi } from "@/lib/api";

const MODEL_KEY = "bytedance/seedance-2-5";
const PANEL_ID = "apix-seedance25-panel";
const TOKEN_PREFIX = "__apix_seedance25:";
const UPLOAD_PATH = "/api/web/seedance25/upload-reference";

const MAX_IMAGES = 30;
const MAX_VIDEOS = 10;
const MAX_AUDIOS = 10;

type Seedance25Options = {
  exactDuration: string;
  autoDuration: boolean;
  outputFormat: "mp4" | "mov";
  generateAudio: boolean;
  returnLastFrame: boolean;
  webSearch: boolean;
  imageFiles: File[];
  videoFiles: File[];
  audioFiles: File[];
  videoRefs: string[];
  audioRefs: string[];
};

type SeedanceWindow = typeof window & {
  __apixSeedance25Options?: Seedance25Options;
  __apixSeedance25Patched?: boolean;
};

const DEFAULT_OPTIONS: Seedance25Options = {
  exactDuration: "",
  autoDuration: false,
  outputFormat: "mp4",
  generateAudio: true,
  returnLastFrame: false,
  webSearch: false,
  imageFiles: [],
  videoFiles: [],
  audioFiles: [],
  videoRefs: [],
  audioRefs: [],
};

function readOptions(): Seedance25Options {
  const win = window as SeedanceWindow;
  return { ...DEFAULT_OPTIONS, ...(win.__apixSeedance25Options || {}) };
}

function writeOptions(patch: Partial<Seedance25Options>): void {
  const win = window as SeedanceWindow;
  win.__apixSeedance25Options = { ...readOptions(), ...patch };
}

function splitLines(value: string, limit: number): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, limit);
}

function token(key: string, value: string | boolean | number): string {
  return `${TOKEN_PREFIX}${key}=${String(value)}`;
}

function selectedModelSelect(): HTMLSelectElement | null {
  return Array.from(document.querySelectorAll("select")).find((select) => {
    const htmlSelect = select as HTMLSelectElement;
    return Array.from(htmlSelect.options).some((option) => option.value === MODEL_KEY);
  }) as HTMLSelectElement | undefined || null;
}

function isSeedance25Selected(): boolean {
  return selectedModelSelect()?.value === MODEL_KEY;
}

function parameterGroup(root: HTMLElement, title: string): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>(".apix-parameter-group")).find(
    (group) => group.querySelector("p")?.textContent?.trim() === title,
  ) || null;
}

function genericReferenceCard(root: HTMLElement): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>(".apix-uploader-card")).find(
    (card) => card.id !== PANEL_ID && card.textContent?.includes("Референсы"),
  ) || null;
}

function applyAutomaticSurface(): void {
  const select = selectedModelSelect();
  const root = select?.closest<HTMLElement>(".apix-generation-layout") || document.body;
  const mode = parameterGroup(root, "Режим");
  const genericRefs = genericReferenceCard(root);

  if (!isSeedance25Selected()) {
    if (mode) mode.style.display = "";
    if (genericRefs) genericRefs.style.display = "";
    return;
  }

  // Provider scenario is an implementation detail. Seedance derives it from refs.
  if (mode) mode.style.display = "none";
  if (genericRefs) genericRefs.style.display = "none";
}

function renderPanel(): HTMLElement {
  const current = readOptions();
  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.className = "apix-uploader-card grid min-w-0 gap-2 rounded-xl border border-primary/30 bg-primary/5 p-2";
  panel.innerHTML = `
    <div class="min-w-0">
      <p class="text-xs font-semibold">Seedance 2.5 · референсы</p>
      <p class="text-[10px] text-muted-foreground">
        Режим определяется автоматически: без референсов — текст → видео; ровно 1 фото — первый кадр; 2+ фото или любое видео/аудио — мультимодальные референсы.
      </p>
    </div>
    <label class="grid min-w-0 gap-1 text-xs font-medium">
      Фото · до ${MAX_IMAGES}
      <input data-seedance25="imageFiles" type="file" accept="image/*" multiple class="w-full text-xs" />
    </label>
    <label class="grid min-w-0 gap-1 text-xs font-medium">
      Видео · до ${MAX_VIDEOS}
      <input data-seedance25="videoFiles" type="file" accept="video/mp4,video/quicktime,video/x-matroska,.mp4,.mov,.mkv" multiple class="w-full text-xs" />
    </label>
    <label class="grid min-w-0 gap-1 text-xs font-medium">
      Аудио · до ${MAX_AUDIOS}
      <input data-seedance25="audioFiles" type="file" accept="audio/*,.mp3,.wav,.aac,.m4a,.ogg" multiple class="w-full text-xs" />
    </label>
    <div class="grid min-w-0 gap-2 sm:grid-cols-2">
      <label class="grid min-w-0 gap-1 text-xs font-medium">
        Доп. video refs по URL
        <textarea data-seedance25="videoRefs" class="min-h-14 w-full rounded-md border bg-background px-2 py-2 font-mono text-xs" placeholder="https://…/ref.mp4"></textarea>
      </label>
      <label class="grid min-w-0 gap-1 text-xs font-medium">
        Audio refs по URL
        <textarea data-seedance25="audioRefs" class="min-h-14 w-full rounded-md border bg-background px-2 py-2 font-mono text-xs" placeholder="https://…/sound.mp3"></textarea>
      </label>
    </div>
    <div class="grid min-w-0 gap-2 sm:grid-cols-2">
      <label class="grid min-w-0 gap-1 text-xs font-medium">
        Точная длительность, сек
        <input data-seedance25="exactDuration" type="number" min="4" max="30" placeholder="4–30" class="w-full rounded-md border bg-background px-2 py-2 text-xs" />
      </label>
      <label class="flex min-w-0 items-center gap-2 rounded-md border bg-background/60 px-2 py-2 text-xs font-medium">
        <input data-seedance25="autoDuration" type="checkbox" />
        Auto duration
      </label>
    </div>
    <div class="grid min-w-0 gap-2 sm:grid-cols-3">
      <label class="grid min-w-0 gap-1 text-xs font-medium">
        Output
        <select data-seedance25="outputFormat" class="w-full rounded-md border bg-background px-2 py-2 text-xs">
          <option value="mp4">mp4</option>
          <option value="mov">mov</option>
        </select>
      </label>
      <label class="flex min-w-0 items-center gap-2 rounded-md border bg-background/60 px-2 py-2 text-xs font-medium">
        <input data-seedance25="generateAudio" type="checkbox" />
        Generate audio
      </label>
      <label class="flex min-w-0 items-center gap-2 rounded-md border bg-background/60 px-2 py-2 text-xs font-medium">
        <input data-seedance25="returnLastFrame" type="checkbox" />
        Return last frame
      </label>
    </div>
    <label class="flex min-w-0 items-center gap-2 rounded-md border bg-background/60 px-2 py-2 text-xs font-medium">
      <input data-seedance25="webSearch" type="checkbox" />
      Web search grounding
    </label>
  `;

  const exactDuration = panel.querySelector<HTMLInputElement>('[data-seedance25="exactDuration"]');
  const autoDuration = panel.querySelector<HTMLInputElement>('[data-seedance25="autoDuration"]');
  const outputFormat = panel.querySelector<HTMLSelectElement>('[data-seedance25="outputFormat"]');
  const generateAudio = panel.querySelector<HTMLInputElement>('[data-seedance25="generateAudio"]');
  const returnLastFrame = panel.querySelector<HTMLInputElement>('[data-seedance25="returnLastFrame"]');
  const webSearch = panel.querySelector<HTMLInputElement>('[data-seedance25="webSearch"]');
  const imageFiles = panel.querySelector<HTMLInputElement>('[data-seedance25="imageFiles"]');
  const videoFiles = panel.querySelector<HTMLInputElement>('[data-seedance25="videoFiles"]');
  const audioFiles = panel.querySelector<HTMLInputElement>('[data-seedance25="audioFiles"]');
  const videoRefs = panel.querySelector<HTMLTextAreaElement>('[data-seedance25="videoRefs"]');
  const audioRefs = panel.querySelector<HTMLTextAreaElement>('[data-seedance25="audioRefs"]');

  if (exactDuration) exactDuration.value = current.exactDuration;
  if (autoDuration) autoDuration.checked = current.autoDuration;
  if (outputFormat) outputFormat.value = current.outputFormat;
  if (generateAudio) generateAudio.checked = current.generateAudio;
  if (returnLastFrame) returnLastFrame.checked = current.returnLastFrame;
  if (webSearch) webSearch.checked = current.webSearch;
  if (videoRefs) videoRefs.value = current.videoRefs.join("\n");
  if (audioRefs) audioRefs.value = current.audioRefs.join("\n");

  panel.addEventListener("input", () => {
    writeOptions({
      exactDuration: exactDuration?.value || "",
      autoDuration: Boolean(autoDuration?.checked),
      outputFormat: outputFormat?.value === "mov" ? "mov" : "mp4",
      generateAudio: Boolean(generateAudio?.checked),
      returnLastFrame: Boolean(returnLastFrame?.checked),
      webSearch: Boolean(webSearch?.checked),
      imageFiles: Array.from(imageFiles?.files || []).slice(0, MAX_IMAGES),
      videoFiles: Array.from(videoFiles?.files || []).slice(0, MAX_VIDEOS),
      audioFiles: Array.from(audioFiles?.files || []).slice(0, MAX_AUDIOS),
      videoRefs: splitLines(videoRefs?.value || "", MAX_VIDEOS),
      audioRefs: splitLines(audioRefs?.value || "", MAX_AUDIOS),
    });
  });
  panel.addEventListener("change", () => panel.dispatchEvent(new Event("input", { bubbles: true })));
  return panel;
}

function mountPanel(): void {
  applyAutomaticSurface();
  const existing = document.getElementById(PANEL_ID);
  if (!isSeedance25Selected()) {
    existing?.remove();
    return;
  }
  if (existing) return;
  const select = selectedModelSelect();
  const modelLabel = select?.closest("label");
  if (!modelLabel?.parentElement) return;
  modelLabel.insertAdjacentElement("afterend", renderPanel());
}

function initData(): string {
  return window.Telegram?.WebApp?.initData || "";
}

async function uploadReference(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(UPLOAD_PATH, {
    method: "POST",
    body: form,
    headers: { "X-Telegram-Init-Data": initData() },
  });
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) throw new Error(String(payload.error || payload.detail || `HTTP ${response.status}`));
  const data = payload.data && typeof payload.data === "object" ? payload.data as Record<string, unknown> : payload;
  const url = String(data.url || "").trim();
  if (!url) throw new Error("Seedance 2.5 upload did not return a URL");
  return url;
}

function unique(values: string[]): string[] {
  return values.filter(Boolean).filter((item, index, all) => all.indexOf(item) === index);
}

function patchCreateVideo(): void {
  const win = window as SeedanceWindow;
  if (win.__apixSeedance25Patched) return;
  const original = MiniAppApi.prototype.createVideo;

  MiniAppApi.prototype.createVideo = async function patchedCreateVideo(body: Record<string, unknown>) {
    if (body.model === MODEL_KEY) {
      const options = readOptions();

      const uploadedImages = await Promise.all(options.imageFiles.map(uploadReference));
      const uploadedVideos = await Promise.all(options.videoFiles.map(uploadReference));
      const uploadedAudios = await Promise.all(options.audioFiles.map(uploadReference));

      const existingImages = unique([
        String(body.image_url || "").trim(),
        ...(Array.isArray(body.reference_urls) ? body.reference_urls.map(String) : []),
      ]);
      const images = unique([...existingImages, ...uploadedImages]).slice(0, MAX_IMAGES);
      body.image_url = images[0] || null;
      body.reference_urls = images.slice(1);

      const existingVideo = String(body.video_url || "").trim();
      const videoRefs = unique([existingVideo, ...options.videoRefs, ...uploadedVideos]).slice(0, MAX_VIDEOS);
      body.video_url = videoRefs[0] || null;

      const audioIds = Array.isArray(body.audio_ids) ? body.audio_ids.map(String) : [];
      const audioRefs = unique([...audioIds, ...options.audioRefs, ...uploadedAudios]).slice(0, MAX_AUDIOS);
      const tokens = [
        token("output_format", options.outputFormat),
        token("generate_audio", options.generateAudio),
        token("return_last_frame", options.returnLastFrame),
        token("web_search", options.webSearch),
        ...videoRefs.slice(1).map((url) => token("video_ref", url)),
      ];
      if (options.autoDuration) tokens.push(token("duration", -1));
      else if (options.exactDuration) {
        tokens.push(token("duration", Math.max(4, Math.min(30, Number(options.exactDuration) || 5))));
      }

      // UI mode is deliberately meaningless for Seedance 2.5. Backend derives
      // text / first-frame / multimodal from the actual refs above.
      body.mode = "text";
      body.grok_mode = null;
      body.audio_ids = [...audioRefs, ...tokens];
      body.character_ids = [];
    }
    return original.call(this, body);
  };
  win.__apixSeedance25Patched = true;
}

export function installSeedance25MiniappEnhancer(): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  patchCreateVideo();
  window.setInterval(mountPanel, 600);
  document.addEventListener("change", () => mountPanel(), true);
  window.setTimeout(mountPanel, 0);
  window.setTimeout(mountPanel, 1200);
}
