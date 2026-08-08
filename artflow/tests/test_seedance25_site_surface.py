from pathlib import Path


def test_seedance25_website_uses_one_multimodal_reference_surface() -> None:
    studio = Path("landing/studio.html").read_text(encoding="utf-8")
    enhancer = Path("landing/js/seedance25-studio.js").read_text(encoding="utf-8")

    assert "seedance25-studio.js" in studio
    assert 'data-s25-image-files' in enhancer
    assert 'data-s25-video-files' in enhancer
    assert 'data-s25-audio-files' in enhancer
    assert 'data-s25-image-urls' in enhancer
    assert 'data-s25-video-urls' in enhancer
    assert 'data-s25-audio-urls' in enhancer
    assert 'token("scenario"' not in enhancer
    assert 'body.mode = "text"' in enhancer
    assert 'body.grok_mode = null' in enhancer
    assert 'refs.style.display = selected() ? "none" : ""' in enhancer
    assert 'seedMode.style.display = selected() ? "none" : ""' in enhancer
