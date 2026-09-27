"""Seedance 2.5 repeat-edit prompt overrides.

This module is deliberately independent from trend personalization. It turns
small user-supplied edits into explicit video-edit instructions while keeping
the original prompt server-side.
"""
from __future__ import annotations

MAX_SEEDANCE_PROMPT_CHARS = 30_000
MAX_NUMBER_VALUE_CHARS = 120
MAX_OUTFIT_VALUE_CHARS = 600


class SeedanceRepeatEditError(ValueError):
    """Invalid Seedance repeat-edit input."""


def _clean(value: str | None, *, max_chars: int, label: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_chars:
        raise SeedanceRepeatEditError(
            f"{label} is too long: maximum is {max_chars} characters"
        )
    return text


def has_seedance_repeat_edits(
    *, number_value: str | None, outfit_value: str | None
) -> bool:
    return bool(
        _clean(number_value, max_chars=MAX_NUMBER_VALUE_CHARS, label="Number/text")
        or _clean(outfit_value, max_chars=MAX_OUTFIT_VALUE_CHARS, label="Outfit")
    )


def build_seedance_repeat_edit_prompt(
    base_prompt: str,
    *,
    number_value: str | None = None,
    outfit_value: str | None = None,
) -> str:
    """Append targeted, high-priority video-edit instructions to a hidden prompt."""
    base = str(base_prompt or "").strip()
    number = _clean(
        number_value,
        max_chars=MAX_NUMBER_VALUE_CHARS,
        label="Number/text",
    )
    outfit = _clean(
        outfit_value,
        max_chars=MAX_OUTFIT_VALUE_CHARS,
        label="Outfit",
    )
    if not number and not outfit:
        return base

    edits: list[str] = []
    if number:
        edits.append(
            "- Replace only the prominent editable number/text visible in the source "
            f'video with "{number}". Preserve its placement, scale, material, '
            "typography and perspective as closely as possible. Do not alter "
            "unrelated text or numbers."
        )
    if outfit:
        edits.append(
            "- Replace the main character's outfit with: "
            f'"{outfit}". Preserve the character identity, face, hair, body '
            "proportions, pose and motion."
        )

    override = (
        "SEEDANCE VIDEO EDIT — USER PRIORITY OVERRIDES:\n"
        "Apply the following changes to the source video. These user edits have "
        "priority over conflicting details in the earlier prompt.\n"
        + "\n".join(edits)
        + "\nPreserve all other scene content, camera motion, timing, composition, "
        "background, lighting and unchanged characters."
    )
    result = f"{base}\n\n{override}" if base else override
    if len(result) > MAX_SEEDANCE_PROMPT_CHARS:
        raise SeedanceRepeatEditError(
            "Seedance 2.5 final prompt exceeds the 30,000 character provider limit"
        )
    return result
