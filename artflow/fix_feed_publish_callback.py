from pathlib import Path

p = Path("bot/handlers/feed.py")
if p.exists():
    s = p.read_text(encoding="utf-8")
else:
    p.parent.mkdir(parents=True, exist_ok=True)
    s = '''from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from db import repository as repo

router = Router()

'''

if "feed:publish:" not in s:
    s += '''

@router.callback_query(F.data.startswith("feed:publish:"))
async def cb_publish_generation(call: CallbackQuery, session: AsyncSession) -> None:
    generation_id = int(call.data.split(":")[-1])
    gen = await repo.get_generation_by_id(session, generation_id)

    if not gen:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    gen.is_public_feed = True
    gen.is_prompt_library = True
    await session.commit()

    await call.answer("Добавлено в библиотеку промптов ✨", show_alert=False)
'''
p.write_text(s, encoding="utf-8")
print("OK: feed publish callback patched")
