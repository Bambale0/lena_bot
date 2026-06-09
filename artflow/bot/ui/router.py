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
    lang = db_user.language or "ru"

    if screen == "main":
        context = await get_main_menu_context(session, user_id=db_user.id, balance=db_user.credits)
        return render_main_menu(context, lang=lang, force_main_text=bool(payload.get("force_main_text")))

    if screen == "image_active":
        image_session = payload.get("image_session") or await repo.get_active_image_session(session, db_user.id)
        if not image_session:
            return render_image_scenarios()
        active_generation = payload.get("active_generation")
        prompt_actions_allowed = payload.get("prompt_actions_allowed")
        if active_generation is None:
            last_generation_id = getattr(image_session, "last_generation_id", None)
            if last_generation_id:
                active_generation = await repo.get_generation_by_id(session, last_generation_id)
        if prompt_actions_allowed is None and active_generation is not None:
            source_feed_gen_id = getattr(active_generation, "source_feed_gen_id", None)
            if source_feed_gen_id:
                source = await repo.get_generation_by_id(session, source_feed_gen_id)
                prompt_actions_allowed = bool(source and getattr(source, "user_id", None) == db_user.id)
        return render_active_image_session(
            image_session,
            active_generation=active_generation,
            prompt_actions_allowed=prompt_actions_allowed,
        )

    if screen == "image_entry":
        return render_image_scenarios()

    if screen == "image_advanced":
        model_costs = payload.get("model_costs") or await repo.get_all_model_costs(session)
        return render_image_advanced_menu(model_costs)

    if screen == "music":
        music_cost = payload.get("music_cost")
        music_model_name = payload.get("music_model_name")
        if music_cost is None:
            model_cost = await repo.get_first_active_model_cost(session, ["suno/v5.5", "suno/v5.0", "suno/v4.5"])
            if model_cost and getattr(model_cost, "is_active", True):
                music_cost = float(model_cost.credits)
                music_model_name = music_model_name or getattr(model_cost, "display_name", None)
        return render_music_menu(payload.get("last_style"), credits=music_cost, model_name=music_model_name)

    raise ValueError(f"Unknown screen: {screen}")
