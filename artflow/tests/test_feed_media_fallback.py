from pathlib import Path


VIEWER = Path("api/feed_media_viewer.py")


def test_webp_preview_redirects_to_source_on_conversion_failure() -> None:
    source = VIEWER.read_text(encoding="utf-8")

    assert "from fastapi.responses import RedirectResponse" in source
    assert "def _source_redirect" in source
    assert 'status_code=307' in source
    assert 'FEED_FALLBACK_CACHE_CONTROL = "no-store"' in source
    assert '"Feed WebP fallback to source generation=%s index=%s"' in source


def test_normal_webp_delivery_remains_immutable() -> None:
    source = VIEWER.read_text(encoding="utf-8")

    assert 'media_type="image/webp"' in source
    assert 'FEED_CACHE_CONTROL = "public, max-age=31536000, immutable"' in source
    assert 'payload["result_url"] = ""' in source
    assert 'payload["result_urls"] = []' in source
