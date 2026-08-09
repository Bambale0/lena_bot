function visibleDialog(): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).find((node) => (
    !node.hidden && !node.closest("[hidden]") && node.getAttribute("aria-hidden") !== "true"
  )) || null;
}

function navigationRoot(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".apix-bottom-nav");
}

function firstNavigationTab(): HTMLButtonElement | null {
  return navigationRoot()?.querySelector<HTMLButtonElement>('[role="tab"]') || null;
}

function activeNavigationTab(): HTMLButtonElement | null {
  return navigationRoot()?.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"]') || null;
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

function mutationTouchesDialog(mutation: MutationRecord): boolean {
  const nodes = [...Array.from(mutation.addedNodes), ...Array.from(mutation.removedNodes)];
  return nodes.some((node) => {
    if (!(node instanceof Element)) return false;
    return node.matches('[role="dialog"]') || Boolean(node.querySelector('[role="dialog"]'));
  });
}

/**
 * Keep Telegram's native BackButton aligned with the Mini App navigation stack.
 *
 * The observer is deliberately narrow: navigation attributes only, plus DOM
 * additions/removals that actually contain a dialog. It must not subscribe to
 * global class/text mutations because that runs work on every React update.
 */
function installTelegramNavigation(): () => void {
  const app = window.Telegram?.WebApp;
  const backButton = app?.BackButton;
  if (!backButton || typeof document === "undefined") return () => undefined;

  let frame = 0;
  let observedNav: HTMLElement | null = null;
  const navObserver = new MutationObserver(() => scheduleSync());

  const sync = () => {
    const first = firstNavigationTab();
    const active = activeNavigationTab();
    const nested = Boolean(visibleDialog()) || Boolean(first && active && first !== active);
    if (nested) backButton.show?.();
    else backButton.hide?.();
  };

  const scheduleSync = () => {
    window.cancelAnimationFrame(frame);
    frame = window.requestAnimationFrame(sync);
  };

  const ensureNavigationObserver = () => {
    const nav = navigationRoot();
    if (!nav || nav === observedNav) return;
    navObserver.disconnect();
    observedNav = nav;
    navObserver.observe(nav, {
      subtree: true,
      attributes: true,
      attributeFilter: ["aria-selected", "aria-current"],
    });
    scheduleSync();
  };

  const onBack = () => {
    if (closeTopLayer()) {
      scheduleSync();
      return;
    }
    const first = firstNavigationTab();
    const active = activeNavigationTab();
    if (first && active && first !== active) {
      first.click();
      scheduleSync();
      return;
    }
    backButton.hide?.();
  };

  backButton.onClick?.(onBack);

  const structureObserver = new MutationObserver((mutations) => {
    ensureNavigationObserver();
    if (mutations.some(mutationTouchesDialog)) scheduleSync();
  });
  structureObserver.observe(document.body, { childList: true, subtree: true });

  window.addEventListener("popstate", scheduleSync);
  ensureNavigationObserver();
  scheduleSync();

  return () => {
    window.cancelAnimationFrame(frame);
    navObserver.disconnect();
    structureObserver.disconnect();
    window.removeEventListener("popstate", scheduleSync);
    backButton.offClick?.(onBack);
    backButton.hide?.();
  };
}

export { installTelegramNavigation };
