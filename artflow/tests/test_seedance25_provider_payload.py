from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENHANCER = ROOT / "webapp" / "src" / "lib" / "seedance25-miniapp-enhancer.ts"
MINIAPP_ROUTES = ROOT / "api" / "miniapp_routes.py"


def test_seedance25_miniapp_does_not_send_null_for_string_grok_mode() -> None:
    frontend = ENHANCER.read_text(encoding="utf-8")
    backend = MINIAPP_ROUTES.read_text(encoding="utf-8")

    # FastAPI validates VideoGenRequest before the Seedance-specific normalizer.
    # Sending JSON null for this non-nullable string causes HTTP 422 immediately.
    assert 'grok_mode: str = "normal"' in backend
    assert 'body.grok_mode = null' not in frontend
    assert 'body.grok_mode = "normal"' in frontend


def test_seedance25_patch_still_routes_from_real_media() -> None:
    frontend = ENHANCER.read_text(encoding="utf-8")

    assert 'body.mode = "text"' in frontend
    assert 'body.image_url = images[0] || null' in frontend
    assert 'body.reference_urls = images.slice(1)' in frontend
    assert 'body.audio_ids = [...audioRefs, ...tokens]' in frontend
