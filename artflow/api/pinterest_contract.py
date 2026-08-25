from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from inspect import signature
from typing import Any, Iterator

from fastapi import HTTPException

PINTEREST_PROMPT_MARKER = "PINTEREST_RECREATION_CONTRACT_V2"
PINTEREST_FLOW = "pinterest_ai"
PINTEREST_REFERENCE_CONTRACT = "pinterest_scene_identity"
_DISPLAY_PROMPT = "Pinterest AI: сохранить внешность с ваших фото в выбранной сцене Pinterest."

_PROVIDER_ROLE_PROMPT = f"""{PINTEREST_PROMPT_MARKER}
PINTEREST SCENE IDENTITY CONTRACT

You are generating a NEW photorealistic image.

Image 1 is the PRIMARY USER_IDENTITY_REFERENCE. Use Image 1 only for the person's face, identity, apparent age, skin tone, facial geometry, hairline, distinctive facial features, natural body build, hair length and hair color.
Image 2 is the only SCENE_REFERENCE. Use Image 2 only for the scene, exact pose, body placement, outfit concept, composition, lighting, camera angle, framing, expression, background and photographic mood.
Images 3 and later, when present, are USER_IDENTITY_EVIDENCE for the SAME person as Image 1. Use them only to reinforce the user's identity, face, hair and natural proportions from additional angles. They never define scene, pose, outfit, background, framing or lighting.

Create a new photo of the person from Image 1 placed naturally into the scene and composition of Image 2. When identity-evidence images are present, use them together with Image 1 to keep that same person recognizable and consistent.

HARD NEGATIVE RULES
- Do not preserve the person from Image 2.
- Do not copy or reuse the person from Image 2.
- Do not copy the face, hair identity, ethnicity, apparent age, or skin tone from Image 2.
- Do not return Image 1 unchanged.
- Do not return Image 2 unchanged.
- Do not use Image 1 or identity-evidence images as the composition, outfit, background, camera, or pose.
- Do not average, blend, or morph identities. Identity from Image 1, supported by identity-evidence images, always wins.
- Do not output a collage, comparison, screenshot, source image, UI, text, watermark, or split-screen.

PARTIAL TRANSFER GUARD
- Do not take ONLY hair color, hair length, or body cues from the user while keeping the SCENE_REFERENCE person's face.
- Do not copy person from scene reference.
- Do not replace identity. Keep the user's facial structure unchanged.

QUALITY RULES
- The result must look like a real new photograph, not an edit preview.
- Keep face, hands, and body anatomy natural.
- Keep the user recognizable from Image 1 and any identity-evidence images.
"""

_provider_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "apix_pinterest_provider_context",
    default=None,
)


def _unique_urls(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        source = value if isinstance(value, (list, tuple)) else [value]
        for item in source:
            clean = str(item or "").strip()
            if clean and clean not in result:
                result.append(clean)
    return result


def _prompt_tags(prompt_source: Any | None) -> set[str]:
    return {
        str(item or "").strip().lower()
        for item in (getattr(prompt_source, "tags", None) or [])
        if str(item or "").strip()
    }


def is_pinterest_prompt_source(prompt_source: Any | None) -> bool:
    if prompt_source is None:
        return False
    tags = _prompt_tags(prompt_source)
    title = str(getattr(prompt_source, "title", "") or "").strip().lower()
    return bool(
        {"pinterest", "pinterest-repeat", "repeat-pinterest"} & tags
        or "pinterest" in title
    )


def build_pinterest_contract(
    *,
    scene_reference: str,
    identity_reference: str,
    identity_evidence: list[str] | None = None,
    trend_id: int | None = None,
    height_cm: int | None = None,
    weight_kg: int | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    scene = str(scene_reference or "").strip()
    identity = str(identity_reference or "").strip()
    evidence = [item for item in _unique_urls(identity_evidence or []) if item not in {scene, identity}]
    logical = _unique_urls(scene, identity, evidence)
    roles: list[str] = []
    for item in logical:
        if item == scene:
            roles.append("scene")
        elif item == identity:
            roles.append("identity")
        else:
            roles.append("identity_evidence")
    provider_images = _unique_urls(identity, scene, evidence)
    provider_roles = ["identity", "scene", *(["identity_evidence"] * len(evidence))]
    return {
        "flow": PINTEREST_FLOW,
        "source": "trend",
        "reference_contract": PINTEREST_REFERENCE_CONTRACT,
        "trend_id": trend_id,
        "scene_reference": scene,
        "identity_reference": identity,
        "identity_evidence": evidence,
        "reference_images": logical,
        "source_reference_images": logical,
        "reference_roles": roles,
        # Nano Banana Pro is more stable when its provider-facing anchors are
        # identity first and scene second. Additional user angles follow those
        # two anchors and are explicitly constrained to identity evidence.
        "provider_reference_images": provider_images,
        "provider_reference_roles": provider_roles,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "confirmed": bool(confirmed),
        "display_prompt": _DISPLAY_PROMPT,
        "prompt_hidden": True,
        "prompt_actions_allowed": False,
        "feed_prompt_visible": False,
        "pinterest_provider_safe_refs": True,
        "generic_reference_guidance_disabled": True,
    }


def pinterest_provider_prompt(
    hidden_prompt: str,
    *,
    height_cm: int | None = None,
    weight_kg: int | None = None,
) -> str:
    measurements: list[str] = []
    if height_cm is not None:
        measurements.append(f"height {height_cm} cm")
    if weight_kg is not None:
        measurements.append(f"weight {weight_kg} kg")
    measurement_text = ", ".join(measurements) if measurements else "not provided"
    original = str(hidden_prompt or "").strip()
    suffix = f"\n\nPRIVATE SCENE INSTRUCTIONS\n{original}" if original else ""
    return (
        f"{_PROVIDER_ROLE_PROMPT}\n"
        f"- User measurements: {measurement_text}. Use them only for realistic body scale; never render measurement text into the image."
        f"{suffix}"
    )


@contextmanager
def pinterest_provider_context(contract: dict[str, Any] | None) -> Iterator[None]:
    token = _provider_context.set(dict(contract or {}) if contract else None)
    try:
        yield
    finally:
        _provider_context.reset(token)


def active_pinterest_contract() -> dict[str, Any] | None:
    current = _provider_context.get()
    return dict(current) if current else None


def _private_input_params(value: Any, contract: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        payload = dict(value)
    elif value in (None, ""):
        payload = {}
    else:
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = {}
        payload = dict(parsed) if isinstance(parsed, dict) else {}
    payload.update(contract)
    payload["prompt_hidden"] = True
    payload["prompt_actions_allowed"] = False
    payload["feed_prompt_visible"] = False
    return payload


def _bound_call(func: Any, args: tuple[Any, ...], kwargs: dict[str, Any], **updates: Any) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Replace named arguments without depending on positional indexes."""
    bound = signature(func).bind_partial(*args, **kwargs)
    for key, value in updates.items():
        bound.arguments[key] = value
    return bound.args, bound.kwargs


def install_pinterest_persistence_contract(repository: Any) -> None:
    """Redact the private Pinterest recipe before the first DB commit.

    ``create_image_generation`` resolves the curated prompt before provider launch.
    Without this hook the private recipe briefly existed in Generation/ImageSession
    rows and remained there on provider failure. The reference flow is fail-closed:
    persistence gets only a safe display label plus role metadata while the provider
    still receives the private prompt from the in-memory launch path.
    """
    if getattr(repository, "_pinterest_persistence_contract_installed", False):
        return

    original_create_generation = repository.create_generation
    original_create_image_session = repository.create_image_session
    original_update_last_prompt = repository.update_image_session_last_prompt

    async def private_create_generation(*args: Any, **kwargs: Any):
        contract = active_pinterest_contract()
        if not contract:
            return await original_create_generation(*args, **kwargs)
        current = signature(original_create_generation).bind_partial(*args, **kwargs)
        private_params = _private_input_params(current.arguments.get("input_params"), contract)
        private_args, private_kwargs = _bound_call(
            original_create_generation,
            args,
            kwargs,
            prompt=_DISPLAY_PROMPT,
            input_params=private_params,
        )
        return await original_create_generation(*private_args, **private_kwargs)

    async def private_create_image_session(*args: Any, **kwargs: Any):
        if not active_pinterest_contract():
            return await original_create_image_session(*args, **kwargs)
        private_args, private_kwargs = _bound_call(
            original_create_image_session,
            args,
            kwargs,
            base_prompt=_DISPLAY_PROMPT,
        )
        return await original_create_image_session(*private_args, **private_kwargs)

    async def private_update_last_prompt(*args: Any, **kwargs: Any):
        if not active_pinterest_contract():
            return await original_update_last_prompt(*args, **kwargs)
        private_args, private_kwargs = _bound_call(
            original_update_last_prompt,
            args,
            kwargs,
            last_prompt=_DISPLAY_PROMPT,
        )
        return await original_update_last_prompt(*private_args, **private_kwargs)

    repository.create_generation = private_create_generation
    repository.create_image_session = private_create_image_session
    repository.update_image_session_last_prompt = private_update_last_prompt
    repository._pinterest_persistence_contract_installed = True


def install_pinterest_provider_contract(image_service: Any) -> None:
    if getattr(image_service, "_pinterest_provider_contract_installed", False):
        return
    original_generate = image_service.generate_image

    async def generate_image_with_roles(*args: Any, **kwargs: Any):
        contract = _provider_context.get()
        if not contract:
            return await original_generate(*args, **kwargs)

        mutable_args = list(args)
        current_prompt = str(mutable_args[1] if len(mutable_args) >= 2 else kwargs.get("prompt") or "")
        provider_prompt = pinterest_provider_prompt(
            current_prompt,
            height_cm=contract.get("height_cm"),
            weight_kg=contract.get("weight_kg"),
        )
        if len(mutable_args) >= 2:
            mutable_args[1] = provider_prompt
        else:
            kwargs["prompt"] = provider_prompt
        kwargs["image_url"] = list(contract.get("provider_reference_images") or [])
        return await original_generate(*mutable_args, **kwargs)

    image_service.generate_image = generate_image_with_roles
    image_service._pinterest_provider_contract_installed = True


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


async def _patch_generation_snapshot(
    miniapp_routes: Any,
    *,
    session: Any,
    generation_id: int,
    contract: dict[str, Any],
) -> None:
    generation = await miniapp_routes.repo.get_generation_by_id(session, generation_id)
    if generation is None:
        return
    payload = _json_dict(getattr(generation, "input_params", None))
    payload.update(contract)
    generation.prompt = _DISPLAY_PROMPT
    generation.input_params = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    await session.commit()


def install_pinterest_miniapp_contract(miniapp_routes: Any) -> None:
    if getattr(miniapp_routes, "_pinterest_miniapp_contract_installed", False):
        return
    original_create = miniapp_routes.create_image_generation
    install_pinterest_persistence_contract(miniapp_routes.repo)

    async def create_image_generation_with_pinterest(
        body,
        session=miniapp_routes.Depends(miniapp_routes.get_session),
        user=miniapp_routes.Depends(miniapp_routes.get_miniapp_user),
        surface: str = "miniapp",
    ):
        if body.prompt_id is None:
            return await original_create(body=body, session=session, user=user, surface=surface)

        from core.trends import is_trend_prompt, trend_kind
        from db.prompt_repository import get_prompt_by_id

        prompt_source = await get_prompt_by_id(session, body.prompt_id)
        if (
            not is_trend_prompt(prompt_source)
            or trend_kind(prompt_source) != "image"
            or not is_pinterest_prompt_source(prompt_source)
        ):
            # Ordinary image trends must never inherit Pinterest role semantics.
            return await original_create(body=body, session=session, user=user, surface=surface)

        current_contract = active_pinterest_contract()
        if current_contract:
            scene = str(current_contract.get("scene_reference") or "").strip()
            identity = str(current_contract.get("identity_reference") or "").strip()
            evidence = _unique_urls(current_contract.get("identity_evidence") or [])
            contract = current_contract
        else:
            scene = str(getattr(prompt_source, "preview_url", "") or "").strip()
            user_refs = _unique_urls(getattr(body, "reference_url", None), getattr(body, "reference_urls", None))
            identity = user_refs[0] if user_refs else ""
            evidence = user_refs[1:]
            contract = build_pinterest_contract(
                scene_reference=scene,
                identity_reference=identity,
                identity_evidence=evidence,
                trend_id=int(prompt_source.id),
            )

        if not scene:
            raise HTTPException(status_code=409, detail="Pinterest scene reference is missing")
        if not identity:
            raise HTTPException(status_code=422, detail="Upload an identity reference first")
        if scene == identity:
            raise HTTPException(status_code=422, detail="Scene and identity references must be different")

        caps = miniapp_routes.IMAGE_CAPS.get(body.model, {})
        max_refs = int(caps.get("max_refs", 1) or 1)
        required_refs = 2 + len(evidence)
        if max_refs < required_refs:
            raise HTTPException(
                status_code=422,
                detail="Selected Pinterest model cannot preserve all scene and identity references separately",
            )

        # Generic request handling validates the same number of references. The
        # provider wrapper owns the final provider order: identity -> scene ->
        # additional identity evidence.
        safe_body = body.model_copy(
            update={
                "reference_url": identity,
                "reference_urls": [scene, *evidence],
            }
        )
        with pinterest_provider_context(contract):
            task = await original_create(body=safe_body, session=session, user=user, surface=surface)
        await _patch_generation_snapshot(
            miniapp_routes,
            session=session,
            generation_id=int(task.id),
            contract=contract,
        )
        return task

    miniapp_routes.create_image_generation = create_image_generation_with_pinterest
    miniapp_routes._pinterest_miniapp_contract_installed = True
