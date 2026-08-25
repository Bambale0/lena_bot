from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from pathlib import Path
from typing import Any, Iterator

PINTEREST_PROMPT_MARKER = "PINTEREST_RECREATION_CONTRACT_V3"
PINTEREST_FLOW = "pinterest"
PINTEREST_SERVICE_ID = "pinterest"
PINTEREST_REFERENCE_CONTRACT = "pinterest_scene_identity"
DISPLAY_PROMPT = "Pinterest AI: сохранить внешность с ваших фото в выбранной сцене Pinterest."
_SAFE_PROVIDER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

_PROVIDER_ROLE_PROMPT = f"""{PINTEREST_PROMPT_MARKER}
PINTEREST SERVICE SCENE IDENTITY CONTRACT

You are generating a NEW photorealistic image.

Image 1 is the only SCENE_REFERENCE. Use Image 1 only for the scene, exact pose, body placement, outfit concept, composition, lighting, camera angle, framing, expression, background and photographic mood.
Image 2 is the PRIMARY USER_IDENTITY_REFERENCE. Use Image 2 only for the person's face, identity, apparent age, skin tone, facial geometry, hairline, distinctive facial features, natural body build, hair length and hair color.
Images 3 and later, when present, are USER_IDENTITY_EVIDENCE for the SAME person as Image 2. Use them only to reinforce the user's identity, face, hair and natural proportions from additional angles. They never define scene, pose, outfit, background, framing or lighting.

Create a new photo of the person from Image 2 placed naturally into the scene and composition of Image 1. When identity-evidence images are present, use them together with Image 2 to keep that same person recognizable and consistent.

HARD NEGATIVE RULES
- Do not preserve the person from Image 1.
- Do not copy or reuse the person from Image 1.
- Do not copy the face, hair identity, ethnicity, apparent age, or skin tone from Image 1.
- Do not return Image 1 unchanged.
- Do not return Image 2 unchanged.
- Do not use Image 2 or identity-evidence images as the composition, outfit, background, camera, or pose.
- Do not average, blend, or morph identities. Identity from Image 2, supported by identity-evidence images, always wins.
- Do not output a collage, comparison, screenshot, source image, UI, text, watermark, or split-screen.

PARTIAL TRANSFER GUARD
- Do not take ONLY hair color, hair length, or body cues from the user while keeping the SCENE_REFERENCE person's face.
- Do not copy person from scene reference.
- Do not replace identity. Keep the user's facial structure unchanged.

QUALITY RULES
- The result must look like a real new photograph, not an edit preview.
- Keep face, hands, and body anatomy natural.
- Keep the user recognizable from Image 2 and any identity-evidence images.
"""

_provider_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "apix_pinterest_service_provider_context",
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


def build_pinterest_service_contract(
    *,
    scene_reference: str,
    identity_reference: str,
    identity_evidence: list[str] | None = None,
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
    return {
        "flow": PINTEREST_FLOW,
        "source": "service",
        "service_id": PINTEREST_SERVICE_ID,
        "reference_contract": PINTEREST_REFERENCE_CONTRACT,
        "scene_reference": scene,
        "identity_reference": identity,
        "identity_evidence": evidence,
        "reference_images": logical,
        "source_reference_images": logical,
        "reference_roles": roles,
        # Provider contract from the reference implementation: SCENE -> USER ->
        # optional additional USER identity evidence. Never reorder identity first.
        "provider_reference_images": logical,
        "provider_reference_roles": roles,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "confirmed": bool(confirmed),
        "display_prompt": DISPLAY_PROMPT,
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
    suffix = f"\n\nPRIVATE SERVICE INSTRUCTIONS\n{original}" if original else ""
    return (
        f"{_PROVIDER_ROLE_PROMPT}\n"
        f"- User measurements: {measurement_text}. Use them only for realistic body scale; never render measurement text into the image."
        f"{suffix}"
    )


@contextmanager
def pinterest_service_provider_context(contract: dict[str, Any] | None) -> Iterator[None]:
    token = _provider_context.set(dict(contract or {}) if contract else None)
    try:
        yield
    finally:
        _provider_context.reset(token)


def active_pinterest_service_contract() -> dict[str, Any] | None:
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


def _bound_call(
    func: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    **updates: Any,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    bound = signature(func).bind_partial(*args, **kwargs)
    for key, value in updates.items():
        bound.arguments[key] = value
    return bound.args, bound.kwargs


def _register_heif_support() -> None:
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener(thumbnails=False)
    except Exception as exc:
        raise RuntimeError("HEIC/HEIF decoder is unavailable") from exc


def _provider_safe_reference_urls(image_service: Any, urls: list[str]) -> list[str]:
    """Normalize local mobile uploads to provider-supported raster formats."""
    _register_heif_support()
    safe: list[str] = []
    for original in urls:
        normalized = image_service.ensure_provider_safe_png_url(original) or original
        path = image_service.local_upload_path_from_url(normalized)
        if path is not None and path.exists() and Path(path).suffix.lower() not in _SAFE_PROVIDER_EXTENSIONS:
            raise RuntimeError(
                f"Unsupported Pinterest reference format: {Path(path).suffix.lower() or 'unknown'}"
            )
        safe.append(normalized)
    return safe


def install_pinterest_persistence_contract(repository: Any) -> None:
    """Redact the private service recipe before the first persistence commit."""
    if getattr(repository, "_pinterest_service_persistence_contract_installed", False):
        return

    original_create_generation = repository.create_generation
    original_create_image_session = repository.create_image_session
    original_update_last_prompt = repository.update_image_session_last_prompt

    @wraps(original_create_generation)
    async def private_create_generation(*args: Any, **kwargs: Any):
        contract = active_pinterest_service_contract()
        if not contract:
            return await original_create_generation(*args, **kwargs)
        current = signature(original_create_generation).bind_partial(*args, **kwargs)
        private_params = _private_input_params(current.arguments.get("input_params"), contract)
        private_args, private_kwargs = _bound_call(
            original_create_generation,
            args,
            kwargs,
            prompt=DISPLAY_PROMPT,
            input_params=private_params,
        )
        return await original_create_generation(*private_args, **private_kwargs)

    @wraps(original_create_image_session)
    async def private_create_image_session(*args: Any, **kwargs: Any):
        if not active_pinterest_service_contract():
            return await original_create_image_session(*args, **kwargs)
        private_args, private_kwargs = _bound_call(
            original_create_image_session,
            args,
            kwargs,
            base_prompt=DISPLAY_PROMPT,
        )
        return await original_create_image_session(*private_args, **private_kwargs)

    @wraps(original_update_last_prompt)
    async def private_update_last_prompt(*args: Any, **kwargs: Any):
        if not active_pinterest_service_contract():
            return await original_update_last_prompt(*args, **kwargs)
        private_args, private_kwargs = _bound_call(
            original_update_last_prompt,
            args,
            kwargs,
            last_prompt=DISPLAY_PROMPT,
        )
        return await original_update_last_prompt(*private_args, **private_kwargs)

    repository.create_generation = private_create_generation
    repository.create_image_session = private_create_image_session
    repository.update_image_session_last_prompt = private_update_last_prompt
    repository._pinterest_service_persistence_contract_installed = True


def install_pinterest_provider_contract(image_service: Any) -> None:
    if getattr(image_service, "_pinterest_service_provider_contract_installed", False):
        return
    original_generate = image_service.generate_image

    @wraps(original_generate)
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

        # Canonicalize by semantic roles instead of trusting caller-provided
        # ordering. This also keeps historical Repeat flows safe.
        scene = str(contract.get("scene_reference") or "").strip()
        identity = str(contract.get("identity_reference") or "").strip()
        evidence = _unique_urls(contract.get("identity_evidence") or [])
        canonical = _unique_urls(scene, identity, evidence)
        provider_refs = canonical or list(contract.get("provider_reference_images") or [])
        kwargs["image_url"] = _provider_safe_reference_urls(image_service, provider_refs)
        return await original_generate(*mutable_args, **kwargs)

    image_service.generate_image = generate_image_with_roles
    image_service._pinterest_service_provider_contract_installed = True
