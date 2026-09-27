from __future__ import annotations

from collections.abc import Mapping


def _clean(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:limit]


def render_seedance_repeat_overrides(prompt: str, data: Mapping[str, object]) -> str:
    """Append user-selected Seedance repeat changes without exposing/replacing the source prompt."""
    number = _clean(data.get("seedance_repeat_number"), limit=80)
    clothing = _clean(data.get("seedance_repeat_clothing"), limit=300)
    if not number and not clothing:
        return prompt

    lines = [
        "",
        "",
        "ВАЖНО: примените следующие параметры пользователя как приоритетные изменения при повторе.",
        "Сохраните остальные детали исходного видео, движение, композицию, камеру и сцену без изменений.",
    ]
    if number:
        lines.append(f"- Число / цифры: {number}")
    if clothing:
        lines.append(f"- Одежда: {clothing}")
    return prompt.rstrip() + "\n".join(lines)
