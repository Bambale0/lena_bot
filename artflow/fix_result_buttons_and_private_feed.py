from pathlib import Path
import re

# ─────────────────────────────────────────────────────────────
# 1) main.py: KIE result should send media WITH buttons
# ─────────────────────────────────────────────────────────────

p = Path("main.py")
s = p.read_text(encoding="utf-8")

# Добавляем импорт кнопок результата, если его нет.
if "get_generation_result_keyboard" not in s:
    # Ищем импорт клавиатур.
    s = re.sub(
        r"from bot\.keyboards\.main_menu import ([^\n]+)",
        lambda m: m.group(0) + "\nfrom bot.keyboards.feed import get_generation_result_keyboard",
        s,
        count=1,
    )

# Если такого модуля/функции нет, позже создадим fallback в bot/keyboards/feed.py.
# Меняем отправку результата: если в main.py есть send_photo(result_url...) без reply_markup.
s = re.sub(
    r"await bot\.send_photo\(\s*chat_id=tg_id,\s*photo=result_url,\s*caption=caption,\s*\)",
    "await bot.send_photo(chat_id=tg_id, photo=result_url, caption=caption, reply_markup=get_generation_result_keyboard(gen.id))",
    s,
    flags=re.S,
)

s = re.sub(
    r"await bot\.send_video\(\s*chat_id=tg_id,\s*video=result_url,\s*caption=caption,\s*\)",
    "await bot.send_video(chat_id=tg_id, video=result_url, caption=caption, reply_markup=get_generation_result_keyboard(gen.id))",
    s,
    flags=re.S,
)

# Более общий случай: send_photo(... caption=..., parse_mode=...)
s = re.sub(
    r"await bot\.send_photo\(([^)]*photo=result_url[^)]*caption=caption[^)]*)\)",
    lambda m: m.group(0) if "reply_markup" in m.group(1) else f"await bot.send_photo({m.group(1)}, reply_markup=get_generation_result_keyboard(gen.id))",
    s,
    flags=re.S,
)

s = re.sub(
    r"await bot\.send_video\(([^)]*video=result_url[^)]*caption=caption[^)]*)\)",
    lambda m: m.group(0) if "reply_markup" in m.group(1) else f"await bot.send_video({m.group(1)}, reply_markup=get_generation_result_keyboard(gen.id))",
    s,
    flags=re.S,
)

p.write_text(s, encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# 2) bot/keyboards/feed.py: ensure result keyboard exists
# ─────────────────────────────────────────────────────────────

p = Path("bot/keyboards/feed.py")
if p.exists():
    s = p.read_text(encoding="utf-8")
else:
    p.parent.mkdir(parents=True, exist_ok=True)
    s = "from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder\n\n"

if "def get_generation_result_keyboard" not in s:
    if "InlineKeyboardBuilder" not in s:
        s = "from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup\nfrom aiogram.utils.keyboard import InlineKeyboardBuilder\n\n" + s

    s += '''

def get_generation_result_keyboard(generation_id: int) -> InlineKeyboardMarkup:
    """Buttons shown directly under generated media."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✨ Ремикс", callback_data=f"feed:remix:{generation_id}"),
        InlineKeyboardButton(text="📚 В библиотеку", callback_data=f"feed:publish:{generation_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔁 Ещё вариант", callback_data=f"feed:again:{generation_id}"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:home"),
    )
    return builder.as_markup()
'''

p.write_text(s, encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# 3) api/miniapp_routes.py: feed only user-published generations
# ─────────────────────────────────────────────────────────────

p = Path("api/miniapp_routes.py")
s = p.read_text(encoding="utf-8")

# Убеждаемся, что create image/video/music не публикуют в feed автоматически.
# Если где-то явно ставится is_public_feed=True при создании miniapp generation — меняем на False.
s = s.replace("is_public_feed=True", "is_public_feed=False")

# Добавляем endpoint publish/add-to-library, если его нет.
if '@router.post("/generations/{gen_id}/publish")' not in s:
    insert = r'''

@router.post("/generations/{gen_id}/publish")
async def publish_generation_to_library(
    gen_id: int,
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
):
    """User explicitly publishes own generation to public feed/prompt library."""
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")

    gen.is_public_feed = True
    gen.is_prompt_library = True
    await session.commit()
    await session.refresh(gen)

    return {
        "ok": True,
        "id": gen.id,
        "is_public_feed": gen.is_public_feed,
        "is_prompt_library": gen.is_prompt_library,
    }
'''
    # Вставим перед payments/plans или в конец.
    s += insert

p.write_text(s, encoding="utf-8")

print("OK: result buttons + private feed backend patched")
