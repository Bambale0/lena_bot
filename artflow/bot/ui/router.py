from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.session_service import get_main_menu_context
from bot.ui.common import ScreenRender
from bot.ui.image_menu import render_active_image_session, render_image_advanced_menu, render_image_scenarios
from bot.ui.main_menu import render_main_menu
from bot.ui.music_menu import render_music_menu
from db import repository as repo
from db.models import User


async def render_screen(
    *,
    screen: str,
    session: AsyncSession,
    db_user: User,
    extra: dict | None = None,
) -> ScreenRender:
    payload = extra or {}

    if screen == "main":
        context = await get_main_menu_context(session, user_id=db_user.id, balance=db_user.credits)
        return render_main_menu(context)

    if screen == "image_active":
        image_session = payload.get("image_session") or await repo.get_active_image_session(session, db_user.id)
        if not image_session:
            return render_image_scenarios()
        return render_active_image_session(image_session)

    if screen == "image_entry":
        return render_image_scenarios()

    if screen == "image_advanced":
        model_costs = payload.get("model_costs") or await repo.get_all_model_costs(session)
        return render_image_advanced_menu(model_costs)

    if screen == "music":
        return render_music_menu(payload.get("last_style"))

    raise ValueError(f"Unknown screen: {screen}")
