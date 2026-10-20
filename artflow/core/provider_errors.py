"""Allowlisted public explanations; never include provider payload or prompt text."""
from __future__ import annotations


def known_generation_user_error(error: BaseException | str | None) -> str | None:
    raw = " ".join(str(error or "").casefold().split())
    if "copyright restrictions" in raw:
        return (
            "Генератор отклонил результат из-за возможного нарушения авторских прав. "
            "Измени описание или используй другой референс, на который у тебя есть права."
        )
    if "provider_rejected_request" in raw:
        return (
            "Генератор отклонил запрос и не сообщил точную причину. "
            "Проверь описание и референсы перед новой попыткой."
        )
    if any(marker in raw for marker in (
        "image fetch failed", "не удалось загрузить исходное изображение",
        "исходное изображение больше недоступно",
    )):
        return (
            "Не удалось загрузить исходное изображение. "
            "Загрузи фото заново и повтори запрос."
        )
    return None
