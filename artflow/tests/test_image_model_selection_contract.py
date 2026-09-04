from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers import image_gen


@pytest.mark.asyncio
async def test_model_selection_opens_task_first_composer_with_db_user() -> None:
    call = SimpleNamespace(
        data="img_model:gpt-image-2-text-to-image",
        message=SimpleNamespace(),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.get_data = AsyncMock(return_value={})
    db_user = SimpleNamespace(id=42, tg_id=42, credits=500)

    with (
        patch(
            "bot.handlers.image_wizard_v2.repo.resolve_image_model_cost",
            AsyncMock(return_value=SimpleNamespace(credits=2)),
        ),
        patch("bot.handlers.image_wizard_v2.safe_edit_message", AsyncMock()) as edit_message,
        patch("bot.handlers.image_wizard_v2.safe_answer_callback", AsyncMock()),
    ):
        await image_gen.cb_image_model(call, state, AsyncMock(), db_user)

    state.set_state.assert_awaited_with(image_gen.ImageGenFSM.prompt_input)
    text = edit_message.await_args.args[1]
    callbacks = [
        button.callback_data
        for row in edit_message.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "GPT Image 2" in text
    assert "Можно сразу отправлять" in text
    assert "Выбери параметры" not in text
    assert "img_v2:ratio" in callbacks
    assert "img_v2:quality" in callbacks
    assert "img_v2:refs" in callbacks
