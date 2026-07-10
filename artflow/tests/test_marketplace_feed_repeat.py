
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import marketplace
from db.models import ImageGenerationAction


@pytest.mark.asyncio
async def test_feed_use_reference_launches_as_repeat_with_source_parent() -> None:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "feed_use_prompt": "hidden source prompt",
        "feed_use_gen_id": 77,
        "use_model_key": "nano-banana-pro",
    })
    message = AsyncMock()
    message.photo = [SimpleNamespace(file_id="file-small", file_size=1), SimpleNamespace(file_id="file-big", file_size=2)]
    db_user = SimpleNamespace(id=42, credits=100)
    model_cost = SimpleNamespace(credits=2)
    image_session = SimpleNamespace(id=123)

    with patch("api.public_files.mirror_telegram_file", AsyncMock(return_value="https://example.test/ref.jpg")), \
         patch("bot.handlers.image_gen._supports_img2img", return_value=True), \
         patch("bot.handlers.marketplace._default_quality_for_model", return_value="basic"), \
         patch("bot.handlers.marketplace._default_count_for_model", return_value=1), \
         patch("bot.handlers.marketplace.repo.resolve_image_model_cost", AsyncMock(return_value=model_cost)), \
         patch("bot.handlers.marketplace.repo.create_image_session", AsyncMock(return_value=image_session)), \
         patch("bot.handlers.image_gen._launch_session_generation", AsyncMock(return_value=True)) as launch:
        await marketplace.fsm_prompt_use_reference(message, AsyncMock(), db_user, state, AsyncMock())

    state.clear.assert_awaited_once()
    launch.assert_awaited_once()
    kwargs = launch.await_args.kwargs
    assert kwargs["action_type"] == ImageGenerationAction.repeat
    assert kwargs["parent_generation_id"] == 77
    assert kwargs["source_feed_gen_id"] == 77
    assert kwargs["reference_url"] == "https://example.test/ref.jpg"
