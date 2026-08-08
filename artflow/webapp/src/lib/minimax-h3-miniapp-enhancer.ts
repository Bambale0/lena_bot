const H3_REFERENCE_MODEL = "minimax-h3/reference-to-video";
const GENERATE_VIDEO_PATH = "/api/v1/generate/video";
const UPLOAD_PATH = "/api/web/upload-media";

let selectedVideoFiles: File[] = [];
let selectedAudioFile: File | null = null;
let fetchInstalled = false;

function replaceLeadingText(label: HTMLElement, text: string): void {
  for (const node of Array.from(label.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
      node.textContent = `\n${text}\n`;
      return;
    }
  }
  label.prepend(document.createTextNode(`${text}\n`));
}

function selectedModel(): string {
  const selects = Array.from(document.querySelectorAll<HTMLSelectElement>("select"));
  const modelSelect = selects.find((select) =>
    Array.from(select.options).some((option) => option.value === H3_REFERENCE_MODEL),
  );
  return modelSelect?.value || "";
}

function uploadPanel(root: HTMLElement): void {
  if (root.querySelector("[data-h3-reference-files]")) return;

  const panel = document.createElement("div");
  panel.dataset.h3ReferenceFiles = "1";
  panel.style.display = "grid";
  panel.style.gap = "10px";
  panel.style.marginTop = "10px";
  panel.innerHTML = `
    <div style="font-weight:700">MiniMax H3 · мультимодальные референсы</div>
    <div style="font-size:13px;opacity:.75">Фото добавляются выше. Здесь можно добавить до 3 коротких видео и 1 аудио/voice-файл.</div>
    <label style="display:grid;gap:6px">
      <span>Видео-референсы · до 3</span>
      <input data-h3-video-files type="file" accept="video/*" multiple />
    </label>
    <label style="display:grid;gap:6px">
      <span>Аудио-референс · до 1</span>
      <input data-h3-audio-file type="file" accept="audio/*" />
    </label>
    <small data-h3-upload-status></small>
  `;

  const anchor = root.querySelector<HTMLElement>("textarea")?.closest("label")?.parentElement;
  (anchor || root).appendChild(panel);

  panel.querySelector<HTMLInputElement>("[data-h3-video-files]")?.addEventListener("change", (event) => {
    const input = event.currentTarget as HTMLInputElement;
    selectedVideoFiles = Array.from(input.files || []).slice(0, 3);
    const status = panel.querySelector<HTMLElement>("[data-h3-upload-status]");
    if (status) status.textContent = `Видео: ${selectedVideoFiles.length}/3 · аудио: ${selectedAudioFile ? 1 : 0}/1`;
  });
  panel.querySelector<HTMLInputElement>("[data-h3-audio-file]")?.addEventListener("change", (event) => {
    const input = event.currentTarget as HTMLInputElement;
    selectedAudioFile = input.files?.[0] || null;
    const status = panel.querySelector<HTMLElement>("[data-h3-upload-status]");
    if (status) status.textContent = `Видео: ${selectedVideoFiles.length}/3 · аудио: ${selectedAudioFile ? 1 : 0}/1`;
  });
}

function enhance(): void {
  const selects = Array.from(document.querySelectorAll<HTMLSelectElement>("select"));
  const modelSelect = selects.find((select) =>
    Array.from(select.options).some((option) => option.value === H3_REFERENCE_MODEL),
  );
  if (!modelSelect || modelSelect.value !== H3_REFERENCE_MODEL) return;

  const root = modelSelect.closest<HTMLElement>(".apix-generation-layout") || document.body;
  const labels = Array.from(root.querySelectorAll<HTMLElement>("label"));

  for (const label of labels) {
    const text = label.textContent || "";
    const textarea = label.querySelector<HTMLTextAreaElement>("textarea");
    if (text.includes("Audio IDs")) {
      replaceLeadingText(label, "Аудио-референс по URL · до 1");
      if (textarea) textarea.placeholder = "HTTPS-ссылка на аудиофайл";
    } else if (text.includes("Character IDs")) {
      replaceLeadingText(label, "Доп. видео-референсы по URL · до 2");
      if (textarea) textarea.placeholder = "HTTPS-ссылки на видео, по одной в строке";
    }
  }

  for (const button of Array.from(root.querySelectorAll<HTMLButtonElement>("button"))) {
    if (button.textContent?.trim() === "Фото") button.textContent = "Референсы";
  }
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
  if (!response.ok) throw new Error(`Не удалось загрузить референс (${response.status})`);
  const payload = await response.json() as Record<string, unknown>;
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
    if (String(body.model || "") !== H3_REFERENCE_MODEL) return originalFetch(input, init);

    const uploadedVideos: string[] = [];
    for (const file of selectedVideoFiles.slice(0, 3)) {
      uploadedVideos.push(await uploadFile(originalFetch, file));
    }
    const uploadedAudio = selectedAudioFile ? await uploadFile(originalFetch, selectedAudioFile) : "";

    const existingVideo = String(body.video_url || "").trim();
    const existingExtraVideos = Array.isArray(body.character_ids)
      ? body.character_ids.map(String).filter(Boolean)
      : [];
    const allVideos = [existingVideo, ...existingExtraVideos, ...uploadedVideos].filter(Boolean).slice(0, 3);
    body.video_url = allVideos[0] || null;
    body.character_ids = allVideos.slice(1);

    const existingAudio = Array.isArray(body.audio_ids) ? body.audio_ids.map(String).filter(Boolean) : [];
    body.audio_ids = [existingAudio[0], uploadedAudio].filter(Boolean).slice(0, 1);

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
      if (selectedModel() !== H3_REFERENCE_MODEL) return;
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
