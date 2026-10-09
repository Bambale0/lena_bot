from __future__ import annotations

import asyncio
import io
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from api import miniapp_routes, video_prompt_service
from api.web import generations as web_generations
from bot.handlers import video_prompt as telegram_video_prompt
from db.models import GenerationType
from db.seed import DEFAULT_MODEL_COSTS


def _nginx_block(text: str, marker: str) -> str:
    assert marker in text, f"Missing Nginx block: {marker}"
    start = text.index("{", text.index(marker)) + 1
    depth = 1
    for index in range(start, len(text)):
        depth += (text[index] == "{") - (text[index] == "}")
        if not depth:
            return text[start:index]
    raise AssertionError(f"Unclosed Nginx block: {marker}")


@pytest.mark.parametrize("host", ["apixbotai.com", "testapi.chillcreative.ru apix.chillcreative.ru"])
def test_video_prompt_ingress_scopes_large_uploads_and_wait_budget_to_exact_routes(host) -> None:
    config = Path("nginx.conf").read_text(encoding="utf-8")
    servers = [_nginx_block(config[match.start():], "server") for match in re.finditer(r"^server \{", config, re.M)]
    server = next(block for block in servers if "listen 443 ssl;" in block and f"server_name {host};" in block)
    generic = _nginx_block(server, "location / {")
    assert re.search(r"client_max_body_size\s+35M;", server.split("location", 1)[0])
    assert "proxy_read_timeout 120s;" in generic
    for route in ("/api/v1/video-prompt", "/api/web/video-prompt"):
        location = _nginx_block(server, f"location = {route} {{")
        assert "client_max_body_size 101M;" in location  # 100 MiB file + multipart envelope.
        assert "proxy_read_timeout 240s;" in location
        assert "proxy_pass http://app:8000;" in location
        for header in ("Host $host", "X-Real-IP $remote_addr", "X-Forwarded-For $proxy_add_x_forwarded_for", "X-Forwarded-Proto $scheme"):
            assert f"proxy_set_header {header};" in location
    assert len(re.findall(r"client_max_body_size\s+101M;", server)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["miniapp", "web"])
@pytest.mark.parametrize("extra_bytes", [0, 1])
async def test_video_prompt_upload_boundary_uses_bounded_read_before_billing(monkeypatch, surface, extra_bytes):
    # Scale the existing 100 MiB product cap for the boundary test, not the read behavior.
    assert miniapp_routes.MAX_VIDEO_PROMPT_BYTES == 100 * 1024 * 1024
    raw = b"\x00\x00\x00\x18ftypmp42payload"
    limit = len(raw)
    monkeypatch.setattr(miniapp_routes, "MAX_VIDEO_PROMPT_BYTES", limit)
    upload = UploadFile(file=io.BytesIO(raw + b"x" * extra_bytes), filename="clip.mp4", headers=Headers({"content-type": "video/mp4"}))
    read = AsyncMock(wraps=upload.read)
    upload.read = read
    spend = AsyncMock(return_value=True)
    provider = AsyncMock(return_value=SimpleNamespace(text="valid prompt"))
    save = MagicMock(return_value="https://example.test/clip.mp4")
    monkeypatch.setattr(miniapp_routes.repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=3.0, is_active=True)))
    monkeypatch.setattr(miniapp_routes.repo, "spend_credits", spend)
    monkeypatch.setattr(miniapp_routes, "generate_prompt_from_video_url", provider)
    monkeypatch.setattr(miniapp_routes, "save_public_file", save)
    monkeypatch.setattr(miniapp_routes, "delete_public_file", MagicMock(return_value=True))
    handler = miniapp_routes.miniapp_video_prompt if surface == "miniapp" else web_generations.video_prompt
    kwargs = {"file": upload, "session": AsyncMock(), "user": SimpleNamespace(id=42)}
    if extra_bytes and surface == "miniapp":
        with pytest.raises(HTTPException) as error:
            await handler(**kwargs)
        assert error.value.status_code == 413
    else:
        result = await handler(**kwargs)
        if extra_bytes:
            assert result.status_code == 413
        else:
            assert "valid prompt" in str(result)
    read.assert_awaited_once_with(limit + 1)
    if extra_bytes:
        spend.assert_not_awaited()
        provider.assert_not_awaited()
        save.assert_not_called()
    else:
        spend.assert_awaited_once()
        provider.assert_awaited_once()


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
@pytest.mark.parametrize("completion", ["failure", "malformed_text", "malformed_choices", "timeout", "success"])
async def test_video_prompt_provider_completion_settles_once(monkeypatch, surface, completion):
    failure = (
        "The request could not be completed. Please retry later, "
        "or reduce the request parameters/content."
    )
    failed = completion != "success"
    text = failure if failed else "Камера плавно движется вдоль берега."
    payload = {"choices": [{"message": {"content": text}}]}
    if completion == "malformed_text":
        payload = {"choices": [{"message": {"content": [
            {"type": "text", "text": {"error": failure}},
        ]}}]}
    elif completion == "malformed_choices":
        payload = {"choices": {"message": {"content": failure}}}
    post = AsyncMock(return_value=payload)
    if completion == "timeout":
        async def late_response(*args, **kwargs):
            await asyncio.sleep(0)
            return httpx.Response(200, json=payload, request=httpx.Request("POST", "https://example.test/provider"))

        client = AsyncMock()
        client.__aenter__.return_value = client
        post = client.post = AsyncMock(side_effect=late_response)
        monkeypatch.setattr(video_prompt_service.httpx, "AsyncClient", lambda **kwargs: client)
        monkeypatch.setattr(video_prompt_service, "asyncio", SimpleNamespace(timeout=lambda seconds: asyncio.timeout(0)))
    else:
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
            assert all(failure not in item for item in sent)
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
