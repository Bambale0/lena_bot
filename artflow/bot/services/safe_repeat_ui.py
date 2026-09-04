from __future__ import annotations

from typing import Any, Callable


def _rewrite_repeat_buttons(markup: Any, *, gen_id: int | None, image_only: bool = True) -> Any:
    if not gen_id or markup is None:
        return markup
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            callback = str(getattr(button, "callback_data", "") or "")
            if callback in {f"img_session:repeat:{gen_id}", f"regen:image:{gen_id}"}:
                button.text = "🔁 Повторить генерацию"
                # Namespace our own numeric Generation.id so it can never be
                # mistaken for a provider task id that happens to be numeric.
                button.callback_data = f"repeat_image_db_{gen_id}"
    return markup


def install_safe_repeat_keyboard_support(keyboards: Any) -> None:
    if getattr(keyboards, "_safe_repeat_keyboard_installed", False):
        return

    original_session: Callable[..., Any] = keyboards.image_session_kb
    original_after: Callable[..., Any] = keyboards.after_generation_kb

    def image_session_kb(gen_id: int | None = None, **kwargs: Any):
        return _rewrite_repeat_buttons(original_session(gen_id, **kwargs), gen_id=gen_id)

    def after_generation_kb(gen_id: int, gen_type: str, **kwargs: Any):
        markup = original_after(gen_id, gen_type, **kwargs)
        if str(gen_type) == "image":
            return _rewrite_repeat_buttons(markup, gen_id=gen_id)
        return markup

    keyboards.image_session_kb = image_session_kb
    keyboards.after_generation_kb = after_generation_kb
    keyboards._safe_repeat_keyboard_installed = True
