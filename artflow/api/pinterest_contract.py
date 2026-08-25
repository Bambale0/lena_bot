from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from fastapi import HTTPException


_PROVIDER_ROLE_PROMPT = """Image 1 is the only USER_IDENTITY_REFERENCE.
Image 2 is the only SCENE_REFERENCE.

Create a new image of the person from Image 1 placed into the scene, pose, outfit, lighting and composition of Image 2.

Do not preserve the person from Image 2.
Do not return Image 1 unchanged.
Do not return Image 2 unchanged.
Do not use extra identity evidence as composition, pose, outfit, or background.
"""

_provider_context: ContextVar[dict[str, Any] | None] = ContextVar("apix_pinterest_provider_context", default=None)


def _unique_urls(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        source = value if isinstance(value, (list, tuple)) else [value]
        for item in source:
            clean = str(item or "").strip()
            if clean and clean not in result:
                result.append(clean)
    return result


def build_pinterest_contract(
    *,
    scene_reference: str,
    identity_reference: str,
    identity_evidence: list[str] | None = None,
    trend_id: int | None = None,
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
    return {
        "flow": "pinterest",
        "source": "trend",
        "trend_id": trend_id,
        "scene_reference": scene,
        "identity_reference": identity,
        "identity_evidence": evidence,
        "reference_images": logical,
        "reference_roles": roles,
        # Provider-safe array is deliberately limited to the two semantic anchors.
        "provider_reference_images": _unique_urls(identity, scene),
        "pinterest_source_url": scene,
    }


def pinterest_provider_prompt(hidden_prompt: str) -> str:
    prompt = str(hidden_prompt or "").strip()
    return f"{_PROVIDER_ROLE_PROMPT}\n\nOriginal scene instructions:\n{prompt}" if prompt else _PROVIDER_ROLE_PROMPT


@contextmanager
def pinterest_provider_context(contract: dict[str, Any] | None) -> Iterator[None]:
    token = _provider_context.set(dict(contract or {}) if contract else None)
    try:
        yield
    finally:
        _provider_context.reset(token)


def install_pinterest_provider_contract(image_service: Any) -> None:
    if getattr(image_service, "_pinterest_provider_contract_installed", False):
        return
    original_generate = image_service.generate_image

    async def generate_image_with_roles(*args: Any, **kwargs: Any):
        contract = _provider_context.get()
        if not contract:
            return await original_generate(*args, **kwargs)

        mutable_args = list(args)
        if len(mutable_args) >= 2:
            mutable_args[1] = pinterest_provider_prompt(str(mutable_args[1] or ""))
        else:
            kwargs["prompt"] = pinterest_provider_prompt(str(kwargs.get("prompt") or ""))
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
    generation.input_params = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    await session.commit()


def install_pinterest_miniapp_contract(miniapp_routes: Any) -> None:
    if getattr(miniapp_routes, "_pinterest_miniapp_contract_installed", False):
        return
    original_create = miniapp_routes.create_image_generation

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
        if not is_trend_prompt(prompt_source) or trend_kind(prompt_source) != "image":
            return await original_create(body=body, session=session, user=user, surface=surface)

        scene = str(getattr(prompt_source, "preview_url", "") or "").strip()
        user_refs = _unique_urls(getattr(body, "reference_url", None), getattr(body, "reference_urls", None))
        identity = user_refs[0] if user_refs else ""
        evidence = user_refs[1:]
        if not scene:
            raise HTTPException(status_code=409, detail="Pinterest scene reference is missing")
        if not identity:
            raise HTTPException(status_code=422, detail="Upload an identity reference first")

        caps = miniapp_routes.IMAGE_CAPS.get(body.model, {})
        max_refs = int(caps.get("max_refs", 1) or 1)
        if max_refs < 2:
            raise HTTPException(status_code=422, detail="Selected trend model cannot preserve scene and identity separately")

        contract = build_pinterest_contract(
            scene_reference=scene,
            identity_reference=identity,
            identity_evidence=evidence,
            trend_id=int(prompt_source.id),
        )
        # Product order remains scene -> identity -> evidence in metadata, while
        # the provider sees identity -> scene for a stable role contract.
        safe_body = body.model_copy(
            update={
                "reference_url": identity,
                "reference_urls": [scene],
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
