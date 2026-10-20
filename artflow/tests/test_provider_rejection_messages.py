from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api import miniapp_routes, realtime
from api.image_errors import image_generation_user_error
from api.web.schemas import GenerationCard
from core.feed_remix_prompt import generation_public_error
from db.models import GenerationStatus, GenerationType


@pytest.mark.parametrize("protected", [False, True])
@pytest.mark.parametrize("raw, expected", [
    ("The request failed because the output image may be related to copyright restrictions.", "авторских прав"),
    ("provider_rejected_request", "отклонил запрос"),
    ("Image fetch failed. Check access settings or use our File Upload API instead.", "Загрузи фото заново"),
])
def test_known_rejections_have_actionable_safe_public_reasons(raw, expected, protected):
    generation = SimpleNamespace(
        error_msg=raw + " private-prompt-must-never-leak", task_id="neironych:test",
        source_feed_gen_id=7 if protected else None, input_params="{}",
    )
    message = generation_public_error(generation)
    assert expected in message
    assert "private-prompt-must-never-leak" not in message
    if "provider_rejected_request" not in raw:
        assert expected in image_generation_user_error(raw)


@pytest.mark.parametrize("raw", [
    "The request failed because the output image may be related to copyright restrictions.",
    "provider_rejected_request",
    "Image fetch failed. Check access settings or use our File Upload API instead.",
])
def test_site_miniapp_and_realtime_share_rejection_reason_without_hidden_prompt(raw):
    generation = SimpleNamespace(
        id=42, user_id=7, model="seedream/5-pro-text-to-image", gen_type=GenerationType.image,
        status=GenerationStatus.failed, prompt="private-recipe", source_feed_gen_id=3,
        error_msg=raw, task_id="provider-task", input_params="{}", result_url=None,
        result_urls=None, created_at=datetime.now(timezone.utc), finished_at=None,
        credits_spent=2, is_public_feed=False, is_prompt_library=False,
    )
    site = GenerationCard.from_generation(generation)
    miniapp = miniapp_routes._gen_out(generation)
    event = realtime.generation_event_payload(generation)
    assert site.error == miniapp.error == event["error"] == generation_public_error(generation)
    assert site.prompt == miniapp.prompt == event["prompt"] == ""
