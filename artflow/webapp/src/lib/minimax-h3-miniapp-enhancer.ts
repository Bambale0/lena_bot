const H3_MODEL = "minimax-h3/text-to-video";
const GENERATE_VIDEO_PATH = "/api/v1/generate/video";
const UPLOAD_PATH = "/api/web/h3/upload-reference";
const MAX_VIDEOS = 3;
const MAX_AUDIOS = 3;
const MIN_SECONDS = 2;
const MAX_SECONDS = 15;
const MAX_TOTAL_SECONDS = 15;

let selectedVideoFiles: File[] = [];
let selectedAudioFiles: File[] = [];
let fetchInstalled = false;

function selectedModel(): string {
  const selects = Array.from(document.querySelectorAll<HTMLSelectElement>("select"));
  const modelSelect = selects.find((select) =>
    Array.from(select.options).some((option) => option.value === H3_MODEL),
  );
  return modelSelect?.value || "";
}

function parameterGroup(root: HTMLElement, label: string): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>(".apix-parameter-group")).find(
    (group) => group.querySelector("p")?.textContent?.trim() === label,
  ) || null;
}

function primeAutomaticMode(root: HTMLElement): void {
  const modeGroup = parameterGroup(root, "Режим");
  if (!modeGroup) return;
  if (!root.dataset.h3AutoModePrimed) {
    const photoButton = Array.from(modeGroup.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent?.trim() === "Фото",
    );
    if (photoButton) {
      root.dataset.h3AutoModePrimed = "1";
      photoButton.click();
    }
  }
  modeGroup.style.display = "none";
}

function relabelQuality(root: HTMLElement): void {
  const resolutionGroup = parameterGroup(root, "Разрешение");
  const label = resolutionGroup?.querySelector("p");
  if (label) label.textContent = "Качество";
}

function mediaDuration(file: File, kind: "video" | "audio"): Promise<number> {
  return new Promise((resolve, reject) => {
    const media = document.createElement(kind);
    const url = URL.createObjectURL(file);
    media.preload = "metadata";
    media.onloadedmetadata = () => {
      const duration = Number(media.duration || 0);
      URL.revokeObjectURL(url);
      resolve(duration);
    };
    media.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`Не удалось прочитать длительность ${file.name}`));
    };
    media.src = url;
  });
}

async function validateMediaFiles(files: File[], kind: "video" | "audio"): Promise<File[]> {
  const maxCount = kind === "video" ? MAX_VIDEOS : MAX_AUDIOS;
  const maxBytes = (kind === "video" ? 50 : 15) * 1024 * 1024;
  const allowed = kind === "video" ? /\.(mp4|mov)$/i : /\.(mp3|wav)$/i;
  const picked = files.slice(0, maxCount);
  let total = 0;
  for (const file of picked) {
    if (!allowed.test(file.name)) {
      throw new Error(kind === "video" ? "H3 принимает видео MP4/MOV" : "H3 принимает аудио MP3/WAV");
    }
    if (file.size > maxBytes) {
      throw new Error(`${file.name}: файл больше ${kind === "video" ? 50 : 15} МБ`);
    }
    const duration = await mediaDuration(file, kind);
    if (duration < MIN_SECONDS || duration > MAX_SECONDS) {
      throw new Error(`${file.name}: длительность должна быть ${MIN_SECONDS}–${MAX_SECONDS} сек`);
    }
    total += duration;
  }
  if (total > MAX_TOTAL_SECONDS + 0.05) {
    throw new Error(`Суммарная длительность ${kind === "video" ? "видео" : "аудио"} не более ${MAX_TOTAL_SECONDS} сек`);
  }
  return picked;
}

function updateStatus(panel: HTMLElement, error = ""): void {
  const status = panel.querySelector<HTMLElement>("[data-h3-upload-status]");
  if (!status) return;
  status.textContent = error || `Видео: ${selectedVideoFiles.length}/${MAX_VIDEOS} · аудио: ${selectedAudioFiles.length}/${MAX_AUDIOS}`;
  status.style.color = error ? "var(--destructive, #dc2626)" : "";
}

function uploadPanel(root: HTMLElement): void {
  if (root.querySelector("[data-h3-reference-files]")) return;

  const panel = document.createElement("div");
  panel.dataset.h3ReferenceFiles = "1";
  panel.className = "apix-uploader-card";
  panel.style.display = "grid";
  panel.style.gap = "10px";
  panel.style.marginTop = "10px";
  panel.style.padding = "10px";
  panel.innerHTML = `
    <div style="font-weight:700">MiniMax H3 · автоматический режим</div>
    <div style="font-size:12px;opacity:.78;line-height:1.45">
      Ничего выбирать не нужно: без референсов — Text-to-Video; 1 фото — первый кадр; 2 фото — первый+последний; 3+ фото или видео/аудио — Reference-to-Video.
      Фото добавляются в штатном блоке «Референсы» (до 9).
    </div>
    <label style="display:grid;gap:6px">
      <span>Видео-референсы · до ${MAX_VIDEOS}, суммарно до ${MAX_TOTAL_SECONDS} сек</span>
      <input data-h3-video-files type="file" accept="video/mp4,video/quicktime,.mp4,.mov" multiple />
    </label>
    <label style="display:grid;gap:6px">
      <span>Аудио-референсы · до ${MAX_AUDIOS}, суммарно до ${MAX_TOTAL_SECONDS} сек</span>
      <input data-h3-audio-files type="file" accept="audio/mpeg,audio/wav,.mp3,.wav" multiple />
    </label>
    <small>Каждый видео/аудио референс: 2–15 сек. Аудио используется только вместе с фото или видео.</small>
    <small data-h3-upload-status></small>
  `;

  const referenceCard = Array.from(root.querySelectorAll<HTMLElement>(".apix-uploader-card")).find(
    (card) => card.textContent?.includes("Референсы"),
  );
  (referenceCard?.parentElement || root).appendChild(panel);

  panel.querySelector<HTMLInputElement>("[data-h3-video-files]")?.addEventListener("change", async (event) => {
    const input = event.currentTarget as HTMLInputElement;
    try {
      selectedVideoFiles = await validateMediaFiles(Array.from(input.files || []), "video");
      updateStatus(panel);
    } catch (error) {
      selectedVideoFiles = [];
      input.value = "";
      updateStatus(panel, error instanceof Error ? error.message : "Некорректные видео-референсы");
    }
  });
  panel.querySelector<HTMLInputElement>("[data-h3-audio-files]")?.addEventListener("change", async (event) => {
    const input = event.currentTarget as HTMLInputElement;
    try {
      selectedAudioFiles = await validateMediaFiles(Array.from(input.files || []), "audio");
      updateStatus(panel);
    } catch (error) {
      selectedAudioFiles = [];
      input.value = "";
      updateStatus(panel, error instanceof Error ? error.message : "Некорректные аудио-референсы");
    }
  });
  updateStatus(panel);
}

function enhance(): void {
  const selects = Array.from(document.querySelectorAll<HTMLSelectElement>("select"));
  const modelSelect = selects.find((select) =>
    Array.from(select.options).some((option) => option.value === H3_MODEL),
  );
  if (!modelSelect || modelSelect.value !== H3_MODEL) return;

  const root = modelSelect.closest<HTMLElement>(".apix-generation-layout") || document.body;
  primeAutomaticMode(root);
  relabelQuality(root);
  uploadPanel(root);
}

function initData(): string {
  return window.Telegram?.WebApp?.initData || "";
}

async function uploadFile(originalFetch: typeof window.fetch, file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const response = await originalFetch(UPLOAD_PATH, {
    method: "POST",
    body: form,
    headers: { "X-Telegram-Init-Data": initData() },
  });
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    const message = String(payload.error || payload.detail || `HTTP ${response.status}`);
    throw new Error(message);
  }
  const nested = payload.data && typeof payload.data === "object" ? payload.data as Record<string, unknown> : payload;
  const url = String(nested.url || "").trim();
  if (!url) throw new Error("Сервер не вернул URL загруженного референса");
  return url;
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function installFetchBridge(): void {
  if (fetchInstalled) return;
  fetchInstalled = true;
  const originalFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = requestUrl(input);
    const isGeneration = url.includes(GENERATE_VIDEO_PATH) && String(init?.method || "GET").toUpperCase() === "POST";
    if (!isGeneration || typeof init?.body !== "string") return originalFetch(input, init);

    let body: Record<string, unknown>;
    try {
      body = JSON.parse(init.body) as Record<string, unknown>;
    } catch {
      return originalFetch(input, init);
    }
    if (String(body.model || "") !== H3_MODEL) return originalFetch(input, init);

    const uploadedVideos: string[] = [];
    for (const file of selectedVideoFiles.slice(0, MAX_VIDEOS)) {
      uploadedVideos.push(await uploadFile(originalFetch, file));
    }
    const uploadedAudios: string[] = [];
    for (const file of selectedAudioFiles.slice(0, MAX_AUDIOS)) {
      uploadedAudios.push(await uploadFile(originalFetch, file));
    }

    const existingVideo = String(body.video_url || "").trim();
    const existingExtraVideos = Array.isArray(body.character_ids)
      ? body.character_ids.map(String).filter(Boolean)
      : [];
    const allVideos = [existingVideo, ...existingExtraVideos, ...uploadedVideos]
      .filter(Boolean)
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, MAX_VIDEOS);
    body.video_url = allVideos[0] || null;
    body.character_ids = allVideos.slice(1);

    const existingAudio = Array.isArray(body.audio_ids) ? body.audio_ids.map(String).filter(Boolean) : [];
    body.audio_ids = [...existingAudio, ...uploadedAudios]
      .filter(Boolean)
      .filter((item, index, all) => all.indexOf(item) === index)
      .slice(0, MAX_AUDIOS);

    body.mode = "image";
    return originalFetch(input, { ...init, body: JSON.stringify(body) });
  };
}

export function installMiniMaxH3MiniappEnhancer(): void {
  installFetchBridge();
  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      if (selectedModel() !== H3_MODEL) return;
      enhance();
    });
  };
  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  document.addEventListener("change", schedule, true);
  schedule();
}
