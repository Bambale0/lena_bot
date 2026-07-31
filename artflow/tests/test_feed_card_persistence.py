from pathlib import Path


APP = Path("webapp/src/v2/VelvetApp.jsx")


def test_preview_error_never_removes_publication_card() -> None:
    source = APP.read_text(encoding="utf-8")

    assert "function FeedMedia" in source
    assert "setFailed(true)" in source
    assert "if (!url || failed) return <MediaFallback compact/>;" in source
    assert "function MediaFallback" in source
    assert "Превью временно недоступно" in source


def test_preview_failure_is_frontend_only() -> None:
    source = APP.read_text(encoding="utf-8")

    assert "FEED_RENDER_CONCURRENCY" not in source
    assert "asyncio" not in source
    assert "placeholder_webp" not in source
    assert "onError={() => setFailed(true)}" in source
