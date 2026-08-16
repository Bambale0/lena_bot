from __future__ import annotations

import html
import logging
import uuid
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    Message,
    URLInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.nexusapi_client import (
    NEXUS_NANO_BANANA_PRO_MODEL,
    NexusApiClient,
    NexusApiError,
    NexusApiTimeout,
    build_nano_banana_pro_params,
    extract_result_base64,
    extract_result_urls,
    find_model_in_catalog,
    pretty_json,
)
from api.public_files import mirror_telegram_file, save_public_file
from bot.filters.admin import IsAdmin
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="nexusapi_test")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_DEFAULT_PROMPT = (
    "Премиальная предметная фотография жёлтой керамической кружки на нейтральном фоне, "
    "мягкий студийный свет, реалистичные материалы, высокая детализация"
)
_RATIO_CALLBACKS = {
    "auto": None,
    "1x1": "1:1",
    "16x9": "16:9",
    "9x16": "9:16",
    "4x3": "4:3",
    "3x4": "3:4",
}


class NexusTestFSM(StatesGroup):
    dashboard = State()
    awaiting_prompt = State()
    awaiting_reference = State()
    awaiting_seed = State()
    awaiting_webhook = State()


def _new_idempotency_key() -> str:
    return str(uuid.uuid4())


def _initial_data() -> dict[str, Any]:
    return {
        "nexus_model": NEXUS_NANO_BANANA_PRO_MODEL,
        "nexus_mode": "text",
        "nexus_prompt": _DEFAULT_PROMPT,
        "nexus_aspect_ratio": None,
        "nexus_seed": None,
        "nexus_image_url": None,
        "nexus_webhook_url": None,
        "nexus_idempotency_key": _new_idempotency_key(),
        "nexus_last_task_id": None,
    }


async def _ensure_data(state: FSMContext) -> dict[str, Any]:
    data = await state.get_data()
    if data.get("nexus_model") != NEXUS_NANO_BANANA_PRO_MODEL:
        defaults = _initial_data()
        await state.update_data(**defaults)
        data = {**data, **defaults}
    if not data.get("nexus_idempotency_key"):
        key = _new_idempotency_key()
        await state.update_data(nexus_idempotency_key=key)
        data = {**data, "nexus_idempotency_key": key}
    return data


async def _change_request(state: FSMContext, **updates: Any) -> None:
    """Change request inputs and rotate idempotency key for the new body."""
    await state.update_data(**updates, nexus_idempotency_key=_new_idempotency_key())


def _clip(value: str, limit: int = 500) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _mode_label(data: dict[str, Any]) -> str:
    return "Image edit" if data.get("nexus_mode") == "edit" else "Text → Image"


def _ratio_label(data: dict[str, Any]) -> str:
    return str(data.get("nexus_aspect_ratio") or "Авто")


def _seed_label(data: dict[str, Any]) -> str:
    value = data.get("nexus_seed")
    return "Авто" if value is None else str(value)


def _dashboard_text(data: dict[str, Any]) -> str:
    client = NexusApiClient()
    prompt = _clip(str(data.get("nexus_prompt") or "").strip(), 450)
    image_url = _clip(str(data.get("nexus_image_url") or "").strip())
    webhook_url = _clip(str(data.get("nexus_webhook_url") or "").strip())
    idem = str(data.get("nexus_idempotency_key") or "")
    key_state = "✅ настроен" if client.configured else "❌ NEXUS_API_KEY не задан"
    text = (
        "🧪 <b>NexusAPI · Nano Banana Pro</b>\n\n"
        "Изолированный админский тест. Кредиты пользователей APIX не списываются, "
        "боевой провайдер не переключается. Платная генерация расходует только баланс NexusAPI.\n\n"
        f"🔑 API key: <b>{key_state}</b>\n"
        f"🌐 Endpoint: <code>{html.escape(client.base_url)}</code>\n"
        f"🤖 Model: <code>{NEXUS_NANO_BANANA_PRO_MODEL}</code>\n"
        f"🧭 Режим: <b>{_mode_label(data)}</b>\n"
        f"📐 Формат: <b>{_ratio_label(data)}</b>\n"
        f"🎲 Seed: <b>{_seed_label(data)}</b>\n"
        f"🖼 Reference: <b>{'есть' if image_url else 'нет'}</b>\n"
        f"🔗 Webhook: <b>{'вкл' if webhook_url else 'выкл'}</b>\n"
        f"🛡 Idempotency: <code>{html.escape(idem)}</code>\n\n"
        f"✍️ <b>Промпт</b>\n{html.escape(prompt or '—')}\n\n"
        "Доступны все поля опубликованной NexusAPI-спеки этой модели: prompt, aspect_ratio, "
        "seed, image_url и webhook_url. Raw payload можно посмотреть до платного запуска."
    )
    if data.get("nexus_last_task_id"):
        text += f"\n\nПоследняя задача: <code>{html.escape(str(data['nexus_last_task_id']))}</code>"
    if image_url:
        text += f"\nReference URL: <code>{html.escape(image_url)}</code>"
    if webhook_url:
        text += f"\nWebhook URL: <code>{html.escape(webhook_url)}</code>"
    return text


def _dashboard_kb(data: dict[str, Any]):
    builder = InlineKeyboardBuilder()
    text_mode = data.get("nexus_mode") != "edit"
    builder.row(
        InlineKeyboardButton(
            text=("✅ " if text_mode else "") + "📝 T2I",
            callback_data="nxt:mode:text",
        ),
        InlineKeyboardButton(
            text=("✅ " if not text_mode else "") + "🖼 Edit",
            callback_data="nxt:mode:edit",
        ),
    )
    builder.row(InlineKeyboardButton(text="✍️ Изменить промпт", callback_data="nxt:prompt"))
    builder.row(
        InlineKeyboardButton(text=f"📐 Формат · {_ratio_label(data)}", callback_data="nxt:ratio"),
        InlineKeyboardButton(text=f"🎲 Seed · {_seed_label(data)}", callback_data="nxt:seed"),
    )
    builder.row(
        InlineKeyboardButton(text="🖼 Референс", callback_data="nxt:reference"),
        InlineKeyboardButton(
            text=f"🔗 Webhook · {'вкл' if data.get('nexus_webhook_url') else 'выкл'}",
            callback_data="nxt:webhook",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Raw payload", callback_data="nxt:payload"),
        InlineKeyboardButton(text="🌐 Live каталог", callback_data="nxt:catalog"),
    )
    if data.get("nexus_last_task_id"):
        builder.row(
            InlineKeyboardButton(text="🔎 Статус последней задачи", callback_data="nxt:status")
        )
    builder.row(InlineKeyboardButton(text="🚀 Запустить тест", callback_data="nxt:run"))
    builder.row(
        InlineKeyboardButton(text="🆕 Новый request ID", callback_data="nxt:newkey"),
        InlineKeyboardButton(text="♻️ Сбросить", callback_data="nxt:reset"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _ratio_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Авто / не отправлять", callback_data="nxt:ratio:auto"))
    for key, ratio in _RATIO_CALLBACKS.items():
        if ratio is not None:
            builder.button(text=ratio, callback_data=f"nxt:ratio:{key}")
    builder.adjust(1, 2, 2, 1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _seed_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Авто / не отправлять", callback_data="nxt:seed:auto"))
    builder.row(InlineKeyboardButton(text="✍️ Ввести seed", callback_data="nxt:seed:custom"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _reference_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🗑 Убрать референс", callback_data="nxt:reference:clear"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _webhook_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔕 Выключить webhook", callback_data="nxt:webhook:clear"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


async def _show_dashboard(message: Message, state: FSMContext) -> None:
    data = await _ensure_data(state)
    await state.set_state(NexusTestFSM.dashboard)
    await safe_edit_message(message, _dashboard_text(data), reply_markup=_dashboard_kb(data))


async def _answer_dashboard(message: Message, state: FSMContext) -> None:
    data = await _ensure_data(state)
    await state.set_state(NexusTestFSM.dashboard)
    await message.answer(_dashboard_text(data), reply_markup=_dashboard_kb(data))


@router.callback_query(F.data == "menu:test")
async def open_nexus_test(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:dashboard")
async def nexus_dashboard(call: CallbackQuery, state: FSMContext) -> None:
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:newkey")
async def nexus_new_key(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(nexus_idempotency_key=_new_idempotency_key())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Новый Idempotency-Key")


@router.callback_query(F.data.startswith("nxt:mode:"))
async def nexus_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = str(call.data or "").rsplit(":", 1)[-1]
    if mode not in {"text", "edit"}:
        await safe_answer_callback(call, "Неизвестный режим", show_alert=True)
        return
    await _change_request(state, nexus_mode=mode)
    if mode == "edit" and not (await state.get_data()).get("nexus_image_url"):
        await state.set_state(NexusTestFSM.awaiting_reference)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            "🖼 <b>Image edit</b>\n\nПришли фото, image-документ или публичный HTTP(S) URL. "
            "Telegram-файл будет сохранён в публичное хранилище APIX и передан NexusAPI "
            "как <code>image_url</code>.",
            reply_markup=_reference_kb(),
        )
    else:
        await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:prompt")
async def nexus_prompt_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NexusTestFSM.awaiting_prompt)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✍️ <b>Промпт Nano Banana Pro</b>\n\nПришли новый текст одним сообщением.",
        reply_markup=_dashboard_kb(await _ensure_data(state)),
    )
    await safe_answer_callback(call)


@router.message(NexusTestFSM.awaiting_prompt, F.text)
async def nexus_prompt_save(message: Message, state: FSMContext) -> None:
    prompt = str(message.text or "").strip()
    if not prompt:
        await message.answer("Промпт не может быть пустым.")
        return
    await _change_request(state, nexus_prompt=prompt)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:ratio")
async def nexus_ratio_menu(call: CallbackQuery) -> None:
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📐 <b>Aspect ratio</b>\n\nВыбери значение из опубликованной NexusAPI-спеки "
        "или «Авто», чтобы поле вообще не отправлялось.",
        reply_markup=_ratio_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("nxt:ratio:"))
async def nexus_ratio_set(call: CallbackQuery, state: FSMContext) -> None:
    key = str(call.data or "").rsplit(":", 1)[-1]
    if key not in _RATIO_CALLBACKS:
        await safe_answer_callback(call, "Неизвестный формат", show_alert=True)
        return
    await _change_request(state, nexus_aspect_ratio=_RATIO_CALLBACKS[key])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:seed")
async def nexus_seed_menu(call: CallbackQuery) -> None:
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎲 <b>Seed</b>\n\nNexusAPI публикует seed как int, но публичная модель-спека "
        "не задаёт диапазон. Поэтому тест не придумывает собственный лимит.",
        reply_markup=_seed_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:seed:auto")
async def nexus_seed_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_seed=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Seed убран")


@router.callback_query(F.data == "nxt:seed:custom")
async def nexus_seed_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NexusTestFSM.awaiting_seed)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎲 <b>Введите seed</b>\n\nТолько целое число.",
        reply_markup=_seed_kb(),
    )
    await safe_answer_callback(call)


@router.message(NexusTestFSM.awaiting_seed, F.text)
async def nexus_seed_save(message: Message, state: FSMContext) -> None:
    raw = str(message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.answer("Нужен целый seed, например <code>12345</code>.")
        return
    await _change_request(state, nexus_seed=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:reference")
async def nexus_reference_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NexusTestFSM.awaiting_reference)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🖼 <b>Reference image</b>\n\nПришли фото, image-документ или публичный HTTP(S) URL. "
        "NexusAPI получит его в <code>image_url</code>.",
        reply_markup=_reference_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:reference:clear")
async def nexus_reference_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_image_url=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Референс убран")


@router.message(NexusTestFSM.awaiting_reference, F.photo)
async def nexus_reference_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    url = await mirror_telegram_file(bot, best.file_id)
    await _change_request(state, nexus_image_url=url, nexus_mode="edit")
    await _answer_dashboard(message, state)


@router.message(NexusTestFSM.awaiting_reference, F.document)
async def nexus_reference_document(message: Message, state: FSMContext, bot: Bot) -> None:
    document = message.document
    mime = str(getattr(document, "mime_type", "") or "").lower() if document else ""
    if not document or not mime.startswith("image/"):
        await message.answer(
            "Пришли именно изображение как фото или image-документ.",
            reply_markup=_reference_kb(),
        )
        return
    telegram_file = await bot.get_file(document.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    url = save_public_file(raw, mime, subdir="nexusapi-test")
    await _change_request(state, nexus_image_url=url, nexus_mode="edit")
    await _answer_dashboard(message, state)


@router.message(NexusTestFSM.awaiting_reference, F.text)
async def nexus_reference_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_nano_banana_pro_params(prompt="test", image_url=value)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)), reply_markup=_reference_kb())
        return
    await _change_request(state, nexus_image_url=value, nexus_mode="edit")
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:webhook")
async def nexus_webhook_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NexusTestFSM.awaiting_webhook)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🔗 <b>Webhook URL</b>\n\nПоле опциональное. Пришли контролируемый публичный HTTP(S) URL. "
        "Даже с webhook тест продолжает polling, чтобы независимо проверить task API.",
        reply_markup=_webhook_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:webhook:clear")
async def nexus_webhook_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_webhook_url=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Webhook выключен")


@router.message(NexusTestFSM.awaiting_webhook, F.text)
async def nexus_webhook_save(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_nano_banana_pro_params(prompt="test", webhook_url=value)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)), reply_markup=_webhook_kb())
        return
    await _change_request(state, nexus_webhook_url=value)
    await _answer_dashboard(message, state)


def _current_request(data: dict[str, Any]) -> dict[str, Any]:
    image_url = data.get("nexus_image_url") if data.get("nexus_mode") == "edit" else None
    params = build_nano_banana_pro_params(
        prompt=str(data.get("nexus_prompt") or ""),
        aspect_ratio=data.get("nexus_aspect_ratio"),
        seed=data.get("nexus_seed"),
        image_url=image_url,
        webhook_url=data.get("nexus_webhook_url"),
    )
    return {"params": params}


@router.callback_query(F.data == "nxt:payload")
async def nexus_payload(call: CallbackQuery, state: FSMContext) -> None:
    data = await _ensure_data(state)
    try:
        payload = _current_request(data)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    text = (
        "📋 <b>Фактический POST /generate</b>\n\n<pre>"
        + html.escape(pretty_json(payload, max_chars=3000))
        + "</pre>"
    )
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:catalog")
async def nexus_catalog(call: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(call, "Проверяю NexusAPI…")
    data = await _ensure_data(state)
    client = NexusApiClient()
    try:
        result = await client.get_public_models()
        entry = find_model_in_catalog(result.payload)
        detail = (
            pretty_json(entry, max_chars=2600)
            if entry is not None
            else "Модель nano-banana-pro не найдена в ответе /public/models.\n\n"
            + pretty_json(result.payload, max_chars=2400)
        )
        text = (
            "🌐 <b>NexusAPI live catalog</b>\n\n"
            f"HTTP: <b>{result.status_code}</b> · {result.elapsed_ms} ms\n"
            f"Model: <code>{NEXUS_NANO_BANANA_PRO_MODEL}</code>\n\n"
            f"<pre>{html.escape(detail)}</pre>"
        )
    except NexusApiError as exc:
        text = "❌ <b>Не удалось получить /public/models</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


@router.callback_query(F.data == "nxt:status")
async def nexus_last_status(call: CallbackQuery, state: FSMContext) -> None:
    data = await _ensure_data(state)
    task_id = str(data.get("nexus_last_task_id") or "").strip()
    if not task_id:
        await safe_answer_callback(call, "Задач ещё нет", show_alert=True)
        return
    await safe_answer_callback(call, "Проверяю статус…")
    try:
        payload = await NexusApiClient().get_task(task_id)
        text = (
            "🔎 <b>NexusAPI task</b>\n\n<pre>"
            + html.escape(pretty_json(payload, max_chars=3000))
            + "</pre>"
        )
    except NexusApiError as exc:
        text = "❌ <b>Ошибка проверки task</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


async def _send_nexus_result(message: Message, task_payload: dict[str, Any]) -> int:
    sent = 0
    for index, url in enumerate(extract_result_urls(task_payload)[:4], start=1):
        try:
            await message.answer_photo(
                URLInputFile(url, filename=f"nexus-nano-banana-pro-{index}.png"),
                caption=f"✅ NexusAPI result #{index}",
            )
        except Exception as exc:
            logger.warning("Failed to send NexusAPI result URL through Telegram: %s", exc)
            await message.answer(f"✅ Result #{index}:\n{html.escape(url)}")
        sent += 1

    if sent:
        return sent

    for index, raw in enumerate(extract_result_base64(task_payload)[:4], start=1):
        try:
            await message.answer_photo(
                BufferedInputFile(raw, filename=f"nexus-nano-banana-pro-{index}.png"),
                caption=f"✅ NexusAPI result #{index}",
            )
            sent += 1
        except TelegramBadRequest as exc:
            logger.warning("Failed to send NexusAPI base64 result through Telegram: %s", exc)
    return sent


def _nexus_error_text(exc: Exception) -> str:
    if isinstance(exc, NexusApiTimeout):
        return (
            "⏱ NexusAPI не завершил задачу за тестовый таймаут. Task ID сохранён — "
            "статус можно проверить кнопкой."
        )
    if isinstance(exc, NexusApiError):
        prefix = {
            401: "🔑 Ключ NexusAPI отклонён.",
            402: "💳 На NexusAPI недостаточно средств.",
            422: "🧩 NexusAPI отклонил параметры модели или Idempotency-Key.",
            429: "🚦 NexusAPI вернул rate limit.",
        }.get(exc.status_code, "❌ Ошибка NexusAPI.")
        return f"{prefix}\n\n{html.escape(str(exc))}"
    return "❌ Ошибка теста: " + html.escape(str(exc))


@router.callback_query(F.data == "nxt:run")
async def nexus_run(call: CallbackQuery, state: FSMContext) -> None:
    data = await _ensure_data(state)
    client = NexusApiClient()
    if not client.configured:
        await safe_answer_callback(call, "Сначала задай NEXUS_API_KEY на сервере", show_alert=True)
        return
    try:
        request_payload = _current_request(data)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    if data.get("nexus_mode") == "edit" and not data.get("nexus_image_url"):
        await safe_answer_callback(call, "Для Edit сначала добавь референс", show_alert=True)
        return

    await safe_answer_callback(call, "Тест запущен")
    status_message = await call.message.answer(  # type: ignore[union-attr]
        "🧪 <b>NexusAPI test</b>\n\nСоздаю платную задачу nano-banana-pro…"
    )
    try:
        params = request_payload["params"]
        created = await client.create_nano_banana_pro(
            prompt=params["prompt"],
            aspect_ratio=params.get("aspect_ratio"),
            seed=params.get("seed"),
            image_url=params.get("image_url"),
            webhook_url=params.get("webhook_url"),
            idempotency_key=str(data["nexus_idempotency_key"]),
        )
        await state.update_data(nexus_last_task_id=created.task_id)
        await status_message.edit_text(
            "🧪 <b>NexusAPI test</b>\n\n"
            f"✅ POST /generate: HTTP {created.status_code} · {created.elapsed_ms} ms\n"
            f"Task: <code>{html.escape(created.task_id)}</code>\n"
            "⏳ Polling результата…"
        )
        finished = await client.wait_for_task(created.task_id)
        final_data = await _ensure_data(state)
        history = " → ".join(finished.status_history) or finished.status
        if finished.failed:
            error = finished.payload.get("error") or "NexusAPI task failed"
            await status_message.edit_text(
                "❌ <b>NexusAPI generation failed</b>\n\n"
                f"Task: <code>{html.escape(created.task_id)}</code>\n"
                f"Statuses: <code>{html.escape(history)}</code>\n"
                f"Error: {html.escape(str(error))}",
                reply_markup=_dashboard_kb(final_data),
            )
            return

        media_count = await _send_nexus_result(call.message, finished.payload)  # type: ignore[arg-type]
        total_ms = created.elapsed_ms + finished.elapsed_ms
        report = (
            "✅ <b>NexusAPI test completed</b>\n\n"
            f"Model: <code>{NEXUS_NANO_BANANA_PRO_MODEL}</code>\n"
            f"Mode: <b>{_mode_label(data)}</b>\n"
            f"POST /generate: HTTP <b>{created.status_code}</b> · {created.elapsed_ms} ms\n"
            f"Total provider time: <b>{total_ms / 1000:.2f} s</b>\n"
            f"Statuses: <code>{html.escape(history)}</code>\n"
            f"Task: <code>{html.escape(created.task_id)}</code>\n"
            f"Idempotency-Key: <code>{html.escape(created.idempotency_key)}</code>\n"
            f"Media returned: <b>{media_count}</b>\n\n"
            "<b>Request payload</b>\n"
            f"<pre>{html.escape(pretty_json(created.request_payload, max_chars=1500))}</pre>\n"
            "<b>Final task payload</b>\n"
            f"<pre>{html.escape(pretty_json(finished.payload, max_chars=1500))}</pre>"
        )
        await status_message.edit_text(report, reply_markup=_dashboard_kb(final_data))
    except Exception as exc:
        logger.exception("NexusAPI admin test failed")
        final_data = await _ensure_data(state)
        await status_message.edit_text(_nexus_error_text(exc), reply_markup=_dashboard_kb(final_data))


@router.callback_query(F.data == "nxt:reset")
async def nexus_reset(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Тест сброшен")
