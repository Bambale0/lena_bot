from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services import image_reference_prompt_flow
from bot.states import ImageGenFSM


def _legacy_stub(*, original_after_ref_upload: AsyncMock, review_text=None):
    return SimpleNamespace(
        _after_ref_upload=original_after_ref_upload,
        _image_review_text=review_text or (lambda **kwargs: "review"),
        _state_reference_file_ids=lambda data: list(data.get("ref_file_ids") or []),
        _ensure_active_image_session_from_state=AsyncMock(),
        _session_reference_url=AsyncMock(),
        _image_review_kb=lambda image_session: "review-kb",
        back_to_menu_kb=lambda: "back-kb",
        repo=SimpleNamespace(resolve_image_model_cost=AsyncMock()),
        ImageGenerationAction=SimpleNamespace(initial=SimpleNamespace(value="initial")),
    )


@pytest.mark.asyncio
async def test_v2_reference_flow_requests_prompt_instead_of_activating_session() -> None:
    original = AsyncMock()
    legacy = _legacy_stub(original_after_ref_upload=original)
    image_reference_prompt_flow.install_image_reference_prompt_flow(legacy)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "image_params_changed": False,
            "model_key": "nano-banana-pro",
            "mode": "image",
            "aspect_ratio": "1:1",
            "quality": "2K",
            "ref_file_ids": ["ref-1", "ref-2"],
        }
    )
    message = SimpleNamespace(answer=AsyncMock(), bot=object())

    await legacy._after_ref_upload(
        message,
        state,
        AsyncMock(),
        SimpleNamespace(id=42),
        "nano-banana-pro",
        "Nano Banana Pro",
        {"max_refs": 8, "has_quality": True},
    )

    original.assert_not_awaited()
    state.update_data.assert_awaited_with(
        mode="image",
        image_mode="image",
        image_session_id=None,
    )
    state.set_state.assert_awaited_once_with(ImageGenFSM.prompt_input)
    text = message.answer.await_args.args[0]
    assert "2 референса добавлены" in text
    assert "Теперь напиши промпт" in text
    assert "Кнопка запуска появится только после" in text


@pytest.mark.asyncio
async def test_v2_reference_flow_reuses_saved_prompt_and_opens_review() -> None:
    original = AsyncMock()
    image_session = SimpleNamespace(
        id=7,
        model="nano-banana-pro",
        quality="2K",
        count=1,
    )
    legacy = _legacy_stub(
        original_after_ref_upload=original,
        review_text=lambda **kwargs: (
            f"📝 Промпт: {kwargs['prompt']}\n"
            "🔢 Количество: <b>1</b>\n"
            f"💋 Стоимость: <b>{kwargs['credits']:g}</b>"
        ),
    )
    legacy._ensure_active_image_session_from_state = AsyncMock(return_value=image_session)
    legacy._session_reference_url = AsyncMock(
        return_value=["https://example.test/ref-1.jpg", "https://example.test/ref-2.jpg"]
    )
    legacy.repo.resolve_image_model_cost = AsyncMock(return_value=SimpleNamespace(credits=12))
    image_reference_prompt_flow.install_image_reference_prompt_flow(legacy)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "image_params_changed": False,
            "model_key": "nano-banana-pro",
            "mode": "image",
            "ref_file_ids": ["ref-1", "ref-2"],
            "pending_image_prompt": "сделай рекламный кадр",
        }
    )
    message = SimpleNamespace(answer=AsyncMock(), bot=object())

    await legacy._after_ref_upload(
        message,
        state,
        AsyncMock(),
        SimpleNamespace(id=42),
        "nano-banana-pro",
        "Nano Banana Pro",
        {"max_refs": 8, "has_quality": True},
    )

    original.assert_not_awaited()
    state.set_state.assert_awaited_once_with(ImageGenFSM.review)
    assert state.update_data.await_count == 2
    pending_update = state.update_data.await_args_list[-1].kwargs
    assert pending_update["pending_image_prompt"] == "сделай рекламный кадр"
    assert pending_update["pending_reference_url"] == [
        "https://example.test/ref-1.jpg",
        "https://example.test/ref-2.jpg",
    ]
    text = message.answer.await_args.args[0]
    assert "сделай рекламный кадр" in text
    assert "🖼 Изображений за запуск: <b>1</b>" in text
    assert message.answer.await_args.kwargs["reply_markup"] == "review-kb"


@pytest.mark.asyncio
async def test_legacy_reference_flow_stays_untouched() -> None:
    original = AsyncMock()
    legacy = _legacy_stub(original_after_ref_upload=original)
    image_reference_prompt_flow.install_image_reference_prompt_flow(legacy)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "model_key": "nano-banana-pro",
            "ref_file_ids": ["ref-1"],
        }
    )
    message = SimpleNamespace(answer=AsyncMock(), bot=object())
    session = AsyncMock()
    db_user = SimpleNamespace(id=42)
    caps = {"max_refs": 8}

    await legacy._after_ref_upload(
        message,
        state,
        session,
        db_user,
        "nano-banana-pro",
        "Nano Banana Pro",
        caps,
    )

    original.assert_awaited_once_with(
        message,
        state,
        session,
        db_user,
        "nano-banana-pro",
        "Nano Banana Pro",
        caps,
    )


def test_review_count_label_explains_what_is_counted() -> None:
    assert image_reference_prompt_flow._humanize_review_count(
        "🔢 Количество: <b>1</b>"
    ) == "🖼 Изображений за запуск: <b>1</b>"
