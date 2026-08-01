from pathlib import Path


COMPONENTS = Path("webapp/src/concept/components.jsx")
FEED = Path("webapp/src/concept/FeedScreen.jsx")


def test_preview_error_advances_fallback_instead_of_removing_card() -> None:
    components = COMPONENTS.read_text(encoding="utf-8")
    feed = FEED.read_text(encoding="utf-8")

    assert "function ProgressiveMedia" in components
    assert "setSourceIndex((value) => value + 1)" in components
    assert "if (!source) return <MediaPlaceholder" in components
    assert "MediaPlaceholder" in components
    assert "return null" not in feed


def test_publication_identity_and_actions_remain_visible() -> None:
    source = FEED.read_text(encoding="utf-8")

    assert "@{item.author" in source
    assert 'aria-label="Нравится"' in source
    assert 'aria-label="Повторить"' in source
    assert 'aria-label="Поделиться"' in source
    assert "onRemoved" in source
