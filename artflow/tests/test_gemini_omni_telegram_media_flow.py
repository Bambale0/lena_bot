from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import gemini_omni_references as omni_refs
from bot.handlers import video_references
from bot.states import VideoGenFSM
from core.gemini_omni import GEMINI_OMNI_VIDEO_MODEL


def _fake_state(**initial: object):
    data = dict(initial)

    async def update_data(**kwargs: object) -> None:
        data.update(kwargs)

    state = AsyncMock()
    state.get_data = AsyncMock(side_effect=lambda: data)
    state.update_data = AsyncMock(side_effect=update_data)
    state.set_state = AsyncMock()
    return state, data


def _message_with_document(
    *,
    file_id: str,
    file_name: str,
    mime_type: str,
    file_size: int = 1_000_000,
):
    return SimpleNamespace(
        document=SimpleNamespace(
            file_id=file_id,
            file_name=file_name,
            mime_type=mime_type,
            file_size=file_size,
        ),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_gemini_video_mode_filter_is_scoped_to_omni_video_mode() -> None:
    state, _ = _fake_state(model_key=GEMINI_OMNI_VIDEO_MODEL, mode="video")
    assert await omni_refs.GeminiOmniVideoModeFilter()(SimpleNamespace(), state)

    other_state, _ = _fake_state(model_key="seedance/2.0", mode="video")
    assert not await omni_refs.GeminiOmniVideoModeFilter()(SimpleNamespace(), other_state)


@pytest.mark.asyncio
async def test_choose_omni_video_mode_shows_done_button_immediately() -> None:
    state, data = _fake_state()
    call = SimpleNamespace(message=SimpleNamespace(), answer=AsyncMock())
    model_cost = SimpleNamespace(display_name="Gemini Omni Video")

    with patch.object(omni_refs.repo, "get_model_cost", AsyncMock(return_value=model_cost)):
        with patch.object(omni_refs, "safe_edit_message", AsyncMock()) as edit:
            with patch.object(omni_refs, "safe_answer_callback", AsyncMock()):
                await omni_refs.choose_gemini_omni_video_mode(call, state, AsyncMock())

    assert data["model_key"] == GEMINI_OMNI_VIDEO_MODEL
    assert data["mode"] == "video"
    state.set_state.assert_awaited_with(VideoGenFSM.image_upload)
    markup = edit.await_args.kwargs["reply_markup"]
    button_texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Готово" in button_texts
    assert "7 слотов" in edit.await_args.args[1]


@pytest.mark.asyncio
async def test_omni_accepts_mov_document_plus_three_png_documents() -> None:
    state, data = _fake_state(
        model_key=GEMINI_OMNI_VIDEO_MODEL,
        mode="video",
        ref_file_ids=[],
        character_ids=[],
    )
    bot = MagicMock()
    mov = _message_with_document(
        file_id="mov_1",
        file_name="IMG_5888.MOV",
        mime_type="video/quicktime",
        file_size=1_400_000,
    )
    png_messages = [
        _message_with_document(
            file_id=f"png_{index}",
            file_name=f"IMG_{index}.PNG",
            mime_type="image/png",
        )
        for index in range(1, 4)
    ]

    with patch.object(
        omni_refs,
        "mirror_telegram_file",
        AsyncMock(return_value="https://cdn.test/source.mov"),
    ):
        await omni_refs.upload_gemini_omni_document(mov, state, bot)

    for message in png_messages:
        await omni_refs.upload_gemini_omni_document(message, state, bot)

    assert data["reference_video_url"] == "https://cdn.test/source.mov"
    assert data["video_clip_start"] == 0
    assert data["video_clip_end"] == 10
    assert data["ref_file_ids"] == ["png_1", "png_2", "png_3"]
    assert "5/7" in png_messages[-1].answer.await_args.args[0]
    assert mov.answer.await_count == 1


@pytest.mark.asyncio
async def test_omni_rejects_media_that_would_overflow_slot_quota() -> None:
    state, data = _fake_state(
        model_key=GEMINI_OMNI_VIDEO_MODEL,
        mode="video",
        reference_video_url="https://cdn.test/source.mov",
        ref_file_ids=["1", "2", "3", "4", "5"],
        character_ids=[],
    )
    extra = _message_with_document(
        file_id="png_6",
        file_name="extra.png",
        mime_type="image/png",
    )

    await omni_refs.upload_gemini_omni_document(extra, state, MagicMock())

    assert data["ref_file_ids"] == ["1", "2", "3", "4", "5"]
    assert "Квота Gemini Omni превышена" in extra.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_omni_done_moves_to_params_without_losing_mixed_refs() -> None:
    state, data = _fake_state(
        model_key=GEMINI_OMNI_VIDEO_MODEL,
        mode="video",
        reference_video_url="https://cdn.test/source.mov",
        ref_file_ids=["png_1", "png_2", "png_3"],
        character_ids=[],
        duration=4,
        aspect_ratio="16:9",
        resolution="720p",
    )
    call = SimpleNamespace(message=SimpleNamespace(), answer=AsyncMock())
    model_cost = SimpleNamespace(display_name="Gemini Omni Video")

    with patch.object(omni_refs.repo, "get_model_cost", AsyncMock(return_value=model_cost)):
        with patch.object(omni_refs, "safe_edit_message", AsyncMock()) as edit:
            with patch.object(omni_refs, "safe_answer_callback", AsyncMock()):
                with patch(
                    "bot.handlers.video_gen._video_params_reply_markup",
                    return_value=MagicMock(),
                ):
                    await omni_refs.finish_gemini_omni_media(call, state, AsyncMock())

    state.set_state.assert_awaited_with(VideoGenFSM.params_select)
    assert data["reference_video_url"] == "https://cdn.test/source.mov"
    assert data["ref_file_ids"] == ["png_1", "png_2", "png_3"]
    assert "5/7" in edit.await_args.args[1]


def test_seedance_video_reference_router_cannot_intercept_gemini_omni() -> None:
    assert f"vid_mode:video:{GEMINI_OMNI_VIDEO_MODEL}" not in video_references._VIDEO_REFERENCE_CALLBACKS
