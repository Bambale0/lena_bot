from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "webapp" / "public" / "apix-product-prototype.html"


def test_product_prototype_is_code_not_poster_image() -> None:
    html = PROTOTYPE.read_text(encoding="utf-8")

    assert "<script>" in html
    assert "data-go=\"create\"" in html
    assert "data-detail" in html
    assert "data-sheet=\"balance\"" in html
    assert "class=\"screen active\"" in html
    assert "class=\"overlay\"" in html

    # The prototype must not be a static poster made from exported mockup images.
    assert "<img" not in html
    assert "position:fixed" in html
    assert "grid-template-columns:1fr 1fr" in html


def test_product_prototype_keeps_top_chrome_compact() -> None:
    css = PROTOTYPE.read_text(encoding="utf-8")

    assert ".status{height:24px" in css
    assert ".hero h1" in css
    assert "font-size:44px" in css
    assert "min-height:100dvh" in css

    forbidden = [
        "height:120px",
        "height:140px",
        "padding-top:80px",
        "status-bar-poster",
    ]
    for token in forbidden:
        assert token not in css
