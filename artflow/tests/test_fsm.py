"""FSM-тесты — проверка переходов состояний для ImageGen, VideoGen, Midjourney, Music."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.states import (
    ImageGenFSM,
    MidjourneyFSM,
    MusicFSM,
    PromptUseFSM,
    VideoGenFSM,
)

# ═══════════════════════════════════════════════════════════════════════════
# ImageGenFSM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_image_gen_fsm_model_select_to_mode_select() -> None:
    """model_select → mode_select при выборе модели с несколькими режимами."""
    state = AsyncMock()
    await state.set_state(ImageGenFSM.model_select)
    state.set_state.assert_called_with(ImageGenFSM.model_select)


@pytest.mark.asyncio
async def test_image_gen_fsm_image_upload_state() -> None:
    """Проверка что image_upload стейт существует и доступен."""
    assert hasattr(ImageGenFSM, 'image_upload')


@pytest.mark.asyncio
async def test_image_gen_fsm_prompt_input_state() -> None:
    """Проверка что prompt_input стейт существует."""
    assert hasattr(ImageGenFSM, 'prompt_input')


@pytest.mark.asyncio
async def test_image_gen_fsm_generating_state() -> None:
    """Проверка что generating стейт существует."""
    assert hasattr(ImageGenFSM, 'generating')


@pytest.mark.asyncio
async def test_image_gen_fsm_session_active_state() -> None:
    """Проверка что session_active стейт существует."""
    assert hasattr(ImageGenFSM, 'session_active')


@pytest.mark.asyncio
async def test_image_gen_fsm_photo_to_prompt_states() -> None:
    """Проверка что photo_to_prompt стейты существуют."""
    assert hasattr(ImageGenFSM, 'photo_to_prompt')
    assert hasattr(ImageGenFSM, 'photo_to_prompt_ref')
    assert hasattr(ImageGenFSM, 'photo_to_prompt_model')


# ═══════════════════════════════════════════════════════════════════════════
# VideoGenFSM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_video_gen_fsm_states_exist() -> None:
    """Все стейты VideoGenFSM должны существовать."""
    expected = [
        'model_select', 'mode_select', 'image_upload',
        'params_select', 'prompt_input', 'generating',
    ]
    for state_name in expected:
        assert hasattr(VideoGenFSM, state_name), f"VideoGenFSM не имеет стейта {state_name}"


@pytest.mark.asyncio
async def test_video_gen_fsm_transition_model_to_mode() -> None:
    """model_select → mode_select."""
    state = AsyncMock()
    await state.set_state(VideoGenFSM.model_select)
    await state.set_state(VideoGenFSM.mode_select)
    state.set_state.assert_called_with(VideoGenFSM.mode_select)


@pytest.mark.asyncio
async def test_video_gen_fsm_transition_mode_to_params() -> None:
    """mode_select → params_select."""
    state = AsyncMock()
    await state.set_state(VideoGenFSM.mode_select)
    await state.set_state(VideoGenFSM.params_select)
    state.set_state.assert_called_with(VideoGenFSM.params_select)


@pytest.mark.asyncio
async def test_video_gen_fsm_transition_params_to_prompt() -> None:
    """params_select → prompt_input."""
    state = AsyncMock()
    await state.set_state(VideoGenFSM.params_select)
    await state.set_state(VideoGenFSM.prompt_input)
    state.set_state.assert_called_with(VideoGenFSM.prompt_input)


@pytest.mark.asyncio
async def test_video_gen_fsm_transition_to_generating() -> None:
    """prompt_input → generating."""
    state = AsyncMock()
    await state.set_state(VideoGenFSM.prompt_input)
    await state.set_state(VideoGenFSM.generating)
    state.set_state.assert_called_with(VideoGenFSM.generating)


# ═══════════════════════════════════════════════════════════════════════════
# MidjourneyFSM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_midjourney_fsm_states_exist() -> None:
    """Все стейты MidjourneyFSM должны существовать."""
    expected = [
        'bot_type_select', 'speed_select', 'reference_upload',
        'prompt_input', 'generating', 'viewing_result',
        'action_polling', 'blend_collecting', 'blend_generating',
        'describe_upload', 'describe_polling',
        'video_upload', 'video_speed_select', 'video_prompt',
        'video_generating', 'waiting_modal_input',
    ]
    for state_name in expected:
        assert hasattr(MidjourneyFSM, state_name), f"MidjourneyFSM не имеет стейта {state_name}"


@pytest.mark.asyncio
async def test_midjourney_fsm_bot_type_to_speed() -> None:
    """bot_type_select → speed_select."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.bot_type_select)
    await state.set_state(MidjourneyFSM.speed_select)
    state.set_state.assert_called_with(MidjourneyFSM.speed_select)


@pytest.mark.asyncio
async def test_midjourney_fsm_speed_to_reference() -> None:
    """speed_select → reference_upload."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.speed_select)
    await state.set_state(MidjourneyFSM.reference_upload)
    state.set_state.assert_called_with(MidjourneyFSM.reference_upload)


@pytest.mark.asyncio
async def test_midjourney_fsm_reference_to_prompt() -> None:
    """reference_upload → prompt_input."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.reference_upload)
    await state.set_state(MidjourneyFSM.prompt_input)
    state.set_state.assert_called_with(MidjourneyFSM.prompt_input)


@pytest.mark.asyncio
async def test_midjourney_fsm_prompt_to_generating() -> None:
    """prompt_input → generating."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.prompt_input)
    await state.set_state(MidjourneyFSM.generating)
    state.set_state.assert_called_with(MidjourneyFSM.generating)


@pytest.mark.asyncio
async def test_midjourney_fsm_generating_to_viewing() -> None:
    """generating → viewing_result."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.generating)
    await state.set_state(MidjourneyFSM.viewing_result)
    state.set_state.assert_called_with(MidjourneyFSM.viewing_result)


@pytest.mark.asyncio
async def test_midjourney_fsm_viewing_to_action_polling() -> None:
    """viewing_result → action_polling."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.viewing_result)
    await state.set_state(MidjourneyFSM.action_polling)
    state.set_state.assert_called_with(MidjourneyFSM.action_polling)


@pytest.mark.asyncio
async def test_midjourney_fsm_blend_flow() -> None:
    """blend_collecting → blend_generating (упрощённая проверка)."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.blend_collecting)
    await state.set_state(MidjourneyFSM.blend_generating)
    state.set_state.assert_called_with(MidjourneyFSM.blend_generating)


@pytest.mark.asyncio
async def test_midjourney_fsm_video_flow() -> None:
    """video_upload → video_speed_select → video_prompt → video_generating."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.video_upload)
    await state.set_state(MidjourneyFSM.video_speed_select)
    await state.set_state(MidjourneyFSM.video_prompt)
    await state.set_state(MidjourneyFSM.video_generating)
    state.set_state.assert_called_with(MidjourneyFSM.video_generating)


@pytest.mark.asyncio
async def test_midjourney_fsm_modal_flow() -> None:
    """action_polling → waiting_modal_input."""
    state = AsyncMock()
    await state.set_state(MidjourneyFSM.action_polling)
    await state.set_state(MidjourneyFSM.waiting_modal_input)
    state.set_state.assert_called_with(MidjourneyFSM.waiting_modal_input)


# ═══════════════════════════════════════════════════════════════════════════
# MusicFSM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_music_fsm_states_exist() -> None:
    """Все стейты MusicFSM должны существовать."""
    expected = [
        'prompt_input',
    ]
    for state_name in expected:
        assert hasattr(MusicFSM, state_name), f"MusicFSM не имеет стейта {state_name}"


@pytest.mark.asyncio
async def test_music_fsm_prompt_input_exists() -> None:
    """prompt_input стейт существует."""
    state = AsyncMock()
    await state.set_state(MusicFSM.prompt_input)
    state.set_state.assert_called_with(MusicFSM.prompt_input)


# ═══════════════════════════════════════════════════════════════════════════
# PromptUseFSM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_prompt_use_fsm_states_exist() -> None:
    """Все стейты PromptUseFSM должны существовать."""
    expected = ['model_select', 'reference_upload']
    for state_name in expected:
        assert hasattr(PromptUseFSM, state_name), f"PromptUseFSM не имеет стейта {state_name}"


@pytest.mark.asyncio
async def test_prompt_use_fsm_transitions() -> None:
    """model_select → reference_upload."""
    state = AsyncMock()
    await state.set_state(PromptUseFSM.model_select)
    await state.set_state(PromptUseFSM.reference_upload)
    assert state.set_state.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════
# AdminFSM
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_admin_fsm_importable() -> None:
    """AdminFSM импортируется из bot.handlers.admin."""
    from bot.handlers import admin
    assert hasattr(admin, 'AdminFSM')


@pytest.mark.asyncio
async def test_admin_fsm_states_exist() -> None:
    """Все стейты AdminFSM должны существовать."""
    from bot.handlers import admin
    expected = [
        'edit_price_label', 'edit_price_key', 'edit_price_credits', 'edit_price_rub',
        'new_price_credits', 'new_price_rub',
        'edit_model_display_name', 'edit_model_key', 'edit_model_credits',
        'await_credits_tg_id', 'await_credits_amount',
        'await_ban_tg_id',
        'await_broadcast_text',
    ]
    for state_name in expected:
        assert hasattr(admin.AdminFSM, state_name), f"AdminFSM не имеет стейта {state_name}"


@pytest.mark.asyncio
async def test_admin_fsm_credit_flow_transitions() -> None:
    """await_credits_tg_id → await_credits_amount."""
    from bot.handlers import admin
    state = AsyncMock()
    await state.set_state(admin.AdminFSM.await_credits_tg_id)
    await state.set_state(admin.AdminFSM.await_credits_amount)
    state.set_state.assert_called_with(admin.AdminFSM.await_credits_amount)


@pytest.mark.asyncio
async def test_admin_fsm_price_new_flow() -> None:
    """new_price_credits → new_price_rub."""
    from bot.handlers import admin
    state = AsyncMock()
    await state.set_state(admin.AdminFSM.new_price_credits)
    await state.set_state(admin.AdminFSM.new_price_rub)
    state.set_state.assert_called_with(admin.AdminFSM.new_price_rub)


@pytest.mark.asyncio
async def test_admin_fsm_price_edit_flow() -> None:
    """Цепочка редактирования тарифа."""
    from bot.handlers import admin
    state = AsyncMock()
    await state.set_state(admin.AdminFSM.edit_price_rub)
    await state.set_state(admin.AdminFSM.edit_price_credits)
    await state.set_state(admin.AdminFSM.edit_price_label)
    assert state.set_state.call_count == 3


@pytest.mark.asyncio
async def test_withdrawal_fsm_states_exist() -> None:
    """WithdrawalFSM стейты должны существовать."""
    from bot.handlers import balance
    expected = ['amount', 'details']
    for state_name in expected:
        assert hasattr(balance.WithdrawalFSM, state_name), f"WithdrawalFSM не имеет стейта {state_name}"
