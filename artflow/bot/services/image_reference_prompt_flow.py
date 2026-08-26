from __future__ import annotations

from typing import Any

from bot.states import ImageGenFSM

_COMPOSER_STATE_MARKER = "image_params_changed"


def _is_task_first_composer(data: dict[str, Any]) -> bool:
    """The v2 model composer owns this marker; legacy image flows do not."""
    return _COMPOSER_STATE_MARKER in data


def _reference_status(count: int) -> str:
    if count == 1:
        return "1 референс добавлен"
    if count in {2, 3, 4}:
        return f"{count} референса добавлены"
    return f"{count} референсов добавлены"


def _humanize_review_count(text: str) -> str:
    return text.replace("🔢 Количество: <b>", "🖼 Изображений за запуск: <b>")


def install_image_reference_prompt_flow(legacy_image_gen: Any) -> None:
    """Keep the v2 composer task-first after one or many reference uploads.

    The v2 composer preselects ratio/quality before the user uploads references.
    The legacy `_after_ref_upload` helper interprets those preselected values as a
    completed legacy wizard and activates an ImageSession immediately. That skips
    the mandatory prompt step. Patch only v2-composer states and delegate every
    legacy state to the original implementation.

    New references also define a new draft boundary. FSM data may survive an
    interrupted or already completed draft, so a previous pending prompt must
    never be inherited here. The user must explicitly submit fresh text after the
    new references before the launch review can appear.
    """

    original_after_ref_upload = legacy_image_gen._after_ref_upload
    if getattr(original_after_ref_upload, "__image_prompt_flow_wrapped__", False):
        return

    original_review_text = legacy_image_gen._image_review_text

    async def after_ref_upload(
        message,
        state,
        session,
        db_user,
        model_key: str,
        display_name: str,
        caps: dict,
    ) -> None:
        data = await state.get_data()
        if not _is_task_first_composer(data):
            await original_after_ref_upload(
                message,
                state,
                session,
                db_user,
                model_key,
                display_name,
                caps,
            )
            return

        refs = legacy_image_gen._state_reference_file_ids(data)
        if not refs:
            await original_after_ref_upload(
                message,
                state,
                session,
                db_user,
                model_key,
                display_name,
                caps,
            )
            return

        # A new set of references starts a new draft. Clear every launch payload
        # that may belong to an older account/session before asking for text.
        await state.update_data(
            mode="image",
            image_mode="image",
            image_session_id=None,
            pending_image_prompt=None,
            pending_reference_url=None,
            pending_parent_generation_id=None,
            pending_source_feed_gen_id=None,
            pending_action_type=None,
        )
        await state.set_state(ImageGenFSM.prompt_input)
        await message.answer(
            f"✅ <b>{_reference_status(len(refs))}</b>\n\n"
            "📝 <b>Теперь напиши промпт</b>\n"
            "Одним сообщением опиши, что нужно создать или изменить.\n\n"
            "Кнопка запуска появится только после того, как промпт будет сохранён.",
            reply_markup=legacy_image_gen.back_to_menu_kb(),
        )

    def review_text(*args: Any, **kwargs: Any) -> str:
        return _humanize_review_count(original_review_text(*args, **kwargs))

    setattr(after_ref_upload, "__image_prompt_flow_wrapped__", True)
    setattr(after_ref_upload, "__wrapped__", original_after_ref_upload)
    setattr(review_text, "__image_prompt_flow_wrapped__", True)
    setattr(review_text, "__wrapped__", original_review_text)

    legacy_image_gen._after_ref_upload = after_ref_upload
    legacy_image_gen._image_review_text = review_text
