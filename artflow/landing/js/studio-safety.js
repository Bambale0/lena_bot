(() => {
  const LEGACY_SAMPLE_PROMPTS = new Set([
    "Элегантный визуал для публикации: главный объект, настроение, свет, фон и желаемая подача",
    "Элегантный портрет для обложки: мягкий лилово-розовый свет, чистый фон, уверенный взгляд, премиальная подача",
  ]);

  let attempts = 0;
  let stopped = false;

  function promptField() {
    return document.querySelector('.account-composer textarea[name="prompt"]');
  }

  function clearLegacySample() {
    if (stopped) return;
    const field = promptField();
    if (!field) return;

    const value = String(field.value || "").trim();
    if (LEGACY_SAMPLE_PROMPTS.has(value)) {
      field.value = "";
      field.dispatchEvent(new Event("input", { bubbles: true }));
      stopped = true;
      return;
    }

    if (value) stopped = true;
  }

  function scheduleChecks() {
    clearLegacySample();
    const timer = window.setInterval(() => {
      attempts += 1;
      clearLegacySample();
      if (stopped || attempts >= 50) window.clearInterval(timer);
    }, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleChecks, { once: true });
  } else {
    scheduleChecks();
  }
})();
