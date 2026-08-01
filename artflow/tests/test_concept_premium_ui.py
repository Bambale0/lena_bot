from pathlib import Path


SRC = Path("webapp/src")
CONCEPT = SRC / "concept"


def test_premium_concept_layer_is_enabled() -> None:
    main = (SRC / "main.jsx").read_text(encoding="utf-8")
    premium = (CONCEPT / "concept-premium.css").read_text(encoding="utf-8")

    assert 'import "./concept/concept-premium.css"' in main
    assert "20260801-velvet-concept-studio-v2" in main
    assert "width: min(100%, 430px)" in premium
    assert ".cxMasonry" in premium
    assert ".cxOrbButton__core" in premium
    assert "backdrop-filter: blur(28px)" in premium


def test_embedded_telegram_header_does_not_duplicate_brand() -> None:
    source = (CONCEPT / "components.jsx").read_text(encoding="utf-8")

    assert "const embedded = Boolean(telegram()?.initData)" in source
    assert '!embedded && <span className="cxWordmark"' in source
    assert "cxBrandBar--embedded" in source


def test_media_fallbacks_are_varied_and_visual() -> None:
    source = (CONCEPT / "fallbackArtV2.js").read_text(encoding="utf-8")
    components = (CONCEPT / "components.jsx").read_text(encoding="utf-8")

    assert "const SCENES = [" in source
    assert "fallbackArtFor(seed" in source
    assert "radialGradient" in source
    assert "fallbackArtFor(item?.id || index)" in components
