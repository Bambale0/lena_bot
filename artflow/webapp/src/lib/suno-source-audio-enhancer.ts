const NORMAL_MUSIC_PATH = "/api/v1/generate/music";
const UPLOAD_PATH = "/api/v1/music/source-audio";
const SOURCE_GENERATE_PATH = "/api/v1/music/from-audio";
const MAX_BYTES = 100 * 1024 * 1024;
const MAX_SECONDS = 480;

let sourceFile: File | null = null;
let sourceDuration = 0;
let operation = "cover";
let fetchInstalled = false;

function initData(): string {
  return window.Telegram?.WebApp?.initData || "";
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function audioDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const audio = document.createElement("audio");
    const url = URL.createObjectURL(file);
    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      const duration = Number(audio.duration || 0);
      URL.revokeObjectURL(url);
      resolve(duration);
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Не удалось прочитать аудиофайл"));
    };
    audio.src = url;
  });
}

async function validateFile(file: File): Promise<number> {
  if (!/\.(mp3|wav|m4a|aac|flac|ogg|opus)$/i.test(file.name)) {
    throw new Error("Поддерживаются MP3, WAV, M4A, AAC, FLAC, OGG и OPUS");
  }
  if (file.size > MAX_BYTES) throw new Error("Файл больше 100 МБ");
  const duration = await audioDuration(file);
  if (!duration || duration > MAX_SECONDS + 0.05) throw new Error("Аудио должно быть не длиннее 8 минут");
  return duration;
}

function status(panel: HTMLElement, message = "", error = false): void {
  const node = panel.querySelector<HTMLElement>("[data-suno-source-status]");
  if (!node) return;
  node.textContent = message || (sourceFile ? `${sourceFile.name} · ${Math.round(sourceDuration)} сек` : "Файл не выбран — обычная генерация по тексту");
  node.style.color = error ? "var(--destructive, #dc2626)" : "";
}

function findMusicSection(): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>("section")).find((section) => {
    const text = section.textContent || "";
    return text.includes("Создать музыку") || text.includes("Создаём…");
  }) || null;
}

function ensurePanel(): void {
  const section = findMusicSection();
  if (!section || section.querySelector("[data-suno-source-audio]")) return;

  const panel = document.createElement("div");
  panel.dataset.sunoSourceAudio = "1";
  panel.style.display = "grid";
  panel.style.gap = "8px";
  panel.style.padding = "10px";
  panel.style.border = "1px solid var(--border)";
  panel.style.borderRadius = "12px";
  panel.style.background = "color-mix(in srgb, var(--background) 65%, transparent)";
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap">
      <div>
        <div style="font-size:12px;font-weight:700">Свой аудиофайл</div>
        <div style="font-size:10px;opacity:.72">До 8 минут. Можно сделать cover, продолжить трек или добавить вокал/инструментал.</div>
      </div>
      <label style="cursor:pointer;border:1px solid var(--border);border-radius:8px;padding:6px 9px;font-size:11px;font-weight:600">
        Выбрать аудио
        <input data-suno-source-file type="file" accept="audio/*,.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus" hidden />
      </label>
    </div>
    <select data-suno-source-operation style="min-height:36px;border:1px solid var(--border);border-radius:9px;background:var(--background);padding:0 9px">
      <option value="cover">Cover — изменить стиль, сохранив основу</option>
      <option value="extend">Продолжить загруженный трек</option>
      <option value="add_vocals">Добавить вокал (нужны название + стиль)</option>
      <option value="add_instrumental">Добавить инструментал (нужны название + стиль)</option>
    </select>
    <div style="font-size:10px;opacity:.72" data-suno-source-status></div>
    <button type="button" data-suno-source-clear style="display:none;border:0;background:transparent;text-align:left;padding:0;font-size:10px;text-decoration:underline;cursor:pointer">Убрать аудиофайл</button>
  `;

  const submit = Array.from(section.querySelectorAll<HTMLButtonElement>("button")).find((button) =>
    (button.textContent || "").includes("Создать"),
  );
  if (submit) section.insertBefore(panel, submit);
  else section.appendChild(panel);

  panel.querySelector<HTMLInputElement>("[data-suno-source-file]")?.addEventListener("change", async (event) => {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0] || null;
    input.value = "";
    if (!file) return;
    try {
      sourceDuration = await validateFile(file);
      sourceFile = file;
      const clear = panel.querySelector<HTMLElement>("[data-suno-source-clear]");
      if (clear) clear.style.display = "block";
      status(panel);
    } catch (error) {
      sourceFile = null;
      sourceDuration = 0;
      status(panel, error instanceof Error ? error.message : "Некорректный аудиофайл", true);
    }
  });
  panel.querySelector<HTMLSelectElement>("[data-suno-source-operation]")?.addEventListener("change", (event) => {
    const select = event.currentTarget as HTMLSelectElement;
    operation = select.value;
  });
  panel.querySelector<HTMLButtonElement>("[data-suno-source-clear]")?.addEventListener("click", () => {
    sourceFile = null;
    sourceDuration = 0;
    const clear = panel.querySelector<HTMLElement>("[data-suno-source-clear]");
    if (clear) clear.style.display = "none";
    status(panel);
  });
  status(panel);
}

async function uploadSource(originalFetch: typeof window.fetch): Promise<{ url: string; duration_seconds: number }> {
  if (!sourceFile) throw new Error("Аудиофайл не выбран");
  const form = new FormData();
  form.append("file", sourceFile);
  const response = await originalFetch(UPLOAD_PATH, {
    method: "POST",
    body: form,
    headers: { "X-Telegram-Init-Data": initData() },
  });
  const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) throw new Error(String(payload.detail || payload.error || `Upload HTTP ${response.status}`));
  return {
    url: String(payload.url || ""),
    duration_seconds: Number(payload.duration_seconds || sourceDuration || 0),
  };
}

function installFetchBridge(): void {
  if (fetchInstalled) return;
  fetchInstalled = true;
  const originalFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = requestUrl(input);
    const isNormalMusic = url.includes(NORMAL_MUSIC_PATH) && String(init?.method || "GET").toUpperCase() === "POST";
    if (!isNormalMusic || !sourceFile || typeof init?.body !== "string") return originalFetch(input, init);

    let body: Record<string, unknown>;
    try {
      body = JSON.parse(init.body) as Record<string, unknown>;
    } catch {
      return originalFetch(input, init);
    }

    const uploaded = await uploadSource(originalFetch);
    const next = {
      ...body,
      operation,
      upload_url: uploaded.url,
      source_duration: uploaded.duration_seconds,
      continue_at: operation === "extend" ? Math.max(0.1, uploaded.duration_seconds - 0.5) : undefined,
    };
    return originalFetch(SOURCE_GENERATE_PATH, {
      ...init,
      body: JSON.stringify(next),
    });
  };
}

export function installSunoSourceAudioEnhancer(): void {
  installFetchBridge();
  let scheduled = false;
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => {
      scheduled = false;
      ensurePanel();
    });
  };
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  schedule();
}
