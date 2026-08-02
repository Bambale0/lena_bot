// APIX production trends entry.
// Uses the existing runtime navigation button instead of rewriting the monolith state.
// This keeps generation/payment/admin/theme flows untouched while making trends the first visible surface.

(() => {
  const SESSION_KEY = "apix:production-trends-entry:v1";
  const SKIP_PARAM = "no_trends_entry";

  function shouldSkip() {
    try {
      const params = new URLSearchParams(window.location.search);
      return params.get(SKIP_PARAM) === "1" || window.sessionStorage.getItem(SESSION_KEY) === "done";
    } catch (_) {
      return false;
    }
  }

  function markDone() {
    try { window.sessionStorage.setItem(SESSION_KEY, "done"); } catch (_) {}
  }

  function isVisible(element) {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function findTrendsButton() {
    const candidates = Array.from(document.querySelectorAll("button, [role='button']"));
    return candidates.find((button) => {
      const text = (button.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      return isVisible(button) && (text.includes("тренды работ") || text === "тренды" || text.includes("тренды"));
    });
  }

  function openTrends() {
    if (shouldSkip()) return true;
    const button = findTrendsButton();
    if (!button) return false;
    markDone();
    button.click();
    return true;
  }

  let attempts = 0;
  const maxAttempts = 80;

  const interval = window.setInterval(() => {
    attempts += 1;
    if (openTrends() || attempts >= maxAttempts) {
      window.clearInterval(interval);
    }
  }, 50);

  const observer = new MutationObserver(() => {
    if (openTrends()) {
      observer.disconnect();
      window.clearInterval(interval);
    }
  });

  try {
    observer.observe(document.documentElement, { childList: true, subtree: true });
    window.setTimeout(() => observer.disconnect(), 4500);
  } catch (_) {}
})();
