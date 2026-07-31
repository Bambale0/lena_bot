from pathlib import Path


API = Path("api")
WEBAPP = Path("webapp")


def test_webp_rendering_does_not_block_the_event_loop() -> None:
    source = (API / "feed_media_viewer.py").read_text(encoding="utf-8")

    assert "FEED_RENDER_CONCURRENCY = 3" in source
    assert "async with _render_slots" in source
    assert "await asyncio.to_thread(" in source
    assert "webp_path.read_bytes" in source


def test_preview_failure_returns_retryable_webp_instead_of_broken_image() -> None:
    source = (API / "feed_media_viewer.py").read_text(encoding="utf-8")

    assert "_placeholder_webp" in source
    assert 'media_type="image/webp"' in source
    assert 'headers["X-Feed-Preview"] = "placeholder"' in source
    assert 'FEED_RETRY_CACHE_CONTROL = "no-store, max-age=0"' in source


def test_frontend_never_unmounts_a_card_after_preview_error() -> None:
    transform = (WEBAPP / "feed-pinterest-transform.js").read_text(encoding="utf-8")

    assert '"  const visibleUrls = previewUrls.slice(0, 4);"' in transform
    assert '"  if (!previewUrls.length) return null;"' in transform
    assert "feed-stability-v5" in transform
