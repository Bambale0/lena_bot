"""Mini App admin-only UI permissions.

The frontend hides the raw model selector for normal users. It asks this tiny
authenticated endpoint whether the current Telegram user is an admin, instead of
shipping ADMIN_IDS to the browser.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends

from core.config import settings


def install_admin_model_visibility(routes: Any) -> None:
    if getattr(routes, "_admin_model_visibility_installed", False):
        return

    @routes.router.get("/me/permissions")
    async def miniapp_permissions(user=Depends(routes.get_miniapp_user)) -> dict[str, bool]:
        tg_id = getattr(user, "tg_id", None)
        return {"is_admin": bool(tg_id and tg_id in settings.ADMIN_IDS)}

    routes._admin_model_visibility_installed = True
