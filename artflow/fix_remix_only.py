from pathlib import Path

path = Path("bot/handlers/image_gen.py")
s = path.read_text(encoding="utf-8")

# 1. Добавляем безопасный helper: брать last_result_url только если модель поддерживает image input.
helper = '''
async def _effective_session_reference_url(
    bot: Bot,
    image_session: ImageSession,
    *,
    prefer_last_result: bool = False,
) -> str | None:
    """Return reference URL only for models that can safely accept image input."""
    if not _supports_img2img(image_session.model):
        return None
    return await _session_reference_url(
        bot,
        image_session,
        prefer_last_result=prefer_last_result,
    )
'''

if "async def _effective_session_reference_url" not in s:
    s = s.replace(
        "\n\nasync def _launch_session_generation(",
        "\n" + helper + "\nasync def _launch_session_generation(",
    )

# 2. Ремикс должен выставлять флаг remix_mode и parent generation.
old = '''@router.callback_query(F.data.startswith("img_session:remix:"))
async def cb_image_session_remix(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ImageGenFSM.session_active)
    await call.message.answer("✨ Напиши, что изменить в текущей картинке:")
    await call.answer()
'''

new = '''@router.callback_query(F.data.startswith("img_session:remix:"))
async def cb_image_session_remix(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
    gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        remix_mode=True,
        remix_parent_generation_id=parent_id or image_session.last_generation_id,
    )
    await call.message.answer(
        "✨ Напиши, что изменить в текущей картинке.\\n"
        "Например: <i>поменяй позу, добавь дождь, сделай другой свет</i>"
    )
    await call.answer()
'''

if old in s:
    s = s.replace(old, new)
else:
    print("WARN: old remix callback not found, skipped callback replacement")

# 3. В handle_session_prompt надо брать last_result_url, если remix_mode=True.
# Ищем старую строку, которая берёт reference_file_id.
old_ref = '''    image_url = await _telegram_file_url(bot, image_session.reference_file_id)
'''

new_ref = '''    is_remix = bool(data.get("remix_mode"))
    parent_id = data.get("remix_parent_generation_id") or image_session.last_generation_id
    image_url = await _effective_session_reference_url(
        bot,
        image_session,
        prefer_last_result=is_remix,
    )
'''

if old_ref in s:
    s = s.replace(old_ref, new_ref, 1)
else:
    print("WARN: old reference line not found")

# 4. parent_generation_id должен быть parent_id, если переменная есть.
s = s.replace(
    "parent_generation_id=parent_id,",
    "parent_generation_id=parent_id,",
)

# 5. После запуска сбрасываем remix флаги.
target = '''    await status_msg.edit_text(
        "⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
        reply_markup=image_session_kb(gen.id),
    )
'''

replacement = '''    await status_msg.edit_text(
        "⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
        reply_markup=image_session_kb(gen.id),
    )
    await state.update_data(remix_mode=False, remix_parent_generation_id=None)
'''

if target in s and "remix_parent_generation_id=None" not in s:
    s = s.replace(target, replacement, 1)

path.write_text(s, encoding="utf-8")
