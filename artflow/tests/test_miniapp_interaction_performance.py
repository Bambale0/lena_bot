from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp" / "src"


def read(relative: str) -> str:
    return (WEBAPP / relative).read_text(encoding="utf-8")


def test_advanced_enhancers_are_not_eagerly_installed() -> None:
    main = read("main.tsx")
    loader = read("lib/model-enhancer-loader.ts")

    assert "installModelEnhancerLoader" in main
    assert "installSeedance25MiniappEnhancer" not in main
    assert "installMiniMaxH3MiniappEnhancer" not in main
    assert "installSunoSourceAudioEnhancer" not in main
    assert 'import("@/lib/minimax-h3-miniapp-enhancer")' in loader
    assert 'import("@/lib/seedance25-miniapp-enhancer")' in loader
    assert 'import("@/lib/suno-source-audio-enhancer")' in loader


def test_viewport_scroll_does_not_rerender_shell() -> None:
    shell = read("components/app-shell.tsx")

    assert 'visualViewport?.addEventListener("scroll"' not in shell
    assert "sameViewport(current, next) ? current : next" in shell
    assert "startTransition(() => onTabChange(tab))" in shell


def test_telegram_navigation_does_not_watch_global_class_mutations() -> None:
    navigation = read("lib/telegram-navigation.ts")

    assert 'attributeFilter: ["aria-selected", "aria-current"]' in navigation
    assert 'attributeFilter: ["aria-selected", "aria-current", "class", "hidden"]' not in navigation
    assert "getComputedStyle" not in navigation


def test_mobile_performance_css_disables_expensive_backdrop_blur() -> None:
    main = read("main.tsx")
    css = read("styles/performance.css")

    assert 'import "@/styles/performance.css"' in main
    assert "backdrop-filter: none !important" in css
    assert "touch-action: manipulation" in css
