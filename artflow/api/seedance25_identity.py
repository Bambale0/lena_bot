"""Seedance 2.5 character identity-transfer contract.

This is a provider-facing prompt contract, not marketing copy. It assigns a
single purpose to each multimodal reference so Seedance does not treat the
source video's actor as a competing identity reference.
"""
from __future__ import annotations

import re

from api.video_prompt_limits import SEEDANCE_25_PROMPT_MAX_CHARS

MAX_IDENTITY_IMAGES = 3
MAX_IDENTITY_NUMBER_LENGTH = 12
MAX_IDENTITY_OUTFIT_LENGTH = 160
_IDENTITY_NUMBER_RE = re.compile(r"^[0-9][0-9 .:/-]{0,11}$")


def validate_identity_transfer_refs(*, images: list[str], videos: list[str]) -> None:
    """Require one source video and one-to-three identity photos."""
    if not images:
        raise ValueError("Seedance Identity Transfer requires at least one identity photo")
    if len(images) > MAX_IDENTITY_IMAGES:
        raise ValueError(
            f"Seedance Identity Transfer supports at most {MAX_IDENTITY_IMAGES} identity photos"
        )
    if len(videos) != 1:
        raise ValueError("Seedance Identity Transfer requires one source video")


def normalize_identity_number(value: str | None) -> str:
    """Validate the optional visible number/digits override without coercing zeros."""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > MAX_IDENTITY_NUMBER_LENGTH or not _IDENTITY_NUMBER_RE.fullmatch(text):
        raise ValueError(
            "Seedance identity number must contain only digits and simple separators "
            f"and be at most {MAX_IDENTITY_NUMBER_LENGTH} characters"
        )
    return text


def normalize_identity_outfit(value: str | None) -> str:
    """Validate the optional clothing override used by identity transfer."""
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) > MAX_IDENTITY_OUTFIT_LENGTH:
        raise ValueError(
            f"Seedance identity outfit must be at most {MAX_IDENTITY_OUTFIT_LENGTH} characters"
        )
    return text


def build_identity_transfer_prompt(
    user_prompt: str,
    *,
    image_count: int,
    number_text: str | None = None,
    outfit_text: str | None = None,
) -> str:
    """Build the tested role-separated prompt for one-to-three identity refs."""
    if image_count < 1 or image_count > MAX_IDENTITY_IMAGES:
        raise ValueError(
            f"Seedance Identity Transfer expects 1-{MAX_IDENTITY_IMAGES} identity photos"
        )

    number = normalize_identity_number(number_text)
    outfit = normalize_identity_outfit(outfit_text)

    if image_count == 1:
        identity_intro = (
            "@Image1 is the sole authoritative identity and appearance reference "
            "for the main person."
        )
        image_roles = "Use @Image1 as the identity anchor in every visible frame and angle."
        represented_by = "@Image1"
    else:
        extras = " and ".join(f"@Image{index}" for index in range(2, image_count + 1))
        identity_intro = (
            "@Image1 is the primary identity and appearance reference for the main person. "
            f"{extras} are additional identity references for the same person and must only "
            "reinforce the same identity across different head angles."
        )
        image_roles = (
            "Use @Image1 as the main identity anchor. "
            f"Use {extras} only to improve identity consistency during head turns and angle changes."
        )
        represented_by = ", ".join(f"@Image{index}" for index in range(1, image_count + 1))

    prompt = f"""\
{identity_intro}

@Video1 is only the reference for motion, body movement, performance, camera movement, framing, timing, background, lighting and scene continuity.

Replace only the main person in @Video1 with the person represented by {represented_by}.

Preserve the same facial identity throughout the whole video: facial shape, eye shape and color, nose, lips, jawline, skin tone, age, hairline, hair color, hairstyle and recognizability.

{image_roles}

Do not inherit, preserve, average, morph or blend the original person's facial identity from @Video1 with the identity from the image references.
Preserve all motion, pose, performance, camera work, framing, timing, environment, lighting and unrelated people from @Video1.
Do not redesign the scene or change unrelated subjects."""

    structured_overrides: list[str] = []
    if number:
        structured_overrides.append(f"Number / digits: {number}")
    if outfit:
        structured_overrides.append(f"Clothing / outfit: {outfit}")
    if structured_overrides:
        prompt += (
            "\n\nApply these priority appearance changes to the replacement person only. "
            "They override conflicting number/clothing details from @Video1, while facial identity "
            "must still come only from the @Image references:\n- "
            + "\n- ".join(structured_overrides)
        )

    extra = str(user_prompt or "").strip()
    if extra:
        prompt += f"\n\nAdditional user instruction:\n{extra}"
    if len(prompt) > SEEDANCE_25_PROMPT_MAX_CHARS:
        raise ValueError(
            "Seedance 2.5 Identity Transfer prompt must be at most 30,000 characters "
            "after reference-role instructions are added"
        )
    return prompt
