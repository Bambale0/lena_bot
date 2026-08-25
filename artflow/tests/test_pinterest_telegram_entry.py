from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes
from api import pinterest_service_routes as pinterest_routes
from bot.ui.main_menu import render_main_menu


def test_main_menu_places_pinterest_flow_next_to_trends() -> None:
    context = SimpleNamespace(
        active_image_session=None,
        balance=9047.5,
        is_admin=True,
    )

    rendered = render_main_menu(context, "ru")
    rows = rendered.reply_markup.inline_keyboard
    trend_row = next(row for row in rows if any(button.callback_data == "menu:trends" for button in row))

    assert [button.text for button in trend_row] == ["👑 Тренды", "📌 Pinterest Flow"]
    pinterest_button = trend_row[1]
    assert pinterest_button.web_app is not None
    assert pinterest_button.web_app.url.endswith("/app?service=pinterest")


@pytest.mark.asyncio
async def test_pinterest_service_uses_miniapp_surface_so_result_reaches_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pinterest_routes, "_validate_runtime", AsyncMock())
    monkeypatch.setattr(pinterest_routes, "_service_price_credits", AsyncMock(return_value=2.0))
    monkeypatch.setattr(pinterest_routes, "_find_idempotent_run", AsyncMock(return_value=None))
    monkeypatch.setattr(pinterest_routes, "_scene_matched_ratio", lambda _url: "9:16")
    monkeypatch.setattr(pinterest_routes, "_patch_service_snapshot", AsyncMock())

    def verify_asset(asset_id: str, *, user_id: int, expected_kind: str):
        assert user_id == 42
        assert expected_kind == "image"
        suffix = "scene" if asset_id == "scene-asset" else "identity"
        return {"url": f"https://example.test/{suffix}.jpg"}

    monkeypatch.setattr(pinterest_routes, "verify_uploaded_asset", verify_asset)

    create_generation = AsyncMock(
        return_value=SimpleNamespace(
            id=321,
            model_dump=lambda: {
                "id": 321,
                "model": "nano-banana-pro",
                "gen_type": "image",
                "status": "pending",
                "credits_spent": 2.0,
            },
        )
    )
    monkeypatch.setattr(miniapp_routes, "create_image_generation", create_generation)

    session = SimpleNamespace(refresh=AsyncMock())
    user = SimpleNamespace(id=42, credits=98.0)
    body = pinterest_routes.PinterestServiceRunRequest(
        reference_asset_ids=["scene-asset", "identity-asset"],
        height_cm=175,
        weight_kg=75,
        confirmed=True,
        idempotency_key="pinterest-delivery-1",
    )

    response = await pinterest_routes.run_pinterest_service(body=body, session=session, user=user)

    assert response["ok"] is True
    create_generation.assert_awaited_once()
    surface = create_generation.await_args.kwargs["surface"]
    assert surface == "miniapp"

    stored_task_id = miniapp_routes.task_id_for_surface("provider-task-1", surface)
    assert stored_task_id == "provider-task-1"
    assert miniapp_routes.is_web_task_id(stored_task_id) is False
