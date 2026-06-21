
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api.music_service import create_music_task, register_miniapp_task, register_task
from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import MusicFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback
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


def _music_model_title(model_key: str | None) -> str:
    key = str(model_key or "").lower()
    if "5.5" in key or "v5_5" in key:
        return "Suno 5.5"
    if "5" in key:
        return "Suno 5"
    if "4.5" in key or "v4_5" in key:
        return "Suno 4.5"
    return "Suno"


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
        screen.text,
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
        f"🎵 Режим выбран: <b>{label}</b>\n\nТеперь напиши описание трека.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)

@router.message(F.text == "🎵 Песня")
async def music_entry(msg: Message, state: FSMContext):
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=False)
    await msg.answer("🎵 Напиши описание трека", reply_markup=back_to_menu_kb())

@router.message(MusicFSM.prompt_input, F.text)
async def music_prompt(msg: Message, state: FSMContext, session: AsyncSession, db_user: User):
    data = await state.get_data()
    model_cost = await _resolve_active_music_model(session)
    music_cost = float(model_cost.credits) if model_cost else float(DEFAULT_MUSIC_CREDITS)

    if db_user.credits < music_cost:
        await msg.answer(
            f"😔 Недостаточно 💋 для музыки.\nНужно: <b>{music_cost:g}</b>, у тебя: <b>{db_user.credits:g}</b>",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    ok = await repo.spend_credits(session, db_user.id, music_cost)
    if not ok:
        await msg.answer(
            "😔 Не удалось списать 💋 для генерации. Попробуй ещё раз.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    selected_model_key = data.get("music_model_key") or getattr(model_cost, "model_key", MUSIC_MODEL_KEY)
    gen = await repo.create_generation(
        session,
        db_user.id,
        selected_model_key,
        GenerationType.music,
        msg.text,
        music_cost,
    )

    await msg.answer("⏳ Генерирую...", reply_markup=back_to_menu_kb())

    try:
        task_id = await create_music_task(msg.text, data.get("instrumental", False), model_key=selected_model_key)
        register_task(task_id, msg.from_user.id)  # type: ignore[union-attr]
        register_miniapp_task(task_id, gen.id)
        await repo.update_generation_task(session, gen.id, task_id)
        await msg.answer(
            "🎵 <b>Генерация запущена!</b>\n\nТрек придёт сюда автоматически (~1-2 мин).",
            reply_markup=back_to_menu_kb(),
        )
    except Exception as e:
        if await repo.fail_generation(session, gen.id, str(e)):
            await repo.add_credits(session, db_user.id, music_cost)
        await msg.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

    await state.clear()
