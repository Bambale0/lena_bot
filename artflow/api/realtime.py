from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import _verify_init_data, verify_web_auth_token
from api.public_files import public_url_is_available
from db import repository as repo
from db.models import Generation, User
from db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["realtime"])


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _generation_result_urls(gen: Generation) -> list[str]:
    raw = getattr(gen, "result_urls", None)
    urls: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            parsed = []
        if isinstance(parsed, list):
            urls = [str(url) for url in parsed if url]
    urls = [url for url in urls if public_url_is_available(url)]
    if not urls and gen.result_url and public_url_is_available(str(gen.result_url)):
        urls = [str(gen.result_url)]
    return urls


def _generation_primary_result_url(gen: Generation) -> str | None:
    result_url = getattr(gen, "result_url", None)
    if result_url and public_url_is_available(str(result_url)):
        return str(result_url)
    urls = _generation_result_urls(gen)
    return urls[0] if urls else None


def generation_event_payload(gen: Generation) -> dict[str, Any]:
    return {
        "type": "generation.updated",
        "generation_id": gen.id,
        "id": gen.id,
        "model": gen.model,
        "gen_type": _enum_value(gen.gen_type),
        "prompt": gen.prompt,
        "status": _enum_value(gen.status),
        "result_url": _generation_primary_result_url(gen),
        "result_urls": _generation_result_urls(gen),
        "error": gen.error_msg,
        "credits_spent": float(gen.credits_spent or 0),
        "created_at": _iso(gen.created_at),
        "finished_at": _iso(gen.finished_at),
        "is_public_feed": bool(gen.is_public_feed),
        "is_prompt_library": bool(getattr(gen, "is_prompt_library", False)),
    }


class GenerationConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket, *, accept: bool = True) -> None:
        if accept:
            await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._connections.get(user_id, set()))
        if not sockets:
            return

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.debug("Realtime send failed user=%s: %s", user_id, exc)
                stale.append(websocket)

        if stale:
            async with self._lock:
                active = self._connections.get(user_id)
                if active:
                    for websocket in stale:
                        active.discard(websocket)
                    if not active:
                        self._connections.pop(user_id, None)

    async def active_count(self, user_id: int | None = None) -> int:
        async with self._lock:
            if user_id is not None:
                return len(self._connections.get(user_id, set()))
            return sum(len(items) for items in self._connections.values())


generation_ws_manager = GenerationConnectionManager()


async def _user_from_ws_auth(
    session: AsyncSession,
    *,
    token: str | None,
    init_data: str | None,
) -> User:
    try:
        if token:
            tg_id = verify_web_auth_token(token)
        elif init_data:
            tg_user = _verify_init_data(init_data)
            tg_id = tg_user.get("id")
        else:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Auth token required")
    except HTTPException as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc.detail)) from exc

    if not tg_id:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="No user id")

    user = await repo.get_user_by_tg_id(session, int(tg_id))
    if not user or getattr(user, "is_banned", False):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="User is not allowed")
    return user


async def publish_generation_event(gen: Generation | None) -> None:
    if not gen:
        return
    await generation_ws_manager.send_to_user(gen.user_id, generation_event_payload(gen))


async def _read_ws_auth(websocket: WebSocket) -> tuple[str | None, str | None]:
    headers = getattr(websocket, "headers", None)
    header_token = headers.get("x-legacy-ws-token") if headers is not None else None
    header_init_data = headers.get("x-legacy-ws-init-data") if headers is not None else None
    if header_init_data and "%" in header_init_data:
        header_init_data = unquote(header_init_data)
    if header_token or header_init_data:
        return (str(header_token) if header_token else None, str(header_init_data) if header_init_data else None)

    query_params = getattr(websocket, "query_params", None)
    legacy_token = query_params.get("token") if query_params is not None else None
    legacy_init_data = query_params.get("init_data") if query_params is not None else None
    if legacy_token or legacy_init_data:
        return (str(legacy_token) if legacy_token else None, str(legacy_init_data) if legacy_init_data else None)

    try:
        message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
    except WebSocketDisconnect:
        raise
    except asyncio.TimeoutError as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Auth timeout") from exc
    except Exception as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid auth payload") from exc

    if not isinstance(message, dict) or message.get("type") != "auth":
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Auth message required")

    token = message.get("token")
    init_data = message.get("init_data")
    return (str(token) if token else None, str(init_data) if init_data else None)


@router.websocket("/ws/generations")
async def generation_updates_ws(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_session),
) -> None:
    await websocket.accept()
    user: User | None = None
    try:
        token, init_data = await _read_ws_auth(websocket)
        user = await _user_from_ws_auth(session, token=token, init_data=init_data)
        await generation_ws_manager.connect(user.id, websocket, accept=False)

        history = await repo.get_user_history(session, user.id, limit=20)
        active = [gen for gen in history if _enum_value(gen.status) in {"pending", "processing"}]
        await websocket.send_json(
            {
                "type": "generation.snapshot",
                "items": [generation_event_payload(gen) for gen in active],
            }
        )

        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except WebSocketException as exc:
        await websocket.close(code=exc.code, reason=exc.reason or "")
    finally:
        if user is not None:
            await generation_ws_manager.disconnect(user.id, websocket)
