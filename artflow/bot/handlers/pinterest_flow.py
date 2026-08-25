from __future__ import annotations

"""Telegram Pinterest flow.

The flow mirrors the Mini App contract: scene reference -> identity -> optional
identity evidence -> body parameters -> explicit launch. Generation is delegated
to the Pinterest service backend, never to trends.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router(name="pinterest_flow")


class PinterestFlow(StatesGroup):
    scene_reference = State()
    identity_reference = State()
    identity_evidence = State()
    height = State()
    weight = State()
    confirm = State()


def _menu():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📌 Pinterest", callback_data="pinterest:start"))
    return kb.as_markup()


@router.callback_query(F.data == "pinterest:start")
async def start_pinterest(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PinterestFlow.scene_reference)
    await call.message.answer(
        "📌 <b>Pinterest</b>\n\n"
        "Как получить результат 1 в 1\n\n"
        "Слева — кадр, который повторяем. Справа — ваше основное фото.\n"
        "Генерация не запускается после загрузки: сначала добавьте все данные и нажмите Создать.\n\n"
        "Отправьте фото-референс Pinterest.",
        reply_markup=_menu(),
    )
    await call.answer()


@router.message(PinterestFlow.scene_reference, F.photo)
async def scene_uploaded(message: Message, state: FSMContext) -> None:
    await state.update_data(scene_reference=message.photo[-1].file_id)
    await state.set_state(PinterestFlow.identity_reference)
    await message.answer("✅ РЕФЕРЕНС готов\n\nТеперь отправьте ваше основное фото — ТЫ.")


@router.message(PinterestFlow.identity_reference, F.photo)
async def identity_uploaded(message: Message, state: FSMContext) -> None:
    await state.update_data(identity_reference=message.photo[-1].file_id)
    await state.set_state(PinterestFlow.identity_evidence)
    await message.answer(
        "✅ ТЫ готов\n\n"
        "Добавьте 1–5 дополнительных ракурсов одного человека или нажмите пропустить."
    )


@router.message(PinterestFlow.identity_evidence)
async def evidence_or_skip(message: Message, state: FSMContext) -> None:
    if message.photo:
        data = await state.get_data()
        refs = list(data.get("identity_evidence", []))
        if len(refs) < 5:
            refs.append(message.photo[-1].file_id)
            await state.update_data(identity_evidence=refs)
        await message.answer(f"Добавлено ракурсов: {len(refs)}/5")
        return
    await state.set_state(PinterestFlow.height)
    await message.answer("Укажите рост в см:")


@router.message(PinterestFlow.height, F.text)
async def height(message: Message, state: FSMContext) -> None:
    await state.update_data(height_cm=int(message.text))
    await state.set_state(PinterestFlow.weight)
    await message.answer("Укажите вес в кг:")


@router.message(PinterestFlow.weight, F.text)
async def weight(message: Message, state: FSMContext) -> None:
    await state.update_data(weight_kg=int(message.text))
    await state.set_state(PinterestFlow.confirm)
    await message.answer("Все данные готовы. Цена и кнопка Создать будут взяты из Pinterest Service.")
