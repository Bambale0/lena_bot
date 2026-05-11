"""Backward-compatible import bridge for legacy webapp auth imports."""

from api.miniapp_auth import _verify_init_data, get_miniapp_user

verify_telegram_init_data = _verify_init_data
get_webapp_user = get_miniapp_user
