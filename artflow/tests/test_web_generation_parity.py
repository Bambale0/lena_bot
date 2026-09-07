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


def test_public_site_billing_keeps_tribute_usd_provider_parity():
    src = (ROOT / "landing/js/prototype-premium.js").read_text()
    assert 'tribute: "USD"' in src
    assert '["tbank", "stars", "crypto", "tribute", "lava"].includes(provider)' in src


def test_public_site_busts_cached_payment_runtime_after_tribute_fix():
    expected = "prototype-premium.js?v=20260907_dual_prices"
    pages = sorted((ROOT / "landing").glob("*.html"))
    referenced = [path for path in pages if "prototype-premium.js?v=" in path.read_text()]
    assert referenced
    for path in referenced:
        assert expected in path.read_text(), path.name


def test_payment_plan_cards_show_rub_and_tribute_usd_together_across_web_surfaces():
    landing = (ROOT / "landing/js/prototype-premium.js").read_text()
    legacy_miniapp = (ROOT / "webapp/src/main.jsx").read_text()
    current_miniapp = (ROOT / "webapp/src/components/balance-sheet.tsx").read_text()

    assert 'return [rub, usd].filter(Boolean).join(" | ")' in landing
    assert 'return [rub, usd].filter(Boolean).join(" | ")' in legacy_miniapp
    assert 'return [rub, usd].filter(Boolean).join(" | ")' in current_miniapp
    assert 'formatPlanListPrice(p)' in legacy_miniapp
    assert 'planListPrice(plan)' in current_miniapp
