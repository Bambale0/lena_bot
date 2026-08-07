import { MiniAppApi } from "@/lib/api";

const MODEL_KEY = "bytedance/seedance-2-5";
const PANEL_ID = "apix-seedance25-panel";
const TOKEN_PREFIX = "__apix_seedance25:";

type Seedance25Options = {
  scenario: string;
  exactDuration: string;
  autoDuration: boolean;
  outputFormat: "mp4" | "mov";
  generateAudio: boolean;
  returnLastFrame: boolean;
  webSearch: boolean;
  videoRefs: string[];
  audioRefs: string[];
};

type SeedanceWindow = typeof window & {
  __apixSeedance25Options?: Seedance25Options;
  __apixSeedance25Patched?: boolean;
};

const DEFAULT_OPTIONS: Seedance25Options = {
  scenario: "text",
  exactDuration: "",
  autoDuration: false,
  outputFormat: "mp4",
  generateAudio: true,
  returnLastFrame: false,
  webSearch: false,
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

function splitLines(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 10);
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

function renderPanel(): HTMLElement {
  const current = readOptions();
  const panel = document.createElement("div");
  panel.id = PANEL_ID;
  panel.className = "apix-uploader-card grid min-w-0 gap-2 rounded-xl border border-primary/30 bg-primary/5 p-2";
  panel.innerHTML = `
    <div class="min-w-0">
      <p class="text-xs font-semibold">Seedance 2.5 · расширенные параметры</p>
      <p class="text-[10px] text-muted-foreground">Сценарии взаимоисключающие: first/last frame нельзя смешивать с multimodal video/audio refs.</p>
    </div>
    <label class="grid min-w-0 gap-1 text-xs font-medium">
      Сценарий
      <select data-seedance25="scenario" class="w-full rounded-md border bg-background px-2 py-2 text-xs">
        <option value="text">Text-to-video</option>
        <option value="image">First frame</option>
        <option value="first_last">First + last frames</option>
        <option value="multimodal">Multimodal refs</option>
      </select>
    </label>
    <div class="grid min-w-0 gap-2 sm:grid-cols-2">
      <label class="grid min-w-0 gap-1 text-xs font-medium">
        Точная длительность, сек
        <input data-seedance25="exactDuration" type="number" min="4" max="30" placeholder="4–30" class="w-full rounded-md border bg-background px-2 py-2 text-xs" />
      </label>
      <label class="flex min-w-0 items-center gap-2 rounded-md border bg-background/60 px-2 py-2 text-xs font-medium">
        <input data-seedance25="autoDuration" type="checkbox" />
        Auto duration (-1)
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
    <label class="grid min-w-0 gap-1 text-xs font-medium">
      Доп. video refs · до 10
      <textarea data-seedance25="videoRefs" class="min-h-14 w-full rounded-md border bg-background px-2 py-2 font-mono text-xs" placeholder="https://…/ref.mp4&#10;https://…/ref.mov"></textarea>
    </label>
    <label class="grid min-w-0 gap-1 text-xs font-medium">
      Audio refs · до 10
      <textarea data-seedance25="audioRefs" class="min-h-14 w-full rounded-md border bg-background px-2 py-2 font-mono text-xs" placeholder="https://…/sound.mp3&#10;https://…/voice.wav"></textarea>
    </label>
  `;

  const scenario = panel.querySelector<HTMLSelectElement>('[data-seedance25="scenario"]');
  const exactDuration = panel.querySelector<HTMLInputElement>('[data-seedance25="exactDuration"]');
  const autoDuration = panel.querySelector<HTMLInputElement>('[data-seedance25="autoDuration"]');
  const outputFormat = panel.querySelector<HTMLSelectElement>('[data-seedance25="outputFormat"]');
  const generateAudio = panel.querySelector<HTMLInputElement>('[data-seedance25="generateAudio"]');
  const returnLastFrame = panel.querySelector<HTMLInputElement>('[data-seedance25="returnLastFrame"]');
  const webSearch = panel.querySelector<HTMLInputElement>('[data-seedance25="webSearch"]');
  const videoRefs = panel.querySelector<HTMLTextAreaElement>('[data-seedance25="videoRefs"]');
  const audioRefs = panel.querySelector<HTMLTextAreaElement>('[data-seedance25="audioRefs"]');

  if (scenario) scenario.value = current.scenario;
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
      scenario: scenario?.value || "text",
      exactDuration: exactDuration?.value || "",
      autoDuration: Boolean(autoDuration?.checked),
      outputFormat: outputFormat?.value === "mov" ? "mov" : "mp4",
      generateAudio: Boolean(generateAudio?.checked),
      returnLastFrame: Boolean(returnLastFrame?.checked),
      webSearch: Boolean(webSearch?.checked),
      videoRefs: splitLines(videoRefs?.value || ""),
      audioRefs: splitLines(audioRefs?.value || ""),
    });
  });
  panel.addEventListener("change", () => panel.dispatchEvent(new Event("input", { bubbles: true })));
  return panel;
}

function mountPanel(): void {
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

function patchCreateVideo(): void {
  const win = window as SeedanceWindow;
  if (win.__apixSeedance25Patched) return;
  const original = MiniAppApi.prototype.createVideo;
  MiniAppApi.prototype.createVideo = function patchedCreateVideo(body: Record<string, unknown>) {
    if (body.model === MODEL_KEY) {
      const options = readOptions();
      const audioIds = Array.isArray(body.audio_ids) ? [...body.audio_ids.map(String)] : [];
      const videoRefs = [...options.videoRefs];
      if (!body.video_url && videoRefs.length) {
        body.video_url = videoRefs.shift() || null;
      }
      const tokens = [
        token("scenario", options.scenario),
        token("output_format", options.outputFormat),
        token("generate_audio", options.generateAudio),
        token("return_last_frame", options.returnLastFrame),
        token("web_search", options.webSearch),
      ];
      if (options.autoDuration) tokens.push(token("duration", -1));
      else if (options.exactDuration) tokens.push(token("duration", Math.max(4, Math.min(30, Number(options.exactDuration) || 5))));
      for (const url of videoRefs) tokens.push(token("video_ref", url));
      for (const url of options.audioRefs) tokens.push(token("audio_ref", url));
      body.mode = options.scenario === "reference" ? "multimodal" : options.scenario;
      body.grok_mode = body.mode;
      body.audio_ids = [...audioIds, ...tokens];
    }
    return original.call(this, body);
  };
  win.__apixSeedance25Patched = true;
}

export function installSeedance25MiniappEnhancer(): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  patchCreateVideo();
  window.setInterval(mountPanel, 600);
  document.addEventListener("change", (event) => {
    if (event.target instanceof HTMLSelectElement) mountPanel();
  });
  window.setTimeout(mountPanel, 0);
  window.setTimeout(mountPanel, 1200);
}
