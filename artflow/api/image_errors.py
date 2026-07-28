from __future__ import annotations


_SAFETY_MARKERS = (
    "image_safety",
    "prohibited_content",
    "responsible ai",
    "prohibited use",
    "flagged as sensitive",
    "violated vertex ai",
    "violated google",
)

_NO_IMAGE_MARKERS = (
    "image_other",
    "no_image",
    "returned no image urls",
    "returned no result url",
    "could not generate the image based on the prompt",
)


def image_generation_user_error(error: BaseException | str) -> str:
    raw = str(error or "").lower()
    if any(marker in raw for marker in _SAFETY_MARKERS):
        return (
            "Модель отклонила промпт или референс из-за safety/moderation. "
            "Попробуй заменить референс или переформулировать запрос мягче."
        )
    if any(marker in raw for marker in _NO_IMAGE_MARKERS):
        return (
            "Модель не смогла собрать изображение по этому промпту/референсам. "
            "Попробуй меньше референсов, проще композицию или другой формат."
        )
    return "Ошибка генерации. Попробуй другой промпт или модель."


def telegram_image_error_text(error: BaseException | str) -> str:
    return f"❌ {image_generation_user_error(error)}\n\n💋 возвращены."
