"""Admin-only Neironych Nano Banana Pro evaluation, without APIX billing."""
from __future__ import annotations

import html
import logging
import uuid
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from redis.asyncio import Redis

from api import neironych_image_adapter
from api import neironych_nano_pro as provider
from api.public_files import mirror_telegram_file
from bot.filters.admin import IsAdmin
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings

logger = logging.getLogger(__name__)
router = Router(name="neironych_nano_pro_test")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class NanoProTestFSM(StatesGroup):
    dashboard = State()
    prompt = State()
    reference = State()


def initial_data() -> dict[str, Any]:
    return {"npro_prompt": "", "npro_refs": [], "npro_ratio": "1:1",
            "npro_quality": "2K", "npro_request_id": str(uuid.uuid4())}


def params(data: dict[str, Any]) -> dict[str, Any]:
    return {"prompt": data.get("npro_prompt", ""), "image_urls": data.get("npro_refs", []),
            "aspect_ratio": data.get("npro_ratio", "1:1"), "quality": data.get("npro_quality", "2K")}


async def update_request(state: FSMContext, **changes: Any) -> None:
    data = await state.get_data()
    if params(data) != params({**data, **changes}):
        await state.update_data(**changes, npro_request_id=str(uuid.uuid4()))


def keyboard(data: dict[str, Any]):
    kb = InlineKeyboardBuilder()
    for label, action in (("✍️ Промпт", "prompt"), ("🖼 Референс", "reference"),
                          ("🗑 Убрать референсы", "clear")):
        kb.button(text=label, callback_data=f"npro:{action}")
    kb.adjust(1)
    for ratio in provider.RATIOS:
        kb.button(text=("✅ " if ratio == data.get("npro_ratio") else "") + ratio,
                  callback_data=f"npro:ratio:{ratio}")
    kb.adjust(1, 1, 1, 3, 3)
    kb.row(*[InlineKeyboardButton(
        text=("✅ " if q == data.get("npro_quality") else "") + q,
        callback_data=f"npro:quality:{q}") for q in provider.QUALITIES])
    kb.row(InlineKeyboardButton(text="🚀 Запустить платный тест", callback_data="npro:run"))
    kb.row(InlineKeyboardButton(text="🔎 Проверить результат", callback_data="npro:status"))
    kb.row(InlineKeyboardButton(text="🆕 Новый тест", callback_data="nxt:model:neur-nano-pro"))
    kb.row(InlineKeyboardButton(text="⬅️ Другие модели", callback_data="nxt:model:choose"))
    return kb.as_markup()


async def show(message: Message, state: FSMContext, *, edit: bool = True) -> None:
    data = await state.get_data()
    await state.set_state(NanoProTestFSM.dashboard)
    text = (
        "🧪 <b>Нейроныч · Nano Banana Pro</b>\n\n"
        "Тест доступен только администраторам. APIX-кредиты не списываются. "
        "Запуск расходует баланс Нейроныча.\n\n"
        f"Формат: {html.escape(data.get('npro_ratio', '1:1'))} · "
        f"Качество: {html.escape(data.get('npro_quality', '2K'))}\n"
        f"Референсы: {len(data.get('npro_refs', []))}/{provider.MAX_REFERENCES}\n\n"
        f"Промпт: {html.escape(str(data.get('npro_prompt') or 'не задан')[:1500])}\n\n"
        f"Request ID: <code>{html.escape(str(data.get('npro_request_id', '')))}</code>"
    )
    if edit:
        await safe_edit_message(message, text, reply_markup=keyboard(data))
    else:
        await message.answer(text, reply_markup=keyboard(data))


@router.callback_query(F.data == "nxt:model:neur-nano-pro")
async def open_lab(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**initial_data())
    await safe_answer_callback(call)
    await show(call.message, state)


@router.callback_query(F.data.in_({"npro:prompt", "npro:reference"}))
async def input_begin(call: CallbackQuery, state: FSMContext) -> None:
    is_prompt = call.data == "npro:prompt"
    await state.set_state(NanoProTestFSM.prompt if is_prompt else NanoProTestFSM.reference)
    await safe_answer_callback(call)
    await call.message.answer(
        "Пришлите промпт одним сообщением." if is_prompt else
        f"Пришлите фото, документ с изображением или HTTPS-ссылку. До {provider.MAX_REFERENCES} референсов."
    )


@router.message(NanoProTestFSM.prompt, F.text)
async def save_prompt(message: Message, state: FSMContext) -> None:
    prompt = str(message.text or "").strip()
    if not prompt:
        await message.answer("Введите непустой промпт.")
        return
    await update_request(state, npro_prompt=prompt)
    await show(message, state, edit=False)


@router.message(NanoProTestFSM.reference)
async def save_reference(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    refs = list(data.get("npro_refs", []))
    if len(refs) >= provider.MAX_REFERENCES:
        await message.answer(f"Уже добавлено {provider.MAX_REFERENCES} референса.")
        return
    try:
        if message.photo:
            url = await mirror_telegram_file(message.bot, message.photo[-1].file_id)
        elif message.document and str(message.document.mime_type or "").startswith("image/"):
            url = await mirror_telegram_file(message.bot, message.document.file_id)
        elif message.text:
            url = message.text.strip()
        else:
            raise ValueError("Пришлите изображение или HTTPS-ссылку.")
        refs = list(dict.fromkeys([*refs, url]))
        provider.build_payload(**{**params(data), "prompt": "validate", "image_urls": refs})
    except Exception:
        logger.warning("neironych_nano_pro_lab_reference_failed")
        await message.answer("Не удалось добавить референс. Пришлите фото или публичную HTTPS-ссылку.")
        return
    await update_request(state, npro_refs=refs)
    await show(message, state, edit=False)


@router.callback_query(F.data.startswith("npro:ratio:") | F.data.startswith("npro:quality:") | (F.data == "npro:clear"))
async def change_settings(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    changes: dict[str, Any] = {}
    action = str(call.data)
    if action.startswith("npro:ratio:"):
        changes["npro_ratio"] = action.removeprefix("npro:ratio:")
    elif action.startswith("npro:quality:"):
        changes["npro_quality"] = action.removeprefix("npro:quality:")
    else:
        changes["npro_refs"] = []
    try:
        provider.build_payload(**{**params({**data, **changes}), "prompt": "validate"})
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    await update_request(state, **changes)
    await safe_answer_callback(call)
    await show(call.message, state)


async def claim_request(request_id: str) -> bool:
    # Permanent claim: even a later repeated callback must never buy another image.
    # A new test gets a fresh UUID. Redis outage fails closed before the paid POST.
    async with Redis.from_url(settings.REDIS_URL) as cache:
        return bool(await cache.set(f"lab:nano-pro:{request_id}", "submitted", nx=True))


async def deliver(message: Message, url: str, request_id: str) -> None:
    try:
        await message.answer_document(URLInputFile(url, filename="nano-banana-pro.png"),
                                      caption="✅ Нейроныч · Nano Banana Pro")
    except Exception:
        logger.exception("neironych_nano_pro_lab_delivery_failed request_id=%s", request_id)
        await message.answer(f"Изображение готово: {html.escape(url)}")


@router.callback_query(F.data == "npro:run")
async def run(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        request_id = str(uuid.UUID(str(data.get("npro_request_id", ""))))
        provider.build_payload(**params(data))
        if not settings.NEIRONYCH_API_KEY.strip():
            raise ValueError("Ключ Нейроныча не настроен.")
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    await safe_answer_callback(call, "Запускаю тест…")
    try:
        claimed = await claim_request(request_id)
    except Exception:
        logger.exception("neironych_nano_pro_lab_claim_failed request_id=%s", request_id)
        await call.message.answer("Не удалось защитить запуск от повтора. Попробуйте позже.")
        return
    if not claimed:
        await call.message.answer("Этот запрос уже отправлен. Нажмите «Проверить результат».")
        return
    logger.info("neironych_nano_pro_lab_started request_id=%s admin_id=%s", request_id, call.from_user.id)
    try:
        url = await provider.generate_image(request_id=request_id, **params(data))
    except Exception:
        logger.exception("neironych_nano_pro_lab_unknown request_id=%s", request_id)
        await call.message.answer(
            f"Не удалось получить результат. Request ID: <code>{request_id}</code>. "
            "Запрос мог быть принят. Автоповтора нет; используйте «Проверить результат»."
        )
        return
    await deliver(call.message, url, request_id)


@router.callback_query(F.data == "npro:status")
async def status(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        request_id = str(uuid.UUID(str(data.get("npro_request_id", ""))))
    except ValueError:
        await safe_answer_callback(call, "Сначала откройте новый тест.", show_alert=True)
        return
    await safe_answer_callback(call, "Проверяю…")
    try:
        result = await neironych_image_adapter.fetch_nano_banana21_status(
            request_id, expected_model=provider.MODEL,
        )
        if result["status"] == "completed" and result.get("result_url"):
            url = await neironych_image_adapter.mirror_verified_nano_banana21_result(result["result_url"])
            await deliver(call.message, url, request_id)
        else:
            await call.message.answer("Статус запроса: " + html.escape(result["status"]))
    except Exception:
        logger.exception("neironych_nano_pro_lab_status_failed request_id=%s", request_id)
        await call.message.answer("Статус временно недоступен. Повторите проверку позже.")

