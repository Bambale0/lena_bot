function visibleDialog(): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).find((node) => {
    const style = window.getComputedStyle(node);
    return style.display !== "none" && style.visibility !== "hidden";
  }) || null;
}

function firstNavigationTab(): HTMLButtonElement | null {
  return document.querySelector<HTMLButtonElement>('.apix-bottom-nav [role="tab"]');
}

function activeNavigationTab(): HTMLButtonElement | null {
  return document.querySelector<HTMLButtonElement>('.apix-bottom-nav [role="tab"][aria-selected="true"]');
}

function closeTopLayer(): boolean {
  const dialog = visibleDialog();
  if (!dialog) return false;
  const close = dialog.querySelector<HTMLButtonElement>('[aria-label="Закрыть"]');
  if (close) {
    close.click();
    return true;
  }
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  return true;
}

/**
 * Keep Telegram's native BackButton aligned with the Mini App navigation stack.
 *
 * Sheets/dialogs close first. On a nested top-level tab, Back returns to Feed.
 * Feed itself hides the native BackButton so Telegram retains control of app exit.
 */
function installTelegramNavigation(): () => void {
  const app = window.Telegram?.WebApp;
  const backButton = app?.BackButton;
  if (!backButton || typeof document === "undefined") return () => undefined;

  const sync = () => {
    const first = firstNavigationTab();
    const active = activeNavigationTab();
    const nested = Boolean(visibleDialog()) || Boolean(first && active && first !== active);
    if (nested) backButton.show?.();
    else backButton.hide?.();
  };

  const onBack = () => {
    if (closeTopLayer()) {
      window.setTimeout(sync, 0);
      return;
    }
    const first = firstNavigationTab();
    const active = activeNavigationTab();
    if (first && active && first !== active) {
      first.click();
      window.setTimeout(sync, 0);
      return;
    }
    backButton.hide?.();
  };

  backButton.onClick?.(onBack);
  const observer = new MutationObserver(sync);
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-selected", "aria-current", "class", "hidden"],
  });
  window.addEventListener("popstate", sync);
  window.requestAnimationFrame(sync);

  return () => {
    observer.disconnect();
    window.removeEventListener("popstate", sync);
    backButton.offClick?.(onBack);
    backButton.hide?.();
  };
}

export { installTelegramNavigation };
