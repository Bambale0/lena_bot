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

        # References switch a dual-mode model to img2img, but must not create an
        # active series before there is a real prompt attached to the task.
        await state.update_data(
            mode="image",
            image_mode="image",
            image_session_id=None,
        )

        saved_prompt = str(data.get("pending_image_prompt") or "").strip()
        bot = getattr(message, "bot", None)
        if saved_prompt and bot is not None:
            image_session = await legacy_image_gen._ensure_active_image_session_from_state(
                session=session,
                state=state,
                db_user=db_user,
            )
            reference_url = await legacy_image_gen._session_reference_url(
                bot,
                image_session,
                prefer_last_result=False,
                state=state,
            )
            if reference_url:
                model_cost = await legacy_image_gen.repo.resolve_image_model_cost(
                    session,
                    image_session.model,
                    quality=image_session.quality,
                )
                credits = model_cost.credits if model_cost else 1
                await state.update_data(
                    pending_image_prompt=saved_prompt,
                    pending_reference_url=reference_url,
                    pending_parent_generation_id=None,
                    pending_source_feed_gen_id=data.get("pending_source_feed_gen_id"),
                    pending_action_type=legacy_image_gen.ImageGenerationAction.initial.value,
                    credits=credits,
                )
                await state.set_state(ImageGenFSM.review)
                await message.answer(
                    _humanize_review_count(
                        original_review_text(
                            image_session=image_session,
                            prompt=saved_prompt,
                            credits=credits,
                            has_reference=True,
                        )
                    ),
                    reply_markup=legacy_image_gen._image_review_kb(image_session),
                )
                return

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
