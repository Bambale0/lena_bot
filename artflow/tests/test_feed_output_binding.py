"""Persisted feed scenes remain exact when available gallery results compact."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import feed_media_viewer, miniapp_routes
from bot.utils import feed_media

A = "https://example.test/first.jpg"
B = "https://example.test/second.jpg"
C = "https://example.test/third.jpg"


@pytest.fixture
def gallery(monkeypatch):
    source = SimpleNamespace(
        id=201, user_id=99, model="nano-banana-2", gen_type="image", prompt="hidden recipe",
        result_url=A, result_urls=f'["{A}", "{B}", "{C}"]', likes_count=0, shares_count=0,
    )
    monkeypatch.setattr(feed_media.settings, "WEB_PUBLIC_URL", "https://apixbotai.com")
    card = SimpleNamespace(generation=source, aspect_ratio="1:1", remix_count=0, username="artist")
    payload = miniapp_routes._feed_card_out(card, SimpleNamespace(id=42))
    urls = ["https://apixbotai.com" + url for url in payload["preview_urls"]]
    return source, payload, urls


def test_feed_card_binding_survives_compaction_without_exposing_recipe(gallery):
    source, payload, urls = gallery
    assert "output_id=" in urls[1]
    assert payload["result_urls"] == []
    assert "hidden recipe" not in str(payload)
    assert A not in str(payload) and B not in str(payload)
    assert feed_media.canonical_feed_source_reference(source, urls[1], [B, C]) == B
    assert feed_media.canonical_feed_source_reference(source, urls[1], [B]) == B
    assert feed_media.validated_feed_source_reference(source, urls[1], [B]) == B


def test_missing_expired_or_cross_post_scene_binding_fails_closed(gallery):
    source, _, urls = gallery
    for selected in [
        urls[0], urls[1].replace("/201/", "/202/"),
        urls[1].replace("https://apixbotai.com", "https://evil.test"),
        "https://apixbotai.com/api/v1/feed/201/preview.webp?index=1",
        urls[1] + "&next=evil", urls[1] + "&output_id=other", urls[1] + "#fragment",
        urls[1].replace("index=1", "index=4"),
        urls[1].replace("output_id=", "output_id=invalid"), A,
    ]:
        with pytest.raises(ValueError):
            feed_media.validated_feed_source_reference(source, selected, [B])
    assert feed_media.validated_feed_source_reference(source, B, [B]) == B


def test_bound_alias_is_never_a_persons_identity_even_after_expiry(gallery, monkeypatch):
    source, _, urls = gallery
    monkeypatch.setattr(feed_media, "public_url_is_available", lambda url: url != B)
    user_photo = "https://example.test/person.jpg"
    assert feed_media.feed_identity_references(source, [user_photo, urls[1]]) == [user_photo]
    assert feed_media.selected_feed_source_url(source, [user_photo, urls[1]]) is None


@pytest.mark.asyncio
async def test_bound_preview_renders_same_scene_after_earlier_output_expires(gallery, monkeypatch):
    source, _, urls = gallery
    binding = urls[1].split("output_id=")[1]
    routes = SimpleNamespace(
        _generation_result_urls=lambda _: [B], _generation_primary_result_url=lambda _: B,
        HTTPException=HTTPException,
    )
    mirror = AsyncMock(return_value=None)
    monkeypatch.setattr(feed_media_viewer, "mirror_url", mirror)
    monkeypatch.setattr(feed_media_viewer, "preview_public_image_url", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed_media_viewer, "local_upload_path_from_url", lambda _: None)
    response = await feed_media_viewer._render_webp(routes, source, index=1, output_id=binding, max_size=480, quality=72)
    assert response.headers["location"] == B
    mirror.assert_awaited_once_with(B, subdir="feed")
    with pytest.raises(HTTPException) as error:
        await feed_media_viewer._render_webp(routes, source, index=0, output_id=urls[0].split("output_id=")[1], max_size=480, quality=72)
    assert error.value.status_code == 404


@pytest.mark.parametrize("slot", ["image_url", "reference_urls"])
@pytest.mark.parametrize("suffix", ["&next=evil", "&output_id=other", "#fragment", "&output_id="])
def test_malformed_trusted_scene_alias_never_becomes_user_identity(gallery, slot, suffix):
    source, _, urls = gallery
    malformed = urls[1] + suffix
    assert feed_media.feed_identity_references(source, [malformed]) == []
    body = miniapp_routes.FeedRemixRequest(
        model="nano-banana-2", **{slot: [malformed] if slot == "reference_urls" else malformed},
    )
    with pytest.raises(HTTPException) as error:
        miniapp_routes._prepare_feed_remix_inputs(source, body, user_id=42)
    assert error.value.status_code == 422
