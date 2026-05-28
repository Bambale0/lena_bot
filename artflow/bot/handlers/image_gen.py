from __future__ import annotations

import hashlib
import html
import json
import logging
from pathlib import Path
from urllib.parse import urlencode

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service
from api.image_service import ImageModel, normalize_quality_for_aspect_ratio
from api.kie_model_specs import IMAGE_SPECS, KieReferenceType
from api.photo_prompt_service import generate_prompt_from_photo
from api.public_files import mirror_telegram_file
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    IMAGE_CAPS,
    IMAGE_SCENARIOS,
    NANA_BANANO_DEFAULT_MODEL,
    NANA_BANANO_MODEL_CHOICES,
    image_aspect_ratio_kb,
    image_count_kb,
    image_dynamic_settings_kb,
    image_mode_kb,
    image_nana_banano_kb,
    image_quality_kb,
    image_session_kb,
    image_session_settings_kb,
    image_style_edit_kb,
    multi_ref_kb,
    public_prompt_text,
    reference_upload_kb,
)
from bot.states import ImageGenFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db import repository as repo
from db.models import GenerationType, ImageGenerationAction, ImageSession, User

logger = logging.getLogger(__name__)
router = Router(name="image_gen")

MAX_CONCURRENT_GENERATIONS = 6

STYLE_EDIT_HINTS: dict[str, tuple[str, str]] = {
    "clothes": ("одежду", "Напиши, на какую одежду заменить. Например: белый костюм, шелковое платье, oversize худи."),
    "haircut": ("прическу", "Напиши, какую прическу сделать. Например: каре, высокий хвост, мягкие локоны."),
    "hair_color": ("цвет волос", "Напиши новый цвет волос. Например: медный блонд, холодный брюнет, пастельно-розовый."),
    "nails": ("ногти", "Напиши, какие ногти нужны. Например: нюдовый маникюр, красный френч, хром."),
}


def _style_edit_prompt(edit_kind: str | None, user_detail: str) -> str:
    detail = user_detail.strip()
    if not edit_kind or not detail:
        return detail

    prompts = {
        "clothes": (
            "Edit the reference image. Change ONLY the main person's clothing to: {detail}. "
            "Keep the face, hair, body, pose, background, vehicles, and all other objects unchanged. "
            "Do not recolor anything except the clothing."
        ),
        "haircut": (
            "Edit the reference image. Change ONLY the main person's hairstyle or haircut to: {detail}. "
            "Keep the face, hair color, clothing, body, pose, background, vehicles, and all other objects unchanged."
        ),
        "hair_color": (
            "Edit the reference image. Change ONLY the main person's hair color to: {detail}. "
            "Keep the hairstyle, face, skin, clothing, body, pose, background, cars, vehicles, and all other objects unchanged. "
            "Do not recolor anything except the hair."
        ),
        "nails": (
            "Edit the reference image. Change ONLY the main person's nails or manicure to: {detail}. "
            "Keep the hands shape, face, hair, clothing, body, pose, background, vehicles, and all other objects unchanged."
        ),
    }
    template = prompts.get(edit_kind)
    return template.format(detail=detail) if template else detail


def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{query}"


def _direct_image_result_urls(result: image_service.ImageResult) -> list[str]:
    result_urls = list(result.result_urls or [])
    if result.url and result.url not in result_urls:
        result_urls.insert(0, result.url)
    return [url for url in result_urls if url]


def _normalize_image_count(model_key: str, count: object) -> int:
    allowed = [int(item) for item in IMAGE_CAPS.get(model_key, {}).get("counts", [1]) if int(item) > 0]
    if not allowed:
        allowed = [1]
    try:
        value = int(count or 1)
    except (TypeError, ValueError):
        value = 1
    if value in allowed:
        return value
    return 1 if 1 in allowed else allowed[0]


async def _telegram_file_url(bot: Bot, file_id: str | None) -> str | None:
    return await mirror_telegram_file(bot, file_id)


def get_image_model_label(model_key: str) -> str:
    """Возвращает человекочитаемое имя модели."""
    from bot.keyboards.models import IMAGE_MODEL_DESC
    return IMAGE_MODEL_DESC.get(model_key, model_key)


def _supports_img2img(model_key: str) -> bool:
    caps = IMAGE_CAPS.get(model_key, {})
    spec = IMAGE_SPECS.get(model_key)
    return "image" in caps.get("modes", []) or bool(spec and spec.remix_model)


def _requires_reference_image(model_key: str) -> bool:
    spec = IMAGE_SPECS.get(model_key)
    if spec:
        return spec.reference_type != KieReferenceType.NONE and "text" not in spec.supported_modes

    modes = IMAGE_CAPS.get(model_key, {}).get("modes", ["text"])
    return "image" in modes and "text" not in modes


def _safe_image_model(model_key: str) -> ImageModel | None:
    try:
        return ImageModel(model_key)
    except ValueError:
        logger.warning("Unknown image model in session flow: %s", model_key)
        return None


def _ratio_options_for_mode(model_key: str, mode: str | None) -> list[str]:
    caps = IMAGE_CAPS.get(model_key, {})
    ratio_modes = caps.get("aspect_ratio_modes", caps.get("modes", ["text"]))
    if mode and mode not in ratio_modes:
        return []
    return caps.get("aspect_ratios", [])


def _should_select_aspect_ratio(model_key: str, mode: str | None) -> bool:
    return bool(_ratio_options_for_mode(model_key, mode))


def _quality_options(model_key: str) -> list[tuple[str, str]]:
    return IMAGE_CAPS.get(model_key, {}).get(
        "quality_options",
        [("basic", "🔷 2K"), ("high", "💎 4K")],
    )


def _default_image_quality(model_key: str) -> str:
    if IMAGE_CAPS.get(model_key, {}).get("has_quality"):
        return _quality_options(model_key)[0][0]
    return "basic"


def _quality_label(model_key: str, quality: str | None) -> str:
    clean_labels = {
        value: label.replace("🔷 ", "").replace("💎 ", "").replace(" (стандарт)", "").replace(" (высокое)", "")
        for value, label in _quality_options(model_key)
    }
    return clean_labels.get(quality or "", quality or "по умолчанию")


def _normalize_session_quality(model_key: str, aspect_ratio: str | None, quality: str | None) -> str:
    normalized = normalize_quality_for_aspect_ratio(model_key, aspect_ratio, quality)
    return str(normalized or quality or "basic")


def _detect_image_ext(raw: bytes) -> str:
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"RIFF") and b"WEBP" in raw[:16]:
        return ".webp"
    return ".jpg"


async def _telegram_photo_public_url(bot: Bot, file_id: str) -> str:
    """Download Telegram photo and save as public image file for KIE."""
    upload_dir = Path(settings.STATIC_UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file = await bot.get_file(file_id)
    downloaded = await bot.download_file(file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)

    ext = _detect_image_ext(raw)
    digest = hashlib.sha256(raw).hexdigest()[:32]
    filename = f"{digest}{ext}"
    out = upload_dir / filename
    out.write_bytes(raw)

    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.STATIC_UPLOAD_URL_PATH.rstrip('/')}/{filename}"



async def _resolve_image_session(
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    gen_id: int | None = None,
) -> tuple[ImageSession | None, int | None]:
    data = await state.get_data()
    image_session_id = data.get("image_session_id")

    if gen_id:
        gen = await repo.get_generation_by_id(session, gen_id)
        if gen and gen.user_id == db_user.id and gen.image_session_id:
            image_session = await repo.get_image_session(session, gen.image_session_id, db_user.id)
            if image_session:
                return image_session, gen.id

    if image_session_id:
        image_session = await repo.get_image_session(session, image_session_id, db_user.id)
        if image_session:
            return image_session, gen_id

    image_session = await repo.get_active_image_session(session, db_user.id)
    return image_session, gen_id


def _stored_reference_file_ids(image_session: ImageSession) -> list[str]:
    raw_reference_file_ids = getattr(image_session, "reference_file_ids", None)
    if not raw_reference_file_ids:
        return []
    try:
        parsed = json.loads(raw_reference_file_ids)
    except (TypeError, ValueError):
        return []
    return [item for item in parsed if isinstance(item, str) and item]


def _state_reference_file_ids(data: dict) -> list[str]:
    ref_file_ids = [item for item in list(data.get("ref_file_ids", []) or []) if item]
    image_file_id = data.get("image_file_id")
    if image_file_id and image_file_id not in ref_file_ids:
        ref_file_ids.insert(0, image_file_id)
    return ref_file_ids


def _state_refs_belong_to_session(data: dict, image_session: ImageSession) -> bool:
    state_session_id = data.get("image_session_id")
    session_id = getattr(image_session, "id", None)
    if not state_session_id or not session_id:
        return True
    try:
        return int(state_session_id) == int(session_id)
    except (TypeError, ValueError):
        return False


def _active_reference_file_ids(image_session: ImageSession, data: dict) -> list[str]:
    refs: list[str] = []
    for file_id in _stored_reference_file_ids(image_session):
        if file_id not in refs:
            refs.append(file_id)
    reference_file_id = getattr(image_session, "reference_file_id", None)
    if reference_file_id and reference_file_id not in refs:
        refs.append(reference_file_id)
    if _state_refs_belong_to_session(data, image_session):
        for file_id in _state_reference_file_ids(data):
            if file_id not in refs:
                refs.append(file_id)
    return refs


def _state_reference_url(data: dict) -> str | None:
    for key in ("remix_reference_url", "carryover_reference_url", "reference_url"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _state_has_reference(data: dict) -> bool:
    return bool(_state_reference_file_ids(data) or _state_reference_url(data))


def _session_has_stored_reference(image_session: ImageSession) -> bool:
    return bool(
        _stored_reference_file_ids(image_session)
        or getattr(image_session, "reference_file_id", None)
        or getattr(image_session, "reference_url", None)
    )


async def _external_source_feed_id(
    *,
    session: AsyncSession,
    db_user: User,
    source_feed_gen_id: int | None,
) -> int | None:
    if not source_feed_gen_id:
        return None
    source = await repo.get_generation_by_id(session, source_feed_gen_id)
    if source and getattr(source, "user_id", None) == getattr(db_user, "id", None):
        return None
    return source_feed_gen_id


async def _source_feed_id_from_parent(
    *,
    session: AsyncSession,
    data: dict,
    parent_gen,
    db_user: User,
) -> int | None:
    if parent_gen and getattr(parent_gen, "user_id", None) == getattr(db_user, "id", None):
        source_feed_gen_id = getattr(parent_gen, "source_feed_gen_id", None)
    else:
        source_feed_gen_id = data.get("source_feed_gen_id")
    return await _external_source_feed_id(
        session=session,
        db_user=db_user,
        source_feed_gen_id=source_feed_gen_id,
    )


async def _source_feed_id_for_generation_or_state(
    *,
    session: AsyncSession,
    db_user: User,
    generation_id: int | None,
    data: dict,
) -> int | None:
    if not data.get("source_feed_gen_id") or not generation_id:
        return await _external_source_feed_id(
            session=session,
            db_user=db_user,
            source_feed_gen_id=data.get("source_feed_gen_id"),
        )
    parent_gen = await repo.get_generation_by_id(session, generation_id)
    return await _source_feed_id_from_parent(
        session=session,
        data=data,
        parent_gen=parent_gen,
        db_user=db_user,
    )


async def _generation_prompt_actions_allowed(
    *,
    session: AsyncSession,
    gen,
    db_user: User,
) -> bool:
    if not gen or getattr(gen, "user_id", None) != getattr(db_user, "id", None):
        return False
    source_feed_gen_id = getattr(gen, "source_feed_gen_id", None)
    if not source_feed_gen_id:
        return True
    source = await repo.get_generation_by_id(session, source_feed_gen_id)
    return bool(source and getattr(source, "user_id", None) == getattr(db_user, "id", None))


async def _session_reference_url(
    bot: Bot,
    image_session: ImageSession,
    *,
    prefer_last_result: bool = False,
    state: FSMContext | None = None,
) -> str | list[str] | None:
    """
    Returns reference URL(s) for the current session.
    For remix: uses last_result_url.
    For multi-ref models: returns list of resolved URLs from ref_file_ids in FSM state.
    For single-ref: returns single URL string.
    """
    if not _supports_img2img(image_session.model):
        return None

    last_result_url = getattr(image_session, "last_result_url", None)
    if prefer_last_result and last_result_url:
        return last_result_url

    # Check FSM state for collected multi-ref file IDs that belong to this session.
    if state:
        data = await state.get_data()
        ref_file_ids: list[str] = list(data.get("ref_file_ids", [])) if _state_refs_belong_to_session(data, image_session) else []
        if len(ref_file_ids) > 1:
            urls = []
            for fid in ref_file_ids:
                url = await _telegram_file_url(bot, fid)
                if url:
                    urls.append(url)
            return urls if urls else None
        if len(ref_file_ids) == 1:
            return await _telegram_file_url(bot, ref_file_ids[0])

    stored_file_ids = _stored_reference_file_ids(image_session)
    if len(stored_file_ids) > 1:
        urls = []
        for fid in stored_file_ids:
            url = await _telegram_file_url(bot, fid)
            if url:
                urls.append(url)
        return urls if urls else None
    if len(stored_file_ids) == 1:
        return await _telegram_file_url(bot, stored_file_ids[0])

    reference_file_id = getattr(image_session, "reference_file_id", None)
    if reference_file_id:
        return await _telegram_file_url(bot, reference_file_id)

    reference_url = getattr(image_session, "reference_url", None)
    if reference_url:
        return reference_url

    return None


def _session_settings_text(image_session: ImageSession) -> str:
    caps = IMAGE_CAPS.get(image_session.model, {})
    ratios = _ratio_options_for_mode(image_session.model, image_session.mode)
    quality_label = _quality_label(image_session.model, image_session.quality) if caps.get("has_quality") else "фиксированное"
    count_label = str(image_session.count) if len(caps.get("counts", [1])) > 1 else "фиксированное"
    ratio_label = image_session.aspect_ratio or ("по умолчанию" if ratios else "не используется")
    mode_label = "Референс → изображение" if image_session.mode == "image" else "Текст → изображение"
    return (
        "⚙️ <b>Настройки активной серии</b>\n\n"
        f"Модель: <b>{get_image_model_label(image_session.model)}</b>\n"
        f"Режим: <b>{mode_label}</b>\n"
        f"Формат кадра: <b>{ratio_label}</b>\n"
        f"Детализация: <b>{quality_label}</b>\n"
        f"Вариантов за запуск: <b>{count_label}</b>\n\n"
        "Показываю только те настройки, которые реально работают у этой модели."
    )


def _active_image_session_text(image_session: ImageSession) -> str:
    caps = IMAGE_CAPS.get(image_session.model, {})
    ratios = _ratio_options_for_mode(image_session.model, image_session.mode)
    quality_label = _quality_label(image_session.model, image_session.quality) if caps.get("has_quality") else "фиксированное"
    count_label = str(image_session.count) if len(caps.get("counts", [1])) > 1 else "фиксированное"
    ratio_label = image_session.aspect_ratio or ("по умолчанию" if ratios else "не используется")
    return (
        "🎨 <b>Активная серия изображений</b>\n\n"
        f"Модель: <b>{get_image_model_label(image_session.model)}</b>\n"
        f"Формат кадра: <b>{ratio_label}</b>\n"
        f"Детализация: <b>{quality_label}</b>\n"
        f"Вариантов за запуск: <b>{count_label}</b>\n\n"
        "Просто отправь новый prompt или фото.\n"
        "Все настройки уже сохранены."
    )


async def _sync_state_with_image_session(state: FSMContext, image_session: ImageSession) -> None:
    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        model_key=image_session.model,
        aspect_ratio=image_session.aspect_ratio,
        count=image_session.count,
        quality=image_session.quality,
        mode=image_session.mode,
        image_mode=image_session.mode,
        image_file_id=image_session.reference_file_id,
        ref_file_ids=_stored_reference_file_ids(image_session),
        remix_mode=False,
        remix_parent_generation_id=None,
        remix_reference_url=None,
    )


async def _show_active_image_session_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    image_session: ImageSession,
) -> None:
    await _sync_state_with_image_session(state, image_session)
    screen = await render_screen(
        screen="image_active",
        session=session,
        db_user=db_user,
        extra={"image_session": image_session},
    )
    await message.answer(screen.text, reply_markup=screen.reply_markup)


async def _show_active_image_session_callback(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    image_session: ImageSession,
) -> None:
    await _sync_state_with_image_session(state, image_session)
    screen = await render_screen(
        screen="image_active",
        session=session,
        db_user=db_user,
        extra={"image_session": image_session},
    )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        screen.text,
        reply_markup=screen.reply_markup,
    )


async def _ensure_active_image_session_from_state(
    *,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> ImageSession:
    data = await state.get_data()
    existing = await repo.get_active_image_session(session, db_user.id)
    if existing:
        try:
            state_session_id = int(data.get("image_session_id") or 0)
        except (TypeError, ValueError):
            state_session_id = 0
        if state_session_id == getattr(existing, "id", None) and existing.model == data["model_key"]:
            return existing

    aspect_ratio = data.get("aspect_ratio")
    mode = data.get("image_mode") or data.get("mode", "text")
    quality = _normalize_session_quality(
        data["model_key"],
        aspect_ratio,
        data.get("quality", "basic"),
    )
    count = _normalize_image_count(data["model_key"], data.get("count", 1))

    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=data["model_key"],
        mode=mode,
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=count,
        base_prompt=None,
        reference_file_id=data.get("image_file_id"),
        reference_file_ids=_state_reference_file_ids(data) if mode == "image" else None,
        reference_url=_state_reference_url(data) if mode == "image" else None,
    )
    await state.update_data(image_session_id=image_session.id, count=count, image_count=count)
    return image_session


async def _promote_reference_mode_if_needed(
    *,
    session: AsyncSession,
    state: FSMContext,
    image_session: ImageSession,
    data: dict,
    current_mode: str | None,
    reference_url: str | list[str] | None,
) -> str | None:
    if current_mode == "image" or not reference_url or not _supports_img2img(image_session.model):
        return current_mode
    if not (_state_has_reference(data) or _session_has_stored_reference(image_session)):
        return current_mode

    image_session.mode = "image"
    await session.commit()
    await state.update_data(mode="image", image_mode="image")
    return "image"


def _session_ratio_choices_kb(image_session: ImageSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ratios = _ratio_options_for_mode(image_session.model, image_session.mode)
    buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if ratio == image_session.aspect_ratio else ''}{ratio}",
            callback_data=f"img_sset_ratio:set:{image_session.id}:{ratio}",
        )
        for ratio in ratios
    ]
    for i in range(0, len(buttons), 3):
        builder.row(*buttons[i:i + 3])
    builder.row(InlineKeyboardButton(text="← К настройкам", callback_data=f"img_sset:back:{image_session.id}"))
    return builder.as_markup()


def _session_quality_choices_kb(image_session: ImageSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for quality, label in _quality_options(image_session.model):
        builder.row(
            InlineKeyboardButton(
                text=f"{'✅ ' if image_session.quality == quality else ''}{label}",
                callback_data=f"img_sset_quality:set:{image_session.id}:{quality}",
            )
        )
    builder.row(InlineKeyboardButton(text="← К настройкам", callback_data=f"img_sset:back:{image_session.id}"))
    return builder.as_markup()


def _session_count_choices_kb(image_session: ImageSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    counts = IMAGE_CAPS.get(image_session.model, {}).get("counts", [1])
    for count in counts:
        builder.row(
            InlineKeyboardButton(
                text=f"{'✅ ' if image_session.count == count else ''}{count} шт",
                callback_data=f"img_sset_count:set:{image_session.id}:{count}",
            )
        )
    builder.row(InlineKeyboardButton(text="← К настройкам", callback_data=f"img_sset:back:{image_session.id}"))
    return builder.as_markup()


async def _launch_session_generation(
    *,
    source_message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    image_session: ImageSession,
    prompt: str,
    action_type: ImageGenerationAction,
    reference_url: str | list[str] | None,
    parent_generation_id: int | None,
    source_feed_gen_id: int | None = None,
    launching_text: str,
    queued_text: str,
) -> bool:
    source_feed_gen_id = await _external_source_feed_id(
        session=session,
        db_user=db_user,
        source_feed_gen_id=source_feed_gen_id,
    )
    normalized_count = _normalize_image_count(image_session.model, image_session.count)
    if normalized_count != image_session.count:
        image_session.count = normalized_count
        await session.commit()
        await state.update_data(count=normalized_count, image_count=normalized_count)

    normalized_quality = _normalize_session_quality(
        image_session.model,
        image_session.aspect_ratio,
        image_session.quality,
    )
    if normalized_quality != image_session.quality:
        image_session.quality = normalized_quality
        await session.commit()
        await state.update_data(quality=normalized_quality)

    model_cost = await repo.resolve_image_model_cost(
        session,
        image_session.model,
        quality=normalized_quality,
    )
    credits = model_cost.credits if model_cost else 1

    model = _safe_image_model(image_session.model)
    if model is None:
        await source_message.answer(
            "❌ Модель серии больше не поддерживается.",
            reply_markup=main_menu_kb(),
        )
        return False

    if _requires_reference_image(image_session.model) and not reference_url:
        await source_message.answer(
            "❌ Эта модель требует референс-изображение. Отправь фото.",
            reply_markup=image_session_kb(parent_generation_id, allow_publish=not bool(source_feed_gen_id)),
        )
        return False

    active_count = await repo.count_user_active_generations(session, db_user.id)
    if active_count >= MAX_CONCURRENT_GENERATIONS:
        await source_message.answer(
            f"⏳ У тебя уже {active_count} генераций в очереди. "
            f"Подожди, пока завершатся текущие.",
            reply_markup=main_menu_kb(),
        )
        return False

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await source_message.answer("❌ Недостаточно 💋.", reply_markup=main_menu_kb())
        return False

    gen = await repo.create_generation(
        session,
        db_user.id,
        image_session.model,
        GenerationType.image,
        prompt,
        credits,
        image_session_id=image_session.id,
        parent_generation_id=parent_generation_id,
        action_type=action_type,
        source_feed_gen_id=source_feed_gen_id,
    )
    await repo.update_image_session_last_prompt(session, image_session.id, prompt)
    image_session.last_prompt = prompt

    status_msg = await source_message.answer(launching_text)

    try:
        result = await image_service.generate_image(
            model,
            prompt,
            image_url=reference_url,
            aspect_ratio=image_session.aspect_ratio,
            n=normalized_count,
            quality=normalized_quality,
            callback_url=_kie_callback_url(),
        )
    except Exception as e:
        logger.error("Session image generation error: %s", e)
        if await repo.fail_generation(session, gen.id, str(e)):
            await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            "❌ Ошибка генерации. 💋 возвращены.",
            reply_markup=image_session_kb(parent_generation_id, allow_publish=not bool(source_feed_gen_id)),
        )
        return False

    publish_actions_allowed = not bool(source_feed_gen_id)
    prompt_actions_allowed = publish_actions_allowed and action_type != ImageGenerationAction.repeat
    prompt_for_menu = prompt if prompt_actions_allowed else None
    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await _sync_state_with_image_session(state, image_session)
    await state.update_data(credits=credits, source_feed_gen_id=source_feed_gen_id)

    if not getattr(result, "is_async", True):
        result_urls = _direct_image_result_urls(result)
        if not result_urls:
            err = "CometAPI image fallback returned no result URL"
            if await repo.fail_generation(session, gen.id, err):
                await repo.add_credits(session, db_user.id, credits)
            await status_msg.edit_text(
                "❌ Ошибка генерации. 💋 возвращены.",
                reply_markup=image_session_kb(parent_generation_id, allow_publish=publish_actions_allowed),
            )
            return False

        await repo.finish_generation(session, gen.id, result_urls[0], result_urls=result_urls)
        await repo.update_image_session_last_result(session, image_session.id, result_urls[0], gen.id)
        image_session.last_result_url = result_urls[0]
        image_session.last_generation_id = gen.id
        try:
            await status_msg.delete()
        except Exception:
            pass

        caption = (
            "✅ <b>Готово!</b>\n\n"
            "🎨 <b>Серия активна.</b>\n"
            "Теперь просто отправляй новый текст или фото — настройки сохранятся."
        )
        for idx, url in enumerate(result_urls):
            try:
                await source_message.answer_photo(
                    URLInputFile(url, filename=f"image_{gen.id}_{idx + 1}.jpg"),
                    caption=caption if idx == 0 else None,
                )
            except Exception:
                try:
                    await source_message.answer_document(
                        URLInputFile(url, filename=f"image_{gen.id}_{idx + 1}.jpg"),
                        caption=caption if idx == 0 else None,
                    )
                except Exception:
                    logger.warning("Failed to send direct image result user=%s gen=%s idx=%s", db_user.tg_id, gen.id, idx)

        for idx, url in enumerate(result_urls):
            try:
                await source_message.answer_document(
                    URLInputFile(url, filename=f"source_{gen.id}_{idx + 1}.png"),
                    caption="📎 <b>Исходник файлом</b>" if idx == 0 else None,
                )
            except Exception:
                logger.warning("Failed to send direct image source document user=%s gen=%s idx=%s", db_user.tg_id, gen.id, idx)

        await source_message.answer(
            "Что делаем дальше?",
            reply_markup=image_session_kb(
                gen.id,
                prompt=prompt_for_menu,
                allow_publish=publish_actions_allowed,
                allow_copy_prompt=prompt_actions_allowed,
            ),
        )
        return True

    await status_msg.edit_text(
        queued_text,
        reply_markup=image_session_kb(
            gen.id,
            prompt=prompt_for_menu,
            allow_publish=publish_actions_allowed,
            allow_copy_prompt=prompt_actions_allowed,
        ),
    )
    return True


# ── Model select ──────────────────────────────────────────────────────────────

_NANA_BANANO_MODEL_LABELS = {
    ImageModel.NANO_BANANA_PRO.value: "Nano Banana Pro",
    ImageModel.NANO_BANANA_2.value: "Nano Banana 2",
}


def _nana_banano_ref_count(data: dict) -> int:
    return len(_state_reference_file_ids(data))


def _image_model_key(model_key: str | ImageModel) -> str:
    return model_key.value if isinstance(model_key, ImageModel) else str(model_key)


def _nana_banano_text(model_key: str, refs_count: int) -> str:
    model_label = _NANA_BANANO_MODEL_LABELS.get(model_key, model_key)
    max_refs = int(IMAGE_CAPS.get(model_key, {}).get("max_refs", 0) or 0)
    refs_label = f"{refs_count}/{max_refs}" if max_refs else str(refs_count)
    return (
        "🍌 <b>nana banano</b>\n\n"
        f"Модель: <b>{model_label}</b>\n"
        f"Референсы: <b>{refs_label}</b>\n\n"
        "👇 <b>Как запустить</b>\n"
        "1️⃣ <b>Отправь фото-референс</b> сюда же.\n"
        "2️⃣ <b>Затем отправь промпт текстом</b> — сразу запущу генерацию."
    )


async def _show_nana_banano_flow(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    model_key: str = NANA_BANANO_DEFAULT_MODEL,
    *,
    preserve_refs: bool = True,
) -> bool:
    model_key = _image_model_key(model_key)
    allowed_models = set(NANA_BANANO_MODEL_CHOICES)
    if model_key not in allowed_models:
        await call.answer("Модель недоступна", show_alert=True)
        return False

    default_quality = _default_image_quality(model_key)
    model_cost = await repo.resolve_image_model_cost(
        session,
        model_key,
        quality=default_quality,
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return False

    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋! Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return False

    data = await state.get_data()
    refs_count = _nana_banano_ref_count(data) if preserve_refs else 0
    mode = "image" if refs_count or _state_reference_url(data) else "text"

    updates = dict(
        nana_banano_flow=True,
        image_session_id=None,
        model_key=model_key,
        image_model=model_key,
        mode=mode,
        image_mode=mode,
        credits=model_cost.credits,
        aspect_ratio=None,
        image_aspect_ratio=None,
        count=1,
        image_count=1,
        quality=default_quality,
        image_quality=default_quality,
        remix_mode=False,
        remix_parent_generation_id=None,
        source_feed_gen_id=None,
    )
    if not preserve_refs:
        updates.update(
            image_file_id=None,
            ref_file_ids=[],
            remix_reference_url=None,
        )
    await state.update_data(**updates)
    await state.set_state(ImageGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _nana_banano_text(model_key, refs_count),
        reply_markup=image_nana_banano_kb(model_key, refs_count),
    )
    return True


async def _open_image_model_select(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    await state.set_state(ImageGenFSM.model_select)
    screen = await render_screen(screen="image_advanced", session=session, db_user=db_user)
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]


async def _start_image_model_flow(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    model_key: str,
    forced_mode: str | None = None,
) -> None:
    default_quality = _default_image_quality(model_key)

    model_cost = await repo.resolve_image_model_cost(
        session,
        model_key,
        quality=default_quality,
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return

    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋! Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])

    if forced_mode and forced_mode in modes:
        default_mode = forced_mode
    else:
        default_mode = "text" if "text" in modes else modes[0]

    await state.update_data(
        image_session_id=None,
        model_key=model_key,
        image_model=model_key,
        mode=default_mode,
        image_mode=default_mode,
        credits=model_cost.credits,
        aspect_ratio=None,
        image_aspect_ratio=None,
        count=1,
        image_count=1,
        image_file_id=None,
        quality=default_quality,
        image_quality=default_quality,
        remix_mode=False,
        remix_parent_generation_id=None,
        source_feed_gen_id=None,
    )

    text = (
        f"🎛 <b>{model_cost.display_name}</b>\n\n"
        "Я покажу только настройки, которые реально поддерживает эта модель.\n"
        "Выбери параметры или нажми «Продолжить»."
    )

    await safe_edit_message(
        call.message,
        text,
        reply_markup=image_dynamic_settings_kb(model_key, default_mode),
    )
    await state.set_state(ImageGenFSM.model_select)
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:image")
async def cb_image_menu(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session = await repo.get_active_image_session(session, db_user.id)
    if image_session:
        model_cost = await repo.resolve_image_model_cost(
            session,
            image_session.model,
            quality=image_session.quality,
        )
        await _sync_state_with_image_session(state, image_session)
        await state.update_data(credits=model_cost.credits if model_cost else 1)
        screen = await render_screen(
            screen="image_active",
            session=session,
            db_user=db_user,
            extra={"image_session": image_session},
        )
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            screen.text,
            reply_markup=screen.reply_markup,
        )
        await safe_answer_callback(call)
        return

    screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
    await state.clear()
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        screen.text,
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "img_menu:advanced")
async def cb_image_advanced_menu(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    await _open_image_model_select(call, session, state, db_user)
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("img_scn:"))
async def cb_image_scenario(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    scenario_key = call.data.split(":")[-1]  # type: ignore[union-attr]
    scenario = IMAGE_SCENARIOS.get(scenario_key)
    if not scenario:
        await call.answer("Сценарий недоступен", show_alert=True)
        return
    if scenario_key == "fast":
        if await _show_nana_banano_flow(
            call=call,
            session=session,
            state=state,
            db_user=db_user,
            model_key=scenario["model"],
            preserve_refs=False,
        ):
            await safe_answer_callback(call)
        return
    await _start_image_model_flow(
        call=call,
        session=session,
        state=state,
        db_user=db_user,
        model_key=scenario["model"],
        forced_mode=scenario["mode"],
    )


@router.callback_query(ImageGenFSM.prompt_input, F.data.startswith("img_nb:model:"))
async def cb_nana_banano_model(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    if await _show_nana_banano_flow(call, state, session, db_user, model_key):
        await call.answer(f"Модель: {_NANA_BANANO_MODEL_LABELS.get(model_key, model_key)}")


@router.callback_query(ImageGenFSM.prompt_input, F.data == "img_nb:refs")
async def cb_nana_banano_refs_hint(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    model_key = _image_model_key(data.get("model_key") or NANA_BANANO_DEFAULT_MODEL)
    refs_count = _nana_banano_ref_count(data)
    max_refs = int(IMAGE_CAPS.get(model_key, {}).get("max_refs", 0) or 0)
    refs_label = f"{refs_count}/{max_refs}" if max_refs else str(refs_count)
    await call.answer(
        f"Отправь фото сюда сообщением до промпта. Сейчас: {refs_label}.",
        show_alert=True,
    )


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:mode:"))
async def cb_image_dynamic_mode(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    await state.update_data(model_key=model_key, image_model=model_key)
    await safe_edit_message(
        call.message,
        "🔀 <b>Выбери режим модели</b>",
        reply_markup=image_mode_kb(model_key),
    )
    await state.set_state(ImageGenFSM.mode_select)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:ratio:"))
async def cb_image_dynamic_ratio(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    await state.update_data(model_key=model_key, image_model=model_key)
    await safe_edit_message(
        call.message,
        "📐 <b>Выбери формат</b>",
        reply_markup=image_aspect_ratio_kb(model_key),
    )
    await state.set_state(ImageGenFSM.aspect_ratio_select)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:quality:"))
async def cb_image_dynamic_quality(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    await state.update_data(model_key=model_key, image_model=model_key)
    await safe_edit_message(
        call.message,
        "💎 <b>Выбери качество</b>",
        reply_markup=image_quality_kb(model_key),
    )
    await state.set_state(ImageGenFSM.count_select)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:count:"))
async def cb_image_dynamic_count(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    await state.update_data(model_key=model_key, image_model=model_key)
    await safe_edit_message(
        call.message,
        "🔢 <b>Выбери количество</b>",
        reply_markup=image_count_kb(model_key),
    )
    await state.set_state(ImageGenFSM.count_select)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:enhance:"))
async def cb_image_dynamic_enhance(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    data = await state.get_data()
    mode = data.get("image_mode") or data.get("mode")
    current = bool(data.get("image_prompt_enhance"))
    await state.update_data(
        model_key=model_key,
        image_model=model_key,
        image_prompt_enhance=not current,
    )
    await safe_edit_message(
        call.message,
        "✨ <b>Улучшение промпта</b>\n\n"
        f"Статус: <b>{'включено' if not current else 'выключено'}</b>\n\n"
        "Выбери параметры или нажми «Продолжить».",
        reply_markup=image_dynamic_settings_kb(model_key, mode),
    )
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:reference:"))
async def cb_image_dynamic_reference(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    await state.update_data(model_key=model_key, image_model=model_key)
    await safe_edit_message(
        call.message,
        "🖼 <b>Загрузи фото-референс</b>\n\n"
        "Отправь фото, которое будет использоваться как основа для генерации.",
        reply_markup=back_to_menu_kb(),
    )
    await state.set_state(ImageGenFSM.image_upload)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_dyn:continue:"))
async def cb_image_dynamic_continue(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":", 2)[2]
    data = await state.get_data()
    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    mode = data.get("image_mode") or data.get("mode") or ("text" if "text" in modes else modes[0])

    await state.update_data(
        model_key=model_key,
        image_model=model_key,
        mode=mode,
        image_mode=mode,
    )

    if mode == "image":
        if _state_has_reference(data):
            await safe_edit_message(
                call.message,
                "✍️ <b>Напиши промпт для изображения</b>\n\n"
                "Референс уже сохранён из предыдущего результата.",
                reply_markup=back_to_menu_kb(),
            )
            await state.set_state(ImageGenFSM.prompt_input)
        else:
            await safe_edit_message(
                call.message,
                "🖼 <b>Загрузи фото-референс</b>\n\n"
                "После фото отправь текст, что нужно изменить или какой стиль сделать.",
                reply_markup=back_to_menu_kb(),
            )
            await state.set_state(ImageGenFSM.image_upload)
    else:
        await safe_edit_message(
            call.message,
            "✍️ <b>Напиши промпт для изображения</b>\n\n"
            "Опиши, что нужно создать. Можно обычным языком.",
            reply_markup=back_to_menu_kb(),
        )
        await state.set_state(ImageGenFSM.prompt_input)

    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("img_model:"))
async def cb_image_model(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    model_key = call.data.removeprefix("img_model:")
    current_state = await state.get_state()

    if current_state == ImageGenFSM.photo_to_prompt_model.state:
        model_cost = await repo.get_model_cost(session, model_key)
        display_name = model_cost.display_name if model_cost else model_key

        await state.set_state(ImageGenFSM.photo_to_prompt)
        await state.update_data(p2p_model_key=model_key, p2p_model_name=display_name)

        data = await state.get_data()
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            _p2p_prompt_text(ref_file_id=data.get("p2p_ref_file_id"), model_name=display_name),
            reply_markup=_p2p_result_kb(
                ref_file_id=data.get("p2p_ref_file_id"),
                model_key=model_key,
                model_name=display_name,
            ),
        )
        await call.answer(f"Модель: {display_name}")
        return

    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    data = await state.get_data()
    carryover_mode = data.get("carryover_mode")
    if carryover_mode in modes:
        default_mode = carryover_mode
    else:
        default_mode = "text" if "text" in modes else modes[0]

    updates = {
        "image_session_id": None,
        "model_key": model_key,
        "image_model": model_key,
        "mode": default_mode,
        "image_mode": default_mode,
        "aspect_ratio": None,
        "image_aspect_ratio": None,
        "count": 1,
        "image_count": 1,
        "quality": _default_image_quality(model_key),
        "image_quality": _default_image_quality(model_key),
        "source_feed_gen_id": None,
    }
    if data.get("carryover_image_file_id"):
        updates["image_file_id"] = data.get("carryover_image_file_id")
    if data.get("carryover_ref_file_ids"):
        updates["ref_file_ids"] = list(data.get("carryover_ref_file_ids") or [])
    if data.get("carryover_reference_url"):
        updates["remix_reference_url"] = data.get("carryover_reference_url")

    await state.update_data(**updates)

    model_title = get_image_model_label(model_key)
    text = (
        f"🎛 <b>{model_title}</b>\n\n"
        "Покажу только те настройки, которые реально работают у этой модели.\n"
        "Выбери параметры или нажми «Продолжить»."
    )

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        text,
        reply_markup=image_dynamic_settings_kb(model_key, default_mode),
    )
    await state.set_state(ImageGenFSM.model_select)
    await call.answer()


@router.callback_query(ImageGenFSM.mode_select, F.data.startswith("img_mode:"))
async def cb_image_mode(call: CallbackQuery, state: FSMContext) -> None:
    _, mode, model_key = call.data.split(":", 2)

    await state.update_data(
        model_key=model_key,
        image_model=model_key,
        mode=mode,
        image_mode=mode,
    )

    model_title = get_image_model_label(model_key)
    mode_label = "Референс → изображение" if mode == "image" else "Текст → изображение"

    text = (
        f"🎛 <b>{model_title}</b>\n\n"
        f"Режим: <b>{mode_label}</b>\n\n"
        "Теперь доступны только подходящие настройки для этого режима."
    )

    await call.message.edit_text(
        text,
        reply_markup=image_dynamic_settings_kb(model_key, mode),
    )
    await state.set_state(ImageGenFSM.model_select)
    await call.answer()


@router.callback_query(ImageGenFSM.aspect_ratio_select, F.data.startswith("img_ratio:"))
async def cb_image_ratio(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    ratio = call.data.removeprefix("img_ratio:")  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    model_key = data["model_key"]
    caps = IMAGE_CAPS.get(model_key, {})
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · {ratio}\n\n💎 <b>Выбери детализацию</b>\n"
            "2K обычно быстрее, 4K даёт больше деталей.",
            reply_markup=image_quality_kb(model_key),
        )
    elif len(caps.get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · {ratio}\n\n🔢 <b>Сколько вариантов создать?</b>",
            reply_markup=image_count_kb(model_key),
        )
    else:
        image_session = await _ensure_active_image_session_from_state(session=session, state=state, db_user=db_user)
        await _show_active_image_session_callback(call, state, session, db_user, image_session)
    await call.answer(ratio)


@router.callback_query(ImageGenFSM.aspect_ratio_select, F.data.startswith("img_back:mode:"))
async def cb_image_back_to_mode(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":")[-1]  # type: ignore[union-attr]
    data = await state.get_data()
    mode = data.get("mode", "text")
    caps = IMAGE_CAPS.get(model_key, {})
    if mode == "image":
        await state.set_state(ImageGenFSM.image_upload)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            "🖼️ Загрузи референс-изображение:",
            reply_markup=reference_upload_kb("menu:image", allow_skip="text" in caps.get("modes", [])),
        )
    else:
        await state.set_state(ImageGenFSM.mode_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            "Выбери режим:",
            reply_markup=image_mode_kb(model_key),
        )
    await call.answer()


# ── Quality / Count ───────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.count_select, F.data.startswith("img_quality:"))
async def cb_image_quality(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    quality = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(quality=quality)
    data = await state.get_data()
    model_key = data["model_key"]
    ratio = data.get("aspect_ratio")
    normalized_quality = _normalize_session_quality(model_key, ratio, quality)
    model_cost = await repo.resolve_image_model_cost(session, model_key, quality=normalized_quality)
    display_name = model_cost.display_name if model_cost else model_key
    q_label = _quality_label(model_key, normalized_quality)
    await state.update_data(credits=model_cost.credits if model_cost else data.get("credits"))
    if normalized_quality != quality:
        await state.update_data(quality=normalized_quality, image_quality=normalized_quality)
    summary = " · ".join(part for part in (display_name, ratio, q_label) if part)

    if len(IMAGE_CAPS.get(model_key, {}).get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{summary}</b>\n\n🔢 Количество изображений:",
            reply_markup=image_count_kb(model_key),
        )
    else:
        image_session = await _ensure_active_image_session_from_state(session=session, state=state, db_user=db_user)
        await _show_active_image_session_callback(call, state, session, db_user, image_session)
    if normalized_quality != quality:
        await call.answer("Для формата 1:1 доступно только 2K")
        return
    await call.answer(q_label)


@router.callback_query(ImageGenFSM.count_select, F.data.startswith("img_count:"))
async def cb_image_count(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    count = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(count=count)

    image_session = await _ensure_active_image_session_from_state(session=session, state=state, db_user=db_user)
    await _show_active_image_session_callback(call, state, session, db_user, image_session)
    await call.answer(f"{count} шт")


@router.callback_query(ImageGenFSM.count_select, F.data == "img_back:ratio")
async def cb_count_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    mode = data.get("mode", "text")
    if _should_select_aspect_ratio(model_key, mode):
        await state.set_state(ImageGenFSM.aspect_ratio_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b>\n\n📐 Соотношение сторон:",
            reply_markup=image_aspect_ratio_kb(model_key),
        )
    else:
        caps = IMAGE_CAPS.get(model_key, {})
        if mode == "image":
            await state.set_state(ImageGenFSM.image_upload)
            await safe_edit_message(
                call.message,  # type: ignore[arg-type]
                "🖼️ Загрузи референс-изображение:",
                reply_markup=reference_upload_kb("menu:image", allow_skip="text" in caps.get("modes", [])),
            )
        else:
            await state.set_state(ImageGenFSM.mode_select)
            await safe_edit_message(
                call.message,  # type: ignore[arg-type]
                f"✅ <b>{display_name}</b>\n\nВыбери режим:",
                reply_markup=image_mode_kb(model_key),
            )
    await call.answer()


# ── Image upload (img2img референс) ───────────────────────────────────────────

@router.message(ImageGenFSM.image_upload, F.photo)
async def handle_reference_upload(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id
    data = await state.get_data()
    model_key = data["model_key"]

    # Collect into multi-ref list
    existing: list[str] = list(data.get("ref_file_ids", []))
    caps = IMAGE_CAPS.get(model_key, {})
    max_refs: int = caps.get("max_refs", 1)

    if file_id not in existing:
        existing.append(file_id)
    await state.update_data(image_file_id=existing[0], ref_file_ids=existing)

    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    # If model supports multiple refs and we haven't hit the max, ask for more
    if max_refs > 1:
        can_add_more = len(existing) < max_refs
        await message.answer(
            f"✅ Фото {len(existing)}/{max_refs} загружено!"
            + (f"\nМожно добавить ещё (до {max_refs} фото)" if can_add_more else "\nДостигнут максимум."),
            reply_markup=multi_ref_kb(len(existing), max_refs),
        )
        return

    # Single-ref flow (unchanged)
    await state.update_data(image_file_id=file_id)
    await _after_ref_upload(message, state, session, db_user, model_key, display_name, caps)


async def _after_ref_upload(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    model_key: str,
    display_name: str,
    caps: dict,
) -> None:
    data = await state.get_data()
    if _should_select_aspect_ratio(model_key, data.get("mode", "image")) and not data.get("aspect_ratio"):
        await state.set_state(ImageGenFSM.aspect_ratio_select)
        await message.answer(
            f"✅ Референс загружен!\n\n📐 <b>Выбери формат кадра</b> · {display_name}\n"
            "Квадрат, вертикаль или горизонталь.",
            reply_markup=image_aspect_ratio_kb(model_key),
        )
    elif caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await message.answer(
            f"✅ Референс загружен!\n\n💎 <b>Выбери детализацию</b> · {display_name}\n"
            "2K обычно быстрее, 4K даёт больше деталей.",
            reply_markup=image_quality_kb(model_key),
        )
    elif len(caps.get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await message.answer(
            f"✅ Референс загружен!\n\n🔢 <b>Сколько вариантов создать?</b> · {display_name}",
            reply_markup=image_count_kb(model_key),
        )
    else:
        image_session = await _ensure_active_image_session_from_state(session=session, state=state, db_user=db_user)
        await _show_active_image_session_message(message, state, session, db_user, image_session)


@router.callback_query(ImageGenFSM.image_upload, F.data == "ref:add_more")
async def cb_ref_add_more(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer("Отправь следующее фото 📸")


@router.callback_query(ImageGenFSM.image_upload, F.data == "ref:done_multi")
async def cb_ref_done_multi(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    caps = IMAGE_CAPS.get(model_key, {})
    await call.answer()
    await _after_ref_upload(call.message, state, session, db_user, model_key, display_name, caps)  # type: ignore[arg-type]


@router.callback_query(ImageGenFSM.image_upload, F.data == "ref:skip")
async def cb_image_reference_skip(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    if "text" not in modes:
        await call.answer("Для этой модели референс обязателен", show_alert=True)
        return

    await state.update_data(mode="text", image_mode="text", image_file_id=None, ref_file_ids=[])
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    data = await state.get_data()
    carryover_mode = data.get("carryover_mode")
    if carryover_mode in modes:
        default_mode = carryover_mode
    else:
        default_mode = "text" if "text" in modes else modes[0]

    updates = {
        "model_key": model_key,
        "image_model": model_key,
        "mode": default_mode,
        "image_mode": default_mode,
    }
    if data.get("carryover_image_file_id"):
        updates["image_file_id"] = data.get("carryover_image_file_id")
    if data.get("carryover_ref_file_ids"):
        updates["ref_file_ids"] = list(data.get("carryover_ref_file_ids") or [])
    if data.get("carryover_reference_url"):
        updates["remix_reference_url"] = data.get("carryover_reference_url")

    await state.update_data(**updates)

    text = (
        f"🎛 <b>{display_name}</b>\n\n"
        "Я покажу только настройки, которые реально поддерживает эта модель.\n"
        "Выбери параметры или нажми «Продолжить»."
    )

    await call.message.edit_text(
        text,
        reply_markup=image_dynamic_settings_kb(model_key, default_mode),
    )
    await state.set_state(ImageGenFSM.model_select)
    await call.answer()
    await call.answer()


# ── First prompt starts a session ─────────────────────────────────────────────

@router.message(ImageGenFSM.prompt_input, F.photo)
async def handle_prompt_reference_upload(
    message: Message,
    state: FSMContext,
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id
    data = await state.get_data()
    model_key = _image_model_key(data.get("model_key") or NANA_BANANO_DEFAULT_MODEL)

    if not _supports_img2img(model_key):
        await message.answer(
            "Эта модель не принимает фото-референсы. Выбери модель с поддержкой референсов или отправь текстовый промпт.",
            reply_markup=image_nana_banano_kb(model_key, _nana_banano_ref_count(data))
            if data.get("nana_banano_flow")
            else back_to_menu_kb(),
        )
        return

    caps = IMAGE_CAPS.get(model_key, {})
    max_refs = int(caps.get("max_refs", 1) or 1)
    existing = _state_reference_file_ids(data)

    if file_id not in existing:
        if len(existing) >= max_refs:
            await message.answer(
                f"У этой модели максимум {max_refs} референсов. Отправь промпт текстом.",
                reply_markup=image_nana_banano_kb(model_key, len(existing))
                if data.get("nana_banano_flow")
                else back_to_menu_kb(),
            )
            return
        existing.append(file_id)

    await state.update_data(
        image_file_id=existing[0],
        ref_file_ids=existing,
        mode="image",
        image_mode="image",
    )

    reply_markup = (
        image_nana_banano_kb(model_key, len(existing))
        if data.get("nana_banano_flow")
        else back_to_menu_kb()
    )
    await message.answer(
        f"✅ Референс {len(existing)}/{max_refs} добавлен.\n\n"
        "👇 <b>Следующий шаг</b>\n"
        "<b>Отправь промпт текстом.</b> Можно сначала добавить ещё фото.",
        reply_markup=reply_markup,
    )


@router.message(ImageGenFSM.prompt_input, F.text)
async def handle_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    prompt = message.text.strip()  # type: ignore[union-attr]
    image_session = await _ensure_active_image_session_from_state(session=session, state=state, db_user=db_user)

    reference_url = await _session_reference_url(bot, image_session, prefer_last_result=False, state=state)
    data = await state.get_data()
    current_mode = data.get("image_mode") or data.get("mode") or getattr(image_session, "mode", None)
    current_mode = await _promote_reference_mode_if_needed(
        session=session,
        state=state,
        image_session=image_session,
        data=data,
        current_mode=current_mode,
        reference_url=reference_url,
    )

    if current_mode != "image" or not _supports_img2img(image_session.model):
        reference_url = None

    if current_mode == "image" and not reference_url:
        await message.answer(
            "🖼 Для выбранной модели нужен фото-референс.\n\n"
            "Отправь фото, а потом напиши, что нужно изменить.",
            reply_markup=back_to_menu_kb(),
        )
        await state.set_state(ImageGenFSM.image_upload)
        return

    await _launch_session_generation(
        source_message=message,
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt,
        action_type=ImageGenerationAction.initial,
        reference_url=reference_url,
        parent_generation_id=None,
        launching_text=f"⏳ <b>Запускаю генерацию...</b>\n<b>{get_image_model_label(image_session.model)}</b>",
        queued_text="⏳ <b>Задача запущена.</b> Пришлю результат, когда генерация будет готова.",
    )


# ── Active image session ──────────────────────────────────────────────────────

@router.message(ImageGenFSM.session_active, F.text)
async def handle_session_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    image_session, _ = await _resolve_image_session(session, db_user, state)

    if not image_session:
        await message.answer("Серия не найдена. Начни новую генерацию.", reply_markup=main_menu_kb())
        await state.clear()
        return

    prompt = message.text.strip()
    is_remix = bool(data.get("remix_mode"))
    style_edit_kind = data.get("style_edit_kind") if is_remix else None
    prompt_for_generation = _style_edit_prompt(style_edit_kind, prompt)
    parent_id = data.get("remix_parent_generation_id") or image_session.last_generation_id
    source_feed_gen_id = (
        await _source_feed_id_for_generation_or_state(
            session=session,
            db_user=db_user,
            generation_id=parent_id,
            data=data,
        )
        if is_remix
        else None
    )

    reference_url = data.get("remix_reference_url") if is_remix else None
    if not reference_url:
        reference_url = await _session_reference_url(
            bot,
            image_session,
            prefer_last_result=is_remix,
            state=state,
        )

    current_mode = data.get("image_mode") or data.get("mode") or getattr(image_session, "mode", None)
    current_mode = await _promote_reference_mode_if_needed(
        session=session,
        state=state,
        image_session=image_session,
        data=data,
        current_mode=current_mode,
        reference_url=reference_url,
    )

    if current_mode != "image" or not _supports_img2img(image_session.model):
        reference_url = None

    if current_mode == "image" and not reference_url:
        await message.answer(
            "🖼 Для выбранной модели нужен фото-референс.\n\n"
            "Отправь фото, а потом напиши, что нужно изменить.",
            reply_markup=back_to_menu_kb(),
        )
        await state.set_state(ImageGenFSM.image_upload)
        return

    launched = await _launch_session_generation(
        source_message=message,
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt_for_generation,
        action_type=ImageGenerationAction.remix if is_remix else ImageGenerationAction.initial,
        reference_url=reference_url,
        parent_generation_id=parent_id,
        source_feed_gen_id=source_feed_gen_id,
        launching_text=f"⏳ <b>Генерирую в активной серии...</b>\n<b>{get_image_model_label(image_session.model)}</b>",
        queued_text="⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
    )
    if launched and style_edit_kind:
        await state.update_data(style_edit_kind=None)


@router.message(ImageGenFSM.session_active, F.photo)
async def handle_session_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)

    if not image_session:
        await message.answer("Серия не найдена. Начни новую генерацию.", reply_markup=main_menu_kb())
        await state.clear()
        return

    if not _supports_img2img(image_session.model):
        await message.answer(
            "Эта модель не принимает фото-референсы. Выбери модель с поддержкой референсов.",
            reply_markup=main_menu_kb(),
        )
        return

    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id
    data = await state.get_data()
    max_refs = int(IMAGE_CAPS.get(image_session.model, {}).get("max_refs", 1) or 1)
    existing = _active_reference_file_ids(image_session, data)
    if max_refs > 1:
        if file_id not in existing:
            if len(existing) >= max_refs:
                await message.answer(
                    f"У этой модели максимум {max_refs} референсов. Напиши промпт или начни новую серию.",
                    reply_markup=image_session_kb(
                        image_session.last_generation_id,
                        allow_publish=not bool(data.get("source_feed_gen_id")),
                    ),
                )
                return
            existing.append(file_id)
        reference_file_ids = existing
    else:
        reference_file_ids = [file_id]

    await repo.update_image_session_references(session, image_session.id, reference_file_ids, mode="image")
    image_session.mode = "image"
    image_session.reference_file_id = reference_file_ids[0] if reference_file_ids else None
    image_session.reference_file_ids = json.dumps(reference_file_ids, ensure_ascii=True) if reference_file_ids else None
    image_session.reference_url = None
    await state.update_data(
        image_file_id=reference_file_ids[0] if reference_file_ids else None,
        ref_file_ids=reference_file_ids,
        image_session_id=image_session.id,
        mode="image",
        image_mode="image",
    )
    label = (
        f"✅ Референс {len(reference_file_ids)}/{max_refs} добавлен для активной серии."
        if max_refs > 1
        else "✅ Новый референс сохранён для активной серии."
    )
    source_feed_gen_id = await _source_feed_id_for_generation_or_state(
        session=session,
        db_user=db_user,
        generation_id=image_session.last_generation_id,
        data=data,
    )
    if source_feed_gen_id != data.get("source_feed_gen_id"):
        await state.update_data(source_feed_gen_id=source_feed_gen_id)

    await message.answer(
        f"{label} Теперь напиши, что изменить.",
        reply_markup=image_session_kb(
            image_session.last_generation_id,
            allow_publish=not bool(source_feed_gen_id),
        ),
    )


# ── Session callbacks ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "img_remix")
@router.callback_query(F.data.startswith("img_session:remix:"))
async def cb_image_session_remix(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    gen_id = None
    if call.data and call.data.startswith("img_session:remix:"):
        gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
        gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    data = await state.get_data()
    if not _supports_img2img(image_session.model):
        await call.answer("Эта модель не поддерживает ремикс по изображению", show_alert=True)
        return

    source_parent_id = parent_id or image_session.last_generation_id
    parent_gen = None
    remix_reference_url = getattr(image_session, "last_result_url", None) or getattr(image_session, "reference_url", None)
    if source_parent_id:
        parent_gen = await repo.get_generation_by_id(session, source_parent_id)
        if parent_gen and parent_gen.user_id == db_user.id and parent_gen.result_url:
            remix_reference_url = parent_gen.result_url
    source_feed_gen_id = await _source_feed_id_from_parent(
        session=session,
        data=data,
        parent_gen=parent_gen,
        db_user=db_user,
    )

    if not remix_reference_url:
        await call.answer("Не нашёл изображение для ремикса", show_alert=True)
        return

    image_session.mode = "image"
    image_session.reference_url = remix_reference_url
    image_session.reference_file_id = None
    image_session.reference_file_ids = None
    await session.commit()

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        mode="image",
        image_mode="image",
        image_file_id=None,
        ref_file_ids=[],
        remix_mode=True,
        remix_parent_generation_id=parent_id or image_session.last_generation_id,
        remix_reference_url=remix_reference_url,
        style_edit_kind=None,
        source_feed_gen_id=source_feed_gen_id,
    )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✨ <b>Режим ремикса</b>\n\n"
        "✍️ Напиши, что изменить.\n"
        "Можно также отправить новое фото, чтобы заменить референс.",
        reply_markup=image_session_kb(
            image_session.last_generation_id,
            allow_publish=not bool(source_feed_gen_id),
        ),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_session:style:"))
async def cb_image_session_style_menu(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
    gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None
    if not gen_id:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return
    if not _supports_img2img(image_session.model):
        await call.answer("Эта модель не поддерживает редактирование по изображению", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "💅 <b>Что поменять в образе?</b>\n\n"
        "Выбери направление, а потом напиши конкретные детали.",
        reply_markup=image_style_edit_kb(parent_id or gen_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_style:"))
async def cb_image_style_choice(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    parts = call.data.split(":") if call.data else []
    if len(parts) < 3:
        await call.answer("Не понял, что менять", show_alert=True)
        return

    edit_kind = parts[1]
    gen_id_raw = parts[2]
    gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None
    label, hint = STYLE_EDIT_HINTS.get(edit_kind, STYLE_EDIT_HINTS["clothes"])

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return
    data = await state.get_data()
    if not _supports_img2img(image_session.model):
        await call.answer("Эта модель не поддерживает редактирование по изображению", show_alert=True)
        return

    source_parent_id = parent_id or gen_id or image_session.last_generation_id
    parent_gen = None
    result_url = getattr(image_session, "last_result_url", None) or getattr(image_session, "reference_url", None)
    if source_parent_id:
        parent_gen = await repo.get_generation_by_id(session, source_parent_id)
        if parent_gen and parent_gen.user_id == db_user.id and parent_gen.result_url:
            result_url = parent_gen.result_url
    source_feed_gen_id = await _source_feed_id_from_parent(
        session=session,
        data=data,
        parent_gen=parent_gen,
        db_user=db_user,
    )

    if not result_url:
        await call.answer("Не нашёл изображение для редактирования", show_alert=True)
        return

    image_session.mode = "image"
    image_session.reference_url = result_url
    image_session.reference_file_id = None
    image_session.reference_file_ids = None
    await session.commit()

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        model_key=image_session.model,
        mode="image",
        image_mode="image",
        image_file_id=None,
        ref_file_ids=[],
        remix_mode=True,
        remix_parent_generation_id=parent_id or gen_id or image_session.last_generation_id,
        remix_reference_url=result_url,
        style_edit_kind=edit_kind,
        source_feed_gen_id=source_feed_gen_id,
    )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"💅 <b>Меняем {label}</b>\n\n{hint}\n\n"
        "Остальное в кадре постараюсь сохранить.",
        reply_markup=image_session_kb(
            parent_id or gen_id or image_session.last_generation_id,
            allow_publish=not bool(source_feed_gen_id),
        ),
    )
    await call.answer()


@router.callback_query(F.data == "img_variation")
@router.callback_query(F.data.startswith("img_session:repeat:"))
async def cb_image_session_repeat(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    gen_id = None
    if call.data and call.data.startswith("img_session:repeat:"):
        gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
        gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    last_gen = await repo.get_last_session_generation(session, image_session.id)
    if not last_gen:
        await call.answer("Нечего повторять", show_alert=True)
        return

    data = await state.get_data()
    source_feed_gen_id = getattr(last_gen, "source_feed_gen_id", None)
    reference_url = await _session_reference_url(bot, image_session, prefer_last_result=False, state=None)

    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=last_gen.prompt,
        action_type=ImageGenerationAction.repeat,
        reference_url=reference_url,
        parent_generation_id=parent_id or last_gen.id,
        source_feed_gen_id=source_feed_gen_id,
        launching_text="🔁 <b>Повторяю последнюю генерацию...</b>",
        queued_text="⏳ <b>Повтор запущен.</b> Результат придёт сюда автоматически.",
    )
    await call.answer()


@router.callback_query(F.data == "img_settings")
@router.callback_query(F.data == "img_session:settings")
async def cb_image_session_settings(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(image_session_id=image_session.id)

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id, image_session.model, image_session.mode),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset:back:"))
async def cb_image_settings_back(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)

    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    await _show_active_image_session_callback(call, state, session, db_user, image_session)
    await call.answer()


@router.callback_query(F.data == "img_new")
@router.callback_query(F.data == "img_session:new")
async def cb_image_session_new(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    await repo.archive_active_image_sessions(session, db_user.id)
    await state.clear()
    screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        screen.text,
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("img_session:animate:"))
async def cb_image_session_animate(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    from api.video_service import VideoModel
    from bot.handlers.video_gen import _DEFAULT_DURATION, _DEFAULT_RATIO, _DEFAULT_RES
    from bot.keyboards.models import VIDEO_CAPS, video_params_kb
    from bot.states import VideoGenFSM

    gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
    gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None

    result_url: str | None = None
    if gen_id:
        gen = await repo.get_generation_by_id(session, gen_id)
        if gen and gen.user_id == db_user.id:
            result_url = gen.result_url

    if not result_url:
        image_session, _ = await _resolve_image_session(session, db_user, state)
        if image_session:
            result_url = image_session.last_result_url

    if not result_url:
        await call.answer("Сначала дождись готового изображения", show_alert=True)
        return

    model_key = VideoModel.GROK_I2V
    duration = _DEFAULT_DURATION.get(model_key, 6)
    aspect_ratio = _DEFAULT_RATIO.get(model_key)
    resolution = _DEFAULT_RES.get(model_key, "480p")
    grok_mode = "normal" if VIDEO_CAPS.get(model_key, {}).get("mode_options") else None
    model_cost = await repo.resolve_video_model_cost(
        session,
        model_key,
        duration=duration,
        resolution=resolution,
    )
    if not model_cost:
        await call.answer("Модель Grok Animate недоступна", show_alert=True)
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋! Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    await state.set_state(VideoGenFSM.params_select)
    await state.update_data(
        model_key=model_key,
        mode="image",
        credits=model_cost.credits,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        grok_mode=grok_mode,
        image_file_id=None,
        image_url=result_url,
        reference_video_url=None,
        motion_step=None,
    )

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎬 <b>Оживляем изображение</b>\n\n"
        f"Модель: <code>{model_cost.display_name}</code>\n\n"
        "⚙️ Настрой параметры и нажми <b>Далее →</b>",
        reply_markup=video_params_kb(
            model_key,
            duration,
            aspect_ratio,
            resolution,
            grok_mode,
            selected_mode="image",
            ref_count=1,
        ),
    )
    await safe_answer_callback(call)


# ── Session settings actions ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("img_sset:ratio:"))
async def cb_image_settings_ratio(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    ratios = _ratio_options_for_mode(image_session.model, image_session.mode)
    if not ratios:
        await call.answer("У модели нет выбора формата", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📐 <b>Выбери формат кадра для активной серии</b>\n"
        "Квадрат, вертикаль или горизонталь.",
        reply_markup=_session_ratio_choices_kb(image_session),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset_ratio:set:"))
async def cb_image_settings_ratio_set(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    _, _, session_id_raw, ratio = call.data.split(":", 3)  # type: ignore[union-attr]
    image_session = await repo.get_image_session(session, int(session_id_raw), db_user.id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    ratios = _ratio_options_for_mode(image_session.model, image_session.mode)
    if ratio not in ratios:
        await call.answer("Этот формат недоступен для модели", show_alert=True)
        return

    previous_quality = image_session.quality
    image_session.aspect_ratio = ratio
    normalized_quality = _normalize_session_quality(image_session.model, ratio, image_session.quality)
    if normalized_quality != image_session.quality:
        image_session.quality = normalized_quality
    await session.commit()
    model_cost = await repo.resolve_image_model_cost(session, image_session.model, quality=image_session.quality)
    await state.update_data(
        image_session_id=image_session.id,
        aspect_ratio=ratio,
        quality=image_session.quality,
        image_quality=image_session.quality,
        credits=model_cost.credits if model_cost else None,
    )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id, image_session.model, image_session.mode),
    )
    if previous_quality != image_session.quality:
        await call.answer("Формат обновлён, качество снижено до 2K для 1:1")
        return
    await call.answer("Формат обновлён")


@router.callback_query(F.data.startswith("img_sset:quality:"))
async def cb_image_settings_quality(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    if not IMAGE_CAPS.get(image_session.model, {}).get("has_quality"):
        await call.answer("У модели нет настройки качества", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "💎 <b>Выбери детализацию для активной серии</b>\n"
        "2K обычно быстрее, 4K даёт больше деталей.",
        reply_markup=_session_quality_choices_kb(image_session),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset_quality:set:"))
async def cb_image_settings_quality_set(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    _, _, session_id_raw, quality = call.data.split(":", 3)  # type: ignore[union-attr]
    image_session = await repo.get_image_session(session, int(session_id_raw), db_user.id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    if not IMAGE_CAPS.get(image_session.model, {}).get("has_quality"):
        await call.answer("У модели нет настройки качества", show_alert=True)
        return

    allowed_quality = {value for value, _ in _quality_options(image_session.model)}
    if quality not in allowed_quality:
        await call.answer("Это качество недоступно для модели", show_alert=True)
        return

    normalized_quality = _normalize_session_quality(image_session.model, image_session.aspect_ratio, quality)
    image_session.quality = normalized_quality
    await session.commit()
    model_cost = await repo.resolve_image_model_cost(session, image_session.model, quality=normalized_quality)
    await state.update_data(
        image_session_id=image_session.id,
        quality=normalized_quality,
        image_quality=normalized_quality,
        credits=model_cost.credits if model_cost else None,
    )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id, image_session.model, image_session.mode),
    )
    if normalized_quality != quality:
        await call.answer("Для формата 1:1 доступно только 2K")
        return
    await call.answer("Качество обновлено")


@router.callback_query(F.data.startswith("img_sset:count:"))
async def cb_image_settings_count(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    counts = IMAGE_CAPS.get(image_session.model, {}).get("counts", [1])
    if len(counts) <= 1:
        await call.answer("У модели фиксированное количество изображений", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🔢 <b>Сколько вариантов создавать за один запуск?</b>",
        reply_markup=_session_count_choices_kb(image_session),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset_count:set:"))
async def cb_image_settings_count_set(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    _, _, session_id_raw, count_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    image_session = await repo.get_image_session(session, int(session_id_raw), db_user.id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    count = int(count_raw)
    counts = IMAGE_CAPS.get(image_session.model, {}).get("counts", [1])
    if count not in counts:
        await call.answer("Это количество недоступно для модели", show_alert=True)
        return

    image_session.count = count
    await session.commit()
    await state.update_data(image_session_id=image_session.id, count=count)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id, image_session.model, image_session.mode),
    )
    await call.answer("Количество обновлено")


@router.callback_query(F.data.startswith("img_sset:model:"))
async def cb_image_settings_model(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    carryover_ref_file_ids: list[str] = []
    carryover_image_file_id: str | None = None
    carryover_reference_url: str | None = None
    carryover_mode: str | None = None

    if image_session:
        carryover_ref_file_ids = _stored_reference_file_ids(image_session)
        carryover_image_file_id = image_session.reference_file_id or (carryover_ref_file_ids[0] if carryover_ref_file_ids else None)
        carryover_reference_url = image_session.reference_url or image_session.last_result_url
        if carryover_ref_file_ids or carryover_image_file_id or carryover_reference_url:
            carryover_mode = "image"
        elif image_session.mode:
            carryover_mode = image_session.mode

    await repo.archive_active_image_sessions(session, db_user.id)
    await state.clear()
    await state.update_data(
        carryover_mode=carryover_mode,
        carryover_image_file_id=carryover_image_file_id,
        carryover_ref_file_ids=carryover_ref_file_ids,
        carryover_reference_url=carryover_reference_url,
    )
    await _open_image_model_select(call, session, state, db_user)
    await safe_answer_callback(call)


# ── Share to feed ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("gen:share:"))
async def cb_gen_share(call: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot) -> None:
    from bot.utils.deep_links import build_start_payload
    from bot.utils.telegram_ui import safe_answer_callback

    gen_id = int(call.data.split(":")[-1])
    existing = await repo.get_generation_by_id(session, gen_id)
    if not await _generation_prompt_actions_allowed(session=session, gen=existing, db_user=db_user):
        await safe_answer_callback(call, "❌ Нельзя опубликовать результат из ленты")
        return

    gen = await repo.share_to_feed(session, gen_id, db_user.id)
    if not gen:
        await safe_answer_callback(call, "❌ Не удалось поделиться")
        return

    bot_info = await bot.get_me()
    share_payload = build_start_payload(ref_code=db_user.referral_code, target_kind="feed", target_id=gen.id)
    share_link = f"https://t.me/{bot_info.username}?start={share_payload}"

    await call.message.answer(  # type: ignore[union-attr]
        "📤 <b>Фото добавлено в ленту</b>\n\n"
        f"🔗 Ссылка на пост для повтора:\n{share_link}",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call, "✅ Ссылка на пост готова")


@router.callback_query(F.data.startswith("gen:library:"))
async def cb_gen_library(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from bot.utils.telegram_ui import safe_answer_callback
    gen_id = int(call.data.split(":")[-1])
    existing = await repo.get_generation_by_id(session, gen_id)
    if not await _generation_prompt_actions_allowed(session=session, gen=existing, db_user=db_user):
        await safe_answer_callback(call, "❌ Нельзя сохранить промпт из ленты")
        return

    gen = await repo.share_to_library(session, gen_id, db_user.id)
    if not gen:
        await safe_answer_callback(call, "❌ Не удалось сохранить промпт")
        return
    await safe_answer_callback(call, "💾 Промпт сохранён в библиотеке!")


@router.callback_query(F.data.startswith("gen:prompt:"))
async def cb_gen_prompt(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    gen_id = int(call.data.split(":")[-1])
    gen = await repo.get_generation_by_id(session, gen_id)
    if not await _generation_prompt_actions_allowed(session=session, gen=gen, db_user=db_user):
        await safe_answer_callback(call, "❌ Промпт недоступен")
        return

    prompt = public_prompt_text(gen.prompt)
    if not prompt:
        await safe_answer_callback(call, "❌ Промпт пустой")
        return

    await call.message.answer(  # type: ignore[union-attr]
        f"📋 <b>Промпт</b>\n\n<code>{html.escape(prompt)}</code>",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call, "Промпт отправлен")


# ── Regen ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("regen:image:"))
async def cb_regen_image(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    prev = await repo.get_generation_by_id(session, gen_id)
    if not prev:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    prev_session = None
    if prev.image_session_id:
        prev_session = await repo.get_image_session(session, prev.image_session_id, db_user.id)

    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=prev.model,
        mode=prev_session.mode if prev_session else "text",
        aspect_ratio=prev_session.aspect_ratio if prev_session else None,
        quality=prev_session.quality if prev_session else "basic",
        count=prev_session.count if prev_session else 1,
        base_prompt=None,
        reference_file_id=prev_session.reference_file_id if prev_session else None,
        reference_file_ids=_stored_reference_file_ids(prev_session) if prev_session else None,
        reference_url=prev_session.reference_url if prev_session else None,
    )
    reference_url = await _session_reference_url(bot, image_session, prefer_last_result=False)
    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prev.prompt,
        action_type=ImageGenerationAction.repeat,
        reference_url=reference_url,
        parent_generation_id=prev.id,
        source_feed_gen_id=getattr(prev, "source_feed_gen_id", None),
        launching_text="🔁 <b>Повторяю генерацию...</b>",
        queued_text="⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
    )
    await call.answer()


# ── Photo → Prompt ────────────────────────────────────────────────────────────


def _p2p_result_kb(*, ref_file_id: str | None, model_key: str | None, model_name: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ref_label = "🖼️ Изменить референс ✅" if ref_file_id else "🖼️ Загрузить референс"
    builder.row(InlineKeyboardButton(text=ref_label, callback_data="p2p:ref"))
    model_label = f"🎨 {model_name} ✅" if model_key else "🎨 Выбрать модель"
    builder.row(InlineKeyboardButton(text=model_label, callback_data="p2p:model"))
    builder.row(InlineKeyboardButton(text="✅ Сгенерировать", callback_data="p2p:generate"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt"))
    return builder.as_markup()


def _p2p_prompt_text(*, ref_file_id: str | None, model_name: str | None) -> str:
    ref_line = "📎 Референс: ✅ добавлен\n" if ref_file_id else "📎 Референс: не выбран (необязательно)\n"
    model_line = f"🎨 Модель: <b>{model_name}</b>\n" if model_name else "🎨 Модель: не выбрана\n"
    return (
        "✨ <b>Промпт готов!</b>\n\n"
        "ИИ проанализировал фото и создал промпт — он применится автоматически.\n\n"
        f"{ref_line}{model_line}\n"
        "Выбери модель и нажми <b>Сгенерировать</b>."
    )


@router.callback_query(F.data == "img:photo2prompt")
async def cb_photo_to_prompt(
    call: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(ImageGenFSM.photo_to_prompt)
    await state.update_data(
        generated_prompt=None,
        p2p_ref_file_id=None,
        p2p_model_key=None,
        p2p_model_name=None,
    )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📸 <b>Фото → Генерация</b>\n\n"
        "Отправь фотографию — ИИ проанализирует её и сразу запустит генерацию.\n\n"
        "Можно также выбрать модель и загрузить референс перед стартом.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt"),
        ]]),
    )
    await safe_answer_callback(call)


@router.message(ImageGenFSM.photo_to_prompt, F.photo)
async def handle_photo_to_prompt(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id

    wait_msg = await message.answer("⏳ Анализирую фотографию…")

    try:
        tg_file = await bot.get_file(file_id)
        downloaded = await bot.download_file(tg_file.file_path)
        raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)  # type: ignore[union-attr]
        ext = _detect_image_ext(raw)
        mime = "image/jpeg" if ext == ".jpg" else ("image/png" if ext == ".png" else "image/webp")
        prompt = await generate_prompt_from_photo(raw, mime)
    except Exception as exc:
        logger.error("photo_to_prompt error: %s", exc)
        await wait_msg.edit_text(
            "❌ Не удалось проанализировать фото. Попробуй ещё раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Закрыть", callback_data="img:cancel_prompt"),
            ]]),
        )
        return

    await state.update_data(generated_prompt=prompt, p2p_ref_file_id=file_id)
    data = await state.get_data()

    await wait_msg.delete()
    await message.answer(
        _p2p_prompt_text(ref_file_id=file_id, model_name=data.get("p2p_model_name")),
        reply_markup=_p2p_result_kb(
            ref_file_id=file_id,
            model_key=data.get("p2p_model_key"),
            model_name=data.get("p2p_model_name"),
        ),
    )


# ── p2p: reference upload ─────────────────────────────────────────────────────

@router.callback_query(F.data == "p2p:ref")
async def cb_p2p_ref(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ImageGenFSM.photo_to_prompt_ref)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🖼️ <b>Загрузи референс-изображение</b>\n\n"
        "Отправь фото, которое будет использоваться как референс при генерации.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="← Назад", callback_data="p2p:back_to_result"),
        ]]),
    )
    await safe_answer_callback(call)


@router.message(ImageGenFSM.photo_to_prompt_ref, F.photo)
async def handle_p2p_ref_upload(message: Message, state: FSMContext) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    ref_file_id = best[0].file_id
    await state.update_data(p2p_ref_file_id=ref_file_id)
    await state.set_state(ImageGenFSM.photo_to_prompt)

    data = await state.get_data()
    await message.answer(
        _p2p_prompt_text(ref_file_id=ref_file_id, model_name=data.get("p2p_model_name")),
        reply_markup=_p2p_result_kb(
            ref_file_id=ref_file_id,
            model_key=data.get("p2p_model_key"),
            model_name=data.get("p2p_model_name"),
        ),
    )


@router.callback_query(F.data == "p2p:back_to_result")
async def cb_p2p_back_to_result(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ImageGenFSM.photo_to_prompt)
    data = await state.get_data()
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _p2p_prompt_text(ref_file_id=data.get("p2p_ref_file_id"), model_name=data.get("p2p_model_name")),
        reply_markup=_p2p_result_kb(
            ref_file_id=data.get("p2p_ref_file_id"),
            model_key=data.get("p2p_model_key"),
            model_name=data.get("p2p_model_name"),
        ),
    )
    await safe_answer_callback(call)


# ── p2p: model select ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "p2p:model")
async def cb_p2p_model(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    await state.set_state(ImageGenFSM.photo_to_prompt_model)
    model_costs = await repo.get_all_model_costs(session)
    from bot.ui.router import render_screen
    screen = await render_screen(screen="image_advanced", session=session, db_user=db_user, extra={"model_costs": model_costs})
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎨 <b>Выбери модель для генерации</b>\n\n" + screen.text.split("\n\n", 1)[-1],
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


# ── p2p: generate ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "p2p:generate")
async def cb_p2p_generate(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    prompt = data.get("generated_prompt", "").strip()
    model_key = data.get("p2p_model_key")
    ref_file_id = data.get("p2p_ref_file_id")

    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return

    # Resolve model: explicit choice → active session → error
    image_session = None
    if model_key:
        quality_opts = IMAGE_CAPS.get(model_key, {}).get("quality_options") or []
        quality = quality_opts[0][0] if quality_opts else "basic"
        mode = "image" if ref_file_id and _supports_img2img(model_key) else "text"
        image_session = await repo.create_image_session(
            session=session,
            user_id=db_user.id,
            model=model_key,
            mode=mode,
            aspect_ratio=None,
            quality=quality,
            count=1,
            base_prompt=None,
            reference_file_id=ref_file_id if mode == "image" else None,
        )
    else:
        image_session = await repo.get_active_image_session(session, db_user.id)
        if not image_session:
            await call.answer("Выбери модель или открой активную серию", show_alert=True)
            return

    # Build reference URL if session uses image mode
    reference_url: str | None = None
    if ref_file_id and _supports_img2img(image_session.model):
        reference_url = await _telegram_file_url(bot, ref_file_id)

    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt,
        action_type=ImageGenerationAction.initial,
        reference_url=reference_url,
        parent_generation_id=None,
        launching_text="📸 <b>Генерирую по промпту из фото...</b>",
        queued_text="⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
    )
    await safe_answer_callback(call)


# ── p2p: cancel ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "img:cancel_prompt")
async def cb_cancel_prompt(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    image_session = await repo.get_active_image_session(session, db_user.id)
    if image_session:
        await _show_active_image_session_callback(call, state, session, db_user, image_session)
    else:
        await state.clear()
        from bot.ui.router import render_screen
        screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            screen.text,
            reply_markup=screen.reply_markup,
        )
    await safe_answer_callback(call)
