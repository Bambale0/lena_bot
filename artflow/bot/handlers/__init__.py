"""Handler package bootstrap.

The UX v2 video wizard is registered before the legacy technical flow. This
keeps all old callbacks working while making task-first navigation the default.
"""
from aiogram import Router

from . import video_gen as _legacy_video_gen
from . import video_wizard as _video_wizard

_video_router = Router(name="video_v2")
_video_router.include_router(_video_wizard.router)
_video_router.include_router(_legacy_video_gen.router)
_legacy_video_gen.router = _video_router
