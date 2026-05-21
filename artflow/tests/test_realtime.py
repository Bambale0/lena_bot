from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocketDisconnect

import api.realtime as realtime
from db.models import GenerationStatus, GenerationType


def _gen(**overrides):
    data = {
        "id": 77,
        "user_id": 42,
        "model": "nano-banana-2",
        "gen_type": GenerationType.image,
        "prompt": "test prompt",
        "status": GenerationStatus.done,
        "result_url": "https://cdn.test/1.png",
        "result_urls": json.dumps(["https://cdn.test/1.png", "https://cdn.test/2.png"]),
        "error_msg": None,
        "credits_spent": 10.0,
        "created_at": datetime(2026, 5, 16, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 5, 16, tzinfo=timezone.utc),
        "is_public_feed": False,
        "is_prompt_library": False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_generation_event_payload_matches_frontend_contract() -> None:
    payload = realtime.generation_event_payload(_gen())

    assert payload["type"] == "generation.updated"
    assert payload["generation_id"] == 77
    assert payload["id"] == 77
    assert payload["status"] == "done"
    assert payload["gen_type"] == "image"
    assert payload["prompt"] == "test prompt"
    assert payload["prompt_hidden"] is False
    assert payload["prompt_actions_allowed"] is True
    assert payload["result_urls"] == ["https://cdn.test/1.png", "https://cdn.test/2.png"]


def test_generation_event_payload_hides_feed_derivative_prompt() -> None:
    payload = realtime.generation_event_payload(_gen(source_feed_gen_id=12, prompt="secret prompt"))

    assert payload["prompt"] == ""
    assert payload["prompt_hidden"] is True
    assert payload["prompt_actions_allowed"] is False


@pytest.mark.asyncio
async def test_connection_manager_sends_only_to_target_user() -> None:
    manager = realtime.GenerationConnectionManager()
    owner_socket = AsyncMock()
    other_socket = AsyncMock()

    await manager.connect(42, owner_socket)
    await manager.connect(99, other_socket)
    await manager.send_to_user(42, {"type": "generation.updated", "id": 77})

    owner_socket.send_json.assert_awaited_once_with({"type": "generation.updated", "id": 77})
    other_socket.send_json.assert_not_awaited()


class _FakeWebSocket:
    def __init__(
        self,
        messages: list[dict] | None = None,
        query_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.sent: list[dict] = []
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.messages = list(messages or [])
        self.query_params = query_params or {}
        self.headers = headers or {}

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason or "")

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_json(self) -> dict:
        if self.messages:
            return self.messages.pop(0)
        raise WebSocketDisconnect()


@pytest.mark.asyncio
async def test_generation_ws_sends_snapshot(monkeypatch) -> None:
    user = SimpleNamespace(id=42, is_banned=False)
    monkeypatch.setattr(realtime, "_user_from_ws_auth", AsyncMock(return_value=user))
    monkeypatch.setattr(realtime.repo, "get_user_history", AsyncMock(return_value=[_gen(status=GenerationStatus.processing)]))
    websocket = _FakeWebSocket([{"type": "auth", "token": "test-token"}])

    await realtime.generation_updates_ws(websocket, session=object())

    assert websocket.accepted is True
    payload = websocket.sent[0]
    assert payload["type"] == "generation.snapshot"
    assert payload["items"][0]["generation_id"] == 77
    assert payload["items"][0]["status"] == "processing"


@pytest.mark.asyncio
async def test_generation_ws_accepts_legacy_query_auth(monkeypatch) -> None:
    user = SimpleNamespace(id=42, is_banned=False)
    auth = AsyncMock(return_value=user)
    monkeypatch.setattr(realtime, "_user_from_ws_auth", auth)
    monkeypatch.setattr(realtime.repo, "get_user_history", AsyncMock(return_value=[]))
    websocket = _FakeWebSocket(query_params={"token": "legacy-token"})

    await realtime.generation_updates_ws(websocket, session=object())

    auth.assert_awaited_once()
    assert websocket.sent[0] == {"type": "generation.snapshot", "items": []}


@pytest.mark.asyncio
async def test_generation_ws_accepts_legacy_header_auth(monkeypatch) -> None:
    user = SimpleNamespace(id=42, is_banned=False)
    auth = AsyncMock(return_value=user)
    monkeypatch.setattr(realtime, "_user_from_ws_auth", auth)
    monkeypatch.setattr(realtime.repo, "get_user_history", AsyncMock(return_value=[]))
    websocket = _FakeWebSocket(headers={"x-legacy-ws-token": "legacy-token"})

    await realtime.generation_updates_ws(websocket, session=object())

    auth.assert_awaited_once()
    assert websocket.sent[0] == {"type": "generation.snapshot", "items": []}
