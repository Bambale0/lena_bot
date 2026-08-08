const H3_MODEL = "minimax-h3/text-to-video";
const GENERATE_VIDEO_PATH = "/api/v1/generate/video";
const UPLOAD_PATH = "/api/web/h3/upload-reference";
const MAX_IMAGES = 9;
const MAX_VIDEOS = 3;
const MAX_AUDIOS = 3;
const MAX_FILES = 12;
const MIN_SECONDS = 2;
const MAX_SECONDS = 15;
const MAX_TOTAL_SECONDS = 15;

let selectedImageFiles: File[] = [];
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

function genericReferenceCard(root: HTMLElement): HTMLElement | null {
  return Array.from(root.querySelectorAll<HTMLElement>(".apix-uploader-card")).find(
    (card) => card.textContent?.includes("Референсы") && !card.dataset.h3ReferenceFiles,
  ) || null;
}

function cleanup(root: HTMLElement): void {
  const modeGroup = parameterGroup(root, "Режим");
  if (modeGroup) modeGroup.style.display = "";
  const resolutionGroup = parameterGroup(root, "Качество") || parameterGroup(root, "Разрешение");
  const label = resolutionGroup?.querySelector("p");
  if (label) label.textContent = "Разрешение";
  const referenceCard = genericReferenceCard(root);
  if (referenceCard) referenceCard.style.display = "";
  const panel = root.querySelector<HTMLElement>("[data-h3-reference-files]");
  if (panel) panel.style.display = "none";
}

function configureAutomaticSurface(root: HTMLElement): void {
  const modeGroup = parameterGroup(root, "Режим");
  if (modeGroup) modeGroup.style.display = "none";

  const resolutionGroup = parameterGroup(root, "Разрешение") || parameterGroup(root, "Качество");
  const label = resolutionGroup?.querySelector("p");
  if (label) label.textContent = "Качество";

  const referenceCard = genericReferenceCard(root);
  if (referenceCard) referenceCard.style.display = "none";
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

function validateImageFiles(files: File[]): File[] {
  const picked = files.slice(0, MAX_IMAGES);
  const allowed = /\.(jpe?g|png|webp|heic|heif)$/i;
  for (const file of picked) {
    if (!allowed.test(file.name)) {
      throw new Error("H3 принимает изображения JPG/JPEG/PNG/WEBP/HEIC/HEIF");
    }
    if (file.size > 30 * 1024 * 1024) {
      throw new Error(`${file.name}: изображение больше 30 МБ`);
    }
  }
  return picked;
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
  status.textContent = error || (
    `Фото: ${selectedImageFiles.length}/${MAX_IMAGES} · видео: ${selectedVideoFiles.length}/${MAX_VIDEOS} · ` +
    `аудио: ${selectedAudioFiles.length}/${MAX_AUDIOS}`
  );
  status.style.color = error ? "var(--destructive, #dc2626)" : "";
}

function uploadPanel(root: HTMLElement): void {
  const existing = root.querySelector<HTMLElement>("[data-h3-reference-files]");
  if (existing) {
    existing.style.display = "grid";
    return;
  }

  const panel = document.createElement("div");
  panel.dataset.h3ReferenceFiles = "1";
  panel.className = "apix-uploader-card";
  panel.style.display = "grid";
  panel.style.gap = "10px";
  panel.style.marginTop = "10px";
  panel.style.padding = "10px";
  panel.innerHTML = `
    <div style="font-weight:700">MiniMax H3 · референсы</div>
    <div style="font-size:12px;opacity:.78;line-height:1.45">
      Режим выбирается автоматически: без файлов — Text-to-Video; 1 фото — первый кадр; 2 фото — первый+последний; 3+ фото или любое видео/аудио — Reference-to-Video.
    </div>
    <label style="display:grid;gap:6px">
      <span>Фото · до ${MAX_IMAGES}</span>
      <input data-h3-image-files type="file" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp,.heic,.heif" multiple />
    </label>
    <label style="display:grid;gap:6px">
      <span>Видео · до ${MAX_VIDEOS}, суммарно до ${MAX_TOTAL_SECONDS} сек</span>
      <input data-h3-video-files type="file" accept="video/mp4,video/quicktime,.mp4,.mov" multiple />
    </label>
    <label style="display:grid;gap:6px">
      <span>Аудио · до ${MAX_AUDIOS}, суммарно до ${MAX_TOTAL_SECONDS} сек</span>
      <input data-h3-audio-files type="file" accept="audio/mpeg,audio/wav,.mp3,.wav" multiple />
    </label>
    <small>Все типы вместе: до ${MAX_FILES} файлов. Видео/аудио: каждый 2–15 сек. Аудио не может быть единственным референсом.</small>
    <small data-h3-upload-status></small>
  `;

  const referenceCard = genericReferenceCard(root);
  (referenceCard?.parentElement || root).appendChild(panel);

  panel.querySelector<HTMLInputElement>("[data-h3-image-files]")?.addEventListener("change", (event) => {
    const input = event.currentTarget as HTMLInputElement;
    try {
      selectedImageFiles = validateImageFiles(Array.from(input.files || []));
      updateStatus(panel);
    } catch (error) {
      selectedImageFiles = [];
      input.value = "";
      updateStatus(panel, error instanceof Error ? error.message : "Некорректные фото-референсы");
    }
  });
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
  const root = modelSelect?.closest<HTMLElement>(".apix-generation-layout") || document.body;
  if (!modelSelect || modelSelect.value !== H3_MODEL) {
    cleanup(root);
    return;
  }

  configureAutomaticSurface(root);
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

function unique(values: string[]): string[] {
  return values.filter(Boolean).filter((item, index, all) => all.indexOf(item) === index);
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

    const uploadedImages: string[] = [];
    for (const file of selectedImageFiles.slice(0, MAX_IMAGES)) uploadedImages.push(await uploadFile(originalFetch, file));
    const uploadedVideos: string[] = [];
    for (const file of selectedVideoFiles.slice(0, MAX_VIDEOS)) uploadedVideos.push(await uploadFile(originalFetch, file));
    const uploadedAudios: string[] = [];
    for (const file of selectedAudioFiles.slice(0, MAX_AUDIOS)) uploadedAudios.push(await uploadFile(originalFetch, file));

    const existingImages = unique([
      String(body.image_url || "").trim(),
      ...(Array.isArray(body.reference_urls) ? body.reference_urls.map(String) : []),
    ]);
    const allImages = unique([...existingImages, ...uploadedImages]).slice(0, MAX_IMAGES);
    body.image_url = allImages[0] || null;
    body.reference_urls = allImages.slice(1);

    const existingVideo = String(body.video_url || "").trim();
    const existingExtraVideos = Array.isArray(body.character_ids) ? body.character_ids.map(String).filter(Boolean) : [];
    const allVideos = unique([existingVideo, ...existingExtraVideos, ...uploadedVideos]).slice(0, MAX_VIDEOS);
    body.video_url = allVideos[0] || null;
    body.character_ids = allVideos.slice(1);

    const existingAudio = Array.isArray(body.audio_ids) ? body.audio_ids.map(String).filter(Boolean) : [];
    const allAudios = unique([...existingAudio, ...uploadedAudios]).slice(0, MAX_AUDIOS);
    body.audio_ids = allAudios;

    const totalFiles = allImages.length + allVideos.length + allAudios.length;
    if (totalFiles > MAX_FILES) throw new Error(`MiniMax H3: максимум ${MAX_FILES} референсных файлов`);
    if (allAudios.length && !allImages.length && !allVideos.length) {
      throw new Error("MiniMax H3: аудио-референс требует фото или видео");
    }

    body.duration = Math.max(4, Math.min(15, Number(body.duration) || 6));
    body.resolution = body.resolution === "768P" ? "768P" : "2K";
    body.mode = "text";
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
