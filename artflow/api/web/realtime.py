from __future__ import annotations

from fastapi import APIRouter

from api.realtime import generation_updates_ws

router = APIRouter(tags=["web"])
router.add_api_websocket_route("/ws/generations", generation_updates_ws)
