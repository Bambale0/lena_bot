"""Kling 4 automatic reference collector with optional character/voice controls."""

from __future__ import annotations

import re
import secrets
from copy import deepcopy
from html import escape
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from fastapi import HTTPException

from api.kling4_assets import MAX_ASSET_BYTES, store_kling4_asset
from api.kling4_contract import (
    KEYFRAME_MODEL,
    KLING4_MODELS,
    NAME,
    REFERENCE_MODEL,
    RESERVED,
    Kling4Input,
)
from core.kling4_access import kling4_visible, set_kling4_access

router = Router(name="kling4")


class Kling4FSM(StatesGroup):
    edit = State()
    text = State()
    media = State()
    confirm = State()


def keyboard(rows, revision=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=action
                    + (f":v{revision}" if revision and action.startswith("k4:") else ""),
                )
                for label, action in row
            ]
            for row in rows
        ]
    )


async def allowed(event, session, user):
    if await kling4_visible(session, user):
        return True
    if isinstance(event, CallbackQuery):
        await event.answer("Kling 4 пока доступен только администратору", show_alert=True)
    else:
        await event.answer("Kling 4 пока доступен только администратору")
    return False


async def render(message, state):
    data = await state.get_data()
    revision = secrets.token_hex(4)
    await state.update_data(k4_revision=revision, k4_field=None)
    options = Kling4Input(**data.get("kling4", {}))
    keyframe = data["model_key"] == KEYFRAME_MODEL
    lines = [
        "🎬 <b>Kling 4" + (" · Ключевые кадры из истории" if keyframe else "") + "</b>",
        f'{options.duration} сек · {options.resolution} · {options.aspect_ratio or "авто"}',
        "\nПромпт: " + escape(str(data.get("prompt") or "ещё не задан")[:500]),
    ]
    if keyframe:
        lines.append(
            f'Кадры: первый {"✓" if options.first_frame_url else "—"}, промежуточных {len(options.keyframe_urls)}, последний {"✓" if options.last_frame_url else "—"}'
        )
        media = [
            ("Первый кадр", "first_frame_url"),
            ("Промежуточные", "keyframe_urls"),
            ("Последний кадр", "last_frame_url"),
        ]
    else:
        lines.append(f"Фото: {len(options.image_urls)} · видео: {len(options.video_urls)}")
        media = [("Фото", "image_urls"), ("Видео", "video_urls")]
        for i, element in enumerate(options.elements):
            lines.append(
                f"Персонаж @{element.name}: {len(element.image_urls)} фото"
                if element.image_urls
                else f"Персонаж @{element.name}: видео"
            )
            media.append((f"Голос @{element.name}", f"bound_{i}"))
        lines.extend(f"Голос @{voice.name}" for voice in options.voices)
    lines.append(
        (
            "\nЭто заказ из истории. Для замены кадра выбери его кнопку. Ссылки в промпте: "
            if keyframe else
            "\nПришли описание и фото, видео или аудио в любом порядке. Тип референса определится автоматически. "
            "Описание можно добавить подписью к файлу. Материалы можно упомянуть в промпте: "
        )
        + (
            "@first_frame, @keyframe_1, @last_frame"
            if keyframe
            else "@image_1, @video_1, @Hero_1, @Voice_1"
        )
        + ". Цена появится перед запуском."
    )
    rows = [
        [("✏️ Промпт", "k4:text:prompt"), ("⏱ Длительность", "k4:text:duration")],
        [
            ("Качество " + options.resolution, "k4:resolution"),
            ("Формат " + (options.aspect_ratio or "auto"), "k4:ratio"),
        ],
    ]
    if keyframe or data.get("k4_advanced"):
        rows += [[(label, f"k4:media:{role}")] for label, role in media]
    if not keyframe and data.get("k4_advanced"):
        rows += [
            [("Персонаж по фото", "k4:element:image"), ("По видео", "k4:element:video")],
            [
                ("🎙 Голос", "k4:voice"),
                ("Исходный звук " + ("✓" if options.keep_original_sound else "—"), "k4:sound"),
            ],
        ]
    for field in ("image_urls", "video_urls", "keyframe_urls"):
        for index, _url in enumerate(getattr(options, field)):
            title = {"image_urls": "Фото", "video_urls": "Видео", "keyframe_urls": "Кадр"}[field]
            rows.append([(f"Убрать {title.lower()} {index+1}", f"k4:remove:{field}:{index}")])
    for index, item in enumerate(options.elements):
        rows += [
            [
                (f"Имя @{item.name}", f"k4:text:element_name_{index}"),
                ("Описание", f"k4:text:element_description_{index}"),
            ]
        ]
        if not item.video_url and not item.voice_url:
            rows.append(
                [
                    (
                        "Тип: "
                        + {
                            "character": "персонаж",
                            "animal": "животное",
                            "prop": "предмет",
                            "costume": "костюм",
                            "scene": "сцена",
                            "effect": "эффект",
                            "others": "другое",
                        }[item.tag or "character"],
                        f"k4:tag:{index}",
                    )
                ]
            )
        rows.append([(f"Удалить @{item.name}", f"k4:remove:elements:{index}")])
    for index, item in enumerate(options.voices):
        rows.append(
            [
                (f"Имя @{item.name}", f"k4:text:voice_name_{index}"),
                ("Удалить голос", f"k4:remove:voices:{index}"),
            ]
        )
    if not keyframe:
        rows.append([("Персонажи и голоса", "k4:advanced")])
    rows += [
        [("Очистить материалы", "k4:clear")],
        [("Рассчитать стоимость", "k4:quote")],
        [("← Видео", "menu:video")],
    ]
    await state.set_state(Kling4FSM.edit)
    await message.answer("\n".join(lines), reply_markup=keyboard(rows, revision=revision))


def next_material_name(options, prefix):
    names = {item["name"].lower() for key in ("elements", "voices") for item in options[key]}
    index = 1
    while f"{prefix}_{index}".lower() in names:
        index += 1
    return f"{prefix}_{index}"


def rename_material(options, prompt, collection, index, name):
    if not NAME.fullmatch(name) or RESERVED.fullmatch(name):
        raise ValueError("Имя: 1–20 латинских/китайских букв, цифр или _, без служебных имён")
    updated = deepcopy(options)
    target = updated[collection][index]
    other_names = [
        item["name"].lower()
        for group in ("elements", "voices")
        for i, item in enumerate(updated[group])
        if group != collection or i != index
    ]
    if name.lower() in other_names:
        raise ValueError("Это имя уже занято")
    old = target["name"]
    target["name"] = name
    return updated, re.sub(r"@" + re.escape(old) + r"(?!\w)", "@" + name, prompt)


async def start_kling4(call, state, session, db_user, model_key):
    if model_key not in KLING4_MODELS or not await allowed(call, session, db_user):
        return
    if (await state.get_data()).get("feed_force_reference"):
        await call.answer(
            "Текущий повтор сохранён. Открой новый заказ Kling 4 из меню видео",
            show_alert=True,
        )
        return
    await state.set_data(
        {"model_key": REFERENCE_MODEL, "kling4": Kling4Input().model_dump(), "intent_id": str(uuid4())}
    )
    await call.answer()
    await render(call.message, state)


@router.message(Command("kling4_access"))
async def rollout(message: Message, session, db_user):
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Администратор: /kling4_access admin | public | disabled")
        return
    try:
        audience = await set_kling4_access(
            session, parts[1], admin_tg_id=db_user.tg_id, source="bot"
        )
    except (HTTPException, ValueError):
        await message.answer("Нет доступа или неизвестный режим")
        return
    await message.answer(
        "Kling 4: "
        + {
            "admin": "только администраторы",
            "public": "доступен всем",
            "disabled": "новые запуски отключены",
        }[audience]
    )


@router.message(Command("kling4"))
async def open_kling4(message: Message, session, db_user, state):
    if not await allowed(message, session, db_user):
        return
    if (await state.get_data()).get("feed_force_reference"):
        await message.answer("Текущий повтор сохранён. Заверши его или открой новый заказ из меню видео.")
        return
    await state.set_data(
        {"model_key": REFERENCE_MODEL, "kling4": Kling4Input().model_dump(), "intent_id": str(uuid4())}
    )
    await render(message, state)


@router.callback_query(F.data.startswith("k4:start:"))
async def choose(call: CallbackQuery, state, session, db_user):
    await start_kling4(call, state, session, db_user, call.data.removeprefix("k4:start:"))


def body_from_state(data):
    from api.miniapp_routes import VideoGenRequest

    options = Kling4Input(**data["kling4"])
    return VideoGenRequest(
        model=data["model_key"],
        prompt=data.get("prompt") or "",
        duration=options.duration,
        resolution=options.resolution,
        aspect_ratio=options.aspect_ratio,
        kling4=options,
        intent_id=data["intent_id"],
        quoted_credits=data.get("quoted_credits"),
    )


@router.callback_query(F.data.startswith("k4:"))
async def action(call: CallbackQuery, state, session, db_user):
    if not await allowed(call, session, db_user):
        return
    data = await state.get_data()
    if data.get("model_key") not in KLING4_MODELS:
        await call.answer("Открой /kling4 заново", show_alert=True)
        return
    action = call.data.removeprefix("k4:")
    if ":v" not in action:
        await call.answer("Эта кнопка устарела. Открой текущую карточку /kling4", show_alert=True)
        return
    action, revision = action.rsplit(":v", 1)
    if revision != data.get("k4_revision"):
        await call.answer("Карточка обновилась. Используй последние кнопки", show_alert=True)
        return
    options = dict(data["kling4"])
    if action == "advanced":
        await state.update_data(k4_advanced=not data.get("k4_advanced"))
        await render(call.message, state)
    elif action.startswith("text:"):
        field = action.split(":")[1]
        await state.update_data(k4_field=field)
        await state.set_state(Kling4FSM.text)
        await call.message.answer(
            "Введи промпт (до 8000 символов):"
            if field == "prompt"
            else "Введи целое число секунд от 3 до 30:"
            if field == "duration"
            else "Введи новое имя для @ссылки: латинские буквы, цифры или _, до 20 символов:"
            if "name" in field
            else "Введи описание элемента до 100 символов:"
        )
    elif action.startswith("media:") or action.startswith("element:") or action == "voice":
        if action.startswith("element:"):
            if len(options["elements"]) >= 7:
                await call.answer("Не больше 7 персонажей", show_alert=True)
                return
            name = next_material_name(options, "Hero")
            await state.update_data(
                k4_field="element_" + action.split(":")[1], k4_new_name=name, k4_pending_images=[]
            )
            hint = (
                f"Персонаж @{name}. Пришли 2–4 фото, затем нажми «Готово»."
                if action.endswith("image")
                else f"Персонаж @{name}. Пришли видео 3–8 секунд, короткая сторона от 700 px."
            )
        else:
            field = action.split(":", 1)[1] if ":" in action else "voice"
            await state.update_data(k4_field=field)
            hint = (
                "Пришли аудиофайл с отчётливой речью, 5–30 секунд."
                if field == "voice" or field.startswith("bound_")
                else "Пришли файл. Кадры добавляются в порядке отправки."
            )
        await state.set_state(Kling4FSM.media)
        await call.message.answer(
            hint, reply_markup=keyboard([[("Готово", "k4:done")]], revision=data.get("k4_revision"))
        )
    elif action.startswith("remove:"):
        _, collection, index = action.split(":")
        if collection in {
            "image_urls",
            "video_urls",
            "keyframe_urls",
            "elements",
            "voices",
        } and int(index) < len(options[collection]):
            options[collection].pop(int(index))
            await state.update_data(kling4=options, intent_id=str(uuid4()), quoted_credits=None)
        await render(call.message, state)
    elif action.startswith("tag:"):
        index = int(action.split(":")[1])
        tags = ["character", "animal", "prop", "costume", "scene", "effect", "others"]
        if index < len(options["elements"]):
            item = options["elements"][index]
            if not item.get("video_url") and not item.get("voice_url"):
                item["tag"] = tags[(tags.index(item.get("tag") or "character") + 1) % len(tags)]
                await state.update_data(kling4=options, intent_id=str(uuid4()), quoted_credits=None)
        await render(call.message, state)
    elif action == "done":
        pending = data.get("k4_pending_images") or []
        if data.get("k4_field") == "element_image":
            if len(pending) < 2:
                await call.answer("Нужно минимум два ракурса персонажа", show_alert=True)
                return
            options["elements"].append(
                {"name": data["k4_new_name"], "image_urls": pending, "tag": "character"}
            )
        await state.update_data(
            kling4=options,
            k4_field=None,
            k4_pending_images=[],
            intent_id=str(uuid4()),
            quoted_credits=None,
        )
        await render(call.message, state)
    elif action in {"resolution", "ratio", "sound", "clear"}:
        if action == "resolution":
            options["resolution"] = "1080p" if options["resolution"] == "720p" else "720p"
        if action == "ratio":
            ratios = ["auto", "16:9", "9:16", "1:1", "21:9"]
            options["aspect_ratio"] = ratios[
                (ratios.index(options["aspect_ratio"] or "auto") + 1) % len(ratios)
            ]
        if action == "sound":
            options["keep_original_sound"] = not options["keep_original_sound"]
        if action == "clear":
            options = Kling4Input(
                duration=options["duration"],
                resolution=options["resolution"],
                aspect_ratio=options["aspect_ratio"],
            ).model_dump()
        await state.update_data(kling4=options, intent_id=str(uuid4()), quoted_credits=None)
        await render(call.message, state)
    elif action == "quote":
        from api.kling4_checkout import quote_kling4

        try:
            _, quote = await quote_kling4(
                body_from_state(data), data.get("prompt") or "", session, db_user
            )
        except (HTTPException, ValueError) as exc:
            await call.message.answer(escape(str(getattr(exc, "detail", exc)))[:2000])
        else:
            token = secrets.token_hex(8)
            await state.update_data(quoted_credits=quote.credits, k4_quote_token=token)
            await state.set_state(Kling4FSM.confirm)
            await call.message.answer(
                f"🎬 Kling 4 · {quote.billable_seconds} оплачиваемых сек\nК оплате: <b>{quote.credits:g} 💋</b>",
                reply_markup=keyboard(
                    [[("▶️ Создать", f"k4:launch:{token}")], [("Изменить", "k4:edit")]],
                    revision=data.get("k4_revision"),
                ),
            )
    elif action.startswith("launch:"):
        from api.kling4_checkout import create_kling4_generation
        from bot.handlers.video_gen import _kie_callback_url

        if await state.get_state() != Kling4FSM.confirm.state or not secrets.compare_digest(
            str(data.get("k4_quote_token") or ""), action.split(":", 1)[1]
        ):
            await call.answer("Сначала проверь стоимость", show_alert=True)
            return
        try:
            gen = await create_kling4_generation(
                body_from_state(data),
                data["prompt"],
                session,
                db_user,
                surface="telegram_bot",
                callback_url=_kie_callback_url(),
            )
        except HTTPException as exc:
            await call.message.answer(escape(str(exc.detail))[:2000])
        else:
            if gen.status.value == "failed":
                await call.message.answer(
                    f"KIE не принял задачу #{gen.id}. {gen.credits_spent:g} 💋 возвращены на баланс."
                )
            else:
                await call.message.answer(
                    f"Задача #{gen.id} принята. Результат придёт сюда и сохранится в истории."
                )
            # Keep intent and confirmation for safe transport retries; edits rotate it.
    elif action == "edit":
        await render(call.message, state)
    await call.answer()


@router.message(Kling4FSM.text, F.text)
@router.message(Kling4FSM.edit, F.text)
@router.message(Kling4FSM.confirm, F.text)
async def text_value(message: Message, state, session, db_user):
    if not await allowed(message, session, db_user):
        return
    data = await state.get_data()
    value = message.text or ""
    field = str(data.get("k4_field") or "")
    if field.startswith(("element_name_", "voice_name_", "element_description_")):
        index = int(field.rsplit("_", 1)[1])
        options = deepcopy(data["kling4"])
        try:
            if "description" in field:
                if len(value) > 100:
                    raise ValueError("Описание: не больше 100 символов")
                options["elements"][index]["description"] = value
                prompt = data.get("prompt") or ""
            else:
                options, prompt = rename_material(
                    options,
                    data.get("prompt") or "",
                    "voices" if field.startswith("voice") else "elements",
                    index,
                    value.strip(),
                )
            await state.update_data(kling4=options, prompt=prompt)
        except (ValueError, IndexError) as exc:
            await message.answer(escape(str(exc)))
            return
    elif data.get("k4_field") == "duration":
        if not value.isdigit() or not 3 <= int(value) <= 30:
            await message.answer("Длительность — целое число от 3 до 30")
            return
        options = {**data["kling4"], "duration": int(value)}
        await state.update_data(kling4=options)
    else:
        if not value.strip() or len(value) > 8000:
            await message.answer("Промпт должен содержать 1–8000 символов")
            return
        await state.update_data(prompt=value)
    await state.update_data(intent_id=str(uuid4()), quoted_credits=None, k4_quote_token=None)
    await render(message, state)


@router.message(Kling4FSM.media)
@router.message(Kling4FSM.edit, F.photo | F.video | F.audio | F.voice | F.document)
@router.message(Kling4FSM.confirm, F.photo | F.video | F.audio | F.voice | F.document)
async def media_value(message: Message, state, session, db_user, bot):
    if not await allowed(message, session, db_user):
        return
    media = (
        message.photo[-1]
        if message.photo
        else message.video or message.audio or message.voice or message.document
    )
    if not media or (media.file_size or 0) > MAX_ASSET_BYTES:
        await message.answer("Пришли фото, видео или аудио до 100 МБ")
        return
    data = await state.get_data()
    field = data.get("k4_field")
    automatic = field is None
    if automatic and data["model_key"] == KEYFRAME_MODEL:
        await message.answer("Для заказа из истории выбери кнопку первого, промежуточного или последнего кадра.")
        return
    caption = (message.caption or "").strip() if automatic else ""
    if len(caption) > 8000:
        await message.answer("Промпт должен содержать 1–8000 символов")
        return
    options = deepcopy(data["kling4"])
    info = await bot.get_file(media.file_id)
    content = await bot.download_file(info.file_path)
    try:
        asset = await store_kling4_asset(
            content.read(), getattr(media, "file_name", None) or info.file_path, user_id=db_user.id
        )
        url = asset["url"]
        kind = asset["kind"]
        if automatic:
            field = {"image": "image_urls", "video": "video_urls", "audio": "voice"}.get(kind)
            if field is None:
                raise ValueError("Пришли фото, видео или аудио")
        if field in {"voice"} or str(field).startswith("bound_"):
            if kind != "audio":
                raise ValueError("Нужен аудиофайл")
            if field == "voice":
                options["voices"].append(
                    {"name": next_material_name(options, "Voice"), "audio_url": url}
                )
            else:
                options["elements"][int(field.split("_")[1])]["voice_url"] = url
        elif field == "element_image":
            if kind != "image":
                raise ValueError("Нужно фото персонажа")
            pending = data.get("k4_pending_images") or []
            if len(pending) >= 4:
                raise ValueError("Не больше 4 ракурсов")
            await state.update_data(k4_pending_images=pending + [url])
            await message.answer(f"Ракурсов: {len(pending)+1}. После двух можно нажать «Готово».")
            return
        elif field == "element_video":
            if kind != "video":
                raise ValueError("Нужно видео персонажа")
            options["elements"].append(
                {"name": data["k4_new_name"], "video_url": url, "tag": "character"}
            )
        else:
            if kind != ("video" if field == "video_urls" else "image"):
                raise ValueError("Неверный тип материала")
            if field in {"first_frame_url", "last_frame_url"}:
                options[field] = url
            elif field in {"image_urls", "video_urls", "keyframe_urls"}:
                options[field].append(url)
            else:
                raise ValueError("Выбери роль материала заново")
        validated = Kling4Input(**options)
        await state.update_data(
            kling4=validated.model_dump(), intent_id=str(uuid4()), quoted_credits=None,
            k4_quote_token=None, **({"prompt": caption} if caption else {}),
        )
        if automatic:
            await render(message, state)
        else:
            await message.answer(
                "Материал добавлен.",
                reply_markup=keyboard([[("Готово", "k4:done")]], revision=data.get("k4_revision")),
            )
    except (ValueError, OSError) as exc:
        await message.answer(escape(str(exc))[:1500])


@router.callback_query(F.data.regexp(r"^(?:regen|reprompt|reparams):video:\d+"))
async def restore_kling4_result(call: CallbackQuery, state, session, db_user):
    from aiogram.dispatcher.event.bases import SkipHandler

    from db import repository as repo
    from db.repeat_lookup import parse_input_params

    generation_id = int(call.data.split(":")[2])
    generation = await repo.get_generation_by_id(session, generation_id)
    if generation is None or generation.user_id != db_user.id:
        await call.answer("Задача не найдена", show_alert=True)
        return
    if generation.model not in KLING4_MODELS:
        raise SkipHandler
    if not await allowed(call, session, db_user):
        return
    params = parse_input_params(generation.input_params)
    options = Kling4Input(**params.get("kling4", {}))
    await state.set_data(
        {
            "model_key": generation.model,
            "kling4": options.model_dump(),
            "intent_id": str(uuid4()),
            "prompt": "" if call.data.startswith("reprompt:") else generation.prompt,
        }
    )
    await render(call.message, state)
    await call.answer()
