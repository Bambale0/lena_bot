from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from api.web.schemas import FeedCard, GenerationCard
from db.models import GenerationStatus, GenerationType


def _generation(**overrides):
    data = {
        "id": 42,
        "model": "nano-banana-2",
        "gen_type": GenerationType.image,
        "prompt": "studio portrait",
        "status": GenerationStatus.done,
        "result_url": "https://example.test/static/upload/missing.jpg",
        "result_urls": '["https://example.test/static/upload/missing.jpg","https://cdn.test/fallback.png"]',
        "credits_spent": 5,
        "is_public_feed": True,
        "is_prompt_library": False,
        "created_at": datetime.now(timezone.utc),
        "likes_count": 1,
        "shares_count": 2,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_generation_card_uses_first_available_result_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("api.public_files.UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr("api.public_files.settings.STATIC_UPLOAD_URL_PATH", "/static/upload")

    payload = GenerationCard.from_generation(_generation())

    assert payload.result_url == "https://cdn.test/fallback.png"
    assert payload.result_urls == ["https://cdn.test/fallback.png"]


def test_feed_card_hides_missing_local_result_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("api.public_files.UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr("api.public_files.settings.STATIC_UPLOAD_URL_PATH", "/static/upload")
    card = SimpleNamespace(
        generation=_generation(result_urls=None),
        username="artist",
        full_name=None,
        remix_count=0,
        aspect_ratio=None,
        quality=None,
    )

    payload = FeedCard.from_feed_card(card)

    assert payload.result_url == ""
