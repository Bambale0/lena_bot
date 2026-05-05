#!/usr/bin/env python3
"""
Patch Artflow KIE image reference/remix/aspect-ratio integration.

Run from artflow/:
    python fix_kie_refs_ratio_patch.py
    python -m compileall api bot db main.py

Then review:
    git diff

This patch targets the current project layout and is intentionally conservative:
- fixes ratio callback parsing bug for values like 4:3 / 9:16
- fixes KIE image reference fields per used model
- prevents empty reference fields
- adds remix routing for text-only models -> edit/i2i models
"""
from __future__ import annotations

from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")


# -----------------------------------------------------------------------------
# 1) api/image_service.py — model specs + correct reference fields
# -----------------------------------------------------------------------------
image_service_path = "api/image_service.py"
s = read(image_service_path)

if "class ImageModelSpec" not in s:
    marker = '''@dataclass
class ImageResult:
    is_async: bool = False
    task_id: str | None = None
    url: str | None = None
    image_bytes: bytes | None = None
    mime_type: str = "image/png"
'''
    insert = marker + '''

@dataclass(frozen=True)
class ImageModelSpec:
    supports_reference: bool
    reference_field: str | None = None
    reference_type: str = "single"  # "single" | "list"
    aspect_ratio_field: str | None = None
    quality_field: str | None = None
    count_field: str | None = None


IMAGE_MODEL_SPECS: dict[ImageModel, ImageModelSpec] = {
    ImageModel.SEEDREAM_45: ImageModelSpec(
        supports_reference=False,
        aspect_ratio_field="aspect_ratio",
        quality_field="quality",
    ),
    ImageModel.SEEDREAM_45_EDIT: ImageModelSpec(
        supports_reference=True,
        reference_field="image_url",
        reference_type="single",
        aspect_ratio_field="aspect_ratio",
        quality_field="quality",
    ),
    ImageModel.GROK_T2I: ImageModelSpec(
        supports_reference=False,
        aspect_ratio_field="aspect_ratio",
    ),
    ImageModel.GROK_I2I: ImageModelSpec(
        supports_reference=True,
        reference_field="image_urls",
        reference_type="list",
        aspect_ratio_field="aspect_ratio",
    ),
    ImageModel.WAN_27_PRO: ImageModelSpec(
        supports_reference=True,
        reference_field="input_urls",
        reference_type="list",
        count_field="n",
    ),
    ImageModel.NANO_BANANA: ImageModelSpec(
        supports_reference=False,
        aspect_ratio_field="image_size",
    ),
    ImageModel.NANO_BANANA_2: ImageModelSpec(
        supports_reference=False,
        aspect_ratio_field="image_size",
    ),
    ImageModel.NANO_BANANA_PRO: ImageModelSpec(
        supports_reference=True,
        reference_field="image_input",
        reference_type="list",
        aspect_ratio_field="aspect_ratio",
    ),
}


def supports_image_reference(model: ImageModel | str) -> bool:
    try:
        model_enum = model if isinstance(model, ImageModel) else ImageModel(str(model))
    except ValueError:
        return False
    return IMAGE_MODEL_SPECS.get(model_enum, ImageModelSpec(False)).supports_reference


def _apply_reference(inp: dict[str, Any], spec: ImageModelSpec, image_url: str | None) -> None:
    if not image_url or not spec.supports_reference or not spec.reference_field:
        return
    if spec.reference_type == "list":
        inp[spec.reference_field] = [image_url]
    else:
        inp[spec.reference_field] = image_url
'''
    if marker not in s:
        raise SystemExit("Cannot find ImageResult marker in api/image_service.py")
    s = s.replace(marker, insert)

pattern = re.compile(r"def _build_input\(.*?\n\s*raise ValueError\(f\"Unknown image model: \{model\}\"\)\n", re.S)
replacement = '''def _build_input(
    model: ImageModel,
    prompt: str,
    image_url: str | None,
    aspect_ratio: str | None,
    n: int,
    quality: str,
) -> dict[str, Any]:
    m = model.value
    ratio = aspect_ratio or "1:1"
    spec = IMAGE_MODEL_SPECS.get(model, ImageModelSpec(False))

    if image_url and not spec.supports_reference:
        logger.warning("Ignoring reference for model without image input support: %s", m)
        image_url = None

    if model == ImageModel.SEEDREAM_45:
        return {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "quality": quality,
            "nsfw_checker": False,
        }

    if model == ImageModel.SEEDREAM_45_EDIT:
        inp = {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "quality": quality,
        }
        _apply_reference(inp, spec, image_url)
        return inp

    if model == ImageModel.GROK_T2I:
        return {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "nsfw_checker": False,
        }

    if model == ImageModel.GROK_I2I:
        inp = {
            "prompt": prompt,
            "aspect_ratio": ratio,
        }
        _apply_reference(inp, spec, image_url)
        return inp

    if model == ImageModel.WAN_27_PRO:
        inp: dict[str, Any] = {
            "prompt": prompt,
            "resolution": "2K",
            "n": max(1, min(4, n)),
            "watermark": False,
        }
        if image_url:
            _apply_reference(inp, spec, image_url)
        else:
            inp["aspect_ratio"] = ratio
        return inp

    if model == ImageModel.NANO_BANANA:
        return {
            "prompt": prompt,
            "image_size": ratio,
            "output_format": "png",
        }

    if model == ImageModel.NANO_BANANA_2:
        return {
            "prompt": prompt,
            "image_size": ratio,
            "resolution": "2K",
            "output_format": "jpg",
        }

    if model == ImageModel.NANO_BANANA_PRO:
        inp = {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "resolution": "2K",
            "output_format": "jpg",
        }
        _apply_reference(inp, spec, image_url)
        return inp

    raise ValueError(f"Unknown image model: {model}")
'''
if not pattern.search(s):
    raise SystemExit("Cannot find _build_input function in api/image_service.py")
s = pattern.sub(replacement, s)

if "KIE image request model=%s has_reference=%s" not in s:
    s = s.replace(
        "    inp = _build_input(model, prompt, image_url, aspect_ratio, n, quality)\n"
        "    resp = await kieai_client.create_task",
        "    inp = _build_input(model, prompt, image_url, aspect_ratio, n, quality)\n"
        "    logger.info(\n"
        "        \"KIE image request model=%s has_reference=%s aspect_ratio=%s n=%s quality=%s\",\n"
        "        model.value, bool(image_url), aspect_ratio, n, quality,\n"
        "    )\n"
        "    resp = await kieai_client.create_task",
    )

write(image_service_path, s)


# -----------------------------------------------------------------------------
# 2) bot/handlers/image_gen.py — ratio parsing + remix routing
# -----------------------------------------------------------------------------
image_gen_path = "bot/handlers/image_gen.py"
s = read(image_gen_path)

s = s.replace('ratio = call.data.split(":")[1]  # type: ignore[union-attr]', 'ratio = call.data.split(":", 1)[1]  # type: ignore[union-attr]')
s = s.replace('ratio = call.data.split(":")[1]', 'ratio = call.data.split(":", 1)[1]')

if "supports_image_reference" not in s:
    s = s.replace(
        "from api.image_service import ImageModel\n",
        "from api.image_service import ImageModel, supports_image_reference\n",
    )

if "IMAGE_REMIX_MODEL_MAP" not in s:
    marker = 'router = Router(name="image_gen")\n'
    insert = '''router = Router(name="image_gen")

IMAGE_REMIX_MODEL_MAP: dict[str, str] = {
    "seedream/4.5-text-to-image": "seedream/4.5-edit",
    "grok-imagine/text-to-image": "grok-imagine/image-to-image",
    "google/nano-banana": "nano-banana-pro",
    "nano-banana-2": "nano-banana-pro",
}
'''
    if marker not in s:
        raise SystemExit("Cannot find router marker in image_gen.py")
    s = s.replace(marker, insert)

pattern = re.compile(r"def _supports_img2img\(model_key: str\) -> bool:\n(?:    .*\n){1,4}")
if pattern.search(s):
    s = pattern.sub(
        "def _supports_img2img(model_key: str) -> bool:\n"
        "    return supports_image_reference(model_key)\n\n",
        s,
        count=1,
    )

if "effective_model_key = image_session.model" not in s:
    s = s.replace(
        "    model_cost = await repo.get_model_cost(session, image_session.model)\n"
        "    credits = model_cost.credits if model_cost else 1\n\n"
        "    model = _safe_image_model(image_session.model)\n",
        "    effective_model_key = image_session.model\n"
        "    if action_type == ImageGenerationAction.remix and reference_url:\n"
        "        effective_model_key = IMAGE_REMIX_MODEL_MAP.get(image_session.model, image_session.model)\n\n"
        "    if reference_url and not _supports_img2img(effective_model_key):\n"
        "        await source_message.answer(\n"
        "            \"⚠️ Эта модель не умеет редактировать по изображению. \"\n"
        "            \"Выбери модель с поддержкой референса или начни новую серию.\",\n"
        "            reply_markup=image_session_kb(parent_generation_id),\n"
        "        )\n"
        "        return False\n\n"
        "    model_cost = await repo.get_model_cost(session, effective_model_key)\n"
        "    credits = model_cost.credits if model_cost else 1\n\n"
        "    model = _safe_image_model(effective_model_key)\n",
    )
    s = s.replace(
        "        image_session.model,\n"
        "        GenerationType.image,\n",
        "        effective_model_key,\n"
        "        GenerationType.image,\n",
        1,
    )

write(image_gen_path, s)


# -----------------------------------------------------------------------------
# 3) bot/handlers/video_gen.py — ratio parsing for video callbacks
# -----------------------------------------------------------------------------
video_gen_path = "bot/handlers/video_gen.py"
if Path(video_gen_path).exists():
    s = read(video_gen_path)
    s = s.replace('ratio = call.data.split(":")[1]  # type: ignore[union-attr]', 'ratio = call.data.split(":", 1)[1]  # type: ignore[union-attr]')
    s = s.replace('ratio = call.data.split(":")[1]', 'ratio = call.data.split(":", 1)[1]')
    write(video_gen_path, s)

print("Patch applied: KIE image specs, reference fields, remix routing, ratio parsing.")
print("Next: python -m compileall api bot db main.py")
