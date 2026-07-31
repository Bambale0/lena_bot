from pathlib import Path


WEBAPP = Path("webapp")


def test_feed_uses_masonry_with_separate_sort_and_content_filters():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")
    styles = (WEBAPP / "src" / "feed-pinterest.css").read_text(encoding="utf-8")

    for label in ("Для тебя", "Новые", "Популярные", "Повторы"):
        assert label in block
    for label in ("Все", "Фото", "Видео"):
        assert label in block

    assert "feedSortRail" in block
    assert "feedTypeTabs" in block
    assert "feedMineToggle" in block
    assert "column-count: 2" in styles
    assert "break-inside: avoid" in styles
    assert "position: sticky" in styles


def test_feed_actions_fit_one_row_and_remain_explicit():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")
    styles = (WEBAPP / "src" / "feed-pinterest.css").read_text(encoding="utf-8")

    assert "Создать" in block
    assert "Лайк" in block
    assert "Ссылка" in block
    assert "feedCardActionRow" in block
    assert "grid-template-columns: minmax(0, 1fr) 44px 44px" in styles
    assert "onClick={handleCopyLink}" in block
    assert "Удалить из ленты" in block


def test_video_cards_use_quiet_preview_instead_of_native_controls():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")

    assert "function FeedMediaThumb" in block
    assert 'className="feedMediaCell feedVideoCell"' in block
    assert "muted" in block
    assert "playsInline" in block
    assert "feedVideoPlay" in block
    assert "controls" not in block


def test_broken_or_missing_media_does_not_render_placeholder_cards():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")

    assert "if (!previewUrls.length" in block
    assert "hideBrokenMedia" in block
    assert "onError={() => hideBrokenMedia(url)}" in block


def test_vite_installs_feed_transform_and_bumps_build_id():
    config = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")
    transform = (WEBAPP / "feed-pinterest-transform.js").read_text(encoding="utf-8")

    assert "feedPinterestMiniApp" in config
    assert "feedFirstMiniApp(), feedPinterestMiniApp(), react()" in config
    assert 'import "./feed-pinterest.css"' in transform
    assert "feed-ux-architecture-v3" in transform
