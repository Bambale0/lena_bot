from __future__ import annotations

from collections.abc import Sequence

from api.video_prompt_limits import SEEDANCE_25_PROMPT_MAX_CHARS


IDENTITY_PRIMARY = "identity_primary"
IDENTITY_SUPPORT = "identity_support"
CLOTHING = "clothing"


def _clean(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit] if text else ""


def _dedupe_urls(values: Sequence[object] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def build_seedance_repeat_reference_plan(
    existing_image_urls: Sequence[object] | None,
    *,
    stored_roles: Sequence[object] | None,
    legacy_identity_transfer: bool,
    clothing_reference_url: str | None,
) -> tuple[list[str], int, int | None, list[str]]:
    """Build the ordered Seedance @ImageN plan for a content-edit repeat.

    The generated video becomes @Video1 and is authoritative for the scene.
    Only identity refs are intentionally carried from the previous generation;
    old generic/style/clothing refs are dropped so they cannot compete with the
    current source video. A new clothing ref is appended after identity refs.
    """
    existing = _dedupe_urls(existing_image_urls)
    roles = [str(item or "").strip() for item in (stored_roles or [])]

    identity_refs: list[str] = []
    if roles:
        for index, url in enumerate(existing):
            role = roles[index] if index < len(roles) else ""
            if role.startswith("identity"):
                identity_refs.append(url)
    elif legacy_identity_transfer:
        identity_refs = existing[:3]

    planned_refs = list(identity_refs)
    planned_roles = [
        IDENTITY_PRIMARY if index == 0 else IDENTITY_SUPPORT
        for index in range(len(identity_refs))
    ]

    clothing_url = str(clothing_reference_url or "").strip()
    clothing_index: int | None = None
    if clothing_url:
        if clothing_url in planned_refs:
            clothing_index = planned_refs.index(clothing_url) + 1
        else:
            planned_refs.append(clothing_url)
            planned_roles.append(CLOTHING)
            clothing_index = len(planned_refs)

    return planned_refs, len(identity_refs), clothing_index, planned_roles


def build_seedance_repeat_prompt(
    original_prompt: str,
    *,
    number: object = "",
    clothing: object = "",
    identity_image_count: int = 0,
    clothing_image_index: int | None = None,
) -> str:
    """Create an explicit role-separated Seedance edit prompt.

    Reference numbering follows the provider payload order:
    @Image1..N are image refs and @Video1 is the generated source video.
    """
    number_text = _clean(number, limit=80)
    clothing_text = _clean(clothing, limit=300)

    parts = [
        "Original generation instruction (preserve unless explicitly overridden below):",
        str(original_prompt or "").strip(),
        "",
        "REFERENCE ROLE CONTRACT:",
        "@Video1 is the authoritative source video for motion, body movement, performance, pose, camera movement, framing, timing, background, lighting, composition and scene continuity.",
        "Edit @Video1 instead of redesigning or regenerating the scene from scratch.",
    ]

    if identity_image_count > 0:
        if identity_image_count == 1:
            parts.extend([
                "@Image1 is the primary identity and appearance reference for the main person.",
                "Use @Image1 only to preserve the same person's face, hair, age, skin tone and recognizability throughout the edit.",
            ])
        else:
            extras = " and ".join(f"@Image{index}" for index in range(2, identity_image_count + 1))
            parts.extend([
                "@Image1 is the primary identity and appearance reference for the main person.",
                f"{extras} are additional identity references for the same person and must only reinforce the same identity across different angles.",
                f"Use @Image1 as the main identity anchor and use {extras} only for identity consistency.",
            ])
    else:
        parts.append("Preserve the main person's identity and face from @Video1 unless the user explicitly asks to change them.")

    if clothing_image_index is not None:
        parts.extend([
            f"@Image{clothing_image_index} is the clothing and outfit reference only.",
            f"Use @Image{clothing_image_index} only for garment design, colors, materials, fit, visible logos and accessories.",
            f"Do not copy the face, body identity, pose, background, framing, camera or lighting from @Image{clothing_image_index}.",
        ])

    parts.extend([
        "",
        "PRIORITY EDITS:",
        "Replace only the requested attributes below. Preserve every unrelated detail from @Video1.",
    ])
    if number_text:
        parts.append(
            f'- The target number / digits must read exactly "{number_text}". '
            "Replace the corresponding existing number only; preserve placement and styling unless the user requested otherwise."
        )
    if clothing_text:
        parts.append(f"- Change only the main person's clothing to: {clothing_text}.")
    if not number_text and not clothing_text and clothing_image_index is None:
        parts.append("- Keep the visual content unchanged; reproduce the source video as closely as possible.")

    parts.extend([
        "",
        "Do not change unrelated people, objects, environment, motion, camera work, timing or composition.",
        "Do not blend reference roles: identity images control identity only; a clothing image controls clothing only; @Video1 controls the source scene and motion.",
    ])

    prompt = "\n".join(part for part in parts if part is not None)
    if len(prompt) > SEEDANCE_25_PROMPT_MAX_CHARS:
        raise ValueError(
            "Seedance 2.5 repeat prompt must be at most 30,000 characters after reference-role instructions are added"
        )
    return prompt
