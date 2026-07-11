(() => {
  const LEGACY_SAMPLE_PROMPTS = new Set([
    "Элегантный визуал для публикации: главный объект, настроение, свет, фон и желаемая подача",
    "Элегантный портрет для обложки: мягкий лилово-розовый свет, чистый фон, уверенный взгляд, премиальная подача",
  ]);

  const valueDescriptor = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    "value",
  );

  function normalize(value) {
    return String(value || "").trim();
  }

  function protectPromptField() {
    const field = document.querySelector('.account-composer textarea[name="prompt"]');
    if (!field || field.dataset.samplePromptGuard === "ready" || !valueDescriptor) return;

    field.dataset.samplePromptGuard = "ready";

    Object.defineProperty(field, "value", {
      configurable: true,
      enumerable: valueDescriptor.enumerable,
      get() {
        return valueDescriptor.get.call(this);
      },
      set(nextValue) {
        const safeValue = LEGACY_SAMPLE_PROMPTS.has(normalize(nextValue)) ? "" : nextValue;
        valueDescriptor.set.call(this, safeValue);
      },
    });

    if (LEGACY_SAMPLE_PROMPTS.has(normalize(valueDescriptor.get.call(field)))) {
      valueDescriptor.set.call(field, "");
      field.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", protectPromptField, { once: true });
  } else {
    protectPromptField();
  }
})();
