from __future__ import annotations

from pathlib import Path

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


def test_telegram_video_prompt_splits_long_result_without_truncation() -> None:
    from bot.utils.telegram_ui import split_text_chunks

    prompt = ("Первый блок. " * 400) + "\n\n" + ("Второй блок. " * 400)
    clean = prompt.strip()
    chunks = split_text_chunks(prompt, max_chars=3000)

    assert len(chunks) > 1
    assert "".join(chunks) == clean
    assert all(len(chunk) <= 3000 for chunk in chunks)

    handler = Path("bot/handlers/video_prompt.py").read_text(encoding="utf-8")
    assert "_MAX_PROMPT_MESSAGE_CHARS" not in handler
    assert "сокращённая версия" not in handler
    assert "split_text_chunks(prompt, max_chars=_MAX_PROMPT_CHUNK_CHARS)" in handler
    assert "for result_message in _result_messages(prompt, credits=credits):" in handler
    assert "Часть {index}/{total}" in handler
