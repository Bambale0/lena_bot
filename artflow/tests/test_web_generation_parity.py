from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_studio_loads_generation_parity_layer():
    html = (ROOT / "landing/studio.html").read_text()
    assert "js/prototype-premium.js" in html
    assert "js/generation-parity.js" in html


def test_web_parity_layer_exposes_advanced_video_contract():
    src = (ROOT / "landing/js/generation-parity.js").read_text()
    for token in (
        "video_start",
        "video_end",
        "audio_ids",
        "character_ids",
        "seed",
        "grok_mode",
        "MAX_GEMINI_MEDIA_SLOTS",
        'body.mode = "motion"',
    ):
        assert token in src


def test_web_parity_layer_exposes_music_voice_contract():
    src = (ROOT / "landing/js/generation-parity.js").read_text()
    for token in (
        "voice_record_id",
        'request("/music/voices")',
        'request("/music/voices", { method: "POST", body: payload })',
        "title",
        "style",
    ):
        assert token in src


def test_existing_web_runtime_already_supports_multi_reference_and_exact_pricing():
    src = (ROOT / "landing/js/prototype-premium.js").read_text()
    for token in (
        "reference_urls",
        "maxRefs",
        "qualityPrices",
        "priceTable",
        "videoInputPrices",
        "creditsPerSec",
    ):
        assert token in src
