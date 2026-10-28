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
    (card) => card.id !== PANEL_ID && Boolean(card.querySelector<HTMLInputElement>('input[type="file"][accept*="image"]')),
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

  // Provider scenario is an implementation detail. The React screen mounts its
  // standard photo-reference uploader explicitly for Seedance 2.5.
  if (mode) mode.style.display = "none";
  const mountedRefs = genericReferenceCard(root);
  if (mountedRefs) mountedRefs.style.display = "";
}

function renderPanel(): HTMLElement {
  const current = readOptions();
  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.className = "apix-uploader-card seedance25-guided grid min-w-0 gap-3 rounded-xl border border-primary/30 bg-primary/5 p-3";
  panel.setAttribute("role", "group");
  panel.setAttribute("aria-label", "Материалы Seedance 2.5");
  panel.innerHTML = `
    <div class="seedance25-guided-head min-w-0">
      <p class="text-sm font-semibold">Добавьте материалы</p>
      <p class="text-[10px] text-muted-foreground">
        Можно выбрать один тип или сочетать несколько. Без файлов видео создаётся только по тексту; первый кадр отдельно не используется.
      </p>
    </div>
    <div class="seedance25-materials grid min-w-0 grid-cols-3 gap-2">
      <button type="button" data-seedance25-material="photo" class="seedance25-material">
        <span aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8" cy="9" r="1.5"/><path d="m3 17 6-5 4 4 3-3 5 5"/></svg></span><strong>Фото</strong><small>до ${MAX_IMAGES}</small>
      </button>
      <button type="button" data-seedance25-material="video" class="seedance25-material">
        <span aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4M10 9l4 3-4 3Z"/></svg></span><strong>Видео</strong><small data-seedance25-count="video">до ${MAX_VIDEOS}</small>
      </button>
      <button type="button" data-seedance25-material="audio" class="seedance25-material">
        <span aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/></svg></span><strong>Аудио</strong><small data-seedance25-count="audio">до ${MAX_AUDIOS}</small>
      </button>
    </div>
    <input data-seedance25="videoFiles" type="file" accept="video/mp4,video/quicktime,.mp4,.mov" multiple class="sr-only" />
    <input data-seedance25="audioFiles" type="file" accept="audio/*,.mp3,.wav,.aac,.m4a,.ogg" multiple class="sr-only" />
    <details class="seedance25-advanced apix-help">
      <summary>Дополнительные настройки</summary>
      <div class="grid min-w-0 gap-2 pt-2">
        <p class="text-[10px] text-muted-foreground">Качество 480p / 720p / 1080p выбирается в общих параметрах ниже.</p>
        <div class="grid min-w-0 gap-2 sm:grid-cols-2">
          <label class="grid min-w-0 gap-1 text-xs font-medium">Ссылки на видео
            <textarea data-seedance25="videoRefs" class="min-h-14 w-full rounded-md border bg-background px-2 py-2 text-xs" placeholder="Одна ссылка на строку"></textarea>
          </label>
          <label class="grid min-w-0 gap-1 text-xs font-medium">Ссылки на аудио
            <textarea data-seedance25="audioRefs" class="min-h-14 w-full rounded-md border bg-background px-2 py-2 text-xs" placeholder="Одна ссылка на строку"></textarea>
          </label>
        </div>
        <div class="grid min-w-0 gap-2 sm:grid-cols-2">
          <label class="grid min-w-0 gap-1 text-xs font-medium">Точная длительность, сек
            <input data-seedance25="exactDuration" type="number" min="4" max="30" placeholder="4–30" class="w-full rounded-md border bg-background px-2 py-2 text-xs" />
          </label>
          <label class="seedance25-check"><input data-seedance25="autoDuration" type="checkbox" />Автоматическая длительность</label>
        </div>
        <label class="grid min-w-0 gap-1 text-xs font-medium">Формат файла
          <select data-seedance25="outputFormat" class="w-full rounded-md border bg-background px-2 py-2 text-xs"><option value="mp4">MP4</option><option value="mov">MOV</option></select>
        </label>
        <label class="seedance25-check"><input data-seedance25="generateAudio" type="checkbox" />Создавать звук</label>
        <label class="seedance25-check"><input data-seedance25="returnLastFrame" type="checkbox" />Вернуть последний кадр</label>
        <label class="seedance25-check"><input data-seedance25="webSearch" type="checkbox" />Использовать поиск в интернете</label>
      </div>
    </details>
  `;

  const exactDuration = panel.querySelector<HTMLInputElement>('[data-seedance25="exactDuration"]');
  const autoDuration = panel.querySelector<HTMLInputElement>('[data-seedance25="autoDuration"]');
  const outputFormat = panel.querySelector<HTMLSelectElement>('[data-seedance25="outputFormat"]');
  const generateAudio = panel.querySelector<HTMLInputElement>('[data-seedance25="generateAudio"]');
  const returnLastFrame = panel.querySelector<HTMLInputElement>('[data-seedance25="returnLastFrame"]');
  const webSearch = panel.querySelector<HTMLInputElement>('[data-seedance25="webSearch"]');
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

  panel.querySelector<HTMLButtonElement>('[data-seedance25-material="photo"]')?.addEventListener("click", () => {
    const select = selectedModelSelect();
    const root = select?.closest<HTMLElement>(".apix-generation-layout") || document.body;
    genericReferenceCard(root)?.querySelector<HTMLInputElement>('input[type="file"]')?.click();
  });
  panel.querySelector<HTMLButtonElement>('[data-seedance25-material="video"]')?.addEventListener("click", () => videoFiles?.click());
  panel.querySelector<HTMLButtonElement>('[data-seedance25-material="audio"]')?.addEventListener("click", () => audioFiles?.click());

  const sync = () => {
    const selectedVideos = Array.from(videoFiles?.files || []).slice(0, MAX_VIDEOS);
    const selectedAudios = Array.from(audioFiles?.files || []).slice(0, MAX_AUDIOS);
    writeOptions({
      exactDuration: exactDuration?.value || "",
      autoDuration: Boolean(autoDuration?.checked),
      outputFormat: outputFormat?.value === "mov" ? "mov" : "mp4",
      generateAudio: Boolean(generateAudio?.checked),
      returnLastFrame: Boolean(returnLastFrame?.checked),
      webSearch: Boolean(webSearch?.checked),
      videoFiles: selectedVideos,
      audioFiles: selectedAudios,
      videoRefs: splitLines(videoRefs?.value || "", MAX_VIDEOS),
      audioRefs: splitLines(audioRefs?.value || "", MAX_AUDIOS),
    });
    const videoCount = panel.querySelector<HTMLElement>('[data-seedance25-count="video"]');
    const audioCount = panel.querySelector<HTMLElement>('[data-seedance25-count="audio"]');
    if (videoCount) videoCount.textContent = selectedVideos.length ? `Выбрано: ${selectedVideos.length}` : `до ${MAX_VIDEOS}`;
    if (audioCount) audioCount.textContent = selectedAudios.length ? `Выбрано: ${selectedAudios.length}` : `до ${MAX_AUDIOS}`;
  };
  panel.addEventListener("input", sync);
  panel.addEventListener("change", sync);
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
  const originalCreate = MiniAppApi.prototype.createVideo;
  const originalQuote = MiniAppApi.prototype.quoteVideo;

  const enrichVideoBody = async (body: Record<string, unknown>) => {
    body = { ...body };
    if (body.model === MODEL_KEY) {
      const options = readOptions();

      const uploadedVideos = await Promise.all(options.videoFiles.map(uploadReference));
      const uploadedAudios = await Promise.all(options.audioFiles.map(uploadReference));

      const existingImages = unique([
        String(body.image_url || "").trim(),
        ...(Array.isArray(body.reference_urls) ? body.reference_urls.map(String) : []),
      ]);
      const images = existingImages.slice(0, MAX_IMAGES);
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
      // text / multimodal from the actual refs above. Keep the
      // generic request field schema-valid: VideoGenRequest.grok_mode is a str.
      body.mode = "text";
      body.grok_mode = "normal";
      body.audio_ids = [...audioRefs, ...tokens];
      body.character_ids = [];
    }
    return body;
  };
  MiniAppApi.prototype.createVideo = async function patchedCreateVideo(body: Record<string, unknown>) {
    return originalCreate.call(this, await enrichVideoBody(body));
  };
  MiniAppApi.prototype.quoteVideo = async function patchedQuoteVideo(body: Record<string, unknown>) {
    return originalQuote.call(this, await enrichVideoBody(body));
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
