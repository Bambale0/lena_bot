from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from api import miniapp_routes, video_prompt_service
from api.web import generations as web_generations
from bot.handlers import video_prompt as telegram_video_prompt
from db.models import GenerationType
from db.seed import DEFAULT_MODEL_COSTS


def test_video_prompt_seed_cost_is_admin_editable_model_cost() -> None:
    rows = [item for item in DEFAULT_MODEL_COSTS if item["model_key"] == "llm.video-prompt"]

    assert len(rows) == 1
    assert rows[0]["display_name"] == "🎬 Видео → промпт"
    assert rows[0]["gen_type"] == GenerationType.video
    assert rows[0]["credits"] == 3


def test_miniapp_api_client_exposes_video_prompt_next_to_photo_prompt() -> None:
    api = Path("webapp/src/lib/api.ts").read_text(encoding="utf-8")
    types = Path("webapp/src/lib/types.ts").read_text(encoding="utf-8")
    services = Path("webapp/src/features/services-screen.tsx").read_text(encoding="utf-8")
    app = Path("webapp/src/app/App.tsx").read_text(encoding="utf-8")
    legacy = Path("webapp/src/main.jsx").read_text(encoding="utf-8")
    v4_api = Path("webapp/src/apix/api.js").read_text(encoding="utf-8")
    v4_app = Path("webapp/src/apix/AppV4.jsx").read_text(encoding="utf-8")

    assert '"/photo-prompt"' in api
    assert '"/video-prompt"' in api
    assert "videoPrompt(file: File)" in api
    assert "export interface VideoPromptResult" in types
    assert "videoPromptBusy" in services
    assert "onVideoPrompt" in services
    assert "accept=\"video/mp4,video/quicktime,video/webm\"" in services
    assert "createVideoPrompt" in app
    assert "videoPromptApi(file)" in legacy
    assert 'accept="video/mp4,video/quicktime,video/webm"' in legacy
    assert "export async function videoPrompt(file)" in v4_api
    assert "handleVideoPrompt" in v4_app


def test_telegram_bot_exposes_video_prompt_and_uses_configured_billing() -> None:
    handler = Path("bot/handlers/video_prompt.py").read_text(encoding="utf-8")
    routers = Path("bot/handlers/__init__.py").read_text(encoding="utf-8")
    menus = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "bot/keyboards/models.py",
            "bot/ui/image_menu.py",
            "bot/ui/navigation_v2.py",
        )
    )

    assert 'VIDEO_PROMPT_MODEL_KEY = "llm.video-prompt"' in Path(
        "api/video_prompt_service.py"
    ).read_text(encoding="utf-8")
    assert "repo.get_model_cost(session, VIDEO_PROMPT_MODEL_KEY)" in handler
    assert 'entry_type="video_prompt_spend"' in handler
    assert 'entry_type="video_prompt_refund"' in handler
    assert "_video_prompt.router" in routers
    assert menus.count("vid:video2prompt") >= 3


# Exercise the real shared parser through each surface; only external IO/billing
# is mocked. No provider request, database write or Telegram send is performed.


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["telegram", "miniapp", "web"])
@pytest.mark.parametrize("failed,missing_video", [
    (True, False),
    (False, False),
    (True, True),
])
async def test_video_prompt_provider_completion_settles_once(
    monkeypatch, surface, failed, missing_video,
):
    failure = (
        "The request could not be completed. Please retry later, "
        "or reduce the request parameters/content."
    )
    missing = (
        "A. Ready-to-use prompt\n"
        "Невозможно составить точный генерационный промпт, потому что видео "
        "не было прикреплено.\n"
        "B. Что я увидел\nВидеоматериал отсутствует."
    )
    text = missing if missing_video else failure if failed else "Камера плавно движется вдоль берега."
    post = AsyncMock(return_value={"choices": [{"message": {"content": text}}]})
    monkeypatch.setattr(video_prompt_service, "_post_json", post)
    handler = telegram_video_prompt if surface == "telegram" else miniapp_routes
    spend = AsyncMock(return_value=True)
    refund = AsyncMock()
    monkeypatch.setattr(handler.repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(
        credits=3.0, is_active=True, display_name="Видео → промпт",
    )))
    monkeypatch.setattr(handler.repo, "spend_credits", spend)
    monkeypatch.setattr(handler.repo, "add_credits", refund)
    monkeypatch.setattr(handler, "save_public_file", MagicMock(return_value="https://example.test/video.mp4"))
    cleanup = MagicMock(return_value=True)
    monkeypatch.setattr(handler, "delete_public_file", cleanup)
    raw = b"\x00\x00\x00\x18ftypmp42payload"
    session = AsyncMock()
    user = SimpleNamespace(id=42, credits=100.0)
    if surface == "telegram":
        monkeypatch.setattr(handler, "_download_telegram_file", AsyncMock(return_value=raw))
        wait = AsyncMock()
        message = AsyncMock()
        message.answer.return_value = wait
        state = AsyncMock()
        await handler._analyse_video(
            message=message, state=state, session=session, db_user=user, bot=AsyncMock(),
            file_id="fixture-video", mime_type="video/mp4", file_size=len(raw),
        )
        sent = [call.args[0] for call in message.answer.await_args_list]
        if failed:
            assert not any("промпт готов" in item for item in sent)
            assert all(failure not in item and missing not in item for item in sent)
            wait.edit_text.assert_awaited_once()
            state.clear.assert_not_awaited()
        else:
            assert any("промпт готов" in item and text in item for item in sent)
            state.clear.assert_awaited_once()
    else:
        upload = UploadFile(file=io.BytesIO(raw), filename="clip.mp4", headers=Headers({"content-type": "video/mp4"}))
        if surface == "miniapp" and failed:
            with pytest.raises(HTTPException) as exc:
                await handler.miniapp_video_prompt(file=upload, session=session, user=user)
            assert exc.value.status_code == 502
            assert failure not in str(exc.value.detail)
        elif surface == "miniapp":
            result = await handler.miniapp_video_prompt(file=upload, session=session, user=user)
            assert result["prompt"] == text
        else:
            result = await web_generations.video_prompt(file=upload, session=session, user=user)
            if failed:
                assert result.status_code == 502
                assert failure.encode() not in result.body
            else:
                assert text in str(result)
    spend.assert_awaited_once()
    post.assert_awaited_once()  # No automatic paid retries.
    cleanup.assert_called_once_with("https://example.test/video.mp4")
    if failed:
        refund.assert_awaited_once()
        assert refund.await_args.args == (session, 42, 3.0)
        assert refund.await_args.kwargs["entry_type"] == "video_prompt_refund"
        assert refund.await_args.kwargs["source_id"] == spend.await_args.kwargs["source_id"]
    else:
        refund.assert_not_awaited()
