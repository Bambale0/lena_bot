#!/usr/bin/env bash
set -euo pipefail

echo "==> Applying KIE webhook + image sessions patch"

BACKUP_DIR=".patch_backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

backup() {
  local f="$1"
  if [ -f "$f" ]; then
    mkdir -p "$BACKUP_DIR/$(dirname "$f")"
    cp "$f" "$BACKUP_DIR/$f"
  fi
}

backup "core/config.py"
backup "api/kieai_client.py"
backup "api/image_service.py"
backup "main.py"
backup "db/models.py"
backup "db/repository.py"
backup "bot/states/__init__.py"
backup "bot/keyboards/models.py"
backup "bot/handlers/image_gen.py"

python - <<'PY'
from pathlib import Path
import re

def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")

def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")

# ---------------------------------------------------------------------
# core/config.py
# ---------------------------------------------------------------------
p = Path("core/config.py")
s = read(str(p))

if "KIE_WEBHOOK_PATH" not in s:
    s = s.replace(
        '    KIE_AI_KEY: str = ""\n',
        '    KIE_AI_KEY: str = ""\n\n'
        '    # KIE.AI callbacks\n'
        '    KIE_WEBHOOK_PATH: str = "/webhook/kie"\n'
        '    KIE_WEBHOOK_SECRET: str = ""\n',
    )

write(str(p), s)

# ---------------------------------------------------------------------
# api/kieai_client.py
# ---------------------------------------------------------------------
p = Path("api/kieai_client.py")
s = read(str(p))

# Add optional callback_url support to create_task without breaking existing callers.
if "callback_url: str | None = None" not in s:
    s = re.sub(
        r"async def create_task\(\s*payload: dict\[str, Any\]\s*\) -> dict\[str, Any\]:",
        "async def create_task(\n    payload: dict[str, Any],\n    callback_url: str | None = None,\n) -> dict[str, Any]:",
        s,
    )
    s = s.replace(
        '    return await post("/api/v1/jobs/createTask", json=payload)\n',
        '    if callback_url:\n'
        '        # KIE expects this exact key name.\n'
        '        payload = dict(payload)\n'
        '        payload["callBackUrl"] = callback_url\n'
        '    return await post("/api/v1/jobs/createTask", json=payload)\n',
    )

write(str(p), s)

# ---------------------------------------------------------------------
# api/image_service.py
# ---------------------------------------------------------------------
p = Path("api/image_service.py")
s = read(str(p))

if "callback_url: str | None = None" not in s:
    s = s.replace(
        '    quality: str = "basic",             # "basic"=2K / "high"=4K (Seedream)\n) -> ImageResult:',
        '    quality: str = "basic",             # "basic"=2K / "high"=4K (Seedream)\n'
        '    callback_url: str | None = None,\n'
        ') -> ImageResult:',
    )
    s = s.replace(
        '    resp = await kieai_client.create_task({"model": model.value, "input": inp})',
        '    resp = await kieai_client.create_task({"model": model.value, "input": inp}, callback_url=callback_url)',
    )

write(str(p), s)

# ---------------------------------------------------------------------
# db/models.py
# ---------------------------------------------------------------------
p = Path("db/models.py")
s = read(str(p))

if "class ImageSessionStatus" not in s:
    s = s.replace(
        "class GenerationStatus(str, enum.Enum):\n"
        '    pending = "pending"\n'
        '    processing = "processing"\n'
        '    done = "done"\n'
        '    failed = "failed"\n',
        "class GenerationStatus(str, enum.Enum):\n"
        '    pending = "pending"\n'
        '    processing = "processing"\n'
        '    done = "done"\n'
        '    failed = "failed"\n\n\n'
        "class ImageSessionStatus(str, enum.Enum):\n"
        '    active = "active"\n'
        '    archived = "archived"\n\n\n'
        "class ImageGenerationAction(str, enum.Enum):\n"
        '    initial = "initial"\n'
        '    remix = "remix"\n'
        '    repeat = "repeat"\n'
        '    reference_update = "reference_update"\n'
        '    animate = "animate"\n',
    )

if "class ImageSession(Base):" not in s:
    image_session_block = '''
class ImageSession(Base):
    """Saved image generation settings for iterative Syntx-like workflow."""

    __tablename__ = "image_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    aspect_ratio: Mapped[str | None] = mapped_column(String(32))
    quality: Mapped[str] = mapped_column(String(32), default="basic", nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    base_prompt: Mapped[str | None] = mapped_column(Text)
    reference_file_id: Mapped[str | None] = mapped_column(Text)
    last_result_url: Mapped[str | None] = mapped_column(Text)
    last_generation_id: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[ImageSessionStatus] = mapped_column(
        Enum(ImageSessionStatus),
        default=ImageSessionStatus.active,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(lazy="noload")
'''
    s = s.replace("\n\nclass Transaction(Base):", "\n\n" + image_session_block + "\n\nclass Transaction(Base):")

if "image_session_id" not in s:
    s = s.replace(
        '    task_id: Mapped[str | None] = mapped_column(String(256))  # CometAPI task id\n',
        '    task_id: Mapped[str | None] = mapped_column(String(256), index=True)  # KIE task id\n'
        '    image_session_id: Mapped[int | None] = mapped_column(\n'
        '        Integer,\n'
        '        ForeignKey("image_sessions.id"),\n'
        '        nullable=True,\n'
        '        index=True,\n'
        '    )\n'
        '    parent_generation_id: Mapped[int | None] = mapped_column(\n'
        '        Integer,\n'
        '        ForeignKey("generations.id"),\n'
        '        nullable=True,\n'
        '    )\n'
        '    action_type: Mapped[ImageGenerationAction | None] = mapped_column(\n'
        '        Enum(ImageGenerationAction),\n'
        '        nullable=True,\n'
        '    )\n',
    )

write(str(p), s)

# ---------------------------------------------------------------------
# db/repository.py
# ---------------------------------------------------------------------
p = Path("db/repository.py")
s = read(str(p))

if "ImageSession" not in s.split("from db.models import", 1)[1].split(")", 1)[0]:
    s = s.replace(
        "    Generation,\n",
        "    Generation,\n"
        "    ImageGenerationAction,\n"
        "    ImageSession,\n"
        "    ImageSessionStatus,\n",
    )

# Extend create_generation signature and constructor.
if "image_session_id: int | None = None" not in s:
    s = s.replace(
        "async def create_generation(\n"
        "    session: AsyncSession,\n"
        "    user_id: int,\n"
        "    model: str,\n"
        "    gen_type: GenerationType,\n"
        "    prompt: str,\n"
        "    credits_spent: int,\n"
        ") -> Generation:",
        "async def create_generation(\n"
        "    session: AsyncSession,\n"
        "    user_id: int,\n"
        "    model: str,\n"
        "    gen_type: GenerationType,\n"
        "    prompt: str,\n"
        "    credits_spent: int,\n"
        "    image_session_id: int | None = None,\n"
        "    parent_generation_id: int | None = None,\n"
        "    action_type: ImageGenerationAction | None = None,\n"
        ") -> Generation:",
    )
    s = s.replace(
        "        credits_spent=credits_spent,\n"
        "        status=GenerationStatus.pending,\n",
        "        credits_spent=credits_spent,\n"
        "        image_session_id=image_session_id,\n"
        "        parent_generation_id=parent_generation_id,\n"
        "        action_type=action_type,\n"
        "        status=GenerationStatus.pending,\n",
    )

if "async def get_generation_by_task_id" not in s:
    insert = '''
async def get_generation_by_id(session: AsyncSession, gen_id: int) -> Generation | None:
    result = await session.execute(select(Generation).where(Generation.id == gen_id))
    return result.scalar_one_or_none()


async def get_generation_by_task_id(session: AsyncSession, task_id: str) -> Generation | None:
    result = await session.execute(select(Generation).where(Generation.task_id == task_id))
    return result.scalar_one_or_none()


# ─── Image Sessions ──────────────────────────────────────────────────────────

async def archive_active_image_sessions(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(ImageSession)
        .where(
            ImageSession.user_id == user_id,
            ImageSession.status == ImageSessionStatus.active,
        )
        .values(status=ImageSessionStatus.archived)
    )
    await session.commit()


async def create_image_session(
    session: AsyncSession,
    user_id: int,
    model: str,
    mode: str,
    aspect_ratio: str | None,
    quality: str,
    count: int,
    base_prompt: str | None,
    reference_file_id: str | None,
) -> ImageSession:
    await archive_active_image_sessions(session, user_id)

    image_session = ImageSession(
        user_id=user_id,
        model=model,
        mode=mode,
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=count,
        base_prompt=base_prompt,
        reference_file_id=reference_file_id,
        status=ImageSessionStatus.active,
    )
    session.add(image_session)
    await session.commit()
    await session.refresh(image_session)
    return image_session


async def get_image_session(
    session: AsyncSession,
    image_session_id: int,
    user_id: int | None = None,
) -> ImageSession | None:
    stmt = select(ImageSession).where(ImageSession.id == image_session_id)
    if user_id is not None:
        stmt = stmt.where(ImageSession.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_active_image_session(session: AsyncSession, user_id: int) -> ImageSession | None:
    result = await session.execute(
        select(ImageSession)
        .where(
            ImageSession.user_id == user_id,
            ImageSession.status == ImageSessionStatus.active,
        )
        .order_by(desc(ImageSession.updated_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_image_session_reference(
    session: AsyncSession,
    image_session_id: int,
    reference_file_id: str | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(reference_file_id=reference_file_id)
    )
    await session.commit()


async def update_image_session_base_prompt(
    session: AsyncSession,
    image_session_id: int,
    base_prompt: str | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(base_prompt=base_prompt)
    )
    await session.commit()


async def update_image_session_last_result(
    session: AsyncSession,
    image_session_id: int,
    result_url: str | None,
    generation_id: int | None,
) -> None:
    await session.execute(
        update(ImageSession)
        .where(ImageSession.id == image_session_id)
        .values(last_result_url=result_url, last_generation_id=generation_id)
    )
    await session.commit()


async def get_last_session_generation(
    session: AsyncSession,
    image_session_id: int,
) -> Generation | None:
    result = await session.execute(
        select(Generation)
        .where(Generation.image_session_id == image_session_id)
        .order_by(desc(Generation.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()

'''
    s = s.replace("\n\nasync def get_user_history(", insert + "\nasync def get_user_history(")

write(str(p), s)

# ---------------------------------------------------------------------
# bot/states/__init__.py
# ---------------------------------------------------------------------
p = Path("bot/states/__init__.py")
s = read(str(p))
wanted = [
    "mode_select",
    "image_upload",
    "aspect_ratio_select",
    "count_select",
    "session_active",
    "remix_prompt",
    "session_reference_upload",
]
for name in wanted:
    if f"    {name} = State()" not in s:
        if name in ("mode_select", "image_upload", "aspect_ratio_select", "count_select"):
            s = s.replace("    reference_upload = State()  # optional reference image\n", f"    {name} = State()\n    reference_upload = State()  # optional reference image\n")
        else:
            s = s.replace("    generating = State()\n", f"    generating = State()\n    {name} = State()\n", 1)

write(str(p), s)

# ---------------------------------------------------------------------
# bot/keyboards/models.py
# ---------------------------------------------------------------------
p = Path("bot/keyboards/models.py")
s = read(str(p))

if "def _prioritize_ratio" not in s:
    s = s.replace(
        "\n# ── Image keyboards",
        '\n\ndef _prioritize_ratio(ratios: list[str], preferred: str = "9:16") -> list[str]:\n'
        '    """Put the most important aspect ratio first without dropping options."""\n'
        '    return ([preferred] if preferred in ratios else []) + [r for r in ratios if r != preferred]\n'
        "\n# ── Image keyboards",
    )

if "ratios = _prioritize_ratio" not in s:
    s = s.replace(
        '    ratios = caps.get("aspect_ratios", [])\n',
        '    ratios = _prioritize_ratio(caps.get("aspect_ratios", []))\n',
    )

if "def image_session_kb" not in s:
    s += '''

def image_session_kb(gen_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    suffix = str(gen_id or 0)
    builder.row(
        InlineKeyboardButton(text="✨ Ремикс", callback_data=f"img_session:remix:{suffix}"),
        InlineKeyboardButton(text="🔁 Повторить", callback_data=f"img_session:repeat:{suffix}"),
    )
    builder.row(
        InlineKeyboardButton(text="🎬 Оживить", callback_data=f"img_session:animate:{suffix}"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="img_session:settings"),
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новая серия", callback_data="img_session:new"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    )
    return builder.as_markup()
'''

write(str(p), s)

# ---------------------------------------------------------------------
# api/kie_webhook.py
# ---------------------------------------------------------------------
write("api/kie_webhook.py", '''# api/kie_webhook.py
from __future__ import annotations

from typing import Any


def extract_task_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") or {}
    info = payload.get("info") or {}

    return (
        str(data.get("task_id"))
        if data.get("task_id")
        else str(data.get("taskId"))
        if data.get("taskId")
        else str(payload.get("task_id"))
        if payload.get("task_id")
        else str(payload.get("taskId"))
        if payload.get("taskId")
        else str(info.get("task_id"))
        if info.get("task_id")
        else str(info.get("taskId"))
        if info.get("taskId")
        else None
    )


def is_success(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    if code is not None and str(code) not in {"0", "200", "success", "SUCCESS"}:
        return False

    data = payload.get("data") or {}
    state = str(
        data.get("state")
        or data.get("status")
        or payload.get("state")
        or payload.get("status")
        or ""
    ).lower()

    if state in {"fail", "failed", "error"}:
        return False
    if state in {"success", "succeeded", "complete", "completed", "done"}:
        return True

    # Some KIE callbacks only send code=200 + URLs.
    return bool(extract_result_urls(payload))


def extract_error(payload: dict[str, Any]) -> str:
    data = payload.get("data") or {}
    return str(
        data.get("failMsg")
        or data.get("error")
        or data.get("msg")
        or payload.get("msg")
        or payload.get("error")
        or "KIE generation failed"
    )


def extract_result_urls(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") or {}
    info = payload.get("info") or {}

    candidates: list[Any] = [
        data.get("result_urls"),
        data.get("resultUrls"),
        data.get("result_urls".replace("_", "")),
        info.get("result_urls"),
        info.get("resultUrls"),
        payload.get("result_urls"),
        payload.get("resultUrls"),
    ]

    urls: list[str] = []
    for item in candidates:
        if isinstance(item, list):
            urls.extend(str(x) for x in item if x)
        elif isinstance(item, str) and item:
            urls.append(item)

    for key in ("video_url", "videoUrl", "image_url", "imageUrl", "url"):
        value = data.get(key) or info.get(key) or payload.get(key)
        if isinstance(value, str) and value:
            urls.append(value)

    # Keep order, remove duplicates.
    seen = set()
    deduped = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped
''')

# ---------------------------------------------------------------------
# bot/handlers/image_gen.py
# ---------------------------------------------------------------------
p = Path("bot/handlers/image_gen.py")
s = read(str(p))

# Imports
s = s.replace("import logging\n", "import logging\nfrom urllib.parse import urlencode\n")
s = s.replace(
    "from bot.keyboards.models import (\n"
    "    IMAGE_CAPS,\n"
    "    after_generation_kb,\n",
    "from bot.keyboards.models import (\n"
    "    IMAGE_CAPS,\n"
    "    after_generation_kb,\n"
    "    image_session_kb,\n",
)
if "from core.config import settings" not in s:
    s = s.replace("from bot.states import ImageGenFSM\n", "from bot.states import ImageGenFSM\nfrom core.config import settings\n")
s = s.replace(
    "from db.models import GenerationType, User",
    "from db.models import GenerationType, ImageGenerationAction, User",
)

helper = '''
def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{query}"


async def _telegram_file_url(bot: Bot, file_id: str | None) -> str | None:
    if not file_id:
        return None
    file = await bot.get_file(file_id)
    return f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"


def _session_caption(prompt: str) -> str:
    return (
        "✅ <b>Готово!</b>\\n\\n"
        f"<i>{prompt[:200]}</i>\\n\\n"
        "🎨 <b>Серия активна.</b> Теперь просто отправляй новый текст или фото — "
        "настройки сохранятся."
    )
'''

if "def _kie_callback_url" not in s:
    s = s.replace("router = Router(name=\"image_gen\")\n", "router = Router(name=\"image_gen\")\n" + helper)

# Replace inline image_url build with helper.
s = re.sub(
    r"    image_url: str \| None = None\n"
    r"    if image_file_id:\n"
    r"        file = await bot.get_file\(image_file_id\)\n"
    r"        image_url = f\"https://api.telegram.org/file/bot\{bot.token\}/\{file.file_path\}\"\n",
    "    image_url = await _telegram_file_url(bot, image_file_id)\n",
    s,
)

# Create image session before generation if absent.
if "image_session = await repo.create_image_session" not in s:
    s = s.replace(
        "    ok = await repo.spend_credits(session, db_user.id, credits)\n",
        "    image_session_id: int | None = data.get(\"image_session_id\")\n"
        "    image_session = None\n"
        "    if image_session_id:\n"
        "        image_session = await repo.get_image_session(session, image_session_id, db_user.id)\n"
        "    if image_session is None:\n"
        "        image_session = await repo.create_image_session(\n"
        "            session=session,\n"
        "            user_id=db_user.id,\n"
        "            model=model_key,\n"
        "            mode=data.get(\"mode\", \"text\"),\n"
        "            aspect_ratio=aspect_ratio,\n"
        "            quality=quality,\n"
        "            count=count,\n"
        "            base_prompt=prompt,\n"
        "            reference_file_id=image_file_id,\n"
        "        )\n"
        "        await state.update_data(image_session_id=image_session.id)\n\n"
        "    ok = await repo.spend_credits(session, db_user.id, credits)\n",
    )

# Extend create_generation call.
s = s.replace(
    "    gen = await repo.create_generation(\n"
    "        session, db_user.id, model_key, GenerationType.image, prompt, credits\n"
    "    )",
    "    gen = await repo.create_generation(\n"
    "        session,\n"
    "        db_user.id,\n"
    "        model_key,\n"
    "        GenerationType.image,\n"
    "        prompt,\n"
    "        credits,\n"
    "        image_session_id=image_session.id,\n"
    "        action_type=ImageGenerationAction.initial,\n"
    "    )",
)

# Add callback_url to generate_image.
s = s.replace(
    "            ImageModel(model_key), prompt,\n"
    "            image_url=image_url, aspect_ratio=aspect_ratio, n=count, quality=quality,\n"
    "        )",
    "            ImageModel(model_key),\n"
    "            prompt,\n"
    "            image_url=image_url,\n"
    "            aspect_ratio=aspect_ratio,\n"
    "            n=count,\n"
    "            quality=quality,\n"
    "            callback_url=_kie_callback_url(),\n"
    "        )",
)

# Replace polling block in handle_prompt.
old = '''    async def on_success(url: str) -> None:
        from api.image_service import ImageResult as IR
        await repo.finish_generation(session, gen.id, url)
        await _send_image_result(
            bot, message.chat.id,
            IR(is_async=False, url=url), gen.id, prompt, status_msg,
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\\nКредиты возвращены.", reply_markup=main_menu_kb()
        )

    asyncio.create_task(
        polling.poll_until_done(
            result.task_id or "", image_service.poll_kieai_status, on_success, on_failure
        )
    )
    await state.clear()
'''
new = '''    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        model_key=model_key,
        credits=credits,
        aspect_ratio=aspect_ratio,
        count=count,
        quality=quality,
        image_file_id=image_file_id,
    )
    await status_msg.edit_text(
        "⏳ <b>Задача запущена.</b>\\n"
        "Пришлю результат, когда генерация будет готова.\\n\\n"
        "Настройки серии сохранены — можешь дождаться результата или продолжить позже.",
        reply_markup=image_session_kb(gen.id),
    )
'''
if old in s:
    s = s.replace(old, new)

# Update send result caption/kb.
s = s.replace(
    '    caption = f"✅ <b>Готово!</b>\\n\\n<i>{prompt[:200]}</i>"\n'
    '    kb = after_generation_kb(gen_id, "image")\n',
    '    caption = _session_caption(prompt)\n'
    '    kb = image_session_kb(gen_id)\n',
)

# Add session handlers before Regen section.
if "async def handle_session_prompt" not in s:
    session_handlers = '''

# ── Active image session ──────────────────────────────────────────────────────

@router.message(ImageGenFSM.session_active, F.text)
async def handle_session_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    image_session_id = data.get("image_session_id")
    image_session = (
        await repo.get_image_session(session, image_session_id, db_user.id)
        if image_session_id
        else await repo.get_active_image_session(session, db_user.id)
    )
    if not image_session:
        await message.answer("Серия не найдена. Начни новую генерацию.", reply_markup=main_menu_kb())
        await state.clear()
        return

    model_cost = await repo.get_model_cost(session, image_session.model)
    credits = model_cost.credits if model_cost else int(data.get("credits", 1))
    prompt = message.text.strip()  # type: ignore[union-attr]

    image_url = await _telegram_file_url(bot, image_session.reference_file_id)

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        return

    parent_id = image_session.last_generation_id
    gen = await repo.create_generation(
        session,
        db_user.id,
        image_session.model,
        GenerationType.image,
        prompt,
        credits,
        image_session_id=image_session.id,
        parent_generation_id=parent_id,
        action_type=ImageGenerationAction.remix,
    )

    status_msg = await message.answer(
        f"⏳ <b>Генерирую в активной серии...</b>\\n<code>{image_session.model}</code>"
    )

    try:
        result = await image_service.generate_image(
            ImageModel(image_session.model),
            prompt,
            image_url=image_url,
            aspect_ratio=image_session.aspect_ratio,
            n=image_session.count,
            quality=image_session.quality,
            callback_url=_kie_callback_url(),
        )
    except Exception as e:
        logger.error("Session image generation error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка генерации. Кредиты возвращены.", reply_markup=image_session_kb(parent_id))
        return

    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await state.update_data(image_session_id=image_session.id)
    await status_msg.edit_text(
        "⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
        reply_markup=image_session_kb(gen.id),
    )


@router.message(ImageGenFSM.session_active, F.photo)
async def handle_session_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    image_session_id = data.get("image_session_id")
    image_session = (
        await repo.get_image_session(session, image_session_id, db_user.id)
        if image_session_id
        else await repo.get_active_image_session(session, db_user.id)
    )
    if not image_session:
        await message.answer("Серия не найдена. Начни новую генерацию.", reply_markup=main_menu_kb())
        await state.clear()
        return

    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    await repo.update_image_session_reference(session, image_session.id, best[0].file_id)
    await state.update_data(image_file_id=best[0].file_id, image_session_id=image_session.id)
    await message.answer(
        "✅ Новый референс сохранён для активной серии. Теперь напиши, что изменить.",
        reply_markup=image_session_kb(image_session.last_generation_id),
    )


@router.callback_query(F.data == "img_session:new")
async def cb_image_session_new(call: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User) -> None:
    await repo.archive_active_image_sessions(session, db_user.id)
    await state.clear()
    await cb_image_menu(call, session, state)


@router.callback_query(F.data == "img_session:settings")
async def cb_image_session_settings(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await cb_image_menu(call, session, state)


@router.callback_query(F.data.startswith("img_session:remix:"))
async def cb_image_session_remix(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ImageGenFSM.session_active)
    await call.message.answer("✨ Напиши, что изменить в текущей картинке:")
    await call.answer()


@router.callback_query(F.data.startswith("img_session:repeat:"))
async def cb_image_session_repeat(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    image_session_id = data.get("image_session_id")
    image_session = (
        await repo.get_image_session(session, image_session_id, db_user.id)
        if image_session_id
        else await repo.get_active_image_session(session, db_user.id)
    )
    if not image_session:
        await call.answer("Серия не найдена", show_alert=True)
        return

    last_gen = await repo.get_last_session_generation(session, image_session.id)
    if not last_gen:
        await call.answer("Нечего повторять", show_alert=True)
        return

    fake_message = call.message
    if fake_message:
        await state.set_state(ImageGenFSM.session_active)
        await state.update_data(image_session_id=image_session.id)
        await fake_message.answer(last_gen.prompt)
    await call.answer("Повторяю последний промпт")


@router.callback_query(F.data.startswith("img_session:animate:"))
async def cb_image_session_animate(call: CallbackQuery) -> None:
    await call.answer("Оживление подключим следующим шагом через video image-to-video.", show_alert=True)

'''
    s = s.replace("\n# ── Regen", session_handlers + "\n# ── Regen")

write(str(p), s)

# ---------------------------------------------------------------------
# main.py
# ---------------------------------------------------------------------
p = Path("main.py")
s = read(str(p))

if "from api.kie_webhook import" not in s:
    s = s.replace(
        "from api.comet_client import close_client, get_client\n",
        "from api.comet_client import close_client, get_client\n"
        "from api.kie_webhook import extract_error, extract_result_urls, extract_task_id, is_success\n",
    )
if "ImageSession" not in s and "from db.models import Base" in s:
    s = s.replace(
        "from db.models import Base\n",
        "from db.models import Base, GenerationType\n",
    )

if "async def kie_webhook" not in s:
    endpoint = '''

# ── KIE.AI Webhook ────────────────────────────────────────────────────────────

@app.post(settings.KIE_WEBHOOK_PATH)
async def kie_webhook(request: Request, secret: str | None = None) -> dict:
    if settings.KIE_WEBHOOK_SECRET and secret != settings.KIE_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid KIE webhook secret")

    payload = await request.json()
    task_id = extract_task_id(payload)
    if not task_id:
        logger.warning("KIE webhook without task_id: %s", payload)
        return {"ok": True}

    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_task_id(session, task_id)
        if not gen:
            logger.warning("KIE webhook for unknown task_id=%s", task_id)
            return {"ok": True}

        # Idempotency: if already finished, acknowledge duplicate callback.
        if gen.status.value in {"done", "failed"}:
            return {"ok": True}

        user = await repo.get_user_by_id(session, gen.user_id)
        if not user:
            logger.warning("KIE webhook user not found for generation=%s", gen.id)
            return {"ok": True}

        if not is_success(payload):
            err = extract_error(payload)
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot:
                try:
                    await bot.send_message(
                        user.tg_id,
                        f"❌ Генерация не удалась.\\nКредиты возвращены.\\n\\n<code>{err[:500]}</code>",
                    )
                except Exception as e:
                    logger.warning("Failed to notify KIE failure user=%s: %s", user.tg_id, e)
            return {"ok": True}

        urls = extract_result_urls(payload)
        if not urls:
            err = "KIE callback success but no result urls"
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, gen.user_id, gen.credits_spent)
            if bot:
                try:
                    await bot.send_message(user.tg_id, f"❌ {err}. Кредиты возвращены.")
                except Exception as e:
                    logger.warning("Failed to notify empty KIE result user=%s: %s", user.tg_id, e)
            return {"ok": True}

        result_url = urls[0]
        await repo.finish_generation(session, gen.id, result_url)

        if gen.image_session_id:
            await repo.update_image_session_last_result(
                session,
                gen.image_session_id,
                result_url,
                gen.id,
            )

        if bot:
            try:
                from bot.keyboards.models import image_session_kb, after_generation_kb

                caption = f"✅ <b>Готово!</b>\\n\\n<i>{gen.prompt[:200]}</i>"
                if gen.gen_type == GenerationType.image:
                    caption += (
                        "\\n\\n🎨 <b>Серия активна.</b> "
                        "Можешь отправлять новый текст или фото — настройки сохранятся."
                    )
                    await bot.send_photo(
                        user.tg_id,
                        result_url,
                        caption=caption,
                        reply_markup=image_session_kb(gen.id),
                    )
                else:
                    await bot.send_video(
                        user.tg_id,
                        result_url,
                        caption=caption,
                        reply_markup=after_generation_kb(gen.id, "video"),
                    )
            except Exception as e:
                logger.warning("Failed to send KIE result user=%s gen=%s: %s", user.tg_id, gen.id, e)

    return {"ok": True}
'''
    s = s.replace("\n@app.get(\"/health\")", endpoint + "\n@app.get(\"/health\")")

write(str(p), s)

# ---------------------------------------------------------------------
# Alembic migration
# ---------------------------------------------------------------------
migration = Path("db/migrations/versions/003_image_sessions.py")
if not migration.exists():
    migration.write_text('''"""add image sessions

Revision ID: 003_image_sessions
Revises: 002_add_tbank_provider
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_image_sessions"
down_revision = "002_add_tbank_provider"
branch_labels = None
depends_on = None


image_session_status = sa.Enum("active", "archived", name="imagesessionstatus")
image_generation_action = sa.Enum(
    "initial",
    "remix",
    "repeat",
    "reference_update",
    "animate",
    name="imagegenerationaction",
)


def upgrade() -> None:
    bind = op.get_bind()
    image_session_status.create(bind, checkfirst=True)
    image_generation_action.create(bind, checkfirst=True)

    op.create_table(
        "image_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("aspect_ratio", sa.String(length=32), nullable=True),
        sa.Column("quality", sa.String(length=32), nullable=False, server_default="basic"),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("base_prompt", sa.Text(), nullable=True),
        sa.Column("reference_file_id", sa.Text(), nullable=True),
        sa.Column("last_result_url", sa.Text(), nullable=True),
        sa.Column("last_generation_id", sa.Integer(), nullable=True),
        sa.Column("status", image_session_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_image_sessions_user_id", "image_sessions", ["user_id"])
    op.create_index("ix_image_sessions_status", "image_sessions", ["status"])

    op.add_column("generations", sa.Column("image_session_id", sa.Integer(), nullable=True))
    op.add_column("generations", sa.Column("parent_generation_id", sa.Integer(), nullable=True))
    op.add_column("generations", sa.Column("action_type", image_generation_action, nullable=True))
    op.create_index("ix_generations_image_session_id", "generations", ["image_session_id"])
    op.create_index("ix_generations_task_id", "generations", ["task_id"])

    op.create_foreign_key(
        "fk_generations_image_session_id_image_sessions",
        "generations",
        "image_sessions",
        ["image_session_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_generations_parent_generation_id_generations",
        "generations",
        "generations",
        ["parent_generation_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_generations_parent_generation_id_generations", "generations", type_="foreignkey")
    op.drop_constraint("fk_generations_image_session_id_image_sessions", "generations", type_="foreignkey")
    op.drop_index("ix_generations_task_id", table_name="generations")
    op.drop_index("ix_generations_image_session_id", table_name="generations")
    op.drop_column("generations", "action_type")
    op.drop_column("generations", "parent_generation_id")
    op.drop_column("generations", "image_session_id")

    op.drop_index("ix_image_sessions_status", table_name="image_sessions")
    op.drop_index("ix_image_sessions_user_id", table_name="image_sessions")
    op.drop_table("image_sessions")

    bind = op.get_bind()
    image_generation_action.drop(bind, checkfirst=True)
    image_session_status.drop(bind, checkfirst=True)
''', encoding="utf-8")

print("Patch files updated.")
PY

echo "==> Running Python syntax check"
python -m compileall core api db bot main.py

echo
echo "==> Patch applied."
echo "Backup dir: $BACKUP_DIR"
echo
echo "Next:"
echo "  git diff"
echo "  alembic upgrade head"
echo "  systemctl restart artflow-webhook"
