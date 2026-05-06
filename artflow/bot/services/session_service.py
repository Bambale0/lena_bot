from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db import repository as repo
from db.models import ImageSession


@dataclass(frozen=True)
class MainMenuContext:
    balance: int
    active_image_session: ImageSession | None
    is_admin: bool


async def get_main_menu_context(
    session: AsyncSession,
    *,
    user_id: int,
    balance: int,
) -> MainMenuContext:
    image_session = await repo.get_active_image_session(session, user_id)
    user = await repo.get_user_by_id(session, user_id)
    is_admin = bool(user and user.tg_id in settings.ADMIN_IDS)
    return MainMenuContext(balance=balance, active_image_session=image_session, is_admin=is_admin)
