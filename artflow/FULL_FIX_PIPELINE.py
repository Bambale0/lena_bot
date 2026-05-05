from pathlib import Path
import re

print("🔥 START FULL FIX")

# =========================
# 1. FIX public_files.py
# =========================

p = Path("api/public_files.py")
s = p.read_text(encoding="utf-8")

if "def _detect_extension" in s:
    s = re.sub(
        r'def _detect_extension\(.*?return ".bin"\n',
        '''def _detect_extension(data: bytes, content_type: str | None = None) -> str:
    ct = (content_type or "").lower()

    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"

    if data.startswith(b"\\xff\\xd8"):
        return ".jpg"
    if data.startswith(b"\\x89PNG"):
        return ".png"
    if data.startswith(b"RIFF"):
        return ".webp"

    return ".jpg"
''',
        s,
        flags=re.S,
    )

# вернуть mirror функции если сломались
if "def mirror_telegram_file" not in s:
    s += '''

import httpx
import uuid

async def mirror_telegram_file(file_url: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(file_url)

    data = r.content
    ext = _detect_extension(data)

    filename = f"{uuid.uuid4().hex}{ext}"
    path = UPLOAD_ROOT / filename
    path.write_bytes(data)

    return f"{settings.WEBHOOK_URL}{settings.STATIC_UPLOAD_URL_PATH}/{filename}"
'''

p.write_text(s, encoding="utf-8")
print("✅ public_files fixed")

# =========================
# 2. FIX image handler (.bin → url)
# =========================

p = Path("bot/handlers/image_gen.py")
s = p.read_text(encoding="utf-8")

if "reference_url" not in s:
    print("⚠️ reference_url not used yet")

# гарантируем что используем URL а не file_id
s = s.replace("reference_file_id", "reference_url")

p.write_text(s, encoding="utf-8")
print("✅ image handler fixed")

# =========================
# 3. ADD MUSIC SERVICE
# =========================

music_file = Path("api/music_service.py")

music_file.write_text("""
import httpx
from core.config import settings

KIE_URL = "https://api.kie.ai/api/v1/generate"

async def create_music_task(prompt: str, instrumental: bool = False):
    headers = {
        "Authorization": f"Bearer {settings.KIE_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": prompt,
        "customMode": False,
        "instrumental": instrumental,
        "model": "V4_5",
        "callBackUrl": f"{settings.WEBHOOK_URL}/webhook/kie/music"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(KIE_URL, json=payload, headers=headers)

    data = r.json()

    if data.get("code") != 200:
        raise Exception(f"KIE music error: {data}")

    return data["data"]["taskId"]
""", encoding="utf-8")

print("✅ music service added")

# =========================
# 4. ADD MUSIC HANDLER
# =========================

Path("bot/handlers/music_gen.py").write_text("""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from api.music_service import create_music_task

router = Router()

@router.message(F.text == "🎵 Песня")
async def music_entry(msg: Message, state: FSMContext):
    await state.update_data(instrumental=False)
    await msg.answer("🎵 Напиши описание трека")

@router.message()
async def music_prompt(msg: Message, state: FSMContext):
    data = await state.get_data()

    if "instrumental" not in data:
        return

    await msg.answer("⏳ Генерирую...")

    try:
        task_id = await create_music_task(msg.text, data["instrumental"])
        await msg.answer(f"🎵 Запущено! ID: {task_id}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")

    await state.clear()
""", encoding="utf-8")

print("✅ music handler added")

# =========================
# 5. FIX MAIN MENU (баланс + кнопка)
# =========================

p = Path("bot/keyboards/main.py")
if p.exists():
    s = p.read_text(encoding="utf-8")

    if "🎵 Песня" not in s:
        s = s.replace("Видео", "Видео\n🎵 Песня")

    p.write_text(s, encoding="utf-8")
    print("✅ menu updated")

# =========================
# DONE
# =========================

print("🚀 ALL FIXED")
