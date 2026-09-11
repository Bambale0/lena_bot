from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api.music_service import create_music_task, register_miniapp_task, register_task
from api.suno_source_audio import create_source_audio_generation, upload_source_audio
from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import MusicFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import GenerationType, User

MUSIC_MODEL_KEY = "suno/v5.5"
DEFAULT_MUSIC_CREDITS = 20
_MUSIC_MODEL_FALLBACK_KEYS = ["suno/v5.5", "suno/v5.0", "suno/v4.5"]

router = Router(name="music_gen")


async def _resolve_active_music_model(session: AsyncSession):
    model_cost = await repo.get_first_active_model_cost(session, _MUSIC_MODEL_FALLBACK_KEYS)
    if model_cost and getattr(model_cost, "gen_type", None) == GenerationType.music:
        return model_cost
    model_cost = await repo.get_model_cost(session, MUSIC_MODEL_KEY)
    if model_cost and getattr(model_cost, "is_active", True):
        return model_cost
    all_costs = await repo.get_all_model_costs(session)
    for item in all_costs:
        if getattr(item, "gen_type", None) == GenerationType.music and getattr(item, "is_active", True):
            return item
    return None


async def _resolve_music_model_for_key(session: AsyncSession, model_key: str | None):
    key = str(model_key or "").strip()
    if key:
        model_cost = await repo.get_model_cost(session, key)
        if (
            model_cost
            and getattr(model_cost, "gen_type", None) == GenerationType.music
            and getattr(model_cost, "is_active", True)
        ):
            return model_cost
    return await _resolve_active_music_model(session)


def _music_model_title(model_key: str | None) -> str:
    key = str(model_key or "").lower()
    if "5.5" in key or "v5_5" in key:
        return "Suno 5.5"
    if "5" in key:
        return "Suno 5"
    if "4.5" in key or "v4_5" in key:
        return "Suno 4.5"
    return "Suno"


def _source_actions_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎛 Cover / изменить стиль", callback_data="music:source:cover")],
            [InlineKeyboardButton(text="➕ Продолжить трек", callback_data="music:source:extend")],
            [InlineKeyboardButton(text="🎤 Добавить вокал", callback_data="music:source:add_vocals")],
            [InlineKeyboardButton(text="🎹 Добавить инструментал", callback_data="music:source:add_instrumental")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


def _review_kb(cost: float, *, affordable: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if affordable:
        rows.append([InlineKeyboardButton(text=f"🚀 Создать за {cost:g} 💋", callback_data="music:review:launch")])
    else:
        rows.append([InlineKeyboardButton(text="💋 Пополнить баланс", callback_data="menu:balance")])
    rows.append([InlineKeyboardButton(text="✏️ Изменить описание", callback_data="music:review:edit")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _source_operation_label(operation: str) -> str:
    return {
        "cover": "Изменить стиль",
        "extend": "Продолжить трек",
        "add_vocals": "Добавить вокал",
        "add_instrumental": "Добавить инструментал",
    }.get(operation, "Обработка аудио")


def _review_text(data: dict, *, balance: float, cost: float) -> str:
    model_name = str(data.get("music_model_name") or "Suno")
    prompt = str(data.get("music_review_prompt") or "").strip()
    kind = str(data.get("music_review_kind") or "prompt")
    if kind == "source":
        mode_label = _source_operation_label(str(data.get("music_review_operation") or ""))
    else:
        mode_label = "Без текста" if data.get("instrumental") else "С текстом"
    after = max(0.0, float(balance) - float(cost))
    return (
        "🎵 <b>Проверь перед запуском</b>\n\n"
        f"Модель: <b>{model_name}</b>\n"
        f"Режим: <b>{mode_label}</b>\n"
        f"Стоимость: <b>{cost:g} 💋</b>\n"
        f"После запуска останется: <b>{after:g} 💋</b>\n\n"
        f"Описание:\n<i>{prompt}</i>\n\n"
        "💋 спишутся только после нажатия «Создать»."
    )


async def _show_music_review(message: Message, state: FSMContext, db_user: User, *, cost: float) -> None:
    data = await state.get_data()
    affordable = float(db_user.credits or 0) >= float(cost)
    await state.set_state(MusicFSM.review)
    await message.answer(
        _review_text(data, balance=float(db_user.credits or 0), cost=cost),
        reply_markup=_review_kb(cost, affordable=affordable),
    )


@router.callback_query(F.data == "menu:music")
async def music_menu(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=False)
    model_cost = await _resolve_active_music_model(session)
    music_cost = float(model_cost.credits) if model_cost else float(DEFAULT_MUSIC_CREDITS)
    music_model_name = _music_model_title(getattr(model_cost, "model_key", MUSIC_MODEL_KEY))
    await state.update_data(music_model_key=getattr(model_cost, "model_key", MUSIC_MODEL_KEY), music_model_name=music_model_name)
    screen = await render_screen(screen="music", session=session, db_user=db_user, extra={"music_cost": music_cost, "music_model_name": music_model_name})
    await call.message.answer(  # type: ignore[union-attr]
        screen.text + "\n\n🎧 <b>Есть свой трек?</b> Просто пришли сюда аудиофайл — можно сделать cover, продолжить его или добавить вокал/инструментал.",
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("music:mode:"))
async def music_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = call.data.split(":")[-1]  # type: ignore[union-attr]
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=(mode == "instrumental"))
    label = "без текста" if mode == "instrumental" else "с текстом"
    await call.message.answer(  # type: ignore[union-attr]
        f"🎵 Режим выбран: <b>{label}</b>\n\nТеперь напиши описание трека.\n\n🎧 Или пришли свой аудиофайл для обработки.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.message(F.text == "🎵 Песня")
async def music_entry(msg: Message, state: FSMContext):
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=False)
    await msg.answer("🎵 Напиши описание трека\n\n🎧 Или пришли свой аудиофайл для Cover / Extend / Vocals / Instrumental.", reply_markup=back_to_menu_kb())


@router.message(MusicFSM.prompt_input, F.audio | F.voice | F.document)
async def music_source_audio(msg: Message, state: FSMContext, bot: Bot):
    media = msg.audio or msg.voice or msg.document
    if media is None:
        return
    mime = str(getattr(media, "mime_type", "") or "").lower()
    filename = str(getattr(media, "file_name", "") or "")
    if msg.voice and not filename:
        filename = "voice.ogg"
    if msg.document and not (mime.startswith("audio/") or filename.lower().endswith((".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"))):
        await msg.answer("Пришли именно аудиофайл: MP3, WAV, M4A, AAC, FLAC, OGG или OPUS.")
        return

    try:
        telegram_file = await bot.get_file(media.file_id)
        downloaded = await bot.download_file(telegram_file.file_path)
        raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
        prepared = await upload_source_audio(raw, filename=filename or "source.mp3", content_type=mime or None)
    except ValueError as exc:
        await msg.answer(f"❌ {exc}", reply_markup=back_to_menu_kb())
        return
    except Exception:
        await msg.answer("❌ Не удалось подготовить аудио. Попробуй другой файл.", reply_markup=back_to_menu_kb())
        return

    await state.update_data(
        suno_source_url=prepared["url"],
        suno_source_duration=prepared["duration_seconds"],
        suno_source_filename=prepared["filename"],
        suno_source_operation=None,
    )
    await msg.answer(
        f"🎧 <b>Аудио готово</b> · {prepared['duration_seconds']:.1f} сек\n\nЧто сделать с исходником?",
        reply_markup=_source_actions_kb(),
    )


@router.callback_query(F.data.startswith("music:source:"))
async def music_source_action(call: CallbackQuery, state: FSMContext) -> None:
    operation = str(call.data or "").rsplit(":", 1)[-1]
    if operation not in {"cover", "extend", "add_vocals", "add_instrumental"}:
        await safe_answer_callback(call, "Неизвестное действие", show_alert=True)
        return
    data = await state.get_data()
    if not data.get("suno_source_url"):
        await safe_answer_callback(call, "Сначала пришли аудиофайл", show_alert=True)
        return
    await state.update_data(suno_source_operation=operation)
    await state.set_state(MusicFSM.source_prompt_input)
    if operation == "cover":
        text = "🎛 Напиши, каким должен стать трек: жанр, настроение, инструменты, вокал."
    elif operation == "extend":
        text = "➕ Напиши, как продолжить трек. Продолжение начнётся с конца загруженного аудио."
    elif operation == "add_vocals":
        text = "🎤 Пришли одной строкой:\n<b>Название | Стиль | Текст/описание вокала</b>"
    else:
        text = "🎹 Пришли одной строкой:\n<b>Название | Стиль инструментала</b>"
    await call.message.answer(text, reply_markup=back_to_menu_kb())  # type: ignore[union-attr]
    await safe_answer_callback(call)


@router.message(MusicFSM.source_prompt_input, F.text)
async def music_source_prompt(msg: Message, state: FSMContext, session: AsyncSession, db_user: User):
    data = await state.get_data()
    operation = str(data.get("suno_source_operation") or "")
    upload_url = str(data.get("suno_source_url") or "")
    source_duration = float(data.get("suno_source_duration") or 0)
    if not operation or not upload_url:
        await state.set_state(MusicFSM.prompt_input)
        await msg.answer("Сначала пришли аудиофайл.", reply_markup=back_to_menu_kb())
        return

    prompt = str(msg.text or "").strip()
    title = None
    style = None
    if operation == "add_vocals":
        parts = [part.strip() for part in prompt.split("|", 2)]
        if len(parts) != 3 or not all(parts):
            await msg.answer("Нужен формат: <b>Название | Стиль | Текст/описание вокала</b>")
            return
        title, style, prompt = parts
    elif operation == "add_instrumental":
        parts = [part.strip() for part in prompt.split("|", 1)]
        if len(parts) != 2 or not all(parts):
            await msg.answer("Нужен формат: <b>Название | Стиль инструментала</b>")
            return
        title, style = parts
        prompt = style

    selected_model_key = str(data.get("music_model_key") or MUSIC_MODEL_KEY)
    model_cost = await _resolve_music_model_for_key(session, selected_model_key)
    selected_model_key = str(getattr(model_cost, "model_key", None) or selected_model_key)
    music_cost = float(getattr(model_cost, "credits", DEFAULT_MUSIC_CREDITS) or DEFAULT_MUSIC_CREDITS)
    continue_at = max(0.1, source_duration - 0.5) if operation == "extend" else None
    await state.update_data(
        music_review_kind="source",
        music_review_prompt=prompt,
        music_review_operation=operation,
        music_review_upload_url=upload_url,
        music_review_style=style,
        music_review_title=title,
        music_review_continue_at=continue_at,
        music_review_source_duration=source_duration,
        music_review_cost=music_cost,
        music_model_key=selected_model_key,
        music_model_name=_music_model_title(selected_model_key),
    )
    await _show_music_review(msg, state, db_user, cost=music_cost)


@router.message(MusicFSM.prompt_input, F.text)
async def music_prompt(msg: Message, state: FSMContext, session: AsyncSession, db_user: User):
    data = await state.get_data()
    selected_model_key = str(data.get("music_model_key") or MUSIC_MODEL_KEY)
    model_cost = await _resolve_music_model_for_key(session, selected_model_key)
    selected_model_key = str(getattr(model_cost, "model_key", None) or selected_model_key)
    music_cost = float(model_cost.credits) if model_cost else float(DEFAULT_MUSIC_CREDITS)
    await state.update_data(
        music_review_kind="prompt",
        music_review_prompt=str(msg.text or "").strip(),
        music_review_cost=music_cost,
        music_model_key=selected_model_key,
        music_model_name=_music_model_title(selected_model_key),
    )
    await _show_music_review(msg, state, db_user, cost=music_cost)


@router.callback_query(F.data == "music:review:edit")
async def music_review_edit(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("music_review_prompt"):
        await safe_answer_callback(call, "Эта подготовка уже устарела", show_alert=True)
        return
    if data.get("music_review_kind") == "source":
        await state.set_state(MusicFSM.source_prompt_input)
        text = "✏️ Отправь новое описание для этой операции с аудио."
    else:
        await state.set_state(MusicFSM.prompt_input)
        text = "✏️ Отправь новое описание трека."
    await safe_edit_message(call.message, text, reply_markup=back_to_menu_kb())
    await safe_answer_callback(call)


@router.callback_query(F.data == "music:review:launch")
async def music_review_launch(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    prompt = str(data.get("music_review_prompt") or "").strip()
    if not prompt:
        await safe_answer_callback(call, "Эта подготовка уже устарела", show_alert=True)
        return

    selected_model_key = str(data.get("music_model_key") or MUSIC_MODEL_KEY)
    model_cost = await _resolve_music_model_for_key(session, selected_model_key)
    selected_model_key = str(getattr(model_cost, "model_key", None) or selected_model_key)
    current_cost = float(getattr(model_cost, "credits", DEFAULT_MUSIC_CREDITS) or DEFAULT_MUSIC_CREDITS)
    reviewed_cost = float(data.get("music_review_cost") or current_cost)
    if current_cost != reviewed_cost:
        await state.update_data(music_review_cost=current_cost)
        refreshed = {**data, "music_review_cost": current_cost}
        await safe_edit_message(
            call.message,
            _review_text(refreshed, balance=float(db_user.credits or 0), cost=current_cost),
            reply_markup=_review_kb(current_cost, affordable=float(db_user.credits or 0) >= current_cost),
        )
        await safe_answer_callback(call, "Цена обновилась — проверь ещё раз", show_alert=True)
        return

    if float(db_user.credits or 0) < current_cost:
        await safe_answer_callback(
            call,
            f"Недостаточно 💋. Нужно {current_cost:g}, у тебя {float(db_user.credits or 0):g}.",
            show_alert=True,
        )
        return

    await safe_edit_message(call.message, "⏳ <b>Запускаю музыку…</b>", reply_markup=None)
    await safe_answer_callback(call)

    if data.get("music_review_kind") == "source":
        try:
            gen = await create_source_audio_generation(
                session=session,
                user=db_user,
                operation=str(data.get("music_review_operation") or ""),
                upload_url=str(data.get("music_review_upload_url") or ""),
                prompt=prompt,
                model_key=selected_model_key,
                instrumental=bool(data.get("instrumental", False)),
                style=data.get("music_review_style"),
                title=data.get("music_review_title"),
                continue_at=data.get("music_review_continue_at"),
                source_duration=data.get("music_review_source_duration"),
                surface="telegram",
            )
            if gen.task_id:
                register_task(str(gen.task_id), call.from_user.id)
            await call.message.answer(
                "🎵 <b>Задача с твоим аудио запущена!</b>\n\nРезультат придёт сюда автоматически.",
                reply_markup=back_to_menu_kb(),
            )
        except PermissionError:
            await call.message.answer("😔 Не хватает 💋 для запуска. Пополни баланс и попробуй снова.", reply_markup=back_to_menu_kb())
        except ValueError:
            await call.message.answer("❌ Не удалось подготовить эту операцию. Проверь исходное аудио и описание.", reply_markup=back_to_menu_kb())
        except Exception:
            await call.message.answer("❌ Не удалось запустить обработку аудио. Попробуй ещё раз чуть позже.", reply_markup=back_to_menu_kb())
        await state.clear()
        return

    if not await repo.spend_credits(session, db_user.id, current_cost):
        await call.message.answer("😔 Не удалось списать 💋. Попробуй ещё раз.", reply_markup=back_to_menu_kb())
        await state.clear()
        return


    gen = None
    try:
        gen = await repo.create_generation(
            session,
            db_user.id,
            selected_model_key,
            GenerationType.music,
            prompt,
            current_cost,
        )
        task_id = await create_music_task(prompt, bool(data.get("instrumental", False)), model_key=selected_model_key)
        register_task(task_id, call.from_user.id)
        register_miniapp_task(task_id, gen.id)
        await repo.update_generation_task(session, gen.id, task_id)
        await call.message.answer(
            "🎵 <b>Генерация запущена!</b>\n\nТрек придёт сюда автоматически (~1–2 мин).",
            reply_markup=back_to_menu_kb(),
        )
    except Exception as exc:
        should_refund = gen is None
        if gen is not None:
            should_refund = await repo.fail_generation(session, gen.id, str(exc))
        if should_refund:
            await repo.add_credits(session, db_user.id, current_cost)
        await call.message.answer(
            "❌ Не удалось запустить генерацию. 💋 возвращены. Попробуй ещё раз чуть позже.",
            reply_markup=back_to_menu_kb(),
        )
    await state.clear()
