const H3_REFERENCE_MODEL = "minimax-h3/reference-to-video";

function replaceLeadingText(label: HTMLElement, text: string): void {
  for (const node of Array.from(label.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
      node.textContent = `\n${text}\n`;
      return;
    }
  }
  label.prepend(document.createTextNode(`${text}\n`));
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
      replaceLeadingText(label, "Аудио-референс · до 1");
      if (textarea) textarea.placeholder = "HTTPS-ссылка на аудиофайл";
    } else if (text.includes("Character IDs")) {
      replaceLeadingText(label, "Доп. видео-референсы · до 2");
      if (textarea) textarea.placeholder = "HTTPS-ссылки на видео, по одной в строке";
    }
  }

  for (const button of Array.from(root.querySelectorAll<HTMLButtonElement>("button"))) {
    if (button.textContent?.trim() === "Фото") button.textContent = "Референсы";
  }
}

export function installMiniMaxH3MiniappEnhancer(): void {
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
