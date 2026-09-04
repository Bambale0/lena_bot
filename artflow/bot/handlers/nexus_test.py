from __future__ import annotations

import html
import json
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
    NEXUS_NANO_BANANA_PRO_MAX_REFS,
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
    awaiting_overrides = State()


def _new_key() -> str:
    return str(uuid.uuid4())


def _initial_data() -> dict[str, Any]:
    return {
        "nexus_model": NEXUS_NANO_BANANA_PRO_MODEL,
        "nexus_mode": "text",
        "nexus_prompt": _DEFAULT_PROMPT,
        "nexus_aspect_ratio": None,
        "nexus_seed": None,
        "nexus_reference_urls": [],
        "nexus_webhook_url": None,
        "nexus_overrides": {},
        "nexus_idempotency_key": _new_key(),
        "nexus_last_task_id": None,
    }


async def _data(state: FSMContext) -> dict[str, Any]:
    data = await state.get_data()
    if data.get("nexus_model") != NEXUS_NANO_BANANA_PRO_MODEL:
        defaults = _initial_data()
        await state.update_data(**defaults)
        return {**data, **defaults}
    if not data.get("nexus_idempotency_key"):
        key = _new_key()
        await state.update_data(nexus_idempotency_key=key)
        data = {**data, "nexus_idempotency_key": key}
    return data


async def _change_request(state: FSMContext, **changes: Any) -> None:
    await state.update_data(**changes, nexus_idempotency_key=_new_key())


def _refs(data: dict[str, Any]) -> list[str]:
    values = data.get("nexus_reference_urls") or []
    return [str(value) for value in values if str(value or "").strip()]


def _overrides(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("nexus_overrides")
    return dict(value) if isinstance(value, dict) else {}


def _clip(value: Any, limit: int = 420) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _mode_label(data: dict[str, Any]) -> str:
    return "Image edit / refs" if data.get("nexus_mode") == "edit" else "Text → Image"


def _dashboard_text(data: dict[str, Any]) -> str:
    client = NexusApiClient()
    refs = _refs(data)
    overrides = _overrides(data)
    key_state = "✅ настроен" if client.configured else "❌ NEXUS_API_KEY не задан"
    text = (
        "🧪 <b>NexusAPI · Nano Banana Pro Lab</b>\n\n"
        "Изолированный админский контур: APIX-кредиты не списываются и боевой provider routing "
        "не меняется. Платный запуск расходует только баланс NexusAPI.\n\n"
        f"🔑 Key: <b>{key_state}</b>\n"
        f"🌐 Base: <code>{html.escape(client.base_url)}</code>\n"
        f"🤖 Model: <code>{NEXUS_NANO_BANANA_PRO_MODEL}</code>\n"
        f"🧭 Mode: <b>{_mode_label(data)}</b>\n"
        f"📐 Ratio: <b>{html.escape(str(data.get('nexus_aspect_ratio') or 'Авто'))}</b>\n"
        f"🎲 Seed: <b>{html.escape(str(data.get('nexus_seed') if data.get('nexus_seed') is not None else 'Авто'))}</b>\n"
        f"🖼 Refs: <b>{len(refs)}/{NEXUS_NANO_BANANA_PRO_MAX_REFS}</b>\n"
        f"🔗 Webhook: <b>{'вкл' if data.get('nexus_webhook_url') else 'выкл'}</b>\n"
        f"🧰 Raw overrides: <b>{len(overrides)} полей</b>\n"
        f"🛡 Request ID: <code>{html.escape(str(data.get('nexus_idempotency_key') or ''))}</code>\n\n"
        f"✍️ <b>Prompt</b>\n{html.escape(_clip(data.get('nexus_prompt'), 500))}"
    )
    if data.get("nexus_last_task_id"):
        text += f"\n\nПоследний task: <code>{html.escape(str(data['nexus_last_task_id']))}</code>"
    if refs:
        text += "\nRefs:\n" + "\n".join(
            f"{index}. <code>{html.escape(_clip(url, 180))}</code>"
            for index, url in enumerate(refs, start=1)
        )
    if overrides:
        text += "\n\nOverrides:\n<pre>" + html.escape(pretty_json(overrides, max_chars=900)) + "</pre>"
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
            text=("✅ " if not text_mode else "") + "🖼 Edit/Refs",
            callback_data="nxt:mode:edit",
        ),
    )
    builder.row(InlineKeyboardButton(text="✍️ Промпт", callback_data="nxt:prompt"))
    builder.row(
        InlineKeyboardButton(
            text=f"📐 {data.get('nexus_aspect_ratio') or 'Авто'}",
            callback_data="nxt:ratio",
        ),
        InlineKeyboardButton(
            text=f"🎲 {data.get('nexus_seed') if data.get('nexus_seed') is not None else 'Авто'}",
            callback_data="nxt:seed",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=f"🖼 Референсы · {len(_refs(data))}/{NEXUS_NANO_BANANA_PRO_MAX_REFS}",
            callback_data="nxt:reference",
        ),
        InlineKeyboardButton(
            text=f"🔗 Webhook · {'вкл' if data.get('nexus_webhook_url') else 'выкл'}",
            callback_data="nxt:webhook",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🧬 Live OpenAPI", callback_data="nxt:schema"),
        InlineKeyboardButton(text="💰 Live каталог", callback_data="nxt:catalog"),
    )
    builder.row(
        InlineKeyboardButton(text="🧰 Raw overrides", callback_data="nxt:overrides"),
        InlineKeyboardButton(text="📋 Итоговый payload", callback_data="nxt:payload"),
    )
    if data.get("nexus_last_task_id"):
        builder.row(
            InlineKeyboardButton(text="🔎 Статус task", callback_data="nxt:status")
        )
    builder.row(InlineKeyboardButton(text="🚀 Запустить платный тест", callback_data="nxt:run"))
    builder.row(
        InlineKeyboardButton(text="🆕 Новый Request ID", callback_data="nxt:newkey"),
        InlineKeyboardButton(text="♻️ Сбросить", callback_data="nxt:reset"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _back(callback: str = "nxt:dashboard"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=callback))
    return builder.as_markup()


def _ratio_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Авто / omit", callback_data="nxt:ratio:auto"))
    for key, ratio in _RATIO_CALLBACKS.items():
        if ratio:
            builder.button(text=ratio, callback_data=f"nxt:ratio:{key}")
    builder.adjust(1, 2, 2, 1)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _seed_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Авто / omit", callback_data="nxt:seed:auto"))
    builder.row(InlineKeyboardButton(text="✍️ Ввести seed", callback_data="nxt:seed:custom"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _reference_kb(data: dict[str, Any]):
    builder = InlineKeyboardBuilder()
    if _refs(data):
        builder.row(InlineKeyboardButton(text="🗑 Очистить refs", callback_data="nxt:reference:clear"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _webhook_kb(data: dict[str, Any]):
    builder = InlineKeyboardBuilder()
    if data.get("nexus_webhook_url"):
        builder.row(InlineKeyboardButton(text="🔕 Выключить webhook", callback_data="nxt:webhook:clear"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


def _overrides_kb(data: dict[str, Any]):
    builder = InlineKeyboardBuilder()
    if _overrides(data):
        builder.row(InlineKeyboardButton(text="🗑 Очистить overrides", callback_data="nxt:overrides:clear"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="nxt:dashboard"))
    return builder.as_markup()


async def _show_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(NexusTestFSM.dashboard)
    await safe_edit_message(message, _dashboard_text(data), reply_markup=_dashboard_kb(data))


async def _answer_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(NexusTestFSM.dashboard)
    await message.answer(_dashboard_text(data), reply_markup=_dashboard_kb(data))


def _current_params(data: dict[str, Any]) -> dict[str, Any]:
    refs = _refs(data) if data.get("nexus_mode") == "edit" else []
    image_urls = refs or None
    return build_nano_banana_pro_params(
        prompt=str(data.get("nexus_prompt") or ""),
        aspect_ratio=data.get("nexus_aspect_ratio"),
        seed=data.get("nexus_seed"),
        image_urls=image_urls,
        webhook_url=data.get("nexus_webhook_url"),
        extra_params=_overrides(data),
    )


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
    await state.update_data(nexus_idempotency_key=_new_key())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Новый Request ID")


@router.callback_query(F.data.startswith("nxt:mode:"))
async def nexus_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = str(call.data or "").rsplit(":", 1)[-1]
    if mode not in {"text", "edit"}:
        await safe_answer_callback(call, "Неизвестный режим", show_alert=True)
        return
    await _change_request(state, nexus_mode=mode)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:prompt")
async def nexus_prompt_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NexusTestFSM.awaiting_prompt)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✍️ <b>Prompt</b>\n\nПришли новый промпт одним сообщением.",
        reply_markup=_back(),
    )
    await safe_answer_callback(call)


@router.message(NexusTestFSM.awaiting_prompt, F.text)
async def nexus_prompt_save(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    if not value:
        await message.answer("Промпт не может быть пустым.")
        return
    await _change_request(state, nexus_prompt=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:ratio")
async def nexus_ratio_menu(call: CallbackQuery) -> None:
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📐 <b>Aspect ratio</b>\n\nКнопки соответствуют статической Nano Banana Pro документации. "
        "Если live OpenAPI покажет новое значение — его можно передать через Raw overrides.",
        reply_markup=_ratio_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("nxt:ratio:"))
async def nexus_ratio_set(call: CallbackQuery, state: FSMContext) -> None:
    key = str(call.data or "").rsplit(":", 1)[-1]
    if key not in _RATIO_CALLBACKS:
        await safe_answer_callback(call, "Неизвестный ratio", show_alert=True)
        return
    await _change_request(state, nexus_aspect_ratio=_RATIO_CALLBACKS[key])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:seed")
async def nexus_seed_menu(call: CallbackQuery) -> None:
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎲 <b>Seed</b>\n\nПубличная схема указывает int без диапазона, поэтому локальный тест "
        "не выдумывает min/max.",
        reply_markup=_seed_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:seed:auto")
async def nexus_seed_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_seed=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:seed:custom")
async def nexus_seed_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NexusTestFSM.awaiting_seed)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎲 Пришли целый seed, например <code>12345</code>.",
        reply_markup=_back(),
    )
    await safe_answer_callback(call)


@router.message(NexusTestFSM.awaiting_seed, F.text)
async def nexus_seed_save(message: Message, state: FSMContext) -> None:
    try:
        value = int(str(message.text or "").strip())
    except ValueError:
        await message.answer("Нужен целый seed.")
        return
    await _change_request(state, nexus_seed=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:reference")
async def nexus_reference_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    if len(_refs(data)) >= NEXUS_NANO_BANANA_PRO_MAX_REFS:
        await safe_answer_callback(call, "Уже добавлено 4 референса", show_alert=True)
        return
    await state.set_state(NexusTestFSM.awaiting_reference)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🖼 <b>Добавить reference</b>\n\nПришли фото, image-документ или публичный HTTP(S) URL. "
        "Все 1–4 refs отправляются как <code>image_urls</code> — это текущий контракт Nano Banana Pro. "
        "Так Nexus гарантированно запускает image-edit, а не обычный text-to-image.",
        reply_markup=_reference_kb(data),
    )
    await safe_answer_callback(call)


async def _append_reference(state: FSMContext, url: str) -> None:
    data = await _data(state)
    refs = _refs(data)
    if url not in refs:
        refs.append(url)
    if len(refs) > NEXUS_NANO_BANANA_PRO_MAX_REFS:
        raise ValueError("Maximum 4 references")
    await _change_request(state, nexus_reference_urls=refs, nexus_mode="edit")


@router.callback_query(F.data == "nxt:reference:clear")
async def nexus_reference_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_reference_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Refs очищены")


@router.message(NexusTestFSM.awaiting_reference, F.photo)
async def nexus_reference_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    await _append_reference(state, await mirror_telegram_file(bot, best.file_id))
    await _answer_dashboard(message, state)


@router.message(NexusTestFSM.awaiting_reference, F.document)
async def nexus_reference_document(message: Message, state: FSMContext, bot: Bot) -> None:
    document = message.document
    mime = str(getattr(document, "mime_type", "") or "").lower() if document else ""
    if not document or not mime.startswith("image/"):
        await message.answer("Нужен image-документ.")
        return
    telegram_file = await bot.get_file(document.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    url = save_public_file(raw, mime, subdir="nexusapi-test")
    await _append_reference(state, url)
    await _answer_dashboard(message, state)


@router.message(NexusTestFSM.awaiting_reference, F.text)
async def nexus_reference_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_nano_banana_pro_params(prompt="validation", image_url=value)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _append_reference(state, value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:webhook")
async def nexus_webhook_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(NexusTestFSM.awaiting_webhook)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🔗 <b>Webhook URL</b>\n\nПришли контролируемый публичный HTTP(S) URL. "
        "Тест всё равно продолжит polling, чтобы независимо проверить task API.",
        reply_markup=_webhook_kb(data),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:webhook:clear")
async def nexus_webhook_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_webhook_url=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(NexusTestFSM.awaiting_webhook, F.text)
async def nexus_webhook_save(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_nano_banana_pro_params(prompt="validation", webhook_url=value)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _change_request(state, nexus_webhook_url=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:overrides")
async def nexus_overrides_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(NexusTestFSM.awaiting_overrides)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🧰 <b>Raw model overrides</b>\n\n"
        "Сначала открой «Live OpenAPI», затем пришли JSON-object с любыми дополнительными "
        "полями живой схемы. Например: <code>{\"image_urls\":[\"https://...\"]}</code>.\n\n"
        "Overrides сливаются в params последними. <code>model_name</code> и <code>prompt</code> "
        "защищены и не могут быть подменены здесь. Неизвестные поля намеренно уйдут в Nexus — "
        "так можно проверить реальную 422-валидацию провайдера.",
        reply_markup=_overrides_kb(data),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:overrides:clear")
async def nexus_overrides_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, nexus_overrides={})
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Overrides очищены")


@router.message(NexusTestFSM.awaiting_overrides, F.text)
async def nexus_overrides_save(message: Message, state: FSMContext) -> None:
    try:
        value = json.loads(str(message.text or ""))
    except json.JSONDecodeError as exc:
        await message.answer(f"Некорректный JSON: {html.escape(str(exc))}")
        return
    if not isinstance(value, dict):
        await message.answer("Нужен JSON object: <code>{...}</code>")
        return
    value.pop("model_name", None)
    value.pop("prompt", None)
    await _change_request(state, nexus_overrides=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "nxt:schema")
async def nexus_schema(call: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(call, "Читаю live OpenAPI…")
    data = await _data(state)
    try:
        result = await NexusApiClient().get_model_schema()
        text = (
            "🧬 <b>Live Nexus OpenAPI</b>\n\n"
            f"Model: <code>{result.model_name}</code>\n"
            f"Schema: <code>{html.escape(result.schema_name)}</code> · {result.elapsed_ms} ms\n\n"
            f"<pre>{html.escape(pretty_json(result.schema, max_chars=3000))}</pre>"
        )
    except NexusApiError as exc:
        text = "❌ <b>OpenAPI schema error</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


@router.callback_query(F.data == "nxt:catalog")
async def nexus_catalog(call: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(call, "Читаю live каталог…")
    data = await _data(state)
    try:
        result = await NexusApiClient().get_public_models()
        entry = find_model_in_catalog(result.payload)
        detail = entry if entry is not None else result.payload
        text = (
            "💰 <b>Live Nexus catalog</b>\n\n"
            f"HTTP {result.status_code} · {result.elapsed_ms} ms\n\n"
            f"<pre>{html.escape(pretty_json(detail, max_chars=3000))}</pre>"
        )
    except NexusApiError as exc:
        text = "❌ <b>Catalog error</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


@router.callback_query(F.data == "nxt:payload")
async def nexus_payload(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    try:
        payload = {"params": _current_params(data)}
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📋 <b>Точный POST /generate payload</b>\n\n"
        f"<pre>{html.escape(pretty_json(payload, max_chars=3200))}</pre>",
        reply_markup=_dashboard_kb(data),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:status")
async def nexus_status(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    task_id = str(data.get("nexus_last_task_id") or "").strip()
    if not task_id:
        await safe_answer_callback(call, "Task ещё нет", show_alert=True)
        return
    await safe_answer_callback(call, "Проверяю task…")
    try:
        payload = await NexusApiClient().get_task(task_id)
        text = "🔎 <b>Nexus task</b>\n\n<pre>" + html.escape(
            pretty_json(payload, max_chars=3200)
        ) + "</pre>"
    except NexusApiError as exc:
        text = "❌ <b>Task error</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


async def _send_results(message: Message, payload: dict[str, Any]) -> int:
    count = 0
    for index, url in enumerate(extract_result_urls(payload)[:4], start=1):
        try:
            await message.answer_photo(
                URLInputFile(url, filename=f"nexus-nano-banana-pro-{index}.png"),
                caption=f"✅ Nexus result #{index}",
            )
        except Exception as exc:
            logger.warning("Nexus result URL delivery failed: %s", exc)
            await message.answer(f"✅ Result #{index}:\n{html.escape(url)}")
        count += 1
    if count:
        return count
    for index, raw in enumerate(extract_result_base64(payload)[:4], start=1):
        try:
            await message.answer_photo(
                BufferedInputFile(raw, filename=f"nexus-nano-banana-pro-{index}.png"),
                caption=f"✅ Nexus result #{index}",
            )
            count += 1
        except TelegramBadRequest as exc:
            logger.warning("Nexus base64 result delivery failed: %s", exc)
    return count


def _error_text(exc: Exception) -> str:
    if isinstance(exc, NexusApiTimeout):
        return "⏱ Task не завершился за тестовый timeout. Task ID сохранён для ручной проверки."
    if isinstance(exc, NexusApiError):
        prefix = {
            401: "🔑 API key отклонён.",
            402: "💳 Недостаточный Nexus balance.",
            422: "🧩 Nexus отклонил params / Request ID.",
            429: "🚦 Nexus rate limit.",
        }.get(exc.status_code, "❌ NexusAPI error.")
        return prefix + "\n\n" + html.escape(str(exc))
    return "❌ Test error: " + html.escape(str(exc))


@router.callback_query(F.data == "nxt:run")
async def nexus_run(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    client = NexusApiClient()
    if not client.configured:
        await safe_answer_callback(call, "На сервере нет NEXUS_API_KEY", show_alert=True)
        return
    try:
        params = _current_params(data)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    has_refs = bool(params.get("image_url") or params.get("image_urls"))
    if data.get("nexus_mode") == "edit" and not has_refs:
        await safe_answer_callback(call, "Для Edit добавь ref или image_url(s) override", show_alert=True)
        return

    await safe_answer_callback(call, "Платный Nexus test запущен")
    status_message = await call.message.answer(  # type: ignore[union-attr]
        "🧪 <b>NexusAPI</b>\n\nPOST /generate…"
    )
    try:
        created = await client.create_params(
            params,
            idempotency_key=str(data["nexus_idempotency_key"]),
        )
        await state.update_data(nexus_last_task_id=created.task_id)
        await status_message.edit_text(
            "🧪 <b>NexusAPI</b>\n\n"
            f"✅ POST: HTTP {created.status_code} · {created.elapsed_ms} ms\n"
            f"Task: <code>{html.escape(created.task_id)}</code>\n"
            "⏳ polling…"
        )
        finished = await client.wait_for_task(created.task_id)
        final_data = await _data(state)
        history = " → ".join(finished.status_history) or finished.status
        if finished.failed:
            await status_message.edit_text(
                "❌ <b>Nexus task failed</b>\n\n"
                f"Task: <code>{html.escape(created.task_id)}</code>\n"
                f"States: <code>{html.escape(history)}</code>\n"
                f"Error: {html.escape(str(finished.payload.get('error') or 'unknown'))}\n\n"
                f"<pre>{html.escape(pretty_json(finished.payload, max_chars=1800))}</pre>",
                reply_markup=_dashboard_kb(final_data),
            )
            return
        media_count = await _send_results(call.message, finished.payload)  # type: ignore[arg-type]
        total_ms = created.elapsed_ms + finished.elapsed_ms
        await status_message.edit_text(
            "✅ <b>Nexus test completed</b>\n\n"
            f"Task: <code>{html.escape(created.task_id)}</code>\n"
            f"POST: <b>{created.elapsed_ms} ms</b>\n"
            f"Total: <b>{total_ms / 1000:.2f} s</b>\n"
            f"States: <code>{html.escape(history)}</code>\n"
            f"Media: <b>{media_count}</b>\n"
            f"Request ID: <code>{html.escape(created.idempotency_key)}</code>\n\n"
            "<b>Request</b>\n"
            f"<pre>{html.escape(pretty_json(created.request_payload, max_chars=1200))}</pre>\n"
            "<b>Final task</b>\n"
            f"<pre>{html.escape(pretty_json(finished.payload, max_chars=1500))}</pre>",
            reply_markup=_dashboard_kb(final_data),
        )
    except Exception as exc:
        logger.exception("NexusAPI admin evaluation failed")
        final_data = await _data(state)
        await status_message.edit_text(_error_text(exc), reply_markup=_dashboard_kb(final_data))


@router.callback_query(F.data == "nxt:reset")
async def nexus_reset(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Lab сброшен")
