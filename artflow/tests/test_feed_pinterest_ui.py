from pathlib import Path


WEBAPP = Path("webapp")


def test_feed_uses_pinterest_masonry_and_publication_filters():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")
    styles = (WEBAPP / "src" / "feed-pinterest.css").read_text(encoding="utf-8")

    for label in ("Для тебя", "Новые", "Популярные", "Повторяемые", "Мои"):
        assert label in block

    assert 'column-count: 2' in styles
    assert 'height: auto' in styles
    assert 'break-inside: avoid' in styles
    assert 'Фильтр публикаций' in block


def test_feed_actions_have_visible_labels_and_share_every_post():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")

    assert "Повторить" in block
    assert "Нравится" in block
    assert "Поделиться" in block
    assert 'onClick={handleCopyLink}' in block
    assert 'item.is_mine && (' in block
    assert "Удалить публикацию" in block


def test_broken_or_missing_media_does_not_render_black_placeholder_cards():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")

    assert "if (!previewUrls.length" in block
    assert "hideBrokenMedia" in block
    assert "onError={() => hideBrokenMedia(url)}" in block


def test_vite_installs_feed_transform_after_feed_first_transform():
    config = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")
    transform = (WEBAPP / "feed-pinterest-transform.js").read_text(encoding="utf-8")

    assert "feedPinterestMiniApp" in config
    assert "feedFirstMiniApp(), feedPinterestMiniApp(), react()" in config
    assert 'import "./feed-pinterest.css"' in transform
    assert "feed-pinterest-filters-v2" in transform
