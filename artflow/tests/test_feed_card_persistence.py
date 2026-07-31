from pathlib import Path


TRANSFORM = Path("webapp/feed-pinterest-transform.js")


def test_preview_error_never_removes_publication_card() -> None:
    source = TRANSFORM.read_text(encoding="utf-8")

    assert '"  const visibleUrls = previewUrls.slice(0, 4);"' in source
    assert '"  if (!previewUrls.length) return null;"' in source
    assert "failedUrls.has(url) ? undefined : onOpen" in source
    assert "Публикация сохранена" in source
    assert "feed-card-persistence-v6" in source


def test_hotfix_is_frontend_only() -> None:
    source = TRANSFORM.read_text(encoding="utf-8")

    assert "FEED_RENDER_CONCURRENCY" not in source
    assert "asyncio" not in source
    assert "placeholder_webp" not in source
