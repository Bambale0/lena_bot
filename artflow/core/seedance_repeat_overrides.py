from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

IDENTITY_PRIMARY = "identity_primary"
IDENTITY_SUPPORT = "identity_support"
CLOTHING = "clothing"


def _clean(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit] if text else ""


@dataclass(frozen=True)
class SeedanceReferencePlan:
    image_urls: tuple[str, ...]
    identity_count: int
    clothing_image_index: int | None
    roles: tuple[str, ...]


def build_seedance_reference_plan(
    identity_urls: Sequence[str],
    clothing_url: str | None = None,
) -> SeedanceReferencePlan:
    identities = list(dict.fromkeys(str(url).strip() for url in identity_urls if str(url).strip()))
    if len(identities) > 3:
        raise ValueError("Можно загрузить не больше 3 фото одного человека.")
    clothing = str(clothing_url or "").strip()
    if clothing in identities:
        raise ValueError("Для одежды используй отдельное фото, отличное от фото лица.")
    refs = identities + ([clothing] if clothing else [])
    roles = [IDENTITY_PRIMARY if i == 0 else IDENTITY_SUPPORT for i in range(len(identities))]
    if clothing:
        roles.append(CLOTHING)
    return SeedanceReferencePlan(
        tuple(refs), len(identities), len(refs) if clothing else None, tuple(roles)
    )


def restore_seedance_reference_plan(
    image_urls: Sequence[str],
    roles: Sequence[str] | None,
    *,
    legacy_identity_transfer: bool = False,
) -> SeedanceReferencePlan:
    """Align roles before deduplication; never guess which image contains clothing."""
    refs = list(image_urls)
    if roles is None and legacy_identity_transfer:
        return build_seedance_reference_plan(refs)
    if roles is None or len(roles) != len(refs):
        raise ValueError("Не удалось восстановить роли фото. Добавь референсы заново.")
    identities, clothing = [], None
    for url, role in zip(refs, roles, strict=True):
        if not str(url or "").strip():
            raise ValueError("Не удалось восстановить фото. Загрузи его заново.")
        if role in (IDENTITY_PRIMARY, IDENTITY_SUPPORT):
            identities.append(url)
        elif role == CLOTHING and clothing is None:
            clothing = url
        else:
            raise ValueError("Некорректные роли референсов. Добавь фото заново.")
    return build_seedance_reference_plan(identities, clothing)


def build_seedance_repeat_reference_plan(
    existing_image_urls: Sequence[object] | None,
    *,
    stored_roles: Sequence[object] | None,
    legacy_identity_transfer: bool,
    clothing_reference_url: str | None,
) -> tuple[list[str], int, int | None, list[str]]:
    existing = [str(url or "").strip() for url in (existing_image_urls or [])]
    if stored_roles:
        if len(stored_roles) != len(existing):
            raise ValueError("Не удалось восстановить роли фото. Добавь референсы заново.")
        identities = [
            url
            for url, role in zip(existing, stored_roles, strict=True)
            if role in (IDENTITY_PRIMARY, IDENTITY_SUPPORT)
        ]
    else:
        identities = existing if legacy_identity_transfer else []
    plan = build_seedance_reference_plan(identities, clothing_reference_url)
    return list(plan.image_urls), plan.identity_count, plan.clothing_image_index, list(plan.roles)


def normalize_seedance_content_edit(value: dict) -> dict[str, str]:
    number = str(value.get("number") or "").strip()
    clothing = str(value.get("clothing") or "").strip()
    if number and (len(number) > 80 or not re.fullmatch(r"[+-]?\d[\d .,:%/+\-]*", number)):
        raise ValueError("В поле числа укажи только число или цифры (до 80 символов).")
    if len(clothing) > 300:
        raise ValueError("Описание одежды слишком длинное: сократи его до 300 символов.")
    if re.search(r"@(image|video)\d+", clothing, re.I):
        raise ValueError("Опиши одежду обычными словами — роли фото бот назначит сам.")
    return {"number": number, "clothing": clothing}


def build_seedance_content_edit_prompt(plan: SeedanceReferencePlan, edit: dict) -> str:
    edit = normalize_seedance_content_edit(edit)
    if not plan.image_urls and not any(edit.values()):
        raise ValueError("Добавь фото лица, одежду или число для замены.")
    return build_seedance_repeat_prompt(
        "",
        number=edit["number"],
        clothing=edit["clothing"],
        identity_image_count=plan.identity_count,
        clothing_image_index=plan.clothing_image_index,
    )


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
    if not 0 <= identity_image_count <= 3:
        raise ValueError("Expected zero to three identity references")
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
            parts.extend(
                [
                    "@Image1 is the primary identity and appearance reference for the main person.",
                    "Use @Image1 only to preserve the same person's face, hair, age, skin tone and recognizability throughout the edit.",
                ]
            )
        else:
            extras = " and ".join(f"@Image{index}" for index in range(2, identity_image_count + 1))
            parts.extend(
                [
                    "@Image1 is the primary identity and appearance reference for the main person.",
                    f"{extras} are additional identity references for the same person and must only reinforce the same identity across different angles.",
                    f"Use @Image1 as the main identity anchor and use {extras} only for identity consistency.",
                ]
            )
    else:
        parts.append(
            "Preserve the main person's identity and face from @Video1 unless the user explicitly asks to change them."
        )

    if identity_image_count:
        parts.append(
            "Replace the main person's facial identity in @Video1 with the identity from @Image1. Do not blend or retain the original face. Preserve the source outfit unless clothing editing is requested."
        )

    if clothing_image_index is not None:
        parts.extend(
            [
                f"@Image{clothing_image_index} is the clothing and outfit reference only.",
                f"Use @Image{clothing_image_index} only for garment design, colors, materials, fit, visible logos and accessories.",
                f"Do not copy the face, body identity, person, pose, body motion, background, framing, camera or lighting from @Image{clothing_image_index}.",
            ]
        )

    parts.extend(
        [
            "",
            "PRIORITY EDITS:",
            "Replace only the requested attributes below. Preserve every unrelated detail from @Video1.",
        ]
    )
    if number_text:
        parts.append(
            f'- The target number / digits must read exactly "{number_text}". '
            "Replace the corresponding existing number only; preserve placement and styling unless the user requested otherwise."
        )
    if clothing_image_index is not None:
        parts.append(
            f"- Replace the main person's outfit using @Image{clothing_image_index}; preserve the source person and all unrelated scene details."
        )
    if clothing_text:
        parts.append(f"- Change only the main person's clothing to: {clothing_text}.")
    if (
        not number_text
        and not clothing_text
        and clothing_image_index is None
        and not identity_image_count
    ):
        parts.append(
            "- Keep the visual content unchanged; reproduce the source video as closely as possible."
        )

    parts.extend(
        [
            "",
            "Do not change unrelated people, objects, environment, motion, camera work, timing or composition.",
            "Do not blend reference roles: identity images control identity only; a clothing image controls clothing only; @Video1 controls the source scene and motion.",
        ]
    )

    prompt = "\n".join(part for part in parts if part is not None)
    from api.video_prompt_limits import SEEDANCE_25_PROMPT_MAX_CHARS

    if len(prompt) > SEEDANCE_25_PROMPT_MAX_CHARS:
        raise ValueError(
            "Seedance 2.5 repeat prompt must be at most 30,000 characters after reference-role instructions are added"
        )
    return prompt
